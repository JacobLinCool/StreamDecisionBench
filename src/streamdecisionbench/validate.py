"""Structural validation of built episodes.

Errors make a dataset unacceptable; warnings flag things a reviewer must look
at. Each episode is checked under the rules of its own schema version, so a
partially rebuilt dataset (some families ``sdb/0.2``, others still ``sdb/0.1``)
validates:

* ``sdb/0.2`` (docs/legacy/REALTIME_FAMILIES.md): timing fields, equal to the
  scenario's and across its variants; medium or hard tier; 1-3 questions,
  choice (2-10 options) and score (3-5 levels) only; option order fixed per
  episode; no option label starting with the letter of an id shown to the model;
  states that satisfy the scenario's JSON Schema with one top-level key order
  per state format, prepared keys first and static; value-only word counts; an
  interpretive-word lint on machine-written fields (every declared path must
  exist); the real-time temporal budget; the scenario's own ``check()``
  guarantees, run against a fresh generator pass that must reproduce the file's
  gold and latent states.
* ``sdb/0.1`` (docs/legacy/SPEC.md): the v0 pilot rules, unchanged.

Both versions share the gold, segment, tag and variant-consistency checks
(paraphrase and decoy share latent and gold with canonical, paraphrase rewords
instructions and options; counterfactuals flip gold in runs of >= 3 ticks) and
the cross-dataset check that no visible request, compared without its opaque
labels, carries two different golds.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from streamdecisionbench.adapters.local import content_words
from streamdecisionbench.authoring.stream import parse_clock
from streamdecisionbench.jev import ContractError, validate_question
from streamdecisionbench.metrics import segments, true_transitions
from streamdecisionbench.schema import (
    CHOICE_OPTIONS,
    COUNTERFACTUAL_VARIANTS,
    DECISION_STRUCTURES,
    EVENT_TAGS,
    INVARIANT_VARIANTS,
    QUESTION_COUNT,
    RT_TIERS,
    SCHEMA_VERSION,
    SCHEMA_VERSIONS,
    SCORE_LEVELS,
    STEPS,
    TASK_FAMILIES,
    TICK_SECONDS,
    TIERS,
    VARIANTS,
    build_request,
    canonical_json,
    deadline_steps_for,
    digest,
    entry_text,
    gold_sequence,
    id_tokens,
    is_realtime,
    question_keys,
    state_text,
)

if TYPE_CHECKING:
    from streamdecisionbench.authoring import Scenario

# sdb/0.1 temporal budget per canonical episode (DESIGN.md section 7). Counts are
# of events: maximal runs of consecutive ticks carrying the tag.
TRANSITIONS = (6, 12)
CF_TRANSITIONS = (4, 16)
TAG_BUDGET = {
    "distractor": (4, 8),
    "minimal_change": (2, 4),
    "recovery": (2, 4),
    "hold_under_activity": (2, 4),
    "boundary": (1, 99),
}
MIN_SEGMENT = 3
STATE_WORDS = (25, 700)
STATE_WORDS_SOFT = (40, 450)
MINIMAL_CF_SIMILARITY = 0.70
MINIMAL_CF_RUNS = (2, 4)  # SPEC 3.4: two to four edits, each flipping a run of gold
REWORDED = 0.8  # paraphrase: an option text or a question's instructions count as reworded below this similarity

# sdb/0.2 budget (REALTIME_FAMILIES.md 3.2, 3.10; open decision 2). Event runs
# also end at a gold transition, so tagged stretches on both sides of a change
# count as two events.
RT_TRANSITIONS = (6, 16)
RT_CF_TRANSITIONS = (4, 20)
RT_TAG_MIN = {"distractor": 4, "minimal_change": 2, "recovery": 2, "hold_under_activity": 2, "boundary": 1}
RT_STATE_WORDS = 700  # hard, whole state, values only
RT_LIVE_WORDS = (60, 400)  # soft, live + bookkeeping (every key not declared prepared)
DECOY_EXTRA_WORDS = 40
PARAPHRASE_SIMILARITY = 0.6
# 3.2: interpretive words that must not appear in machine-written text.
INTERPRETIVE = re.compile(r"\b(?:missing|wrong|mistakes?|unsafe|done|nok)\b|\?", re.IGNORECASE)

BASE_FIELDS = ("schema_version", "episode_id", "task_family", "contrast_family", "variant", "questions", "hidden", "steps")
REALTIME_FIELDS = ("title", "schema_id", "tick_seconds", "window_start", "deadline_seconds", "deadline_steps", "difficulty", "decision_structures")
TIMING_FIELDS = ("schema_id", "tick_seconds", "window_start", "deadline_seconds")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    @property
    def ok(self) -> bool:
        return not self.errors


def tag_events(episode: dict[str, Any], tag: str, breaks: Iterable[int] = ()) -> list[tuple[int, int]]:
    """Maximal runs ``(start, end_exclusive)`` of ticks carrying ``tag``; a run also ends before any tick in ``breaks``."""
    breaks = set(breaks)
    runs = []
    start = None
    for step in episode["steps"]:
        has = tag in step["event_tags"]
        if start is not None and (not has or step["t"] in breaks):
            runs.append((start, step["t"]))
            start = None
        if has and start is None:
            start = step["t"]
    if start is not None:
        runs.append((start, len(episode["steps"])))
    return runs


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _words(entry: Any) -> int:
    return len(entry_text(entry).split())


def value_words(obj: Any) -> int:
    """Words of a state counted on values only (keys excluded); non-string scalars count one."""
    if isinstance(obj, str):
        return len(obj.split())
    if isinstance(obj, dict):
        return sum(value_words(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(value_words(v) for v in obj)
    return 1


def strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def language_values(obj: Any) -> list[str]:
    """Natural-language string values of a state, in document order.

    Tokens containing a digit (timestamps, numbers, IDs) are dropped, and so is
    any string left with fewer than two words (enum values, labels, names).
    """
    out = []
    for s in strings(obj):
        words = [w for w in s.split() if not any(ch.isdigit() for ch in w)]
        if len(words) >= 2:
            out.append(" ".join(words))
    return out


class LanguageSimilarity:
    """Character similarity of two states' natural-language values (3.9).

    Values are paired in document order when both states have the same number
    of them (the ratio of the concatenation under that alignment); otherwise the
    joined texts are compared. Pair ratios are cached, so static prepared text
    and transcript lines that persist across ticks are compared once.
    """

    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], float] = {}

    def pair(self, a: str, b: str) -> float:
        if (a, b) not in self.cache:
            self.cache[(a, b)] = similarity(a, b)
        return self.cache[(a, b)]

    def __call__(self, x: Any, y: Any) -> float:
        xs, ys = language_values(x), language_values(y)
        if len(xs) != len(ys) or not xs:
            return self.pair("\n".join(xs), "\n".join(ys))
        total = sum(len(a) + len(b) for a, b in zip(xs, ys))
        return sum(self.pair(a, b) * (len(a) + len(b)) for a, b in zip(xs, ys)) / total if total else 1.0


def resolves(obj: Any, path: str) -> bool:
    """Whether a ``select`` path names a field of ``obj``; a ``name[]`` over empty lists counts (nothing to lint yet)."""
    found = [obj]
    for part in path.split("."):
        each = part.endswith("[]")
        name = part[:-2] if each else part
        if name:
            found = [v[name] for v in found if isinstance(v, dict) and name in v]
            if not found:
                return False
        if each:
            lists = [v for v in found if isinstance(v, list)]
            if not lists:
                return False
            found = [item for v in lists for item in v]
            if not found:
                return True
    return True


def select(obj: Any, path: str) -> list[tuple[str, Any]]:
    """Values at a dotted path; ``name[]`` descends into every item: ``"channels[].activity"``."""
    found: list[tuple[str, Any]] = [("", obj)]
    for part in path.split("."):
        each = part.endswith("[]")
        name = part[:-2] if each else part
        nxt: list[tuple[str, Any]] = []
        for where, value in found:
            if name:
                if not isinstance(value, dict) or name not in value:
                    continue
                where, value = (f"{where}.{name}" if where else name), value[name]
            if not each:
                nxt.append((where, value))
            elif isinstance(value, list):
                nxt.extend((f"{where}[{i}]", item) for i, item in enumerate(value))
        found = nxt
    return found


# ---------------------------------------------------------------------------
# Single episodes
# ---------------------------------------------------------------------------


def _check_meta(episode: dict[str, Any], report: Report, realtime: bool) -> None:
    eid = episode["episode_id"]
    if episode["task_family"] not in TASK_FAMILIES:
        report.error(eid, f"unknown task family {episode['task_family']!r}")
    if episode["variant"] not in VARIANTS:
        report.error(eid, f"unknown variant {episode['variant']!r}")
    tiers = RT_TIERS if realtime else TIERS
    if episode["difficulty"].get("tier") not in tiers:
        report.error(eid, f"tier must be one of {tiers}")
    bad = set(episode["decision_structures"]) - set(DECISION_STRUCTURES)
    if bad or not episode["decision_structures"]:
        report.error(eid, f"decision_structures must be a non-empty subset of the taxonomy (bad: {sorted(bad)})")


def _check_timing(episode: dict[str, Any], report: Report) -> None:
    eid = episode["episode_id"]
    tick = episode["tick_seconds"]
    if isinstance(tick, bool) or tick not in TICK_SECONDS:
        report.error(eid, f"tick_seconds {tick!r} must be one of {TICK_SECONDS}")
    try:
        parse_clock(str(episode["window_start"]))
    except ValueError:
        report.error(eid, f"window_start {episode['window_start']!r} is not a clock (mm:ss[.s] or hh:mm:ss[.s])")
    deadline = episode["deadline_seconds"]
    if not isinstance(deadline, (int, float)) or isinstance(deadline, bool) or deadline <= 0:
        report.error(eid, "deadline_seconds must be a positive number")
    elif not isinstance(tick, bool) and tick in TICK_SECONDS and episode["deadline_steps"] != deadline_steps_for(deadline, tick):
        report.error(eid, f"deadline_steps must be {deadline_steps_for(deadline, tick)} for {deadline:g} s at {tick:g} s ticks")
    if not isinstance(episode["schema_id"], str) or not episode["schema_id"]:
        report.error(eid, "schema_id must name the family's state format")


def _check_questions(episode: dict[str, Any], keys: list[str], report: Report, realtime: bool) -> None:
    eid = episode["episode_id"]
    if keys != [f"q{i}" for i in range(1, len(keys) + 1)]:
        report.error(eid, f"public question keys must be q1..qN, got {keys}")
    if realtime and not QUESTION_COUNT[0] <= len(keys) <= QUESTION_COUNT[1]:
        report.error(eid, f"a decision has {QUESTION_COUNT[0]}-{QUESTION_COUNT[1]} questions, got {len(keys)}")
    semantics = episode["hidden"].get("option_semantics", {})
    for key in keys:
        question = episode["questions"][key]
        try:
            validate_question(key, question)
        except ContractError as error:
            report.error(eid, str(error))
            continue
        if not entry_text(question["instructions"]).strip():
            report.error(eid, f"{key}: empty instructions")
        if realtime:
            n = len(question.get("criteria") or ())
            if question["type"] == "noul":
                report.error(eid, f"{key}: noul questions are not allowed in {SCHEMA_VERSION}; ask a 2-option choice")
                continue
            if question["type"] == "choice" and not CHOICE_OPTIONS[0] <= n <= CHOICE_OPTIONS[1]:
                report.error(eid, f"{key}: a choice needs {CHOICE_OPTIONS[0]}-{CHOICE_OPTIONS[1]} options, has {n}")
            if question["type"] == "score" and not SCORE_LEVELS[0] <= n <= SCORE_LEVELS[1]:
                report.error(eid, f"{key}: a score needs {SCORE_LEVELS[0]}-{SCORE_LEVELS[1]} levels, has {n}")
        if question["type"] == "choice":
            mapping = semantics.get(key)
            if not mapping or set(mapping) != set(question["criteria"]):
                report.error(eid, f"{key}: option_semantics must cover exactly the option labels")
                continue
            if len(set(mapping.values())) != len(mapping):
                report.error(eid, f"{key}: two labels share one semantic action")
            if len(mapping) < 2:
                report.error(eid, f"{key}: a choice needs at least two options")
            lengths = [_words(v) for v in question["criteria"].values()]
            if min(lengths) == 0:
                report.error(eid, f"{key}: every option needs a description")
            elif max(lengths) / min(lengths) > 3.0:
                report.warn(eid, f"{key}: option lengths are unbalanced ({min(lengths)}..{max(lengths)} words)")
            for label in mapping:
                if any(ch in label.lower() for ch in "aeiou") or len(label) > 3:
                    report.warn(eid, f"{key}: label {label!r} may not be opaque")


def _check_label_letters(episode: dict[str, Any], keys: list[str], report: Report) -> None:
    """No sdb/0.2 option label may start with the letter of an id shown to the model (``S4``, ``P10``, ``H4``)."""
    texts = [q.get("instructions") for q in episode["questions"].values()]
    texts += [v for q in episode["questions"].values() for v in (q["criteria"].values() if isinstance(q.get("criteria"), dict) else q.get("criteria") or [])]
    shown = id_tokens(*(s["state"] for s in episode["steps"]), *texts)
    for key in keys:
        criteria = episode["questions"][key].get("criteria")
        for label in criteria if episode["questions"][key]["type"] == "choice" and isinstance(criteria, dict) else ():
            if label[:1] in shown:
                report.error(episode["episode_id"], f"{key}: label {label!r} starts like the id {shown[label[0]]!r} shown in a state or question text; rebuild")


def check_episode(episode: dict[str, Any], report: Report) -> None:
    eid = episode.get("episode_id", "<unknown>")
    version = episode.get("schema_version")
    if version not in SCHEMA_VERSIONS:
        report.error(eid, f"schema_version {version!r} is not one of {SCHEMA_VERSIONS}")
        return
    realtime = version == SCHEMA_VERSION
    for key in BASE_FIELDS + (REALTIME_FIELDS if realtime else ()):
        if key not in episode:
            report.error(eid, f"missing field {key!r}")
            return
    _check_meta(episode, report, realtime)
    if realtime:
        _check_timing(episode, report)
    elif not isinstance(episode.get("deadline_steps"), int) or not 1 <= episode["deadline_steps"] <= 5:
        report.error(eid, "deadline_steps must be an integer in 1..5")

    steps = episode["steps"]
    if len(steps) != STEPS or [s["t"] for s in steps] != list(range(STEPS)):
        report.error(eid, f"must have exactly {STEPS} steps numbered 0..{STEPS - 1}")
        return

    keys = question_keys(episode)
    _check_questions(episode, keys, report, realtime)
    semantics = episode["hidden"].get("option_semantics", {})
    all_text = set()
    labels = {k: set(q["criteria"]) for k, q in episode["questions"].items() if q["type"] == "choice"}
    option_texts = {
        (k, label): entry_text(v).strip().lower()
        for k, q in episode["questions"].items()
        if q["type"] == "choice"
        for label, v in q["criteria"].items()
    }
    word_counts = []
    verbatim: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for step in steps:
        where = f"{eid} t={step['t']}"
        for key in keys:
            if key not in step["gold"]:
                report.error(where, f"no gold for {key}")
                continue
            question = episode["questions"][key]
            gold = step["gold"][key]
            if question["type"] == "choice" and gold not in set(semantics.get(key, {}).values()):
                report.error(where, f"{key}: gold {gold!r} is not a semantic option")
            if question["type"] == "score" and (not isinstance(gold, int) or isinstance(gold, bool) or not 0 <= gold < len(question["criteria"])):
                report.error(where, f"{key}: gold {gold!r} is not a level")
            if question["type"] == "noul" and not isinstance(gold, bool):
                report.error(where, f"{key}: gold must be a bool")
        if realtime and "criteria_order" in step:
            report.error(where, f"{SCHEMA_VERSION} steps carry no criteria_order; the option order lives in the question")
        for key, order in step.get("criteria_order", {}).items():
            if set(order) != labels.get(key, set()) or len(order) != len(labels.get(key, ())):
                report.error(where, f"{key}: criteria_order is not a permutation of the labels")
        bad_tags = set(step["event_tags"]) - set(EVENT_TAGS)
        if bad_tags:
            report.error(where, f"unknown event tags {sorted(bad_tags)}")
        text = state_text(step["state"])
        if realtime:
            if not isinstance(step["state"], dict):
                report.error(where, f"an {SCHEMA_VERSION} state must be a JSON object")
            words = value_words(step["state"])
            if words > RT_STATE_WORDS:
                report.error(where, f"state has {words} words (at most {RT_STATE_WORDS}, values only)")
            all_text.add(canonical_json(step["state"]))
        else:
            words = len(text.split())
            if not STATE_WORDS[0] <= words <= STATE_WORDS[1]:
                report.error(where, f"state has {words} words (allowed {STATE_WORDS})")
            all_text.add(text)
        word_counts.append(words)
        lowered = text.lower()
        for (key, label), option in option_texts.items():
            if len(option) > 12 and option.rstrip(".") in lowered:
                verbatim[(key, label)].append(step)
        try:
            json.dumps(step["latent"])
        except TypeError:
            report.error(where, "latent state is not JSON-serialisable")

    # An option text that appears in every state is static context (e.g. a list
    # of segment names). One that appears only sometimes, mostly when it is the
    # gold answer, is a trigger-phrase leak.
    for (key, label), hits in verbatim.items():
        if len(hits) == len(steps):
            continue
        sem = semantics.get(key, {}).get(label)
        gold_hits = sum(1 for st in hits if st["gold"].get(key) == sem)
        if gold_hits > len(hits) / 2:
            report.error(eid, f"{key}: option {label} text appears verbatim in {len(hits)} states, {gold_hits} of them where it is gold")
        else:
            report.warn(eid, f"{key}: option {label} text appears verbatim in {len(hits)} states")

    if realtime:
        _check_label_letters(episode, keys, report)
    if len(all_text) < 0.95 * STEPS:
        report.warn(eid, f"only {len(all_text)} distinct states out of {STEPS}")
    if not realtime:
        soft_out = sum(1 for w in word_counts if not STATE_WORDS_SOFT[0] <= w <= STATE_WORDS_SOFT[1])
        if soft_out:
            report.warn(eid, f"{soft_out} states fall outside {STATE_WORDS_SOFT} words")

    gold = gold_sequence(episode)
    trans = true_transitions(gold)
    cf = episode["variant"] in COUNTERFACTUAL_VARIANTS
    low, high = (RT_CF_TRANSITIONS if cf else RT_TRANSITIONS) if realtime else (CF_TRANSITIONS if cf else TRANSITIONS)
    if not low <= len(trans) <= high:
        report.error(eid, f"{len(trans)} transitions (expected {low}-{high})")
    for a, b, value in segments(gold):
        if b - a < MIN_SEGMENT:
            report.error(eid, f"gold segment t={a}..{b - 1} ({value}) is shorter than {MIN_SEGMENT} ticks")
    if len({v for _, _, v in segments(gold)}) < 3:
        report.warn(eid, "fewer than three distinct decisions over the episode")

    if episode["variant"] == "canonical":
        transition_ticks = {t for t, _ in trans}
        if realtime:
            for tag, lo in RT_TAG_MIN.items():
                n = len(tag_events(episode, tag, transition_ticks))
                if n < lo:
                    report.error(eid, f"{n} '{tag}' events (expected at least {lo})")
        else:
            for tag, (lo, hi) in TAG_BUDGET.items():
                n = len(tag_events(episode, tag))
                if not lo <= n <= hi:
                    report.error(eid, f"{n} '{tag}' events (expected {lo}-{hi})")
        for a, _ in tag_events(episode, "minimal_change", transition_ticks if realtime else ()):
            if a not in transition_ticks:
                report.warn(eid, f"minimal_change event at t={a} does not start on a gold transition")
        if not realtime:
            for a, b in tag_events(episode, "distractor") + tag_events(episode, "hold_under_activity"):
                if any(a <= t < b for t in transition_ticks):
                    report.warn(eid, f"hold/distractor event t={a}..{b - 1} contains a gold transition")

    report.stats.setdefault("state_words", []).extend(word_counts)


# ---------------------------------------------------------------------------
# sdb/0.2: the scenario's state format and generator
# ---------------------------------------------------------------------------


def resolve_scenarios(
    episodes: Sequence[dict[str, Any]], report: Report, given: Iterable[Scenario] = ()
) -> dict[str, Scenario]:
    """scenario_id -> Scenario for the sdb/0.2 episodes, from ``given`` first, then the family registry."""
    index = {s.scenario_id: s for s in given}
    families = sorted({e["task_family"] for e in episodes if is_realtime(e) and e.get("contrast_family") not in index and "task_family" in e})
    if families:
        from streamdecisionbench.families import load_scenarios

        for family in families:
            try:
                for scenario in load_scenarios([family]):
                    index.setdefault(scenario.scenario_id, scenario)
            except Exception as error:
                report.error(family, f"cannot load scenarios: {type(error).__name__}: {error}")
    return index


def _schema_validator(scenario: Scenario, cache: dict[str, Any], report: Report) -> Any:
    if scenario.schema_id not in cache:
        cache[scenario.schema_id] = None
        try:
            cls = validator_for(scenario.state_schema, default=Draft202012Validator)
            cls.check_schema(scenario.state_schema)
            cache[scenario.schema_id] = cls(scenario.state_schema)
        except SchemaError as error:
            report.error(scenario.schema_id, f"state_schema is not a valid JSON Schema: {error.message}")
    return cache[scenario.schema_id]


def check_state_format(episode: dict[str, Any], scenario: Scenario, report: Report, cache: dict[str, Any]) -> None:
    """Timing and format as the scenario declares them, JSON Schema conformance, key order,
    static prepared keys, the prepared/live word split and the machine-text lint."""
    eid = episode["episode_id"]
    if not scenario.prepared_keys or not scenario.machine_fields:
        report.error(eid, "the scenario must declare prepared_keys and machine_fields")
    for name in TIMING_FIELDS:
        if episode.get(name) != getattr(scenario, name):
            report.error(eid, f"{name} {episode.get(name)!r} != the scenario's {getattr(scenario, name)!r}; rebuild with `sdb build`")
    validator = _schema_validator(scenario, cache, report)
    prepared = list(scenario.prepared_keys)
    prepared_at_0: str | None = None
    prepared_changed: int | None = None
    unresolved = set(scenario.machine_fields)
    schema_errors: Counter[str] = Counter()
    first: dict[str, tuple[int, str]] = {}
    lint: Counter[tuple[str, str]] = Counter()
    lint_first: dict[tuple[str, str], tuple[int, str]] = {}
    order = None
    live_words = []
    for step in episode["steps"]:
        state, t = step["state"], step["t"]
        if not isinstance(state, dict):
            continue
        if validator is not None:
            for err in validator.iter_errors(state):
                path = ".".join("[]" if isinstance(p, int) else str(p) for p in err.absolute_path) or "<state>"
                key = f"{path} ({err.validator})"
                schema_errors[key] += 1
                first.setdefault(key, (t, err.message[:160]))
        keys = list(state)
        if order is None:
            order = keys
            if keys[: len(prepared)] != prepared:
                report.error(eid, f"prepared keys {prepared} must come first in every state, got {keys}")
        elif keys != order:
            report.error(eid, f"t={t}: top-level key order {keys} differs from t=0 {order}")
            order = keys
        live_words.append(value_words({k: v for k, v in state.items() if k not in prepared}))
        static = canonical_json({k: state.get(k) for k in prepared})
        if prepared_at_0 is None:
            prepared_at_0 = static
        elif static != prepared_at_0 and prepared_changed is None:
            prepared_changed = t
        unresolved -= {path for path in unresolved if resolves(state, path)}
        for path in scenario.machine_fields:
            for where, value in select(state, path):
                for text in strings(value):
                    for word in INTERPRETIVE.findall(text):
                        hit = (path, word.lower())
                        lint[hit] += 1
                        lint_first.setdefault(hit, (t, f"{where}={text[:80]!r}"))
    for key, n in schema_errors.items():
        t, message = first[key]
        report.error(eid, f"state schema: {key}: {message} ({n} errors, first t={t})")
    if prepared_changed is not None:
        report.error(eid, f"prepared keys {prepared} change at t={prepared_changed}; prepared context is static for the episode")
    for path in sorted(unresolved):
        report.error(eid, f"machine_fields path {path!r} selects nothing in any state; the interpretive-word lint would skip it")
    for (path, word), n in lint.items():
        t, sample = lint_first[(path, word)]
        report.error(eid, f"interpretive word {word!r} in machine-written {path} ({n} hits, first t={t}: {sample})")
    soft_out = sum(1 for w in live_words if not RT_LIVE_WORDS[0] <= w <= RT_LIVE_WORDS[1])
    if soft_out:
        report.warn(eid, f"{soft_out} states have live+bookkeeping words outside {RT_LIVE_WORDS}")
    report.stats.setdefault("live_words", []).extend(live_words)


def check_generator(episode: dict[str, Any], scenario: Scenario, report: Report) -> None:
    """Re-run the generator's timeline and policy, require the file to match, then run ``scenario.check``."""
    from streamdecisionbench.authoring import gold_track

    eid, variant = episode["episode_id"], episode["variant"]
    try:
        _, ticks, golds = gold_track(scenario, variant)
    except Exception as error:
        report.error(eid, f"generator fails: {type(error).__name__}: {error}")
        return
    key_map = episode["hidden"].get("question_keys", {})
    stale = [
        s["t"]
        for s, tick, gold in zip(episode["steps"], ticks, golds)
        if {qid: gold.get(k) for qid, k in key_map.items()} != s["gold"]
        or json.loads(json.dumps(tick.latent)) != s["latent"]
    ]
    if stale:
        report.error(eid, f"gold or latent differs from the generator at {len(stale)} ticks (first t={stale[0]}); rebuild with `sdb build`")
        return
    try:
        messages = scenario.check(variant, ticks, golds, [s["state"] for s in episode["steps"]])
    except Exception as error:
        report.error(eid, f"check() failed: {type(error).__name__}: {error}")
        return
    for message in messages:
        report.error(eid, message)


# ---------------------------------------------------------------------------
# Contrast families and the whole dataset
# ---------------------------------------------------------------------------


def _structure(episode: dict[str, Any]) -> list[Any]:
    out = []
    for key in question_keys(episode):
        q = episode["questions"][key]
        sem = sorted(episode["hidden"]["option_semantics"].get(key, {}).values())
        out.append((q["type"], len(q.get("criteria") or []) if q["type"] == "score" else None, sem))
    return out


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def decoy_margin(episode: dict[str, Any], key: str | None = None) -> float:
    """Mean over ticks of (best wrong-option overlap - gold-option overlap) for one choice question (default: the first)."""
    if key is None:
        keys = [k for k in question_keys(episode) if episode["questions"][k]["type"] == "choice"]
        if not keys:
            return 0.0
        key = keys[0]
    mapping = episode["hidden"]["option_semantics"].get(key, {})
    reverse = {v: k for k, v in mapping.items()}
    option_words = {label: set(content_words(entry_text(v))) for label, v in episode["questions"][key]["criteria"].items()}
    margins = []
    for step in episode["steps"]:
        gold_label = reverse.get(step["gold"].get(key))
        if gold_label not in option_words:
            continue  # reported by check_episode
        words = set(content_words(state_text(step["state"])))
        gold_overlap = len(words & option_words[gold_label])
        wrong = max((len(words & w) for label, w in option_words.items() if label != gold_label), default=0)
        margins.append(wrong - gold_overlap)
    return _mean(margins)


