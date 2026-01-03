FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for healthcheck curl
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Create data directory for SQLite database
RUN mkdir -p /app/data && chmod 777 /app/data

# Environment defaults (can be overridden)
ENV DJANGO_ALLOWED_HOSTS="*" \
    DJANGO_DEBUG="False" \
    DATABASE_PATH="/app/data/db.sqlite3"

EXPOSE 8000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Volume for persistent data
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/backlog/health/ || exit 1

CMD ["/entrypoint.sh"]