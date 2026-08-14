# PallorHb PPG head — rev A design

Companion to [`constraints.md`](constraints.md), [`fab.md`](fab.md), [`sourcing.md`](sourcing.md),
[`bringup.md`](bringup.md). Read `constraints.md` first — it states the measurement physics that
justifies every choice below.

---

## 1. Architecture

### 1.1 Block diagram

```
                 ┌──────────── MAIN BOARD 46 × 30 mm ────────────┐
 USB-C ──┬─ ESD ─┤ TP4056 ──┬── power path ── VSYS ──┬── TLV75533 ──> 3V3_D ── ESP32-S3-MINI-1
         │       │  charger │   (FET + Schottky)     │              │
         └─ D+/D-────────────────────────────────────┼──────────────┴── TLV75533 ──> 3V3_A
                 │  1S LiPo ┘                        │                (gated, ANALOG_EN)
                 │                                   └── load switch ──> VLED
                 │  ADS131M02  (24-bit, 2 ch SIMULTANEOUS)  <──SPI── ESP32-S3
                 └───────────────────┬───────────────────────────────┘
                                     │ 15-way JST-GH, 100 mm silicone
                 ┌───────────────────┴──── OPTICAL HEAD 26 × 20 mm ────┐
                 │                                                      │
                 │   PD_far ──[TIA_far 1M0]──> AIN1P      ρ₂ = 11.5 mm  │
                 │      ║                                               │
                 │   ═══╬══ slot + via fence ════════════               │
                 │      ║                                               │
                 │   EMITTER SITE:  660 ─┐                              │
                 │                  810 ─┼─ 3 current sinks ── VLED     │
                 │                  850 ─┘                              │
                 │      ║                                               │
                 │   ═══╬══ slot + via fence ════════════               │
                 │      ║                                               │
                 │   PD_near ─[TIA_near 470k]─> AIN0P     ρ₁ = 6.5 mm   │
                 └──────────────────────────────────────────────────────┘
```

### 1.2 The two decisions that define this board

**One emitter site, two detectors — not two emitters, one detector.** Both detectors sample the
*same* LED pulse simultaneously (the ADS131M02 has two independent, simultaneously-sampling
modulators). LED radiant output drifts with junction temperature, drive current and age; in the
far/near ratio it is a **common factor that cancels exactly**. The mirror-image topology would
make the measurement depend on the ratio of two LEDs' outputs — the least stable quantity in the
system, requiring per-session calibration against a reference target. This choice removes that
entire failure mode.

**DC attenuation versus distance, not AC/DC wavelength ratios.** See `constraints.md` §"The
measurement". Wavelength ratios cancel c_Hb by construction; distance ratios do not.

### 1.3 Acquisition sequence

| Phase | Lit | Duration | Settle | Convert |
|---|---|---|---|---|
| 0 | 660 nm | 312.5 µs | 100 µs | 212.5 µs |
| 1 | 810 nm | 312.5 µs | 100 µs | 212.5 µs |
| 2 | 850 nm | 312.5 µs | 100 µs | 212.5 µs |
| 3 | DARK (all off) | 312.5 µs | 100 µs | 212.5 µs |

Frame = 1.25 ms → **800 Hz**. Each frame yields 4 phases × 2 detectors = 8 conversions.
Dark-subtract each lit phase against phase 3, low-pass at 20 Hz, decimate ×8 → **100 Hz per
wavelength per detector**.

Settling verified in simulation (§7.1): near 42.7 µs, far 82.8 µs to 0.01%. The 100 µs budget has
>3× margin on the near channel and 1.2× on the far — deliberately generous because unsettled
residue appears as *inter-wavelength crosstalk* that dark subtraction cannot remove and that looks
like physiology.

---

## 2. Net-by-net schematic

Reference designators: 1xx = power/USB, 2xx = MCU, 3xx = ADC, 4xx = TIA, 5xx = emitters/sinks.

### 2.1 USB-C, ESD, charging

| Ref | Part | Connections |
|---|---|---|
| J101 | USB-C receptacle, 16-pin | VBUS→`VBUS`; GND→`GND`; CC1→R101; CC2→R102; D+→U101.4; D−→U101.6; SHIELD→`GND` via C101 |
| R101, R102 | 5.1 kΩ 0402 | CC1/CC2 → `GND`. Advertises a sink; without both, many chargers supply nothing |
| U101 | USBLC6-2SC6 | Pin1 D−_in, Pin2 GND, Pin3 D−_out→ESP32 GPIO19, Pin4 D+_in, Pin5 VBUS, Pin6 D+_out→ESP32 GPIO20 |
| C101 | 100 nF 0402 50 V | Shield → `GND`. AC-couples the shield; keeps chassis noise off signal ground |
| C102 | 10 µF 0805 X5R 16 V | `VBUS` → `GND` |
| D101 | SS34 / B340 | `VBUS` → `VSYS` (anode VBUS). USB path of the power-path OR |
| U102 | TP4056-42 ESOP-8 | 1 TEMP→`GND` (disables NTC gate); 2 PROG→R103; 3 GND; 4 VBAT→`VBAT`; 5 VBAT; 6 STAT→R104; 7 CE→`VBUS`; 8 VCC→`VBUS`; EP→`GND` |
| R103 | **2.4 kΩ** 0603 | PROG → `GND`. TP4056: I_chg = 1200/R_PROG → 1200/2400 = **500 mA** (0.5 C on a 500 mAh cell). 1.2 kΩ would give 1 A and over-stress the cell |
| R104 | 4.7 kΩ 0603 | STAT → GPIO38 (open-drain, active low when charging) |
| C103 | 10 µF 0805 | `VBAT` → `GND` |
| J102 | JST-PH 2-pin | `VBAT`, `GND` — 1S LiPo 500 mAh, **protected cell required** |

> ⚠️ The TP4056 has no battery-protection FETs. Use a cell with an integrated protection PCM, or
> the pack can be over-discharged and shorted. This is not optional.

### 2.2 Power path and regulation

