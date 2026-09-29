"""Command line: ``sdb build | validate | eval | metrics | questions | serve-mock | show | ...``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from streamdecisionbench.schema import (
    VARIANTS,
    build_request,
    digest,
    is_realtime,
    load_episodes,
    save_episode,
)

DEFAULT_DATA = Path("data/legacy/v0")


def cmd_build(args: argparse.Namespace) -> int:
    from streamdecisionbench.authoring import build_episode
    from streamdecisionbench.families import load_scenarios

    scenarios = load_scenarios(args.family or None)
    if args.scenario:
        scenarios = [s for s in scenarios if s.scenario_id in set(args.scenario)]
    if not scenarios:
        print("no scenarios found", file=sys.stderr)
        return 1
    root = Path(args.data)
    failures = 0
    for scenario in scenarios:
        for variant in VARIANTS:
            try:
                episode = build_episode(scenario, variant)
            except Exception as error:
                failures += 1
                print(f"FAIL {scenario.scenario_id}_{variant}: {type(error).__name__}: {error}", file=sys.stderr)
                continue
            path = save_episode(root, episode)
            print(f"built {path}")
    if not args.no_manifest:
        write_manifest(root)
    return 1 if failures else 0


def write_manifest(root: Path) -> None:
    import hashlib
    from collections import Counter

    import streamdecisionbench

    episodes = load_episodes(root)
    package = Path(streamdecisionbench.__file__).parent
    sources = sorted(
        [*(package / "authoring").glob("*.py"), package / "schema.py", *(package / "families").glob("*.py")]
    )
    manifest = {
        "schema_versions": sorted({e["schema_version"] for e in episodes}),
        "episodes": len(episodes),
        "steps": sum(len(e["steps"]) for e in episodes),
        "counts": {
            "schema_version": dict(sorted(Counter(e["schema_version"] for e in episodes).items())),
            "task_family": dict(sorted(Counter(e["task_family"] for e in episodes).items())),
            "variant": dict(sorted(Counter(e["variant"] for e in episodes).items())),
            "tier": dict(sorted(Counter(e["difficulty"]["tier"] for e in episodes).items())),
        },
        "generator_sources": {
            str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
        "hashes": {e["episode_id"]: digest(e) for e in episodes},
        "public_hashes": {
            e["episode_id"]: digest([build_request(e, s) for s in e["steps"]]) for e in episodes
        },
    }
    manifest["dataset_hash"] = digest(manifest["hashes"])
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")


def cmd_validate(args: argparse.Namespace) -> int:
    from streamdecisionbench.validate import validate

    episodes = load_episodes(Path(args.data))
    if args.family:
        episodes = [e for e in episodes if e["task_family"] in set(args.family)]
    if args.scenario:
        episodes = [e for e in episodes if e["contrast_family"] in set(args.scenario)]
    report = validate(episodes, expect_full=not args.partial)
    for w in report.warnings:
        print(f"WARN  {w}")
    for e in report.errors:
        print(f"ERROR {e}")
    print(json.dumps(report.stats, indent=1, default=str))
    print(f"{len(report.errors)} errors, {len(report.warnings)} warnings over {len(episodes)} episodes")
    return 0 if report.ok else 1


def _summary(metrics: dict[str, Any]) -> str:
    """The untimed run, then the real-time replays when the run has timed episodes."""

    def f(x: Any, pct: bool = False) -> str:
        if x is None:
            return "-"
        return f"{100 * x:.1f}" if pct else f"{x:.3g}"

    def block(m: dict[str, Any], title: str) -> list[str]:
        p, s = m["primary"], m["secondary"]
        seconds = p.get("reaction_delay_s_median")
        rd = f"RD med {f(p['reaction_delay_median'])} p90 {f(p['reaction_delay_p90'])}"
        if seconds is not None:
            rd += f" ({f(seconds)} / {f(p['reaction_delay_s_p90'])} s)"
        late = f" | late {f(s['late_rate'], True)}" if s.get("late_rate") is not None else ""
        stale = f" | stale {f(s['stale_rate'], True)} | timeout {f(s['timeout_rate'], True)}" if "stale_rate" in s else ""
        lines = [
            f"{title}: episodes={m['episodes']} steps={m['steps']}",
            (
                f"  SBA {f(p['sba'], True)} | TransF1 {f(p['transition_f1'], True)} | {rd}"
                f" | ESR {f(p['esr'])} | DSR {f(p['dsr'], True)} (early {f(s['early_switch_rate'], True)})"
                f" | p95 {f(p['latency_ms_p95'])} ms | CSA {f(p['csa'], True)}"
            ),
            (
                f"  acc {f(s['accuracy'], True)} | TransF1@0 {f(s['transition_f1_exact'], True)} | raw-switch {f(s['raw_switch_rate'])}"
                f" | CSA-probe {f(s['csa_probe'], True)} | invalid {f(s['invalid_rate'], True)} | failed req {f(s['failed_request_rate'], True)}"
                f" | p50 {f(s['latency_ms_p50'])} p99 {f(s['latency_ms_p99'])} ms{late}{stale}"
            ),
        ]
        r = m.get("resampled")
        if r:
            spread = " | ".join(
                f"{name} {100 * r[key]['mean']:.1f} ± {100 * r[key]['sd']:.1f}"
                for key, name in (("sba", "SBA"), ("transition_f1", "TransF1"), ("dsr", "DSR"), ("accuracy", "acc"))
                if key in r
            )
            lines.append(f"  over {r['resamples']} latency redraws: {spread}")
        return lines

    lines = block(metrics, "untimed")
    for key, title in (("realtime", "realtime (single request in flight)"), ("realtime_pipelined", "realtime (pipelined)")):
        if key in metrics:
            lines += block(metrics[key], title)
    return "\n".join(lines)


def cmd_eval(args: argparse.Namespace) -> int:
    from streamdecisionbench.adapters import FatalAdapterError, make_adapter_factory
    from streamdecisionbench.evaluator import evaluate
    from streamdecisionbench.metrics import TemporalConfig, score_run

    episodes = load_episodes(Path(args.data), args.episode or None)
    if args.family:
        episodes = [e for e in episodes if e["task_family"] in set(args.family)]
    try:
        factory = make_adapter_factory(args.model, episodes)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else None

    def progress(eid: str, done: int, total: int) -> None:
        print(f"[{done}/{total}] {eid}", file=sys.stderr)

    try:
        predictions = evaluate(factory, episodes, out=out, concurrency=args.concurrency, progress=progress)
    except FatalAdapterError as error:
        print(f"error: {error}", file=sys.stderr)
        if out is not None:
            print(f"finished episodes are kept in {out}; rerun the same command to resume", file=sys.stderr)
        return 2
    metrics = score_run(episodes, predictions, TemporalConfig(delta=args.delta, hold=args.hold))
    metrics["model"] = args.model
    if out is not None:
        (out / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    print(_summary(metrics))
    return 0


def _load_run(run: Path) -> dict[str, list[dict[str, Any]]]:
    predictions: dict[str, list[dict[str, Any]]] = {}
    for line in (run / "predictions.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            predictions.setdefault(r["episode_id"], []).append(r)
    return predictions


def _run_model(run: Path, predictions: dict[str, list[dict[str, Any]]]) -> str | None:
    """The model a run evaluated: the adapter spec its metrics.json keeps, else the model its responses name."""
    from collections import Counter

    path = run / "metrics.json"
    if path.is_file():
        try:
            model = json.loads(path.read_text()).get("model")
        except json.JSONDecodeError:
            model = None
        if model:
            return model
    names = Counter(r["model"] for rs in predictions.values() for r in rs if r.get("model"))
    return names.most_common(1)[0][0] if names else None


def cmd_metrics(args: argparse.Namespace) -> int:
    from streamdecisionbench.metrics import TemporalConfig, score_run

    run = Path(args.run)
    predictions = _load_run(run)
    episodes = load_episodes(Path(args.data), list(predictions))
    metrics = score_run(episodes, predictions, TemporalConfig(delta=args.delta, hold=args.hold))
    metrics["model"] = _run_model(run, predictions)
    (run / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    print(_summary(metrics))
    return 0


def question_report(metrics: dict[str, Any], by: str = "episode", prior: bool = False) -> str:
    """Markdown tables of per-question accuracy (invalid responses count as wrong).

    With ``prior``, each cell also shows in parentheses the share of the most
    frequent gold answer, i.e. what always giving that one answer would score.
    """

    def pct(x: float | None) -> str:
        return "" if x is None else f"{100 * x:.1f}"

    rows = metrics["per_episode"]
    width = max(len(m["questions"]) for m in rows)
    keys = [f"q{i + 1}" for i in range(width)]
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in rows:
        groups.setdefault(m["episode_id"] if by == "episode" else m["contrast_family"], []).append(m)

    def label(q: dict[str, str]) -> str:
        return q["role"] if q["type"] == "choice" else f"{q['role']} ({q['type']})"

    lines = [
        f"| {by} | tier | questions | joint | " + " | ".join(keys) + " |",
        "|---|---|---|--:|" + "--:|" * width,
    ]
    for name, ms in groups.items():
        first = ms[0]
        cells = [pct(sum(m["accuracy"] for m in ms) / len(ms))]
        for key in keys:
            vals = [m["per_question_accuracy"][key] for m in ms if key in m["per_question_accuracy"]]
            cell = pct(sum(vals) / len(vals)) if vals else ""
            if prior and vals:
                base = [m["per_question_prior"][key] for m in ms]
                cell += f" ({pct(sum(base) / len(base))})"
            cells.append(cell)
        questions = " / ".join(label(first["questions"][k]) for k in first["questions"])
        lines.append(f"| {name} | {first['tier']} | {questions} | " + " | ".join(cells) + " |")
    for field, title in (("by_role", "role"), ("by_type", "type"), ("by_key", "key")):
        lines += ["", f"| {title} | questions | steps | accuracy |", "|---|--:|--:|--:|"]
        for k, v in metrics["by_question"][field].items():
            lines.append(f"| {k} | {v['episodes']} | {v['steps']} | {pct(v['accuracy'])} |")
    return "\n".join(lines)


def cmd_questions(args: argparse.Namespace) -> int:
    from streamdecisionbench.metrics import aggregate

    predictions = _load_run(Path(args.run))
    episodes = load_episodes(Path(args.data), list(predictions))
    report = question_report(aggregate(episodes, predictions), args.by, args.prior)
    if args.out:
        Path(args.out).write_text(report + "\n")
    print(report)
    return 0


def cmd_serve_mock(args: argparse.Namespace) -> int:
    from streamdecisionbench.adapters import make_adapter_factory
    from streamdecisionbench.mock_server import serve

    episodes = load_episodes(Path(args.data)) if args.backend.startswith("oracle") else []
    server = serve(
        make_adapter_factory(args.backend, episodes),
        host=args.host,
        port=args.port,
        latency_ms=args.latency_ms,
        jitter_ms=args.jitter_ms,
        api_key=args.api_key,
    )
    print(f"Jev-compatible mock on http://{args.host}:{args.port} (backend={args.backend})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _parse_range(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return [t for t in out if 0 <= t < n]


def _clock(episode: dict[str, Any], t: int) -> str:
    """Read time of tick ``t`` in the episode's own clock format (sdb/0.2), else ""."""
    from streamdecisionbench.authoring.stream import fmt_like, parse_clock

    if not is_realtime(episode):
        return ""
    start = episode["window_start"]
    return fmt_like(parse_clock(start) + t * episode["tick_seconds"], start)


