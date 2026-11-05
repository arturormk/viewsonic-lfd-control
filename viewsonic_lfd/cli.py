"""Command-line interface for ViewSonic LFD displays."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import __version__
from .client import (
    BACKLIGHT_LEVEL_SET_COMMAND,
    BACKLIGHT_ON_OFF_SET_COMMAND,
    BOOL_STATE_NAMES,
    BOOL_VALUES,
    BRIGHTNESS_GET_COMMAND,
    BRIGHTNESS_SET_COMMAND,
    BUTTON_LOCK_GET_COMMAND,
    BUTTON_LOCK_SET_COMMAND,
    DEFAULT_DISPLAY_ID,
    DEFAULT_RETRIES,
    INPUT_SOURCES,
    LOCK_STATE_NAMES,
    MENU_LOCK_SET_COMMAND,
    MUTE_GET_COMMAND,
    MUTE_SET_COMMAND,
    POWER_LOCK_GET_COMMAND,
    POWER_LOCK_SET_COMMAND,
    REMOTE_CONTROL_GET_COMMAND,
    REMOTE_CONTROL_NAMES,
    REMOTE_CONTROL_SET_COMMAND,
    REMOTE_CONTROL_VALUES,
    VOLUME_GET_COMMAND,
    VOLUME_SET_COMMAND,
    ViewSonicLfdClient,
    ViewSonicLfdError,
    ViewSonicTransaction,
    resolve_input,
)
from .protocol import hex_bytes, validate_display_id, validate_field3
from .transport import DEFAULT_PORT, DEFAULT_TIMEOUT

ENV_HOST = "VIEWSONIC_LFD_HOST"
ENV_PORT = "VIEWSONIC_LFD_PORT"
ENV_SERIAL_PORT = "VIEWSONIC_LFD_SERIAL_PORT"
ENV_DISPLAY_ID = "VIEWSONIC_LFD_DISPLAY_ID"
ENV_TIMEOUT = "VIEWSONIC_LFD_TIMEOUT"
ENV_RETRIES = "VIEWSONIC_LFD_RETRIES"


@dataclass(frozen=True)
class CliConfig:
    host: str | None
    port: int
    serial_port: str | None
    display_id: str
    timeout: float
    retries: int
    json_output: bool
    verbose: bool


def parse_port(value: str) -> int:
    try:
        port = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid port: {value}") from exc
    if port <= 0 or port > 65535:
        raise argparse.ArgumentTypeError("port must be in range 1..65535")
    return port


def parse_positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid number: {value}") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def parse_nonnegative_int(value: str) -> int:
    try:
        number = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return number


def parse_display_id(value: str) -> str:
    try:
        return validate_display_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_serial_port(value: str) -> str:
    path = value.strip()
    if not path:
        raise argparse.ArgumentTypeError("serial port must not be empty")
    return path


def parse_value3(value: str) -> str:
    try:
        return validate_field3(value, "value")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def env_or_default(
    args: argparse.Namespace,
    field: str,
    env: Mapping[str, str],
    env_name: str,
    default: Any,
    parser: Any,
) -> Any:
    arg_value = getattr(args, field)
    if arg_value is not None:
        return arg_value
    env_value = env.get(env_name)
    if env_value is None:
        return default
    try:
        return parser(env_value)
    except argparse.ArgumentTypeError as exc:
        raise ValueError(f"{env_name}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vslfd",
        description="ViewSonic LFD command-line client",
    )
    parser.add_argument("--host", help=f"monitor IP/host, or {ENV_HOST}")
    parser.add_argument("--port", type=parse_port, help=f"default: {DEFAULT_PORT}")
    parser.add_argument(
        "--serial-port",
        type=parse_serial_port,
        help=f"RS-232 device path, or {ENV_SERIAL_PORT}",
    )
    parser.add_argument(
        "--display-id",
        type=parse_display_id,
        help=f"display ID, or {ENV_DISPLAY_ID}; default: {DEFAULT_DISPLAY_ID}",
    )
    parser.add_argument(
        "--timeout",
        type=parse_positive_float,
        help=f"I/O timeout seconds, default: {DEFAULT_TIMEOUT}",
    )
    parser.add_argument(
        "--retries",
        type=parse_nonnegative_int,
        help=f"retry count after timeout/failure, default: {DEFAULT_RETRIES}",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--verbose", action="store_true", help="print packet details")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subcommands = parser.add_subparsers(dest="group", required=True)

    power = subcommands.add_parser("power", help="power-state commands")
    power_subcommands = power.add_subparsers(dest="action", required=True)
    power_subcommands.add_parser("get", help="read power state")
    power_set = power_subcommands.add_parser("set", help="set power state")
    power_set.add_argument("state", choices=("on", "standby", "off"))

    input_cmd = subcommands.add_parser("input", help="input-source commands")
    input_subcommands = input_cmd.add_subparsers(dest="action", required=True)
    input_subcommands.add_parser("get", help="read input source")
    input_subcommands.add_parser("list", help="list known input names and codes")
    input_set = input_subcommands.add_parser("set", help="set input source")
    input_set.add_argument(
        "source",
        help="input name (e.g. hdmi1, dp, usb-c, ops, android; see 'input list'), "
        "two-character code (e.g. 04), or raw three-byte value",
    )

    brightness = subcommands.add_parser("brightness", help="brightness commands")
    add_percentage_commands(brightness)

    volume = subcommands.add_parser("volume", help="volume commands")
    add_percentage_commands(volume)

    mute = subcommands.add_parser("mute", help="mute commands")
    add_bool_commands(mute, ("on", "off"))

    backlight = subcommands.add_parser("backlight", help="backlight commands")
    backlight_subcommands = backlight.add_subparsers(dest="action", required=True)
    backlight_level = backlight_subcommands.add_parser(
        "set-level",
        help="set backlight level",
    )
    backlight_level.add_argument("value", help="0..100, up, or down")
    backlight_set = backlight_subcommands.add_parser("set", help="set backlight on/off")
    backlight_set.add_argument("state", choices=("on", "off"))

    lock = subcommands.add_parser("lock", help="lock commands")
    lock_targets = lock.add_subparsers(dest="target", required=True)
    for target in ("power", "button", "menu"):
        target_parser = lock_targets.add_parser(target, help=f"{target} lock")
        target_subcommands = target_parser.add_subparsers(dest="action", required=True)
        if target != "menu":
            target_subcommands.add_parser("get", help=f"read {target} lock")
        target_set = target_subcommands.add_parser("set", help=f"set {target} lock")
        target_set.add_argument("state", choices=("lock", "unlock"))

    remote = subcommands.add_parser("remote-control", help="remote-control commands")
    remote_subcommands = remote.add_subparsers(dest="action", required=True)
    remote_subcommands.add_parser("get", help="read remote-control mode")
    remote_set = remote_subcommands.add_parser("set", help="set remote-control mode")
    remote_set.add_argument("mode", choices=("disable", "enable", "pass-through"))

    keypad = subcommands.add_parser("keypad", help="keypad emulation")
    keypad_subcommands = keypad.add_subparsers(dest="action", required=True)
    keypad_press = keypad_subcommands.add_parser("press", help="press a keypad key")
    keypad_press.add_argument(
        "key",
        choices=("up", "down", "left", "right", "enter", "input", "menu-exit", "exit"),
    )

    date_cmd = subcommands.add_parser("date", help="date commands")
    date_subcommands = date_cmd.add_subparsers(dest="action", required=True)
    date_set = date_subcommands.add_parser("set", help="set one date component")
    date_set.add_argument("part", choices=("year", "month", "day"))
    date_set.add_argument("value", type=parse_nonnegative_int)

    time_cmd = subcommands.add_parser("time", help="time commands")
    time_subcommands = time_cmd.add_subparsers(dest="action", required=True)
    time_set = time_subcommands.add_parser("set", help="set one time component")
    time_set.add_argument("part", choices=("hour", "minute", "second"))
    time_set.add_argument("value", type=parse_nonnegative_int)

    raw = subcommands.add_parser("raw", help="raw protocol commands")
    raw_subcommands = raw.add_subparsers(dest="action", required=True)
    raw_get = raw_subcommands.add_parser("get", help="send raw Get request")
    raw_get.add_argument("command")
    raw_get.add_argument("selector", nargs="?", default="000", type=parse_value3)
    raw_set = raw_subcommands.add_parser("set", help="send raw Set request")
    raw_set.add_argument("command_type")
    raw_set.add_argument("command")
    raw_set.add_argument("value", type=parse_value3)
    raw_set.add_argument(
        "--allow-destructive",
        action="store_true",
        help="allow destructive raw Set commands such as restore defaults",
    )

    probe = subcommands.add_parser("probe", help="safe read-only probing")
    probe_subcommands = probe.add_subparsers(dest="action", required=True)
    probe_subcommands.add_parser("safe", help="run safe read-only probe sequence")

    return parser


def add_percentage_commands(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="action", required=True)
    subcommands.add_parser("get", help="read current value")
    set_cmd = subcommands.add_parser("set", help="set current value")
    set_cmd.add_argument("value", help="0..100, up, or down")


def add_bool_commands(
    parser: argparse.ArgumentParser,
    choices: tuple[str, ...],
) -> None:
    subcommands = parser.add_subparsers(dest="action", required=True)
    subcommands.add_parser("get", help="read current state")
    set_cmd = subcommands.add_parser("set", help="set current state")
    set_cmd.add_argument("state", choices=choices)


def config_from_args(args: argparse.Namespace, env: Mapping[str, str]) -> CliConfig:
    host = args.host or env.get(ENV_HOST)
    serial_port = args.serial_port or env.get(ENV_SERIAL_PORT)
    if serial_port is not None:
        try:
            serial_port = parse_serial_port(serial_port)
        except argparse.ArgumentTypeError as exc:
            raise ValueError(f"{ENV_SERIAL_PORT}: {exc}") from exc
    if host and serial_port:
        raise ValueError("--host and --serial-port are mutually exclusive")
    if serial_port and (args.port is not None or ENV_PORT in env):
        raise ValueError("--port cannot be used with --serial-port")
    if not host and not serial_port:
        raise ValueError(
            f"host or serial port is required; pass --host, --serial-port, "
            f"or set {ENV_HOST}/{ENV_SERIAL_PORT}"
        )

    return CliConfig(
        host=host,
        port=env_or_default(args, "port", env, ENV_PORT, DEFAULT_PORT, parse_port),
        serial_port=serial_port,
        display_id=env_or_default(
            args,
            "display_id",
            env,
            ENV_DISPLAY_ID,
            DEFAULT_DISPLAY_ID,
            parse_display_id,
        ),
        timeout=env_or_default(
            args,
            "timeout",
            env,
            ENV_TIMEOUT,
            DEFAULT_TIMEOUT,
            parse_positive_float,
        ),
        retries=env_or_default(
            args,
            "retries",
            env,
            ENV_RETRIES,
            DEFAULT_RETRIES,
            parse_nonnegative_int,
        ),
        json_output=args.json,
        verbose=args.verbose,
    )


def print_result(payload: dict[str, object], config: CliConfig) -> None:
    if config.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(payload["message"])
    transaction = payload.get("transaction")
    if config.verbose and isinstance(transaction, dict):
        print(f"Request: {transaction['request']}")
        print(f"Request bytes: {transaction['request_escaped']}")
        response = transaction.get("response")
        if isinstance(response, dict):
            print(f"Response: {response['raw']}")
            print(f"Response bytes: {response['raw_escaped']}")
            print(
                "Parsed: "
                f"kind={response['kind']} "
                f"display_id={response['display_id']} "
                f"command={response['command']} "
                f"value={response['value']!r} "
                f"accepted={response['accepted']}"
            )
        skipped = transaction.get("skipped")
        if skipped:
            print(f"Skipped: {skipped}")


def payload(message: str, transaction: ViewSonicTransaction) -> dict[str, object]:
    return {
        "message": message,
        "transaction": transaction.to_dict(),
    }


def run_command(
    args: argparse.Namespace,
    client: ViewSonicLfdClient,
) -> tuple[str, Any]:
    if args.group == "power" and args.action == "get":
        state, transaction = client.get_power()
        return f"Power: {state}", transaction
    if args.group == "power" and args.action == "set":
        return f"Power set to {args.state}", client.set_power(args.state)

    if args.group == "input" and args.action == "get":
        source, transaction = client.get_input()
        return f"Input: {source}", transaction
    if args.group == "input" and args.action == "set":
        transaction = client.set_input(args.source)
        try:
            target = resolve_input(args.source)
            label = f"{target.label} ({target.name})"
        except ValueError:
            label = args.source
        return f"Input set to {label}", transaction

    if args.group == "brightness" and args.action == "get":
        value, transaction = client.get_percentage(BRIGHTNESS_GET_COMMAND, "brightness")
        return f"Brightness: {value}", transaction
    if args.group == "brightness" and args.action == "set":
        return (
            f"Brightness set to {args.value}",
            client.set_percentage_or_step(
                BRIGHTNESS_SET_COMMAND,
                args.value,
                "brightness",
            ),
        )

    if args.group == "volume" and args.action == "get":
        value, transaction = client.get_percentage(VOLUME_GET_COMMAND, "volume")
        return f"Volume: {value}", transaction
    if args.group == "volume" and args.action == "set":
        return (
            f"Volume set to {args.value}",
            client.set_percentage_or_step(VOLUME_SET_COMMAND, args.value, "volume"),
        )

    if args.group == "mute" and args.action == "get":
        state, transaction = client.get_bool(MUTE_GET_COMMAND, BOOL_STATE_NAMES, "mute")
        return f"Mute: {state}", transaction
    if args.group == "mute" and args.action == "set":
        return (
            f"Mute set to {args.state}",
            client.set_named_value(MUTE_SET_COMMAND, args.state, BOOL_VALUES),
        )

    if args.group == "backlight" and args.action == "set-level":
        return (
            f"Backlight level set to {args.value}",
            client.set_percentage_or_step(
                BACKLIGHT_LEVEL_SET_COMMAND,
                args.value,
                "backlight",
                command_type="A",
            ),
        )
    if args.group == "backlight" and args.action == "set":
        return (
            f"Backlight set to {args.state}",
            client.set_named_value(
                BACKLIGHT_ON_OFF_SET_COMMAND,
                args.state,
                BOOL_VALUES,
            ),
        )

    if args.group == "lock":
        return run_lock_command(args, client)

    if args.group == "remote-control" and args.action == "get":
        state, transaction = client.get_bool(
            REMOTE_CONTROL_GET_COMMAND,
            REMOTE_CONTROL_NAMES,
            "remote-control",
        )
        return f"Remote control: {state}", transaction
    if args.group == "remote-control" and args.action == "set":
        return (
            f"Remote control set to {args.mode}",
            client.set_named_value(
                REMOTE_CONTROL_SET_COMMAND,
                args.mode,
                REMOTE_CONTROL_VALUES,
            ),
        )

    if args.group == "keypad" and args.action == "press":
        return f"Keypad pressed: {args.key}", client.press_keypad(args.key)

    if args.group == "date" and args.action == "set":
        return (
            f"Date {args.part} set to {args.value}",
            client.set_date_part(args.part, args.value),
        )

    if args.group == "time" and args.action == "set":
        return (
            f"Time {args.part} set to {args.value}",
            client.set_time_part(args.part, args.value),
        )

    if args.group == "raw" and args.action == "get":
        transaction = client.raw_get(args.command, args.selector)
        raw_value = (
            "" if transaction.response is None else transaction.response.value_text
        )
        return f"Raw Get value: {raw_value}", transaction
    if args.group == "raw" and args.action == "set":
        return (
            "Raw Set accepted",
            client.raw_set(
                args.command_type,
                args.command,
                args.value,
                allow_destructive=args.allow_destructive,
            ),
        )

    if args.group == "probe" and args.action == "safe":
        transactions = client.probe_safe()
        return f"Safe probe completed: {len(transactions)} commands", transactions

    raise ValueError("unsupported command")


def run_lock_command(
    args: argparse.Namespace,
    client: ViewSonicLfdClient,
) -> tuple[str, ViewSonicTransaction]:
    commands = {
        "power": (POWER_LOCK_GET_COMMAND, POWER_LOCK_SET_COMMAND),
        "button": (BUTTON_LOCK_GET_COMMAND, BUTTON_LOCK_SET_COMMAND),
        "menu": (None, MENU_LOCK_SET_COMMAND),
    }
    get_command, set_command = commands[args.target]
    if args.action == "get":
        if get_command is None:
            raise ValueError("menu lock Get is ambiguous in the protocol docs")
        state, transaction = client.get_bool(get_command, LOCK_STATE_NAMES, args.target)
        return f"{args.target.title()} lock: {state}", transaction
    if args.action == "set":
        return (
            f"{args.target.title()} lock set to {args.state}",
            client.set_named_value(set_command, args.state, BOOL_VALUES),
        )
    raise ValueError("unsupported lock command")


def print_probe(
    message: str,
    transactions: list[ViewSonicTransaction],
    config: CliConfig,
) -> None:
    result = {
        "message": message,
        "transactions": [transaction.to_dict() for transaction in transactions],
    }
    if config.json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(message)
    for transaction in transactions:
        response = transaction.response
        response_text = "no response"
        if response is not None:
            response_text = (
                f"{response.kind} command={response.command!r} "
                f"value={response.value_text!r} raw={response.raw_hex}"
            )
        print(f"{hex_bytes(transaction.request)} -> {response_text}")


def format_input_list(json_output: bool) -> str:
    if json_output:
        return json.dumps(
            [
                {
                    "name": src.name,
                    "label": src.label,
                    "code": src.code,
                    "set_value": src.set_value,
                    "aliases": list(src.aliases),
                }
                for src in INPUT_SOURCES
            ],
            indent=2,
        )
    lines = [f"{'NAME':<16} {'CODE':<5} {'LABEL':<32} ALIASES"]
    for src in INPUT_SOURCES:
        lines.append(
            f"{src.name:<16} {src.code:<5} {src.label:<32} {', '.join(src.aliases)}"
        )
    lines.append("Not every input is available on every model.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.group == "input" and args.action == "list":
        print(format_input_list(args.json))
        return 0

    try:
        config = config_from_args(args, os.environ)
        client = ViewSonicLfdClient(
            host=config.host,
            port=config.port,
            serial_port=config.serial_port,
            display_id=config.display_id,
            timeout=config.timeout,
            retries=config.retries,
        )
        message, result = run_command(args, client)
        if isinstance(result, list):
            print_probe(message, result, config)
        else:
            print_result(payload(message, result), config)
        return 0
    except (ValueError, ViewSonicLfdError, OSError) as exc:
        parser.exit(1, f"vslfd: error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
