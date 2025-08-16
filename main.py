from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Post, BusinessProfile, SocialAccount, Notification, Campaign, PostStatus, BrandAsset, MediaType
from forms import BusinessProfileForm, CampaignForm, BrandAssetForm, FileUploadForm
from tasks.generation import regenerate_post, generate_single_post
from tasks.publishing import schedule_approved_posts
from services.ai_service import ai_service
import requests
import os
from datetime import datetime, timedelta
from utils import allowed_file

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    # Get user stats
    total_posts = Post.query.filter_by(user_id=current_user.id, status=PostStatus.POSTED).count()
    scheduled_posts = Post.query.filter_by(user_id=current_user.id, status=PostStatus.SCHEDULED).count()
    pending_posts = Post.query.filter_by(user_id=current_user.id, status=PostStatus.PENDING).count()
    total_generated = Post.query.filter_by(user_id=current_user.id).count()
    
    # Get recent activity
    recent_posts = Post.query.filter_by(user_id=current_user.id)\
        .order_by(Post.created_at.desc()).limit(5).all()
    
    # Calculate total reach
    total_reach = db.session.query(db.func.sum(Post.reach))\
        .filter_by(user_id=current_user.id).scalar() or 0
    
    # Fixed stats dictionary with all required keys
    stats = {
        'total_posts': total_posts,
        'total_reach': total_reach,
        'scheduled': scheduled_posts,
        'total_generated': total_generated,
        'pending': pending_posts,
        'total_media': Post.query.filter_by(user_id=current_user.id).count(),  # Total media files
        'processing': Post.query.filter_by(
            user_id=current_user.id, 
            status=PostStatus.PENDING
        ).count()  # Posts currently processing
    }
    
    return render_template('dashboard.html', stats=stats, recent_posts=recent_posts)

@main_bp.route('/posts')
@login_required
def posts():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    
    # Build query
    query = Post.query.filter_by(user_id=current_user.id)
    
    if status_filter != 'all':
        if status_filter == 'pending':
            query = query.filter_by(status=PostStatus.PENDING)
        elif status_filter == 'approved':
            query = query.filter_by(status=PostStatus.APPROVED)
        elif status_filter == 'scheduled':
            query = query.filter_by(status=PostStatus.SCHEDULED)
        elif status_filter == 'posted':
            query = query.filter_by(status=PostStatus.POSTED)
        elif status_filter == 'rejected':
            query = query.filter_by(status=PostStatus.REJECTED)
    
    posts = query.order_by(Post.created_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    
    return render_template('posts.html', posts=posts, status_filter=status_filter)

@main_bp.route('/campaigns')
@login_required
def campaigns():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    # Show all campaigns for the current user
    campaigns = Campaign.query.filter_by(user_id=current_user.id)\
        .order_by(Campaign.created_at.desc()).all()
    
    return render_template('campaigns.html', campaigns=campaigns)

@main_bp.route('/campaigns/new', methods=['GET', 'POST'])
@login_required
def new_campaign():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    form = CampaignForm()
    if form.validate_on_submit():
        # Create new campaign with user-defined parameters
        campaign = Campaign(
            user_id=current_user.id,
            name=form.name.data,
            description=form.description.data,
            # This is the core - the prompt template that defines what content to generate
            prompt_template=form.prompt_template.data,
            # How many posts per week this campaign should generate
            posts_per_week=form.posts_per_week.data
        )
        db.session.add(campaign)
        db.session.commit()
        
        flash('Campaign created successfully!', 'success')
        return redirect(url_for('main.campaigns'))
    
    return render_template('new_campaign.html', form=form)

@main_bp.route('/campaigns/ai-generate', methods=['GET', 'POST'])
@login_required
def ai_generate_campaign():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    if request.method == 'POST':
        data = request.get_json()
        num_posts = data.get('num_posts', 7)
        num_images = data.get('num_images', 5) 
        num_videos = data.get('num_videos', 2)
        
        # Get user's business profile
        profile = current_user.profile
        if not profile:
            return jsonify({'error': 'Please complete your business profile first'}), 400
        
        # Build business profile data
        business_profile = {
            'brand_name': profile.brand_name or 'Your Brand',
            'brand_description': profile.brand_description or '',
            'brand_voice': profile.brand_voice or 'Professional and engaging',
            'brand_style': profile.brand_style or '',
            'target_audience': profile.target_audience or 'General audience',
            'industry': profile.industry or '',
            'content_themes': profile.content_themes or [],
            'hashtag_preferences': profile.hashtag_preferences or [],
            'ai_instructions': profile.ai_instructions or '',
            'brand_colors': profile.brand_colors or []
        }
        
        # Generate campaign prompts using AI
        result = ai_service.generate_campaign_prompts(
            business_profile, num_posts, num_images, num_videos
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'campaign_name': result['campaign_name'],
                'campaign_description': result['campaign_description'],
                'prompts': result['prompts'],
                'metadata': result['metadata']
            })
        else:
            return jsonify({'error': result['error']}), 500
    
    return render_template('ai_generate_campaign.html')

