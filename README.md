# ViewSonic LFD Python Client

Small, dependency-free Python CLI and client library for ViewSonic CDE/LFD
displays using the raw byte control protocol over TCP or RS-232.

The first target is the ViewSonic CDE4314-2C over TCP port `5000`. The
application protocol is kept separate from transport I/O so the same packet
logic is used over RS-232.

## Installation

From a checkout:

```bash
python3 -m pip install .
```

Directly from GitHub:

```bash
python3 -m pip install git+https://github.com/arturormk/viewsonic-lfd-control.git
```

## Requirements

- Python `3.10` or newer.
- Optional: [`uv`](https://docs.astral.sh/uv/) for environment and command
  management.

## Usage

Run from the repository root:

```bash
python3 vslfd.py --host 192.0.2.15 power get
python3 vslfd.py --host 192.0.2.15 volume set 20
python3 vslfd.py --host 192.0.2.15 input set hdmi1
python3 vslfd.py --serial-port /dev/ttyUSB0 power get
```

or:

```bash
python3 -m viewsonic_lfd --host 192.0.2.15 power get
```

After installation, the console command is:

```bash
vslfd --host 192.0.2.15 power get
vslfd --serial-port /dev/ttyUSB0 power get
```

## Global Options

Global options must appear before the command group:

```bash
vslfd [global-options] <command-group> ...
```

| Option | Environment variable | Default |
|---|---|---|
| `--host HOST` | `VIEWSONIC_LFD_HOST` | required for TCP |
| `--port PORT` | `VIEWSONIC_LFD_PORT` | `5000` |
| `--serial-port PATH` | `VIEWSONIC_LFD_SERIAL_PORT` | required for RS-232 |
| `--display-id ID` | `VIEWSONIC_LFD_DISPLAY_ID` | `01` |
| `--timeout SECONDS` | `VIEWSONIC_LFD_TIMEOUT` | `2.0` |
| `--retries COUNT` | `VIEWSONIC_LFD_RETRIES` | `1` |

Use either `--host` for TCP or `--serial-port` for RS-232, not both. The
RS-232 transport uses the ViewSonic-documented `9600 8N1` settings and the
same CR-terminated protocol packets as TCP.

Other global options:

| Option | Meaning |
|---|---|
| `--json` | Print structured JSON output. |
| `--verbose` | Print request/response packets and parsed fields. |
| `--version` | Print the installed client version. |

## Examples

```bash
vslfd --host 192.0.2.15 power get
vslfd --host 192.0.2.15 power set on
vslfd --host 192.0.2.15 brightness set up
vslfd --host 192.0.2.15 mute set off
vslfd --host 192.0.2.15 raw get l
vslfd --host 192.0.2.15 probe safe
vslfd --serial-port /dev/ttyUSB0 power get
```

The `raw` commands are intended for controlled protocol probing. Destructive
raw Set packets require `--allow-destructive`.

## Development

```bash
uv run python -m unittest
uv run ruff check .
uv run mypy
uv build
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

This is an independent project and is not affiliated with, endorsed by, or
sponsored by ViewSonic.
