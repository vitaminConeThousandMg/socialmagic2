from flask import Blueprint, request, jsonify, current_app
from models import db, ImageReference, Notification, User
from datetime import datetime
import hmac
import hashlib

webhooks_bp = Blueprint('webhooks', __name__)

@webhooks_bp.route('/n8n/post-status', methods=['POST'])
def n8n_post_status():
    """Webhook to receive post status updates from n8n"""
    
    # Verify webhook signature
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if webhook_secret != current_app.config.get('N8N_WEBHOOK_SECRET'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Find the image reference
        image_ref = ImageReference.query.filter_by(
            n8n_media_id=data.get('media_id')
        ).first()
        
        if not image_ref:
            return jsonify({'error': 'Media reference not found'}), 404
        
        # Update image reference with post data
        image_ref.status = data.get('status', 'posted')
        image_ref.posted = True
        image_ref.posted_at = datetime.fromisoformat(data.get('posted_at', datetime.utcnow().isoformat()))
        image_ref.instagram_post_id = data.get('instagram_post_id')
        image_ref.instagram_url = data.get('instagram_url')
        image_ref.facebook_post_id = data.get('facebook_post_id')
        image_ref.caption = data.get('caption')
        image_ref.hashtags = data.get('hashtags', [])
        
        # Create notification
        notification = Notification(
            user_id=image_ref.user_id,
            type='post_published',
            title='Post Published!',
            message=f'Your post "{(data.get("caption") or "")[:50]}..." has been published successfully!',
            data={
                'instagram_url': data.get('instagram_url'),
                'media_id': image_ref.id
            }
        )
        
        db.session.add(notification)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Status updated successfully'})
        
    except Exception as e:
        current_app.logger.error(f'Webhook error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@webhooks_bp.route('/n8n/processing-update', methods=['POST'])
def n8n_processing_update():
    """Webhook to receive processing status updates from n8n"""
    
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if webhook_secret != current_app.config.get('N8N_WEBHOOK_SECRET'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        
        image_ref = ImageReference.query.filter_by(
            n8n_media_id=data.get('media_id')
        ).first()
        
        if not image_ref:
            return jsonify({'error': 'Media reference not found'}), 404
        
        # Update processing status
        status = data.get('status')  # processing, scheduled, failed
        image_ref.status = status
        
        if status == 'failed':
            # Create error notification
            notification = Notification(
                user_id=image_ref.user_id,
                type='processing_failed',
                title='Processing Failed',
                message=f'Failed to process {image_ref.original_filename}: {data.get("error", "Unknown error")}',
                data={'media_id': image_ref.id, 'error': data.get('error')}
            )
            db.session.add(notification)
        
        elif status == 'scheduled':
            # Update with AI-generated content
            image_ref.caption = data.get('generated_caption')
            image_ref.hashtags = data.get('generated_hashtags', [])
            
            # Create scheduled notification
            notification = Notification(
                user_id=image_ref.user_id,
                type='post_scheduled',
                title='Post Scheduled',
                message=f'Your post has been scheduled and will be published soon!',
                data={'media_id': image_ref.id}
            )
            db.session.add(notification)
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        current_app.logger.error(f'Processing webhook error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@webhooks_bp.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        import stripe
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config.get('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle subscription events
    if event['type'] == 'customer.subscription.created':
        subscription = event['data']['object']
        customer_id = subscription['customer']
        
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.subscription_active = True
            user.subscription_tier = 'premium'
            db.session.commit()
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription['customer']
        
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.subscription_active = False
            user.subscription_tier = 'basic'
            db.session.commit()
    
    return jsonify({'success': True})