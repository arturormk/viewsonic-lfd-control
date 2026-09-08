# ViewSonic CDE4314-2C TCP/RS-232 Control Protocol

## Purpose

This document is an implementation-oriented protocol specification for a coding agent building a controller, CLI utility, library, daemon, Home Assistant integration, or test harness for a **ViewSonic CDE4314-2C** display.

It combines:

1. the **model-specific CDE14 Series User Guide**, which documents LAN transport on TCP port `5000` and the CDE14 Set-Function table;
2. the more complete official **ViewSonic IFP110 RS-232 Protocols** document, which describes the shared Get-Function, extended reply, automatic reply, and remote-control pass-through formats;
3. hardware observation on the target CDE4314-2C:
   - IP address: `192.0.2.15` in examples below;
   - TCP port `5000` is open;
   - Get-Power command `l` has been tested successfully.

The IFP110 is a different product family. Treat its Get commands and additional optional Set commands as **protocol-compatible candidates**, not guaranteed CDE4314-2C features, unless confirmed on the hardware.

---

## Source precedence and compatibility labels

When sources disagree, use this precedence:

1. **Hardware-confirmed on the CDE4314-2C**
2. **Documented in the CDE14 Series manual**
3. **Documented only in the IFP110 protocol document**
4. **Inference**

Compatibility labels used below:

| Label | Meaning |
|---|---|
| `confirmed` | Tested successfully on the target CDE4314-2C |
| `cde-documented` | Explicitly listed in the CDE14 Series manual |
| `supplemental` | Listed only in the IFP110 protocol document; probe before exposing |
| `ambiguous` | The source contains a collision, typo, or inconsistency |
| `destructive` | Can reset configuration or otherwise cause disruptive behavior |

Important transport difference:

- The CDE14 manual specifies **TCP port `5000`**.
- The IFP110 page specifies **TCP port `7142`** for that model.

For the CDE4314-2C, use **port `5000`**. Do not replace it with `7142`.

---

## Transport

### LAN transport for CDE4314-2C

| Property | Value |
|---|---|
| Physical interface | RJ45 Ethernet |
| Transport | TCP/IP |
| TCP port | `5000` |
| Wake-on-LAN | UDP port `9` |
| Cross-subnet control | Not supported by the manual |
| Authentication | None |
| Target currently observed | `192.0.2.15:5000` |

The application protocol is a raw ASCII-oriented byte protocol over TCP. It is not HTTP, Telnet, JSON, or line-oriented text in the usual LF sense.

TCP is a byte stream:

- one `send()` does not imply one `recv()`;
- a packet can arrive in fragments;
- several packets can arrive in one `recv()`;
- automatic status packets may arrive without a request.

Maintain a receive buffer and split packets on carriage return, byte `0x0D`.

### RS-232 transport

The same application-level protocol is documented for RS-232.

| Property | Value |
|---|---|
| Baud rate | `9600` bps |
| Data bits | `8` |
| Parity | None |
| Stop bits | `1` |
| Typical shorthand | `9600 8N1` |
| Cable | Crossover/null-modem |
| Flow control | Not specified |

### Connection lifecycle

The documents do not define a mandatory persistent-session policy. A robust implementation should:

1. allow persistent TCP connections;
2. serialize requests per connection;
3. reconnect after EOF, reset, timeout, standby transition, or socket error;
4. preserve partial receive data until CR arrives;
5. tolerate unsolicited automatic replies while connected.

---

## Encoding, fields, and terminator

Most protocol fields are ASCII bytes.

Every normal packet ends with:

```text
CR = carriage return = 0x0D = \r
```

Do not require or append LF (`0x0A`).

The leading Length field is itself an ASCII byte. For a standard eight-byte message body, the first byte is:

```text
ASCII "8" = 0x38
```

It is not binary `0x08`.

Extended 32-byte replies are an exception discussed later: the examples begin with ASCII `"2"` (`0x32`) even though the packet contains 32 bytes before CR. A parser must therefore not assume that the first byte can always be converted directly to a one-digit decimal byte count.

### Display ID

| ID | Meaning |
|---|---|
| `01` to `98` | Address an individual display |
| `99` | Broadcast Set command |
| Default | `01` |

For broadcast ID `99`, the documentation says only display ID `01` should reply.

The target display is assumed to use ID `01` unless changed in the OSD.

---

# Packet formats

## Set-Function request

A normal Set request contains eight bytes before CR and nine bytes including CR:

```text
8 II s C VVV \r
│ │  │ │  │   └─ CR, 0x0D
│ │  │ │  └──── three-byte ASCII value
│ │  │ └─────── one-byte ASCII command code
│ │  └───────── command type, normally "s"
│ └──────────── two-byte display ID
└────────────── ASCII "8"
```

Compact form:

```text
8IIsCVVV\r
```

Example: power on display ID `01`:

```text
801s!001\r
```

Hex:

```text
38 30 31 73 21 30 30 31 0D
```

### Set request builder

```python
def build_set(display_id: str, command: str, value: str,
              command_type: str = "s") -> bytes:
    assert len(display_id) == 2 and display_id.isdigit()
    assert len(command_type.encode("ascii")) == 1
    assert len(command.encode("ascii")) == 1
    assert len(value.encode("ascii")) == 3
    return f"8{display_id}{command_type}{command}{value}\r".encode("ascii")
```

