import copy
import threading
import time

import pytest

from streamdecisionbench.jev import make_answer
from streamdecisionbench.lite.core import compose, decode, encode_scenario, request_for
from streamdecisionbench.lite.runtime import run_episode
from streamdecisionbench.lite.scoring import episode_scores


def example(tick=2.0):
    q = lambda values: {"type": "choice", "instructions": "Select the supported value.", "criteria": {v: v for v in values}}
    return encode_scenario({
        "episode_id": "test", "task_family": "test", "scenario_id": "test", "title": "test", "tick_seconds": tick,
        "questions": {"route": q(["A", "B"]), "a": q(["yes", "no"]), "b": q(["yes", "no"])},
        "decision_spec": {"route_question": "route", "always": [], "branches": {"A": ["a"], "B": ["b"]}},
        "steps": [
            {"t": 0, "state": {"event": 0}, "gold": {"route": "A", "a": "yes", "b": "no"}, "evidence": ["event zero"]},
            {"t": 1, "state": {"event": 1}, "gold": {"route": "A", "a": "yes", "b": "yes"}, "evidence": ["inactive detail changes"]},
            {"t": 2, "state": {"event": 2}, "gold": {"route": "B", "a": "yes", "b": "yes"}, "evidence": ["route changes"]},
        ],
    })


def releases(ep):
    return [{"t": s["t"], "release_s": s["t"] * ep["tick_seconds"], "planned_s": s["t"] * ep["tick_seconds"]} for s in ep["steps"]]


def response(t, pred, arrival):
    return {"t": t, "ok": True, "pred": pred, "accepted": True, "accepted_s": arrival,
            "started_s": 2.0 * t, "completed_s": arrival, "discard_reason": None}


def test_wire_has_no_gold_or_authoring_witnesses_and_options_are_stable():
    ep = example()
    req = request_for(ep, ep["steps"][0])
    assert set(req) == {"state", "questions"}
    assert req["state"] == {"event": 0}
    assert req["questions"] == request_for(ep, ep["steps"][1])["questions"]
    labels = {k: next(label for label, value in mapping.items() if value == ep["steps"][0]["gold"][k]) for k, mapping in ep["option_semantics"].items()}
    assert decode(ep, labels) == ep["steps"][0]["gold"]


def test_unused_question_changes_neither_correctness_nor_reference_segments():
    ep = example()
    records = [response(s["t"], {**s["gold"], **({"b": "no"} if s["t"] == 1 else {})}, s["t"] * 2.0) for s in ep["steps"]]
    score = episode_scores(ep, records, releases(ep))
    assert score["untimed_decision_accuracy"] == 1
    assert score["time_accuracy"] == 1
    assert score["reference_transitions"] == 1
    assert score["all_questions_exact_accuracy"] == 2 / 3
    assert score["inactive_only_error_states"] == 1


def test_wrong_route_cannot_choose_its_own_exemption():
    ep = example()
    true = ep["steps"][0]["gold"]
    assert compose(ep["decision_spec"], {**true, "route": "B"}) != compose(ep["decision_spec"], true)


def test_delay_is_integrated_and_old_branch_does_not_change_at_gold_transition():
    ep = example()
    records = [response(s["t"], s["gold"], s["t"] * 2 + 0.8) for s in ep["steps"]]
    score = episode_scores(ep, records, releases(ep))
    # 0-.8 has no answer; 4-4.8 retains route A although gold has switched to B.
    assert score["time_accuracy"] == pytest.approx(4.4 / 6)
    assert score["segment_time_accuracy"] == pytest.approx(((3.2 / 4) + (1.2 / 2)) / 2)
    assert score["error_seconds"] == pytest.approx({"no_decision": 0.8, "source_correct": 0.8, "source_incorrect": 0})


