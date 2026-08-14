# Board Constraints — PallorHb PPG head (rev A)

## What this board is for

A reflectance PPG front end that produces **spatially-resolved** optical measurements at three
wavelengths, feeding `pallor_hb.features`. It is not a MAX30102 carrier: the whole point is that
the board measures something a stock pulse-oximetry module structurally cannot.

### The measurement, stated precisely

Modified Beer–Lambert for the pulsatile component gives, at wavelength λ,

    AC/DC |λ  ≈  ε_λ(S) · c_Hb · Δd · DPF_λ

Any **ratio of two AC/DC values divides out c_Hb and Δd**. That is why the classic ratio-of-ratios
R = (AC/DC)₆₆₀ / (AC/DC)_IR measures oxygen *saturation* and is deliberately blind to total
haemoglobin. Adding an isosbestic wavelength and ratioing it the same way does not fix this — it
just produces a second saturation estimator. **This board therefore does not rely on wavelength
ratios for its Hb signal.**

Instead it measures **DC attenuation versus source–detector separation** at a fixed wavelength:

    ln[ DC(ρ₂)/DC(ρ₁) ]  ≈  −μ_eff·(ρ₂−ρ₁) + 2·ln(ρ₁/ρ₂)
    μ_eff = sqrt( 3·μ_a·(μ_a + μ_s') )

μ_a at the isosbestic wavelength is proportional to **total haem** in the sampled volume,
independent of saturation. Worked number for finger tissue: μ_a(810) ≈ 0.025 mm⁻¹, μ_s' ≈ 1 mm⁻¹
→ μ_eff = 0.277 mm⁻¹. A 13→9 g/dL drop (μ_a −30%) gives μ_eff = 0.231 mm⁻¹; over Δρ = 5 mm the
far/near DC ratio changes by **~25%** — large and measurable.

It is also **melanin-robust to first order**: a fixed epidermal attenuation is a common
multiplicative factor on both detectors and cancels in the ratio. Absolute DC does not have this
property, which is why single-detector designs fail across skin tones.

**Honest limit, to be stated in every writeup:** μ_eff tracks c_Hb × blood-volume-fraction. This
yields a *screening index*, not absolute Hb. Calibration against a reference CBC is still required
and blood-volume-fraction remains an uncontrolled confound.

## Form factor

- One fabricated outline **78 × 30 mm**, 2-layer, snapped into two boards on a routed break line
  with three 2.2 mm mouse-bite tabs. A single design with break tabs is not charged as a panel.
- **Main board 46 × 30 mm** — MCU, USB, charger, regulators, ADC.
- **Optical head 26 × 20 mm** — photodiodes, TIAs, emitters, current sinks.
- Joined by a **15-way JST-GH** silicone ribbon, 100 mm (pinout in `design.md` §2.7).
- Head sits in a black-PETG finger clip; main board and LiPo sit outside the clip.

Rationale for the split: it puts the 2.4 GHz antenna, the SPI clock, the USB transceiver, the
charger's self-heating and the LiPo pouch physically outside the finger clip, and lets each TIA
sit ~3 mm from its photodiode.

## Optical geometry (drives everything else)

| Item | Value | Why |
|---|---|---|
| Emitter cluster | one site, 3 dies | Single site is what makes the two detectors comparable |
| PD_near centre distance ρ₁ | **6.5 mm** | Standard reflectance PPG separation; good perfusion index |
| PD_far centre distance ρ₂ | **11.5 mm** | Δρ = 5 mm gives ~25% ratio change over the Hb range |
| Optical barrier | interrupted annular routed slot, 1.6 mm wide | Blocks substrate/overmold light piping |
| Via fence | 0.3 mm vias @ 1.0 mm pitch either side of each slot | Blocks in-copper and in-FR4 paths |
| PD active area | 4.4 mm² (VEMD5010X01) | Far detector is photon-starved; area is free SNR |

**Why two detectors and one emitter, not one detector and two emitters:** the two detectors sample
the *same* LED pulse simultaneously (ADS131M02 has two simultaneously-sampling ADCs). LED radiant
output — which drifts with junction temperature, drive current and age — is therefore a **common
factor that cancels exactly** in the far/near ratio. The alternative (two emitters, one detector)
makes the measurement depend on the *ratio of two LEDs' outputs*, which is the least stable
quantity in the system. This is the single most important architectural decision on the board.

## Acquisition timing

- 4-phase frame: **660 / 810 / 850 / DARK**, frame rate **800 Hz**, 312.5 µs per phase.
- Each phase: LED on at the boundary → settle → convert only in the settled window.
- **Verified by simulation** (ngspice, single-pole 350 kHz GBW op-amp model), settling to 0.01%:
  near channel Rf = 470 k / Cf = 10 p → **42.7 µs**; far channel Rf = 1 M / Cf = 4.7 p → **82.8 µs**.
  Both fit inside 312.5 µs with >3× margin.
- Each lit phase is **dark-subtracted** against the adjacent DARK phase (correlated double
  sampling — also removes TIA offset and 1/f drift).
- Decimate ×8 to exactly **100 Hz per wavelength**, matching what the ML pipeline expects.

**Why 800 Hz and not simply 100 Hz:** sampling each wavelength directly at 100 Hz aliases 100 Hz
and 200 Hz mains flicker (UK 50 Hz → 100 Hz optical) straight onto DC, corrupting
`perfusion_index` and `red_ir_ratio` at source. The oversampled frame plus dark subtraction is the
fix, and it is why the ADC and the LED duty cycle are sized as they are.

## Power budget

| Rail | Source | Load |
|---|---|---|
| VBUS 5 V | USB-C | charger only |
| VBAT 3.0–4.2 V | 1S LiPo 500 mAh | — |
| VSYS | power-path (VBUS or VBAT) | VLED, regulators |
| 3V3_D | TLV75533 | ESP32-S3 |
| 3V3_A | TLV75533 (separate) | ADS131M02, OPA333 ×2, MCP6002 |

- LED peak drive 20 mA nominal / 40 mA hardware ceiling, duty **≤ 25%** (one die lit per phase,
  3 lit phases of 4) → average emitter current ≤ 15 mA.
- ESP32-S3 active with BLE off: ~40 mA. Analog section: ~6 mA.
- Expected runtime on 500 mAh: **~7 h** streaming.

## Noise-sensitive nets

`PD_NEAR_K`, `PD_FAR_K` (photodiode cathodes — highest impedance nodes on the board),
`TIA_NEAR_OUT`, `TIA_FAR_OUT`, `TIA_BIAS`, `AIN0P/N`, `AIN1P/N`, `VREF`.

Rules: no copper under the PD cathode node on either layer except its own guard ring; guard ring
driven to `TIA_BIAS`; keep each PD-to-TIA trace under 5 mm; never route SPI, CLKIN or any enable
line on the head under the analog section.

## Mechanical

- Contact pressure target **15–25 kPa**, set by a printed leaf spring plus an M3 thumbscrew stop.
  Below ~10 kPa motion artefact dominates; above ~40 kPa arterial flow is occluded and the AC
  component collapses.
- Clip material **black PETG**. ⚠️ Common black PLA is *not* opaque at 850–940 nm — many black
  pigments are carbon-black-free and pass NIR. This must be tested on a coupon before printing the
  clip (see `bringup.md` step 1).
- Mounting: 2 × M2 holes on the head, 2 × M2 on the main board, 2.2 mm drill, 4.4 mm keep-out.

## Hard requirements (violations block the build)

1. Emitter dies, current sinks, enable lines and frame phases must be **one consistent list**.
   Rev A: 3 dies, 3 sinks, 3 enables, 4 phases. Do not populate a second emitter site.
2. Both ADC input arms must be **impedance-matched** (same series R, same C to AGND). An
   unmatched pair collapses cable CMRR to ~0.5 dB.
3. Every current sink needs a **gate pulldown and series gate resistor**; VLED must be gated off
   with the analog rail so emitters cannot be live while the control loop is unpowered.
4. Raw dark-phase level and raw lit DC must be **logged per channel**, and any window where a
   channel exceeds 80% of TIA headroom must be hard-rejected with a recorded reason.
5. `src/pallor_hb/features.py` must be fixed (see `design.md` §6) **before** any real capture.
   Four of the nine feature columns are currently dead or meaningless on real waveforms.
