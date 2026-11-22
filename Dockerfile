FROM python:3.13-slim

ENV DATABASE_PATH=/data/seal-log.db
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --user-group --uid 10001 appuser
RUN mkdir -p /data && chown appuser:appuser /data

COPY app.py schema.sql ./

USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--access-logfile", "-", "app:app"]
