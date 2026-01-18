# syntax=docker/dockerfile:1

ARG DI2SE_URL="https://builds.steffenl.com/download/dead-island-2-save-editor/0.10.0/di2se-0.10.0-linux.x86_64.tar.gz"

# ---- stage 1: fetch di2se bundle (bin/di2save + bin/data/*) ----
FROM debian:bookworm-slim AS fetcher
ARG DI2SE_URL

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl tar \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN curl -fsSL "$DI2SE_URL" -o di2se.tar.gz \
  && mkdir -p /out \
  && tar -xzf di2se.tar.gz -C /out \
  && rm -f di2se.tar.gz

# Normalize extracted folder to /out/di2se
RUN set -eux; \
  DI2SE_DIR="$(find /out -maxdepth 3 -type f -path '*/bin/di2save' -print | head -n 1 | xargs -r dirname | xargs -r dirname)"; \
  test -n "$DI2SE_DIR"; \
  mkdir -p /out/di2se; \
  cp -a "$DI2SE_DIR"/. /out/di2se/

# ---- stage 2: runtime API ----
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY --from=fetcher /out/di2se /opt/di2se

# Build context must be repo root for these paths:
COPY commands.json /app/commands.json
COPY api/main.py /app/main.py

RUN useradd -m -u 10001 app \
  && chown -R app:app /app /opt/di2se
USER app

ENV DI2SE_BIN_DIR=/opt/di2se/bin
ENV DI2SAVE_BIN=./di2save
ENV COMMANDS_FILE=/app/commands.json
ENV SAVE_DIR=/data
ENV CMD_TIMEOUT_SEC=60
ENV MAX_OUTPUT_CHARS=400000

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000"]
