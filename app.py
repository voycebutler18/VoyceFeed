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

# Stripe configuration with better error handling
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', 'price_1RlTWbJhjilOfxPRUg9SzyST')

# Debug: Check Stripe configuration at startup
print(f"Stripe API Key set: {bool(stripe.api_key)}")
print(f"Stripe Publishable Key set: {bool(STRIPE_PUBLISHABLE_KEY)}")
print(f"Stripe Price ID: {STRIPE_PRICE_ID}")

if not stripe.api_key:
    print("WARNING: STRIPE_SECRET_KEY environment variable not set!")
if not STRIPE_PUBLISHABLE_KEY:
    print("WARNING: STRIPE_PUBLISHABLE_KEY environment variable not set!")

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
    
    # Relationship to comments
    comments = db.relationship('Comment', backref='user', lazy=True)
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def has_active_subscription(self):
        if not self.subscription:
            return False
        return (self.subscription.status == 'active' and 
                self.subscription.current_period_end > datetime.utcnow())
    
    def get_display_name(self):
        """Get display name for user (email prefix)"""
        return self.email.split('@')[0] if self.email else 'User'

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
    
    # Relationship to comments
    comments = db.relationship('Comment', backref='video', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)  # For replies
    content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Self-referential relationship for replies
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True)
    
    # Relationship to likes
    comment_likes = db.relationship('CommentLike', backref='comment', lazy=True, cascade='all, delete-orphan')
    
    def get_time_ago(self):
        """Get human-readable time ago"""
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    
    def is_liked_by_user(self, user_id):
        """Check if comment is liked by specific user"""
        return CommentLike.query.filter_by(comment_id=self.id, user_id=user_id).first() is not None
    
    def to_dict(self, user_id=None):
        """Convert comment to dictionary for JSON response"""
        return {
            'id': self.id,
            'author': self.user.get_display_name(),
            'content': self.content,
            'likes': self.likes,
            'liked': self.is_liked_by_user(user_id) if user_id else False,
            'time': self.get_time_ago(),
            'created_at': self.created_at.isoformat(),
            'replies': [reply.to_dict(user_id) for reply in self.replies] if self.replies else []
        }

class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate likes
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='unique_user_comment_like'),)

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

