import os
import sys
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Auto-configure OAuth SocialApp on dev server start to avoid missing SocialApp errors
        try:
            # Only run when the development server main process is starting
            if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true':
                from django.core.management import call_command
                call_command('configure_oauth')
        except Exception:
            # Do not raise on startup; log would be visible in server output
            pass
