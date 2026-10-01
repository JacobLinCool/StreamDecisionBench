"""Verify frozen self-hosted runs and publish standalone / hybrid measurements.

No model runtime, API or hardware profiler is invoked. Original-clock standalone
results and common-clock compositions remain distinct in the output.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from lite_numbers import FACTS_COLUMNS, FAMILIES, MODELS, fixed
from lite_trajectory_value import LABELS, POLICY_MACROS, integrate
from streamdecisionbench.lite.__main__ import rescore_run
from streamdecisionbench.lite.core import digest
from trajectory_replay import METRICS, PARTITION, aggregate, evaluate, prepare

POLICY_PATH = ROOT / "paper/analysis/openweight_policy.json"
OUT = ROOT / "docs/research/openweight-hybrids"
RESULT_START = "<!-- BEGIN GENERATED SDB RESULTS -->"
RESULT_END = "<!-- END GENERATED SDB RESULTS -->"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(value: float) -> str:
    return fixed(value * 100, 2)


def verified_run(path: Path) -> tuple[dict, dict]:
    run = rescore_run(path)
    frozen = run["frozen"]
    if sha(path / "events.jsonl") != frozen["events_sha256"]:
        raise ValueError(f"{path.name}: event hash mismatch")
    episodes = run["episodes"]
    if len(episodes) != 8 or sum(len(ep["steps"]) for ep in episodes) != 480:
        raise ValueError(f"{path.name}: incomplete dataset coverage")
    if len({ep["episode_id"] for ep in episodes}) != 8:
        raise ValueError(f"{path.name}: duplicate scenario")
    for ep in episodes:
        eid = ep["episode_id"]
        if digest(ep) != frozen["dataset_manifest"]["hashes"][eid]:
            raise ValueError(f"{path.name}/{eid}: episode hash mismatch")
        expected = {s["t"] for s in ep["steps"]}
        for records in (run["responses"][eid], run["releases"][eid]):
            if len(records) != len(expected) or {r["t"] for r in records} != expected:
                raise ValueError(f"{path.name}/{eid}: duplicate or missing state")
    evidence = {file: sha(path / file) for file in ("run.json", "episodes.json", "events.jsonl")}
    return run, evidence


def verify_audit(spec: dict, run: dict) -> dict:
    path = ROOT / "runs" / spec["audit"]
    audit = json.loads(path.read_text())
    if audit["dataset_hash"] != run["frozen"]["dataset_manifest"]["dataset_hash"]:
        raise ValueError(f"{spec['name']}: audit dataset mismatch")
    if "audit_setting" in spec:
        row = audit["settings"][spec["audit_setting"]]
        count = row["states"]
        if row["model_revision"] != run["frozen"]["config"]["model_revision"]:
            raise ValueError(f"{spec['name']}: audit model mismatch")
    else:
        row = audit
        count = row["requests"]
        if sha(path) != run["frozen"]["config"]["input_audit_sha256"]:
            raise ValueError(f"{spec['name']}: audit hash mismatch")
    if count != 480 or row["question_rows"] != 3120 or row["issues"]:
        raise ValueError(f"{spec['name']}: incomplete or invalid input audit")
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path),
            "max_sequence_tokens": row["max_sequence_tokens"], "issues": len(row["issues"])}


def original_clock(scenarios, run):
    return [replace(sc, releases_s=tuple(r["release_s"] for r in run["releases"][sc.episode_id]))
            for sc in scenarios]


def verify_standalone(scenarios, name, run):
    """Compare all six time classes with the independent original-clock scorer."""
    own = original_clock(scenarios, run)
    expected = {r["episode_id"]: r for r in run["scores"]["per_episode"]}
    nominal = []
    for sc in own:
        actual = evaluate(sc, name, None, 2)
        recorded = expected[sc.episode_id]
        pairs = [(actual["accuracy"], recorded["time_accuracy"])] + [
            (actual[k], recorded["time_partition_seconds"][k] / recorded["observed_duration_s"])
            for k in PARTITION]
        if any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-12) for a, b in pairs):
            raise ValueError(f"{name}/{sc.episode_id}: standalone scorer disagrees")
    for sc in scenarios:
        nominal.append(abs(evaluate(sc, name, None, 2)["accuracy"]
                           - expected[sc.episode_id]["time_accuracy"]) * 100)
    return own, max(nominal)


def compare_published(result, report, name, tolerance):
    for scope in ["overall", *[f for _, f in FAMILIES]]:
        actual = result["overall"] if scope == "overall" else result["by_family"][scope]
        expected = report["auc"]["primary"]["overall"] if scope == "overall" else report["auc"]["primary"]["by_family"][scope]
        for metric in ("accuracy", "oracle", *PARTITION):
            if abs(actual[metric] - expected[metric]) > tolerance:
                raise ValueError(f"{name}/{scope}/{metric}: published AUC disagrees")


def analyze():
    policy = json.loads(POLICY_PATH.read_text())
    auc_policy = json.loads((ROOT / "paper/analysis/evaluation_policy.json").read_text())
    paths = {name: ROOT / "runs" / folder for name, _, folder in MODELS}
    paths.update({spec["name"]: ROOT / "runs" / spec["run"] for spec in policy["settings"]})
    runs, provenance = {}, {}
    for name, path in paths.items():
        runs[name], hashes = verified_run(path)
        provenance[name] = {"run": str(path.relative_to(ROOT)), "sha256": hashes}
    scenarios = prepare(runs)  # Reject different frozen content, including references.
    data = {"policy": policy, "auc_policy": auc_policy, "provenance": provenance,
            "hosted": {}, "standalone": {}, "systems": {}, "controls": {}, "verification": {}}
    report_names = {name: report for name, report, _ in MODELS}
    gaps = {}
    for name, run in runs.items():
        spec = next((s for s in policy["settings"] if s["name"] == name), None)
        report_dir = report_names[name] if spec is None else spec["run"].replace("/runs/", "/")
        report_path = ROOT / "docs/lite/results" / report_dir / "analysis.json"
        report = json.loads(report_path.read_text())
        if report["events_sha256"] != run["frozen"]["events_sha256"]:
            raise ValueError(f"{name}: published report uses different events")
        if report["dataset_hash"] != run["frozen"]["dataset_manifest"]["dataset_hash"]:
            raise ValueError(f"{name}: published report uses different data")
        if report["config"] != run["frozen"]["config"]:
            raise ValueError(f"{name}: published execution configuration disagrees")
        provenance[name]["published_report"] = {"path": str(report_path.relative_to(ROOT)), "sha256": sha(report_path)}
        own, gaps[name] = verify_standalone(scenarios, name, run)
        # Hosted summary retains its existing published aggregate; the two
        # composition controls are independently integrated below.
        if spec is None:
            data["hosted"][name] = {"label": FACTS_COLUMNS[name], "report": report_dir,
                "model": run["frozen"]["config"]["model"],
                "accuracy": report["auc"]["primary"]["overall"]["accuracy"],
                "untimed": report["scores"]["overall"]["untimed_decision_accuracy"],
                "median_s": report["latency_s"]["p50"]}
            continue
        if "audit" in spec:
            provenance[name]["input_audit"] = verify_audit(spec, run)
        cohort = (ROOT / "runs" / spec["run"]).parent.parent
        source_path = cohort / "source-provenance.json"
        provenance[name]["native_sources"] = {"path": str(source_path.relative_to(ROOT)),
            "sha256": sha(source_path), "revisions": json.loads(source_path.read_text())}
        if "prepared_checkpoint" in run["frozen"]["config"]:
            weight_path = cohort / (Path(spec["run"]).name + ".prepared.json")
            weights = json.loads(weight_path.read_text())
            if weights != run["frozen"]["config"]["prepared_checkpoint"]:
                raise ValueError(f"{name}: prepared weight provenance disagrees")
            provenance[name]["weights"] = {"path": str(weight_path.relative_to(ROOT)), "sha256": sha(weight_path)}
        result = integrate(own, name, None, "freshest", auc_policy["primary"])
        compare_published(result, report, name, auc_policy["integration"]["tolerance"])
        delays = [r["successful_attempt_s"] for ep in run["scores"]["per_episode"]
                  for r in ep["normalization"]["records"]]
        for key, quantile in [("p50", 50), ("p95", 95)]:
            if abs(float(np.percentile(delays, quantile)) - report["latency_s"][key]) > 1e-12:
                raise ValueError(f"{name}: latency {key} disagrees")
        if abs(run["scores"]["overall"]["untimed_decision_accuracy"]
               - report["scores"]["overall"]["untimed_decision_accuracy"]) > 1e-12:
            raise ValueError(f"{name}: untimed accuracy disagrees")
        data["standalone"][name] = {"spec": spec, "integrated": result,
            "untimed": run["scores"]["overall"]["untimed_decision_accuracy"],
            "latency_s": report["latency_s"], "config": run["frozen"]["config"],
            "retry_reliability": report["retry_reliability"]}
        print(f"Verified standalone {name}", flush=True)
    slow = policy["correction_setting"]
    if data["hosted"][slow]["accuracy"] != max(r["accuracy"] for n, r in data["hosted"].items() if n != "Jev"):
        raise ValueError("declared correction-setting selection no longer matches hosted results")
    data["controls"]["TerraNone"] = integrate(scenarios, slow, None, "freshest", auc_policy["primary"])
    data["controls"]["JevTerraNone"] = integrate(scenarios, "Jev", slow, "freshest", auc_policy["primary"])
    for spec in policy["settings"]:
        name = spec["name"]
        data["systems"][name] = {}
        for arbitration in policy["policies"]:
            data["systems"][name][arbitration] = {
                "integrated": integrate(scenarios, name, slow, arbitration, auc_policy["primary"]),
                "fixed_two": aggregate([evaluate(sc, name, slow, 2, arbitration) for sc in scenarios])}
            print(f"Replayed {name}/{arbitration}", flush=True)
    hosted_compositions = json.loads((ROOT / "docs/research/trajectory-value/analysis.json").read_text())
    if hosted_compositions["auc_policy"] != auc_policy:
        raise ValueError("hosted composition report uses a different evaluation policy")
    shared = {"TerraNone": hosted_compositions["standalone"]["TerraNone"]["integrated"],
              "JevTerraNone": hosted_compositions["systems"]["TerraNone"]["freshest"]["integrated"]}
    for name, expected in shared.items():
        for metric in METRICS:
            if not math.isclose(data["controls"][name]["overall"][metric],
                                expected["overall"][metric], rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"{name}: shared hosted composition disagrees for {metric}")
    data["verification"] = {"standalone_partition_checks": len(runs) * len(scenarios),
        "max_nominal_recorded_gap_points": max(gaps.values()), "nominal_recorded_gaps_points": gaps,
        "shared_hosted_control_checks": len(shared) * len(METRICS)}
    sources = ["paper/analysis/lite_openweight.py", "paper/analysis/openweight_policy.json",
        "paper/analysis/lite_trajectory_value.py", "paper/analysis/trajectory_replay.py",
        "paper/analysis/lite_numbers.py", "paper/analysis/evaluation_policy.json",
        "paper/analysis/figstyle.py", "src/streamdecisionbench/lite/__main__.py",
        "src/streamdecisionbench/lite/core.py", "src/streamdecisionbench/lite/scoring.py",
        "src/streamdecisionbench/lite/retry_scoring.py", "src/streamdecisionbench/lite/interval_scoring.py",
        "docs/research/trajectory-value/analysis.json"]
    data["sources_sha256"] = {p: sha(ROOT / p) for p in sources}
    return data


def standalone_table(data, prefix=""):
    lines = ["| Setting | Log-AUC 0.5–8 s (%) | Untimed (%) | p50 / p95 (s) | GPU; same-host latency |",
             "|---|---:|---:|---:|---|"]
    for name, row in data["standalone"].items():
        spec = row["spec"]
        report = spec["run"].replace("/runs/", "/")
        lines.append(f"| [{spec['label']}]({prefix}docs/lite/results/{report}/REPORT.md) | "
            f"{100*row['integrated']['overall']['accuracy']:.2f} | {100*row['untimed']:.2f} | "
            f"{row['latency_s']['p50']:.3f} / {row['latency_s']['p95']:.3f} | {spec['gpu']} |")
    return lines


def hybrid_summary(data):
    lines = ["| System | Log-AUC 0.5–8 s (%) |", "|---|---:|"]
    for key, label in [("TerraNone", "Terra none alone"), ("JevTerraNone", "Jev + Terra none")]:
        lines.append(f"| {label} | {100*data['controls'][key]['overall']['accuracy']:.2f} |")
    for name, row in data["standalone"].items():
        lines.append(f"| {row['spec']['label']} + Terra none | {100*data['systems'][name]['freshest']['integrated']['overall']['accuracy']:.2f} |")
    return lines


def render_results(data):
    lines = ["## Results", "", "One recorded pass per setting over all 480 states (8 scenarios in 4 families), recorded at a 2 s",
        "time-step interval. The primary score is normalized log-AUC over 0.5–8 s, with equal scenario weights",
        "within each family and then equal family weights. Interval evaluations retain the recorded answers",
        "and latencies; they assume service latency does not change with the request rate.", "",
        "The 0.5–8 s domain spans update rates four times faster and slower than the 2 s recording cadence.",
        "Each doubling interval receives equal log weight, balancing faster and slower conditions around that cadence.",
        "These bounds define a controlled evaluation domain; deployment-specific event rates can motivate other ranges.", "",
        "### Hosted APIs", "", "Latency includes the remote service and internet round trip from the benchmark client.", "",
        "| Setting | Model | Log-AUC 0.5–8 s (%) | Untimed (%) | Median latency (s) |", "|---|---|---:|---:|---:|"]
    for row in sorted(data["hosted"].values(), key=lambda r: -r["accuracy"]):
        lines.append(f"| {row['label']} | `{row['model']}` | {100*row['accuracy']:.2f} | {100*row['untimed']:.2f} | {row['median_s']:.3f} |")
    lines += ["", "[Family scores and hosted reports](docs/lite/results/four-family/README.md).", "",
        "### Self-hosted open-weight settings", "", *standalone_table(data), "",
        "All seven settings use BF16 backbones and native decision readouts. Benchmark and model run on the",
        "same GPU host; latency includes request processing, runtime queueing and inference, and excludes",
        "download, initialization and warmup. These rows describe the measured deployments: the GPU cohorts",
        "and hosted APIs are not a controlled hardware comparison.", "",
        "Nimble scores each field sequentially with its full prompt; its latency covers the complete decision",
        "request. The Qwen row uses SemIf's direct option logits with thinking disabled; it is not an evaluation",
        "of Qwen's usual generated answers. Details: [RTX PRO 6000 cohort](docs/lite/results/runpod-openweight-20260930/README.md)",
        "and [L40S cohort](docs/lite/results/runpod-openweight-20260930-round2/README.md).", "",
        "### Provisional decisions with corrections", "", *hybrid_summary(data), "",
        "Both components receive each state. A provisional answer never moves the active source backward;",
        "the correction wins equal-source ties and, under the **freshest-source** rule used above, cannot",
        "overwrite a newer source. These are counterfactual compositions of independent recordings on",
        "common nominal releases, retaining original measured latencies. Joint deployment contention is unmeasured.", "",
        "The Jev pairing improves on Terra none alone, while several faster self-hosted components reduce",
        "accuracy: an incorrect answer for a newer state can displace a still-correct correction. Speed alone",
        "does not determine whether composition helps. Nimble occupies the provisional slot in this analysis",
        "even though its recorded median latency exceeds Terra none's.", "",
        "[Complete local/policy matrix, curves and provenance](docs/research/openweight-hybrids/README.md);",
        "[all five Jev/GPT pairs and three arbitration policies](docs/research/trajectory-value/README.md).",
        "Each setting has one pass and adjacent states are dependent; differences do not establish stable rankings.", "",
        "Regenerate the verified summary, paper tables and composition curves without model calls:", "",
        "```bash", "uv run --group paper python paper/analysis/lite_openweight.py", "```"]
    return "\n".join(lines)


def render_report(data):
    lines = ["# Self-hosted decisions and their counterfactual compositions", "",
        "Reproduce: `uv run --group paper python paper/analysis/lite_openweight.py`.", "",
        "All primary values are normalized log-AUC over 0.5–8 s, equally averaged over scenarios within each",
        "family and then families. Standalone measurements retain their original release clocks; compositions",
        "use common nominal releases. Every recorded successful-attempt duration plus commit lag is retained.", "",
        *standalone_table(data, "../../../"), "", "## Pair selection and acceptance", "", data["policy"]["selection"], "",
        "The provisional component never regresses the active source; Terra none wins equal-source ties.",
        "Its correction may regress by zero ticks (freshest), one tick (one-tick lag), or without a cross-component",
        "bound (late override). Each component maintains its own source high-water mark even on rejected",
        "deliveries. No rule consults references or output correctness. Nimble is a provisional-role control,",
        "not a faster component in these recordings.", "", *hybrid_summary(data), "",
        "## Complete local/policy matrix", "",
        "| Provisional setting | Arbitration | Log-AUC 0.5–8 s (%) | Fixed 2 s A (%) | Correction time share, log-weighted (%) |",
        "|---|---|---:|---:|---:|"]
    for name, policies in data["systems"].items():
        for policy, row in policies.items():
            integrated = row["integrated"]["overall"]
            lines.append(f"| {data['standalone'][name]['spec']['label']} | {LABELS[policy]} | "
                f"{100*integrated['accuracy']:.2f} | {100*row['fixed_two']['overall']['accuracy']:.2f} | {100*integrated['slow_share']:.2f} |")
    lines += ["", "## Verification and scope", "",
        f"Original-clock replay reproduces correctness and all six time classes in {data['verification']['standalone_partition_checks']} setting/scenario checks.",
        f"The largest nominal/original-clock difference at 2 s is {data['verification']['max_nominal_recorded_gap_points']:.6f} percentage points.",
        "The log integral is analytical between every release/arrival crossing; a third interior point checks each affine piece.",
        "Published standalone aggregates and family partitions are checked against independently recomputed areas.",
        "The observations cover one pass per setting on synthetic development scenarios. Retiming assumes fixed",
        "service latency; hardware normalization, joint contention, repeated-run stability and generative Qwen",
        "performance are outside the measurements. Sol-2B had no executable public native runtime and receives no score.", "",
        "[analysis.json](analysis.json) includes all scenario/family partitions, full curves, raw event and input-audit",
        "hashes, execution configuration and analysis-source hashes. Original recording files are unchanged."]
    return "\n".join(lines) + "\n"


def write_tex(data):
    numbers = ["% Generated by paper/analysis/lite_openweight.py; do not edit."]
    def add(name, value, source):
        numbers.extend([f"% docs/research/openweight-hybrids/analysis.json: {source}", f"\\newcommand{{\\Ow{name}}}{{{value}}}"])
    add("NumSettings", str(len(data["standalone"])), "policy.settings")
    words = {7: "seven", 13: "thirteen"}
    add("NumSettingsWord", words[len(data["standalone"])], "policy.settings")
    add("TotalSettingsWord", words[len(data["hosted"]) + len(data["standalone"])], "hosted + standalone")
    add("NominalGap", fixed(data["verification"]["max_nominal_recorded_gap_points"], 6), "verification.max_nominal_recorded_gap_points")
    for name, row in data["standalone"].items():
        for suffix, value in [("Auc", pct(row["integrated"]["overall"]["accuracy"])), ("Untimed", pct(row["untimed"])),
                              ("Median", fixed(row["latency_s"]["p50"], 3)), ("Tail", fixed(row["latency_s"]["p95"], 3))]:
            add(name + suffix, value, f"standalone.{name}")
        for prefix, family in FAMILIES:
            add(name + prefix + "Auc", pct(row["integrated"]["by_family"][family]["accuracy"]), f"standalone.{name}.integrated.by_family.{family}")
        for policy, result in data["systems"][name].items():
            add(name + POLICY_MACROS[policy] + "Auc", pct(result["integrated"]["overall"]["accuracy"]), f"systems.{name}.{policy}.integrated.overall.accuracy")
    for name, row in data["controls"].items():
        add(name + "Auc", pct(row["overall"]["accuracy"]), f"controls.{name}.overall.accuracy")
    (ROOT / "paper/generated/openweight_numbers.tex").write_text("\n".join(numbers) + "\n")
    tables = ["% Generated by paper/analysis/lite_openweight.py; do not edit."]
    def table(command, rows):
        tables.append("\\newcommand{\\" + command + "}{%\n" + "\n".join(rows) + "\n}")
    table("TabOpenweightFamilies", [" & ".join([row["spec"]["label"],
        *[f"\\Ow{name}{prefix}Auc" for prefix, _ in FAMILIES], f"\\Ow{name}Auc", f"\\Ow{name}Untimed"]) + r" \\"
        for name, row in data["standalone"].items()])
    table("TabOpenweightLatency", [" & ".join([row["spec"]["label"], row["spec"]["gpu"],
        f"\\Ow{name}Median", f"\\Ow{name}Tail"]) + r" \\" for name, row in data["standalone"].items()])
    table("TabOpenweightHybrids", [" & ".join([row["spec"]["label"],
        *[f"\\Ow{name}{POLICY_MACROS[p]}Auc" for p in data["policy"]["policies"]]]) + r" \\"
        for name, row in data["standalone"].items()])
    (ROOT / "paper/generated/openweight_tables.tex").write_text("\n".join(tables) + "\n")


def plot(data):
    from figstyle import TEXT, PALETTE, figure, save, use_style
    use_style()
    fig, ax = figure(width=TEXT, ratio=2.65 / TEXT)
    for key, label, color, style in [("TerraNone", "Terra none alone", "#777777", "--"),
                                    ("JevTerraNone", "Jev + Terra none", PALETTE["blue"], "-")]:
        curve = data["controls"][key]["curve"]
        ax.plot(curve["intervals_s"], np.array(curve["accuracy"]) * 100, label=label, color=color, linestyle=style)
    for name, color, style in [("DJev", "orange", "-"), ("Kev", "green", "-."), ("QwenLogits", "purple", ":")]:
        curve = data["systems"][name]["freshest"]["integrated"]["curve"]
        ax.plot(curve["intervals_s"], np.array(curve["accuracy"]) * 100,
                label=data["standalone"][name]["spec"]["label"] + " + Terra none", color=PALETTE[color], linestyle=style)
    ax.set(xscale="log", xlim=(.5, 8), ylim=(0, 100), xlabel="Time-step interval (s)", ylabel="In-force accuracy (%)")
    ax.set_xticks([.5, 1, 2, 4, 8], labels=["0.5", "1", "2", "4", "8"])
    ax.minorticks_off()
    ax.legend(loc="upper left", fontsize=7, frameon=False, ncol=2)
    save(fig, str(ROOT / "paper/figures/fig_openweight_hybrids"))


def main():
    data = analyze()  # Validate every input and result before publishing.
    OUT.mkdir(parents=True, exist_ok=True)
    path = ROOT / "README.md"
    text = path.read_text()
    if text.count(RESULT_START) != 1 or text.count(RESULT_END) != 1:
        raise ValueError("README must contain exactly one generated-results region")
    before, rest = text.split(RESULT_START)
    _, after = rest.split(RESULT_END)
    (OUT / "analysis.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    (OUT / "README.md").write_text(render_report(data))
    write_tex(data)
    path.write_text(before + RESULT_START + "\n" + render_results(data) + "\n" + RESULT_END + after)
    plot(data)
    print(f"Wrote {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
