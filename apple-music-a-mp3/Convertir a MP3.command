#!/bin/bash
# Mac: haz doble clic en este archivo para abrir el convertidor en el Terminal.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Necesitas Python 3: https://www.python.org/downloads/"
  read -r -p "Pulsa Intro para salir..."
  exit 1
fi
exec python3 biblioteca_a_mp3.py "$@"
