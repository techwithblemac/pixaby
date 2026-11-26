#!/usr/bin/env bash
# Z_clean.sh - remove Python cache files and "tests" folders from the project.
# (This replaces clean.py, which no longer exists.)
#
# Usage (from anywhere):
#   ./Z_clean.sh                  clean this project folder (asks first)
#   ./Z_clean.sh path/to/project  clean another folder
#   ./Z_clean.sh --dry-run        list what would be removed, delete nothing
#   ./Z_clean.sh --yes            don't ask for confirmation
#   ./Z_clean.sh --keep-tests     only clear caches, leave "tests" folders alone
#
# Removed: __pycache__, .pytest_cache, .mypy_cache, .ruff_cache, *.pyc, *.pyo
# and every folder named "tests". Never searched: .git .hg .svn venv .venv env
# node_modules.

DRY=0; YES=0; KEEP_TESTS=0; ROOT=""
for arg in "$@"; do
    case "$arg" in
        --dry-run)       DRY=1 ;;
        -y|--yes)        YES=1 ;;
        --keep-tests)    KEEP_TESTS=1 ;;
        -h|--help)       sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)              echo "Unknown option: $arg (try --help)"; exit 1 ;;
        *)               ROOT="$arg" ;;
    esac
done

[ -z "$ROOT" ] && ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$ROOT" ] || { echo "Not a folder: $ROOT"; exit 1; }
ROOT="$(cd "$ROOT" && pwd)"

echo "Cleaning up the game environment..."
echo "Project: $ROOT"
echo

# Build the list. A matching folder is printed and then pruned, so nothing
# inside an item that is already going to be deleted is listed twice.
DIRS=( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache )
[ "$KEEP_TESTS" -eq 0 ] && DIRS+=( -o -name tests )

mapfile -d '' TARGETS < <(
    find "$ROOT" \
        \( -name .git -o -name .hg -o -name .svn -o -name venv -o -name .venv -o -name env -o -name node_modules \) -prune -o \
        -type d \( "${DIRS[@]}" \) -print0 -prune -o \
        -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0
)

if [ "${#TARGETS[@]}" -eq 0 ]; then
    echo "Nothing to clean."
else
    for t in "${TARGETS[@]}"; do
        if [ -d "$t" ]; then echo "  [dir]  ${t#"$ROOT"/}"; else echo "  [file] ${t#"$ROOT"/}"; fi
    done
    echo
    echo "${#TARGETS[@]} item(s) found."

    if [ "$DRY" -eq 1 ]; then
        echo "Dry run - nothing deleted."
    else
        go=1
        if [ "$YES" -eq 0 ]; then
            read -r -p "Delete these? [y/N] " answer
            case "$answer" in y|Y) ;; *) go=0 ;; esac
        fi
        if [ "$go" -eq 0 ]; then
            echo "Cancelled."
        else
            failed=0
            for t in "${TARGETS[@]}"; do
                rm -rf -- "$t" || { failed=$((failed + 1)); echo "  Could not remove ${t#"$ROOT"/}"; }
            done
            echo "Done. Removed $(( ${#TARGETS[@]} - failed )) item(s)$([ "$failed" -gt 0 ] && echo ", $failed failed")."
        fi
    fi
fi

# keep the window open when launched by double-click, like the other Z_ scripts
if [ -t 0 ] && [ "$YES" -eq 0 ]; then
    echo "Press Q to quit"
    while true; do
        read -n 1 -s key
        if [[ $key == "q" || $key == "Q" ]]; then
            echo "Closing..."
            exit 0
        fi
    done
fi