| Ref | Part | Connections |
|---|---|---|
| Q101 | AO3401A (P-ch) | S→`VBAT`, D→`VSYS`, G→`VBUS` via R105. Turns the battery *off* when USB is present |
| R105 | 100 kΩ 0603 | `VBUS` → Q101.G |
| R106 | 100 kΩ 0603 | Q101.G → `VBAT` (pulls gate low when no USB, turning the battery on) |
| C104 | 22 µF 0805 X5R | `VSYS` → `GND` |
| U103 | TLV75533PDBVR SOT-23-5 | 1 IN←`VSYS`; 2 GND; 3 EN←`VSYS`; 4 NC; 5 OUT→`3V3_D` |
| C105/C106 | 1 µF 0603 / 10 µF 0805 | U103 IN / OUT decoupling |
| U104 | TLV75533PDBVR SOT-23-5 | 1 IN←`VSYS`; 2 GND; 3 EN←`ANALOG_EN` (GPIO18); 5 OUT→`3V3_A` |
| C107/C108 | 1 µF 0603 / 10 µF 0805 | U104 IN / OUT decoupling |
| R107 | 100 kΩ 0603 | `3V3_A` → `GND`. **Bleeder** — the TLV755P has no active discharge, so without this 3V3_A floats after gating |
| Q102 | AO3401A (P-ch) | S→`VSYS`, D→`VLED`, G via R108 100 kΩ to `VSYS`, gate pulled low by Q103 (2N7002) driven from `ANALOG_EN`. **VLED must die with 3V3_A** or emitters can be live while the sink control loop is unpowered |
| C109 | 100 µF 1206 X5R | `VLED` → `GND` at the *emitter site on the head*. Reservoir for the 30 mA pulse |
| C110 | 1 µF 0603 | `VLED` → `GND`, adjacent to C109 |

**Battery sense:** R109 (200 kΩ) `VBAT`→`VBAT_SNS`, R110 (100 kΩ) `VBAT_SNS`→Q104 drain;
Q104 = 2N7002 with source to `GND`, gate = GPIO2. C111 = 100 nF at `VBAT_SNS` → GPIO1 (ADC1_CH0).
The FET disconnects the divider in sleep — a permanently connected 300 kΩ divider drains ~14 µA,
which is 4× the rest of the sleep budget.

### 2.3 MCU

**U201 = ESP32-S3-MINI-1-N8** (LCSC C2913206). S3 rather than C3 for the vector DSP instructions
used by the W11 on-device inference goal, and 8 MB flash for model storage. No PSRAM needed:
buffer maths = 2 s × 800 Hz × 8 conversions × 4 B = 51.2 kB, comfortably inside 512 kB SRAM.

| Pin | Net | Note |
|---|---|---|
| GPIO0 | `BOOT` | SW201 to `GND`, R201 10 kΩ pull-up. **Strap — must be high at boot** |
| GPIO1 | `VBAT_SNS` | ADC1_CH0 |
| GPIO2 | `VBAT_SNS_EN` | Q104 gate |
| GPIO4 | `EN660` | sink enable |
| GPIO5 | `EN810` | sink enable |
| GPIO6 | `EN850` | sink enable |
| GPIO7 | `NTC_SNS` | ADC1_CH6, head thermistor |
| GPIO8 | `ADC_CLKIN` | LEDC PWM, 8.192 MHz |
| GPIO9 | `ADC_SYNC_RESET` | active low |
| GPIO10 | `ADC_CS` | active low |
| GPIO11 | `ADC_SDI` | SPI MOSI |
| GPIO12 | `ADC_SCLK` | SPI CLK |
| GPIO13 | `ADC_SDO` | SPI MISO |
| GPIO14 | `ADC_DRDY` | input, active low. **No internal pull-up** — see §2.6 |
| GPIO15/16/17 | `ISET660/810/850` | LEDC PWM → RC → sink reference |
| GPIO18 | `ANALOG_EN` | gates 3V3_A **and** VLED |
| GPIO19/20 | `USB_D−` / `USB_D+` | native USB-Serial-JTAG |
| GPIO21 | `LED_STAT` | R202 1 kΩ → D201 green 0603 → `GND` |
| GPIO38 | `CHG_STAT` | from TP4056 STAT |
| GPIO43/44 | `TXD0` / `RXD0` | 4-pin debug header J201 |
| EN | `RESET` | R203 10 kΩ to `3V3_D`, C201 1 µF to `GND` |

Decoupling: C202 10 µF 0805 + C203 1 µF 0603 + C204 100 nF 0402, all on the module's 3V3 pin,
100 nF closest.

**Unused straps GPIO45 and GPIO46: leave unconnected.** Do not route to test points — a probe
capacitance on a strap can change boot mode.

### 2.4 ADC

**U301 = ADS131M02IPWR**, TSSOP-20 (LCSC C2922448, 7 481 in stock, $3.65). 24-bit, two
**simultaneously sampling** delta-sigma channels, 64 kSPS, native 2.7–3.6 V, internal 1.2 V
reference, PGA per channel. All four properties confirmed against the TI product page — the
internal reference is why no external REF3325 is fitted, and the native 3.3 V range is why no
boost converter is needed (the ADS1256 alternative needs a 5 V analog supply, which would have
reintroduced switching noise into the optical measurement).

Chosen over MCP3564R, which the design review flagged as the weakest sourcing line on the board:
MCP3564RT-E/ST has **22 units** in stock at $8.80, MCP3561/3562 return zero results, and the
similarly-named MCP3564-E/ST has *no internal reference* — a one-character part-number error that
would cost a board revision.

**Exact PW (TSSOP-20) pinout, from the TI datasheet (SBAS853A) Table 5-1:**

| Pin | Name | Net | Note |
|---|---|---|---|
| 1 | AVDD | `3V3_A` | C301 **1 µF** to AGND (datasheet-specified) + C302 100 nF |
| 2 | AGND | `AGND` | |
| 3 | AIN0P | `TIA_NEAR_OUT` | via matched network §2.5 |
| 4 | AIN0N | `TIA_BIAS_BUF` | via matched network |
| 5 | **AIN1N** | `TIA_BIAS_BUF` | ⚠️ **N before P on channel 1** — reversed vs channel 0 |
| 6 | **AIN1P** | `TIA_FAR_OUT` | ⚠️ easy to wire backwards; check against the datasheet figure |
| 7–10 | NC | — | leave unconnected |
| 11 | /SYNC//RESET | `ADC_SYNC_RESET` | GPIO9, R301 10 kΩ pull-up to `3V3_A` |
| 12 | /CS | `ADC_CS` | GPIO10, via 100 Ω series |
| 13 | /DRDY | `ADC_DRDY` | GPIO14 |
| 14 | SCLK | `ADC_SCLK` | GPIO12, via 100 Ω series |
| 15 | DOUT | `ADC_SDO` | GPIO13 |
| 16 | DIN | `ADC_SDI` | GPIO11, via 100 Ω series |
| 17 | CLKIN | `ADC_CLKIN` | GPIO8 LEDC PWM, 8.192 MHz |
| 18 | CAP | — | C304 **220 nF** to DGND — internal digital LDO output, **not** 1 µF |
| 19 | DGND | `AGND` | tied to AGND at a single point under the package |
| 20 | DVDD | `3V3_A` | C303 **1 µF** to DGND (datasheet-specified) |