@pytest.mark.parametrize("second_pred, outdated_kind", [
    ({"route": "A", "a": "yes", "b": "no"}, "stale"),              # right for its source, outdated at t=4
    ({"route": "A", "a": "no", "b": "no"}, "compound"),            # wrong for its source and for the new reference
    ({"route": "B", "a": "no", "b": "yes"}, "outdated_correct"),   # wrong for its source, matches the new reference
])
def test_time_partition_separates_timing_from_judgment(second_pred, outdated_kind):
    ep = example()
    arrivals = [0.5, 2.5, 5.0]
    preds = [ep["steps"][0]["gold"], second_pred, ep["steps"][2]["gold"]]
    score = episode_scores(ep, [response(t, preds[t], arrivals[t]) for t in range(3)], releases(ep))
    part = score["time_partition_seconds"]
    # 0-.5 no decision; .5-2.5 source 0 current and right; 2.5-4 source 1 current (right or a judgment error);
    # 4-5 source 1 outdated after the route changes to B; 5-6 source 2 current and right.
    second_right = compose(ep["decision_spec"], second_pred) == compose(ep["decision_spec"], ep["steps"][1]["gold"])
    expected = {"current_correct": 3.0 + (1.5 if second_right else 0), "judgment": 0 if second_right else 1.5,
                "stale": 0.0, "compound": 0.0, "outdated_correct": 0.0, "no_decision": 0.5}
    expected[outdated_kind] += 1.0
    assert part == pytest.approx(expected)
    assert score["current_source_share"] == pytest.approx(4.5 / 6)
    oracle = episode_scores(ep, [response(t, ep["steps"][t]["gold"], arrivals[t]) for t in range(3)], releases(ep))
    assert score["current_source_share"] == pytest.approx(oracle["time_accuracy"])


def test_incomplete_and_duplicate_records_cannot_masquerade_as_full_scores():
    ep = example()
    r = [response(s["t"], s["gold"], s["t"] * 2) for s in ep["steps"]]
    with pytest.raises(ValueError, match="exactly one"):
        episode_scores(ep, r[:-1], releases(ep))
    with pytest.raises(ValueError, match="exactly one"):
        episode_scores(ep, [*r, r[0]], releases(ep))


def test_nonfinite_or_noncausal_timing_is_rejected():
    ep = example()
    records = [response(s["t"], s["gold"], s["t"] * 2) for s in ep["steps"]]
    records[1]["accepted_s"] = 1.0
    with pytest.raises(ValueError, match="causality"):
        episode_scores(ep, records, releases(ep))
    records[1]["accepted_s"] = float("nan")
    with pytest.raises(ValueError, match="causality"):
        episode_scores(ep, records, releases(ep))


def test_response_log_failure_aborts_run_instead_of_returning_scores():
    from streamdecisionbench.adapters.local import FirstOptionAdapter

    ep = example(0.01)
    def failing_log(event):
        if event["kind"] == "response":
            raise OSError("disk failure")
    with pytest.raises(OSError, match="disk failure"):
        run_episode(ep, FirstOptionAdapter, failing_log)


def test_real_clock_out_of_order_and_after_horizon_updates_are_not_accepted():
    ep = example(0.06)
    second_started = threading.Event()
    seen = []

    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, req):
            t = req["state"]["event"]
            seen.append(t)
            if t == 0:
                assert second_started.wait(2)
                time.sleep(0.03)
            elif t == 1:
                second_started.set()
            else:
                time.sleep(0.10)
            gold = ep["steps"][t]["gold"]
            answers = {}
            for key, question in req["questions"].items():
                label = next(k for k, value in ep["option_semantics"][key].items() if value == gold[key])
                answers[key] = make_answer(question, {k: float(k == label) for k in question["criteria"]})
            return {"answers": answers}

    events = []
    records, released = run_episode(ep, Adapter, events.append)
    assert seen == [0, 1, 2]
    assert records[0]["discard_reason"] == "older_than_active"
    assert records[1]["accepted"]
    assert records[2]["discard_reason"] == "after_horizon"
    score = episode_scores(ep, records, released)
    assert score["untimed_decision_accuracy"] == 1
    assert score["time_accuracy"] < 0.6
    assert len([e for e in events if e["kind"] == "release"]) == 3
