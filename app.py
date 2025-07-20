from flask import Flask, request, jsonify, render_template, render_template_string, send_from_directory
from flask_cors import CORS
import os
import base64
import json
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import requests
import hashlib

# Get client IP address
def get_client_ip():
    """Get the client's IP address"""
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        return request.environ['REMOTE_ADDR']
    else:
        return request.environ['HTTP_X_FORWARDED_FOR']

def get_ip_hash():
    """Get a hash of the client's IP for tracking"""
    ip = get_client_ip()
    return hashlib.md5(ip.encode()).hexdigest()

def has_used_free_trial(ip_hash):
    """Check if this IP has already used the free trial"""
    try:
        # In a real app, you'd store this in a database
        # For now, we'll use a simple file-based approach
        trial_file = 'free_trials_used.txt'
        if os.path.exists(trial_file):
            with open(trial_file, 'r') as f:
                used_ips = f.read().splitlines()
                return ip_hash in used_ips
        return False
    except:
        return False

def mark_free_trial_used(ip_hash):
    """Mark this IP as having used the free trial"""
    try:
        trial_file = 'free_trials_used.txt'
        with open(trial_file, 'a') as f:
            f.write(f"{ip_hash}\n")
    except:
        pass

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-not-for-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def encode_image_to_base64(image_path):
    """Convert image to base64 for API"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Base64 encoding error: {e}")
        return None

def call_openai_api(image_paths, persona):
    """Call OpenAI API using requests instead of openai library"""
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("OpenAI API key not found")
            return None
        
        # Prepare images for API
        image_messages = []
        for path in image_paths[:2]:  # Limit to 2 images
            base64_image = encode_image_to_base64(path)
            if base64_image:
                image_messages.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "low"
                    }
                })
        
        if not image_messages:
            return None
        
        persona_context = get_persona_context(persona)
        
        prompt = f"""
        Analyze these property images and create marketing content for {persona}.
        
        Target: {persona_context['description']}
        Priorities: {persona_context['priorities']}
        
        Create a compelling property description that highlights features appealing to {persona}.
        Keep it under 300 words and focus on emotional appeal.
        """
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_messages
                    ]
                }
            ],
            "max_tokens": 1000
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            print(f"OpenAI API Error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return None

def get_persona_context(persona):
    """Get detailed context for different buyer personas"""
    personas = {
        "First-Time Homebuyers": {
            "description": "Young professionals or couples (25-35) buying their first home",
            "priorities": "affordability, move-in ready, good neighborhood, future resale value",
            "tone": "encouraging, educational, emphasizing security and smart investment",
            "pain_points": "budget constraints, mortgage concerns, inexperience with home buying"
        },
        "Luxury Seeker": {
            "description": "High-income individuals seeking premium properties",
            "priorities": "exclusivity, high-end finishes, prestige, unique features, privacy",
            "tone": "sophisticated, aspirational, emphasizing quality and status",
            "pain_points": "finding truly unique properties, ensuring privacy, investment value"
        },
        "Growing Family": {
            "description": "Families with children or planning to have children",
            "priorities": "space, safety, good schools, family-friendly features, neighborhood",
            "tone": "warm, family-focused, emphasizing comfort and practical benefits",
            "pain_points": "finding enough space, ensuring child safety, school districts"
        },
        "Downsizing Retirees": {
            "description": "Empty nesters or retirees looking to simplify",
            "priorities": "low maintenance, accessibility, proximity to amenities, security",
            "tone": "respectful, focusing on lifestyle benefits and ease of living",
            "pain_points": "letting go of larger home, finding right-sized space, accessibility needs"
        }
    }
    return personas.get(persona, personas["First-Time Homebuyers"])

def analyze_property_with_ai(image_paths, persona):
    """Use OpenAI's vision model to analyze property images and generate marketing content"""
    
    # Try calling OpenAI API
    ai_content = call_openai_api(image_paths, persona)
    
    if ai_content:
        # Format AI response into structured content
        return {
            "listing": f"<h2>Perfect Home for {persona}!</h2><p>{ai_content}</p>",
            "social": f"<h3>Social Media Posts:</h3><p>🏡 New listing perfect for {persona.lower()}! {ai_content[:150]}... #RealEstate #NewListing #{persona.replace(' ', '')}</p>",
            "video": f"<h3>Video Script:</h3><p>30-second tour highlighting the best features for {persona.lower()}. {ai_content[:200]}...</p>",
            "points": f"<h3>Key Selling Points for {persona}:</h3><ul><li><strong>Perfect Location</strong></li><li><strong>Move-in Ready</strong></li><li><strong>Great for {persona}</strong></li><li><strong>Modern Updates</strong></li><li><strong>Excellent Value</strong></li></ul>",
            "analysis": f"AI analysis completed for {persona} based on property images."
        }
    else:
        # Fall back to demo content
        return generate_fallback_content(persona)

