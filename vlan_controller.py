#!/usr/bin/env python3
"""
Progetto 11 - Controller Ryu SDN per gestione VLAN
Gestisce SW1, SW2 (con VLAN1/VLAN2) e SW3 (L2 semplice).

VLAN ID 10 = VLAN1 (Privileged)  - 192.168.1.0/24
VLAN ID 20 = VLAN2 (Restricted)  - 192.168.2.0/24

Porte degli switch (assegnate da Mininet in ordine di addLink):
  SW1 (dpid=1):
    porta 1 -> H1  (VLAN1, access)
    porta 2 -> H2  (VLAN2, access)
    porta 3 -> H3  (VLAN1, access)
    porta 4 -> R1  (trunk)

  SW2 (dpid=2):
    porta 1 -> H4  (VLAN2, access)
    porta 2 -> H5  (VLAN1, access)
    porta 3 -> H6  (VLAN1, access)
    porta 4 -> H7  (VLAN1, access)
    porta 5 -> R1  (trunk)

  SW3 (dpid=3):
    porta 1 -> R2   (semplice L2)
    porta 2 -> S1
    porta 3 -> PROXY
    porta 4 -> S2

Avvio: ryu-manager vlan_controller.py
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, vlan, arp, ipv4
from ryu.lib import mac

# ---------------------------------------------------------------------------
# Configurazione VLAN per ogni switch
# ---------------------------------------------------------------------------
VLAN1_ID = 10
VLAN2_ID = 20

# Mapping: dpid -> {porta: vlan_id} per le access port
ACCESS_PORTS = {
    1: {  # SW1
        1: VLAN1_ID,   # H1 -> VLAN1
        2: VLAN2_ID,   # H2 -> VLAN2
        3: VLAN1_ID,   # H3 -> VLAN1
    },
    2: {  # SW2
        1: VLAN2_ID,   # H4 -> VLAN2
        2: VLAN1_ID,   # H5 -> VLAN1
        3: VLAN1_ID,   # H6 -> VLAN1
        4: VLAN1_ID,   # H7 -> VLAN1
    },
}

# Mapping: dpid -> [porte trunk]
TRUNK_PORTS = {
    1: [4],   # SW1: porta 4 -> R1
    2: [5],   # SW2: porta 5 -> R1
}


class VlanController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # MAC address table per switch: {dpid: {mac: port}}
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Installa regola di default: invia al controller."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Regola table-miss: manda al controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, match, actions)

        self.logger.info(f"Switch connesso: dpid={datapath.id}")

    def _add_flow(self, datapath, priority, match, actions, idle_timeout=0,
                  hard_timeout=0):
        """Aggiunge una flow entry allo switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst, idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Gestisce i pacchetti ricevuti dal controller."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        dst = eth.dst
        src = eth.src

        # SW3 (dpid=3): switch L2 semplice, no VLAN
        if dpid == 3:
            self._handle_sw3(datapath, msg, in_port, src, dst, pkt)
            return

        # SW1 (dpid=1) e SW2 (dpid=2): gestione VLAN
        if dpid in ACCESS_PORTS:
            self._handle_vlan_switch(datapath, msg, in_port, src, dst, pkt)

    def _handle_sw3(self, datapath, msg, in_port, src, dst, pkt):
        """Switch L2 semplice per la Service Network (no VLAN)."""
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Installa flow se la porta di destinazione e' nota
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(datapath, 1, match, actions, idle_timeout=300)

        self._send_packet(datapath, msg, actions)

    def _handle_vlan_switch(self, datapath, msg, in_port, src, dst, pkt):
        """Gestisce VLAN su SW1 e SW2."""
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        access_ports = ACCESS_PORTS.get(dpid, {})
        trunk_ports = TRUNK_PORTS.get(dpid, [])

        # Determina la VLAN del pacchetto in ingresso
        vlan_pkt = pkt.get_protocol(vlan.vlan)

        if in_port in access_ports:
            # Pacchetto da access port: assegna VLAN
            pkt_vlan = access_ports[in_port]
        elif in_port in trunk_ports:
            # Pacchetto da trunk port: leggi VLAN tag
            if vlan_pkt:
                pkt_vlan = vlan_pkt.vid
            else:
                # Pacchetto senza tag su trunk: scarta
                return
        else:
            return

        # MAC learning con VLAN: (dpid, vlan) -> {mac: port}
        key = (dpid, pkt_vlan)
        self.mac_to_port.setdefault(key, {})
        self.mac_to_port[key][src] = in_port

        # Determina porta di uscita
        out_port = None
        if dst in self.mac_to_port[key]:
            out_port = self.mac_to_port[key][dst]

        if out_port is None:
            # Flood: invia a tutte le porte della stessa VLAN + trunk
            self._flood_vlan(datapath, msg, in_port, pkt_vlan,
                             access_ports, trunk_ports)
            return

        # Costruisci azioni per la porta di uscita
        actions = self._build_output_actions(parser, in_port, out_port,
                                             pkt_vlan, access_ports,
                                             trunk_ports)

        # Installa flow
        if in_port in access_ports:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
        else:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src,
                                    vlan_vid=(0x1000 | pkt_vlan))

        self._add_flow(datapath, 10, match, actions, idle_timeout=300)
        self._send_packet(datapath, msg, actions)

    def _build_output_actions(self, parser, in_port, out_port, vlan_id,
                              access_ports, trunk_ports):
        """Costruisce le azioni per l'output con gestione VLAN tag."""
        actions = []

        is_in_access = in_port in access_ports
        is_out_access = out_port in access_ports
        is_out_trunk = out_port in trunk_ports

        if is_in_access and is_out_access:
            # Access -> Access: nessun tag (stessa VLAN locale)
            actions.append(parser.OFPActionOutput(out_port))

        elif is_in_access and is_out_trunk:
            # Access -> Trunk: aggiungi VLAN tag
            actions.append(parser.OFPActionPushVlan(0x8100))
            actions.append(parser.OFPActionSetField(
                vlan_vid=(0x1000 | vlan_id)))
            actions.append(parser.OFPActionOutput(out_port))

        elif not is_in_access and is_out_access:
            # Trunk -> Access: rimuovi VLAN tag
            actions.append(parser.OFPActionPopVlan())
            actions.append(parser.OFPActionOutput(out_port))

        elif not is_in_access and is_out_trunk:
            # Trunk -> Trunk: mantieni tag
            actions.append(parser.OFPActionOutput(out_port))

        return actions

    def _flood_vlan(self, datapath, msg, in_port, vlan_id, access_ports,
                    trunk_ports):
        """Flooding limitato alla VLAN corretta."""
        parser = datapath.ofproto_parser
        actions = []

        is_in_access = in_port in access_ports

        # Invia a tutte le access port della stessa VLAN (tranne in_port)
        for port, vid in access_ports.items():
            if port == in_port:
                continue
            if vid != vlan_id:
                continue

            if is_in_access:
                # Access -> Access: nessun tag
                actions.append(parser.OFPActionOutput(port))
            else:
                # Trunk -> Access: pop VLAN tag
                actions.append(parser.OFPActionPopVlan())
                actions.append(parser.OFPActionOutput(port))
                # Dopo il pop, per la prossima porta serve push di nuovo
                # Soluzione: usiamo group table o inviamo pacchetti separati
                # Per semplicita, inviamo il pacchetto direttamente per ogni porta
                self._send_packet(datapath, msg, actions)
                actions = []

        # Invia alle trunk port (tranne in_port)
        for port in trunk_ports:
            if port == in_port:
                continue
            if is_in_access:
                # Access -> Trunk: push VLAN tag
                actions.append(parser.OFPActionPushVlan(0x8100))
                actions.append(parser.OFPActionSetField(
                    vlan_vid=(0x1000 | vlan_id)))
                actions.append(parser.OFPActionOutput(port))
            else:
                # Trunk -> Trunk: mantieni tag
                actions.append(parser.OFPActionOutput(port))

        if actions:
            self._send_packet(datapath, msg, actions)

    def _send_packet(self, datapath, msg, actions):
        """Invia un pacchetto tramite packet-out."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
            out = parser.OFPPacketOut(
                datapath=datapath, buffer_id=msg.buffer_id,
                in_port=msg.match['in_port'], actions=actions)
        else:
            out = parser.OFPPacketOut(
                datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=msg.match['in_port'], actions=actions,
                data=msg.data)
        datapath.send_msg(out)
