"""Client and command wrappers for ViewSonic LFD displays."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .protocol import (
    ParsedPacket,
    build_get,
    build_set,
    classify_packet,
    extract_cr_packets,
    format_int3,
    hex_bytes,
    parse_int3,
    validate_display_id,
    validate_field3,
)
from .transport import (
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    ByteTransport,
    SerialTransport,
    TcpTransport,
)

DEFAULT_DISPLAY_ID = "01"
DEFAULT_RETRIES = 1

POWER_SET_COMMAND = "!"
POWER_GET_COMMAND = "l"
INPUT_SET_COMMAND = '"'
INPUT_GET_COMMAND = "j"
BRIGHTNESS_SET_COMMAND = "$"
BRIGHTNESS_GET_COMMAND = "b"
BACKLIGHT_LEVEL_SET_COMMAND = "B"
BACKLIGHT_ON_OFF_SET_COMMAND = "("
VOLUME_SET_COMMAND = "5"
VOLUME_GET_COMMAND = "f"
MUTE_SET_COMMAND = "6"
MUTE_GET_COMMAND = "g"
POWER_LOCK_SET_COMMAND = "4"
POWER_LOCK_GET_COMMAND = "o"
BUTTON_LOCK_SET_COMMAND = "8"
BUTTON_LOCK_GET_COMMAND = "p"
MENU_LOCK_SET_COMMAND = ">"
NUMBER_KEY_SET_COMMAND = "@"
KEYPAD_SET_COMMAND = "A"
REMOTE_CONTROL_SET_COMMAND = "B"
REMOTE_CONTROL_GET_COMMAND = "n"
DATE_SET_COMMAND = "V"
TIME_SET_COMMAND = "W"
ACK_GET_COMMAND = "z"
MAC_GET_COMMAND = "5"
IP_GET_COMMAND = "6"
SERIAL_GET_COMMAND = "7"
FIRMWARE_GET_COMMAND = "8"
RESTORE_DEFAULTS_COMMAND = "~"

POWER_SET_VALUES = {"standby": "000", "off": "000", "on": "001"}
POWER_GET_VALUES = {"000": "standby", "001": "on"}

INPUT_VALUES = {
    "hdmi1": "004",
    "hdmi-1": "004",
    "hdmi2": "014",
    "hdmi-2": "014",
    "hdmi3": "024",
    "hdmi-3": "024",
    "third-hdmi": "024",
    "vga": "006",
    "ops": "007",
    "slot-in-pc": "007",
    "displayport": "009",
    "display-port": "009",
    "dp": "009",
    "usb-c": "019",
    "usbc": "019",
    "type-c": "019",
    "embedded-android": "00A",
    "android": "00A",
    "main-android": "00A",
}

VALUE_TO_INPUT = {
    "004": "hdmi1",
    "014": "hdmi2",
    "024": "hdmi3",
    "006": "vga",
    "007": "ops",
    "009": "displayport",
    "019": "usb-c",
    "00A": "embedded-android",
}

BOOL_VALUES = {
    "off": "000",
    "on": "001",
    "unlock": "000",
    "unlocked": "000",
    "lock": "001",
    "locked": "001",
}

BOOL_STATE_NAMES = {
    "000": "off",
    "001": "on",
}

LOCK_STATE_NAMES = {
    "000": "unlock",
    "001": "lock",
}

KEYPAD_VALUES = {
    "up": "000",
    "down": "001",
    "left": "002",
    "right": "003",
    "enter": "004",
    "ok": "004",
    "input": "005",
    "menu-exit": "006",
    "menu": "006",
    "exit": "007",
}

REMOTE_CONTROL_VALUES = {
    "disable": "000",
    "disabled": "000",
    "enable": "001",
    "enabled": "001",
    "pass-through": "002",
    "passthrough": "002",
}

REMOTE_CONTROL_NAMES = {
    "000": "disable",
    "001": "enable",
    "002": "pass-through",
}


class ViewSonicLfdError(Exception):
    """Base error for ViewSonic LFD client operations."""


class ViewSonicLfdProtocolError(ViewSonicLfdError):
    """The display returned malformed or unexpected protocol data."""


class ViewSonicLfdNackError(ViewSonicLfdError):
    """The display rejected a Set request."""


@dataclass(frozen=True)
class ViewSonicTransaction:
    request: bytes
    response: ParsedPacket | None
    skipped: tuple[ParsedPacket, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "request": hex_bytes(self.request),
            "request_escaped": repr(self.request),
            "response": None if self.response is None else self.response.to_dict(),
            "skipped": [packet.to_dict() for packet in self.skipped],
        }


TransportFactory = Callable[[], ByteTransport]
GetKind = Literal["get_reply", "extended_get_reply"]


class ViewSonicLfdClient:
    def __init__(
        self,
        host: str | None = None,
        port: int = DEFAULT_PORT,
        display_id: str = DEFAULT_DISPLAY_ID,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        serial_port: str | None = None,
        transport_factory: TransportFactory | None = None,
    ):
        validate_display_id(display_id)
        if port <= 0 or port > 65535:
            raise ValueError("port must be in range 1..65535")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if retries < 0:
            raise ValueError("retries must be >= 0")
        if host and serial_port:
            raise ValueError("host and serial_port are mutually exclusive")
        if transport_factory is None and not host and not serial_port:
            raise ValueError("host is required")

        self.host = host
        self.port = port
        self.serial_port = serial_port
        self.display_id = display_id
        self.timeout = timeout
        self.retries = retries
        self._transport_factory = transport_factory

    def _new_transport(self) -> ByteTransport:
        if self._transport_factory is not None:
            return self._transport_factory()
        if self.serial_port is not None:
            return SerialTransport(self.serial_port, timeout=self.timeout)
        if self.host is None:
            raise ValueError("host is required")
        return TcpTransport(self.host, self.port, self.timeout)

    def build_set(
        self,
        command: str,
        value: str,
        command_type: str = "s",
    ) -> bytes:
        return build_set(self.display_id, command, value, command_type)

    def build_get(self, command: str, selector: str = "000") -> bytes:
        return build_get(self.display_id, command, selector)

    def send_raw(
        self,
        packet: bytes,
        expected_display_id: str | None = None,
        expected_command: str | None = None,
        expected_kinds: tuple[str, ...] | None = None,
    ) -> ViewSonicTransaction:
        attempts = self.retries + 1
        last_error: Exception | None = None
        for _ in range(attempts):
            transport = self._new_transport()
            try:
                transport.connect()
                transport.send_all(packet)
                response, skipped = self._recv_matching(
                    transport,
                    expected_display_id=expected_display_id,
                    expected_command=expected_command,
                    expected_kinds=expected_kinds,
                )
                return ViewSonicTransaction(
                    request=packet,
                    response=response,
                    skipped=tuple(skipped),
                )
            except (TimeoutError, ConnectionError, OSError, ViewSonicLfdError) as exc:
                last_error = exc
            finally:
                transport.close()

        if last_error is None:
            raise ViewSonicLfdError("transaction failed")
        raise ViewSonicLfdError(f"transaction failed: {last_error}") from last_error

    def raw_set(
        self,
        command_type: str,
        command: str,
        value: str,
        *,
        allow_destructive: bool = False,
    ) -> ViewSonicTransaction:
        if command == RESTORE_DEFAULTS_COMMAND and not allow_destructive:
            raise ValueError("restore-defaults requires --allow-destructive")
        packet = self.build_set(command, value, command_type)
        transaction = self.send_raw(
            packet,
            expected_display_id=self.display_id,
            expected_kinds=("set_ack",),
        )
        require_ack(transaction.response)
        return transaction

    def raw_get(self, command: str, selector: str = "000") -> ViewSonicTransaction:
        packet = self.build_get(command, selector)
        return self.send_raw(
            packet,
            expected_display_id=self.display_id,
            expected_command=command,
            expected_kinds=("get_reply", "extended_get_reply"),
        )

    def set_value(
        self,
        command: str,
        value: str,
        command_type: str = "s",
    ) -> ViewSonicTransaction:
        transaction = self.raw_set(command_type, command, value)
        require_ack(transaction.response)
        return transaction

    def get_value(self, command: str, selector: str = "000") -> ViewSonicTransaction:
        transaction = self.raw_get(command, selector)
        if transaction.response is None:
            raise ViewSonicLfdError("Get command did not return a response")
        return transaction

    def get_power(self) -> tuple[str, ViewSonicTransaction]:
        transaction = self.get_value(POWER_GET_COMMAND)
        state = value_name(transaction.response, POWER_GET_VALUES, "power")
        return state, transaction

    def set_power(self, state: str) -> ViewSonicTransaction:
        return self.set_value(POWER_SET_COMMAND, name_to_value(state, POWER_SET_VALUES))

    def set_input(self, source: str) -> ViewSonicTransaction:
        return self.set_value(INPUT_SET_COMMAND, input_name_to_value(source))

    def get_input(self) -> tuple[str, ViewSonicTransaction]:
        transaction = self.get_value(INPUT_GET_COMMAND)
        response = require_response(transaction.response)
        text = response.value_text
        if len(text) == 3 and text[:1] in ("0", "1"):
            input_code = text[1:]
            signal = "signal" if text[0] == "1" else "no-signal"
            name = VALUE_TO_INPUT.get(input_code, input_code)
            return f"{signal}:{name}", transaction
        return VALUE_TO_INPUT.get(text, text), transaction

    def get_percentage(
        self,
        command: str,
        label: str,
    ) -> tuple[int, ViewSonicTransaction]:
        transaction = self.get_value(command)
        value = parse_int3(require_response(transaction.response).value, label)
        return value, transaction

    def set_percentage_or_step(
        self,
        command: str,
        value: str,
        label: str,
        command_type: str = "s",
    ) -> ViewSonicTransaction:
        return self.set_value(
            command,
            percentage_or_step_to_value(value, label),
            command_type,
        )

    def get_bool(
        self,
        command: str,
        names: dict[str, str],
        label: str,
    ) -> tuple[str, ViewSonicTransaction]:
        transaction = self.get_value(command)
        return value_name(transaction.response, names, label), transaction

    def set_named_value(
        self,
        command: str,
        value: str,
        values: dict[str, str],
        command_type: str = "s",
    ) -> ViewSonicTransaction:
        return self.set_value(command, name_to_value(value, values), command_type)

    def press_keypad(self, key: str) -> ViewSonicTransaction:
        return self.set_named_value(KEYPAD_SET_COMMAND, key, KEYPAD_VALUES)

    def set_date_part(self, part: str, value: int) -> ViewSonicTransaction:
        prefixes = {"year": "Y", "month": "M", "day": "D"}
        limits = {"year": (0, 99), "month": (1, 12), "day": (1, 31)}
        if part not in prefixes:
            raise ValueError("date part must be year, month, or day")
        minimum, maximum = limits[part]
        if value < minimum or value > maximum:
            raise ValueError(f"{part} must be in range {minimum}..{maximum}")
        return self.set_value(DATE_SET_COMMAND, f"{prefixes[part]}{value:02d}")

    def set_time_part(self, part: str, value: int) -> ViewSonicTransaction:
        prefixes = {"hour": "H", "minute": "M", "second": "S"}
        limits = {"hour": (0, 23), "minute": (0, 59), "second": (0, 59)}
        if part not in prefixes:
            raise ValueError("time part must be hour, minute, or second")
        minimum, maximum = limits[part]
        if value < minimum or value > maximum:
            raise ValueError(f"{part} must be in range {minimum}..{maximum}")
        return self.set_value(TIME_SET_COMMAND, f"{prefixes[part]}{value:02d}")

    def probe_safe(self) -> list[ViewSonicTransaction]:
        commands = (
            ACK_GET_COMMAND,
            POWER_GET_COMMAND,
            BRIGHTNESS_GET_COMMAND,
            VOLUME_GET_COMMAND,
            MUTE_GET_COMMAND,
            INPUT_GET_COMMAND,
            MAC_GET_COMMAND,
            IP_GET_COMMAND,
            SERIAL_GET_COMMAND,
            FIRMWARE_GET_COMMAND,
        )
        return [self.raw_get(command) for command in commands]

    def _recv_matching(
        self,
        transport: ByteTransport,
        expected_display_id: str | None,
        expected_command: str | None,
        expected_kinds: tuple[str, ...] | None,
    ) -> tuple[ParsedPacket, list[ParsedPacket]]:
        buffer = bytearray()
        skipped: list[ParsedPacket] = []

        while True:
            chunk = transport.recv(1024)
            if not chunk:
                details = f"; skipped={format_packets(skipped)}" if skipped else ""
                raise ConnectionError(f"connection closed before response{details}")
            buffer.extend(chunk)
            packets = extract_cr_packets(buffer)
            for raw in packets:
                packet = classify_packet(raw)
                if packet_matches(
                    packet,
                    expected_display_id=expected_display_id,
                    expected_command=expected_command,
                    expected_kinds=expected_kinds,
                ):
                    return packet, skipped
                skipped.append(packet)


def packet_matches(
    packet: ParsedPacket,
    expected_display_id: str | None,
    expected_command: str | None,
    expected_kinds: tuple[str, ...] | None,
) -> bool:
    if expected_kinds is not None and packet.kind not in expected_kinds:
        return False
    if expected_display_id is not None and packet.display_id != expected_display_id:
        return False
    if expected_command is not None and packet.command != expected_command:
        return False
    return True


def require_response(packet: ParsedPacket | None) -> ParsedPacket:
    if packet is None:
        raise ViewSonicLfdError("missing response")
    return packet


def require_ack(packet: ParsedPacket | None) -> None:
    packet = require_response(packet)
    if packet.kind != "set_ack":
        raise ViewSonicLfdProtocolError(f"expected Set ACK, got {packet.kind}")
    if packet.accepted is not True:
        raise ViewSonicLfdNackError("display rejected Set command")


def name_to_value(name: str, values: dict[str, str]) -> str:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in values:
        return values[normalized]
    validate_field3(name, "value")
    return name


def input_name_to_value(name: str) -> str:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in INPUT_VALUES:
        return INPUT_VALUES[normalized]
    validate_field3(name, "input value")
    return name


def percentage_or_step_to_value(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in ("up", "+", "increase"):
        return "901"
    if normalized in ("down", "-", "decrease"):
        return "900"
    try:
        number = int(normalized, 10)
    except ValueError as exc:
        raise ValueError(f"{label} must be 0..100, up, or down") from exc
    return format_int3(number, label)


def value_name(
    packet: ParsedPacket | None,
    names: dict[str, str],
    label: str,
) -> str:
    response = require_response(packet)
    text = response.value_text
    if text in names:
        return names[text]
    return f"unknown-{label}:{text}"


def format_packets(packets: list[ParsedPacket]) -> str:
    return ", ".join(f"{packet.kind}:{packet.raw_hex}" for packet in packets)
