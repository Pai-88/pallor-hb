# Hardware — PPG front-end

The primary modality is a low-cost reflectance PPG at the fingertip. This reuses the analog-front-end
and ESP32 workflow from my EMG project — same toolchain, new sensor.

## Bill of materials (target < $20)

| Part | Purpose | Notes |
|------|---------|-------|
| ESP32 (SuperMini / DevKit) | MCU + BLE/serial streaming | already in my parts bin |
| MAX30102 breakout | red + IR reflectance PPG | I2C; integrated LEDs + photodiode |
| Opaque finger clip / shroud | block ambient light | 3D-printed; critical for SNR |
| Colour reference card | white balance for conjunctiva imaging | secondary modality only |

An AFE such as the MAX30102 handles LED drive and sampling internally, so the biggest hardware task is
**mechanical**: a light-tight finger interface with consistent contact pressure. Ambient light and
motion are the dominant noise sources.

## Capture plan (roadmap W4–W5)

1. Stream red + IR at a fixed rate (e.g. 100 Hz) over serial/BLE; log with timestamps.
2. Bandpass filter (~0.5–5 Hz), segment beats, reject windows failing a perfusion-index / motion QC gate.
3. Extract the feature schema in `pallor_hb.features.ppg_features_from_waveform` — identical to what the
   model already consumes, so hardware captures drop straight into the trained pipeline.

## Safety / scope

Reflectance PPG at the fingertip is low-risk, but this is a **research prototype, not a medical
device**. No electrical connection to the body beyond the standard sensor breakout; no mains-adjacent
circuitry. If an ECG modality is ever added, proper isolation would be mandatory — out of scope here.
