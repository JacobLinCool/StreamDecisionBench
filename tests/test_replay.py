"""Real-time scoring: the replay protocol, metrics.json layout, reference adapters and the CLI.

Episodes here are small synthetic sdb/0.2 streams (one choice question, a
state carrying the clock) and latencies are synthetic, so every expected
timeline can be worked out by hand.
"""

from __future__ import annotations

import json

import pytest

from streamdecisionbench.adapters import make_adapter_factory
from streamdecisionbench.cli import main
from streamdecisionbench.evaluator import evaluate
from streamdecisionbench.metrics import TemporalConfig, aggregate, replay, score_run
from streamdecisionbench.schema import deadline_steps_for, save_episode

LABELS = {"A": "K2", "B": "M3", "C": "P4", "D": "R5"}
GOLD = "AAAABBBBCCCCAAAA"


def stream(gold: str = GOLD, tick: float = 1, deadline_s: float = 2, variant: str = "canonical", family: str = "fam_t") -> dict:
    """A timed episode with one 4-option choice; gold letters are semantic ids."""
    return {
        "schema_version": "sdb/0.2",
        "episode_id": f"{family}_{variant}",
        "task_family": "presentation_navigation",
        "contrast_family": family,
        "variant": variant,
        "title": "synthetic stream",
        "schema_id": "synthetic/1",
        "tick_seconds": tick,
        "window_start": "00:00.0",
        "deadline_seconds": deadline_s,
        "difficulty": {"tier": "medium", "question_count": 1, "option_counts": {"q1": 4}, "features": []},
        "decision_structures": ["advance"],
        "deadline_steps": deadline_steps_for(deadline_s, tick),
        "questions": {"q1": {"type": "choice", "instructions": "Which slide is up?", "criteria": {l: f"slide {s}" for s, l in LABELS.items()}}},
        "hidden": {"question_keys": {"q1": "slide"}, "option_semantics": {"q1": {l: s for s, l in LABELS.items()}}, "construction": {}},
        "steps": [
            {"t": t, "state": {"clock": {"now": f"{t * tick:.1f}"}, "family": family, "variant": variant, "slide": g}, "gold": {"q1": g},
             "latent": {"slide": g}, "event_tags": ["steady"], "note": ""}
            for t, g in enumerate(gold)
        ],
    }


def oracle_records(episode: dict, latency_ms: float | list[float], failed: tuple[int, ...] = ()) -> list[dict]:
    """Untimed-run records answering every tick with its own gold."""
    lat = latency_ms if isinstance(latency_ms, list) else [latency_ms] * len(episode["steps"])
    out = []
    for step, ms in zip(episode["steps"], lat):
        if step["t"] in failed:
            out.append({"episode_id": episode["episode_id"], "t": step["t"], "ok": False, "error": "boom", "latency_ms": ms})
        else:
            g = step["gold"]["q1"]
            probs = {s: (0.9 if s == g else 0.1 / 3) for s in LABELS}
            out.append({"episode_id": episode["episode_id"], "t": step["t"], "ok": True, "pred": {"q1": g}, "probs": {"q1": probs}, "latency_ms": ms})
    return out


def sources(episode: dict, records: list[dict], mode: str) -> list[int | None]:
    return [r["source_t"] for r in replay(episode, records, mode)[0]]


CFG = TemporalConfig(delta=2, hold=2)


# ---------------------------------------------------------------------------
# The replay protocol
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("latency", [0.0, 400.0, 999.9])
def test_answers_inside_the_tick_are_perfect_in_both_modes(latency):
    ep = stream()
    recs = oracle_records(ep, latency)
    for mode in ("single", "pipelined"):
        assert sources(ep, recs, mode) == list(range(len(GOLD)))
    m = score_run([ep], {ep["episode_id"]: recs}, CFG)
    for block in ("realtime", "realtime_pipelined"):
        p, s = m[block]["primary"], m[block]["secondary"]
        assert p["sba"] == 1 and p["transition_f1"] == 1 and p["dsr"] == 1 and p["esr"] == 0
        assert s["accuracy"] == 1 and s["invalid_rate"] == 0 and s["stale_rate"] == 0 and s["late_rate"] == 0
        assert p["reaction_delay_s_median"] == pytest.approx(latency / 1000)  # wall-clock: the answer's own latency
        assert s["transition_f1_exact"] == 1 and s["timeout_rate"] == 0
        assert m[block]["resampled"]["sba"] == {"mean": 1, "sd": 0}


