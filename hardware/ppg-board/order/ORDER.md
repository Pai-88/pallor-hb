# PallorHb rev A — order sheet

**Status: parts AND the PCB are orderable. Layout is finished; DRC is clean (0 errors, 0 unconnected,
0 schematic-parity). Gerbers are in [`../release_20260810/`](../release_20260810/).**

Quantities are sized for **2 builds plus spares**, because a first mixed-signal board with hand
assembly reliably eats at least one set of parts.

Stock and prices checked live on 2026-08-10. Re-check before paying — several lines moved during
design.

---

## 1. Order today — LCSC

Import [`parts_lcsc.csv`](parts_lcsc.csv) into the LCSC cart, or paste the part numbers manually.

### Priority A — scarce, order first, do not batch with anything slow

| LCSC | Part | Qty | Why urgent |
|---|---|---|---|
| **C22447934** | JNJ-L-3535AW30-80530-SL-J2-D3, ~810 nm | **10** | 307 in stock, no abundant substitute anywhere. The isosbestic channel dies without it |
| **C2922448** | ADS131M02IPWR, 24-bit 2-ch simultaneous | **3** | 7 481 in stock but this part class was already dry once (MCP3564R has 22) |

⚠️ **When D502 arrives, read the datasheet and record its actual peak wavelength.** The whole
spatially-resolved argument needs 805–815 nm. If it is 830–840 nm, the extinction balance drifts —
say so in the writeup rather than fudging it.

### Priority B — semiconductors and optics

| LCSC | Part | Pkg | Qty | £ ea | £ |
|---|---|---|---|---|---|
| C2913206 | ESP32-S3-MINI-1-N8 | module | 3 | 3.70 | 11.10 |
| C30878 | OPA333AIDBVR (TIA) | SOT-23-5 | 6 | 0.33 | 1.98 |
| C7377 | MCP6002T-I/SN (sinks + bias buffer) | SOIC-8 | 6 | 0.19 | 1.14 |
| C3151612 | VEMD5010X01 photodiode | SMD-4P | 6 | 0.52 | 3.12 |
| C53191416 | CT-3030SUR660/850C-PT dual-die | SMD3030-4P | 5 | 0.11 | 0.55 |
| C16581 | TP4056-42 charger | ESOP-8 | 3 | 0.15 | 0.45 |
| C404027 | TLV75533PDBVR LDO | SOT-23-5 | 6 | 0.15 | 0.90 |
| C2687116 | USBLC6-2SC6 ESD | SOT-23-6 | 3 | 0.03 | 0.09 |
| C15127 | AO3401A P-ch **(Basic)** | SOT-23 | 10 | 0.04 | 0.40 |
| C20917 | AO3400A N-ch **(Basic)** | SOT-23 | 10 | 0.05 | 0.50 |
| C8545 | 2N7002 **(Basic)** | SOT-23 | 15 | 0.01 | 0.15 |
| C8678 | SS34 Schottky **(Basic)** | SMA | 5 | 0.02 | 0.10 |
| C2765186 | USB-C 16-pin receptacle | SMD | 5 | 0.06 | 0.30 |
| C49247666 | NTC 10 kΩ B3950 | 0603 | 5 | 0.04 | 0.20 |

### Priority C — passives

Buy in strips of 50–100; the per-part cost is noise and running out mid-build is not.

**Resistors, 0603 1%** — 10 Ω (×3/bd), 220 Ω (×3), 1 kΩ (×8), 2.4 kΩ, 3.3 kΩ (×4), 4.7 kΩ,
5.1 kΩ (×2), 10 kΩ (×5), 100 kΩ (×6), 200 kΩ, **470 kΩ**, **1.0 MΩ**.
The 470 kΩ, 1.0 MΩ and the four 3.3 kΩ **must be 1%** — the 3.3 kΩ set impedance-matches the ADC
driver arms, and a mismatch there collapses cable CMRR from ~40 dB to ~0.5 dB.

