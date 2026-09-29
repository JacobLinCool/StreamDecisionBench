"""The latent-state -> policy -> renderer framework every scenario is written in.

A scenario author writes four things:

* ``questions(variant)`` - the typed questions (choice / score) whose answers
  together form one decision. Option texts may be reworded per variant, but
  semantic ids, level counts and the decision policy stay the same.
* ``timeline(variant)`` - exactly ``STEPS`` ``Tick`` objects: the open-loop
  latent trajectory z_0..z_99 plus per-tick surface content (what is being
  said, logged or typed at that moment) and event tags.
* ``policy(latent)`` - the deterministic gold decision for one latent state.
  It must implement, rule for rule, the policy written in the instructions.
* ``render(history, variant)`` - the complete state for the newest tick in
  ``history``. The renderer only ever sees the past and present, which rules
  out future leakage by construction.

A real-time (``sdb/0.2``) scenario also declares its timing (``tick_seconds``,
``window_start``, ``deadline_seconds``), its family's fixed state format
(``schema_id``, ``state_schema``, ``prepared_keys``, ``machine_fields``) and may
override ``check`` with family-specific guarantees; ``render`` then returns a
JSON object. Scenarios that leave ``tick_seconds`` unset build as legacy
``sdb/0.1`` episodes. Shared stream conventions (clocks, speech, windows,
threshold margins) live in ``authoring.stream``.

``build_episode`` turns a scenario and a variant into an episode file with
opaque option labels and hidden gold. In ``sdb/0.2`` the option order is fixed
per episode and lives in the public question (``option_order`` balances it
across the five variants), and no label starts with the letter of an id shown
to the model (``S4``, ``P10``); in ``sdb/0.1`` it is reshuffled every tick
(``criteria_order``).
"""

from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Iterable, Sequence

from streamdecisionbench.authoring.stream import parse_clock
from streamdecisionbench.schema import (
    CHOICE_OPTIONS,
    COUNTERFACTUAL_VARIANTS,
    LEGACY_SCHEMA_VERSION,
    QUESTION_COUNT,
    RT_TIERS,
    SCHEMA_VERSION,
    SCORE_LEVELS,
    STEPS,
    TICK_SECONDS,
    VARIANTS,
    composite,
    deadline_steps_for,
    id_tokens,
)

Entry = str | dict[str, Any] | list[Any]


@dataclass(frozen=True)
class Choice:
    """Select one option. ``options`` maps hidden semantic ids to option texts."""

    key: str
    instructions: Entry
    options: dict[str, Entry | None]


@dataclass(frozen=True)
class Score:
    """Select one ordered level. Gold is the level index (0-based)."""

    key: str
    instructions: Entry
    levels: list[Entry]


@dataclass(frozen=True)
class Noul:
    """A yes/no judgment. Gold is a bool. Legacy ``sdb/0.1`` only: real-time
    scenarios ask a binary decision as a two-option ``Choice``."""

    key: str
    instructions: Entry
    criteria: dict[str, Entry] | None = None


Question = Choice | Score | Noul


@dataclass
class Tick:
    """One moment of the stream.

    ``latent`` holds every decision-relevant fact (z_t). ``surface`` holds the
    moment's narrative content (utterances, log lines, chat messages) keyed
    however the renderer likes. It must never be needed to recover a fact that
    is absent from ``latent``.
    """

    latent: dict[str, Any]
    surface: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    note: str = ""


class Timeline:
    """A small helper for writing scripts tick by tick.

    >>> tl = Timeline({"mode": "on_route", "point": 1})
    >>> tl.step({"say": "Good morning."}, tags=["steady"])
    >>> tl.step({"say": "Let's begin."}, point=2)
    """

    def __init__(self, initial: dict[str, Any]):
        self.latent = copy.deepcopy(initial)
        self.ticks: list[Tick] = []

    def step(
        self,
        surface: dict[str, Any] | None = None,
        tags: Iterable[str] = (),
        note: str = "",
        **updates: Any,
    ) -> Tick:
        self.latent.update(copy.deepcopy(updates))
        tick = Tick(copy.deepcopy(self.latent), dict(surface or {}), list(tags), note)
        self.ticks.append(tick)
        return tick

    def steps(self, surfaces: Sequence[dict[str, Any]], tags: Iterable[str] = (), note: str = "", **updates: Any) -> None:
        """Several ticks with the same latent state; updates apply at the first one."""
        tags = list(tags)
        for i, surface in enumerate(surfaces):
            self.step(surface, tags, note, **(updates if i == 0 else {}))


