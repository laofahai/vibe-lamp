# Vibe Lamp Edge V1 PCB Draft

This is a first KiCad PCB draft for the magnetic MacBook A-cover lamp form factor.
It is a mechanical/electrical placement sketch, not a fabrication-ready routed PCB.

## Mechanical Direction

- PCB outline: 38 mm x 16 mm rectangle.
- PCB stackup: FR4, 2 layers, 1 oz copper, 1.6 mm thickness.
- Minimum rule target: 6 mil track/clearance, 0.3 mm drill.
- USB-C sits on the bottom edge.
- Four edge-facing RGB/NeoPixel LED positions sit near the top edge.
- Back-side center area is reserved for a thin magnet or magnetic sheet in the enclosure.
- ESP32-C3 antenna end is placed near the top edge with a keepout note.

## Manufacturing Notes

- Solder mask: choose black or white for a product look; green is fine for engineering samples.
- Silkscreen: white.
- Surface finish: HASL is acceptable, ENIG is nicer for small pads and appearance.
- This file is a layout/concept draft. Replace placeholder footprints with exact supplier parts before ordering.
- Do not export Gerbers from this draft for fabrication yet. Nets and footprints are placeholders and routing is intentionally not complete.

## Open Items Before Fabrication

- Select exact USB-C receptacle footprint.
- Select exact LED package: 2020/2427 side-view addressable RGB, or discrete RGB LEDs.
- Decide whether V1 uses one RGB LED from the existing firmware or a WS2812 chain.
- Run KiCad DRC after footprints and schematic nets are finalized.
- Verify enclosure wall thickness, diffuser geometry, and magnet placement.
