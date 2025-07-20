# app.py
# This Flask server uses the public scraping bot to get real data for AI analysis.

import os
import asyncio
import json
import openai
from flask import Flask, render_template, request, jsonify
from bot import scrape_public_profile # Import the scraping function from bot.py

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

def get_specific_analysis_prompt(scraped_data: dict, profile_url: str):
    """Constructs a detailed, non-generic prompt for OpenAI based on scraped data."""
    
    prompt = f"""
    As a world-class social media strategist, perform a direct and brutally honest analysis of the following scraped data from the personal Facebook profile: {profile_url}.

    **Scraped Bio Text:**
    "{scraped_data['bio']}"

    **Scraped Text from Recent Posts:**
    1. "{scraped_data['posts'][0]}"
    2. "{scraped_data['posts'][1]}"
    3. "{scraped_data['posts'][2]}"
    4. "{scraped_data['posts'][3]}"
    5. "{scraped_data['posts'][4]}"

    **Your Task:**
    Based ONLY on the specific text provided above, deliver a non-generic, actionable critique. If the scraped data for posts says it failed or is empty, you MUST state that you cannot analyze the posts and cannot provide a content strategy. Do not make up a generic strategy.

    ### Bio Analysis:
    Critique the provided bio. Is it effective? Is it clear? What is wrong with it? Provide a rewritten, improved example. If no bio was found, state that and explain the importance of a good bio.

    ### Post Content Analysis:
    - What is the primary theme or topic you see in these posts?
    - Which post is the WEAKEST and why? Be specific.
    - Which post is the STRONGEST and why? Be specific.
    - If you could not analyze the posts because scraping failed, state that clearly here.

    ### Specific Viral Strategy:
    Based on their STRONGEST post, give them 3 concrete, specific, and creative ideas for new posts that expand on that successful theme. Do not give generic advice. If you could not identify a strong post, state that you cannot create a specific strategy without more data.
    """
    return prompt

@app.route('/')
def index():
    """Serves the main dashboard page."""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Receives a URL, triggers the scraping bot, gets an AI analysis,
    and returns the result.
    """
    data = request.get_json()
    profile_url = data.get('profileUrl')

    if not profile_url:
        return jsonify({'success': False, 'error': 'Profile URL is required.'}), 400

    if not OPENAI_API_KEY:
        return jsonify({'success': False, 'error': 'OpenAI API key is not configured on the server.'}), 500

    try:
        # --- Step 1: Scrape the Public Profile ---
        print(f"Starting scrape for {profile_url}")
        # Run the async scraping function
        scraped_data = asyncio.run(scrape_public_profile(profile_url))
        print(f"Scraping complete. Data: {scraped_data}")

        # --- Step 2: Get AI Analysis ---
        prompt = get_specific_analysis_prompt(scraped_data, profile_url)
        
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        analysis = response.choices[0].message.content
        
        return jsonify({'success': True, 'analysis': analysis})

    except Exception as e:
        print(f"An error occurred in the /analyze route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
