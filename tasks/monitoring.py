# =============================================================================
# tasks/monitoring.py - Webhook and system health monitoring tasks
# =============================================================================

from tasks.celery_app import current_app as celery
from models import db, WebhookEvent, User, Post, Notification
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@celery.task
def check_webhook_health():
    """Check webhook processing health and send alerts if needed"""
    try:
        from monitoring.webhook_monitor import WebhookMonitor
        monitor = WebhookMonitor()
        stats = monitor.check_webhook_health(hours_back=24)
        
        logger.info(f'Webhook health check completed: {stats}')
        return stats
        
    except Exception as e:
        logger.error(f'Error in webhook health check: {str(e)}')
        return {'error': str(e)}

@celery.task  
def system_health_check():
    """Comprehensive system health check"""
    try:
        health_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'database_healthy': check_database_health(),
            'celery_healthy': check_celery_health(),
            'webhook_healthy': check_webhook_recent_activity(),
            'user_activity': get_user_activity_stats()
        }
        
        # Send alert if any critical issues
        issues = []
        if not health_data['database_healthy']['status']:
            issues.append('Database connectivity issues')
        if not health_data['celery_healthy']['status']:
            issues.append('Celery worker issues')
            
        if issues:
            from tasks.email_tasks import send_admin_alert
            send_admin_alert.delay(
                'System Health Alert',
                f'Issues detected: {", ".join(issues)}',
                'high'
            )
        
        return health_data
        
    except Exception as e:
        logger.error(f'System health check failed: {str(e)}')
        return {'error': str(e)}

def check_database_health():
    """Check database connectivity and performance"""
    try:
        # Simple query to check connectivity
        user_count = User.query.count()
        return {
            'status': True,
            'user_count': user_count,
            'last_check': datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            'status': False,
            'error': str(e)
        }

def check_celery_health():
    """Check Celery worker status"""
    try:
        from celery_app import celery_health_check
        return celery_health_check()
    except Exception as e:
        return {
            'status': False,
            'error': str(e)
        }

def check_webhook_recent_activity():
    """Check if webhooks have been processed recently"""
    try:
        recent_events = WebhookEvent.query.filter(
            WebhookEvent.processed_at >= datetime.utcnow() - timedelta(hours=24)
        ).count()
        
        return {
            'status': True,
            'recent_events': recent_events
        }
    except Exception as e:
        return {
            'status': False,
            'error': str(e)
        }

def get_user_activity_stats():
    """Get basic user activity statistics"""
    try:
        total_users = User.query.count()
        active_subscribers = User.query.filter_by(subscription_active=True).count()
        recent_posts = Post.query.filter(
            Post.created_at >= datetime.utcnow() - timedelta(days=7)
        ).count()
        
        return {
            'total_users': total_users,
            'active_subscribers': active_subscribers,
            'posts_last_week': recent_posts
        }
    except Exception as e:
        return {'error': str(e)}

# =============================================================================
# tasks/maintenance.py - System cleanup and maintenance tasks  
# =============================================================================

@celery.task
def cleanup_old_webhook_events():
    """Clean up webhook events older than 30 days"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        deleted_count = WebhookEvent.query.filter(
            WebhookEvent.processed_at < cutoff_date
        ).delete()
        
        db.session.commit()
        
        logger.info(f'Cleaned up {deleted_count} old webhook events')
        return {'deleted_count': deleted_count}
        
    except Exception as e:
        logger.error(f'Error cleaning up webhook events: {str(e)}')
        db.session.rollback()
        return {'error': str(e)}

@celery.task
def cleanup_old_notifications():
    """Clean up read notifications older than 90 days"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        deleted_count = Notification.query.filter(
            Notification.created_at < cutoff_date,
            Notification.is_read == True
        ).delete()
        
        db.session.commit()
        
        logger.info(f'Cleaned up {deleted_count} old notifications')
        return {'deleted_count': deleted_count}
        
    except Exception as e:
        logger.error(f'Error cleaning up notifications: {str(e)}')
        db.session.rollback()
        return {'error': str(e)}

@celery.task
def cleanup_failed_posts():
    """Clean up failed posts older than 7 days"""
    try:
        from models import PostStatus
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        deleted_count = Post.query.filter(
            Post.created_at < cutoff_date,
            Post.status == PostStatus.FAILED
        ).delete()
        
        db.session.commit()
        
        logger.info(f'Cleaned up {deleted_count} failed posts')
        return {'deleted_count': deleted_count}
        
    except Exception as e:
        logger.error(f'Error cleaning up failed posts: {str(e)}')
        db.session.rollback()
        return {'error': str(e)}

