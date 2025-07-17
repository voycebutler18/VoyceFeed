# FILE LOCATION: /app.py (root of your GitHub repo)
# Complete Flask application for subscription-based storytelling website

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta, date # Import date for last_watch_date
import os # Import os module for path manipulation
import re
# import stripe # REMOVED: Stripe is no longer used
from functools import wraps
from sqlalchemy import func
import logging # Import the logging module
from flask_wtf.csrf import CSRFProtect # Import CSRFProtect
from flask_limiter import Limiter # Import Limiter
from flask_limiter.util import get_remote_address # Import get_remote_address

# Initialize Flask app
app = Flask(__name__)

# --- NEW: Define the path for the persistent data directory ---
# This directory will be created within your project structure.
# Render's persistent disk will then mount to this specific directory.
DATA_DIR = os.path.join(os.getcwd(), 'data') # Use 'data' as the subdirectory name

# Ensure the data directory exists. This is crucial for local development and Render.
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    print(f"Created persistent data directory: {DATA_DIR}")

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# --- MODIFIED: Update SQLALCHEMY_DATABASE_URI to point to the new data directory ---
# The database file will now be located at ./data/stories.db
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(DATA_DIR, "stories.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

print(f"Using SQLite database at: {app.config['SQLALCHEMY_DATABASE_URI']}") # Updated print statement

# Stripe configuration with better error handling - REMOVED
# stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
# STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
# STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', 'price_1RlTWbJhjilOfxPRUg9SzyST')

# Debug: Check Stripe configuration at startup - REMOVED
# print(f"Stripe API Key set: {bool(stripe.api_key)}")
# print(f"Stripe Publishable Key set: {bool(STRIPE_PUBLISHABLE_KEY)}")
# print(f"Stripe Price ID: {STRIPE_PRICE_ID}")

# if not stripe.api_key:
#     print("WARNING: STRIPE_SECRET_KEY environment variable not set!")
# if not STRIPE_PUBLISHABLE_KEY:
#     print("WARNING: STRIPE_PUBLISHABLE_KEY environment variable not set!")

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app) # Initialize CSRFProtect
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
) # Initialize Limiter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Database Models
class User(db.Model):
    __tablename__ = 'user'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_watch_date = db.Column(db.Date, nullable=True)
    watch_streak = db.Column(db.Integer, default=0)
    
    # subscription = db.relationship('Subscription', backref='user', uselist=False) # REMOVED: No more subscriptions
    comments = db.relationship('Comment', backref='user', lazy=True, cascade='all, delete-orphan')
    comment_likes = db.relationship('CommentLike', backref='user', lazy=True, cascade='all, delete-orphan')
    video_likes = db.relationship('VideoLike', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    # def has_active_subscription(self): # REMOVED: No more subscriptions
    #     if not self.subscription:
    #         return False
    #     return (self.subscription.status == 'active' and 
    #             self.subscription.current_period_end > datetime.utcnow())
    
    def get_display_name(self):
        return self.email.split('@')[0]

# class Subscription(db.Model): # REMOVED: No more subscriptions
#     __tablename__ = 'subscription'
#     __table_args__ = {'extend_existing': True}
    
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     stripe_customer_id = db.Column(db.String(100), nullable=False)
#     stripe_subscription_id = db.Column(db.String(100), nullable=False)
#     status = db.Column(db.String(20), default='inactive')
#     current_period_start = db.Column(db.DateTime)
#     current_period_end = db.Column(db.DateTime)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Video(db.Model):
    __tablename__ = 'video'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    youtube_url = db.Column(db.String(500), nullable=False)
    youtube_video_id = db.Column(db.String(50), nullable=False)
    thumbnail_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    likes_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    genre = db.Column(db.String(100), nullable=True)
    featured_tag = db.Column(db.String(50), nullable=True)

    comments = db.relationship('Comment', backref='video', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('VideoLike', backref='video', lazy=True, cascade='all, delete-orphan')

class VideoLike(db.Model):
    __tablename__ = 'video_like'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'video_id'),
        {'extend_existing': True}
    )

class Comment(db.Model):
    __tablename__ = 'comment'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    text = db.Column(db.Text, nullable=False)
    likes_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    replies = db.relationship('Comment', 
                             backref=db.backref('parent', remote_side=[id]),
                             lazy=True,
                             cascade='all, delete-orphan')
    
    likes = db.relationship('CommentLike', backref='comment', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self, current_user_id=None):
        liked_by_user = False
        if current_user_id:
            liked_by_user = any(like.user_id == current_user_id for like in self.likes)
        
        return {
            'id': self.id,
            'author': self.user.get_display_name(),
            'text': self.text,
            'time': self.get_time_ago(),
            'likes': self.likes_count,
            'liked': liked_by_user,
            'replies': [reply.to_dict(current_user_id) for reply in self.replies],
            'created_at': self.created_at.isoformat()
        }
    
    def get_time_ago(self):
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

