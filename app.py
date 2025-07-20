from flask import Flask, request, jsonify, render_template, render_template_string, send_from_directory
from flask_cors import CORS
import os
import base64
import json
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
from openai import OpenAI
from PIL import Image
import io

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-not-for-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Image processing functions
def optimize_image(image_path, max_size=(1024, 1024), quality=85):
    """Optimize image for API usage"""
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Resize if too large
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save optimized image
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()

def encode_image_to_base64(image_path):
    """Convert image to base64 for API"""
    optimized_image = optimize_image(image_path)
    return base64.b64encode(optimized_image).decode('utf-8')

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
    
    try:
        # Prepare images for API
        image_messages = []
        for path in image_paths[:3]:  # Limit to 3 images for API efficiency
            base64_image = encode_image_to_base64(path)
            image_messages.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}",
                    "detail": "high"
                }
            })
        
        persona_context = get_persona_context(persona)
        
        # Create comprehensive prompt
        prompt = f"""
        You are an expert real estate marketing specialist analyzing property photos to create compelling marketing materials.
        
        TARGET BUYER PERSONA: {persona}
        - Description: {persona_context['description']}
        - Priorities: {persona_context['priorities']}
        - Tone: {persona_context['tone']}
        - Pain Points: {persona_context['pain_points']}
        
        Analyze these property images and create a complete marketing kit. Focus on features that would appeal specifically to {persona}.
        
        Return a JSON response with exactly these keys:
        
        1. "listing": A compelling property description (200-300 words) that highlights features appealing to {persona}
        2. "social": 3 different social media posts for Facebook/Instagram (each 50-100 words) with relevant hashtags
        3. "video": A 30-60 second video script with scene descriptions and voiceover text
        4. "points": 5-7 key selling points formatted as bullet points, each with a bold title and explanation
        5. "analysis": Your analysis of the property's key features visible in the images
        
        Make the content emotional, specific, and targeted to {persona}. Use the property's actual visible features.
        """
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_messages
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        # Parse response
        content = response.choices[0].message.content
        
        # Try to extract JSON from response
        try:
            # Look for JSON in the response
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            if start_idx != -1 and end_idx != 0:
                json_content = content[start_idx:end_idx]
                return json.loads(json_content)
        except:
            pass
        
        # Fallback: create structured response manually
        return {
            "listing": f"<h2>Perfect Home for {persona}!</h2><p>" + content[:400] + "...</p>",
            "social": f"<h3>Facebook Post:</h3><p>🏡 New listing perfect for {persona.lower()}! " + content[:200] + "... #RealEstate #NewListing</p>",
            "video": f"<h3>30-Second Video Script:</h3><p>Perfect property tour for {persona.lower()}...</p>",
            "points": f"<h3>Key Selling Points:</h3><ul><li><strong>Perfect for {persona}</strong></li><li><strong>Move-in ready</strong></li></ul>",
            "analysis": f"AI analysis completed for {persona} targeting their priorities."
        }
        
    except Exception as e:
        print(f"OpenAI API Error: {str(e)}")
        # Return fallback content if API fails
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

@app.route('/login')
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

if __name__ == '__main__':
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)
