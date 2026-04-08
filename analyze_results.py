#!/usr/bin/env python3
"""
Progetto RdC Pietro Zarbo - Analisi risultati e generazione grafici
Legge i log CSV prodotti dai test iperf e genera grafici con matplotlib.

Uso:
  python3 analyze_results.py [--logdir ./logs] [--outdir ./graphs]
"""

import argparse
import csv
import glob
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# Configurazione
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
GRAPH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'graphs')

# Ritardi attesi (one-way) in ms dalla topologia
EXPECTED_RTT = {
    # Da S1/S2 (Service Network) verso i nodi
    # Service -> R2: 1ms, R2 -> R1: 60ms, R1 -> SW: 5ms, SW -> Host: 5ms
    # RTT = 2 * (1 + 60 + 5 + 5) = 142ms per host intranet via R1
    'H1': 142, 'H2': 142, 'H3': 142, 'H4': 142, 'H5': 142, 'H6': 142, 'H7': 142,
    # Service -> R2: 1ms, R2 -> R1: 60ms
    'R1_VLAN1': 132, 'R1_WAN': 122,
    # Service -> R2: 1ms
    'R2': 4, 'R2_WAN': 122, 'R2_SVC': 4,
    # Locale service network: 1ms + 1ms
    'S1': 4, 'S2': 4, 'PROXY': 4,
}


def load_throughput_csv(filepath):
    """Carica un file CSV di throughput."""
    results = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row['bandwidth_mbps'] = float(row.get('bandwidth_mbps', 0))
                row['bandwidth_bps'] = int(row.get('bandwidth_bps', 0))
                row['transfer_bytes'] = int(row.get('transfer_bytes', 0))
            except (ValueError, TypeError):
                row['bandwidth_mbps'] = 0
                row['bandwidth_bps'] = 0
                row['transfer_bytes'] = 0
            results.append(row)
    return results


def load_connectivity_csv(filepath):
    """Carica il file CSV dei test di connettivita."""
    results = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row['rtt_avg'] = float(row.get('rtt_avg', 0))
                row['rtt_min'] = float(row.get('rtt_min', 0))
                row['rtt_max'] = float(row.get('rtt_max', 0))
                row['packet_loss'] = float(row.get('packet_loss', 0))
            except (ValueError, TypeError):
                pass
            results.append(row)
    return results


def plot_throughput_by_destination(data, server_name, outdir):
    """Grafico 1: Throughput medio per destinazione (bar chart)."""
    # Filtra solo test riusciti
    successful = [r for r in data if r.get('status') == 'success']
    if not successful:
        print(f"  Nessun test riuscito per {server_name}, skip grafico throughput")
        return

    # Raggruppa per target
    targets = {}
    for r in successful:
        name = r.get('target_name', r.get('target_ip', 'unknown'))
        if name not in targets:
            targets[name] = []
        targets[name].append(r['bandwidth_mbps'])

    names = list(targets.keys())
    means = [np.mean(v) for v in targets.values()]
    stds = [np.std(v) if len(v) > 1 else 0 for v in targets.values()]

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(range(len(names)), means, yerr=stds, capsize=5,
                  color='steelblue', edgecolor='navy', alpha=0.8)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_ylabel('Throughput (Mbps)')
    ax.set_title(f'Throughput TCP per Destinazione - Server {server_name}')
    ax.grid(axis='y', alpha=0.3)

    # Aggiungi valori sopra le barre
    for bar, mean in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                f'{mean:.1f}', ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    filepath = os.path.join(outdir, f'throughput_by_dest_{server_name}.png')
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Salvato: {filepath}")


