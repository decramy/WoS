#!/usr/bin/env sh
set -e

# Check database file permissions
DB_FILE="${DATABASE_PATH:-/app/data/db.sqlite3}"
DB_DIR=$(dirname "$DB_FILE")

echo "🔍 Checking database permissions..."

# Ensure directory exists
if [ ! -d "$DB_DIR" ]; then
    echo "📁 Creating database directory: $DB_DIR"
    mkdir -p "$DB_DIR" || {
        echo "❌ ERROR: Cannot create database directory: $DB_DIR"
        echo "   Please ensure the volume is mounted with write permissions."
        exit 1
    }
fi

# Check directory is writable
if [ ! -w "$DB_DIR" ]; then
    echo "❌ ERROR: Database directory is not writable: $DB_DIR"
    echo "   Current permissions: $(ls -ld "$DB_DIR")"
    echo "   Running as user: $(id)"
    echo ""
    echo "   Fix: Ensure the mounted volume has correct permissions."
    echo "   Example: docker run -v /path/to/data:/app/data:rw ..."
    exit 1
fi

# If database exists, check it's writable
if [ -f "$DB_FILE" ]; then
    if [ ! -w "$DB_FILE" ]; then
        echo "❌ ERROR: Database file is not writable: $DB_FILE"
        echo "   Current permissions: $(ls -l "$DB_FILE")"
        echo "   Running as user: $(id)"
        exit 1
    fi
    echo "✅ Database file is writable: $DB_FILE"
else
    echo "📝 Database file will be created: $DB_FILE"
fi

# Apply migrations
echo "🔄 Applying database migrations..."
python manage.py migrate --noinput

# Verify database is actually writable by doing a test write
echo "🧪 Testing database write access..."
python -c "
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wos.settings')
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS _write_test (id INTEGER PRIMARY KEY)')
cursor.execute('DROP TABLE _write_test')
print('✅ Database write test passed!')
" || {
    echo "❌ ERROR: Database write test failed!"
    echo "   The database file exists but cannot be written to."
    exit 1
}

# Collect static files
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting Gunicorn..."
# Start Gunicorn
exec gunicorn wos.wsgi:application --bind 0.0.0.0:8000 --workers 3