class CommentLike(db.Model):
    __tablename__ = 'comment_like'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'comment_id'),
        {'extend_existing': True}
    )

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    feedback_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='feedbacks')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'feedback_text': self.feedback_text,
            'created_at': self.created_at.isoformat(),
            'user_email': self.user.email
        }


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
            flash('Please log in to access this page', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# def subscription_required(f): # REMOVED: No more subscriptions
#     """Decorator to require active subscription"""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'user_id' not in session:
#             if request.is_json:
#                 return jsonify({'success': False, 'message': 'Authentication required'}), 401
#             return redirect(url_for('index'))
        
#         user = User.query.get(session['user_id'])
#         if not user or not user.has_active_subscription():
#             if request.is_json:
#                 return jsonify({'success': False, 'message': 'Active subscription required'}), 402
#             return redirect(url_for('subscribe'))
        
#         return f(*args, **kwargs)
#     return decorated_function

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
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            else: # MODIFIED: No more subscription check, all logged-in users go to dashboard
                return redirect(url_for('dashboard'))
    
    return render_template('index.html')

# Authentication Routes
@app.route('/api/auth/register', methods=['POST'])
def register():
    """User registration endpoint"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        if len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters long'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'An account with this email already exists'}), 400
        
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(email=email, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()
        
        session['user_id'] = user.id
        session['user_email'] = user.email
        
        # MODIFIED: Redirect directly to dashboard after registration, no hasSubscription flag
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'isAdmin': False,
            'redirect': '/dashboard' # Indicate redirect to frontend
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during registration: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Registration failed. Please try again.'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_email'] = user.email
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'isAdmin': user.is_admin
            }) # MODIFIED: Removed hasSubscription
        else:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
            
    except Exception as e:
        logger.error(f"Error during login: {e}", exc_info=True)
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
            'has_subscription': True # MODIFIED: Always true since content is free
        }
    })

# Video Like System Routes
@app.route('/api/videos/<int:video_id>/like', methods=['POST'])
@login_required # MODIFIED: Changed from subscription_required
def toggle_video_like(video_id):
    """Toggle like on a video"""
    try:
        video = Video.query.get_or_404(video_id)
        user_id = session['user_id']
        
        existing_like = VideoLike.query.filter_by(
            user_id=user_id,
            video_id=video_id
        ).first()
        
        if existing_like:
            db.session.delete(existing_like)
            video.likes_count = max(0, video.likes_count - 1)
            liked = False
        else:
            new_like = VideoLike(user_id=user_id, video_id=video_id)
            db.session.add(new_like)
            video.likes_count += 1
            liked = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'liked': liked,
            'likes_count': video.likes_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling video like: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update like'}), 500

@app.route('/dashboard')
@login_required # MODIFIED: Only login_required, not subscription_required
def dashboard():
    """User dashboard"""
    # The login_required decorator already handles redirection if not logged in.
    # No further redirects here to allow non-subscribers to view the dashboard.
    return render_template('dashboard.html')

@app.route('/api/videos')
@login_required # MODIFIED: Only login_required, not subscription_required
def get_videos():
    """
    Get all active videos for feed.
    'can_watch' flag is always true now.
    """
    videos = Video.query.filter_by(is_active=True).order_by(Video.created_at.desc()).all()
    current_user = User.query.get(session['user_id']) # Get current user object

    video_list = []
    for video in videos:
        user_liked = VideoLike.query.filter_by(
            user_id=current_user.id,
            video_id=video.id
        ).first() is not None
        
        video_list.append({
            'id': video.id,
            'title': video.title,
            'description': video.description,
            'youtube_url': video.youtube_url,
            'youtube_video_id': video.youtube_video_id,
            'thumbnail_url': video.thumbnail_url,
            'likes_count': video.likes_count,
            'user_liked': user_liked,
            'created_at': video.created_at.isoformat(),
            'genre': video.genre,
            'featured_tag': video.featured_tag,
            'can_watch': True # MODIFIED: Always true as content is free
        })
    
    return jsonify({'success': True, 'videos': video_list})

# Comment System Routes
@app.route('/api/videos/<int:video_id>/comments', methods=['GET'])
@login_required # MODIFIED: Changed from subscription_required
def get_comments(video_id):
    """Get comments for a specific video"""
    try:
        video = Video.query.get_or_404(video_id)
        
        comments = Comment.query.filter_by(
            video_id=video_id, 
            parent_id=None
        ).order_by(Comment.created_at.desc()).all()
        
        current_user_id = session['user_id']
        
        comment_list = []
        for comment in comments:
            comment_list.append(comment.to_dict(current_user_id))
        
        return jsonify({
            'success': True,
            'comments': comment_list,
            'total_count': len(comments)
        })
        
    except Exception as e:
        logger.error(f"Error getting comments: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to load comments'}), 500

@app.route('/api/videos/<int:video_id>/comments', methods=['POST'])
@login_required # MODIFIED: Changed from subscription_required
def post_comment(video_id):
    """Post a new comment on a video"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        parent_id = data.get('parent_id')
        
        if not text:
            return jsonify({'success': False, 'message': 'Comment text is required'}), 400
        
        video = Video.query.get_or_404(video_id)
        
        if parent_id:
            parent_comment = Comment.query.get(parent_id)
            if not parent_comment or parent_comment.video_id != video_id:
                return jsonify({'success': False, 'message': 'Invalid parent comment'}), 400
        
        comment = Comment(
            video_id=video_id,
            user_id=session['user_id'],
            parent_id=parent_id,
            text=text
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment posted successfully',
            'comment': comment.to_dict(session['user_id'])
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error posting comment: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to post comment'}), 500

@app.route('/api/comments/<int:comment_id>/like', methods=['POST'])
@login_required # MODIFIED: Changed from subscription_required
def toggle_comment_like(comment_id):
    """Toggle like on a comment"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        user_id = session['user_id']
        
        existing_like = CommentLike.query.filter_by(
            user_id=user_id,
            comment_id=comment_id
        ).first()
        
        if existing_like:
            db.session.delete(existing_like)
            comment.likes_count = max(0, comment.likes_count - 1)
            liked = False
        else:
            new_like = CommentLike(user_id=user_id, comment_id=comment_id)
            db.session.add(new_like)
            comment.likes_count += 1
            liked = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'liked': liked,
            'likes_count': comment.likes_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling comment like: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update like'}), 500

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
@login_required # MODIFIED: Changed from subscription_required
def delete_comment(comment_id):
    """Delete a comment (only by the author or admin)"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        user = User.query.get(session['user_id'])
        
        if comment.user_id != user.id and not user.is_admin:
            return jsonify({'success': False, 'message': 'Not authorized to delete this comment'}), 403
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Comment deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting comment: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to delete comment'}), 500

@app.route('/api/comments/<int:comment_id>', methods=['PUT'])
@login_required # MODIFIED: Changed from subscription_required
def edit_comment(comment_id):
    """Edit a comment (only by the author)"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        user_id = session['user_id']
        
        if comment.user_id != user_id:
            return jsonify({'success': False, 'message': 'Not authorized to edit this comment'}), 403
        
        data = request.get_json()
        new_text = data.get('text', '').strip()
        
        if not new_text:
            return jsonify({'success': False, 'message': 'Comment text is required'}), 400
        
        comment.text = new_text
        comment.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment updated successfully',
            'comment': comment.to_dict(user_id)
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing comment: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update comment'}), 500

# @app.route('/payment-success') # REMOVED: No more payments
# @login_required
# def payment_success():
#     """Handle successful payment - wait for webhook to process"""
#     return render_template('payment_success.html')

# @app.route('/subscribe') # REMOVED: No more subscriptions
# @login_required
# def subscribe():
#     """Subscription page with comprehensive checks"""
#     try:
#         user = User.query.get(session['user_id'])
        
#         if not user:
#             flash('Please log in to subscribe', 'error')
#             return redirect(url_for('index'))
            
#         if user.has_active_subscription(): # Check if user has active subscription
#             flash('You already have an active subscription!', 'info')
#             return redirect(url_for('dashboard')) # Redirect to dashboard if already subscribed
#         elif user.subscription and user.subscription.status in ['incomplete', 'incomplete_expired', 'trialing']:
#             flash('You have a pending subscription. Please complete the payment process.', 'warning')
#             return redirect(url_for('dashboard'))
#         elif user.subscription and user.subscription.status == 'past_due':
#             flash('Your subscription payment is past due. Please update your payment method.', 'warning')
        
#         return render_template('subscribe.html', stripe_key=STRIPE_PUBLISHABLE_KEY)
        
#     except Exception as e:
#         print(f"Error in subscribe route: {e}")
#         flash('An error occurred. Please try again.', 'error')
#         return redirect(url_for('index'))

# @app.route('/api/create-checkout-session', methods=['POST']) # REMOVED: No more subscriptions
# @csrf.exempt
# @login_required
# @limiter.limit("5 per minute")
# def create_checkout_session():
#     # Explicitly re-import session and request to avoid UnboundLocalError
#     from flask import session, request 

#     if not request.is_json:
#         return jsonify({'success': False, 'message': 'Request must be JSON'}), 400

#     try:
#         if not all([stripe.api_key, STRIPE_PRICE_ID]):
#             logger.error("Stripe not properly configured")
#             return jsonify({'success': False, 'message': 'Payment system unavailable'}), 500
        
#         user = User.query.get(session['user_id'])
#         if not user:
#             return jsonify({'success': False, 'message': 'User not found'}), 404

#         if user.has_active_subscription():
#             logger.info(f"User {user.id} already has active subscription")
#             return jsonify({
#                 'success': False, 
#                 'message': 'Active subscription exists',
#                 'redirect': '/dashboard'
#             }), 409

#         if user.subscription and user.subscription.status in ['incomplete', 'incomplete_expired']:
#             return jsonify({
#                 'success': False,
#                 'message': 'Complete your pending subscription first',
#                 'redirect': '/dashboard'
#             }), 409

#         if recent := check_recent_checkout_sessions(user):
#             return jsonify({
#                 'success': False,
#                 'message': 'Complete your recent checkout first',
#                 'checkout_url': recent['url']
#             }), 429

#         if not (customer_id := get_or_create_stripe_customer(user)):
#             return jsonify({'success': False, 'message': 'Payment profile error'}), 500

#         if subs := stripe.Subscription.list(customer=customer_id, status='active', limit=1).data:
#             sync_subscription_from_stripe(user, subs[0])
#             return jsonify({
#                 'success': False,
#                 'message': 'Subscription exists in payment system',
#                 'redirect': '/dashboard'
#             }), 409

#         session_stripe = stripe.checkout.Session.create(
#             payment_method_types=['card'],
#             line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
#             mode='subscription',
#             success_url=url_for('payment_success', _external=True),
#             cancel_url=url_for('subscribe', _external=True),
#             customer=customer_id,
#             metadata={'user_id': str(user.id)},
#             subscription_data={'metadata': {'user_id': str(user.id)}},
#             idempotency_key=f"{user.id}-{int(datetime.utcnow().timestamp())}"
#         )

#         logger.info(f"Created checkout session {session_stripe.id} for user {user.id}")
#         return jsonify({'success': True, 'checkout_url': session_stripe.url})

#     except stripe.error.StripeError as e:
#         logger.error(f"Stripe error: {str(e)}", exc_info=True)
#         return jsonify({'success': False, 'message': 'Payment system error'}), 500
#     except Exception as e:
#         logger.error(f"Unexpected error: {str(e)}", exc_info=True)
#         return jsonify({'success': False, 'message': 'System error'}), 500

# def get_or_create_stripe_customer(user): # REMOVED: No more subscriptions
#     """Get existing or create new Stripe customer"""
#     try:
#         if user.subscription and user.subscription.stripe_customer_id and user.subscription.stripe_customer_id != 'manual_unlimited':
#             try:
#                 stripe.Customer.retrieve(user.subscription.stripe_customer_id)
#                 return user.subscription.stripe_customer_id
#             except stripe.error.InvalidRequestError:
#                 pass
        
#         existing_customers = stripe.Customer.list(email=user.email, limit=1)
#         if existing_customers.data:
#             customer = existing_customers.data[0]
#             if user.subscription:
#                 user.subscription.stripe_customer_id = customer.id
#             else:
#                 new_subscription = Subscription(
#                     user_id=user.id,
#                     stripe_customer_id=customer.id,
#                     stripe_subscription_id='',
#                     status='incomplete'
#                 )
#                 db.session.add(new_subscription)
#             db.session.commit()
#             return customer.id
        
#         customer = stripe.Customer.create(
#             email=user.email,
#             metadata={
#                 'user_id': str(user.id),
#                 'created_at': str(int(datetime.utcnow().timestamp()))
#             }
#         )
        
#         if user.subscription:
#             user.subscription.stripe_customer_id = customer.id
#         else:
#             new_subscription = Subscription(
#                 user_id=user.id,
#                 stripe_customer_id=customer.id,
#                 stripe_subscription_id='',
#                 status='incomplete'
#             )
#             db.session.add(new_subscription)
#         db.session.commit()
        
#         return customer.id
        
#     except Exception as e:
#         print(f"Error creating customer: {e}")
#         return None

# def check_recent_checkout_sessions(user): # REMOVED: No more subscriptions
#     """Check for recent incomplete checkout sessions"""
#     try:
#         if not user.subscription or not user.subscription.stripe_customer_id:
#             return None
        
#         customer_id = user.subscription.stripe_customer_id
#         if customer_id == 'manual_unlimited':
#             return None
        
#         thirty_minutes_ago = int((datetime.utcnow() - timedelta(minutes=30)).timestamp())
        
#         checkout_sessions = stripe.checkout.Session.list(
#             customer=customer_id,
#             created={'gte': thirty_minutes_ago},
#             limit=5
#         )
        
#         for session_obj in checkout_sessions.data:
#             if session_obj.status == 'open':
#                 return {
#                     'id': session_obj.id,
#                     'url': session_obj.url,
#                     'status': session_obj.status
#                 }
        
#         return None
        
#     except Exception as e:
#         print(f"Error checking recent checkout sessions: {e}")
#         return None

# def sync_subscription_from_stripe(user, stripe_subscription): # REMOVED: No more subscriptions
#     """Sync subscription from Stripe to database"""
#     try:
#         existing_subscription = Subscription.query.filter_by(user_id=user.id).first()
        
#         if existing_subscription:
#             existing_subscription.stripe_subscription_id = stripe_subscription.id
#             existing_subscription.status = stripe_subscription.status
#             existing_subscription.current_period_start = datetime.fromtimestamp(stripe_subscription.current_period_start)
#             existing_subscription.current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)
#             existing_subscription.updated_at = datetime.utcnow()
#         else:
#             new_subscription = Subscription(
#                 user_id=user.id,
#                 stripe_customer_id=stripe_subscription.customer,
#                 stripe_subscription_id=stripe_subscription.id,
#                 status=stripe_subscription.status,
#                 current_period_start=datetime.fromtimestamp(stripe_subscription.current_period_start),
#                 current_period_end=datetime.fromtimestamp(stripe_subscription.current_period_end)
#             )
#             db.session.add(new_subscription)
#         db.session.commit()
#     except Exception as e:
#         logger.error(f"Error syncing subscription from Stripe for user {user.id}: {e}", exc_info=True)

# @app.route('/api/user/subscription-status') # REMOVED: No more subscriptions
# @login_required
# def subscription_status():
#     """Check user's subscription status with Stripe sync"""
#     user = User.query.get(session['user_id'])
    
#     if user.subscription and user.subscription.stripe_subscription_id and user.subscription.stripe_subscription_id != 'manual_unlimited':
#         try:
#             stripe_subscription = stripe.Subscription.retrieve(user.subscription.stripe_subscription_id)
            
#             if user.subscription.status != stripe_subscription.status:
#                 user.subscription.status = stripe_subscription.status
#                 user.subscription.current_period_start = datetime.fromtimestamp(stripe_subscription.current_period_start)
#                 user.subscription.current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)
#                 user.subscription.updated_at = datetime.utcnow()
#                 db.session.commit()
                
#         except stripe.error.InvalidRequestError:
#             user.subscription.status = 'canceled'
#             db.session.commit()
#         except Exception as e:
#             print(f"Error syncing subscription status: {e}")
    
#     return jsonify({
#         'success': True,
#         'hasActiveSubscription': user.has_active_subscription(),
#         'subscription': {
#             'status': user.subscription.status if user.subscription else None,
#             'current_period_end': user.subscription.current_period_end.isoformat() if user.subscription and user.subscription.current_period_end else None
#         } if user.subscription else None
#     })

# @app.route('/api/admin/check-duplicate-subscriptions') # REMOVED: No more subscriptions
# @admin_required
# def check_duplicate_subscriptions():
#     """Check for users with duplicate subscriptions"""
#     try:
#         duplicate_users = db.session.query(User).join(Subscription).group_by(User.id).having(func.count(Subscription.id) > 1).all()
        
#         duplicates = []
#         for user in duplicate_users:
#             user_subs = Subscription.query.filter_by(user_id=user.id).all()
#             duplicates.append({
#                 'user_id': user.id,
#                 'email': user.email,
#                 'subscriptions': [{
#                     'id': sub.id,
#                     'status': sub.status,
#                     'stripe_subscription_id': sub.stripe_subscription_id,
#                     'created_at': sub.created_at.isoformat()
#                 } for sub in user_subs]
#             })
        
#         return jsonify({
#             'success': True,
#             'duplicates': duplicates,
#             'count': len(duplicates)
#         })
        
#     except Exception as e:
#         return jsonify({'success': False, 'message': str(e)}), 500

# @app.route('/api/check-subscription-status') # REMOVED: No more subscriptions
# @login_required
# def check_subscription_status():
#     """Check if subscription is active (for payment success page)"""
#     user = User.query.get(session['user_id'])
#     has_active = user.has_active_subscription()
    
#     return jsonify({
#         'success': True,
#         'hasActiveSubscription': has_active,
#         'isProcessing': not has_active
#     })

# @app.route('/webhook/stripe', methods=['POST']) # REMOVED: No more Stripe webhooks
# def stripe_webhook():
#     """Handle Stripe webhooks"""
#     payload = request.get_data(as_text=True)
#     sig_header = request.headers.get('Stripe-Signature')
    
#     try:
#         event = stripe.Webhook.construct_event(
#             payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET')
#         )
#         print(f"Webhook event type: {event['type']}")
#     except ValueError as e:
#         print(f"Invalid payload: {e}")
#         return '', 400
#     except stripe.error.SignatureVerificationError as e:
#         print(f"Invalid signature: {e}")
#         return '', 400
    
#     if event['type'] == 'checkout.session.completed':
#         session_data = event['data']['object']
#         print(f"Checkout session completed: {session_data['id']}")
        
#         user_id = session_data.get('metadata', {}).get('user_id')
#         if not user_id:
#             print("No user_id in session metadata")
#             return '', 400
        
#         user_id = int(user_id)
        
#         subscription = stripe.Subscription.retrieve(session_data['subscription'])
#         print(f"Subscription status: {subscription['status']}")
        
#         user = User.query.get(user_id)
#         if user:
#             existing_subscription = Subscription.query.filter_by(user_id=user_id).first()
#             if existing_subscription:
#                 existing_subscription.stripe_customer_id = session_data['customer']
#                 existing_subscription.stripe_subscription_id = session_data['subscription']
#                 existing_subscription.status = subscription['status']
#                 existing_subscription.current_period_start = datetime.fromtimestamp(subscription['current_period_start'])
#                 existing_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
#                 existing_subscription.updated_at = datetime.utcnow()
#                 print(f"Updated existing subscription for user {user_id}")
#             else:
#                 new_subscription = Subscription(
#                     user_id=user_id,
#                     stripe_customer_id=session_data['customer'],
#                     stripe_subscription_id=session_data['subscription'], # Corrected from session['subscription']
#                     status=subscription['status'],
#                     current_period_start=datetime.fromtimestamp(subscription['current_period_start']),
#                     current_period_end=datetime.fromtimestamp(subscription['current_period_end'])
#                 )
#                 db.session.add(new_subscription)
#                 print(f"Created new subscription for user {user_id}")
            
#             try:
#                 db.session.commit()
#                 print(f"Successfully updated subscription for user {user_id}")
#             except Exception as e:
#                 print(f"Error committing subscription update: {e}")
#                 db.session.rollback()
#                 return '', 500
    
#     elif event['type'] == 'invoice.payment_succeeded':
#         invoice = event['data']['object']
#         subscription_id = invoice['subscription']
        
#         if subscription_id:
#             subscription = stripe.Subscription.retrieve(subscription_id)
            
#             db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
#             if db_subscription:
#                 db_subscription.status = 'active'
#                 db_subscription.current_period_start = datetime.fromtimestamp(subscription['current_period_start'])
#                 db_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
#                 db_subscription.updated_at = datetime.utcnow()
#                 db.session.commit()
#                 print(f"Updated subscription status to active for subscription {subscription_id}")
    
#     elif event['type'] == 'invoice.payment_failed':
#         invoice = event['data']['object']
#         subscription_id = invoice['subscription']
        
#         if subscription_id:
#             db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
#             if db_subscription:
#                 db_subscription.status = 'past_due'
#                 db_subscription.updated_at = datetime.utcnow()
#                 db.session.commit()
#                 print(f"Updated subscription status to past_due for subscription {subscription_id}")
    
#     elif event['type'] == 'customer.subscription.updated':
#         subscription_data = event['data']['object']
        
#         db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_data['id']).first()
#         if db_subscription:
#             db_subscription.status = subscription_data['status']
#             db_subscription.current_period_start = datetime.fromtimestamp(subscription_data['current_period_start'])
#             db_subscription.current_period_end = datetime.fromtimestamp(subscription_data['current_period_end'])
#             db_subscription.updated_at = datetime.utcnow()
#             db.session.commit()
#             print(f"Updated subscription for subscription {subscription_data['id']}")
    
#     elif event['type'] == 'customer.subscription.deleted':
#         subscription_data = event['data']['object']
        
#         db_subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_data['id']).first()
#         if db_subscription:
#             db_subscription.status = 'canceled'
#             db_subscription.updated_at = datetime.utcnow()
#             db.session.commit()
#             print(f"Canceled subscription {subscription_data['id']}")
    
#     return '', 200

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
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        
        # Fetch active subscriptions directly from Stripe - REMOVED
        # stripe_active_subscriptions = stripe.Subscription.list(status='active', limit=100).data # Fetch up to 100 active subscriptions
        # active_subscribers_count = len(stripe_active_subscriptions)

        stats = {
            'total_videos': Video.query.filter_by(is_active=True).count(),
            'total_users': User.query.count(),
            'active_subscribers': User.query.count(), # MODIFIED: All users are "active subscribers" now
            'videos_this_month': Video.query.filter(
                Video.created_at >= month_start,
                Video.is_active == True
            ).count(),
            'total_comments': Comment.query.count(),
            'comments_this_month': Comment.query.filter(
                Comment.created_at >= month_start
            ).count()
        }
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        logger.error(f"Error fetching admin stats: {e}", exc_info=True)
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
                'likes_count': video.likes_count,
                'created_at': video.created_at.isoformat(),
                'genre': video.genre,
                'featured_tag': video.featured_tag
            })
        
        return jsonify({'success': True, 'videos': video_list})
        
    except Exception as e:
        logger.error(f"Error fetching admin videos: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/videos/<int:video_id>/likes', methods=['GET'])
@admin_required
def admin_get_video_likes(video_id):
    """Get all likes for a specific video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        
        likes = db.session.query(VideoLike, User).join(User).filter(
            VideoLike.video_id == video_id
        ).order_by(VideoLike.created_at.desc()).all()
        
        like_list = []
        for like, user in likes:
            like_list.append({
                'id': like.id,
                'user_name': user.get_display_name(),
                'user_email': user.email,
                'created_at': like.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'likes': like_list,
            'video_title': video.title,
            'total_likes': len(like_list)
        })
        
    except Exception as e:
        logger.error(f"Error fetching video likes for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/videos/<int:video_id>/comments', methods=['GET'])
@admin_required
def admin_get_video_comments(video_id):
    """Get all comments for a specific video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        
        comments = db.session.query(Comment, User).join(User).filter(
            Comment.video_id == video_id
        ).order_by(Comment.created_at.desc()).all()
        
        comment_list = []
        for comment, user in comments:
            replies_count = Comment.query.filter_by(parent_id=comment.id).count()
            
            comment_list.append({
                'id': comment.id,
                'user_name': user.get_display_name(),
                'user_email': user.email,
                'text': comment.text,
                'likes_count': comment.likes_count,
                'replies_count': replies_count,
                'created_at': comment.created_at.isoformat(),
                'is_reply': comment.parent_id is not None
            })
        
        return jsonify({
            'success': True,
            'comments': comment_list,
            'video_title': video.title,
            'total_comments': len(comment_list)
        })
        
    except Exception as e:
        logger.error(f"Error fetching video comments for admin: {e}", exc_info=True)
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
        genre = data.get('genre', '').strip()
        featured_tag = data.get('featured_tag', '').strip()
        
        if not title or not youtube_url:
            return jsonify({'success': False, 'message': 'Title and YouTube URL are required'}), 400
        
        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return jsonify({'success': False, 'message': 'Invalid YouTube URL'}), 400
        
        existing_video = Video.query.filter_by(youtube_video_id=video_id).first()
        if existing_video:
            return jsonify({'success': False, 'message': 'This video has already been added'}), 400
        
        thumbnail_url = get_youtube_thumbnail(video_id)
        
        video = Video(
            title=title,
            description=description if description else None,
            youtube_url=youtube_url,
            youtube_video_id=video_id,
            thumbnail_url=thumbnail_url,
            genre=genre if genre else None,
            featured_tag=featured_tag if featured_tag else None
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
                'created_at': video.created_at.isoformat(),
                'genre': video.genre,
                'featured_tag': video.featured_tag
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding video for admin: {e}", exc_info=True)
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
        logger.error(f"Error deleting video for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to delete video'}), 500

@app.route('/api/admin/videos/<int:video_id>', methods=['PUT'])
@admin_required
def admin_update_video(video_id):
    """Update video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        data = request.get_json()
        
        if 'title' in data:
            video.title = data['title'].strip()
        if 'description' in data:
            video.description = data['description'].strip() if data['description'] else None
        if 'is_active' in data:
            video.is_active = bool(data['is_active'])
        if 'genre' in data:
            video.genre = data['genre'].strip() if data['genre'] else None
        if 'featured_tag' in data:
            video.featured_tag = data['featured_tag'].strip() if data['featured_tag'] else None
        
        video.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Video updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating video for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update video'}), 500

@app.route('/api/admin/comments', methods=['GET'])
@admin_required
def admin_get_comments():
    """Get all comments for admin moderation"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        video_id = request.args.get('video_id', type=int)
        
        query = Comment.query
        
        if video_id:
            query = query.filter_by(video_id=video_id)
        
        comments = query.order_by(Comment.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        comment_list = []
        for comment in comments.items:
            comment_data = comment.to_dict()
            comment_data['video_title'] = comment.video.title
            comment_data['user_email'] = comment.user.email
            comment_list.append(comment_data)
        
        return jsonify({
            'success': True,
            'comments': comment_list,
            'pagination': {
                'page': comments.page,
                'pages': comments.pages,
                'per_page': comments.per_page,
                'total': comments.total,
                'has_next': comments.has_next,
                'has_prev': comments.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting comments for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/comments/<int:comment_id>', methods=['DELETE'])
@admin_required
def admin_delete_comment(comment_id):
    """Delete comment (admin only)"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Comment deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting comment for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to delete comment'}), 500

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    """Get all users for admin"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # users = db.session.query(User).options(db.joinedload(User.subscription)).order_by(User.created_at.desc()).paginate( # MODIFIED: Removed subscription join
        users = db.session.query(User).order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        user_list = []
        for user in users.items:
            user_data = {
                'id': user.id,
                'email': user.email,
                'display_name': user.get_display_name(),
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat(),
                'has_subscription': True, # MODIFIED: Always true
                'subscription_status': 'active', # MODIFIED: Always active
                'subscription_end': None, # MODIFIED: No end date for free content
                'comment_count': Comment.query.filter_by(user_id=user.id).count(),
                'watch_streak': user.watch_streak,
                'last_watch_date': user.last_watch_date.isoformat() if user.last_watch_date else None
            }
            user_list.append(user_data)
        
        return jsonify({
            'success': True,
            'users': user_list,
            'pagination': {
                'page': users.page,
                'pages': users.pages,
                'per_page': users.per_page,
                'total': users.total,
                'has_next': users.has_next,
                'has_prev': users.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting users for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_user_admin(user_id):
    """Toggle admin status for a user"""
    try:
        user = User.query.get_or_404(user_id)
        current_admin = User.query.get(session['user_id'])
        
        if user.id == current_admin.id:
            return jsonify({'success': False, 'message': 'Cannot modify your own admin status'}), 400
        
        user.is_admin = not user.is_admin
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {"granted" if user.is_admin else "revoked"} admin access',
            'is_admin': user.is_admin
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling admin status: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update user'}), 500

# User Profile Routes
@app.route('/api/user/profile', methods=['GET'])
@login_required
def get_user_profile():
    """Get current user's profile"""
    try:
        user = User.query.get(session['user_id'])
        
        profile_data = {
            'id': user.id,
            'email': user.email,
            'display_name': user.get_display_name(),
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat(),
            'has_subscription': True, # MODIFIED: Always true
            'subscription_status': 'active', # MODIFIED: Always active
            'subscription_end': None, # MODIFIED: No end date for free content
            'comment_count': Comment.query.filter_by(user_id=user.id).count(),
            'watch_streak': user.watch_streak,
            'last_watch_date': user.last_watch_date.isoformat() if user.last_watch_date else None
        }
        
        return jsonify({
            'success': True,
            'profile': profile_data
        })
        
    except Exception as e:
        logger.error(f"Error getting user profile: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to load profile'}), 500

@app.route('/api/user/comments', methods=['GET'])
@login_required # MODIFIED: Changed from subscription_required
def get_user_comments():
    """Get current user's comments"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        user_id = session['user_id']
        
        comments = Comment.query.filter_by(user_id=user_id).order_by(
            Comment.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        comment_list = []
        for comment in comments.items:
            comment_data = comment.to_dict(user_id)
            comment_data['video_title'] = comment.video.title
            comment_data['video_id'] = comment.video.id
            comment_list.append(comment_data)
        
        return jsonify({
            'success': True,
            'comments': comment_list,
            'pagination': {
                'page': comments.page,
                'pages': comments.pages,
                'per_page': comments.per_page,
                'total': comments.total,
                'has_next': comments.has_next,
                'has_prev': comments.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting user comments: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to load comments'}), 500

# Search Routes
@app.route('/api/search/videos', methods=['GET'])
@login_required # MODIFIED: Changed from subscription_required
def search_videos():
    """Search videos by title and description"""
    try:
        query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify({'success': False, 'message': 'Search query is required'}), 400
        
        videos = Video.query.filter(
            Video.is_active == True,
            db.or_(
                Video.title.ilike(f'%{query}%'),
                Video.description.ilike(f'%{query}%')
            )
        ).order_by(Video.created_at.desc()).all()
        
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
        
        return jsonify({
            'success': True,
            'videos': video_list,
            'query': query,
            'count': len(video_list)
        })
        
    except Exception as e:
        logger.error(f"Error searching videos: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Search failed'}), 500

@app.route('/api/search/comments', methods=['GET'])
@login_required # MODIFIED: Changed from subscription_required
def search_comments():
    """Search comments by text"""
    try:
        query = request.args.get('q', '').strip()
        video_id = request.args.get('video_id', type=int)
        
        if not query:
            return jsonify({'success': False, 'message': 'Search query is required'}), 400
        
        comment_query = Comment.query.filter(
            Comment.text.ilike(f'%{query}%')
        )
        
        if video_id:
            comment_query = comment_query.filter_by(video_id=video_id)
        
        comments = comment_query.order_by(Comment.created_at.desc()).all()
        
        current_user_id = session['user_id']
        comment_list = []
        for comment in comments:
            comment_data = comment.to_dict(current_user_id)
            comment_data['video_title'] = comment.video.title
            comment_data['video_id'] = comment.video.id
            comment_list.append(comment_data)
        
        return jsonify({
            'success': True,
            'comments': comment_list,
            'query': query,
            'count': len(comment_list)
        })
        
    except Exception as e:
        logger.error(f"Error searching comments: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Search failed'}), 500

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

# NEW FEATURE ROUTES START HERE

@app.route('/api/videos/categorized', methods=['GET'])
@login_required # MODIFIED: Only login_required
def get_categorized_videos():
    """
    API to get videos based on their featured_tag.
    Query parameters:
        tag: 'Top Story', 'New Series', etc.
        genre: Optional, to filter new series by genre.
    """
    try:
        tag = request.args.get('tag', '').strip()
        genre = request.args.get('genre', '').strip()
        current_user = User.query.get(session['user_id']) # Get current user object

        if not tag:
            return jsonify({'success': False, 'message': 'Tag parameter is required'}), 400

        query = Video.query.filter_by(is_active=True, featured_tag=tag)

        if tag == 'Top Story':
            videos = query.order_by(Video.likes_count.desc()).limit(10).all()
        elif tag == 'New Series':
            if genre:
                query = query.filter_by(genre=genre)
            videos = query.order_by(Video.created_at.desc()).limit(10).all()
        else:
            videos = query.order_by(Video.created_at.desc()).limit(10).all()

        video_list = []
        for video in videos:
            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_video_id': video.youtube_video_id,
                'thumbnail_url': video.thumbnail_url,
                'likes_count': video.likes_count,
                'created_at': video.created_at.isoformat(),
                'genre': video.genre,
                'featured_tag': video.featured_tag,
                'can_watch': True # MODIFIED: Always true as content is free
            })
        
        return jsonify({'success': True, 'videos': video_list})
    except Exception as e:
        logger.error(f"Error fetching categorized videos for tag '{tag}': {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Failed to load {tag} videos'}), 500

@app.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """
    API to submit user feedback or story suggestions.
    """
    try:
        data = request.get_json()
        feedback_text = data.get('feedback', '').strip()

        if not feedback_text:
            return jsonify({'success': False, 'message': 'Feedback text cannot be empty'}), 400
        
        user_id = session['user_id']
        
        feedback_entry = Feedback(
            user_id=user_id,
            feedback_text=feedback_text
        )
        db.session.add(feedback_entry)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Feedback submitted successfully!'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting feedback for user {session.get('user_id')}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to submit feedback'}), 500

@app.route('/api/user/watch-streak', methods=['GET', 'POST'])
@login_required
def user_watch_streak():
    """
    API to get and update user's daily watch streak.
    GET: Returns current streak.
    POST: Updates streak based on daily activity (e.g., watching a video).
    """
    user = User.query.get(session['user_id'])
    today = date.today()

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'streak': user.watch_streak,
            'last_watch_date': user.last_watch_date.isoformat() if user.last_watch_date else None
        })
    
    elif request.method == 'POST':
        try:
            if user.last_watch_date == today:
                # Already updated today, no change needed
                return jsonify({
                    'success': True,
                    'message': 'Streak already updated for today',
                    'streak': user.watch_streak,
                    'last_watch_date': user.last_watch_date.isoformat()
                })
            elif user.last_watch_date == (today - timedelta(days=1)):
                # Watched yesterday, increment streak
                user.watch_streak += 1
                logger.info(f"User {user.id} streak incremented to {user.watch_streak}")
            else:
                # Gap in watching or first watch, reset streak to 1
                user.watch_streak = 1
                logger.info(f"User {user.id} streak reset to {user.watch_streak}")
            
            user.last_watch_date = today
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Watch streak updated',
                'streak': user.watch_streak,
                'last_watch_date': user.last_watch_date.isoformat()
            })
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating watch streak for user {user.id}: {e}", exc_info=True)
            return jsonify({'success': False, 'message': 'Failed to update watch streak'}), 500


# NEW FEATURE ROUTES END HERE


def create_tables():
    """Create database tables and default admin user"""
    try:
        with app.app_context():
            db.create_all() # This will create all tables and new columns

            # Admin user setup
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

            # Create permanent customer access - REMOVED: No more special customer accounts for subscriptions
            # customer_email = 'peterbutler41@gmail.com'
            # customer_password = 'Bruton20!'

            # if not User.query.filter_by(email=customer_email).first():
            #     customer_user = User(
            #         email=customer_email,
            #         password_hash=bcrypt.generate_password_hash(customer_password).decode('utf-8'),
            #         is_admin=False
            #     )
            #     db.session.add(customer_user)
            #     db.session.commit()
            #     print(f"Created customer account: {customer_email}")
            # else:
            #     customer_user = User.query.filter_by(email=customer_email).first()

            # Ensure the manual_unlimited subscription is handled robustly - REMOVED
            # if not (customer_user.subscription and customer_user.subscription.stripe_customer_id == 'manual_unlimited'):
            #     # Check if a subscription exists but is not 'manual_unlimited' and remove it
            #     if customer_user.subscription:
            #         db.session.delete(customer_user.subscription)
            #         db.session.commit()

            #     unlimited_subscription = Subscription(
            #         user_id=customer_user.id,
            #         stripe_customer_id='manual_unlimited',
            #         stripe_subscription_id='manual_unlimited',
            #         status='active',
            #         current_period_start=datetime.utcnow(),
            #         current_period_end=datetime.utcnow() + timedelta(days=3650)  # 10 years
            #     )
            #     db.session.add(unlimited_subscription)
            #     db.session.commit()
            #     print(f"Granted unlimited access to: {customer_email}")

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
