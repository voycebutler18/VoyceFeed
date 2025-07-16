# FILE LOCATION: /app.py (root of your GitHub repo)
# Complete Flask application for subscription-based storytelling website

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import os
import re
import stripe
from functools import wraps
from sqlalchemy import func

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# Use SQLite for now (works with Python 3.13)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stories.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

print("Using SQLite database for compatibility with Python 3.13")

# Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', 'price_1RlTWbJhjilOfxPRUg9SzyST')  # Your price ID

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
    patterns = [
        r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})',
        r'youtube\.com\/watch\?v=([^"&?\/\s]{11})',
        r'youtu\.be\/([^"&?\/\s]{11})',
        r'youtube\.com\/embed\/([^"&?\/\s]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_thumbnail(video_id):
    """Get YouTube thumbnail URL"""
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    """Decorator to require active subscription"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            return redirect(url_for('index'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.has_active_subscription():
            if request.is_json:
                return jsonify({'success': False, 'message': 'Active subscription required'}), 402
            return redirect(url_for('subscribe'))
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            return redirect(url_for('index'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Admin access required'}), 403
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    """Main landing page"""
    # Check if user is already logged in
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            elif user.has_active_subscription():
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('subscribe'))
    
    return render_template('index.html')

# Authentication Routes
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
            'hasSubscription': False,
            'isAdmin': False
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

@app.route('/api/auth/check')
@login_required
def auth_check():
    """Check if user is authenticated"""
    user = User.query.get(session['user_id'])
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'is_admin': user.is_admin,
            'has_subscription': user.has_active_subscription()
        }
    })

# Dashboard Routes
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

# Subscription Routes
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
        if not stripe.api_key:
            return jsonify({'success': False, 'message': 'Stripe not configured'}), 500
        
        if not STRIPE_PRICE_ID:
            return jsonify({'success': False, 'message': 'Stripe price ID not configured'}), 500
        
        user = User.query.get(session['user_id'])
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('dashboard', _external=True) + '?success=true',
            cancel_url=url_for('subscribe', _external=True) + '?canceled=true',
            customer_email=user.email,
            metadata={
                'user_id': str(user.id)
            }
        )
        
        return jsonify({'success': True, 'checkout_url': checkout_session.url})
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {e}")
        return jsonify({'success': False, 'message': f'Stripe error: {str(e)}'}), 500
    except Exception as e:
        print(f"Checkout error: {e}")
        return jsonify({'success': False, 'message': 'Failed to create checkout session'}), 500

@app.route('/api/user/subscription-status')
@login_required
def subscription_status():
    """Check user's subscription status"""
    user = User.query.get(session['user_id'])
    return jsonify({
        'success': True,
        'hasActiveSubscription': user.has_active_subscription(),
        'subscription': {
            'status': user.subscription.status if user.subscription else None,
            'current_period_end': user.subscription.current_period_end.isoformat() if user.subscription and user.subscription.current_period_end else None
        } if user.subscription else None
    })

# Stripe Webhook
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
        user_id = int(session_data['metadata']['user_id'])
        
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
                existing_subscription.updated_at = datetime.utcnow()
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
            db_subscription.current_period_start = datetime.fromtimestamp(subscription['current_period_start'])
            db_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
            db_subscription.updated_at = datetime.utcnow()
            db.session.commit()
    
    elif event['type'] == 'invoice.payment_failed':
        # Handle failed payment
        subscription_id = event['data']['object']['subscription']
        
        db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if db_subscription:
            db_subscription.status = 'past_due'
            db_subscription.updated_at = datetime.utcnow()
            db.session.commit()
    
    elif event['type'] == 'customer.subscription.updated':
        # Handle subscription updates
        subscription_data = event['data']['object']
        
        db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_data['id']).first()
        if db_subscription:
            db_subscription.status = subscription_data['status']
            db_subscription.current_period_start = datetime.fromtimestamp(subscription_data['current_period_start'])
            db_subscription.current_period_end = datetime.fromtimestamp(subscription_data['current_period_end'])
            db_subscription.updated_at = datetime.utcnow()
            db.session.commit()
    
    elif event['type'] == 'customer.subscription.deleted':
        # Handle subscription cancellation
        subscription_data = event['data']['object']
        
        db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_data['id']).first()
        if db_subscription:
            db_subscription.status = 'canceled'
            db_subscription.updated_at = datetime.utcnow()
            db.session.commit()
    
    return '', 200

# Admin Routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    return render_template('admin.html')

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    """Get admin dashboard statistics"""
    try:
        # Get current month start
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        
        stats = {
            'total_videos': Video.query.filter_by(is_active=True).count(),
            'total_users': User.query.count(),
            'active_subscribers': Subscription.query.filter_by(status='active').filter(
                Subscription.current_period_end > datetime.utcnow()
            ).count(),
            'videos_this_month': Video.query.filter(
                Video.created_at >= month_start,
                Video.is_active == True
            ).count()
        }
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/videos', methods=['GET'])
@admin_required
def admin_get_videos():
    """Get all videos for admin"""
    try:
        videos = Video.query.order_by(Video.created_at.desc()).all()
        
        video_list = []
        for video in videos:
            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_url': video.youtube_url,
                'youtube_video_id': video.youtube_video_id,
                'thumbnail_url': video.thumbnail_url,
                'is_active': video.is_active,
                'created_at': video.created_at.isoformat()
            })
        
        return jsonify({'success': True, 'videos': video_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/videos', methods=['POST'])
@admin_required
def admin_add_video():
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
        
        # Check if video already exists
        existing_video = Video.query.filter_by(youtube_video_id=video_id).first()
        if existing_video:
            return jsonify({'success': False, 'message': 'This video has already been added'}), 400
        
        # Generate thumbnail URL
        thumbnail_url = get_youtube_thumbnail(video_id)
        
        # Create video record
        video = Video(
            title=title,
            description=description if description else None,
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
                'thumbnail_url': video.thumbnail_url,
                'created_at': video.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to add video'}), 500

@app.route('/api/admin/videos/<int:video_id>', methods=['DELETE'])
@admin_required
def admin_delete_video(video_id):
    """Delete video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        
        db.session.delete(video)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Video deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to delete video'}), 500

@app.route('/api/admin/videos/<int:video_id>', methods=['PUT'])
@admin_required
def admin_update_video(video_id):
    """Update video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        data = request.get_json()
        
        # Update fields
        if 'title' in data:
            video.title = data['title'].strip()
        if 'description' in data:
            video.description = data['description'].strip() if data['description'] else None
        if 'is_active' in data:
            video.is_active = bool(data['is_active'])
        
        video.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Video updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to update video'}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    if request.is_json:
        return jsonify({'success': False, 'message': 'Not found'}), 404
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.is_json:
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    return redirect(url_for('index'))

# Initialize database
def create_tables():
    """Create database tables and default admin user"""
    try:
        with app.app_context():
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
                print(f"Created admin user: {admin_email}")
    except Exception as e:
        print(f"Database setup error: {e}")

# Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    create_tables()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
else:
    # This runs when deployed (not in debug mode)
    create_tables()
