"""Release evidence on a monotonic clock; accept complete, newer responses atomically."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from streamdecisionbench.adapters.base import RetryableHTTPError
from streamdecisionbench.jev import ContractError, committed_answer, validate_response
from streamdecisionbench.lite.core import compose, decode, digest, request_for, sources
from streamdecisionbench.lite.scoring import episode_scores, summarize


class IncompleteRunError(RuntimeError):
    """The run lacks a valid response for one or more logical requests."""


def is_transport_error(error: Exception) -> bool:
    """Retry connectivity/timeouts, never model answers, schema errors or auth."""
    from openai import APIConnectionError

    return isinstance(error, (APIConnectionError, ConnectionError, TimeoutError))


def run_episode(episode: dict, factory: Callable, log: Callable, *, workers: int = 32,
                max_attempts: int = 5, retry_delay_s: float = 0.5) -> tuple[list[dict], list[dict]]:
    """One pipelined request per release, across-episode concurrency exactly one.

    The returned state is committed inside the worker, not reconstructed later.
    Connectivity errors and explicit rate limits are retried. Every attempt is logged, while actual
    wall-clock acceptance remains separate from retry-excluded scoring.
    """
    if workers < 1:
        raise ValueError("workers must be positive")
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if not math.isfinite(retry_delay_s) or retry_delay_s < 0:
        raise ValueError("retry_delay_s must be finite and nonnegative")
    local = threading.local()
    lock, stop = threading.Lock(), threading.Event()
    adapters, records, releases = [], [], []
    failures = []
    session = uuid.uuid4().hex
    horizon = len(episode["steps"]) * episode["tick_seconds"]
    latest = -1
    retry_not_before = 0.0
    start = time.monotonic()

    def persist(event: dict) -> None:
        # The caller holds lock so individual lines cannot interleave.
        try:
            log(event)
        except BaseException:
            stop.set()
            raise

    def execute(step: dict, release_s: float) -> None:
        nonlocal latest, retry_not_before
        request = request_for(episode, step)
        r = {"episode_id": episode["episode_id"], "t": step["t"], "release_s": release_s,
             "request_hash": digest(request), "ok": False, "accepted": False,
             "discard_reason": "request_failed", "started_s": time.monotonic() - start,
             "attempts": []}
        for number in range(1, max_attempts + 1):
            # A server rate limit pauses new dispatches across this episode's workers.
            while not stop.is_set():
                with lock:
                    cooldown_s = max(0.0, retry_not_before - time.monotonic())
                if cooldown_s == 0 or stop.wait(cooldown_s):
                    break
            if stop.is_set():
                break
            attempt = {"attempt": number, "started_s": time.monotonic() - start,
                       "ok": False, "retryable": False}
            if number == 1:
                r["started_s"] = attempt["started_s"]
            response = None
            try:
                if not hasattr(local, "adapter"):
                    adapter = factory()
                    with lock:
                        adapters.append(adapter)
                    adapter.start_episode(session)
                    local.adapter = adapter
                response = local.adapter.system_one(copy.deepcopy(request))
                attempt["received_s"] = time.monotonic() - start
                if response.get("request_id") is not None:
                    attempt["request_id"] = response["request_id"]
                validate_response(response, episode["questions"])
                wire = {k: committed_answer(q, response["answers"][k]) for k, q in episode["questions"].items()}
                pred = decode(episode, wire)
                decision = compose(episode["decision_spec"], pred)
                attempt["ok"] = True
                r.update(ok=True, received_s=attempt["received_s"], pred=pred, wire_answers=wire,
                         decision=decision, model=response.get("model"), usage=response.get("usage"))
            except Exception as error:
                # Never persist exception bodies, which may echo private inputs.
                transient_http = isinstance(error, RetryableHTTPError)
                attempt.update(error_type=type(error).__name__, retryable=is_transport_error(error) or transient_http)
                if transient_http:
                    delay = max(1.0, min(retry_delay_s * 2 ** min(number - 1, 10), 8.0))
                    if error.retry_after_s is not None:
                        delay = max(delay, error.retry_after_s)
                        attempt["retry_after_s"] = error.retry_after_s
                    attempt["retry_delay_s"] = delay
                    with lock:
                        retry_not_before = max(retry_not_before, time.monotonic() + delay)
                if isinstance(error, ContractError) and response is not None:
                    # Model output only, kept to diagnose contract failures.
                    attempt["invalid_answers"] = response.get("answers")
                status = getattr(error, "status_code", None)
                if isinstance(status, int):
                    attempt["http_status"] = status
                request_id = getattr(error, "request_id", None)
                if request_id is not None:
                    attempt["request_id"] = request_id
            attempt["completed_s"] = time.monotonic() - start
            r["attempts"].append(attempt)
            with lock:
                persist({"kind": "attempt", "episode_id": episode["episode_id"], "t": step["t"],
                         "request_hash": r["request_hash"], **attempt})
            if attempt["ok"]:
                break
            if not attempt["retryable"] or number == max_attempts:
                r["error_type"] = attempt["error_type"]
                r["failure_reason"] = ("rate_limit_retry_exhausted" if attempt["error_type"] == "RateLimitError"
                                       else "http_retry_exhausted" if transient_http
                                       else "transport_retry_exhausted") if attempt["retryable"] else "non_retryable_error"
                with lock:
                    failures.append(r["failure_reason"])
                stop.set()
                break
            # Retry once immediately, then use bounded backoff. All such wait is
            # excluded from normalized timing and retained in the raw record.
            delay = 0.0 if number == 1 else min(retry_delay_s * 2 ** min(number - 2, 10), 8.0)
            if stop.wait(delay):
                break
        r["completed_s"] = r["attempts"][-1]["completed_s"] if r["attempts"] else time.monotonic() - start
        if not r["ok"] and "failure_reason" not in r:
            r["failure_reason"] = "run_cancelled"
        with lock:
            accepted_s = time.monotonic() - start
            r["actual_recorded_s"] = accepted_s
            if r["ok"]:
                if accepted_s >= horizon:
                    r["discard_reason"] = "after_horizon"
                elif step["t"] <= latest:
                    r["discard_reason"] = "older_than_active"
                else:
                    latest = step["t"]
                    r.update(accepted=True, accepted_s=accepted_s, discard_reason=None)
            records.append(r)
            persist({"kind": "response", **r})

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for step in episode["steps"]:
                planned = step["t"] * episode["tick_seconds"]
                if stop.wait(max(0.0, start + planned - time.monotonic())):
                    break
                release = {"episode_id": episode["episode_id"], "t": step["t"],
                           "planned_s": planned, "release_s": time.monotonic() - start}
                with lock:
                    releases.append(release)
                    persist({"kind": "release", **release})
                futures.append(pool.submit(execute, step, release["release_s"]))
            if not stop.is_set():
                stop.wait(max(0.0, start + horizon - time.monotonic()))
            for future in futures:
                future.result()
    finally:
        for adapter in adapters:
            adapter.close()
    if failures or len(records) != len(episode["steps"]) or any(not r["ok"] for r in records):
        raise IncompleteRunError("not every logical request produced a valid response; inspect attempt metadata")
    return sorted(records, key=lambda r: r["t"]), releases


def run_dataset(episodes: list[dict], manifest: dict, factory: Callable, output: Path, config: dict,
                progress: Callable = print) -> dict:
    from streamdecisionbench.lite.retry_scoring import PROTOCOL, normalized_episode_scores, summarize_normalized

    if config["protocol"] != PROTOCOL:
        raise ValueError("new runs require the explicit retry-excluded protocol")
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    frozen = {"started_at_utc": started, "status": "running", "config": config,
              "dataset_manifest": manifest, "run_sources": sources()}
    (output / "run.json").write_text(json.dumps(frozen, indent=2) + "\n")
    (output / "episodes.json").write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + "\n")
    results, raw_results = [], []
    try:
        with (output / "events.jsonl").open("x", buffering=1) as handle:
            def log(event: dict) -> None:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                handle.flush()

            for i, episode in enumerate(episodes, 1):
                progress(f"[{i}/{len(episodes)}] {episode['episode_id']}: live release started", flush=True)
                records, releases = run_episode(episode, factory, log, workers=config["workers"],
                                                max_attempts=config["max_attempts"], retry_delay_s=config["retry_delay_s"])
                raw = episode_scores(episode, records, releases)
                score = normalized_episode_scores(episode, records, releases)
                results.append(score)
                raw_results.append(raw)
                (output / f"{episode['episode_id']}.json").write_text(json.dumps(score, indent=2) + "\n")
                (output / f"{episode['episode_id']}.raw_wallclock.json").write_text(json.dumps(raw, indent=2) + "\n")
                progress(f"  untimed={score['untimed_decision_accuracy']:.3f} time={score['time_accuracy']:.3f} "
                         f"all-questions={score['all_questions_exact_accuracy']:.3f} failures={score['failed_requests']}", flush=True)
        summary = summarize_normalized(results)
        (output / "metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
        (output / "raw_wallclock_metrics.json").write_text(json.dumps(summarize(raw_results), indent=2) + "\n")
        frozen["status"] = "complete"
        frozen["events_sha256"] = hashlib.sha256((output / "events.jsonl").read_bytes()).hexdigest()
        return summary
    except BaseException as error:
        frozen.update(status="incomplete", error_type=type(error).__name__, completed_episodes=len(results))
        raise
    finally:
        frozen["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "run.json").write_text(json.dumps(frozen, indent=2) + "\n")