The TSSOP package has **no thermal pad** (only the WQFN variant does), so nothing to tie.

Datasheet limits confirmed against §6.3: AVDD 2.7–3.6 V ✓; analog input absolute range
AGND − 1.3 V to AVDD at gain 1/2/4, so the 0.30 V bias and 1.19 V peak are both well inside ✓;
CLKIN 8.192 MHz nominal for high-resolution mode ✓; differential input impedance **300 kΩ** at
gain ≤ 4, against our 4.3 kΩ source — 1.4% loading, negligible, and identical on both arms ✓.

PGA: near = 1 (0.94 V swing into ±1.2 V FS), far = 4 (0.20 V → 0.80 V).

### 2.5 Transimpedance amplifiers — on the head

Two identical channels. **Photodiode in photovoltaic (zero-bias) mode** — cathode to `TIA_BIAS`,
anode to the summing node — for lowest dark current and lowest noise.

| Ref | Part | Connections |
|---|---|---|
| D401 | VEMD5010X01 | K→`TIA_BIAS`, A→U401.IN− |
| U401 | OPA333AIDBVR SOT-23-5 | IN+←`TIA_BIAS`, IN−←D401.A, OUT→`TIA_NEAR_OUT`, V+←`3V3_A`, V−←`AGND` |
| R401 | **470 kΩ** 0603 1% | U401 IN− → OUT |
| C401 | **10 pF** 0402 C0G | across R401 |
| D402 | VEMD5010X01 | K→`TIA_BIAS`, A→U402.IN− |
| U402 | OPA333AIDBVR | as U401 → `TIA_FAR_OUT` |
| R402 | **1.0 MΩ** 0603 1% | U402 IN− → OUT |
| C402 | **4.7 pF** 0402 C0G | across R402 |

**Why these values, and why not the textbook ones.** The classic compensation
Cf = √(Cin / 2π·Rf·GBW) gives 6.8 pF for the near channel (65° phase margin, 1 dB peaking). Under
simulation that 1 dB of peaking *rings*, and settling to 0.01% takes **57.9 µs**. Over-compensating
to 10 pF gives a flat response that settles in **42.7 µs** — 26% faster. In a time-multiplexed
sampled system, settling time is the figure of merit, not bandwidth. Full data in §7.1.

The far channel uses Rf = 1 MΩ rather than the ~4.7 MΩ that would equalise the two outputs,
because 4.7 MΩ settles in 130 µs against 83 µs for 1 MΩ. The missing gain is recovered in the ADC
PGA, which costs nothing. Noise check: at Rf = 1 MΩ the resistor's thermal noise current is
128 fA/√Hz, versus 253 fA/√Hz of shot noise on the 0.2 µA far photocurrent — the channel remains
**photon-limited**, which is the correct design point. Raising Rf would improve a noise term that
is already dominated.

**Bias generator:** R403 (100 kΩ) `3V3_A`→`TIA_BIAS_RAW`, R404 (10 kΩ) →`AGND`, giving 0.30 V;
C403 10 µF + C404 100 nF to `AGND`. Buffered by U403A (MCP6002) → `TIA_BIAS_BUF`.

**Matched ADC driver network — mandatory.** Both arms must present identical source impedance or
cable common-mode rejection collapses to ~0.5 dB:

| Arm | Head-side series R | Head-side C to AGND | ADC-side series R |
|---|---|---|---|
| `TIA_NEAR_OUT` → AIN0P | R405 3.3 kΩ 1% | C405 1 nF C0G | R409 1 kΩ 1% |
| `TIA_BIAS_BUF` → AIN0N | R406 3.3 kΩ 1% | C406 1 nF C0G | R410 1 kΩ 1% |
| `TIA_FAR_OUT` → AIN1P | R407 3.3 kΩ 1% | C407 1 nF C0G | R411 1 kΩ 1% |
| `TIA_BIAS_BUF` → AIN1N | R408 3.3 kΩ 1% | C408 1 nF C0G | R412 1 kΩ 1% |

Plus a differential capacitor across each pair at the ADC: C409, C410 = 10 nF C0G (10× the
single-ended caps — the standard delta-sigma driver network, and it defines the differential
impedance the switched-cap input sees).

3.3 kΩ, not 33 kΩ: τ = 3.3 µs gives 30 time constants inside the 100 µs settle window
(residue ~1e−13). At 33 kΩ, τ = 33 µs leaves 0.23% of the inter-phase step unsettled — which is
**23% of a cardiac AC amplitude** of memory from the previous wavelength, landing directly on the
ratio features.

**Head thermistor:** RT401 10 kΩ NTC 0603 to `AGND`, R413 10 kΩ to `3V3_A`, midpoint → `NTC_SNS`.
Logged per frame; the ~810 nm die's peak shifts 0.2–0.3 nm/K.

### 2.6 Emitters and current sinks — on the head

| Ref | Part | Note |
|---|---|---|
| D501 | **CT-3030SUR660+850C-PT** (note `+`, not `/`) | Dual-die 660 + 850 nm, SMD3030-4P, 3.2 × 3.0 × **0.63 mm** |
| D502 | JNJ-L-3535AW30-80530-SL-J2-D3 | **810 nm confirmed**, SMD3535-3P, 3.5 × 3.5 × **4.09 mm** |

### Datasheet-verified pinouts — one of these was wrong

**D501** (Chongtian rev A1, 2025-09-18). The pin order is **850 first**, which is the opposite of
what the part name suggests:

| Pad | Function |
|---|---|
| 1 | 850 nm **anode** |
| 2 | 850 nm **cathode** |
| 3 | 660 nm **anode** |
| 4 | 660 nm **cathode** |

⚠️ My original symbol had 1/2 = 660 and 3/4 = 850 — **backwards**. Left uncorrected, the "660"
current sink would have driven the 850 die and vice versa. The board would have powered up, lit,
produced clean-looking waveforms, and labelled every sample with the wrong wavelength. Fixed:
symbol `pallorhb_emitters:CT3030_DUAL` now carries the datasheet order, and D501 is rewired.

**D502** (JNJ rev A/2, 2024-04-06): pad **1 = cathode**, **2 = anode**, **3 = centre, no connect**.
This matches how it was already wired.

### ⚠️ Mechanical conflict the datasheets exposed

| Part | Height |
|---|---|
| D501 emitter | **0.63 mm** |
| D401/D402 photodiodes | 0.90 mm |
| **D502 (810 nm)** | **4.09 mm** — silicone dome, Ø2.8 mm aperture |

