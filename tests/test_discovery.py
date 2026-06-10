import json
import unittest

from classroom_hand_raise.shared.constants import DISCOVERY_MAGIC
from classroom_hand_raise.shared.discovery import decode_discovery_packet, primary_local_ip_address, rank_local_ip_addresses


class DiscoveryTests(unittest.TestCase):
    def test_decode_discovery_packet_accepts_teacher_broadcast(self):
        packet = json.dumps(
            {
                "type": DISCOVERY_MAGIC,
                "classroom_name": "软件工程课堂",
                "tcp_port": 8765,
                "addresses": ["192.168.1.20"],
                "timestamp": 123.4,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        classroom = decode_discovery_packet(packet, ("192.168.1.20", 38765))

        self.assertEqual(classroom["classroom_name"], "软件工程课堂")
        self.assertEqual(classroom["tcp_port"], 8765)
        self.assertEqual(classroom["source_host"], "192.168.1.20")

    def test_decode_discovery_packet_rejects_unrelated_payload(self):
        packet = json.dumps({"type": "other"}).encode("utf-8")

        self.assertIsNone(decode_discovery_packet(packet, ("127.0.0.1", 38765)))

    def test_rank_local_ip_addresses_prefers_lan_address_over_loopback_and_virtual_gateways(self):
        ranked = rank_local_ip_addresses(["127.0.0.1", "172.23.160.1", "192.168.234.1", "192.168.102.130"])

        self.assertEqual(ranked[0], "192.168.102.130")
        self.assertEqual(ranked[-1], "127.0.0.1")
        self.assertEqual(primary_local_ip_address(ranked), "192.168.102.130")


if __name__ == "__main__":
    unittest.main()
