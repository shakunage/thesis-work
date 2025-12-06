import json
import logging
import random
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from models.post import Post

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 10  # seconds

def kauppalehti_scraper(thread_url, company_name, ticker):
    """
    Scrape posts from a Kauppalehti forum thread.
    
    Args:
        thread_url: URL of the forum thread
        company_name: Name of the company
        ticker: Stock ticker symbol
        
    Returns:
        List of dictionaries containing scraped post data
    """
    logger.info(f"Starting scraper for {company_name} at {thread_url}")
    data = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page_count = 0

            try:
                # Go to the forum's listing page with retry logic
                retry_count = 0
                while retry_count < MAX_RETRIES:
                    try:
                        page.goto(thread_url, wait_until="networkidle", timeout=60000)
                        
                        # Check if we got rate limited or blocked
                        if page.locator("text=/rate limit|blocked|access denied/i").count() > 0:
                            retry_delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                            logger.warning(f"Possible rate limiting detected. Waiting {retry_delay}s before retry {retry_count+1}/{MAX_RETRIES}")
                            time.sleep(retry_delay)
                            retry_count += 1
                            continue
                        
                        logger.debug(f"Successfully loaded initial page: {thread_url}")
                        break
                    except PlaywrightTimeoutError:
                        retry_count += 1
                        if retry_count >= MAX_RETRIES:
                            logger.error(f"Timeout loading initial page after {MAX_RETRIES} retries: {thread_url}")
                            browser.close()
                            return []
                        retry_delay = INITIAL_RETRY_DELAY * (2 ** (retry_count - 1))
                        logger.warning(f"Timeout on attempt {retry_count}/{MAX_RETRIES}. Retrying in {retry_delay}s")
                        time.sleep(retry_delay)
                        
            except Exception as e:
                logger.error(f"Error loading initial page: {e}")
                browser.close()
                return []

            while True:
                page_count += 1
                logger.debug(f"Scraping page {page_count}")
                
                try:
                    # Adjust selectors to match the forum's HTML structure
                    posts = page.locator(".message.message--post.js-post.js-inlineModContainer")
                    post_count = posts.count()
                    logger.debug(f"Found {post_count} posts on page {page_count}")

                    for i in range(post_count):
                        try:
                            post = posts.nth(i)
                            reactions_locator = post.locator("div.reactionsBar.js-reactionsList.is-active")
                            
                            # Extract data with None checks
                            data_content = post.get_attribute('data-content')
                            user_id = post.locator('h4.message-name > a').get_attribute('data-user-id')
                            message_href = post.locator('.message-attribution-gadget').get_attribute('href')
                            datetime_attr = post.locator("time").get_attribute("datetime")
                            
                            # Skip post if critical data is missing
                            if not all([data_content, user_id, message_href, datetime_attr]):
                                logger.warning(f"Skipping post {i+1} on page {page_count}: missing critical data")
                                continue
                            
                            post_data = {
                                "id": f"Kauppalehti.{data_content}",
                                "author_id": f"Kauppalehti.{user_id}",
                                "message": post.locator(".bbWrapper").inner_text(),
                                "date_time": datetime_attr,
                                "engagement": reactions_locator.inner_text() if reactions_locator.count() > 0 else "N/A",
                                "company_name": company_name,
                                "ticker": ticker,
                                "forum": "Kauppalehti",
                                "url": f"https://keskustelu.kauppalehti.fi{message_href}",
                            }
                            data.append(Post(**post_data))
                        except Exception as e:
                            logger.warning(f"Error scraping post {i+1} on page {page_count}: {e}")
                            continue
                    
                    # Check if next page button exists
                    next_button = page.locator("a.pageNav-jump.pageNav-jump--next").last
                    if next_button.count() == 0:
                        logger.debug("No more pages to scrape")
                        break
                    
                    # Wait for a random time between 2.5s and 4.5s (more conservative)
                    wait_time = random.uniform(2.5, 4.5)
                    logger.debug(f"Waiting {wait_time:.1f}s before next page")
                    time.sleep(wait_time)
                    
                    # Get the href and navigate to it directly
                    next_url = next_button.get_attribute("href")
                    if not next_url:
                        logger.debug("Next button has no href, stopping")
                        break
                    
                    # Navigate to the next page with retry logic
                    full_next_url = f"https://keskustelu.kauppalehti.fi{next_url}"
                    logger.debug(f"Navigating to next page: {full_next_url}")
                    
                    retry_count = 0
                    while retry_count < MAX_RETRIES:
                        try:
                            page.goto(full_next_url, wait_until="networkidle", timeout=60000)
                            
                            # Check if we got rate limited
                            if page.locator("text=/rate limit|blocked|access denied/i").count() > 0:
                                retry_delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                                logger.warning(f"Rate limiting detected on page {page_count}. Waiting {retry_delay}s")
                                time.sleep(retry_delay)
                                retry_count += 1
                                continue
                            break
                        except PlaywrightTimeoutError:
                            retry_count += 1
                            if retry_count >= MAX_RETRIES:
                                logger.error(f"Timeout navigating to page after {MAX_RETRIES} retries, stopping pagination")
                                raise
                            retry_delay = INITIAL_RETRY_DELAY * (2 ** (retry_count - 1))
                            logger.warning(f"Timeout on page navigation attempt {retry_count}/{MAX_RETRIES}. Retrying in {retry_delay}s")
                            time.sleep(retry_delay)
                    
                except PlaywrightTimeoutError:
                    logger.error(f"Timeout on page {page_count}, stopping pagination")
                    break
                except Exception as e:
                    logger.error(f"Error on page {page_count}: {e}")
                    break
            
            browser.close()
            
    except Exception as e:
        logger.error(f"Unexpected error in scraper: {e}", exc_info=True)
        return []
    
    # Convert Pydantic models to a list of dictionaries for JSON serialization
    output_data = [post.model_dump(mode="json") for post in data]
    logger.info(f"Scraper completed. Collected {len(output_data)} posts from {page_count} pages")
    
    # Save to individual JSON file by forum and company (save progress even if incomplete)
    output_dir = Path(__file__).parent.parent.parent / "output_data"
    output_dir.mkdir(exist_ok=True)
    
    # Create safe filename from company name (remove special characters)
    safe_company_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in company_name)
    safe_company_name = safe_company_name.replace(' ', '_').lower()
    output_file = output_dir / f"kauppalehti_{safe_company_name}.json"
    
    # Save even if we only got partial data
    if len(output_data) > 0:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(output_data)} posts to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save output file {output_file}: {e}", exc_info=True)
    else:
        logger.warning(f"No data collected for {company_name}, skipping file save")
    
    return output_data