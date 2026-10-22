#!/usr/bin/env bash
# Entry point for dotenv Manager. Delegates to the stdlib-only Python source.
set -eu

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/src/dotenv_manager.py" "$@"