def generate_fallback_content(persona):
    """Generate fallback content when AI fails"""
    persona_context = get_persona_context(persona)
    
    return {
        "listing": f"""
        <h2>Perfect Home for {persona}!</h2>
        <p>This beautiful property offers everything that {persona_context['description']} are looking for. 
        With thoughtful design and modern amenities, this home addresses key priorities like {persona_context['priorities']}. 
        The space has been carefully maintained and offers excellent value in today's market. 
        Don't miss this opportunity to own a home that truly fits your lifestyle and needs.</p>
        """,
        "social": f"""
        <h3>Facebook Post:</h3>
        <p>🏡 JUST LISTED! Perfect home for {persona.lower()}! This beautiful property checks all the boxes - 
        {persona_context['priorities'].split(',')[0]} and so much more. Schedule your private tour today! 
        #RealEstate #NewListing #{persona.replace(' ', '')} #DreamHome</p>
        
        <h3>Instagram Story:</h3>
        <p>✨ New listing alert! Swipe to see why this home is perfect for {persona.lower()} ➡️ 
        DM for details! #JustListed #RealEstate</p>
        """,
        "video": f"""
        <h3>30-Second Video Script:</h3>
        <p><strong>Scene 1 (0-5s):</strong> Exterior shot of the home<br>
        <strong>Voiceover:</strong> "Looking for the perfect home as {persona_context['description']}?"</p>
        
        <p><strong>Scene 2 (5-15s):</strong> Interior walkthrough of main areas<br>
        <strong>Voiceover:</strong> "This beautiful property offers everything you need - {persona_context['priorities'][:50]}..."</p>
        
        <p><strong>Scene 3 (15-25s):</strong> Highlight key features<br>
        <strong>Voiceover:</strong> "From the moment you walk in, you'll feel at home."</p>
        
        <p><strong>Scene 4 (25-30s):</strong> Contact information<br>
        <strong>Voiceover:</strong> "Schedule your private tour today. Your dream home is waiting."</p>
        """,
        "points": f"""
        <h3>Key Selling Points for {persona}:</h3>
        <ul>
        <li><strong>Perfect Location:</strong> Situated in a desirable neighborhood that meets your lifestyle needs</li>
        <li><strong>Move-In Ready:</strong> Beautifully maintained and updated throughout</li>
        <li><strong>Smart Investment:</strong> Excellent value in today's market with strong appreciation potential</li>
        <li><strong>Lifestyle Focused:</strong> Designed with {persona_context['priorities'].split(',')[0]} in mind</li>
        <li><strong>Quality Features:</strong> Modern amenities and thoughtful details throughout</li>
        </ul>
        """,
        "analysis": f"Property analyzed for {persona} targeting their key priorities: {persona_context['priorities']}"
    }

@app.route('/')
def homepage():
    """Serve the homepage/landing page"""
    return render_template('homepage.html')

