#!/usr/bin/env sh
set -e

# Apply migrations
python manage.py migrate --noinput

# Start Gunicorn
exec gunicorn wos.wsgi:application --bind 0.0.0.0:8000 --workers 3