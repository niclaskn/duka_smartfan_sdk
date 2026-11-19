# Real fan probe results (2026-11-19)

Read-only probe (`tools/probe.py`) of one Duka smart fan: firmware 2.2 (16-6-2022), unit type 6.

## Protocol answers

1. **Reply port:** the fan replies to the sender's port, not only to 4000. `listen_port` may differ from 4000 (tests use 0); production keeps the default 4000.
2. **Password in replies:** empty (`password_len=0`). The reply password field proves nothing, so the 2.4 password check is **not** added.
3. **Size prefix:** every multi-byte field comes with `0xFE <size> <param>` (0x04, 0x06, 0x1F, 0x20, 0x21, 0x86, 0xB9).
4. **Markers:** `0xFD <param>` = parameter not supported (seen for 0x0B, 0x12). Now handled by the parser. `0xFC` / `0xFF` were not seen.

## Parameters

| Param | Name | Supported | Raw value | Decoded |
| --- | --- | --- | --- | --- |
| 0x01 | On / off | yes | `01` | on |
| 0x02 | Battery status | yes | `00` | 0 ("discharged"; likely mains-powered, so not useful as an entity) |
| 0x03 | 24-hour mode | yes | `00` | off |
| 0x04 | Fan speed (rpm) | yes | `fe 02 04 00 00` | 0 rpm while 0x01 = on (standby in auto mode) |
| 0x05 | Boost mode | yes | `00` | off |
| 0x06 | Boost countdown (s) | yes | `fe 03 06 00 00 00` | 0 |
| 0x07 | Timer running | yes | `00` | |
| 0x08 | Running by humidity | yes | `00` | |
| 0x0A | Running by temperature | yes | `00` | |
| 0x0B | Running by motion | **no** | `fd 0b` | |
| 0x0C | Running by external switch | yes | `00` | |
| 0x0D | Running by interval ventilation | yes | `00` | |
| 0x0E | Running in silent mode | yes | `00` | |
| 0x0F | Humidity trigger | yes | `01` | automatic |
| 0x11 | Temperature trigger | yes | `00` | off |
| 0x12 | Motion trigger | **no** | `fd 12` | |
| 0x13 | External switch trigger | yes | `01` | on |
| 0x14 | Humidity threshold (%) | yes | `40` | 64 |
| 0x16 | Temperature threshold (°C) | yes | `1b` | 27 |
| 0x17 | Unknown | yes | `0a` | 10 |
| 0x18 | Max speed (%) | yes | `4f` | 79 |
| 0x1A | Silent speed (%) | yes | `3c` | 60 |
| 0x1B | Interval speed (%) | yes | `1e` | 30 |
| 0x1D | Interval ventilation on | yes | `01` | on |
| 0x1E | Silent mode on | yes | `00` | off |
| 0x1F | Silent start (s) | yes | `fe 03 1f 00 00 00` | 0 = 00:00 |
| 0x20 | Silent end (s) | yes | `fe 03 20 60 54 00` | 21600 = 06:00 |
| 0x21 | Fan clock (s) | yes | `fe 03 21 d9 ce 00` | 52953 = 14:42:33 |
| 0x23 | Turn-off delay | yes | `03` | code 3 |
| 0x24 | Turn-on delay | yes | `00` | code 0 |
| 0x2E | Humidity (%) | yes | `32` | 50 |
| 0x31 | Temperature (°C) | yes | `18` | 24 |
| 0x86 | Firmware | yes | `fe 06 86 02 02 10 06 e6 07` | 2.2, 16-6-2022 |
| 0xB9 | Unit type | yes | `fe 02 b9 06 00` | 6 |

## Consequences

- `is_active` (rpm > 0) and `is_on` (0x01) disagree when the fan is on but idle in automatic mode. The HA fan entity should decide which one "on" means (Phase 5).
- Phase 8: skip the motion entities and the battery-low entity.
