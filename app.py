# FILE LOCATION: /app.py (root of your GitHub repo)
# Complete Flask application for subscription-based storytelling website

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta, date
import os
import re
from functools import wraps
from sqlalchemy import func, desc # Import desc for ordering
import logging
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from flask import send_from_directory

# Initialize Flask app
app = Flask(__name__)

# --- NEW: Define the path for the persistent data directory ---
DATA_DIR = os.path.join(os.getcwd(), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    print(f"Created persistent data directory: {DATA_DIR}")

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(DATA_DIR, "stories.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure upload folder for videos
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100 MB max upload size (increased for videos)

print(f"Using SQLite database at: {app.config['SQLALCHEMY_DATABASE_URI']}")
print(f"Using Upload Folder at: {app.config['UPLOAD_FOLDER']}")

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

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
    
    comments = db.relationship('Comment', backref='user', lazy=True, cascade='all, delete-orphan')
    comment_likes = db.relationship('CommentLike', backref='user', lazy=True, cascade='all, delete-orphan')
    video_likes = db.relationship('VideoLike', backref='user', lazy=True, cascade='all, delete-orphan')
    watch_history = db.relationship('WatchHistory', backref='user', lazy=True, cascade='all, delete-orphan') # New relationship

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def get_display_name(self):
        return self.email.split('@')[0]

class Video(db.Model):
    __tablename__ = 'video'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    youtube_url = db.Column(db.String(500), nullable=True) # Now stores playback URL for both YouTube and local files
    youtube_video_id = db.Column(db.String(50), nullable=True) # Stores YouTube ID or local placeholder
    thumbnail_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    likes_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    genre = db.Column(db.String(100), nullable=True)
    featured_tag = db.Column(db.String(50), nullable=True)
    local_file_path = db.Column(db.String(500), nullable=True) # Path on server (ONLY for locally uploaded files)
    hashtags = db.Column(db.String(500), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    is_short = db.Column(db.Boolean, default=False)
    views_count = db.Column(db.Integer, default=0)

    comments = db.relationship('Comment', backref='video', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('VideoLike', backref='video', lazy=True, cascade='all, delete-orphan')
    watch_history = db.relationship('WatchHistory', backref='video', lazy=True, cascade='all, delete-orphan')

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

class WatchHistory(db.Model):
    __tablename__ = 'watch_history'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    watched_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress_seconds = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'video_id'),
    )


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
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" # Standard YouTube thumbnail URL

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
            else:
                return redirect(url_for('dashboard'))
    
    return render_template('index.html')

# --- STATIC PAGES ROUTES ---
@app.route('/about')
def about_page():
    return render_template('about.html')

@app.route('/terms')
def terms_page():
    return render_template('terms.html')

@app.route('/privacy')
def privacy_page():
    return render_template('privacy.html')

@app.route('/contact')
def contact_page():
    return render_template('contact.html')

@app.route('/help-support')
def help_support_page():
    return render_template('help_support.html')

@app.route('/account-settings')
@login_required
def account_settings_page():
    user = User.query.get(session['user_id'])
    return render_template('account_settings.html', user=user)

# Serve uploaded media files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- END STATIC PAGES ROUTES ---


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
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'isAdmin': False,
            'redirect': '/dashboard'
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
            })
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
    flash('You have been logged out successfully.', 'info')
    return jsonify({'success': True, 'message': 'Logged out successfully', 'redirect': url_for('index')})

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
            'has_subscription': True
        }
    })

# Video Like System Routes
@app.route('/api/videos/<int:video_id>/like', methods=['POST'])
@login_required
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

