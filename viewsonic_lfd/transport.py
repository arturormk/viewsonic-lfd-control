"""Byte transports for ViewSonic LFD control."""

from __future__ import annotations

import os
import select
import socket
import time
from typing import Any, Protocol

DEFAULT_PORT = 5000
DEFAULT_SERIAL_BAUD = 9600
DEFAULT_TIMEOUT = 2.0


class ByteTransport(Protocol):
    def connect(self) -> None:
        """Open the transport."""

    def send_all(self, data: bytes) -> None:
        """Send all bytes."""

    def recv(self, max_bytes: int) -> bytes:
        """Receive bytes, returning b'' on EOF."""

    def close(self) -> None:
        """Close the transport."""


class TcpTransport:
    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if not host:
            raise ValueError("host is required")
        if port <= 0 or port > 65535:
            raise ValueError("port must be in range 1..65535")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        self.close()
        self._socket = socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        )
        self._socket.settimeout(self.timeout)

    def send_all(self, data: bytes) -> None:
        if self._socket is None:
            raise ConnectionError("transport is not connected")
        self._socket.sendall(data)

    def recv(self, max_bytes: int) -> bytes:
        if self._socket is None:
            raise ConnectionError("transport is not connected")
        return self._socket.recv(max_bytes)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> TcpTransport:
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


class SerialTransport:
    def __init__(
        self,
        path: str,
        baud: int = DEFAULT_SERIAL_BAUD,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if not path:
            raise ValueError("serial port is required")
        if baud != 9600:
            raise ValueError("only 9600 baud is supported")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.path = path
        self.baud = baud
        self.timeout = timeout
        self._fd: int | None = None

    def connect(self) -> None:
        self.close()
        fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            termios_module = _termios()
            self._configure(fd, termios_module)
            termios_module.tcflush(fd, termios_module.TCIOFLUSH)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def send_all(self, data: bytes) -> None:
        if self._fd is None:
            raise ConnectionError("transport is not connected")
        offset = 0
        deadline = time.monotonic() + self.timeout
        while offset < len(data):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("serial write timed out")
            _readable, writable, _errors = select.select([], [self._fd], [], remaining)
            if not writable:
                raise TimeoutError("serial write timed out")
            offset += os.write(self._fd, data[offset:])

    def recv(self, max_bytes: int) -> bytes:
        if self._fd is None:
            raise ConnectionError("transport is not connected")
        readable, _writable, _errors = select.select([self._fd], [], [], self.timeout)
        if not readable:
            raise TimeoutError("serial read timed out")
        return os.read(self._fd, max_bytes)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> SerialTransport:
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    @staticmethod
    def _configure(fd: int, termios_module: Any) -> None:
        attrs = termios_module.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = (
            termios_module.CREAD | termios_module.CLOCAL | termios_module.CS8
        )
        attrs[3] = 0
        attrs[4] = termios_module.B9600
        attrs[5] = termios_module.B9600
        attrs[6][termios_module.VMIN] = 0
        attrs[6][termios_module.VTIME] = 0
        termios_module.tcsetattr(fd, termios_module.TCSANOW, attrs)


def _termios() -> Any:
    try:
        import termios
    except ImportError as exc:
        raise OSError("serial transport requires POSIX termios support") from exc
    return termios
