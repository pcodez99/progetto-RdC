#!/usr/bin/env python3
"""
Progetto RdC Pietro Zarbo - Server Flask per test iperf TCP
Esegue su S1 e S2. Fornisce API REST per lanciare test di throughput TCP
verso tutti i nodi della topologia, con logging CSV.

Avvio:
  python3 flask_server.py --port 5001 --name S1 --logdir ./logs
  python3 flask_server.py --port 5002 --name S2 --logdir ./logs
"""

import argparse
import csv
import os
import subprocess
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

SERVER_NAME = 'S1'
SERVER_PORT = 5001
LOG_DIR = './logs'

# H2/H4 esclusi: bloccati dal firewall R1 (10.0.1.0/24 → 192.168.2.0/24 DROP)
# S1/S2 esclusi: iptables su ciascuno accetta solo connessioni dal PROXY
TARGETS = {
    'H1': '192.168.1.1',
    'H3': '192.168.1.2',
    'H5': '192.168.1.3',
    'H6': '192.168.1.4',
    'H7': '192.168.1.5',
    'PROXY': '10.0.1.3',
}

IPERF_PORT = 5201


def run_iperf_test(target_ip, duration=10):
    """Esegue un test iperf TCP verso il target e restituisce i risultati."""
    try:
        cmd = [
            'iperf', '-c', target_ip,
            '-p', str(IPERF_PORT),
            '-t', str(duration),
            '-y', 'C'
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=duration + 30
        )

        if result.returncode != 0:
            return {
                'status': 'error',
                'target': target_ip,
                'error': result.stderr.strip() or 'Connection failed',
                'bandwidth_bps': 0
            }

        # Formato CSV iperf: timestamp,src_ip,src_port,dst_ip,dst_port,
        #                     transfer_id,interval,transfer_bytes,bandwidth_bps
        output = result.stdout.strip()
        if not output:
            return {
                'status': 'error',
                'target': target_ip,
                'error': 'No output from iperf',
                'bandwidth_bps': 0
            }

        last_line = output.split('\n')[-1]
        fields = last_line.split(',')

        if len(fields) >= 9:
            return {
                'status': 'success',
                'target': target_ip,
                'timestamp': fields[0],
                'source_ip': fields[1],
                'source_port': fields[2],
                'dest_ip': fields[3],
                'dest_port': fields[4],
                'interval': fields[6],
                'transfer_bytes': int(fields[7]),
                'bandwidth_bps': int(fields[8]),
                'bandwidth_mbps': round(int(fields[8]) / 1e6, 2),
                'raw_csv': output
            }
        else:
            return {
                'status': 'error',
                'target': target_ip,
                'error': f'Unexpected output format: {last_line}',
                'bandwidth_bps': 0
            }

    except subprocess.TimeoutExpired:
        return {
            'status': 'error',
            'target': target_ip,
            'error': 'Timeout',
            'bandwidth_bps': 0
        }
    except FileNotFoundError:
        return {
            'status': 'error',
            'target': target_ip,
            'error': 'iperf not found',
            'bandwidth_bps': 0
        }


def log_result(result, target_name):
    """Salva il risultato in un file CSV di log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f'{SERVER_NAME}_throughput.csv')
    file_exists = os.path.exists(log_file)

    with open(log_file, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'timestamp', 'server', 'target_name', 'target_ip',
                'status', 'transfer_bytes', 'bandwidth_bps',
                'bandwidth_mbps', 'error'
            ])
        writer.writerow([
            datetime.now().isoformat(),
            SERVER_NAME,
            target_name,
            result.get('target', ''),
            result.get('status', ''),
            result.get('transfer_bytes', 0),
            result.get('bandwidth_bps', 0),
            result.get('bandwidth_mbps', 0),
            result.get('error', '')
        ])


@app.route('/api/throughput', methods=['GET'])
def throughput_all():
    """
    Esegue test iperf verso tutti i nodi della topologia.
    Query params:
      - duration: durata test in secondi (default 10)
      - exclude_self: esclude il server stesso (default true)
    """
    duration = request.args.get('duration', 10, type=int)
    exclude_self = request.args.get('exclude_self', 'true').lower() == 'true'

    results = {}
    for name, ip in TARGETS.items():
        if exclude_self and name == SERVER_NAME:
            continue

        app.logger.info(f'Test throughput verso {name} ({ip})...')
        result = run_iperf_test(ip, duration)
        result['target_name'] = name
        results[name] = result
        log_result(result, name)

    return jsonify({
        'server': SERVER_NAME,
        'timestamp': datetime.now().isoformat(),
        'duration_seconds': duration,
        'results': results
    })


@app.route('/api/throughput/<target>', methods=['GET'])
def throughput_single(target):
    """
    Esegue test iperf verso un nodo specifico.
    target puo' essere un nome (H1, H3, ...) o un IP.
    Query params:
      - duration: durata test in secondi (default 10)
    """
    duration = request.args.get('duration', 10, type=int)

    if target.upper() in TARGETS:
        target_name = target.upper()
        target_ip = TARGETS[target_name]
    else:
        target_name = target
        target_ip = target

    app.logger.info(f'Test throughput verso {target_name} ({target_ip})...')
    result = run_iperf_test(target_ip, duration)
    result['target_name'] = target_name
    log_result(result, target_name)

    return jsonify({
        'server': SERVER_NAME,
        'timestamp': datetime.now().isoformat(),
        'duration_seconds': duration,
        'result': result
    })


@app.route('/api/results', methods=['GET'])
def get_results():
    """Restituisce i log CSV dei test precedenti."""
    log_file = os.path.join(LOG_DIR, f'{SERVER_NAME}_throughput.csv')

    if not os.path.exists(log_file):
        return jsonify({'server': SERVER_NAME, 'results': [], 'message': 'No logs yet'})

    results = []
    with open(log_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)

    return jsonify({
        'server': SERVER_NAME,
        'total_tests': len(results),
        'results': results
    })


@app.route('/api/status', methods=['GET'])
def status():
    """Health check."""
    return jsonify({
        'server': SERVER_NAME,
        'status': 'running',
        'port': SERVER_PORT,
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Flask iperf test server')
    parser.add_argument('--port', type=int, default=5001, help='Porta Flask')
    parser.add_argument('--name', type=str, default='S1', help='Nome server (S1 o S2)')
    parser.add_argument('--logdir', type=str, default='./logs', help='Directory log')
    args = parser.parse_args()

    SERVER_NAME = args.name
    SERVER_PORT = args.port
    LOG_DIR = args.logdir

    os.makedirs(LOG_DIR, exist_ok=True)

    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)
