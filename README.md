**English** | [简体中文](README.zh-CN.md)

# Vibe Lamp

> A physical ambient status light for AI coding — turns your Claude Code / Codex session state into a desk lamp.
> A glance tells you whether the AI is working, finished, or stuck waiting on you — no need to stare at the screen.

**Blue = working · Green = done · Red = needs you.** Inspired by [Vibe Island](https://vibeisland.app/) (the macOS notch / menu-bar panel) — it brings the same status to a lamp you can actually see on your desk. Think of it as the "physical lamp edition."

> **But it does NOT depend on, nor require, Vibe Island.** Vibe Lamp reads each agent's own hooks directly (Claude Code `~/.claude/settings.json`, Codex `~/.codex/hooks.json`) to get state — it is an independent "hook consumer," just like Vibe Island. The two can coexist (hooks run side by side), or you can install just one.

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

## Hardware list

A single RGB LED is enough to validate the full color and animation model; add a WS2812 ring later for multi-session segmented display.

| Part | Prototype (minimal) | Finished build (optional upgrade) |
|---|---|---|
| MCU | The ESP32 dev board you already have | ESP32-C3 SuperMini / XIAO ESP32-C3 (smaller, cheaper, zero feature difference) |
| Display | A single **common-cathode RGB LED** (3 PWM channels) | WS2812 ring (16 LEDs) |
| Parts | Breadboard, jumper wires, 3 × ~220Ω current-limit resistors | ~330Ω resistor in series on the WS2812 data line, ~1000µF cap across power |
| Diffusion | None (bare LED is fine) | Milky acrylic diffuser / white PLA 3D-printed enclosure |
| Power | USB | USB |

> For detailed wiring, pinout, flashing, WiFi setup, and a light-up self-test, see **[HARDWARE.md](HARDWARE.md)**.

---

## Quick start

Follow **[HARDWARE.md](HARDWARE.md)** end to end and the lamp will track real sessions tonight. Roughly:

1. Wire it up (single RGB LED, or a WS2812 ring).
2. Flash the firmware: `cd firmware && pio run -e esp32 -t upload`.
3. WiFi setup: connect your phone to the `VibeLamp-Setup` hotspot → the captive portal pops up → enter your home WiFi password.
4. Manual light-up self-test: `curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"working","tool":"code"}]}'`.
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

# Build the on-board firmware (single RGB LED version)
pio run -e esp32

# Build the ring version
pio run -e esp32_ring

# Flash + serial monitor
pio run -e esp32 -t upload && pio device monitor
```

> The `pio` above can use the repo's bundled virtualenv: `.venv/bin/pio`.

---

## Project status / roadmap

The design doc + 5 implementation plans are complete and public. Current progress:

**Done**
- ✅ Design doc (three-layer architecture, state model, display-driver abstraction, disconnection handling, custom settings).
- ✅ ESP32 firmware: networking + mDNS (`vibelamp.local`), HTTP `/state` `/health`, watchdog lost-detection, four display-hardware abstractions, multi-session segmentation, the full set of state animations, boot animation. **All 14 native tests green; `esp32` / `esp32_ring` / `esp32_ble` all compile.**
- ✅ Python daemon: session merge, heartbeat, timeout fallback, push retry, launchd autostart; Claude Code + Codex hook integration (Codex included). **All 57 pytest green.**
- ✅ WiFiManager web provisioning (connect to the `VibeLamp-Setup` hotspot, configure in browser, credentials stored in NVS, survive power loss).
- ✅ User customization: the lamp's own settings page (brightness / color / animation, stored in NVS, at `http://vibelamp.local/`) + daemon config file `~/.vibelamp/config.json`.

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
├── firmware/                  # ESP32 firmware (PlatformIO)
│   ├── platformio.ini         #   envs: esp32 / esp32_ring / native
│   ├── include/config.h       #   pins, LED count, timeout, mDNS name, brightness cap
│   ├── src/                   #   render engine + display driver + networking + HTTP API
│   └── test/                  #   render-engine native unit tests
├── daemon/                    # Mac-side daemon (Python, stdlib only)
│   ├── install.py             #   idempotent hook install + launchd + Codex config
│   ├── vibelamp/              #   server, session merge, lamp push client, config
│   └── tests/                 #   pytest
└── superpowers/               # design doc & implementation plans
    ├── specs/                 #   overall design
    └── plans/                 #   5 implementation plans
```

---

## Tech stack

- **Daemon**: Python (stdlib only, zero third-party deps), macOS launchd autostart.
- **Firmware**: PlatformIO + Arduino-ESP32 (core 2.0.17), FastLED, ArduinoJson, WiFiManager.
- **Addressing**: mDNS `vibelamp.local` (resolved natively by macOS, no extra software needed).

Design doc: [superpowers/specs/2026-06-13-vibe-lamp-design.md](superpowers/specs/2026-06-13-vibe-lamp-design.md)
