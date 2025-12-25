import json
import logging
import time
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from models.post import Post

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 5  # seconds
POSTS_PER_BATCH = 300  # Save and navigate every 300 posts

def inderes_scraper(thread_url, company_name, ticker):
    """
    Scrape posts from an Inderes forum thread (with infinite scrolling).
    
    Args:
        thread_url: URL of the forum thread
        company_name: Name of the company
        ticker: Stock ticker symbol
        
    Returns:
        List of dictionaries containing scraped post data
    """
    logger.info(f"Starting scraper for {company_name} at {thread_url}")
    data = []
    scraped_post_ids = set()  # Track scraped post IDs to avoid duplicates
    
    # Setup output file path
    output_dir = Path(__file__).parent.parent.parent / "output_data"
    output_dir.mkdir(exist_ok=True)
    safe_company_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in company_name)
    safe_company_name = safe_company_name.replace(' ', '_').lower()
    output_file = output_dir / f"inderes_{safe_company_name}.json"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="fi-FI"
            )

            try:
                # Go to the forum's listing page with retry logic
                retry_count = 0
                while retry_count < MAX_RETRIES:
                    try:
                        page.goto(thread_url, wait_until="domcontentloaded", timeout=60000)
                        time.sleep(4)  # Fixed wait for page to load (site polls constantly)
                        
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

            # Wait for first post to load
            try:
                page.locator('.boxed.onscreen-post').first.wait_for(state="visible", timeout=5000)
            except PlaywrightTimeoutError:
                logger.error("No posts found on initial load")
                browser.close()
                return []
            
            # Get total post count
            total_posts = int(page.locator('.timeline-replies').inner_text().split()[-1])
            logger.info(f"Total posts in thread: {total_posts}")
            logger.info(f"Estimated scraping time for the thread: {(total_posts / 22.5):.2f} min")
            
            # Calculate batches needed
            current_batch_start = 1
            
            while current_batch_start <= total_posts:
                # Navigate to the starting post of this batch if not the first batch
                if current_batch_start > 1:
                    batch_url = f"{thread_url}/{current_batch_start}"
                    logger.info(f"Navigating to batch starting at post {current_batch_start}: {batch_url}")
                    
                    retry_count = 0
                    while retry_count < MAX_RETRIES:
                        try:
                            page.goto(batch_url, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(4)
                            
                            if page.locator("text=/rate limit|blocked|access denied/i").count() > 0:
                                retry_delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                                logger.warning(f"Rate limiting detected. Waiting {retry_delay}s")
                                time.sleep(retry_delay)
                                retry_count += 1
                                continue
                            break
                        except PlaywrightTimeoutError:
                            retry_count += 1
                            if retry_count >= MAX_RETRIES:
                                logger.error(f"Failed to load batch at post {current_batch_start}")
                                browser.close()
                                return data
                            time.sleep(INITIAL_RETRY_DELAY * (2 ** (retry_count - 1)))
                    
                    # Wait for posts to load
                    try:
                        page.locator('.boxed.onscreen-post').first.wait_for(state="visible", timeout=5000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"No posts found at batch starting at {current_batch_start}")
                        break

            # Tab-based navigation scraping logic for this batch
                logger.info(f"Starting scraping batch from post {current_batch_start}")
                batch_post_count = 0
                consecutive_failures = 0
                max_consecutive_failures = 5
                batch_end = min(current_batch_start + POSTS_PER_BATCH - 1, total_posts)
            
                while consecutive_failures < max_consecutive_failures and batch_post_count < POSTS_PER_BATCH:
                    try:
                    
                        # Check if a share button is focused and scroll it
                        is_share_focused = page.evaluate("""
                            document.activeElement && 
                            document.activeElement.tagName === 'BUTTON' && 
                            document.activeElement.classList.contains('share')
                        """)
                        
                        # Check if a relative-date span is focused
                        is_date_focused = page.evaluate("""
                            document.activeElement && 
                            document.activeElement.tagName === 'A' && 
                            document.activeElement.classList.contains('post-date')
                        """)
                        
                        # Scroll focused element to top (for both share and date)
                        if is_share_focused or is_date_focused:
                            page.evaluate("""
                                if (document.activeElement) {
                                    document.activeElement.scrollIntoView({ 
                                        behavior: 'instant', 
                                        block: 'start' 
                                    });
                                }
                            """)
                            time.sleep(0.3)
                        
                        if is_date_focused:
                            # We're on a date element, scrape the parent post
                            try:
                                # Find the parent post container
                                date_element = page.locator(':focus')
                                post = date_element.locator('xpath=ancestor::article[contains(@class, "boxed")]').first
                                
                                # Get post global ID to avoid duplicates
                                post_id = post.get_attribute('data-post-id', timeout=2000)

                                # Extract post number
                                post_number_in_thread = int(post.get_attribute('id', timeout=2000)[5:])

                                # Check if we reached the end of this batch
                                if post_number_in_thread > batch_end:
                                    logger.info(f"Reached end of batch at post {post_number_in_thread}")
                                    break
                                
                                # Check if we've reached the end of the thread
                                if post_number_in_thread >= total_posts:
                                    logger.info(f"All messages scraped. Finishing scrape.")
                                    consecutive_failures = max_consecutive_failures  # Force exit outer loop
                                    break
                                
                                if post_id and post_id not in scraped_post_ids:
                                    scraped_post_ids.add(post_id)
                                    batch_post_count += 1
                                                                    
                                    # Extract user ID
                                    user_id = post.get_attribute('data-user-id')
                                    
                                    # Extract post content
                                    content_locator = post.locator('.cooked')
                                    message_text = content_locator.inner_text(timeout=2000) if content_locator.count() > 0 else ""
                                    
                                    # Extract datetime from the focused date element
                                    datetime_str = post.locator('.relative-date').get_attribute('data-time', timeout=2000)
                                    
                                    # Parse datetime from Unix timestamp and convert to Finnish time
                                    datetime_attr = None
                                    if datetime_str:
                                        try:
                                            timestamp_ms = int(datetime_str)
                                            datetime_attr = datetime.fromtimestamp(timestamp_ms / 1000, tz=ZoneInfo("Europe/Helsinki"))
                                        except Exception as e:
                                            logger.debug(f"Failed to parse Unix timestamp {datetime_str}: {e}")
                                    
                                    # Skip if missing critical data
                                    if not datetime_attr or not message_text:
                                        logger.warning(f"Skipping post {post_id}: missing critical data")
                                        logger.info(f"Post content: '{message_text}', datetime: '{datetime_attr}'")
                                    else:
                                        # Get post URL
                                        post_url = f"{thread_url}/{post_number_in_thread}" if post_number_in_thread else thread_url
                                        
                                        # Extract likes/engagement
                                        likes = "0"
                                        try:
                                            likes_locator = post.locator('button.like-count')
                                            if likes_locator.count() > 0:
                                                likes = likes_locator.get_attribute('label', timeout=1000).split()[0]  or "0"
                                        except:
                                            pass

                                        post_data = {
                                            "id": f"Inderes.{post_id}",
                                            "author_id": f"Inderes.{user_id}",
                                            "message": message_text,
                                            "date_time": datetime_attr,
                                            "engagement": likes,
                                            "company_name": company_name,
                                            "ticker": ticker,
                                            "forum": "Inderes",
                                            "url": post_url,
                                        }
                                        data.append(Post(**post_data))
                                        consecutive_failures = 0  # Reset on success
                                        wait_time = random.uniform(1.0, 2.0)
                                        time.sleep(wait_time)  # Small delay to be polite
                                
                            except Exception as e:
                                logger.warning(f"Error scraping focused post: {e}")
                                consecutive_failures += 1
                        
                        # Press Tab to move to next element
                        page.keyboard.press('Tab')
                        time.sleep(0.05)  # Small delay for focus to change
                        
                    except Exception as e:
                        logger.error(f"Error during tab navigation: {e}")
                        consecutive_failures += 1
                        # Try to continue
                        try:
                            page.keyboard.press('Tab')
                            time.sleep(0.05)
                        except:
                            break
            
                logger.info(f"Batch completed. Scraped {batch_post_count} posts in this batch")
                
                # Save progress after each batch
                if len(data) > 0:
                    output_data = [post.model_dump(mode="json") for post in data]
                    try:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump(output_data, f, ensure_ascii=False, indent=2)
                        logger.info(f"Saved {len(output_data)} posts to {output_file}")
                    except Exception as e:
                        logger.error(f"Failed to save output file: {e}")
                
                # Move to next batch
                current_batch_start += POSTS_PER_BATCH
            
            logger.info(f"All batches completed. Total scraped: {len(data)} posts")
            browser.close()
            
    except Exception as e:
        logger.error(f"Unexpected error in scraper: {e}", exc_info=True)
        return []
    
    # Convert Pydantic models to a list of dictionaries for JSON serialization
    output_data = [post.model_dump(mode="json") for post in data]
    
    # Deduplicate by 'id' field
    seen_ids = set()
    deduplicated_data = []
    for post in output_data:
        if post['id'] not in seen_ids:
            seen_ids.add(post['id'])
            deduplicated_data.append(post)
    
    logger.info(f"Scraper completed. Collected {len(output_data)} posts, {len(deduplicated_data)} after deduplication")
    
    # Save final deduplicated data
    if len(deduplicated_data) > 0:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(deduplicated_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(deduplicated_data)} deduplicated posts to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save output file {output_file}: {e}", exc_info=True)
    else:
        logger.warning(f"No data collected for {company_name}, skipping file save")
    
    return deduplicated_data