The 810 nm emitter stands **3.5 mm proud** of everything else on the head. On a finger-contact
optical head that is not cosmetic: the dome touches skin first, holds the finger off the other
three components, and puts a 3 mm air gap over the photodiodes — destroying both the light seal
and the contact-pressure control the clip exists to provide.

Options, in order of preference:

1. **Mill a relief pocket in the clip** so the dome sits recessed and the finger rests on a flat
   window. Cheapest, keeps the part, but the dome's 30° beam then couples through a cavity.
2. **Counterbore the PCB** — not possible at JLCPCB on a 1.6 mm 2-layer board.
3. **Substitute a flat-top 810 nm emitter.** Best optically, but §sourcing shows ~810 nm stock is
   thin (307 pcs of this line, no abundant alternative), so this may not be available.
4. **Mount D502 on the back of the head** and route its light through a board hole — adds a hole
   and loses the co-planar geometry.

**This must be settled before layout finishes**, because it changes the clip CAD and possibly the
board outline. It is now the top open item in `STATUS.md`.

### As-placed source–detector distances

D501 is centred **on** the detector axis and rotated 90°, so its two dies straddle that axis and
get identical ρ. D502 sits to one side with its own ρ pair.

| Emitter | ρ_near | ρ_far | Δρ |
|---|---|---|---|
| 850 nm (D501 die) | 6.176 mm | 11.325 mm | 5.149 mm |
| 660 nm (D501 die) | 6.176 mm | 11.325 mm | 5.149 mm |
| 810 nm (D502) | 7.817 mm | 12.297 mm | 4.480 mm |

Equal ρ *across* wavelengths is a convenience, not a requirement: μ_eff is extracted per wavelength
from that wavelength's own far/near pair, so each emitter only needs its own ρ known accurately.
What matters is that these numbers go into the firmware and the model as constants.

The ±0.75 mm die offset inside D501 is **estimated from the datasheet drawing**, not dimensioned.
Combined with the VEMD5010X01's unstated optical-centre offset, this means the geometric ρ above
should be treated as a starting value and **calibrated empirically** against the PTFE reference
target (bring-up §6) rather than trusted outright.

Three sinks, one per die. Each identical:

| Ref | Part | Connections |
|---|---|---|
| U403B / U404A / U404B | MCP6002 (2 × SOIC-8) | IN+ ← `ISETn` (filtered), IN− ← Rsense top, OUT → gate network |
| Q501–Q503 | AO3400A SOT-23 | D → LED cathode, S → Rsense top, G ← R_g |
| R501–R503 | **220 Ω** 0603 | op-amp OUT → gate. Isolates the ~400 pF Ciss; without it the loop oscillates |
| R504–R506 | **100 kΩ** 0603 | gate → `AGND`. Defines the gate when 3V3_A is off; without it leakage can bias the FET on and dimly light the emitters while "off" |
| C501–C503 | **47 pF** 0402 | op-amp OUT → IN−. Loop compensation |
| R507–R509 | **10 Ω** 0805 1% | Rsense, source → `AGND` |

I_LED = V_ISET / 10 Ω.

**One shared ISET line, three fast enables.** Only one die is ever lit at a time, so all three
sinks take the same current reference. GPIO15 drives a PWM that is filtered *on the head* by R510
(10 kΩ) → node, R513 (1 kΩ) to `AGND`, C504 (100 nF) across the 1 kΩ. Divider ratio 1/11 →
**V_ISET max 0.30 V → 30 mA hardware ceiling**, 20 mA nominal at 67% duty. Time constant
(10 k ∥ 1 k) × 100 nF = 91 µs; the duty is set once at session start and left alone, never changed
per phase.

Switching is done by the enables, not by the reference — pulling ISET would take 91 µs to decay,
which eats most of the 100 µs settle budget. Each `ENn` (GPIO4/5/6) drives Q504–Q506 (2N7002)
whose drain pulls that sink's op-amp **non-inverting input** to `AGND` through 100 Ω, overriding
the shared reference for that channel only. Turn-off is then limited by the op-amp and gate
network, not by the RC — measured settle target < 20 µs (bring-up step 5.2).

R511/R512 and C505/C506 are therefore **not fitted** in rev A; the footprints remain for a future
per-wavelength reference if the three dies turn out to need very different drive.

**Compliance check at end of discharge — updated with verified Vf data.**

| Die | Verified Vf | Source |
|---|---|---|
| 660 nm (D501 red) | **1.4–1.6 V** | JLCPCB C53191416 |
| 850 nm (D501 IR) | **1.8–2.2 V** | JLCPCB C53191416 |
| **810 nm (D502)** | **2.5–2.6 V** | JLCPCB C22447934 |

This **corrects an assumption**: the earlier analysis named the 660 nm AlGaInP die as the
worst case at ~2.6 V. It is actually the *lowest* at 1.4–1.6 V. The binding channel is the
**810 nm emitter at 2.6 V**.

Worst case at VBAT = 3.4 V (firmware cutoff): 3.4 − 2.6 (Vf 810) − 0.20 (V_sense) − 0.2
(Q502 V_ds sat) = **0.4 V margin**. The conclusion is unchanged, but the channel to watch during
bring-up step 5.2 is **810 nm, not 660 nm** — sweep VSYS down to 3.4 V and confirm the 810 sink
still regulates. The 660 nm channel has ~1.0 V more headroom than originally budgeted.

Firmware **must** enforce the 3.4 V cutoff; below it the 810 nm sink drops out of compliance and
`mueff_810` — the concentration-sensitive channel — drifts with state of charge while still
producing a plausible-looking waveform.

**Also verified on D502:** peak **810 nm** with 30 nm half-width, 30° viewing angle, 700 mA max
rating. The wavelength confirmation is what the whole spatially-resolved isosbestic argument
depended on, and it passes. Note it is a high-power die run at only 20 mA (3% of rating) — output
will be modest but adequate, and current density that low is a stable operating point.

**Enable mechanism:** `EN660/810/850` each drive a 2N7002 (Q504–Q506) that pulls the corresponding
`ISETn` node to `AGND`. Pulling ISET rather than the gate avoids op-amp saturation-recovery time
inside the 312 µs phase.

**Back-drive protection.** The ADC and head op-amps sit on `3V3_A`, which GPIO18 gates off, while
the ESP32 stays on `3V3_D`. Any SPI pin left driven high would forward-bias the ADC's ESD diode
into an unpowered rail, float `3V3_A` to ~2.6 V and leave the analog section in an undefined
state. Two mitigations, both required:

