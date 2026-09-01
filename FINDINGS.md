# Conjunctival pallor screening on CP-AnemiC: duplicate leakage and an honest baseline

**Status:** software-only study on public data. No hardware, no patient recruitment, no clinical claims.
The current `python3 scripts/run_full_analysis.py` run (~9 min with the alignment pass, cached thereafter) produces the corrected numbers in the banner above; prose and figures below are being revised to match.

---

## Summary

Using the public CP-AnemiC dataset (710 conjunctiva photographs of Ghanaian children aged
6–59 months with paired laboratory haemoglobin), this study reports three things.

**1 · The benchmark contains duplicate leakage large enough to change conclusions.**
Of 710 metadata rows only **383 are distinct photographs**, in three forms that each defeat the
detection method sufficient for the last. 212 files are byte-identical copies registered under
different image IDs. A further 19 are re-encoded copies (13 exactly pixel-identical after
region-of-interest extraction, 6 near-identical) whose bytes differ, so content hashing misses
them. The largest and least visible group is **96 shifted or re-cropped copies**: their bytes
differ *and* their hand-drawn masks differ, so bounding-box pixel comparison misses them too.
**116 groups carry conflicting haemoglobin on the same photograph** — one spans 3.3 to
10.4 g/dL — and **125 groups are attributed to more than one hospital**, which defeats
site-grouped cross-validation as well as random splits. A random split inflates AUROC by
**+0.176 (95 % CI +0.120 to +0.232, bootstrap p < 0.001)**.

**2 · After removing all three forms, twelve interpretable colour features reach
AUROC 0.706 (95 % CI 0.653–0.757)** for WHO anaemia (Hb < 11 g/dL) under hospital-grouped
cross-validation, against a demographics-only floor of 0.524. The image contributes
**+0.182 AUROC (DeLong 95 % CI +0.107 to +0.258, p = 2.1 × 10⁻⁶)**.

**3 · It is a triage screen, not a haemoglobin meter.** Bland–Altman limits of agreement span
**7.8 g/dL** (−3.87 to +3.92) with strong proportional bias (slope −0.81), so no haemoglobin
value from this model should be reported to a clinician.

---

## Data

