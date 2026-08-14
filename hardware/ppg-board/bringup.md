# Bring-up Plan — PallorHb PPG head rev A

Fill in the "measured" column as you go. **The board is not "working" until every gate passes.**
Stop at the first failed gate and diagnose; do not proceed hoping a later step explains it.

---

## Step 0 — Before the board arrives

### 0.1 Filament NIR-opacity coupon ⚠️ do this first

Common black PLA is **not** opaque at 850–940 nm. Many black pigments are carbon-black-free and
pass NIR freely, which would silently destroy the optical barrier the whole design depends on.

1. Print a 20 × 20 mm coupon, 2 mm thick, in the exact filament you plan to use for the clip, at
   the exact layer height and 100% infill.
2. Point any IR remote at a phone camera without an IR-cut filter (most webcams, or a cheap
   USB camera) and confirm you can see the emitter flashing.
3. Interpose the coupon. **Pass = the flash is completely invisible.**
4. Repeat at 1 mm thickness. If 2 mm passes but 1 mm does not, set the clip's minimum wall to 3 mm.

| Filament tried | 2 mm opaque? | 1 mm opaque? | Verdict |
|---|---|---|---|
| | | | |

**If no filament passes:** print in any colour and line the optical cavity with matte black
adhesive vinyl or aluminium tape. Do not proceed to the clip print until this is settled.

### 0.2 Pre-buy the scarce parts

Order **before** layout, not with the main BOM:

- [ ] D502 ~810 nm emitter (C22447934) × 10 — stock was 307 and this is the only line with no
      abundant substitute
- [ ] Read D502's datasheet and record its **actual peak wavelength**: ________ nm
      (the isosbestic argument requires 805–815 nm)
- [ ] U301 ADS131M02IPWR × 3

### 0.3 Verify the six [VERIFY] BOM lines

Re-run `scratchpad/jlcverify.py "<part>"` for each and record the LCSC number and stock.

---

## Step 1 — Visual inspection (board arrives, nothing powered)

- [ ] Solder bridges, especially U301 TSSOP-20 at 0.65 mm pitch — inspect under magnification
- [ ] Orientation: U201 pin 1, U301 pin 1, U101/U102 pin 1, D101 cathode band, D501/D502 anode
- [ ] Q501–503 orientation (SOT-23 is easy to rotate)
- [ ] Photodiode orientation — cathode to `TIA_BIAS`, anode to the summing node
- [ ] **Measure and record as-built ρ₁ and ρ₂** from the emitter centroid to each PD active-area
      centre, with callipers: ρ₁ = ______ mm, ρ₂ = ______ mm.
      These feed the μ_eff extraction directly; a 0.3 mm error is a 6% error in Δρ
- [ ] Continuity: `GND`–`AGND` single-point tie present; no short `3V3_D`–`GND`, `3V3_A`–`GND`,
      `VLED`–`GND`, `VSYS`–`GND`

---

## Step 2 — Power-up on bench PSU, current limit 100 mA

**Do not connect the battery or USB yet.** Inject 4.0 V at `VSYS` from a current-limited supply.

| Check | Expected | Measured |
|---|---|---|
| Inrush settles within | < 1 s | |
| Quiescent current, `ANALOG_EN` low | 15–35 mA (ESP32 boot) | |
| `3V3_D` (TP1) | 3.30 V ±3% (3.20–3.40) | |
| `3V3_A` (TP2), ANALOG_EN low | **< 0.1 V** | |
| `VLED` (TP4), ANALOG_EN low | **< 0.1 V** | |

> **Smoke gate.** If `3V3_A` or `VLED` sits at some intermediate voltage (~2.6 V is the classic
> symptom) rather than near zero, the back-drive path through the ADC's SPI pins is live. Stop.
> Check the 100 Ω series resistors on /CS, SCLK, DIN, DOUT and confirm firmware sets GPIO10–13 to
> high-Z before de-asserting GPIO18. Leaving this unresolved slowly degrades the ADC.

Then assert `ANALOG_EN`:

| Check | Expected | Measured |
|---|---|---|
| `3V3_A` (TP2) | 3.30 V ±3% | |
| `VLED` (TP4) | ≈ VSYS − 0.05 V | |
| Total current | 40–55 mA | |
| `TIA_BIAS` (TP7) | 0.300 V ±5% | |
| `3V3_D` ripple | < 20 mV pk-pk | |
| `3V3_A` ripple | **< 5 mV pk-pk** | |

De-assert `ANALOG_EN` again and confirm `3V3_A` decays to < 0.1 V within 200 ms (the R107 bleeder
is doing its job).

---

## Step 3 — USB and charging

- [ ] USB-C plugged: `VBUS` = 5.0 V ±5%; enumerate as USB-Serial-JTAG
- [ ] Both cable orientations work (proves both CC resistors)
- [ ] Battery connected, USB in: charge current ≈ 500 mA (measure into the cell), `CHG_STAT` low
- [ ] Q101 power path: with USB in, `VSYS` follows VBUS; with USB out, `VSYS` follows `VBAT`, no
      glitch on `3V3_D` during the transition (scope it)
- [ ] `VBAT_SNS` reads within 2% of the true cell voltage when GPIO2 is asserted, and the divider
      draws < 1 µA when it is not

---

## Step 4 — Programming and ADC comms

