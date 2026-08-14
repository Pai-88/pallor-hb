# PallorHb rev A — build status

Updated 2026-08-10. Release in `release_20260810/` (6-layer gerbers + drill + BOM + CPL + STEP).

**Routing and DRC are finished.** The remaining gate is the physical/sourcing checklist at the
bottom — nothing there is a layout change.

## Current state — routing complete, DRC clean

| Check | Result |
|---|---|
| **DRC errors** | **0** |
| **Unconnected** | **0** |
| Schematic parity | **0** |
| Pad shorts | **0** |
| Clearance violations | **0** |
| Copper-to-edge violations | **0** |
| Keep-out violations | **0** |
| Dangling vias / tracks | **0** |
| Tracks crossing a barrier slot | **0** (independently verified) |
| Track segments / vias | 1367 / 241 |
| Filled planes | 4 (GND, AGND, 3V3_D, 3V3_A) — **both plane layers solid** |
| Silk over copper / overlap / edge | 148 (cosmetic, see deviations) |
| `lib_footprint_mismatch` | 1 (U201, documented) |

Unconnected went **314 → 0**. The board is electrically complete.

### How the last connections were closed

The final 3 unconnected plus 5 copper-to-edge violations were resolved by ripping up every track
still sitting on a reserved plane layer (57 on In4.Cu) plus the 5 that skirted the barrier slots,
then re-routing those 13 nets with a purpose-built **6-layer A\* maze router** restricted to the four
signal layers (`tools/maze_router.py`). Vias are placed only where a through-hole clears every
layer; Edge.Cuts and the barrier slots are rasterised as hard obstacles.

Side effect worth having: **In4.Cu went 57 → 0 segments**, so the 3V3 plane is now solid too. The
earlier note about a split 3V3_A plane no longer applies.

Three router bugs were found and fixed while doing this, all of which had put copper too close to
something: a scan box sized on the track radius while testing against the larger via radius; pads
modelled as circles of `max(w,h)/2`, which understates a rectangular pad's corner on a diagonal
approach; and `o is t` identity tests that never match because pcbnew mints a fresh SWIG proxy on
every `GetTracks()` call.

## Board summary

- **L-shaped outline**, 100 × 40 mm envelope: main board 50 × 40, optical head 46 × 30, break line
  at x ≈ 52. One fabricated outline, inside JLCPCB's free 100 × 100 tier.
- **6 layers.** F.Cu signal / **In1.Cu ground plane** / In2.Cu signal / In3.Cu signal /
  **In4.Cu 3V3 plane** / B.Cu signal. Both plane layers carry zero signal copper.
  Grounds partitioned by placement: GND under the digital-power section, AGND under the analog
  section, joined at a single point through R520 (0 Ω). Same for 3V3_D / 3V3_A on In4.Cu.
  See `fab.md` for why 6 and how the planes were kept solid.
- **117 components**, 77 nets, 431 pads.

### Optical geometry (the instrument — do not disturb)

| Ref | Position | Rot |
|---|---|---|
| D401 (PD near) | (69.00, 15.00) | 0 |
| D501 (660/850) | (75.18, 15.00) | **0** |
| D402 (PD far) | (86.51, 15.00) | 0 |
| D502 (810) | (75.80, 11.00) | 0 |

For **D501 (660/850)**: ρ₁ = **6.180 mm**, ρ₂ = **11.330 mm**, with D401/D501/D402 collinear to
**0.0000 mm** in y. Verified from the board file, not from this document. D502 is a separate case —
see below.

### ⚠️ D502 (810 nm) sits OFF the detector axis — the firmware needs two ρ pairs

D502 is at (75.80, 11.00), i.e. **4 mm off** the D401–D501–D402 line. Measured from the board file:

| Emitter | to D401 (near) | to D402 (far) | Δρ |
|---|---|---|---|
| D501 (660 / 850 nm) | 6.180 mm | 11.330 mm | **5.150 mm** |
| **D502 (810 nm)** | **7.889 mm** | **11.433 mm** | **3.544 mm** |

This is geometry, not a defect — but 810 nm is the wavelength the whole μ_eff → total-haemoglobin
fit runs on. `ln[DC(ρ₂)/DC(ρ₁)] ≈ −μ_eff·Δρ + 2·ln(ρ₁/ρ₂)` uses **both** ρ values, so applying the
660/850 pair to the 810 channel biases μ_eff by roughly Δρ ratio 5.150/3.544 = **1.45×** — a 45 %
systematic error on the primary measurand, with nothing in the data to reveal it.

**Action before any capture:** put per-wavelength ρ constants in the firmware/analysis, not one
shared pair. Re-measure all four with callipers on the assembled board and use the measured values
(this is also where the unresolved VEMD5010X01 optical-centre offset lands).

