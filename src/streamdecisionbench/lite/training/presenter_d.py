"""Training variant of presenter voice control: a museum curator's livestreamed lecture on a raised wreck.

Shared-rules variant: the family's published rules, questions, decision spec,
builder and reference are imported unchanged from the evaluation module; only
the session, deck and transcript are new.
"""

from __future__ import annotations

from streamdecisionbench.lite.tasks import presenter
from streamdecisionbench.lite.tasks.presenter import RULES, SPEC, A, C, H, P, _build, _deck, _questions

reference = presenter.reference

EPISODE_ID = "train_presenter_d"
TITLE = "Maritime museum lecture with two clips, a floor comment and a floor request for an earlier slide"

DECK = _deck(["evening programme", "estuary map", "diver footage", "hull survey", "lifting frame",
              "lift animation", "soaking tanks", "wax treatment", "drying hall", "skippers logbook",
              "gallery plan", "opening day"], {3, 6}, 2)

DEPLOYMENT = (
    "Fictional evening lecture at the Gullhaven Maritime Museum, given in the museum's own lecture room and "
    "livestreamed on its website; Kwame Osei, head of public programmes, chairs it, and questions come from a "
    "floor microphone in the room. Odile Brennan, the curator, speaks her slide changes and clip cues out loud "
    "instead of using a clicker. A voice-driven stage controller hears the streaming ASR on all four channels "
    "and runs the projector, the video player, the captions shown in the room and on the livestream, the "
    "chair's tablet and the curator's confidence monitor. The diver footage carries the divers' own radio "
    "talk; the lift animation is silent. The controller ran in shadow mode: a technician moved the slides by "
    "hand, what the controller would have shown was only logged, and no one in the room saw it."
)

# schedule[t] lists (speaker, start tick, text, final); a later line with the same speaker and start replaces it.
SCHEDULE: dict[int, list[tuple]] = {
    0: [(P, 0, "this is the bend in the estuary where the linnet", False)],
    1: [(P, 0, "This is the bend in the estuary where the Linnet sank in 1911.", True)],
    2: [(P, 2, "next slide", False)],
    3: [(P, 2, "Next slide, please.", True)],
    4: [(P, 4, "play the video", False)],
    5: [(P, 4, "Play the video.", True)],
    6: [(C, 6, "were at nine metres", False)],
    7: [(C, 6, "We're at nine metres and the visibility is poor.", True)],
    8: [(C, 8, "Hold it.", True)],
    9: [(P, 9, "pause", False)],
    10: [(P, 9, "Pores in the oak are still full of mud.", True)],
    11: [(P, 11, "hold it there", False)],
    12: [(P, 11, "Okay, hold it there. You can just read her name board.", True)],
    13: [(P, 13, "resume", False)],
    14: [(P, 13, "Resume, please.", True)],
    15: [(P, 15, "close the video", False)],
    16: [(P, 15, "Close the video?", True)],
    17: [(H, 17, "Yes, go ahead.", True)],
    18: [(P, 18, "next slide", False)],
    19: [(P, 18, "next slide the stern post is", False)],
    20: [(P, 18, "Next slide. The stern post is solid oak and still sound.", True)],
    21: [(P, 21, "go to the lifting frame", False)],
    22: [(P, 21, "Go to the lift animation.", True)],
    23: [(P, 23, "now play the", False)],
    24: [(P, 23, "Now play the animation.", True)],
    25: [(P, 25, "watch how slowly the cradle", False)],
    26: [(P, 25, "Watch how slowly the cradle comes up.", True)],
    27: [(H, 27, "theres a hand up at the front", False)],
    28: [(H, 27, "There's a hand up at the front. Let's take one question.", True)],
    29: [(P, 29, "sure close the animation", False)],
    30: [(P, 29, "Sure, close the animation.", True)],
    31: [(A, 31, "my grandad sailed", False)],
    32: [(A, 31, "My grandad sailed on her.", True)],
    33: [(P, 33, "how lovely", False)],
    34: [(P, 33, "How lovely. Right, let's move on.", True)],
    35: [(P, 35, "every plank traces back to you", False)],
    36: [(P, 35, "every plank traces back to youngs yard", False)],
    37: [(P, 35, "Every plank traces back to Young's yard, where she was built.", True)],
    38: [(P, 38, "ill stop there and hand back to you", False)],
    40: [(H, 40, "wonderful odile", False)],
    41: [(P, 38, "I'll stop there and hand back to you.", True), (H, 40, "wonderful odile lets take", False)],
    42: [(H, 40, "Wonderful, Odile. Let's take questions from the floor.", True)],
    44: [(A, 44, "where exactly", False)],
    45: [(A, 44, "where exactly did the divers", False)],
    46: [(A, 44, "Where exactly did the divers find her?", True)],
    47: [(P, 47, "so the question is where", False)],
    48: [(P, 47, "So the question is where she was found. Back to the estuary map slide.", True)],
    49: [(A, 49, "back to the hull", False)],
    50: [(A, 49, "Back to the hull survey, please.", True)],
    51: [(P, 51, "go back to slide four", False)],
    52: [(P, 51, "Go back to slide 4.", True)],
    53: [(A, 53, "is she on show", False)],
    54: [(A, 53, "Is she on show yet?", True)],
    55: [(P, 55, "not yet she opens in the autumn", False)],
    56: [(P, 55, "Not yet, she opens in the autumn. Back to you, Kwame.", True)],
    57: [(H, 57, "Let's thank Odile.", True)],
    58: [(P, 58, "previous slide", False)],
    59: [(P, 58, "Previous slide. That's her underwater, for anyone staying.", True)],
}


def _initial() -> dict:
    return {
        "prepared": {"deployment": DEPLOYMENT, "rules": RULES},
        "clock": {"now": 0},
        "session": {"talk": "Raising the Linnet: an oyster smack out of the estuary mud",
                    "presenter": "Odile Brennan", "host": "Kwame Osei"},
        "deck": DECK, "transcript": [],
    }


def scenarios() -> list[dict]:
    """One 60-tick trajectory; gold is always computed by the shared public reference."""
    scenario = _build(_initial(), SCHEDULE, episode_id=EPISODE_ID, title=TITLE,
                      questions=_questions(DECK), decision_spec=SPEC)
    scenario["scenario_id"] = "presenter_d"
    return [scenario]
