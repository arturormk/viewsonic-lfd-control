import os
import select
import unittest

from viewsonic_lfd.transport import SerialTransport

try:
    import pty
except ImportError:
    pty = None


@unittest.skipIf(pty is None, "PTY support is unavailable")
class SerialTransportTests(unittest.TestCase):
    def setUp(self):
        assert pty is not None
        self.master_fd, slave_fd = pty.openpty()
        self.slave_path = os.ttyname(slave_fd)
        os.close(slave_fd)
        os.set_blocking(self.master_fd, False)

    def tearDown(self):
        os.close(self.master_fd)

    def test_send_all_writes_to_serial_device(self):
        transport = SerialTransport(self.slave_path, timeout=0.25)
        transport.connect()
        try:
            transport.send_all(b"801gl000\r")
            readable, _writable, _errors = select.select([self.master_fd], [], [], 0.25)
            self.assertTrue(readable)
            self.assertEqual(os.read(self.master_fd, 1024), b"801gl000\r")
        finally:
            transport.close()

    def test_recv_reads_from_serial_device(self):
        transport = SerialTransport(self.slave_path, timeout=0.25)
        transport.connect()
        try:
            os.write(self.master_fd, b"801rl001\r")
            self.assertEqual(transport.recv(1024), b"801rl001\r")
        finally:
            transport.close()

    def test_recv_timeout_raises(self):
        transport = SerialTransport(self.slave_path, timeout=0.05)
        transport.connect()
        try:
            with self.assertRaises(TimeoutError):
                transport.recv(1024)
        finally:
            transport.close()


if __name__ == "__main__":
    unittest.main()
