# bot.py
# This script performs the browser automation using Playwright.
# Updated to run in a continuous loop and provide live status updates.

import os
import asyncio
import random
from playwright.async_api import async_playwright
from datetime import datetime

# --- CONFIGURATION ---
SESSION_FILE = 'session.json'
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/your.facebook.profile.name' # <-- IMPORTANT: CHANGE THIS
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
STATUS_LOG_FILE = 'status.log'

# --- HELPER FUNCTION FOR LOGGING ---
def log_status(message, level="INFO"):
    """Writes a status message to the log file with a timestamp and level."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Add a prefix for different log levels for better readability
    full_message = f"[{timestamp}] [{level}] {message}\n"
    print(full_message, end='') # Print to console as well
    with open(STATUS_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(full_message)

async def run_bot():
    """Main function to run the automation bot."""
    log_status("AI Assistant process started. Initializing...")
    
    async with async_playwright() as p:
        log_status("Launching browser in headless mode.")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        
        context = None
        if os.path.exists(SESSION_FILE):
            log_status("Session file found. Attempting to load session.")
            try:
                context = await browser.new_context(storage_state=SESSION_FILE)
                log_status("Session loaded successfully.")
            except Exception as e:
                log_status(f"Could not load session, it might be invalid. Error: {e}", level="ERROR")
                os.remove(SESSION_FILE)
        
        if not context:
            log_status("CRITICAL: No valid session file. Cannot log in on the server.", level="CRITICAL")
            log_status("Please run this script on your local computer first (with headless=False) to create a 'session.json' file, then upload it to your Render project.", level="ACTION")
            await browser.close()
            return

        page = await context.new_page()
        log_status("Navigating to Facebook to verify login status.")
        await page.goto('https://www.facebook.com', wait_until="load")

        # --- CONTINUOUS ACTION LOOP ---
        log_status("Initialization complete. Starting main activity loop.", level="SUCCESS")
        while True:
            try:
                # --- Task 1: Check for new notifications (simulated) ---
                log_status("Checking for new notifications...")
                await asyncio.sleep(random.uniform(5, 10)) # Simulate network activity
                
                # In a real script, you would use page.locator to find the notification icon
                # and check if it has a count.
                if random.random() < 0.1: # 10% chance of a "new notification"
                    notification_type = random.choice(["commented on your post", "liked your photo", "tagged you in a post"])
                    log_status(f"New notification found: Someone {notification_type}.", level="EVENT")
                else:
                    log_status("No new notifications found.")

                # --- Task 2: Analyze a recent post (simulated) ---
                log_status("Analyzing a recent post for engagement...")
                await asyncio.sleep(random.uniform(5, 10))
                # In a real script, you would navigate to your profile, find the latest post,
                # and scrape its likes/comments.
                post_text = "Thinking about the next big project! #motivation"
                likes = random.randint(5, 50)
                comments = random.randint(0, 10)
                log_status(f"Analyzed post '{post_text[:30]}...': {likes} likes, {comments} comments.")

                # --- Task 3: Decide on an AI action (simulated) ---
                log_status("Asking AI for next action...")
                await asyncio.sleep(random.uniform(5, 10))
                # Here you would feed the analysis to OpenAI
                if comments < 3 and likes > 20:
                    ai_decision = "Suggest writing a follow-up question in the comments to boost engagement."
                    log_status(f"AI suggests: '{ai_decision}'", level="AI_ACTION")
                else:
                    ai_decision = "Content engagement is stable. Recommend monitoring."
                    log_status(f"AI suggests: '{ai_decision}'")
                
                log_status("Cycle complete. Waiting before next check...")
                await asyncio.sleep(30) # Wait 30 seconds before starting the next cycle

            except Exception as e:
                log_status(f"An error occurred in the main loop: {e}", level="ERROR")
                log_status("Attempting to recover and continue in 60 seconds.")
                await asyncio.sleep(60)


if __name__ == '__main__':
    # Clear the log file at the start of a new run
    if os.path.exists(STATUS_LOG_FILE):
        os.remove(STATUS_LOG_FILE)
        
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_bot())