**Capacitors** — 100 nF 0402 (×10/bd), 1 µF 0603 (×5), 10 µF 0805 (×5), 22 µF 0805, 100 µF 1206,
1 nF C0G 0402 (×4), 10 nF C0G 0402 (×2), **10 pF C0G 0402**, **4.7 pF C0G 0402**.
The 10 pF and 4.7 pF are the TIA compensation caps — **C0G/NP0 only**. X7R's voltage and
temperature coefficients would shift the compensation and change the settling time the whole
4-phase timing budget depends on.

Plus: tactile switch, green 0603 LED, JST-PH 2-pin.

---

## 2. Order separately — not on LCSC

| Item | Qty | Where | Note |
|---|---|---|---|
| **JST-GH 15-way** connectors + 100 mm silicone jumper | 2 conn + 1 cable | RS / Mouser / Digi-Key UK, or an AliExpress "GH1.25 15P" assembly | Not stocked at LCSC. Buying the pre-made cable assembly is far easier than crimping 15 GH contacts |
| **1S LiPo 500 mAh, PROTECTED cell** | 2 | UK hobby supplier | ⚠️ The TP4056 has **no** protection FETs. An unprotected cell can be over-discharged and shorted |
| Black PETG filament | — | any | ⚠️ Run the NIR-opacity coupon test (`bringup.md` §0.1) **before** printing the clip. Much black PLA is transparent at 850–940 nm |
| White PTFE or white PETG plug | 1 | offcut / print | Reference target for session drift correction |

---

## 3. Cost

| | £ |
|---|---|
| LCSC priority A + B | ~29 |
| LCSC passives | ~8 |
| Connectors + cable | ~5 |
| 2 × protected LiPo | ~10 |
| **Parts subtotal** | **~52** |
| PCB (5 pcs, **6-layer**, ENIG, black mask) | ~13-22 |
| PCB shipping to UK | ~7-13 |
| LCSC shipping to UK | ~8-12 |
| **UK import VAT @ 20%** (charged at checkout on both orders) | ~16-18 |
| **Total** | **~96-117** |

### Why the PCB got cheaper than the earlier £45-90 estimate

Checked against JLCPCB's own pages rather than assumed:

- **ENIG is free of charge** on 6-layer — it is not the surcharge I had assumed.
- **Black soldermask is a standard colour** (green/purple/red/yellow/blue/white/black), no extra.
- **No slot-routing fee.** JLC charges when routed path reaches 120 m/m² for slots >1.0 mm. This
  board is 0.004 m² → a 480 mm allowance; the L-outline + two barrier slots + break line come to
  roughly 385 mm. Under, but only by ~20 % — if you add slots on rev B, recheck this.
- **No drill fee.** 251 drill hits against a 600 allowance (150 000/m²).
- **No large-board fee.** 40 cm², far below the 650 cm² threshold.

Anchors: 6-layer 5 pcs is $2 at 50 x 50 mm and $35.10 at 100 x 100 mm. This board is 100 x 40 mm,
so expect roughly $17-28 before shipping. There is also a **$33 6-layer coupon** (60-day validity)
which could take the boards to near zero — check the events page before paying.

## 3b. End-to-end cost — everything to a working prototype

The £100 figure is the *order*. Getting from gerbers to a bring-up-signed-off board costs more,
and the variable is tooling, not parts.

### Must buy regardless

| | £ |
|---|---|
| PCB + parts order (section 3) | 96-117 |
| SMD stencil, framework-less — **order with the PCB so it ships free** | ~7 |
| Solder paste, 35 g syringe | 12 |
| No-clean flux pen | 8 |
| 0.3 mm solder wire | 10 |
| Isopropanol + desolder braid | 9 |
| Fine ESD tweezers | 10 |
| Black PETG, 1 kg (clip + the §0.1 opacity coupons) | 20 |
| **Subtotal** | **~172-193** |

A stencil is listed as optional in `fab.md`, but this board has a 0.65 mm TSSOP-20 and 0402 caps
whose value sets the TIA compensation. At £7 shipped alongside the boards it is the cheapest yield
insurance in the whole project — treat it as mandatory.