# --- NEW: VIEW COUNT ENDPOINT ---
@app.route('/api/videos/<int:video_id>/view', methods=['POST'])
@login_required
def record_view(video_id):
    """Records a view for a video. This is a simple incrementer."""
    try:
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'success': False, 'message': 'Video not found'}), 404

        # Using a more robust method to increment to avoid race conditions
        Video.query.filter_by(id=video_id).update({'views_count': Video.views_count + 1})
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'View recorded'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error recording view for video {video_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to record view'}), 500


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    return render_template('dashboard.html')

@app.route('/api/videos')
@login_required
def get_videos():
    """
    Get all active videos for feed.
    'can_watch' flag is always true now.
    """
    videos = Video.query.filter_by(is_active=True).order_by(Video.created_at.desc()).all()
    current_user = User.query.get(session['user_id'])

    video_list = []
    for video in videos:
        user_liked = VideoLike.query.filter_by(
            user_id=current_user.id,
            video_id=video.id
        ).first() is not None
        
        # Determine correct playback URL
        playback_url = None
        if video.local_file_path:
            playback_url = url_for('uploaded_file', filename=os.path.basename(video.local_file_path))
        elif video.youtube_url: # This now holds the YouTube URL (for YouTube videos)
            playback_url = video.youtube_url

        video_list.append({
            'id': video.id,
            'title': video.title,
            'description': video.description,
            'youtube_url': video.youtube_url, # Original YouTube URL (if applicable)
            'youtube_video_id': video.youtube_video_id, # YouTube ID (if applicable)
            'thumbnail_url': video.thumbnail_url,
            'likes_count': video.likes_count,
            'user_liked': user_liked,
            'created_at': video.created_at.isoformat(),
            'genre': video.genre,
            'featured_tag': video.featured_tag,
            'can_watch': True,
            'local_file_path': playback_url, # This field is now the primary playback URL for both types
            'duration_seconds': video.duration_seconds,
            'is_short': video.is_short,
            'views_count': video.views_count,
            'hashtags': video.hashtags,
            'comment_count': Comment.query.filter_by(video_id=video.id).count()
        })
    
    return jsonify({'success': True, 'videos': video_list})

# Comment System Routes
@app.route('/api/videos/<int:video_id>/comments', methods=['GET'])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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

        stats = {
            'total_videos': Video.query.filter_by(is_active=True).count(),
            'total_users': User.query.count(),
            'active_subscribers': User.query.count(), # Note: This will count all users, not just paying subs, if subscriptions are disabled.
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
            
            # Determine source URL for admin view
            source_url_for_admin = None
            if video.local_file_path:
                source_url_for_admin = url_for('uploaded_file', filename=os.path.basename(video.local_file_path))
            elif video.youtube_url: # This now holds the YouTube URL (for YouTube videos)
                source_url_for_admin = video.youtube_url

            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_url': video.youtube_url, # Original YouTube URL (if applicable)
                'youtube_video_id': video.youtube_video_id, # YouTube ID (if applicable)
                'thumbnail_url': video.thumbnail_url,
                'is_active': video.is_active,
                'likes_count': video.likes_count,
                'created_at': video.created_at.isoformat(),
                'genre': video.genre,
                'featured_tag': video.featured_tag,
                'local_file_path': source_url_for_admin, # This is the source URL for admin view/playback
                'duration_seconds': video.duration_seconds,
                'is_short': video.is_short,
                'views_count': video.views_count,
                'hashtags': video.hashtags,
                'comment_count': comment_count
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
        
        comments = Comment.query.filter_by(parent_id=None, video_id=video_id).order_by(Comment.created_at.desc()).all()
        
        comment_list = []
        for comment in comments:
            replies_count = Comment.query.filter_by(parent_id=comment.id).count()
            
            comment_list.append({
                'id': comment.id,
                'user_name': comment.user.get_display_name(),
                'user_email': comment.user.email,
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
        # Determine if form data is JSON (from edit modal) or multipart (from add video form)
        # Using request.form for all data to handle both types uniformly via FormData
        data = request.form
        video_source_type = data.get('video_source_type')

        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        genre = data.get('genre', '').strip()
        featured_tag = data.get('featured_tag', '').strip()
        hashtags = data.get('hashtags', '').strip()
        is_short = data.get('is_short', 'false').lower() == 'true'
        duration_seconds_str = data.get('duration_seconds') # String, could be empty
        
        # Convert duration_seconds to int if provided, otherwise None
        duration_seconds = None
        if duration_seconds_str:
            try:
                duration_seconds = int(duration_seconds_str)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid duration format (must be a number)'}), 400

        video_id = None
        youtube_url = None
        local_file_path = None
        thumbnail_url = url_for('static', filename='default_thumbnail.jpg') # Default thumbnail

        if video_source_type == 'youtube_url':
            youtube_url_input = data.get('youtube_url', '').strip()
            if not title or not youtube_url_input:
                return jsonify({'success': False, 'message': 'Title and YouTube URL are required'}), 400
            
            video_id = extract_youtube_video_id(youtube_url_input)
            if not video_id:
                return jsonify({'success': False, 'message': 'Invalid YouTube URL'}), 400
            
            # Check for existing YouTube video
            if Video.query.filter_by(youtube_video_id=video_id).first():
                return jsonify({'success': False, 'message': 'This YouTube video has already been added'}), 400
            
            thumbnail_url = get_youtube_thumbnail(video_id)
            youtube_url = youtube_url_input # Store original YouTube URL

        elif video_source_type == 'file_upload':
            if 'video_file' not in request.files:
                return jsonify({'success': False, 'message': 'No video file part for upload'}), 400
            
            video_file = request.files['video_file']
            if video_file.filename == '':
                return jsonify({'success': False, 'message': 'No selected video file'}), 400
            
            if not title:
                return jsonify({'success': False, 'message': 'Title is required for uploaded video'}), 400

            allowed_extensions = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
            if '.' not in video_file.filename or video_file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
                return jsonify({'success': False, 'message': 'Unsupported file type for upload'}), 400
            
            filename = secure_filename(video_file.filename)
            filename_with_user_id = f"{session['user_id']}_{datetime.utcnow().timestamp()}_{filename}"
            local_file_path_on_server = os.path.join(app.config['UPLOAD_FOLDER'], filename_with_user_id)
            video_file.save(local_file_path_on_server)

            # For local uploads, the 'youtube_url' field in the DB will store the public URL
            youtube_url = url_for('uploaded_file', filename=filename_with_user_id)
            youtube_video_id_placeholder = f"local_{filename_with_user_id.split('.')[0]}"
            video_id = youtube_video_id_placeholder # Use this as video_id for local files

            # Check for existing local file video (by server path)
            if Video.query.filter_by(local_file_path=local_file_path_on_server).first():
                 # Clean up the uploaded file if it's a duplicate based on path
                os.remove(local_file_path_on_server)
                return jsonify({'success': False, 'message': 'This video file has already been uploaded'}), 400
            
            local_file_path = local_file_path_on_server # Store the actual path for DB

        else:
            return jsonify({'success': False, 'message': 'Invalid video source type'}), 400

        # Now create the Video object
        video = Video(
            title=title,
            description=description if description else None,
            youtube_url=youtube_url, # Stores public URL for local files OR original YouTube URL
            youtube_video_id=video_id, # Stores local_id OR YouTube_ID
            thumbnail_url=thumbnail_url,
            is_active=True,
            likes_count=0,
            genre=genre if genre else None,
            featured_tag=featured_tag if featured_tag else None,
            local_file_path=local_file_path, # Stores server internal path (None for YouTube)
            hashtags=hashtags if hashtags else None,
            duration_seconds=duration_seconds,
            is_short=is_short,
            views_count=0
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
                'local_file_path': url_for('uploaded_file', filename=os.path.basename(video.local_file_path)) if video.local_file_path else None, # Return playable URL for local
                'thumbnail_url': video.thumbnail_url,
                'created_at': video.created_at.isoformat(),
                'genre': video.genre,
                'featured_tag': video.featured_tag,
                'hashtags': video.hashtags,
                'is_short': video.is_short,
                'duration_seconds': video.duration_seconds
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding video for admin: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to add video. ' + str(e)}), 500


@app.route('/api/admin/videos/<int:video_id>', methods=['DELETE'])
@admin_required
def admin_delete_video(video_id):
    """Delete video (admin only)"""
    try:
        video = Video.query.get_or_404(video_id)
        
        # If it's a locally uploaded file, delete the file too
        if video.local_file_path and os.path.exists(video.local_file_path):
            os.remove(video.local_file_path)
            print(f"Deleted local file: {video.local_file_path}")

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
        if 'hashtags' in data:
            video.hashtags = data['hashtags'].strip() if data['hashtags'] else None
        if 'is_short' in data:
            video.is_short = bool(data['is_short'])
        
        # Handle duration_seconds from optional input
        if 'duration_seconds' in data and data['duration_seconds'] is not None and data['duration_seconds'] != '':
            try:
                video.duration_seconds = int(data['duration_seconds'])
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid duration format'}), 400
        else: # If empty string or None, set to None in DB
            video.duration_seconds = None

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
        logger.error(f"Error deleting comment: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to delete comment'}), 500

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    """Get all users for admin"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
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
                'has_subscription': True, # All users are "active subscribers" now
                'subscription_status': 'active', # All users are "active" now
                'subscription_end': None, # No end date for free content
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
            'has_subscription': True, # All users are "active subscribers" now
            'subscription_status': 'active', # All users are "active" now
            'subscription_end': None, # No end date for free content
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
@login_required
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
@login_required
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
                Video.description.ilike(f'%{query}%'),
                Video.hashtags.ilike(f'%{query}%') # Search by hashtags
            )
        ).order_by(Video.created_at.desc()).all()
        
        video_list = []
        for video in videos:
            # Determine correct playback URL
            playback_url = None
            if video.local_file_path:
                playback_url = url_for('uploaded_file', filename=os.path.basename(video.local_file_path))
            elif video.youtube_url: # This holds the public YouTube URL
                playback_url = video.youtube_url

            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_url': video.youtube_url,
                'youtube_video_id': video.youtube_video_id,
                'thumbnail_url': video.thumbnail_url,
                'created_at': video.created_at.isoformat(),
                'local_file_path': playback_url, # Frontend will use this for playback
                'duration_seconds': video.duration_seconds,
                'is_short': video.is_short,
                'views_count': video.views_count
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
@login_required
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

@app.route('/api/videos/categorized', methods=['GET'])
@login_required
def get_categorized_videos():
    """
    API to get videos based on their featured_tag.
    Also handles "Trending Now" and "New This Week" logic.
    Query parameters:
        tag: 'Trending Now', 'Snayvu Originals', 'Shorts', 'New This Week', 'Emotional Picks', 'Live Now', 'Featured Creator', 'Continue Watching'
        genre: Optional, to filter by genre.
    """
    try:
        tag = request.args.get('tag', '').strip()
        genre = request.args.get('genre', '').strip()
        current_user_id = session['user_id']

        if not tag:
            return jsonify({'success': False, 'message': 'Tag parameter is required'}), 400

        query = Video.query.filter_by(is_active=True)
        
        # --- UPDATED LOGIC TO HANDLE ALL SIDEBAR LINKS ---
        if tag == 'Trending Now' or tag == 'Discover': # Discover will show trending content
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            videos = query.filter(Video.created_at >= seven_days_ago).order_by(Video.views_count.desc(), Video.likes_count.desc()).limit(15).all()
        
        elif tag == 'Snayvu Originals':
            videos = query.filter_by(featured_tag='Snayvu Originals').order_by(Video.created_at.desc()).limit(15).all()
        
        elif tag == 'Shorts' or tag == 'Just Dropped': # Both link to the same logic
            videos = query.filter_by(is_short=True).order_by(Video.created_at.desc()).limit(15).all()
        
        elif tag == 'New This Week':
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            videos = query.filter(Video.created_at >= seven_days_ago).order_by(Video.created_at.desc()).limit(15).all()
        
        elif tag == 'Emotional Picks' or tag == 'For You (Mood Feed)': # Both link to the same logic
            videos = query.filter_by(featured_tag='Emotional Picks').order_by(Video.created_at.desc()).limit(15).all()
        
        elif tag == 'Live Now':
            videos = query.filter_by(featured_tag='Live').order_by(Video.created_at.desc()).limit(10).all()
        
        elif tag == 'Channels' or tag == 'Featured Creator': # Both link to the same logic
            videos = query.filter_by(featured_tag='Featured Creator').order_by(Video.created_at.desc()).limit(15).all()
        
        elif tag == 'Continue Watching':
            watch_history_entries = WatchHistory.query.filter_by(
                user_id=current_user_id,
                completed=False
            ).order_by(desc(WatchHistory.watched_at)).limit(10).all()
            
            video_ids = [entry.video_id for entry in watch_history_entries]
            if not video_ids:
                videos = []
            else:
                # Fetch the actual video objects based on history order
                videos_from_history = Video.query.filter(Video.id.in_(video_ids)).order_by(
                    db.case(
                        {id_: index for index, id_ in enumerate(video_ids)},
                        value=Video.id
                    )
                ).all()
                
                # Attach progress and total duration for frontend
                video_map_with_progress = {}
                for entry in watch_history_entries:
                    video = next((v for v in videos_from_history if v.id == entry.video_id), None)
                    if video:
                        video.progress_seconds = entry.progress_seconds
                        video.total_duration = video.duration_seconds # Assuming duration_seconds is set for all videos
                        video_map_with_progress[video.id] = video
                videos = [video_map_with_progress[id_] for id_ in video_ids if id_ in video_map_with_progress] # Maintain order

        else:
            # Default to fetching by any other provided featured_tag or return empty
            videos = query.filter_by(featured_tag=tag).order_by(Video.created_at.desc()).limit(10).all()

        video_list = []
        for video in videos:
            video_playback_url = ''
            if video.local_file_path:
                video_playback_url = url_for('uploaded_file', filename=os.path.basename(video.local_file_path))
            elif video.youtube_url:
                video_playback_url = video.youtube_url

            video_list.append({
                'id': video.id,
                'title': video.title,
                'description': video.description,
                'youtube_url': video.youtube_url,
                'youtube_video_id': video.youtube_video_id,
                'thumbnail_url': video.thumbnail_url,
                'likes_count': video.likes_count,
                'user_liked': VideoLike.query.filter_by(user_id=current_user_id, video_id=video.id).first() is not None,
                'created_at': video.created_at.isoformat(),
                'genre': video.genre,
                'featured_tag': video.featured_tag,
                'can_watch': True,
                'local_file_path': video_playback_url,
                'duration_seconds': video.duration_seconds,
                'is_short': video.is_short,
                'views_count': video.views_count,
                'hashtags': video.hashtags,
                'comment_count': Comment.query.filter_by(video_id=video.id).count(),
                'progress_seconds': getattr(video, 'progress_seconds', 0),
                'total_duration': getattr(video, 'total_duration', video.duration_seconds)
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

    if user is None:
        session.clear()
        return jsonify({'success': False, 'message': 'User session invalid, please log in again.', 'redirect': url_for('index')}), 401

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
                return jsonify({
                    'success': True,
                    'message': 'Streak already updated for today',
                    'streak': user.watch_streak,
                    'last_watch_date': user.last_watch_date.isoformat()
                })
            elif user.last_watch_date == (today - timedelta(days=1)):
                user.watch_streak += 1
                logger.info(f"User {user.id} streak incremented to {user.watch_streak}")
            else:
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

# --- NEW: Watch History API ---
@app.route('/api/watch-history/<int:video_id>', methods=['POST'])
@login_required
def update_watch_history(video_id):
    """
    Update watch history for a video.
    Expected JSON: {'progress_seconds': int, 'completed': bool}
    """
    user_id = session['user_id']
    data = request.get_json()
    progress_seconds = data.get('progress_seconds', 0)
    completed = data.get('completed', False)

    try:
        video = Video.query.get(video_id)
        if not video:
            return jsonify({'success': False, 'message': 'Video not found'}), 404

        history_entry = WatchHistory.query.filter_by(user_id=user_id, video_id=video_id).first()

        if history_entry:
            history_entry.progress_seconds = progress_seconds
            history_entry.completed = completed
            history_entry.watched_at = datetime.utcnow() # Update last watched time
        else:
            history_entry = WatchHistory(
                user_id=user_id,
                video_id=video_id,
                progress_seconds=progress_seconds,
                completed=completed
            )
            db.session.add(history_entry)
        
        # Increment views_count for trending logic (simple view tracking)
        # Only increment if progress > 0 (watched some part) and not already incremented recently for this session/video
        # For simplicity, we just increment on every update with progress > 0.
        # A more robust system would use a separate view_event table or daily unique views.
        if progress_seconds > 0 and video.views_count is not None:
             video.views_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Watch history updated'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating watch history for user {user_id}, video {video_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update watch history'}), 500

# --- NEW: VIDEO UPLOAD ROUTE ---
# This route is specifically for user uploads via dashboard, not admin panel.
# Admin panel uses admin_add_video, which is now unified.
# If users can upload from dashboard without being admin, this route is appropriate for them.
@app.route('/api/upload-video', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def upload_video():
    # This route is for general users to upload via a dashboard modal.
    # The admin_add_video now handles file uploads from the admin page.
    # To avoid confusion, you might consider removing this if all uploads are via admin.
    # However, if non-admin users can upload, this route is appropriate for them.
    
    if 'video_file' not in request.files:
        return jsonify({'success': False, 'message': 'No video file part'}), 400
    
    video_file = request.files['video_file']
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    hashtags_str = request.form.get('hashtags', '').strip()
    duration_str = request.form.get('duration_seconds', '').strip() # Changed from '0' to '' to handle optional empty field
    is_short_input = request.form.get('is_short', 'false').lower() == 'true'

    if video_file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if not title:
        return jsonify({'success': False, 'message': 'Video title is required'}), 400

    allowed_extensions = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
    if '.' not in video_file.filename or video_file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'success': False, 'message': 'Unsupported file type'}), 400

    try:
        duration_seconds = int(duration_str) if duration_str.isdigit() else None # Parse to int or None
        is_short = is_short_input or (duration_seconds is not None and duration_seconds < 60) # Auto-set is_short if duration provided

        filename = secure_filename(video_file.filename)
        filename_with_user_id = f"{session['user_id']}_{datetime.utcnow().timestamp()}_{filename}"
        local_file_path_on_server = os.path.join(app.config['UPLOAD_FOLDER'], filename_with_user_id)
        video_file.save(local_file_path_on_server)

        thumbnail_url = url_for('static', filename='default_thumbnail.jpg') # Generic thumbnail for now

        # Use the /uploads/ endpoint for playback URL (stored in youtube_url for consistency in frontend)
        playback_url_for_frontend = url_for('uploaded_file', filename=filename_with_user_id)

        new_video = Video(
            title=title,
            description=description if description else None,
            youtube_url=playback_url_for_frontend, # Stores public URL for local files
            youtube_video_id=None, # Not a YouTube ID
            thumbnail_url=thumbnail_url,
            is_active=True,
            genre="Uploaded",
            featured_tag="Just Dropped", # Mark as "Just Dropped"
            local_file_path=local_file_path_on_server, # Store the actual path on server
            hashtags=hashtags_str if hashtags_str else None,
            duration_seconds=duration_seconds, # Can be None
            is_short=is_short,
            views_count=0
        )
        db.session.add(new_video)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Video uploaded successfully!',
            'video': {
                'id': new_video.id,
                'title': new_video.title,
                'description': new_video.description,
                'local_file_path': playback_url_for_frontend, # Frontend will use this for playback
                'thumbnail_url': new_video.thumbnail_url,
                'duration_seconds': new_video.duration_seconds,
                'is_short': new_video.is_short
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during video upload: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to upload video. Please try again.'}), 500


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


def create_tables():
    """Create database tables and default admin user"""
    try:
        with app.app_context():
            db.create_all() # This will create all tables and new columns

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
        print("WARNING: If you added new columns, you might need to delete stories.db and restart.")


# Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    create_tables()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
else:
    create_tables()
