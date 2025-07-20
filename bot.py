# bot.py
# This bot logs in, scrapes specific content from your profile, and sends it to OpenAI for analysis.

import os
import asyncio
import json
import openai
from playwright.async_api import async_playwright
from datetime import datetime

# --- CONFIGURATION ---
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/your.facebook.profile.name' # <-- IMPORTANT: CHANGE THIS
STATUS_LOG_FILE = 'status.log'
SESSION_FILE = 'session.json'

# --- API KEY FROM ENVIRONMENT ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

def log_status(message, level="INFO"):
    """Writes a status message to the log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] [{level}] {message}\n"
    print(full_message, end='')
    with open(STATUS_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(full_message)

async def get_specific_analysis(scraped_data):
    """Sends scraped data to OpenAI and gets a specific analysis."""
    if not OPENAI_API_KEY:
        return "CRITICAL: OpenAI API key not found. Cannot perform analysis."

    log_status("Sending your specific profile data to AI for analysis...")
    
    # Construct a detailed prompt with the real data
    prompt = f"""
    As an expert social media strategist, analyze the following scraped data from a user's personal Facebook profile.

    **Scraped Bio Text:**
    "{scraped_data['bio']}"

    **Scraped Text from Last 5 Posts:**
    1. "{scraped_data['posts'][0]}"
    2. "{scraped_data['posts'][1]}"
    3. "{scraped_data['posts'][2]}"
    4. "{scraped_data['posts'][3]}"
    5. "{scraped_data['posts'][4]}"

    Based ONLY on this specific information, provide a direct, non-generic analysis.

    ### Bio Analysis:
    Critique the bio. Is it effective? What specific words or phrases should be changed to be more engaging? Provide a rewritten example.

    ### Post Content Analysis:
    What is the user's primary content theme based on these posts? Are the posts engaging? Point out the weakest post and explain why. Point out the strongest post and explain why.

    ### Specific Viral Strategy:
    Based on their strongest post, give them 3 concrete, specific ideas for new posts that follow that successful theme.
    """

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        analysis = response.choices[0].message.content.strip()
        log_status("Specific analysis received from AI.", level="SUCCESS")
        return analysis
    except Exception as e:
        log_status(f"Error calling OpenAI API: {e}", level="ERROR")
        return "Error: Could not get analysis from AI."


async def run_bot():
    """Main function to run the automation bot."""
    log_status("AI Analyzer process started.")
    
    if not os.path.exists(SESSION_FILE):
        log_status("CRITICAL: session.json not found. Please log in first.", level="CRITICAL")
        return

    async with async_playwright() as p:
        log_status("Launching browser...")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=SESSION_FILE)
        page = await context.new_page()
        
        log_status("Login successful. Navigating to your profile...")
        await page.goto(FACEBOOK_PROFILE_URL, wait_until="networkidle")
        log_status("Profile page loaded.")

        # --- SCRAPING LOGIC ---
        log_status("Scraping profile data...")
        
        # Scrape Bio (Note: Facebook's structure changes; this selector may need updates)
        bio_text = "No bio found."
        try:
            bio_element = page.locator('div[data-pagelet="ProfileTimeline"] ul > li:first-child span').first
            bio_text = await bio_element.inner_text(timeout=5000)
            log_status("Successfully scraped bio.", level="SUCCESS")
        except Exception:
            log_status("Could not find a bio with the specific selector. Using default.", level="WARNING")

        # Scrape Posts
        post_texts = []
        try:
            # This selector targets divs that are likely to be individual posts in the timeline.
            post_locators = page.locator('div[data-pagelet*="ProfileTimeline"] div[role="article"]')
            count = await post_locators.count()
            log_status(f"Found {count} potential post elements.")
            
            for i in range(min(5, count)):
                post_text_content = await post_locators.nth(i).inner_text()
                # Clean up the text to get the main content, avoiding "Like, Comment, Share" etc.
                cleaned_post = post_text_content.split('\n')[0]
                post_texts.append(cleaned_post)
            
            # Ensure we have 5 posts for the prompt, even if fewer were found
            while len(post_texts) < 5:
                post_texts.append("(No post found)")

            log_status("Successfully scraped recent posts.", level="SUCCESS")
        except Exception as e:
            log_status(f"Could not scrape posts: {e}", level="ERROR")
            post_texts = ["(Error scraping posts)"] * 5


        # --- ANALYSIS ---
        scraped_data = {"bio": bio_text, "posts": post_texts}
        specific_analysis = await get_specific_analysis(scraped_data)

        log_status("--- SPECIFIC AI ANALYSIS ---", level="AI_ANALYSIS")
        log_status(specific_analysis, level="AI_ANALYSIS")
        log_status("--- END OF ANALYSIS ---", level="AI_ANALYSIS")
        
        log_status("Analysis complete. Bot has finished its task.")
        await browser.close()

if __name__ == '__main__':
    if os.path.exists(STATUS_LOG_FILE):
        os.remove(STATUS_LOG_FILE)
    asyncio.run(run_bot())