@main_bp.route('/campaigns/create-from-ai', methods=['POST'])
@login_required
def create_campaign_from_ai():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    data = request.get_json()
    
    # Create individual campaigns for each prompt or one combined campaign
    campaign_type = data.get('campaign_type', 'combined')  # 'combined' or 'individual'
    
    if campaign_type == 'combined':
        # Create one campaign with all prompts combined
        combined_prompts = []
        for prompt_data in data.get('prompts', []):
            combined_prompts.append(f"[{prompt_data['type'].upper()}] {prompt_data['prompt']}")
        
        campaign = Campaign(
            user_id=current_user.id,
            name=data.get('campaign_name', 'AI Generated Campaign'),
            description=data.get('campaign_description', ''),
            prompt_template='\n'.join(combined_prompts),
            posts_per_week=len(data.get('prompts', []))
        )
        db.session.add(campaign)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign created successfully!',
            'campaign_id': campaign.id
        })
    
    else:
        # Create individual campaigns for each prompt
        created_campaigns = []
        
        for i, prompt_data in enumerate(data.get('prompts', [])):
            campaign = Campaign(
                user_id=current_user.id,
                name=f"{data.get('campaign_name', 'AI Generated')} - {prompt_data.get('content_theme', '').replace('_', ' ').title()}",
                description=f"AI generated {prompt_data['type']} content: {prompt_data.get('content_theme', '')}",
                prompt_template=prompt_data['prompt'],
                posts_per_week=1  # Each individual campaign generates 1 post per week
            )
            db.session.add(campaign)
            db.session.flush()  # Get ID
            created_campaigns.append({
                'id': campaign.id,
                'name': campaign.name,
                'type': prompt_data['type']
            })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Created {len(created_campaigns)} individual campaigns!',
            'campaigns': created_campaigns
        })
@main_bp.route('/brand-assets')
@login_required
def brand_assets():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    assets = BrandAsset.query.filter_by(user_id=current_user.id, is_active=True)\
        .order_by(BrandAsset.created_at.desc()).all()
    
    return render_template('brand_assets.html', assets=assets)

@main_bp.route('/brand-assets/upload', methods=['GET', 'POST'])
@login_required
def upload_brand_asset():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    form = BrandAssetForm()
    if form.validate_on_submit():
        file = form.file.data
        
        if file and allowed_file(file.filename):
            # Read file data
            file_data = file.read()
            file.seek(0)  # Reset file pointer
            
            # Upload to S3
            file_url = storage_service.upload_brand_asset(
                file_data=file_data,
                filename=file.filename,
                user_id=current_user.id,
                asset_type=form.asset_type.data
            )
            
            if file_url:
                # Create brand asset record
                asset = BrandAsset(
                    user_id=current_user.id,
                    name=form.name.data,
                    asset_type=form.asset_type.data,
                    file_url=file_url,
                    file_size=len(file_data),
                    mime_type=file.content_type,
                    description=form.description.data
                )
                db.session.add(asset)
                db.session.commit()
                
                flash('Brand asset uploaded successfully!', 'success')
                return redirect(url_for('main.brand_assets'))
            else:
                flash('Failed to upload file. Please try again.', 'error')
        else:
            flash('Invalid file type. Please upload images or PDFs only.', 'error')
    
    return render_template('upload_brand_asset.html', form=form)

@main_bp.route('/brand-assets/<int:asset_id>/delete', methods=['POST'])
@login_required
def delete_brand_asset(asset_id):
    if not current_user.subscription_active:
        return jsonify({'error': 'Subscription required'}), 403
    
    asset = BrandAsset.query.filter_by(id=asset_id, user_id=current_user.id).first()
    if not asset:
        return jsonify({'error': 'Asset not found'}), 404
    
    # Delete from S3
    storage_service.delete_media(asset.file_url)
    
    # Mark as inactive instead of deleting
    asset.is_active = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Asset deleted successfully'})