def override(
    ticks: list[Tick],
    at: Iterable[int],
    surface: Callable[[Tick, int], dict[str, Any]] | None = None,
    tags: Iterable[str] | None = None,
    note: str | None = None,
    **updates: Any,
) -> list[Tick]:
    """Copy ``ticks`` with latent ``updates`` applied at the given indices.

    Used to derive counterfactual variants from the canonical timeline so that
    everything not explicitly changed stays identical.
    """
    out = [copy.deepcopy(t) for t in ticks]
    for i in at:
        out[i].latent.update(copy.deepcopy(updates))
        if surface is not None:
            out[i].surface = surface(out[i], i)
        if tags is not None:
            out[i].tags = list(tags)
        if note is not None:
            out[i].note = note
    return out


def span_tags(spec: dict[str, Iterable[int | tuple[int, int]]], steps: int = STEPS) -> list[list[str]]:
    """Per-tick tag lists from ``{tag: [t, (start, end_inclusive), ...]}``."""
    out: list[list[str]] = [[] for _ in range(steps)]
    for tag, items in spec.items():
        for item in items:
            start, end = (item, item) if isinstance(item, int) else item
            for t in range(start, end + 1):
                if tag not in out[t]:
                    out[t].append(tag)
    return out


def seeded(*keys: Any) -> random.Random:
    material = "\x1f".join(str(k) for k in keys).encode()
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


def pick(options: Sequence[Any], *keys: Any) -> Any:
    """Deterministically pick one phrasing, varying with ``keys`` (e.g. the tick)."""
    if not options:
        raise ValueError("pick() needs at least one option")
    return options[seeded(*keys).randrange(len(options))]


def cycle(options: Sequence[Any], index: int) -> Any:
    return options[index % len(options)]


