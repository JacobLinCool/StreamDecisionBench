"""sdb/0.2 framework: fixed option order, question rules, stream helpers, validation end to end.

``ReadingToy`` is a tiny real-time scenario (1-s ticks, one reader, a prompt
display) written only for these tests. It uses the shared speech model for its
latent state and its renderer, and its ``check()`` uses the margin and
evidence-timing helpers, so building and validating it exercises the whole
sdb/0.2 path.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from streamdecisionbench.authoring import Choice, Noul, Scenario, Score, Tick, build_episode
from streamdecisionbench.authoring.stream import (
    MarginError,
    Speech,
    Utterance,
    assert_margin,
    first_tick,
    fmt_hms,
    fmt_like,
    fmt_mmss,
    margin_problem,
    parse_clock,
    spoken,
    window,
)
from streamdecisionbench.schema import SCHEMA_VERSION, VARIANTS, build_request, load_episodes
from streamdecisionbench.validate import language_values, validate, value_words

DATA = Path(__file__).resolve().parents[1] / "data" / "legacy" / "v0"

# ---------------------------------------------------------------------------
# The toy scenario
# ---------------------------------------------------------------------------


def U(start: float, end: float, text: str, section: str, speaker: str = "reader") -> Utterance:
    return Utterance(start, end, speaker, text, info={"section": section})


LINES = [
    U(1.0, 4.2, "Good evening, and thank you for coming out in this weather.", "intro"),
    U(5.0, 8.6, "I'm going to read you a story about a bridge and a ferry.", "intro"),
    U(9.4, 12.8, "It was written by my grandmother in 1961, on a train.", "intro"),
    U(13.6, 17.5, "She never meant anyone to read it, least of all out loud.", "intro"),
    U(26.6, 30.2, "So, the story begins on the morning the ferry stopped.", "body"),
    U(31.0, 34.2, "The whole village walked down to the water to look.", "body"),
    U(35.0, 38.4, "Nobody had seen the river that low in forty years.", "body"),
    U(39.2, 42.0, "The ferryman sat on his boat and refused to talk.", "body"),
    U(42.8, 46.6, "My grandmother, aged nine, asked him why it wasn't moving.", "body"),
    U(47.4, 50.5, "He said the river had decided to rest.", "body"),
    U(60.2, 63.0, "Sorry. The river had decided to rest, he said.", "body"),
    U(63.8, 67.2, "So the village decided to build a bridge instead.", "body"),
    U(68.0, 71.8, "It took them two summers and most of their savings.", "body"),
    U(72.6, 75.8, "Which brings me to the end, and what she learned.", "outro"),
    U(76.6, 80.0, "Three lessons, she wrote, and I'll read them quickly.", "outro"),
    U(80.8, 84.4, "Rivers rest, people don't, and bridges outlast both.", "outro"),
    U(93.6, 97.0, "Forgive me. That last one always gets me.", "outro"),
    U(97.8, 101.2, "She finished the story on the day the bridge opened.", "outro"),
    U(101.9, 105.3, "And she crossed it first, on foot, with the ferryman.", "outro"),
    U(105.9, 109.5, "Thank you all so much, and good night.", "outro"),
]

PARAPHRASE = [
    "Welcome, everyone; I appreciate you braving the rain tonight.",
    "Tonight's reading is a tale involving a ferry and a crossing.",
    "Grandma wrote it on a railway journey back in 1961.",
    "It was private writing, never intended for a public reading.",
    "Right, our tale opens on the day that ferry went quiet.",
    "Every villager wandered to the riverbank to stare.",
    "In four decades no one had watched the water sink so far.",
    "The boatman stayed on deck and would not say a word.",
    "Grandma, just nine then, wanted to know what was wrong with it.",
    "His answer: the water needed a break.",
    "Pardon me. The water needed a break, was his answer.",
    "So instead the villagers agreed to span the river.",
    "Two whole summers it took, and nearly all their money.",
    "And that leads me to the finish, and her takeaways.",
    "She listed three takeaways; let me get through them fast.",
    "Water pauses, humans can't, and spans outlive them both.",
    "Excuse me. That final one moves me every time.",
    "Her writing ended the day the crossing was opened.",
    "She was the first across, walking, beside the boatman.",
    "Many thanks to you all, and sleep well.",
]

ROOM = ["[chairs scraping]", "[coughing]", "[door closes]", "[murmuring]"]
DECOYS = {  # background speech borrowing the wrong cue option's words
    30: "the next line of the bus timetable is shown on the board",
    58: "can you show me the next line on the ticket machine",
    70: "a nudge to the reader behind me, next line please",
    90: "show the next line of the raffle numbers now",
}

INSTRUCTIONS = {
    "role": "You drive the prompt display for a reader giving a live reading. `segments` holds every finalized phrase that ended in the last 30 s (inclusive); a phrase is final 0.3 s after it ends. `partials` never count as said.",
    "rules": "1. `section`: the plan section of the newest finalized phrase. 2. `cue`: nudge if the reader has been silent 4 s or more by `clock.now`, otherwise keep the display empty.",
}
PARA_INSTRUCTIONS = {
    "role": "You operate the reader's cue screen during a live reading. Every ASR phrase that finished within the last 30 s (boundary included) is listed in `segments`, 0.3 s after it finishes. Interim text in `partials` is not speech yet.",
    "rules": "1. `section`: which part of the plan the latest final phrase belongs to. 2. `cue`: when the reader's silence at `clock.now` has lasted at least 4 s, flash the next sentence; else show nothing.",
}


class ReadingToy(Scenario):
    family = "presentation_navigation"
    scenario_id = "toy_reading"
    title = "Toy: prompt display for a live reading"
    tier = "medium"
    decision_structures = ["maintain", "advance", "wait", "recover"]
    tick_seconds = 1
    window_start = "00:10.0"
    deadline_seconds = 2
    schema_id = "toy_reading/1"
    prepared_keys = ("plan",)
    machine_fields = ("voice", "room")
    state_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["plan", "clock", "segments", "partials", "voice", "room"],
        "properties": {
            "plan": {"type": "object"},
            "clock": {"type": "object", "required": ["now"], "properties": {"now": {"type": "string"}}},
            "segments": {"type": "array", "items": {"type": "object", "required": ["start", "end", "speaker", "text"]}},
            "partials": {"type": "array", "items": {"type": "object", "required": ["speaker", "since", "text"]}},
            "voice": {"type": "object", "properties": {"state": {"enum": ["speaking", "silent"]}, "since": {"type": ["string", "null"]}}},
            "room": {"type": "array", "items": {"type": "string"}},
        },
    }

    SECTIONS = ("intro", "body", "outro")

    def lines(self, variant: str) -> list[Utterance]:
        lines = copy.deepcopy(LINES)
        if variant == "paraphrase":
            for u, text in zip(lines, PARAPHRASE):
                u.text = text
        if variant == "minimal_cf":
            lines[4] = U(26.6, 30.2, "One more thing first: the car park is free tonight.", "intro")
            lines.insert(10, U(53.0, 56.6, "Right. Back to the ferryman, then.", "body"))
        if variant == "structural_cf":
            lines[13].info["section"] = "body"  # the re-cut plan ends the body with this line
        return lines

    def speech(self, variant: str) -> Speech:
        return Speech(self.lines(variant), lag=0.3, window=30.0)

    def plan(self, variant: str) -> dict[str, Any]:
        if variant == "paraphrase":
            return {"title": "Grandma's tale of the ferry and the crossing", "sections": {
                "intro": "Welcome and where the tale came from", "body": "The day the ferry went quiet and the span was built",
                "outro": "Three takeaways and how the tale ends"}}
        outro = "Three lessons and the ending" if variant != "structural_cf" else "Starts at the three lessons; the ending"
        return {"title": "My grandmother's bridge story", "sections": {
            "intro": "Welcome and how the story was written", "body": "The morning the ferry stopped and the bridge",
            "outro": outro}}

    def questions(self, variant: str) -> list[Any]:
        para = variant == "paraphrase"
        instructions = PARA_INSTRUCTIONS if para else INSTRUCTIONS
        sections = ["The welcome part", "The central narrative", "The farewell part"] if para else ["Opening remarks", "Main story", "Closing remarks"]
        cue = ["Display nothing to the reader", "Flash the upcoming sentence"] if para else ["Keep the prompt area empty", "Show the next line as a nudge"]
        return [
            Choice("section", instructions, dict(zip(self.SECTIONS, sections))),
            Choice("cue", instructions, dict(zip(("quiet", "nudge"), cue))),
        ]

    def timeline(self, variant: str) -> list[Tick]:
        speech = self.speech(variant)
        tags = {
            "distractor": [(5, 7), (30, 33), (58, 62), (90, 93)],
            "minimal_change": [(12, 13), (45, 46)],
            "recovery": [(17, 19), (51, 53)],
            "hold_under_activity": [(25, 29), (70, 74)],
            "boundary": [(67, 69)],
        }
        ticks = []
        for t in range(100):
            T = self.read_time(t)
            final = speech.finals(T, "reader")
            silence = speech.silence(T, "reader")
            latent = {"section": final[-1].info["section"], "silence": None if silence is None else round(silence, 1)}
            tick_tags = [tag for tag, spans in tags.items() if any(a <= t <= b for a, b in spans)]
            ticks.append(Tick(latent, {}, tick_tags if variant == "canonical" else []))
        return ticks

    def policy(self, latent: dict[str, Any]) -> dict[str, Any]:
        silence = latent["silence"]
        return {"section": latent["section"], "cue": "nudge" if silence is not None and silence >= 4 else "quiet"}

    def render(self, history: list[Tick], variant: str) -> dict[str, Any]:
        t = len(history) - 1
        T = self.read_time(t)
        speech = self.speech(variant)
        clock = fmt_mmss
        state, since = speech.activity(T, "reader")
        room = [ROOM[(t // 7) % len(ROOM)], f"[applause] x{t % 3 + 1}" if t % 11 == 0 else "[quiet]"]
        if variant == "lexical_decoy":
            room.append(next((text for at, text in DECOYS.items() if at <= t < at + 8), "[quiet]"))
        return {
            "plan": self.plan(variant),
            "clock": {"now": clock(T)},
            "segments": speech.segment_rows(T, clock),
            "partials": speech.partial_rows(T, clock),
            "voice": {"state": state, "since": None if since is None else clock(since)},
            "room": room,
        }

    def construction(self, variant: str) -> dict[str, Any]:
        return {"summary": f"toy {variant}"}

    def check(self, variant, ticks, golds, states):
        speech = self.speech(variant)
        problems = speech.problems()
        for t, tick in enumerate(ticks):
            if tick.latent["silence"] is not None:
                problems += [p for p in [margin_problem(tick.latent["silence"], 4, 0.1, what=f"t={t} silence")] if p]
        start = parse_clock(self.window_start)
        anchors = {first_tick(speech.final_at(u), start, self.tick_seconds) for u in speech.utterances}
        changes = {t for t in range(1, len(ticks)) if ticks[t].latent["section"] != ticks[t - 1].latent["section"]}
        problems += [f"t={t}: section changes with no phrase finalized at that tick" for t in sorted(changes - anchors)]
        return problems


@pytest.fixture(scope="module")
def toy() -> list[dict[str, Any]]:
    return [build_episode(ReadingToy(), v) for v in VARIANTS]


def errors_about(report, text: str) -> list[str]:
    return [e for e in report.errors if text in e]


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def test_toy_builds_and_validates(toy):
    canonical = toy[0]
    assert canonical["schema_version"] == SCHEMA_VERSION
    assert (canonical["tick_seconds"], canonical["window_start"], canonical["deadline_seconds"]) == (1, "00:10.0", 2)
    assert canonical["deadline_steps"] == 2 and canonical["schema_id"] == "toy_reading/1"
    report = validate(toy, expect_full=False, scenarios=[ReadingToy()])
    assert report.errors == []
    assert report.stats["paraphrase_similarity"]["toy_reading"] < 0.6


def test_option_order_fixed_for_the_episode(toy):
    for episode in toy:
        assert all("criteria_order" not in step for step in episode["steps"])
        shown = {k: list(q["criteria"]) for k, q in episode["questions"].items()}
        for step in episode["steps"]:
            request = build_request(episode, step)
            assert {k: list(q["criteria"]) for k, q in request["questions"].items()} == shown
    again = build_episode(ReadingToy(), "canonical")
    assert [list(q["criteria"]) for q in again["questions"].values()] == [list(q["criteria"]) for q in toy[0]["questions"].values()]
    # The order is a seeded shuffle, not the authoring order, in at least one episode.
    authored = [[toy_label for toy_label, _ in e["hidden"]["option_semantics"]["q1"].items()] for e in toy]
    assert any(list(e["questions"]["q1"]["criteria"]) != a for e, a in zip(toy, authored))


def test_two_option_choice_accepted_and_noul_rejected(toy):
    assert toy[0]["difficulty"]["option_counts"] == {"q1": 3, "q2": 2}

    class WithNoul(ReadingToy):
        def questions(self, variant):
            return [super().questions(variant)[0], Noul("cue", "Nudge now?")]

    with pytest.raises(ValueError, match="noul"):
        build_episode(WithNoul(), "canonical")

    class TooMany(ReadingToy):
        def questions(self, variant):
            options = {"intro": "a", "body": "b", "outro": "c"} | {f"s{i}": f"option {i}" for i in range(8)}
            return [Choice("section", "?", options), super().questions(variant)[1]]

    with pytest.raises(ValueError, match="2-10 options"):
        build_episode(TooMany(), "canonical")

    class TwoLevels(ReadingToy):
        def questions(self, variant):
            return [super().questions(variant)[0], Score("cue", "?", ["low", "high"])]

    with pytest.raises(ValueError, match="3-5 levels"):
        build_episode(TwoLevels(), "canonical")

    bad = copy.deepcopy(toy)
    bad[0]["questions"]["q2"] = {"type": "noul", "instructions": "Nudge now?"}
    assert errors_about(validate(bad, expect_full=False, scenarios=[ReadingToy()]), "noul questions are not allowed")


def test_validator_checks_state_schema_key_order_and_lint(toy):
    bad = copy.deepcopy(toy)
    bad[0]["steps"][5]["state"]["voice"]["state"] = "mumbling"
    bad[1]["steps"][7]["state"] = dict(reversed(list(bad[1]["steps"][7]["state"].items())))
    bad[2]["steps"][9]["state"]["room"][0] = "mic 2 wrong channel?"
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert errors_about(report, "toy_reading_canonical: state schema: voice.state (enum)")
    assert errors_about(report, "toy_reading_paraphrase: t=7: top-level key order")
    assert errors_about(report, "interpretive word 'wrong'") and errors_about(report, "interpretive word '?'")


def test_validator_runs_the_scenario_check_hook():
    class Tie(ReadingToy):
        def lines(self, variant):
            lines = super().lines(variant)
            lines[3].end = 17.0  # silence is exactly 4.0 s at 00:21.0
            return lines

    episodes = [build_episode(Tie(), v) for v in VARIANTS]
    report = validate(episodes, expect_full=False, scenarios=[Tie()])
    assert errors_about(report, "t=11 silence 4 sits exactly on the threshold 4")


def test_validator_detects_stale_episodes(toy):
    stale = copy.deepcopy(toy)
    stale[0]["steps"][3]["latent"]["silence"] = 99
    assert errors_about(validate(stale, expect_full=False, scenarios=[ReadingToy()]), "rebuild with `sdb build`")


def test_mixed_schema_versions_validate_together(toy):
    """A partially rebuilt dataset: one legacy sdb/0.1 scenario next to an sdb/0.2 one."""
    legacy: dict[str, list[dict[str, Any]]] = {}
    for e in load_episodes(DATA):
        if e["schema_version"] == "sdb/0.1":
            legacy.setdefault(e["contrast_family"], []).append(e)
    complete = [group for group in legacy.values() if len(group) == len(VARIANTS)]
    if not complete:
        pytest.skip("no complete legacy scenario in data/legacy/v0")
    report = validate(complete[0] + toy, expect_full=False, scenarios=[ReadingToy()])
    assert report.errors == []


def test_identical_requests_across_variants_must_share_gold(toy):
    """Labels differ per episode, so the check compares label-free requests across the whole dataset."""
    canonical, minimal = toy[0], toy[3]
    t = next(t for t in range(100) if canonical["steps"][t]["gold"] != minimal["steps"][t]["gold"])
    bad = copy.deepcopy(toy)
    bad[3]["steps"][t]["state"] = copy.deepcopy(canonical["steps"][t]["state"])
    assert canonical["questions"]["q1"]["criteria"] != bad[3]["questions"]["q1"]["criteria"]  # other labels, other order
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert errors_about(report, f"t={t}: identical request to toy_reading_")


def test_prepared_keys_stay_static_and_machine_fields_resolve(toy):
    bad = copy.deepcopy(toy)
    for step in bad[0]["steps"][50:]:
        step["state"]["plan"]["title"] = "A re-titled plan"
    assert errors_about(validate(bad, expect_full=False, scenarios=[ReadingToy()]), "prepared keys ['plan'] change at t=50")

    class Typo(ReadingToy):
        machine_fields = ("voices", "rooms")

    report = validate(toy, expect_full=False, scenarios=[Typo()])
    assert errors_about(report, "machine_fields path 'voices' selects nothing") and errors_about(report, "'rooms' selects nothing")

    class Undeclared(ReadingToy):
        machine_fields = ()

    with pytest.raises(ValueError, match="machine_fields"):
        build_episode(Undeclared(), "canonical")


def test_timing_tier_and_question_count(toy):
    bad = copy.deepcopy(toy)
    bad[0]["difficulty"]["tier"] = "easy"
    bad[1]["tick_seconds"] = True
    bad[2]["window_start"] = "00:99.0"
    bad[3].update(tick_seconds=2, deadline_steps=1)
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert errors_about(report, "toy_reading_canonical: tier must be one of ('medium', 'hard')")
    assert errors_about(report, "toy_reading_paraphrase: tick_seconds True must be one of")
    assert errors_about(report, "toy_reading_lexical_decoy: window_start '00:99.0' is not a clock")
    assert errors_about(report, "toy_reading_minimal_cf: tick_seconds 2 != the scenario's 1")
    assert errors_about(report, "toy_reading_minimal_cf: tick_seconds differ from the canonical variant")

    class Easy(ReadingToy):
        tier = "easy"

    class FourQuestions(ReadingToy):
        def questions(self, variant):
            qs = super().questions(variant)
            return qs + [Choice(f"extra{i}", "?", {"a": "one way", "b": "another way"}) for i in range(2)]

    for cls, message in ((Easy, "tier"), (FourQuestions, "1-3 questions")):
        with pytest.raises(ValueError, match=message):
            build_episode(cls(), "canonical")


def test_malformed_choice_is_reported_not_raised(toy):
    bad = copy.deepcopy(toy)
    label = next(iter(bad[0]["questions"]["q2"]["criteria"]))
    bad[0]["questions"]["q2"]["criteria"] = {label: bad[0]["questions"]["q2"]["criteria"][label]}
    bad[0]["hidden"]["option_semantics"]["q2"] = {label: bad[0]["hidden"]["option_semantics"]["q2"][label]}
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert errors_about(report, "q2: a choice needs 2-10 options, has 1")


def test_paraphrase_must_reword_instructions_and_options(toy):
    bad = copy.deepcopy(toy)
    canonical, para = bad[0], bad[1]
    for key in ("q1", "q2"):
        para["questions"][key]["instructions"] = canonical["questions"][key]["instructions"]
        m0 = {v: k for k, v in canonical["hidden"]["option_semantics"][key].items()}
        for label, sem in para["hidden"]["option_semantics"][key].items():
            para["questions"][key]["criteria"][label] = canonical["questions"][key]["criteria"][m0[sem]] + "."  # a one-character edit
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert errors_about(report, "q1: instructions are not reworded") and errors_about(report, "only 0/5 option texts are reworded")


def test_minimal_counterfactual_with_too_many_edits_warns(toy):
    bad = copy.deepcopy(toy)
    minimal = bad[3]
    for start in (80, 86, 92):  # three more flipped runs of 3 ticks
        for step in minimal["steps"][start : start + 3]:
            step["gold"]["q2"] = "nudge" if step["gold"]["q2"] == "quiet" else "quiet"
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert [w for w in report.warnings if "minimal counterfactual flips 5 runs" in w]


def test_labels_avoid_ids_shown_to_the_model(toy):
    class WithIds(ReadingToy):
        def plan(self, variant):
            plan = super().plan(variant)
            plan["title"] += ", B2 draft, rev K9 of L3"
            return plan

    episode = build_episode(WithIds(), "canonical")
    labels = [label for m in episode["hidden"]["option_semantics"].values() for label in m]
    assert not {label[0] for label in labels} & {"B", "K", "L"}
    bad = copy.deepcopy(toy)
    label = next(iter(bad[0]["questions"]["q1"]["criteria"]))
    for step in bad[0]["steps"]:
        step["state"]["plan"]["title"] += f" ({label[0]}7)"
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert errors_about(report, f"q1: label '{label}' starts like the id '{label[0]}7'")


def test_option_order_is_balanced_across_variants(toy):
    for key in ("q1", "q2"):
        firsts = [e["hidden"]["option_semantics"][key][next(iter(e["questions"][key]["criteria"]))] for e in toy]
        n = len(toy[0]["questions"][key]["criteria"])
        assert max(firsts.count(x) for x in firsts) <= -(-len(toy) // n)
    bad = copy.deepcopy(toy)
    for e in bad:  # put the same option first everywhere
        q = e["questions"]["q1"]
        label = next(label for label, sem in e["hidden"]["option_semantics"]["q1"].items() if sem == "intro")
        q["criteria"] = {label: q["criteria"][label]} | {k: v for k, v in q["criteria"].items() if k != label}
    report = validate(bad, expect_full=False, scenarios=[ReadingToy()])
    assert [w for w in report.warnings if "q1: option 'intro' is listed first in 5 of 5 variants" in w]


def test_ordered_blind_export_round_trip(toy):
    from streamdecisionbench.blind import export_ordered, score_batch

    batch, key = export_ordered(toy, {e["episode_id"]: range(100) for e in toy}, "s")
    assert len(batch["streams"]) == 5 and len(key) == 500
    text = str(batch)
    assert "gold" not in text and "latent" not in text and "toy_reading" not in text
    for stream in batch["streams"]:
        assert [item["t"] for item in stream["ticks"]] == list(range(100))
    episodes = {e["episode_id"]: e for e in toy}
    answers = {}
    for item, where in key.items():
        e = episodes[where["episode_id"]]
        reverse = {k: {v: label for label, v in m.items()} for k, m in e["hidden"]["option_semantics"].items()}
        answers[item] = {k: reverse[k][g] for k, g in e["steps"][where["t"]]["gold"].items()}
    assert score_batch(episodes, key, answers)["accuracy"] == 1.0


# ---------------------------------------------------------------------------
# Stream helpers
# ---------------------------------------------------------------------------


def test_clocks():
    assert fmt_mmss(441.6) == "07:21.6" and fmt_mmss(-12.5) == "-00:12.5" and fmt_mmss(158, signed=True) == "+02:38.0"
    assert fmt_hms(37925) == "10:32:05" and fmt_hms(37925.4, 1) == "10:32:05.4" and fmt_mmss(420 + 0.1 * 3) == "07:00.3"
    assert parse_clock("07:00.0") == 420 and parse_clock("10:32:05.4") == pytest.approx(37925.4) and parse_clock("-00:12.5") == -12.5
    assert parse_clock("75:10.0") == 4510  # the leading field is not wrapped
    assert fmt_like(442, "07:00.0") == "07:22.0" and fmt_like(37926, "10:32:00") == "10:32:06"
    assert first_tick(441.9, 420, 2) == 11 and first_tick(442.0, 420, 2) == 11 and first_tick(419, 420, 2) == 0
    for text in ("7 minutes", "07:75", "10:99:99", "00:99.0", "10:60:00"):
        with pytest.raises(ValueError):
            parse_clock(text)
    # Clocks never round silently: an off-grid time would let a checked margin flip once displayed.
    for value, fmt in ((0.25, fmt_mmss), (37925.5, fmt_hms), (100.5, lambda v: fmt_mmss(v, 0))):
        with pytest.raises(ValueError, match="display grid"):
            fmt(value)


def test_speech_finalization_lag_and_window_boundary():
    u = Utterance(1.0, 2.0, "lapel", "Hello there.")
    speech = Speech([u], lag=0.5, window=10.0)
    assert speech.segments(2.4) == [] and speech.segments(2.5) == [u]
    assert speech.segments(12.0) == [u] and speech.segments(12.1) == []
    assert Speech([u], lag=0.5, window=10.0, inclusive=False).segments(12.0) == []
    by_start = Speech([u], lag=0.5, window=10.0, window_by="start")
    assert by_start.segments(11.0) == [u] and by_start.segments(11.1) == []
    assert Speech([u], lag=0.5, window=None).segments(1000) == [u]
    assert speech.final_at(u) == 2.5


def test_speech_partials():
    speech = Speech(
        [
            Utterance(0.0, 4.0, "floor", "Was the 12% with pruning at 0.3, or off?"),
            Utterance(1.0, 3.0, "lapel", "Good question.", revisions=((1.2, "good que"),)),
            Utterance(0.5, 2.0, "room", "[laughter]"),
        ],
        lag=0.3,
    )
    partials = {p.speaker: p.text for p in speech.partials(2.0)}  # half of the 12 spoken words, one revision
    assert partials == {"floor": "was the twelve percent with pruning", "lapel": "good que"}
    assert {p.speaker: p.text for p in speech.partials(4.1)} == {"floor": "was the twelve percent with pruning at zero point three or off"}
    assert speech.partials(4.3) == []
    assert speech.partial_rows(1.0, fmt_mmss)[0] == {"speaker": "floor", "since": "00:00.0", "text": "was the twelve"}
    assert spoken("Don't \"quote\" end-to-end 41,900 on the 3rd") == "don't quote end to end forty one thousand nine hundred on the third"


def test_speech_voice_activity_and_problems():
    speech = Speech(
        [Utterance(1.0, 2.0, "a", "One."), Utterance(2.2, 3.0, "a", "Two."), Utterance(5.0, 6.0, "a", "Three.")],
        lag=0.1,
        hangover=0.3,
    )
    assert speech.activity(0.5, "a") == ("silent", None) and speech.silence(0.5, "a") is None
    assert speech.activity(2.1, "a") == ("speaking", 1.0)  # the 0.2 s gap is inside the hangover
    assert speech.activity(3.2, "a") == ("speaking", 1.0)
    assert speech.activity(4.0, "a") == ("silent", 3.0) and speech.silence(4.0, "a") == pytest.approx(1.0)
    assert speech.activity(5.5, "a") == ("speaking", 5.0)
    assert speech.problems() == []
    overlapping = Speech([Utterance(1.0, 2.0, "a", "x"), Utterance(2.1, 3.0, "a", "y")], lag=0.3)
    assert "previous utterance is final" in overlapping.problems()[0]
    # Sound events never produce partials, so back-to-back room events are fine.
    room = Speech([Utterance(10.0, 12.0, "room", "[applause]"), Utterance(12.1, 13.0, "room", "[laughter]")], lag=0.3)
    assert room.problems() == [] and room.partials(12.2) == []


def test_event_window():
    events = [{"at": float(t), "event": f"e{t}"} for t in range(10)]
    at = lambda e: e["at"]
    assert [e["event"] for e in window(events, 5.0, at, last=3)] == ["e3", "e4", "e5"]
    assert [e["event"] for e in window(events, 9.0, at, seconds=2)] == ["e7", "e8", "e9"]
    assert [e["event"] for e in window(events, 9.0, at, seconds=2, inclusive=False)] == ["e8", "e9"]


def test_threshold_margins():
    assert margin_problem(4.9, 5, 0.1) is None and margin_problem(5.1, 5, 0.1) is None
    assert "exactly" in margin_problem(20, 20, 1)
    assert margin_problem(20, 20, 1, exact_allowed=True) is None
    assert "less than one unit" in margin_problem(4.95, 5, 0.1)
    with pytest.raises(MarginError):
        assert_margin(2.95, 3, 0.1)
    assert_margin(84, 84, 1, exact_allowed=True)


def test_state_word_counting():
    state = {"plan": {"title": "Two words"}, "clock": {"now": "07:00.0"}, "flags": [True, None], "text": "a b c"}
    assert value_words(state) == 2 + 1 + 2 + 3
    assert language_values(state) == ["Two words", "a b c"]
    assert language_values({"x": "speaking since 07:21.6", "y": "lapel"}) == ["speaking since"]
