#!/usr/bin/env python3
"""
Progetto 11 - Reti di Calcolatori A.A. 2025-2026
Topologia Mininet: 2 Router L3, 2 Switch L2 VLAN, 10 Host

Topologia:
  INTRANET (VLAN1: 192.168.1.0/24, VLAN2: 192.168.2.0/24)
    SW1 -- H1(V1), H2(V2), H3(V1)
    SW2 -- H4(V2), H5(V1), H6(V1), H7(V1)
    R1  -- SW1, SW2, R2
  WAN (200.0.1.0/30)
    R1 -- R2
  SERVICE NETWORK (10.0.1.0/24)
    SW3 -- S1, PROXY, S2
    R2  -- SW3
"""

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSKernelSwitch, RemoteController, Host
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info
import time
import os

# ---------------------------------------------------------------------------
# Costanti di indirizzamento
# ---------------------------------------------------------------------------
# VLAN1 (Privileged) - 192.168.1.0/24
VLAN1_GW = '192.168.1.254'
H1_IP = '192.168.1.1/24'
H3_IP = '192.168.1.2/24'
H5_IP = '192.168.1.3/24'
H6_IP = '192.168.1.4/24'
H7_IP = '192.168.1.5/24'

# VLAN2 (Restricted) - 192.168.2.0/24
VLAN2_GW = '192.168.2.254'
H2_IP = '192.168.2.1/24'
H4_IP = '192.168.2.2/24'

# WAN - 200.0.1.0/30
R1_WAN_IP = '200.0.1.1/30'
R2_WAN_IP = '200.0.1.2/30'

# Service Network - 10.0.1.0/24
R2_SVC_IP = '10.0.1.1/24'
S1_IP = '10.0.1.2/24'
PROXY_IP = '10.0.1.3/24'
S2_IP = '10.0.1.4/24'


