FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[saas]"

# Copy application code
COPY . .
RUN pip install --no-cache-dir -e ".[saas]"

# Default: run the API
CMD ["uvicorn", "saas.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
