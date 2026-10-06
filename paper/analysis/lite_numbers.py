"""Write the paper's number and table macros from the recorded SDB Lite runs.

    uv run python paper/analysis/lite_numbers.py           # from the repository root
    uv run python paper/analysis/lite_numbers.py --list    # also print every macro, value and source

Outputs: paper/generated/numbers.tex (one macro per stated number, each with its
source) and paper/generated/tables.tex (table bodies built from those macros).

Every run recomputes from the frozen files and makes no network request:

1. The primary and network-removed scores are recomputed from each run's own event
   log with the benchmark's scorer (`rescore_run`) and network estimator
   (`scripts/lite/network.py`, fixed seed); the published analysis files must match.
2. Untimed accuracy, paired counts, latency and token statistics are recomputed
   independently from the raw events and the frozen episodes; the executable public
   reference is re-evaluated on every released state.
3. Counterfactual replays of the recorded runs, with the benchmark's replay scorer
   (`normalized_episode_scores`): the reference answers delivered with each model's
   recorded delays (timing ceiling), and every recorded delay scaled by a constant
   (equivalent to another release interval). No model is queried.
4. The Figure 1 window is recomputed with the rule in lite_window.py.
5. Audit counts are derived from paper/notes/audit_record.json.
6. Family macro identities and partitions are checked; FACTS.md is regenerated from verified values.
7. Setting counts, the mean orderings the prose states, and Astra low's pass-1 untimed miss (its state,
   the preceding one and the audit finding on the same question) are checked against the runs, the
   frozen states and the audit record.

Disagreements are reported before publishing number and table macros. Frozen runs are read-only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # imports src/ and scripts/ read-only; leave no bytecode behind

import argparse  # noqa: E402
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
from collections import Counter  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from decimal import ROUND_HALF_UP, Decimal  # noqa: E402
from pathlib import Path  # noqa: E402
from statistics import mean, median  # noqa: E402

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "lite"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lite_window import scan as window_scan  # noqa: E402
from network import network_adjustment  # noqa: E402
from streamdecisionbench import jev as jev_contract  # noqa: E402
from streamdecisionbench.lite.__main__ import rescore_run  # noqa: E402
from streamdecisionbench.lite.retry_scoring import normalized_episode_scores  # noqa: E402
from streamdecisionbench.lite.tasks import assembly, debugging, support, presenter
from streamdecisionbench.lite.reference_scoring import family_mean  # noqa: E402

OUT = ROOT / "paper" / "generated"
DATA = "data/lite/v1"
POLICY_PATH = "paper/analysis/evaluation_policy.json"
POLICY = json.loads((ROOT / POLICY_PATH).read_text())
RECORDING_INTERVAL = POLICY["recording_interval_s"]
FACTS = "paper/notes/audit_summary.md"
AUDIT = "paper/notes/audit_record.json"
PROTOCOL = "docs/lite/PROTOCOL.md"
RESULTS_README = "docs/lite/results/README.md"
RUNTIME = "src/streamdecisionbench/lite/runtime.py"
# Counterfactual delay scales: every recorded delay multiplied by the factor, which is
# equivalent to dividing the release interval (and every event time) by it.
DELAY_SCALES = (("Half", Decimal("0.5")), ("TwoThirds", Decimal(2) / Decimal(3)),
                ("ThreeHalves", Decimal("1.5")), ("Double", Decimal(2)))
# Figure 5 (appendix): the support-call state released when the hold threshold is reached.
EXAMPLE = {"episode": "lite_support_a", "t": 33}
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}

# Macro prefix, results folder under docs/lite/results, run folder under runs/.
# Order: the GPT settings together (each GPT-5.6 model at low then no reasoning, then GPT-6 Astra, whose lowest
# accepted effort is low), then Jev. Tables, FACTS columns and figures follow it.
MODELS = (
    ("Luna", "four-family/gpt-5.6-luna-low", "lite-v1-gpt-5.6-luna-low-four-family-retry-v1"),
    ("LunaNone", "four-family/gpt-5.6-luna-none", "lite-v1-gpt-5.6-luna-none-four-family-retry-v1"),
    ("Terra", "four-family/gpt-5.6-terra-low", "lite-v1-gpt-5.6-terra-low-four-family-retry-v1"),
    ("TerraNone", "four-family/gpt-5.6-terra-none", "lite-v1-gpt-5.6-terra-none-four-family-retry-v1"),
    ("Astra", "four-family/gpt-6-astra-low", "lite-v1-gpt-6-astra-low-four-family-retry-v1"),
    ("Jev", "four-family/jev-latest", "lite-v1-jev-latest-four-family-retry-v1"),
)
# Standard-tier list prices in USD per 1M tokens (input, cached input, output, source, date read), from the
# providers' official pages as documented in paper/notes/pricing.md. OpenAI bills reasoning tokens as output
# (usage.output_tokens includes them); TypeSafe bills input only ("Output tokens are free") and reports no
# cached tokens.
PRICING_NOTE = "paper/notes/pricing.md"
PRICES = {
    ("openai", "gpt-5.6-luna"): (Decimal("0.20"), Decimal("0.02"), Decimal("1.20"),
                                 "developers.openai.com/api/docs/pricing (gpt-5.6-luna, Standard, short context)", "2026-09-29"),
    ("openai", "gpt-5.6-terra"): (Decimal("2.00"), Decimal("0.20"), Decimal("12.00"),
                                  "developers.openai.com/api/docs/pricing (gpt-5.6-terra, Standard, short context)", "2026-09-29"),
    ("openai", "gpt-6-astra"): (Decimal("10.00"), Decimal("1.00"), Decimal("50.00"),
                                "developers.openai.com/api/docs/pricing (gpt-6-astra, Standard, short context)", "2026-09-30"),
    ("typesafe", "jev-latest"): (Decimal("0.042"), None, Decimal("0"), "docs.typesafe.ai/models (Jev; output tokens free)",
                                 "2026-09-29"),
}
# FACTS "Results" column header for each macro prefix.
FACTS_COLUMNS = {"Luna": "Luna low", "LunaNone": "Luna none", "Terra": "Terra low", "TerraNone": "Terra none",
                 "Astra": "Astra low", "Jev": "Jev"}
# Candidate, baseline, folder holding comparison.json (Astra low is paired with Terra low, the most accurate
# untimed of the other settings).
COMPARISONS = (("Terra", "Luna", "gpt-5.6-terra-low"), ("Jev", "Luna", "jev-latest"),
               ("LunaNone", "Luna", "gpt-5.6-luna-none"), ("TerraNone", "Terra", "gpt-5.6-terra-none"),
               ("Astra", "Terra", "gpt-6-astra-low"))
# Astra low's single untimed miss, stated in the paper as validity evidence (checked in astra_macros).
ASTRA_MISS = {"episode": "lite_assembly_a", "t": 32}
FAMILIES = (("Debug", "live_debugging"), ("Assembly", "procedural_coaching"), ("Support", "support_call_assist"), ("Presenter", "presenter_voice_control"))
SCENARIOS = (
    ("DebugA", "Debug", "lite_debugging_a"), ("DebugB", "Debug", "lite_debugging_b"),
    ("AssemblyA", "Assembly", "lite_assembly_a"), ("AssemblyB", "Assembly", "lite_assembly_b"),
    ("SupportA", "Support", "lite_support_a"), ("SupportB", "Support", "lite_support_b"),
    ("PresenterA", "Presenter", "lite_presenter_a"), ("PresenterB", "Presenter", "lite_presenter_b"),
)
REFERENCE = {"live_debugging": debugging, "procedural_coaching": assembly, "support_call_assist": support, "presenter_voice_control": presenter}
REFERENCE_SRC = "src/streamdecisionbench/lite/tasks/{debugging,assembly,support,presenter}.py:reference(state)"
# Default table labels; the paper may define these before \input{generated/tables}.
LABELS = {"LunaRowLabel": "Luna low", "LunaNoneRowLabel": "Luna none", "TerraRowLabel": "Terra low",
          "TerraNoneRowLabel": "Terra none", "AstraRowLabel": "Astra low", "JevRowLabel": "Jev",
          "DebugLabel": "IDE debugging", "AssemblyLabel": "Assembly station", "SupportLabel": "Support call", "PresenterLabel": "Presenter control"}


# --------------------------------------------------------------------------- formatting

def _dec(x) -> Decimal:
    if isinstance(x, bool):
        raise TypeError("boolean is not a number")
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    if not math.isfinite(x):
        raise ValueError(f"non-finite value {x!r}")
    return Decimal(repr(float(x)))


class NumericText(str):
    """Rendered number retaining its exact value for aggregation before rounding."""

    def __new__(cls, text, value, places, is_count=False):
        result = super().__new__(cls, text)
        result.number = _dec(value)
        result.places = places
        result.is_count = is_count
        return result


def fixed(x, places: int) -> str:
    """Half-up rounding of the full-precision decimal value."""
    value = _dec(x).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return NumericText(f"{abs(value) if value == 0 else value:f}", x, places)


def pct(fraction) -> str:
    return fixed(_dec(fraction) * 100, 1)


def shown(fraction) -> Decimal:
    """A fraction as the percentage the paper prints (one decimal, half-up)."""
    return Decimal(pct(fraction))


def points(value) -> str:
    return fixed(value, 1)


def sec(value) -> str:
    return fixed(value, 2)


def sec1(value) -> str:
    """Accumulated error time: one decimal, the resolution one recorded pass supports."""
    return fixed(value, 1)


def word(n: int) -> str:
    """Small counts spelled out for running prose."""
    return WORDS[n]


def ms(value) -> str:
    return fixed(value, 1)


def count(n) -> str:
    if isinstance(n, float):
        if not n.is_integer():
            raise ValueError(f"count is not an integer: {n!r}")
        n = int(n)
    return NumericText(f"{n:,}".replace(",", "{,}") if n >= 10000 else str(n), n, 0, is_count=True)


def exact(x) -> str:
    """Design constants are printed exactly as declared."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def as_count(fraction: float, total: int, what: str) -> int:
    value = fraction * total
    if abs(value - round(value)) > 1e-6:
        raise ValueError(f"{what}: {fraction} x {total} is not a whole number of states")
    return int(round(value))


def tex_text(s: str) -> str:
    return re.sub(r"([&%$#_{}])", r"\\\1", s).replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")


# --------------------------------------------------------------------------- sources and checks