@main_bp.route('/analytics')
@login_required
def analytics():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    # Get analytics data for the last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Get posted content
    posted_posts = Post.query.filter(
        Post.user_id == current_user.id,
        Post.status == PostStatus.POSTED,
        Post.posted_at >= thirty_days_ago
    ).all()
    
    # Calculate metrics
    total_reach = sum(post.reach or 0 for post in posted_posts)
    total_impressions = sum(post.impressions or 0 for post in posted_posts)
    total_likes = sum(post.likes or 0 for post in posted_posts)
    total_comments = sum(post.comments or 0 for post in posted_posts)
    
    avg_engagement_rate = 0
    if posted_posts:
        engagement_rates = [post.engagement_rate for post in posted_posts if post.engagement_rate]
        if engagement_rates:
            avg_engagement_rate = sum(engagement_rates) / len(engagement_rates)
    
    # Get top performing posts
    top_posts = sorted(posted_posts, key=lambda p: p.engagement_rate or 0, reverse=True)[:5]
    
    analytics_data = {
        'total_reach': total_reach,
        'total_impressions': total_impressions,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'avg_engagement_rate': round(avg_engagement_rate, 2),
        'top_performing_posts': top_posts,
        'posts_count': len(posted_posts)
    }
    
    return render_template('analytics.html', analytics=analytics_data)

@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    form = BusinessProfileForm()
    profile = current_user.profile
    
    if form.validate_on_submit():
        profile.brand_name = form.brand_name.data
        profile.brand_voice = form.brand_voice.data
        profile.target_audience = form.target_audience.data
        profile.ai_instructions = form.ai_instructions.data
        profile.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('main.settings'))
    
    # Pre-populate form
    form.brand_name.data = profile.brand_name
    form.brand_voice.data = profile.brand_voice
    form.target_audience.data = profile.target_audience
    form.ai_instructions.data = profile.ai_instructions
    
    # Get connected social accounts
    social_accounts = SocialAccount.query.filter_by(user_id=current_user.id).all()
    
    return render_template('settings.html', form=form, social_accounts=social_accounts)

# API Routes
@main_bp.route('/api/posts/<int:post_id>/approve', methods=['POST'])
@login_required
def approve_post(post_id):
    """Approve a pending post"""
    if not current_user.subscription_active:
        return jsonify({'error': 'Subscription required'}), 403
    
    post = Post.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if post.status != PostStatus.PENDING:
        return jsonify({'error': 'Post is not pending approval'}), 400
    
    post.status = PostStatus.APPROVED
    db.session.commit()
    
    # Schedule approved posts
    schedule_approved_posts.delay(current_user.id)
    
    return jsonify({
        'success': True,
        'message': 'Post approved successfully'
    })

@main_bp.route('/api/posts/<int:post_id>/reject', methods=['POST'])
@login_required
def reject_post(post_id):
    """Reject a pending post with feedback"""
    if not current_user.subscription_active:
        return jsonify({'error': 'Subscription required'}), 403
    
    post = Post.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    if post.status != PostStatus.PENDING:
        return jsonify({'error': 'Post is not pending approval'}), 400
    
    data = request.get_json()
    rejection_note = data.get('note', '').strip()
    
    if not rejection_note:
        return jsonify({'error': 'Rejection note is required'}), 400
    
    post.status = PostStatus.REJECTED
    post.rejection_note = rejection_note
    db.session.commit()
    
    # Queue regeneration
    regenerate_post.delay(post_id, rejection_note)
    
    return jsonify({
        'success': True,
        'message': 'Post rejected and queued for regeneration'
    })

@main_bp.route('/api/stats')
@login_required
def api_stats():
    """Get dashboard stats"""
    total_posts = Post.query.filter_by(user_id=current_user.id, status=PostStatus.POSTED).count()
    scheduled = Post.query.filter_by(user_id=current_user.id, status=PostStatus.SCHEDULED).count()
    pending = Post.query.filter_by(user_id=current_user.id, status=PostStatus.PENDING).count()
    total_generated = Post.query.filter_by(user_id=current_user.id).count()
    
    total_reach = db.session.query(db.func.sum(Post.reach))\
        .filter_by(user_id=current_user.id).scalar() or 0
    
    return jsonify({
        'total_posts': total_posts,
        'total_reach': total_reach,
        'scheduled': scheduled,
        'total_generated': total_generated,
        'pending': pending
    })
    
class MediaUploadForm(FlaskForm):
    files = MultipleFileField('Files', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'mp4', 'mov'], 'Images and videos only!')
    ])