| Property | Value |
|---|---|
| Source | CP-AnemiC, Mendeley Data [`m53vz6b7fx`](https://data.mendeley.com/datasets/m53vz6b7fx/1) |
| Metadata rows | 710 |
| Distinct files (SHA-256, pass 1) | 498 |
| Distinct after re-encode merge (pass 2) | 479 |
| **Distinct photographs after alignment (pass 3)** | **383** |
| Rows whose file hash appears exactly once | 407 |
| Duplicate groups with conflicting Hb (hash grain) | 90 |
| — the same, at the 383-photograph grain | 116 |
| Groups attributed to more than one hospital | 125 |
| Label | Laboratory Hb (g/dL); WHO threshold 11 g/dL |
| Prevalence after dedup | 0.509 |
| Collection sites | 10 hospitals, 4 Ghanaian regions |
| Cohort | Children 6–59 months |

Each image is RGBA where **the alpha channel is a hand-drawn conjunctiva mask** covering ~25 % of
the frame; the rest is black padding. Colour statistics must be computed over masked pixels only —
ignoring the mask shifts mean RGB by more than 100/255 and yields features encoding *mask area*
rather than tissue colour.

---

## Method

Twelve interpretable colour features over the masked ROI: mean RGB; **circular** mean hue and hue
concentration; mean saturation; CIELAB `L*`, `a*`, `b*` (`a*` is the perceptual red–green axis a
clinician reads as pallor); an illumination-normalised redness index `r/(r+g+b)`; its 10th
percentile; and the red/green ratio.

Two deliberate exclusions:

- **Mask area is not a feature.** It reflects annotator behaviour, not physiology; had it
  correlated with site or severity the model would have learned the annotator.
- **Hue is averaged circularly.** Red tissue sits near both 0.0 and 1.0 on the hue circle, so a
  linear mean of 0.98 and 0.02 returns 0.5 — cyan.

A gradient-boosted regressor predicts haemoglobin; its output negated doubles as the screening
score. Hyperparameters were **fixed a priori and never tuned on this data**. All reported metrics
are out-of-fold.

---

## Results

### Progressive removal of optimism

Colour features only. Each row closes one more leak than the row above.

| Configuration | n | AUROC [95 % CI] | MAE (g/dL) |
|---|---|---|---|
| Random split, duplicates kept *(the common setup)* | 710 | 0.883 [0.858–0.906] | 1.46 |
| Exact duplicates removed, random split | 498 | 0.796 [0.758–0.834] | 1.44 |
| + grouped by collection site | 498 | 0.809 [0.772–0.847] | 1.42 |
| + re-encoded copies removed | 479 | 0.780 [0.737–0.818] | 1.46 |
| **+ shifted/re-cropped copies removed (headline)** | **383** | **0.706 [0.653–0.757]** | **1.60** |

![Leakage waterfall](results/fig2_leakage.png)

### Ablation — does the camera contribute?

| Feature set | AUROC [95 % CI] | vs colour (DeLong) |
|---|---|---|
| Demographics only (age, sex) | 0.524 [0.468–0.582] | Δ −0.182, p = 2.1 × 10⁻⁶ |
| **Colour only** | **0.706 [0.653–0.757]** | — |
| Colour + demographics | 0.699 [0.647–0.751] | Δ −0.008, p = 0.55 (no difference) |

The image adds real signal; demographics add nothing detectable on top of it.

![ROC curves](results/fig1_roc.png)

### Model choice

Both models are reported because they answer different questions and the better one was not
quietly adopted after the fact.

| Model | AUROC [95 % CI] | Hb output | Agreement assessable |
|---|---|---|---|
| Hb regressor *(headline)* | 0.706 [0.653–0.757] | yes, MAE 1.60 g/dL | yes — LoA span 7.8 g/dL |
| Binary classifier | **0.733 [0.680–0.785]** | no | no |

The classifier discriminates better, as expected when optimising the decision directly, but
produces no haemoglobin estimate and so cannot be checked for clinical agreement. The regressor is
kept as the headline because the agreement finding is the more consequential result.

### Calibration

| Variant | Brier | ECE | Hosmer–Lemeshow p | AUROC | probability range |
|---|---|---|---|---|---|
| **Uncalibrated** | 0.220 | 0.114 | <0.001 | **0.733** | [0.01, 0.98] |
| Isotonic, `CalibratedClassifierCV(cv=3)` | 0.220 | **0.079** | **0.156** | 0.711 | [0.10, 0.84] |

Neither variant yields probabilities fit to report. The uncalibrated model discriminates better
but is clearly miscalibrated (H–L p < 0.001, ECE 0.114); isotonic repairs the calibration
(H–L p = 0.156, ECE 0.079) at a cost of 0.022 AUROC, compressing the range to [0.10, 0.84]. The
mechanism is visible in the last column: `CalibratedClassifierCV` fits k sub-models on k−1 folds
each and averages them, which pulls probabilities toward the centre, and at ~300 training rows per
fold each sub-model is data-starved. The uncalibrated model is the headline because this is a
ranking triage screen — but its output should not be read as a probability of anaemia. On the
incompletely deduplicated data this section previously reported the opposite conclusion, which is
a reminder that model-selection findings inherit the evaluation set's contamination.

![Calibration](results/fig4_calibration.png)

### Screening operating point

Sensitivity 0.713, specificity 0.532 at the WHO threshold. Tuned to catch 90 % of anaemic children,
specificity falls to **0.303** — referring roughly 70 % of healthy children. This, not AUROC, is the
number that decides deployability, and it is not yet good enough.

### Agreement as a haemoglobin estimator

Bias +0.03 g/dL; limits of agreement **−3.87 to +3.92 g/dL** (span 7.8); proportional-bias slope **−0.81**.
The model shrinks toward the population mean, over-predicting anaemic children and under-predicting
healthy ones. A useful non-invasive haemoglobin meter needs limits nearer ±1 g/dL.

![Bland-Altman](results/fig5_bland_altman.png)

### Cross-site generalisation (leave-one-site-out)

| Site | n | AUROC | Prevalence |
|---|---|---|---|
| Ahmadiyya Muslim Hospital | 68 | 0.747 | 0.43 |
| Komfo Anokye Teaching Hospital | 68 | 0.606 | 0.31 |
| Sunyani Municipal Hospital | 61 | 0.748 | 0.48 |
| Bolgatanga Regional Hospital | 48 | 0.661 | 0.56 |
| Nkawie-Toase Government Hospital | 48 | 0.793 | 0.65 |
| Kintampo Municipal Hospital | 34 | 0.621 | 0.65 |
| Manhyia District Hospital | 25 | 0.747 | 0.60 |
| Ejusu Government Hospital | 18 | 0.701 | 0.61 |
| SDA Hospital | 10 | 0.875 | 0.80 |
| Holy Family Hospital | 3 | — | — |

Mean 0.722 across nine evaluable sites (range 0.606–0.875). The top score at SDA Hospital rests on
n = 10 at 80 % prevalence and is noise, not performance. Read the large sites instead: of the two
largest, Komfo Anokye returns the lowest score of all (0.606) and Ahmadiyya 0.747 — so
generalisation to an unseen hospital is nearer 0.7 than the mean suggests, with a wide spread.

![Per-site forest](results/fig3_sites.png)

### Which features carry the signal

Permutation importance measured **out-of-fold** (the model's own impurity importances are computed
on training data and biased toward continuous features, so they cannot support this claim):

| Feature | ΔAUROC when shuffled | SD |
|---|---|---|
| Hue (circular mean) | 0.042 | 0.032 |
| Saturation (mean) | 0.041 | 0.032 |
| Redness, 10th percentile | 0.041 | 0.037 |
| Redness index | 0.040 | 0.023 |
| Red (mean) | 0.036 | 0.033 |

Hue, saturation and the pale tail of the redness distribution lead, within overlapping error bars —
physiologically the expected direction. Because these features are strongly correlated, a low score means "redundant given the
others", not "irrelevant".

![Permutation importance](results/fig6_importance.png)

---

## Controls

Every check below is designed to make the headline number *fail* if it is an artefact.

| Control | Result | Interpretation |
|---|---|---|
| **Label permutation** (10 repeats) | AUROC 0.529 ± 0.032 | Chance. The harness does not leak. |
| **Seed stability** (10 seeds) | 0.702 ± 0.006 (0.691–0.710) | The result is not fold-assignment luck. |
| **Bootstrap vs DeLong CI** | [0.653, 0.757] vs [0.655, 0.758] | Independent machinery, same interval. |
| **Byte-hash singles only** (n = 407) | 0.763 | Robustness check at the hash grain; a handful of re-encoded and shifted copies survive this filter, so it is not conflict-free. |
| **Nested-CV hyperparameter tuning** | 0.706 → 0.662 (Δ −0.044) | Tuning inside folds overfits at this n; fixed settings were not cherry-picked. |
| **Re-encode threshold sweep** (0.5–5.0) | 0.697–0.712 | Insensitive to the pass-2 cutoff. |
| **Alignment threshold sweep** (1.0–4.0) | 0.685–0.728, n 397–376 | Moderately sensitive; reported rather than hidden. |
| **Matched-n control for pass 3** (25 draws) | 0.744 ± 0.021 | Subsampling 479 → 383 *without* removing duplicates lands midway: about half the pass-3 drop is sample size, about half is leakage. |

![Threshold sensitivity](results/fig8_threshold.png)

### Would more data help?

| Training images | 96 | 153 | 211 | 268 | 326 | 383 |
|---|---|---|---|---|---|---|
| AUROC | 0.575 | 0.611 | 0.650 | 0.645 | 0.689 | **0.704** |

Not plateaued at full size (though the ascent is not monotone), so performance here is
plausibly limited by **sample size as well as** the dataset's irreducible label noise. A larger clean dataset would likely beat 0.706.

![Learning curve](results/fig7_learning_curve.png)

---

## Limitations

- **Label noise is irreducible.** 116 groups carry conflicting haemoglobin on identical
  pixels; merging took the median, which cannot recover the truth. A performance ceiling is baked
  into the dataset.
- **No colour calibration.** No colour card or white-balance reference was captured, so absolute
  RGB partly encodes illumination. The normalised ratios mitigate but do not remove this.
- **One country, one age band.** Children 6–59 months in Ghana. Nothing here supports use in
  adults, in pregnancy, or across different skin tones and camera pipelines.
- **Masks are hand-drawn.** A deployed system would need automatic conjunctiva segmentation, whose
  error is not represented anywhere in these numbers.
- **No true external validation.** Leave-one-site-out varies camera, operator and prevalence but
  not country or protocol. Validating on an independent dataset (e.g. Eyes-defy-anemia, Italian and
  Indian patients) is the obvious next step and is gated only on dataset access.
- **Not a clinical device.** No regulatory, ethical or safety assessment has been performed.

---

## Reproducing

```bash
pip install -r requirements.txt
# download CP-AnemiC (8.3 MB) from https://data.mendeley.com/datasets/m53vz6b7fx/1
# unpack into data/cp-anemic/   (RAR5 archive — `brew install unar` if needed)
python3 scripts/run_full_analysis.py
python3 -m pytest tests/ -q          # 62 tests, incl. adversarial leakage guards
```

Outputs in `results/`: the experiment matrix, per-site generalisation, permutation importance,
learning curve, threshold sweep, model and calibration comparisons, a machine-readable
`cp_anemic_summary.json`, and figures 1–13.

The test suite is organised by failure mode rather than by module — split integrity, feature
correctness, numerical robustness, determinism, statistical machinery, and adversarial nulls —
because the dangerous failure here is not a crash but a plausible wrong number.

## Data citation

Asare, J. W., Appiahene, P., & Donkoh, E. T. (2023). *CP-AnemiC: A conjunctival pallor dataset
and benchmark for anemia detection in children.* Mendeley Data, `m53vz6b7fx`.
Used under its published licence; no patient-identifiable data is stored in this repository.
