from celery import current_app
from models import db, User, Post, Campaign, WeeklyGeneration, BusinessProfile, PostStatus, MediaType
from services.ai_service import ai_service
from services.storage_service import storage_service
from datetime import datetime, timedelta
import logging
import base64

logger = logging.getLogger(__name__)

@current_app.task
def generate_weekly_posts():
    """Generate weekly posts for all active users"""
    
    today = datetime.utcnow().date()
    current_weekday = today.weekday()  # 0=Monday, 6=Sunday
    
    # Find users whose generation day is today
    users = User.query.filter(
        User.subscription_active == True,
        User.weekly_generation_day == current_weekday
    ).all()
    
    for user in users:
        try:
            # Check if we already generated for this week
            week_start = today - timedelta(days=current_weekday)
            existing_generation = WeeklyGeneration.query.filter(
                WeeklyGeneration.user_id == user.id,
                WeeklyGeneration.week_start_date == week_start
            ).first()
            
            if existing_generation and existing_generation.generation_completed:
                continue
            
            # Check if user can generate more posts this month
            if not user.can_generate_posts():
                logger.warning(f"User {user.id} has reached monthly post limit")
                continue
            
            # Generate posts for user
            generate_user_weekly_posts.delay(user.id, week_start)
            
        except Exception as e:
            logger.error(f"Error initiating weekly generation for user {user.id}: {str(e)}")

@current_app.task
def generate_user_weekly_posts(user_id: int, week_start_date):
    """Generate weekly posts for a specific user"""
    
    try:
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return
        
        # Get or create weekly generation record
        weekly_gen = WeeklyGeneration.query.filter(
            WeeklyGeneration.user_id == user_id,
            WeeklyGeneration.week_start_date == week_start_date
        ).first()
        
        if not weekly_gen:
            weekly_gen = WeeklyGeneration(
                user_id=user_id,
                week_start_date=week_start_date
            )
            db.session.add(weekly_gen)
            db.session.commit()
        
        # Get user's business profile
        profile = BusinessProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            logger.error(f"No business profile found for user {user_id}")
            return
        
        # Get active campaigns - this is where campaigns drive content generation
        # Get active campaigns
        campaigns = Campaign.query.filter(
            Campaign.user_id == user_id,
            Campaign.is_active == True
        ).all()
        
        if not campaigns:
            # Create default campaign if none exist - every user needs at least one campaign
            # Create default campaign if none exist
            default_campaign = Campaign(
                user_id=user_id,
                name="Default Weekly Posts",
                description="Automatically generated weekly content",
                # This template uses brand profile variables to create personalized content
                prompt_template="Create engaging social media content for {brand_name} targeting {target_audience}",
                posts_per_week=7
            )
            db.session.add(default_campaign)
            db.session.commit()
            campaigns = [default_campaign]
        
        # Calculate total posts based on all active campaigns
        total_posts_to_generate = sum(c.posts_per_week for c in campaigns)
        posts_generated = 0
        
        # Generate posts for each campaign separately
        # Generate posts for each campaign
        for campaign in campaigns:
            # Each campaign generates its specified number of posts per week
            for i in range(campaign.posts_per_week):
                try:
                    # Generate individual post
                    post_result = generate_single_post.delay(
                        user_id, 
                        campaign.id, 
                        weekly_gen.id
                    )
                    
                    if post_result:
                        posts_generated += 1
                        
                except Exception as e:
                    logger.error(f"Error generating post {i+1} for campaign {campaign.id}: {str(e)}")
        
        # Update weekly generation record
        weekly_gen.posts_generated = posts_generated
        weekly_gen.generation_completed = True
        db.session.commit()
        
        # Send notification email
        send_weekly_posts_email.delay(user_id, weekly_gen.id)
        
        logger.info(f"Generated {posts_generated} posts for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in generate_user_weekly_posts: {str(e)}")

