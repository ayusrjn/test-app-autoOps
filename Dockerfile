FROM python:3.11-slim

WORKDIR /app

# Install basic system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Default configuration environment variables
ENV PYTHONUNBUFFERED=1


# Expose port
EXPOSE 8000

# Start application server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