# Comment Routes
@app.route('/api/videos/<int:video_id>/comments', methods=['GET'])
@subscription_required
def get_comments(video_id):
    """Get comments for a specific video"""
    try:
        # Verify video exists
        video = Video.query.get_or_404(video_id)
        
        # Get top-level comments (not replies)
        comments = Comment.query.filter_by(video_id=video_id, parent_id=None).order_by(Comment.created_at.desc()).all()
        
        user_id = session.get('user_id')
        comment_list = [comment.to_dict(user_id) for comment in comments]
        
        return jsonify({
            'success': True,
            'comments': comment_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': 'Failed to load comments'}), 500

@app.route('/api/videos/<int:video_id>/comments', methods=['POST'])
@subscription_required
def add_comment(video_id):
    """Add a comment to a video"""
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        parent_id = data.get('parent_id')  # For replies
        
        if not content:
            return jsonify({'success': False, 'message': 'Comment content is required'}), 400
        
        # Verify video exists
        video = Video.query.get_or_404(video_id)
        
        # If it's a reply, verify parent comment exists
        if parent_id:
            parent_comment = Comment.query.get_or_404(parent_id)
            if parent_comment.video_id != video_id:
                return jsonify({'success': False, 'message': 'Invalid parent comment'}), 400
        
        # Create comment
        comment = Comment(
            user_id=session['user_id'],
            video_id=video_id,
            parent_id=parent_id,
            content=content
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment added successfully',
            'comment': comment.to_dict(session['user_id'])
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to add comment'}), 500

@app.route('/api/comments/<int:comment_id>/like', methods=['POST'])
@subscription_required
def toggle_comment_like(comment_id):
    """Toggle like on a comment"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        user_id = session['user_id']
        
        # Check if user already liked this comment
        existing_like = CommentLike.query.filter_by(comment_id=comment_id, user_id=user_id).first()
        
        if existing_like:
            # Unlike
            db.session.delete(existing_like)
            comment.likes = max(0, comment.likes - 1)
            liked = False
        else:
            # Like
            new_like = CommentLike(comment_id=comment_id, user_id=user_id)
            db.session.add(new_like)
            comment.likes += 1
            liked = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'liked': liked,
            'likes': comment.likes
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to toggle like'}), 500

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
@subscription_required
def delete_comment(comment_id):
    """Delete a comment (only by comment author or admin)"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        user = User.query.get(session['user_id'])
        
        # Check if user can delete this comment
        if comment.user_id != user.id and not user.is_admin:
            return jsonify({'success': False, 'message': 'Not authorized to delete this comment'}), 403
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Comment deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to delete comment'}), 500

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
            ).count(),
            'total_comments': Comment.query.count(),
            'comments_this_month': Comment.query.filter(Comment.created_at >= month_start).count()
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
            comment_count = Comment.query.filter_by(video_id=video.id).count()
            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_url': video.youtube_url,
                'youtube_video_id': video.youtube_video_id,
                'thumbnail_url': video.thumbnail_url,
                'is_active': video.is_active,
                'created_at': video.created_at.isoformat(),
                'comment_count': comment_count
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
            'message': 'Video added successfully
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to add video'}), 500

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
        
        # If YouTube URL is updated, re-extract video ID and thumbnail
        if 'youtube_url' in data:
            new_url = data['youtube_url'].strip()
            new_video_id = extract_youtube_video_id(new_url)
            if not new_video_id:
                return jsonify({'success': False, 'message': 'Invalid YouTube URL'}), 400
            
            # Check if another video already uses this ID
            existing_video = Video.query.filter_by(youtube_video_id=new_video_id).filter(Video.id != video_id).first()
            if existing_video:
                return jsonify({'success': False, 'message': 'This video is already in the system'}), 400
            
            video.youtube_url = new_url
            video.youtube_video_id = new_video_id
            video.thumbnail_url = get_youtube_thumbnail(new_video_id)
        
        video.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Video updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to update video'}), 500

@app.route('/api/admin/videos/<int:video_id>', methods=['DELETE'])
@admin_required
def admin_delete_video(video_id):
    """Delete video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        
        # Delete video and all associated comments (cascade should handle this)
        db.session.delete(video)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Video deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to delete video'}), 500

@app.route('/api/admin/users')
@admin_required
def admin_get_users():
    """Get all users for admin"""
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        
        user_list = []
        for user in users:
            comment_count = Comment.query.filter_by(user_id=user.id).count()
            user_list.append({
                'id': user.id,
                'email': user.email,
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat(),
                'has_subscription': user.has_active_subscription(),
                'subscription_status': user.subscription.status if user.subscription else None,
                'subscription_end': user.subscription.current_period_end.isoformat() if user.subscription and user.subscription.current_period_end else None,
                'comment_count': comment_count
            })
        
        return jsonify({'success': True, 'users': user_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_user_admin(user_id):
    """Toggle user admin status"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Don't allow removing admin from self
        if user.id == session['user_id']:
            return jsonify({'success': False, 'message': 'Cannot modify your own admin status'}), 400
        
        user.is_admin = not user.is_admin
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {"granted" if user.is_admin else "revoked"} admin privileges',
            'is_admin': user.is_admin
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to update user'}), 500

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    """Delete user (admin only)"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Don't allow deleting self
        if user.id == session['user_id']:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
        
        # Cancel Stripe subscription if exists
        if user.subscription and user.subscription.stripe_subscription_id:
            try:
                stripe.Subscription.modify(
                    user.subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
            except stripe.error.StripeError:
                pass  # Continue with deletion even if Stripe fails
        
        # Delete user and all associated data (cascade should handle this)
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'User deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to delete user'}), 500

@app.route('/api/admin/comments')
@admin_required
def admin_get_comments():
    """Get all comments for admin moderation"""
    try:
        comments = Comment.query.join(User).join(Video).order_by(Comment.created_at.desc()).limit(100).all()
        
        comment_list = []
        for comment in comments:
            comment_list.append({
                'id': comment.id,
                'content': comment.content,
                'author': comment.user.email,
                'video_title': comment.video.title,
                'video_id': comment.video.id,
                'likes': comment.likes,
                'created_at': comment.created_at.isoformat(),
                'is_reply': comment.parent_id is not None,
                'reply_count': len(comment.replies)
            })
        
        return jsonify({'success': True, 'comments': comment_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Not found'}), 404
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    return redirect(url_for('index'))

# Database initialization
def init_db():
    """Initialize database with tables"""
    with app.app_context():
        db.create_all()
        print("Database tables created successfully")
        
        # Create admin user if it doesn't exist
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        
        admin_user = User.query.filter_by(email=admin_email).first()
        if not admin_user:
            password_hash = bcrypt.generate_password_hash(admin_password).decode('utf-8')
            admin_user = User(
                email=admin_email,
                password_hash=password_hash,
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print(f"Admin user created: {admin_email}")
        else:
            print(f"Admin user already exists: {admin_email}")

# Context processor for templates
@app.context_processor
def inject_template_vars():
    """Inject variables into all templates"""
    return {
        'stripe_publishable_key': STRIPE_PUBLISHABLE_KEY
    }

# Development server
if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Run development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print(f"Starting Flask app on port {port}")
    print(f"Debug mode: {debug}")
    print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