1. The 100 Ω series resistors on /CS, SCLK, DIN, DOUT (§2.4) limit back-drive current.
2. Firmware **must** reconfigure GPIO10–13 to high-Z inputs *before* de-asserting GPIO18, and
   restore them after asserting it. GPIO14 (/DRDY) must have its internal pull-up disabled.

### 2.7 Inter-board connector

**J401 / J202 = JST-GH 15-way**, 1.25 mm pitch, silicone ribbon 100 mm.

**As wired** (this supersedes the earlier draft — the two negative arms need *separate* conductors
or the impedance matching of §2.5 is defeated at the cable):

| Pin | Net | Note |
|---|---|---|
| 1 | `VLED` | |
| 2 | `GND` | power return |
| 3 | `3V3_A` | |
| 4 | `AGND` | |
| 5 | `CBL_AIN0P` | near-channel signal — **differential pair with pin 6** |
| 6 | `CBL_AIN0N` | near-channel reference arm |
| 7 | `AGND` | flanks the ch0 pair |
| 8 | `CBL_AIN1P` | far-channel signal — **differential pair with pin 9** |
| 9 | `CBL_AIN1N` | far-channel reference arm |
| 10 | `AGND` | flanks the ch1 pair |
| 11 | `NTC_SNS` | head thermistor |
| 12 | `EN660` | digital |
| 13 | `EN810` | digital |
| 14 | `EN850` | digital |
| 15 | `ISET_PWM` | digital PWM from GPIO15, filtered to DC on the head |

Each channel's P and N conductors are **adjacent**, so cable-coupled interference arrives as common
mode on a matched pair and is rejected by the ADC's 100 dB CMRR — that is the whole point of
matching R405–R408 and R409–R412 to 1%. Each pair is flanked by an AGND conductor.

**No analog reference crosses the cable.** `ISET_PWM` is carried as a *digital* PWM and filtered to
DC on the head by R510/R513/C504 (§2.6). Sending an already-filtered high-impedance analog level
down 100 mm of ribbon alongside the TIA outputs would be a direct injection path; sending a square
wave and filtering at the destination is not. Add 1 kΩ + 1 nF at the head end of pins 12–15 to
slow their edges so the transitions do not couple into the analog group. Route the ribbon so it
leaves the head on the side away from the photodiodes.

---

## 2.9 Corrections found during schematic capture

Entering the design into KiCad surfaced errors in the sections above. All are now fixed in the
schematic; they are recorded here because the *reasoning* matters more than the fix.

| # | What was wrong | How it was caught | Fix |
|---|---|---|---|
| 1 | **TP4056 pinout was wrong.** §2.1 had pin 6 = STAT, 7 = CE, 8 = VCC. | The KiCad symbol's pin names disagreed. | Real pinout: 1 TEMP, 2 PROG, 3 GND, 4 VCC, 5 BAT, 6 STDBY, 7 CHRG, 8 CE, 9 EPAD. Wired accordingly; CE→VBUS, CHRG→R104→GPIO38. |
| 2 | **ADS131M02 CAP decoupling was 1 µF.** | TI datasheet Table 5-1. | It is the internal digital-LDO output and wants **220 nF**. AVDD and DVDD want 1 µF each. |
| 3 | **AIN1N/AIN1P are reversed relative to channel 0** (pin 5 = N, pin 6 = P). | Datasheet pinout. | Wired correctly. This is a classic silent-failure trap — the far channel would have inverted. |
| 4 | **Power-path FET orientation would have back-charged the battery.** With source→VBAT / drain→VSYS, the P-channel body diode conducts VSYS→VBAT whenever USB is present, bypassing the charger's current and voltage regulation — genuinely unsafe on a LiPo. | Working through the body-diode direction while wiring. | Reversed: **source→VSYS, drain→VBAT**, so the body diode only conducts VBAT→VSYS. Gate divider changed from 100 k/100 k to **R105 = 10 kΩ (VBUS→gate), R106 = 1 MΩ (gate→GND)**, which puts the gate at 4.95 V against a 4.7 V source — solidly off on USB, hard on when USB is absent. The original divider left Vgs at −1.5 V, i.e. the FET would never have turned off. |
| 5 | **Sink op-amps were a dual (MCP6002).** | Multi-unit symbols complicate capture and the part count did not divide cleanly (3 sinks + 1 bias buffer). | Changed to **4 × TLV9001** singles (SOT-23-5). Cheaper ($0.086 vs $0.24), better stocked, one unit per function. |
| 6 | **Enable logic had no defined state.** Shunting the shared ISET node would have collapsed the reference for *all three* sinks at once. | Tracing what happens when one channel is disabled. | Each sink gets its own **10 kΩ series (R514–R516)** from `ISET_SHARED` to its own `ISET_n`, and Q504–Q506 shunt only that node. Added **R517–R519 (100 kΩ pull-ups to 3V3_A)** so a floating MCU pin holds the shunt FET *on* = LED *off*. Note the enables are therefore **active-low**: drive low to light. |
| 7 | **Photodiode-to-emitter gap was too tight for the barrier slot.** At ρ₁ = 6.5 mm with a 5 mm-tall PD and a 3.5 mm LED, the gap is 2.25 mm — less than a 1.6 mm slot plus clearance. | Arithmetic while placing. | **PDs rotated 90°** so their 4.1 mm axis faces the emitter. Gap becomes 2.7 mm, giving 0.55 mm clearance each side of the slot. ρ₁ = 6.5 mm is preserved. |
| 8 | **ESP32-S3-MINI-1 footprint does not exist** in the KiCad libraries. | Board sync reported it missing. | Uses `RF_Module:ESP32-S2-MINI-1` — the shared Espressif MINI-1 module footprint, 65 pads, and the KiCad footprint's own description links to the **S3**-MINI-1 datasheet. Verify against the mechanical drawing before ordering. |

### 2.8 Test points

`TP1` 3V3_D, `TP2` 3V3_A, `TP3` VSYS, `TP4` VLED, `TP5` TIA_NEAR_OUT, `TP6` TIA_FAR_OUT,
`TP7` TIA_BIAS, `TP8` AGND, `TP9` GND, `TP10` ADC_DRDY, `TP11` Rsense top (660 sink — lets you
scope the actual LED current), `TP12` ADC_CLKIN.

---

## 3. Bill of materials

Prices are LCSC USD unit at 2026-08-10, converted at ~0.79 GBP/USD. One board.

