#!/bin/bash
# Peluncur Melolo Linux — membuka GUI oleh default.
# Pemakaian:
#   ./buka.sh                 -> buka aplikasi GUI
#   ./buka.sh cli <perintah>  -> jalankan CLI (misal: ./buka.sh cli categories)
cd "$(dirname "$0")"
# Lingkungan ini punya QT_QPA_PLATFORM=wayland yang membuat jendela tidak muncul;
# paksa xcb agar Qt memakai X11 (DISPLAY=:0).
export QT_QPA_PLATFORM=xcb

if [ "$1" = "cli" ]; then
  shift
  python3 melolo_client.py "$@"
else
  exec python3 melolo_gui.py
fi
