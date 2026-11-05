import io
import json
import unittest
from contextlib import redirect_stdout

from viewsonic_lfd import __version__
from viewsonic_lfd.cli import build_parser, config_from_args, run_command
from viewsonic_lfd.client import ViewSonicTransaction
from viewsonic_lfd.protocol import classify_packet


class FakeClient:
    def __init__(self):
        self.calls = []

    def _transaction(self, request=b"801gl000\r", response=b"801rl001\r"):
        return ViewSonicTransaction(request, classify_packet(response))

    def get_power(self):
        self.calls.append(("get_power",))
        return "on", self._transaction()

    def set_power(self, state):
        self.calls.append(("set_power", state))
        return self._transaction(b"801s!001\r", b"401+\r")

    def set_input(self, source):
        self.calls.append(("set_input", source))
        return self._transaction(b'801s"004\r', b"401+\r")

    def raw_get(self, command, selector="000"):
        self.calls.append(("raw_get", command, selector))
        return self._transaction(b"801gl000\r", b"801rl001\r")


class CliTests(unittest.TestCase):
    def parse(self, argv):
        return build_parser().parse_args(argv)

    def test_cli_flags_override_env(self):
        args = self.parse(
            [
                "--host",
                "192.0.2.20",
                "--port",
                "5001",
                "--display-id",
                "02",
                "--timeout",
                "1.5",
                "--retries",
                "2",
                "--json",
                "--verbose",
                "power",
                "get",
            ]
        )
        config = config_from_args(
            args,
            {
                "VIEWSONIC_LFD_HOST": "192.0.2.10",
                "VIEWSONIC_LFD_PORT": "5000",
                "VIEWSONIC_LFD_DISPLAY_ID": "01",
                "VIEWSONIC_LFD_TIMEOUT": "2.0",
                "VIEWSONIC_LFD_RETRIES": "1",
            },
        )
        self.assertEqual(config.host, "192.0.2.20")
        self.assertEqual(config.port, 5001)
        self.assertIsNone(config.serial_port)
        self.assertEqual(config.display_id, "02")
        self.assertEqual(config.timeout, 1.5)
        self.assertEqual(config.retries, 2)
        self.assertTrue(config.json_output)
        self.assertTrue(config.verbose)

    def test_env_vars_apply_when_flags_absent(self):
        args = self.parse(["power", "get"])
        config = config_from_args(
            args,
            {
                "VIEWSONIC_LFD_HOST": "192.0.2.10",
                "VIEWSONIC_LFD_PORT": "0x1388",
                "VIEWSONIC_LFD_DISPLAY_ID": "03",
                "VIEWSONIC_LFD_TIMEOUT": "2.5",
                "VIEWSONIC_LFD_RETRIES": "3",
            },
        )
        self.assertEqual(config.host, "192.0.2.10")
        self.assertEqual(config.port, 5000)
        self.assertIsNone(config.serial_port)
        self.assertEqual(config.display_id, "03")
        self.assertEqual(config.timeout, 2.5)
        self.assertEqual(config.retries, 3)

    def test_serial_port_does_not_require_host(self):
        args = self.parse(["--serial-port", "/dev/ttyUSB0", "power", "get"])
        config = config_from_args(args, {})
        self.assertIsNone(config.host)
        self.assertEqual(config.serial_port, "/dev/ttyUSB0")
        self.assertEqual(config.port, 5000)

    def test_serial_port_env_applies(self):
        args = self.parse(["power", "get"])
        config = config_from_args(
            args,
            {"VIEWSONIC_LFD_SERIAL_PORT": "/dev/ttyUSB0"},
        )
        self.assertIsNone(config.host)
        self.assertEqual(config.serial_port, "/dev/ttyUSB0")

    def test_host_and_serial_port_are_mutually_exclusive(self):
        args = self.parse(
            ["--host", "192.0.2.10", "--serial-port", "/dev/ttyUSB0", "power", "get"]
        )
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            config_from_args(args, {})

    def test_serial_port_rejects_tcp_port(self):
        args = self.parse(
            ["--serial-port", "/dev/ttyUSB0", "--port", "5000", "power", "get"]
        )
        with self.assertRaisesRegex(ValueError, "--port cannot be used"):
            config_from_args(args, {})

    def test_missing_target_is_clear_error(self):
        args = self.parse(["power", "get"])
        with self.assertRaisesRegex(ValueError, "host or serial port is required"):
            config_from_args(args, {})

    def test_version_flag_prints_package_version(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as context:
                self.parse(["--version"])
        self.assertEqual(context.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"vslfd {__version__}")

    def test_run_power_get(self):
        args = self.parse(["--host", "192.0.2.10", "power", "get"])
        client = FakeClient()
        message, transaction = run_command(args, client)
        self.assertEqual(message, "Power: on")
        self.assertEqual(transaction.request, b"801gl000\r")
        self.assertEqual(client.calls, [("get_power",)])

    def test_run_input_set(self):
        args = self.parse(["--host", "192.0.2.10", "input", "set", "hdmi1"])
        client = FakeClient()
        message, _transaction = run_command(args, client)
        self.assertEqual(message, "Input set to HDMI 1 (hdmi1)")
        self.assertEqual(client.calls, [("set_input", "hdmi1")])

    def test_run_raw_get(self):
        args = self.parse(["--host", "192.0.2.10", "raw", "get", "l"])
        client = FakeClient()
        message, _transaction = run_command(args, client)
        self.assertEqual(message, "Raw Get value: 001")
        self.assertEqual(client.calls, [("raw_get", "l", "000")])

    def test_json_transaction_shape(self):
        transaction = ViewSonicTransaction(
            b"801gl000\r",
            classify_packet(b"801rl001\r"),
        )
        payload = transaction.to_dict()
        encoded = json.dumps(payload)
        self.assertIn("801rl001", encoded)


if __name__ == "__main__":
    unittest.main()