A few source rows print an unusual command type such as `A`. Do not force all model-documented Set rows to `s`; preserve an explicit `command_type` field in the registry.

## Set-Function reply

Normal Set acknowledgement:

```text
4 II R \r
```

Where `R` is:

| Reply type | Meaning |
|---|---|
| `+` | Valid/accepted |
| `-` | Invalid, malformed, or unsupported |

Examples:

```text
401+\r
401-\r
```

The formal packet diagrams include length and ID even though the prose sometimes describes the reply merely as `+` or `-` followed by CR.

A positive acknowledgement means the command was accepted. It does not necessarily prove that the visible operation has fully completed.

---

## Get-Function request

The supplemental protocol explicitly states that a Get request has the same nine-byte structure as a Set request.

```text
8 II g C QQQ \r
│ │  │ │  │   └─ CR
│ │  │ │  └──── three-byte query argument/selector
│ │  │ └─────── Get command code
│ │  └───────── command type "g"
│ └──────────── display ID
└────────────── ASCII "8"
```

Compact form:

```text
8IIgCQQQ\r
```

For ordinary Get commands, `QQQ` is:

```text
000
```

Example: query power state from display ID `01`:

```text
801gl000\r
```

This exact form has been confirmed to work on the target CDE4314-2C.

### Important correction to the earlier hypothesis

Get commands do **not** omit the value bytes in the complete ViewSonic protocol. They retain a three-byte query field.

Most use `000`, but some use selectors:

- Date: `Y00`, `M00`, `D00`
- Time: `H00`, `M00`, `S00`
- Smart hub: `000`, `00A`, `00B`, `00C`, or `00D`

The short experimental packet `501gl\r` should not be used by the high-level implementation.

### Get request builder

```python
def build_get(display_id: str, command: str,
              selector: str = "000") -> bytes:
    assert len(display_id) == 2 and display_id.isdigit()
    assert len(command.encode("ascii")) == 1
    assert len(selector.encode("ascii")) == 3
    return f"8{display_id}g{command}{selector}\r".encode("ascii")
```

---

## Standard Get-Function reply

A valid ordinary Get response uses command type `r` and echoes the command code:

```text
8 II r C VVV \r
```

Example: power is on:

```text
801rl001\r
```

Example: power is in standby:

```text
801rl000\r
```

Example from the supplemental source: brightness `67` for ID `05`:

```text
805rb067\r
```

An invalid or unsupported Get request returns the normal short negative packet:

```text
4II-\r
```

Example:

```text
401-\r
```

### Standard Get parser

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class GetReply:
    display_id: str
    command: str
    value: bytes
    raw: bytes

def parse_standard_get(packet: bytes) -> GetReply:
    if len(packet) != 9 or packet[-1:] != b"\r":
        raise ValueError("not a standard Get reply")
    if packet[0:1] != b"8" or packet[3:4] != b"r":
        raise ValueError("not a valid standard Get reply")
    return GetReply(
        display_id=packet[1:3].decode("ascii"),
        command=packet[4:5].decode("ascii"),
        value=packet[5:8],
        raw=packet,
    )
```

Do not decode all response payloads as decimal integers. Date, time, temperature, input, and other values use structured ASCII.

---

## Extended 32-byte Get replies

Some Get commands use a fixed **32-byte reply body**, followed by CR.

The source examples begin with:

```text
0x32 = ASCII "2"
```

and then contain:

```text
ID[2] + "r" + command + payload + NUL padding
```

The examples are described as 32-byte replies, but the one-byte Length field cannot literally contain the decimal string `"32"`. Treat leading `"2"` as an extended-format marker used by this protocol revision, not as an independently trustworthy decimal length.

### Practical parser rule

Parse the TCP stream primarily by CR:

1. accumulate bytes until `0x0D`;
2. retain embedded NUL bytes (`0x00`);
3. if the packet begins with `b"2"` and is 33 bytes including CR, classify it as an extended reply;
4. parse bytes `1:3` as ID;
5. expect byte `3` to be `r`;
6. byte `4` is the echoed command;
7. bytes `5:-1` are a command-specific payload padded with NUL;
8. remove only trailing NUL padding, not meaningful spaces or punctuation.

```python
def parse_extended_get(packet: bytes) -> tuple[str, str, bytes]:
    if len(packet) != 33 or packet[-1:] != b"\r":
        raise ValueError("not a 32-byte extended reply")
    if packet[0:1] != b"2" or packet[3:4] != b"r":
        raise ValueError("invalid extended reply header")
    display_id = packet[1:3].decode("ascii")
    command = packet[4:5].decode("ascii")
    payload = packet[5:-1].rstrip(b"\x00")
    return display_id, command, payload
