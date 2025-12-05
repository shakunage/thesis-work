import json
import random
import time
from playwright.sync_api import sync_playwright
from models.post import Post

FORUM_URL = "https://keskustelu.kauppalehti.fi/threads/betolar.249000/"
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go to the forum's listing page
        page.goto(FORUM_URL, wait_until="networkidle")

        data = []

        while True:
            # Adjust selectors to match the forum's HTML structure
            posts = page.locator(".message.message--post.js-post.js-inlineModContainer")

            for i in range(posts.count()):
                post = posts.nth(i)
                reactions_locator = post.locator("div.reactionsBar.js-reactionsList.is-active")
                post_data = {
                    "id": f"Kauppalehti.{post.get_attribute("data-content")}",
                    "author_id": f"Kauppalehti.{post.locator("h4.message-name > a").get_attribute("data-user-id")}",
                    "message": post.locator(".bbWrapper").inner_text(),
                    "date_time": post.locator("time").get_attribute("datetime"),
                    "engagement": reactions_locator.inner_text() if reactions_locator.count() > 0 else "N/A",
                    "company_name": "Neste",  # Fix static value
                    "ticker": "NESTE",       # Fix static value
                    "forum": "Kauppalehti",  # Fix static value
                    "url": f"https://keskustelu.kauppalehti.fi{post.locator(".message-attribution-gadget").get_attribute("href")}",
                }
                data.append(Post(**post_data))
            
            # Check if next page button exists and is visible
            next_button = page.locator("a.pageNav-jump.pageNav-jump--next").last
            if next_button.count() == 0:
                break
            
            # Wait for a random time between 1.5s and 2.5s
            wait_time = random.uniform(1.5, 2.5)
            time.sleep(wait_time)
            
            # Get the href and navigate to it directly
            next_url = next_button.get_attribute("href")
            if not next_url:
                break
            
            # Navigate to the next page
            page.goto(f"https://keskustelu.kauppalehti.fi{next_url}", wait_until="networkidle")
        
        # Convert Pydantic models to a list of dictionaries for JSON serialization
        output_data = [post.model_dump(mode="json") for post in data]

        with open("posts.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

        browser.close()

if __name__ == "__main__":
  main()