@app.route('/try-free')
def try_free():
    """Serve the free trial page"""
    ip_hash = get_ip_hash()
    already_used = has_used_free_trial(ip_hash)
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Try AuraMarkt Free - No Payment Required</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #0a0a0a; color: #e2e8f0; }
            .glass-pane { background: rgba(255, 255, 255, 0.03); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); }
            .spinner { border: 4px solid rgba(255, 255, 255, 0.2); border-radius: 50%; border-top-color: #10b981; width: 48px; height: 48px; animation: spin 1s ease-in-out infinite; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .persona-card { transition: all 0.3s ease; border: 2px solid transparent; }
            .persona-card.selected { border-color: #10b981; transform: scale(1.05); background: rgba(16, 185, 129, 0.1); }
        </style>
    </head>
    <body>
        <div class="container mx-auto p-4 sm:p-6 lg:p-8">
            <header class="text-center mb-12">
                <h1 class="text-5xl sm:text-6xl font-black text-white">Try AuraMarkt Free</h1>
                <p class="text-slate-400 mt-2 text-lg">Get one FREE AI marketing kit • No payment required</p>
                {% if already_used %}
                <div class="mt-4 bg-red-600/20 border border-red-500/30 rounded-lg p-4 max-w-lg mx-auto">
                    <p class="text-red-300 text-sm">
                        <span class="font-semibold">⚠️ Free trial already used</span><br>
                        You've already tried our free service. Ready for unlimited access?
                    </p>
                    <a href="/" class="inline-block mt-3 bg-violet-600 hover:bg-violet-700 text-white font-bold py-2 px-4 rounded transition-colors">
                        View Plans
                    </a>
                </div>
                {% else %}
                <div class="mt-4 bg-green-600/20 border border-green-500/30 rounded-lg p-4 max-w-lg mx-auto">
                    <p class="text-green-300 text-sm">
                        <span class="font-semibold">🎉 Free trial available!</span><br>
                        Upload your property photos and get one marketing kit free
                    </p>
                </div>
                {% endif %}
            </header>

            {% if not already_used %}
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div class="lg:col-span-1 flex flex-col gap-8">
                    <div class="glass-pane p-6 rounded-2xl">
                        <h2 class="text-xl font-bold text-white mb-4 flex items-center">
                            <span class="bg-green-500 text-white rounded-full w-8 h-8 flex items-center justify-center mr-3">1</span> 
                            Upload Property Photos
                        </h2>
                        <div id="image-uploader" class="mt-4 border-2 border-dashed border-slate-600 rounded-lg p-6 text-center cursor-pointer hover:border-green-400 transition-colors">
                            <input type="file" id="file-input" multiple accept="image/*" class="hidden">
                            <svg class="mx-auto h-12 w-12 text-slate-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
                            </svg>
                            <p class="mt-2 text-slate-400">Drag & drop or click to upload</p>
                            <p class="text-xs text-slate-500">Up to 5 images (JPG, PNG)</p>
                        </div>
                        <div id="preview-grid" class="mt-4 grid grid-cols-3 gap-2"></div>
                    </div>

                    <div class="glass-pane p-6 rounded-2xl">
                        <h2 class="text-xl font-bold text-white mb-4 flex items-center">
                            <span class="bg-green-500 text-white rounded-full w-8 h-8 flex items-center justify-center mr-3">2</span> 
                            Select Buyer Persona
                        </h2>
                        <div id="persona-selector" class="grid grid-cols-2 gap-4 mt-4">
                            <div class="persona-card p-4 rounded-lg cursor-pointer text-center" data-persona="First-Time Homebuyers">
                                <p class="text-3xl">👨‍👩‍👧</p><p class="font-semibold mt-1">First-Time Buyers</p>
                            </div>
                            <div class="persona-card p-4 rounded-lg cursor-pointer text-center" data-persona="Luxury Seeker">
                                <p class="text-3xl">💎</p><p class="font-semibold mt-1">Luxury Seeker</p>
                            </div>
                            <div class="persona-card p-4 rounded-lg cursor-pointer text-center" data-persona="Growing Family">
                                <p class="text-3xl">🏡</p><p class="font-semibold mt-1">Growing Family</p>
                            </div>
                            <div class="persona-card p-4 rounded-lg cursor-pointer text-center" data-persona="Downsizing Retirees">
                                <p class="text-3xl">🌅</p><p class="font-semibold mt-1">Downsizing Retirees</p>
                            </div>
                        </div>
                    </div>
                    
                    <button id="generate-button" class="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-4 px-6 rounded-lg transition-colors flex items-center justify-center disabled:bg-slate-600 disabled:cursor-not-allowed">
                        Generate FREE Marketing Kit
                    </button>
                </div>

                <div class="lg:col-span-2 glass-pane p-6 rounded-2xl">
                    <h2 class="text-2xl font-bold text-white mb-4">Your FREE AI-Generated Marketing Kit</h2>
                    <div id="output-container">
                        <div id="loading-spinner" class="hidden flex-col items-center justify-center h-full text-center py-20">
                            <div class="spinner"></div>
                            <p class="mt-4 text-slate-400">AI is creating your free marketing kit...</p>
                        </div>
                        <div id="placeholder-text" class="text-center py-20">
                            <p class="text-slate-500">Upload photos and select a persona to get your free marketing kit!</p>
                        </div>
                        <div id="results-container" class="hidden">
                            <div id="tab-content" class="prose prose-invert max-w-none prose-headings:text-green-400"></div>
                            <div class="mt-8 bg-violet-600/20 border border-violet-500/30 rounded-lg p-6 text-center">
                                <h3 class="text-2xl font-bold text-white mb-2">Like what you see?</h3>
                                <p class="text-violet-200 mb-4">Get unlimited marketing kits with our paid plans</p>
                                <a href="/" class="inline-block bg-violet-600 hover:bg-violet-700 text-white font-bold py-3 px-6 rounded-lg transition-colors">
                                    View Plans & Pricing
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            {% endif %}
        </div>

        <script>
            {% if not already_used %}
            const uploader = document.getElementById('image-uploader');
            const fileInput = document.getElementById('file-input');
            const previewGrid = document.getElementById('preview-grid');
            const personaSelector = document.getElementById('persona-selector');
            const generateButton = document.getElementById('generate-button');
            const loadingSpinner = document.getElementById('loading-spinner');
            const placeholderText = document.getElementById('placeholder-text');
            const resultsContainer = document.getElementById('results-container');
            const tabContent = document.getElementById('tab-content');

            let uploadedFiles = [];
            let selectedPersona = '';

            uploader.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

            function handleFiles(files) {
                uploadedFiles = Array.from(files).slice(0, 5);
                previewGrid.innerHTML = '';
                uploadedFiles.forEach(file => {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        const img = document.createElement('img');
                        img.src = e.target.result;
                        img.className = 'w-full h-20 object-cover rounded-md';
                        previewGrid.appendChild(img);
                    };
                    reader.readAsDataURL(file);
                });
            }

            personaSelector.addEventListener('click', (e) => {
                const card = e.target.closest('.persona-card');
                if (!card) return;
                document.querySelectorAll('.persona-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedPersona = card.dataset.persona;
            });

            generateButton.addEventListener('click', async () => {
                if (uploadedFiles.length === 0) {
                    alert('Please upload at least one property photo.');
                    return;
                }
                if (!selectedPersona) {
                    alert('Please select a buyer persona.');
                    return;
                }

                placeholderText.classList.add('hidden');
                resultsContainer.classList.add('hidden');
                loadingSpinner.classList.remove('hidden');
                generateButton.disabled = true;

                try {
                    const formData = new FormData();
                    uploadedFiles.forEach(file => formData.append('files', file));
                    
                    const uploadResponse = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const uploadResult = await uploadResponse.json();
                    
                    if (uploadResult.success) {
                        const generateResponse = await fetch('/api/generate-free', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                persona: selectedPersona,
                                file_paths: uploadResult.files.map(f => f.filename)
                            })
                        });

                        const result = await generateResponse.json();
                        
                        if (result.success) {
                            loadingSpinner.classList.add('hidden');
                            resultsContainer.classList.remove('hidden');
                            tabContent.innerHTML = result.content.listing;
                        } else {
                            throw new Error(result.error || 'Generation failed');
                        }
                    } else {
                        throw new Error(uploadResult.error || 'Upload failed');
                    }
                } catch (error) {
                    console.error('Error:', error);
                    alert('Failed to generate marketing kit: ' + error.message);
                    loadingSpinner.classList.add('hidden');
                    placeholderText.classList.remove('hidden');
                } finally {
                    generateButton.disabled = false;
                }
            });
            {% endif %}
        </script>
    </body>
    </html>
    """, already_used=already_used)
def login_page():
    """Serve the login page after successful payment"""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AuraMarkt - Login</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #0a0a0a; color: #e2e8f0; }
        </style>
    </head>
    <body class="min-h-screen flex items-center justify-center">
        <div class="max-w-md w-full bg-gray-900 rounded-lg p-8 border border-gray-700">
            <div class="text-center mb-8">
                <h1 class="text-3xl font-bold text-white mb-2">Welcome to AuraMarkt!</h1>
                <p class="text-gray-400">Sign in to your account</p>
            </div>
            
            <form id="loginForm" class="space-y-6">
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Email Address</label>
                    <input type="email" id="email" required class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-md text-white focus:outline-none focus:border-violet-500">
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Password</label>
                    <input type="password" id="password" required class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-md text-white focus:outline-none focus:border-violet-500">
                </div>
                
                <button type="submit" class="w-full bg-violet-600 hover:bg-violet-700 text-white font-bold py-3 px-4 rounded-md transition-colors">
                    Sign In
                </button>
            </form>
            
            <div class="mt-6 text-center">
                <p class="text-sm text-gray-400">
                    New users: Your 3-day trial starts after sign up.
                </p>
            </div>
        </div>
        
        <script>
            document.getElementById('loginForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const email = document.getElementById('email').value.toLowerCase();
                const password = document.getElementById('password').value;
                
                // Owner account - free forever access
                if (email === 'peterbutler41@gmail.com' && password === 'Bruton20!') {
                    // Set owner privileges
                    localStorage.setItem('userEmail', email);
                    localStorage.setItem('userPlan', 'owner');
                    localStorage.setItem('isLoggedIn', 'true');
                    localStorage.setItem('isOwner', 'true');
                    localStorage.setItem('unlimitedAccess', 'true');
                    
                    // Redirect to app
                    window.location.href = '/app';
                    return;
                }
                
                // Regular user login validation
                if (email && password.length >= 6) {
                    // Check if they came from payment (have selectedPlan)
                    const selectedPlan = localStorage.getItem('selectedPlan');
                    
                    if (selectedPlan) {
                        // New paid user
                        localStorage.setItem('userEmail', email);
                        localStorage.setItem('userPlan', selectedPlan);
                        localStorage.setItem('isLoggedIn', 'true');
                        localStorage.setItem('trialStartDate', new Date().toISOString());
                        localStorage.removeItem('selectedPlan'); // Clear after use
                    } else {
                        // Existing user login
                        localStorage.setItem('userEmail', email);
                        localStorage.setItem('isLoggedIn', 'true');
                    }
                    
                    // Redirect to app
                    window.location.href = '/app';
                } else {
                    alert('Please enter valid credentials. Password must be at least 6 characters.');
                }
            });
        </script>
    </body>
    </html>
    """)