```

A real implementation should also preserve the untrimmed payload for diagnostics.

### Known extended replies

| Command | Meaning | Payload representation |
|---|---|---|
| `1` | Accumulated operation hours | Six ASCII decimal digits |
| `4` | Device name | ASCII string |
| `5` | MAC address | Twelve ASCII hex digits, no separators in the example |
| `6` | IP address | ASCII dotted-decimal string |
| `7` | Serial number | ASCII string |
| `8` | Firmware version | ASCII string |
| `:` | Smart-hub data | One or more fixed six-byte tagged fields |

Example operation hours `123456`:

```text
2 01 r 1 123456 <NUL padding> \r
```

Example MAC `00:11:22:aa:bb:cc`:

```text
2 01 r 5 001122aabbcc <NUL padding> \r
```

Example IP address `192.168.100.2`:

```text
2 01 r 6 192.168.100.2 <NUL padding> \r
```

The target CDE4314-2C may or may not implement every extended command. Probe each read-only command and record positive or negative results.

---

## Automatic replies

The supplemental protocol states that the display can send updated state automatically, without a Get request, when a user changes one of these through the remote, panel keys, or touch interface:

- Power
- Input
- Brightness
- Backlight
- Volume
- Mute

These packets are expected to use the same `r` reply form as Get responses.

Consequences for the client:

- do not assume every incoming `r` packet corresponds to the oldest pending request;
- match a requested reply by display ID and command code;
- dispatch unmatched `r` packets as state-change events;
- keep reading after a Set acknowledgement, because an automatic state packet may follow;
- serialize Get requests if the implementation does not maintain a command-aware pending-request queue.

---

## Remote-control pass-through

Enable pass-through using the model-documented Set command:

```text
801sB002\r
```

In pass-through mode:

- the display does not normally act on the pressed remote key;
- it emits a remote-control packet to the host;
- the supplemental document describes this over RS-232;
- behavior over the CDE4314-2C TCP connection is not guaranteed and must be tested.

Packet format:

```text
6 II p HH \r
│ │  │ │   └─ CR
│ │  │ └──── two ASCII hexadecimal key-code characters
│ │  └────── command type "p"
│ └───────── display ID
└─────────── ASCII "6"
```

Total size is seven bytes including CR.

Example: Volume Up from display ID `05`, code `10`:

```text
605p10\r
```

### Pass-through key codes

| Key | Code |
|---|---|
| `1` | `01` |
| `2` | `02` |
| `3` | `03` |
| `4` | `04` |
| `5` | `05` |
| `6` | `06` |
| `7` | `07` |
| `8` | `08` |
| `9` | `09` |
| `0` | `0A` |
| `-` | `0B` |
| Recall/Last | `0C` |
| Info/Display | `0D` |
| Aspect/Zoom/Size | `0F` |
| Volume Up | `10` |
| Volume Down | `11` |
| Mute | `12` |
| Channel/Page Up or Brightness+ | `13` |
| Channel/Page Down or Brightness- | `14` |
| Power | `15` |
| Sources/Input | `16` |
| Sleep | `19` |
| Menu | `1A` |
| Up | `1B` |
| Down | `1C` |
| Left | `1D` |
| Right | `1E` |
| OK/Enter/Set | `1F` |
| Exit | `20` |
| Red/F1 | `2C` |
| Green/F2 | `2D` |
| Yellow/F3 | `2E` |
| Blue/F4 | `2F` |

Reserved or undocumented codes include `0E`, `17`, `18`, and `21` through `2B`.

Pass-through notes from the supplemental source:

- the pass-through code is not necessarily the same as the physical remote's internal key code;
- Power has special behavior:
  - if the display is off, it turns on and then forwards Power;
  - if it is on, it forwards Power and then turns off;
- Power Lock can suppress the Power-key response;
- Volume Up/Down packets repeat while the key is held.

To leave pass-through mode:

```text
801sB001\r
```

This restores normal remote-control behavior.

---

# CDE4314-2C Set commands

The following table is model-specific to the CDE14 manual. Unless otherwise stated, packet construction is:

```text
8<ID><type><code><value>\r
```

## Basic Set commands

| Function | Type | Code | Values | Status and notes |
|---|---:|---:|---|---|
| Power | `s` | `!` | `000` standby; `001` on | `cde-documented`; LAN power-on may require an enabled network standby mode |
| Input | `s` | `"` | See input table | `cde-documented` |
| Brightness | `s` | `$` | `000`-`100`; `900` down; `901` up | `cde-documented` |
| Backlight level | `A` | `B` | `000`-`100` | `ambiguous`; unusual type `A` is printed in both sources |
| Power lock | `s` | `4` | `000` unlock; `001` lock | `cde-documented` |
| Volume | `s` | `5` | `000`-`100`; `900` down; `901` up | `cde-documented` |
| Mute | `s` | `6` | `000` off; `001` on | `cde-documented` |
| Button lock | `s` | `8` | `000` unlock; `001` lock | `cde-documented` |
| Menu lock | `s` | `>` | `000` unlock; `001` lock | `cde-documented` |
| Number key | `s` | `@` | `000`-`009` | `cde-documented` |
| Keypad emulation | `s` | `A` | See keypad table | `cde-documented` |
| Remote-control mode | `s` | `B` | `000` disable; `001` enable; `002` pass-through | `cde-documented` |
| Restore defaults | `s` | `~` | `000` | `destructive` |

### Input values documented for CDE14

| Value | Input |
|---|---|
| `004` | HDMI 1 |
| `014` | HDMI 2 |
| `024` | Third HDMI entry; the CDE table labels it only as HDMI |
| `006` | VGA |
| `007` | Slot-in PC / OPS |
| `009` | DisplayPort |
| `019` | USB Type-C |
| `00A` | Embedded/Main Android |

