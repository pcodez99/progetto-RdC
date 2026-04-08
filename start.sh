#!/bin/bash
# ===========================================================
# Script di avvio
# ===========================================================
# Uso: sudo ./start.sh
#
# Prerequisiti:
#   - Mininet / Containernet
#   - Ryu (installato nel venv locale: ./venv/)
#   - Flask, NGINX, iperf
#
# Configurazione:
#   Copia .env.example in .env e imposta i percorsi della tua macchina.
#   I valori nel .env possono essere sovrascritti con variabili d'ambiente:
#     sudo CONTAINERNET_VENV=/altro/path ./start.sh
# ===========================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Sotto sudo, $HOME diventa /root: recupera la home dell'utente reale
REAL_HOME="$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)"

# Carica .env se esiste (non sovrascrive variabili gia' impostate nell'ambiente)
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    HOME="$REAL_HOME" source "$SCRIPT_DIR/.env"
    set +a
fi

# Percorsi del venv Ryu (locale al progetto)
RYU_PYTHON="$(ls "$SCRIPT_DIR/venv/bin/python3"* 2>/dev/null | grep -E 'python3(\.[0-9]+)?$' | sort -V | tail -1)"
RYU_MANAGER="$SCRIPT_DIR/venv/bin/ryu-manager"

# Ricerca del venv di containernet/mininet
# Priorita': 1) CONTAINERNET_VENV da .env o ambiente, 2) path comuni, 3) mn di sistema
if [ -z "$CONTAINERNET_VENV" ]; then
    for candidate in \
        "$HOME/containernet/venv" \
        "/opt/containernet/venv" \
        "/usr/local/lib/containernet/venv"
    do
        if [ -x "$candidate/bin/python3" ]; then
            CONTAINERNET_VENV="$candidate"
            break
        fi
    done
fi

if [ -n "$CONTAINERNET_VENV" ] && [ -x "$CONTAINERNET_VENV/bin/python3" ]; then
    MININET_PYTHON="$CONTAINERNET_VENV/bin/python3"
    MN="$CONTAINERNET_VENV/bin/mn"
    export PATH="$CONTAINERNET_VENV/bin:$PATH"
else
    MININET_PYTHON="$(which python3)"
    MN="$(which mn 2>/dev/null || echo '')"
    if [ -z "$MN" ]; then
        echo "ERRORE: mn (mininet) non trovato."
        echo "  1) Copia .env.example in .env e imposta CONTAINERNET_VENV"
        echo "  2) Oppure: sudo CONTAINERNET_VENV=/path/to/venv ./start.sh"
        exit 1
    fi
fi

echo "=============================================="
echo "  Progetto RdC - Avvio Sistema di Rete"
echo "=============================================="

# Verifica root
if [ "$EUID" -ne 0 ]; then
    echo "ERRORE: Eseguire con sudo"
    echo "  sudo ./start.sh"
    exit 1
fi

# Cleanup precedente
echo "[1/5] Cleanup sessione Mininet precedente..."
"$MN" -c 2>/dev/null || true

# Kill processi precedenti
echo "[2/5] Kill processi precedenti..."
pkill -f ryu-manager 2>/dev/null || true
pkill -f flask_server 2>/dev/null || true
sleep 1

# Crea directory logs
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/graphs"
chown -R "${SUDO_USER:-$USER}":"${SUDO_USER:-$USER}" "$SCRIPT_DIR/logs" "$SCRIPT_DIR/graphs" 2>/dev/null || true

# Avvia controller Ryu
echo "[3/5] Avvio controller Ryu SDN..."
"$RYU_MANAGER" "$SCRIPT_DIR/vlan_controller.py" \
    --ofp-tcp-listen-port 6653 \
    2>&1 | tee "$SCRIPT_DIR/logs/ryu_controller.log" &
RYU_PID=$!
echo "  Controller Ryu avviato (PID: $RYU_PID)"

echo "[4/5] Attesa avvio controller (3 secondi)..."
sleep 3

# Verifica che Ryu sia ancora in esecuzione
if ! kill -0 $RYU_PID 2>/dev/null; then
    echo "ERRORE: Il controller Ryu non si e' avviato correttamente"
    echo "Controlla il log: $SCRIPT_DIR/logs/ryu_controller.log"
    exit 1
fi

# Avvia Mininet
echo "[5/5] Avvio topologia Mininet..."
echo ""
echo "=============================================="
echo "  Per i test di performance:"
echo "    h1 python3 $SCRIPT_DIR/run_tests.py"
echo ""
echo "  Per generare i grafici (dopo i test):"
echo "    exit (dalla CLI Mininet)"
echo "    $SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/analyze_results.py"
echo "=============================================="
echo ""

"$MININET_PYTHON" "$SCRIPT_DIR/topology.py"

# Cleanup alla chiusura
echo ""
echo "Cleanup..."
pkill -f ryu-manager 2>/dev/null || true
"$MN" -c 2>/dev/null || true
echo "Fatto."