@current_app.task
def generate_single_post(user_id: int, campaign_id: int, weekly_gen_id: int):
    """Generate a single post"""
    
    try:
        user = User.query.get(user_id)
        # Get the specific campaign that's driving this post generation
        campaign = Campaign.query.get(campaign_id)
        profile = BusinessProfile.query.filter_by(user_id=user_id).first()
        
        if not all([user, campaign, profile]):
            logger.error(f"Missing data for post generation: user={user}, campaign={campaign}, profile={profile}")
            return False
        
        # Build brand profile for AI - this combines user profile with campaign context
        brand_profile = {
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
        
        # Use the campaign's prompt template and format it with brand profile data
        # This is where the campaign concept becomes actual content
        content_result = ai_service.generate_post_content(
            campaign.prompt_template.format(**brand_profile),
            brand_profile
        )
        
        if not content_result['success']:
            logger.error(f"Failed to generate content: {content_result.get('error')}")
            return False
        
        # Determine media type (for now, default to image)
        media_type = MediaType.IMAGE
        
        # Generate media
        if media_type == MediaType.IMAGE:
            media_result = ai_service.generate_image(
                content_result['image_prompt'],
                brand_profile
            )
        else:
            media_result = ai_service.generate_video(
                content_result['image_prompt'],
                brand_profile
            )
        
        if not media_result['success']:
            logger.error(f"Failed to generate media: {media_result.get('error')}")
            return False
        
        # Create post record linked to the campaign
        post = Post(
            user_id=user_id,
            # This links the post back to the campaign that generated it
            campaign_id=campaign_id,
            media_type=media_type,
            caption=content_result['caption'],
            hashtags=content_result['hashtags'],
            # Store the actual prompt used (formatted campaign template)
            prompt_used=campaign.prompt_template,
            generation_metadata={
                'content_generation': content_result.get('metadata', {}),
                'media_generation': media_result.get('metadata', {}),
                'weekly_generation_id': weekly_gen_id
            },
            status=PostStatus.PENDING
        )
        
        db.session.add(post)
        db.session.flush()  # Get post ID
        
        # Upload media to S3
        if 'image_file' in media_result:
            media_url = storage_service.upload_generated_media(
                media_result['image_file'],
                media_type.value,
                user_id,
                post.id
            )
        elif 'video_file' in media_result:
            media_url = storage_service.upload_generated_media(
                media_result['video_file'],
                media_type.value,
                user_id,
                post.id
            )
        else:
            logger.error("No media file found in generation result")
            return False
            
        if media_url:
            post.media_url = media_url
            
            # Generate thumbnail for videos
            if media_type == MediaType.VIDEO:
                thumbnail_url = storage_service.generate_thumbnail(
                    media_url, user_id, post.id
                )
                if thumbnail_url:
                    post.thumbnail_url = thumbnail_url
        
        db.session.commit()
        
        logger.info(f"Successfully generated post {post.id} for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error in generate_single_post: {str(e)}")
        return False

@current_app.task
def regenerate_post(post_id: int, rejection_note: str):
    """Regenerate a rejected post with user feedback"""
    
    try:
        post = Post.query.get(post_id)
        if not post:
            logger.error(f"Post {post_id} not found")
            return False
        
        user = User.query.get(post.user_id)
        profile = BusinessProfile.query.filter_by(user_id=post.user_id).first()
        
        if not all([user, profile]):
            logger.error(f"Missing data for post regeneration")
            return False
        
        # Build brand profile
        brand_profile = {
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
        
        # Generate new content with rejection feedback
        content_result = ai_service.generate_post_content(
            post.prompt_used,
            brand_profile,
            rejection_note
        )
        
        if not content_result['success']:
            logger.error(f"Failed to regenerate content: {content_result.get('error')}")
            return False
        
        # Generate new media
        if post.media_type == MediaType.IMAGE:
            media_result = ai_service.generate_image(
                content_result['image_prompt'],
                brand_profile
            )
        else:
            media_result = ai_service.generate_video(
                content_result['image_prompt'],
                brand_profile
            )
        
        if not media_result['success']:
            logger.error(f"Failed to regenerate media: {media_result.get('error')}")
            return False
        
        # Delete old media if it exists
        if post.media_url:
            storage_service.delete_media(post.media_url)
        if post.thumbnail_url:
            storage_service.delete_media(post.thumbnail_url)
        
        # Upload new media
        if 'image_file' in media_result:
            media_url = storage_service.upload_generated_media(
                media_result['image_file'],
                post.media_type.value,
                post.user_id,
                post.id
            )
        elif 'video_file' in media_result:
            media_url = storage_service.upload_generated_media(
                media_result['video_file'],
                post.media_type.value,
                post.user_id,
                post.id
            )
        else:
            logger.error("No media file found in regeneration result")
            return False
            
        if media_url:
            post.media_url = media_url
            
            # Generate thumbnail for videos
            if post.media_type == MediaType.VIDEO:
                thumbnail_url = storage_service.generate_thumbnail(
                    media_url, post.user_id, post.id
                )
                if thumbnail_url:
                    post.thumbnail_url = thumbnail_url
        
        # Update post
        post.caption = content_result['caption']
        post.hashtags = content_result['hashtags']
        post.rejection_note = rejection_note
        post.regeneration_count += 1
        post.status = PostStatus.PENDING
        post.updated_at = datetime.utcnow()
        
        # Update generation metadata
        if not post.generation_metadata:
            post.generation_metadata = {}
        post.generation_metadata['regeneration'] = {
            'rejection_note': rejection_note,
            'regeneration_count': post.regeneration_count,
            'regenerated_at': datetime.utcnow().isoformat()
        }
        
        db.session.commit()
        
        logger.info(f"Successfully regenerated post {post_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error in regenerate_post: {str(e)}")
        return False

@current_app.task
def send_weekly_posts_email(user_id: int, weekly_gen_id: int):
    """Send email notification about weekly posts"""
    
    try:
        from flask_mail import Message
        from app import mail
        
        user = User.query.get(user_id)
        weekly_gen = WeeklyGeneration.query.get(weekly_gen_id)
        
        if not all([user, weekly_gen]):
            logger.error(f"Missing data for email notification")
            return False
        
        # Get pending posts for this week
        posts = Post.query.filter(
            Post.user_id == user_id,
            Post.status == PostStatus.PENDING,
            Post.created_at >= weekly_gen.created_at
        ).all()
        
        msg = Message(
            'Your Weekly Posts Are Ready! 🎉',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[user.email]
        )
        
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #6366f1;">Your Weekly Posts Are Ready!</h2>
            <p>Hi there!</p>
            <p>We've generated <strong>{len(posts)} new posts</strong> for your social media accounts this week.</p>
            
            <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">What's Next?</h3>
                <ol>
                    <li>Review your posts in the dashboard</li>
                    <li>Approve the ones you love ✅</li>
                    <li>Reject any that need changes (with feedback) ❌</li>
                    <li>We'll automatically schedule approved posts</li>
                </ol>
            </div>
            
            <a href="{request.url_root}dashboard" style="background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 20px 0;">
                Review Your Posts
            </a>
            
            <p>Best regards,<br>The SocialMagic Team</p>
        </div>
        """
        
        mail.send(msg)
        
        # Update weekly generation record
        weekly_gen.email_sent = True
        db.session.commit()
        
        logger.info(f"Sent weekly posts email to user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending weekly posts email: {str(e)}")
        return False