Examples:

```text
801s"004\r    HDMI 1
801s"014\r    HDMI 2
801s"024\r    third HDMI input
801s"019\r    USB Type-C
801s"00A\r    Embedded/Main Android
```

### Keypad values

| Value | Key |
|---|---|
| `000` | Up |
| `001` | Down |
| `002` | Left |
| `003` | Right |
| `004` | Enter |
| `005` | Input |
| `006` | Menu/Exit |
| `007` | Exit |

Examples:

```text
801sA000\r
801sA004\r
801sA005\r
801sA006\r
```

### Lock behavior

A client should provide explicit recovery commands because lock operations can make local operation difficult:

```text
801s4000\r    unlock power
801s8000\r    unlock buttons
801s>000\r    unlock menu
801sB001\r    enable remote control normally
```

## Optional Set commands documented for CDE14

| Function | Type | Code | Values | Notes |
|---|---:|---:|---|---|
| Contrast | `s` | `#` | `000`-`100` | Optional |
| Sharpness | `s` | `%` | `000`-`100` | Optional |
| Color | `s` | `&` | `000`-`100` | Optional |
| Tint | `s` | `'` | `000`-`100` | Optional |
| Backlight on/off | `s` | `(` | `000` off; `001` on | Source prints hex `29`, but ASCII `(` is `0x28` |
| Color mode | `s` | `)` | `000` normal; `001` warm; `002` cold; `003` personal | Optional |
| Freeze | `s` | `*` | `000` off; `001` on | CDE source character is consistent with hex `0x2A` |
| Bass | `s` | `.` | `000`-`100` | Optional |
| Treble | `s` | `/` | `000`-`100` | Optional |
| Balance | `s` | `0` | `000`-`100`; `050` center | Optional |
| Picture size | `s` | `1` | `000` 16:9; `001` 4:3; `002` 1:1 | Optional |
| OSD language | `s` | `2` | `000` English; `001` French; `002` Spanish | More languages may exist |
| Date | `s` | `V` | `Ynn`, `Mnn`, `Dnn` | Send one component per command |
| Time | `s` | `W` | `Hnn`, `Mnn`, `Snn` | 24-hour clock |
| Custom hot key | `s` | `X` | `001`-`999`; CDE source defines `001` as MVBA app | Optional |

Examples:

```text
801s#050\r    contrast 50
801s(001\r    backlight on
801s*001\r    freeze on
801s0050\r    balance 50
801sVY26\r    year 2026
801sVM08\r    month August
801sVD02\r    day 2
801sWH21\r    hour 21
801sWM00\r    minute 00
801sWS00\r    second 00
```

---

# Supplemental Set commands from the IFP110 protocol

These are not listed in the CDE14 Set table. Do not enable them automatically for the CDE4314-2C.

| Function | Type | Code | Values |
|---|---:|---:|---|
| Input cycle | `s` | `"` | `00Z` |
| Surround sound | `s` | `-` | `000` off; `001` on |
| PIP mode | `s` | `9` | `000` off; `001` PIP/POP; `002` PBP |
| PIP sound | `s` | `:` | `000` main; `001` sub |
| PIP position | `s` | `;` | `000` up; `001` down; `002` left; `003` right |
| PIP input | `s` | `7` | Input selector |
| Tiling mode | `s` | `P` | `000` off; `001` on |
| Tiling compensation | `s` | `Q` | `000` off; `001` on |
| Tiling H×V | `s` | `R` | Encoded horizontal and vertical counts |
| Tiling position | `s` | `S` | `001`-`025` |
| Function on/off multiplexer | `s` | `=` | See below |

Function multiplexer values from the supplemental source:

| Value | Meaning |
|---|---|
| `001` | Backlight off |
| `101` | Backlight on |
| `002` | Freeze off |
| `102` | Freeze on |
| `003` | Touch off |
| `103` | Touch on |

Additional input values from the IFP source include TV, AV, S-Video, YPbPr, HDMI4, DVI, additional VGA/DP/Type-C entries, and internal memory. They should not be copied into the CDE model registry without testing because physical inputs differ by model.

---

# Get commands

Unless a selector is shown, send:

```text
8<ID>g<code>000\r
```

Only Get-Power `l` is currently hardware-confirmed on the CDE4314-2C. All other rows are supplemental candidates.

## Basic Get commands

| Function | Code | Request selector | Response | Compatibility |
|---|---:|---|---|---|
| Brightness | `b` | `000` | `000`-`100` | `supplemental` |
| Backlight level | `B` | `000` | `000`-`100` | `ambiguous`; source row prints Get type `a` rather than `g` |
| Volume | `f` | `000` | `000`-`100` | `supplemental` |
| Mute | `g` | `000` | `000` off; `001` muted | `supplemental` |
| Input | `j` | `000` | Three-byte encoded status | `supplemental` |
| Power | `l` | `000` | `000` standby; `001` on | `confirmed` |
| Remote-control mode | `n` | `000` | `000` disabled; `001` enabled; `002` pass-through | `supplemental` |
| Power lock | `o` | `000` | `000` unlocked; `001` locked | `supplemental` |
| Button lock | `p` | `000` | `000` unlocked; `001` locked | `supplemental` |
| Menu lock | `l` as printed | `000` | `000` unlocked; `001` locked | `ambiguous`; collides with Power |
| ACK/link test | `z` | `000` | `000` | `supplemental`, safe probe |
| Thermal | `0` | `000` | `000`-`100` or negative `-01`-`-99` | `supplemental` |
| Operation hours | `1` | `000` | Extended reply, six decimal digits | `supplemental` |
| Device name | `4` | `000` | Extended ASCII reply | `supplemental` |
| MAC address | `5` | `000` | Extended ASCII reply | `supplemental` |
| IP address | `6` | `000` | Extended ASCII reply | `supplemental` |
| Serial number | `7` | `000` | Extended ASCII reply | `supplemental` |
| Firmware version | `8` | `000` | Extended ASCII reply | `supplemental` |

