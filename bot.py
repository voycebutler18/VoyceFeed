# bot.py
# This is the main automation script. It reads the session file created by
# the login form and performs the continuous AI tasks.

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
SESSION_FILE = 'session.json' # The bot will read the session from this file

# --- API KEY FROM ENVIRONMENT ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# Initialize the OpenAI client
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

def log_status(message, level="INFO"):
    """Writes a status message to the log file with a timestamp and level."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] [{level}] {message}\n"
    print(full_message, end='') # Also print to server console
    with open(STATUS_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(full_message)

async def get_ai_response(prompt):
    """Gets a response from the OpenAI API."""
    if not OPENAI_API_KEY:
        log_status("OpenAI API key is not set. Returning a placeholder.", level="WARNING")
        return "AI is offline. Placeholder response."

    log_status("Sending prompt to OpenAI...")
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful social media assistant. Your responses should be concise and ready to be used as a comment or post idea."},
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
    
    if not os.path.exists(SESSION_FILE):
        log_status("CRITICAL: session.json not found. Please log in through the web dashboard first.", level="CRITICAL")
        return

    async with async_playwright() as p:
        log_status("Launching browser...")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        
        log_status(f"Loading session from {SESSION_FILE}...")
        with open(SESSION_FILE, 'r') as f:
            storage_state = json.load(f)
        
        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()
        
        log_status("Session loaded. Navigating to Facebook to verify login.")
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
                prompt = f"My latest Facebook post says: '{post_text}'. It has {likes} likes and {comments} comments. Suggest a creative comment I could add to spark more conversation."
                
                ai_decision = await get_ai_response(prompt)
                log_status(f"AI suggests: '{ai_decision}'", level="AI_ACTION")
                
                # TODO: Add Playwright logic here to actually post the comment.
                
                log_status("Cycle complete. Waiting before next check...")
                await asyncio.sleep(60) # Wait 60 seconds before next cycle

            except Exception as e:
                log_status(f"An error occurred in the main loop: {e}", level="ERROR")
                await asyncio.sleep(60)

if __name__ == '__main__':
    if not OPENAI_API_KEY:
        log_status("CRITICAL: OPENAI_API_KEY environment variable is not set.", level="CRITICAL")
    
    asyncio.run(run_bot())
