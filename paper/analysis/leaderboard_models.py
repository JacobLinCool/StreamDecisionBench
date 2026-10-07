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
        for index in range(2, 4)
    ))
    for name, report, run in HOSTED_MODELS
}

# Wity has one authorized complete pass per reasoning mode.
HOSTED_LABELS.update(WityAuto="Wity-1 (auto)", WityOff="Wity-1 (off)")
HOSTED_PASSES.update({
    "WityAuto": (("wity-20261003/auto", "wity-1-auto-workers16-retry-after-20261003-pass1"),),
    "WityOff": (("wity-20261003/off", "wity-1-off-workers16-retry-after-20261003-pass1"),),
})

HOSTED_LABELS["Perplexity"] = "Perplexity Decider v1 27B"
HOSTED_PASSES["Perplexity"] = tuple(
    (f"perplexity-20261003/pass{index}", f"perplexity-pass{index}")
    for index in range(1, 4)
)

HOSTED_LABELS["Glide"] = "GLiDE (Fastino)"
HOSTED_PASSES["Glide"] = (
    ("glide-20261003", "lite-v1-glide-20261003-pass1-retry-v1"),
    ("glide-20261003/pass2", "lite-v1-glide-20261003-pass2-retry-v1"),
    ("glide-20261003/pass3", "lite-v1-glide-20261003-pass3-retry-v1"),
)

HOSTED_LABELS["LunaDecisions"] = "GPT-6-Luna (Decisions API)"
HOSTED_PASSES["LunaDecisions"] = (
    ("gpt-6-luna-decisions-20261007", "lite-v1-gpt-6-luna-decisions-20261007-pass1-retry-v1"),
    ("gpt-6-luna-decisions-20261007/pass2", "lite-v1-gpt-6-luna-decisions-20261007-pass2-retry-v1"),
    ("gpt-6-luna-decisions-20261007/pass3", "lite-v1-gpt-6-luna-decisions-20261007-pass3-retry-v1"),
)
