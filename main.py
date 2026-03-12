#!/usr/bin/env python
"""Django's command-line utility for running the development server."""
import os
import sys

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'splitgood.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    # Run the development server on 0.0.0.0:5000
    execute_from_command_line(['manage.py', 'runserver', '0.0.0.0:5000'])


if __name__ == '__main__':
    main()
