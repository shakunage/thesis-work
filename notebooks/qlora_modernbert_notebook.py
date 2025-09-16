# QLoRA Fine-tuning for ModernBERT - Complete Notebook
# Optimized for sentiment analysis and resource-efficient training

# ============================================================================
# SECTION 1: SETUP AND INSTALLATIONS
# ============================================================================

# Install required packages (run this cell first)
!pip install transformers==4.36.0
!pip install datasets==2.14.0
!pip install peft==0.6.0
!pip install bitsandbytes==0.41.3
!pip install accelerate==0.24.0
!pip install torch torchvision torchaudio
!pip install scikit-learn
!pip install wandb  # Optional: for experiment tracking

# ============================================================================
# SECTION 2: IMPORTS AND CONFIGURATION
# ============================================================================

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
import json
import os
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# Transformers and PEFT imports
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding,
    BitsAndBytesConfig,
    get_linear_schedule_with_warmup
)
from peft import (
    LoraConfig,
    TaskType,
    get_peft_model,
    prepare_model_for_kbit_training,
    PeftModel
)
from datasets import Dataset

# Configuration
class Config:
    # Model settings
    model_name = "answerdotai/ModernBERT-base"  # Use base for resource efficiency
    # Alternative: "answerdotai/ModernBERT-large" for better performance
    
    # QLoRA settings
    load_in_4bit = True
    bnb_4bit_compute_dtype = torch.bfloat16
    bnb_4bit_use_double_quant = True
    bnb_4bit_quant_type = "nf4"
    
    # LoRA settings
    lora_r = 16  # Rank - higher = more parameters but better performance
    lora_alpha = 32  # Scaling factor
    lora_dropout = 0.1
    lora_bias = "none"
    target_modules = ["query", "key", "value", "dense"]  # Which layers to apply LoRA
    
    # Training settings
    max_seq_length = 512
    batch_size = 8  # Adjust based on your GPU memory
    gradient_accumulation_steps = 4  # Effective batch size = 8 * 4 = 32
    learning_rate = 2e-4  # Higher than standard fine-tuning due to LoRA
    num_epochs = 3
    warmup_steps = 100
    weight_decay = 0.01
    logging_steps = 10
    save_steps = 500
    eval_steps = 500
    
    # Data settings
    num_labels = 3  # negative, neutral, positive
    label_names = ["negative", "neutral", "positive"]
    
    # Output settings
    output_dir = "./qlora_modernbert_results"
    logging_dir = "./logs"
    
config = Config()

print(f"Using device: {torch.cuda.get_device_name() if torch.cuda.is_available() else 'CPU'}")
print(f"Model: {config.model_name}")
print(f"LoRA rank: {config.lora_r}, alpha: {config.lora_alpha}")

# ============================================================================
# SECTION 3: DATA PREPARATION
# ============================================================================

class SentimentDataset(Dataset):
    """Custom dataset class for sentiment analysis"""
    
    def __init__(self, texts, labels, tokenizer, max_length=512):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        # Tokenize text
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }

def create_sample_data():
    """Create sample sentiment data - replace with your actual dataset"""
    sample_data = {
        'text': [
            "The stock market showed strong gains today",
            "Company profits are declining rapidly",
            "Economic indicators remain stable",
            "Investors are optimistic about future growth",
            "Market volatility continues to concern traders",
            "The quarterly earnings report exceeded expectations",
            "Bond yields are falling significantly",
            "Consumer confidence has improved this month",
            "The central bank maintains current interest rates",
            "Tech stocks experienced mixed trading results"
        ] * 100,  # Repeat for more data
        'label': [2, 0, 1, 2, 0, 2, 0, 2, 1, 1] * 100  # 0=negative, 1=neutral, 2=positive
    }
    return pd.DataFrame(sample_data)

def prepare_dataset():
    """Prepare and split dataset"""
    # Load your data here - replace with actual data loading
    df = create_sample_data()
    
    # For Finnish data, you might load like this:
    # df = pd.read_csv('finnish_sentiment_data.csv')
    # df['label'] = df['sentiment'].map({'negative': 0, 'neutral': 1, 'positive': 2})
    
    print(f"Dataset shape: {df.shape}")
    print(f"Label distribution:\n{df['label'].value_counts()}")
    
    # Split data
    train_texts, temp_texts, train_labels, temp_labels = train_test_split(
        df['text'].tolist(), 
        df['label'].tolist(), 
        test_size=0.3, 
        random_state=42, 
        stratify=df['label']
    )
    
    val_texts, test_texts, val_labels, test_labels = train_test_split(
        temp_texts, 
        temp_labels, 
        test_size=0.5, 
        random_state=42, 
        stratify=temp_labels
    )
    
    print(f"Train samples: {len(train_texts)}")
    print(f"Validation samples: {len(val_texts)}")
    print(f"Test samples: {len(test_texts)}")
    
    return (train_texts, train_labels), (val_texts, val_labels), (test_texts, test_labels)

# ============================================================================
# SECTION 4: MODEL AND TOKENIZER SETUP
# ============================================================================

