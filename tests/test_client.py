import unittest

from viewsonic_lfd.client import (
    ViewSonicLfdClient,
    ViewSonicLfdNackError,
    decode_input_status,
    input_name_to_value,
)
from viewsonic_lfd.transport import SerialTransport


class FakeTransport:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def send_all(self, data):
        self.sent.append(data)

    def recv(self, _max_bytes):
        if self.chunks:
            return self.chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


class TransportFactory:
    def __init__(self, *chunks):
        self.transport = FakeTransport(chunks)

    def __call__(self):
        return self.transport


class ClientTests(unittest.TestCase):
    def test_get_power(self):
        factory = TransportFactory(b"801rl001\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        state, transaction = client.get_power()
        self.assertEqual(state, "on")
        self.assertEqual(factory.transport.sent, [b"801gl000\r"])
        self.assertEqual(transaction.response.raw, b"801rl001\r")

    def test_set_power(self):
        factory = TransportFactory(b"401+\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        transaction = client.set_power("on")
        self.assertEqual(factory.transport.sent, [b"801s!001\r"])
        self.assertTrue(transaction.response.accepted)

    def test_set_nack_raises(self):
        factory = TransportFactory(b"401-\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        with self.assertRaises(ViewSonicLfdNackError):
            client.set_power("on")

    def test_skips_unmatched_automatic_packet(self):
        factory = TransportFactory(b"801rf020\r801rl000\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        state, transaction = client.get_power()
        self.assertEqual(state, "standby")
        self.assertEqual(len(transaction.skipped), 1)
        self.assertEqual(transaction.skipped[0].command, "f")

    def test_get_input_decodes_signal_and_source(self):
        factory = TransportFactory(b"801rj104\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        status, _ = client.get_input()
        self.assertEqual(factory.transport.sent, [b"801gj000\r"])
        self.assertTrue(status.signal)
        self.assertEqual(status.name, "hdmi1")
        self.assertEqual(str(status), "HDMI 1 (hdmi1), signal detected")

    def test_decode_input_status_variants(self):
        self.assertEqual(decode_input_status("00A").name, "android")
        self.assertFalse(decode_input_status("00A").signal)
        self.assertEqual(decode_input_status("119").name, "usb-c1")
        self.assertEqual(decode_input_status("134").name, "hdmi4")
        unknown = decode_input_status("1ZZ")
        self.assertIsNone(unknown.source)
        self.assertIn("unknown", str(unknown))

    def test_input_name_to_value_accepts_friendly_names(self):
        cases = {
            "hdmi1": "004",
            "HDMI 1": "004",
            "hdmi-2": "014",
            "HDMI_4": "034",
            "dp": "009",
            "DisplayPort 2": "029",
            "usb-c": "019",
            "type-c2": "039",
            "ops": "007",
            "android": "00A",
            "vga": "006",
            "04": "004",
            "0a": "00A",
            "00a": "00A",
            "024": "024",
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                self.assertEqual(input_name_to_value(name), value)

    def test_input_name_to_value_raw_and_unknown(self):
        self.assertEqual(input_name_to_value("0ZZ"), "0ZZ")
        with self.assertRaisesRegex(ValueError, "unknown input"):
            input_name_to_value("hdmi9")

    def test_set_input_by_name(self):
        factory = TransportFactory(b"401+\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        client.set_input("DisplayPort 1")
        self.assertEqual(factory.transport.sent, [b'801s"009\r'])

    def test_raw_destructive_guard(self):
        client = ViewSonicLfdClient(transport_factory=TransportFactory(b"401+\r"))
        with self.assertRaisesRegex(ValueError, "allow-destructive"):
            client.raw_set("s", "~", "000")

    def test_raw_destructive_can_be_allowed(self):
        factory = TransportFactory(b"401+\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        client.raw_set("s", "~", "000", allow_destructive=True)
        self.assertEqual(factory.transport.sent, [b"801s~000\r"])

    def test_backlight_level_uses_unusual_command_type(self):
        factory = TransportFactory(b"401+\r")
        client = ViewSonicLfdClient(transport_factory=factory)
        client.set_percentage_or_step("B", "50", "backlight", command_type="A")
        self.assertEqual(factory.transport.sent, [b"801AB050\r"])

    def test_serial_port_creates_serial_transport(self):
        client = ViewSonicLfdClient(serial_port="/dev/ttyUSB0")
        transport = client._new_transport()
        self.assertIsInstance(transport, SerialTransport)
        self.assertEqual(transport.path, "/dev/ttyUSB0")

    def test_host_and_serial_port_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            ViewSonicLfdClient(host="192.0.2.10", serial_port="/dev/ttyUSB0")


if __name__ == "__main__":
    unittest.main()