### Safe examples

```text
801gl000\r    get power
801gz000\r    communication ACK test
801gb000\r    get brightness
801gf000\r    get volume
801gg000\r    get mute
801gj000\r    get input
801g5000\r    get MAC address
801g6000\r    get IP address
801g7000\r    get serial number
801g8000\r    get firmware version
```

### Input response encoding

The supplemental source says:

- first response digit:
  - `0` = no signal;
  - `1` = signal detected;
- second and third digits identify the input.

Do not assume that the three-byte Get response is identical to the three-byte Set input value. Log real responses and build a CDE-specific mapping from observation.

### Thermal response

The documented examples/range allow:

```text
000 ... 100
-01 ... -99
```

The three-byte fixed field makes `-01` possible. Parse signed decimal text rather than an unsigned integer.

## Optional Get commands

| Function | Code | Selector | Response |
|---|---:|---|---|
| Contrast | `a` | `000` | `000`-`100` |
| Sharpness | `c` | `000` | `000`-`100` |
| Color | `d` | `000` | `000`-`100` |
| Tint | `e` | `000` | `000`-`100` |
| Backlight on/off | `h` | `000` | `000` off; `001` on |
| Freeze on/off | `i` | `000` | `000` off; `001` on |
| PIP mode | `t` | `000` | `000` off; `001` PIP/POP; `002` PBP |
| PIP input | `u` | `000` | Input selector |
| Tiling mode | `v` | `000` | `000` off; `001` on |
| Tiling compensation | `w` | `000` | `000` off; `001` on |
| Tiling H×V | `x` | `000` | Encoded H/V counts |
| Tiling position | `y` | `000` | `000` off or `001`-`025` |
| Date year | `2` | `Y00` | `Ynn` |
| Date month | `2` | `M00` | `Mnn` |
| Date day | `2` | `D00` | `Dnn` |
| Time hour | `3` | `H00` | `Hnn` |
| Time minute | `3` | `M00` | `Mnn` |
| Time second | `3` | `S00` | `Snn` |
| Smart hub, all | `:` | `000` | Extended tagged reply |
| Smart hub, temperature | `:` | `00A` | Extended `Axxxxx` field |
| Smart hub, humidity | `:` | `00B` | Extended `Bxxxxx` field |
| Smart hub, light | `:` | `00C` | Extended `Cxxxxx` field |
| Smart hub, PIR | `:` | `00D` | Extended `Dxxxxx` field |
| Function on/off | `=` | `000` or source-specific selector | Multiplexed state | `ambiguous`; source prints command type uppercase `G` |

Date example:

```text
801g2Y00\r    get year
801g2M00\r    get month
801g2D00\r    get day
```

Time example:

```text
801g3H00\r    get hour
801g3M00\r    get minute
801g3S00\r    get second
```

---

# Smart-hub extended payload

The supplemental source defines six-byte tagged fields:

| Tag | Field | Example |
|---|---|---|
| `A` | Ambient temperature | `A-05.0` |
| `B` | Ambient humidity | `B030.0` |
| `C` | Ambient light | `C00080` |
| `D` | PIR detection | `D00001` |

An all-fields payload can be concatenated:

```text
A-05.0B030.0C00080D00001
```

and NUL padded to the fixed extended response size.

This is unlikely to apply to the CDE4314-2C unless it contains the corresponding sensors. Keep it disabled unless the display returns a positive response.

---

# Unified receive parser

The parser must be binary-safe because extended packets contain NUL bytes.

## Packet classifier

Classify a CR-terminated packet in this order:

1. **Set/negative acknowledgement**
   - total length: 5 bytes;
   - body: `4<ID>+\r` or `4<ID>-\r`.

2. **Standard Get or automatic state reply**
   - total length: 9 bytes;
   - body: `8<ID>r<command><value3>\r`.

3. **Extended Get reply**
   - expected total length: 33 bytes;
   - body begins `2<ID>r<command>`;
   - payload is NUL padded.

4. **Remote pass-through**
   - total length: 7 bytes;
   - body: `6<ID>p<hex2>\r`.

5. **Unknown**
   - preserve and log without crashing.

## Reference classifier