class ProjectTopology(Topo):
    """Topologia del progetto con VLAN, router e service network."""

    def build(self):
        # ==================================================================
        # Switch L2 (OpenFlow, gestiti dal controller Ryu)
        # ==================================================================
        sw1 = self.addSwitch('sw1', cls=OVSKernelSwitch, protocols='OpenFlow13')
        sw2 = self.addSwitch('sw2', cls=OVSKernelSwitch, protocols='OpenFlow13')
        sw3 = self.addSwitch('sw3', cls=OVSKernelSwitch, protocols='OpenFlow13')

        # ==================================================================
        # Host Intranet
        # ==================================================================
        # Gli host non hanno IP assegnato qui perche' il controller Ryu
        # gestisce le VLAN. L'IP viene assegnato dopo con setup_network.
        # Tuttavia, per semplicita, assegniamo l'IP direttamente.
        h1 = self.addHost('h1', ip=H1_IP, defaultRoute='via 192.168.1.254')
        h2 = self.addHost('h2', ip=H2_IP, defaultRoute='via 192.168.2.254')
        h3 = self.addHost('h3', ip=H3_IP, defaultRoute='via 192.168.1.254')
        h4 = self.addHost('h4', ip=H4_IP, defaultRoute='via 192.168.2.254')
        h5 = self.addHost('h5', ip=H5_IP, defaultRoute='via 192.168.1.254')
        h6 = self.addHost('h6', ip=H6_IP, defaultRoute='via 192.168.1.254')
        h7 = self.addHost('h7', ip=H7_IP, defaultRoute='via 192.168.1.254')

        # ==================================================================
        # Router (host Linux con IP forwarding)
        # ==================================================================
        r1 = self.addHost('r1', ip='0.0.0.0')  # IP assegnato dopo sulle sub-if
        r2 = self.addHost('r2', ip=R2_WAN_IP.split('/')[0])

        # ==================================================================
        # Host Service Network
        # ==================================================================
        s1 = self.addHost('s1', ip=S1_IP, defaultRoute='via 10.0.1.1')
        proxy = self.addHost('proxy', ip=PROXY_IP, defaultRoute='via 10.0.1.1')
        s2 = self.addHost('s2', ip=S2_IP, defaultRoute='via 10.0.1.1')

        # ==================================================================
        # Link INTRANET: Host <-> Switch (1Gbps, 5ms)
        # ==================================================================
        bw_intra = 1000  # Mbps
        delay_intra = '5ms'

        # SW1: H1(porta1), H2(porta2), H3(porta3), R1(porta4) - trunk
        self.addLink(h1, sw1, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw1-eth1
        self.addLink(h2, sw1, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw1-eth2
        self.addLink(h3, sw1, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw1-eth3
        self.addLink(r1, sw1, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw1-eth4, r1-eth0

        # SW2: H4(porta1), H5(porta2), H6(porta3), H7(porta4), R1(porta5) - trunk
        self.addLink(h4, sw2, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw2-eth1
        self.addLink(h5, sw2, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw2-eth2
        self.addLink(h6, sw2, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw2-eth3
        self.addLink(h7, sw2, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw2-eth4
        self.addLink(r1, sw2, bw=bw_intra, delay=delay_intra, cls=TCLink)  # sw2-eth5, r1-eth1

        # ==================================================================
        # Link WAN: R1 <-> R2 (1Gbps, 60ms) - 200.0.1.0/30
        # ==================================================================
        self.addLink(r1, r2, bw=1000, delay='60ms', cls=TCLink)  # r1-eth2, r2-eth0

        # ==================================================================
        # Link Service Network: R2 <-> SW3, SW3 <-> {S1, PROXY, S2} (1Gbps, 1ms)
        # ==================================================================
        bw_svc = 1000
        delay_svc = '1ms'

        self.addLink(r2, sw3, bw=bw_svc, delay=delay_svc, cls=TCLink)    # sw3-eth1, r2-eth1
        self.addLink(s1, sw3, bw=bw_svc, delay=delay_svc, cls=TCLink)    # sw3-eth2
        self.addLink(proxy, sw3, bw=bw_svc, delay=delay_svc, cls=TCLink) # sw3-eth3
        self.addLink(s2, sw3, bw=bw_svc, delay=delay_svc, cls=TCLink)    # sw3-eth4


def configure_routers(net):
    """Configura R1 e R2 come router Linux con sub-interfacce VLAN."""
    r1 = net.get('r1')
    r2 = net.get('r2')

    info('*** Configurazione Router R1\n')

    # Abilita IP forwarding
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    # R1 ha 3 interfacce:
    #   r1-eth0 -> SW1 (trunk VLAN1 + VLAN2)
    #   r1-eth1 -> SW2 (trunk VLAN1 + VLAN2)
    #   r1-eth2 -> R2  (WAN 200.0.1.0/30)

    # Rimuovi eventuali IP preesistenti
    r1.cmd('ip addr flush dev r1-eth0')
    r1.cmd('ip addr flush dev r1-eth1')
    r1.cmd('ip addr flush dev r1-eth2')

    # -- Sub-interfacce VLAN su r1-eth0 (trunk verso SW1) --
    # VLAN ID 10 = VLAN1 (Privileged), VLAN ID 20 = VLAN2 (Restricted)
    r1.cmd('ip link add link r1-eth0 name r1-eth0.10 type vlan id 10')
    r1.cmd('ip addr add 192.168.1.254/24 dev r1-eth0.10')
    r1.cmd('ip link set r1-eth0.10 up')

    r1.cmd('ip link add link r1-eth0 name r1-eth0.20 type vlan id 20')
    r1.cmd('ip addr add 192.168.2.254/24 dev r1-eth0.20')
    r1.cmd('ip link set r1-eth0.20 up')

    # -- Sub-interfacce VLAN su r1-eth1 (trunk verso SW2) --
    # Non assegniamo IP aggiuntivi; usiamo un bridge per unire i trunk
    # OPPURE: creiamo sub-interfacce e le mettiamo in bridge con quelle di eth0
    # Approccio piu semplice: bridge le sub-interfacce della stessa VLAN
    r1.cmd('ip link add link r1-eth1 name r1-eth1.10 type vlan id 10')
    r1.cmd('ip link set r1-eth1.10 up')

    r1.cmd('ip link add link r1-eth1 name r1-eth1.20 type vlan id 20')
    r1.cmd('ip link set r1-eth1.20 up')

    # Bridge VLAN1: r1-eth0.10 + r1-eth1.10
    r1.cmd('ip link add br-vlan1 type bridge')
    r1.cmd('ip link set r1-eth0.10 master br-vlan1')
    r1.cmd('ip link set r1-eth1.10 master br-vlan1')
    r1.cmd('ip addr flush dev r1-eth0.10')
    r1.cmd('ip addr add 192.168.1.254/24 dev br-vlan1')
    r1.cmd('ip link set br-vlan1 up')

    # Bridge VLAN2: r1-eth0.20 + r1-eth1.20
    r1.cmd('ip link add br-vlan2 type bridge')
    r1.cmd('ip link set r1-eth0.20 master br-vlan2')
    r1.cmd('ip link set r1-eth1.20 master br-vlan2')
    r1.cmd('ip addr flush dev r1-eth0.20')
    r1.cmd('ip addr add 192.168.2.254/24 dev br-vlan2')
    r1.cmd('ip link set br-vlan2 up')

    # -- Interfaccia WAN --
    r1.cmd('ip addr add 200.0.1.1/30 dev r1-eth2')
    r1.cmd('ip link set r1-eth2 up')

    # -- Rotte R1 --
    r1.cmd('ip route add 10.0.1.0/24 via 200.0.1.2')

    # ==================================================================
    info('*** Configurazione Router R2\n')

    r2.cmd('sysctl -w net.ipv4.ip_forward=1')

    r2.cmd('ip addr flush dev r2-eth0')
    r2.cmd('ip addr flush dev r2-eth1')

    r2.cmd('ip addr add 200.0.1.2/30 dev r2-eth0')
    r2.cmd('ip link set r2-eth0 up')

    r2.cmd('ip addr add 10.0.1.1/24 dev r2-eth1')
    r2.cmd('ip link set r2-eth1 up')

    # Rotte R2 verso Intranet
    r2.cmd('ip route add 192.168.1.0/24 via 200.0.1.1')
    r2.cmd('ip route add 192.168.2.0/24 via 200.0.1.1')


def configure_firewall(net):
    """Configura iptables per le politiche di isolamento."""
    r1 = net.get('r1')
    s1 = net.get('s1')
    s2 = net.get('s2')
    proxy = net.get('proxy')

    info('*** Configurazione Firewall (iptables)\n')

    # ---- R1: Isolamento VLAN2 dalla rete esterna ----
    # VLAN2 NON puo' raggiungere la Service Network o la WAN
    r1.cmd('iptables -A FORWARD -s 192.168.2.0/24 -d 10.0.1.0/24 -j DROP')
    r1.cmd('iptables -A FORWARD -s 192.168.2.0/24 -d 200.0.1.0/30 -j DROP')
    # Blocca anche il ritorno dalla Service Network verso VLAN2
    r1.cmd('iptables -A FORWARD -s 10.0.1.0/24 -d 192.168.2.0/24 -j DROP')
    # VLAN2 puo' comunicare con VLAN1 (default ACCEPT)
    # VLAN1 puo' raggiungere tutto (default ACCEPT)

    # ---- PROXY: raggiungibile solo da VLAN1 (192.168.1.0/24) ----
    proxy.cmd('iptables -A INPUT -i lo -j ACCEPT')
    proxy.cmd('iptables -A INPUT -s 10.0.1.0/24 -j ACCEPT')  # traffico locale service net
    proxy.cmd('iptables -A INPUT -s 192.168.1.0/24 -j ACCEPT')  # da VLAN1
    proxy.cmd('iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT')
    proxy.cmd('iptables -A INPUT -j DROP')  # tutto il resto bloccato

    # ---- S1 e S2: raggiungibili solo dal PROXY ----
    for server in [s1, s2]:
        server.cmd('iptables -A INPUT -i lo -j ACCEPT')
        server.cmd('iptables -A INPUT -s 10.0.1.3 -j ACCEPT')   # dal PROXY
        server.cmd('iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT')
        server.cmd('iptables -A INPUT -j DROP')  # tutto il resto bloccato


def start_services(net):
    """Avvia i servizi: iperf server su tutti i nodi, Flask su S1/S2, NGINX su PROXY."""
    info('*** Avvio servizi\n')

    project_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(project_dir, 'logs')

    # Avvia iperf server (-s) su tutti gli host per ricevere test
    all_hosts = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 's1', 's2', 'proxy']
    for hostname in all_hosts:
        host = net.get(hostname)
        host.cmd(f'iperf -s -p 5201 &')
        info(f'  iperf server avviato su {hostname}\n')

    # Avvia Flask su S1 (porta 5001) e S2 (porta 5002)
    s1 = net.get('s1')
    s2 = net.get('s2')

    flask_script = os.path.join(project_dir, 'flask_server.py')
    s1.cmd(f'python3 {flask_script} --port 5001 --name S1 --logdir {log_dir} &')
    s2.cmd(f'python3 {flask_script} --port 5002 --name S2 --logdir {log_dir} &')
    info('  Flask avviato su S1 (porta 5001) e S2 (porta 5002)\n')

    # Avvia NGINX su PROXY
    proxy = net.get('proxy')
    nginx_conf = os.path.join(project_dir, 'nginx_proxy.conf')
    proxy.cmd(f'nginx -c {nginx_conf}')
    info('  NGINX avviato su PROXY (porta 80)\n')


def run():
    """Funzione principale: crea la rete, configura e avvia la CLI."""
    setLogLevel('info')

    topo = ProjectTopology()

    net = Mininet(
        topo=topo,
        switch=OVSKernelSwitch,
        controller=RemoteController('ryu', ip='127.0.0.1', port=6653),
        link=TCLink,
        autoSetMacs=True
    )

    net.start()
    info('*** Rete avviata\n')

    # Attendi che il controller si colleghi agli switch
    time.sleep(3)

    # Configura router
    configure_routers(net)

    # Configura firewall
    configure_firewall(net)

    # Avvia servizi (iperf, Flask, NGINX)
    start_services(net)

    info('\n*** Rete pronta. Usa la CLI per interagire.\n')
    info('*** Comandi utili:\n')
    info('    h1 ping h3          (VLAN1 <-> VLAN1, stesso switch)\n')
    info('    h1 ping h5          (VLAN1 <-> VLAN1, switch diversi)\n')
    info('    h1 ping h2          (VLAN1 <-> VLAN2)\n')
    info('    h2 ping 10.0.1.3    (VLAN2 -> esterno, BLOCCATO)\n')
    info('    h1 curl http://10.0.1.3/s1/api/throughput\n')

    CLI(net)

    # Cleanup
    info('*** Arresto servizi\n')
    for hostname in ['s1', 's2', 'proxy']:
        host = net.get(hostname)
        host.cmd('kill %python3 2>/dev/null')
    net.get('proxy').cmd('nginx -s stop 2>/dev/null')

    net.stop()


if __name__ == '__main__':
    run()
