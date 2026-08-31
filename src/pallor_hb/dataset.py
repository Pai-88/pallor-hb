"""Dataset loading and synthetic data generation.

`load_cp_anemic` loads the real CP-AnemiC conjunctiva dataset (the data behind the
paper), including its duplicate handling; `make_synthetic_ppg` produces a
physiologically-motivated synthetic PPG dataset used by the unit tests and the
legacy CLI demo.

No patient data is ever committed to this repo; see data/README.md.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# WHO anemia threshold for children 6-59 months (CP-AnemiC's cohort), g/dL.
# Kept here so the loader, the labels, and the clinical evaluation all agree.
WHO_ANEMIA_HB_THRESHOLD = 11.0

# Colour features produced for the conjunctiva imaging modality. The real
# extractor (`features.conjunctiva_color_features`) must emit exactly these keys,
# so the model never has to know whether features came from PPG or an image.
CONJ_FEATURE_COLUMNS = [
    "r_mean", "g_mean", "b_mean",   # mean RGB over the conjunctiva ROI
    "h_mean",                       # circular mean hue (linear mean is invalid — hue wraps)
    "h_concentration",              # hue consistency; blanching spreads the hue distribution
    "s_mean",                       # mean saturation ("value" is dropped: == r_mean here)
    "lab_l", "lab_a", "lab_b",      # CIELAB — a* is the perceptual red-green (pallor) axis
    "redness_index",                # r / (r+g+b): illumination-normalised redness
    "redness_p10",                  # 10th-percentile redness — the pale tail
    "rg_ratio",                     # red/green ratio
    "age",                          # demographic covariate (months, per CP-AnemiC)
    "is_female",                    # demographic covariate (0/1)
]

# Extracted but deliberately NOT modelled. `roi_px` is the size of the
# hand-drawn mask, i.e. annotator behaviour rather than physiology; if mask size
# happened to correlate with site or severity the model would learn the
# annotator, not the patient. Kept for quality control only.
CONJ_QC_COLUMNS = ["roi_px"]

# Demographics-only feature set. Age and sex alone predict childhood anemia
# reasonably well, so any image model must be shown to beat this — otherwise the
# "image" result is really a demographics result wearing a camera.
DEMOGRAPHIC_COLUMNS = ["age", "is_female"]


# Feature columns produced for the PPG modality. Kept in one place so the
# synthetic generator, real loaders, and the model all agree on the schema.
PPG_FEATURE_COLUMNS = [
    "red_ir_ratio",       # ratio of red/IR AC-DC (classic pulse-oximetry style feature)
    "perfusion_index",    # AC/DC amplitude, a signal-quality + physiology proxy
    "systolic_amp",       # normalized systolic peak amplitude
    "dicrotic_ratio",     # dicrotic notch height / systolic height (vascular tone)
    "pulse_area",         # area under one normalized pulse
    "rise_time",          # foot-to-peak time (s)
    "hr_bpm",             # heart rate
    "age",                # demographic covariate
    "is_female",          # demographic covariate (0/1)
]


@dataclass
class Dataset:
    """A simple (features, target, groups) bundle."""

    X: pd.DataFrame
    y: np.ndarray          # reference hemoglobin, g/dL
    groups: np.ndarray     # subject id, for leakage-free CV
    meta: pd.DataFrame | None = None   # per-row provenance (site, image id, QC)

    def __len__(self) -> int:
        return len(self.y)

    @property
    def anemic(self) -> np.ndarray:
        """Binary WHO anemia label (1 = Hb below threshold)."""
        return (self.y < WHO_ANEMIA_HB_THRESHOLD).astype(int)


def make_synthetic_ppg(n: int = 2000, seed: int = 0, n_subjects: int | None = None) -> Dataset:
    """Generate a synthetic (PPG-feature, Hb) dataset.

    The generative model is deliberately *simple but not linear*: hemoglobin is
    driven by a few features through monotone-ish relationships plus interaction
    and noise, so a linear model underfits and a gradient-boosted model has
    something real to learn. This is a stand-in for real data, NOT a claim about
    true PPG physiology.

    Args:
        n: number of samples.
        seed: RNG seed.
        n_subjects: number of distinct subjects (for group-aware CV). Defaults to n//4.
    """
    rng = np.random.default_rng(seed)
    if n_subjects is None:
        n_subjects = max(2, n // 4)

    groups = rng.integers(0, n_subjects, size=n)
    # Per-subject random offset so repeated samples from one subject correlate.
    subject_offset = rng.normal(0, 0.6, size=n_subjects)[groups]

    age = rng.uniform(5, 80, size=n)
    is_female = rng.integers(0, 2, size=n).astype(float)

    # Latent physiology.
    perfusion_index = np.clip(rng.gamma(2.0, 0.9, size=n), 0.05, 8.0)
    hr_bpm = np.clip(rng.normal(78, 14, size=n), 45, 150)
    red_ir_ratio = np.clip(rng.normal(0.9, 0.15, size=n), 0.4, 1.6)
    dicrotic_ratio = np.clip(rng.normal(0.35, 0.1, size=n), 0.05, 0.8)
    rise_time = np.clip(rng.normal(0.16, 0.03, size=n), 0.08, 0.3)
    systolic_amp = np.clip(rng.normal(1.0, 0.12, size=n), 0.5, 1.6)
    pulse_area = np.clip(systolic_amp * (0.55 + 0.4 * dicrotic_ratio)
                         + rng.normal(0, 0.05, size=n), 0.2, 1.6)

    # Hemoglobin as a nonlinear function of features + demographics + subject effect.
    hb = (
        13.5
        - 3.2 * (red_ir_ratio - 0.9)          # higher red/IR ratio -> lower Hb
        + 0.9 * np.log(perfusion_index)        # better perfusion -> slightly higher signal Hb
        - 1.1 * is_female                       # sex difference in reference ranges
        - 0.015 * (age - 40)                    # mild age trend
        + 2.0 * (dicrotic_ratio - 0.35)         # vascular-tone interaction
        - 1.5 * (systolic_amp - 1.0) * red_ir_ratio  # interaction term
        + subject_offset
        + rng.normal(0, 0.7, size=n)            # irreducible noise (~0.7 g/dL)
    )
    hb = np.clip(hb, 4.0, 19.0)

    X = pd.DataFrame(
        {
            "red_ir_ratio": red_ir_ratio,
            "perfusion_index": perfusion_index,
            "systolic_amp": systolic_amp,
            "dicrotic_ratio": dicrotic_ratio,
            "pulse_area": pulse_area,
            "rise_time": rise_time,
            "hr_bpm": hr_bpm,
            "age": age,
            "is_female": is_female,
        },
        columns=PPG_FEATURE_COLUMNS,
    )
    return Dataset(X=X, y=hb.astype(float), groups=groups)


# --------------------------------------------------------------------------- #
# Conjunctiva imaging modality — real public data (CP-AnemiC)
# --------------------------------------------------------------------------- #

# Flexible column-name matching: Mendeley/Excel exports vary in casing and
# wording, so we match on substrings rather than hard-coding exact headers.
_COL_ALIASES = {
    "hb":     ["hb", "hgb", "haemoglobin", "hemoglobin"],
    "age":    ["age"],
    "sex":    ["sex", "gender"],
    "site":   ["site", "hospital", "facility", "centre", "center", "location"],
    "id":     ["id", "number", "no", "code", "subject", "patient"],
    "image":  ["image", "file", "filename", "img", "photo"],
}


def _match_column(columns: list[str], key: str) -> str | None:
    """Find the column matching `key`, preferring whole-word matches.

    Two passes, because naive substring matching is actively dangerous here:
    "IMAGE_ID" contains the substring "age", so a substring-first search binds
    the age covariate to the identifier column and everything downstream is
    silently wrong. Tokenising on non-alphanumerics and requiring an exact token
    match first avoids that; substring is kept only as a fallback for headers
    like "Hb(g/dL)" where the token is fused to units.
    """
    tokens = {c: set(re.split(r"[^a-z0-9]+", c.strip().lower())) for c in columns}
    for alias in _COL_ALIASES[key]:
        for col in columns:
            if alias in tokens[col]:
                return col
    for alias in _COL_ALIASES[key]:
        for col in columns:
            if alias in col.strip().lower():
                return col
    return None


def _find_metadata_file(root: Path) -> Path:
    """Locate the CP-AnemiC metadata spreadsheet under `root`."""
    for pattern in ("*.csv", "*.xlsx", "*.xls"):
        hits = sorted(root.rglob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(
        f"No .csv/.xlsx/.xls metadata found under {root}. "
        "Download CP-AnemiC from https://data.mendeley.com/datasets/m53vz6b7fx/1 "
        "and unzip it into this folder."
    )


def _sex_to_female(value) -> float:
    """Map a free-text sex/gender cell to is_female in {0.0, 1.0, nan}."""
    s = str(value).strip().lower()
    if s in {"f", "female", "girl", "1"}:
        return 1.0
    if s in {"m", "male", "boy", "0"}:
        return 0.0
    return np.nan


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Mean-absolute pixel difference (0-255 scale) below which two ROI thumbnails are
# treated as the same photograph. In CP-AnemiC the merged pairs all lie below
# ~2.1 and the closest genuinely distinct pair sits at ~4.1, so any threshold in
# that gap yields the same 479 groups; outside it the count drifts only slightly
# (483 at 1.0, 476 at 5.0). 3.0 sits inside the gap.
PERCEPTUAL_DUP_MAD = 3.0

# Pass 3: shifted/re-cropped copies of one photograph defeat BOTH passes above —
# different bytes (new hash) and a different hand-drawn mask (new bounding box,
# so the bbox-normalised thumbnail mismatches). They are caught by aligning
# full-resolution canvases under small integer translations and comparing RGB
# inside the joint mask. Aligned mean-abs-diff: same-capture pairs sit below
# ~2.7 (flat compression-noise residual); visually distinct repeat captures
# start at ~3.1 (structured residual). 3.0 sits in that measured gap.
ALIGNED_DUP_DIFF = 3.0
_ALIGN_MAX_SHIFT = 30          # +/- px translation searched
_ALIGN_MIN_OVERLAP = 0.60      # joint mask must cover >=60% of the smaller ROI
_ALIGN_THUMB_CUTOFF = 20.0     # candidate prefilter A: generous thumbnail MAD
_ALIGN_HIST_CUTOFF = 0.10      # candidate prefilter B: ROI colour-histogram L1
_ALIGN_CACHE_NAME = "pass3_alignment_cache.json"


def _roi_thumbnail(path: Path, size: int = 32) -> np.ndarray:
    """Downscaled RGB thumbnail of the masked conjunctiva ROI, as a flat vector.

    Cropping to the mask bounding box before resizing makes the comparison
    invariant to surrounding padding, so the same photograph saved with a
    different canvas or PNG encoder still matches.
    """
    from PIL import Image

    a = np.asarray(Image.open(path).convert("RGBA"), dtype=float)
    m = a[..., 3] >= 128
    if not m.any():
        return np.zeros(size * size * 3)
    r = np.where(m.any(axis=1))[0]
    c = np.where(m.any(axis=0))[0]
    crop = a[r.min(): r.max() + 1, c.min(): c.max() + 1, :3].astype(np.uint8)
    thumb = Image.fromarray(crop).resize((size, size))
    return np.asarray(thumb, dtype=float).reshape(-1)


def _perceptual_groups(paths: list[Path], threshold: float = PERCEPTUAL_DUP_MAD) -> list[int]:
    """Assign a group id per path, merging images that are the same photograph.

    Byte-level hashing misses re-encoded copies: CP-AnemiC contains images with
    distinct SHA-256 that are pixel-identical once the ROI is extracted, carrying
    conflicting Hb values and different attributed sites. Those must be collapsed
    or they leak across folds exactly like exact duplicates.

    Distances are computed row-by-row rather than as one N x N tensor, which
    would need multiple GB at this feature width.
    """
    thumbs = np.stack([_roi_thumbnail(p) for p in paths])
    n = len(paths)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(n - 1):
        mad = np.abs(thumbs[i + 1:] - thumbs[i]).mean(axis=1)
        for off in np.where(mad < threshold)[0]:
            union(i, i + 1 + int(off))
    return [find(i) for i in range(n)]


def _canvas_and_mask(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Full-resolution RGB canvas and boolean conjunctiva mask."""
    from PIL import Image

    a = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)
    return a[..., :3], a[..., 3] >= 128


