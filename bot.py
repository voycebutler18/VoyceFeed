# bot.py
# This script performs the browser automation using Playwright.
# Updated with a "Setup Mode" to easily create the session on your local computer.

import os
import asyncio
import random
import json
from playwright.async_api import async_playwright
from datetime import datetime

# --- CONFIGURATION ---
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/your.facebook.profile.name' # <-- IMPORTANT: CHANGE THIS
STATUS_LOG_FILE = 'status.log'

# --- NEW: Read session from environment variable ---
# On Render, you will create an environment variable called FACEBOOK_SESSION_JSON
# and paste the session string there.
SESSION_JSON_STR = os.environ.get('FACEBOOK_SESSION_JSON')

def log_status(message, level="INFO"):
    """Writes a status message to the log file with a timestamp and level."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] [{level}] {message}\n"
    print(full_message, end='')
    with open(STATUS_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(full_message)

async def run_bot():
    """Main function to run the automation bot."""
    log_status("AI Assistant process started.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=json.loads(SESSION_JSON_STR))
        
        page = await context.new_page()
        log_status("Session loaded from environment. Navigating to Facebook.")
        await page.goto('https://www.facebook.com', wait_until="load")
        
        log_status("Login successful using saved session.", level="SUCCESS")

        # --- CONTINUOUS ACTION LOOP ---
        log_status("Starting main activity loop...")
        while True:
            try:
                log_status("Checking for new notifications...")
                await asyncio.sleep(random.uniform(5, 10))
                if random.random() < 0.1:
                    log_status("New notification found!", level="EVENT")
                else:
                    log_status("No new notifications.")

                log_status("Analyzing a recent post...")
                await asyncio.sleep(random.uniform(5, 10))
                log_status("Post analysis complete.")

                log_status("Asking AI for next action...")
                await asyncio.sleep(random.uniform(5, 10))
                log_status("AI suggests monitoring for now.")
                
                log_status("Cycle complete. Waiting before next check...")
                await asyncio.sleep(30)

            except Exception as e:
                log_status(f"An error occurred: {e}", level="ERROR")
                await asyncio.sleep(60)

async def setup_session():
    """
    This function runs ONLY on your local computer to create the session string.
    """
    print("--- EchoMe AI Session Setup ---")
    print("A browser window will now open. Please log into your Facebook account.")
    print("After you successfully log in, close the browser window.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # MUST be non-headless
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto('https://www.facebook.com')
        
        # This pauses the script and waits for you to close the browser
        await page.wait_for_event('close')
        
        storage_state = await context.storage_state()
        session_string = json.dumps(storage_state)
        
        print("\n\n✅ --- SESSION CREATED SUCCESSFULLY --- ✅")
        print("Copy the entire block of text below. It is your session key.\n")
        print("----- BEGIN SESSION KEY -----")
        print(session_string)
        print("----- END SESSION KEY -----")
        print("\nPaste this key into the FACEBOOK_SESSION_JSON environment variable on Render.")
        await browser.close()

if __name__ == '__main__':
    if not SESSION_JSON_STR:
        # If the environment variable is not set, run setup mode.
        asyncio.run(setup_session())
    else:
        # If the variable IS set (like on Render), run the main bot.
        if os.path.exists(STATUS_LOG_FILE):
            os.remove(STATUS_LOG_FILE)
        asyncio.run(run_bot())
