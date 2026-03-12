import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'splitgood.settings')

app = Celery('splitgood')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
