#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

cd "$ROOT_DIR"
uv run python scripts/db/doctor_url.py