def setup_model_and_tokenizer():
    """Setup quantized model and tokenizer"""
    
    # BitsAndBytesConfig for 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.load_in_4bit,
        bnb_4bit_compute_dtype=config.bnb_4bit_compute_dtype,
        bnb_4bit_use_double_quant=config.bnb_4bit_use_double_quant,
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
    )
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # Load model with quantization
    model = AutoModelForSequenceClassification.from_pretrained(
        config.model_name,
        num_labels=config.num_labels,
        quantization_config=bnb_config,
        device_map="auto",  # Automatically distribute across available GPUs
        torch_dtype=torch.bfloat16,
        trust_remote_code=True
    )
    
    # Prepare model for k-bit training
    model = prepare_model_for_kbit_training(model)
    
    # Print model info
    print(f"Model loaded: {config.model_name}")
    print(f"Model parameters: {model.num_parameters():,}")
    print(f"Model device: {next(model.parameters()).device}")
    
    return model, tokenizer

def setup_lora(model):
    """Setup LoRA configuration and apply to model"""
    
    # LoRA configuration
    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,  # Sequence classification
        inference_mode=False,
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.target_modules,
        bias=config.lora_bias,
    )
    
    # Apply LoRA
    model = get_peft_model(model, lora_config)
    
    # Print trainable parameters
    model.print_trainable_parameters()
    
    return model

# ============================================================================
# SECTION 5: TRAINING SETUP
# ============================================================================

def compute_metrics(eval_pred):
    """Compute accuracy and other metrics"""
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)
    
    accuracy = accuracy_score(labels, predictions)
    
    return {
        'accuracy': accuracy,
    }

def create_trainer(model, tokenizer, train_dataset, val_dataset):
    """Create Hugging Face Trainer"""
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        per_device_eval_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_steps=config.warmup_steps,
        logging_dir=config.logging_dir,
        logging_steps=config.logging_steps,
        evaluation_strategy="steps",
        eval_steps=config.eval_steps,
        save_steps=config.save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        dataloader_pin_memory=False,  # Can help with memory on some systems
        gradient_checkpointing=True,  # Save memory at cost of speed
        fp16=torch.cuda.is_available(),  # Use mixed precision if available
        report_to=None,  # Disable wandb for now
        remove_unused_columns=False,
    )
    
    # Data collator
    data_collator = DataCollatorWithPadding(
        tokenizer=tokenizer,
        padding=True,
        max_length=config.max_seq_length
    )
    
    # Create trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )
    
    return trainer

# ============================================================================
# SECTION 6: MAIN TRAINING FUNCTION
# ============================================================================

def main_training_pipeline():
    """Main training pipeline"""
    
    print("=" * 50)
    print("STARTING QLORA MODERNBERT FINE-TUNING")
    print("=" * 50)
    
    # 1. Prepare data
    print("\n1. Preparing dataset...")
    (train_texts, train_labels), (val_texts, val_labels), (test_texts, test_labels) = prepare_dataset()
    
    # 2. Setup model and tokenizer
    print("\n2. Setting up model and tokenizer...")
    model, tokenizer = setup_model_and_tokenizer()
    
    # 3. Apply LoRA
    print("\n3. Applying LoRA...")
    model = setup_lora(model)
    
    # 4. Create datasets
    print("\n4. Creating datasets...")
    train_dataset = SentimentDataset(train_texts, train_labels, tokenizer, config.max_seq_length)
    val_dataset = SentimentDataset(val_texts, val_labels, tokenizer, config.max_seq_length)
    test_dataset = SentimentDataset(test_texts, test_labels, tokenizer, config.max_seq_length)
    
    # Convert to HF datasets
    train_hf_dataset = Dataset.from_dict({
        'input_ids': [item['input_ids'] for item in train_dataset],
        'attention_mask': [item['attention_mask'] for item in train_dataset],
        'labels': [item['labels'] for item in train_dataset]
    })
    
    val_hf_dataset = Dataset.from_dict({
        'input_ids': [item['input_ids'] for item in val_dataset],
        'attention_mask': [item['attention_mask'] for item in val_dataset],
        'labels': [item['labels'] for item in val_dataset]
    })
    
    # 5. Create trainer
    print("\n5. Creating trainer...")
    trainer = create_trainer(model, tokenizer, train_hf_dataset, val_hf_dataset)
    
    # 6. Start training
    print("\n6. Starting training...")
    print(f"Training for {config.num_epochs} epochs")
    print(f"Effective batch size: {config.batch_size * config.gradient_accumulation_steps}")
    
    # Clear cache before training
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    # Train!
    trainer.train()
    
    # 7. Save final model
    print("\n7. Saving final model...")
    final_model_path = os.path.join(config.output_dir, "final_model")
    trainer.save_model(final_model_path)
    tokenizer.save_pretrained(final_model_path)
    
    # 8. Evaluate on test set
    print("\n8. Evaluating on test set...")
    test_results = evaluate_model(model, tokenizer, test_texts, test_labels)
    print(f"Test Results: {test_results}")
    
    print("\n" + "=" * 50)
    print("TRAINING COMPLETED SUCCESSFULLY!")
    print(f"Model saved to: {final_model_path}")
    print("=" * 50)
    
    return model, tokenizer, test_results

