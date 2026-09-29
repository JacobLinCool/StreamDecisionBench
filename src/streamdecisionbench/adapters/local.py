"""In-process reference models that speak the System One format.

These are sanity baselines and test fixtures, not shortcut audits (see
``streamdecisionbench.audit`` for those):

* ``random``   - uniform over options; the chance floor.
* ``first``    - always the first listed option. sdb/0.2 fixes the option
                 order per episode, so this is one fixed option all episode;
                 sdb/0.1 reshuffles it every tick.
* ``sticky``   - answers once at random per episode and never changes; the
                 degenerate "never switch" controller.
* ``lexical``  - picks the option sharing the most content words with the state.
* ``oracle``   - looks gold up by request digest; proves metrics reach their
                 ceiling. ``oracle-noisy:P`` corrupts each answer with probability P;
                 ``oracle-lag:K`` / ``oracle-lead:K`` answer with the gold of K
                 ticks earlier / later, calibrating the temporal metrics.
* ``lagged-sticky:K`` - holds the previous gold, K ticks late (the oracle lagged
                 by K, default 3, just outside the transition tolerance): the
                 decision-13 baseline of a controller that only follows events.
* ``copy-human`` - the decision the humans' own latest actions imply (slide
                 clicks, mics, playback), from the family's map in
                 ``audit.heuristics``; the decision-13 echo baseline.

Randomness is seeded by the request itself (for ``sticky``, the episode's
first request), never by call counters or session tokens, so a reference run
gives the same answers at any concurrency.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from streamdecisionbench.adapters.base import StatelessAdapter
from streamdecisionbench.authoring import seeded
from streamdecisionbench.jev import make_answer
from streamdecisionbench.schema import build_request, digest, entry_text, state_text

STOPWORDS = frozenset(
    """a an the and or but if then else of to in on at by for with from as is are was were be been being
    it its this that these those there here into onto over under about after before while during not no
    yes do does did done has have had can could should would will shall may might must than so such
    any all each every some more most other same own only just also very too now still yet again
    i you he she we they them his her their our your my me us who whom which what when where why how
    up down out off one two""".split()
)

_WORD = re.compile(r"[a-z0-9]+")


def content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


def _uniform(question: dict[str, Any]) -> dict[str, Any]:
    if question["type"] == "choice":
        return make_answer(question, {k: 1.0 for k in question["criteria"]})
    if question["type"] == "score":
        return make_answer(question, {str(i): 1.0 for i in range(len(question["criteria"]))})
    return make_answer(question, 0.5)


def _one_hot(question: dict[str, Any], label: Any, mass: float = 1.0) -> dict[str, Any]:
    if question["type"] == "noul":
        return make_answer(question, mass if label else 1 - mass)
    keys = list(question["criteria"]) if question["type"] == "choice" else [str(i) for i in range(len(question["criteria"]))]
    rest = (1 - mass) / max(len(keys) - 1, 1)
    return make_answer(question, {k: (mass if k == str(label) else rest) for k in keys})


class RandomAdapter(StatelessAdapter):
    name = "random"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        rng = seeded("random", self.seed, digest(request))
        out = {}
        for key, q in request["questions"].items():
            if q["type"] == "choice":
                out[key] = _one_hot(q, rng.choice(list(q["criteria"])), 0.6)
            elif q["type"] == "score":
                out[key] = _one_hot(q, rng.randrange(len(q["criteria"])), 0.6)
            else:
                out[key] = make_answer(q, rng.random())
        return out


class FirstOptionAdapter(StatelessAdapter):
    name = "first"

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for key, q in request["questions"].items():
            if q["type"] == "choice":
                out[key] = _one_hot(q, next(iter(q["criteria"])), 0.9)
            elif q["type"] == "score":
                out[key] = _one_hot(q, 0, 0.9)
            else:
                out[key] = make_answer(q, 0.9)
        return out


class StickyAdapter(StatelessAdapter):
    """Commits to one random decision at the start of each episode and holds it."""

    name = "sticky"

    def __init__(self, seed: int = 0):
        self.seed = seed
        self.memory: dict[str, Any] = {}

    def start_episode(self, session: str) -> None:
        self.memory = {}

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        rng = seeded("sticky", self.seed, digest(request))  # only draws on the episode's first request
        out = {}
        for key, q in request["questions"].items():
            if key not in self.memory:
                if q["type"] == "choice":
                    self.memory[key] = rng.choice(sorted(q["criteria"]))
                elif q["type"] == "score":
                    self.memory[key] = rng.randrange(len(q["criteria"]))
                else:
                    self.memory[key] = rng.random() < 0.5
            out[key] = _one_hot(q, self.memory[key], 0.9)
        return out


class LexicalAdapter(StatelessAdapter):
    """Content-word overlap between the state and each option description."""

    name = "lexical"

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        words = set(content_words(state_text(request["state"])))
        out = {}
        for key, q in request["questions"].items():
            if q["type"] == "choice":
                weights = {k: 1.0 + len(words & set(content_words(entry_text(v)))) for k, v in q["criteria"].items()}
                out[key] = make_answer(q, {k: w**3 for k, w in weights.items()})
            elif q["type"] == "score":
                weights = {str(i): 1.0 + len(words & set(content_words(entry_text(v)))) for i, v in enumerate(q["criteria"])}
                out[key] = make_answer(q, {k: w**3 for k, w in weights.items()})
            else:
                crit = q.get("criteria") or {}
                yes = len(words & set(content_words(entry_text(crit.get("true")))))
                no = len(words & set(content_words(entry_text(crit.get("false")))))
                out[key] = make_answer(q, 0.5 if yes == no else (0.7 if yes > no else 0.3))
        return out


class CopyHumanAdapter(StatelessAdapter):
    """Answers with ``audit.heuristics.HEURISTICS["copy-human"]`` of the request's family.

    The map reads only the state; like the oracle, the adapter finds the
    request's episode by digest, but only to know its family and to turn the
    map's semantic answers into that episode's labels. A question the map
    leaves open gets its first listed option.
    """

    name = "copy-human"

    def __init__(self, episodes: Iterable[dict[str, Any]]):
        from streamdecisionbench.audit.heuristics import HEURISTICS, semantic_options

        maps = HEURISTICS["copy-human"]
        episodes = list(episodes)
        missing = sorted({e["task_family"] for e in episodes} - set(maps))
        if missing:
            raise ValueError(f"copy-human has no human-action map for {missing}; select families with --family ({sorted(maps)})")
        self.table: dict[str, tuple[Any, dict[str, set[str]], dict[str, str], dict[str, dict[str, str]]]] = {}
        for episode in episodes:
            labels = {qid: {sem: label for label, sem in m.items()} for qid, m in episode["hidden"]["option_semantics"].items()}
            entry = (maps[episode["task_family"]], semantic_options(episode), episode["hidden"]["question_keys"], labels)
            for step in episode["steps"]:
                self.table[digest(build_request(episode, step))] = entry

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        ref = digest(request)
        if ref not in self.table:
            raise KeyError("copy-human has no episode for this request")
        heuristic, options, keys, labels = self.table[ref]
        decided = heuristic(request["state"], options)
        out = {}
        for qid, q in request["questions"].items():
            value = decided.get(keys.get(qid, qid))
            if q["type"] == "choice":
                label = labels.get(qid, {}).get(value, next(iter(q["criteria"])))
            else:
                label = value if value is not None else 0
            out[qid] = _one_hot(q, label, 0.9)
        return out


class OracleAdapter(StatelessAdapter):
    """Answers from gold. Test fixture only: it proves the harness and metrics.

    ``shift`` answers with the gold of ``shift`` ticks later (negative: earlier),
    clamped to the episode's first and last tick. A shifted oracle recognises
    its stream from the requests seen since ``start_episode``, so it needs the
    in-process protocol (every tick, in order); ``fork`` gives each worker its
    own stream memory over shared gold tables.
    """

    def __init__(self, episodes: Iterable[dict[str, Any]], noise: float = 0.0, seed: int = 0, shift: int = 0):
        self.noise = noise
        self.seed = seed
        self.shift = shift
        self.name = f"oracle-noisy:{noise:g}" if noise else "oracle"
        if shift:
            self.name = f"oracle-{'lead' if shift > 0 else 'lag'}:{abs(shift)}"
        self.table: dict[str, dict[str, Any]] = {}  # request digest -> gold in wire terms
        self.streams: dict[str, list[str]] = {}  # episode id -> request digest per tick
        self.candidates: list[str] = []  # episodes whose requests match this stream so far
        self.seen = 0
        for episode in episodes:
            reverse = {
                qid: {sem: label for label, sem in mapping.items()}
                for qid, mapping in episode["hidden"]["option_semantics"].items()
            }
            stream = []
            for step in episode["steps"]:
                key = digest(build_request(episode, step))
                gold = {}
                for qid, value in step["gold"].items():
                    gold[qid] = reverse[qid][value] if qid in reverse else value
                self.table[key] = gold
                stream.append(key)
            self.streams[episode["episode_id"]] = stream

    def fork(self) -> OracleAdapter:
        """A fresh adapter with its own stream memory, sharing this one's gold tables."""
        other = copy.copy(self)
        other.candidates, other.seen = [], 0
        return other

    def start_episode(self, session: str) -> None:
        self.candidates, self.seen = [], 0

    def _gold(self, ref: str) -> dict[str, Any]:
        if ref not in self.table:
            raise KeyError("oracle has no gold for this request")
        if not self.shift:
            return self.table[ref]
        t, self.seen = self.seen, self.seen + 1
        pool = self.candidates if t else list(self.streams)
        self.candidates = [e for e in pool if t < len(self.streams[e]) and self.streams[e][t] == ref]
        if not self.candidates:
            raise KeyError("shifted oracle: ticks must arrive in order after start_episode")
        stream = self.streams[self.candidates[0]]
        return self.table[stream[min(max(t + self.shift, 0), len(stream) - 1)]]

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        ref = digest(request)
        gold = self._gold(ref)
        rng = seeded("oracle", self.seed, ref)
        out = {}
        for key, q in request["questions"].items():
            label = gold[key]
            if self.noise and rng.random() < self.noise:
                if q["type"] == "choice":
                    label = rng.choice([k for k in q["criteria"] if k != label] or [label])
                elif q["type"] == "score":
                    label = rng.choice([i for i in range(len(q["criteria"])) if i != label] or [label])
                else:
                    label = not label
            out[key] = _one_hot(q, label, 0.95)
        return out
