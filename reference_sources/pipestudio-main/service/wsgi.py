"""Entry point for gunicorn: `gunicorn service.wsgi:app`."""

from .app import create_app

app = create_app()