### Tools — the real variable

| | £ | Note |
|---|---|---|
| Hot air rework station | 40-80 | **Not optional.** The TP4056 is ESOP-8 and the ADS131M02 is a PW package; both have exposed thermal pads that an iron cannot reach. |
| Temperature-controlled iron | 0-60 | |
| USB microscope / loupe | 0-35 | For inspecting 0.65 mm pitch. |
| Digital callipers | 0-15 | **Required** — §1 makes you re-measure ρ as-built, and that number feeds the model. |
| Current-limited bench PSU | 0-70 | Step 2 mandates a 100 mA current limit. **Use the UCL lab.** |
| Oscilloscope | 0-150+ | Steps 4 and 5.2. **Use the UCL lab.** |

### Three scenarios

| | £ |
|---|---|
| **UCL lab for PSU + scope, you own iron/tweezers, buy hot air only** | **~215-250** |
| Realistic — above plus microscope and callipers | ~260-300 |
| Own nothing, buy everything including PSU and scope | ~500+ |

### Then add rev B

A first mixed-signal board of this complexity should be assumed to need one respin: another PCB
order plus replacement parts for the sections that change, **~£45-65**. Budget it now rather than
discovering it.

**Realistic all-in, using UCL lab equipment: £260-315 including one respin.**

Note this is the *prototype* cost and says nothing about the project's sub-$20-per-unit target,
which is a volume BOM figure — the parts subtotal here buys 2 builds plus spares at 5-off pricing.

---

**The budget risk is now VAT and shipping, not the board.** Two separate consignments (JLCPCB and
LCSC) each attract UK import VAT at 20 % plus their own carriage, and that is what pushes the total
to the edge of the £100 envelope. Consolidating passives into the LCSC order rather than a separate
supplier is the cheapest lever.

---

## 4. PCB order form settings — READ BEFORE PAYING

Upload [`../release_20260810/pallorhb_ppg_gerbers.zip`](../release_20260810/pallorhb_ppg_gerbers.zip)
and set these explicitly. The defaults are wrong for this board:

| Field | Value | Why it matters |
|---|---|---|
| **Layers** | **6** | The default is 2. Selecting 2 with these gerbers gets the order queried or built wrong. |
| Thickness | 1.6 mm | |
| **Surface finish** | **ENIG** | Not HASL. Domed HASL pads wreck the 0402 TIA feedback caps and the 0.65 mm TSSOP. |
| **Soldermask** | **Black** | Load-bearing, not cosmetic: green mask transmits at 850-940 nm and would short-circuit the optical barrier. |
| Silkscreen | White | |
| Impedance control | No | |
| Assembly (PCBA) | **No** | Hand assembly; see `fab.md`. |

After upload, check JLC's layer-assignment preview shows six copper layers in the order
F / In1 / In2 / In3 / In4 / B.

**Price check.** `fab.md` estimates GBP 45-60 shipped, but that was an estimate, not a quote.
6-layer + ENIG + black mask at 100 x 40 mm can land closer to GBP 90. Get the real number at
checkout before committing, because the whole project budget is GBP 100.

**Optional tidy-up.** The zip contains 15 non-manufacturing layers (F_Fab, courtyards, User_*,
adhesive). Harmless, but deleting them before upload removes any chance of JLC's parser mapping the
dense F_Fab assembly drawing onto silkscreen.

**Order the parts now anyway.** LCSC shipping to the UK takes 1–3 weeks, the 810 nm emitter is the
single scarcest line in the design, and parts and PCB can arrive in parallel.

---

## 5. House-rule flag, unresolved

`BOARD_RULES.md` for this board says *"Never Extended without approval."* Almost every line above is
Extended — JLC's Basic/Preferred libraries contain no PPG analog parts at all. Since this board is
**hand-assembled**, the Extended per-part loading fee never applies, so the rule's purpose is not
violated in substance. Basic parts are marked above where they exist.

Confirm you are happy with this before paying.
