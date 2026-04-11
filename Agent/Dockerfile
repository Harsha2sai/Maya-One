# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ripgrep \
        sqlite3 \
        curl \
        procps \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash maya
WORKDIR /app

COPY Agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY Agent/ ./Agent/
COPY k8s/ ./k8s/

RUN mkdir -p /app/logs /app/data /home/maya/.maya \
    && chown -R maya:maya /app /home/maya/.maya

COPY Agent/scripts/docker_entrypoint.sh /entrypoint.sh
COPY Agent/scripts/healthcheck.sh /healthcheck.sh
RUN chmod +x /entrypoint.sh /healthcheck.sh

USER maya

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD /healthcheck.sh || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["dev"]

