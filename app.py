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

app = Flask(__name__)
CORS(app)

# --- In-memory storage for demonstration (resets on server restart) ---
# In a real application, this data would be stored in a database (e.g., Firestore).
_brand_profiles = []
_social_posts = []
_leads = []
_team_members = []
# -------------------------------------------------------------------

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-not-for-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024 # Increased max content length to 20MB for more images

# Create upload directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def encode_image_to_base64(image_path):
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Base64 encoding error: {e}")
        return None

def get_client_ip():
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        return request.environ['REMOTE_ADDR']
    else:
        return request.environ['HTTP_X_FORWARDED_FOR']

def get_ip_hash():
    ip = get_client_ip()
    return hashlib.md5(ip.encode()).hexdigest()

def has_used_free_trial(ip_hash):
    try:
        trial_file = 'free_trials_used.txt'
        if os.path.exists(trial_file):
            with open(trial_file, 'r') as f:
                used_ips = f.read().splitlines()
                return ip_hash in used_ips
        return False
    except:
        return False

def mark_free_trial_used(ip_hash):
    try:
        trial_file = 'free_trials_used.txt'
        with open(trial_file, 'a') as f:
            f.write(f"{ip_hash}\n")
    except:
        pass

def get_persona_context(persona):
    personas = {
        "First-Time Homebuyers": {
            "description": "Young professionals or couples buying their first home",
            "priorities": "affordability, move-in ready, good neighborhood",
            "tone": "encouraging, educational, emphasizing security"
        },
        "Luxury Seeker": {
            "description": "High-income individuals seeking premium properties",
            "priorities": "exclusivity, high-end finishes, prestige",
            "tone": "sophisticated, aspirational, emphasizing quality"
        },
        "Growing Family": {
            "description": "Families with children or planning children",
            "priorities": "space, safety, good schools, family features",
            "tone": "warm, family-focused, emphasizing comfort"
        },
        "Downsizing Retirees": {
            "description": "Empty nesters looking to simplify",
            "priorities": "low maintenance, accessibility, amenities",
            "tone": "respectful, focusing on lifestyle benefits"
        }
    }
    return personas.get(persona, personas["First-Time Homebuyers"])

def generate_fallback_content(persona):
    persona_context = get_persona_context(persona)
    return {
        "listing": f"<h2>Perfect Home for {persona}!</h2><p>This beautiful property offers everything that {persona_context['description']} are looking for. With thoughtful design and modern amenities, this home addresses key priorities like {persona_context['priorities']}.</p>",
        "social": f"<h3>Facebook Post:</h3><p>🏡 JUST LISTED! Perfect home for {persona.lower()}! This beautiful property checks all the boxes. #RealEstate #NewListing</p>",
        "video": f"<h3>30-Second Video Script:</h3><p>Perfect property tour for {persona.lower()}. Highlighting the best features that appeal to your lifestyle.</p>",
        "points": f"<h3>Key Selling Points:</h3><ul><li><strong>Perfect for {persona}</strong></li><li><strong>Move-in ready</strong></li><li><strong>Great location</strong></li></ul>",
        "analysis": f"Property analyzed for {persona} targeting their priorities."
    }

def analyze_property_with_ai(image_paths, persona):
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("OpenAI API key not found, using fallback")
            return generate_fallback_content(persona)
        
        # Prepare images for API
        image_messages = []
        for path in image_paths: # Send all valid paths from the upload (up to 20 from frontend)
            base64_image = encode_image_to_base64(path)
            if base64_image:
                image_messages.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "low" # Using 'low' detail to conserve tokens and speed up response
                    }
                })
        
        if not image_messages:
            print("No valid images for AI analysis")
            return generate_fallback_content(persona)
        
        persona_context = get_persona_context(persona)
        
        prompt = f"""Analyze these property images and create marketing content for {persona}.

Target buyer: {persona_context['description']}
Key priorities: {persona_context['priorities']}
Writing tone: {persona_context['tone']}

Create a compelling 250-word property description that highlights features visible in the images that would appeal to {persona}. Focus on emotional appeal and specific details you can see."""
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": "gpt-4o", # Using the latest GPT-4o model for vision
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_messages
                    ]
                }
            ],
            "max_tokens": 800 # Max tokens for the AI's text response
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60 # Increased timeout for potentially more images
        )
        
        if response.status_code == 200:
            result = response.json()
            ai_content = result['choices'][0]['message']['content']
            
            # Format AI response into structured content
            return {
                "listing": f"<h2>Perfect Home for {persona}!</h2><p>{ai_content}</p>",
                "social": f"<h3>Facebook Post:</h3><p>🏡 New listing perfect for {persona.lower()}! {ai_content[:150]}... #RealEstate #NewListing #{persona.replace(' ', '')}</p>",
                "video": f"<h3>30-Second Video Script:</h3><p>Perfect property tour for {persona.lower()}. {ai_content[:200]}...</p>",
                "points": f"<h3>Key Selling Points:</h3><ul><li><strong>Perfect for {persona}</strong></li><li><strong>Move-in Ready</strong></li><li><strong>Great Location</strong></li><li><strong>Unique Features</strong></li></ul>",
                "analysis": f"AI analysis completed for {persona} based on actual property images."
            }
        else:
            print(f"OpenAI API Error: {response.status_code}")
            print(f"OpenAI API Error details: {response.text}") 
            return generate_fallback_content(persona)
            
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return generate_fallback_content(persona)

