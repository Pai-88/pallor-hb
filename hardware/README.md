# Hardware — PPG front end

The primary modality is a reflectance PPG at the fingertip. The design lives in
[`ppg-board/`](ppg-board/):

| File | Contents |
|---|---|
| [`constraints.md`](ppg-board/constraints.md) | The measurement physics and the hard requirements. **Read first.** |
| [`design.md`](ppg-board/design.md) | Architecture, net-by-net schematic, BOM, layout plan, firmware contract |
| [`fab.md`](ppg-board/fab.md) | JLCPCB order parameters and design rules |
| [`sourcing.md`](ppg-board/sourcing.md) | Live LCSC stock/price checks and the decisions they forced |
| [`bringup.md`](ppg-board/bringup.md) | Staged bring-up with numeric pass gates |

## Why this is not a MAX30102 board

The original plan here was "ESP32 + MAX30102 breakout". Two things changed it.

**Sourcing.** Every integrated PPG AFE is unusable: the MAX30102 has 6 units in stock at $11.61,
the MAX86141 is a wafer-level package that cannot be hand-soldered, the AFE4404 has 1 unit. A
discrete front end turned out to be both cheaper and abundantly stocked. Details in `sourcing.md`.

**Physics.** More importantly, a two-wavelength AC/DC ratio *cannot* measure total haemoglobin.
Modified Beer–Lambert gives AC/DC|λ ≈ ε_λ(S)·c_Hb·Δd·DPF_λ, so any ratio of two AC/DC values
divides out c_Hb by construction — that is precisely why the ratio-of-ratios measures oxygen
saturation. Adding an isosbestic wavelength and ratioing it the same way just produces a second
saturation estimator.

This board instead measures **DC attenuation versus source–detector distance** at a fixed
wavelength, which yields μ_eff and is concentration-sensitive rather than concentration-cancelling.
Two photodiodes at 6.5 mm and 11.5 mm read the same LED pulse simultaneously, so LED drift cancels
in the ratio. See `constraints.md` for the derivation and the honest limits.

## Capture plan (roadmap W4–W5)

1. Stream 3 wavelengths × 2 detectors at 100 Hz over USB CDC (`design.md` §6.3).
2. Per-beat feature extraction — **note that `src/pallor_hb/features.py` must be rewritten first**;
   four of the nine feature columns are currently dead on real waveforms (`design.md` §6.5).
3. Quality gating on TIA headroom and dark level, with recorded rejection reasons.

## Safety / scope

Reflectance PPG at the fingertip, battery powered, no mains connection, no electrical stimulation.
LED drive is capped at 30 mA in hardware and 20 mA nominal in firmware, at ≤25% duty.

This is a **research prototype, not a medical device**, and produces a screening index rather than
an absolute haemoglobin value. It is not for clinical use.