def test_answer_on_the_boundary_is_in_force_from_the_next_tick():
    ep = stream(tick=2)
    recs = oracle_records(ep, 2000.0)  # exactly one tick
    for mode in ("single", "pipelined"):
        assert sources(ep, recs, mode) == [None, *range(len(GOLD) - 1)]
    m = score_run([ep], {ep["episode_id"]: recs}, CFG)
    rt = m["realtime"]
    assert rt["secondary"]["late_rate"] == 1 and rt["secondary"]["invalid_rate"] == 1 / len(GOLD)
    assert rt["primary"]["reaction_delay_median"] == 1 and rt["primary"]["reaction_delay_s_median"] == 2
    assert m["primary"]["sba"] == 1  # the untimed run ignores latency


def test_single_mode_skips_states_and_lags_when_latency_exceeds_the_tick():
    ep = stream()
    recs = oracle_records(ep, 1500.0)
    in_force, sent = replay(ep, recs, "single")
    # Requests at 0, 1.5, 3.0, 4.5, ... s carry the newest released state; states 2, 5, 8, ... are never sent.
    assert [r["t"] for r in sent] == [0, 1, 3, 4, 6, 7, 9, 10, 12, 13, 15]
    assert [r["source_t"] for r in in_force] == [None, 0, 0, 1, 3, 3, 4, 6, 6, 7, 9, 9, 10, 12, 12, 13]
    assert in_force[4]["received_s"] == 4.5 and in_force[0]["ok"] is False
    # Pipelined: every state is sent at its release and lands 1.5 s later, one tick late.
    assert sources(ep, recs, "pipelined") == [None, *range(len(GOLD) - 1)]

    m = score_run([ep], {ep["episode_id"]: recs}, CFG)
    single, piped = m["realtime"], m["realtime_pipelined"]
    assert piped["primary"]["sba"] > single["primary"]["sba"]
    assert m["realtime"]["episodes"] == 1 and m["realtime"]["protocol"] == "single"
    per_ep = aggregate([ep], {ep["episode_id"]: replay(ep, recs, "single")[0]}, CFG)["per_episode"][0]
    assert per_ep["reaction_delays"] == [2, 2, 1] and per_ep["fp"] == 0  # the first answer is not a switch
    per_ep = aggregate([ep], {ep["episode_id"]: replay(ep, recs, "pipelined")[0]}, CFG)["per_episode"][0]
    assert per_ep["reaction_delays"] == [1, 1, 1]
    assert single["secondary"]["stale_rate"] == 15 / 16 and piped["secondary"]["stale_rate"] == 15 / 16


def test_failed_responses_keep_the_previous_decision():
    ep = stream()
    recs = oracle_records(ep, 500.0, failed=(0, 3))
    assert sources(ep, recs, "single") == [None, 1, 2, 2, *range(4, len(GOLD))]
    assert sources(ep, recs, "pipelined") == [None, 1, 2, 2, *range(4, len(GOLD))]
    # A slow failure blocks the single request slot: sent at 2.0, back at 4.5, so state 3 is skipped.
    recs = oracle_records(ep, [500.0, 500.0, 2500.0, *[500.0] * (len(GOLD) - 3)], failed=(2,))
    in_force, sent = replay(ep, recs, "single")
    assert [r["t"] for r in sent][:5] == [0, 1, 2, 4, 5]
    assert [r["source_t"] for r in in_force][:6] == [0, 1, 1, 1, 1, 5]
    # No records at all: nothing is ever in force.
    m = score_run([ep], {}, CFG)
    assert m["realtime"]["secondary"]["invalid_rate"] == 1 and m["realtime"]["primary"]["sba"] == 0


