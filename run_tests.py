#!/usr/bin/env python3
"""
Progetto 11 - Script per eseguire test di performance
Da eseguire DENTRO Mininet dopo che la rete e' attiva.

Questo script viene eseguito da un host VLAN1 (es. H1) e:
1. Verifica la connettivita tra i nodi (ping)
2. Invoca l'API REST su S1/S2 tramite il PROXY per lanciare test iperf
3. Esegue test di carico con flussi simultanei
4. Salva tutti i risultati in logs/

Uso da CLI Mininet:
  h1 python3 /path/to/run_tests.py
"""

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# Configurazione
PROXY_IP = '10.0.1.3'
PROXY_PORT = 80
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

# Nodi della topologia per test di connettivita
ALL_NODES = {
    'H1': '192.168.1.1',
    'H2': '192.168.2.1',
    'H3': '192.168.1.2',
    'H4': '192.168.2.2',
    'H5': '192.168.1.3',
    'H6': '192.168.1.4',
    'H7': '192.168.1.5',
    'R1_VLAN1': '192.168.1.254',
    'R2': '10.0.1.1',
    'S1': '10.0.1.2',
    'PROXY': '10.0.1.3',
    'S2': '10.0.1.4',
}

VLAN1_HOSTS = ['H1', 'H3', 'H5', 'H6', 'H7']
VLAN2_HOSTS = ['H2', 'H4']


def ping_test(target_ip, count=3, timeout=5):
    """Esegue un ping test e restituisce i risultati."""
    try:
        cmd = ['ping', '-c', str(count), '-W', str(timeout), target_ip]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        output = result.stdout
        # Parsa RTT dalla riga "rtt min/avg/max/mdev = ..."
        rtt_line = [l for l in output.split('\n') if 'rtt' in l or 'round-trip' in l]
        if rtt_line:
            parts = rtt_line[0].split('=')[1].strip().split('/')
            return {
                'status': 'success',
                'target': target_ip,
                'rtt_min': float(parts[0]),
                'rtt_avg': float(parts[1]),
                'rtt_max': float(parts[2]),
                'packet_loss': 0
            }

        # Controlla packet loss
        loss_line = [l for l in output.split('\n') if 'packet loss' in l]
        if loss_line:
            loss = loss_line[0].split('%')[0].split()[-1]
            return {
                'status': 'failed' if float(loss) == 100 else 'partial',
                'target': target_ip,
                'packet_loss': float(loss),
                'rtt_min': 0, 'rtt_avg': 0, 'rtt_max': 0
            }

        return {'status': 'failed', 'target': target_ip, 'packet_loss': 100,
                'rtt_min': 0, 'rtt_avg': 0, 'rtt_max': 0}

    except (subprocess.TimeoutExpired, Exception) as e:
        return {'status': 'error', 'target': target_ip, 'error': str(e),
                'packet_loss': 100, 'rtt_min': 0, 'rtt_avg': 0, 'rtt_max': 0}


def api_call(server, endpoint, timeout=600):
    """Chiama l'API REST tramite il PROXY."""
    url = f'http://{PROXY_IP}:{PROXY_PORT}/{server}/{endpoint}'
    try:
        cmd = ['curl', '-s', '-m', str(timeout), url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return {'error': result.stderr or 'Empty response'}
    except Exception as e:
        return {'error': str(e)}


def test_connectivity():
    """Test 1: Verifica connettivita tra nodi (ping)."""
    print("=" * 60)
    print("TEST 1: Verifica Connettivita (Ping)")
    print("=" * 60)

    results = []
    for name, ip in ALL_NODES.items():
        result = ping_test(ip)
        result['target_name'] = name
        results.append(result)

        status = 'OK' if result['status'] == 'success' else 'FAIL'
        rtt = f"RTT={result['rtt_avg']:.1f}ms" if result['status'] == 'success' else ''
        print(f"  {name:15s} ({ip:15s}) -> {status:5s} {rtt}")

    # Salva risultati
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, 'connectivity_test.csv'), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'target_name', 'target_ip', 'status',
                         'rtt_min', 'rtt_avg', 'rtt_max', 'packet_loss'])
        for r in results:
            writer.writerow([
                datetime.now().isoformat(), r['target_name'], r['target'],
                r['status'], r['rtt_min'], r['rtt_avg'], r['rtt_max'],
                r['packet_loss']
            ])

    print(f"\n  Risultati salvati in {LOG_DIR}/connectivity_test.csv")
    return results


def test_throughput_basic(duration=10):
    """Test 2: Throughput base da S1 e S2 verso tutti i nodi."""
    print("\n" + "=" * 60)
    print(f"TEST 2: Throughput Base (durata {duration}s per test)")
    print("=" * 60)

    for server in ['s1', 's2']:
        print(f"\n  --- Test da {server.upper()} ---")
        result = api_call(server, f'api/throughput?duration={duration}')

        if 'error' in result:
            print(f"  ERRORE: {result['error']}")
            continue

        if 'results' in result:
            for name, data in result['results'].items():
                status = data.get('status', 'unknown')
                bw = data.get('bandwidth_mbps', 0)
                if status == 'success':
                    print(f"    -> {name:15s}: {bw:>10.2f} Mbps")
                else:
                    err = data.get('error', 'unknown')
                    print(f"    -> {name:15s}: FAILED ({err})")

    print(f"\n  Risultati salvati nei log CSV dei server")


