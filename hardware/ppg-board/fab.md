# Fab Settings — PallorHb PPG head (rev A), JLCPCB

## Order parameters

| Setting | Value | Note |
|---|---|---|
| Layers | **6** | Changed 2 → 4 → 6; see below |
| Stackup | JLC06161H-1080 or similar (1.6 mm, 1 oz outer / 0.5 oz inner) | JLCPCB standard 6-layer |
| Dimensions | **L-shaped, 100 × 40 mm envelope** (main 50 × 40, head 46 × 30) | Inside the 100 × 100 mm promo tier — area is free |
| Quantity | 5 | |
| Thickness | 1.6 mm | |
| Copper | 1 oz outer | |
| Surface finish | **ENIG** | Not HASL — see below |
| Soldermask | **Black** | Optical opacity at the sensor; also stops FR4 edge-piping |
| Silkscreen | White | |
| Impedance control | No | No net above ~10 MHz except CLKIN (8.192 MHz, short) |
| Castellated holes | No | |
| Assembly | **No — hand assembly** | See sourcing rationale |

## Why 6 layers (changed from 2)

`constraints.md` allowed 4 layers "if justified". Two things justified going to 4, one measured
and one by design intent; routing evidence then forced 6 (see below).

**Measured.** On 2 layers the autorouter plateaued at 140 unrouted connections over 41 passes and
then crashed. With no ground plane, all 110 GND/AGND pads — 28% of every pad on the board — have to
be routed as individual traces. On 4 layers with planes poured, the same router reached 78 unrouted
within 65 passes and was still improving.

**By design.** This is a sub-microvolt analog front end. A solid, unbroken ground plane directly
beneath the TIA inputs and the ADC is worth more on this board than on almost anything else you
would build — it is the single biggest signal-integrity lever after the optical geometry itself.
The 2-layer pour was a compromise made too early.

### Plane assignment (6-layer) — as built

| Layer | Main board (x 0–52) | Optical head (x 52.5–100) | Signal segments |
|---|---|---|---|
| F.Cu | signal | signal | 944 |
| **In1.Cu** | **GND plane** | **AGND plane** | **0 — solid** |
| In2.Cu | signal | signal | 126 |
| In3.Cu | signal | signal | 168 |
| **In4.Cu** | **3V3_D plane** | **3V3_A plane** | **0 — solid** |
| B.Cu | signal | signal | 129 |

Plus 241 through-hole vias. Both planes are unbroken: **0 signal segments on either.**

### Why 6 layers, and how the planes were kept solid

4 layers routed cleanly only when both inner layers were left available to the router — which put
**1494 mm of signal through the two planes**, shredding the ground reference. Reserving the planes
cost 76–105 unrouted connections.

Diagnosis: **Freerouting mishandles DSN `type power` layers.** 6-layer with 2 reserved gave 96
unrouted despite having the same 4 signal layers as the 4-layer all-signal case that reached 1.
The layer count was never the constraint.

Approach used, in two steps:

1. Route with **all six layers declared signal**, then relocate the whole set of tracks that landed
   on In1.Cu onto the then-empty B.Cu. This is safe because a set of tracks sharing one layer is
   already a non-colliding routing, so moving it entire to an empty layer introduces no new
   collisions, and through-hole vias still meet the relocated tracks. In1.Cu: 111 → 0.
2. Rip up everything remaining on In4.Cu (57 segments) plus 5 tracks that skirted the optical
   barrier slots, and re-route those 13 nets with a **6-layer A\* maze router restricted to the four
   signal layers** (`tools/maze_router.py`, 0.25 mm grid, vias only where a through-hole clears every
   layer, Edge.Cuts and slots rasterised as hard obstacles). In4.Cu: 57 → 0.

Result: **0 unconnected, 0 DRC violations, 0 schematic-parity errors, both planes solid.**

The extra layers earned their keep by providing an empty destination layer in step 1. On 4 layers
there was nowhere to put the displaced tracks.

The ground planes are **partitioned by placement, not split within a domain** — GND under the
digital/power section, AGND under the analog section, joined at a single point by R520 (0 Ω). This
is exactly the strategy `constraints.md` specifies, now on a dedicated layer instead of a 2-layer
pour.

Cost: JLCPCB 6-layer, 100 × 40 mm, 5 pieces ≈ £45–60 shipped, versus ~£28 at 4-layer.

## Deviations from the house default, with justification

