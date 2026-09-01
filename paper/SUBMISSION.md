# Submission sheet

Everything needed to post this preprint. Requirements below were verified against arXiv and
medRxiv on 2026-08-22 — re-check if more than a month has passed.

---

## Still yours to do — two items

- [ ] **Read the manuscript end to end.** Delete the fragment. The next sentence already carries the point: "The *Use of generative AI* section states, in your name, that you have reviewed and verified the entire manuscript." The *Use of generative AI*
      section states, in your name, that you have reviewed and verified the entire manuscript.
      That sentence is already public on GitHub. Roughly two hours for 14 pages. Every number has
      been checked against `../results/cp_anemic_summary.json` (see the verified list in
      `README.md`), so you are reading for sense, framing and anything you would not defend —
      not for arithmetic.
- [ ] **Fill in the Acknowledgements.** Name anyone who helped: supervisors, endorsers, anyone who
      read a draft. Then delete the `ACTION REQUIRED` comment in `main.tex`. If genuinely nobody
      helped, delete the section rather than leave it empty.

Everything else below is done.

---

## Where to post — recommendation: medRxiv first

**medRxiv**, because it removes the one real obstacle to a first submission.

| | medRxiv | arXiv |
|---|---|---|
| Endorsement needed? | **No** | **Possibly** — "if you are a new user or are submitting to a new category, you may be required to find endorsements" |
| Fit | Health sciences; a screening method on a clinical dataset | eess.IV / cs.CV; frames it as a methods paper |
| Screening | 1–2 days, checks scope and safety | Moderation for topicality |
| Needs | Institutional affiliation (you have UCL), competing-interests declaration (present) | LaTeX source preferred (ready) |

Endorsement is the thing that stalls first-time arXiv submissions, and chasing one costs days you
do not have before 7 September. medRxiv has no such gate and is a defensible home for a
non-invasive screening paper. medRxiv permits later submission of the same preprint to arXiv.

If you do go to arXiv: **eess.IV** primary, cross-list **cs.CV** and **cs.LG**. Ask a UCL
supervisor with an arXiv history for the endorsement — this is also a legitimate, low-cost reason
to open a conversation with one.

---

## Ready to paste

**Title**

> Duplicate leakage in a public conjunctival pallor benchmark, and an honest baseline for
> image-based anaemia screening

**Author** — Paing Hein Htet, Department of Medical Physics and Biomedical Engineering,
University College London, London, United Kingdom. Corresponding: `zcemphh@ucl.ac.uk`

**Abstract** — plain text, 287 words, in `_abstract_plain.txt` (LaTeX macros already stripped).

**Competing interests** — None declared. *(Already a section in the manuscript.)*

**Funding** — none. State this explicitly; leaving it blank invites a query.

**Suggested keywords** — anaemia screening; conjunctival pallor; dataset integrity; data leakage;
benchmark evaluation; medical imaging; low-resource settings

**ORCID** — register at orcid.org before submitting if you do not already have an iD; both venues accept one.

---

## AI disclosure — already handled, and it satisfies both venues

The manuscript carries a `\section*{Use of generative AI}` stating that Claude drafted and
typeset it from your own analysis and findings, that the design, dataset audit, leakage discovery,
controls and interpretation are yours, and that you have reviewed and verified the whole thing.

This matches arXiv's stated policy, which asks authors to "report in their work any significant
use of sophisticated tools… we now include in particular text-to-text generative AI among those
that should be reported", and which holds that an author who signs takes "full responsibility for
all its contents, irrespective of how the contents were generated." arXiv is also explicit that
generative AI "should not be listed as an author" — it is not.

Both venues require this declaration. Confirm it is present in `main.tex` and `arxiv/main.tex` before uploading (see the grep check below).

---

## Files to upload

Submit the **`arxiv/`** bundle — it is flat and self-contained (figures in `figs/`, no `../results/`
paths that would break on their build servers).

```
arxiv/main.tex      the manuscript
arxiv/figs/         13 figures
```

Do **not** upload `main.pdf` alongside the source; both venues build it themselves from LaTeX.

### Keeping the bundle in sync — run this after ANY edit to `main.tex`

`arxiv/main.tex` is generated from `main.tex`; do not edit it directly. Regenerate it after every change to `main.tex`, or the bundle ships an out-of-date manuscript.

```bash
cd ~/Documents/pallor-hb/paper
python3 - <<'EOF'
import re, pathlib
src = pathlib.Path("main.tex").read_text()
out = re.sub(r'\{\.\./results/([^}]+)\}', r'{figs/\1}', src)
pathlib.Path("arxiv/main.tex").write_text(out)
print("synced")
EOF

# figures are NOT copied by the snippet above -- do it explicitly, or the bundle
# ships stale plots while the .tex is current:
cp ../results/*.png arxiv/figs/
```

Then rebuild and check the declaration survived:

```bash
grep -c 'Use of generative AI' arxiv/main.tex
```

---

## Pre-flight checks — all passing as of 2026-08-22

- [x] Every quoted number verified against `../results/cp_anemic_summary.json` — AUROC 0.706 [0.653, 0.757];
      demographics floor 0.524; naive-leaky 0.883; leakage inflation CI [0.120, 0.232];
      specificity 0.303 at 90 % sensitivity; leave-one-site-out mean 0.722; permutation null
      0.529 ± 0.032; seed stability sd 0.006; Bland–Altman LoA span 7.79 → "7.8".
      Re-verified 2026-09-01 after the third deduplication pass; `verify_paper_numbers.py`
      now asserts 53 claims and exits 0.
- [x] 13 `\includegraphics` calls, all resolve; 13 figures present in `arxiv/figs/`
- [x] No dangling `\ref`s (21 labels, 10 referenced)
- [x] 6 citations, 6 bibitems, none unresolved, none uncited
- [x] Corresponding-author email in the title block
- [x] Competing-interests section present
- [x] AI-use declaration present in **both** `main.tex` and `arxiv/main.tex`
- [x] Both build clean under tectonic (one cosmetic underfull hbox, harmless)
- [ ] Manuscript read end to end by the author
- [ ] Acknowledgements completed

---

*Data: CP-AnemiC (Asare, Appiahene & Donkoh 2023, Mendeley `m53vz6b7fx`), used under its published
licence. No patient-identifiable data is redistributed.*
