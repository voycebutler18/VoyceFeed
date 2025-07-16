# FILE LOCATION: /app.py (root of your GitHub repo)
# Main Flask application for subscription-based storytelling website

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import os
import re
import stripe
from functools import wraps

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///stories.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID')  # Your subscription price ID

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to subscription
    subscription = db.relationship('Subscription', backref='user', uselist=False)
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def has_active_subscription(self):
        if not self.subscription:
            return False
        return (self.subscription.status == 'active' and 
                self.subscription.current_period_end > datetime.utcnow())

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stripe_customer_id = db.Column(db.String(100), nullable=False)
    stripe_subscription_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='inactive')
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    youtube_url = db.Column(db.String(500), nullable=False)
    youtube_video_id = db.Column(db.String(50), nullable=False)
    thumbnail_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Helper Functions
def extract_youtube_video_id(url):
    """Extract YouTube video ID from URL"""
    pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_youtube_thumbnail(video_id):
    """Get YouTube thumbnail URL"""
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    """Decorator to require active subscription"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or not user.has_active_subscription():
            return jsonify({'success': False, 'message': 'Active subscription required'}), 402
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    """Main landing page"""
    # Check if user is already logged in
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.has_active_subscription():
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('subscribe'))
    
    return render_template('index.html')

@app.route('/api/auth/register', methods=['POST'])
def register():
    """User registration endpoint"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        # Validation
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        if len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters long'}), 400
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'An account with this email already exists'}), 400
        
        # Create new user
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(email=email, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()
        
        # Log user in
        session['user_id'] = user.id
        session['user_email'] = user.email
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'hasSubscription': False
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Registration failed. Please try again.'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        # Validation
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            # Log user in
            session['user_id'] = user.id
            session['user_email'] = user.email
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'hasSubscription': user.has_active_subscription(),
                'isAdmin': user.is_admin
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Login failed. Please try again.'}), 500

@app.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    """User logout endpoint"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/dashboard')
@subscription_required
def dashboard():
    """Main dashboard with video feed"""
    return render_template('dashboard.html')

@app.route('/api/videos')
@subscription_required
def get_videos():
    """Get all active videos for feed"""
    videos = Video.query.filter_by(is_active=True).order_by(Video.created_at.desc()).all()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video.id,
            'title': video.title,
            'description': video.description,
            'youtube_url': video.youtube_url,
            'youtube_video_id': video.youtube_video_id,
            'thumbnail_url': video.thumbnail_url,
            'created_at': video.created_at.isoformat()
        })
    
    return jsonify({'success': True, 'videos': video_list})

@app.route('/subscribe')
@login_required
def subscribe():
    """Subscription page"""
    user = User.query.get(session['user_id'])
    if user.has_active_subscription():
        return redirect(url_for('dashboard'))
    
    return render_template('subscribe.html', stripe_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/api/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Create Stripe checkout session"""
    try:
        user = User.query.get(session['user_id'])
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('dashboard', _external=True),
            cancel_url=url_for('subscribe', _external=True),
            customer_email=user.email,
            metadata={
                'user_id': user.id
            }
        )
        
        return jsonify({'checkout_url': checkout_session.url})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError:
        return '', 400
    except stripe.error.SignatureVerificationError:
        return '', 400
    
    # Handle different event types
    if event['type'] == 'checkout.session.completed':
        session_data = event['data']['object']
        user_id = session_data['metadata']['user_id']
        
        # Get subscription details
        subscription = stripe.Subscription.retrieve(session_data['subscription'])
        
        # Update user subscription
        user = User.query.get(user_id)
        if user:
            existing_subscription = Subscription.query.filter_by(user_id=user_id).first()
            if existing_subscription:
                existing_subscription.stripe_customer_id = session_data['customer']
                existing_subscription.stripe_subscription_id = session_data['subscription']
                existing_subscription.status = subscription['status']
                existing_subscription.current_period_start = datetime.fromtimestamp(subscription['current_period_start'])
                existing_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
            else:
                new_subscription = Subscription(
                    user_id=user_id,
                    stripe_customer_id=session_data['customer'],
                    stripe_subscription_id=session_data['subscription'],
                    status=subscription['status'],
                    current_period_start=datetime.fromtimestamp(subscription['current_period_start']),
                    current_period_end=datetime.fromtimestamp(subscription['current_period_end'])
                )
                db.session.add(new_subscription)
            
            db.session.commit()
    
    elif event['type'] == 'invoice.payment_succeeded':
        # Handle successful payment
        subscription_id = event['data']['object']['subscription']
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if db_subscription:
            db_subscription.status = 'active'
            db_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
            db.session.commit()
    
    elif event['type'] == 'invoice.payment_failed':
        # Handle failed payment
        subscription_id = event['data']['object']['subscription']
        
        db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if db_subscription:
            db_subscription.status = 'past_due'
            db.session.commit()
    
    return '', 200

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    return render_template('admin.html')

@app.route('/api/admin/videos', methods=['POST'])
@admin_required
def add_video():
    """Add new video (admin only)"""
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        youtube_url = data.get('youtube_url', '').strip()
        
        if not title or not youtube_url:
            return jsonify({'success': False, 'message': 'Title and YouTube URL are required'}), 400
        
        # Extract video ID
        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return jsonify({'success': False, 'message': 'Invalid YouTube URL'}), 400
        
        # Generate thumbnail URL
        thumbnail_url = get_youtube_thumbnail(video_id)
        
        # Create video record
        video = Video(
            title=title,
            description=description,
            youtube_url=youtube_url,
            youtube_video_id=video_id,
            thumbnail_url=thumbnail_url
        )
        
        db.session.add(video)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Video added successfully',
            'video': {
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_video_id': video.youtube_video_id,
                'thumbnail_url': video.thumbnail_url
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to add video'}), 500

# Create tables and admin user
@app.before_first_request
def create_tables():
    """Create database tables and default admin user"""
    db.create_all()
    
    # Create admin user if it doesn't exist
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@yourdomain.com')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    if not User.query.filter_by(email=admin_email).first():
        admin_user = User(
            email=admin_email,
            password_hash=bcrypt.generate_password_hash(admin_password).decode('utf-8'),
            is_admin=True
        )
        db.session.add(admin_user)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
