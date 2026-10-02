"""Completed hosted recordings published on the public leaderboard.

The manuscript's fixed cohort stays in lite_numbers.MODELS. New recordings join
this registry without changing its paper claims or counterfactual pair selection.
"""
from lite_numbers import FACTS_COLUMNS, MODELS

HOSTED_MODELS = (*MODELS,
    ("Clef", "four-family/clef", "lite-v1-clef-four-family-retry-v1"),
    ("ClefFlash", "four-family/clef-flash", "lite-v1-clef-flash-four-family-retry-v1"),
)
HOSTED_LABELS = {**FACTS_COLUMNS, "Clef": "Clef", "ClefFlash": "Clef Flash"}
