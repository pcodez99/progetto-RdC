#!/usr/bin/env python3
"""
Progetto RdC Pietro Zarbo - Reti di Calcolatori A.A. 2025-2026
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

import os
import sys
import time

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

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

        sw1 = self.addSwitch('sw1', cls=OVSKernelSwitch, protocols='OpenFlow13')
        sw2 = self.addSwitch('sw2', cls=OVSKernelSwitch, protocols='OpenFlow13')
        sw3 = self.addSwitch('sw3', cls=OVSKernelSwitch, protocols='OpenFlow13')

        h1 = self.addHost('h1', ip=H1_IP, mac='00:00:00:00:00:01', defaultRoute='via 192.168.1.254')
        h2 = self.addHost('h2', ip=H2_IP, mac='00:00:00:00:00:02', defaultRoute='via 192.168.2.254')
        h3 = self.addHost('h3', ip=H3_IP, mac='00:00:00:00:00:03', defaultRoute='via 192.168.1.254')
        h4 = self.addHost('h4', ip=H4_IP, mac='00:00:00:00:00:04', defaultRoute='via 192.168.2.254')
        h5 = self.addHost('h5', ip=H5_IP, mac='00:00:00:00:00:05', defaultRoute='via 192.168.1.254')
        h6 = self.addHost('h6', ip=H6_IP, mac='00:00:00:00:00:06', defaultRoute='via 192.168.1.254')
        h7 = self.addHost('h7', ip=H7_IP, mac='00:00:00:00:00:07', defaultRoute='via 192.168.1.254')

        r1 = self.addHost('r1', ip='0.0.0.0', mac='00:00:00:00:00:FE')
        r2 = self.addHost('r2', ip=R2_WAN_IP.split('/')[0], mac='00:00:00:00:00:FF')

        s1    = self.addHost('s1',    ip=S1_IP,    mac='00:00:00:00:01:01', defaultRoute='via 10.0.1.1')
        proxy = self.addHost('proxy', ip=PROXY_IP, mac='00:00:00:00:01:02', defaultRoute='via 10.0.1.1')
        s2    = self.addHost('s2',    ip=S2_IP,    mac='00:00:00:00:01:03', defaultRoute='via 10.0.1.1')

        linkopt_intra = dict(bw=1000, delay='5ms',  cls=TCLink, use_tbf=True)
        linkopt_wan   = dict(bw=1000, delay='60ms', cls=TCLink, use_tbf=True)
        linkopt_svc   = dict(bw=1000, delay='1ms',  cls=TCLink, use_tbf=True)

        # SW1: H1(porta1), H2(porta2), H3(porta3), R1(porta4) - trunk
        self.addLink(h1, sw1, **linkopt_intra)  # sw1-eth1
        self.addLink(h2, sw1, **linkopt_intra)  # sw1-eth2
        self.addLink(h3, sw1, **linkopt_intra)  # sw1-eth3
        self.addLink(r1, sw1, **linkopt_intra)  # sw1-eth4, r1-eth0

        # SW2: H4(porta1), H5(porta2), H6(porta3), H7(porta4), R1(porta5) - trunk
        self.addLink(h4, sw2, **linkopt_intra)  # sw2-eth1
        self.addLink(h5, sw2, **linkopt_intra)  # sw2-eth2
        self.addLink(h6, sw2, **linkopt_intra)  # sw2-eth3
        self.addLink(h7, sw2, **linkopt_intra)  # sw2-eth4
        self.addLink(r1, sw2, **linkopt_intra)  # sw2-eth5, r1-eth1

        # WAN: R1 <-> R2 (1Gbps, 60ms) - 200.0.1.0/30
        self.addLink(r1, r2, **linkopt_wan)     # r1-eth2, r2-eth0

        # Service Network: R2 <-> SW3, SW3 <-> {S1, PROXY, S2}
        self.addLink(r2,    sw3, **linkopt_svc) # sw3-eth1, r2-eth1
        self.addLink(s1,    sw3, **linkopt_svc) # sw3-eth2
        self.addLink(proxy, sw3, **linkopt_svc) # sw3-eth3
        self.addLink(s2,    sw3, **linkopt_svc) # sw3-eth4


def configure_routers(net):
    r1 = net.get('r1')
    r2 = net.get('r2')

    print("--- Configurazione Router R1 ---")

    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    # R1: r1-eth0 -> SW1 (trunk), r1-eth1 -> SW2 (trunk), r1-eth2 -> R2 (WAN)
    r1.cmd('ip addr flush dev r1-eth0')
    r1.cmd('ip addr flush dev r1-eth1')
    r1.cmd('ip addr flush dev r1-eth2')

    r1.cmd('ip link add link r1-eth0 name r1-eth0.10 type vlan id 10')
    r1.cmd('ip link add link r1-eth0 name r1-eth0.20 type vlan id 20')
    r1.cmd('ip link set r1-eth0.10 up')
    r1.cmd('ip link set r1-eth0.20 up')

    r1.cmd('ip link add link r1-eth1 name r1-eth1.10 type vlan id 10')
    r1.cmd('ip link add link r1-eth1 name r1-eth1.20 type vlan id 20')
    r1.cmd('ip link set r1-eth1.10 up')
    r1.cmd('ip link set r1-eth1.20 up')

    # Bridge VLAN1 (ID 10): unisce r1-eth0.10 e r1-eth1.10
    r1.cmd('ip link add br-vlan1 type bridge')
    r1.cmd('ip link set r1-eth0.10 master br-vlan1')
    r1.cmd('ip link set r1-eth1.10 master br-vlan1')
    r1.cmd('ip addr add 192.168.1.254/24 dev br-vlan1')
    r1.cmd('ip link set br-vlan1 up')

    # Bridge VLAN2 (ID 20): unisce r1-eth0.20 e r1-eth1.20
    r1.cmd('ip link add br-vlan2 type bridge')
    r1.cmd('ip link set r1-eth0.20 master br-vlan2')
    r1.cmd('ip link set r1-eth1.20 master br-vlan2')
    r1.cmd('ip addr add 192.168.2.254/24 dev br-vlan2')
    r1.cmd('ip link set br-vlan2 up')

    r1.cmd('ip addr add 200.0.1.1/30 dev r1-eth2')
    r1.cmd('ip link set r1-eth2 up')

    r1.cmd('ip route add 10.0.1.0/24 via 200.0.1.2')

    print("--- Configurazione Router R2 ---")

    r2.cmd('sysctl -w net.ipv4.ip_forward=1')

    r2.cmd('ip addr flush dev r2-eth0')
    r2.cmd('ip addr flush dev r2-eth1')

    r2.cmd('ip addr add 200.0.1.2/30 dev r2-eth0')
    r2.cmd('ip link set r2-eth0 up')

    r2.cmd('ip addr add 10.0.1.1/24 dev r2-eth1')
    r2.cmd('ip link set r2-eth1 up')

    r2.cmd('ip route add 192.168.1.0/24 via 200.0.1.1')
    r2.cmd('ip route add 192.168.2.0/24 via 200.0.1.1')


def configure_firewall(net):
    r1    = net.get('r1')
    s1    = net.get('s1')
    s2    = net.get('s2')
    proxy = net.get('proxy')

    print("--- Configurazione Firewall (iptables) ---")

    # R1: VLAN2 non puo' raggiungere la Service Network o la WAN
    r1.cmd('iptables -A FORWARD -s 192.168.2.0/24 -d 10.0.1.0/24  -j DROP')
    r1.cmd('iptables -A FORWARD -s 192.168.2.0/24 -d 200.0.1.0/30 -j DROP')
    r1.cmd('iptables -A FORWARD -s 10.0.1.0/24   -d 192.168.2.0/24 -j DROP')

    # PROXY: raggiungibile solo da VLAN1
    proxy.cmd('iptables -A INPUT -i lo -j ACCEPT')
    proxy.cmd('iptables -A INPUT -s 10.0.1.0/24 -j ACCEPT')
    proxy.cmd('iptables -A INPUT -s 192.168.1.0/24 -j ACCEPT')
    proxy.cmd('iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT')
    proxy.cmd('iptables -A INPUT -j DROP')

    # S1 e S2: raggiungibili solo dal PROXY
    for server in [s1, s2]:
        server.cmd('iptables -A INPUT -i lo -j ACCEPT')
        server.cmd('iptables -A INPUT -s 10.0.1.3 -j ACCEPT')
        server.cmd('iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT')
        server.cmd('iptables -A INPUT -j DROP')


def start_services(net):
    project_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir     = os.path.join(project_dir, 'logs')
    venv_python = sys.executable

    print("--- Avvio Servizi ---")

    for hostname in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 's1', 's2', 'proxy']:
        net.get(hostname).cmd('iperf -s -p 5201 &')

    flask_script = os.path.join(project_dir, 'flask_server.py')
    net.get('s1').cmd(f'{venv_python} {flask_script} --port 5001 --name S1 --logdir {log_dir} > {log_dir}/flask_s1.log 2>&1 &')
    net.get('s2').cmd(f'{venv_python} {flask_script} --port 5002 --name S2 --logdir {log_dir} > {log_dir}/flask_s2.log 2>&1 &')
    print("  Flask avviato su S1 (porta 5001) e S2 (porta 5002)")

    time.sleep(2)

    nginx_conf = os.path.join(project_dir, 'nginx_proxy.conf')
    net.get('proxy').cmd(f'nginx -c {nginx_conf} 2>/tmp/nginx_start.log')
    print("  NGINX avviato su PROXY (porta 80)")


def run():
    setLogLevel('info')

    topo = ProjectTopology()

    net = Mininet(
        topo=topo,
        switch=OVSKernelSwitch,
        controller=RemoteController('ryu', ip='127.0.0.1', port=6653),
        link=TCLink
    )

    net.start()

    for host in net.hosts:
        for intf in host.intfList():
            if intf.name != 'lo':
                host.cmd(f'ethtool -K {intf.name} tx off rx off 2>/dev/null')

    time.sleep(3)

    configure_routers(net)
    configure_firewall(net)
    start_services(net)

    print("\n--- Rete pronta ---")
    print("  h1 ping h3          (VLAN1 <-> VLAN1, stesso switch)")
    print("  h1 ping h5          (VLAN1 <-> VLAN1, switch diversi)")
    print("  h1 ping h2          (VLAN1 <-> VLAN2)")
    print("  h2 ping 10.0.1.3    (VLAN2 -> esterno, BLOCCATO)")
    print("  h1 curl http://10.0.1.3/s1/api/throughput")

    CLI(net)

    print("--- Arresto servizi ---")
    for hostname in ['s1', 's2', 'proxy']:
        net.get(hostname).cmd('kill %python3 2>/dev/null')
    net.get('proxy').cmd('nginx -s stop 2>/dev/null')

    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