@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/login_page')
def login_page_route():
    return render_template('loginpage.html')

@app.route('/try-free')
def try_free():
    ip_hash = get_ip_hash()
    already_used = has_used_free_trial(ip_hash)
    
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Try AuraMarkt Free</title>
    <script src="https://cdn.tailwindcss.com"></script>
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
            <h1 class="text-5xl font-black text-white">Try AuraMarkt Free</h1>
            <p class="text-slate-400 mt-2 text-lg">Get one FREE AI marketing kit</p>'''
    
    if already_used:
        html_content += '''
            <div class="mt-4 bg-red-600/20 border border-red-500/30 rounded-lg p-4 max-w-lg mx-auto">
                <p class="text-red-300 text-sm">
                    <span class="font-semibold">⚠️ Free trial already used</span><br>
                    You've already tried our free service.
                </p>
                <a href="/" class="inline-block mt-3 bg-violet-600 text-white font-bold py-2 px-4 rounded">View Plans</a>
            </div>
        </header>
    </div>
</body>
</html>'''
    else:
        html_content += '''
            <div class="mt-4 bg-green-600/20 border border-green-500/30 rounded-lg p-4 max-w-lg mx-auto">
                <p class="text-green-300 text-sm">
                    <span class="font-semibold">🎉 Free trial available!</span><br>
                    Upload photos and get one free marketing kit
                </p>
            </div>
        </header>
        
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="lg:col-span-1 flex flex-col gap-8">
                <div class="glass-pane p-6 rounded-2xl">
                    <h2 class="text-xl font-bold text-white mb-4">Upload Photos</h2>
                    <div id="image-uploader" class="border-2 border-dashed border-slate-600 rounded-lg p-6 text-center cursor-pointer">
                        <input type="file" id="file-input" multiple accept="image/*" class="hidden">
                        <p class="text-slate-400">Click to upload images</p>
                    </div>
                    <div id="preview-grid" class="mt-4 grid grid-cols-3 gap-2"></div>
                </div>
                
                <div class="glass-pane p-6 rounded-2xl">
                    <h2 class="text-xl font-bold text-white mb-4">Select Persona</h2>
                    <div id="persona-selector" class="grid grid-cols-2 gap-4">
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
                            <p class="text-3xl">🌅</p><p class="font-semibold mt-1">Retirees</p>
                        </div>
                    </div>
                </div>
                
                <button id="generate-button" class="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-4 px-6 rounded-lg">
                    Generate FREE Marketing Kit
                </button>
            </div>
            
            <div class="lg:col-span-2 glass-pane p-6 rounded-2xl">
                <h2 class="text-2xl font-bold text-white mb-4">Your FREE Marketing Kit</h2>
                <div id="output-container">
                    <div id="loading-spinner" class="hidden flex-col items-center justify-center py-20">
                        <div class="spinner"></div>
                        <p class="mt-4 text-slate-400">Creating your free marketing kit...</p>
                    </div>
                    <div id="placeholder-text" class="text-center py-20">
                        <p class="text-slate-500">Upload photos and select a persona to get started!</p>
                    </div>
                    <div id="results-container" class="hidden">
                        <div id="tab-content" class="prose prose-invert max-w-none"></div>
                        <div class="mt-8 bg-violet-600/20 border border-violet-500/30 rounded-lg p-6 text-center">
                            <h3 class="text-2xl font-bold text-white mb-2">Like what you see?</h3>
                            <p class="text-violet-200 mb-4">Get unlimited marketing kits with our paid plans</p>
                            <a href="/" class="inline-block bg-violet-600 text-white font-bold py-3 px-6 rounded-lg">View Plans</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const uploader = document.getElementById("image-uploader");
        const fileInput = document.getElementById("file-input");
        const previewGrid = document.getElementById("preview-grid");
        const personaSelector = document.getElementById("persona-selector");
        const generateButton = document.getElementById("generate-button");
        const loadingSpinner = document.getElementById("loading-spinner");
        const placeholderText = document.getElementById("placeholder-text");
        const resultsContainer = document.getElementById("results-container");
        const tabContent = document.getElementById("tab-content");

        let uploadedFiles = [];
        let selectedPersona = "";

        uploader.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", (e) => handleFiles(e.target.files));

        function handleFiles(files) {
            uploadedFiles = Array.from(files).slice(0, 5);
            previewGrid.innerHTML = "";
            uploadedFiles.forEach(file => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const img = document.createElement("img");
                    img.src = e.target.result;
                    img.className = "w-full h-20 object-cover rounded-md";
                    previewGrid.appendChild(img);
                };
                reader.readAsDataURL(file);
            });
        }

        personaSelector.addEventListener("click", (e) => {
            const card = e.target.closest(".persona-card");
            if (!card) return;
            document.querySelectorAll(".persona-card").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            selectedPersona = card.dataset.persona;
        });

        generateButton.addEventListener("click", async () => {
            if (uploadedFiles.length === 0) {
                alert("Please upload at least one photo.");
                return;
            }
            if (!selectedPersona) {
                alert("Please select a buyer persona.");
                return;
            }

            placeholderText.classList.add("hidden");
            resultsContainer.classList.add("hidden");
            loadingSpinner.classList.remove("hidden");
            generateButton.disabled = true;

            try {
                const formData = new FormData();
                uploadedFiles.forEach(file => formData.append("files", file));
                
                const uploadResponse = await fetch("/api/upload", {
                    method: "POST",
                    body: formData
                });
                
                const uploadResult = await uploadResponse.json();
                
                if (uploadResult.success) {
                    const generateResponse = await fetch("/api/generate-free", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            persona: selectedPersona,
                            file_paths: uploadResult.files.map(f => f.filename)
                        })
                    });

                    const result = await generateResponse.json();
                    
                    if (result.success) {
                        loadingSpinner.classList.add("hidden");
                        resultsContainer.classList.remove("hidden");
                        tabContent.innerHTML = result.content.listing;
                    } else {
                        throw new Error(result.error || "Generation failed");
                    }
                } else {
                    throw new Error(uploadResult.error || "Upload failed");
                }
            } catch (error) {
                alert("Failed to generate kit: " + error.message);
                loadingSpinner.classList.add("hidden");
                placeholderText.classList.remove("hidden");
            } finally {
                generateButton.disabled = false;
            }
        });
    </script>
