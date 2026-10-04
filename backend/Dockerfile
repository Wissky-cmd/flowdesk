FROM python:3.14.7-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements-linux.lock backend/requirements-linux.lock
RUN pip install --no-cache-dir --require-hashes -r backend/requirements-linux.lock && useradd --create-home --uid 10001 flowdesk
COPY backend backend
COPY scripts scripts
RUN mkdir -p /data/exports && chown -R flowdesk:flowdesk /data /app
USER flowdesk
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