class Source:
    """A JSON file whose values are cited by file and path."""

    def __init__(self, rel: str):
        self.rel = rel
        self.data = json.loads((ROOT / rel).read_text())

    @classmethod
    def from_data(cls, rel, data):
        source = cls.__new__(cls)
        source.rel, source.data = rel, data
        return source

    def get(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value

    def ref(self, *keys, note: str = "") -> str:
        path = "".join(f"[{k}]" if isinstance(k, int) else (f".{k}" if i else k) for i, k in enumerate(keys))
        return f"{self.rel}:{path}" + (f" ({note})" if note else "")


@dataclass(frozen=True)
class Macro:
    name: str
    value: str
    source: str


class Macros:
    def __init__(self):
        self.items: dict[str, Macro] = {}

    def add(self, name: str, value: str, source: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Za-z]*", name):
            raise ValueError(f"macro names use letters only: {name!r}")
        if name in self.items:
            raise ValueError(f"duplicate macro {name}")
        if "\n" in value or "\n" in source:
            raise ValueError(f"macro {name} spans lines")
        self.items[name] = Macro(name, value, source)

    def __contains__(self, name: str) -> bool:
        return name in self.items


class Checks:
    def __init__(self):
        self.failures: list[str] = []
        self.passed = 0

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def equal(self, what: str, got, want) -> None:
        if got == want:
            self.passed += 1
        else:
            self.fail(f"{what}: got {got!r}, expected {want!r}")

    def close(self, what: str, got, want, tol: float = 1e-9) -> None:
        if got is None or want is None:
            self.equal(what, got, want)
        elif abs(got - want) <= tol * max(1.0, abs(want)):
            self.passed += 1
        else:
            self.fail(f"{what}: got {got!r}, expected {want!r}")

    def same(self, what: str, got, want, tol: float = 1e-12) -> None:
        """Deep equality with a numeric tolerance."""
        if isinstance(want, dict) and isinstance(got, dict):
            if set(got) != set(want):
                self.fail(f"{what}: keys differ {sorted(set(got) ^ set(want))}")
                return
            for key in want:
                self.same(f"{what}.{key}", got[key], want[key], tol)
        elif isinstance(want, list) and isinstance(got, list):
            if len(got) != len(want):
                self.fail(f"{what}: length {len(got)} != {len(want)}")
                return
            for i, (a, b) in enumerate(zip(got, want)):
                self.same(f"{what}[{i}]", a, b, tol)
        elif (isinstance(want, (int, float)) and not isinstance(want, bool)
              and isinstance(got, (int, float)) and not isinstance(got, bool)):
            self.close(what, got, want, tol)
        else:
            self.equal(what, got, want)


def sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def compose(spec: dict, answers: dict) -> dict:
    """Independent restatement of the branch composition in PROTOCOL.md."""
    route = answers[spec["route_question"]]
    keys = [spec["route_question"], *spec["always"], *spec["branches"][route]]
    return {key: answers[key] for key in keys}


# --------------------------------------------------------------------------- loading

def load_benchmark(checks: Checks) -> dict:
    manifest = Source(f"{DATA}/manifest.json")
    order = [e["episode_id"] for e in manifest.get("episodes")]
    checks.equal("scenario order", order, [eid for _, _, eid in SCENARIOS])
    episodes = {eid: Source(f"{DATA}/{eid}.json") for eid in order}
    family_by_prefix = dict(FAMILIES)
    for _, family_prefix, eid in SCENARIOS:
        checks.equal(f"{eid} family", episodes[eid].get("task_family"), family_by_prefix[family_prefix])
    derived = {}
    agree = total = 0
    for i, eid in enumerate(order):
        ep = episodes[eid].data
        spec, steps = ep["decision_spec"], ep["steps"]
        gold = [compose(spec, s["gold"]) for s in steps]
        transitions = sum(gold[t] != gold[t - 1] for t in range(1, len(gold)))
        checks.equal(f"{eid} transitions (gold vs manifest)", transitions, manifest.get("episodes", i, "decision_transitions"))
        checks.equal(f"{eid} questions (data vs manifest)", len(ep["questions"]), manifest.get("episodes", i, "questions"))
        checks.equal(f"{eid} steps (data vs manifest)", len(steps), manifest.get("episodes", i, "steps"))
        checks.equal(f"{eid} duration", len(steps) * ep["tick_seconds"], manifest.get("episodes", i, "duration_s"))
        checks.equal(f"{eid} route options vs branches", len(ep["questions"][spec["route_question"]]["criteria"]),
                     len(spec["branches"]))
        checks.equal(f"{eid} routes seen", sorted({s["gold"][spec["route_question"]] for s in steps}),
                     manifest.get("episodes", i, "routes_seen"))
        for key, q in ep["questions"].items():
            checks.equal(f"{eid}.{key} options", len(q["criteria"]), len(ep["option_semantics"][key]))
        module = REFERENCE[ep["task_family"]]
        for s in steps:
            total += 1
            agree += module.reference(copy.deepcopy(s["state"])) == s["gold"]
        derived[eid] = {"consumed": [len(g) for g in gold]}
    checks.equal("executable reference agrees with gold", agree, total)
    return {"manifest": manifest, "episodes": episodes, "order": order, "derived": derived,
            "reference_agree": agree, "reference_total": total}


def events_summary(run_rel: str, bench: dict, checks: Checks) -> dict:
    """Independent statistics from the raw event log and the frozen episodes."""
    responses, releases = {}, {}
    for line in (ROOT / run_rel / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        key = (event["episode_id"], event["t"])
        if event["kind"] == "response":
            if key in responses:
                checks.fail(f"{run_rel}: duplicate response for {key}")
            responses[key] = event
        elif event["kind"] == "release":
            releases[key] = event
    correct, exact_match = {}, {}
    for eid in bench["order"]:
        ep = bench["episodes"][eid].data
        spec = ep["decision_spec"]
        for s in ep["steps"]:
            r = responses[(eid, s["t"])]
            if not r["ok"]:
                checks.fail(f"{run_rel}: unsuccessful final response at {eid} t={s['t']}")
                continue
            decoded = {k: ep["option_semantics"][k][v] for k, v in r["wire_answers"].items()}
            checks.equal(f"{run_rel} {eid} t={s['t']} decoded answers", decoded, r["pred"])
            correct[(eid, s["t"])] = compose(spec, decoded) == compose(spec, s["gold"])
            exact_match[(eid, s["t"])] = decoded == s["gold"]
    ordered = [responses[(eid, t)] for eid in bench["order"] for t in range(len(bench["episodes"][eid].get("steps")))]
    latency = [r["attempts"][-1]["completed_s"] - r["attempts"][-1]["started_s"] for r in ordered]
    usage = [r["usage"] for r in ordered]
    return {"responses": responses, "releases": releases, "correct": correct, "exact": exact_match,
            "latency": latency, "usage": usage, "ok": sum(r["ok"] for r in ordered)}


def saved_fields(got, saved):
    """``got`` restricted to the fields a saved analysis has. The scorer may add fields after a report was
    written; every field the report does have must still match exactly."""
    if isinstance(saved, dict) and isinstance(got, dict):
        return {k: saved_fields(got[k], saved[k]) if k in got else got.get(k) for k in saved}
    if isinstance(saved, list) and isinstance(got, list) and len(saved) == len(got):
        return [saved_fields(a, b) for a, b in zip(got, saved)]
    return got


def network_measurements(report: dict) -> dict:
    """Separate explanatory prose from the complete reproducible fit evidence.

    Historical reports retain their original prose. Every other field, including
    the method, estimator settings, coefficients, uncertainty and replay scores,
    must still reproduce; unknown measurement fields are not discarded.
    """
    documentary = {'assumption', 'interpretation'}
    for key in documentary:
        if not isinstance(report.get(key), str) or not report[key].strip():
            raise ValueError(f'Network report requires documentary field {key}')
    return {key: value for key, value in report.items() if key not in documentary}


def load_model(prefix: str, folder: str, run: str, bench: dict, checks: Checks) -> dict:
    analysis = Source(f"docs/lite/results/{folder}/analysis.json")
    run_rel = f"runs/{run}"
    a = analysis.data
    checks.equal(f"{prefix} dataset hash", a["dataset_hash"], bench["manifest"].get("dataset_hash"))
    checks.equal(f"{prefix} events sha256", a["events_sha256"], sha256(f"{run_rel}/events.jsonl"))
    checks.equal(f"{prefix} analysis run folder", Path(a["run"]).name, Path(run).name)
    # 1. Recompute scores and the network-removed estimate with the benchmark's own code.
    verified = rescore_run(ROOT / run_rel)
    checks.equal(f"{prefix} frozen dataset hash", verified["frozen"]["dataset_manifest"]["dataset_hash"], a["dataset_hash"])
    for i, ep in enumerate(verified["episodes"]):
        checks.equal(f"{prefix} frozen episode {ep['episode_id']} equals {DATA}", ep, bench["episodes"][ep["episode_id"]].data)
    checks.same(f"{prefix} recorded scores vs analysis.json", saved_fields(verified["scores"], a["scores"]), a["scores"])
    checks.same(f"{prefix} rescored raw wall-clock scores vs analysis.json",
                saved_fields(verified["raw_wallclock_scores"], a["raw_wallclock_scores"]), a["raw_wallclock_scores"])
    net = network_adjustment(verified["episodes"], verified["responses"], verified["releases"],
                             generates_text=a["config"].get("provider", "openai") == "openai")
    checks.same(f"{prefix} physical network fit vs analysis.json",
                network_measurements(net), network_measurements(a["network_adjustment"]))
    recorded = verified
    checks.same(f"{prefix} evaluation policy", a["evaluation_policy"], POLICY)
    from lite_auc import compute_auc
    auc_now = compute_auc(verified)
    # Source digests are provenance: a later edit of a source is reported, not a failure.
    for path, digest in a["auc"]["sources_sha256"].items():
        if auc_now["sources_sha256"].get(path) != digest:
            print(f"note: {prefix}: {path} changed after its AUC was computed", file=sys.stderr)
    checks.same(f"{prefix} integrated evaluation",
                {k: v for k, v in auc_now.items() if k != "sources_sha256"},
                {k: v for k, v in a["auc"].items() if k != "sources_sha256"}, 1e-12)
    # 2. Independent statistics from the events.
    ev = events_summary(run_rel, bench, checks)
    ev["recorded_releases"] = ev["releases"]
    ev["releases"] = {(eid, r["t"]): r for eid, rows in verified["releases"].items() for r in rows}
    per = a["scores"]["per_episode"]
    checks.equal(f"{prefix} per-episode order", [x["episode_id"] for x in per], bench["order"])
    for i, eid in enumerate(bench["order"]):
        states = [ev["correct"][(eid, t)] for t in range(per[i]["states"])]
        checks.close(f"{prefix} {eid} untimed (independent)", mean(states), per[i]["untimed_decision_accuracy"])
        checks.close(f"{prefix} {eid} exact match (independent)",
                     mean(ev["exact"][(eid, t)] for t in range(per[i]["states"])), per[i]["all_questions_exact_accuracy"])
        checks.equal(f"{prefix} {eid} reference transitions", per[i]["reference_transitions"],
                     bench["manifest"].get("episodes", i, "decision_transitions"))
        errors = sum(per[i]["error_seconds"].values())
        checks.close(f"{prefix} {eid} in-force = 1 - error/observed", 1 - errors / per[i]["observed_duration_s"],
                     per[i]["time_accuracy"])
        correct_s = sum(x["end_s"] - x["start_s"] for x in per[i]["intervals"] if x["kind"] == "correct")
        checks.close(f"{prefix} {eid} in-force from intervals", correct_s / per[i]["observed_duration_s"], per[i]["time_accuracy"])
    for key in ("untimed_decision_accuracy", "untimed_segment_accuracy", "all_questions_exact_accuracy",
                "time_accuracy", "segment_time_accuracy"):
        checks.close(f"{prefix} overall {key} = scenario mean", family_mean(per, lambda p: p[key]), a["scores"]["overall"][key])
        for _, family in FAMILIES:
            checks.close(f"{prefix} {family} {key} = scenario mean",
                         mean(p[key] for p in per if p["task_family"] == family), a["scores"]["by_family"][family][key])
    values = np.array(ev["latency"])
    for q, key in ((50, "p50"), (95, "p95")):
        checks.close(f"{prefix} latency {key} (independent)", float(np.percentile(values, q)), a["latency_s"][key])
    checks.close(f"{prefix} latency max (independent)", float(values.max()), a["latency_s"]["max"])
    for key in ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens"):
        checks.equal(f"{prefix} usage {key} (independent)", sum(u.get(key) or 0 for u in ev["usage"]), a["usage"][key])
    checks.equal(f"{prefix} valid responses (independent)", ev["ok"], a["retry_reliability"]["successful_logical_requests"])
    checks.equal(f"{prefix} accepted updates = scenario sum", sum(p["accepted_updates"] for p in per), a["accepted_updates"])
    for kind in ("no_decision", "source_correct", "source_incorrect"):
        checks.close(f"{prefix} error seconds {kind} = scenario sum", sum(p["error_seconds"][kind] for p in per),
                     a["error_seconds"][kind])
    # Reconstructed arrivals after the next evidence release (the horizon for the final release).
    late = total = 0
    for i, eid in enumerate(bench["order"]):
        horizon = len(verified["episodes"][i]["steps"]) * verified["episodes"][i]["tick_seconds"]
        for record in per[i]["normalization"]["records"]:
            t = record["t"]
            nxt = ev["releases"][(eid, t + 1)]["release_s"] if (eid, t + 1) in ev["releases"] else horizon
            late += record["normalized_ready_s"] > nxt
            total += 1
    return {"prefix": prefix, "analysis": analysis, "run_rel": run_rel, "events": ev, "late": late, "late_total": total,
            "verified": verified, "recorded": recorded}


# --------------------------------------------------------------------------- macros

def benchmark_macros(m: Macros, bench: dict, checks: Checks) -> None:
    man, eps, order = bench["manifest"], bench["episodes"], bench["order"]
    D = f"{DATA}/*.json"
    families = sorted({eps[e].get("task_family") for e in order})
    per_family = Counter(eps[e].get("task_family") for e in order)
    checks.equal("scenarios per family are equal", len(set(per_family.values())), 1)
    steps = [man.get("episodes", i, "steps") for i in range(len(order))]
    ticks = {eps[e].get("tick_seconds") for e in order}
    horizons = {man.get("episodes", i, "duration_s") for i in range(len(order))}
    checks.equal("one release count", len(set(steps)), 1)
    checks.equal("one release interval", len(ticks), 1)
    checks.equal("one horizon", len(horizons), 1)
    m.add("NumFamilies", count(len(families)), f"{D}:task_family (distinct values)")
    m.add("NumScenarios", count(len(order)), man.ref("episodes", note="count"))
    m.add("ScenariosPerFamily", count(next(iter(per_family.values()))), f"{D}:task_family (scenarios per value)")
    m.add("ReleasesPerScenario", count(steps[0]), man.ref("episodes", "*", "steps"))
    m.add("ReleaseIntervalSec", exact(next(iter(ticks))), f"{D}:tick_seconds")
    m.add("HorizonSec", exact(next(iter(horizons))), man.ref("episodes", "*", "duration_s"))
    m.add("NumStates", count(sum(steps)), man.ref("episodes", "*", "steps", note="sum"))
    m.add("ObservedSecTotal", exact(sum(len(eps[e].get("steps")) * RECORDING_INTERVAL for e in order)),
          man.ref("episodes", "*", "duration_s", note="sum"))
    m.add("DatasetHashShort", man.get("dataset_hash")[:8], man.ref("dataset_hash", note="first 8 hex digits"))
    questions = [len(eps[e].get("questions")) for e in order]
    m.add("QuestionsTotal", count(sum(questions)), f"{D}:questions (count, summed over scenarios)")
    m.add("QuestionsMin", count(min(questions)), f"{D}:questions (count, minimum over scenarios)")
    m.add("QuestionsMax", count(max(questions)), f"{D}:questions (count, maximum over scenarios)")
    m.add("AnswersPerPass", count(sum(q * s for q, s in zip(questions, steps))), f"{D}:questions x steps (summed)")
    routes = [len(eps[e].get("option_semantics", eps[e].get("decision_spec", "route_question"))) for e in order]
    m.add("RouteOptionsMin", count(min(routes)), f"{D}:option_semantics.route (count, minimum)")
    m.add("RouteOptionsMax", count(max(routes)), f"{D}:option_semantics.route (count, maximum)")
    options = [len(v) for e in order for v in eps[e].get("option_semantics").values()]
    m.add("OptionsMin", count(min(options)), f"{D}:option_semantics.* (options per question, minimum)")
    m.add("OptionsMax", count(max(options)), f"{D}:option_semantics.* (options per question, maximum)")
    transitions = [man.get("episodes", i, "decision_transitions") for i in range(len(order))]
    m.add("TransitionsTotal", count(sum(transitions)), man.ref("episodes", "*", "decision_transitions", note="sum"))
    m.add("TransitionsMin", count(min(transitions)), man.ref("episodes", "*", "decision_transitions", note="minimum"))
    m.add("TransitionsMax", count(max(transitions)), man.ref("episodes", "*", "decision_transitions", note="maximum"))
    m.add("SegmentsTotal", count(sum(transitions) + len(order)),
          man.ref("episodes", "*", "decision_transitions", note="sum + one segment per scenario"))
    consumed = [c for e in order for c in bench["derived"][e]["consumed"]]
    m.add("ConsumedAnswersMin", count(min(consumed)), f"{D}:steps[].gold composed by decision_spec (answers, minimum)")
    m.add("ConsumedAnswersMax", count(max(consumed)), f"{D}:steps[].gold composed by decision_spec (answers, maximum)")
    m.add("ReferenceAgreementStates", count(bench["reference_agree"]),
          f"{REFERENCE_SRC} == {D}:steps[].gold (states agreeing, of {bench['reference_total']})")
    for name, family_prefix, eid in SCENARIOS:
        ep, i = eps[eid], order.index(eid)
        route_q = ep.get("decision_spec", "route_question")
        opts = [len(v) for v in ep.get("option_semantics").values()]
        m.add(f"{name}Title", tex_text(ep.get("title")), ep.ref("title"))
        m.add(f"{name}Questions", count(len(ep.get("questions"))), ep.ref("questions", note="count"))
        m.add(f"{name}RouteOptions", count(len(ep.get("option_semantics", route_q))), ep.ref("option_semantics", route_q, note="count"))
        m.add(f"{name}RoutesUsed", count(len(man.get("episodes", i, "routes_seen"))), man.ref("episodes", i, "routes_seen", note="count"))
        m.add(f"{name}OptionsMin", count(min(opts)), ep.ref("option_semantics", note="options per question, minimum"))
        m.add(f"{name}OptionsMax", count(max(opts)), ep.ref("option_semantics", note="options per question, maximum"))
        m.add(f"{name}Transitions", count(man.get("episodes", i, "decision_transitions")), man.ref("episodes", i, "decision_transitions"))
    # Reference segments: their mean length, and how many last a single release.
    segment_lengths, constant_share = [], []
    for eid in order:
        ep = eps[eid].data
        gold = [json.dumps(compose(ep["decision_spec"], s["gold"]), sort_keys=True) for s in ep["steps"]]
        run = 1
        for t in range(1, len(gold)):
            if gold[t] == gold[t - 1]:
                run += 1
            else:
                segment_lengths.append(run)
                run = 1
        segment_lengths.append(run)
        # The best constant policy: the most frequent composed reference decision of the scenario.
        constant_share.append(Counter(gold).most_common(1)[0][1] / len(gold))
    checks.equal("segments counted from gold", len(segment_lengths), sum(transitions) + len(order))
    observed = sum(len(eps[eid].get("steps")) * RECORDING_INTERVAL for eid in order)
    m.add("MeanSegmentSec", fixed(_dec(observed) / len(segment_lengths), 1),
          man.ref("episodes", "*", "duration_s", note="sum / reference segments"))
    m.add("SingleReleaseSegments", count(sum(x == 1 for x in segment_lengths)),
          f"{D}:steps[].gold composed by decision_spec (segments lasting one release)")
    m.add("BaselineBestConstant", pct(mean(constant_share)),
          f"{D}:steps[].gold composed by decision_spec (share of the most frequent decision, mean over scenarios)")
    m.add("BaselineBestConstantMin", pct(min(constant_share)), f"{D}:steps[].gold (most frequent decision share, minimum over scenarios)")
    m.add("BaselineBestConstantMax", pct(max(constant_share)), f"{D}:steps[].gold (most frequent decision share, maximum over scenarios)")
    for name in ("NumFamilies", "ScenariosPerFamily", "NumScenarios"):
        m.add(f"{name}Word", word(int(m.items[name].value)), f"\\{name} spelled out")
    # Figure 5: the released state at which the payment call's hold reaches its threshold.
    ex = eps[EXAMPLE["episode"]]
    t = EXAMPLE["t"]
    state, prev = ex.get("steps", t, "state"), ex.get("steps", t - 1, "state")
    threshold = state["prepared"]["hold_check_ticks"]
    since, now = state["telephony"]["since"], state["clock"]["now"]
    tick_s = RECORDING_INTERVAL
    checks.equal("example state is on hold", state["telephony"]["status"], "hold")
    checks.equal("example state reaches the hold threshold", now - since, threshold)
    checks.equal("example hold action changes at this release",
                 (ex.get("steps", t - 1, "gold", "hold_action"), ex.get("steps", t, "gold", "hold_action")), ("wait", "return_customer"))
    checks.equal("example previous state is under the threshold", prev["clock"]["now"] - prev["telephony"]["since"] < threshold, True)
    claim = [u for u in state["transcript"] if u["speaker"] == "Agent" and u["at"] == since and "long enough" in u["text"]]
    checks.equal("example agent claim at the start of hold", len(claim), 1)
    checks.equal("example time step equals its clock", now, t)
    src = ex.ref("steps", t, "state")
    m.add("ExampleStateStep", exact(now), f"{src}.clock.now (time steps)")
    m.add("ExampleStateSec", exact(now * tick_s), f"{src}.clock.now x tick_seconds")
    m.add("ExampleHoldSinceStep", exact(since), f"{src}.telephony.since (time steps; also the agent's claim, transcript[].at)")
    m.add("ExampleHoldSinceSec", exact(since * tick_s), f"{src}.telephony.since x tick_seconds")
    m.add("SupportAHoldThresholdSteps", exact(threshold), f"{src}.prepared.hold_check_ticks")
    m.add("SupportAHoldThresholdSec", exact(threshold * tick_s), f"{src}.prepared.hold_check_ticks x tick_seconds")
    for family_prefix, family in FAMILIES:
        ids = [eid for _, fp, eid in SCENARIOS if fp == family_prefix]
        for fact, get in (("Questions", lambda e: len(eps[e].get("questions"))),
                          ("RouteOptions", lambda e: len(eps[e].get("option_semantics", eps[e].get("decision_spec", "route_question"))))):
            values = {get(e) for e in ids}
            if len(values) == 1:  # only stated per family when both scenarios agree
                m.add(f"{family_prefix}{fact}", count(values.pop()), f"{DATA}/{{{','.join(ids)}}}.json ({fact}, equal in both scenarios)")


def model_macros(m: Macros, model: dict, bench: dict, checks: Checks) -> None:
    p, A, ev = model["prefix"], model["analysis"], model["events"]
    a = A.data
    run = model["run_rel"]
    events_src = f"{run}/events.jsonl"

    def add_pct(name, *keys, note=""):
        m.add(name, pct(A.get(*keys)), A.ref(*keys, note=note))

    for metric, key in (("Untimed", "untimed_decision_accuracy"), ("UntimedSeg", "untimed_segment_accuracy"),
                        ("ExactMatch", "all_questions_exact_accuracy"), ("InForce", "time_accuracy"),
                        ("InForceSeg", "segment_time_accuracy")):
        add_pct(f"{p}{metric}", "scores", "overall", key)
    states = a["scores"]["states"]
    m.add(f"{p}UntimedStates", count(as_count(a["scores"]["overall"]["untimed_decision_accuracy"], states, p)),
          A.ref("scores", "overall", "untimed_decision_accuracy", note=f"x {states} states"))
    for suffix, bound in (("", "estimate"), ("Low", "low"), ("High", "high")):
        add_pct(f"{p}NetRemoved{suffix}", "network_adjustment", "scores", bound, "overall", "time_accuracy")
        add_pct(f"{p}NetRemovedSeg{suffix}", "network_adjustment", "scores", bound, "overall", "segment_time_accuracy")
        m.add(f"{p}NetSec{suffix}", sec(A.get("network_adjustment", "network_s", bound)), A.ref("network_adjustment", "network_s", bound))
    net = a["network_adjustment"]
    m.add(f"{p}PrefillMsPerKTok", ms(net["prefill_s_per_1k_input_tokens"] * 1000),
          A.ref("network_adjustment", "prefill_s_per_1k_input_tokens", note="x 1000"))
    if net["decode_s_per_output_token"] is not None:
        m.add(f"{p}DecodeMsPerTok", ms(net["decode_s_per_output_token"] * 1000),
              A.ref("network_adjustment", "decode_s_per_output_token", note="x 1000"))
    m.add(f"{p}LatencyFloor", sec(net["latency_floor_s"]), A.ref("network_adjustment", "latency_floor_s"))
    clamped = [net["scores"][b]["clamped_requests"] for b in ("estimate", "low", "high")]
    m.add(f"{p}ClampedRequests", count(max(clamped)),
          A.ref("network_adjustment", "scores", "{estimate,low,high}", "clamped_requests", note="maximum"))
    for metric, key in (("Median", "p50"), ("PNinetyFive", "p95"), ("Max", "max")):
        m.add(f"{p}Latency{metric}", sec(A.get("latency_s", key)), A.ref("latency_s", key))
    m.add(f"{p}LatencyMean", sec(mean(ev["latency"])),
          f"{events_src}:response.attempts[-1].completed_s - started_s (mean over {len(ev['latency'])} responses)")
    m.add(f"{p}LateArrivals", pct(model["late"] / model["late_total"]),
          A.ref("scores", "per_episode", "*", "normalization", "records", "*", "normalized_ready_s",
                note=f"share of {model['late_total']} after the next release_s in {events_src}, or the horizon for the last release"))
    for metric, key in (("InputTok", "input_tokens"), ("OutputTok", "output_tokens"), ("ReasoningTok", "reasoning_tokens")):
        values = [u.get(key) or 0 for u in ev["usage"]]
        m.add(f"{p}{metric}Median", fixed(median(values), 0),
              f"{events_src}:response.usage.{key} (median over {len(values)} responses, half-up)")
        m.add(f"{p}{metric}Total", count(A.get("usage", key)), A.ref("usage", key))
    inputs = [u["input_tokens"] for u in ev["usage"]]
    m.add(f"{p}InputTokMin", count(min(inputs)), f"{events_src}:response.usage.input_tokens (minimum)")
    m.add(f"{p}InputTokMax", count(max(inputs)), f"{events_src}:response.usage.input_tokens (maximum)")
    m.add(f"{p}CachedTokTotal", count(A.get("usage", "cached_tokens")), A.ref("usage", "cached_tokens"))
    # Cost of the recorded pass at list prices: uncached input, cached input and output (reasoning included).
    cfg = a["config"]
    price_in, price_cached, price_out, price_src, price_date = PRICES[(cfg.get("provider", "openai"), cfg["model"])]
    usage = {k: Decimal(A.get("usage", k) or 0) for k in ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")}
    checks.equal(f"{p} reasoning tokens are part of output tokens", usage["reasoning_tokens"] <= usage["output_tokens"], True)
    if price_cached is None:
        checks.equal(f"{p} no cached tokens where no cached price is published", usage["cached_tokens"], 0)
        price_cached = price_in
    million = Decimal(1_000_000)
    cost_in = ((usage["input_tokens"] - usage["cached_tokens"]) * price_in + usage["cached_tokens"] * price_cached) / million
    cost_out = usage["output_tokens"] * price_out / million
    model["cost_usd"] = cost_in + cost_out
    note = f"{A.rel}:usage at {price_src} list prices retrieved {price_date}"
    m.add(f"{p}CostInputUSD", fixed(cost_in, 3), f"{note} (input: uncached x input price + cached x cached price)")
    m.add(f"{p}CostOutputUSD", fixed(cost_out, 3), f"{note} (output tokens, reasoning included, x output price)")
    m.add(f"{p}CostUSD", fixed(cost_in + cost_out, 3), f"{note} (input + output)")
    m.add(f"{p}PriceInput", fixed(price_in, 3), f"{price_src}: USD per 1M input tokens")
    m.add(f"{p}PriceOutput", fixed(price_out, 2), f"{price_src}: USD per 1M output tokens")
    per = a["scores"]["per_episode"]
    observed = sum(x["observed_duration_s"] for x in per)
    errors = a["error_seconds"]
    error_total = sum(errors.values())
    for metric, key in (("NoDecision", "no_decision"), ("Stale", "source_correct"), ("Incorrect", "source_incorrect")):
        m.add(f"{p}Err{metric}Sec", sec1(errors[key]), A.ref("error_seconds", key))
        m.add(f"{p}Err{metric}Pct", pct(family_mean(per, lambda row: row["error_seconds"][key] / row["observed_duration_s"])),
              A.ref("error_seconds", key, note="scenario error fraction, then equal family mean"))
    m.add(f"{p}ErrTotalSec", sec1(error_total), A.ref("error_seconds", note="sum of the three kinds"))
    m.add(f"{p}ObservedSec", sec1(observed), A.ref("scores", "per_episode", "*", "observed_duration_s", note="sum"))
    raw = a["raw_wallclock_scores"]["overall"]["time_accuracy"]
    m.add(f"{p}InForceRecorded", pct(a["scores"]["overall"]["time_accuracy"]), A.ref("scores", "overall", "time_accuracy"))
    m.add(f"{p}InForcePhysical", pct(raw), A.ref("raw_wallclock_scores", "overall", "time_accuracy", note="physical wall-clock trace"))
    m.add(f"{p}ExcludedDispatchSec", sec(a["retry_reliability"]["excluded_dispatch_s"]),
          A.ref("retry_reliability", "excluded_dispatch_s", note="summed over the pass"))
    m.add(f"{p}MaxDispatchLagSec", sec(a["max_dispatch_lag_s"]), A.ref("max_dispatch_lag_s"))
    m.add(f"{p}EventsHash", a["events_sha256"][:16], A.ref("events_sha256", note=f"first 16 hex digits; equals sha256 of {events_src}"))
    m.add(f"{p}StaleShareOfError", pct(family_mean(per, lambda row: row["error_seconds"]["source_correct"] / row["observed_duration_s"]) / (1 - a["scores"]["overall"]["time_accuracy"])),
          A.ref("error_seconds", "source_correct", note="macro-weighted error share / (1 - primary accuracy)"))
    m.add(f"{p}IncorrectShareOfError", pct(family_mean(per, lambda row: row["error_seconds"]["source_incorrect"] / row["observed_duration_s"]) / (1 - a["scores"]["overall"]["time_accuracy"])),
          A.ref("error_seconds", "source_incorrect", note="macro-weighted error share / (1 - primary accuracy)"))
    m.add(f"{p}AcceptedUpdates", count(a["accepted_updates"]), A.ref("accepted_updates"))
    m.add(f"{p}DiscardedUpdates", count(sum(a["discarded_updates"].values())), A.ref("discarded_updates", note="sum over reasons"))
    m.add(f"{p}DiscardedAfterHorizon", count(a["discarded_updates"].get("after_horizon", 0)),
          A.ref("discarded_updates", "after_horizon", note="absent = 0"))
    m.add(f"{p}DiscardedOlder", count(a["discarded_updates"].get("older_than_active", 0)),
          A.ref("discarded_updates", "older_than_active", note="absent = 0"))
    rel = a["retry_reliability"]
    m.add(f"{p}ValidResponses", count(rel["successful_logical_requests"]), A.ref("retry_reliability", "successful_logical_requests"))
    m.add(f"{p}Attempts", count(rel["attempts"]), A.ref("retry_reliability", "attempts"))
    m.add(f"{p}FailedAttempts", count(rel["failed_attempts"]), A.ref("retry_reliability", "failed_attempts"))
    m.add(f"{p}RetriedRequests", count(rel["retried_logical_requests"]), A.ref("retry_reliability", "retried_logical_requests"))
    m.add(f"{p}InactiveOnlyErrors", count(a["scores"]["inactive_only_error_states"]), A.ref("scores", "inactive_only_error_states"))
    overall = a["scores"]["overall"]
    # Differences between printed percentages are taken from the printed (one-decimal) values, so a
    # reader subtracting the two numbers in the text gets the stated difference.
    gap = shown(overall["untimed_decision_accuracy"]) - shown(overall["time_accuracy"])
    if gap < 0:
        checks.fail(f"{p}: in-force accuracy exceeds untimed accuracy; rename {p}UntimedMinusInForce")
    m.add(f"{p}UntimedMinusInForce", points(gap),
          A.ref("scores", "overall", "{untimed_decision_accuracy - time_accuracy}", note="points, from the printed values"))
    for suffix, bound in (("", "estimate"), ("Low", "low"), ("High", "high")):
        gain = shown(net["scores"][bound]["overall"]["time_accuracy"]) - shown(overall["time_accuracy"])
        if gain < 0:
            checks.fail(f"{p}: network removal lowers in-force accuracy ({bound}); rename {p}NetRemovedMinusInForce")
        m.add(f"{p}NetRemovedMinusInForce{suffix}", points(gain),
              A.ref("network_adjustment", "scores", bound, "overall", "time_accuracy", note="minus scores.overall.time_accuracy, points"))
    started = a["started_at_utc"]
    m.add(f"{p}RecordedUTC", f"{started[:10]} {started[11:16]}", A.ref("started_at_utc", note="date and minute"))
    served = a["models_returned"]
    checks.equal(f"{p} one served model", len(served), 1)
    m.add(f"{p}ServedModel", tex_text(next(iter(served))), A.ref("models_returned", note="single key"))
    m.add(f"{p}RequestedModel", tex_text(a["config"]["model"]), A.ref("config", "model"))
    if a["config"]["reasoning_effort"]:
        m.add(f"{p}ReasoningEffort", a["config"]["reasoning_effort"], A.ref("config", "reasoning_effort"))
    for fp, family in FAMILIES:
        for metric, key in (("Untimed", "untimed_decision_accuracy"), ("UntimedSeg", "untimed_segment_accuracy"),
                            ("ExactMatch", "all_questions_exact_accuracy"), ("InForce", "time_accuracy"),
                            ("InForceSeg", "segment_time_accuracy")):
            add_pct(f"{p}{fp}{metric}", "scores", "by_family", family, key)
        for suffix, bound in (("", "estimate"), ("Low", "low"), ("High", "high")):
            add_pct(f"{p}{fp}NetRemoved{suffix}", "network_adjustment", "scores", bound, "by_family", family, "time_accuracy")
        for metric, key in (("Median", "p50"), ("PNinetyFive", "p95")):
            m.add(f"{p}{fp}Latency{metric}", sec(A.get("latency_by_family_s", family, key)), A.ref("latency_by_family_s", family, key))
    for name, _, eid in SCENARIOS:
        i = next(k for k, row in enumerate(per) if row["episode_id"] == eid)
        for metric, key in (("Untimed", "untimed_decision_accuracy"), ("ExactMatch", "all_questions_exact_accuracy"),
                            ("InForce", "time_accuracy"), ("InForceSeg", "segment_time_accuracy")):
            add_pct(f"{p}{name}{metric}", "scores", "per_episode", i, key, note=eid)
        for metric, key in (("NoDecision", "no_decision"), ("Stale", "source_correct"), ("Incorrect", "source_incorrect")):
            m.add(f"{p}{name}Err{metric}Sec", sec1(per[i]["error_seconds"][key]),
                  A.ref("scores", "per_episode", i, "error_seconds", key, note=eid))
        for metric, key in (("Median", "latency_s_p50"), ("PNinetyFive", "latency_s_p95")):
            m.add(f"{p}{name}Latency{metric}", sec(per[i][key]), A.ref("scores", "per_episode", i, key, note=eid))
        m.add(f"{p}{name}AcceptedUpdates", count(per[i]["accepted_updates"]), A.ref("scores", "per_episode", i, "accepted_updates", note=eid))


def shared_macros(m: Macros, models: dict, checks: Checks) -> None:
    luna = models["Luna"]["analysis"]
    for key in ("first_option", "lexical_overlap"):
        for p, model in models.items():
            checks.same(f"{p} baseline {key} equals Luna's", model["analysis"].get("baselines", key), luna.get("baselines", key))
    states = luna.get("scores", "states")
    for name, key in (("FirstOption", "first_option"), ("Lexical", "lexical_overlap")):
        m.add(f"Baseline{name}", pct(luna.get("baselines", key, "overall")), luna.ref("baselines", key, "overall"))
        per = luna.get("baselines", key, "per_episode")
        sizes = {row["episode_id"]: row["states"] for row in luna.get("scores", "per_episode")}
        n = sum(as_count(row["accuracy"], sizes[row["episode_id"]], key) for row in per)
        checks.equal(f"baseline {key} states", n, as_count(luna.get("baselines", key, "overall"), states, key))
        m.add(f"Baseline{name}States", count(n), luna.ref("baselines", key, "per_episode", "*", "accuracy", note="x states per scenario, summed"))
    config_keys = (("MaxWorkers", "workers"), ("MaxAttempts", "max_attempts"), ("RequestTimeoutSec", "request_timeout_s"),
                   ("RetryDelaySec", "retry_delay_s"), ("SdkRetries", "sdk_retries"))
    for name, key in config_keys:
        values = {model["analysis"].get("config", key) for model in models.values()}
        checks.equal(f"config {key} identical across models", len(values), 1)
        m.add(name, exact(luna.get("config", key)), luna.ref("config", key, note="identical in all runs"))
    estimators = {model["analysis"].get("network_adjustment", "estimator") for model in models.values()}
    checks.equal("network estimator identical across models", len(estimators), 1)
    estimator = luna.get("network_adjustment", "estimator")
    match = re.fullmatch(r"(0\.\d+)-quantile regression intercept with nonnegative token slopes; (\d+)% range from "
                         r"(\d+) moving-block bootstrap resamples \((\d+) consecutive releases within each scenario, seed (\d+)\)",
                         estimator)
    if not match:
        checks.fail(f"unrecognised network estimator description: {estimator!r}")
        return
    ref = luna.ref("network_adjustment", "estimator")
    m.add("NetQuantilePct", exact(int(Decimal(match[1]) * 100)), ref)
    m.add("NetRangeLevel", match[2], ref)
    m.add("NetBootstrapResamples", match[3], ref)
    m.add("NetBootstrapBlock", match[4], ref)
    m.add("NetBootstrapSeed", match[5], ref)
    # A merged run lists each recording it combines; a single run is its own recording.
    dates = {part["started_at_utc"][:10] for model in models.values()
             for part in model["analysis"].data.get("combined_from") or [model["analysis"].data]}
    n_dates = len(dates)
    if len(dates) == 1:
        m.add("RecordingDatesUTC", next(iter(dates)), "docs/lite/results/four-family/*/analysis.json:started_at_utc (date, identical in all runs)")
    else:
        m.add("RecordingDatesUTC", " and ".join(sorted(dates)), "docs/lite/results/four-family/*/analysis.json:started_at_utc (dates)")
    m.add("RecordingDaysWord", word(n_dates) if n_dates in WORDS else count(n_dates),
          "docs/lite/results/four-family/*/analysis.json:started_at_utc (distinct dates, spelled out)")


def comparison_macros(m: Macros, models: dict, family_of: dict, checks: Checks) -> None:
    for cand, base, _ in COMPARISONS:
        cc, bc = models[cand]["events"]["correct"], models[base]["events"]["correct"]
        checks.equal(f"{cand}/{base} paired state coverage", sorted(cc), sorted(bc))
        outcomes = (("Both", lambda k: cc[k] and bc[k]),
                    (f"{base}Only", lambda k: bc[k] and not cc[k]),
                    (f"{cand}Only", lambda k: cc[k] and not bc[k]),
                    ("Neither", lambda k: not cc[k] and not bc[k]))
        for fp, family in [("", None), *FAMILIES]:
            keys = [k for k in cc if family is None or family_of[k[0]] == family]
            counts = [sum(test(k) for k in keys) for _, test in outcomes]
            checks.equal(f"{cand}/{base}/{fp} paired partition", sum(counts), len(keys))
            for (label, _), value in zip(outcomes, counts):
                m.add(f"Pair{cand}{base}{fp}{label}", count(value),
                      f"{models[cand]['run_rel']} and {models[base]['run_rel']} events: independent composed correctness")
        getters = {"Untimed": lambda x: x["scores"]["overall"]["untimed_decision_accuracy"],
                   "InForce": lambda x: x["scores"]["overall"]["time_accuracy"],
                   "InForceSeg": lambda x: x["scores"]["overall"]["segment_time_accuracy"],
                   "NetRemoved": lambda x: x["network_adjustment"]["scores"]["estimate"]["overall"]["time_accuracy"]}
        for metric, get in getters.items():
            d = shown(get(models[cand]["analysis"].data)) - shown(get(models[base]["analysis"].data))
            first, second = (cand, base) if d >= 0 else (base, cand)
            m.add(f"{first}Minus{second}{metric}", points(abs(d)),
                  f"{models[cand]['analysis'].rel} minus {models[base]['analysis'].rel}: {metric}, printed percentage points")


def audit_macros(m: Macros, facts: dict, bench: dict, checks: Checks) -> None:
    """Audit counts derived from the audit record; FACTS and PROTOCOL must agree."""
    rows = facts["Validity audit (LLM agents, not human validation)"]
    record = Source(AUDIT)
    items, groups = record.get("checks"), record.get("grouped_findings")

    def nums(label):
        return [int(float(x)) for x in numbers(rows[label])]

    derivations = [c for c in items if c["role"] in ("blind", "walk")]
    per_scenario = Counter(c["scenario"] for c in derivations)
    checks.equal("audit covers the original six scenarios", sorted(per_scenario), sorted(e for e in bench["order"] if "presenter" not in e))
    m.add("AuditScenarios", count(len(per_scenario)), f"{AUDIT}:checks scenario coverage")
    checks.equal("audit re-derivations per scenario are equal", len(set(per_scenario.values())), 1)
    checks.equal("audit roles per scenario", {s: sorted(c["role"] for c in derivations if c["scenario"] == s) for s in per_scenario},
                 {s: ["blind", "walk"] for s in per_scenario})
    each = next(iter(per_scenario.values()))
    agreeing = sum("60/60" in c["agreement"] for c in derivations)
    code_text = [c for c in items if c["role"] == "audit"]
    checks.equal("audit code-vs-text checks = one per family", sorted(c["family"] for c in code_text), sorted(f for _, f in FAMILIES if f != "presenter_voice_control"))
    structural = [c for c in items if c["role"] == "structural"]
    lens_sets = Counter(tuple(sorted(v["lens"] for v in g["votes"])) for g in groups)
    checks.equal("audit: every grouped finding has three votes", {len(g["votes"]) for g in groups}, {3})
    lenses = 3
    reference_sets = tuple(sorted(record.get("lenses", "reference_answer_findings")))
    reference_groups = lens_sets[reference_sets]
    wrong = sum(g["majority_verdict"] == "gold_wrong" for g in groups)
    ambiguous = [g for g in groups if g["status"] == "confirmed" and g["majority_verdict"] == "ambiguous_text"]
    affected = sum(len(g["affected_t"]) for g in ambiguous)
    checks.equal("audit ambiguities: scenarios", sorted(g["scenario"] for g in ambiguous),
                 ["lite_assembly_a", "lite_assembly_b", "lite_debugging_b"])
    src = f"{AUDIT}"
    # FACTS must state the same counts.
    def endpoints(ticks):
        runs, out = [], []
        for t in ticks:
            if runs and t == runs[-1][-1] + 1:
                runs[-1].append(t)
            else:
                runs.append([t])
        for r in runs:
            out += [r[0]] if len(r) == 1 else [r[0], r[-1]]
        return out

    tick_ranges = [x for g in ambiguous for x in endpoints(g["affected_t"])]
    for label, want in (("Blind re-derivations", [each, len(derivations), 60, 60]),
                        ("Additional checks", [len(code_text), len(structural)]),
                        ("Adversarial verification", [lenses, reference_groups, len(groups) - reference_groups]),
                        ("Outcome", [wrong, len(ambiguous), affected, *tick_ranges])):
        checks.equal(f"FACTS audit {label} vs {AUDIT}", nums(label), want)
    checks.equal("audit: every re-derivation agrees at all consumed decisions (default reading)", agreeing, len(derivations))
    m.add("AuditRederivationsPerScenario", count(each), f"{src}:checks[role in blind, walk] (per scenario)")
    m.add("AuditRederivationsPerScenarioWord", word(each), r"\AuditRederivationsPerScenario spelled out")
    m.add("AuditRederivations", count(len(derivations)), f"{src}:checks[role in blind, walk] (count)")
    m.add("AuditRederivationsFullAgreement", count(agreeing), f"{src}:checks[role in blind, walk].agreement (reporting 60/60 consumed decisions)")
    m.add("AuditCodeTextChecks", count(len(code_text)), f"{src}:checks[role = audit] (count)")
    m.add("AuditCodeTextChecksWord", word(len(code_text)), r"\AuditCodeTextChecks spelled out")
    m.add("AuditStructuralChecks", count(len(structural)), f"{src}:checks[role = structural] (count)")
    m.add("AuditStructuralChecksWord", word(len(structural)), r"\AuditStructuralChecks spelled out")
    m.add("AuditLenses", count(lenses), f"{src}:grouped_findings[].votes (per finding)")
    m.add("AuditLensesWord", word(lenses), r"\AuditLenses spelled out")
    m.add("AuditFindingGroups", count(len(groups)), f"{src}:grouped_findings (count)")
    m.add("AuditReferenceFindingGroups", count(reference_groups), f"{src}:grouped_findings (judged by the reference-answer lenses)")
    reference_status = Counter(g["status"] for g in groups if tuple(sorted(v["lens"] for v in g["votes"])) == reference_sets)
    m.add("AuditReferenceFindingsRejected", count(reference_status["rejected"]),
          f"{src}:grouped_findings (reference-answer lenses, status rejected)")
    m.add("AuditReferenceFindingsConfirmed", count(reference_status["confirmed"]),
          f"{src}:grouped_findings (reference-answer lenses, status confirmed)")
    m.add("AuditConfirmedWrong", count(wrong), f"{src}:grouped_findings (majority verdict gold_wrong)")
    m.add("AuditAmbiguities", count(len(ambiguous)), f"{src}:grouped_findings (confirmed, majority verdict ambiguous_text)")
    m.add("AuditAmbiguitiesWord", word(len(ambiguous)), r"\AuditAmbiguities spelled out")
    m.add("AuditAffectedStates", count(affected), f"{src}:grouped_findings[ambiguous].affected_t (summed)")
    words = {"one": 1, "two": 2, "three": 3, "four": 4}
    fix = re.match(r"(\w+) public rule sentences clarified", rows["Fix"])
    clarified = words.get(fix[1]) if fix else None
    if clarified is None:
        checks.fail(f"FACTS Fix row not understood: {rows['Fix']!r}")
        return
    m.add("AuditClarifiedSentences", count(clarified), f"{FACTS}: Validity audit / Fix")
    m.add("AuditClarifiedSentencesWord", fix[1], f"{FACTS}: Validity audit / Fix")
    # Corroborate the Fix row against PROTOCOL, which FACTS cites for it.
    protocol = (ROOT / PROTOCOL).read_text()
    checks.equal(f"FACTS clarified sentences vs {PROTOCOL}", f"clarifies {fix[1]} public rule" in " ".join(protocol.split()), True)


# --------------------------------------------------------------------------- counterfactual replays

def _scaled(record: dict, release_s: float, scale: Decimal) -> dict:
    """The record with every recorded delay after its evidence release multiplied by ``scale``."""
    out = copy.deepcopy(record)
    factor = float(scale)

    def move(x):
        return release_s + factor * (x - release_s)

    for key in ("started_s", "completed_s", "received_s", "actual_recorded_s"):
        if key in out:
            out[key] = move(out[key])
    for attempt in out["attempts"]:
        for key in ("started_s", "completed_s", "received_s"):
            if key in attempt:
                attempt[key] = move(attempt[key])
    return out


def replay(verified: dict, transform) -> list[dict]:
    """Rescore every scenario with the benchmark's replay scorer after transforming each record."""
    out = []
    for ep in verified["episodes"]:
        eid = ep["episode_id"]
        releases = verified["releases"][eid]
        release_s = {r["t"]: r["release_s"] for r in releases}
        records = [transform(ep, r, release_s[r["t"]]) for r in verified["responses"][eid]]
        out.append(normalized_episode_scores(ep, records, releases))
    return out


def counterfactual_macros(m: Macros, models: dict, bench: dict, checks: Checks) -> None:
    residuals = []
    for p, model in models.items():
        a, verified = model["analysis"].data, model["verified"]
        A = model["analysis"]
        overall = a["scores"]["overall"]["time_accuracy"]
        # Identity: scale 1 must reproduce the published primary scores.
        same = replay(verified, lambda ep, r, rel: _scaled(r, rel, Decimal(1)))
        checks.close(f"{p} replay at delay scale 1 = primary in-force", mean(s["time_accuracy"] for s in same), overall, 1e-9)
        # Timing ceiling: the reference answers, delivered with the model's recorded delays.
        def oracle(ep, r, rel):
            out = copy.deepcopy(r)
            out["pred"] = copy.deepcopy(ep["steps"][r["t"]]["gold"])
            return out
        ceiling = replay(verified, oracle)
        checks.equal(f"{p} timing-ceiling replay is correct at every state", mean(s["untimed_decision_accuracy"] for s in ceiling), 1)
        value = mean(s["time_accuracy"] for s in ceiling)
        model["timing_ceiling"] = value
        m.add(f"{p}TimingCeiling", pct(value),
              f"{model['run_rel']}/events.jsonl replayed with retry_scoring.normalized_episode_scores, every pred replaced by "
              f"{DATA} gold (mean over scenarios)")
        m.add(f"{p}TimingCeilingLoss", points(100 - _dec(value) * 100), f"100 minus \\{p}TimingCeiling (points)")
        for name, scale in DELAY_SCALES:
            scores = replay(verified, lambda ep, r, rel, s=scale: _scaled(r, rel, s))
            m.add(f"{p}InForceDelay{name}", pct(mean(s["time_accuracy"] for s in scores)),
                  f"{model['run_rel']}/events.jsonl replayed with every delay after release x{float(scale):.4g} "
                  "(retry_scoring.normalized_episode_scores; mean over scenarios)")
        # Equation 3 with the model's own judgment: U_e * (1 - K_e * mean delay_e / observed_e) per scenario.
        per = a["scores"]["per_episode"]
        approx, delays = [], []
        for i, eid in enumerate(bench["order"]):
            records = per[i]["normalization"]["records"]
            rel = model["events"]["releases"]
            d = [x["normalized_ready_s"] - rel[(eid, x["t"])]["release_s"] for x in records]
            delays += d
            k = per[i]["reference_transitions"] + 1
            value_e = per[i]["untimed_decision_accuracy"] * (1 - k * mean(d) / per[i]["observed_duration_s"])
            approx.append(value_e)
            residuals.append(abs(value_e - per[i]["time_accuracy"]))
        m.add(f"{p}DelayApprox", pct(mean(approx)),
              A.ref("scores", "per_episode", "*", note="untimed x (1 - segments x mean effective delay / observed), mean over scenarios"))
        m.add(f"{p}MeanDelaySec", sec(mean(delays)),
              A.ref("scores", "per_episode", "*", "normalization", "records", "*", "normalized_ready_s",
                    note="minus release_s, mean over requests"))
    interval = Decimal(m.items["ReleaseIntervalSec"].value)
    for name, scale in DELAY_SCALES:
        eq = interval / scale
        m.add(f"Delay{name}IntervalSec", exact(int(eq)) if eq == eq.to_integral_value() else fixed(eq, 2),
              f"\\ReleaseIntervalSec / delay scale {float(scale):.4g} (equivalent release interval, s)")
    m.add("DelayApproxMaxResidual", points(_dec(max(residuals)) * 100),
          "per scenario |Eq. 3 approximation - in-force accuracy| (points, maximum over models and scenarios)")


# --------------------------------------------------------------------------- judgment x timing

PARTITION = ("current_correct", "judgment", "stale", "compound", "outdated_correct", "no_decision")
CROSSINGS = (("Jev", "Luna"), ("Jev", "Terra"), ("Jev", "TerraNone"), ("TerraNone", "Terra"), ("TerraNone", "Luna"),
             ("Jev", "Astra"), ("Luna", "Astra"), ("Terra", "Astra"))
REGIME_STEPS, REGIME_DRAWS = 60, 300


def _uniform_schedule(k: int) -> list[int]:
    base, extra = divmod(REGIME_STEPS, k + 1)
    return _from_dwells([base + (1 if i < extra else 0) for i in range(k + 1)])


def _from_dwells(dwells: list[int], labels: list[int] | None = None) -> list[int]:
    seq = [x for i, d in enumerate(dwells) for x in [labels[i] if labels else i] * d]
    if len(seq) != REGIME_STEPS:
        raise ValueError(f"schedule has {len(seq)} time steps")
    return seq


def _bursty_schedule(k: int = 22, bursts: int = 4) -> list[int]:
    """k changes packed into bursts of one-step segments between long stable spans."""
    per = [k // bursts + (1 if b < k % bursts else 0) for b in range(bursts)]
    long_total = REGIME_STEPS - (sum(per) - bursts)
    longs = [long_total // (bursts + 1) + (1 if b < long_total % (bursts + 1) else 0) for b in range(bursts + 1)]
    return _from_dwells([d for b in range(bursts) for d in [longs[b]] + [1] * (per[b] - 1)] + [longs[-1]])


# 23 segments (22 changes): twelve of one step, five of two, two of three and four long ones.
LONG_TAIL_DWELLS = [1, 5, 1, 2, 1, 3, 1, 7, 1, 2, 1, 1, 9, 2, 1, 1, 3, 2, 1, 11, 1, 2, 1]
REGIMES = (
    ("Sparse", "sparse", _uniform_schedule(5)),
    ("Medium", "medium", _uniform_schedule(11)),
    ("Uniform", "uniform", _uniform_schedule(22)),
    ("Dense", "dense", _uniform_schedule(40)),
    ("Bursty", "bursty", _bursty_schedule(22)),
    ("LongTail", "long-tail dwell", _from_dwells(LONG_TAIL_DWELLS)),
    ("Recurrent", "recurrent A-B-A", [i % 2 for i in _uniform_schedule(22)]),
)


def current_source_share(ref: list, release: list[float], ready: list[float], horizon: float) -> float:
    """Share of [release[0], horizon) whose decision in force answered a state with the current reference.

    Acceptance depends only on arrival times and source order, never on answers, so this is the oracle
    in-force accuracy for any reference schedule and latencies (checked against the benchmark scorer)."""
    n = len(ref)
    latest, changes = -1, []
    for i in sorted(range(n), key=lambda i: (ready[i], -i)):
        if ready[i] < horizon and i > latest:
            latest = i
            changes.append((ready[i], i))
    cuts = sorted({release[0], horizon, *release, *(c[0] for c in changes)})
    ok, ci, source, gi = 0.0, 0, None, -1
    for a, b in zip(cuts, cuts[1:]):
        while gi + 1 < n and release[gi + 1] <= a:
            gi += 1
        while ci < len(changes) and changes[ci][0] <= a:
            source = changes[ci][1]
            ci += 1
        if gi >= 0 and source is not None and ref[source] == ref[gi]:
            ok += b - a
    return ok / (horizon - release[0])


def decomposition_macros(m: Macros, models: dict, bench: dict, checks: Checks, *, write_crossings=True) -> None:
    """Timing-by-judgment partition, the untimed x oracle factorization, crossing intervals and schedule projections."""
    import random

    tick = Decimal(str(POLICY["recording_interval_s"]))
    cache: dict = {}

    def at_interval(p: str, interval: Decimal) -> float:
        """In-force accuracy of the recorded pass evaluated with time steps `interval` seconds apart."""
        key = (p, interval)
        if key not in cache:
            scores = replay(models[p]["recorded"], lambda ep, r, rel: _scaled(r, rel, Decimal(str(ep["tick_seconds"])) / interval))
            cache[key] = mean(s["time_accuracy"] for s in scores)
        return cache[key]

    deviations, gaps, ucur_gaps = [], {}, {}
    for p, model in models.items():
        verified, src = model["verified"], f"{model['run_rel']}/events.jsonl"
        same = replay(verified, lambda ep, r, rel: _scaled(r, rel, Decimal(1)))
        zero = replay(verified, lambda ep, r, rel: _scaled(r, rel, Decimal(0)))
        oracle = replay(verified, lambda ep, r, rel: dict(copy.deepcopy(r), pred=copy.deepcopy(ep["steps"][r["t"]]["gold"])))
        observed = sum(s["observed_duration_s"] for s in same)
        part = {k: sum(s["time_partition_seconds"][k] for s in same) for k in PARTITION}
        checks.close(f"{p} partition stale = error_seconds.source_correct", part["stale"],
                     sum(s["error_seconds"]["source_correct"] for s in same), 1e-9)
        checks.close(f"{p} partition judgment + compound = error_seconds.source_incorrect", part["judgment"] + part["compound"],
                     sum(s["error_seconds"]["source_incorrect"] for s in same), 1e-9)
        checks.close(f"{p} current-source share = oracle in-force accuracy",
                     mean(s["current_source_share"] for s in same), model["timing_ceiling"], 1e-12)
        for s, o in zip(same, oracle):
            checks.close(f"{p} {s['episode_id']} current-source share = oracle", s["current_source_share"], o["time_accuracy"], 1e-12)
        for s, z in zip(same, zero):
            checks.close(f"{p} {s['episode_id']} in-force accuracy at zero latency = untimed accuracy",
                         z["time_accuracy"], s["untimed_decision_accuracy"], 1e-3)
        note = f"{src} rescored with lite.scoring (time_partition_seconds, summed over scenarios)"
        for name, key in (("ErrJudgment", "judgment"), ("ErrCompound", "compound"), ("Lucky", "outdated_correct")):
            m.add(f"{p}{name}Sec", sec1(part[key]), note)
            m.add(f"{p}{name}Pct", pct(family_mean(same, lambda row: row["time_partition_seconds"][key] / row["observed_duration_s"])), f"{note}; each scenario divided by its own observed duration, then equal family mean")
        fractions = {k: family_mean(same, lambda row: row["time_partition_seconds"][k] / row["observed_duration_s"]) for k in PARTITION}
        current = fractions["current_correct"] + fractions["judgment"]
        m.add(f"{p}UCurrent", pct(fractions["current_correct"] / current),
              f"{note}; macro-normalized current_correct / (current_correct + judgment)")
        for name, _, eid in SCENARIOS:
            s = next(x for x in same if x["episode_id"] == eid)
            for metric, key in (("ErrJudgment", "judgment"), ("ErrCompound", "compound")):
                m.add(f"{p}{name}{metric}Sec", sec1(s["time_partition_seconds"][key]), f"{src} rescored ({eid}, time_partition_seconds.{key})")
        # Untimed x oracle: exact product of the two single-factor counterfactuals, per scenario.
        product = [s["untimed_decision_accuracy"] * o["time_accuracy"] for s, o in zip(same, oracle)]
        deviations += [abs(s["time_accuracy"] - x) for s, x in zip(same, product)]
        gap = shown(mean(s["time_accuracy"] for s in same)) - shown(mean(product))
        gaps[p] = gap
        m.add(f"{p}Product", pct(mean(product)), f"{src} rescored: mean over scenarios of untimed accuracy x oracle in-force accuracy")
        m.add(f"{p}InForceMinusProduct", points(gap), f"\\{p}InForce minus \\{p}Product (points)")
        # Under macro weighting, U_cur is normalized current-correct mass / current-source mass.
        checks.close(f"{p} macro A = O * U_cur + lucky", family_mean(same, lambda row: row["time_accuracy"]),
                     current * (fractions["current_correct"] / current) + fractions["outdated_correct"], 1e-12)
        ucur_gaps[p] = abs(_dec(fractions["current_correct"] / current) - _dec(mean(s["untimed_decision_accuracy"] for s in same))) * 100
    lucky = {p: Decimal(m.items[f"{p}LuckyPct"].value) for p in models}
    m.add("LuckyPctMax", m.items[f"{max(lucky, key=lucky.get)}LuckyPct"].value, "maximum over settings of \\<Model>LuckyPct")
    m.add("CostTotalUSD", fixed(sum(model["cost_usd"] for model in models.values()), 2),
          f"sum of \\<Model>CostUSD over the {word(len(models))} recorded passes (USD, list prices)")
    used = {(model["analysis"].get("config").get("provider", "openai"), model["analysis"].get("config", "model"))
            for model in models.values()}
    checks.equal("every recorded model has a list price", sorted(used - set(PRICES)), [])
    dates = sorted({PRICES[key][4] for key in used})
    m.add("PricesRetrieved", " and ".join(dates),
          f"dates the list prices were read from the providers' official pages ({PRICING_NOTE})")
    m.add("UCurrentMaxDiff", points(max(ucur_gaps.values())), "max over settings |UCurrent - Untimed| (points)")
    m.add("ProductMaxDeviation", points(_dec(max(deviations)) * 100),
          "per scenario |in-force - untimed x oracle| (points, maximum over settings and scenarios)")
    low, high = min(gaps, key=gaps.get), max(gaps, key=gaps.get)
    m.add("InForceMinusProductMin", points(gaps[low]), f"minimum over settings (\\{low}InForceMinusProduct)")
    m.add("InForceMinusProductMax", points(gaps[high]), f"maximum over settings (\\{high}InForceMinusProduct)")

    # Common-interval sensitivity; no expected rank or crossing is imposed.
    lo, hi = Decimal("0.5"), Decimal("8")
    grid = [lo + (hi - lo) * Decimal(k) / 40 for k in range(41)]
    crossings = []
    for a, b in CROSSINGS:
        diff = [at_interval(a, x) - at_interval(b, x) for x in grid]
        roots = []
        for k in range(len(grid) - 1):
            if diff[k] * diff[k + 1] >= 0:
                continue
            left, right, sign = grid[k], grid[k + 1], diff[k] > 0
            for _ in range(24):
                mid = (left + right) / 2
                if (at_interval(a, mid) > at_interval(b, mid)) == sign:
                    left = mid
                else:
                    right = mid
            roots.append(float((left + right) / 2))
        crossings.extend({"a": a, "b": b, "interval_s": x} for x in roots)
        if len(roots) == 1:
            m.add(f"Cross{a}{b}Sec", sec(roots[0]), "common-interval replay, root found within 0.5--8 s")
    OUT.mkdir(parents=True, exist_ok=True)
    if write_crossings:
        (OUT / "crossings.json").write_text(json.dumps(crossings, indent=2) + "\n")
    for p in models:
        for name, interval in (("Two", Decimal(2)), ("Eight", Decimal(8))):
            m.add(f"{p}Common{name}", pct(at_interval(p, interval)), "common-interval replay of frozen answers and latencies")

    # Projection over reference schedules: untimed accuracy x oracle share with resampled recorded latencies.
    lite = {p: [] for p in models}
    pools = {}
    for p, model in models.items():
        verified = model["verified"]
        same = replay(verified, lambda ep, r, rel: _scaled(r, rel, Decimal(1)))
        pool = []
        for ep, s in zip(verified["episodes"], same):
            rel = verified["releases"][ep["episode_id"]]
            release = [r["release_s"] for r in rel]
            ready = [d["normalized_ready_s"] for d in sorted(s["normalization"]["records"], key=lambda d: d["t"])]
            ref = [json.dumps(compose(ep["decision_spec"], st["gold"]), sort_keys=True) for st in ep["steps"]]
            horizon = len(ep["steps"]) * ep["tick_seconds"]
            checks.close(f"{p} {ep['episode_id']} tick-level oracle share = benchmark scorer",
                         current_source_share(ref, release, ready, horizon), s["current_source_share"], 1e-12)
            pool += [ready[i] - release[i] for i in range(len(release))]
            lite[p].append(ref)
        pools[p] = pool

    def projected(p: str, schedule: list, label: str) -> float:
        rng = random.Random(f"sdb-regime:{p}:{label}")
        release = [i * float(tick) for i in range(len(schedule))]
        horizon = len(schedule) * float(tick)
        draws = [current_source_share(schedule, release, [r + rng.choice(pools[p]) for r in release], horizon)
                 for _ in range(REGIME_DRAWS)]
        return models[p]["analysis"].get("scores", "overall", "untimed_decision_accuracy") * mean(draws)

    worst = Decimal(0)
    for p in models:
        value = mean(projected(p, ref, f"lite{k}") for k, ref in enumerate(lite[p]))
        m.add(f"RegimeLite{p}", pct(value), f"projection on the eight SDB reference schedules ({REGIME_DRAWS} latency resamples each)")
        worst = max(worst, abs(_dec(value) - _dec(models[p]["analysis"].get("scores", "overall", "time_accuracy"))) * 100)
    m.add("RegimeLiteMaxDiff", points(worst), "max over settings |projection on SDB's schedules - observed in-force accuracy| (points)")
    for name, _, schedule in REGIMES:
        m.add(f"Regime{name}Changes", count(sum(x != y for x, y in zip(schedule, schedule[1:]))), f"reference changes in the {name} schedule")
        for p in models:
            m.add(f"Regime{name}{p}", pct(projected(p, schedule, name)),
                  f"untimed accuracy x mean oracle share over {REGIME_DRAWS} resamples of recorded latencies ({name} schedule, "
                  f"{REGIME_STEPS} time steps of \\ReleaseIntervalSec\\,s)")
    def gain(name, p):
        return Decimal(m.items[f"Regime{name}{p}"].value) - Decimal(m.items[f"RegimeUniform{p}"].value)
    # "Low": the GPT settings at low reasoning effort (Luna low, Terra low, Astra low); "other": the rest.
    low_effort = ("Luna", "Terra", "Astra")
    low = [gain(n, p) for n in ("Bursty", "LongTail") for p in low_effort]
    other = [gain(n, p) for n in ("Bursty", "LongTail") for p in models if p not in low_effort]
    m.add("RegimeStructureGainLowMin", points(min(low)),
          "min over {Bursty,LongTail} x {Luna,Terra,Astra} of projection minus the uniform schedule (points)")
    m.add("RegimeStructureGainLowMax", points(max(low)), "max of the same (points)")
    m.add("RegimeStructureGainOtherMax", points(max(abs(x) for x in other)), "max absolute change from uniform, other settings")
    m.add("RegimeSteps", count(REGIME_STEPS), "time steps per projected schedule")
    m.add("RegimeDraws", count(REGIME_DRAWS), "latency resamples per projected schedule")


def pair_macros(m: Macros, models: dict, checks: Checks) -> None:
    a = {p: models[p]["analysis"].data for p in models}
    # Terra against Jev has no comparison.json; differences from the two analyses, sign folded into the name.
    for metric, get in (("Untimed", lambda x: x["scores"]["overall"]["untimed_decision_accuracy"]),
                        ("InForce", lambda x: x["scores"]["overall"]["time_accuracy"]),
                        ("NetRemoved", lambda x: x["network_adjustment"]["scores"]["estimate"]["overall"]["time_accuracy"])):
        d = shown(get(a["Terra"])) - shown(get(a["Jev"]))
        first, second = ("Terra", "Jev") if d >= 0 else ("Jev", "Terra")
        m.add(f"{first}Minus{second}{metric}", points(abs(d)), "docs/lite/results/four-family/{gpt-5.6-terra-low,jev-latest}/analysis.json (difference, points)")
    # Dropping reasoning: how much sooner each GPT model responds at the median.
    for low, none in (("Luna", "LunaNone"), ("Terra", "TerraNone")):
        saving = _dec(a[low]["latency_s"]["p50"]) - _dec(a[none]["latency_s"]["p50"])
        m.add(f"{none}LatencySavingSec", sec(saving),
              f"latency_s.p50 of {low} minus {none} (s; docs/lite/results/four-family/*/analysis.json)")
    # Scenarios in which one model's in-force accuracy exceeds another's.
    for first, second in (("Terra", "Luna"), ("Luna", "Jev"), ("Jev", "Luna"), ("Terra", "Jev")):
        n = sum(x["time_accuracy"] > y["time_accuracy"]
                for x, y in zip(a[first]["scores"]["per_episode"], a[second]["scores"]["per_episode"]))
        m.add(f"{first}AheadOf{second}Scenarios", count(n), f"scores.per_episode[*].time_accuracy, {first} > {second} (scenarios)")
        m.add(f"{first}AheadOf{second}ScenariosWord", word(n) if n in WORDS else count(n), f"\\{first}AheadOf{second}Scenarios spelled out")
    # Untimed minus in-force accuracy per scenario: the smallest for Luna low and Terra low (the macro keeps its
    # name; it covers exactly these two settings), for Astra low, and the largest for Jev.
    gap = {p: [(_dec(x["untimed_decision_accuracy"]) - _dec(x["time_accuracy"])) * 100 for x in a[p]["scores"]["per_episode"]]
           for p in a}
    m.add("GPTMinScenarioGap", points(min(gap["Luna"] + gap["Terra"])),
          "scores.per_episode[*] untimed_decision_accuracy - time_accuracy (points, minimum over Luna low, Terra low and scenarios)")
    m.add("AstraMinScenarioGap", points(min(gap["Astra"])),
          "docs/lite/results/four-family/gpt-6-astra-low/analysis.json:scores.per_episode[*] untimed - in-force (points, minimum)")
    m.add("JevMaxScenarioGap", points(max(gap["Jev"])),
          "docs/lite/results/four-family/jev-latest/analysis.json:scores.per_episode[*] untimed - in-force (points, maximum)")
    for p in a:
        outputs = [u.get("output_tokens") or 0 for u in models[p]["events"]["usage"]]
        m.add(f"{p}OutputTokMin", count(min(outputs)), f"{models[p]['run_rel']}/events.jsonl:response.usage.output_tokens (minimum)")
    diff = max(abs(_dec(x["raw_wallclock_scores"]["overall"]["time_accuracy"]) - _dec(x["scores"]["overall"]["time_accuracy"]))
               for x in a.values()) * 100
    m.add("MaxReplayPhysicalDiff", fixed(diff, 2), "analysis.json raw_wallclock_scores vs scores, overall time_accuracy (max |difference|, points)")
    # Retry waits: runtime.py waits 0 s after the first failed attempt, then retry_delay_s * 2^(n-2), capped at 8 s.
    runtime = (ROOT / RUNTIME).read_text()
    checks.equal(f"{RUNTIME} backoff formula", "min(retry_delay_s * 2 ** min(number - 2, 10), 8.0)" in runtime, True)
    cfg = a["Luna"]["config"]
    waits = [min(cfg["retry_delay_s"] * 2 ** min(n - 2, 10), 8.0) for n in range(2, cfg["max_attempts"])]
    text = ", ".join(exact(w) for w in waits[:-1]) + f" and {exact(waits[-1])}"
    m.add("RetryLaterDelaysSec", text, f"{RUNTIME} backoff with config retry_delay_s and max_attempts")
    m.add("JevReportStep", exact(jev_contract.REPORTED_STEP), "src/streamdecisionbench/jev.py:REPORTED_STEP")
    # The first Jev pass and the rerun (docs/lite/results/README.md); only the Jev runner differs.
    readme = " ".join((ROOT / RESULTS_README).read_text().split())
    stop = re.search(r"Jev's first attempt stopped at `(\w+)` t(\d+)", readme)
    checks.equal(f"{RESULTS_README} names where the first Jev pass stopped", bool(stop) and stop[1] == "lite_assembly_a", True)
    if stop:
        m.add("JevStoppedRelease", stop[2], f"{RESULTS_README} (first Jev pass, lite_assembly_a)")
    # A merged pass lists the recordings it combines; a single-session pass is its own recording.
    parts = [(p, part) for p, analysis in a.items() for part in analysis.get("combined_from") or [analysis]]
    for source in ("lite/runtime.py", "adapters/llm.py", "jev.py"):
        hashes = {part["run_sources"][source] for _, part in parts}
        checks.equal(f"paper claim: recordings share {source}", len(hashes), 1)



def window_macros(m: Macros, models: dict, bench: dict, checks: Checks) -> None:
    a = {p: models[p]["analysis"].data for p in models}
    order = bench["order"]
    shown = ("Luna", "Terra", "Jev")  # the settings Figure 1 draws
    intervals = {p: {row["episode_id"]: row["intervals"] for row in a[p]["scores"]["per_episode"]} for p in shown}
    overall = {p: a[p]["scores"]["overall"]["time_accuracy"] for p in shown}
    ep = next(e for e in models["Luna"]["verified"]["episodes"] if e["episode_id"] == "lite_presenter_a")
    result = window_scan(intervals, overall, ["lite_presenter_a"], ep["tick_seconds"], len(ep["steps"]) * ep["tick_seconds"])
    chosen = result["chosen"]
    src = "paper/analysis/lite_window.py over docs/lite/results/four-family/*/analysis.json scores.per_episode[*].intervals"
    m.add("NumWindows", count(result["candidates"]), f"{src} (candidate windows)")
    m.add("TrajWindowSec", exact(result["window_s"]), f"{src} (window length)")
    m.add("TrajWindowStart", exact(chosen["start"]), f"{src} (chosen window)")
    m.add("TrajWindowEnd", exact(chosen["end"]), f"{src} (chosen window)")
    m.add("TrajWindowMaxDev", points(_dec(chosen["max_deviation"]) * 100), f"{src} (largest |window share - in-force accuracy|, points)")
    checks.equal("Figure 1 window scenario", chosen["episode"], "lite_presenter_a")
    for p in shown:
        m.add(f"{p}TrajShare", pct(chosen["share"][p]), f"{src} (correct share in the chosen window)")

    return result


# --------------------------------------------------------------------------- settings and Astra low

def setting_macros(m: Macros, models: dict, checks: Checks) -> None:
    """How many settings and hosted models the paper reports, and that they saw identical requests."""
    configs = {p: model["analysis"].get("config") for p, model in models.items()}
    settings = {(c.get("provider", "openai"), c["model"], c.get("reasoning_effort")) for c in configs.values()}
    checks.equal("each setting is a distinct model and reasoning effort", len(settings), len(models))
    checks.equal("every setting is a hosted service (no custom endpoint)", [p for p, c in configs.items() if c.get("custom_endpoint")], [])
    served = {p: next(iter(model["analysis"].get("models_returned"))) for p, model in models.items()}
    checks.equal("served model identifiers are distinct per model", len(set(served.values())), len({c["model"] for c in configs.values()}))
    hosted = {model for _, model, _ in settings}
    gpt = {model for provider, model, _ in settings if provider == "openai"}
    src = "docs/lite/results/four-family/*/analysis.json:config"
    m.add("NumSettings", count(len(models)), f"{src} (distinct model and reasoning effort; three recorded passes each)")
    m.add("NumSettingsWord", word(len(models)), r"\NumSettings spelled out")
    m.add("NumHostedModels", count(len(hosted)), f"{src}.model (distinct values)")
    m.add("NumHostedModelsWord", word(len(hosted)), r"\NumHostedModels spelled out")
    m.add("NumGPTModels", count(len(gpt)), f"{src}.model (distinct values with provider openai)")
    m.add("NumGPTModelsWord", word(len(gpt)), r"\NumGPTModels spelled out")
    # Every setting received the same request at every state (the request digest covers the model-visible input).
    digests = {p: {k: r["request_hash"] for k, r in model["events"]["responses"].items()} for p, model in models.items()}
    first = next(iter(digests.values()))
    for p, d in digests.items():
        checks.equal(f"{p} request digests equal the first setting's at every state", d, first)


def claim_checks(m: Macros, models: dict, checks: Checks) -> None:
    """Check the manuscript's descriptive claims on three-pass means."""
    primary = {p: model["analysis"].get("auc", "primary", "overall") for p, model in models.items()}
    largest = {p: max(("stale", "judgment", "compound", "no_decision"), key=lambda k: row[k])
               for p, row in primary.items()}
    checks.equal("mean error classes", largest,
                 {p: "judgment" if p in ("Jev", "LunaNone") else "stale" for p in models})
    leaders = {family: max(models, key=lambda p: models[p]["analysis"].get("auc", "primary", "by_family", family, "accuracy"))
               for _, family in FAMILIES}
    checks.equal("mean family leaders", leaders,
                 {"live_debugging": "Terra", "procedural_coaching": "Jev",
                  "support_call_assist": "Jev", "presenter_voice_control": "Jev"})
    checks.equal("mean primary hosted leader", max(primary, key=lambda p: primary[p]["accuracy"]), "Jev")
    checks.equal("mean oracle minimum", min(primary, key=lambda p: primary[p]["oracle"]), "Luna")
    checks.equal("mean median maximum", max(models, key=lambda p: models[p]["analysis"].get("latency_s", "p50")), "Luna")
    expected = {"Linear": "Terra", "Narrow": "TerraNone", "HalfFour": "Jev", "OneEight": "TerraNone",
                "TenthFour": "Jev", "TenthEight": "Jev"}
    for key, leader in expected.items():
        checks.equal(f"mean sensitivity leader {key}", max(models, key=lambda p: models[p]["analysis"].get("auc", "sensitivity", key, "overall", "accuracy")), leader)
    gaps = [100 * (model["analysis"].get("scores", "by_family", family, "untimed_decision_accuracy") -
                   model["analysis"].get("network_adjustment", "scores", "high", "by_family", family, "time_accuracy"))
            for p, model in models.items() if p in ("Luna", "Terra", "Astra") for _, family in FAMILIES]
    m.add("NetRemovedLowEffortMinGap", points(min(gaps)), "three-pass family means: untimed minus network-removed high endpoint")
    above = [p for p in models if p != "Jev" and Decimal(m.items[p+"CommonEight"].value) > Decimal(m.items["JevCommonEight"].value)]
    m.add("GPTAboveJevCommonEight", count(len(above)), "three-pass fixed 8 s means")
    m.add("GPTAboveJevCommonEightWord", word(len(above)), "three-pass fixed 8 s means")
    for p, row in primary.items():
        checks.close(f"{p} mean integrated factorization", row["accuracy"],
                     row["oracle"] * row["current_correct"] / row["oracle"] + row["outdated_correct"], 1e-12)



def astra_macros(m: Macros, models: dict, bench: dict, checks: Checks) -> None:
    """Astra low pass 1: its recording session and concrete validity case."""
    astra = models["Astra"]
    A, ev = astra["analysis"], astra["events"]
    a = A.data
    events_src = f"{astra['run_rel']}/events.jsonl"
    cfg = a["config"]
    checks.equal("Astra: requested model and effort", (cfg.get("provider"), cfg["model"], cfg["reasoning_effort"]),
                 ("openai", "gpt-6-astra", "low"))
    # One session over all scenarios, recorded after every other setting's pass, on the same frozen data.
    checks.equal("Astra: one recording session (not a merged pass)", a.get("combined_from"), None)
    checks.equal("Astra: the session covers every scenario", a["episode_order"], bench["order"])
    started, finished = a["started_at_utc"], a["finished_at_utc"]
    checks.equal("Astra: the session lies within one UTC day", started[:10], finished[:10])
    others = [part["finished_at_utc"] for p, model in models.items() if p != "Astra"
              for part in model["analysis"].data.get("combined_from") or [model["analysis"].data]]
    checks.equal("Astra: recorded after every other setting's recordings", started > max(others), True)
    m.add("AstraRecordedEndUTC", finished[11:16], A.ref("finished_at_utc", note="minute; same UTC date as started_at_utc"))
    # Astra low rarely emits reasoning tokens, so its latency is not a reasoning cost.
    decode = {p: models[p]["analysis"].get("network_adjustment", "decode_s_per_output_token") for p in ("Luna", "Terra", "Astra")}
    checks.equal("paper claim: Astra low decodes more slowly per token than Luna low and Terra low",
                 decode["Astra"] > max(decode["Luna"], decode["Terra"]), True)
    gpt_decode = {p: models[p]["analysis"].get("network_adjustment", "decode_s_per_output_token") for p in models
                  if models[p]["analysis"].get("config").get("provider", "openai") == "openai"}
    checks.equal("paper claim: Astra low has the highest decode slope", max(gpt_decode, key=gpt_decode.get), "Astra")
    out_median = median([u.get("output_tokens") or 0 for u in ev["usage"]])
    none_median = median([u.get("output_tokens") or 0 for u in models["LunaNone"]["events"]["usage"]])
    checks.equal("paper claim: Astra low's median output is within 10% of Luna none's", abs(out_median - none_median) <= 0.1 * none_median, True)
    reasoning = [(u.get("reasoning_tokens") or 0) for u in ev["usage"]]
    checks.equal("Astra: one usage record per state", len(reasoning), a["scores"]["states"])
    m.add("AstraReasoningResponses", count(sum(r > 0 for r in reasoning)),
          f"{events_src}: responses whose usage reports reasoning_tokens > 0")
    # Exactly one composed-decision miss.
    misses = sorted(k for k, ok in ev["correct"].items() if not ok)
    eid, t = ASTRA_MISS["episode"], ASTRA_MISS["t"]
    checks.equal("paper claim: Astra low's only composed-decision miss", misses, [(eid, t)])
    states = a["scores"]["states"]
    checks.equal("Astra states = \\NumStates", count(states), m.items["NumStates"].value)
    checks.equal("Astra correct states + misses = states", int(m.items["AstraUntimedStates"].value) + len(misses), states)
    m.add("AstraStates", count(states), A.ref("scores", "states"))
    m.add("AstraUntimedMisses", count(len(misses)),
          f"{events_src}: states whose composed decision differs from {DATA} gold (independent recount)")
    m.add("AstraUntimedMissesWord", word(len(misses)), r"\AstraUntimedMisses spelled out")
    if misses != [(eid, t)]:
        return
    ep = bench["episodes"][eid]
    E = ep.data
    spec = E["decision_spec"]
    name, family_prefix = next((n, fp) for n, fp, e in SCENARIOS if e == eid)
    pred, gold = compose(spec, ev["responses"][(eid, t)]["pred"]), compose(spec, E["steps"][t]["gold"])
    prev_pred, prev_gold = compose(spec, ev["responses"][(eid, t - 1)]["pred"]), compose(spec, E["steps"][t - 1]["gold"])
    checks.equal("Astra miss: the reference is unchanged from the preceding time step", gold, prev_gold)
    checks.equal("Astra miss: at the preceding time step Astra returned the reference", prev_pred, prev_gold)
    # The two states differ only by the clock and one appended heartbeat record, which the rules say changes nothing.
    before, state = E["steps"][t - 1]["state"], E["steps"][t]["state"]
    added = state["station_log"][len(before["station_log"]):]
    expected = copy.deepcopy(before)
    expected["clock"]["tick"] = t
    expected["station_log"] = before["station_log"] + added
    checks.equal("Astra miss: one record added since the preceding state", [r["kind"] for r in added], ["heartbeat"])
    checks.equal("Astra miss: the states differ only by the clock and that heartbeat", state, expected)
    rules = " ".join(state["work_instruction"]["rules"])
    for phrase in ("status heartbeats", "do not change any decision", "Incomplete future stages are not defects",
                   "Returning to an earlier target moves the stage back"):
        checks.equal(f"Astra miss: the public rules state {phrase!r}", phrase in rules, True)
    # The answers: Astra repairs a missing inspection; the reference advances to inspection from fasten.
    checks.equal("Astra miss: Astra's composed decision",
                 (pred["route"], pred["stage"], pred.get("target"), pred.get("method")), ("repair", "fasten", "inspection", "complete_missing"))
    checks.equal("Astra miss: the reference decision", (gold["route"], gold["stage"], gold.get("next_step")),
                 ("advance", "fasten", "inspection"))
    # The evidence: a J2 rework after the only inspection PASS moved the stage back to fasten.
    log = state["station_log"]
    inspections = [r for r in log if r["kind"] == "inspection"]
    checks.equal("Astra miss: one inspection record, a PASS", [(r["code"]) for r in inspections], ["PASS"])
    inspection = inspections[-1]
    screws = [r for r in log if r["kind"] == "replace_screw"]
    checks.equal("Astra miss: one screw replacement, at J2, after the inspection",
                 [(r["target"], r["tick"] > inspection["tick"]) for r in screws], [("J2", True)])
    screw = screws[-1]
    rundowns = [r for r in log if r["kind"] == "rundown" and r["target"] == screw["target"] and r["tick"] > screw["tick"]]
    checks.equal("Astra miss: one J2 rundown after the replacement", len(rundowns), 1)
    rundown = rundowns[-1]
    low, high = state["work_instruction"]["torque_nm"][screw["target"]]
    checks.equal("Astra miss: the rundown is in range (endpoints included)", low <= rundown["value"] <= high, True)
    productive = [r for r in log if r["kind"] in ("scan", "gasket", "engage", "rundown", "replace_screw", "inspection")]
    checks.equal("Astra miss: the latest productive record is that rundown", productive[-1], rundown)
    # The original blind audit adjudicated this question at these time steps; every lens upheld the reference.
    audited = [g for g in Source(AUDIT).get("grouped_findings")
               if g["scenario"] == eid and {t - 1, t} <= set(g["ticks"]) and "route" in g["questions"]]
    checks.equal("Astra miss: one audit finding covers this question at both time steps", len(audited), 1)
    if audited:
        votes = [v["verdict"] for v in audited[0]["votes"]]
        checks.equal("Astra miss: every audit lens judged the reference correct", votes,
                     ["gold_correct"] * int(m.items["AuditLenses"].value))
        # The audit grouped the states at which this reading would change the decision (this one and the preceding
        # time step among them); Astra returned the reference at all of them but this one.
        situation = sorted(audited[0]["ticks"])
        wrong = [k for k in situation if not ev["correct"][(eid, k)]]
        checks.equal("Astra miss: the only audited state of this situation that Astra missed", wrong, [t])
        m.add("AstraSituationStates", count(len(situation)),
              f"{AUDIT}: grouped finding {audited[0]['id']} ticks ({eid}; stale inspection PASS while the stage is earlier)")
        m.add("AstraSituationCorrect", count(len(situation) - len(wrong)),
              f"{events_src}: states of that finding whose composed decision equals gold")
    src = ep.ref("steps", t, "state")
    m.add("AstraMissScenarioTitle", m.items[f"{name}Title"].value, ep.ref("title"))
    m.add("AstraMissScenarioLabel", f"\\{family_prefix}Label{{}} {name[-1]}", f"{eid} (as labelled in the per-scenario table)")
    m.add("AstraMissStep", exact(t), f"{events_src}: the only response whose composed decision differs from gold ({eid})")
    m.add("AstraMissSec", exact(t * RECORDING_INTERVAL), r"\AstraMissStep x recording interval (s)")
    m.add("AstraMissPrevStep", exact(t - 1), f"{events_src}: {eid} t={t - 1}, composed decision equal to gold")
    m.add("AstraMissRoute", tex_text(pred["route"]), f"{events_src}: {eid} t={t} pred.route")
    m.add("AstraMissTarget", tex_text(pred["target"]), f"{events_src}: {eid} t={t} pred.target")
    m.add("AstraMissMethod", tex_text(pred["method"]), f"{events_src}: {eid} t={t} pred.method")
    m.add("AstraMissRefRoute", tex_text(gold["route"]), ep.ref("steps", t, "gold", "route"))
    m.add("AstraMissRefStage", tex_text(gold["stage"]), ep.ref("steps", t, "gold", "stage"))
    m.add("AstraMissRefNextStep", tex_text(gold["next_step"]), ep.ref("steps", t, "gold", "next_step"))
    m.add("AstraMissInspectionStep", exact(inspection["tick"]), f"{src}.station_log[kind=inspection].tick (code PASS)")
    m.add("AstraMissScrewStep", exact(screw["tick"]), f"{src}.station_log[kind=replace_screw].tick (target {screw['target']})")
    m.add("AstraMissRundownStep", exact(rundown["tick"]), f"{src}.station_log[kind=rundown, target {screw['target']}, after the replacement].tick")
    for value in (rundown["value"], low, high):  # torques are stated to one decimal in the data
        checks.equal(f"Astra miss: torque {value!r} has one decimal", _dec(value) == Decimal(fixed(value, 1)), True)
    m.add("AstraMissRundownNm", fixed(rundown["value"], 1), f"{src}.station_log[kind=rundown, tick {rundown['tick']}].value")
    m.add("AstraMissTorqueMinNm", fixed(low, 1), f"{src}.work_instruction.torque_nm.{screw['target']}[0]")
    m.add("AstraMissTorqueMaxNm", fixed(high, 1), f"{src}.work_instruction.torque_nm.{screw['target']}[1]")


# --------------------------------------------------------------------------- FACTS.md cross-check

def parse_facts() -> tuple[dict, str]:
    text = (ROOT / FACTS).read_text()
    sections, current, header = {}, None, False
    for line in text.splitlines():
        if line.startswith("## "):
            current, header = line[3:].strip(), True
            continue
        if current and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header:
                sections.setdefault(current, {})["__header__"] = cells
                header = False
                continue
            value_only = sections[current]["__header__"][1:] == ["Value", "Source"]
            sections[current][cells[0]] = cells[1] if value_only else cells[1:]
    return sections, " ".join(text.split())


def numbers(cell: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", re.sub(r"`[^`]*`", "", cell))


def rng(low: str, high: str, m: Macros) -> str:
    return f"\\{low}" if m.items[low].value == m.items[high].value else f"\\{low}--\\{high}"


def tables(m: Macros) -> list[tuple[str, str, list[str]]]:
    models = [p for p, _, _ in MODELS]
    out = []

    rows = []
    for fp, _ in FAMILIES:
        if rows:
            rows.append(r"\midrule")
        for k, (name, family_prefix, _) in enumerate(s for s in SCENARIOS if s[1] == fp):
            rows.append(" & ".join([f"\\{fp}Label" if k == 0 else "", name[-1], f"\\{name}Questions", f"\\{name}RouteOptions",
                                    rng(f"{name}OptionsMin", f"{name}OptionsMax", m), f"\\{name}Transitions"]) + r" \\")
    rows += [r"\midrule", " & ".join([r"\multicolumn{2}{l}{All}", rng("QuestionsMin", "QuestionsMax", m),
                                     rng("RouteOptionsMin", "RouteOptionsMax", m), rng("OptionsMin", "OptionsMax", m),
                                     r"\TransitionsTotal"]) + r" \\"]
    out.append(("TabBenchmarkBody",
                "Benchmark by family and scenario. Columns (6): l l r r r r = Family, Scenario, Questions per request, "
                "Route options, Options per question, Reference transitions.", rows))

    rows = []
    for p in models:
        rows.append(f"\\{p}RowLabel & \\{p}LatencyMedian & \\{p}Untimed & \\{p}InForce & \\{p}NetRemoved & "
                    f"(\\{p}NetRemovedLow--\\{p}NetRemovedHigh) \\\\")
    out.append(("TabMainBody",
                "Main results, overall (family macro mean). Columns (6): l r r r r l = Setting, Median response time s, "
                "Untimed decision accuracy %, In-force accuracy %, Network-removed in-force accuracy %, its 95% bootstrap range.", rows))

    rows = []
    for fp, _ in FAMILIES:
        if rows:
            rows.append(r"\midrule")
        rows.append(f"\\multicolumn{{5}}{{l}}{{\\textit{{\\{fp}Label}}}} \\\\")
        for p in models:
            q = f"{p}{fp}"
            rows.append(f"\\{p}RowLabel & \\{q}Untimed & \\{q}InForce & \\{q}NetRemoved & "
                        f"(\\{q}NetRemovedLow--\\{q}NetRemovedHigh) \\\\")
    out.append(("TabFamilyBody",
                "Results by family, % (mean of two scenarios; appendix). Columns (5): l r r r l = Setting, Untimed decision "
                "accuracy, In-force accuracy, Network-removed in-force accuracy, its 95% bootstrap range.", rows))

    rows = []
    for p in models:
        decode = f"\\{p}DecodeMsPerTok" if f"{p}DecodeMsPerTok" in m else "--"
        rows.append(f"\\{p}RowLabel & \\{p}NetSec & (\\{p}NetSecLow--\\{p}NetSecHigh) & \\{p}PrefillMsPerKTok & {decode} & "
                    f"\\{p}LatencyMedian & \\{p}LatencyPNinetyFive \\\\")
    out.append(("TabLatencyBody",
                "Latency decomposition. Columns (7): l r l r r r r = Model, Estimated network s per request, its 95% "
                "bootstrap range, Prefill ms per 1k uncached input tokens, Decode ms per output token (-- = no generated "
                "text, not modelled), Latency p50 s, Latency p95 s.", rows))

    rows = []
    for name, fp, _ in SCENARIOS:
        if rows:
            rows.append(r"\midrule")
        for k, p in enumerate(models):
            q = f"{p}{name}"
            rows.append(" & ".join([f"\\{fp}Label{{}} {name[-1]}" if k == 0 else "", f"\\{p}RowLabel", f"\\{q}Untimed",
                                    f"\\{q}Auc", f"\\{q}InForce", f"\\{q}InForceSeg", f"\\{q}ErrNoDecisionSec", f"\\{q}ErrStaleSec",
                                    f"\\{q}ErrJudgmentSec", f"\\{q}ErrCompoundSec", f"\\{q}LatencyMedian"]) + r" \\")
    out.append(("TabScenarioBody",
                "Per-scenario results (appendix). Columns (10): l l r r r r r r r r = Scenario, Model, Untimed %, In-force %, "
                "Segment-balanced in-force %, Error seconds (120 s per scenario at the 2 s recording cadence) with no decision, stale (outdated source, correct for "
                "it), judgment (current source, wrong), compound (outdated source, wrong), Latency p50 s.", rows))

    rows = []
    interval = Decimal(m.items["ReleaseIntervalSec"].value)
    scales = [("Half", Decimal("0.5")), ("TwoThirds", Decimal(2) / Decimal(3)), ("", Decimal(1)),
              ("ThreeHalves", Decimal("1.5")), ("Double", Decimal(2))]
    labels = {"Half": r"$\times$0.5", "TwoThirds": r"$\times$2/3", "": r"$\times$1",
              "ThreeHalves": r"$\times$1.5", "Double": r"$\times$2"}
    for name, scale in scales:
        equivalent = interval / scale
        eq = fixed(equivalent, 2)
        cells = [f"\\{p}InForce" if not name else f"\\{p}InForceDelay{name}" for p in models]
        rows.append(" & ".join([labels[name], eq, *cells]) + r" \\")
    out.append(("TabPaceBody",
                f"In-force accuracy (%) of each recorded pass evaluated at other time-step intervals (every latency scaled). "
                f"Columns ({2 + len(models)}): l r {'r ' * len(models)}= "
                f"Latency scale, Equivalent time-step interval (s), {', '.join(FACTS_COLUMNS[p] for p in models)}.", rows))

    rows = [" & ".join([r"SDB (eight scenarios)", "--", *[f"\\RegimeLite{p}" for p in models]]) + r" \\", r"\midrule"]
    for name, label, _ in REGIMES:
        rows.append(" & ".join([label, f"\\Regime{name}Changes", *[f"\\Regime{name}{p}" for p in models]]) + r" \\")
    out.append(("TabRegimeBody",
                f"Projected in-force accuracy (%) = untimed accuracy x oracle share over reference schedules of 60 time steps. "
                f"Columns ({2 + len(models)}): l r {'r ' * len(models)}= Schedule, Reference changes, "
                f"{', '.join(FACTS_COLUMNS[p] for p in models)}.", rows))
    from lite_auc import auc_tables
    out.extend(auc_tables(models))
    return out


# --------------------------------------------------------------------------- output

NAMING = r"""% Naming (letters only; LaTeX macro names cannot contain digits):
%   \<Model><Metric>            one model, overall (equal family macro mean). Model: Luna, LunaNone, Terra, TerraNone, Astra, Jev
%                               (Luna, Terra and Astra: low reasoning effort; *None: no reasoning)
%   \<Model><Family><Metric>    family mean of two scenarios. Family: Debug, Assembly, Support, Presenter
%   \<Model><Scenario><Metric>  one scenario. Scenario: DebugA, DebugB, AssemblyA, AssemblyB, SupportA, SupportB
%   \<Family|Scenario><Fact>    benchmark facts, e.g. \DebugAQuestions, \SupportBRouteOptions, \AssemblyATitle
%   \Pair<Cand><Base>[<Family>]<Outcome>  paired untimed effective decisions: Both, <Base>Only, <Cand>Only, Neither
%   \<A>Minus<B><Metric>        difference in points between two models, named so the value is nonnegative
%   \Num*, \Questions*, \Options*, \Transitions*, ...  benchmark totals; \Net*  network-estimator settings;
%   \Baseline*  local baselines (BestConstant: most frequent composed reference decision per scenario);
%   \Audit*  LLM-agent validity audit (derived from notes/audit_record.json, checked against FACTS.md);
%   \Max*, \Request*, \Retry*  execution; \Traj*, \NumWindows*  Figure 1 window (lite_window.py);
%   \Example*  the appendix example state; *Word  small counts spelled out for prose;
%   \<A>AheadOf<B>Scenarios  scenario counts;  \NumSettings, \NumHostedModels, \NumGPTModels (and *Word)  what was measured;
%   \AstraMiss*  Astra low's single untimed miss (scenario, time steps, answers and the evidence behind the reference)
% Metrics:
%   Untimed        untimed branch-composed decision accuracy (%)      UntimedSeg   its segment-balanced version (%)
%   ExactMatch     all-question exact match, diagnostic (%)            UntimedStates  correct states of 480
%   Auc            primary normalized log-AUC over 0.5--8 s (%)
%   InForce        fixed 2 s diagnostic: correct duration / observed duration (%)
%   InForceSeg     segment-balanced in-force accuracy (%)
%   NetRemoved[Low|High]     network-removed in-force accuracy, estimate and 95% bootstrap range (%)
%   NetRemovedSeg[Low|High]  the same, segment-balanced (%)
%   NetSec[Low|High]         estimated network seconds per request (non-token remainder; may include fixed server time)
%   PrefillMsPerKTok  prefill slope, ms per 1,000 uncached input tokens
%   DecodeMsPerTok    decode slope, ms per output token (undefined for Jev: no generated text, not modelled)
%   Latency{Median,PNinetyFive,Max,Mean}  successful-attempt latency (s); LatencyFloor  fastest time before receipt (s)
%   LateArrivals      % of requests whose reconstructed arrival is after the next evidence release (horizon for the last)
%   {Input,Output,Reasoning}Tok{Median,Total}, InputTok{Min,Max}, CachedTokTotal  tokens per request / per pass
%   Cost{Input,Output,}USD  cost of the recorded pass at standard list prices (USD); Price{Input,Output}  USD per 1M tokens
%   Err{NoDecision,Stale,Incorrect}{Sec,Pct}, ErrTotalSec  error time over the observed horizon (s; % of observed time).
%       Stale = the decision in force was correct for the evidence it answered but not for the current reference.
%   {Stale,Incorrect}ShareOfError  % of error time;  ObservedSec  observed duration summed over scenarios (s)
%   UntimedMinusInForce, NetRemovedMinusInForce[Low|High]  differences in points
%   InForcePhysical   in-force accuracy on the physical wall-clock trace (%); ExcludedDispatchSec  dispatch wait (s)
%   TimingCeiling[Loss]  oracle in-force accuracy: reference answers at the model's recorded latencies (%; 100 minus it);
%       equals the share of time whose decision in force has a current source state
%   InForceDelay{Half,TwoThirds,ThreeHalves,Double}  evaluated at another time-step interval: every latency scaled (%)
%   Err{Judgment,Compound}{Sec,Pct}, Lucky{Sec,Pct}  timing-by-judgment partition: current source but wrong (judgment),
%       outdated and wrong (compound), outdated, wrong for its source but matching the current reference (lucky, correct)
%   UCurrent  accuracy while the source is current (%);  Product  mean over scenarios of untimed x oracle (%)
%   InForceMinusProduct  points;  UCurrentMaxDiff  max |UCurrent - Untimed| (points)
%   Cross<A><B>Sec  time-step interval where A and B have equal in-force accuracy;  Regime<Schedule><Model>  projection (%)
%   DelayApprox, MeanDelaySec  Eq. 3 with untimed accuracy as a factor (%), mean effective delay (s)
%   AcceptedUpdates, Discarded{Updates,AfterHorizon,Older}, ValidResponses, Attempts, FailedAttempts, RetriedRequests,
%   InactiveOnlyErrors (states whose consumed decision is right but an unused answer is wrong), ClampedRequests
% Formatting: percentages and points have one decimal and no % sign (write \LunaInForce\%); measured seconds have two
%   decimals, accumulated error seconds one; ms slopes one decimal; counts are integers ({,} from 10,000); design constants are exact (2, 120, 0.5).
%   Rounding is half-up from the full-precision source value. The trailing comment names the source file:JSON path;
%   "*" means every element, and a parenthesis states the reduction applied."""


def write(m: Macros, inputs: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    head = ["% Generated by paper/analysis/lite_numbers.py; do not edit by hand.",
            "% Regenerate from the repository root: uv run python paper/analysis/lite_numbers.py",
            "% Inputs (sha256):"] + [f"%   {sha256(rel)[:16]}  {rel}" for rel in inputs]
    lines = [*head, "%", NAMING, ""]
    width = min(72, max(len(f"\\newcommand{{\\{x.name}}}{{{x.value}}}") for x in m.items.values()))
    for x in m.items.values():
        definition = f"\\newcommand{{\\{x.name}}}{{{x.value}}}"
        lines.append(f"{definition}{' ' * max(1, width - len(definition))}% {x.source}")
    (OUT / "numbers.tex").write_text("\n".join(lines) + "\n")

    body = [*head, "%",
            "% Table bodies (rows only, booktabs). \\input{generated/numbers} must come first; cells are macros from it.",
            "% Model and family labels below are defaults the paper may define before this file.", ""]
    body += [f"\\providecommand{{\\{k}}}{{{v}}}" for k, v in LABELS.items()] + [""]
    for name, description, rows in tables(m):
        body += [f"% {description}", f"\\newcommand{{\\{name}}}{{%", *[f"  {row}" for row in rows], "}", ""]
    (OUT / "tables.tex").write_text("\n".join(body))


def write_facts(m: Macros, models: dict, bench: dict) -> None:
    lines = ["# SDB verified facts", "", "Generated by `paper/analysis/lite_numbers.py` after frozen-event verification.", "",
             f"Dataset `{bench['manifest'].get('dataset_hash')}`; {len(bench['order'])} scenarios, four families, 60 releases each.",
             "Recorded at 2 s; primary score is normalized log-AUC over 0.5--8 s, equal scenario and family weights.", "",
             "| Setting | Untimed (%) | Log-AUC 0.5--8 s (%) | Common 2 s (%) | Common 8 s (%) | Latency p50 (s) |",
             "|---|---:|---:|---:|---:|---:|"]
    for p in models:
        keys = [f"{p}{key}" for key in ("Untimed", "Auc", "CommonTwo", "CommonEight", "LatencyMedian")]
        lines.append("| " + " | ".join([FACTS_COLUMNS[p], *[m.items[k].value for k in keys]]) + " |")
    v = {k: x.value.replace("\\_", "_") for k, x in m.items.items()}
    lines += ["", f"Astra low is correct at {v['AstraUntimedStates']} of {v['AstraStates']} evaluations across three passes untimed. In pass 1, its miss is "
              f"`{ASTRA_MISS['episode']}` t={v['AstraMissStep']}: it answered {v['AstraMissRoute']} "
              f"(target {v['AstraMissTarget']}, method {v['AstraMissMethod']}); the reference is {v['AstraMissRefRoute']} "
              f"to {v['AstraMissRefNextStep']} at stage {v['AstraMissRefStage']}, because the J2 screw replacement "
              f"(t={v['AstraMissScrewStep']}) and rundown (t={v['AstraMissRundownStep']}, {v['AstraMissRundownNm']} N m) after the "
              f"t={v['AstraMissInspectionStep']} inspection PASS moved the stage back to fasten. At t={v['AstraMissPrevStep']}, "
              "whose state differs only by one heartbeat record, it returned the reference; the original audit's grouped finding "
              "covering both time steps upheld the reference under every lens.",
              "", "The independent LLM-agent audit covers the original six scenarios only; see `audit_summary.md` and `audit_record.json`.",
              "Presenter reference tests and public-rule agreement cover its 120 released states; no equivalent blind LLM-agent audit is claimed.",
              "All numeric macros and their provenance are in `../generated/numbers.tex`; primary reports and recorded-cadence diagnostics are in `../../docs/lite/results/four-family/`.", ""]
    (ROOT / "paper/notes/FACTS.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print every macro with its value and source")
    args = parser.parse_args()
    from lite_repeated import generate_numbers
    return generate_numbers(args)


if __name__ == "__main__":
    raise SystemExit(main())
