"""python -m streamdecisionbench.lite build|run|score|merge"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from streamdecisionbench.lite.core import build_dataset, load_dataset, select_episodes


PHYSICAL_PROTOCOL = "wall_clock_pipelined_latest_source"
RETRY_PROTOCOL = "retry_excluded_successful_attempt_v1"


def rescore_run(run: Path) -> dict:
    """Recompute a completed recording's scores from its own events and frozen episodes.

    Only the recording's internal structure is checked. It is never compared
    with current source code or previously saved metrics, so later code changes
    do not invalidate earlier runs.
    """
    from streamdecisionbench.lite.scoring import episode_scores, summarize

    frozen = json.loads((run / "run.json").read_text())
    if frozen["status"] != "complete":
        raise ValueError("an incomplete run cannot be scored as the full dataset")
    protocol = frozen["config"]["protocol"]
    if protocol not in {PHYSICAL_PROTOCOL, RETRY_PROTOCOL}:
        raise ValueError(f"unsupported timing protocol: {protocol}")
    episodes = json.loads((run / "episodes.json").read_text())
    event_bytes = (run / "events.jsonl").read_bytes()
    released_states = {(e["episode_id"], s["t"]) for e in episodes for s in e["steps"]}
    responses, releases, attempts = defaultdict(list), defaultdict(list), defaultdict(list)
    for line in event_bytes.splitlines():
        event = json.loads(line)
        kind = event["kind"]
        key = (event["episode_id"], event["t"])
        if key not in released_states or kind not in {"release", "response", "attempt"}:
            raise ValueError("event log contains an unknown event kind, episode, or tick")
        if kind == "attempt" and protocol != RETRY_PROTOCOL:
            raise ValueError("physical v1 run unexpectedly contains retry-attempt events")
        if kind == "attempt":
            attempts[key].append(event)
        else:
            (responses if kind == "response" else releases)[event["episode_id"]].append(event)
    if protocol == RETRY_PROTOCOL:
        for eid, records in responses.items():
            for record in records:
                nested = record.get("attempts", [])
                logged = attempts[(eid, record["t"])]
                if not nested or len(logged) != len(nested):
                    raise ValueError("attempt event count differs from final response")
                if not record["ok"] or not nested[-1]["ok"]:
                    raise ValueError("completed retry-normalized run contains an unsuccessful logical request")
                for attempt, event in zip(nested, logged):
                    if any(key not in event or event[key] != value for key, value in attempt.items()):
                        raise ValueError("attempt event differs from embedded final-response attempt")
        from streamdecisionbench.lite.retry_scoring import normalized_episode_scores, summarize_normalized

        per = [normalized_episode_scores(e, responses[e["episode_id"]], releases[e["episode_id"]]) for e in episodes]
        result = summarize_normalized(per)
        raw = summarize([episode_scores(e, responses[e["episode_id"]], releases[e["episode_id"]]) for e in episodes])
    else:
        result = summarize([episode_scores(e, responses[e["episode_id"]], releases[e["episode_id"]]) for e in episodes])
        raw = None
    return {"frozen": frozen, "episodes": episodes, "responses": dict(responses), "releases": dict(releases),
            "scores": result, "raw_wallclock_scores": raw, "time_basis": protocol}


def merge_runs(parts: list[Path], data: Path, output: Path, *, allow_served_model_change: bool = False) -> dict:
    """Combine recordings of one setting that cover disjoint episodes into one complete run.

    Every episode must equal the episode of the given build and appear in exactly
    one part, and the parts must share execution settings. Each episode keeps its
    own recorded timeline, so the combined run scores exactly as its parts do.
    Recorded source versions are kept per part and are not compared.
    """
    import hashlib

    from streamdecisionbench.lite.core import digest

    dataset, manifest = load_dataset(data)
    verified = [rescore_run(part) for part in parts]
    for part, run in zip(parts, verified):
        if hashlib.sha256((part / "events.jsonl").read_bytes()).hexdigest() != run["frozen"].get("events_sha256"):
            raise ValueError(f"{part}: event log differs from its recorded hash")
    configs = [{k: v for k, v in run["frozen"]["config"].items() if k != "selection"} for run in verified]
    differing = sorted({k for c in configs for k in c if any(o.get(k) != c.get(k) for o in configs)})
    if differing:
        raise ValueError(f"parts differ in execution settings: {', '.join(differing)}")
    owner = {}
    for i, run in enumerate(verified):
        for episode in run["episodes"]:
            eid = episode["episode_id"]
            if manifest["hashes"].get(eid) != digest(episode):
                raise ValueError(f"{parts[i]}: {eid} is not an episode of this build")
            if eid in owner:
                raise ValueError(f"{eid} is recorded in more than one part")
            owner[eid] = i
    missing = [e["episode_id"] for e in dataset if e["episode_id"] not in owner]
    if missing:
        raise ValueError(f"no part records {', '.join(missing)}")
    served = [sorted({r.get("model") for rows in run["responses"].values() for r in rows}) for run in verified]
    if not allow_served_model_change and any(s != served[0] for s in served):
        raise ValueError(f"parts were answered by different served models: {served}")

    lines = defaultdict(list)
    for part in parts:
        for line in (part / "events.jsonl").read_bytes().splitlines():
            lines[json.loads(line)["episode_id"]].append(line)
    event_bytes = b"".join(line + b"\n" for e in dataset for line in lines[e["episode_id"]])
    frames = [run["frozen"] for run in verified]
    shared_sources = frames[0].get("run_sources") if all(f.get("run_sources") == frames[0].get("run_sources") for f in frames) else None
    frozen = {"started_at_utc": min(f["started_at_utc"] for f in frames),
              "finished_at_utc": max(f["finished_at_utc"] for f in frames),
              "status": "complete", "config": configs[0], "dataset_manifest": manifest, "run_sources": shared_sources,
              "events_sha256": hashlib.sha256(event_bytes).hexdigest(),
              # Each part is recorded relative to the merged run folder, so the file names no machine path.
              "combined_from": [{"run": Path(os.path.relpath(part.resolve(), output.resolve())).as_posix(),
                                 "episodes": [e["episode_id"] for e in run["episodes"]],
                                 "started_at_utc": run["frozen"]["started_at_utc"],
                                 "finished_at_utc": run["frozen"]["finished_at_utc"],
                                 "dataset_hash": run["frozen"]["dataset_manifest"]["dataset_hash"],
                                 "events_sha256": run["frozen"]["events_sha256"], "served_models": models,
                                 "selection": run["frozen"]["config"].get("selection"),
                                 "run_sources": run["frozen"].get("run_sources")}
                                for part, run, models in zip(parts, verified, served)]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "episodes.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n")
    (output / "events.jsonl").write_bytes(event_bytes)
    (output / "run.json").write_text(json.dumps(frozen, indent=2) + "\n")
    combined = rescore_run(output)
    (output / "metrics.json").write_text(json.dumps(combined["scores"], indent=2) + "\n")
    if combined["raw_wallclock_scores"] is not None:
        (output / "raw_wallclock_metrics.json").write_text(json.dumps(combined["raw_wallclock_scores"], indent=2) + "\n")
    return combined["scores"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--data", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--provider", choices=("openai", "openai-decisions", "typesafe", "cloudflare", "wity", "perplexity", "fastino"), default="openai")
    run.add_argument("--model", required=True)
    run.add_argument("--effort", help="reasoning effort for openai (e.g. none, low); omit it for a model or compatible endpoint without reasoning effort; only accepted for openai")
    run.add_argument("--reasoning", choices=("auto", "off", "always"), help="Wity reasoning mode (default: auto); only accepted for wity")
    run.add_argument("--timeout", type=float, help="request timeout in seconds (default: 300 for Fastino, 60 for Wity, 30 for Perplexity, 20 otherwise)")
    run.add_argument("--max-attempts", type=int, default=5)
    run.add_argument("--retry-delay", type=float, default=0.5)
    subset = run.add_mutually_exclusive_group()
    subset.add_argument("--families", help="comma-separated task families to record (default: every episode)")
    subset.add_argument("--episodes", help="comma-separated episode ids to record (default: every episode)")
    score = commands.add_parser("score")
    score.add_argument("--run", type=Path, required=True)
    merge = commands.add_parser("merge", help="combine runs of one setting that cover disjoint episodes of a build")
    merge.add_argument("--data", type=Path, required=True)
    merge.add_argument("--runs", type=Path, nargs="+", required=True)
    merge.add_argument("--out", type=Path, required=True)
    merge.add_argument("--allow-served-model-change", action="store_true",
                       help="combine parts even if the provider served different model versions")
    args = parser.parse_args()
    if args.command == "build":
        manifest = build_dataset(args.data)
        print(json.dumps({"dataset_hash": manifest["dataset_hash"], "episodes": manifest["episodes"]}, indent=2))
    elif args.command == "run":
        from streamdecisionbench.cli import load_dotenv
        from streamdecisionbench.lite.runtime import run_dataset

        load_dotenv()
        openai = args.provider == "openai"
        if args.timeout is None:
            args.timeout = {"wity": 60.0, "perplexity": 30.0, "fastino": 300.0}.get(args.provider, 20.0)
        credentials = {"openai": ("OPENAI_API_KEY",), "openai-decisions": ("OPENAI_API_KEY",), "typesafe": ("TYPESAFE_API_KEY",),
                       "wity": ("WITY_API_KEY",),
                       "perplexity": ("PERPLEXITY_API_KEY",),
                       "fastino": ("FASTINO_API_KEY",),
                       "cloudflare": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_AUTH_TOKEN")}
        for key in credentials[args.provider]:
            if not os.environ.get(key):
                parser.error(f"{key} is required")
        endpoint = {"openai": "OPENAI_BASE_URL", "openai-decisions": "OPENAI_BASE_URL", "typesafe": "TYPESAFE_BASE_URL", "wity": "WITY_BASE_URL",
                    "perplexity": "PERPLEXITY_BASE_URL", "fastino": "FASTINO_BASE_URL"}.get(args.provider)
        if args.reasoning is not None and args.provider != "wity":
            parser.error(f"--reasoning is not accepted for {args.provider}")
        if args.provider == "wity" and args.model != "wity-1":
            parser.error("Wity model must be wity-1; the API does not select models")
        if not openai and args.effort is not None:
            parser.error(f"--effort is not accepted for {args.provider}")
        if args.provider == "cloudflare" and args.model not in {"clef", "clef-flash"}:
            parser.error("Cloudflare model must be clef or clef-flash")
        if args.provider == "perplexity" and args.model != "pplx-decider-v1-27b":
            parser.error("Perplexity Decisions model must be pplx-decider-v1-27b")
        if args.provider == "fastino" and args.model != "fastino/GLiDE":
            parser.error("Fastino decision model must be fastino/GLiDE")
        if args.provider == "openai-decisions" and args.model != "gpt-6-luna":
            parser.error("OpenAI Decisions model must be gpt-6-luna")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            parser.error("timeout must be positive and finite")
        if args.max_attempts < 1:
            parser.error("max-attempts must be at least one")
        if not math.isfinite(args.retry_delay) or args.retry_delay < 0:
            parser.error("retry-delay must be nonnegative and finite")
        episodes, manifest = load_dataset(args.data)
        families = args.families.split(",") if args.families else None
        episode_ids = args.episodes.split(",") if args.episodes else None
        try:
            episodes = select_episodes(episodes, families=families, episode_ids=episode_ids)
        except ValueError as error:
            parser.error(str(error))
        config = {"provider": args.provider, "model": args.model, "reasoning_effort": args.effort,
                  "protocol": RETRY_PROTOCOL, "workers": 16 if args.provider == "wity" else 32,
                  "episode_concurrency": 1, "request_timeout_s": args.timeout,
                  "max_attempts": args.max_attempts, "retry_delay_s": args.retry_delay,
                  "sdk_retries": 0, "custom_endpoint": bool(endpoint and os.environ.get(endpoint)),
                  "untimed": "one final successful response per state; failed transport attempts excluded from model timing"}
        if families or episode_ids:
            config["selection"] = {"families": families} if families else {"episodes": episode_ids}
        if args.provider == "wity":
            config["reasoning"] = args.reasoning or "auto"
        if args.provider == "openai-decisions":
            config["rate_limit_policy"] = "http429_5xx_retry_after_shared_cooldown_v1"
        if args.provider in {"wity", "perplexity"}:
            config["rate_limit_policy"] = "http429_retry_after_shared_cooldown_v1"
        if args.provider == "fastino":
            config["rate_limit_policy"] = "http425_429_503_retry_after_shared_cooldown_v1"
            config["score_mapping"] = "expected_level_to_score_v1"
        if openai:
            from streamdecisionbench.adapters.llm import OpenAIAdapter

            factory = lambda: OpenAIAdapter(model=args.model, effort=args.effort, timeout=args.timeout, max_retries=0)
        elif args.provider == "openai-decisions":
            from streamdecisionbench.adapters.openai_decisions import OpenAIDecisionsAdapter

            factory = lambda: OpenAIDecisionsAdapter(model=args.model, timeout=args.timeout)
        elif args.provider == "typesafe":
            from streamdecisionbench.adapters.remote import TypeSafeAdapter

            factory = lambda: TypeSafeAdapter(model=args.model, timeout=args.timeout, max_retries=0)
        elif args.provider == "wity":
            from streamdecisionbench.adapters.wity import WityAdapter

            factory = lambda: WityAdapter(model=args.model, reasoning=config["reasoning"], timeout=args.timeout)
        elif args.provider == "perplexity":
            from streamdecisionbench.adapters.perplexity import PerplexityAdapter

            factory = lambda: PerplexityAdapter(model=args.model, timeout=args.timeout)
        elif args.provider == "fastino":
            from streamdecisionbench.adapters.fastino import FastinoAdapter

            factory = lambda: FastinoAdapter(model=args.model, timeout=args.timeout)
        else:
            from streamdecisionbench.adapters.cloudflare import CloudflareAdapter

            factory = lambda: CloudflareAdapter(model=args.model, timeout=args.timeout)
        result = run_dataset(episodes, manifest, factory, args.out, config)
        print(json.dumps({k: v for k, v in result.items() if k != "per_episode"}, indent=2))
    elif args.command == "merge":
        try:
            result = merge_runs(args.runs, args.data, args.out, allow_served_model_change=args.allow_served_model_change)
        except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
            parser.error(str(error))
        print(json.dumps({k: v for k, v in result.items() if k != "per_episode"}, indent=2))
    else:
        try:
            result = rescore_run(args.run)["scores"]
        except (ValueError, KeyError, FileNotFoundError) as error:
            parser.error(str(error))
        print(json.dumps({k: v for k, v in result.items() if k != "per_episode"}, indent=2))


if __name__ == "__main__":
    main()
