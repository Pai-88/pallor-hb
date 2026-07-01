"""Feature extraction from raw sensor signals.

The synthetic dataset in `dataset.py` emits features directly. Once real captures
land (roadmap W2/W4), raw PPG waveforms are turned into the same feature schema by
`ppg_features_from_waveform`, and conjunctiva images by `conjunctiva_color_features`.
Keeping the output schema identical means the model never has to know where the
features came from.
"""

from __future__ import annotations

import numpy as np

from .dataset import PPG_FEATURE_COLUMNS


def ppg_features_from_waveform(
    red: np.ndarray,
    ir: np.ndarray,
    fs: float,
    age: float,
    is_female: float,
) -> dict[str, float]:
    """Extract PPG morphology features from one red/IR window.

    This is a compact, dependency-light implementation intended for real captures.
    It is exercised by the unit tests on a clean synthetic sine-like pulse; on real
    signals it must be preceded by bandpass filtering and beat segmentation (W2/W5).

    Args:
        red, ir: raw reflectance PPG samples (same length).
        fs: sample rate (Hz).
        age, is_female: demographic covariates.
    """
    red = np.asarray(red, dtype=float)
    ir = np.asarray(ir, dtype=float)
    if red.size < int(fs) or red.size != ir.size:
        raise ValueError("need >= 1 s of equal-length red/ir samples")

    def ac_dc(x: np.ndarray) -> tuple[float, float]:
        dc = float(np.mean(x))
        ac = float(np.max(x) - np.min(x))
        return ac, dc

    ac_r, dc_r = ac_dc(red)
    ac_ir, dc_ir = ac_dc(ir)
    # Ratio-of-ratios, the classic pulse-oximetry feature; guard against div-by-zero.
    red_ir_ratio = ((ac_r / dc_r) / (ac_ir / dc_ir)) if dc_r and dc_ir and ac_ir else 0.0
    perfusion_index = (ac_ir / dc_ir * 100.0) if dc_ir else 0.0

    # Work on the IR channel (higher SNR) for morphology.
    x = ir - np.mean(ir)
    if np.ptp(x) > 0:
        x = x / np.ptp(x)
    peak_idx = int(np.argmax(x))
    systolic_amp = float(x[peak_idx] - np.min(x))
    rise_time = peak_idx / fs
    pulse_area = float(np.trapezoid(np.clip(x - np.min(x), 0, None)) / fs)

    # Dicrotic notch: crude estimate as the secondary peak after the systolic peak.
    tail = x[peak_idx:]
    dicrotic_ratio = float(np.max(tail[1:]) - np.min(tail)) / (systolic_amp + 1e-9) if tail.size > 2 else 0.0
    dicrotic_ratio = float(np.clip(dicrotic_ratio, 0.0, 1.0))

    # Heart rate from dominant spectral peak of the IR AC component.
    hr_bpm = _dominant_hr(ir, fs)

    return {
        "red_ir_ratio": red_ir_ratio,
        "perfusion_index": perfusion_index,
        "systolic_amp": systolic_amp,
        "dicrotic_ratio": dicrotic_ratio,
        "pulse_area": pulse_area,
        "rise_time": rise_time,
        "hr_bpm": hr_bpm,
        "age": float(age),
        "is_female": float(is_female),
    }


def _dominant_hr(x: np.ndarray, fs: float) -> float:
    """Heart rate (bpm) from the dominant frequency in the 0.7–3.5 Hz band."""
    x = np.asarray(x, dtype=float)
    x = x - np.mean(x)
    n = x.size
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    mag = np.abs(np.fft.rfft(x))
    band = (freqs >= 0.7) & (freqs <= 3.5)  # 42–210 bpm
    if not np.any(band):
        return 0.0
    f_peak = freqs[band][int(np.argmax(mag[band]))]
    return float(f_peak * 60.0)


def conjunctiva_color_features(rgb_patch: np.ndarray) -> dict[str, float]:
    """Colour features from a white-balanced conjunctiva ROI (H x W x 3, 0–1 floats).

    Pallor = reduced redness; these features feed the secondary imaging modality
    (roadmap W6). Requires colour-card white balancing upstream to be meaningful.
    """
    p = np.asarray(rgb_patch, dtype=float)
    if p.ndim != 3 or p.shape[-1] != 3:
        raise ValueError("expected an H x W x 3 RGB patch")
    r, g, b = p[..., 0].mean(), p[..., 1].mean(), p[..., 2].mean()
    total = r + g + b + 1e-9
    return {
        "mean_r": float(r),
        "mean_g": float(g),
        "mean_b": float(b),
        "redness_index": float((r - g) / total),        # higher = redder = likely higher Hb
        "r_over_g": float(r / (g + 1e-9)),
    }


__all__ = [
    "PPG_FEATURE_COLUMNS",
    "ppg_features_from_waveform",
    "conjunctiva_color_features",
]
