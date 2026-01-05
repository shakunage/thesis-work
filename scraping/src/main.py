import logging
import random
import sys
from datetime import datetime
from pathlib import Path
import yaml
from scrapers.kauppalehti_scraper import kauppalehti_scraper
from scrapers.sijoitustieto_scraper import sijoitustieto_scraper
from scrapers.inderes_scraper import inderes_scraper
from scrapers.yahoofinance_scraper import yahoofinance_scraper

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
    # Possible values for forum argument: kauppalehti, sijoitustieto, inderes, yahoofinance
    if len(sys.argv) < 2:
        logger.error("Usage: python main.py <scraper_name>")
        logger.error("Available scrapers: kauppalehti, sijoitustieto, inderes, yahoofinance")
        sys.exit(1)
    
    scraper_name = sys.argv[1].lower()
    
    # Map scraper names to their scraper functions
    scraper_map = {
        'kauppalehti': kauppalehti_scraper,
        'sijoitustieto': sijoitustieto_scraper,
        'inderes': inderes_scraper,
        'yahoofinance': yahoofinance_scraper
    }
    
    if scraper_name not in scraper_map:
        logger.error(f"Unknown scraper: {scraper_name}")
        logger.error("Available scrapers: kauppalehti, sijoitustieto, inderes, yahoofinance")
        sys.exit(1)
    
    scraper_function = scraper_map[scraper_name]
    logger.info(f"Starting scraping process for: {scraper_name}")
    
    # Yahoo Finance scraper has different logic - it only needs tickers
    if scraper_name == 'yahoofinance':
        return run_yahoofinance_scraper()
    
    # Load URLs from YAML file for forum scrapers
    input_file = Path(__file__).parent.parent / "input_data" / f"urls_{scraper_name}.yaml"
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
            posts = scraper_function(url, company, ticker)
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

def run_yahoofinance_scraper():
    """Run the Yahoo Finance scraper for all tickers in YAML files."""
    input_dir = Path(__file__).parent.parent / "input_data"
    output_dir = Path(__file__).parent.parent / "output_data"
    output_dir.mkdir(exist_ok=True)
    
    # Collect all unique tickers from all YAML files
    all_tickers = set()
    
    for yaml_file in input_dir.glob('urls_*.yaml'):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                urls_data = yaml.safe_load(f)
            
            for item in urls_data:
                ticker = item.get('ticker')
                if ticker:
                    all_tickers.add(ticker)
            
            logger.info(f"Loaded tickers from {yaml_file.name}")
        except Exception as e:
            logger.error(f"Error loading {yaml_file}: {e}")
            continue
    
    logger.info(f"Found {len(all_tickers)} unique tickers to scrape")
    
    successful_scrapes = 0
    failed_scrapes = 0
    total_rows = 0
    
    # Process each ticker
    for idx, ticker in enumerate(sorted(all_tickers), 1):
        logger.info(f"[{idx}/{len(all_tickers)}] Scraping Yahoo Finance data for {ticker}")
        
        try:
            rows = yahoofinance_scraper(ticker)
            if rows > 0:
                total_rows += rows
                successful_scrapes += 1
                logger.info(f"Successfully scraped {rows} rows for {ticker}")
            else:
                failed_scrapes += 1
                logger.warning(f"No data scraped for {ticker}")
            
            # Add delay between requests to be respectful
            if idx < len(all_tickers):
                import time
                wait_time = random.uniform(2, 4)
                logger.debug(f"Waiting {wait_time:.1f}s before next ticker")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"Failed to scrape {ticker}: {e}", exc_info=True)
            failed_scrapes += 1
            continue
    
    logger.info(f"Yahoo Finance scraping complete. Total rows: {total_rows}, Successful: {successful_scrapes}, Failed: {failed_scrapes}")

if __name__ == "__main__":
    main()