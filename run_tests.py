#!/usr/bin/env python3
"""
Progetto RdC Pietro Zarbo - Script per eseguire test di performance
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
import time
from datetime import datetime

PROXY_IP = '10.0.1.3'
PROXY_PORT = 80
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

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


def ping_test(target_ip, count=3, timeout=5):
    """Esegue un ping test e restituisce i risultati."""
    try:
        cmd = ['ping', '-c', str(count), '-W', str(timeout), target_ip]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        output = result.stdout
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


def get_my_ips():
    """Restituisce gli IP locali dell'host corrente.

    Usa 'ip -4 addr show' invece di 'hostname -I' perche' quest'ultimo
    non funziona in modo affidabile nei namespace di rete di Mininet.
    """
    try:
        result = subprocess.run(['ip', '-4', 'addr', 'show'],
                                capture_output=True, text=True)
        ips = set()
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('inet '):
                ip = line.split()[1].split('/')[0]
                if ip != '127.0.0.1':
                    ips.add(ip)
        return ips
    except Exception:
        return set()


def test_throughput_load(duration=10):
    """Test 3: Throughput con carico - flussi simultanei."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Throughput sotto Carico (flussi simultanei)")
    print("=" * 60)

    my_ips = get_my_ips()
    targets = {
        name: ip for name, ip in {
            'H1': '192.168.1.1',
            'H3': '192.168.1.2',
            'H5': '192.168.1.3',
            'H6': '192.168.1.4',
        }.items() if ip not in my_ips
    }

    if not targets:
        print("  ERRORE: nessun target disponibile (tutti gli IP sono locali)")
        return

    os.makedirs(LOG_DIR, exist_ok=True)

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

        for name, ip, p, log_file in processes:
            stdout, stderr = p.communicate(timeout=duration + 30)
            output = stdout.decode().strip()

            if output:
                last_line = output.split('\n')[-1]
                fields = last_line.split(',')
                if len(fields) >= 9:
                    bw_mbps = int(fields[8]) / 1e6
                    print(f"    -> {name}: {bw_mbps:.2f} Mbps")
                    with open(log_file, 'w') as f:
                        f.write(output + '\n')
                else:
                    print(f"    -> {name}: output non valido")
            else:
                print(f"    -> {name}: FAILED")

        if num_flows < 3:
            time.sleep(2)


def get_my_vlan():
    """Determina la VLAN dell'host corrente in base all'IP."""
    my_ips = get_my_ips()
    for ip in my_ips:
        if ip.startswith('192.168.1.'):
            return 1
        if ip.startswith('192.168.2.'):
            return 2
    return None


def test_vlan_isolation():
    """Test 4: Verifica isolamento VLAN2."""
    print("\n" + "=" * 60)
    print("TEST 4: Verifica Isolamento VLAN2")
    print("=" * 60)

    my_vlan = get_my_vlan()
    my_ips = get_my_ips()
    print(f"  Host corrente: IP={my_ips}, VLAN={my_vlan if my_vlan else 'sconosciuta'}")

    # VLAN1: PROXY raggiungibile, S1/S2 bloccati da iptables (solo via PROXY)
    # VLAN2: PROXY, S1, S2 tutti bloccati dal firewall R1
    expected = {
        'PROXY': {1: 'success', 2: 'fail'},
        'S1':    {1: 'fail',    2: 'fail'},
        'S2':    {1: 'fail',    2: 'fail'},
    }

    external_targets = {
        'PROXY': '10.0.1.3',
        'S1': '10.0.1.2',
        'S2': '10.0.1.4',
    }

    all_ok = True
    for name, ip in external_targets.items():
        result = ping_test(ip, count=2, timeout=3)
        reachable = result['status'] == 'success'
        status_str = 'RAGGIUNGIBILE' if reachable else 'BLOCCATO'

        if my_vlan in (1, 2):
            exp = expected[name][my_vlan]
            correct = (reachable and exp == 'success') or (not reachable and exp == 'fail')
            verdict = 'OK' if correct else 'ERRORE'
            if not correct:
                all_ok = False
        else:
            verdict = '?'

        print(f"  -> {name} ({ip}): {status_str} [{verdict}]")

    if my_vlan == 1:
        print("\n  Da VLAN1 il PROXY deve essere raggiungibile,")
        print("  S1/S2 bloccati da iptables (accesso solo via PROXY).")
        print("  Per testare l'isolamento VLAN2 eseguire:")
        print(f"    h2 python3 {os.path.abspath(__file__)}")
    elif my_vlan == 2:
        print("\n  Da VLAN2 PROXY/S1/S2 devono essere tutti bloccati.")

    if all_ok and my_vlan:
        print("\n  Isolamento VLAN: CORRETTO")
    elif not all_ok:
        print("\n  ERRORE")


def test_proxy_access():
    """Test 5: Verifica che S1/S2 siano raggiungibili solo via PROXY."""
    print("\n" + "=" * 60)
    print("TEST 5: Verifica Accesso via PROXY")
    print("=" * 60)

    print("  Via PROXY:")
    for server in ['s1', 's2']:
        result = api_call(server, 'api/status', timeout=10)
        if 'error' not in result:
            print(f"    -> {server.upper()} via PROXY: OK ({result.get('status', 'unknown')})")
        else:
            print(f"    -> {server.upper()} via PROXY: FAILED ({result.get('error', '')})")

    print("  Accesso diretto (deve fallire):")
    for name, ip, port in [('S1', '10.0.1.2', 5001), ('S2', '10.0.1.4', 5002)]:
        try:
            cmd = ['curl', '-s', '-m', '5', f'http://{ip}:{port}/api/status']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                print(f"    -> {name} diretto: RAGGIUNGIBILE ERRORE")
            else:
                print(f"    -> {name} diretto: BLOCCATO (corretto)")
        except Exception:
            print(f"    -> {name} diretto: BLOCCATO (corretto)")


def main():
    """Esegue tutti i test in sequenza."""
    print("=" * 60)
    print("  Progetto RdC Pietro Zarbo - TEST DI PERFORMANCE")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)

    os.makedirs(LOG_DIR, exist_ok=True)

    test_connectivity()
    test_throughput_basic(duration=10)
    test_throughput_load(duration=10)
    test_vlan_isolation()
    test_proxy_access()

    print("\n" + "=" * 60)
    print("  TUTTI I TEST COMPLETATI")
    print(f"  Log salvati in: {LOG_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
