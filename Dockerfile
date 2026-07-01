
FROM python:3.12-slim

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --no-create-home \
        --shell /usr/sbin/nologin appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appgroup services/ ./services/
ENV PYTHONPATH=/app/services \
    PYTHONUNBUFFERED=1
USER appuser
WORKDIR /app/services/ride-booking
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3001"]
