FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONWARNINGS=ignore::DeprecationWarning
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY playtrend ./playtrend

# api:    uvicorn playtrend.api.main:app --host 0.0.0.0 --port 8000 (behind Caddy; its X-Forwarded-For gives the client IP)
# worker: python -m playtrend.cli worker
CMD ["uvicorn", "playtrend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
