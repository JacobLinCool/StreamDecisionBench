"""The evaluation loop.

For every episode the evaluator signals a fresh stream, then for t = 0..99
sends the tick's System One request, times the call, validates the response
against the full decision contract, and records the committed decision in
hidden semantic terms. Invalid or failed responses count as incorrect. The
model never receives future states, gold labels, option semantics or tags.
A ``FatalAdapterError`` (bad key, unknown model) stops the whole run instead:
only fully finished episodes are saved, so the same command resumes later.

Episodes are independent streams, so several may run concurrently; the ticks
of one episode are always sent strictly in order, one at a time.

This is the untimed run. Every record keeps its measured latency, from which
``metrics.replay`` rebuilds the real-time runs on a virtual clock (no
sleeping), so concurrency must stay low enough not to inflate latency.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from streamdecisionbench.adapters.base import Adapter, FatalAdapterError
from streamdecisionbench.jev import INVALID, ContractError, committed_answer, validate_response
from streamdecisionbench.schema import build_request, to_semantic


def _probabilities(episode: dict[str, Any], key: str, question: dict[str, Any], answer: dict[str, Any]) -> Any:
    if question["type"] == "noul":
        return answer["noul"]
    if question["type"] == "score":
        return {str(k): v for k, v in answer["probabilities"].items()}
    mapping = episode["hidden"]["option_semantics"][key]
    return {mapping[label]: p for label, p in answer["probabilities"].items()}


def run_episode(adapter: Adapter, episode: dict[str, Any]) -> list[dict[str, Any]]:
    adapter.start_episode(uuid.uuid4().hex)
    records = []
    for step in episode["steps"]:
        request = build_request(episode, step)
        record: dict[str, Any] = {"episode_id": episode["episode_id"], "t": step["t"]}
        started = time.perf_counter()
        try:
            response = adapter.system_one(request)
            latency = (time.perf_counter() - started) * 1000
            validate_response(response, request["questions"])
        except FatalAdapterError:
            raise
        except ContractError as error:
            latency = (time.perf_counter() - started) * 1000
            record.update(ok=False, error=f"contract: {error}", latency_ms=latency)
        except Exception as error:  # transport or model failure
            latency = (time.perf_counter() - started) * 1000
            record.update(ok=False, error=f"{type(error).__name__}: {error}", latency_ms=latency)
        else:
            pred, probs = {}, {}
            for key, question in request["questions"].items():
                answer = response["answers"][key]
                semantic = to_semantic(episode, key, committed_answer(question, answer))
                pred[key] = INVALID if semantic is None else semantic
                probs[key] = _probabilities(episode, key, question, answer)
            record.update(
                ok=True,
                latency_ms=latency,
                pred=pred,
                probs=probs,
                model=response.get("model"),
                usage=response.get("usage"),
            )
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        records.append(record)
    return records


def evaluate(
    adapter_factory: Callable[[], Adapter],
    episodes: Sequence[dict[str, Any]],
    out: Path | None = None,
    concurrency: int = 1,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Run every episode; returns ``episode_id -> per-tick records``.

    With ``out`` set, records are appended to ``out/predictions.jsonl`` as each
    episode finishes, and episodes already complete there are skipped (resume).
    """
    done: dict[str, list[dict[str, Any]]] = {}
    path = None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        path = out / "predictions.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    done.setdefault(r["episode_id"], []).append(r)
            expected = {e["episode_id"]: len(e["steps"]) for e in episodes}
            done = {k: v for k, v in done.items() if len(v) == expected.get(k)}
    todo = [e for e in episodes if e["episode_id"] not in done]
    lock = threading.Lock()
    local = threading.local()
    adapters: list[Adapter] = []

    def adapter() -> Adapter:
        if not hasattr(local, "adapter"):
            local.adapter = adapter_factory()
            with lock:
                adapters.append(local.adapter)
        return local.adapter

    def work(episode: dict[str, Any]) -> None:
        records = run_episode(adapter(), episode)
        with lock:
            done[episode["episode_id"]] = records
            if path is not None:
                with path.open("a") as handle:
                    for r in records:
                        handle.write(json.dumps(r, ensure_ascii=False) + "\n")
            if progress:
                progress(episode["episode_id"], len(done), len(episodes))

    try:
        if concurrency <= 1:
            for episode in todo:
                work(episode)
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(work, episode) for episode in todo]
                try:
                    for future in as_completed(futures):
                        future.result()
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
    finally:
        for a in {id(a): a for a in adapters}.values():
            try:
                a.close()
            except Exception:
                pass
    return done