def _aligned_best_diff(A: np.ndarray, ma: np.ndarray,
                       B: np.ndarray, mb: np.ndarray,
                       max_shift: int = _ALIGN_MAX_SHIFT) -> float:
    """Smallest masked mean-abs RGB difference over integer translations.

    Coarse stride-3 search over +/-max_shift, then a +/-2 refinement around the
    best coarse shift. Only the joint mask is compared, and a candidate shift
    counts only if that joint mask covers most of the smaller ROI — otherwise a
    sliver of overlap could match by luck.
    """
    smaller_roi = min(ma.sum(), mb.sum())

    def diff_at(dy: int, dx: int) -> float:
        ay0, by0 = max(0, dy), max(0, -dy)
        ax0, bx0 = max(0, dx), max(0, -dx)
        h = min(A.shape[0] - ay0, B.shape[0] - by0)
        w = min(A.shape[1] - ax0, B.shape[1] - bx0)
        if h < 20 or w < 20:
            return np.inf
        mm = ma[ay0:ay0 + h, ax0:ax0 + w] & mb[by0:by0 + h, bx0:bx0 + w]
        if mm.sum() < _ALIGN_MIN_OVERLAP * smaller_roi:
            return np.inf
        return float(np.abs(A[ay0:ay0 + h, ax0:ax0 + w][mm]
                            - B[by0:by0 + h, bx0:bx0 + w][mm]).mean())

    coarse = min((diff_at(dy, dx), dy, dx)
                 for dy in range(-max_shift, max_shift + 1, 3)
                 for dx in range(-max_shift, max_shift + 1, 3))
    fine = min((diff_at(dy, dx), dy, dx)
               for dy in range(coarse[1] - 2, coarse[1] + 3)
               for dx in range(coarse[2] - 2, coarse[2] + 3))
    return min(coarse[0], fine[0])