def _sound_choice(episode: dict[str, Any], key: str) -> bool:
    """A choice question whose labels, semantics and gold are consistent enough to compare across variants."""
    q = episode["questions"].get(key, {})
    mapping = episode["hidden"].get("option_semantics", {}).get(key)
    if q.get("type") != "choice" or not isinstance(q.get("criteria"), dict) or not mapping:
        return False
    if len(mapping) < 2 or set(mapping) != set(q["criteria"]) or len(set(mapping.values())) != len(mapping):
        return False
    return all(step["gold"].get(key) in set(mapping.values()) for step in episode["steps"])


def visible_request(episode: dict[str, Any], step: dict[str, Any]) -> tuple[str, str]:
    """The digest of a tick's request without its opaque labels, and its gold in visible terms.

    Each choice's criteria become the sorted list of option texts and its gold
    the gold option's text; score levels and level indices stay. Labels are
    drawn per episode, so this is what makes requests of different variants
    comparable.
    """
    request = build_request(episode, step)
    gold = []
    for key, q in request["questions"].items():
        value = step["gold"].get(key)
        if q["type"] == "choice" and isinstance(q.get("criteria"), dict):
            texts = {label: canonical_json(v) for label, v in q["criteria"].items()}
            label_of = {sem: label for label, sem in episode["hidden"].get("option_semantics", {}).get(key, {}).items()}
            q["criteria"] = sorted(texts.values())
            value = texts.get(label_of.get(value))
        gold.append(value)
    return digest(request), canonical_json(gold)


