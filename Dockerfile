FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ app/
RUN mkdir -p data

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV HEALTH_PORT=8080

# Expose health check port
EXPOSE 8080

# Run the bot
CMD ["python", "-m", "app"]