def _alignment_pair_distances(paths: list[Path], shas: list[str],
                              cache_dir: Path, verbose: bool = True) -> list[tuple[int, int, float]]:
    """Aligned distances for every candidate pair among `paths`, disk-cached.

    Candidates come from the union of two independent prefilters — a generous
    thumbnail MAD and a translation-invariant ROI colour histogram — so pairs
    whose masks differ (which defeats the thumbnail alone) are still examined.
    The verified distances are cached next to the data, keyed by the content
    hashes and the search parameters, so re-loads and threshold sweeps are free.
    """
    import hashlib as _hl
    import json

    key = _hl.md5(("|".join(sorted(shas))
                   + f"|{_ALIGN_MAX_SHIFT}|{_ALIGN_MIN_OVERLAP}"
                   + f"|{_ALIGN_THUMB_CUTOFF}|{_ALIGN_HIST_CUTOFF}").encode()).hexdigest()
    cache_path = cache_dir / _ALIGN_CACHE_NAME
    if cache_path.exists():
        try:
            blob = json.loads(cache_path.read_text())
            if blob.get("key") == key:
                sha_to_idx = {s: i for i, s in enumerate(shas)}
                return [(sha_to_idx[a], sha_to_idx[b], d)
                        for a, b, d in blob["pairs"]
                        if a in sha_to_idx and b in sha_to_idx]
        except (json.JSONDecodeError, KeyError):
            pass  # stale or corrupt cache: recompute below

    n = len(paths)
    thumbs = np.stack([_roi_thumbnail(p) for p in paths])
    canv, masks, hists = [], [], []
    for p in paths:
        rgb, m = _canvas_and_mask(p)
        canv.append(rgb)
        masks.append(m)
        h = np.concatenate([np.histogram(rgb[..., c][m], bins=32,
                                         range=(0, 256))[0] for c in range(3)]).astype(float)
        hists.append(h / h.sum())
    hists = np.stack(hists)

    cands: list[tuple[int, int]] = []
    for i in range(n - 1):
        tm = np.abs(thumbs[i + 1:] - thumbs[i]).mean(axis=1)
        hd = np.abs(hists[i + 1:] - hists[i]).sum(axis=1)
        cands += [(i, i + 1 + int(off))
                  for off in np.where((tm < _ALIGN_THUMB_CUTOFF)
                                      | (hd < _ALIGN_HIST_CUTOFF))[0]]
    if verbose:
        print(f"  alignment pass: verifying {len(cands)} candidate pairs "
              f"(one-off; cached afterwards)")
    pairs = [(i, j, _aligned_best_diff(canv[i], masks[i], canv[j], masks[j]))
             for i, j in cands]

    cache_path.write_text(json.dumps(
        {"key": key, "pairs": [[shas[i], shas[j], round(d, 4)]
                               for i, j, d in pairs if np.isfinite(d)]}))
    return [(i, j, d) for i, j, d in pairs if np.isfinite(d)]


