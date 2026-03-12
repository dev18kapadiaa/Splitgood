import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'splitgood.settings')
from dotenv import load_dotenv
load_dotenv()
import django
django.setup()
from django.conf import settings
print('ENV PGPASSWORD=', os.environ.get('PGPASSWORD'))
print('ENV PGUSER=', os.environ.get('PGUSER'))
print('ENV DATABASE_URL=', os.environ.get('DATABASE_URL'))
print('settings.DATABASES=')
import pprint
pprint.pprint(settings.DATABASES)
