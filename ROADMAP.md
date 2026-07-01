# PallorHb — 12-Week Roadmap

A summer build plan (≈12 weeks) taking the project from a synthetic-data scaffold to a hardware
prototype with a validation story worth putting on a CV. Each week has a **concrete deliverable**;
the repo should always be in a runnable, demonstrable state.

Design principle: *the evaluation harness leads the project.* Before collecting any real data, the
metrics, plots, and clinical decision rule already exist and are unit-tested — so real data just
flows into a pipeline that already tells the truth about performance.

---

## Phase 1 — Software spine (Weeks 1–3)

- **W1 — Scaffold + synthetic pipeline.** Repo, feature extraction, model, clinical evaluation
  (MAE/RMSE, Bland–Altman, sensitivity/specificity) all runnable on synthetic data. Unit tests green.
  *Deliverable: `python -m pallor_hb.train` produces metrics + plots.* ✅ (this scaffold)
- **W2 — Real public dataset #1 (PPG).** Integrate a public non-invasive-Hb / PPG dataset; replace
  synthetic features with real signal processing (filtering, beat segmentation, QC rejection).
  *Deliverable: baseline metrics on real PPG.*
- **W3 — Feature engineering + model comparison.** Waveform morphology features (systolic/diastolic
  ratios, area, red/IR ratio), compared classical (GBM / RF / linear) vs. a small 1-D CNN on raw
  windows. Honest cross-validation (subject-level splits, no leakage).
  *Deliverable: model comparison table + chosen baseline.*

## Phase 2 — Hardware front-end (Weeks 4–7)

- **W4 — PPG capture rig.** MAX30102 (or AFE) on ESP32; stream red/IR at fixed rate over serial/BLE;
  log to disk with timestamps. *Deliverable: clean captured waveforms + a capture script.*
- **W5 — Signal quality + preprocessing on-device path.** Motion/contact QC, perfusion index gate,
  ambient-light handling. *Deliverable: QC that rejects bad captures reproducibly.*
- **W6 — Conjunctiva imaging path (secondary modality).** Colour-card white balance, ROI selection,
  colour-feature extraction. *Deliverable: image → colour features with calibration.*
- **W7 — Integration.** One capture app that records PPG (+ optional image) into the dataset format
  the ML pipeline already expects. *Deliverable: hardware → same feature schema as W1.*

## Phase 3 — Real paired data + validation (Weeks 8–10)

- **W8 — Small paired collection.** Collect paired (device, reference-Hb) samples. Reference =
  HemoCue or lab CBC where ethically/practically available; otherwise self + volunteers with clear
  consent and scope limits. Document protocol. *Deliverable: a real, documented mini-dataset.*
- **W9 — Calibration + fairness slice.** Fit/calibrate on real data; report performance sliced by
  skin tone / perfusion. Surface uncertainty per prediction. *Deliverable: Bland–Altman on real
  data + subgroup metrics.*
- **W10 — Decision rule + operating point.** Choose the anemia-flag threshold to hit a sensitivity
  target; document the sensitivity/specificity trade-off. *Deliverable: final screening rule + ROC.*

## Phase 4 — Ship the story (Weeks 11–12)

- **W11 — Edge deployment.** Quantize/port the chosen model to run on-device (TFLite-Micro / ONNX /
  hand-rolled) so a reading happens without a laptop. *Deliverable: end-to-end on-device demo.*
- **W12 — Write-up + polish.** README results section with real numbers and plots, a short
  methods/limitations write-up, a demo GIF/video, and a clean tagged release.
  *Deliverable: recruiter-legible repo + a 1-page project brief.*

---

## What "good" looks like for a CV

- A **Bland–Altman plot on real paired data** with stated limits of agreement — signals you
  understand clinical method comparison, not just `model.score()`.
- **Subject-level cross-validation** and a **fairness slice across skin tones** — signals you know
  where these systems fail and that you tested for it.
- A **runnable edge demo** — signals hardware + ML integration, not a notebook.
- Honest limitations section — signals scientific maturity, which is rarer than another 0.98 accuracy.

## Explicitly out of scope

Clinical claims, regulatory pathway, or any use on patients for care decisions. This is a research
and portfolio prototype.