| Ref | Qty | Part | LCSC | Pkg | £ ea | £ |
|---|---|---|---|---|---|---|
| U201 | 1 | ESP32-S3-MINI-1-N8 | C2913206 | module | 3.70 | 3.70 |
| U301 | 1 | ADS131M02IPWR | C2922448 | TSSOP-20 | 2.89 | 2.89 |
| U401,U402 | 2 | OPA333AIDBVR | C30878 | SOT-23-5 | 0.33 | 0.66 |
| U403,U404 | 2 | MCP6002T-I/SN | C7377 | SOIC-8 | 0.19 | 0.38 |
| U101 | 1 | USBLC6-2SC6 | C2687116 | SOT-23-6 | 0.03 | 0.03 |
| U102 | 1 | TP4056-42 | C16581 | ESOP-8 | 0.15 | 0.15 |
| U103,U104 | 2 | TLV75533PDBVR | C404027 | SOT-23-5 | 0.15 | 0.30 |
| D401,D402 | 2 | VEMD5010X01 | C3151612 | SMD-4P | 0.52 | 1.04 |
| D501 | 1 | CT-3030SUR660/850C-PT | C53191416 | SMD3030-4P | 0.11 | 0.11 |
| D502 | 1 | JNJ-L-3535AW30-80530-SL-J2-D3 **[VERIFY λ]** | C22447934 | SMD3535-3P | 0.78 | 0.78 |
| Q101,Q102 | 2 | AO3401A (P-ch) | — **[VERIFY]** | SOT-23 | 0.06 | 0.12 |
| Q501–503 | 3 | AO3400A | C20917 | SOT-23 | 0.05 | 0.15 |
| Q103,Q104,Q504–506 | 5 | 2N7002 | — **[VERIFY]** | SOT-23 | 0.02 | 0.10 |
| D101 | 1 | SS34 Schottky | — **[VERIFY]** | SMA | 0.04 | 0.04 |
| J101 | 1 | USB-C 16-pin receptacle | — **[VERIFY]** | SMD | 0.20 | 0.20 |
| J102 | 1 | JST-PH 2-pin | — | SMD | 0.08 | 0.08 |
| J401,J202 | 2 | JST-GH 15-way | — **[VERIFY]** | SMD | 0.42 | 0.84 |
| — | 1 | JST-GH 15-way silicone ribbon 100 mm | — | — | 1.40 | 1.40 |
| RT401 | 1 | NTC 10 kΩ B3950 | — | 0603 | 0.05 | 0.05 |
| R401 | 1 | 470 kΩ 1% | — | 0603 | 0.01 | 0.01 |
| R402 | 1 | 1.0 MΩ 1% | — | 0603 | 0.01 | 0.01 |
| R405–412 | 8 | 3.3 kΩ / 1 kΩ 1% | — | 0603 | 0.01 | 0.08 |
| R507–509 | 3 | 10 Ω 1% | — | 0805 | 0.01 | 0.03 |
| — | ~35 | assorted R (10k, 100k, 220R, 1k, 5.1k, 2.4k, 4.7k) | — | 0603/0402 | 0.01 | 0.35 |
| C401 | 1 | 10 pF C0G | — | 0402 | 0.01 | 0.01 |
| C402 | 1 | 4.7 pF C0G | — | 0402 | 0.01 | 0.01 |
| C405–410 | 6 | 1 nF / 10 nF C0G | — | 0402 | 0.01 | 0.06 |
| C109 | 1 | 100 µF X5R 6.3 V | — | 1206 | 0.10 | 0.10 |
| — | ~30 | assorted C (100n, 1µ, 10µ, 22µ) | — | 0402/0603/0805 | 0.02 | 0.60 |
| SW201 | 1 | Tactile switch | — | SMD | 0.05 | 0.05 |
| D201 | 1 | Green LED | — | 0603 | 0.02 | 0.02 |
| BT1 | 1 | LiPo 500 mAh **protected** | — | — | 5.00 | 5.00 |
| | | | | | **Total** | **~£19.0** |

Add PCB (~£28 for 5, ENIG + black mask, shipped) → **~£47 for the first board**, ~£66 including a
spare build set. Inside the £100 budget with room for a rev B.

**[VERIFY] before ordering:** the six lines marked above were not confirmed against live stock, and
D502's actual peak wavelength must be read off the manufacturer datasheet — the whole isosbestic
argument depends on it being 805–815 nm, not 830–840 nm. Re-run
`scratchpad/jlcverify.py "<part>"` to refresh.

---

## 4. Layout plan

### 4.1 Floorplan

```
 ◄──────────────────── 78 mm ────────────────────►
┌─────────────────────────────────────┬╌╌╌╌╌╌╌╌╌╌╌╌┐  ▲
│ ▓▓ANT▓▓                             ┊            │  │
│ ▓keep▓  U201 ESP32-S3-MINI-1        ┊  D402 PD_far│  │
│ ▓out ▓                              ┊      ▲     │  │
│                                     ┊   ═══╪═══  │  │ 30
│  J101   U101  U102   Q101  U103     ┊   slot+via │  │ mm
│  USB-C  ESD   chg    path  3V3_D    ┊      ▼     │  │
│                            U104     ┊  D501 D502 │  │
│  J102 LiPo    C104   R109  3V3_A    ┊  emitters  │  │
│                                     ┊  Q501-503  │  │
│         U301 ADS131M02      J202 ═══╪═══ J401    │  │
│         (analog corner)             ┊   ═══╪═══  │  │
│                                     ┊      ▼     │  │
│                                     ┊  D401 PD_near│ │
└─────────────────────────────────────┴╌╌╌╌╌╌╌╌╌╌╌╌┘  ▼
 ◄────────── main 46 mm ──────────►  break  ◄─26 mm─►
```

Head detail — emitter at origin, both detectors on the same axis:

```
        D402 PD_far   ●  ────── ρ₂ = 11.5 mm ──────┐
                                                    │
        ══════ slot 1.6 mm + via fence ═════        │
                                                    │
        D501 (660+850) ▣  D502 (810) ▣   ← emitter site (origin)
                                                    │
        ══════ slot 1.6 mm + via fence ═════        │
                                                    │
        D401 PD_near  ●  ─── ρ₁ = 6.5 mm ───────────┘
```

Emitter dies must be **optically co-located**: place D501 and D502 with their emitting apertures
within 2 mm of each other, and define the emitter origin as the centroid of the three dies. ρ₁ and
ρ₂ are measured from that centroid to each photodiode's active-area centre. Record the as-built
distances from the fabricated board — the μ_eff extraction uses them directly, so a 0.3 mm error
is a 6% error in Δρ.

### 4.2 Stackup and pour

2-layer, 1.6 mm. **F.Cu = signal + local pours; B.Cu = continuous ground pour.**

**Do not split the ground plane.** A split forces return currents around the gap and makes things
worse. Instead *partition by placement*: analog parts in one region, digital in another, with the
ADC straddling the boundary and its AGND/DGND pins tied at a single point under the package. Route
nothing across the analog region on B.Cu.

### 4.3 Routing order

1. `VLED` and its return — **0.5 mm minimum**, tightest possible loop from C109 through the LED,
   the FET and Rsense back to AGND. This loop carries the 30 mA pulse edges and is the dominant
   radiator on the board.
2. Photodiode cathode nodes — shortest possible, <5 mm, with a `TIA_BIAS`-driven guard ring and
   **no copper beneath on either layer** except that ring.
3. Matched ADC driver pairs — route as tightly coupled pairs, equal length within 2 mm.
4. `ADC_CLKIN` — 8.192 MHz, keep short, add the 100 Ω series at the source.
5. SPI, then everything else.

### 4.4 Keep-outs

- **ESP32 antenna: no copper on any layer**, 15 × 8 mm, module at the board edge with the antenna
  overhanging the outline. This is a hard requirement, not a guideline.
- No copper under photodiode packages except the guard ring.
- 2 mm keep-out around each routed slot.

### 4.5 Mounting

Main board: M2 at (3, 3) and (43, 27). Head: M2 at (3, 3) and (23, 17), 2.2 mm drill, 4.4 mm
keep-out. Origin at each board's lower-left after depanelisation.

---

## 5. Design rules

See [`fab.md`](fab.md) §"Design rules". Load `JLCPCB.kicad_dru` (symlinked here) and add the
VLED 0.5 mm minimum-width net class and the antenna keep-out.

---

## 6. Firmware and feature contract

### 6.1 ADC init

1. Assert `ANALOG_EN`, wait 5 ms for 3V3_A.
2. Start LEDC PWM on GPIO8 at 8.192 MHz, 50% duty (ADC CLKIN).
3. Pulse `/SYNC//RESET` low 10 µs, wait 1 ms.
4. Write `CLOCK`: both channels enabled, OSR = 256, power mode high-resolution.
5. Write `GAIN`: ch0 = 1, ch1 = 4.
6. Set the three `ISETn` PWM duty cycles for 20 mA nominal; leave all `ENn` deasserted.
7. Enable `/DRDY` interrupt on GPIO14, falling edge.

### 6.2 Frame loop (ISR-driven, no busy-wait)

```
on DRDY:
  read 2 × 24-bit words
  if sample_index in settled window: accumulate into phase_acc[phase]
  at phase end: advance phase, set EN lines for next phase
  at frame end (phase 3 done):
    for w in {660, 810, 850}:
        near[w] = phase_acc[w].near - phase_acc[DARK].near
        far[w]  = phase_acc[w].far  - phase_acc[DARK].far
    log raw dark level and raw lit DC per channel   ← REQUIRED, see §6.4
    push to 20 Hz IIR, decimate ×8 → 100 Hz output
```

### 6.3 Stream format

CSV over USB CDC at 100 Hz, one line per decimated frame:

```
t_us, near660, near810, near850, far660, far810, far850,
dark_near, dark_far, dc_near850, dc_far850, ntc_c, vbat_mv, flags
```

`flags` bit 0 = TIA headroom exceeded, bit 1 = dark level high (ambient), bit 2 = VBAT below
cutoff, bit 3 = frame overrun.

### 6.4 Quality gates (hardware-enabled, firmware-enforced)

- Reject any window where a channel's lit DC exceeds **80% of TIA headroom**. With Rf = 470 kΩ and
  a 0.30 V bias on a 3.3 V rail, total photocurrent (signal + ambient leakage) caps at ~6.3 µA.
  A fully exposed photodiode in a 500 lux room collects ~2.6 µA; a window seat with a −20 dB seal
  still delivers ~5 µA. If the TIA rails, dark subtraction still returns a *number* — clipping
  removes the cardiac AC while leaving the DC pedestal, so the capture looks like a poorly
  perfused finger rather than a broken measurement. **This is the highest-value gate on the board.**
- Reject if dark level exceeds 10% of headroom.
- Record the rejection reason. Silent rejection biases the dataset against bright-room and
  darker-skin captures.

### 6.5 Feature computation — and the bugs that must be fixed first

`src/pallor_hb/features.py` has **four dead or meaningless columns** on real waveforms. Verified
empirically at fs = 100 Hz, 72 bpm:

| Column | Measured behaviour | Cause |
|---|---|---|
| `systolic_amp` | **≡ 1.000000** for every input, across a 200× amplitude range *and* every pulse shape | `x = x / np.ptp(x)` forces ptp to 1, then `systolic_amp = max − min ≡ 1` |
| `dicrotic_ratio` | **≡ 1.00000** across all shapes tested | `tail = x[peak_idx:]` spans later beats whose peaks ≈ the global max, so it returns ptp/ptp and clips at 1. It never locates a notch |
| `rise_time` | 0.21 → 1.04 s tracking which beat happens to be tallest | `peak_idx / fs` is time from an arbitrary window start to the global max, not foot-to-peak |
| `pulse_area` | varies with shape (1.24 → 2.31) but is **amplitude-blind** and scales with window length | computed on the ptp-normalised signal |

The synthetic path hides all of this because `dataset.py` emits features directly rather than
waveforms — the bug only bites when real captures arrive, which is exactly what this board is for.
`metrics.json` currently assigns importance 0.060 / 0.029 / 0.028 / 0.019 to these four columns,
so today's feature-importance table attributes predictive power to columns that carry no signal.

**Required rewrite, before the first capture:**

1. Bandpass 0.5–8 Hz; detect beat feet as minima of the first derivative; segment beat by beat.
2. Per beat: `systolic_amp` = (peak − preceding foot) in **absolute units, divided by that
   channel's own DC**; `rise_time` = foot-to-peak in seconds; `pulse_area` normalised by **both**
   beat duration and systolic amplitude; `dicrotic_ratio` from the first zero-crossing of the
   second derivative after the systolic peak, returning **NaN when undetectable — do not clip to 1**.
3. Take the median across beats; add an inter-beat IQR column as a quality metric.
4. Unit tests asserting `rise_time` is invariant to window-start offset and `pulse_area` is
   invariant to window length. The current suite catches none of this.

