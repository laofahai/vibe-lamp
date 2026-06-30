**English** | [简体中文](README.zh-CN.md)

# Vibe Lamp

Physical ambient status light for AI coding agents.

Vibe Lamp turns local coding-agent state into desk light: blue when the agent is working, green when it finishes, red when it needs you, and amber when the connection is lost.

<p align="center">
  <img src="hardware/kicad/vibe_lamp_core_v1/renders/vibe_lamp_core_v1-iso.png" alt="Vibe Lamp Core V1 PCB 3D render" width="680">
</p>

Core V1 is a complete ESP32-C3 controller board with USB-C power/programming, a board-mounted WS2812B status LED, a reset/provisioning button, and a reserved WS2812 expansion pad. The KiCad source, 3D renders, Gerber, BOM, and CPL files are included.

Inspired by [Vibe Island](https://vibeisland.app/), but independent from it. Vibe Lamp consumes agent hooks directly and can coexist with other hook consumers.

---

## Agent Support

| Level | Agents / tools | How it works |
|---|---|---|
| Built in | Claude Code, Codex | `daemon/install.py` installs local hooks and launchd autostart on macOS. |
| Generic API | OpenCode, Qwen Code, Gemini CLI, Aider, Cursor, Windsurf, CodeBuddy / WorkBuddy, Trae, MarsCode / Doubao, Factory / Droid-style tools | Any tool that can run a hook, plugin, wrapper, or notification command can POST normalized events to `/event/generic`. |
| Future adapters | Tool-specific integrations | Add adapter logic in the Mac daemon only; the ESP32 firmware stays agent-agnostic. |

Generic event example:

```bash
curl -s -o /dev/null --max-time 1 \
  -X POST http://127.0.0.1:8787/event/generic \
  -H 'Content-Type: application/json' \
  -d '{"agent":"opencode","session_id":"default","state":"working","tool":"code"}' || true
```

Supported normalized states are `idle`, `working`, `done`, `error`, and `needs_you`. See [daemon/AGENTS.md](daemon/AGENTS.md) for adapter notes.

---

## Architecture

All decision-making lives on the Mac. The ESP32 is a display endpoint.

```
Claude Code / Codex / generic agent
        │
        ▼
Mac daemon
  - normalizes hook events
  - merges multiple sessions
  - pushes state + heartbeat
        │ WiFi / HTTP
        ▼
ESP32 firmware
  - renders LED color/animation
  - enters lost state when heartbeat stops
```

Merge priority for a single LED:

```text
needs_you > error > working > done > idle
```

The lamp never freezes on stale state: if the daemon or network disappears, firmware switches to amber lost mode after the watchdog timeout.

---

## Hardware

Two hardware paths are supported:

| Path | Use it for | Notes |
|---|---|---|
| Core V1 PCBA | Finished build | Recommended. Factory-assembled ESP32-C3 board with board-mounted WS2812B. |
| Breadboard prototype | Bring-up and experiments | ESP32 dev board plus RGB LED or WS2812 ring. |

<p align="center">
  <img src="hardware/kicad/vibe_lamp_core_v1/renders/vibe_lamp_core_v1-top.png" alt="Vibe Lamp Core V1 PCB top render" width="520">
</p>

Core V1 production files live in [hardware/kicad/vibe_lamp_core_v1](hardware/kicad/vibe_lamp_core_v1):

- KiCad PCB source
- PCB renders
- JLCPCB Gerber zip
- JLCPCB BOM and CPL

<details>
<summary>Breadboard prototype parts</summary>

RGB LED prototype:

| Part | Qty | Notes |
|---|---:|---|
| ESP32 dev board | 1 | Any `esp32dev`-compatible board |
| Common-cathode RGB LED | 1 | 4-pin LED |
| 220 ohm resistor | 3 | One per R/G/B channel |
| Breadboard | 1 | Bring-up |
| Jumper wires | Several | Board-dependent |
| USB data cable | 1 | Power and flashing |

WS2812 ring prototype:

| Part | Qty | Notes |
|---|---:|---|
| ESP32 dev board | 1 | Same firmware stack |
| WS2812 / WS2812B ring | 1 | 16 LEDs by default |
| 330 ohm resistor | 1 | In series with DIN |
| 1000 uF electrolytic capacitor | 1 | Across 5V and GND |
| Jumper wires + USB data cable | Several | Power, data, flashing |

</details>

Detailed wiring, flashing, WiFi provisioning, and self-test steps are in [HARDWARE.md](HARDWARE.md).

---

## Quick Start

```bash
# Core V1 firmware
cd firmware
pio run -e c3_core_v1 -t upload

# Mac daemon + Claude Code / Codex hooks
cd ../daemon
python install.py install
```

After WiFi provisioning, test the lamp directly:

```bash
curl --noproxy '*' -X POST http://vibelamp-<id>.local/state \
  -H 'Content-Type: application/json' \
  -d '{"sessions":[{"state":"working","tool":"code"}]}'
```

---

## Development

```bash
# Daemon tests
cd daemon
python -m pytest

# Firmware logic tests
cd ../firmware
pio test -e native

# Firmware builds
pio run -e c3_core_v1
pio run -e esp32
pio run -e esp32_ring
```

The `pio` command can use the repo virtualenv: `.venv/bin/pio`.

---

## Status

Done:

- ESP32 firmware: WiFi provisioning, HTTP state API, mDNS, watchdog lost mode, RGB/WS2812 display drivers, animations, multi-session rendering.
- macOS daemon: Claude Code and Codex hooks, generic event API, session merge, heartbeat, retry, rediscovery, launchd autostart.
- Core V1 hardware: KiCad board source, renders, JLCPCB Gerber/BOM/CPL.

Planned:

- Dedicated adapters for more coding agents.
- OTA firmware update.
- Phone control page.
- Enclosure and diffuser polish.
- BLE fallback when WiFi is unavailable.

---

## Repository Layout

```text
vibe-lamp/
├── hardware/    # Core V1 docs, KiCad source, renders, fab outputs
├── firmware/    # ESP32 firmware, PlatformIO environments, native tests
├── daemon/      # macOS daemon, hook installer, normalization logic, pytest
└── scripts/     # release packaging helpers
```

---

## License

MIT. See [LICENSE](LICENSE).
