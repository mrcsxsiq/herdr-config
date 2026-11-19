#!/bin/sh
# One command to install this Herdr configuration. Everything is in scripts/install.py.
# Options: --dry-run --yes --switch-layout --claude-extras --no-check --home DIR --src-dir DIR
exec python3 "$(dirname "$0")/scripts/install.py" "$@"
