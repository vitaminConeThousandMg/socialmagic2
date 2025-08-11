from celery import Celery
from config import Config

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=Config.CELERY_RESULT_BACKEND,
        broker=Config.CELERY_BROKER_URL
    )
    
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        beat_schedule={
            'weekly-post-generation': {
                'task': 'tasks.generation.generate_weekly_posts',
                'schedule': 60.0 * 60.0 * 24.0,  # Daily check
            },
            'publish-scheduled-posts': {
                'task': 'tasks.publishing.publish_scheduled_posts',
                'schedule': 60.0 * 15.0,  # Every 15 minutes
            },
            'update-analytics': {
                'task': 'tasks.analytics.update_post_analytics',
                'schedule': 60.0 * 60.0 * 6.0,  # Every 6 hours
            },
        }
    )
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery