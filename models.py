from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from enum import Enum
import secrets
import string

db = SQLAlchemy()

# Enums for better data integrity
class MediaType(Enum):
    IMAGE = 'image'
    VIDEO = 'video'

class PostStatus(Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    SCHEDULED = 'scheduled'
    POSTED = 'posted'
    FAILED = 'failed'

class SubscriptionTier(Enum):
    BASIC = 'basic'
    PRO = 'pro'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    subscription_active = db.Column(db.Boolean, default=False)
    subscription_tier = db.Column(db.Enum(SubscriptionTier), default=SubscriptionTier.BASIC)
    stripe_customer_id = db.Column(db.String(100))
    trial_ends_at = db.Column(db.DateTime)
    weekly_generation_day = db.Column(db.Integer, default=0)  # 0=Sunday, 6=Saturday
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    profile = db.relationship('BusinessProfile', backref='user', uselist=False)
    social_accounts = db.relationship('SocialAccount', backref='user')
    campaigns = db.relationship('Campaign', backref='user')
    posts = db.relationship('Post', backref='user')
    notifications = db.relationship('Notification', backref='user')
    
    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if not self.verification_token:
            self.verification_token = self.generate_verification_token()
    
    def generate_verification_token(self):
        """Generate email verification token"""
        return secrets.token_urlsafe(32)
    
    def get_posts_this_month(self):
        """Get number of posts created this month"""
        from sqlalchemy import extract
        now = datetime.utcnow()
        return Post.query.filter(
            Post.user_id == self.id,
            extract('year', Post.created_at) == now.year,
            extract('month', Post.created_at) == now.month
        ).count()
    
    def can_generate_posts(self):
        """Check if user can generate more posts this month"""
        from config import Config
        tier_info = Config.SUBSCRIPTION_TIERS.get(self.subscription_tier.value)
        if not tier_info:
            return False
        return self.get_posts_this_month() < tier_info['posts_per_month']

class BusinessProfile(db.Model):
    __tablename__ = 'business_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    brand_name = db.Column(db.String(100))
    brand_description = db.Column(db.Text)
    brand_voice = db.Column(db.Text)
    brand_style = db.Column(db.Text)
    target_audience = db.Column(db.String(200))
    industry = db.Column(db.String(100))
    content_themes = db.Column(db.JSON)  # Array of themes
    hashtag_preferences = db.Column(db.JSON)
    ai_instructions = db.Column(db.Text)
    logo_url = db.Column(db.String(500))
    brand_colors = db.Column(db.JSON)  # Array of hex colors
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SocialAccount(db.Model):
    __tablename__ = 'social_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    platform = db.Column(db.String(20), nullable=False)  # 'instagram', 'facebook', 'tiktok'
    account_id = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100))
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expires_at = db.Column(db.DateTime)
    is_connected = db.Column(db.Boolean, default=False)
    is_business_account = db.Column(db.Boolean, default=False)
    follower_count = db.Column(db.Integer, default=0)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_sync = db.Column(db.DateTime)

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # This is the core of the campaign - the template that defines what content to generate
    prompt_template = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    # How many posts this campaign should generate per week
    posts_per_week = db.Column(db.Integer, default=7)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    # All posts generated from this campaign
    posts = db.relationship('Post', backref='campaign')

class Post(db.Model):
    __tablename__ = 'posts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Links each post back to the campaign that generated it
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    
    # Content
    media_type = db.Column(db.Enum(MediaType), nullable=False)
    media_url = db.Column(db.String(500))  # S3 URL
    thumbnail_url = db.Column(db.String(500))  # For videos
    caption = db.Column(db.Text)
    hashtags = db.Column(db.JSON)
    
    # Generation details
    # The actual prompt used to generate this specific post (derived from campaign template)
    prompt_used = db.Column(db.Text)
    generation_metadata = db.Column(db.JSON)
    
    # Status and workflow
    status = db.Column(db.Enum(PostStatus), default=PostStatus.PENDING)
    rejection_note = db.Column(db.Text)
    regeneration_count = db.Column(db.Integer, default=0)
    
    # Scheduling
    scheduled_for = db.Column(db.DateTime)
    posted_at = db.Column(db.DateTime)
    instagram_post_id = db.Column(db.String(100))
    facebook_post_id = db.Column(db.String(100))
    tiktok_post_id = db.Column(db.String(100))
    
    # Performance metrics
    likes = db.Column(db.Integer, default=0)
    comments = db.Column(db.Integer, default=0)
    shares = db.Column(db.Integer, default=0)
    reach = db.Column(db.Integer, default=0)
    impressions = db.Column(db.Integer, default=0)
    engagement_rate = db.Column(db.Float, default=0.0)
    last_metrics_update = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BrandAsset(db.Model):
    __tablename__ = 'brand_assets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    asset_type = db.Column(db.String(50), nullable=False)  # 'logo', 'image', 'style_guide'
    file_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # post_published, upload_complete, etc.
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    data = db.Column(db.JSON)  # Additional notification data
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WeeklyGeneration(db.Model):
    __tablename__ = 'weekly_generations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    posts_generated = db.Column(db.Integer, default=0)
    posts_approved = db.Column(db.Integer, default=0)
    posts_rejected = db.Column(db.Integer, default=0)
    generation_completed = db.Column(db.Boolean, default=False)
    email_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)