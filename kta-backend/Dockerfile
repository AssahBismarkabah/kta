# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5001 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    HOST=0.0.0.0

# Create app directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Create keycloak-configs directory
RUN mkdir -p /app/keycloak-configs

# Expose port
EXPOSE ${PORT}

# Run the application with proper host binding
CMD ["python", "-c", "import os; from app import app; app.run(host=os.environ.get('HOST', '0.0.0.0'), port=int(os.environ.get('PORT', 5001)))"]
