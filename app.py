# app.py - Render-compatible Facebook analyzer
from flask import Flask, render_template_string, request, jsonify
import os
import requests
import openai
from datetime import datetime

app = Flask(__name__)

# Get API key from Render environment variables
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Facebook Profile AI Analyzer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { 
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
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
            <h1 class="text-4xl font-bold text-center mb-8">🤖 Facebook Profile AI Analyzer</h1>
            
            <div class="glass rounded-lg p-6 mb-6">
                <h2 class="text-2xl font-semibold mb-4">Manual Content Input</h2>
                <p class="mb-4 text-gray-200">Since we can't automatically scrape Facebook, please manually copy and paste your profile content below:</p>
                
                <form id="analysisForm">
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-2">Your Facebook Profile URL:</label>
                        <input type="url" id="profileUrl" class="w-full p-3 rounded bg-white/20 border border-white/30 text-white placeholder-gray-300" placeholder="https://facebook.com/your.profile" required>
                    </div>
                    
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-2">Your Bio/About Section:</label>
                        <textarea id="bioText" rows="3" class="w-full p-3 rounded bg-white/20 border border-white/30 text-white placeholder-gray-300" placeholder="Copy and paste your Facebook bio here..."></textarea>
                    </div>
                    
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-2">Recent Posts (copy 3-5 recent posts):</label>
                        <textarea id="postsText" rows="8" class="w-full p-3 rounded bg-white/20 border border-white/30 text-white placeholder-gray-300" placeholder="Copy and paste your recent Facebook posts here, one per paragraph..."></textarea>
                    </div>
                    
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-2">Your Goals:</label>
                        <select id="goals" class="w-full p-3 rounded bg-white/20 border border-white/30 text-white">
                            <option value="general">General growth and engagement</option>
                            <option value="business">Business/professional growth</option>
                            <option value="personal">Personal brand building</option>
                            <option value="viral">Viral content creation</option>
                            <option value="networking">Networking and connections</option>
                        </select>
                    </div>
                    
                    <button type="submit" id="analyzeBtn" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition-colors">
                        🚀 Analyze My Profile
                    </button>
                </form>
            </div>
            
            <div id="loadingDiv" class="hidden glass rounded-lg p-6 text-center">
                <div class="spinner mx-auto mb-4"></div>
                <p>AI is analyzing your profile content...</p>
            </div>
            
            <div id="resultsDiv" class="hidden glass rounded-lg p-6">
                <h3 class="text-2xl font-semibold mb-4">📊 Your Personalized Analysis</h3>
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
            const bioText = document.getElementById('bioText').value;
            const postsText = document.getElementById('postsText').value;
            const goals = document.getElementById('goals').value;

            if (!profileUrl || (!bioText && !postsText)) {
                alert('Please provide your profile URL and at least your bio or some posts.');
                return;
            }

            // Show loading
            form.style.display = 'none';
            loadingDiv.classList.remove('hidden');
            
            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        profileUrl,
                        bioText,
                        postsText,
                        goals
                    })
                });

                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('analysisContent').innerHTML = 
                        data.analysis.replace(/\\n/g, '<br>').replace(/### /g, '<h3 class="text-xl font-semibold mt-6 mb-3">').replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
                    
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
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/analyze', methods=['POST'])
def analyze_profile():
    try:
        data = request.json
        profile_url = data.get('profileUrl', '')
        bio_text = data.get('bioText', '')
        posts_text = data.get('postsText', '')
        goals = data.get('goals', 'general')
        
        if not OPENAI_API_KEY:
            return jsonify({'success': False, 'error': 'OpenAI API key not configured'})
        
        # Create analysis prompt
        prompt = f"""
As a Facebook growth expert, analyze this REAL profile content and provide specific, actionable recommendations:

**PROFILE URL:** {profile_url}

**BIO/ABOUT SECTION:**
{bio_text if bio_text else "No bio provided"}

**RECENT POSTS:**
{posts_text if posts_text else "No posts provided"}

**USER'S GOALS:** {goals}

Provide a comprehensive analysis with these sections:

### Bio Analysis & Optimization
- Critique the current bio (or lack thereof)
- Provide a rewritten, optimized bio example
- Explain what makes it more effective

### Content Strategy Analysis
- Analyze the themes and patterns in the posts
- Identify the strongest and weakest content
- Suggest content pillars for consistent posting

### Viral Growth Tactics
- 5 specific post ideas based on their successful content patterns
- Hashtag strategy for their niche
- Engagement tactics to boost reach
- Collaboration opportunities

### Posting Strategy
- Optimal posting schedule
- Content mix recommendations
- Audience engagement techniques

### Immediate Action Plan
- 3 changes to make this week
- Content calendar for next 30 days
- Profile optimization checklist

Be specific and actionable. Reference their actual content when making suggestions. If content is limited, focus on what can be improved and suggest data collection methods.
"""

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
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
