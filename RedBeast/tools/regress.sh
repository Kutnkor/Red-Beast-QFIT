#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
export PYTHONPATH=backend
mkdir -p evidence/integration reports/integration
.venv/bin/python -m pytest backend/tests -q --junitxml=evidence/integration/backend-tests.xml > evidence/integration/backend-tests.txt 2>&1
npm test --prefix frontend -- --reporter=json --outputFile=../evidence/integration/frontend-tests.json > evidence/integration/frontend-tests.txt 2>&1
npm run build --prefix frontend > evidence/integration/frontend-build.txt 2>&1
npm run lint --prefix frontend > evidence/integration/frontend-lint.txt 2>&1
.venv/bin/python tools/check_integration.py
if [[ "${1:-}" != "--no-docker" ]]; then
  BLINKSPACE_DOCKER=$(command -v docker || true)
  if [[ -z "$BLINKSPACE_DOCKER" && -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
    BLINKSPACE_DOCKER=/Applications/Docker.app/Contents/Resources/bin/docker
  fi
  [[ -n "$BLINKSPACE_DOCKER" ]] || { echo 'Docker is required (or explicitly use --no-docker for local-only checks).'; exit 1; }
  "$BLINKSPACE_DOCKER" build --progress=plain -t blinkspace:integration . > evidence/integration/docker-build.txt 2>&1
  .venv/bin/python tools/check_docker.py "$BLINKSPACE_DOCKER"
fi
printf '%s\n' 'Automated regression gates passed. Browser/GPU and paid-provider checks remain separately reported.'
