FROM python:3.11-slim

# Set working directory
WORKDIR /app/backend

# Install system dependencies for asyncpg / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer-cache friendly)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/ .

# Expose API port
EXPOSE 8000

# Railway sets PORT dynamically. Run migrations and idempotent seeders before
# starting the API so each deploy brings the database up to date automatically.
CMD ["sh", "/app/backend/scripts/railway_start.sh"]
