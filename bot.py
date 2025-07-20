# improved_bot.py
# Enhanced Facebook profile analyzer that actually scrapes real content

import os
import asyncio
import json
import openai
from playwright.async_api import async_playwright
from datetime import datetime
import time

# --- CONFIGURATION ---
FACEBOOK_PROFILE_URL = 'https://www.facebook.com/voyce.butler'  # Your profile URL
STATUS_LOG_FILE = 'analysis_log.txt'
SESSION_FILE = 'facebook_session.json'

# --- API KEY FROM ENVIRONMENT ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

def log_status(message, level="INFO"):
    """Writes a status message to the log file and console."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] [{level}] {message}"
    print(full_message)
    with open(STATUS_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(full_message + '\n')

async def login_to_facebook(page):
    """Handle Facebook login process."""
    log_status("Starting Facebook login process...")
    
    try:
        await page.goto('https://www.facebook.com/', wait_until="networkidle")
        
        # Check if already logged in
        if 'facebook.com' in page.url and '/login' not in page.url:
            log_status("Already logged in to Facebook")
            return True
            
        log_status("Please log in to Facebook manually in the browser window...")
        log_status("The browser will stay open for 60 seconds for you to log in")
        
        # Wait for successful login (URL change or specific element)
        try:
            await page.wait_for_url(lambda url: '/login' not in url and 'facebook.com' in url, timeout=60000)
            log_status("Login successful!")
            
            # Save session for future use
            await page.context.storage_state(path=SESSION_FILE)
            log_status("Session saved for future use")
            return True
            
        except Exception as e:
            log_status(f"Login timeout or failed: {e}", "ERROR")
            return False
            
    except Exception as e:
        log_status(f"Login error: {e}", "ERROR")
        return False

async def scrape_profile_content(page, profile_url):
    """Enhanced scraping function with multiple fallback strategies."""
    log_status(f"Navigating to profile: {profile_url}")
    
    try:
        await page.goto(profile_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)  # Wait for dynamic content to load
        
        scraped_data = {
            'bio': '',
            'posts': [],
            'profile_info': '',
            'recent_activity': []
        }
        
        # Scrape bio/intro section with multiple selectors
        log_status("Attempting to scrape bio/intro section...")
        bio_selectors = [
            'div[data-pagelet="ProfileTimeline"] div[data-overviewsection="intro"]',
            'div[data-pagelet="ProfileComposer"] + div',
            'div.x1a0jr6h.x6ikm8r.x10wlt62',
            'div[data-ad-preview="message"]'
        ]
        
        for selector in bio_selectors:
            try:
                bio_elements = await page.locator(selector).all()
                for element in bio_elements:
                    text = await element.inner_text(timeout=3000)
                    if text and len(text) > 10:
                        scraped_data['bio'] += text + ' '
                        break
            except:
                continue
                
        if not scraped_data['bio']:
            scraped_data['bio'] = "No bio information found"
        
        # Scrape recent posts with multiple strategies
        log_status("Attempting to scrape recent posts...")
        post_selectors = [
            'div[role="main"] div[data-pagelet="ProfileTimeline"] div[role="article"]',
            'div[role="feed"] > div',
            'div[data-pagelet="ProfileTimeline"] div[data-ad-preview="message"]',
            'div.x1a0jr6h.x193iq5w.x1lliihq'
        ]
        
        posts_found = 0
        for selector in post_selectors:
            if posts_found >= 5:
                break
                
            try:
                post_elements = await page.locator(selector).all()
                for i, element in enumerate(post_elements[:10]):  # Check first 10 elements
                    if posts_found >= 5:
                        break
                        
                    try:
                        post_text = await element.inner_text(timeout=2000)
                        if post_text and len(post_text) > 20 and post_text not in scraped_data['posts']:
                            scraped_data['posts'].append(post_text[:500])  # Limit length
                            posts_found += 1
                            log_status(f"Found post {posts_found}: {post_text[:100]}...")
                    except:
                        continue
            except:
                continue
        
        # Fill remaining slots if needed
        while len(scraped_data['posts']) < 5:
            scraped_data['posts'].append("No additional post content found")
        
        # Try to get profile information
        log_status("Attempting to scrape profile information...")
        try:
            profile_name = await page.locator('h1').first.inner_text(timeout=5000)
            scraped_data['profile_info'] = f"Profile name: {profile_name}"
        except:
            scraped_data['profile_info'] = "Could not extract profile name"
        
        log_status(f"Scraping completed. Found bio: {bool(scraped_data['bio'])}, Posts: {len([p for p in scraped_data['posts'] if 'No additional' not in p])}")
        return scraped_data
        
    except Exception as e:
        log_status(f"Scraping error: {e}", "ERROR")
        return {
            'bio': "Scraping failed - could not access profile content",
            'posts': ["Scraping failed"] * 5,
            'profile_info': "Could not access profile",
            'recent_activity': []
        }

async def get_ai_analysis(scraped_data):
    """Send scraped data to OpenAI for detailed analysis."""
    if not OPENAI_API_KEY:
        return "ERROR: OpenAI API key not found. Please set OPENAI_API_KEY environment variable."

    log_status("Sending scraped data to OpenAI for analysis...")
    
    prompt = f"""
