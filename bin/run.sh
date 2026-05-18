#!/bin/bash
# DXT entry point. Uses `uv` to provision Python (≥3.11) and runtime deps from
# pyproject.toml. uv auto-downloads a managed CPython if none ≥3.11 is present.
#
# Falls back to a pip-based bootstrap if uv is unavailable.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

log() { printf 'genealogy-mcp: %s\n' "$*" >&2; }

# 1. Try to locate uv. Claude Desktop GUI processes don't inherit a login shell
#    PATH, so we check common install locations explicitly.
UV=""
for cand in \
  uv \
  "$HOME/.local/bin/uv" \
  "$HOME/.cargo/bin/uv" \
  /opt/homebrew/bin/uv \
  /usr/local/bin/uv \
  /opt/local/bin/uv
do
  resolved="$(command -v "$cand" 2>/dev/null || true)"
  if [[ -n "$resolved" && -x "$resolved" ]]; then
    UV="$resolved"
    break
  fi
done

if [[ -n "$UV" ]]; then
  log "using uv at $UV"
  # uv will:
  #   - download a managed Python 3.11 if none is available,
  #   - resolve and cache deps from pyproject.toml in ~/.cache/uv,
  #   - sync into a project venv at $DIR/.venv,
  #   - exec the server.
  export UV_PROJECT_ENVIRONMENT="$DIR/.venv"
  export UV_PYTHON_PREFERENCE="${UV_PYTHON_PREFERENCE:-managed}"
  exec "$UV" run --directory "$DIR" --python ">=3.11" \
    python -m genealogy_mcp "$@"
fi

# 2. Fallback: find a Python ≥3.11 and pip install --target lib/.
log "uv not found; falling back to pip-based bootstrap"
LIB="$DIR/lib"
PY=""
for cand in \
  python3.13 python3.12 python3.11 \
  /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
  /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
  /opt/local/bin/python3.13 /opt/local/bin/python3.12 /opt/local/bin/python3.11
do
  resolved="$(command -v "$cand" 2>/dev/null || true)"
  [[ -z "$resolved" ]] && continue
  if "$resolved" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$resolved"
    break
  fi
done

if [[ -z "$PY" ]]; then
  log "ERROR: neither uv nor Python ≥3.11 found."
  log "  Install uv:    curl -LsSf https://astral.sh/uv/install.sh | sh"
  log "  Or python:     brew install python@3.12"
  exit 1
fi

PY_TAG="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
MARKER="$LIB/.bootstrapped-$PY_TAG"
if [[ ! -f "$MARKER" ]]; then
  log "bootstrapping deps with $PY (one-time, ~30s)..."
  rm -rf "$LIB"
  mkdir -p "$LIB"
  if ! "$PY" -m pip install --quiet --disable-pip-version-check \
      --target "$LIB" fastmcp httpx pydantic >&2; then
    log "ERROR: pip install failed."
    exit 1
  fi
  touch "$MARKER"
fi

export PYTHONPATH="$LIB:$DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m genealogy_mcp "$@"
