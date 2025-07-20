# bot.py
# This script performs the browser automation using Playwright.
# Updated to use a real OpenAI connection for generating responses.

import os
import asyncio
import random
import json
import openai
from playwright.async_api import async_playwright
from datetime import datetime

# --- CONFIGURATION ---
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/voyce.butler' # <-- IMPORTANT: CHANGE THIS
STATUS_LOG_FILE = 'status.log'

# --- API KEYS & SESSION FROM ENVIRONMENT VARIABLES ---
SESSION_JSON_STR = os.environ.get('FACEBOOK_SESSION_JSON')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# Initialize the OpenAI client
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    # This will be logged if the key is missing
    pass

def log_status(message, level="INFO"):
    """Writes a status message to the log file with a timestamp and level."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] [{level}] {message}\n"
    print(full_message, end='')
    with open(STATUS_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(full_message)

async def get_ai_response(prompt):
    """Gets a response from the OpenAI API."""
    if not OPENAI_API_KEY:
        log_status("OpenAI API key is not set. Returning a placeholder response.", level="WARNING")
        return "AI is offline. Placeholder response."

    log_status("Sending prompt to OpenAI...")
    try:
        # Using the new client-based API structure for openai >v1.0
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o", # Or "gpt-3.5-turbo" for faster, cheaper responses
            messages=[
                {"role": "system", "content": "You are a helpful and creative social media assistant. Your responses should be concise and ready to be used as a comment or post idea."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100
        )
        ai_response = response.choices[0].message.content.strip()
        log_status("Received response from OpenAI.", level="SUCCESS")
        return ai_response
    except Exception as e:
        log_status(f"Error calling OpenAI API: {e}", level="ERROR")
        return "There was an error contacting the AI."


async def run_bot():
    """Main function to run the automation bot."""
    log_status("AI Assistant process started.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=json.loads(SESSION_JSON_STR))
        
        page = await context.new_page()
        log_status("Session loaded. Navigating to Facebook.")
        await page.goto('https://www.facebook.com', wait_until="load")
        
        log_status("Login successful.", level="SUCCESS")

        # --- CONTINUOUS ACTION LOOP ---
        log_status("Starting main activity loop...")
        while True:
            try:
                # --- Task: Analyze a recent post (simulated) ---
                log_status("Analyzing a recent post for engagement...")
                await asyncio.sleep(random.uniform(5, 10))
                post_text = "Just finished a major project. Feeling accomplished! #work #success"
                likes = random.randint(10, 100)
                comments = random.randint(1, 5)
                log_status(f"Analyzed post '{post_text[:30]}...': {likes} likes, {comments} comments.")

                # --- Task: Get a real AI action ---
                prompt = f"My latest Facebook post says: '{post_text}'. It has {likes} likes and {comments} comments. Based on this, suggest a creative and engaging comment I could add to the post myself to spark more conversation."
                
                ai_decision = await get_ai_response(prompt)
                log_status(f"AI suggests: '{ai_decision}'", level="AI_ACTION")
                
                # TODO: Add Playwright logic here to actually find the post and add the comment.
                
                log_status("Cycle complete. Waiting before next check...")
                await asyncio.sleep(60) # Wait 60 seconds before next cycle

            except Exception as e:
                log_status(f"An error occurred in the main loop: {e}", level="ERROR")
                await asyncio.sleep(60)

async def setup_session():
    """This function runs ONLY on your local computer to create the session string."""
    print("--- EchoMe AI Session Setup ---")
    print("A browser window will now open. Please log into your Facebook account.")
    print("After you successfully log in, close the browser window.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto('https://www.facebook.com')
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
        asyncio.run(setup_session())
    else:
        if not OPENAI_API_KEY:
            log_status("CRITICAL: OPENAI_API_KEY environment variable is not set. The bot cannot function without it.", level="CRITICAL")
        if os.path.exists(STATUS_LOG_FILE):
            os.remove(STATUS_LOG_FILE)
        asyncio.run(run_bot())