# =============================================================================
# tasks/subscription.py - Subscription management tasks
# =============================================================================

import stripe
from flask import current_app
from models import SubscriptionTier

@celery.task
def sync_subscription_statuses():
    """Sync subscription statuses with Stripe (reconciliation)"""
    try:
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        
        # Get users with active subscriptions
        active_users = User.query.filter_by(subscription_active=True).all()
        
        synced_count = 0
        issues_found = 0
        
        for user in active_users:
            if not user.stripe_customer_id:
                continue
                
            try:
                # Get customer's subscriptions from Stripe
                subscriptions = stripe.Subscription.list(
                    customer=user.stripe_customer_id,
                    limit=10
                )
                
                active_stripe_subs = [
                    sub for sub in subscriptions.data 
                    if sub.status in ['active', 'trialing']
                ]
                
                if not active_stripe_subs and user.subscription_active:
                    # User shows active in our DB but not in Stripe
                    logger.warning(f'User {user.id} shows active but no active Stripe subscription')
                    user.subscription_active = False
                    user.subscription_status = 'sync_deactivated'
                    issues_found += 1
                
                elif active_stripe_subs:
                    # Update subscription details from Stripe
                    stripe_sub = active_stripe_subs[0]  # Take the first active subscription
                    
                    # Determine tier from price ID
                    price_id = stripe_sub.items.data[0].price.id
                    stripe_tier = determine_tier_from_price_id(price_id)
                    
                    if user.subscription_tier != stripe_tier:
                        user.subscription_tier = stripe_tier
                        issues_found += 1
                    
                    user.subscription_status = stripe_sub.status
                    user.stripe_subscription_id = stripe_sub.id
                
                synced_count += 1
                
            except stripe.error.StripeError as e:
                logger.error(f'Stripe error syncing user {user.id}: {str(e)}')
                continue
        
        db.session.commit()
        
        result = {
            'synced_users': synced_count,
            'issues_found': issues_found,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Send alert if many issues found
        if issues_found > 0:
            from tasks.email_tasks import send_admin_alert
            send_admin_alert.delay(
                'Subscription Sync Issues Found',
                f'Found {issues_found} subscription sync issues during reconciliation',
                'medium'
            )
        
        logger.info(f'Subscription sync completed: {result}')
        return result
        
    except Exception as e:
        logger.error(f'Error in subscription sync: {str(e)}')
        db.session.rollback()
        return {'error': str(e)}

@celery.task
def send_trial_ending_reminders():
    """Send reminders to users whose trials are ending soon"""
    try:
        # Find users with trials ending in 1-3 days
        upcoming_end = datetime.utcnow() + timedelta(days=3)
        soon_end = datetime.utcnow() + timedelta(days=1)
        
        trial_ending_users = User.query.filter(
            User.trial_ends_at.between(soon_end, upcoming_end),
            User.subscription_active == False
        ).all()
        
        reminders_sent = 0
        
        for user in trial_ending_users:
            days_remaining = (user.trial_ends_at - datetime.utcnow()).days
            
            # Check if we already sent a reminder for this timeframe
            recent_reminder = Notification.query.filter(
                Notification.user_id == user.id,
                Notification.type == 'trial_ending',
                Notification.created_at >= datetime.utcnow() - timedelta(days=1)
            ).first()
            
            if not recent_reminder:
                from tasks.email_tasks import send_trial_ending_email
                send_trial_ending_email.delay(user.id, days_remaining)
                reminders_sent += 1
        
        logger.info(f'Sent {reminders_sent} trial ending reminders')
        return {'reminders_sent': reminders_sent}
        
    except Exception as e:
        logger.error(f'Error sending trial reminders: {str(e)}')
        return {'error': str(e)}

@celery.task
def process_failed_payment_retries():
    """Process and monitor failed payment retries"""
    try:
        # Find users with recent payment failures
        failed_payment_users = User.query.filter(
            User.payment_failed == True,
            User.last_payment_failure >= datetime.utcnow() - timedelta(days=7)
        ).all()
        
        processed_count = 0
        
        for user in failed_payment_users:
            if not user.stripe_customer_id:
                continue
            
            try:
                # Check latest invoices for this customer
                invoices = stripe.Invoice.list(
                    customer=user.stripe_customer_id,
                    limit=5
                )
                
                # Check if any recent invoice was paid successfully
                for invoice in invoices.data:
                    if (invoice.status == 'paid' and 
                        invoice.created > user.last_payment_failure.timestamp()):
                        
                        # Payment succeeded, update user status
                        user.payment_failed = False
                        user.payment_retry_count = 0
                        user.subscription_active = True
                        processed_count += 1
                        break
                
            except stripe.error.StripeError as e:
                logger.error(f'Error checking payment status for user {user.id}: {str(e)}')
                continue
        
        db.session.commit()
        
        logger.info(f'Processed {processed_count} failed payment recoveries')
        return {'recovered_payments': processed_count}
        
    except Exception as e:
        logger.error(f'Error processing payment retries: {str(e)}')
        db.session.rollback()
        return {'error': str(e)}

def determine_tier_from_price_id(price_id):
    """Helper function to determine tier from Stripe price ID"""
    try:
        tiers = current_app.config['SUBSCRIPTION_TIERS']
        
        for tier_name, tier_config in tiers.items():
            if tier_config.get('price_id') == price_id:
                return SubscriptionTier(tier_name.upper())
        
        return SubscriptionTier.BASIC
    except Exception:
        return SubscriptionTier.BASIC

# =============================================================================
# tasks/analytics.py - Analytics and reporting tasks  
# =============================================================================

@celery.task
def generate_usage_reports():
    """Generate daily usage reports for monitoring"""
    try:
        from models import PostStatus
        
        # Get yesterday's stats
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_of_day = datetime.combine(yesterday, datetime.min.time())
        end_of_day = datetime.combine(yesterday, datetime.max.time())
        
        # User activity stats
        new_users = User.query.filter(
            User.created_at.between(start_of_day, end_of_day)
        ).count()
        
        new_subscribers = User.query.filter(
            User.created_at.between(start_of_day, end_of_day),
            User.subscription_active == True
        ).count()
        
        # Post generation stats
        posts_generated = Post.query.filter(
            Post.created_at.between(start_of_day, end_of_day)
        ).count()
        
        posts_published = Post.query.filter(
            Post.posted_at.between(start_of_day, end_of_day),
            Post.status == PostStatus.POSTED
        ).count()
        
        # Calculate conversion metrics
        total_users = User.query.count()
        total_subscribers = User.query.filter_by(subscription_active=True).count()
        conversion_rate = (total_subscribers / total_users * 100) if total_users > 0 else 0
        
        report = {
            'date': yesterday.isoformat(),
            'new_users': new_users,
            'new_subscribers': new_subscribers,
            'posts_generated': posts_generated,
            'posts_published': posts_published,
            'total_users': total_users,
            'total_subscribers': total_subscribers,
            'conversion_rate': round(conversion_rate, 2)
        }
        
        # Store report (you might want to create a DailyReport model)
        logger.info(f'Daily usage report: {report}')
        
        # Send to admins if significant changes
        if new_subscribers > 10:  # Configurable threshold
            from tasks.email_tasks import send_admin_alert
            send_admin_alert.delay(
                'High Conversion Day!',
                f'Great day yesterday: {new_subscribers} new subscribers, {new_users} new users',
                'info'
            )
        
        return report
        
    except Exception as e:
        logger.error(f'Error generating usage report: {str(e)}')
        return {'error': str(e)}

@celery.task 
def update_user_engagement_scores():
    """Update user engagement scores based on recent activity"""
    try:
        # This is a placeholder for more sophisticated engagement tracking
        # You could track things like:
        # - How often users approve vs reject posts
        # - How long they spend in the app
        # - How many campaigns they create
        # - Social media posting frequency
        
        updated_count = 0
        
        users = User.query.filter_by(subscription_active=True).all()
        
        for user in users:
            # Simple engagement score based on recent activity
            recent_posts = Post.query.filter(
                Post.user_id == user.id,
                Post.created_at >= datetime.utcnow() - timedelta(days=30)
            ).count()
            
            recent_approvals = Post.query.filter(
                Post.user_id == user.id,
                Post.status == PostStatus.APPROVED,
                Post.updated_at >= datetime.utcnow() - timedelta(days=30)
            ).count()
            
            # Calculate engagement score (0-100)
            engagement_score = min(100, (recent_approvals * 10) + (recent_posts * 2))
            
            # You would store this in a UserEngagement model or user field
            # user.engagement_score = engagement_score
            updated_count += 1
        
        # db.session.commit()
        
        logger.info(f'Updated engagement scores for {updated_count} users')
        return {'updated_users': updated_count}
        
    except Exception as e:
        logger.error(f'Error updating engagement scores: {str(e)}')
        return {'error': str(e)}
