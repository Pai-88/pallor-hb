# Data

**No patient data or PHI is ever committed to this repo.** This directory holds dataset *pointers*
and small derived/synthetic artifacts only. Add real datasets to `.gitignore`d subfolders.

## Public datasets to integrate (roadmap W2)

Non-invasive hemoglobin / anemia estimation has a growing public-data footprint. Candidates to
evaluate (verify licenses and consent terms before use):

- **PPG-based Hb / vital-sign datasets** — search PhysioNet and Kaggle for photoplethysmography
  recordings paired with reference hemoglobin or CBC values. Prefer datasets with subject IDs so
  cross-validation can be split by subject (no leakage).
- **Conjunctiva / eye-pallor image sets** — several published smartphone-based anemia studies release
  conjunctiva image sets with paired lab Hb (e.g. "eyes-defy-anemia"-style collections). Colour-card
  calibration metadata is a must for the imaging modality.
- **Fingernail / palm pallor images** — an alternative imaging site used in some smartphone studies.

> Update this list with the exact dataset chosen, its URL, license, size, and reference-Hb
> distribution once selected.

## Expected schema

Real loaders in `pallor_hb.dataset` must emit the same schema the synthetic generator does:

- **Features:** the columns in `PPG_FEATURE_COLUMNS` (PPG) or the colour features from
  `conjunctiva_color_features` (imaging).
- **Target `y`:** reference hemoglobin in **g/dL**.
- **`groups`:** subject ID, so `GroupKFold` / `GroupShuffleSplit` prevent same-subject leakage.

## Collecting a small paired set (roadmap W8)

If collecting original data: obtain informed consent, keep scope limited to research/portfolio, use a
proper reference (HemoCue or lab CBC), record skin tone and capture conditions for the fairness slice,
and store any identifiers outside the repo. This project makes **no clinical claims**.
