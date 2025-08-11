import time
from google import genai
from google.genai import types
from config import Config
import json
import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class GeminiAIService:
    def __init__(self):
        self.client = genai.Client(api_key=Config.GOOGLE_AI_API_KEY)
        
    def generate_post_content(self, 
                            prompt: str, 
                            brand_profile: Dict,
                            rejection_note: Optional[str] = None) -> Dict:
        """Generate post content including caption and hashtags"""
        
        # Build comprehensive prompt
        system_prompt = self._build_system_prompt(brand_profile, rejection_note)
        full_prompt = f"{system_prompt}\n\nGenerate content for: {prompt}"
        
        try:
            response = self.client.models.generate_content(
                model='gemini-1.5-pro',
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1000
                )
            )
            
            # Parse response (expecting JSON format)
            content = json.loads(response.candidates[0].content.parts[0].text)
            
            return {
                'success': True,
                'caption': content.get('caption', ''),
                'hashtags': content.get('hashtags', []),
                'image_prompt': content.get('image_prompt', ''),
                'style_notes': content.get('style_notes', ''),
                'metadata': {
                    'model': 'gemini-1.5-pro',
                    'temperature': 0.7,
                    'prompt_tokens': len(full_prompt.split())
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating content: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_image(self, prompt: str, brand_style: Dict) -> Dict:
        """Generate image using Imagen 3"""
        
        # Enhance prompt with brand style
        enhanced_prompt = self._enhance_image_prompt(prompt, brand_style)
        
        try:
            response = self.client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=enhanced_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    safety_filter_level="block_some",
                    person_generation="allow_adult"
                )
            )
            
            # Extract image data from response
            if response.generated_images:
                generated_image = response.generated_images[0]
                
                return {
                    'success': True,
                    'image_file': generated_image.image,
                    'prompt_used': enhanced_prompt,
                    'metadata': {
                        'model': 'imagen-3.0-generate-002',
                        'size': '1024x1024'
                    }
                }
            
        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_video(self, prompt: str, brand_style: Dict) -> Dict:
        """Generate video using Google Veo 3"""
        
        enhanced_prompt = self._enhance_video_prompt(prompt, brand_style)
        
        try:
            # Generate video with Veo 3
            operation = self.client.models.generate_videos(
                model="veo-3.0-generate-preview",
                prompt=enhanced_prompt,
            )
            
            # Poll the operation status until the video is ready
            max_wait_time = 300  # 5 minutes max wait
            wait_time = 0
            
            while not operation.done and wait_time < max_wait_time:
                logger.info("Waiting for video generation to complete...")
                time.sleep(10)
                wait_time += 10
                operation = self.client.operations.get(operation)
            
            if operation.done and operation.response.generated_videos:
                generated_video = operation.response.generated_videos[0]
                
                return {
                    'success': True,
                    'video_file': generated_video.video,
                    'prompt_used': enhanced_prompt,
                    'metadata': {
                        'model': 'veo-3.0-generate-preview',
                        'duration': '5s',  # Default Veo duration
                        'format': 'mp4'
                    }
                }
            else:
                return {
                    'success': False,
                    'error': 'Video generation timed out or failed'
                }
            
        except Exception as e:
            logger.error(f"Error generating video: {str(e)}")
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_video_from_image(self, prompt: str, image_file, brand_style: Dict) -> Dict:
        """Generate video from image using Veo 2 (as Veo 3 doesn't support image input yet)"""
        
        enhanced_prompt = self._enhance_video_prompt(prompt, brand_style)
        
        try:
            # Generate video with Veo 2 using image input
            operation = self.client.models.generate_videos(
                model="veo-2.0-generate-001",
                prompt=enhanced_prompt,
                image=image_file,
            )
            
            # Poll the operation status until the video is ready
            max_wait_time = 300  # 5 minutes max wait
            wait_time = 0
            
            while not operation.done and wait_time < max_wait_time:
                logger.info("Waiting for video generation to complete...")
                time.sleep(10)
                wait_time += 10
                operation = self.client.operations.get(operation)
            
            if operation.done and operation.response.generated_videos:
                generated_video = operation.response.generated_videos[0]
                
                return {
                    'success': True,
                    'video_file': generated_video.video,
                    'prompt_used': enhanced_prompt,
                    'metadata': {
                        'model': 'veo-2.0-generate-001',
                        'duration': '5s',
                        'format': 'mp4',
                        'generated_from_image': True
                    }
                }
            else:
                return {
                    'success': False,
                    'error': 'Video generation timed out or failed'
                }
                
        except Exception as e:
            logger.error(f"Error generating video: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _build_system_prompt(self, brand_profile: Dict, rejection_note: Optional[str] = None) -> str:
        """Build comprehensive system prompt for content generation"""
        
        prompt_parts = [
            "You are an expert social media content creator specializing in Instagram and Facebook posts.",
            "Generate engaging, brand-consistent content that drives engagement and conversions.",
            "",
            "BRAND PROFILE:",
            f"- Brand Name: {brand_profile.get('brand_name', 'N/A')}",
            f"- Industry: {brand_profile.get('industry', 'N/A')}",
            f"- Brand Voice: {brand_profile.get('brand_voice', 'Professional and engaging')}",
            f"- Target Audience: {brand_profile.get('target_audience', 'General audience')}",
            f"- Brand Description: {brand_profile.get('brand_description', 'N/A')}",
            "",
            "CONTENT REQUIREMENTS:",
            "- Caption should be 150-300 characters for optimal engagement",
            "- Include 5-10 relevant hashtags (mix of popular and niche)",
            "- Use emojis strategically to increase visual appeal",
            "- Include a clear call-to-action when appropriate",
            "- Maintain brand voice and personality throughout",
            "",
            "RESPONSE FORMAT (JSON):",
            "{",
            '  "caption": "Engaging post caption with emojis",',
            '  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3"],',
            '  "image_prompt": "Detailed prompt for image generation",',
            '  "style_notes": "Visual style and composition notes"',
            "}",
        ]
        
        # Add custom AI instructions if provided
        if brand_profile.get('ai_instructions'):
            prompt_parts.extend([
                "",
                "CUSTOM BRAND INSTRUCTIONS:",
                brand_profile['ai_instructions']
            ])
        
        # Add rejection feedback if regenerating
        if rejection_note:
            prompt_parts.extend([
                "",
                "PREVIOUS REJECTION FEEDBACK:",
                f"The user rejected the previous version with this note: {rejection_note}",
                "Please address this feedback in the new generation."
            ])
        
        return "\n".join(prompt_parts)
    
    def _enhance_image_prompt(self, base_prompt: str, brand_style: Dict) -> str:
        """Enhance image prompt with brand style elements"""
        
        enhancements = [
            base_prompt,
            "High-quality, professional photography style.",
        ]
        
        if brand_style.get('brand_colors'):
            colors = ', '.join(brand_style['brand_colors'])
            enhancements.append(f"Brand colors: {colors}")
        
        if brand_style.get('brand_style'):
            enhancements.append(f"Visual style: {brand_style['brand_style']}")
        
        enhancements.extend([
            "Instagram-optimized composition (square 1:1 aspect ratio)",
            "Clean, modern aesthetic with good lighting",
            "Suitable for social media posting",
            "High resolution and professional quality"
        ])
        
        return ". ".join(enhancements)
    
    def _enhance_video_prompt(self, base_prompt: str, brand_style: Dict) -> str:
        """Enhance video prompt with brand style elements"""
        
        enhancements = [
            base_prompt,
            "Short-form video content (15-30 seconds)",
            "High-quality, engaging visual storytelling",
        ]
        
        if brand_style.get('brand_colors'):
            colors = ', '.join(brand_style['brand_colors'])
            enhancements.append(f"Brand colors: {colors}")
        
        enhancements.extend([
            "Vertical format (9:16) optimized for Instagram Reels and Stories",
            "Dynamic movement and visual interest",
            "Professional production quality",
            "Engaging visual storytelling within 5-10 seconds",
            "Smooth camera movements and transitions"
        ])
        
        return ". ".join(enhancements)

# Initialize service instance
ai_service = GeminiAIService()

    def generate_campaign_prompts(self, 
                                 business_profile: Dict, 
                                 num_posts: int = 7,
                                 num_images: int = 5,
                                 num_videos: int = 2) -> Dict:
        """Generate campaign prompts using Gemini based on business profile"""
        
        # Build comprehensive business context
        business_context = self._build_business_context(business_profile)
        
        # Create the campaign generation prompt
        campaign_prompt = f"""
{business_context}

TASK: Generate {num_posts} diverse social media content prompts for this business.

REQUIREMENTS:
- {num_images} prompts should be for IMAGE posts (photos, graphics, product shots)
- {num_videos} prompts should be for VIDEO posts (reels, stories, behind-the-scenes)
- Each prompt should be specific, actionable, and aligned with the brand voice
- Vary the content types: product features, behind-the-scenes, customer stories, tips, lifestyle, etc.
- Consider seasonal trends and current social media best practices
- Each prompt should be 1-2 sentences that clearly describe the content to create

RESPONSE FORMAT (JSON):
{{
  "campaign_name": "Suggested campaign name",
  "campaign_description": "Brief description of the overall campaign strategy",
  "prompts": [
    {{
      "type": "image",
      "prompt": "Specific content prompt for image post",
      "content_theme": "product_showcase|behind_scenes|lifestyle|tips|customer_story"
    }},
    {{
      "type": "video", 
      "prompt": "Specific content prompt for video post",
      "content_theme": "product_demo|behind_scenes|testimonial|tutorial|lifestyle"
    }}
  ]
}}
"""
        
        try:
            response = self.client.models.generate_content(
                model='gemini-1.5-pro',
                contents=campaign_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,  # Higher creativity for campaign ideas
                    max_output_tokens=2000
                )
            )
            
            # Parse response
            content = json.loads(response.candidates[0].content.parts[0].text)
            
            return {
                'success': True,
                'campaign_name': content.get('campaign_name', 'AI Generated Campaign'),
                'campaign_description': content.get('campaign_description', ''),
                'prompts': content.get('prompts', []),
                'metadata': {
                    'model': 'gemini-1.5-pro',
                    'temperature': 0.8,
                    'total_prompts': len(content.get('prompts', [])),
                    'image_prompts': len([p for p in content.get('prompts', []) if p.get('type') == 'image']),
                    'video_prompts': len([p for p in content.get('prompts', []) if p.get('type') == 'video'])
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating campaign prompts: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _build_business_context(self, business_profile: Dict) -> str:
        """Build comprehensive business context for campaign generation"""
        
        context_parts = [
            "BUSINESS PROFILE:",
            f"- Brand Name: {business_profile.get('brand_name', 'N/A')}",
            f"- Industry: {business_profile.get('industry', 'N/A')}",
            f"- Brand Description: {business_profile.get('brand_description', 'N/A')}",
            f"- Brand Voice: {business_profile.get('brand_voice', 'Professional and engaging')}",
            f"- Target Audience: {business_profile.get('target_audience', 'General audience')}",
            f"- Visual Style: {business_profile.get('brand_style', 'N/A')}",
        ]
        
        # Add content themes if available
        if business_profile.get('content_themes'):
            themes = ', '.join(business_profile['content_themes'])
            context_parts.append(f"- Preferred Content Themes: {themes}")
        
        # Add brand colors if available
        if business_profile.get('brand_colors'):
            colors = ', '.join(business_profile['brand_colors'])
            context_parts.append(f"- Brand Colors: {colors}")
        
        # Add custom AI instructions if available
        if business_profile.get('ai_instructions'):
            context_parts.extend([
                "",
                "CUSTOM BRAND INSTRUCTIONS:",
                business_profile['ai_instructions']
            ])
        
        return "\n".join(context_parts)