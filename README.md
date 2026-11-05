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

### Input sources

```bash
vslfd input list                              # names, codes, aliases (no connection needed)
vslfd --host 192.0.2.15 input set hdmi2
vslfd --host 192.0.2.15 input set "DisplayPort 1"
vslfd --host 192.0.2.15 input set 0A          # two-character code also works
vslfd --host 192.0.2.15 input get             # e.g. "Input: HDMI 1 (hdmi1), signal detected"
```

Names are matched ignoring case, spaces, `-` and `_`, so `hdmi1`, `HDMI 1`
and `hdmi-1` are equivalent. Not every input exists on every model; the display
rejects unsupported inputs with a NACK.

### Input signal detection

`signal get` reports whether the active input currently has a video signal.
It reads the signal flag from the input Get reply, so it costs a single
request:

```bash
vslfd --host 192.0.2.15 signal get            # "Signal: detected on HDMI 1"
vslfd --host 192.0.2.15 --json signal get     # adds an "input" object with "signal": true/false
```

| Exit code | Meaning |
|---|---|
| `0` | Signal detected |
| `1` | Error (connection, timeout, rejected request, ...) |
| `2` | Invalid command-line usage |
| `3` | No signal on the active input |
| `4` | Reply did not include a recognizable signal flag |

This makes it usable directly from shell scripts and monitoring checks:

```bash
vslfd --host 192.0.2.15 signal get || echo "display has no video signal"
```

The result is a snapshot of the moment of the query. To keep a history (for
example, to show when the source started sending video), log it periodically,
e.g. from cron every 5 minutes:

```cron
*/5 * * * * echo "$(date -Is) $(vslfd --host 192.0.2.15 power get) | $(vslfd --host 192.0.2.15 signal get 2>&1)" >> $HOME/vslfd-signal.log
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