```python
from dataclasses import dataclass
from typing import Literal

PacketKind = Literal[
    "set_ack",
    "get_reply",
    "extended_get_reply",
    "remote_key",
    "unknown",
]

@dataclass(frozen=True)
class ParsedPacket:
    kind: PacketKind
    display_id: str | None
    command: str | None
    value: bytes
    accepted: bool | None
    raw: bytes

def classify_packet(packet: bytes) -> ParsedPacket:
    if not packet.endswith(b"\r"):
        raise ValueError("packet is not CR terminated")

    if (
        len(packet) == 5
        and packet[0:1] == b"4"
        and packet[3:4] in (b"+", b"-")
    ):
        return ParsedPacket(
            kind="set_ack",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command=None,
            value=b"",
            accepted=packet[3:4] == b"+",
            raw=packet,
        )

    if (
        len(packet) == 9
        and packet[0:1] == b"8"
        and packet[3:4] == b"r"
    ):
        return ParsedPacket(
            kind="get_reply",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command=packet[4:5].decode("ascii", errors="replace"),
            value=packet[5:8],
            accepted=True,
            raw=packet,
        )

    if (
        len(packet) == 33
        and packet[0:1] == b"2"
        and packet[3:4] == b"r"
    ):
        return ParsedPacket(
            kind="extended_get_reply",
            display_id=packet[1:3].decode("ascii", errors="replace"),
            command=packet[4:5].decode("ascii", errors="replace"),
            value=packet[5:-1].rstrip(b"\x00"),
            accepted=True,
            raw=packet,
        )

    if (
        len(packet) == 7
        and packet[0:1] == b"6"
        and packet[3:4] == b"p"
    ):
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
```

The exact extended packet length should be verified on the CDE hardware. Keep an option to classify any `2<ID>r...CR` packet as extended even if its observed length differs from 33.

## TCP receive loop

```python
def extract_cr_packets(buffer: bytearray) -> list[bytes]:
    packets: list[bytes] = []
    while True:
        index = buffer.find(b"\r")
        if index < 0:
            break
        packets.append(bytes(buffer[:index + 1]))
        del buffer[:index + 1]
    return packets
```

Apply a maximum buffered-packet size, for example 4096 bytes, to avoid unbounded memory use on malformed input.

---

# Request/reply correlation

The protocol has no transaction ID.

Recommended policy:

- allow only one outstanding Set request at a time per display connection;
- allow only one outstanding Get request per command code;
- preferably serialize all requests until the hardware behavior is characterized;
- match standard/extended Get replies by:
  - display ID;
  - echoed command code;
- treat unmatched `r` packets as automatic state updates;
- treat `4<ID>-\r` as rejection of the current outstanding request, because it does not echo the command.

A Set command can produce:

1. a short `+` acknowledgement;
2. an automatic `r` state update;
3. both, possibly in separate TCP reads.

---

# Machine-readable registry

