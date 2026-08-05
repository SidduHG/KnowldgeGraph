FROM python:3.11-slim

WORKDIR /app

# git is required by get_diff_context
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Set Python path
ENV PYTHONPATH=/app

# Expose HTTP port
EXPOSE 8001

# Start HTTP server (use MODE env to switch)
CMD ["uvicorn", "app.adapters.http_api:app", "--host", "0.0.0.0", "--port", "8001"]
