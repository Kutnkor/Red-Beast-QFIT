# syntax=docker/dockerfile:1
# One container serves both the built UI and the FastAPI application.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Frontend contract tests type-check against the exact published catalogue/profile JSON.
COPY backend/blinkspace/resources/motion_catalogue.json backend/blinkspace/resources/stellar_profiles.json /backend/blinkspace/resources/
COPY tools/contracts/assistant-commands.json /tools/contracts/assistant-commands.json
RUN npm run build

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    BLINKSPACE_DATA_DIR=/data \
    BLINKSPACE_FRONTEND_DIST=/app/frontend/dist \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements.lock ./
RUN pip install --no-cache-dir -c requirements.lock -r requirements.txt
RUN useradd --create-home --uid 1000 app && mkdir -p /data /app/seed-data && \
    chown app:app /data /app/seed-data
COPY --chown=app:app backend/blinkspace ./blinkspace
COPY --chown=app:app backend/vendor ./vendor
COPY --chown=app:app backend/tools ./tools
COPY --from=web --chown=app:app /web/dist /app/frontend/dist
COPY --chown=app:app docker/ /app/docker/
RUN chmod +x /app/docker/entrypoint.sh
# Optional local seed, exported with tools.package_seed. Never copy runtime data wholesale.
COPY --chown=app:app seed-data/ /app/seed-data/
# uid 1000 also matches the default user on Docker Spaces.
USER app
ARG BLINKSPACE_BUILD_SEED=1
RUN if [ "$BLINKSPACE_BUILD_SEED" = "1" ]; then \
      if [ ! -f /app/seed-data/blinkspace.sqlite3 ]; then \
        BLINKSPACE_DATA_DIR=/app/seed-data python -m tools.prepare_presets && \
        BLINKSPACE_DATA_DIR=/app/seed-data python -m tools.precompute_tracks; \
      fi; \
      python /app/docker/verify_seed.py /app/seed-data; \
    fi
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health', timeout=4).read()" || exit 1
ENTRYPOINT ["/app/docker/entrypoint.sh"]
