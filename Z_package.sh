echo "Starting Build..."

python -m PyInstaller --onedir --windowed --icon=assets/icons/icon.ico pixaby.py
python -m PyInstaller --onedir --windowed --icon=assets/icons/icon_2.ico launch_level_editor.py

echo "Press Q to quit"
while true; do
    read -n 1 -s key
    if [[ $key == "q" || $key == "Q" ]]; then
        echo "Closing..."
        exit 0
    fi
done