**D501 rotation is load-bearing.** The datasheet puts the 850 die in the upper half of the package
and 660 in the lower, so unrotated the dies are offset along y — perpendicular to the optical axis,
which keeps both wavelengths equidistant from both detectors. Rotating it 90° would split the two
ρ values by ~24% with no DRC error and nothing visible in the layout. Add a silkscreen axis tick at
y = 15 before release so a re-annotation cannot silently flip it.

### Barrier slots

| Slot | x | y | Width | Clearance |
|---|---|---|---|---|
| near (D501↔D401) | 71.69 – 72.89 | 9 – 21 | 1.2 mm | 0.640 mm each side |
| far (D501↔D402) | 79.80 – 81.20 | 9 – 21 | 1.4 mm | 2.97 / 3.26 mm |

Both stop ≥ 9 mm short of the board edges so the ground pour wraps around each end. **Zero tracks
or vias cross either slot** — verified by sampling every track segment against both rectangles. A
trace crossing a routed slot is severed at fabrication and would not show as a DRC error.

### Placement

Aligned to a 0.25 mm grid with near-collinear parts snapped to shared axes; head and main board
aligned independently. The optical cluster was frozen out of this pass. The sink block:

| | 76.0 | 80.0 | 84.5 | 89.25 | 93.0 | 97.5 |
|---|---|---|---|---|---|---|
| **y 24.5** | Q501 | U404 | Q502 | U405 | Q503 | U406 |
| **y 27.0** | R507 | R501 | R508 | R502 | R509 | R503 |
| **y 28.9** | R504 | C501 | R505 | C502 | R506 | C503 |

Alignment also improved routability — same router and settings gave 2 unrouted on the ad-hoc
placement and 1 on the aligned one.

## Accepted deviations

- **148 silkscreen violations** — reference designators over pads. Silk over pad is masked off at
  fab. Value fields hidden, refs 0.8 mm (JLC minimum).
- **`lib_footprint_mismatch` on U201** — uses `RF_Module:ESP32-S2-MINI-1` for the S3-MINI-1
  (same Espressif MINI-1 mechanical, 65 pads). Verify against the drawing.
- **Extended parts** — see `fab.md`; hand assembly, so the per-part fee never applies.
- **Power tracks are 0.20–0.25 mm, not the 0.4 mm (rails) / 0.5 mm (VLED) that `fab.md` specifies.**
  Freerouting laid everything at 0.20 mm and the rule was never enforced. Checked rather than
  assumed: VLED carries 40 mA peak, so 0.20 mm 1 oz over ~30 mm is ≈0.07 Ω → **~3 mV** drop, and LED
  current is set by the current sinks, whose compliance absorbs it. VBAT's worst case is the 500 mA
  TP4056 charge current → ~36 mV, ~18 mW, against roughly 1 A ampacity for 0.20 mm 1 oz. Electrically
  fine, comfortably inside JLC's 6-layer 0.09 mm minimum. Accepted for rev A; widen on rev B.

## Defects caught that would have scrapped a board

1. **Emitter footprints were the guessed `_PROVISIONAL` ones.** `sync_schematic_to_board` updates
   nets but does **not** replace footprints on existing components, so the PCB kept invented pad
   geometry — including the wrong die mapping (pads 1/2 as 660 nm when the datasheet says 850).
   Both replaced with datasheet-verified footprints and pad-by-pad net reassignment.
2. **U102, R104, C103 sat inside U201's 45 × 19.5 mm antenna keep-out**, where copper and tracks are
   forbidden. Would have detuned the 2.4 GHz antenna invisibly. Moving them also freed a routing
   channel — unrouted dropped 17 → 5 immediately.
3. **RT401 had a pad directly over the far barrier slot** (0.000 mm clearance — a routed hole
   through the pad).
4. **Wavelength swap in the schematic.** The CT3030 datasheet orders pads 850-first; the original
   symbol had 660 on pads 1/2, which would have driven each die from the wrong current sink and
   labelled every sample with the wrong wavelength.

## Still open before ordering

- [ ] **VEMD5010X01 optical-centre offset** — the pad geometry is datasheet-verified but the optical
      centre is offset from the package centre and I could not read the offset. It shifts ρ
      one-for-one. Confirm, then re-measure as-built with callipers (`bringup.md` §1).
- [ ] **D502 peak wavelength** — datasheet says 810 nm; confirm on arrival.
- [ ] Six `[VERIFY]` BOM lines in `design.md` §3.
- [ ] Extended-parts sign-off (`fab.md`).
- [ ] Filament NIR-opacity coupon test (`bringup.md` §0.1) before printing the clip.
- [ ] Silkscreen axis tick at y = 15 to lock D501's rotation.
