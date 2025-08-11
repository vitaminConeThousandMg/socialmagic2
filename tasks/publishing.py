from celery import current_app
from models import db, Post, SocialAccount, PostStatus
from services.social_service import instagram_service, facebook_service
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@current_app.task
def publish_scheduled_posts():
    """Publish posts that are scheduled for now"""
    
    try:
        # Find posts scheduled for publishing (within the last 15 minutes)
        now = datetime.utcnow()
        cutoff_time = now - timedelta(minutes=15)
        
        posts_to_publish = Post.query.filter(
            Post.status == PostStatus.SCHEDULED,
            Post.scheduled_for <= now,
            Post.scheduled_for >= cutoff_time
        ).all()
        
        for post in posts_to_publish:
            try:
                publish_single_post.delay(post.id)
            except Exception as e:
                logger.error(f"Error queuing post {post.id} for publishing: {str(e)}")
        
        logger.info(f"Queued {len(posts_to_publish)} posts for publishing")
        
    except Exception as e:
        logger.error(f"Error in publish_scheduled_posts: {str(e)}")

@current_app.task
def publish_single_post(post_id: int):
    """Publish a single post to social media platforms"""
    
    try:
        post = Post.query.get(post_id)
        if not post:
            logger.error(f"Post {post_id} not found")
            return False
        
        if post.status != PostStatus.SCHEDULED:
            logger.warning(f"Post {post_id} is not scheduled for publishing (status: {post.status})")
            return False
        
        # Get user's social accounts
        instagram_account = SocialAccount.query.filter(
            SocialAccount.user_id == post.user_id,
            SocialAccount.platform == 'instagram',
            SocialAccount.is_connected == True
        ).first()
        
        facebook_account = SocialAccount.query.filter(
            SocialAccount.user_id == post.user_id,
            SocialAccount.platform == 'facebook',
            SocialAccount.is_connected == True
        ).first()
        
        # Social accounts are optional - simulate posting if not connected
        if not instagram_account:
            logger.info(f"No Instagram account connected for user {post.user_id} - simulating post")
            post.status = PostStatus.POSTED
            post.posted_at = datetime.utcnow()
            db.session.commit()
            return True
        
        # Prepare caption with hashtags
        full_caption = post.caption
        if post.hashtags:
            hashtag_string = ' '.join(post.hashtags)
            full_caption = f"{post.caption}\n\n{hashtag_string}"
        
        # Publish to Instagram
        instagram_result = publish_to_instagram(
            instagram_account.access_token,
            post.media_url,
            full_caption
        )
        
        if instagram_result['success']:
            post.instagram_post_id = instagram_result['media_id']
            logger.info(f"Successfully published post {post_id} to Instagram")
            
            # Cross-post to Facebook if connected
            if facebook_account:
                facebook_result = publish_to_facebook(
                    facebook_account.access_token,
                    facebook_account.account_id,
                    full_caption,
                    post.media_url
                )
                
                if facebook_result['success']:
                    post.facebook_post_id = facebook_result['post_id']
                    logger.info(f"Successfully cross-posted post {post_id} to Facebook")
                else:
                    logger.warning(f"Failed to cross-post to Facebook: {facebook_result.get('error')}")
            
            # Update post status
            post.status = PostStatus.POSTED
            post.posted_at = datetime.utcnow()
            
        else:
            logger.error(f"Failed to publish post {post_id} to Instagram: {instagram_result.get('error')}")
            post.status = PostStatus.FAILED
        
        db.session.commit()
        
        # Schedule analytics update
        if post.status == PostStatus.POSTED:
            update_post_analytics.delay(post_id, delay_hours=1)
        
        return post.status == PostStatus.POSTED
        
    except Exception as e:
        logger.error(f"Error in publish_single_post: {str(e)}")
        return False

def publish_to_instagram(access_token: str, media_url: str, caption: str) -> dict:
    """Publish content to Instagram"""
    
    try:
        # Create media container
        container_result = instagram_service.create_media_container(
            access_token, media_url, caption
        )
        
        if not container_result['success']:
            return container_result
        
        # Publish media
        publish_result = instagram_service.publish_media(
            access_token, container_result['container_id']
        )
        
        return publish_result
        
    except Exception as e:
        logger.error(f"Error publishing to Instagram: {str(e)}")
        return {'success': False, 'error': str(e)}

def publish_to_facebook(access_token: str, page_id: str, message: str, image_url: str) -> dict:
    """Publish content to Facebook"""
    
    try:
        result = facebook_service.post_to_page(
            access_token, page_id, message, image_url
        )
        return result
        
    except Exception as e:
        logger.error(f"Error publishing to Facebook: {str(e)}")
        return {'success': False, 'error': str(e)}

@current_app.task
def schedule_approved_posts(user_id: int):
    """Schedule all approved posts for a user"""
    
    try:
        # Get all approved posts that haven't been scheduled yet
        approved_posts = Post.query.filter(
            Post.user_id == user_id,
            Post.status == PostStatus.APPROVED,
            Post.scheduled_for.is_(None)
        ).order_by(Post.created_at).all()
        
        if not approved_posts:
            logger.info(f"No approved posts to schedule for user {user_id}")
            return
        
        # Schedule posts with optimal timing
        # For now, we'll schedule them daily at 10 AM starting tomorrow
        base_time = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
        base_time += timedelta(days=1)  # Start tomorrow
        
        for i, post in enumerate(approved_posts):
            # Schedule posts daily
            scheduled_time = base_time + timedelta(days=i)
            
            post.scheduled_for = scheduled_time
            post.status = PostStatus.SCHEDULED
        
        db.session.commit()
        
        logger.info(f"Scheduled {len(approved_posts)} posts for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error scheduling approved posts: {str(e)}")

@current_app.task
def update_post_analytics(post_id: int, delay_hours: int = 0):
    """Update analytics for a published post"""
    
    try:
        if delay_hours > 0:
            # Delay execution
            update_post_analytics.apply_async(
                args=[post_id, 0],
                countdown=delay_hours * 3600
            )
            return
        
        post = Post.query.get(post_id)
        if not post or post.status != PostStatus.POSTED:
            return
        
        # Get Instagram account
        instagram_account = SocialAccount.query.filter(
            SocialAccount.user_id == post.user_id,
            SocialAccount.platform == 'instagram',
            SocialAccount.is_connected == True
        ).first()
        
        if not instagram_account or not post.instagram_post_id:
            return
        
        # Get insights from Instagram
        insights_result = instagram_service.get_media_insights(
            instagram_account.access_token,
            post.instagram_post_id
        )
        
        if insights_result['success']:
            insights_data = insights_result['insights']['data']
            
            # Update post metrics
            for insight in insights_data:
                metric_name = insight['name']
                metric_value = insight['values'][0]['value']
                
                if metric_name == 'impressions':
                    post.impressions = metric_value
                elif metric_name == 'reach':
                    post.reach = metric_value
                elif metric_name == 'likes':
                    post.likes = metric_value
                elif metric_name == 'comments':
                    post.comments = metric_value
                elif metric_name == 'shares':
                    post.shares = metric_value
            
            # Calculate engagement rate
            if post.reach and post.reach > 0:
                total_engagement = (post.likes or 0) + (post.comments or 0) + (post.shares or 0)
                post.engagement_rate = (total_engagement / post.reach) * 100
            
            post.last_metrics_update = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Updated analytics for post {post_id}")
        
    except Exception as e:
        logger.error(f"Error updating post analytics: {str(e)}")