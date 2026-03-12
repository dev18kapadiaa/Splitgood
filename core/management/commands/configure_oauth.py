import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Configure Site domain and Google SocialApp from environment'

    def handle(self, *args, **options):
        from django.contrib.sites.models import Site
        from allauth.socialaccount.models import SocialApp

        
        #Default to local runserver host/port used in development
        domain = os.environ.get('SITE_DOMAIN', '127.0.0.1:8000')

        # Also support linking the app to common local hostnames used in development
        extra_domains = [
            domain,
            '127.0.0.1:8000',
            'localhost:8000',
        ]

        # Ensure Site with id=1 exists and points to our primary domain
        site = Site.objects.get(id=1)
        if site.domain != domain:
            site.domain = domain
            site.name = 'Splitgood'
            site.save()
            self.stdout.write(f'Updated site domain to: {domain}')
        else:
            self.stdout.write(f'Site domain already set: {domain}')

        # Create or ensure extra Site entries exist (127.0.0.1:8000 and localhost:8000)
        created_sites = []
        for d in set(extra_domains):
            try:
                s, created = Site.objects.get_or_create(domain=d, defaults={'name': 'Splitgood'})
                if created:
                    created_sites.append(d)
                    self.stdout.write(f'Created site entry for: {d}')
            except Exception:
                # ignore any race/permission issues
                pass

        client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')

        if not client_id or not client_secret:
            self.stdout.write(self.style.WARNING('Google OAuth credentials not found in environment'))
            return

        app, created = SocialApp.objects.get_or_create(
            provider='google',
            defaults={
                'name': 'Google',
                'client_id': client_id,
                'secret': client_secret,
            }
        )
        if not created:
            if app.client_id != client_id or app.secret != client_secret:
                app.client_id = client_id
                app.secret = client_secret
                app.save()
                self.stdout.write('Updated Google SocialApp credentials')
        else:
            self.stdout.write('Created Google SocialApp')

        # Link SocialApp to all relevant sites
        for sdomain in set([site.domain] + extra_domains):
            try:
                s = Site.objects.filter(domain=sdomain).first()
                if s and not app.sites.filter(id=s.id).exists():
                    app.sites.add(s)
                    self.stdout.write(f'Linked SocialApp to site: {sdomain}')
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS(
            f'OAuth configured. Callback: https://{domain}/accounts/google/login/callback/'
        ))