</body>
</html>'''
    
    return html_content

@app.route('/success')
def payment_success():
    return render_template_string('''<!DOCTYPE html>
<html><head><title>Payment Success</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-black text-white min-h-screen flex items-center justify-center">
<div class="text-center"><h1 class="text-3xl font-bold mb-4">Payment Successful!</h1>
<p class="mb-6">Your 3-day trial has started!</p>
<a href="/login" class="bg-violet-600 text-white py-3 px-6 rounded-lg">Create Account</a></div>
</body></html>''')

@app.route('/login')
def login_page():
    return render_template_string('''<!DOCTYPE html>
<html><head><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-black text-white min-h-screen flex items-center justify-center">
<div class="max-w-md w-full bg-gray-900 rounded-lg p-8">
<h1 class="text-3xl font-bold text-center mb-8">Welcome to AuraMarkt!</h1>
<form id="loginForm" class="space-y-6">
<div><label class="block text-sm font-medium mb-2">Email</label>
<input type="email" id="email" required class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-md text-white"></div>
<div><label class="block text-sm font-medium mb-2">Password</label>
<input type="password" id="password" required class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-md text-white"></div>
<button type="submit" class="w-full bg-violet-600 text-white font-bold py-3 px-4 rounded-md">Sign In</button>
</form></div>
<script>
document.getElementById("loginForm").addEventListener("submit", function(e) {
    e.preventDefault();
    const email = document.getElementById("email").value.toLowerCase();
    const password = document.getElementById("password").value;
    if (email === "peterbutler41@gmail.com" && password === "Bruton20!") {
        localStorage.setItem("userEmail", email);
        localStorage.setItem("userPlan", "owner");
        localStorage.setItem("isLoggedIn", "true");
        localStorage.setItem("isOwner", "true");
        window.location.href = "/app";
        return;
    }
    if (email && password.length >= 6) {
        const selectedPlan = localStorage.getItem("selectedPlan");
        if (selectedPlan) {
            localStorage.setItem("userEmail", email);
            localStorage.setItem("userPlan", selectedPlan);
            localStorage.setItem("isLoggedIn", "true");
            localStorage.setItem("trialStartDate", new Date().toISOString());
            localStorage.removeItem("selectedPlan");
        } else {
            localStorage.setItem("userEmail", email);
            localStorage.setItem("isLoggedIn", "true");
        }
        window.location.href = "/app";
    } else {
        alert("Please enter valid credentials.");
    }
});
</script></body></html>''')

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == 
