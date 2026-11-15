#!/bin/sh
set -eu

PORT="${PORT:-8000}"
export PORT
case "$PORT" in
  ''|*[!0-9]*) echo "PORT must be an integer." >&2; exit 2 ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "PORT must be between 1 and 65535." >&2
  exit 2
fi

python /app/docker/initialize_data.py /app/seed-data "${BLINKSPACE_DATA_DIR:-/data}"
exec python -m uvicorn blinkspace.api:app_factory --factory \
  --host 0.0.0.0 --port "$PORT" --workers 1 --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