def _timing(episode: dict[str, Any]) -> str:
    if not is_realtime(episode):
        return f"{episode['episode_id']} ({episode['schema_version']}): untimed ticks, deadline {episode['deadline_steps']} ticks"
    last = len(episode["steps"]) - 1
    return (
        f"{episode['episode_id']} ({episode['schema_version']}, {episode['schema_id']}): tick {episode['tick_seconds']:g} s, "
        f"window {_clock(episode, 0)}-{_clock(episode, last)}, deadline {episode['deadline_seconds']:g} s "
        f"({episode['deadline_steps']} ticks)"
    )


def cmd_show(args: argparse.Namespace) -> int:
    (episode,) = load_episodes(Path(args.data), [args.episode])
    print(_timing(episode))
    if args.questions or not args.steps:
        print(json.dumps(episode["questions"], indent=1, ensure_ascii=False))
    ticks = _parse_range(args.steps, len(episode["steps"]))
    for t in ticks:
        step = episode["steps"][t]
        clock = f" ({_clock(episode, t)})" if is_realtime(episode) else ""
        print(f"\n--- t={t}{clock} tags={step['event_tags']}")
        if args.gold:
            print(f"gold={step['gold']} note={step['note']!r}")
            if args.latent:
                print(f"latent={json.dumps(step['latent'], ensure_ascii=False)}")
        state = step["state"]
        print(state if isinstance(state, str) else json.dumps(state, indent=1, ensure_ascii=False))
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    """Compact view of gold decisions and tags across all variants of a scenario."""
    from streamdecisionbench.schema import composite, question_keys

    episodes = {e["variant"]: e for e in load_episodes(Path(args.data)) if e["contrast_family"] == args.scenario}
    if not episodes:
        print("no episodes", file=sys.stderr)
        return 1
    base = episodes.get("canonical") or next(iter(episodes.values()))
    keys = question_keys(base)
    print(_timing(base))
    clock_head = [f"{'clock':>10}"] if is_realtime(base) else []
    print(" ".join(["  t", *clock_head, *(f"{v:<34}" for v in VARIANTS if v in episodes), "tags"]))
    for t in range(len(base["steps"])):
        row = [f"{t:>3}"]
        if is_realtime(base):
            row.append(f"{_clock(base, t):>10}")
        for v in VARIANTS:
            if v in episodes:
                row.append(f"{composite(episodes[v]['steps'][t]['gold'], keys):<34}")
        row.append(",".join(x for x in base["steps"][t]["event_tags"] if x != "steady"))
        print(" ".join(row))
    return 0


