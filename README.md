**English** | [简体中文](README.zh-CN.md)

# Vibe Lamp

> A physical ambient status light for AI coding — turns your Claude Code / Codex session state into a desk lamp.
> A glance tells you whether the AI is working, finished, or stuck waiting on you — no need to stare at the screen.

**Blue = working · Green = done · Red = needs you.** Inspired by [Vibe Island](https://vibeisland.app/) (the macOS notch / menu-bar panel) — it brings the same status to a lamp you can actually see on your desk. Think of it as the "physical lamp edition."

> **But it does NOT depend on, nor require, Vibe Island.** Vibe Lamp reads each agent's own hooks directly (Claude Code `~/.claude/settings.json`, Codex `~/.codex/hooks.json`) to get state — it is an independent "hook consumer," just like Vibe Island. The two can coexist (hooks run side by side), or you can install just one.

<p align="center">
  <img src="hardware/kicad/vibe_lamp_core_v1/renders/vibe_lamp_core_v1-iso.png" alt="Vibe Lamp Core V1 PCB 3D render" width="680">
</p>

Core V1 is a complete desk-lamp controller board: ESP32-C3, USB-C power/programming, a board-mounted WS2812B status LED, reset/provisioning button, and an expansion pad for an external LED ring or strip. The KiCad project includes PCB source, 3D renders, JLCPCB Gerber, BOM, and CPL outputs.

---

## What it solves

Staring at the terminal waiting for an AI agent to finish — or missing the moment it stalls waiting for your approval — is tiring. Vibe Lamp turns your current coding session's state into a beam of ambient light:

- **Ambient awareness**: state becomes ambient desk light. It doesn't grab your attention, but it's visible at a glance when you need it.
- **Never lies**: the lamp always reflects the real state. When the link drops it shows "lost" (amber slow breathing) instead of freezing on a stale color and misleading you.
- **Multi-agent**: supports Claude Code and Codex at the same time, and is architecturally extensible to more.

---

## Architecture at a glance

All the business logic lives on the Mac; the ESP32 is just a "dumb display." Three layers, each with one job:

```
┌──────────────────────────── Your Mac ────────────────────────────┐
│                                                                   │
│   Claude Code ──hooks──┐                                          │
│                        ├──→  Translator (resident background daemon)│
│   Codex ──────hooks────┘       · merges all session state          │
│                                · decides what the lamp should show  │
│                                · heartbeat + timeout fallback + retry│
│                                       │                           │
└───────────────────────────────────────│──────────────────────────┘
                                        │  WiFi / HTTP push + heartbeat
                                        ▼
                              ┌────────────────────┐
                              │  ESP32 (dumb display)│
                              │  · recv cmd → drive LED│
                              │  · watchdog → lost det.│
                              └─────────│──────────┘
                                        ▼
                          RGB LED / WS2812 ring (color + animation)
```

- **Capture layer**: each agent uses its own hook mechanism; on every state change it POSTs the event to the local translator with a one-line `curl` (with `--max-time 1 || true`, so even if the translator is down it never slows the agent itself).
- **Translate / aggregate layer**: a resident Mac daemon merges the state of all active sessions, computes "what to show," pushes it to the lamp over WiFi, and sends a periodic heartbeat.
- **Display layer**: the ESP32 runs a tiny HTTP server to receive commands and renders color and animation frame-by-frame locally; if it goes ~30 s without a message it enters the "lost" display.

> Adding a new agent only touches the translator — **not a single line of firmware changes**. Animations run locally on the firmware; only "discrete state changes + heartbeat" cross the network, so traffic is tiny.

---

## State → color reference

| State | Display | When |
|---|---|---|
| ⚫ Idle | Dim / off | Session ended / no activity |
| 🔵 Working | Blue **breathing**, color-coded by tool: coding = blue · command = purple · search = cyan | Prompt submitted / tool called |
| 💓 One step forward | A **pulse beat** on each tool call | Tool called |
| 🟢 Done | Green for 3–5 s → **fades** back to idle | Main turn finished |
| 🔴 Needs you | Red **slow blink** | Permission / approval request |
| ⚡ Error | Red **quick flash** → snaps back to the working color | Tool call errored |
| 🟠 Lost | Dim amber **slow breathing** (clearly distinct from all the above) | Watchdog: ~30 s with no message |
| 🚀 Boot | Runs a sweep animation on power-up | Power-up / session start |

**Iron rule**: "idle (dim)" and "lost (amber)" are strictly distinguished — a lamp frozen on blue is worse than no lamp at all.

With multiple sessions (e.g. Claude Code + Codex open together), a WS2812 ring is split into segments, each session occupying one segment showing its own state; a single RGB LED only shows the merged overall state.

---

## How it works (merge priority)

The translator merges all active sessions into "what the lamp should show." For a single LED / overall ambient mood, the priority is:

```
Any session "needs you"  → 🔴 red (highest priority)
else any "error"         → ⚡ red quick flash
else any "working"       → 🔵 blue breathing
else any "just done"     → 🟢 green (brief, fades to idle after a few seconds)
else all idle            → ⚫ dim
```

---

## Hardware

There are two supported hardware paths:

1. **Core V1 PCBA** — the finished board in this repository. This is the recommended project build: order the generated fabrication files, flash firmware, provision WiFi, and put it in a diffuser/enclosure.
2. **Breadboard prototype** — useful for firmware bring-up or quick experiments with an ESP32 dev board plus a single RGB LED or WS2812 ring.

<p align="center">
  <img src="hardware/kicad/vibe_lamp_core_v1/renders/vibe_lamp_core_v1-top.png" alt="Vibe Lamp Core V1 PCB top render" width="520">
</p>

| Part | Breadboard prototype | Core V1 PCBA |
|---|---|---|
| MCU | ESP32 dev board / ESP32-C3 board | ESP32-C3-MINI-1 module |
| Display | Single RGB LED or WS2812 ring | Board-mounted WS2812B LED, external WS2812 pad reserved |
| Assembly | Breadboard, jumper wires, resistors | Factory SMT PCBA; no user soldering for the main board |
| Production files | Not needed | KiCad source + `fab/` Gerber/BOM/CPL |
| Power | USB | USB |

Breadboard prototype parts:

| Part | Qty | Notes |
|---|---:|---|
| ESP32 dev board | 1 | Any `esp32dev`-compatible board is enough for the original RGB prototype |
| Common-cathode RGB LED | 1 | 4-pin LED: common cathode plus R/G/B pins |
| 220 ohm resistor | 3 | One current-limit resistor per R/G/B channel |
| Breadboard | 1 | For quick bring-up |
| Jumper wires | Several | Male-male or whatever matches your board |
| USB data cable | 1 | Power and flashing |

WS2812 ring prototype parts:

| Part | Qty | Notes |
|---|---:|---|
| ESP32 dev board | 1 | Same firmware stack, different display env |
| WS2812 / WS2812B ring | 1 | 16 LEDs is the default test target |
| 330 ohm resistor | 1 | In series with DIN |
| 1000 uF electrolytic capacitor | 1 | Across 5V and GND, mind polarity |
| Jumper wires + USB data cable | Several | Power, data, flashing |

For wiring diagrams, Core V1 production notes, flashing, WiFi setup, and a light-up self-test, see **[HARDWARE.md](HARDWARE.md)**.

---

## Quick start

Follow **[HARDWARE.md](HARDWARE.md)** end to end and the lamp will track real sessions tonight. Roughly:

1. Use Core V1 PCBA, or wire the breadboard RGB / WS2812 prototype.
2. Flash the firmware: `cd firmware && pio run -e c3_core_v1 -t upload` for Core V1, or `pio run -e esp32 -t upload` for the original ESP32 RGB prototype.
3. WiFi setup: connect your phone to the `VibeLamp-Setup-<id>` hotspot (each lamp's AP and mDNS name carry a 6-hex suffix from its MAC) → the captive portal pops up → enter your home WiFi password.
4. Manual light-up self-test (use the lamp's per-device name `vibelamp-<id>.local`, shown on the portal, or its IP): `curl -X POST http://vibelamp-<id>.local/state -d '{"sessions":[{"state":"working","tool":"code"}]}'`.
5. Hook into real sessions: `cd daemon && python install.py install`, then run a task in Claude Code / Codex and watch the lamp.

---

## Develop / test

**Daemon (Python, main path is stdlib-only; the optional BLE fallback needs `bleak`):**

```bash
# Run all tests (57) — must run from inside daemon/ (otherwise vibelamp isn't on the import path)
cd daemon && python -m pytest

# Start the daemon manually for local use
cd daemon && python -m vibelamp
```

**Firmware (PlatformIO / Arduino-ESP32 core 2.0.17):**

```bash
cd firmware

# Run the render-engine pure-logic unit tests (14, no board needed)
pio test -e native

# Build the Core V1 board firmware
pio run -e c3_core_v1

# Build the original single RGB LED prototype firmware
pio run -e esp32

# Build the ring version
pio run -e esp32_ring

# Flash + serial monitor
pio run -e esp32 -t upload && pio device monitor
```

> The `pio` above can use the repo's bundled virtualenv: `.venv/bin/pio`.

---

## Project status / roadmap

Current progress:

**Done**
- ✅ ESP32 firmware: networking + per-device mDNS (`vibelamp-<id>.local`), HTTP `/state` `/health`, watchdog lost-detection, four display-hardware abstractions, multi-session segmentation, the full set of state animations, boot animation. **All 14 native tests green; `esp32` / `esp32_ring` / `esp32_ble` all compile.**
- ✅ Python daemon: session merge, heartbeat, timeout fallback, push retry, auto-rediscovery (on push failure it re-scans the LAN by `lamp_id`/`lamp_mac`, so the lamp is re-found after an IP change or after you switch WiFi networks), launchd autostart; Claude Code + Codex hook integration (Codex included). **All 57 pytest green.**
- ✅ WiFi provisioning + multi-network connect: a self-managed multi-network credential table in NVS is the single source of truth; on boot the firmware scans nearby APs and connects to the strongest known network (mesh-aware: handles one SSID spread across multiple BSSIDs, relaxes min security for WPA-only APs, retries across rounds). WiFiManager only serves the captive-portal UI (`VibeLamp-Setup-<id>` hotspot, configure in browser, credentials survive power loss).
- ✅ User customization: the lamp's own settings page (brightness / color / animation, stored in NVS, at `http://vibelamp-<id>.local/`) + daemon config file `~/.vibelamp/config.json`.
- ✅ Core V1 hardware: KiCad board source, 3D renders, JLCPCB Gerber/BOM/CPL outputs, and routing/DRC status are included under `hardware/kicad/vibe_lamp_core_v1/`.

**To do (v1.1+)**
- ⏳ **Plan 04 — BLE**: fall back to BLE push when WiFi drops (dual-channel redundancy) + Espressif official-app BLE provisioning.
- ⏳ **On-device calibration**: refine the tool-name → color map, observe animation feel on the board, tune brightness / breathing speed; verify Codex hook fields on real hardware (Plan 03 Task 5).
- ⏳ OTA wireless firmware update, direct phone control, more agents (Gemini CLI / Cursor), a physical button, a finished enclosure.

---

## Directory structure

```
vibe-lamp/
├── README.md                  # English (GitHub homepage)
├── README.zh-CN.md            # Chinese
├── HARDWARE.md                # The hardware getting-started guide to follow tonight
├── hardware/                  # Core V1 specs, wiring diagram, KiCad source, fab outputs
├── firmware/                  # ESP32 firmware (PlatformIO)
│   ├── platformio.ini         #   envs: c3_core_v1 / esp32 / esp32_ring / esp32_ble / native
│   ├── include/config.h       #   pins, LED count, timeout, mDNS name, brightness cap
│   ├── src/                   #   render engine + display driver + networking + HTTP API
│   └── test/                  #   render-engine native unit tests
├── daemon/                    # Mac-side daemon (Python, stdlib only)
│   ├── install.py             #   idempotent hook install + launchd + Codex config
│   ├── vibelamp/              #   server, session merge, lamp push client, config
│   └── tests/                 #   pytest
└── scripts/                   # release packaging helpers
```

---

## Tech stack

- **Daemon**: Python (stdlib only, zero third-party deps), macOS launchd autostart.
- **Firmware**: PlatformIO + Arduino-ESP32 (core 2.0.17), FastLED, ArduinoJson, WiFiManager.
- **Addressing**: per-device mDNS `vibelamp-<id>.local` (a 6-hex MAC suffix avoids name clashes on shared networks). The daemon's primary way to find the lamp is a LAN scan (`/api/discover`), keyed on `lamp_id` + `lamp_mac` as the stable identity, so mDNS/IP can change and it re-binds automatically.

## License

Released under the [MIT License](LICENSE) — free to use, modify, and distribute.
