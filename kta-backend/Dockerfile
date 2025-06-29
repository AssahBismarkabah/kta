FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install minimal system dependencies and security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Create non-root user and directories
RUN useradd -m -u 1001 appuser \
    && mkdir -p /app/keycloak-configs/_templates /app/keycloak-configs/tenants \
    && chown -R appuser:appuser /app

# Set environment variables for security
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV KEYCLOAK_CONFIGS_REPO_PATH=/app/keycloak-configs
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# Run the application
CMD ["python", "app.py"]