def test_client_timeout_abandons_a_slow_request():
    ep = stream()  # 1-s ticks, 2-s deadline: requests are abandoned after max(3 ticks, 2 s) = 3 s
    recs = oracle_records(ep, [500.0, 500.0, 60000.0, *[500.0] * (len(GOLD) - 3)])
    in_force, sent = replay(ep, recs, "single")
    # State 2 is sent at 2.0 and abandoned at 5.0, when the newest state (5) goes out at once.
    assert [r["t"] for r in sent][:4] == [0, 1, 2, 5] and sent[2]["abandoned"] and not sent[2]["ok"]
    assert [r["source_t"] for r in in_force][:7] == [0, 1, 1, 1, 1, 5, 6]
    assert sources(ep, recs, "pipelined")[:4] == [0, 1, 1, 3]  # the abandoned answer never arrives
    m = score_run([ep], {ep["episode_id"]: recs}, CFG)
    assert m["realtime"]["secondary"]["timeout_rate"] == 1 / len(sent) and m["realtime"]["secondary"]["failed_request_rate"] == 1 / len(sent)
    assert m["realtime"]["primary"]["latency_ms_p95"] == 60000  # the model's own latency stays in the tail


def test_latency_stats_include_failed_requests():
    ep = stream()
    lat = [30000.0 if t in (3, 9) else 100.0 for t in range(len(GOLD))]
    m = score_run([ep], {ep["episode_id"]: oracle_records(ep, lat, failed=(3, 9))}, CFG)
    s = m["secondary"]
    assert m["primary"]["latency_ms_p95"] == 30000 and s["latency_ms_p99"] == 30000 and s["latency_ms_p50"] == 100
    assert s["late_rate"] == 2 / 16 and s["failed_request_rate"] == 2 / 16 and s["invalid_rate"] == 2 / 16


def test_failures_can_score_higher_in_the_replay_than_untimed():
    """SPEC 2.3: the untimed run scores a failed tick wrong; a replay keeps the previous decision in force."""
    ep = stream()
    m = score_run([ep], {ep["episode_id"]: oracle_records(ep, 100.0, failed=tuple(range(1, len(GOLD), 2)))}, CFG)
    assert m["secondary"]["accuracy"] == 0.5 and m["realtime"]["secondary"]["accuracy"] == 1


def test_replay_reaction_delay_and_deadline_are_wall_clock():
    ep = stream(tick=2, deadline_s=2)  # deadline 1 tick
    fast = score_run([ep], {ep["episode_id"]: oracle_records(ep, 1500.0)}, CFG)["realtime_pipelined"]["primary"]
    assert fast["reaction_delay_s_median"] == 1.5 and fast["reaction_delay_median"] == 0 and fast["dsr"] == 1
    slow = score_run([ep], {ep["episode_id"]: oracle_records(ep, 2500.0)}, CFG)
    rt = slow["realtime_pipelined"]["primary"]
    # One tick late in both cases, but 2.5 s after the evidence: past the 2-s deadline (the tick count would allow it).
    assert rt["reaction_delay_median"] == 1 and rt["reaction_delay_s_median"] == 2.5 and rt["dsr"] == 0
    assert slow["primary"]["dsr"] == 1  # the untimed run has no clock


def test_resampled_replay_reports_the_spread_of_tail_latencies():
    ep = stream(gold="AAAABBBBCCCCAAAA" * 4)
    lat = [5000.0 if t % 16 == 7 else 200.0 for t in range(64)]
    r = score_run([ep], {ep["episode_id"]: oracle_records(ep, lat)}, CFG)["realtime"]["resampled"]
    assert r["resamples"] == 20 and r["sba"]["sd"] > 0 and 0 < r["sba"]["mean"] < 1
    again = score_run([ep], {ep["episode_id"]: oracle_records(ep, lat)}, CFG)["realtime"]["resampled"]
    assert again == r  # seeded


