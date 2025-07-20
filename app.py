# app.py - API-based Facebook analyzer for Render
from flask import Flask, render_template_string, request, jsonify
import os
import requests
import openai
from datetime import datetime
import json

app = Flask(__name__)

# --- CONFIGURATION ---
# These keys need to be set in your Render Environment Variables
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# --- HTML TEMPLATE ---
# The entire frontend is contained in this single string for simplicity.
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Facebook Profile AI Analyzer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%);
            min-height: 100vh;
        }
        .glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .spinner {
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top: 4px solid white;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body class="text-white">
    <div class="container mx-auto px-4 py-8">
        <div class="max-w-4xl mx-auto">
            <h1 class="text-5xl font-bold text-center mb-4">🤖 Facebook AI Analyzer</h1>
            <p class="text-center text-blue-100 mb-8">Get personalized growth strategies for your Facebook profile</p>
            
            <div class="glass rounded-lg p-6 mb-6">
                <h2 class="text-2xl font-semibold mb-4">🔗 URL-Based Analysis</h2>
                
                <form id="analysisForm">
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-2">Facebook Profile URL:</label>
                        <input type="url" id="profileUrl" class="w-full p-3 rounded bg-white/20 border border-white/30 text-white placeholder-gray-300" placeholder="https://facebook.com/your.profile" required>
                        <p class="text-sm text-blue-200 mt-1">Enter your public Facebook profile URL</p>
                    </div>
                    
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-2">Focus Area:</label>
                        <select id="focusArea" class="w-full p-3 rounded bg-white/20 border border-white/30 text-white">
                            <option value="growth">Overall Growth Strategy</option>
                            <option value="engagement">Engagement Optimization</option>
                            <option value="content">Content Strategy</option>
                            <option value="viral">Viral Content Creation</option>
                            <option value="business">Business/Professional</option>
                        </select>
                    </div>
                    
                    <button type="submit" id="analyzeBtn" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition-colors">
                        🚀 Analyze Profile
                    </button>
                </form>
            </div>
            
            <div id="loadingDiv" class="hidden glass rounded-lg p-6 text-center">
                <div class="spinner mx-auto mb-4"></div>
                <p>AI is analyzing your Facebook profile...</p>
                <p class="text-sm text-blue-200 mt-2">This may take 30-60 seconds...</p>
            </div>
            
            <div id="resultsDiv" class="hidden glass rounded-lg p-6">
                <h3 class="text-2xl font-semibold mb-4">📊 Your Profile Analysis</h3>
                <div id="analysisContent" class="prose prose-invert max-w-none"></div>
            </div>
        </div>
    </div>
    <script>
        const form = document.getElementById('analysisForm');
        const loadingDiv = document.getElementById('loadingDiv');
        const resultsDiv = document.getElementById('resultsDiv');
        const analyzeBtn = document.getElementById('analyzeBtn');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const profileUrl = document.getElementById('profileUrl').value;
            const focusArea = document.getElementById('focusArea').value;

            if (!profileUrl) {
                alert('Please provide your Facebook profile URL.');
                return;
            }

            // Show loading state
            form.style.display = 'none';
            resultsDiv.classList.add('hidden');
            loadingDiv.classList.remove('hidden');

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profileUrl, focusArea })
                });

                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('analysisContent').innerHTML = formatAnalysis(data.analysis);
                    loadingDiv.classList.add('hidden');
                    resultsDiv.classList.remove('hidden');
                } else {
                    throw new Error(data.error || 'Analysis failed');
                }
                            
            } catch (error) {
                alert('Error: ' + error.message);
                loadingDiv.classList.add('hidden');
                form.style.display = 'block';
            }
        });

        function formatAnalysis(text) {
            // A simple markdown-like formatter
            return text
                .replace(/### (.*?)\\n/g, '<h3 class="text-xl font-semibold mt-6 mb-3 text-blue-300">$1</h3>')
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong class="text-white">$1</strong>')
                .replace(/\\n\\n/g, '</p><p class="mb-4">')
                .replace(/\\n/g, '<br>')
                .replace(/^\\s*/, '<p class="mb-4">')
                .replace(/\\s*$/, '</p>');
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Serves the HTML template."""
    return render_template_string(HTML_TEMPLATE)

def extract_profile_info_from_url(profile_url):
    """Extracts basic info from a Facebook URL."""
    profile_info = {'username': '', 'url': profile_url}
    if 'facebook.com/' in profile_url:
        parts = profile_url.split('facebook.com/')
        if len(parts) > 1:
            username = parts[1].split('?')[0].split('/')[0]
            profile_info['username'] = username
    return profile_info

def generate_smart_analysis_prompt(profile_url, focus_area):
    """Generates a detailed prompt for the OpenAI API."""
    profile_info = extract_profile_info_from_url(profile_url)
    username = profile_info.get('username', 'this profile')
    
    focus_prompts = {
        'growth': "Focus on follower acquisition, networking strategies, and organic reach expansion techniques.",
        'engagement': "Emphasize comment generation, share-worthy content, and community building tactics.",
        'content': "Concentrate on content planning, posting schedules, and content format optimization.",
        'viral': "Target viral content creation, trending topic engagement, and shareability factors.",
        'business': "Focus on professional networking, business page optimization, and lead generation."
    }
    focus_specific_prompt = focus_prompts.get(focus_area, focus_prompts['growth'])

    prompt = f"""
    As a Facebook growth expert, analyze this profile and provide specific recommendations.
    **PROFILE URL:** {profile_url}
    **USERNAME:** {username}
    **FOCUS AREA:** {focus_area.title()}

    Since you cannot directly access the profile's content, provide a strategic analysis based on proven Facebook growth principles, tailored to the specific focus area.

    ### Profile Analysis for @{username}
    - **Profile Optimization:** Recommendations for the profile picture, banner, and bio to maximize impact.
    - **Username Effectiveness:** Assess the username for discoverability and branding.

    ### {focus_area.title()} Strategy
    Provide specific, actionable recommendations for the chosen focus area: {focus_specific_prompt}

    ### Content Plan
    - **Content Formats:** Suggest the best mix of content (videos, images, text).
    - **Hashtag Strategy:** Recommend a hashtag strategy for their niche.
    - **Posting Times:** Suggest optimal posting times for high engagement.

    ### 30-Day Action Plan
    Provide a week-by-week plan of actionable steps.
    1.  **Week 1:** Profile setup and optimization.
    2.  **Week 2:** Content strategy implementation.
    3.  **Week 3:** Engagement and community building.
    4.  **Week 4:** Analytics and refinement.

    Provide advice that the user can implement immediately.
    """
    return prompt

@app.route('/analyze', methods=['POST'])
def analyze_profile():
    """Handles the analysis request from the frontend."""
    try:
        data = request.json
        profile_url = data.get('profileUrl', '')
        focus_area = data.get('focusArea', 'growth')

        if not OPENAI_API_KEY:
            return jsonify({'success': False, 'error': 'OpenAI API key is not configured on the server.'})

        if not profile_url:
            return jsonify({'success': False, 'error': 'Profile URL is required.'})

        prompt = generate_smart_analysis_prompt(profile_url, focus_area)
        
        # Call OpenAI API
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        
        analysis = response.choices[0].message.content
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })

    except Exception as e:
        print(f"Error during analysis: {e}")
        return jsonify({
            'success': False,
            'error': f'Analysis failed: {str(e)}'
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
