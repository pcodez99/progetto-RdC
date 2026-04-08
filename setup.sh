#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Crea .env se non esiste
[ ! -f "$SCRIPT_DIR/.env" ] && cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"

# Carica .env
set -a; source "$SCRIPT_DIR/.env"; set +a

# Crea venv Ryu con il python specificato in .env
"${RYU_PYTHON:-python3.9}" -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

echo "Setup completato. Modifica .env se necessario, poi: sudo ./start.sh"
