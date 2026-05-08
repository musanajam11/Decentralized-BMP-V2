FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
RUN chmod +x ./scripts/fetch_builds.sh ./scripts/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8420

EXPOSE 8420

# tini reaps zombies and forwards SIGTERM so the publish loop can shut
# down within the SIGTERM grace period. The entrypoint fetches and
# patches the BeamMP binaries on every start (idempotent — cached files
# are kept) and then execs the command.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8420", "--proxy-headers", "--forwarded-allow-ips=*"]

