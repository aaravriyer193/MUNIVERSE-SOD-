# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install gunicorn

# Copy code
COPY . .

# Koyeb automatically sets $PORT
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Start Flask with Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:${PORT}", "app:app"]