def test_throughput_load(duration=10):
    """Test 3: Throughput con carico - flussi simultanei."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Throughput sotto Carico (flussi simultanei)")
    print("=" * 60)

    # Lancia test simultanei da S1 verso piu host VLAN1
    # Usiamo iperf direttamente per il parallelismo
    targets = {
        'H1': '192.168.1.1',
        'H3': '192.168.1.2',
        'H5': '192.168.1.3',
    }

    os.makedirs(LOG_DIR, exist_ok=True)

    # Test con 1, 2, 3 flussi simultanei
    for num_flows in [1, 2, 3]:
        print(f"\n  --- {num_flows} flusso/i simultaneo/i ---")
        flow_targets = list(targets.items())[:num_flows]

        processes = []
        for name, ip in flow_targets:
            log_file = os.path.join(LOG_DIR, f'load_test_{num_flows}flows_{name}.csv')
            cmd = [
                'iperf', '-c', ip, '-p', '5201',
                '-t', str(duration), '-y', 'C'
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append((name, ip, p, log_file))

        # Attendi completamento
        for name, ip, p, log_file in processes:
            stdout, stderr = p.communicate(timeout=duration + 30)
            output = stdout.decode().strip()

            if output:
                last_line = output.split('\n')[-1]
                fields = last_line.split(',')
                if len(fields) >= 9:
                    bw_mbps = int(fields[8]) / 1e6
                    print(f"    -> {name}: {bw_mbps:.2f} Mbps")

                    # Salva CSV
                    with open(log_file, 'w') as f:
                        f.write(output + '\n')
                else:
                    print(f"    -> {name}: output non valido")
            else:
                print(f"    -> {name}: FAILED")

        # Pausa tra i test
        if num_flows < 3:
            time.sleep(2)


def test_vlan_isolation():
    """Test 4: Verifica isolamento VLAN2."""
    print("\n" + "=" * 60)
    print("TEST 4: Verifica Isolamento VLAN2")
    print("=" * 60)

    print("  Nota: questo test verifica che VLAN2 NON puo' raggiungere")
    print("  la Service Network. Eseguire da un host VLAN2 (H2 o H4).")
    print("  Da CLI Mininet:")
    print("    h2 ping -c 3 10.0.1.3   (deve fallire)")
    print("    h2 ping -c 3 192.168.1.1 (deve funzionare - verso VLAN1)")
    print("    h4 ping -c 3 10.0.1.3   (deve fallire)")

    # Verifica dal nodo corrente
    external_targets = {
        'PROXY': '10.0.1.3',
        'S1': '10.0.1.2',
        'S2': '10.0.1.4',
    }

    for name, ip in external_targets.items():
        result = ping_test(ip, count=2, timeout=3)
        status = 'RAGGIUNGIBILE' if result['status'] == 'success' else 'BLOCCATO'
        print(f"  -> {name} ({ip}): {status}")


def test_proxy_access():
    """Test 5: Verifica che S1/S2 siano raggiungibili solo via PROXY."""
    print("\n" + "=" * 60)
    print("TEST 5: Verifica Accesso via PROXY")
    print("=" * 60)

    # Accesso tramite PROXY (deve funzionare da VLAN1)
    print("  Via PROXY:")
    for server in ['s1', 's2']:
        result = api_call(server, 'api/status', timeout=10)
        if 'error' not in result:
            print(f"    -> {server.upper()} via PROXY: OK ({result.get('status', 'unknown')})")
        else:
            print(f"    -> {server.upper()} via PROXY: FAILED ({result.get('error', '')})")

    # Accesso diretto (deve fallire)
    print("  Accesso diretto (deve fallire):")
    for name, ip, port in [('S1', '10.0.1.2', 5001), ('S2', '10.0.1.4', 5002)]:
        try:
            cmd = ['curl', '-s', '-m', '5', f'http://{ip}:{port}/api/status']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                print(f"    -> {name} diretto: RAGGIUNGIBILE (ERRORE: dovrebbe essere bloccato!)")
            else:
                print(f"    -> {name} diretto: BLOCCATO (corretto)")
        except Exception:
            print(f"    -> {name} diretto: BLOCCATO (corretto)")


def main():
    """Esegue tutti i test in sequenza."""
    print("=" * 60)
    print("  PROGETTO 11 - TEST DI PERFORMANCE")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)

    os.makedirs(LOG_DIR, exist_ok=True)

    # Test 1: Connettivita
    test_connectivity()

    # Test 2: Throughput base
    test_throughput_basic(duration=10)

    # Test 3: Throughput sotto carico
    test_throughput_load(duration=10)

    # Test 4: Isolamento VLAN2
    test_vlan_isolation()

    # Test 5: Accesso via PROXY
    test_proxy_access()

    print("\n" + "=" * 60)
    print("  TUTTI I TEST COMPLETATI")
    print(f"  Log salvati in: {LOG_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
