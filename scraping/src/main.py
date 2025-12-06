import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
import yaml
from scrapers.kauppalehti_scraper import kauppalehti_scraper

# Create logs directory and setup logging
logs_dir = Path(__file__).parent.parent / "logs"
logs_dir.mkdir(exist_ok=True)

# Create log filename with current datetime
log_filename = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_filepath = logs_dir / log_filename

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filepath, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"Logging to {log_filepath}")

def main():
    logger.info("Starting scraping process")
    
    # Load URLs from YAML file
    input_file = Path(__file__).parent.parent / "input_data" / "urls_kauppalehti.yaml"
    output_dir = Path(__file__).parent.parent / "output_data"
    output_dir.mkdir(exist_ok=True)
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            urls_data = yaml.safe_load(f)
        logger.info(f"Loaded {len(urls_data)} URLs from {input_file}")
    except FileNotFoundError:
        logger.error(f"Input file not found: {input_file}")
        return
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        return
    except Exception as e:
        logger.error(f"Unexpected error loading input file: {e}")
        return
    
    successful_scrapes = 0
    failed_scrapes = 0
    total_posts = 0
    
    # Process each URL
    for idx, item in enumerate(urls_data, 1):
        url = item.get('url')
        company = item.get('company')
        ticker = item.get('ticker')
        
        if not all([url, company, ticker]):
            logger.warning(f"Skipping item {idx}: missing required fields (url, company, or ticker)")
            failed_scrapes += 1
            continue
        
        logger.info(f"[{idx}/{len(urls_data)}] Scraping {company} ({ticker}) from {url}")
        
        try:
            posts = kauppalehti_scraper(url, company, ticker)
            total_posts += len(posts)
            successful_scrapes += 1
            logger.info(f"Successfully scraped {len(posts)} posts from {company}")
            
            # Add delay between threads to be respectful
            if idx < len(urls_data):
                import time
                wait_time = random.uniform(3, 5)
                logger.debug(f"Waiting {wait_time:.1f}s before next thread")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"Failed to scrape {company} ({ticker}): {e}", exc_info=True)
            failed_scrapes += 1
            continue
    
    logger.info(f"Scraping complete. Total posts: {total_posts}, Successful threads: {successful_scrapes}, Failed threads: {failed_scrapes}")

if __name__ == "__main__":
    main()