As an expert social media growth strategist, analyze this REAL data scraped from a Facebook profile and provide specific, actionable recommendations.

**ACTUAL PROFILE DATA:**

**Bio/Intro:** {scraped_data['bio']}

**Profile Info:** {scraped_data['profile_info']}

**Recent Posts (actual content):**
1. {scraped_data['posts'][0]}
2. {scraped_data['posts'][1]} 
3. {scraped_data['posts'][2]}
4. {scraped_data['posts'][3]}
5. {scraped_data['posts'][4]}

**ANALYSIS REQUIREMENTS:**
You must provide specific, data-driven recommendations based ONLY on the actual content above. Do not give generic advice.

### Bio Analysis
- Critique the actual bio text provided
- Identify specific weaknesses in the current bio
- Provide a rewritten version that's more compelling
- If no bio was found, explain why this is critical

### Content Pattern Analysis  
- What specific themes/topics appear in the actual posts?
- Which post performed best potential (most engaging content)?
- What content gaps do you identify?
- What's the overall tone and style?

### Specific Growth Recommendations
Based on the actual posting patterns, provide:
- 3 specific post ideas that build on their successful content themes
- Optimal posting strategy for their specific content style  
- Specific hashtag recommendations for their niche
- Engagement tactics tailored to their audience

### Immediate Action Items
List 5 specific, actionable steps they should take this week based on the analysis.

**CRITICAL:** If the scraping failed or no real content was found, you MUST state this clearly and explain that a proper analysis cannot be performed without actual profile data.
"""

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        
        analysis = response.choices[0].message.content.strip()
        log_status("AI analysis completed successfully")
        return analysis
        
    except Exception as e:
        log_status(f"OpenAI API error: {e}", "ERROR")
        return f"Error getting AI analysis: {e}"

async def main():
    """Main execution function."""
    log_status("=== Facebook Profile AI Analyzer Started ===")
    
    # Clear previous log
    if os.path.exists(STATUS_LOG_FILE):
        os.remove(STATUS_LOG_FILE)
    
    async with async_playwright() as p:
        # Launch browser (headless=False so you can see the login)
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Try to load existing session
            if os.path.exists(SESSION_FILE):
                log_status("Loading existing Facebook session...")
                await context.close()
                context = await browser.new_context(storage_state=SESSION_FILE)
                page = await context.new_page()
            
            # Login to Facebook
            if not await login_to_facebook(page):
                log_status("Login failed. Exiting.", "ERROR")
                return
            
            # Scrape profile content
            scraped_data = await scrape_profile_content(page, FACEBOOK_PROFILE_URL)
            
            # Get AI analysis
            analysis = await get_ai_analysis(scraped_data)
            
            # Output results
            log_status("=== AI ANALYSIS RESULTS ===")
            log_status(analysis)
            log_status("=== END ANALYSIS ===")
            
            # Save results to file
            with open('facebook_analysis_results.txt', 'w', encoding='utf-8') as f:
                f.write("=== FACEBOOK PROFILE AI ANALYSIS ===\n\n")
                f.write(f"Profile URL: {FACEBOOK_PROFILE_URL}\n")
                f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("=== SCRAPED DATA ===\n")
                f.write(f"Bio: {scraped_data['bio']}\n\n")
                f.write("Posts:\n")
                for i, post in enumerate(scraped_data['posts'], 1):
                    f.write(f"{i}. {post}\n\n")
                f.write("=== AI ANALYSIS ===\n")
                f.write(analysis)
            
            log_status("Analysis complete! Results saved to facebook_analysis_results.txt")
            
        except Exception as e:
            log_status(f"Main execution error: {e}", "ERROR")
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