```yaml
device:
  model: "ViewSonic CDE4314-2C"
  host_observed: "192.0.2.15"
  display_id_default: "01"

transport:
  lan:
    protocol: tcp
    port: 5000
    authentication: false
    terminator_hex: "0D"
    cross_subnet_documented: false
  wol:
    protocol: udp
    port: 9
  serial:
    baud: 9600
    data_bits: 8
    parity: none
    stop_bits: 1

framing:
  set_request: "8{ID}s{CODE}{VALUE3}\\r"
  set_ack: "4{ID}{+|-}\\r"
  get_request: "8{ID}g{CODE}{SELECTOR3}\\r"
  get_reply: "8{ID}r{CODE}{VALUE3}\\r"
  extended_get_reply:
    prefix: "2{ID}r{CODE}"
    body_bytes_excluding_cr: 32
    padding: nul
  remote_pass_through: "6{ID}p{HEX2}\\r"

set_commands:
  power:
    type: "s"
    code: "!"
    values: {standby: "000", on: "001"}
    compatibility: cde-documented

  input:
    type: "s"
    code: '"'
    values:
      hdmi1: "004"
      hdmi2: "014"
      hdmi3_or_third_hdmi: "024"
      vga: "006"
      ops: "007"
      displayport: "009"
      usb_c: "019"
      embedded_android: "00A"
    compatibility: cde-documented

  brightness:
    type: "s"
    code: "$"
    numeric_range: [0, 100]
    special: {down: "900", up: "901"}
    compatibility: cde-documented

  backlight_level:
    type: "A"
    code: "B"
    numeric_range: [0, 100]
    compatibility: ambiguous
    warning: "Source prints command type A, not s"

  power_lock:
    type: "s"
    code: "4"
    values: {unlock: "000", lock: "001"}

  volume:
    type: "s"
    code: "5"
    numeric_range: [0, 100]
    special: {down: "900", up: "901"}

  mute:
    type: "s"
    code: "6"
    values: {off: "000", on: "001"}

  button_lock:
    type: "s"
    code: "8"
    values: {unlock: "000", lock: "001"}

  menu_lock:
    type: "s"
    code: ">"
    values: {unlock: "000", lock: "001"}

  number_key:
    type: "s"
    code: "@"
    numeric_range: [0, 9]

  keypad:
    type: "s"
    code: "A"
    values:
      up: "000"
      down: "001"
      left: "002"
      right: "003"
      enter: "004"
      input: "005"
      menu_exit: "006"
      exit: "007"

  remote_control:
    type: "s"
    code: "B"
    values:
      disable: "000"
      enable: "001"
      pass_through: "002"

  restore_defaults:
    type: "s"
    code: "~"
    values: {restore: "000"}
    destructive: true

  contrast: {type: "s", code: "#", numeric_range: [0, 100], optional: true}
  sharpness: {type: "s", code: "%", numeric_range: [0, 100], optional: true}
  color: {type: "s", code: "&", numeric_range: [0, 100], optional: true}
  tint: {type: "s", code: "'", numeric_range: [0, 100], optional: true}

  backlight_on_off:
    type: "s"
    code: "("
    values: {off: "000", on: "001"}
    optional: true
    warning: "Printed hex is inconsistent; ASCII '(' is 0x28"

  color_mode:
    type: "s"
    code: ")"
    values:
      normal: "000"
      warm: "001"
      cold: "002"
      personal: "003"
    optional: true

  freeze:
    type: "s"
    code: "*"
    values: {off: "000", on: "001"}
    optional: true

  bass: {type: "s", code: ".", numeric_range: [0, 100], optional: true}
  treble: {type: "s", code: "/", numeric_range: [0, 100], optional: true}

  balance:
    type: "s"
    code: "0"
    numeric_range: [0, 100]
    center: 50
    optional: true

  picture_size:
    type: "s"
    code: "1"
    values:
      full_16_9: "000"
      normal_4_3: "001"
      real_1_1: "002"
    optional: true

  osd_language:
    type: "s"
    code: "2"
    values:
      english: "000"
      french: "001"
      spanish: "002"
    optional: true

  date:
    type: "s"
    code: "V"
    formats: {year: "Ynn", month: "Mnn", day: "Dnn"}
    optional: true

  time:
    type: "s"
    code: "W"
    formats: {hour: "Hnn", minute: "Mnn", second: "Snn"}
    optional: true

get_commands:
  brightness:
    code: "b"
    selector: "000"
    response: decimal_000_100
    compatibility: supplemental

  backlight_level:
    code: "B"
    selector: "000"
    response: decimal_000_100
    compatibility: ambiguous
    warning: "Source table prints command type a instead of g"

  volume:
    code: "f"
    selector: "000"
    response: decimal_000_100
    compatibility: supplemental

  mute:
    code: "g"
    selector: "000"
    response_values: {off: "000", muted: "001"}
    compatibility: supplemental

  input:
    code: "j"
    selector: "000"
    response: signal_flag_plus_input
    compatibility: supplemental

  power:
    code: "l"
    selector: "000"
    response_values: {standby: "000", on: "001"}
    compatibility: confirmed

  remote_control:
    code: "n"
    selector: "000"
    response_values:
      disable: "000"
      enable: "001"
      pass_through: "002"
    compatibility: supplemental

  power_lock:
    code: "o"
    selector: "000"
    response_values: {unlock: "000", lock: "001"}
    compatibility: supplemental

  button_lock:
    code: "p"
    selector: "000"
    response_values: {unlock: "000", lock: "001"}
    compatibility: supplemental

  menu_lock:
    code: "l"
    selector: "000"
    compatibility: ambiguous
    warning: "Collides with documented Get-Power code"

  ack:
    code: "z"
    selector: "000"
    response_values: {ok: "000"}
    compatibility: supplemental

  thermal:
    code: "0"
    selector: "000"
    response: signed_temperature_text
    compatibility: supplemental

  operation_hours:
    code: "1"
    selector: "000"
    response: extended_six_digit_decimal
    compatibility: supplemental

  device_name:
    code: "4"
    selector: "000"
    response: extended_ascii
    compatibility: supplemental

  mac_address:
    code: "5"
    selector: "000"
    response: extended_ascii_hex12
    compatibility: supplemental

  ip_address:
    code: "6"
    selector: "000"
    response: extended_ascii_ip
    compatibility: supplemental

  serial_number:
    code: "7"
    selector: "000"
    response: extended_ascii
    compatibility: supplemental

  firmware_version:
    code: "8"
    selector: "000"
    response: extended_ascii
    compatibility: supplemental

  contrast: {code: "a", selector: "000", compatibility: supplemental}
  sharpness: {code: "c", selector: "000", compatibility: supplemental}
  color: {code: "d", selector: "000", compatibility: supplemental}
  tint: {code: "e", selector: "000", compatibility: supplemental}
  backlight_on_off: {code: "h", selector: "000", compatibility: supplemental}
  freeze: {code: "i", selector: "000", compatibility: supplemental}
  pip_mode: {code: "t", selector: "000", compatibility: supplemental}
  pip_input: {code: "u", selector: "000", compatibility: supplemental}
  tiling_mode: {code: "v", selector: "000", compatibility: supplemental}
  tiling_compensation: {code: "w", selector: "000", compatibility: supplemental}
  tiling_hv: {code: "x", selector: "000", compatibility: supplemental}
  tiling_position: {code: "y", selector: "000", compatibility: supplemental}

  date_year: {code: "2", selector: "Y00", compatibility: supplemental}
  date_month: {code: "2", selector: "M00", compatibility: supplemental}
  date_day: {code: "2", selector: "D00", compatibility: supplemental}
  time_hour: {code: "3", selector: "H00", compatibility: supplemental}
  time_minute: {code: "3", selector: "M00", compatibility: supplemental}
  time_second: {code: "3", selector: "S00", compatibility: supplemental}
```

---

# Documentation anomalies to preserve

