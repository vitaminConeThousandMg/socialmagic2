from flask import current_app
from flask_mail import Message
from models import db, BusinessProfile
import requests
import os

def send_verification_email(user):
    """Send email verification"""
    from app import mail
    
    msg = Message(
        'Verify Your SocialMagic Account',
        sender=current_app.config['MAIL_USERNAME'],
        recipients=[user.email]
    )
    
    verification_url = f"{request.url_root}verify/{user.verification_token}"
    
    msg.html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #6366f1;">Welcome to SocialMagic!</h2>
        <p>Thank you for signing up. Please click the link below to verify your email address:</p>
        <a href="{verification_url}" style="background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 20px 0;">
            Verify Email Address
        </a>
        <p>If you didn't create this account, you can safely ignore this email.</p>
        <p>Best regards,<br>The SocialMagic Team</p>
    </div>
    """
    
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send verification email: {str(e)}')
        return False

def send_to_n8n(user, file, media_id):
    """Send file to n8n webhook for processing"""
    try:
        profile = BusinessProfile.query.filter_by(user_id=user.id).first()
        
        # Prepare files and data for n8n
        files = {'file': (file.filename, file, file.content_type)}
        
        data = {
            'clientName': user.n8n_client_name,
            'mediaId': str(media_id),
            'metadata': {
                'user_id': user.id,
                'brand_name': profile.brand_name or '',
                'brand_voice': profile.brand_voice or '',
                'target_audience': profile.target_audience or '',
                'ai_instructions': profile.ai_instructions or '',
                'filename': file.filename
            }
        }
        
        response = requests.post(
            current_app.config['N8N_WEBHOOK_URL'],
            files=files,
            data=data,
            headers={
                'X-API-Key': current_app.config['N8N_API_KEY']
            },
            timeout=30
        )
        
        if response.ok:
            result = response.json()
            # Update the image reference with n8n media ID if provided
            from models import ImageReference
            image_ref = ImageReference.query.get(media_id)
            if image_ref and 'media_id' in result:
                image_ref.n8n_media_id = result['media_id']
                db.session.commit()
            return True
        else:
            current_app.logger.error(f'N8N webhook failed: {response.status_code} - {response.text}')
            return False
            
    except Exception as e:
        current_app.logger.error(f'Error sending to n8n: {str(e)}')
        return False

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"from flask import current_app, request
from flask_mail import Message
from models import db, BusinessProfile
import requests
import os

def send_verification_email(user):
    """Send email verification"""
    from app import app
    
    with app.app_context():
        mail = app.mail
        
        msg = Message(
            'Verify Your SocialMagic Account',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[user.email]
        )
        
        verification_url = f"{request.url_root}auth/verify/{user.verification_token}"
        
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #6366f1;">Welcome to SocialMagic!</h2>
            <p>Thank you for signing up. Please click the link below to verify your email address:</p>
            <a href="{verification_url}" style="background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin: 20px 0;">
                Verify Email Address
            </a>
            <p>If you didn't create this account, you can safely ignore this email.</p>
            <p>Best regards,<br>The SocialMagic Team</p>
        </div>
        """
        
        try:
            mail.send(msg)
            return True
        except Exception as e:
            current_app.logger.error(f'Failed to send verification email: {str(e)}')
            return False

def send_to_n8n(user, file, media_id):
    """Send file to n8n webhook for processing"""
    try:
        profile = BusinessProfile.query.filter_by(user_id=user.id).first()
        
        # Prepare files and data for n8n
        files = {'file': (file.filename, file, file.content_type)}
        
        data = {
            'clientName': getattr(user, 'n8n_client_name', f'user_{user.id}'),
            'mediaId': str(media_id),
            'metadata': {
                'user_id': user.id,
                'brand_name': profile.brand_name if profile else '',
                'brand_voice': profile.brand_voice if profile else '',
                'target_audience': profile.target_audience if profile else '',
                'ai_instructions': profile.ai_instructions if profile else '',
                'filename': file.filename
            }
        }
        
        # Only try to send to n8n if webhook URL is configured
        webhook_url = current_app.config.get('N8N_WEBHOOK_URL')
        api_key = current_app.config.get('N8N_API_KEY')
        
        if not webhook_url:
            current_app.logger.warning('N8N_WEBHOOK_URL not configured')
            return False
            
        response = requests.post(
            webhook_url,
            files=files,
            data=data,
            headers={
                'X-API-Key': api_key
            } if api_key else {},
            timeout=30
        )
        
        if response.ok:
            result = response.json()
            # Update the image reference with n8n media ID if provided
            from models import ImageReference
            try:
                image_ref = ImageReference.query.get(media_id)
                if image_ref and 'media_id' in result:
                    image_ref.n8n_media_id = result['media_id']
                    db.session.commit()
            except Exception as e:
                current_app.logger.error(f'Error updating image reference: {str(e)}')
            return True
        else:
            current_app.logger.error(f'N8N webhook failed: {response.status_code} - {response.text}')
            return False
            
    except Exception as e:
        current_app.logger.error(f'Error sending to n8n: {str(e)}')
        return False

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"
