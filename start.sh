#!/bin/bash
# ===========================================================
# Progetto 11 - Script di avvio completo
# ===========================================================
# Uso: sudo ./start.sh
#
# Prerequisiti:
#   - Mininet installato
#   - Ryu installato (pip install ryu)
#   - Flask installato (pip install flask)
#   - NGINX installato (apt install nginx)
#   - iperf installato (apt install iperf)
#   - matplotlib e pandas (pip install matplotlib pandas numpy)
# ===========================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================="
echo "  Progetto 11 - Avvio Sistema di Rete"
echo "=============================================="

# Verifica root
if [ "$EUID" -ne 0 ]; then
    echo "ERRORE: Eseguire con sudo"
    echo "Uso: sudo ./start.sh"
    exit 1
fi

# Cleanup precedente
echo "[1/5] Cleanup sessione Mininet precedente..."
mn -c 2>/dev/null || true

# Kill processi precedenti
echo "[2/5] Kill processi precedenti..."
pkill -f ryu-manager 2>/dev/null || true
pkill -f flask_server 2>/dev/null || true
sleep 1

# Crea directory logs
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/graphs"

# Avvia controller Ryu
echo "[3/5] Avvio controller Ryu SDN..."
ryu-manager "$SCRIPT_DIR/vlan_controller.py" \
    --ofp-tcp-listen-port 6653 \
    --verbose 2>&1 | tee "$SCRIPT_DIR/logs/ryu_controller.log" &
RYU_PID=$!
echo "  Controller Ryu avviato (PID: $RYU_PID)"

# Attendi che il controller sia pronto
echo "[4/5] Attesa avvio controller (3 secondi)..."
sleep 3

# Verifica che Ryu sia ancora in esecuzione
if ! kill -0 $RYU_PID 2>/dev/null; then
    echo "ERRORE: Il controller Ryu non si e' avviato correttamente"
    echo "Controlla il log: $SCRIPT_DIR/logs/ryu_controller.log"
    exit 1
fi

# Avvia topologia Mininet
echo "[5/5] Avvio topologia Mininet..."
echo ""
echo "=============================================="
echo "  La CLI di Mininet si aprira' a breve."
echo "  Comandi utili:"
echo "    pingall              - Test connettivita"
echo "    h1 ping h3           - Ping VLAN1<->VLAN1"
echo "    h1 ping h2           - Ping VLAN1<->VLAN2"
echo "    h2 ping 10.0.1.3    - VLAN2->esterno (BLOCCATO)"
echo ""
echo "  Per i test di performance:"
echo "    h1 python3 $SCRIPT_DIR/run_tests.py"
echo ""
echo "  Per generare i grafici (dopo i test):"
echo "    exit (dalla CLI Mininet)"
echo "    python3 $SCRIPT_DIR/analyze_results.py"
echo "=============================================="
echo ""

python3 "$SCRIPT_DIR/topology.py"

# Cleanup alla chiusura
echo ""
echo "Cleanup..."
pkill -f ryu-manager 2>/dev/null || true
mn -c 2>/dev/null || true
echo "Fatto."