Do not silently normalize these in code without a compatibility layer.

1. **CDE TCP port versus IFP TCP port**
   - CDE14: `5000`
   - IFP110: `7142`
   - Use `5000` for CDE4314-2C.

2. **Get request value field**
   - The supplemental prose says it is always `000`.
   - Date, time, and smart-hub examples use selectors.
   - Model the field as `selector`, defaulting to `000`.

3. **Backlight-level Set command**
   - Both tables print type `A`, code `B`.
   - This is structurally unusual.
   - Preserve literal support for `801ABnnn\r`; do not assume `sB`.

4. **Backlight-level Get command**
   - The Get table prints type `a`, code `B`.
   - The formal Get format requires type `g`.
   - Do not expose this command until tested; allow raw probes.

5. **Get Menu Lock**
   - Printed code `l`, which collides with Get Power.
   - Do not map a high-level `get_menu_lock()` to `l` automatically.

6. **Get Remote Control length**
   - The source prints length `S`, apparently a typo for `8`.

7. **Get Function On/Off**
   - The source prints type uppercase `G`, inconsistent with the formal `g` type.

8. **Backlight On/Off Set hex**
   - Command character `(` is ASCII `0x28`.
   - Source prints hex `29`, which belongs to `)`.

9. **Freeze Set character in the IFP table**
   - One rendering shows `.` while hex is `2A`.
   - The CDE table and ASCII hex identify the command as `*`.

10. **Extended reply length**
    - Called a 32-byte reply but begins with ASCII `2`.
    - Parse by CR and known structure, not by naive one-digit conversion.

11. **Input response mapping**
    - The supplemental source describes a signal flag plus an input code in only three bytes.
    - Record actual CDE replies before defining a complete enum.

---

# Recommended safe capability probe

Run only read-only commands during discovery.

Suggested sequence:

```text
801gz000\r    ACK/link test
801gl000\r    power
801gb000\r    brightness
801gf000\r    volume
801gg000\r    mute
801gj000\r    input
801g5000\r    MAC
801g6000\r    IP
801g7000\r    serial
801g8000\r    firmware
```

For each command record:

- raw TX ASCII and hex;
- raw RX ASCII and hex;
- response class;
- parsed value;
- positive, negative, timeout, or connection reset;
- firmware version;
- current input and power state.

Do not automatically probe:

- factory reset;
- lock commands;
- remote disable/pass-through;
- power-off;
- undocumented Set commands.

---

# Acceptance tests for the coding agent

## Packet construction

- `build_set("01", "!", "001")` returns exactly:

```python
b"801s!001\r"
```

- `build_get("01", "l")` returns exactly:

```python
b"801gl000\r"
```

- `build_get("01", "2", "Y00")` returns exactly:

```python
b"801g2Y00\r"
```

- reject non-ASCII command characters;
- reject values/selectors not exactly three bytes;
- reject malformed two-byte IDs.

## Parser tests

Parse these fixtures:

```python
b"401+\r"       # positive Set ACK
b"401-\r"       # negative reply
b"801rl001\r"   # power on
b"801rl000\r"   # standby
b"801rb067\r"   # brightness 67
b"605p10\r"     # pass-through Volume Up
```

Extended fixture:

```python
packet = (
    b"201r6"
    + b"192.168.100.2"
    + b"\x00" * (27 - len(b"192.168.100.2"))
    + b"\r"
)
assert len(packet) == 33
```

The extended parser should return command `6` and payload:

```python
b"192.168.100.2"
```

## TCP fragmentation tests

Feed the receive buffer:

```python
[b"801r", b"l001\r401", b"+\r"]
```

It must extract:

```python
b"801rl001\r"
b"401+\r"
```

Also test several complete packets in one chunk.

## Hardware smoke test

Against `192.0.2.15:5000`:

1. connect;
2. send `b"801gl000\r"`;
3. accept `b"801rl000\r"` or `b"801rl001\r"`;
4. log exact bytes;
5. close cleanly.

---

# Implementation recommendations

- Keep the core transport byte-oriented.
- Keep packet parsing separate from semantic decoding.
- Retain raw packets on every parsed event.
- Use enums only for confirmed values; preserve unknown values.
- Make model/firmware capability discovery data-driven.
- Store command metadata with source and compatibility status.
- Never infer support from syntax alone.
- Do not retry destructive Set commands automatically.
- Consider a configurable inter-command delay.
- Use explicit CLI quoting for punctuation command codes such as `"`, `'`, `(`, `)`, `>`, and `~`.
- Make logging show both escaped bytes and hex.

Example log:

```text
TX ascii=b'801gl000\r'
TX hex=38 30 31 67 6c 30 30 30 0d
RX ascii=b'801rl001\r'
RX hex=38 30 31 72 6c 30 30 31 0d
```

---

# References

- ViewSonic CDE14 Series User Guide, RS-232 Protocol section, pages 74-80. This is the model-specific source for the CDE4314-2C transport and Set table.
- ViewSonic Documentation, **IFP110 RS-232 Protocols**, revision dated 2024-10-15. This is the supplemental source for Get commands, extended replies, automatic replies, and remote pass-through.
- Hardware test on ViewSonic CDE4314-2C: Get-Power `801gl000\r` confirmed operational over TCP port `5000`.
