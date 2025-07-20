# bot.py
# This bot scrapes a PUBLIC Facebook profile URL without needing a login.
# It extracts visible text to be used for a specific AI analysis.

import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_public_profile(profile_url: str):
    """
    Launches a browser, navigates to a public Facebook profile,
    and scrapes the visible bio and post content.

    Args:
        profile_url (str): The public Facebook profile URL to scrape.

    Returns:
        dict: A dictionary containing the scraped 'bio' and 'posts'.
              Returns an error message if scraping fails.
    """
    scraped_data = {
        'bio': "Scraping failed: Could not find a bio.",
        'posts': ["(Scraping Failed - Could not extract post text)"] * 5
    }

    async with async_playwright() as p:
        try:
            print(f"Launching browser to scrape {profile_url}...")
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                # Emulate a common user agent to avoid being blocked
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(profile_url, wait_until="networkidle", timeout=30000)
            print("Profile page loaded.")

            # --- SCRAPING LOGIC ---
            # Scrape Bio
            try:
                # This selector targets a common container for the bio/intro text on public profiles.
                bio_element = page.locator('div.x1b0d499.x1d69dk1').first
                bio_text = await bio_element.inner_text(timeout=5000)
                scraped_data['bio'] = bio_text
                print("Successfully scraped bio.")
            except Exception as e:
                print(f"Could not scrape bio: {e}")

            # Scrape Posts
            post_texts = []
            try:
                # This selector targets the main feed container to find posts.
                feed_container = page.locator('div[role="feed"]').first
                post_locators = feed_container.locator('> div')
                count = await post_locators.count()
                print(f"Found {count} potential post elements.")
                
                for i in range(min(5, count)):
                    post_element = post_locators.nth(i)
                    # This looks for a specific data attribute that often holds the post text.
                    text_div = post_element.locator('div[data-ad-preview="message"]').first
                    post_text = await text_div.inner_text(timeout=3000)
                    post_texts.append(post_text)

                if post_texts:
                    scraped_data['posts'] = post_texts
                    # Pad the list if fewer than 5 posts were found
                    while len(scraped_data['posts']) < 5:
                        scraped_data['posts'].append("(No more public posts found)")
                    print("Successfully scraped recent posts.")
                else:
                    raise Exception("No posts could be extracted.")

            except Exception as e:
                print(f"Could not scrape posts: {e}")
            
            await browser.close()
            
        except Exception as e:
            print(f"A critical error occurred during scraping: {e}")
            # The function will return the default error messages in scraped_data

    return scraped_data

if __name__ == '__main__':
    # This is for local testing. You can run `python bot.py` to test it.
    test_url = "https://www.facebook.com/facebook" # Using a public page for testing
    
    async def test_run():
        print(f"--- Running local test for URL: {test_url} ---")
        data = await scrape_public_profile(test_url)
        print("\n--- SCRAPED DATA ---")
        print(json.dumps(data, indent=2))
        print("--- TEST COMPLETE ---")

    asyncio.run(test_run())
