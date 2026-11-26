#!/usr/bin/env bash
# Launch the level editor (Linux / macOS). Works from any folder.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
echo "Starting the Pixaby level editor..."
exec python3 launch_level_editor.py "$@"
