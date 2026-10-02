"""Training variant of presenter voice control: a marine-acoustics guest lecture with two clips.

Shared-rules variant: the family's published rules, questions, decision spec,
builder and reference are imported unchanged from the evaluation module; only
the session, deck and transcript are new.
"""

from __future__ import annotations

from streamdecisionbench.lite.tasks import presenter
from streamdecisionbench.lite.tasks.presenter import RULES, SPEC, A, C, H, P, _build, _deck, _questions

reference = presenter.reference

EPISODE_ID = "train_presenter_c"

DECK = _deck(["welcome", "sound in seawater", "hydrophone moorings", "sperm whale dive", "shipping lanes",
              "noise budget", "spectrogram reading", "masking", "reef chorus", "quiet harbour trial",
              "open recordings", "further reading", "acknowledgements"], {4, 9}, 4)

DEPLOYMENT = (
    "Fictional guest lecture in the Corran lecture theatre of the Saltmarsh Institute of Ocean Science, filmed "
    "for the institute's public lecture channel; Elliot Fairbanks, who leads its acoustics group, chairs it. "
    "Tamsin speaks from the lectern and calls for her slides out loud, the way she would cue a projectionist "
    "sitting in the booth. A stage controller follows the lapel, chair, floor and clip channels through streaming "
    "speech recognition and works out which slide the projector should hold, whether a clip should run, whose "
    "words the theatre and online captions carry, and what the confidence monitor at the lectern and the tablet "
    "on the chair's table should display. "
    "The sperm whale clip has a narrator; the reef chorus clip is a field recording with no speech. "
    "Nothing the controller decided reached the projector: the booth projectionist ran the deck by hand and the "
    "controller's output was only written to a log."
)


SCHEDULE: dict[int, list[tuple]] = {
    0: [(P, 0, "this tag rode on a sperm whale for fourteen hours", False)],
    1: [(P, 0, "This tag rode on a sperm whale for 14 hours.", True)],
    2: [(P, 2, "play the video", False)],
    3: [(P, 2, "Play the video.", True)],
    4: [(C, 4, "pause", False)],
    5: [(C, 4, "pauses between clicks shrink", False), (P, 5, "pause the video", False)],
    6: [(C, 4, "Pauses between clicks shrink as she nears the squid.", True), (P, 5, "pause the video at home", False)],
    7: [(P, 5, "Pause the video at home and count the clicks yourself.", True)],
    8: [(P, 8, "hold the video", False)],
    9: [(P, 8, "Hold the video, please.", True)],
    10: [(P, 10, "each click is her sonar", False)],
    11: [(P, 10, "Each click is her sonar, and the gap between clicks tracks how far ahead she is looking.", True)],
    12: [(P, 12, "Okay, resume.", True)],
    13: [(P, 13, "close the video", False)],
    14: [(P, 13, "Close the video.", True)],
    15: [(P, 15, "go to slide six", False)],
    16: [(P, 15, "Go to slide 6.", True)],
    17: [(P, 17, "the noise budget adds up every ship within twenty five kilometres", False)],
    18: [(P, 17, "The noise budget adds up every ship within 25 kilometres of the moorings.", True)],
    19: [(P, 19, "go to the spectrogram reading", False)],
    20: [(P, 19, "Go to the spectrogram reading guide in the course notes if these plots are new.", True)],
    21: [(P, 21, "go to the reef chorus", False)],
    22: [(P, 21, "Go to the reef chorus slide.", True)],
    23: [(P, 23, "Play it.", True)],
    24: [(P, 24, "that crackle is snapping shrimp", False)],
    25: [(P, 24, "That crackle is snapping shrimp, thousands of them on one reef.", True)],
    26: [(P, 26, "Next slide.", True)],
    27: [(P, 27, "when ships slowed to ten knots", False)],
    28: [(P, 27, "When ships slowed to 10 knots, the reef got its evenings back.", True)],
    29: [(H, 29, "lets take questions", False)],
    30: [(H, 29, "Let's take questions from the floor.", True)],
    32: [(A, 32, "could we see the reef", False)],
    33: [(A, 32, "could we see the reef chorus again where are the fish", False)],
    34: [(A, 32, "Could we see the reef chorus again? Where are the fish calls?", True)],
    35: [(P, 35, "back to the reef chorus", False)],
    36: [(P, 35, "back to the reef chorus of course previous", False)],
    37: [(P, 35, "Back to the reef chorus? Of course. Previous slide.", True)],
    38: [(P, 38, "so the question is where", False)],
    39: [(P, 38, "So the question is where the fish calls are in this recording.", True)],
    40: [(P, 40, "they are the low grunts under the crackle", False)],
    41: [(P, 40, "They're the low grunts under the crackle, mostly after sunset.", True)],
    42: [(A, 42, "Thanks, that's really clear.", True)],
    43: [(P, 43, "Okay, let's move on.", True)],
    44: [(P, 44, "go to the open recordings", False)],
    45: [(P, 44, "Go to the open recordings.", True)],
    46: [(P, 46, "the harbour master lent us his pier", False)],
    47: [(P, 46, "the harbour master lent us his pier so the first copies go back to you", False)],
    48: [(P, 46, "The harbour master lent us his pier, so the first copies go back to Hugh.", True)],
    49: [(P, 49, "those are all the recordings i brought back to you", False)],
    50: [(P, 49, "Those are all the recordings I brought. Back to you, Elliot.", True)],
    52: [(H, 52, "right lets thank tamsin", False)],
    53: [(H, 52, "Right, let's thank Tamsin.", True)],
    54: [(H, 54, "tamsin could you put the", False)],
    55: [(H, 54, "Tamsin, could you put the acknowledgements up?", True)],
    56: [(P, 56, "Go to slide 13.", True)],
    57: [(P, 57, "Next slide.", True)],
    58: [(P, 58, "oh thats the last one", False)],
    59: [(P, 58, "Oh, that's the last one. Thank you all.", True)],
}


def _lecture() -> dict:
    initial = {
        "prepared": {"deployment": DEPLOYMENT, "rules": RULES},
        "clock": {"now": 0},
        "session": {"talk": "Listening to a noisy ocean: whales, ships and reefs",
                    "presenter": "Tamsin Valdez", "host": "Elliot Fairbanks"},
        "deck": DECK, "transcript": [],
    }
    scenario = _build(initial, SCHEDULE, episode_id=EPISODE_ID,
                      title="Marine acoustics guest lecture with a narrated dive clip and a reef recording",
                      questions=_questions(DECK), decision_spec=SPEC)
    scenario["scenario_id"] = "presenter_c"
    return scenario


def scenarios() -> list[dict]:
    """One 60-tick training trajectory of the presenter voice-control family."""
    return [_lecture()]
