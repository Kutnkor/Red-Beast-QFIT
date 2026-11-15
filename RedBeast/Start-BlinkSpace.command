#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
if [[ ! -x .venv/bin/python ]]; then
  if command -v python3.13 >/dev/null 2>&1; then python3.13 -m venv .venv; else python3 -m venv .venv; fi
fi
blinkspace_deps_hash=$(shasum -a 256 backend/requirements.txt backend/requirements.lock | shasum -a 256)
if [[ ! -f .venv/.blinkspace-deps-ready ]] || [[ "$(cat .venv/.blinkspace-deps-ready)" != "$blinkspace_deps_hash" ]]; then
  .venv/bin/pip install -c backend/requirements.lock -r backend/requirements.txt
  print -r -- "$blinkspace_deps_hash" > .venv/.blinkspace-deps-ready
fi
if [[ ! -f frontend/dist/index.html ]]; then
  npm --prefix frontend ci
  npm --prefix frontend run build
fi
export BLINKSPACE_ARCHIVE_PROTOCOL=sia
export BLINKSPACE_GAIA_PROVIDER=esa
export BLINKSPACE_ALLWISE_PROVIDER=vizier
export PYTHONPATH=backend
.venv/bin/python -m tools.launch
