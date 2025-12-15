import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from models.post import Post

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 5  # seconds

def sijoitustieto_scraper(thread_url, company_name, ticker):
    """
    Scrape posts from a Sijoitustieto forum thread.
    
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
                    posts = page.locator(".comment.js-comment")
                    post_count = posts.count()
                    logger.debug(f"Found {post_count} posts on page {page_count}")

                    for i in range(post_count):
                        try:
                            post = posts.nth(i)
                            
                            # Extract data with None checks and shorter timeout (5s instead of 30s default)
                            post_id = post.get_attribute('id', timeout=5000) or "Unknown"
                            
                            # User ID with fallback
                            user_id_locator = post.locator('.data-comment-user-id')
                            user_id = user_id_locator.inner_text() if user_id_locator.count() > 0 else "Unknown"
                            
                            # Message href with fallback - find link with "Permalink to this comment" title
                            message_href_locator = post.locator('a[title="Permalink to this comment"]')
                            message_href = message_href_locator.get_attribute('href', timeout=5000) if message_href_locator.count() > 0 else None
                            
                            # Get datetime - find text directly inside message-top div (not wrapped in other elements)
                            datetime_attr = None
                            message_top = post.locator('.message-top')
                            if message_top.count() > 0:
                                try:
                                    # Use evaluate to get direct text nodes (not wrapped in children)
                                    datetime_str = message_top.evaluate("""
                                        el => {
                                            for (let node of el.childNodes) {
                                                if (node.nodeType === 3 && node.textContent.trim()) {
                                                    return node.textContent.trim();
                                                }
                                            }
                                            return null;
                                        }
                                    """, timeout=5000)
                                    
                                    # Convert string to datetime object (format: "30.9.2015 - 13:38")
                                    if datetime_str:
                                        datetime_attr = datetime.strptime(datetime_str, "%d.%m.%Y - %H:%M")
                                except Exception as e:
                                    logger.debug(f"Failed to parse datetime: {e}")
                                    datetime_attr = None
                            
                            # Skip post if critical data is missing (message_href and datetime are critical)
                            if not message_href or not datetime_attr:
                                logger.warning(f"Skipping post {i+1} on page {page_count}: missing critical data (href or datetime)")
                                continue

                            # Locate the engagement/reactions element (span with trending_up or trending_down text)
                            reactions_container = post.locator("span.material-symbols-rounded:has-text('trending_')").locator("..")

                            # Get engagement value (text sibling of the material icon)
                            engagement = "N/A"
                            if reactions_container.count() > 0:
                                try:
                                    engagement_text = reactions_container.inner_text(timeout=5000)
                                    # Extract just the number, removing the icon text
                                    engagement = engagement_text.replace("trending_up", "").replace("trending_down", "").strip()
                                except:
                                    engagement = "N/A"
                            
                            post_data = {
                                "id": f"Sijoitustieto.{post_id}",
                                "author_id": f"Sijoitustieto.{user_id}",
                                "message": post.locator(".message-post").inner_text(),
                                "date_time": datetime_attr,
                                "engagement": engagement,
                                "company_name": company_name,
                                "ticker": ticker,
                                "forum": "Sijoitustieto",
                                "url": f"{page.url}{message_href}",
                            }
                            data.append(Post(**post_data))
                        except Exception as e:
                            logger.warning(f"Error scraping post {i+1} on page {page_count}: {e}")
                            continue
                    
                    # Check if next page button exists - find current page and check for next sibling (use first occurrence to avoid strict mode)
                    current_page_link = page.locator('a[title="Tämänhetkinen sivu"]').first
                    if current_page_link.count() == 0:
                        logger.debug("Could not find current page marker, stopping")
                        break
                    
                    # Get parent li element and check if there's a next li sibling
                    has_next_page = current_page_link.evaluate("""
                        el => {
                            const parentLi = el.closest('li');
                            if (!parentLi) return false;
                            const nextLi = parentLi.nextElementSibling;
                            return nextLi !== null && nextLi.tagName === 'LI';
                        }
                    """)
                    
                    if not has_next_page:
                        logger.debug("No more pages to scrape")
                        break
                    
                    # Wait for a random time between 2.5s and 4.5s (more conservative)
                    wait_time = random.uniform(2.5, 4.5)
                    logger.debug(f"Waiting {wait_time:.1f}s before next page")
                    time.sleep(wait_time)
                    
                    # Get the next page link and navigate to it
                    next_page_link = current_page_link.evaluate("""
                        el => {
                            const parentLi = el.closest('li');
                            const nextLi = parentLi.nextElementSibling;
                            const link = nextLi.querySelector('a');
                            return link ? link.href : null;
                        }
                    """)
                    
                    if not next_page_link:
                        logger.debug("Next page has no link, stopping")
                        break
                    
                    # Navigate to the next page with retry logic
                    logger.debug(f"Navigating to next page: {next_page_link}")
                    
                    retry_count = 0
                    while retry_count < MAX_RETRIES:
                        try:
                            page.goto(next_page_link, wait_until="networkidle", timeout=60000)
                            
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
    output_file = output_dir / f"sijoitustieto_{safe_company_name}.json"
    
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