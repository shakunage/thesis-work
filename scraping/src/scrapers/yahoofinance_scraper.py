import csv
import logging
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 5  # seconds

# Fixed date periods (Jan 1, 2012 to future date)
PERIOD1 = 1325376000
PERIOD2 = 1767139200

def yahoofinance_scraper(ticker):
    """
    Scrape OHLC and Volume data from Yahoo Finance for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (without .HE suffix)
        
    Returns:
        int: Number of rows scraped
    """
    # Add .HE suffix for Helsinki exchange
    url = f"https://finance.yahoo.com/quote/{ticker}/history/?period1={PERIOD1}&period2={PERIOD2}"
    
    logger.info(f"Starting Yahoo Finance scraper for {ticker} ({ticker})")
    logger.info(f"URL: {url}")
    
    # Setup output file path
    output_dir = Path(__file__).parent.parent.parent / "output_data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"yahoofinance_{ticker}.csv"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US"
            )
            
            try:
                # Navigate to the page with retry logic
                retry_count = 0
                while retry_count < MAX_RETRIES:
                    try:
                        logger.debug(f"Attempting to load page: {url}")
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        time.sleep(3)  # Wait for dynamic content to load
                        
                        # Check if we got blocked or rate limited
                        if page.locator("text=/rate limit|blocked|access denied/i").count() > 0:
                            retry_delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                            logger.warning(f"Possible rate limiting detected. Waiting {retry_delay}s before retry {retry_count+1}/{MAX_RETRIES}")
                            time.sleep(retry_delay)
                            retry_count += 1
                            continue
                        
                        logger.debug(f"Successfully loaded page: {url}")
                        break
                        
                    except PlaywrightTimeoutError:
                        retry_count += 1
                        if retry_count >= MAX_RETRIES:
                            logger.error(f"Timeout loading page after {MAX_RETRIES} retries: {url}")
                            browser.close()
                            return 0
                        retry_delay = INITIAL_RETRY_DELAY * (2 ** (retry_count - 1))
                        logger.warning(f"Timeout on attempt {retry_count}/{MAX_RETRIES}. Retrying in {retry_delay}s")
                        time.sleep(retry_delay)
                
            except Exception as e:
                logger.error(f"Error loading page for {ticker}: {e}")
                browser.close()
                return 0
            
            # Wait for the historical data table to load
            try:
                # Yahoo Finance uses a table with data-testid or specific class
                # Try to find the table element
                page.wait_for_selector('table', timeout=300)
                time.sleep(2)  # Additional wait for all rows to render
                logger.info(f"Table loaded for {ticker}")
                
            except PlaywrightTimeoutError:
                logger.error(f"No data table found for {ticker} ({ticker})")
                # Take screenshot for debugging
                screenshot_path = output_dir / f"debug_{ticker}_no_table.png"
                page.screenshot(path=str(screenshot_path))
                logger.error(f"Screenshot saved to {screenshot_path}")
                browser.close()
                return 0
            
            # Extract data from the table
            try:
                # Find all table rows
                rows = page.locator('table tbody tr').all()
                
                if not rows:
                    logger.warning(f"No data rows found for {ticker}")
                    screenshot_path = output_dir / f"debug_{ticker}_no_rows.png"
                    page.screenshot(path=str(screenshot_path))
                    logger.warning(f"Screenshot saved to {screenshot_path}")
                    browser.close()
                    return 0
                
                logger.info(f"Found {len(rows)} total rows in table for {ticker}")
                
                data_rows = []
                skipped_reasons = {
                    'too_few_cells': 0,
                    'dividend_split': 0,
                    'missing_data': 0,
                    'parse_error': 0
                }
                
                for idx, row in enumerate(rows):
                    try:
                        # Get all cells in the row
                        cells = row.locator('td').all()
                        
                        if len(cells) < 7:  # Need at least 7 columns (Date, Open, High, Low, Close, Adj Close, Volume)
                            skipped_reasons['too_few_cells'] += 1
                            if idx < 3:  # Log first few rows for debugging
                                logger.debug(f"Row {idx}: Only {len(cells)} cells found, need 7")
                            continue
                        
                        # Extract cell values
                        date = cells[0].inner_text().strip()
                        
                        # Skip rows that aren't data (like "Dividend" or other labels)
                        if not date or 'dividend' in date.lower() or 'split' in date.lower():
                            skipped_reasons['dividend_split'] += 1
                            if idx < 3:
                                logger.debug(f"Row {idx}: Skipped dividend/split row with date: {date}")
                            continue
                        
                        open_price = cells[1].inner_text().strip()
                        high_price = cells[2].inner_text().strip()
                        low_price = cells[3].inner_text().strip()
                        close_price = cells[4].inner_text().strip()
                        adj_close = cells[5].inner_text().strip()
                        volume = cells[6].inner_text().strip()
                        
                        # Log first few rows for debugging
                        if idx < 3:
                            logger.debug(f"Row {idx} data: Date={date}, Open={open_price}, High={high_price}, Low={low_price}, Close={close_price}, Adj={adj_close}, Vol={volume}")
                        
                        data_rows.append({
                            'Date': date,
                            'Open': open_price,
                            'High': high_price,
                            'Low': low_price,
                            'Close': close_price,
                            'Adj Close': adj_close,
                            'Volume': volume
                        })
                        
                    except Exception as e:
                        skipped_reasons['parse_error'] += 1
                        if idx < 3:
                            logger.warning(f"Row {idx}: Error parsing - {e}")
                        continue
                
                browser.close()
                
                if not data_rows:
                    logger.warning(f"No valid data rows extracted for {ticker}")
                    return 0
                
                # Write to CSV
                with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    writer.writerows(data_rows)
                
                logger.info(f"Successfully scraped {len(data_rows)} rows for {ticker} to {output_file}")
                return len(data_rows)
                
            except Exception as e:
                logger.error(f"Error extracting data for {ticker}: {e}")
                browser.close()
                return 0
                
    except Exception as e:
        logger.error(f"Unexpected error scraping {ticker}: {e}", exc_info=True)
        return 0
