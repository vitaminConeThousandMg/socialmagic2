# Add this task to your tasks/email_tasks.py file

@celery.task
def send_admin_alert(subject: str, message: str, severity: str = 'medium', admin_emails: list = None):
    """Send alert email to administrators"""
    try:
        from app import app
        
        with app.app_context():
            mail = app.mail
            
            # Get admin emails from config or parameter
            if not admin_emails:
                admin_emails = current_app.config.get('ADMIN_EMAILS', [])
                if isinstance(admin_emails, str):
                    admin_emails = [admin_emails]
            
            if not admin_emails:
                logger.warning('No admin emails configured for alerts')
                return False
            
            # Choose colors and icons based on severity
            severity_config = {
                'low': {'color': '#10b981', 'icon': 'ℹ️', 'bg_color': '#ecfdf5'},
                'medium': {'color': '#f59e0b', 'icon': '⚠️', 'bg_color': '#fefbeb'},
                'high': {'color': '#dc2626', 'icon': '🚨', 'bg_color': '#fef2f2'},
                'info': {'color': '#3b82f6', 'icon': '📊', 'bg_color': '#eff6ff'}
            }
            
            config = severity_config.get(severity, severity_config['medium'])
            
            msg = Message(
                f"{config['icon']} SocialMagic Admin Alert: {subject}",
                sender=current_app.config['MAIL_USERNAME'],
                recipients=admin_emails
            )
            
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: {config['color']}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 20px;">{config['icon']} Admin Alert</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Severity: {severity.upper()}</p>
                </div>
                
                <div style="padding: 30px; background: white; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px;">
                    <h2 style="color: #1f2937; margin-top: 0;">{subject}</h2>
                    
                    <div style="background: {config['bg_color']}; padding: 20px; border-radius: 6px; border-left: 4px solid {config['color']};">
                        <pre style="white-space: pre-wrap; font-family: 'Courier New', monospace; margin: 0; color: #374151; line-height: 1.5;">{message}</pre>
                    </div>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">
                        <p style="margin: 0;">
                            <strong>Timestamp:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC<br>
                            <strong>Environment:</strong> {current_app.config.get('ENV', 'Unknown')}<br>
                            <strong>Application:</strong> SocialMagic
                        </p>
                    </div>
                </div>
            </div>
            """
            
            mail.send(msg)
            logger.info(f'Admin alert sent: {subject} ({severity})')
            return True
            
    except Exception as e:
        logger.error(f'Error sending admin alert: {str(e)}')
        return False