@main_bp.route('/media_library')
@login_required
def media_library():
    """Display user's media library with pagination"""
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    page = request.args.get('page', 1, type=int)
    
    # Get all posts for the user (these contain the media)
    media = Post.query.filter_by(user_id=current_user.id)\
        .order_by(Post.created_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    
    return render_template('media_library.html', media=media)

@main_bp.route('/queue')
@login_required
def queue():
    """Display processing queue and scheduled posts"""
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    # Get processing posts (pending AI generation)
    processing_posts = Post.query.filter_by(
        user_id=current_user.id,
        status=PostStatus.PENDING
    ).order_by(Post.created_at.desc()).all()
    
    # Get scheduled posts (approved and scheduled for publishing)
    scheduled_posts = Post.query.filter_by(
        user_id=current_user.id,
        status=PostStatus.SCHEDULED
    ).order_by(Post.scheduled_for.asc()).all()
    
    return render_template('queue.html', 
                         processing_posts=processing_posts,
                         scheduled_posts=scheduled_posts)

@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Handle media file uploads"""
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    from forms import FileUploadForm
    from werkzeug.utils import secure_filename
    import os
    
    form = FileUploadForm()
    
    if form.validate_on_submit():
        files = request.files.getlist('files')
        uploaded_count = 0
        
        for file in files:
            if file and allowed_file(file.filename):
                try:
                    # Secure the filename
                    filename = secure_filename(file.filename)
                    
                    # Determine media type
                    file_ext = filename.rsplit('.', 1)[1].lower()
                    is_video = file_ext in ['mp4', 'mov', 'avi']
                    media_type = MediaType.VIDEO if is_video else MediaType.IMAGE
                    
                    # Create post record (for AI generation)
                    post = Post(
                        user_id=current_user.id,
                        media_type=media_type,
                        status=PostStatus.PENDING,
                        prompt_used="Generate engaging social media content",
                        generation_metadata={
                            'original_filename': filename,
                            'upload_method': 'manual'
                        }
                    )
                    db.session.add(post)
                    db.session.flush()  # Get post ID
                    
                    # Upload to S3
                    from services.storage_service import storage_service
                    media_url = storage_service.upload_generated_media(
                        file,
                        media_type.value,
                        current_user.id,
                        post.id
                    )
                    
                    if media_url:
                        post.media_url = media_url
                        
                        # Generate thumbnail for videos
                        if media_type == MediaType.VIDEO:
                            thumbnail_url = storage_service.generate_thumbnail(
                                media_url, current_user.id, post.id
                            )
                            if thumbnail_url:
                                post.thumbnail_url = thumbnail_url
                        
                        uploaded_count += 1
                        
                        # Queue AI caption generation
                        from tasks.generation import generate_single_post
                        
                        # Find or create a default campaign
                        campaign = Campaign.query.filter_by(
                            user_id=current_user.id,
                            is_active=True
                        ).first()
                        
                        if not campaign:
                            campaign = Campaign(
                                user_id=current_user.id,
                                name="Manual Uploads",
                                description="Posts from manually uploaded media",
                                prompt_template="Create engaging social media content for this image/video",
                                posts_per_week=7
                            )
                            db.session.add(campaign)
                            db.session.flush()
                        
                        # Trigger AI generation for caption
                        generate_single_post.delay(
                            current_user.id,
                            campaign.id,
                            0  # No weekly generation ID for manual uploads
                        )
                        
                except Exception as e:
                    current_app.logger.error(f'Error uploading file {filename}: {str(e)}')
                    flash(f'Error uploading {filename}', 'error')
        
        db.session.commit()
        
        if uploaded_count > 0:
            flash(f'Successfully uploaded {uploaded_count} file(s). AI is generating captions...', 'success')
            return redirect(url_for('main.queue'))
        else:
            flash('No valid files were uploaded', 'warning')
    
    return render_template('upload.html', form=form)

# Add helper function if not already present
def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Add campaign toggle API endpoint
@main_bp.route('/api/campaigns/<int:campaign_id>/toggle', methods=['POST'])
@login_required
def toggle_campaign(campaign_id):
    """Toggle campaign active status"""
    campaign = Campaign.query.filter_by(
        id=campaign_id, 
        user_id=current_user.id
    ).first()
    
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    campaign.is_active = not campaign.is_active
    db.session.commit()
    
    return jsonify({
        'success': True,
        'is_active': campaign.is_active,
        'message': f'Campaign {"activated" if campaign.is_active else "deactivated"}'
    })

# Add campaign edit route
@main_bp.route('/campaigns/<int:campaign_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_campaign(campaign_id):
    """Edit existing campaign"""
    if not current_user.subscription_active:
        return redirect(url_for('auth.subscription'))
    
    campaign = Campaign.query.filter_by(
        id=campaign_id,
        user_id=current_user.id
    ).first_or_404()
    
    form = CampaignForm(obj=campaign)
    
    if form.validate_on_submit():
        campaign.name = form.name.data
        campaign.description = form.description.data
        campaign.prompt_template = form.prompt_template.data
        campaign.posts_per_week = form.posts_per_week.data
        campaign.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Campaign updated successfully!', 'success')
        return redirect(url_for('main.campaigns'))
    
    return render_template('new_campaign.html', form=form, editing=True)
