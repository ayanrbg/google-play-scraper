FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONWARNINGS=ignore::DeprecationWarning
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY gpi ./gpi

# api:    uvicorn gpi.api.main:app --host 0.0.0.0 --port 8000
# worker: python -m gpi.cli worker
CMD ["uvicorn", "gpi.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