# ============================================================================
# SECTION 7: EVALUATION FUNCTIONS
# ============================================================================

def evaluate_model(model, tokenizer, test_texts, test_labels):
    """Evaluate model on test set"""
    model.eval()
    
    predictions = []
    true_labels = test_labels
    
    # Create test dataset
    test_dataset = SentimentDataset(test_texts, test_labels, tokenizer, config.max_seq_length)
    test_dataloader = DataLoader(test_dataset, batch_size=config.batch_size, shuffle=False)
    
    with torch.no_grad():
        for batch in tqdm(test_dataloader, desc="Evaluating"):
            input_ids = batch['input_ids'].to(model.device)
            attention_mask = batch['attention_mask'].to(model.device)
            
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits
            
            batch_predictions = torch.argmax(logits, dim=-1).cpu().numpy()
            predictions.extend(batch_predictions)
    
    # Calculate metrics
    accuracy = accuracy_score(true_labels, predictions)
    
    # Print detailed results
    print(f"\nTest Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(true_labels, predictions, target_names=config.label_names))
    
    print("\nConfusion Matrix:")
    print(confusion_matrix(true_labels, predictions))
    
    return {
        'accuracy': accuracy,
        'predictions': predictions,
        'true_labels': true_labels
    }

def predict_sentiment(text, model, tokenizer):
    """Predict sentiment for a single text"""
    model.eval()
    
    # Tokenize
    encoding = tokenizer(
        text,
        truncation=True,
        padding='max_length',
        max_length=config.max_seq_length,
        return_tensors='pt'
    )
    
    # Move to device
    input_ids = encoding['input_ids'].to(model.device)
    attention_mask = encoding['attention_mask'].to(model.device)
    
    # Predict
    with torch.no_grad():
        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        logits = outputs.logits
        probabilities = torch.softmax(logits, dim=-1)
        predicted_class = torch.argmax(logits, dim=-1).item()
    
    return {
        'predicted_label': config.label_names[predicted_class],
        'predicted_class': predicted_class,
        'probabilities': {
            label: prob.item() 
            for label, prob in zip(config.label_names, probabilities[0])
        },
        'confidence': probabilities[0][predicted_class].item()
    }

# ============================================================================
# SECTION 8: UTILITY FUNCTIONS
# ============================================================================

def save_config():
    """Save configuration to JSON"""
    config_dict = {k: v for k, v in config.__dict__.items() if not k.startswith('_')}
    # Convert non-serializable items
    config_dict['bnb_4bit_compute_dtype'] = str(config_dict['bnb_4bit_compute_dtype'])
    
    with open(os.path.join(config.output_dir, 'training_config.json'), 'w') as f:
        json.dump(config_dict, f, indent=2)

def load_trained_model(model_path):
    """Load a trained LoRA model"""
    # Load base model
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.load_in_4bit,
        bnb_4bit_compute_dtype=config.bnb_4bit_compute_dtype,
        bnb_4bit_use_double_quant=config.bnb_4bit_use_double_quant,
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
    )
    
    base_model = AutoModelForSequenceClassification.from_pretrained(
        config.model_name,
        num_labels=config.num_labels,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True
    )
    
    # Load LoRA weights
    model = PeftModel.from_pretrained(base_model, model_path)
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    
    return model, tokenizer

# ============================================================================
# SECTION 9: EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Create output directory
    os.makedirs(config.output_dir, exist_ok=True)
    
    # Save configuration
    save_config()
    
    # Run training
    model, tokenizer, test_results = main_training_pipeline()
    
    # Test prediction on sample texts
    print("\n" + "=" * 50)
    print("TESTING PREDICTIONS")
    print("=" * 50)
    
    sample_texts = [
        "The company's quarterly earnings exceeded all expectations with strong revenue growth.",
        "Stock prices fell dramatically due to market uncertainty and economic concerns.",
        "The financial report shows stable performance with no significant changes."
    ]
    
    for text in sample_texts:
        result = predict_sentiment(text, model, tokenizer)
        print(f"\nText: {text}")
        print(f"Predicted: {result['predicted_label']} (confidence: {result['confidence']:.3f})")
        print(f"Probabilities: {result['probabilities']}")

# ============================================================================
# SECTION 10: MEMORY OPTIMIZATION TIPS
# ============================================================================

"""
Memory Optimization Tips for M4 MacBook Air:

1. Reduce batch_size if you get OOM errors:
   config.batch_size = 4 or even 2

2. Increase gradient_accumulation_steps to maintain effective batch size:
   config.gradient_accumulation_steps = 8

3. Reduce max_seq_length for shorter texts:
   config.max_seq_length = 256

4. Use smaller LoRA rank:
   config.lora_r = 8

5. Enable gradient checkpointing (already enabled):
   gradient_checkpointing=True

6. Clear cache frequently:
   torch.cuda.empty_cache() if torch.cuda.is_available()

7. Use base model instead of large:
   model_name = "answerdotai/ModernBERT-base"
"""

print("\n🎉 Notebook setup complete! Run main_training_pipeline() to start training.")