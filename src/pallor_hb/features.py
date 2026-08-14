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


ALPHA_ROI_THRESHOLD = 128
"""Alpha cutoff separating conjunctiva tissue from background.

CP-AnemiC ships each image as RGBA where the alpha channel is a hand-drawn
conjunctiva mask: only ~25 % of pixels are opaque tissue and the rest are pure
black. The mask is *soft* (anti-aliased, ~11 alpha levels), and boundary pixels
blend tissue colour with that black background, so a hard threshold is used
rather than alpha-weighting — partially transparent pixels are colour-corrupted
and must be excluded, not down-weighted.
"""


def load_conjunctiva_roi(source) -> np.ndarray:
    """Return an (N, 3) array of conjunctiva pixels in 0–1 RGB floats.

    Accepts an image path (RGBA with a mask, as CP-AnemiC ships) or a raw array.
    Only masked-in tissue pixels are returned; the caller sees a flat pixel list
    with no spatial layout, which is all the colour statistics need.

    Ignoring the mask is not a small error: averaging the full frame mixes in
    ~75 % black pixels and shifts mean RGB by >100/255, so the resulting
    "colour" feature mostly encodes how much of the frame was masked.
    """
    if isinstance(source, np.ndarray):
        a = source.astype(float)
        if a.max() > 1.0:  # accept 0–255 arrays too
            a = a / 255.0
        if a.ndim != 3 or a.shape[-1] not in (3, 4):
            raise ValueError("expected an H x W x 3 or H x W x 4 image array")
        if a.shape[-1] == 4:
            mask = a[..., 3] >= (ALPHA_ROI_THRESHOLD / 255.0)
            px = a[..., :3][mask]
        else:
            px = a.reshape(-1, 3)
    else:
        from PIL import Image  # optional dep; only needed for the imaging modality

        img = np.asarray(Image.open(source).convert("RGBA"), dtype=float) / 255.0
        mask = img[..., 3] >= (ALPHA_ROI_THRESHOLD / 255.0)
        px = img[..., :3][mask]

    if px.size == 0:
        raise ValueError("conjunctiva mask selected zero pixels")
    return px


def conjunctiva_color_features(
    source,
    age: float = float("nan"),
    is_female: float = float("nan"),
) -> dict[str, float]:
    """Colour features from a masked conjunctiva ROI.

    Pallor = reduced redness of the conjunctiva, so colour statistics over the
    tissue ROI carry the anemia signal. Emits the `CONJ_FEATURE_COLUMNS` schema
    so it drops straight into the same model/eval harness as the PPG modality.

    Percentiles are included alongside means because pallor changes the *shape*
    of the colour distribution (a partly-blanched conjunctiva has a pale tail
    long before its mean moves), and the mean alone throws that away.

    Note: absolute RGB depends on illumination. CP-AnemiC was captured under
    broadly controlled conditions, but no colour card was used, so the
    illumination-normalised ratios below are the more transferable features —
    which the external-validation step is designed to test.
    """
    from matplotlib.colors import rgb_to_hsv

    px = load_conjunctiva_roi(source)
    r, g, b = (float(px[:, i].mean()) for i in range(3))
    hsv = rgb_to_hsv(px)

    # Hue is circular: red tissue sits near BOTH 0.0 and 1.0, so a linear mean of
    # 0.98 and 0.02 returns 0.5 (cyan) — the opposite of the truth. Average the
    # unit vectors instead and convert the resultant angle back to [0, 1).
    ang = 2.0 * np.pi * hsv[:, 0]
    h_mean = float((np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) / (2.0 * np.pi)) % 1.0)
    # Hue concentration in [0, 1]: 1 = all pixels one hue, 0 = uniformly spread.
    # A blanched conjunctiva is less consistently red, so this is informative in
    # a way the circular mean alone is not.
    h_concentration = float(np.hypot(np.sin(ang).mean(), np.cos(ang).mean()))
    s_mean = float(hsv[:, 1].mean())
    # NOTE: HSV "value" is max(R,G,B), which for red tissue is always the red
    # channel — v_mean would duplicate r_mean exactly, so it is not emitted.

    # CIELAB a* is the perceptual red-green axis — the closest numerical analogue
    # to what a clinician judges when they call a conjunctiva "pale". Computed
    # via sRGB -> linear -> XYZ (D65) -> Lab.
    lab_l, lab_a, lab_b = _srgb_to_lab_mean(px)

    # Illumination-normalised redness: red's share of total intensity. Dividing
    # by the sum cancels a global brightness scale, so this survives exposure
    # differences that would swamp raw r_mean.
    total = r + g + b + 1e-9
    redness_index = r / total

    # Pale tail of the distribution: the 10th percentile of redness across
    # pixels, which moves earlier than the mean in partial blanching.
    px_total = px.sum(axis=1) + 1e-9
    redness_p10 = float(np.percentile(px[:, 0] / px_total, 10))

    return {
        "r_mean": r, "g_mean": g, "b_mean": b,
        "h_mean": h_mean, "h_concentration": h_concentration, "s_mean": s_mean,
        "lab_l": lab_l, "lab_a": lab_a, "lab_b": lab_b,
        "redness_index": float(redness_index),
        "redness_p10": redness_p10,
        "rg_ratio": float(r / (g + 1e-9)),
        "roi_px": float(px.shape[0]),
        "age": float(age),
        "is_female": float(is_female),
    }


def _srgb_to_lab_mean(px: np.ndarray) -> tuple[float, float, float]:
    """Mean CIELAB (L*, a*, b*) of an (N, 3) sRGB array in 0–1, under D65."""
    # sRGB -> linear RGB (undo the gamma transfer function).
    lin = np.where(px <= 0.04045, px / 12.92, ((px + 0.055) / 1.055) ** 2.4)
    # linear RGB -> XYZ (sRGB D65 matrix).
    m = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = lin @ m.T
    # Normalise by the D65 white point.
    white = np.array([0.95047, 1.00000, 1.08883])
    t = xyz / white
    d = 6.0 / 29.0
    f = np.where(t > d ** 3, np.cbrt(t), t / (3 * d ** 2) + 4.0 / 29.0)
    L = 116.0 * f[:, 1] - 16.0
    a = 500.0 * (f[:, 0] - f[:, 1])
    b = 200.0 * (f[:, 1] - f[:, 2])
    return float(L.mean()), float(a.mean()), float(b.mean())


__all__ = [
    "PPG_FEATURE_COLUMNS",
    "ppg_features_from_waveform",
    "conjunctiva_color_features",
]