- [ ] Flash via PlatformIO over native USB; serial banner appears
- [ ] `ADC_CLKIN` (TP12): 8.192 MHz ±1%, clean edges
- [ ] Read the ADS131M02 ID register — must match the datasheet value
- [ ] `/DRDY` (TP10) toggles at the configured rate
- [ ] With inputs shorted to `TIA_BIAS`, both channels read within ±200 LSB of zero

**Noise floor, inputs shorted** — record RMS in LSB and µV referred to input:

| Channel | Gain | Expected | Measured |
|---|---|---|---|
| ch0 (near) | 1 | < 10 µV rms | |
| ch1 (far) | 4 | < 4 µV rms | |

The datasheet input-referred noise is **5.35 µV rms typical** at gain 1, 4 kSPS, so anything under
~10 µV rms at gain 1 is healthy and a target below 5 µV would be unachievable. Noise falls with
higher OSR — if you are close to the limit, raise OSR before suspecting the board.

- [ ] **USB-vs-battery A/B:** repeat the noise floor on battery only. If battery is materially
      quieter, the USB ground is injecting noise — note it and always collect data on battery.

---

## Step 5 — Optical bring-up, staged

### 5.1 Optical zero — gate before any finger touches the sensor

Cover the whole optical head with opaque tape. All LEDs off.

| Check | Expected | Measured |
|---|---|---|
| `TIA_NEAR_OUT` | 0.300 V ±2 mV (= bias, i.e. no photocurrent) | |
| `TIA_FAR_OUT` | 0.300 V ±2 mV | |
| Drift over 60 s | < 1 mV | |

**Gate:** if either output sits materially above bias with the head covered, there is a light leak
or a dark-current problem. Do not proceed.

### 5.2 LED current — one wavelength at a time

Scope across Rsense (TP11) with each `ENn` asserted individually.

| Emitter | ISET duty | Expected I | Measured | Vf |
|---|---|---|---|---|
| 660 nm | 67% | 20 mA ±5% | | |
| 810 nm | 67% | 20 mA ±5% | | |
| 850 nm | 67% | 20 mA ±5% | | |

- [ ] Current edges are clean — **no ringing or oscillation**. Oscillation here means the sink
      loop is unstable; check R501 (220 Ω gate series) and C501 (47 pF compensation)
- [ ] Turn-on settles within 20 µs
- [ ] With all `ENn` deasserted, current is < 10 µA (gate pulldowns working)
- [ ] Sweep VSYS down to 3.4 V and confirm the 660 nm channel still regulates 20 mA — this is the
      compliance limit and where the design is tightest

### 5.3 Optical crosstalk — the barrier test

Head uncovered, **nothing in front of the sensor** (point it at open air / a black cloth).

| Check | Expected | Measured |
|---|---|---|
| Near channel, 850 nm lit, no target | < 2% of the with-finger DC | |
| Far channel, 850 nm lit, no target | < 2% of the with-finger DC | |

**Gate:** this measures light piping straight from emitter to detector through the board and mask.
If it exceeds ~5%, the slot or via fence is not doing its job and every subsequent measurement has
a large additive offset that does *not* dark-subtract out.

### 5.4 Ambient sweep

Head uncovered, no finger, all LEDs off — this reads pure ambient.

| Condition | Dark level expected | Measured |
|---|---|---|
| Dark room | < 1% of headroom | |
| 500 lux office | < 10% of headroom | |
| Next to a window | flag bit 1 should assert | |

- [ ] Repeat **with a finger in the sealed clip** in all three conditions and confirm perfusion
      index is unchanged within 10%. If PI changes with room lighting, the mechanical seal is
      inadequate — that is a clip problem, not an electronics problem

### 5.5 First pulse

Finger in the clip, 850 nm, near channel.

| Check | Expected | Measured |
|---|---|---|
| DC level | 20–60% of TIA headroom | |
| Visible cardiac AC | yes | |
| Perfusion index | 0.5–5% | |
| Heart rate vs manual pulse count | within ±3 bpm | |
| Far channel DC | 5–15% of near DC | |

**Gate:** the far/near DC ratio is the whole measurement. If it is above ~30%, optical crosstalk is
dominating; if below ~2%, the far channel is too photon-starved — raise drive current or reduce ρ₂.

### 5.6 Full frame

- [ ] All four phases running at 800 Hz, no frame overruns over 10 minutes
- [ ] Dark-subtracted outputs stable
- [ ] Decimated stream is exactly 100 Hz
- [ ] Inter-wavelength crosstalk check: light only 850, confirm the 660 and 810 slots read within
      noise of the dark level. **Any systematic offset here is unsettled TIA residue** — recheck
      the settle window and the 3.3 kΩ/1 nF network

---

## Step 6 — Reference target and drift

- [ ] Machine or print a white PTFE / white PETG plug that seats in the clip at a defined stop
- [ ] 10 s reference capture; record all six channel DC values
- [ ] Repeat after 30 min of continuous running — **drift < 2%**
- [ ] Repeat cold (from a cold start) versus warm, logging `head_temp_c`

This reference capture becomes the first and last step of every data-collection session.

---

## Step 7 — Sign-off

The board is "working" only when all of the following are true:

- [ ] Every gate above passed and is recorded with a number
- [ ] Optical zero holds, crosstalk < 2%, ambient sweep passes with the seal
- [ ] 10-minute capture with zero overruns and a physiologically plausible PI and HR
- [ ] Reference-target drift < 2% over 30 min
- [ ] `features.py` rewrite (design.md §6.5) is merged **and its new unit tests pass**

Only then start collecting data. Anything earlier bakes a hardware or software defect into the
first labelled dataset.