class Scenario:
    """Base class for one base scenario (a contrast family of five variants).

    Real-time (``sdb/0.2``) scenarios set ``tick_seconds`` (0.5, 1, 2, 3 or 5)
    and the other timing and state-format class variables below; usually a
    family base class sets the format ones for both of its scenarios.
    """

    family: ClassVar[str]
    scenario_id: ClassVar[str]
    title: ClassVar[str]
    tier: ClassVar[str]
    difficulty_features: ClassVar[list[str]] = []
    decision_structures: ClassVar[list[str]] = []
    deadline_steps: ClassVar[int] = 2  # sdb/0.1 only; sdb/0.2 derives it from deadline_seconds

    # sdb/0.2: timing (REALTIME_FAMILIES.md 3.1).
    tick_seconds: ClassVar[float | None] = None  # None builds a legacy sdb/0.1 episode
    window_start: ClassVar[str] = ""  # clock at t=0 in the family's format, e.g. "07:00.0", "10:32:00"
    deadline_seconds: ClassVar[float] = 0.0  # DSR deadline on the composite decision
    # sdb/0.2: the family's fixed state format (3.2).
    schema_id: ClassVar[str] = ""  # e.g. "presentation_navigation/1"
    state_schema: ClassVar[dict[str, Any]] = {}  # JSON Schema every state must satisfy
    prepared_keys: ClassVar[tuple[str, ...]] = ()  # top-level keys of static prepared context; they come first
    machine_fields: ClassVar[tuple[str, ...]] = ()  # machine-written paths ("mic_log", "channels[].activity") linted for interpretive words

    def questions(self, variant: str) -> list[Question]:
        raise NotImplementedError

    def timeline(self, variant: str) -> list[Tick]:
        raise NotImplementedError

    def policy(self, latent: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def render(self, history: list[Tick], variant: str) -> Entry:
        raise NotImplementedError

    def construction(self, variant: str) -> dict[str, Any]:
        """Hidden notes describing what this variant changes and why."""
        return {}

    def check(
        self, variant: str, ticks: list[Tick], golds: list[dict[str, Any]], states: list[dict[str, Any]]
    ) -> list[str]:
        """Family-specific guarantees for one built variant; each message is a validation error.

        Called by the validator with this variant's timeline, the policy's gold
        per tick (internal question keys, semantic values) and the built states.
        Families check what the generic validator cannot: renderer guarantees
        (3.4), threshold margins (3.8, ``stream.margin_problem``), evidence
        timing (a gold change lands on ``stream.first_tick`` of its evidence),
        decoy carriers.
        """
        return []

    @property
    def realtime(self) -> bool:
        return self.tick_seconds is not None

    def read_time(self, t: int) -> float:
        """Clock seconds at which tick ``t``'s state is read (``window_start + t * tick_seconds``)."""
        assert self.tick_seconds is not None, "read_time needs a real-time scenario"
        return round(parse_clock(self.window_start) + t * self.tick_seconds, 6)


# ---------------------------------------------------------------------------
# Episode building
# ---------------------------------------------------------------------------

_LETTERS = "BCDFGHJKLMNPQRSTVWXZ"
_DIGITS = "23456789"


def opaque_labels(n: int, *keys: Any, taken: set[str] | None = None, avoid: Iterable[str] = ()) -> list[str]:
    """``n`` distinct letter+digit labels, seeded by ``keys``, none in ``taken`` and none starting with a letter in ``avoid``."""
    rng = seeded("labels", *keys)
    avoid = set(avoid)
    letters = [ch for ch in _LETTERS if ch not in avoid]
    if not letters:
        raise ValueError("no label letters left to draw from")
    taken = set(taken or ())
    labels: list[str] = []
    while len(labels) < n:
        label = rng.choice(letters) + rng.choice(_DIGITS)
        if label not in taken:
            taken.add(label)
            labels.append(label)
    return labels


def option_order(scenario_id: str, variant: str, key: str, options: Iterable[str]) -> list[str]:
    """The sdb/0.2 display order of a choice's semantic options in one variant.

    One seeded permutation per scenario and question, rotated by the variant's
    index: with five or more options no option (the idle or majority one
    included) is listed first, or in any other one position, in more than one
    of the five variants; with fewer, the first slot cycles through them.
    """
    base = sorted(options)
    seeded("order", scenario_id, key).shuffle(base)
    shift = VARIANTS.index(variant) % len(base)
    return base[shift:] + base[:shift]


def question_texts(question: Question) -> list[Entry]:
    """Everything a question shows the model besides labels: instructions and option or level texts."""
    if isinstance(question, Choice):
        return [question.instructions, *(v for v in question.options.values() if v is not None)]
    if isinstance(question, Score):
        return [question.instructions, *question.levels]
    return [question.instructions, *(question.criteria or {}).values()]


def _question_wire(
    question: Question, labels: list[str] | None, order: list[str] | None = None
) -> tuple[dict[str, Any], dict[str, str] | None]:
    """Public question plus hidden label -> semantic id map; ``order`` fixes the shown option order."""
    if isinstance(question, Choice):
        assert labels is not None
        semantics = dict(zip(labels, question.options))
        criteria = {label: question.options[semantics[label]] for label in (order or labels)}
        return {"type": "choice", "instructions": question.instructions, "criteria": criteria}, semantics
    if isinstance(question, Score):
        return {"type": "score", "instructions": question.instructions, "criteria": list(question.levels)}, None
    wire: dict[str, Any] = {"type": "noul", "instructions": question.instructions}
    if question.criteria is not None:
        wire["criteria"] = dict(question.criteria)
    return wire, None


def _check_gold(question: Question, value: Any) -> None:
    if isinstance(question, Choice):
        if value not in question.options:
            raise ValueError(f"gold {value!r} is not an option of {question.key!r}")
    elif isinstance(question, Score):
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < len(question.levels):
            raise ValueError(f"gold {value!r} is not a level of {question.key!r}")
    elif not isinstance(value, bool):
        raise ValueError(f"gold {value!r} for noul {question.key!r} must be a bool")


def gold_track(scenario: Scenario, variant: str) -> tuple[list[Question], list[Tick], list[dict[str, Any]]]:
    questions = scenario.questions(variant)
    ticks = scenario.timeline(variant)
    if len(ticks) != STEPS:
        raise ValueError(f"{scenario.scenario_id}/{variant}: timeline has {len(ticks)} ticks, expected {STEPS}")
    golds = []
    for t, tick in enumerate(ticks):
        gold = scenario.policy(tick.latent)
        keys = {q.key for q in questions}
        if set(gold) != keys:
            raise ValueError(f"{scenario.scenario_id}/{variant} t={t}: policy answered {sorted(gold)}, expected {sorted(keys)}")
        for q in questions:
            _check_gold(q, gold[q.key])
        golds.append(gold)
    return questions, ticks, golds


def _check_realtime(scenario: Scenario, episode_id: str, questions: list[Question]) -> None:
    """Build-time checks of an sdb/0.2 scenario's declarations and question types."""
    if isinstance(scenario.tick_seconds, bool) or scenario.tick_seconds not in TICK_SECONDS:
        raise ValueError(f"{episode_id}: tick_seconds must be one of {TICK_SECONDS}")
    parse_clock(scenario.window_start)
    if not scenario.deadline_seconds > 0 or not scenario.schema_id or not scenario.state_schema:
        raise ValueError(f"{episode_id}: a real-time scenario needs deadline_seconds, schema_id and state_schema")
    if not scenario.prepared_keys or not scenario.machine_fields:
        raise ValueError(f"{episode_id}: a real-time scenario declares its prepared_keys and machine_fields")
    if scenario.tier not in RT_TIERS:
        raise ValueError(f"{episode_id}: tier must be one of {RT_TIERS}")
    if not QUESTION_COUNT[0] <= len(questions) <= QUESTION_COUNT[1]:
        raise ValueError(f"{episode_id}: a decision has {QUESTION_COUNT[0]}-{QUESTION_COUNT[1]} questions, not {len(questions)}")
    for q in questions:
        if isinstance(q, Noul):
            raise ValueError(f"{episode_id}: {q.key!r} is a noul; sdb/0.2 asks binary decisions as 2-option choices")
        if isinstance(q, Choice) and not CHOICE_OPTIONS[0] <= len(q.options) <= CHOICE_OPTIONS[1]:
            raise ValueError(f"{episode_id}: choice {q.key!r} needs {CHOICE_OPTIONS[0]}-{CHOICE_OPTIONS[1]} options")
        if isinstance(q, Score) and not SCORE_LEVELS[0] <= len(q.levels) <= SCORE_LEVELS[1]:
            raise ValueError(f"{episode_id}: score {q.key!r} needs {SCORE_LEVELS[0]}-{SCORE_LEVELS[1]} levels")


def build_episode(scenario: Scenario, variant: str) -> dict[str, Any]:
    """One episode file. Real-time scenarios build ``sdb/0.2``, others legacy ``sdb/0.1``.

    sdb/0.2: the option order of each choice is fixed for the episode
    (``option_order``) and is the insertion order of the public ``criteria``;
    steps carry no ``criteria_order``. States are rendered first, so labels can
    avoid every letter that starts an id-like token (``S4``, ``H4``) in the
    states or the question texts.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    episode_id = f"{scenario.scenario_id}_{variant}"
    realtime = scenario.realtime
    if realtime:
        _check_realtime(scenario, episode_id, scenario.questions(variant))
    questions, ticks, golds = gold_track(scenario, variant)
    internal_keys = [q.key for q in questions]
    if len(set(internal_keys)) != len(internal_keys):
        raise ValueError(f"{episode_id}: duplicate question keys")

    states = [scenario.render(ticks[: t + 1], variant) for t in range(len(ticks))]
    avoid = set(id_tokens(*states, *(text for q in questions for text in question_texts(q)))) if realtime else set()

    public: dict[str, Any] = {}
    key_map: dict[str, str] = {}
    semantics: dict[str, dict[str, str]] = {}
    labels_by_key: dict[str, list[str]] = {}
    taken: set[str] = set()
    for index, question in enumerate(questions, start=1):
        qid = f"q{index}"
        key_map[qid] = question.key
        labels: list[str] | None = None
        order: list[str] | None = None
        if isinstance(question, Choice):
            labels = opaque_labels(len(question.options), episode_id, question.key, taken=taken, avoid=avoid)
            taken.update(labels)
            if realtime:
                label_of = dict(zip(question.options, labels))
                order = [label_of[sem] for sem in option_order(scenario.scenario_id, variant, question.key, question.options)]
            else:
                labels_by_key[qid] = labels
        wire, sem = _question_wire(question, labels, order)
        public[qid] = wire
        if sem is not None:
            semantics[qid] = sem

    reverse = {v: k for k, v in key_map.items()}
    canonical_golds: list[dict[str, Any]] | None = None
    if variant in COUNTERFACTUAL_VARIANTS:
        _, _, canonical_golds = gold_track(scenario, "canonical")

    ordered = [reverse[k] for k in internal_keys]
    steps = []
    previous = None
    for t, (tick, gold) in enumerate(zip(ticks, golds)):
        public_gold = {reverse[k]: v for k, v in gold.items()}
        token = composite(public_gold, ordered)
        tags = [tag for tag in tick.tags if tag not in ("transition", "cf_flip")]
        if previous is not None and token != previous:
            tags.append("transition")
        if canonical_golds is not None and canonical_golds[t] != gold:
            tags.append("cf_flip")
        if not tags:
            tags = ["steady"]
        previous = token
        state = states[t]
        step: dict[str, Any] = {"t": t, "state": state}
        if realtime:
            if not isinstance(state, dict):
                raise ValueError(f"{episode_id} t={t}: an sdb/0.2 state must be a JSON object")
        else:
            per_tick = {}
            for qid, labels in labels_by_key.items():
                shuffled = list(labels)
                seeded("order", episode_id, t, qid).shuffle(shuffled)
                per_tick[qid] = shuffled
            step["criteria_order"] = per_tick
        step.update(gold=public_gold, latent=copy.deepcopy(tick.latent), event_tags=tags, note=tick.note)
        steps.append(step)

    option_counts = {
        qid: (len(q["criteria"]) if q["type"] in ("choice", "score") else 2) for qid, q in public.items()
    }
    episode: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION if realtime else LEGACY_SCHEMA_VERSION,
        "episode_id": episode_id,
        "task_family": scenario.family,
        "contrast_family": scenario.scenario_id,
        "variant": variant,
        "title": scenario.title,
    }
    deadline = scenario.deadline_steps
    if scenario.tick_seconds is not None:
        episode.update(
            schema_id=scenario.schema_id,
            tick_seconds=scenario.tick_seconds,
            window_start=scenario.window_start,
            deadline_seconds=scenario.deadline_seconds,
        )
        deadline = deadline_steps_for(scenario.deadline_seconds, scenario.tick_seconds)
    return episode | {
        "difficulty": {
            "tier": scenario.tier,
            "question_count": len(public),
            "option_counts": option_counts,
            "features": list(scenario.difficulty_features),
        },
        "decision_structures": list(scenario.decision_structures),
        "deadline_steps": deadline,
        "questions": public,
        "hidden": {
            "question_keys": key_map,
            "option_semantics": semantics,
            "construction": scenario.construction(variant),
        },
        "steps": steps,
    }