def _live(state: Any, prepared: Sequence[str]) -> Any:
    return {k: v for k, v in state.items() if k not in prepared} if isinstance(state, dict) and prepared else state


def check_families(
    episodes: Iterable[dict[str, Any]],
    report: Report,
    expect_full: bool = True,
    scenarios: dict[str, Scenario] | None = None,
) -> None:
    scenarios = scenarios or {}
    episodes = list(episodes)
    families: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for e in episodes:
        if e["variant"] in families[e["contrast_family"]]:
            report.error(e["episode_id"], "duplicate variant in contrast family")
        families[e["contrast_family"]][e["variant"]] = e

    per_task = Counter()
    language = LanguageSimilarity()
    for name, fam in sorted(families.items()):
        missing = [v for v in VARIANTS if v not in fam]
        if missing:
            (report.error if expect_full else report.warn)(name, f"missing variants {missing}")
        canonical = fam.get("canonical")
        if canonical is None:
            continue
        if len({e["schema_version"] for e in fam.values()}) > 1:
            report.error(name, "variants mix schema versions; rebuild the whole scenario")
            continue
        realtime = is_realtime(canonical)
        scenario = scenarios.get(name)
        prepared = list(scenario.prepared_keys) if scenario is not None else []
        per_task[canonical["task_family"]] += 1
        base_structure = _structure(canonical)
        base_gold = gold_sequence(canonical)
        base_text = [state_text(s["state"]) for s in canonical["steps"]]
        for variant, e in fam.items():
            if e["task_family"] != canonical["task_family"]:
                report.error(e["episode_id"], "task family differs from the canonical variant")
            if _structure(e) != base_structure:
                report.error(e["episode_id"], "question structure / semantic options differ from the canonical variant")
            if realtime:
                differ = [f for f in TIMING_FIELDS if e.get(f) != canonical.get(f)]
                if differ:
                    report.error(e["episode_id"], f"{', '.join(differ)} differ from the canonical variant; every variant shares the scenario's timing and state format")
        if realtime:
            _check_first_options(name, fam, report)
        for variant in INVARIANT_VARIANTS:
            e = fam.get(variant)
            if e is None:
                continue
            if gold_sequence(e) != base_gold:
                report.error(e["episode_id"], "gold trajectory must equal the canonical one")
            if [s["latent"] for s in e["steps"]] != [s["latent"] for s in canonical["steps"]]:
                report.error(e["episode_id"], "latent trajectory must equal the canonical one")
        para = fam.get("paraphrase")
        if para is not None:
            if realtime:
                sims = [language(a["state"], b["state"]) for a, b in zip(canonical["steps"], para["steps"])]
            else:
                sims = [similarity(a, state_text(s["state"])) for a, s in zip(base_text, para["steps"])]
            report.stats.setdefault("paraphrase_similarity", {})[name] = round(_mean(sims), 3)
            if _mean(sims) > PARAPHRASE_SIMILARITY:
                what = "natural-language values" if realtime else "states"
                report.error(para["episode_id"], f"paraphrase {what} are too close to canonical (mean similarity {_mean(sims):.2f})")
            changed = 0
            total = 0
            instruction_sims = {}
            for key in question_keys(canonical):
                if key not in para["questions"]:
                    continue
                q0, q1 = canonical["questions"][key], para["questions"][key]
                if realtime:  # sdb/0.1 keeps the pilot rule: any edit counts as a rewording
                    sim = language(q0["instructions"], q1["instructions"])
                    instruction_sims[key] = round(sim, 3)
                    if sim >= REWORDED:
                        report.error(para["episode_id"], f"{key}: instructions are not reworded (similarity {sim:.2f} to canonical, need < {REWORDED})")
                if not (_sound_choice(canonical, key) and _sound_choice(para, key)):
                    continue
                m0 = {v: k for k, v in canonical["hidden"]["option_semantics"][key].items()}
                m1 = {v: k for k, v in para["hidden"]["option_semantics"][key].items()}
                for sem in m0.keys() & m1.keys():
                    a, b = entry_text(q0["criteria"][m0[sem]]), entry_text(q1["criteria"][m1[sem]])
                    total += 1
                    changed += similarity(a, b) < REWORDED if realtime else a != b
            if realtime:
                report.stats.setdefault("paraphrase_instruction_similarity", {})[name] = instruction_sims
            if total and changed < 0.8 * total:
                bound = f" (similarity < {REWORDED})" if realtime else ""
                report.error(para["episode_id"], f"only {changed}/{total} option texts are reworded{bound}")
        decoy = fam.get("lexical_decoy")
        if decoy is not None:
            choice_keys = [k for k in question_keys(canonical) if _sound_choice(canonical, k) and _sound_choice(decoy, k)]
            if realtime:
                margins = {k: (decoy_margin(canonical, k), decoy_margin(decoy, k)) for k in choice_keys}
                report.stats.setdefault("decoy_margin", {})[name] = {k: (round(a, 2), round(b, 2)) for k, (a, b) in margins.items()}
                if margins and not any(b > a for a, b in margins.values()):
                    report.error(decoy["episode_id"], f"decoy raises the wrong-option overlap of no choice question ({margins})")
                extra = [
                    (s1["t"], value_words(s1["state"]) - value_words(s0["state"]))
                    for s0, s1 in zip(canonical["steps"], decoy["steps"])
                ]
                over = [(t, n) for t, n in extra if n > DECOY_EXTRA_WORDS]
                if over:
                    report.error(decoy["episode_id"], f"decoys add more than {DECOY_EXTRA_WORDS} words at {len(over)} ticks (first t={over[0][0]}: +{over[0][1]})")
            elif choice_keys:
                m_base, m_decoy = decoy_margin(canonical, choice_keys[0]), decoy_margin(decoy, choice_keys[0])
                report.stats.setdefault("decoy_margin", {})[name] = (round(m_base, 2), round(m_decoy, 2))
                if m_decoy <= m_base:
                    report.error(decoy["episode_id"], f"decoy does not raise wrong-option overlap ({m_base:.2f} -> {m_decoy:.2f})")
                if m_decoy <= 0:
                    report.warn(decoy["episode_id"], f"wrong options still overlap less than gold on average ({m_decoy:.2f})")
        for variant in COUNTERFACTUAL_VARIANTS:
            e = fam.get(variant)
            if e is None:
                continue
            seq = gold_sequence(e)
            diff = [t for t in range(len(seq)) if seq[t] != base_gold[t]]
            runs = segments(["d" if t in set(diff) else "s" for t in range(len(seq))])
            flip_runs = [r for r in runs if r[2] == "d"]
            report.stats.setdefault("cf_flips", {})[e["episode_id"]] = {"ticks": len(diff), "runs": len(flip_runs)}
            if variant == "minimal_cf":
                if len(flip_runs) < MINIMAL_CF_RUNS[0]:
                    report.error(e["episode_id"], f"minimal counterfactual flips only {len(flip_runs)} run(s); need >= {MINIMAL_CF_RUNS[0]}")
                elif realtime and len(flip_runs) > MINIMAL_CF_RUNS[1]:
                    report.warn(e["episode_id"], f"minimal counterfactual flips {len(flip_runs)} runs; SPEC 3.4 allows edits at {MINIMAL_CF_RUNS[0]}-{MINIMAL_CF_RUNS[1]} places")
                for a, b, _ in flip_runs:
                    if b - a < MIN_SEGMENT:
                        report.error(e["episode_id"], f"minimal counterfactual flip t={a}..{b - 1} lasts {b - a} ticks; each edit must flip gold for >= {MIN_SEGMENT}")
                if realtime:
                    sims = [language(_live(canonical["steps"][t]["state"], prepared), _live(e["steps"][t]["state"], prepared)) for t in diff]
                else:
                    sims = [similarity(base_text[t], state_text(e["steps"][t]["state"])) for t in diff]
                if sims and min(sims) < MINIMAL_CF_SIMILARITY:
                    report.error(e["episode_id"], f"flipped states differ too much from canonical (min similarity {min(sims):.2f})")
                for t in diff:
                    changed_fields = [
                        k for k in set(e["steps"][t]["latent"]) | set(canonical["steps"][t]["latent"])
                        if e["steps"][t]["latent"].get(k) != canonical["steps"][t]["latent"].get(k)
                    ]
                    if len(changed_fields) > 2:
                        report.warn(e["episode_id"], f"t={t}: {len(changed_fields)} latent fields differ ({changed_fields})")
            else:
                if len(diff) < 3:
                    report.error(e["episode_id"], f"structural counterfactual changes gold on only {len(diff)} ticks")
            if not e["hidden"].get("construction"):
                report.warn(e["episode_id"], "no construction notes for the counterfactual")

    if expect_full:
        for task in TASK_FAMILIES:
            if per_task[task] != 2:
                report.error(task, f"{per_task[task]} base scenarios (expected 2)")

    # One state format, one top-level key order: every tick, both scenarios, all variants (3.2).
    orders: dict[str, tuple[list[str], str]] = {}
    for e in episodes:
        if not is_realtime(e) or not e["steps"] or not isinstance(e["steps"][0].get("state"), dict):
            continue
        keys = list(e["steps"][0]["state"])
        seen = orders.setdefault(e.get("schema_id", ""), (keys, e["episode_id"]))
        if seen[0] != keys:
            report.error(e["episode_id"], f"top-level key order {keys} differs from {seen[1]} ({seen[0]}) under {e.get('schema_id')!r}")

    # The same visible request must never carry two different gold decisions,
    # anywhere in the dataset: compared without labels (drawn per episode), so
    # canonical and its counterfactuals are compared too.
    seen_requests: dict[str, tuple[str, str]] = {}
    for fam in families.values():
        for e in fam.values():
            for step in e["steps"]:
                d, g = visible_request(e, step)
                if d in seen_requests and seen_requests[d][0] != g:
                    report.error(f"{e['episode_id']} t={step['t']}", f"identical request to {seen_requests[d][1]} but different gold")
                seen_requests.setdefault(d, (g, f"{e['episode_id']} t={step['t']}"))