def test_pipelined_keeps_the_newest_state_when_answers_arrive_out_of_order():
    ep = stream()
    lat = [2500.0, 200.0, *[200.0] * (len(GOLD) - 2)]
    assert sources(ep, oracle_records(ep, lat), "pipelined")[:4] == [None, 1, 2, 3]
    # Single mode waits for the slow first answer (2.5 s), then sends state 2, which is back at 2.7 s.
    assert sources(ep, oracle_records(ep, lat), "single")[:5] == [None, None, 2, 3, 4]


def test_metrics_layout_and_untimed_compatibility():
    timed = stream()
    legacy = stream(family="fam_legacy")
    for key in ("tick_seconds", "window_start", "deadline_seconds", "schema_id"):
        del legacy[key]
    legacy["schema_version"] = "sdb/0.1"
    preds = {e["episode_id"]: oracle_records(e, 1500.0) for e in (timed, legacy)}
    m = score_run([timed, legacy], preds, CFG)
    assert m["episodes"] == 2 and m["primary"]["sba"] == 1
    assert set(m["realtime"]) == {"protocol", "episodes", "steps", "primary", "secondary", "by_family", "by_variant", "by_tier", "resampled"}
    assert set(m["realtime_pipelined"]) == {"protocol", "episodes", "steps", "primary", "secondary", "resampled"}
    assert "resampled" not in score_run([timed], preds, CFG, resamples=0)["realtime"]
    assert m["realtime"]["episodes"] == 1 and m["realtime"]["steps"] == len(GOLD)
    assert m["secondary"]["late_rate"] == 1  # only the timed episode's responses have a tick to be late for
    assert "realtime" not in score_run([legacy], preds, CFG)
    assert m["realtime"]["secondary"]["calibration"]["answers"] > 0


def test_single_mode_latency_stats_cover_the_requests_it_sent():
    ep = stream()
    lat = [2500.0 if t % 4 == 0 else 300.0 for t in range(len(GOLD))]
    m = score_run([ep], {ep["episode_id"]: oracle_records(ep, lat)}, CFG)
    _, sent = replay(ep, oracle_records(ep, lat), "single")
    assert [r["t"] for r in sent] == [0, 2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15]
    assert m["realtime"]["secondary"]["late_rate"] == 4 / 12 and m["realtime"]["primary"]["latency_ms_p95"] == 2500
    assert m["realtime_pipelined"]["secondary"]["late_rate"] == m["secondary"]["late_rate"] == 0.25


# ---------------------------------------------------------------------------
# Reference adapters
# ---------------------------------------------------------------------------


def family(tick: float = 2, deadline_s: float = 2) -> list[dict]:
    return [stream(tick=tick, deadline_s=deadline_s, family=f"fam_{i}") for i in range(3)]


def test_oracle_lag_and_lead():
    eps = family(tick=2, deadline_s=2)  # deadline 1 tick
    lag1 = aggregate(eps, evaluate(make_adapter_factory("oracle-lag:1", eps), eps), CFG)
    assert lag1["primary"]["transition_f1"] == 1 and lag1["primary"]["dsr"] == 1
    assert lag1["primary"]["reaction_delay_median"] == 1 and lag1["primary"]["reaction_delay_s_median"] == 2
    assert lag1["secondary"]["accuracy"] == 1 - 3 / 16  # wrong exactly at each of the 3 transitions
    lag2 = aggregate(eps, evaluate(make_adapter_factory("oracle-lag:2", eps), eps), CFG)
    assert lag2["primary"]["transition_f1"] == 1 and lag2["primary"]["dsr"] == 0 and lag2["primary"]["reaction_delay_s_p90"] == 4
    assert lag1["secondary"]["transition_f1_exact"] == 0  # the delta = 0 view sees the lag
    lead1 = aggregate(eps, evaluate(make_adapter_factory("oracle-lead:1", eps), eps), CFG)
    assert lead1["secondary"]["early_switch_rate"] == 1 and lead1["primary"]["reaction_delay_median"] is None
    assert lead1["primary"]["transition_f1"] == 1 and lead1["primary"]["dsr"] == 0  # anticipating the evidence is not on time
    assert lead1["secondary"]["accuracy"] == 1 - 3 / 16
    zero = aggregate(eps, evaluate(make_adapter_factory("oracle-lag:0", eps), eps), CFG)
    assert zero["primary"]["sba"] == 1 and zero["secondary"]["transition_f1_exact"] == 1
    with pytest.raises(ValueError):
        make_adapter_factory("oracle-lag:-1", eps)
    sticky = make_adapter_factory("lagged-sticky", eps)
    assert sticky().name == "lagged-sticky:3"
    lagged = aggregate(eps, evaluate(sticky, eps), CFG)
    assert lagged["primary"]["transition_f1"] == 0 and lagged["secondary"]["accuracy"] == 1 - 9 / 16