**`perfusion_index` and `red_ir_ratio` also need per-beat definitions.** Both currently use the
peak-to-peak of the whole window, so on a real finger they are dominated by respiratory baseline
wander rather than the cardiac pulse. With true cardiac PI held at 1.00%, adding sinusoidal drift
at 0.25 Hz moves reported PI to 1.39% / 2.95% / 6.84% at 0.2% / 1% / 3% drift, and `red_ir_ratio`
from 0.800 to 0.971. Real reflectance PPG routinely shows 1–5% respiratory modulation — larger
than the cardiac AC itself. Define AC per beat (systolic peak − preceding foot), DC as a <0.3 Hz
low-pass at the same beat, take the median, and compute R beat-wise rather than as a ratio of two
window aggregates.

### 6.6 New columns from this board

| Column | Definition |
|---|---|
| `mueff_810` | from `ln(DC_far810/DC_near810)`, corrected for the `2·ln(ρ₁/ρ₂)` geometric term |
| `mueff_660`, `mueff_850` | same at the other two wavelengths, for comparison |
| `sd_ratio_810` | raw far/near DC ratio, kept unprocessed for audit |
| `beat_iqr` | inter-beat spread, quality metric |
| `head_temp_c` | for drift correction |

`mueff_810` is the concentration-sensitive channel. Everything else is context.

---

## 7. Verification performed

### 7.1 TIA stability and settling (ngspice)

Op-amp modelled as single-pole, Aol = 1e6, GBW = 350 kHz (OPA333 class); Cin = 50 pF
(VEMD5010X01 Cj ≈ 40 pF + 10 pF stray).

Peaking versus Cf — peaking is a proxy for phase margin:

| Rf | Cf | Peaking (dB) | |
|---|---|---|---|
| 470 kΩ | 1.0 pF | 11.14 | unstable |
| 470 kΩ | 2.2 pF | 7.24 | unstable |
| 470 kΩ | 4.7 pF | 2.88 | marginal |
| 470 kΩ | 6.8 pF | 0.99 | textbook optimum, ~65° PM |
| **470 kΩ** | **10 pF** | **0.00** | **chosen** |
| 1.0 MΩ | 3.3 pF | 0.00 | |
| **1.0 MΩ** | **4.7 pF** | **0.00** | **chosen** |

Step settling, 2 µA (near) / 0.2 µA (far):

| Config | Swing | t(0.1%) | t(0.01%) |
|---|---|---|---|
| 470 kΩ / 6.8 pF | 940 mV | 44.3 µs | 57.9 µs |
| **470 kΩ / 10 pF** | 940 mV | 36.2 µs | **42.7 µs** |
| 4.7 MΩ / 3.3 pF | 941 mV | 85.1 µs | 129.7 µs |
| 2.2 MΩ / 3.3 pF | 441 mV | 92.7 µs | 121.4 µs |
| **1.0 MΩ / 4.7 pF** | 200 mV | 63.4 µs | **82.8 µs** |

Both chosen configurations settle inside the 100 µs budget.

> **Deviation from house rules, flagged.** The LTspice MCP server could not run these: its working
> directory is `/`, so it fails to write artifacts to `/.ltspice-mcp` on a read-only filesystem.
> These results are from **ngspice** invoked directly. To restore the house workflow, set a
> writable working directory in `/ltspice-mcp.toml` (or `LTSPICE_MCP_CONFIG`) and re-run
> `scratchpad/tia2.cir`. The op-amp is a behavioural single-pole model, not the OPA333 vendor
> model — worth re-running with the real model before committing rev A.

### 7.2 Sourcing

Every major part checked against live LCSC stock on 2026-08-10 — see [`sourcing.md`](sourcing.md).
The headline result: **every integrated PPG AFE is unsourceable or unsolderable**, which is what
drove this design to a discrete front end. Six BOM lines remain **[VERIFY]**.

---

## 8. The honest experiment

The one original measurement that justifies the mechanical work.

**Question:** how does contact pressure affect PPG signal quality, and where is the optimum?

**Independent variable:** clip contact pressure, set by the M3 thumbscrew against the printed leaf
spring, calibrated beforehand by pressing the clip onto a kitchen scale and recording grams versus
turns. Five levels spanning ~5–45 kPa.

**Dependent variables:** perfusion index (per-beat definition, §6.5), beat-to-beat IQR, and far/near
DC ratio at 810 nm.

**Protocol:** single subject (self), 5 pressure levels × 6 repeats, randomised order, 60 s per
capture, 2 min rest between, room temperature and ambient light logged, same finger, same time of
day. Reference capture on the white PTFE target at the start and end of every session.

**Expected result:** perfusion index rises then falls, peaking somewhere in 15–25 kPa — low
pressure gives motion artefact and poor coupling, high pressure occludes arterial inflow. The
plot is PI versus pressure with error bars across repeats.

**Why it is worth doing:** it is a real, falsifiable measurement that only exists because you built
the mechanics, it directly justifies the clip design, and it needs no ethics approval or reference
blood draw. It is the plot that turns "I built a board" into "I measured something."

---

## 9. Known limitations, and what rev B fixes

1. **No absolute Hb.** μ_eff tracks c_Hb × blood-volume-fraction. This is a screening index.
   Say so plainly everywhere.
2. **Cohort variance is the real critical path, not the PCB.** A healthy student cohort spans
   ~12–17 g/dL with sex accounting for much of it — and `is_female` and `age` are already in the
   feature vector. With N ≈ 20 and a GBM, you will get MAE ≈ 1 g/dL and Bland–Altman limits near
   ±2 g/dL *reproducible from demographics alone with the optics disconnected*. Mitigation, all
   before any data collection: make the headline result an **ablation** (demographics-only baseline
   in the same table as the full model, plus a permutation test on the optical block), wire it into
   `train.py` so it cannot be skipped, and pre-register N and the primary endpoint in the repo.
3. **Bland–Altman independence.** `evaluate.py` treats every window as independent; many windows
   per subject will understate the limits of agreement. Aggregate to one prediction per
   subject-session before computing bias and SD, report the number of independent subjects, and
   print the 95% CI on the limits.
4. **Reference floor.** HemoCue capillary versus lab CBC has SD ≈ 0.5–0.8 g/dL. ±1.5 g/dL limits
   are the noise floor even for a perfect device.
5. **D502 wavelength unverified.** If its true peak is 830–840 nm rather than 805–815 nm, the
   extinction balance drifts and the isosbestic claim weakens. Verify on the datasheet and on
   arrival; if it fails, say so in the writeup rather than fudging it.
6. **Rev B candidates:** a fourth wavelength for a proper multi-λ fit; a third detector distance to
   over-determine μ_eff and get a residual as a quality metric; an ambient-light photodiode with no
   emitter for a true ambient reference channel; a proper optical bandpass filter over each PD.
