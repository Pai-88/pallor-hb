# Data

**No patient data or PHI is ever committed to this repo.** This directory holds dataset *pointers*
and small derived/synthetic artifacts only. Real datasets live in `.gitignore`d subfolders that
each user downloads themselves.

## CP-AnemiC (the dataset used by the paper)

- **Source:** Asare, Appiahene & Donkoh, *CP-AnemiC*, Mendeley Data
  [`m53vz6b7fx`](https://data.mendeley.com/datasets/m53vz6b7fx/1) — conjunctiva photographs of
  Ghanaian children aged 6–59 months with paired laboratory haemoglobin, collected at ten
  hospitals. Used under its published licence; not redistributed here.
- **Unpack location:** `data/cp-anemic/` (gitignored), so that the images sit at
  `data/cp-anemic/cp-anemic/{Anemic,Non-anemic}/` next to `Anemia_Data_Collection_Sheet.xlsx`.
- **Integrity caveat:** the release contains 710 image files but only **383 distinct photographs**
  (212 byte-identical copies, 19 re-encoded copies of which 13 are exactly pixel-identical, and 96
  shifted/re-cropped copies that defeat both hashing and thumbnail comparison). 116 final-grain
  groups carry conflicting Hb labels on the same photograph, and 125 groups are attributed to more
  than one hospital. Load it with `load_cp_anemic(..., dedup="perceptual")` (three passes); see
  `FINDINGS.md` for the full audit.
- **Images are RGBA** with the conjunctiva ROI stored in the alpha channel — colour features must
  be computed over masked pixels only (`features.load_conjunctiva_roi`).

## Expected schema

Loaders in `pallor_hb.dataset` emit a common schema:

- **Features:** the columns in `PPG_FEATURE_COLUMNS` (synthetic PPG) or the colour features from
  `conjunctiva_color_features` (imaging).
- **Target `y`:** reference haemoglobin in **g/dL**.
- **`groups`:** collection site (or subject ID), so `GroupKFold` prevents leakage across folds.

## Collecting a small paired set (future work)

If collecting original data: obtain informed consent, keep scope limited to research/portfolio, use
a proper reference (HemoCue or lab CBC), record skin tone and capture conditions for the fairness
slice, and store any identifiers outside the repo. This project makes **no clinical claims**.
