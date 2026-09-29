"""Shortcut audits: how far do surface-similarity methods get without understanding?

Every method sees what a model sees (state text and option texts), never the
instructions' logic. Cross-scenario methods are evaluated with
leave-one-contrast-family-out folds (DESIGN.md section 10): a held-out scenario's
five variants are never in training.

Methods
  bm25, tfidf           lexical match of the state against each option text
  cos:<emb>             embedding cosine between state and option text
  knn<k>:<emb>          k nearest training states vote for the current option most
                        similar to each neighbour's gold option text
  probe:<emb>           logistic regression over (state, option) embedding features,
                        trained to recognise gold pairs
  pairmlp:<emb>         a shallow MLP over the same pair features (a cheap stand-in
                        for a state-action cross encoder)
Within-scenario analyses
  within-knn:<emb>      nearest neighbour among the *other* variants of the same
                        scenario, copying its gold; tests whether contrast variants
                        defeat surface similarity (see the cf_flip breakdown)
Family heuristics (``audit.heuristics``; no training, no embeddings)
  copy-human            the decision the humans' latest actions imply (decision 13)
  nearest-unit          presentation's "latest content phrase -> nearest unit"
A heuristic answers only the questions (and families) it covers: its question
accuracy and per-question breakdown are over those items (``coverage`` gives
their share), and its decision accuracy and SBA over ticks and episodes it
covers completely (None when there are none).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from streamdecisionbench.audit.heuristics import HEURISTICS, semantic_options
from streamdecisionbench.schema import entry_text, question_keys, state_text

EMBEDDERS = {
    "e5": ("intfloat/multilingual-e5-small", "query: ", "passage: "),
    "bge": ("BAAI/bge-m3", "", ""),
    "qwen": ("Qwen/Qwen3-Embedding-0.6B", "", ""),
}

_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass
class Item:
    episode_id: str
    scenario: str
    family: str
    variant: str
    t: int
    qid: str
    kind: str  # choice | score | noul
    state: str
    option_ids: list[Any]  # semantic ids (choice), level indices (score), [True, False] (noul)
    option_texts: list[str]
    gold: Any
    tags: list[str] = field(default_factory=list)
    role: str = ""  # internal question key (position, cue, ...)


def collect(episodes: Sequence[dict[str, Any]]) -> list[Item]:
    items = []
    for e in episodes:
        semantics = e["hidden"]["option_semantics"]
        for key in question_keys(e):
            q = e["questions"][key]
            if q["type"] == "choice":
                ids = [semantics[key][label] for label in q["criteria"]]
                texts = [entry_text(v) for v in q["criteria"].values()]
            elif q["type"] == "score":
                ids = list(range(len(q["criteria"])))
                texts = [entry_text(v) for v in q["criteria"]]
            else:
                crit = q.get("criteria") or {}
                ids = [True, False]
                texts = [entry_text(crit.get("true")) or "yes", entry_text(crit.get("false")) or "no"]
            for step in e["steps"]:
                items.append(
                    Item(
                        e["episode_id"], e["contrast_family"], e["task_family"], e["variant"], step["t"], key,
                        q["type"], state_text(step["state"]), ids, texts, step["gold"][key], step["event_tags"],
                        e["hidden"].get("question_keys", {}).get(key, key),
                    )
                )
    return items


# ---------------------------------------------------------------------------
# Lexical scorers
# ---------------------------------------------------------------------------


class BM25:
    def __init__(self, corpus: Iterable[str], k1: float = 1.2, b: float = 0.75):
        docs = [tokens(d) for d in corpus]
        self.n = len(docs)
        self.df = Counter(w for d in docs for w in set(d))
        self.avg = sum(len(d) for d in docs) / max(self.n, 1)
        self.k1, self.b = k1, b

    def idf(self, w: str) -> float:
        df = self.df.get(w, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query: str, doc: str) -> float:
        d = tokens(doc)
        tf = Counter(d)
        norm = self.k1 * (1 - self.b + self.b * len(d) / self.avg)
        return sum(self.idf(w) * tf[w] * (self.k1 + 1) / (tf[w] + norm) for w in set(tokens(query)) if w in tf)


def _tfidf_vectors(texts: Sequence[str], bm: BM25) -> list[dict[str, float]]:
    out = []
    for text in texts:
        tf = Counter(tokens(text))
        v = {w: (1 + math.log(c)) * bm.idf(w) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out.append({w: x / norm for w, x in v.items()})
    return out


def _sparse_cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


# ---------------------------------------------------------------------------
# Embeddings (cached on disk)
# ---------------------------------------------------------------------------


class EmbeddingCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def encode(self, name: str, texts: Sequence[str], role: str) -> np.ndarray:
        model_id, q_prefix, p_prefix = EMBEDDERS[name]
        prefix = q_prefix if role == "query" else p_prefix
        unique = sorted(set(texts))
        digest = hashlib.sha256(("\x1e".join(unique) + name + role).encode()).hexdigest()[:16]
        path = self.root / f"{name}-{role}-{digest}.npz"
        if path.exists():
            data = np.load(path, allow_pickle=True)
            table = dict(zip(data["texts"].tolist(), data["vectors"]))
        else:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_id, device=_device())
            model.max_seq_length = min(getattr(model, "max_seq_length", 512) or 512, 512)
            vectors = model.encode([prefix + t for t in unique], batch_size=32, normalize_embeddings=True, show_progress_bar=True)
            np.savez(path, texts=np.array(unique, dtype=object), vectors=vectors)
            table = dict(zip(unique, vectors))
        return np.stack([table[t] for t in texts])


def _device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _argmax(scores: Sequence[float]) -> int:
    best = max(scores)
    return scores.index(best)


def _pair_features(s: np.ndarray, o: np.ndarray, with_raw: bool) -> np.ndarray:
    parts = [s * o, np.abs(s - o), (s * o).sum(axis=-1, keepdims=True)]
    if with_raw:
        parts = [s, o] + parts
    return np.concatenate(parts, axis=-1)


class Audit:
    def __init__(self, episodes: Sequence[dict[str, Any]], cache_dir: Path):
        self.episodes = episodes
        self.items = collect(episodes)
        self.cache = EmbeddingCache(cache_dir)
        self.bm25 = BM25([it.state for it in self.items[:: max(1, len(self.items) // 20000)]] + [t for it in self.items for t in it.option_texts])
        self.predictions: dict[str, list[Any]] = {}

    # Each method returns one predicted option id per item, aligned with self.items.
    def lexical(self) -> None:
        bm = []
        tf = []
        vec_cache: dict[str, dict[str, float]] = {}

        def vec(text: str) -> dict[str, float]:
            if text not in vec_cache:
                vec_cache[text] = _tfidf_vectors([text], self.bm25)[0]
            return vec_cache[text]

        for it in self.items:
            scores = [self.bm25.score(it.state, o) / max(1, len(tokens(o))) ** 0.5 for o in it.option_texts]
            bm.append(it.option_ids[_argmax(scores)])
            sv = vec(it.state)
            tf.append(it.option_ids[_argmax([_sparse_cos(sv, vec(o)) for o in it.option_texts])])
        self.predictions["bm25"] = bm
        self.predictions["tfidf"] = tf

    def _embed(self, name: str) -> tuple[np.ndarray, list[np.ndarray]]:
        states = self.cache.encode(name, [it.state for it in self.items], "query")
        all_options = sorted({o for it in self.items for o in it.option_texts})
        table = dict(zip(all_options, self.cache.encode(name, all_options, "passage")))
        options = [np.stack([table[o] for o in it.option_texts]) for it in self.items]
        return states, options

    def embedding_methods(self, name: str, ks: Sequence[int] = (1, 5, 20), probes: bool = True) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.neural_network import MLPClassifier

        S, O = self._embed(name)
        n = len(self.items)
        cos = [self.items[i].option_ids[int(np.argmax(O[i] @ S[i]))] for i in range(n)]
        self.predictions[f"cos:{name}"] = cos

        scenarios = sorted({it.scenario for it in self.items})
        idx_by_scen = defaultdict(list)
        for i, it in enumerate(self.items):
            idx_by_scen[it.scenario].append(i)
        gold_text = []
        for it in self.items:
            gold_text.append(it.option_texts[it.option_ids.index(it.gold)])
        gold_opt_emb = np.stack([O[i][self.items[i].option_ids.index(self.items[i].gold)] for i in range(n)])

        knn_preds = {k: [None] * n for k in ks}
        probe_pred = [None] * n
        mlp_pred = [None] * n
        # One state per (episode, t) for neighbour search, to avoid counting a
        # tick once per question.
        kmax = max(ks)
        for held in scenarios:
            test = idx_by_scen[held]
            train = [i for s in scenarios if s != held for i in idx_by_scen[s]]
            train_arr = np.array(train)
            block = S[np.array(test)] @ S[train_arr].T  # (test, train) cosine
            top = np.argpartition(-block, kth=min(kmax, block.shape[1] - 1), axis=1)[:, :kmax]
            for row, i in enumerate(test):
                order = top[row][np.argsort(-block[row, top[row]])]
                for k in ks:
                    neigh = train_arr[order[:k]]
                    weights = np.clip(block[row, order[:k]], 0.0, None)
                    votes = (O[i] @ gold_opt_emb[neigh].T) @ weights
                    knn_preds[k][i] = self.items[i].option_ids[int(np.argmax(votes))]
            if probes:
                lr_rows = train[:: max(1, len(train) // 6000)]
                X = np.concatenate([_pair_features(np.repeat(S[i][None], len(O[i]), 0), O[i], with_raw=False) for i in lr_rows])
                y = np.array([1 if oid == self.items[i].gold else 0 for i in lr_rows for oid in self.items[i].option_ids])
                lr = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
                lr.fit(X, y)
                mlp_rows = train[:: max(1, len(train) // 3000)]
                Xr = np.concatenate([_pair_features(np.repeat(S[i][None], len(O[i]), 0), O[i], with_raw=True) for i in mlp_rows])
                yr = np.array([1 if oid == self.items[i].gold else 0 for i in mlp_rows for oid in self.items[i].option_ids])
                mlp = MLPClassifier(hidden_layer_sizes=(256,), max_iter=200, early_stopping=True, random_state=0)
                mlp.fit(Xr, yr)
                for i in test:
                    s_rep = np.repeat(S[i][None], len(O[i]), 0)
                    p = lr.decision_function(_pair_features(s_rep, O[i], with_raw=False))
                    probe_pred[i] = self.items[i].option_ids[int(np.argmax(p))]
                    q = mlp.predict_proba(_pair_features(s_rep, O[i], with_raw=True))[:, 1]
                    mlp_pred[i] = self.items[i].option_ids[int(np.argmax(q))]
        for k in ks:
            self.predictions[f"knn{k}:{name}"] = knn_preds[k]
        if probes:
            self.predictions[f"probe:{name}"] = probe_pred
            self.predictions[f"pairmlp:{name}"] = mlp_pred

        # Within-scenario nearest neighbour across variants.
        within = [None] * n
        for scen, idx in idx_by_scen.items():
            by_variant = defaultdict(list)
            for i in idx:
                by_variant[self.items[i].variant].append(i)
            for i in idx:
                it = self.items[i]
                pool = np.array([j for v, js in by_variant.items() if v != it.variant for j in js if self.items[j].qid == it.qid])
                sims = S[pool] @ S[i]
                within[i] = self.items[pool[int(np.argmax(sims))]].gold
        self.predictions[f"within-knn:{name}"] = within

    def family_heuristics(self) -> None:
        """Every ``audit.heuristics`` method on the families it covers; None elsewhere."""
        episodes = {e["episode_id"]: e for e in self.episodes}
        for name, by_family in HEURISTICS.items():
            answers: dict[tuple[str, int], dict[str, Any]] = {}
            preds = []
            for it in self.items:
                heuristic = by_family.get(it.family)
                if heuristic is None:
                    preds.append(None)
                    continue
                if (it.episode_id, it.t) not in answers:
                    e = episodes[it.episode_id]
                    answers[(it.episode_id, it.t)] = heuristic(e["steps"][it.t]["state"], semantic_options(e))
                preds.append(answers[(it.episode_id, it.t)].get(it.role))
            self.predictions[name] = preds

    def majority_oracle(self) -> None:
        """Each episode's most frequent gold decision at every tick.

        Not a shortcut a model could learn directly, but the ceiling of any
        prior-only strategy ("always pick the idle action"): streams have long
        stable regions, so this bounds what a method gains without reading the
        state.
        """
        by_ep: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for it in self.items:
            by_ep[(it.episode_id, it.qid)][json.dumps(it.gold)] += 1
        self.predictions["majority-oracle"] = [
            json.loads(by_ep[(it.episode_id, it.qid)].most_common(1)[0][0]) for it in self.items
        ]

    # -----------------------------------------------------------------------
    def report(self, strong: float | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"items": len(self.items), "methods": {}}
        chance_q = [1.0 / len(it.option_ids) for it in self.items]
        out["chance_question_accuracy"] = float(np.mean(chance_q))
        # Composite chance per tick: product over the tick's questions.
        by_tick: dict[tuple[str, int], list[int]] = defaultdict(list)
        for i, it in enumerate(self.items):
            by_tick[(it.episode_id, it.t)].append(i)
        chance_c = [float(np.prod([chance_q[i] for i in idx])) for idx in by_tick.values()]
        out["chance_decision_accuracy"] = float(np.mean(chance_c))
        # Segment-balanced accuracy needs the gold composite per tick.
        from streamdecisionbench.metrics import segments

        ticks_by_episode: dict[str, list[tuple[int, list[int]]]] = defaultdict(list)
        for (eid, t), idx in by_tick.items():
            ticks_by_episode[eid].append((t, idx))
        for v in ticks_by_episode.values():
            v.sort()

        def sba(hits: list[bool], covered: set[str]) -> float | None:
            scores = []
            for eid, ticks in ticks_by_episode.items():
                if eid not in covered:
                    continue
                gold = [json.dumps([self.items[i].gold for i in sorted(idx, key=lambda i: self.items[i].qid)]) for _, idx in ticks]
                ok = [all(hits[i] for i in idx) for _, idx in ticks]
                segs = segments(gold)
                scores.append(sum(sum(ok[a:b]) / (b - a) for a, b, _ in segs) / len(segs))
            return float(np.mean(scores)) if scores else None

        def mean_or_none(values: list[bool]) -> float | None:
            return float(np.mean(values)) if values else None

        out["chance_sba"] = out["chance_decision_accuracy"]
        for method, preds in sorted(self.predictions.items()):
            hits = [p is not None and p == it.gold for p, it in zip(preds, self.items)]
            answered = [p is not None for p in preds]
            ticks = [idx for idx in by_tick.values() if all(answered[i] for i in idx)]
            covered = {eid for eid, ts in ticks_by_episode.items() if all(answered[i] for _, idx in ts for i in idx)}
            res: dict[str, Any] = {
                "coverage": float(np.mean(answered)),
                "question_accuracy": mean_or_none([h for h, a in zip(hits, answered) if a]),
                "decision_accuracy": mean_or_none([all(hits[i] for i in idx) for idx in ticks]),
                "sba": sba(hits, covered),
            }
            for tag in ("transition", "cf_flip", "distractor", "minimal_change", "steady"):
                sel = [h for h, a, it in zip(hits, answered, self.items) if a and tag in it.tags]
                if sel:
                    res[f"question_accuracy@{tag}"] = float(np.mean(sel))
            for field_name, key in (("by_family", "family"), ("by_variant", "variant"), ("by_question", "role")):
                groups = defaultdict(list)
                for h, a, it in zip(hits, answered, self.items):
                    if a:
                        groups[getattr(it, key)].append(h)
                res[field_name] = {k: float(np.mean(v)) for k, v in sorted(groups.items())}
            if strong is not None and res["sba"] is not None and not method.startswith("within"):
                # DESIGN.md section 10 target: a shortcut should capture no more than
                # about a quarter of the gain from chance to a strong semantic model.
                c = out["chance_sba"]
                res["capture_of_strong_gain_sba"] = (res["sba"] - c) / (strong - c) if strong > c else None
            out["methods"][method] = res
        return out


def run_audit(
    episodes: Sequence[dict[str, Any]],
    cache_dir: Path,
    embedders: Sequence[str] = ("e5", "bge", "qwen"),
    strong: float | None = None,
    probes: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    audit = Audit(episodes, cache_dir)
    log(f"{len(audit.items)} question-items over {len(episodes)} episodes")
    audit.lexical()
    audit.majority_oracle()
    audit.family_heuristics()
    log("lexical and family heuristics done")
    for name in embedders:
        audit.embedding_methods(name, probes=probes)
        log(f"{name} done")
    return audit.report(strong=strong)
