# bot.py
# This script performs the browser automation using Playwright.
# Updated to log its status to a file for the web UI to display.

import os
import asyncio
from playwright.async_api import async_playwright
from datetime import datetime

# --- CONFIGURATION ---
SESSION_FILE = 'session.json'
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/your.facebook.profile.name' # <-- IMPORTANT: CHANGE THIS
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
STATUS_LOG_FILE = 'status.log'

# --- HELPER FUNCTION FOR LOGGING ---
def log_status(message):
    """Writes a status message to the log file with a timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] {message}\n"
    print(full_message, end='') # Print to console as well
    with open(STATUS_LOG_FILE, 'a') as f:
        f.write(full_message)

async def run_bot():
    """Main function to run the automation bot."""
    log_status("AI Assistant process started.")
    
    async with async_playwright() as p:
        log_status("Launching browser...")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        
        context = None
        if os.path.exists(SESSION_FILE):
            log_status("Session file found. Loading session...")
            try:
                context = await browser.new_context(storage_state=SESSION_FILE)
            except Exception as e:
                log_status(f"Could not load session, it might be invalid. Error: {e}")
                os.remove(SESSION_FILE)
        
        if not context:
            log_status("No valid session. A new login will be required.")
            context = await browser.new_context()

        page = await context.new_page()
        log_status("Navigating to Facebook...")
        await page.goto('https://www.facebook.com')

        # --- LOGIN CHECK ---
        email_input = page.locator('input[name="email"]')
        try:
            if await email_input.is_visible(timeout=5000):
                log_status("CRITICAL: Not logged in. Cannot proceed on server.")
                log_status("Please run locally with 'headless=False' to create a 'session.json' file, then upload it.")
                await browser.close()
                return
            else:
                log_status("Login successful using saved session.")
        except Exception:
            log_status("Login form not found. Assuming successful login.")

        # --- AUTOMATION TASKS ---
        log_status(f"Navigating to profile: {FACEBOOK_PROFILE_URL}")
        await page.goto(FACEBOOK_PROFILE_URL)
        
        log_status("Taking a screenshot of the profile...")
        await page.screenshot(path='profile_screenshot.png')
        log_status("Screenshot saved as 'profile_screenshot.png'.")

        # --- Scrape recent posts (Placeholder) ---
        log_status("Analyzing recent posts...")
        # In a real scenario, you would loop through posts here
        # For demonstration, we'll simulate finding a post and asking the AI
        await asyncio.sleep(2) # Simulate work
        found_post_text = "Just had a great day exploring the city! #adventure"
        log_status(f"Found post: '{found_post_text}'")
        
        await asyncio.sleep(1)
        log_status("Asking AI for a comment suggestion...")
        # TODO: Add actual OpenAI call here
        await asyncio.sleep(3) # Simulate AI thinking
        ai_suggestion = "Sounds like an amazing day! What was your favorite part?"
        log_status(f"AI suggests commenting: '{ai_suggestion}'")
        
        # TODO: Add Playwright logic to actually post the comment
        log_status("Action complete. Simulating next task...")
        await asyncio.sleep(2)

        log_status("Bot tasks finished. Closing browser.")
        await browser.close()

if __name__ == '__main__':
    # Clear the log file at the start of a new run
    if os.path.exists(STATUS_LOG_FILE):
        os.remove(STATUS_LOG_FILE)
        
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_bot())
