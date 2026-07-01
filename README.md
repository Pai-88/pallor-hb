# PallorHb — Non-Invasive Point-of-Care Anemia Screening

**Estimating blood hemoglobin (Hb) without a needle**, from a low-cost photoplethysmography (PPG)
front-end and/or a smartphone image of the palpebral conjunctiva — and flagging anemia against WHO
thresholds. Built as an end-to-end ML + embedded-hardware system: sensor → signal/feature extraction
→ calibrated regression model → clinical decision, with an honest validation story (error bars, not
just a single accuracy number).

> **Status:** early scaffold. The ML pipeline runs end-to-end **today on synthetic data** so the
> architecture and evaluation are testable before real data collection. See the [12-week roadmap](ROADMAP.md).

---

## Why this matters

Anemia affects roughly **2 billion people** and is a leading cause of morbidity in pregnancy and
childhood, disproportionately in low-resource settings. The gold standard (a venous draw + lab CBC,
or a HemoCue cuvette) needs consumables, a phlebotomist, and cold-chain logistics. A **non-invasive,
reagent-free, sub-$20 screener** that runs on a microcontroller would let community health workers
triage who actually needs a confirmatory lab test.

This is *screening*, not diagnosis. The design target is high **sensitivity** at the WHO anemia cutoff
(so few true anemics are missed), with the model's uncertainty surfaced rather than hidden.

## The clinical target

| Population        | Anemia threshold (Hb) |
|-------------------|-----------------------|
| Children 6–59 mo  | < 11.0 g/dL           |
| Non-preg. women   | < 12.0 g/dL           |
| Pregnant women    | < 11.0 g/dL           |
| Men               | < 13.0 g/dL           |

Success is measured against a **reference Hb** (lab CBC or HemoCue) using:
- **MAE / RMSE** in g/dL and **Bland–Altman** limits of agreement (the right tool for method
  comparison — a high R² can still hide a clinically unacceptable bias).
- **Sensitivity / specificity** at the population-appropriate cutoff, with the operating point chosen
  to prioritise sensitivity.

## Approach

Two complementary, cheap modalities:

1. **PPG (primary).** A reflectance PPG sensor (e.g. MAX30102, red + IR) on a fingertip. Hb and blood
   volume change the absorption of red/IR light; waveform morphology and the red/IR ratio carry
   information about Hb. This reuses analog-front-end skills from my [EMG project](https://github.com/).
2. **Conjunctiva pallor (secondary).** A colour-calibrated image of the lower-eyelid conjunctiva;
   pallor (reduced redness) correlates with low Hb. Handled as a colour-feature regression with a
   reference colour card for white balance.

Pipeline: `capture → preprocess/QC → feature extraction → regression (calibrated) → Hb estimate + anemia flag + uncertainty`.

## What runs today

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Train + evaluate on synthetic PPG-feature data (writes plots + metrics to results/)
python -m pallor_hb.train --modality ppg --n 2000 --seed 0
```

This generates a physiologically-motivated synthetic dataset, fits a gradient-boosted regressor,
and writes `results/metrics.json`, a Bland–Altman plot, and a predicted-vs-actual plot. It is a
**placeholder for real data** — the point is that the feature extraction, model, and clinical
evaluation are wired together and unit-tested from day one.

## Repository layout

```
pallor-hb/
├── README.md
├── ROADMAP.md              # 12-week milestone plan
├── requirements.txt
├── src/pallor_hb/
│   ├── dataset.py          # loaders + synthetic data generator
│   ├── features.py         # PPG waveform + conjunctiva colour features
│   ├── model.py            # regression model wrapper
│   ├── evaluate.py         # MAE/RMSE, Bland–Altman, sensitivity/specificity
│   └── train.py            # end-to-end train/eval entry point
├── hardware/               # BOM + PPG front-end / capture notes
├── data/                   # dataset pointers (no PHI committed)
├── notebooks/              # exploration
└── tests/                  # unit tests for features + evaluation
```

## Datasets (real data, to be integrated)

See [`data/README.md`](data/README.md) for pointers to public non-invasive-Hb datasets and the plan
for collecting a small IRB-appropriate paired (PPG, reference-Hb) set. **No patient data is committed
to this repo.**

## Honest limitations

- Skin tone, perfusion, motion, and ambient light are real confounders; the model must be validated
  *across* skin tones or it will fail the people it most needs to serve.
- This is a personal research/portfolio project, **not a medical device** and not for clinical use.

## License

MIT — see [LICENSE](LICENSE).
