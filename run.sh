#!/bin/bash
# Always run using the project venv
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/venv/bin/activate"

if [ "$1" = "dashboard" ]; then
  python "$DIR/dashboard.py"
else
  python "$DIR/main.py" "$@"
fi
