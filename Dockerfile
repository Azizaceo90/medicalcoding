# Container image for the Medical Coding & Billing System.
# Works on Render, Railway, Fly.io, Cloud Run, or any container host.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hosts inject the listening port via $PORT; default to 8000 locally.
ENV PORT=8000 HOST=0.0.0.0
EXPOSE 8000

# Bind to 0.0.0.0:$PORT so the platform's router can reach it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