def test_lagged_oracle_with_real_latency_adds_up():
    eps = family(tick=1)
    preds = evaluate(make_adapter_factory("oracle-lag:1", eps), eps)
    for rs in preds.values():
        for r in rs:
            r["latency_ms"] = 1200.0  # every answer also lands one tick late (pipelined)
    m = score_run(eps, preds, CFG)
    assert m["primary"]["reaction_delay_median"] == 1 and m["realtime_pipelined"]["primary"]["reaction_delay_median"] == 2


@pytest.mark.parametrize("spec", ["random:3", "sticky:1", "oracle-noisy:0.3", "first", "lexical"])
def test_reference_adapters_reproduce_at_any_concurrency(spec):
    eps = family() + [stream(family="fam_x", variant="paraphrase")]

    def run(concurrency: int) -> dict:
        preds = evaluate(make_adapter_factory(spec, eps), eps, concurrency=concurrency)
        return {eid: [(r["t"], r["pred"], r["probs"]) for r in rs] for eid, rs in preds.items()}

    assert run(1) == run(4) == run(1)


def test_calibration_is_null_for_one_hot_runs():
    ep = stream()
    recs = oracle_records(ep, 100.0)
    assert aggregate([ep], {ep["episode_id"]: recs}, CFG)["secondary"]["calibration"]["answers"] == len(GOLD)
    for r in recs:
        r["probs"] = {"q1": {s: (1.0 if s == r["pred"]["q1"] else 0.0) for s in LABELS}}
    m = score_run([ep], {ep["episode_id"]: recs}, CFG)
    assert m["secondary"]["calibration"] is None and m["realtime"]["secondary"]["calibration"] is None
    for r in recs:
        del r["probs"]
    assert aggregate([ep], {ep["episode_id"]: recs}, CFG)["secondary"]["calibration"] is None


def test_dsr_deadline_comes_from_seconds():
    ep = stream(tick=2, deadline_s=4)  # 2 ticks
    ep["deadline_steps"] = 1  # a stale stored value is ignored for timed episodes
    lag2 = aggregate([ep], evaluate(make_adapter_factory("oracle-lag:2", [ep]), [ep]), CFG)
    assert lag2["primary"]["dsr"] == 1 and lag2["per_episode"][0]["deadline_steps"] == 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_eval_metrics_and_questions(tmp_path, capsys):
    data, run = tmp_path / "data", tmp_path / "run"
    for e in family(tick=1):
        save_episode(data, e)
    assert main(["eval", "--model", "oracle-lag:1", "--data", str(data), "--out", str(run)]) == 0
    out = capsys.readouterr().out
    assert "untimed: episodes=3" in out and "realtime (single request in flight)" in out and "realtime (pipelined)" in out
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["model"] == "oracle-lag:1" and "realtime" in metrics

    del metrics["model"]
    (run / "metrics.json").write_text(json.dumps(metrics))
    assert main(["metrics", "--run", str(run), "--data", str(data)]) == 0
    assert json.loads((run / "metrics.json").read_text())["model"] == "oracle-lag:1"  # from the responses
    (run / "metrics.json").write_text(json.dumps({"model": "custom-spec"}))
    assert main(["metrics", "--run", str(run), "--data", str(data)]) == 0
    assert json.loads((run / "metrics.json").read_text())["model"] == "custom-spec"
    assert "realtime (pipelined)" in capsys.readouterr().out

    assert main(["questions", "--run", str(run), "--data", str(data), "--by", "scenario", "--prior"]) == 0
    assert "| fam_0 | medium | slide |" in capsys.readouterr().out