def _check_first_options(name: str, fam: dict[str, dict[str, Any]], report: Report) -> None:
    """Warn when one option of a choice is listed first in more variants than an even spread allows (position bias)."""
    canonical = fam["canonical"]
    for key in question_keys(canonical):
        if not all(_sound_choice(e, key) for e in fam.values()):
            continue
        firsts = Counter(e["hidden"]["option_semantics"][key][next(iter(e["questions"][key]["criteria"]))] for e in fam.values())
        n = len(canonical["questions"][key]["criteria"])
        sem, count = firsts.most_common(1)[0]
        if count > -(-len(fam) // n):
            report.warn(name, f"{key}: option {sem!r} is listed first in {count} of {len(fam)} variants; rebuild (authoring.option_order balances it)")


def _summary(values: list[int]) -> dict[str, int]:
    values = sorted(values)
    return {"min": values[0], "median": values[len(values) // 2], "max": values[-1]}


def validate(
    episodes: Sequence[dict[str, Any]], expect_full: bool = True, scenarios: Iterable[Scenario] = ()
) -> Report:
    """Validate episodes of either schema version.

    sdb/0.2 episodes need their Scenario class (state schema, prepared keys,
    machine fields, ``check()``): taken from ``scenarios`` if given there, else
    loaded from the family registry.
    """
    report = Report()
    for e in episodes:
        check_episode(e, report)
    index = resolve_scenarios(episodes, report, scenarios)
    cache: dict[str, Any] = {}
    for e in episodes:
        if not is_realtime(e) or any(k not in e for k in BASE_FIELDS + REALTIME_FIELDS):
            continue
        scenario = index.get(e["contrast_family"])
        if scenario is None:
            report.error(e["episode_id"], f"no scenario class for {e['contrast_family']!r}; sdb/0.2 checks need it")
            continue
        check_state_format(e, scenario, report, cache)
        check_generator(e, scenario, report)
    check_families(episodes, report, expect_full=expect_full, scenarios=index)
    for key in ("state_words", "live_words"):
        words = report.stats.pop(key, [])
        if words:
            report.stats[key] = _summary(words)
    report.stats["episodes"] = len(episodes)
    report.stats["steps"] = sum(len(e["steps"]) for e in episodes)
    return report