**ENIG instead of lead-free HASL.** HASL leaves a domed, uneven pad. The board has two SOT-23-5
op-amps whose inverting inputs carry sub-nA photocurrents, a TSSOP-20 ADC at 0.65 mm pitch, and
0402 feedback capacitors of 4.7–10 pF where a few tenths of a pF of pad-geometry variation shifts
the TIA compensation measurably. ENIG is flat and coplanar. Cost delta at 5 pieces is a few pounds
and it materially improves hand-soldering yield on the fine-pitch parts.

**Black soldermask.** The optical barrier between emitter and detectors is the board's main
signal-integrity feature. Green mask transmits usefully at 850–940 nm; black does not. This works
with the routed slot and via fence rather than replacing them.

**Routed break line rather than a panel.** Three 2.2 mm mouse-bite tabs on a 1.6 mm routed line.
JLCPCB charges this as one board outline, so the two-board split costs nothing.

## Slot specification (the optical barrier)

- Two interrupted annular slots, **1.6 mm wide**, drawn on `Edge.Cuts`, between the emitter site
  and each photodiode.
- Interrupted, not continuous — a full annulus would island the copper pour and sever the
  photodiode guard-ring return. Leave two 3 mm bridges per slot, positioned away from the direct
  emitter→detector line of sight.
- JLCPCB minimum internal slot width is 1.0 mm; 1.6 mm is comfortably inside spec and costs
  nothing extra as a routed feature.
- Flank each slot with a via fence: **0.3 mm vias at 1.0 mm pitch**, tied to AGND, on both sides.

## Design rules (set these in KiCad before routing)

Use the house rule file `JLCPCB.kicad_dru` (symlinked in this directory), plus:

| Rule | Value |
|---|---|
| Min trace / space (signal) | 0.15 mm / 0.15 mm |
| Min trace (VLED pulse path) | **0.5 mm** — carries 40 mA peak |
| Min trace (power rails) | 0.4 mm |
| Via | 0.3 mm drill / 0.6 mm pad |
| Annular ring | ≥ 0.13 mm |
| Board edge to copper | 0.3 mm |
| Slot edge to copper | 0.4 mm |
| ESP32 antenna keep-out | **no copper on any layer** in a 15 × 8 mm region under and beyond the module antenna; module placed at the board edge with the antenna overhanging |

## House-rule deviation: Extended parts — NEEDS APPROVAL

`BOARD_RULES.md` for this board says *"Prefer JLC Basic parts; escalate to Preferred only when required.
Never Extended without approval."*

**This BOM is almost entirely Extended parts, and there is no way to avoid it.** The JLC Basic and
Preferred libraries contain no PPG analog front-end parts at all. Of the whole BOM only three lines
are Basic or Preferred: XC6206 (LDO, not used — TLV75533 chosen for PSR), TP4056-42 (Preferred),
AO3400A (Basic), and MCP6002 (Preferred). Every ADC, every precision op-amp, every photodiode and
every emitter is Extended. See [`sourcing.md`](sourcing.md) for the evidence.

The per-part loading fee only applies to **JLCPCB assembly**, which this board does not use — it is
hand-assembled, so "Extended" here costs nothing beyond the part price. The rule's purpose
(avoiding assembly surcharges) is therefore not violated in substance.

**Action: confirm this is acceptable before ordering.** If the intent of the rule is broader than
assembly cost, the alternative is a MAX30101 carrier board, which sacrifices the entire
spatially-resolved measurement that justifies the project.

## Assembly

**Hand assembly, not JLC PCBA.** Nothing in the analog chain is a JLC *Basic* part, so PCBA would
levy the per-part loading fee across most of the BOM and still leave the optical parts to be
placed by hand for alignment. Every package on this board was selected to be hand-solderable:
SOT-23, SOT-23-5/6, SOIC-8, TSSOP-16/20 (0.65 mm), 0603/0402 passives, and the module.

Order of assembly: passives → ICs → connectors → **optical parts last** (their alignment matters
and they should not see repeated reflow).

Consumables to budget: solder paste, a stencil is *not* required for hand assembly at this pitch
but helps; flux; 0.3 mm solder wire; isopropanol.

## Cost

| Line | GBP |
|---|---|
| PCB, 5 pcs, **6-layer**, ENIG, black mask, incl. shipping | ~45-60 |
| BOM, 1 board built (see `design.md` §3) | ~24 |
| Spares / second build set | ~15 |
| **Total to first working board** | **~85-100** |

This sits at the top of the £100 budget. A rev B respin would exceed it, so the pre-order checks in
`STATUS.md` matter more than they would on a cheap 2-layer board.