@app.route('/success')
def payment_success():
    """Handle successful payment redirect from Stripe"""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Successful - AuraMarkt</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #0a0a0a; color: #e2e8f0; }
        </style>
    </head>
    <body class="min-h-screen flex items-center justify-center">
        <div class="max-w-md w-full text-center">
            <div class="bg-gray-900 rounded-lg p-8 border border-gray-700">
                <div class="text-6xl mb-4">🎉</div>
                <h1 class="text-3xl font-bold text-white mb-4">Payment Successful!</h1>
                <p class="text-gray-400 mb-6">
                    Thank you for choosing AuraMarkt. Your 3-day trial has started!
                </p>
                <a href="/login" class="inline-block bg-violet-600 hover:bg-violet-700 text-white font-bold py-3 px-6 rounded-md transition-colors">
                    Create Your Account
                </a>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/api/generate-free', methods=['POST'])
def generate_free_marketing_kit():
    """Generate one free marketing kit per IP address"""
    try:
        ip_hash = get_ip_hash()
        
        # Check if this IP has already used the free trial
        if has_used_free_trial(ip_hash):
            return jsonify({'error': 'Free trial already used from this location'}), 403
        
        data = request.get_json()
        persona = data.get('persona')
        file_paths = data.get('file_paths', [])
        
        if not persona or not file_paths:
            return jsonify({'error': 'Missing persona or images'}), 400
        
        # Verify files exist
        valid_paths = []
        for path in file_paths:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], path)
            if os.path.exists(full_path):
                valid_paths.append(full_path)
        
        if not valid_paths:
            return jsonify({'error': 'No valid image files found'}), 400
        
        # Generate content
        try:
            content = analyze_property_with_ai(valid_paths, persona)
        except Exception as ai_error:
            print(f"AI Generation Error: {str(ai_error)}")
            content = generate_fallback_content(persona)
        
        # Mark this IP as having used the free trial
        mark_free_trial_used(ip_hash)
        
        return jsonify({
            'success': True,
            'content': content,
            'message': 'Free marketing kit generated! Upgrade for unlimited access.'
        })
        
    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Handle file uploads"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        uploaded_files = []
        
        for file in files[:10]:  # Limit to 10 files
            if file and allowed_file(file.filename):
                # Generate unique filename
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                file.save(filepath)
                uploaded_files.append({
                    'filename': unique_filename,
                    'original_name': filename,
                    'path': filepath
                })
        
        if not uploaded_files:
            return jsonify({'error': 'No valid image files uploaded'}), 400
        
        return jsonify({
            'success': True,
            'files': uploaded_files,
            'message': f'{len(uploaded_files)} files uploaded successfully'
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/generate', methods=['POST'])
def generate_marketing_kit():
    """Generate AI-powered marketing content"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        persona = data.get('persona')
        file_paths = data.get('file_paths', [])
        
        if not persona:
            return jsonify({'error': 'Buyer persona not specified'}), 400
        
        if not file_paths:
            return jsonify({'error': 'No images provided'}), 400
        
        # Verify files exist
        valid_paths = []
        for path in file_paths:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], path)
            if os.path.exists(full_path):
                valid_paths.append(full_path)
        
        if not valid_paths:
            return jsonify({'error': 'No valid image files found'}), 400
        
        # Generate content using AI
        try:
            content = analyze_property_with_ai(valid_paths, persona)
        except Exception as ai_error:
            print(f"AI Generation Error: {str(ai_error)}")
            content = generate_fallback_content(persona)
        
        # Store generation record
        generation_record = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'persona': persona,
            'file_count': len(valid_paths),
            'content': content
        }
        
        return jsonify({
            'success': True,
            'content': content,
            'generation_id': generation_record['id']
        })
        
    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

@app.route('/api/personas', methods=['GET'])
def get_personas():
    """Get available buyer personas"""
    personas = [
        {
            'id': 'First-Time Homebuyers',
            'name': 'First-Time Buyers',
            'emoji': '👨‍👩‍👧',
            'description': 'Young professionals and couples entering the housing market'
        },
        {
            'id': 'Luxury Seeker',
            'name': 'Luxury Seeker',
            'emoji': '💎',
            'description': 'High-income buyers seeking premium properties'
        },
        {
            'id': 'Growing Family',
            'name': 'Growing Family',
            'emoji': '🏡',
            'description': 'Families needing more space and family-friendly features'
        },
        {
            'id': 'Downsizing Retirees',
            'name': 'Downsizing Retirees',
            'emoji': '🌅',
            'description': 'Empty nesters seeking low-maintenance, accessible homes'
        }
    ]
    
    return jsonify({'personas': personas})

@app.route('/cancel-subscription', methods=['POST'])
def cancel_subscription():
    """Handle subscription cancellation"""
    try:
        data = request.get_json()
        user_email = data.get('user_email')
        
        # In a real implementation, you would:
        # 1. Find the customer in Stripe by email
        # 2. Get their subscription ID
        # 3. Cancel the subscription
        # 4. Update your database
        
        # For now, return success
        return jsonify({
            'success': True,
            'message': 'Subscription cancelled successfully. You will retain access until the end of your trial period.'
        })
        
    except Exception as e:
        return jsonify({'error': f'Cancellation failed: {str(e)}'}), 500

@app.route('/login')
def upload_files():
    """Handle file uploads"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        uploaded_files = []
        
        for file in files[:10]:  # Limit to 10 files
            if file and allowed_file(file.filename):
                # Generate unique filename
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                file.save(filepath)
                uploaded_files.append({
                    'filename': unique_filename,
                    'original_name': filename,
                    'path': filepath
                })
        
        if not uploaded_files:
            return jsonify({'error': 'No valid image files uploaded'}), 400
        
        return jsonify({
            'success': True,
            'files': uploaded_files,
            'message': f'{len(uploaded_files)} files uploaded successfully'
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/generate', methods=['POST'])
def generate_marketing_kit():
    """Generate AI-powered marketing content"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        persona = data.get('persona')
        file_paths = data.get('file_paths', [])
        
        if not persona:
            return jsonify({'error': 'Buyer persona not specified'}), 400
        
        if not file_paths:
            return jsonify({'error': 'No images provided'}), 400
        
        # Verify files exist
        valid_paths = []
        for path in file_paths:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], path)
            if os.path.exists(full_path):
                valid_paths.append(full_path)
        
        if not valid_paths:
            return jsonify({'error': 'No valid image files found'}), 400
        
        # Generate content using OpenAI API
        try:
            content = analyze_property_with_ai(valid_paths, persona)
        except Exception as ai_error:
            print(f"AI Generation Error: {str(ai_error)}")
            content = generate_fallback_content(persona)
        
        # Store generation record
        generation_record = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'persona': persona,
            'file_count': len(valid_paths),
            'content': content
        }
        
        return jsonify({
            'success': True,
            'content': content,
            'generation_id': generation_record['id']
        })
        
    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

@app.route('/api/personas', methods=['GET'])
def get_personas():
    """Get available buyer personas"""
    personas = [
        {
            'id': 'First-Time Homebuyers',
            'name': 'First-Time Buyers',
            'emoji': '👨‍👩‍👧',
            'description': 'Young professionals and couples entering the housing market'
        },
        {
            'id': 'Luxury Seeker',
            'name': 'Luxury Seeker',
            'emoji': '💎',
            'description': 'High-income buyers seeking premium properties'
        },
        {
            'id': 'Growing Family',
            'name': 'Growing Family',
            'emoji': '🏡',
            'description': 'Families needing more space and family-friendly features'
        },
        {
            'id': 'Downsizing Retirees',
            'name': 'Downsizing Retirees',
            'emoji': '🌅',
            'description': 'Empty nesters seeking low-maintenance, accessible homes'
        }
    ]
    
    return jsonify({'personas': personas})

@app.route('/cancel-subscription', methods=['POST'])
def cancel_subscription():
    """Handle subscription cancellation"""
    try:
        data = request.get_json()
        user_email = data.get('user_email')
        
        # In a real implementation, you would:
        # 1. Find the customer in Stripe by email
        # 2. Get their subscription ID
        # 3. Cancel the subscription
        # 4. Update your database
        
        # For now, return success
        return jsonify({
            'success': True,
            'message': 'Subscription cancelled successfully. You will retain access until the end of your trial period.'
        })
        
    except Exception as e:
        return jsonify({'error': f'Cancellation failed: {str(e)}'}), 500

@app.route('/app')
def app_interface():
    """Serve the main application interface"""
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'AuraMarkt API'
    })

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/app')
def app_interface():
    """Serve the main application interface"""
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'AuraMarkt API'
    })

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)
