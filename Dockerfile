FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml ./
COPY core/ ./core/
COPY apps/ ./apps/
COPY db/ ./db/
COPY strategies/ ./strategies/

# Install Python dependencies
RUN uv pip install --system -e .

# Default command (overridden by docker-compose)
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
