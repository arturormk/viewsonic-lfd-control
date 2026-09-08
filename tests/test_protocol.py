import unittest

from viewsonic_lfd.protocol import (
    build_get,
    build_set,
    classify_packet,
    extract_cr_packets,
)


class ProtocolTests(unittest.TestCase):
    def test_build_set(self):
        self.assertEqual(build_set("01", "!", "001"), b"801s!001\r")

    def test_build_get(self):
        self.assertEqual(build_get("01", "l"), b"801gl000\r")
        self.assertEqual(build_get("01", "2", "Y00"), b"801g2Y00\r")

    def test_build_set_preserves_command_type(self):
        self.assertEqual(build_set("01", "B", "050", "A"), b"801AB050\r")

    def test_rejects_malformed_fields(self):
        with self.assertRaisesRegex(ValueError, "display_id"):
            build_get("1", "l")
        with self.assertRaisesRegex(ValueError, "ASCII"):
            build_get("01", "é")
        with self.assertRaisesRegex(ValueError, "selector"):
            build_get("01", "l", "00")

    def test_parse_ack_packets(self):
        packet = classify_packet(b"401+\r")
        self.assertEqual(packet.kind, "set_ack")
        self.assertEqual(packet.display_id, "01")
        self.assertTrue(packet.accepted)

        packet = classify_packet(b"401-\r")
        self.assertEqual(packet.kind, "set_ack")
        self.assertFalse(packet.accepted)

    def test_parse_standard_get(self):
        packet = classify_packet(b"801rl001\r")
        self.assertEqual(packet.kind, "get_reply")
        self.assertEqual(packet.display_id, "01")
        self.assertEqual(packet.command, "l")
        self.assertEqual(packet.value, b"001")

    def test_parse_remote_key(self):
        packet = classify_packet(b"605p10\r")
        self.assertEqual(packet.kind, "remote_key")
        self.assertEqual(packet.display_id, "05")
        self.assertEqual(packet.command, "p")
        self.assertEqual(packet.value, b"10")

    def test_parse_extended_get(self):
        payload = b"192.168.100.2"
        packet = b"201r6" + payload + b"\x00" * (27 - len(payload)) + b"\r"
        self.assertEqual(len(packet), 33)
        parsed = classify_packet(packet)
        self.assertEqual(parsed.kind, "extended_get_reply")
        self.assertEqual(parsed.command, "6")
        self.assertEqual(parsed.value, payload)

    def test_unknown_packet(self):
        packet = classify_packet(b"abc\r")
        self.assertEqual(packet.kind, "unknown")
        self.assertEqual(packet.value, b"abc")

    def test_extract_fragmented_packets(self):
        buffer = bytearray()
        packets = []
        for chunk in (b"801r", b"l001\r401", b"+\r"):
            buffer.extend(chunk)
            packets.extend(extract_cr_packets(buffer))
        self.assertEqual(packets, [b"801rl001\r", b"401+\r"])

    def test_extract_coalesced_packets(self):
        buffer = bytearray(b"801rl001\r401+\r")
        self.assertEqual(extract_cr_packets(buffer), [b"801rl001\r", b"401+\r"])
        self.assertEqual(buffer, bytearray())


if __name__ == "__main__":
    unittest.main()
