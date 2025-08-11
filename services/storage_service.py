import boto3
from botocore.exceptions import ClientError
from config import Config
import uuid
import logging
from typing import Optional, Dict
import base64
from io import BytesIO

logger = logging.getLogger(__name__)

class S3StorageService:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_S3_REGION
        )
        self.bucket_name = Config.AWS_S3_BUCKET
    
    def upload_generated_media(self, 
                             media_file, 
                             media_type: str,
                             user_id: int,
                             post_id: int) -> Optional[str]:
        """Upload generated media to S3"""
        
        try:
            # Generate unique filename
            file_extension = 'jpg' if media_type == 'image' else 'mp4'
            filename = f"generated/{user_id}/{post_id}/{uuid.uuid4()}.{file_extension}"
            
            # Handle different file input types
            if hasattr(media_file, 'read'):
                # File-like object from Gemini API
                media_data = media_file.read()
            elif isinstance(media_file, bytes):
                # Raw bytes
                media_data = media_file
            else:
                # Gemini file object - download it first
                self.s3_client.download_file(media_file, filename)
                # Return URL directly since file is already uploaded
                url = f"https://{self.bucket_name}.s3.{Config.AWS_S3_REGION}.amazonaws.com/{filename}"
                return url
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=media_data,
                ContentType=f"{media_type}/{'jpeg' if media_type == 'image' else 'mp4'}",
                ACL='public-read'
            )
            
            # Return public URL
            url = f"https://{self.bucket_name}.s3.{Config.AWS_S3_REGION}.amazonaws.com/{filename}"
            return url
            
        except ClientError as e:
            logger.error(f"Error uploading to S3: {str(e)}")
            return None
    
    def upload_brand_asset(self, 
                          file_data: bytes,
                          filename: str,
                          user_id: int,
                          asset_type: str) -> Optional[str]:
        """Upload brand asset to S3"""
        
        try:
            # Generate S3 key
            file_extension = filename.split('.')[-1].lower()
            s3_key = f"brand_assets/{user_id}/{asset_type}/{uuid.uuid4()}.{file_extension}"
            
            # Determine content type
            content_type_map = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'pdf': 'application/pdf',
                'svg': 'image/svg+xml'
            }
            content_type = content_type_map.get(file_extension, 'application/octet-stream')
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
                ACL='public-read'
            )
            
            # Return public URL
            url = f"https://{self.bucket_name}.s3.{Config.AWS_S3_REGION}.amazonaws.com/{s3_key}"
            return url
            
        except ClientError as e:
            logger.error(f"Error uploading brand asset: {str(e)}")
            return None
    
    def upload_user_media(self, file_data: bytes, filename: str, user_id: int, media_type: str) -> Optional[str]:
        """Upload user-provided media to S3"""
        try:
            # Generate unique S3 key
            file_extension = filename.split('.')[-1].lower()
            s3_key = f"user_uploads/{user_id}/{media_type}/{uuid.uuid4()}.{file_extension}"
            
            # Determine content type
            content_type_map = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'mp4': 'video/mp4',
                'mov': 'video/quicktime'
            }
            content_type = content_type_map.get(file_extension, 'application/octet-stream')
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
                ACL='public-read'
            )
            
            # Return public URL
            return f"https://{self.bucket_name}.s3.{Config.AWS_S3_REGION}.amazonaws.com/{s3_key}"
            
        except ClientError as e:
            logger.error(f"Error uploading user media: {str(e)}")
            return None
    
    def generate_thumbnail(self, video_url: str, user_id: int, post_id: int) -> Optional[str]:
        """Generate thumbnail for video (placeholder implementation)"""
        
        # This would typically use FFmpeg or similar to extract a frame
        # For now, returning a placeholder
        try:
            thumbnail_key = f"thumbnails/{user_id}/{post_id}/{uuid.uuid4()}.jpg"
            
            # Placeholder thumbnail generation logic
            # In production, you'd extract a frame from the video
            
            return f"https://{self.bucket_name}.s3.{Config.AWS_S3_REGION}.amazonaws.com/{thumbnail_key}"
            
        except Exception as e:
            logger.error(f"Error generating thumbnail: {str(e)}")
            return None
    
    def delete_media(self, url: str) -> bool:
        """Delete media from S3"""
        
        try:
            # Extract key from URL
            key = url.split(f"{self.bucket_name}.s3.{Config.AWS_S3_REGION}.amazonaws.com/")[1]
            
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting from S3: {str(e)}")
            return False

# Initialize service instance
storage_service = S3StorageService()
