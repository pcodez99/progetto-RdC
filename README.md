# Progetto Reti di Calcolatori

Topologia SDN con VLAN, routing L3, firewall e reverse proxy.

## Prerequisiti

- [Containernet](mininet-install.md) installato (fornisce `mn` e `python3` con Mininet)
- Python 3.8 o 3.9 installato nel sistema (richiesto da Ryu)
- `nginx`, `iperf` installati nel sistema

## Avvio

```bash
# 1. Setup (solo la prima volta)
./setup.sh

# 2. Controlla/modifica i path in .env
nano .env

# 3. Avvia
sudo ./start.sh
```

## Test

Dalla CLI Mininet:

```
h1 python3 /path/to/run_tests.py
```

Dopo aver chiuso Mininet (`exit`):

```bash
python3 analyze_results.py
```
