from flask import Flask, request, jsonify, render_template_string, send_from_directory
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
import asyncio

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# OpenAI client (set API key in your environment variables)
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        
        # Call OpenAI API with new client
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
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
            "listing": f"Beautiful property perfect for {persona.lower()}. " + content[:300],
            "social": f"🏡 New listing alert! Perfect for {persona.lower()}. #RealEstate #NewListing #DreamHome",
            "video": "30-second tour showcasing the best features of this amazing property.",
            "points": f"• Perfect for {persona}\n• Move-in ready\n• Great location\n• Modern updates\n• Excellent value",
            "analysis": "Property analysis based on uploaded images."
        }
        
    except Exception as e:
        print(f"AI Analysis Error: {str(e)}")
        # Return fallback content
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
def index():
    """Serve the main application page"""
    # Read the HTML content from the uploaded file
    try:
        with open('index (3).html', 'r') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        # Fallback to a simple HTML template
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AuraMarkt - AI Property Marketing</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #0a0a0a; color: white; }
                .container { max-width: 800px; margin: 0 auto; }
                h1 { color: #a78bfa; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>AuraMarkt</h1>
                <p>AI-Powered Real Estate Marketing Platform</p>
                <p>Please upload your HTML files to use the full interface.</p>
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
        
        # Generate content using AI (or fallback)
        try:
            # Use AI analysis with the updated function
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
