"""Reproduce a frozen SDB run report and local baseline diagnostics; no API calls."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np

from streamdecisionbench.adapters.local import FirstOptionAdapter, LexicalAdapter
from streamdecisionbench.jev import committed_answer
from streamdecisionbench.lite.core import compose, decode, digest, request_for, sources
from streamdecisionbench.lite.__main__ import PHYSICAL_PROTOCOL, RETRY_PROTOCOL, rescore_run
from network import network_adjustment


NAMES = {"live_debugging": "IDE debugging", "procedural_coaching": "Assembly",
         "support_call_assist": "Support", "presenter_voice_control": "Presenter voice control"}
ROOT = Path(__file__).resolve().parents[2]


def model_label(config: dict) -> str:
    return " ".join(part for part in (config["model"], config["reasoning_effort"]) if part)


def relative_link(target: Path, output: Path) -> str:
    return Path(os.path.relpath(target.resolve(), output.resolve())).as_posix()


def command_path(path: Path) -> str:
    """Repository-relative path (relative even outside the repository), so reports name no machine path."""
    return Path(os.path.relpath(path.resolve(), ROOT)).as_posix()


def _combined_from(run: Path, parts: list[dict] | None) -> list[dict] | None:
    """Merge parts with repository-relative paths; run.json stores them relative to the merged run folder."""
    if parts is None:
        return None
    return [{**part, "run": command_path(run / part["run"])} for part in parts]


def _latencies(records: list[dict], *, successful_attempt: bool = False) -> dict:
    timed = [r["attempts"][-1] for r in records] if successful_attempt else records
    values = [r["completed_s"] - r["started_s"] for r in timed]
    return {"p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95)), "max": max(values)}


def _retry_report_lines(data: dict) -> list[str]:
    reliability = data["retry_reliability"]
    raw, latency = data["raw_wallclock_scores"], data["raw_wallclock_latency_s"]
    policy = data["config"].get("rate_limit_policy")
    fastino = policy == "http425_429_503_retry_after_shared_cooldown_v1"
    rate_limits = fastino or policy == "http429_retry_after_shared_cooldown_v1"
    statuses = "425, 429, and 503" if fastino else "429"
    return [
        "## Transport reliability and raw-clock diagnostics", "",
        f"- Attempt error rate: {reliability['attempt_error_rate']:.2%} "
        f"({reliability['failed_attempts']} failed attempts / {reliability['attempts']} total attempts, including final successes).",
        f"- Logical request retry rate: {reliability['retried_logical_rate']:.2%} "
        f"({reliability['retried_logical_requests']} retried requests / {reliability['logical_requests']} logical requests).",
        f"- Failed attempt types: {json.dumps(reliability['attempt_errors_by_type'], ensure_ascii=False)}.",
        f"- Failed attempts took {reliability['failed_attempt_duration_s']:.3f} s in total; "
        f"excluded failures and retry waits total {reliability['excluded_retry_s']:.3f} s, "
        f"and excluded dispatch queueing totals {reliability['excluded_dispatch_s']:.3f} s. "
        "Requests can overlap, so these sums are not the recording's wall-clock duration.",
        f"- At most {data['config']['max_attempts']} attempts per request; the first retry is immediate, "
        f"then backoff starts at {data['config']['retry_delay_s']:g} s and is capped at 8 s. SDK retries are disabled.",
        *([f"- The immediate-first-retry rule above applies to transport failures. HTTP {statuses} uses "
           "Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. "
           "Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. "
           f"Concurrency is limited to {data['config']['workers']} workers; rate-limit attempts count toward the same attempt budget."]
          if rate_limits else []),
        *(["- Fastino HTTP 425 waits at least 60 s for model warmup; all transient HTTP attempts "
           "share the same cooldown and bounded attempt budget."] if fastino else []),
        "", "The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:", "",
        "| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |", "|---|---:|---:|",
        f"| Overall | {raw['overall']['time_accuracy']:.2%} | {raw['overall']['segment_time_accuracy']:.2%} |",
        *[f"| {NAMES[family]} | {row['time_accuracy']:.2%} | {row['segment_time_accuracy']:.2%} |"
          for family, row in raw["by_family"].items()],
        "", f"Raw logical request duration, including failed attempts and retry waits: p50 {latency['p50']:.3f} s, "
        f"p95 {latency['p95']:.3f} s; {sum(row['accepted_updates'] for row in raw['per_episode'])} accepted raw-clock updates.",
        "", "Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. "
        "API and response validity determine success. Reference-answer correctness never triggers a retry.", "",
    ]


def _network_report_lines(net: dict) -> list[str]:
    pct = lambda x: f"{100*x:.2f}%"
    n, s = net["network_s"], net["scores"]
    decode = (f"decode {1000 * net['decode_s_per_output_token']:.2f} ms/token"
              if net["decode_s_per_output_token"] is not None else "no decode term (the model does not generate text)")
    lines = ["## Network-removed estimate (secondary)", "",
             "Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + "
             "decode (proportional to output tokens, for text-generating models). The token-independent remainder "
             "is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept "
             "of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario "
             "bootstrap samples with blocks of 10 consecutive releases.", "",
             f"Estimated network {n['estimate']:.3f} s (range {n['low']:.3f}–{n['high']:.3f} s); "
             f"prefill {1000 * net['prefill_s_per_1k_input_tokens']:.1f} ms/1k tokens; {decode}; "
             f"fastest response {net['latency_floor_s']:.3f} s; {s['estimate']['clamped_requests']} requests clamped at receipt.", "",
             "| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |", "|---|---:|---:|---:|---:|"]
    scopes = [("Overall", lambda block: block["overall"])]
    scopes += [(NAMES[f], lambda block, f=f: block["by_family"][f]) for f in s["estimate"]["by_family"]]
    for name, pick in scopes:
        lines.append(f"| {name} | {pct(pick(net['observed']))} | {pct(pick(s['estimate'])['time_accuracy'])} | "
                     f"{pct(pick(s['low'])['time_accuracy'])}–{pct(pick(s['high'])['time_accuracy'])} | "
                     f"{pct(pick(net['untimed_ceiling']))} |")
    if net["negative_intercept_projected"]:
        raw = net["unconstrained_intercept_s"]
        lines += ["", f"Unconstrained intercept {raw['estimate']:.6f} s (range {raw['low']:.6f}–{raw['high']:.6f} s). "
                  "Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay "
                  "projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged."]
    lines += ["", "This secondary estimate leaves the primary score unchanged. The token-independent remainder "
              "can include fixed server time, so it bounds the network effect from above. The range reflects "
              "estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level "
              "diagnostic, not an upper bound for arbitrary in-force trajectories.", ""]
    return lines


def analyze(run: Path) -> dict:
    verified = rescore_run(run)
    frozen, episodes = verified["frozen"], verified["episodes"]
    episode_hashes = {e["episode_id"]: digest(e) for e in episodes}
    responses = verified["responses"]
    recomputed = verified["scores"]
    per = recomputed["per_episode"]
    normalized = frozen["config"]["protocol"] == RETRY_PROTOCOL
    baselines = {}
    for name, adapter_type in (("first_option", FirstOptionAdapter), ("lexical_overlap", LexicalAdapter)):
        rows = []
        for e in episodes:
            adapter = adapter_type()
            adapter.start_episode(e["episode_id"])
            correct = []
            for s in e["steps"]:
                request = request_for(e, s)
                answer = adapter.system_one(request)["answers"]
                wire = {k: committed_answer(q, answer[k]) for k, q in e["questions"].items()}
                pred = decode(e, wire)
                correct.append(compose(e["decision_spec"], pred) == compose(e["decision_spec"], s["gold"]))
            adapter.close()
            rows.append({"episode_id": e["episode_id"], "family": e["task_family"], "accuracy": mean(correct)})
        baselines[name] = {"overall": mean(r["accuracy"] for r in rows), "per_episode": rows,
                           "by_family": {f: mean(r["accuracy"] for r in rows if r["family"] == f) for f in recomputed["by_family"]}}
    records = [r for rows in responses.values() for r in rows]
    family_for = {e["episode_id"]: e["task_family"] for e in episodes}
    usage = {k: sum((r.get("usage") or {}).get(k, 0) for r in records)
             for k in ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")}
    data = {"run": command_path(run), "config": frozen["config"], "dataset_hash": frozen["dataset_manifest"]["dataset_hash"],
            "time_basis": recomputed["time_basis"] if normalized else PHYSICAL_PROTOCOL,
            "episode_hashes": episode_hashes, "run_sources": frozen["run_sources"], "events_sha256": frozen["events_sha256"],
            "analysis_sources": {**sources(), "scripts/lite/lite_report.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "episode_order": [e["episode_id"] for e in episodes],
            "episode_specs": [{"episode_id": e["episode_id"], "title": e["title"], "tick_seconds": e["tick_seconds"],
                               "duration_s": len(e["steps"]) * e["tick_seconds"]} for e in episodes],
            "started_at_utc": frozen["started_at_utc"], "finished_at_utc": frozen["finished_at_utc"],
            "combined_from": _combined_from(run, frozen.get("combined_from")),
            "scores": recomputed, "baselines": baselines, "usage": usage,
            "raw_wallclock_scores": verified["raw_wallclock_scores"],
            "raw_wallclock_latency_s": _latencies(records) if normalized else None,
            "retry_reliability": recomputed["retry_reliability"] if normalized else None,
            "network_adjustment": (network_adjustment(episodes, responses, verified["releases"],
                                                      generates_text=frozen["config"].get("provider", "openai") == "openai")
                                   if normalized else None),
            "models_returned": dict(Counter(r.get("model") for r in records if r["ok"])),
            "latency_s": _latencies(records, successful_attempt=normalized),
            "latency_by_family_s": {f: _latencies([r for r in records if family_for[r["episode_id"]] == f], successful_attempt=normalized)
                                    for f in recomputed["by_family"]},
            "environment": {"python": platform.python_version(), "system": platform.system(),
                            "openai_sdk": importlib.metadata.version("openai")},
            "total_failed": sum(not r["ok"] for r in records),
            "accepted_updates": sum(r["accepted_updates"] for r in per),
            "discarded_updates": dict(sum((Counter(r["discarded_updates"]) for r in per), Counter())),
            "error_seconds": {k: sum(r["error_seconds"][k] for r in per)
                              for k in ("no_decision", "source_correct", "source_incorrect")},
            "max_release_lag_s": max(r["max_release_lag_s"] for r in per),
            "max_dispatch_lag_s": max(r["max_dispatch_lag_s"] for r in per)}
    return data



def render_report(data: dict, output: Path) -> str:
    """Render English diagnostics from an existing analysis without changing evidence."""
    scores, rows = data["scores"], data["scores"]["per_episode"]
    config, label = data["config"], model_label(data["config"])
    normalized = config["protocol"] == RETRY_PROTOCOL
    timing_label = "In-force accuracy (transport retries excluded)" if normalized else "In-force accuracy (raw clock)"
    request_description = ("One final valid response per state; transport failures are retried as configured."
                           if normalized else "Each state is queried once.")
    if config.get("rate_limit_policy") == "http429_retry_after_shared_cooldown_v1":
        timing_label = "In-force accuracy (failed attempts and retry waits excluded)"
        request_description += " HTTP 429 honors Retry-After through a shared cooldown within the attempt budget."
    duration_text = "/".join(f"{duration:g}" for duration in sorted({e["duration_s"] for e in data["episode_specs"]}))
    tick_text = "/".join(f"{tick:g}" for tick in sorted({e["tick_seconds"] for e in data["episode_specs"]}))
    command = shlex.join(["uv", "run", "python", "scripts/lite/lite_report.py", "--run", command_path(ROOT / data["run"]),
                          "--out", command_path(output)])
    task_docs = ROOT / "docs" / "lite"
    pct = lambda x: f"{100*x:.2f}%"
    lines = [f"# SDB recording-cadence diagnostics: {label}", "",
             f"{len(scores['by_family'])} families, {scores['episodes']} scenarios; duration {duration_text} s per scenario, "
             f"evidence releases every {tick_text} s, {scores['states']} logical requests. {request_description} "
             f"Requested model: {config['model']}" + (f", reasoning effort {config['reasoning_effort']}" if config["reasoning_effort"] else "")
             + ". All model scores use recorded responses.", "",
             f"**Untimed decision accuracy: {pct(scores['overall']['untimed_decision_accuracy'])}; "
             f"{timing_label}: {pct(scores['overall']['time_accuracy'])}.**", "",
             "These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.", "",
             *([f"Network-removed in-force accuracy (secondary estimate): {pct(net['scores']['estimate']['overall']['time_accuracy'])} "
                f"(range {pct(net['scores']['low']['overall']['time_accuracy'])}–{pct(net['scores']['high']['overall']['time_accuracy'])}).", ""]
               if (net := data.get("network_adjustment")) else []),
             *(["[Recorded error witnesses](FINDINGS.md) compare specific mistakes with the public rules.", ""]
               if (output / "FINDINGS.md").exists() else []),
             "## Family results", "",
             "| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |",
             "|---|---:|---:|---:|---:|"]
    for family, r in scores["by_family"].items():
        lines.append(f"| {NAMES[family]} | {pct(r['untimed_decision_accuracy'])} | {pct(r['time_accuracy'])} | {pct(r['segment_time_accuracy'])} | {pct(r['all_questions_exact_accuracy'])} |")
    timing_description = ("The reconstructed timeline anchors each successful attempt's duration at its evidence release, "
                          "retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, "
                          "and recomputes arrival order and acceptance. This differs from observed deployment time; "
                          "raw-clock results appear separately. " if normalized else
                          "Duration scores integrate actual releases and accepted update times exactly. ")
    lines += ["", "The application decision contains the model's own route, globally required answers and fields used "
              "by that route. Incorrect inactive fields do not lower decision accuracy. "
              + timing_description + "Family and overall recording-cadence scores give scenarios equal weight.", "",
              *(_network_report_lines(data["network_adjustment"]) if data.get("network_adjustment") else []),
              "## Scenario results", "",
              "| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |",
              "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['episode_id']} | {r['reference_transitions']} | {pct(r['untimed_decision_accuracy'])} | {pct(r['time_accuracy'])} | {r['latency_s_p50']:.2f} / {r['latency_s_p95']:.2f} | {r['failed_requests']} |")
    lines += ["", "## Execution and scoring checks", "",
              f"- Completed {scores['states']} states in {scores['episodes']} scenarios; {data['total_failed']} failed logical requests.",
              f"- {'Successful-attempt' if normalized else 'Full-response'} latency: p50 {data['latency_s']['p50']:.3f} s, p95 {data['latency_s']['p95']:.3f} s; "
              + ("includes same-host native calls, queueing and inference." if config.get('transport') == 'native_library'
                 else "includes client processing and the recorded service/network path."),
              f"- Maximum recorded release lag {data['max_release_lag_s']:.4f} s; maximum dispatch lag {data['max_dispatch_lag_s']:.4f} s.",
              f"- {scores['inactive_only_error_states']} states have only inactive-field errors, leaving the application decision correct.",
              f"- {data['accepted_updates']} updates accepted on the {'reconstructed timeline' if normalized else 'raw clock'}; rejected responses: {json.dumps(data['discarded_updates'], ensure_ascii=False)}.",
              "- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.",
              "- Untimed accuracy uses the same responses without another model pass. "
              + ("Native calls have no network timeout."
                 + (f" The setting's process timeout is {config['setting_process_timeout_s']:g} s."
                    if 'setting_process_timeout_s' in config else "")
                 if config.get('transport') == 'native_library'
                 else f"SDK retries: {config['sdk_retries']}; network timeout: {config['request_timeout_s']:g} s."),
              f"- Protocol: {config['protocol']}; at most {config['workers']} request workers; scenario concurrency {config['episode_concurrency']}.",
              "- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.", "",
              "Error duration grouped by the source of the decision in force: no decision "
              f"{data['error_seconds']['no_decision']:.2f} s; correct for its source but wrong for current evidence "
              f"{data['error_seconds']['source_correct']:.2f} s; wrong for both source and current evidence "
              f"{data['error_seconds']['source_incorrect']:.2f} s. These sums span all scenarios; source groups are not causal attribution.", "",
              *(_retry_report_lines(data) if normalized else []),
              "## Simple baselines", "", "Local offline baselines compare answer correctness; their duration scores were not measured.", "",
              f"| Family | First option | Lexical overlap | {label} decision |", "|---|---:|---:|---:|"]
    for f in scores["by_family"]:
        lines.append(f"| {NAMES[f]} | {pct(data['baselines']['first_option']['by_family'][f])} | {pct(data['baselines']['lexical_overlap']['by_family'][f])} | {pct(scores['by_family'][f]['untimed_decision_accuracy'])} |")
    lines += ["", "## Error localization", "",
              "Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. "
              "Several fields can be wrong at one state, so counts cannot be summed into error duration. "
              "Branch-field errors can coexist with route errors and do not establish independent capability deficits.", "",
              "| Scenario | Wrong active fields and state counts | First error ticks |", "|---|---|---|"]
    for r in rows:
        counts = Counter(q for m in r["mistakes"] for q in m["wrong_active_questions"])
        kinds = ", ".join(f"{q}: {n}" for q, n in counts.most_common()) or "None"
        ticks = ", ".join(str(m["t"]) for m in r["mistakes"][:12]) or "None"
        lines.append(f"| {r['episode_id']} | {kinds} | {ticks} |")
    lines += ["", "## Interpretation limits", "",
              "One recorded model pass on development scenarios. Adjacent states are dependent; these observations "
              "do not establish general model discrimination, repeated-run stability or deployment validity. "
              "Release cadence is controlled and has no independent human-timing calibration. The language reference "
              "supports a finite authored expression set, rather than arbitrary natural language.", "",
              "The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. "
              "The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences "
              "cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not "
              "trigger question edits or additional model calls for this analysis.", "",
              "## Reproduction files", "",
              f"- [Task and execution protocol]({relative_link(task_docs / 'PROTOCOL.md', output)})",
              f"- [Debugging rules]({relative_link(task_docs / 'debugging.md', output)}), "
              f"[assembly rules]({relative_link(task_docs / 'assembly.md', output)}), "
              f"[support rules]({relative_link(task_docs / 'support.md', output)})"
              + (f", [presenter rules]({relative_link(task_docs / 'presenter.md', output)})"
                 if "presenter_voice_control" in scores["by_family"] else ""),
              f"- [Frozen run]({relative_link(ROOT / data['run'] / 'run.json', output)})",
              f"- [Frozen episodes]({relative_link(ROOT / data['run'] / 'episodes.json', output)})",
              f"- [Release and response events]({relative_link(ROOT / data['run'] / 'events.jsonl', output)})",
              "- [Complete scores, errors and raw-clock diagnostics](analysis.json)", "",
              "From the repository root, reproduce the report and local baselines without model calls:", "", "```sh", command,
              "```", "",
              "Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned "
              "none is unknown. No cost estimate is inferred here.", "", "```json",
              json.dumps(data["usage"], indent=2), "```", ""]
    return "\n".join(lines)


def report(data: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "REPORT.md").write_text(render_report(data, output))
    (output / "analysis.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report(analyze(args.run), args.out)
