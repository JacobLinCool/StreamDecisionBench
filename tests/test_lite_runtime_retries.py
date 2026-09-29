import copy
import json
import threading
import time

import pytest

from streamdecisionbench.adapters.base import FatalAdapterError
from streamdecisionbench.jev import make_answer
from streamdecisionbench.lite.runtime import IncompleteRunError, is_transport_error, run_episode
from streamdecisionbench.lite.scoring import episode_scores
from test_lite_core import example


def answer(ep, request, *, wrong=False):
    step = ep["steps"][request["state"]["event"]]
    result = {}
    for key, question in ep["questions"].items():
        label = next(k for k, semantic in ep["option_semantics"][key].items() if semantic == step["gold"][key])
        if wrong and key == "route":
            label = next(k for k in question["criteria"] if k != label)
        result[key] = make_answer(question, {k: float(k == label) for k in question["criteria"]})
    return {"answers": result}


def test_connection_retry_preserves_input_and_recovers_after_wallclock_horizon():
    from streamdecisionbench.lite.retry_scoring import normalized_episode_scores

    ep = example(0.06)
    calls, requests = {}, []
    mutex = threading.Lock()

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, req):
            t = req["state"]["event"]
            with mutex:
                calls[t] = calls.get(t, 0) + 1
                n = calls[t]
                requests.append((t, copy.deepcopy(req)))
            if t == 0 and n == 1:
                req["state"]["event"] = 999  # A failed adapter cannot corrupt a retry.
                time.sleep(0.24)
                raise ConnectionError("secret-token-never-persist")
            return answer(ep, req)

    events = []
    records, releases = run_episode(ep, Adapter, events.append, max_attempts=3, retry_delay_s=0)
    assert calls == {0: 2, 1: 1, 2: 1}
    assert requests[0][1] == next(req for t, req in requests[1:] if t == 0)
    assert records[0]["ok"] and records[0]["discard_reason"] == "after_horizon"
    assert len(records[0]["attempts"]) == 2
    assert sum(e["kind"] == "attempt" for e in events) == 4
    assert "secret-token" not in json.dumps(events)
    normalized = normalized_episode_scores(ep, records, releases)
    raw = episode_scores(ep, records, releases)
    assert normalized["untimed_decision_accuracy"] == 1
    assert normalized["time_accuracy"] > raw["time_accuracy"]


def test_valid_wrong_answers_are_never_retried():
    ep = example(0.01)
    calls = []

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, request):
            calls.append(request["state"]["event"])
            return answer(ep, request, wrong=True)

    records, releases = run_episode(ep, Adapter, lambda _: None, max_attempts=5)
    assert calls == [0, 1, 2]
    assert all(len(r["attempts"]) == 1 for r in records)
    assert episode_scores(ep, records, releases)["untimed_decision_accuracy"] == 0


@pytest.mark.parametrize("error,max_attempts,expected_calls", [
    (ConnectionError("network"), 3, 3),
    (ValueError("bad schema"), 3, 1),
    (FatalAdapterError("bad credentials"), 3, 1),
])
def test_exhausted_transport_and_nonretryable_failures_leave_run_incomplete(error, max_attempts, expected_calls):
    ep = example(1)
    calls = []

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, request):
            calls.append(request)
            raise error

    events = []
    with pytest.raises(IncompleteRunError):
        run_episode(ep, Adapter, events.append, max_attempts=max_attempts, retry_delay_s=0)
    assert len(calls) == expected_calls
    assert sum(e["kind"] == "attempt" for e in events) == expected_calls
    assert [e for e in events if e["kind"] == "response"][0]["ok"] is False


def test_contract_failure_is_not_retried_and_keeps_the_invalid_answers():
    ep = example(1)

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, request):
            response = answer(ep, request)
            response["answers"]["route"]["choice"] = next(
                k for k, p in response["answers"]["route"]["probabilities"].items() if p == 0)
            return response

    events = []
    with pytest.raises(IncompleteRunError):
        run_episode(ep, Adapter, events.append, max_attempts=3, retry_delay_s=0)
    attempts = [e for e in events if e["kind"] == "attempt"]
    assert len(attempts) == 1 and attempts[0]["error_type"] == "ContractError" and not attempts[0]["retryable"]
    assert set(attempts[0]["invalid_answers"]) == set(ep["questions"])


