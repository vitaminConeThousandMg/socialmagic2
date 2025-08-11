import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging
from config import Config

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self):
        self.app_id = Config.INSTAGRAM_APP_ID
        self.app_secret = Config.INSTAGRAM_APP_SECRET
        self.base_url = "https://graph.instagram.com"
    
    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Instagram OAuth URL"""
        
        scopes = [
            'instagram_basic',
            'instagram_content_publish',
            'instagram_manage_insights',
            'pages_show_list',
            'pages_read_engagement'
        ]
        
        params = {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'scope': ','.join(scopes),
            'response_type': 'code',
            'state': state
        }
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://api.instagram.com/oauth/authorize?{query_string}"
    
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict:
        """Exchange authorization code for access token"""
        
        try:
            response = requests.post('https://api.instagram.com/oauth/access_token', data={
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
                'code': code
            })
            
            if response.ok:
                data = response.json()
                
                # Get long-lived token
                long_lived_response = requests.get(f"{self.base_url}/access_token", params={
                    'grant_type': 'ig_exchange_token',
                    'client_secret': self.app_secret,
                    'access_token': data['access_token']
                })
                
                if long_lived_response.ok:
                    long_lived_data = long_lived_response.json()
                    return {
                        'success': True,
                        'access_token': long_lived_data['access_token'],
                        'expires_in': long_lived_data.get('expires_in', 5184000),  # 60 days default
                        'user_id': data['user_id']
                    }
            
            return {'success': False, 'error': 'Token exchange failed'}
            
        except Exception as e:
            logger.error(f"Error exchanging Instagram token: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_user_info(self, access_token: str) -> Dict:
        """Get Instagram user information"""
        
        try:
            response = requests.get(f"{self.base_url}/me", params={
                'fields': 'id,username,account_type,media_count',
                'access_token': access_token
            })
            
            if response.ok:
                return {'success': True, 'data': response.json()}
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error getting Instagram user info: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def create_media_container(self, 
                             access_token: str,
                             image_url: str,
                             caption: str,
                             is_carousel: bool = False) -> Dict:
        """Create media container for posting"""
        
        try:
            data = {
                'image_url': image_url,
                'caption': caption,
                'access_token': access_token
            }
            
            if is_carousel:
                data['media_type'] = 'CAROUSEL'
            
            response = requests.post(f"{self.base_url}/me/media", data=data)
            
            if response.ok:
                return {'success': True, 'container_id': response.json()['id']}
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error creating Instagram media container: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def publish_media(self, access_token: str, container_id: str) -> Dict:
        """Publish media container"""
        
        try:
            response = requests.post(f"{self.base_url}/me/media_publish", data={
                'creation_id': container_id,
                'access_token': access_token
            })
            
            if response.ok:
                return {'success': True, 'media_id': response.json()['id']}
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error publishing Instagram media: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def schedule_post(self, 
                     access_token: str,
                     media_url: str,
                     caption: str,
                     publish_time: datetime) -> Dict:
        """Schedule Instagram post"""
        
        # Create media container
        container_result = self.create_media_container(access_token, media_url, caption)
        
        if not container_result['success']:
            return container_result
        
        # Note: Instagram API doesn't support native scheduling
        # This would typically be handled by your task queue (Celery)
        # For now, we'll return the container ID for later publishing
        
        return {
            'success': True,
            'container_id': container_result['container_id'],
            'scheduled_for': publish_time.isoformat(),
            'message': 'Post prepared for scheduling'
        }
    
    def get_media_insights(self, access_token: str, media_id: str) -> Dict:
        """Get insights for a specific media post"""
        
        try:
            metrics = [
                'impressions',
                'reach',
                'likes',
                'comments',
                'shares',
                'saved'
            ]
            
            response = requests.get(f"{self.base_url}/{media_id}/insights", params={
                'metric': ','.join(metrics),
                'access_token': access_token
            })
            
            if response.ok:
                return {'success': True, 'insights': response.json()}
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error getting Instagram insights: {str(e)}")
            return {'success': False, 'error': str(e)}

class FacebookService:
    def __init__(self):
        self.app_id = Config.FACEBOOK_APP_ID
        self.app_secret = Config.FACEBOOK_APP_SECRET
        self.base_url = "https://graph.facebook.com/v18.0"
    
    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Facebook OAuth URL"""
        
        scopes = [
            'pages_manage_posts',
            'pages_read_engagement',
            'pages_show_list',
            'publish_to_groups'
        ]
        
        params = {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'scope': ','.join(scopes),
            'response_type': 'code',
            'state': state
        }
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query_string}"
    
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict:
        """Exchange authorization code for access token"""
        
        try:
            response = requests.get(f"{self.base_url}/oauth/access_token", params={
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'redirect_uri': redirect_uri,
                'code': code
            })
            
            if response.ok:
                data = response.json()
                return {
                    'success': True,
                    'access_token': data['access_token'],
                    'expires_in': data.get('expires_in', 5184000)
                }
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error exchanging Facebook token: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_user_pages(self, access_token: str) -> Dict:
        """Get user's Facebook pages"""
        
        try:
            response = requests.get(f"{self.base_url}/me/accounts", params={
                'access_token': access_token
            })
            
            if response.ok:
                return {'success': True, 'pages': response.json()['data']}
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error getting Facebook pages: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def post_to_page(self, 
                    page_access_token: str,
                    page_id: str,
                    message: str,
                    image_url: Optional[str] = None) -> Dict:
        """Post to Facebook page"""
        
        try:
            data = {
                'message': message,
                'access_token': page_access_token
            }
            
            if image_url:
                data['link'] = image_url
            
            response = requests.post(f"{self.base_url}/{page_id}/feed", data=data)
            
            if response.ok:
                return {'success': True, 'post_id': response.json()['id']}
            else:
                return {'success': False, 'error': response.json()}
                
        except Exception as e:
            logger.error(f"Error posting to Facebook: {str(e)}")
            return {'success': False, 'error': str(e)}

# Initialize service instances
instagram_service = InstagramService()
facebook_service = FacebookService()