def cmd_blind_export(args: argparse.Namespace) -> int:
    from streamdecisionbench.authoring import seeded
    from streamdecisionbench.blind import export_batch, export_ordered, write_json

    episodes = load_episodes(Path(args.data), args.episode or None)
    if args.scenario:
        episodes = [e for e in episodes if e["contrast_family"] in set(args.scenario)]
    if args.variant:
        episodes = [e for e in episodes if e["variant"] in set(args.variant)]
    if not episodes:
        print("no episodes selected", file=sys.stderr)
        return 1
    out = Path(args.out)
    if args.ordered:
        if args.sample or args.chunks:
            print("--ordered exports whole streams; use --steps, not --sample or --chunks", file=sys.stderr)
            return 2
        batch, key = export_ordered(episodes, {e["episode_id"]: _parse_range(args.steps, len(e["steps"])) for e in episodes}, args.seed)
        write_json(out, batch)
        write_json(out.with_suffix(".key.json"), key)
        print(f"wrote {len(batch['streams'])} streams, {len(key)} ticks to {out} (key: {out.with_suffix('.key.json')})")
        return 0
    ticks = {}
    for e in episodes:
        chosen = _parse_range(args.steps, len(e["steps"]))
        if args.sample and args.sample < len(chosen):
            rng = seeded("sample", args.seed, e["episode_id"])
            # Always keep transition ticks and tagged ticks; fill the rest at random.
            special = [t for t in chosen if set(e["steps"][t]["event_tags"]) - {"steady"}]
            rest = [t for t in chosen if t not in special]
            rng.shuffle(special)
            rng.shuffle(rest)
            chosen = sorted((special + rest)[: args.sample])
        ticks[e["episode_id"]] = chosen
    if args.chunks and args.chunks > 1:
        # Disjoint shuffled chunks covering every selected tick exactly once.
        pairs = [(eid, t) for eid, ts in ticks.items() for t in ts]
        seeded("chunks", args.seed).shuffle(pairs)
        size = -(-len(pairs) // args.chunks)
        for c in range(args.chunks):
            part: dict[str, list[int]] = {}
            for eid, t in sorted(pairs[c * size : (c + 1) * size]):
                part.setdefault(eid, []).append(t)
            batch, key = export_batch(episodes, part, f"{args.seed}-{c}")
            path = out.with_name(f"{out.stem}_{c + 1}{out.suffix}")
            write_json(path, batch)
            write_json(path.with_suffix(".key.json"), key)
            print(f"wrote {len(batch['items'])} items to {path}")
        return 0
    batch, key = export_batch(episodes, ticks, args.seed)
    write_json(out, batch)
    write_json(out.with_suffix(".key.json"), key)
    print(f"wrote {len(batch['items'])} items to {out} (key: {out.with_suffix('.key.json')})")
    return 0


def cmd_blind_score(args: argparse.Namespace) -> int:
    from streamdecisionbench.blind import score_batch, write_json

    batch_path = Path(args.batch)
    key = json.loads(batch_path.with_suffix(".key.json").read_text())
    answers = json.loads(Path(args.answers).read_text())
    ids = sorted({v["episode_id"] for v in key.values()})
    episodes = {e["episode_id"]: e for e in load_episodes(Path(args.data), ids)}
    result = score_batch(episodes, key, answers)
    if args.out:
        write_json(Path(args.out), result)
    print(f"{result['correct']}/{result['items']} correct ({100 * (result['accuracy'] or 0):.1f}%)")
    for k, v in result["per_question"].items():
        print(f"  {k}: {100 * v:.1f}%")
    for row in result["disagreements"]:
        print(f"- {row['item']} {row['episode_id']} t={row['t']} answer={row['answer']} gold={row['gold']} tags={row['tags']} note={row['note']!r}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from streamdecisionbench.audit.shortcuts import run_audit

    episodes = load_episodes(Path(args.data))
    if args.family:
        episodes = [e for e in episodes if e["task_family"] in set(args.family)]
    report = run_audit(
        episodes,
        Path(args.cache),
        embedders=tuple(e for e in args.embedder or ("e5", "bge", "qwen") if e != "none"),
        strong=args.strong,
        probes=not args.no_probes,
        log=lambda m: print(m, file=sys.stderr),
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    def num(x: float | None, width: int, digits: int = 3) -> str:
        return f"{'-':>{width}s}" if x is None else f"{x:{width}.{digits}f}"

    print(f"chance: decision {report['chance_decision_accuracy']:.3f}, question {report['chance_question_accuracy']:.3f}")
    print(f"{'method':20s} {'SBA':>6s} {'dec':>6s} {'q':>6s} {'@trans':>7s} {'@flip':>6s} {'capture':>8s} {'cover':>6s}  per question")
    for name, r in report["methods"].items():
        per_question = " ".join(f"{k} {v:.3f}" for k, v in r["by_question"].items())
        print(
            f"{name:20s} {num(r['sba'], 6)} {num(r['decision_accuracy'], 6)} {num(r['question_accuracy'], 6)} "
            f"{num(r.get('question_accuracy@transition'), 7)} {num(r.get('question_accuracy@cf_flip'), 6)} "
            f"{num(r.get('capture_of_strong_gain_sba'), 8, 2)} {num(r['coverage'], 6, 2)}  {per_question}"
        )
    return 0


def cmd_diff_gold(args: argparse.Namespace) -> int:
    """Ticks whose gold (or latent state) differs between two dataset directories."""
    from streamdecisionbench.schema import composite, question_keys

    new = {e["episode_id"]: e for e in load_episodes(Path(args.data))}
    old = {e["episode_id"]: e for e in load_episodes(Path(args.against))}
    families = set(args.family or [])
    changed = 0
    for eid in sorted(set(new) | set(old)):
        e = new.get(eid) or old.get(eid)
        if families and e["task_family"] not in families:
            continue
        if eid not in new or eid not in old:
            print(f"{eid}: only in {'new' if eid in new else 'old'}")
            changed += 1
            continue
        if old[eid]["schema_version"] != new[eid]["schema_version"]:
            print(f"{eid}: schema {old[eid]['schema_version']} -> {new[eid]['schema_version']}")
        keys = question_keys(new[eid])
        for a, b in zip(old[eid]["steps"], new[eid]["steps"]):
            g0, g1 = composite(a["gold"], keys), composite(b["gold"], keys)
            if g0 != g1:
                print(f"{eid} t={a['t']}: gold {g0} -> {g1}")
                changed += 1
            elif args.latent and a["latent"] != b["latent"]:
                print(f"{eid} t={a['t']}: latent changed (gold unchanged)")
    print(f"{changed} gold differences")
    return 0


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE lines from ``.env`` into the environment.

    Variables already set in the environment win, so a shell ``export`` always
    overrides the file. Supports comments, blank lines, ``export`` prefixes and
    single or double quotes.
    """
    import os

    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="sdb", description="StreamDecisionBench")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="build episodes from scenario generators")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--family", action="append")
    p.add_argument("--scenario", action="append")
    p.add_argument("--no-manifest", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="structural validation")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--family", action="append")
    p.add_argument("--scenario", action="append")
    p.add_argument("--partial", action="store_true", help="do not require all families/variants")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("eval", help="evaluate a model")
    p.add_argument("--model", required=True, help="adapter spec, e.g. random, oracle, jev:jev-latest")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--out")
    p.add_argument("--episode", action="append")
    p.add_argument("--family", action="append")
    p.add_argument(
        "--concurrency", type=int, default=1, help="episodes in parallel; keep it low enough not to inflate latency (it drives the real-time replay)"
    )
    p.add_argument("--delta", type=int, default=2)
    p.add_argument("--hold", type=int, default=2)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("metrics", help="recompute metrics.json (untimed and real-time replay) for a run directory")
    p.add_argument("--run", required=True)
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--delta", type=int, default=2)
    p.add_argument("--hold", type=int, default=2)
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("questions", help="per-question accuracy of a run, per episode or scenario")
    p.add_argument("--run", required=True)
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--by", choices=["episode", "scenario"], default="episode")
    p.add_argument("--prior", action="store_true", help="show the majority-answer share next to each accuracy")
    p.add_argument("--out", help="also write the markdown tables to this file")
    p.set_defaults(func=cmd_questions)

    p = sub.add_parser("serve-mock", help="run a local Jev-compatible System One server")
    p.add_argument("--backend", default="random")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--latency-ms", type=float, default=0.0)
    p.add_argument("--jitter-ms", type=float, default=0.0)
    p.add_argument("--api-key")
    p.set_defaults(func=cmd_serve_mock)

    p = sub.add_parser("show", help="print an episode's questions and states")
    p.add_argument("episode")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--steps", help="e.g. 0-5,40")
    p.add_argument("--gold", action="store_true")
    p.add_argument("--latent", action="store_true")
    p.add_argument("--questions", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("timeline", help="gold decisions across variants of one scenario")
    p.add_argument("scenario")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("blind-export", help="export gold-free requests for blind solving (shuffled ticks or ordered streams)")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--episode", action="append")
    p.add_argument("--scenario", action="append")
    p.add_argument("--variant", action="append")
    p.add_argument("--steps", help="tick range per episode, e.g. 0-99")
    p.add_argument("--sample", type=int, help="ticks per episode (tagged ticks first)")
    p.add_argument("--seed", default="0")
    p.add_argument("--chunks", type=int, help="split the selected ticks into N disjoint shuffled batches")
    p.add_argument("--ordered", action="store_true", help="one stream per episode: questions once, states in tick order")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_blind_export)

    p = sub.add_parser("blind-score", help="score blind answers against gold")
    p.add_argument("--batch", required=True)
    p.add_argument("--answers", required=True)
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--out")
    p.set_defaults(func=cmd_blind_score)

    p = sub.add_parser("diff-gold", help="list ticks whose gold differs from another dataset directory")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--against", required=True)
    p.add_argument("--family", action="append")
    p.add_argument("--latent", action="store_true")
    p.set_defaults(func=cmd_diff_gold)

    p = sub.add_parser("audit", help="shortcut audits (needs the 'audit' extra)")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--family", action="append")
    p.add_argument("--embedder", action="append", choices=["e5", "bge", "qwen", "none"], help="'none': lexical and family heuristics only")
    p.add_argument("--strong", type=float, help="SBA of a strong semantic model, for the capture ratio")
    p.add_argument("--no-probes", action="store_true")
    p.add_argument("--cache", default=".cache/sdb-embeddings")
    p.add_argument("--out")
    p.set_defaults(func=cmd_audit)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
