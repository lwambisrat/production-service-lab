# Shared image for all three services. They are structurally identical
# (uvicorn app:app, importing the shared `common` package), so one image runs
# all of them — docker-compose.yml just points each container at a different
# service directory and port. Keeps the build simple and consistent.
FROM python:3.12-slim

WORKDIR /app

# curl is included so internal discovery can be tested from inside a container
# (e.g. `docker compose exec ride-booking curl http://driver-matching:3002/health`).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code (all three services + the shared common package).
COPY services/ ./services/

# PYTHONPATH lets each service import `common`; unbuffered output means logs
# reach stdout immediately so `docker compose logs` shows them in real time.
ENV PYTHONPATH=/app/services \
    PYTHONUNBUFFERED=1

# Default command is overridden per-service in docker-compose.yml
# (different working_dir + port). Provided here so the image is runnable alone.
WORKDIR /app/services/ride-booking
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3001"]