def _alignment_groups(paths: list[Path], shas: list[str], cache_dir: Path,
                      threshold: float = ALIGNED_DUP_DIFF,
                      verbose: bool = True) -> list[int]:
    """Group ids merging shifted/re-cropped copies of one photograph."""
    parent = list(range(len(paths)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i, j, d in _alignment_pair_distances(paths, shas, cache_dir, verbose=verbose):
        if d < threshold:
            union(i, j)
    return [find(i) for i in range(len(paths))]


def load_cp_anemic(
    root: str | Path,
    dedup: str = "hash",
    label_agg: str = "median",
    verbose: bool = True,
    perceptual_threshold: float = PERCEPTUAL_DUP_MAD,
    aligned_threshold: float = ALIGNED_DUP_DIFF,
) -> Dataset:
    """Load the CP-AnemiC conjunctiva dataset into the standard Dataset schema.

    CP-AnemiC ships 710 metadata rows but only 383 distinct photographs
    (498 byte-distinct files; 479 after merging re-encoded copies; 383 after
    merging shifted/re-cropped copies). 116 final-grain groups carry
    *different* Hb values on the same photograph (90 at the hash grain; one
    group spans 3.3–10.4 g/dL), and 125 groups are attributed to more than one
    hospital. Any random split therefore places the same photograph on both
    sides — and cross-site copies defeat site-grouped splits too — so accuracy
    measured naively is substantially memorisation.

    This loader makes that explicit rather than hiding it:

    - ``dedup="none"``    keep all 710 rows (reproduces the optimistic, leaky setup)
    - ``dedup="hash"``    one row per byte-distinct image, Hb aggregated by `label_agg`
    - ``dedup="thumbnail"`` additionally merge re-encoded copies below
      ``PERCEPTUAL_DUP_MAD`` (n=479)
    - ``dedup="perceptual"`` additionally merge shifted/re-cropped copies of one
      photograph below ``ALIGNED_DUP_DIFF`` — the headline setting (n=383)
    - ``dedup="singles"`` keep only images whose byte hash appears exactly once;
      note a handful of re-encoded and shifted copies survive at this grain

    Groups are the collection **site** (hospital), so `GroupKFold` additionally
    tests generalisation across cameras, operators and populations. Deduplication
    and grouping close two different leaks; both are needed.

    Args:
        root: folder containing the unzipped CP-AnemiC images + metadata file.
        dedup: "none" | "hash" | "thumbnail" | "perceptual" | "singles" (see above).
        label_agg: how to reconcile conflicting Hb within a duplicate group
            when ``dedup="hash"`` — "median" (robust) or "first".
        verbose: print a short data-integrity summary.

    Returns:
        Dataset with X (CONJ_FEATURE_COLUMNS), y (Hb g/dL), groups (site),
        and meta (image id, site, region, severity, sha, QC columns).
    """
    from .features import conjunctiva_color_features  # local import avoids cycle

    # Validate arguments before touching the filesystem: hashing several hundred
    # images and only then rejecting a misspelled mode wastes a minute and buries
    # the real error under an unrelated one.
    if dedup not in {"none", "hash", "thumbnail", "perceptual", "singles"}:
        raise ValueError(
            f"dedup must be 'none', 'hash', 'thumbnail', 'perceptual' or 'singles'; "
            f"got {dedup!r}"
        )
    if label_agg not in {"median", "first"}:
        raise ValueError(f"label_agg must be 'median' or 'first'; got {label_agg!r}")

    root = Path(root).expanduser()
    meta_path = _find_metadata_file(root)
    meta = (pd.read_csv(meta_path) if meta_path.suffix.lower() == ".csv"
            else pd.read_excel(meta_path))

    cols = list(meta.columns)
    hb_col = _match_column(cols, "hb")
    if hb_col is None:
        raise ValueError(f"Could not find an Hb column in {meta_path.name}: {cols}")
    age_col = _match_column(cols, "age")
    sex_col = _match_column(cols, "sex")
    site_col = _match_column(cols, "site")
    id_col = _match_column(cols, "id")
    img_col = _match_column(cols, "image")

    # Index images on disk by lowercased stem so rows resolve to files whether
    # the spreadsheet stores a filename or a bare id.
    img_paths = [p for p in root.rglob("*")
                 if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}]
    by_stem = {p.stem.lower(): p for p in img_paths}

    # --- resolve rows to files, and hash file contents to detect duplicates ---
    recs, unmatched = [], 0
    hash_cache: dict[Path, str] = {}
    for _, row in meta.iterrows():
        key = None
        if img_col is not None and pd.notna(row[img_col]):
            key = Path(str(row[img_col])).stem.lower()
        elif id_col is not None and pd.notna(row[id_col]):
            key = re.sub(r"\.0$", "", str(row[id_col]).strip().lower())
        img = by_stem.get(key) if key is not None else None
        if img is None or pd.isna(row[hb_col]):
            unmatched += 1
            continue
        if img not in hash_cache:
            hash_cache[img] = _sha256(img)
        recs.append({
            "path": img,
            "sha": hash_cache[img],
            "image_id": str(row[img_col]) if img_col else key,
            "hb": float(row[hb_col]),
            "age": float(row[age_col]) if age_col and pd.notna(row[age_col]) else np.nan,
            "is_female": _sex_to_female(row[sex_col]) if sex_col else np.nan,
            "site": str(row[site_col]).strip() if site_col and pd.notna(row[site_col]) else "unknown",
        })
    if not recs:
        raise RuntimeError(
            f"Matched 0 images to metadata rows in {root}. "
            "Check that images and the spreadsheet share ids/filenames."
        )
    rec = pd.DataFrame(recs)

    # --- data-integrity accounting, reported before any modelling happens -----
    grp = rec.groupby("sha")
    n_rows, n_unique = len(rec), rec.sha.nunique()
    conflict = int((grp.hb.nunique() > 1).sum())
    if verbose:
        print(f"CP-AnemiC: {n_rows} metadata rows -> {n_unique} distinct images "
              f"({n_rows - n_unique} redundant); {conflict} duplicate groups carry "
              f"conflicting Hb")
        if unmatched:
            print(f"  dropped {unmatched} rows with no image or no Hb")

    # --- deduplication strategy ----------------------------------------------
    if dedup == "none":
        keep = rec
    elif dedup == "singles":
        counts = rec.sha.map(rec.sha.value_counts())
        keep = rec[counts == 1].copy()
    elif dedup == "hash":
        agg_hb = grp.hb.median() if label_agg == "median" else grp.hb.first()
        keep = rec.drop_duplicates("sha").copy()
        keep["hb"] = keep.sha.map(agg_hb)
    elif dedup in {"thumbnail", "perceptual"}:
        # Pass 2: collapse exact duplicates first (cheap), then merge re-encoded
        # copies whose ROI thumbnails match (moderate cost).
        agg_hb = grp.hb.median() if label_agg == "median" else grp.hb.first()
        keep = rec.drop_duplicates("sha").copy()
        keep["hb"] = keep.sha.map(agg_hb)
        keep = keep.reset_index(drop=True)
        keep["pgroup"] = _perceptual_groups(list(keep.path), threshold=perceptual_threshold)
        pg = keep.groupby("pgroup")
        merged = int((pg.size() > 1).sum())
        agg_p = pg.hb.median() if label_agg == "median" else pg.hb.first()
        keep = keep.drop_duplicates("pgroup").copy()
        keep["hb"] = keep.pgroup.map(agg_p)
        if verbose and merged:
            print(f"  thumbnail pass: merged {merged} groups of re-encoded copies "
                  f"that byte-hashing missed")
        if dedup == "perceptual":
            # Pass 3: merge shifted/re-cropped copies of one photograph, which
            # carry both a new hash AND a new mask (so passes 1-2 miss them).
            keep = keep.reset_index(drop=True)
            keep["agroup"] = _alignment_groups(
                list(keep.path), list(keep.sha), cache_dir=meta_path.parent,
                threshold=aligned_threshold, verbose=verbose)
            ag = keep.groupby("agroup")
            merged_a = int((ag.size() > 1).sum())
            agg_a = ag.hb.median() if label_agg == "median" else ag.hb.first()
            keep = keep.drop_duplicates("agroup").copy()
            keep["hb"] = keep.agroup.map(agg_a)
            if verbose and merged_a:
                print(f"  alignment pass: merged {merged_a} groups of shifted/"
                      f"re-cropped copies that both earlier passes missed")
    else:  # pragma: no cover - unreachable; dedup is validated on entry
        raise AssertionError(dedup)
    keep = keep.reset_index(drop=True)
    if verbose:
        lab = (keep.hb < WHO_ANEMIA_HB_THRESHOLD).mean()
        print(f"  dedup={dedup!r}: n={len(keep)}, anemic rate={lab:.3f}, "
              f"{keep.site.nunique()} sites")

    # --- feature extraction ---------------------------------------------------
    feats = [conjunctiva_color_features(r.path, age=r.age, is_female=r.is_female)
             for r in keep.itertuples()]
    fdf = pd.DataFrame(feats)
    X = fdf[CONJ_FEATURE_COLUMNS].copy()
    meta_out = pd.concat(
        [keep[["image_id", "sha", "site"]].reset_index(drop=True),
         fdf[CONJ_QC_COLUMNS].reset_index(drop=True)], axis=1
    )
    return Dataset(X=X, y=keep.hb.to_numpy(float),
                   groups=keep.site.to_numpy(), meta=meta_out)
