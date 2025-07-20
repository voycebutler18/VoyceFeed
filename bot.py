# bot.py
# This script performs the browser automation using Playwright.
# It logs into Facebook and performs tasks on your personal profile.

import os
import asyncio
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
# The file to save your session cookies to. This avoids logging in every time.
SESSION_FILE = 'session.json'
# Your personal Facebook profile URL.
# IMPORTANT: Replace 'your.facebook.profile.name' with your actual profile name or ID.
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/your.facebook.profile.name' 
# Set your OpenAI API key in an environment variable
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')


async def run_bot():
    """Main function to run the automation bot."""
    async with async_playwright() as p:
        print("Launching browser...")
        # For server deployment (like Render), you must run in headless mode.
        # For local testing, you can set headless=False to see the browser window.
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        
        context = None # Initialize context to None

        # Check if a session file exists to log in automatically
        if os.path.exists(SESSION_FILE):
            print("Session file found. Loading session...")
            try:
                context = await browser.new_context(storage_state=SESSION_FILE)
            except Exception as e:
                print(f"Could not load session, it might be invalid. A new login is required. Error: {e}")
                os.remove(SESSION_FILE) # Remove corrupted session file
        
        if not context:
            print("No valid session. A new login will be required.")
            context = await browser.new_context()

        page = await context.new_page()

        print("Navigating to Facebook...")
        await page.goto('https://www.facebook.com')

        # --- LOGIN CHECK ---
        # A simple way to check if we are logged in is to look for the login form.
        # If the email/phone input is visible, we are not logged in.
        email_input = page.locator('input[name="email"]')
        
        try:
            # Check if the login form is visible within a short timeout
            if await email_input.is_visible(timeout=5000):
                print("Not logged in. A new login is required.")
                print("ERROR: This script cannot handle manual login on a headless server.")
                print("Please run this script locally with 'headless=False' first to create a 'session.json' file.")
                print("Then, upload the 'session.json' file to your server alongside the bot.")
                await browser.close()
                return # Stop the script
            else:
                print("Successfully logged in using saved session.")
        except Exception:
            # If the locator times out, it's not visible, which means we are likely logged in.
            print("Login form not found. Assuming we are logged in.")


        # --- AUTOMATION TASKS ---
        print(f"Navigating to profile: {FACEBOOK_PROFILE_URL}")
        await page.goto(FACEBOOK_PROFILE_URL)
        
        print("Taking a screenshot of the profile...")
        await page.screenshot(path='profile_screenshot.png')
        print("Screenshot saved as 'profile_screenshot.png'.")

        # TODO: Scrape recent posts
        # This is where you would add the logic to find post elements,
        # extract their text, likes, and comments.
        print("Scraping recent posts (placeholder)...")
        # Example:
        # posts = await page.locator('[aria-label="Timeline"] .x1yztbdb').all()
        # for post in posts[:5]:
        #     post_text = await post.inner_text()
        #     print(f"Found post: {post_text[:100]}...")
        #     # TODO: Send post_text to OpenAI API
        
        print("Bot tasks complete. Closing browser.")
        await browser.close()

if __name__ == '__main__':
    # On Windows, this might be needed for Playwright's async nature.
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_bot())