def plot_rtt_comparison(conn_data, outdir):
    """Grafico 2: RTT misurato vs atteso."""
    successful = [r for r in conn_data if r.get('status') == 'success']
    if not successful:
        print("  Nessun test connettivita riuscito, skip grafico RTT")
        return

    names = []
    measured = []
    expected = []

    for r in successful:
        name = r['target_name']
        names.append(name)
        measured.append(r['rtt_avg'])
        expected.append(EXPECTED_RTT.get(name, 0))

    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 6))
    bars1 = ax.bar(x - width/2, measured, width, label='Misurato',
                   color='steelblue', edgecolor='navy', alpha=0.8)
    bars2 = ax.bar(x + width/2, expected, width, label='Atteso (teoria)',
                   color='coral', edgecolor='darkred', alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_ylabel('RTT (ms)')
    ax.set_title('RTT Misurato vs Atteso')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    filepath = os.path.join(outdir, 'rtt_comparison.png')
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Salvato: {filepath}")


def plot_connectivity_matrix(conn_data, outdir):
    """Grafico 3: Matrice di raggiungibilita (heatmap)."""
    if not conn_data:
        return

    names = [r['target_name'] for r in conn_data]
    reachable = [1 if r['status'] == 'success' else 0 for r in conn_data]

    fig, ax = plt.subplots(figsize=(10, 2))
    data_matrix = np.array([reachable])

    im = ax.imshow(data_matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_yticks([0])
    ax.set_yticklabels(['Raggiungibile'])
    ax.set_title('Matrice di Raggiungibilita dalla sorgente del test')

    # Annota celle
    for j, val in enumerate(reachable):
        text = 'OK' if val == 1 else 'NO'
        color = 'white' if val == 0 else 'black'
        ax.text(j, 0, text, ha='center', va='center', fontweight='bold',
                color=color)

    plt.tight_layout()
    filepath = os.path.join(outdir, 'connectivity_matrix.png')
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Salvato: {filepath}")


def plot_load_test(logdir, outdir):
    """Grafico 4: Effetto del carico (flussi simultanei)."""
    # Cerca file load_test_*flows_*.csv
    load_files = glob.glob(os.path.join(logdir, 'load_test_*flows_*.csv'))
    if not load_files:
        print("  Nessun file load test trovato, skip grafico carico")
        return

    # Organizza: {num_flows: {target: bandwidth}}
    results = {}
    for filepath in load_files:
        basename = os.path.basename(filepath)
        # Formato: load_test_Nflows_TARGET.csv
        parts = basename.replace('.csv', '').split('_')
        num_flows_str = parts[2]  # es. "1flows" o "2flows"
        num_flows = int(num_flows_str.replace('flows', ''))
        target = parts[3]

        with open(filepath, 'r') as f:
            content = f.read().strip()
            if content:
                last_line = content.split('\n')[-1]
                fields = last_line.split(',')
                if len(fields) >= 9:
                    bw_mbps = int(fields[8]) / 1e6
                    if num_flows not in results:
                        results[num_flows] = {}
                    results[num_flows][target] = bw_mbps

    if not results:
        return

    # Grafico: throughput per target al variare dei flussi
    all_targets = set()
    for flows_data in results.values():
        all_targets.update(flows_data.keys())
    all_targets = sorted(all_targets)

    fig, ax = plt.subplots(figsize=(10, 6))
    num_flows_list = sorted(results.keys())
    x = np.arange(len(num_flows_list))
    width = 0.2
    offset = 0

    for target in all_targets:
        values = [results.get(nf, {}).get(target, 0) for nf in num_flows_list]
        ax.bar(x + offset, values, width, label=target, alpha=0.8)
        offset += width

    ax.set_xticks(x + width * (len(all_targets) - 1) / 2)
    ax.set_xticklabels([f'{n} flusso/i' for n in num_flows_list])
    ax.set_ylabel('Throughput (Mbps)')
    ax.set_title('Effetto del Carico: Throughput con Flussi Simultanei')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    filepath = os.path.join(outdir, 'load_test_comparison.png')
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Salvato: {filepath}")


def plot_packet_loss(conn_data, outdir):
    """Grafico 5: Packet loss per destinazione."""
    if not conn_data:
        return

    names = [r['target_name'] for r in conn_data]
    losses = [r.get('packet_loss', 0) for r in conn_data]

    if all(l == 0 or l == 100 for l in losses):
        # Solo 0% o 100% - non molto interessante come grafico
        # ma lo generiamo comunque
        pass

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = ['green' if l == 0 else 'red' if l == 100 else 'orange' for l in losses]
    ax.bar(range(len(names)), losses, color=colors, edgecolor='black', alpha=0.8)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_ylabel('Packet Loss (%)')
    ax.set_title('Packet Loss per Destinazione')
    ax.set_ylim(0, 110)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    filepath = os.path.join(outdir, 'packet_loss.png')
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Salvato: {filepath}")


def plot_throughput_summary(all_data, outdir):
    """Grafico 6: Confronto throughput S1 vs S2."""
    if not all_data:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    servers = list(all_data.keys())
    x_offset = 0
    width = 0.35

    for i, server in enumerate(servers):
        data = all_data[server]
        successful = [r for r in data if r.get('status') == 'success']
        if not successful:
            continue

        targets = {}
        for r in successful:
            name = r.get('target_name', 'unknown')
            if name not in targets:
                targets[name] = []
            targets[name].append(r['bandwidth_mbps'])

        names = list(targets.keys())
        means = [np.mean(v) for v in targets.values()]

        x = np.arange(len(names))
        ax.bar(x + i * width, means, width, label=server, alpha=0.8)

    if servers:
        # Usa il set di nomi dal primo server
        first_data = all_data[servers[0]]
        first_successful = [r for r in first_data if r.get('status') == 'success']
        if first_successful:
            first_targets = list(dict.fromkeys(
                r.get('target_name', 'unknown') for r in first_successful
            ))
            ax.set_xticks(np.arange(len(first_targets)) + width / 2)
            ax.set_xticklabels(first_targets, rotation=45, ha='right')

    ax.set_ylabel('Throughput (Mbps)')
    ax.set_title('Confronto Throughput: S1 vs S2')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    filepath = os.path.join(outdir, 'throughput_s1_vs_s2.png')
    plt.savefig(filepath, dpi=150)
    plt.close()
    print(f"  Salvato: {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Analisi risultati e grafici')
    parser.add_argument('--logdir', default=LOG_DIR, help='Directory log CSV')
    parser.add_argument('--outdir', default=GRAPH_DIR, help='Directory output grafici')
    args = parser.parse_args()

    logdir = args.logdir
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    print("=" * 60)
    print("  ANALISI RISULTATI E GENERAZIONE GRAFICI")
    print("=" * 60)

    # Carica dati throughput per ogni server
    all_throughput = {}
    for server in ['S1', 'S2']:
        filepath = os.path.join(logdir, f'{server}_throughput.csv')
        if os.path.exists(filepath):
            data = load_throughput_csv(filepath)
            all_throughput[server] = data
            print(f"\n  Caricati {len(data)} record da {server}")

            # Grafico 1: Throughput per destinazione
            plot_throughput_by_destination(data, server, outdir)
        else:
            print(f"\n  File non trovato: {filepath}")

    # Carica dati connettivita
    conn_file = os.path.join(logdir, 'connectivity_test.csv')
    conn_data = []
    if os.path.exists(conn_file):
        conn_data = load_connectivity_csv(conn_file)
        print(f"\n  Caricati {len(conn_data)} record connettivita")

        # Grafico 2: RTT comparison
        plot_rtt_comparison(conn_data, outdir)

        # Grafico 3: Connectivity matrix
        plot_connectivity_matrix(conn_data, outdir)

        # Grafico 5: Packet loss
        plot_packet_loss(conn_data, outdir)
    else:
        print(f"\n  File non trovato: {conn_file}")

    # Grafico 4: Load test
    plot_load_test(logdir, outdir)

    # Grafico 6: S1 vs S2 comparison
    if len(all_throughput) >= 2:
        plot_throughput_summary(all_throughput, outdir)

    print("\n" + "=" * 60)
    print(f"  Grafici salvati in: {outdir}")
    print("=" * 60)


if __name__ == '__main__':
    main()
