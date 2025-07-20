# bot.py
# A more advanced and robust public scraping bot for Facebook profiles.

import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_public_profile(profile_url: str):
    """
    Launches a browser and uses advanced techniques to scrape a public Facebook profile.
    """
    scraped_data = {
        'bio': "Scraping failed: Could not find a bio.",
        'posts': ["(Scraping Failed - Could not extract post text)"] * 5
    }
    
    print(f"--- Starting Advanced Scrape for {profile_url} ---")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
                java_script_enabled=True,
                accept_downloads=False,
                has_touch=False,
                is_mobile=False,
                locale='en-US'
            )
            page = await context.new_page()
            
            print("Navigating to profile page...")
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
            
            # --- Wait for the main feed to be present ---
            print("Waiting for the main feed container to appear...")
            feed_selector = 'div[role="feed"]'
            await page.wait_for_selector(feed_selector, timeout=20000)
            print("Feed container found. Waiting for content to settle...")
            await page.wait_for_timeout(3000) # Give time for posts to render

            # --- Scrape Bio ---
            print("Attempting to scrape bio...")
            try:
                # This selector looks for a common bio pattern near the top of the profile
                bio_element = page.locator('div[data-pagelet="ProfileTimeline"] div.x1b0d499.x1d69dk1').first
                bio_text = await bio_element.inner_text(timeout=5000)
                if bio_text:
                    scraped_data['bio'] = bio_text
                    print(f"Successfully scraped bio: '{bio_text[:100]}...'")
            except Exception as e:
                print(f"Could not scrape bio with primary selector: {e}")

            # --- Scrape Posts with Scrolling ---
            print("Attempting to scrape posts...")
            post_texts = []
            try:
                # Scroll down a few times to load more posts
                for i in range(3):
                    print(f"Scrolling down (Pass {i+1}/3)...")
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(2000) # Wait for new posts to load

                # This selector targets the individual post containers within the feed
                post_locators = page.locator(f'{feed_selector} > div')
                count = await post_locators.count()
                print(f"Found {count} potential post elements after scrolling.")

                for i in range(min(10, count)): # Check up to 10 elements to find 5 posts
                    if len(post_texts) >= 5:
                        break
                    
                    post_element = post_locators.nth(i)
                    try:
                        # This looks for the specific div that holds the main text content
                        text_div = post_element.locator('div[data-ad-preview="message"]').first
                        post_text = await text_div.inner_text(timeout=2000)
                        
                        # Basic filtering to ensure it's a real post
                        if post_text and len(post_text) > 20:
                            post_texts.append(post_text.strip())
                            print(f"  - Scraped Post {len(post_texts)}: '{post_text[:70]}...'")

                    except Exception:
                        # This element was likely not a post, so we skip it
                        continue
                
                if post_texts:
                    scraped_data['posts'] = post_texts
                    while len(scraped_data['posts']) < 5:
                        scraped_data['posts'].append("(No more public posts found)")
                    print("Successfully scraped recent posts.")
                else:
                    raise Exception("No valid post text could be extracted.")

            except Exception as e:
                print(f"Could not scrape posts: {e}")
            
            await browser.close()
            print("--- Scrape Complete ---")
            
        except Exception as e:
            print(f"A critical error occurred during the scraping process: {e}")
            # The function will return the default error messages in scraped_data

    return scraped_data
