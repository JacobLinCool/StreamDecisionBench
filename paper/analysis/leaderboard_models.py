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

# Public single-model measurements include every authorized repeat. The fixed
# manuscript and counterfactual compositions continue to use HOSTED_MODELS.
HOSTED_REPEAT_COHORT = "hosted-api-repeats-20261003"
HOSTED_SETTING_IDS = {
    "Luna": "gpt-5.6-luna-low", "LunaNone": "gpt-5.6-luna-none",
    "Terra": "gpt-5.6-terra-low", "TerraNone": "gpt-5.6-terra-none",
    "Astra": "gpt-6-astra-low", "Jev": "jev-latest",
    "Clef": "clef", "ClefFlash": "clef-flash",
}
HOSTED_PASSES = {
    name: ((report, run), *(
        (f"{HOSTED_REPEAT_COHORT}/pass{index}/{HOSTED_SETTING_IDS[name]}",
         f"{HOSTED_REPEAT_COHORT}/pass{index}/{HOSTED_SETTING_IDS[name]}")
        for index in range(2, 3 if name == "Astra" else 4)
    ))
    for name, report, run in HOSTED_MODELS
}
