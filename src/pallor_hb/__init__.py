"""PallorHb — non-invasive point-of-care anemia screening.

Estimate blood hemoglobin (Hb) from a low-cost PPG front-end and/or a conjunctiva
image, and flag anemia against WHO thresholds.
"""

__version__ = "0.1.0"

# WHO hemoglobin cutoffs for anemia (g/dL), by population.
WHO_ANEMIA_CUTOFFS = {
    "children_6_59mo": 11.0,
    "women_nonpreg": 12.0,
    "women_preg": 11.0,
    "men": 13.0,
}