def test_attempt_log_failure_stops_before_retry():
    ep = example(1)
    calls = []

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, request):
            calls.append(request)
            raise ConnectionError("network")

    def log(event):
        if event["kind"] == "attempt":
            raise OSError("cannot persist audit log")

    with pytest.raises(OSError, match="audit log"):
        run_episode(ep, Adapter, log, max_attempts=3, retry_delay_s=0)
    assert len(calls) == 1


def test_retry_classifier_uses_transport_types_not_error_text():
    import httpx
    from openai import APIConnectionError, APITimeoutError

    request = httpx.Request("POST", "https://example.invalid")
    assert is_transport_error(APIConnectionError(request=request))
    assert is_transport_error(APITimeoutError(request=request))
    assert is_transport_error(TimeoutError())
    assert not is_transport_error(ValueError("connection timeout"))
    assert not is_transport_error(OSError("disk write failed"))


@pytest.mark.parametrize("kwargs", [{"max_attempts": 0}, {"max_attempts": True},
                                   {"retry_delay_s": -1}, {"retry_delay_s": float("nan")}])
def test_invalid_retry_limits_rejected_before_requests(kwargs):
    with pytest.raises(ValueError):
        run_episode(example(), lambda: pytest.fail("should not open client"), lambda _: None, **kwargs)


def test_failed_adapter_initialization_retries_with_an_initialized_client():
    ep = example(0.01)
    clients = []

    class Adapter:
        def __init__(self):
            self.ready = False
            self.closed = False
            clients.append(self)

        def start_episode(self, session):
            if len(clients) == 1:
                raise ConnectionError("temporary initialization failure")
            self.ready = True

        def close(self):
            self.closed = True

        def system_one(self, request):
            assert self.ready
            return answer(ep, request)

    records, _ = run_episode(ep, Adapter, lambda _: None, workers=1, max_attempts=2)
    assert len(records[0]["attempts"]) == 2
    assert all(r["ok"] for r in records)
    assert all(client.closed for client in clients)


@pytest.mark.parametrize("recover", [True, False])
def test_dataset_persists_complete_dual_timing_or_incomplete_status(tmp_path, recover):
    from streamdecisionbench.lite.__main__ import rescore_run
    from streamdecisionbench.lite.core import digest
    from streamdecisionbench.lite.retry_scoring import PROTOCOL, TIME_BASIS
    from streamdecisionbench.lite.runtime import run_dataset

    ep = example(0.01)
    calls = {}

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, request):
            t = request["state"]["event"]
            calls[t] = calls.get(t, 0) + 1
            if t == 0 and (calls[t] == 1 or not recover):
                raise ConnectionError("temporary disconnect")
            return answer(ep, request)

    hashes = {ep["episode_id"]: digest(ep)}
    manifest = {"hashes": hashes, "dataset_hash": digest(hashes)}
    config = {"protocol": PROTOCOL, "workers": 1, "max_attempts": 2, "retry_delay_s": 0}
    output = tmp_path / "run"
    if recover:
        summary = run_dataset([ep], manifest, Adapter, output, config, progress=lambda *a, **kw: None)
        assert summary["time_basis"] == TIME_BASIS
        assert summary["retry_reliability"]["failed_attempts"] == 1
        assert summary["retry_reliability"]["attempts"] == 4
        assert summary["overall"]["untimed_decision_accuracy"] == 1
        assert (output / "raw_wallclock_metrics.json").exists()
        assert rescore_run(output)["scores"] == summary
    else:
        with pytest.raises(IncompleteRunError):
            run_dataset([ep], manifest, Adapter, output, config, progress=lambda *a, **kw: None)
        assert json.loads((output / "run.json").read_text())["status"] == "incomplete"
        assert not (output / "metrics.json").exists()
        with pytest.raises(ValueError, match="incomplete"):
            rescore_run(output)
