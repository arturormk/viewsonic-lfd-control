"""Packet construction and parsing for the ViewSonic LFD byte protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PacketKind = Literal[
    "set_ack",
    "get_reply",
    "extended_get_reply",
    "remote_key",
    "unknown",
]

MAX_BUFFER_SIZE = 4096


def hex_bytes(data: bytes) -> str:
    return data.hex(" ").upper()


def escaped_bytes(data: bytes) -> str:
    return repr(data)


def _ascii_len(value: str, name: str, length: int) -> None:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be ASCII") from exc
    if len(encoded) != length:
        raise ValueError(f"{name} must be exactly {length} ASCII byte(s)")


def validate_display_id(display_id: str) -> str:
    _ascii_len(display_id, "display_id", 2)
    if not display_id.isdigit():
        raise ValueError("display_id must contain two decimal digits")
    return display_id


def validate_command(value: str, name: str = "command") -> str:
    _ascii_len(value, name, 1)
    return value


def validate_field3(value: str, name: str) -> str:
    _ascii_len(value, name, 3)
    return value


def build_set(
    display_id: str,
    command: str,
    value: str,
    command_type: str = "s",
) -> bytes:
    validate_display_id(display_id)
    validate_command(command_type, "command_type")
    validate_command(command)
    validate_field3(value, "value")
    return f"8{display_id}{command_type}{command}{value}\r".encode("ascii")


def build_get(display_id: str, command: str, selector: str = "000") -> bytes:
    validate_display_id(display_id)
    validate_command(command)
    validate_field3(selector, "selector")
    return f"8{display_id}g{command}{selector}\r".encode("ascii")


@dataclass(frozen=True)
class ParsedPacket:
    kind: PacketKind
    display_id: str | None
    command: str | None
    value: bytes
    accepted: bool | None
    raw: bytes

    @property
    def raw_hex(self) -> str:
        return hex_bytes(self.raw)

    @property
    def value_text(self) -> str:
        return self.value.decode("ascii", errors="replace")

    def command_matches(self, display_id: str, command: str) -> bool:
        return self.display_id == display_id and self.command == command

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "display_id": self.display_id,
            "command": self.command,
            "value": self.value_text,
            "value_hex": hex_bytes(self.value),
            "accepted": self.accepted,
            "raw": self.raw_hex,
            "raw_escaped": escaped_bytes(self.raw),
        }


def classify_packet(packet: bytes) -> ParsedPacket:
    if not packet.endswith(b"\r"):
        raise ValueError("packet is not CR terminated")

    if len(packet) == 5 and packet[0:1] == b"4" and packet[3:4] in (b"+", b"-"):
        return ParsedPacket(
            kind="set_ack",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command=None,
            value=b"",
            accepted=packet[3:4] == b"+",
            raw=packet,
        )

    if len(packet) == 9 and packet[0:1] == b"8" and packet[3:4] == b"r":
        return ParsedPacket(
            kind="get_reply",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command=packet[4:5].decode("ascii", errors="replace"),
            value=packet[5:8],
            accepted=True,
            raw=packet,
        )

    if len(packet) >= 6 and packet[0:1] == b"2" and packet[3:4] == b"r":
        return ParsedPacket(
            kind="extended_get_reply",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command=packet[4:5].decode("ascii", errors="replace"),
            value=packet[5:-1].rstrip(b"\x00"),
            accepted=True,
            raw=packet,
        )

    if len(packet) == 7 and packet[0:1] == b"6" and packet[3:4] == b"p":
        return ParsedPacket(
            kind="remote_key",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command="p",
            value=packet[4:6],
            accepted=True,
            raw=packet,
        )

    return ParsedPacket(
        kind="unknown",
        display_id=None,
        command=None,
        value=packet[:-1],
        accepted=None,
        raw=packet,
    )


def extract_cr_packets(
    buffer: bytearray,
    max_size: int = MAX_BUFFER_SIZE,
) -> list[bytes]:
    if len(buffer) > max_size:
        raise ValueError(f"receive buffer exceeded {max_size} bytes without CR")

    packets: list[bytes] = []
    while True:
        index = buffer.find(b"\r")
        if index < 0:
            break
        packets.append(bytes(buffer[: index + 1]))
        del buffer[: index + 1]
    return packets


def parse_int3(value: bytes, name: str, minimum: int = 0, maximum: int = 100) -> int:
    text = value.decode("ascii", errors="strict")
    try:
        number = int(text, 10)
    except ValueError as exc:
        raise ValueError(f"{name} is not a decimal value: {text!r}") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be in range {minimum}..{maximum}")
    return number


def format_int3(value: int, name: str, minimum: int = 0, maximum: int = 100) -> str:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be in range {minimum}..{maximum}")
    return f"{value:03d}"
