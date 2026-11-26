#!/usr/bin/env bash
# Launch the game (Linux / macOS). Works from any folder.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
echo "Starting Pixaby..."
exec python3 pixaby.py "$@"
