import unittest

from viewsonic_lfd.client import ViewSonicLfdClient, ViewSonicLfdNackError
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
