"""Public-evidence checks for training variant debugging_c (pre-merge CI and approval assistant)."""

from copy import deepcopy
import json

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.training import debugging_c
from streamdecisionbench.lite.training.audit import (
    MAX_LAYOUT_OVERLAP, check_module, layout_overlap, leakage, spec_overlap)
from streamdecisionbench.lite.training.debugging_c import _glob, reference, scenarios

C1, C2, C3, C4, C5, C6 = "a41c0de", "5be7d12", "c90e4f1", "e27b3a9", "7d0e5c3", "f4a8b61"
HOLD = "internal/reserve/hold.go"
HOLD_TEST = "internal/reserve/hold_test.go"
MAIN = "cmd/stockhold/main.go"
DOC = "docs/holds.md"
SWEEP_TEST = "internal/reserve/sweep/sweep_test.go"
TXN = "internal/storage/kvclient/txn.go"
RENEWAL, CONFLICT = "TestRenewExtendsFromNow", "TestReserveRetriesOnConflict"
CAP, BACKOFF = "TestReserveRetryCapHonoured", "TestTxnRetryBackoff"
TOP_KEYS = {"now", "assistant", "pull_request", "commits", "ci", "reviews", "approval_rules", "chat"}
FINISHED = {"passed", "failed", "cancelled"}


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def at(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def job(state, name, commit, attempt=1):
    return next(j for j in state["ci"]["jobs"]
                if j["name"] == name and j["commit"] == commit and j["attempt"] == attempt)


def decision(episode, state):
    return compose(episode["decision_spec"], reference(state))


def add_review(state, reviewer, verdict, commit, when):
    state["reviews"].append({"reviewer": reviewer, "verdict": verdict, "commit": commit, "at": when,
                             "body": "counterfactual"})
    state["reviews"].sort(key=lambda r: r["at"])


# ---------------------------------------------------------------------------
# Structure, causality and stated conventions
# ---------------------------------------------------------------------------

def test_identity_and_public_reference_reproduces_every_tick(episode):
    assert (episode["episode_id"], episode["task_family"], episode["scenario_id"]) == (
        "train_debugging_c", "live_debugging", "debugging_c")
    assert episode["tick_seconds"] == 2.0 and len(episode["steps"]) == 60
    assert len(episode["questions"]) == 8
    rules = episode["steps"][0]["state"]["assistant"]
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        assert step["t"] == tick and state["now"] == tick
        assert set(state) == TOP_KEYS
        assert state["assistant"] == rules
        assert step["evidence"] and all(isinstance(e, str) and e for e in step["evidence"])
        assert reference(json.loads(json.dumps(state))) == step["gold"]
        assert set(step["gold"]) == set(episode["questions"])
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"], (tick, question, value)


def test_nothing_is_later_than_now(episode):
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        times = [c["at"] for c in state["commits"]] + [r["at"] for r in state["reviews"]]
        times += [c["at"] for c in state["chat"]]
        for j in state["ci"]["jobs"]:
            times += [t for t in (j["queued_at"], j["started_at"], j["finished_at"]) if t is not None]
        assert max(times) <= tick


def test_history_is_cumulative(episode):
    previous = None
    for step in episode["steps"]:
        state = step["state"]
        if previous is not None:
            for key in ("commits", "reviews", "chat"):
                assert state[key][:len(previous[key])] == previous[key], key
            files = state["pull_request"]["files_changed"]
            assert files[:len(previous["pull_request"]["files_changed"])] == previous["pull_request"]["files_changed"]
            jobs = state["ci"]["jobs"]
            assert len(jobs) >= len(previous["ci"]["jobs"])
            for old, new in zip(previous["ci"]["jobs"], jobs):
                assert (old["name"], old["commit"], old["attempt"], old["queued_at"]) == (
                    new["name"], new["commit"], new["attempt"], new["queued_at"])
                if old["status"] in FINISHED:
                    assert new == old
                elif old["status"] == "running":
                    assert new["started_at"] == old["started_at"] and new["status"] != "queued"
        previous = state


def test_ci_record_conventions(episode):
    stages = {"lint": "lint", "build": "build", "unit-reserve": "unit", "unit-storage": "unit",
              "integration-kv": "integration", "bench-holds": "unit"}
    for step in episode["steps"]:
        state = step["state"]
        head = state["pull_request"]["head_commit"]
        assert head == state["commits"][-1]["sha"]
        assert [c["at"] for c in state["commits"]] == sorted(c["at"] for c in state["commits"])
        push_ticks = {c["sha"]: c["at"] for c in state["commits"]}
        order = [c["sha"] for c in state["commits"]]
        attempts = {}
        for j in state["ci"]["jobs"]:
            assert j["stage"] == stages[j["name"]]
            assert j["queued_at"] >= push_ticks[j["commit"]]
            attempts.setdefault((j["name"], j["commit"]), []).append(j["attempt"])
            if j["status"] == "queued":
                assert j["started_at"] is None and j["finished_at"] is None and j["runner"] is None
            elif j["status"] == "running":
                assert j["started_at"] is not None and j["finished_at"] is None and j["runner"]
                assert j["queued_at"] <= j["started_at"]
            else:
                assert j["status"] in FINISHED and j["finished_at"] is not None
            if j["status"] == "cancelled":
                # Cancelled only by a later push, at that push's tick; head attempts are never cancelled.
                assert j["commit"] != head
                later = order[order.index(j["commit"]) + 1]
                assert j["finished_at"] == push_ticks[later]
            if j["status"] == "failed" and j["stage"] in ("unit", "integration"):
                assert j["failing_tests"]
            if j["stage"] in ("lint", "build") or j["status"] != "failed":
                assert j["failing_tests"] == []
        for numbers in attempts.values():
            assert numbers == list(range(1, len(numbers) + 1))
        reviews = state["reviews"]
        assert [r["at"] for r in reviews] == sorted(r["at"] for r in reviews)
        assert len({(r["reviewer"], r["at"]) for r in reviews}) == len(reviews)
        author = state["pull_request"]["author"]
        assert all(set(r["approvers"]) - {author} for r in state["approval_rules"])


def test_unfinished_older_attempts_are_cancelled_at_each_push(episode):
    for tick in (6, 13, 35, 43):
        state = at(episode, tick)
        head = state["pull_request"]["head_commit"]
        assert all(j["status"] in FINISHED for j in state["ci"]["jobs"] if j["commit"] != head)
    state = at(episode, 13)
    assert job(state, "integration-kv", C3)["status"] == "cancelled"
    assert job(state, "integration-kv", C3)["started_at"] is None


def test_encoded_episode_and_audits(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["decision_transitions"] == 31
    assert summary["routes_unseen"] == []
    assert leakage([episode]) == []
    assert spec_overlap([episode]) == []
    assert layout_overlap(episode) <= MAX_LAYOUT_OVERLAP
    assert layout_overlap(episode) == 0.0
    result = check_module(debugging_c)
    assert result["episodes"][0]["episode_id"] == "train_debugging_c"


def test_rules_live_in_the_state_and_own_the_specification(episode):
    state = at(episode, 0)
    rules = state["assistant"]["rules"]
    assert isinstance(rules, list) and all(isinstance(r, str) for r in rules)
    text = " ".join(rules)
    for phrase in ("the governing rule is the one with the longest pattern", "wherever it stands in the list",
                   "only between equally long patterns does the one listed earlier govern",
                   "a single * matches any sequence of characters except /",
                   "reaching the limit exactly counts", "equality counts", "assistant.bots",
                   "commented reviews never change a standing", "when it failed does not matter",
                   "is not flaky by that alone", "chat is informational only",
                   "comes first in reviews", "A file that matches no rule needs no approval"):
        assert phrase in text


def test_inactive_branch_answers_are_none(episode):
    spec = episode["decision_spec"]
    for step in episode["steps"]:
        active = set(compose(spec, step["gold"]))
        branch = set(spec["branches"][step["gold"]["card"]])
        for question, value in step["gold"].items():
            if question not in active:
                assert value == "none", (step["t"], question)
            elif question in branch:
                assert value != "none", (step["t"], question)


# Options the gold never selects: the optional job and its benchmark, the bot, the author and approvers
# without a change request as reviewers, unasked approvers, and files that are covered or need no approval
# when reached.
DISTRACTORS = {"job": {"bench-holds"}, "test": {"BenchmarkSweepExpired"},
               "reviewer": {"esme", "oskar", "ingrid", "noor", "sentinel-bot"},
               "file": {"internal/reserve/renew.go", DOC, TXN}, "approver": {"ruth", "wendell", "noor"}}


def test_routes_badges_and_branch_values_reached(episode):
    seen = {q: {s["gold"][q] for s in episode["steps"]} for q in episode["questions"]}
    for question, spec in episode["questions"].items():
        assert seen[question] == set(spec["criteria"]) - DISTRACTORS.get(question, set()), question
    assert seen["reviewer"] == {"halvard", "ruth", "wendell", "none"}
    assert seen["file"] == {HOLD, HOLD_TEST, MAIN, SWEEP_TEST, "none"}
    assert seen["approver"] == {"halvard", "esme", "ingrid", "oskar", "none"}


def test_distractor_options_are_offered(episode):
    questions = episode["questions"]
    assert {"bench-holds", "none"} <= set(questions["job"]["criteria"])
    assert "BenchmarkSweepExpired" in questions["test"]["criteria"]
    assert {"sentinel-bot", "noor"} <= set(questions["reviewer"]["criteria"])
    assert DOC in questions["file"]["criteria"]


def test_no_runner_runs_two_attempts_at_once(episode):
    jobs = episode["steps"][-1]["state"]["ci"]["jobs"]
    spans = {}
    for j in jobs:
        if j["runner"]:
            end = j["finished_at"] if j["finished_at"] is not None else 60
            spans.setdefault(j["runner"], []).append((j["started_at"], end))
    for runner, busy in spans.items():
        busy.sort()
        assert all(later[0] >= earlier[1] for earlier, later in zip(busy, busy[1:])), runner


def test_scenarios_are_fresh_and_deterministic(episode):
    other = scenarios()
    assert other == [episode]
    other[0]["steps"][0]["state"]["ci"]["jobs"].clear()
    assert episode["steps"][0]["state"]["ci"]["jobs"]


def test_reference_does_not_mutate(episode):
    for step in episode["steps"]:
        state = deepcopy(step["state"])
        reference(state)
        assert state == step["state"]


# ---------------------------------------------------------------------------
# Story key ticks
# ---------------------------------------------------------------------------

KEY_TICKS = {
    0: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "none"},
    1: {"card": "investigate_test", "ci_badge": "red", "review_badge": "none", "job": "unit-reserve",
        "test": RENEWAL},
    2: {"card": "fix_lint", "ci_badge": "red", "review_badge": "none", "job": "lint"},
    4: {"card": "fix_lint", "ci_badge": "red", "review_badge": "changes_requested", "job": "lint"},
    6: {"card": "address_review", "ci_badge": "stale", "review_badge": "changes_requested",
        "reviewer": "halvard"},
    7: {"card": "address_review", "ci_badge": "pending", "review_badge": "changes_requested",
        "reviewer": "halvard"},
    10: {"card": "fix_build", "ci_badge": "red", "review_badge": "changes_requested", "job": "build"},
    12: {"card": "fix_build", "ci_badge": "red", "review_badge": "approved", "job": "build"},
    13: {"card": "wait_ci", "ci_badge": "stale", "review_badge": "approval_stale"},
    14: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approval_stale"},
    17: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approval_stale"},
    18: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approval_stale"},
    19: {"card": "unblock_queue", "ci_badge": "pending", "review_badge": "approval_stale",
         "job": "unit-storage"},
    20: {"card": "unblock_queue", "ci_badge": "pending", "review_badge": "approval_stale",
         "job": "integration-kv"},
    21: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approval_stale"},
    23: {"card": "retry_flaky", "ci_badge": "red", "review_badge": "approval_stale", "job": "integration-kv",
         "test": CONFLICT},
    24: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approval_stale"},
    27: {"card": "retry_flaky", "ci_badge": "red", "review_badge": "approval_stale", "job": "integration-kv",
         "test": CONFLICT},
    29: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approval_stale"},
    32: {"card": "investigate_test", "ci_badge": "red", "review_badge": "approval_stale",
         "job": "integration-kv", "test": CONFLICT},
    35: {"card": "wait_ci", "ci_badge": "stale", "review_badge": "approval_stale"},
    38: {"card": "investigate_test", "ci_badge": "red", "review_badge": "approval_stale",
         "job": "integration-kv", "test": CAP},
    39: {"card": "investigate_test", "ci_badge": "red", "review_badge": "approval_stale",
         "job": "unit-storage", "test": BACKOFF},
    40: {"card": "investigate_test", "ci_badge": "red", "review_badge": "approval_stale",
         "job": "unit-storage", "test": BACKOFF},
    41: {"card": "investigate_test", "ci_badge": "red", "review_badge": "changes_requested",
         "job": "unit-storage", "test": BACKOFF},
    42: {"card": "investigate_test", "ci_badge": "red", "review_badge": "changes_requested",
         "job": "unit-storage", "test": BACKOFF},
    43: {"card": "address_review", "ci_badge": "stale", "review_badge": "changes_requested", "reviewer": "ruth"},
    45: {"card": "address_review", "ci_badge": "pending", "review_badge": "changes_requested", "reviewer": "ruth"},
    46: {"card": "address_review", "ci_badge": "pending", "review_badge": "changes_requested",
         "reviewer": "wendell"},
    48: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approved"},
    49: {"card": "wait_ci", "ci_badge": "pending", "review_badge": "approved"},
    50: {"card": "request_review", "ci_badge": "green", "review_badge": "approved", "file": HOLD,
         "approver": "halvard"},
    51: {"card": "request_review", "ci_badge": "green", "review_badge": "approved", "file": HOLD,
         "approver": "halvard"},
    52: {"card": "request_review", "ci_badge": "green", "review_badge": "approved", "file": HOLD_TEST,
         "approver": "esme"},
    54: {"card": "request_review", "ci_badge": "green", "review_badge": "approved", "file": MAIN,
         "approver": "ingrid"},
    55: {"card": "request_review", "ci_badge": "green", "review_badge": "approved", "file": MAIN,
         "approver": "ingrid"},
    56: {"card": "request_review", "ci_badge": "green", "review_badge": "approved", "file": SWEEP_TEST,
         "approver": "oskar"},
    58: {"card": "merge", "ci_badge": "green", "review_badge": "approved"},
    59: {"card": "merge", "ci_badge": "green", "review_badge": "approved"},
}


@pytest.mark.parametrize("tick", sorted(KEY_TICKS))
def test_key_ticks(episode, tick):
    assert compose(episode["decision_spec"], episode["steps"][tick]["gold"]) == KEY_TICKS[tick]


def test_holds_under_distractors(episode):
    """Chat claims, optional jobs, bot reviews and author comments leave the decision unchanged."""
    gold = [compose(episode["decision_spec"], s["gold"]) for s in episode["steps"]]
    for tick in (3, 8, 9, 11, 17, 18, 26, 34, 40, 49, 51, 53, 55, 57, 59):
        assert gold[tick] == gold[tick - 1], tick


# ---------------------------------------------------------------------------
# Counterfactual edits that flip a decision for the stated reason
# ---------------------------------------------------------------------------

def test_earliest_stage_wins_over_earlier_failure_time(episode):
    state = at(episode, 2)
    assert decision(episode, state) == KEY_TICKS[2]
    job(state, "lint", C2).update(status="passed", log_tail="PASS")
    assert reference(state)["card"] == "investigate_test"
    state = at(episode, 39)
    job(state, "unit-storage", C5).update(status="passed", failing_tests=[])
    answer = reference(state)
    assert (answer["job"], answer["test"]) == ("integration-kv", CAP)


def test_within_a_stage_ci_required_order_decides(episode):
    state = at(episode, 39)
    job(state, "unit-reserve", C5).update(status="failed", finished_at=39, failing_tests=[RENEWAL])
    assert (reference(state)["job"], reference(state)["test"]) == ("unit-reserve", RENEWAL)
    required = state["ci"]["required"]
    required[2], required[3] = required[3], required[2]
    assert reference(state)["job"] == "unit-storage"


def test_queue_limit_equality(episode):
    assert reference(at(episode, 18))["card"] == "wait_ci"
    assert reference(at(episode, 19))["card"] == "unblock_queue"
    state = at(episode, 18)
    job(state, "integration-kv", C4)["queued_at"] = 13
    assert reference(state)["card"] == "unblock_queue"
    state = at(episode, 19)
    job(state, "integration-kv", C4)["queued_at"] = 15
    assert (reference(state)["card"], reference(state)["job"]) == ("unblock_queue", "unit-storage")
    job(state, "unit-storage", C4)["queued_at"] = 15
    assert reference(state)["card"] == "wait_ci"
    state = at(episode, 19)
    state["assistant"]["queue_limit"] = 6
    assert reference(state)["card"] == "wait_ci"


def test_stuck_queue_tie_breaks(episode):
    state = at(episode, 19)
    stuck = [j for j in state["ci"]["jobs"] if j["commit"] == C4 and j["status"] == "queued"]
    assert {(j["name"], j["queued_at"]) for j in stuck} == {("unit-storage", 14), ("integration-kv", 14)}
    assert reference(state)["job"] == "unit-storage"  # same queued_at 14: first in ci.required
    required = state["ci"]["required"]
    required.remove("integration-kv")
    required.insert(0, "integration-kv")
    assert reference(state)["job"] == "integration-kv"
    state = at(episode, 19)
    job(state, "integration-kv", C4)["queued_at"] = 13
    assert reference(state)["job"] == "integration-kv"  # smaller queued_at wins over ci.required order
    state = at(episode, 20)
    assert job(state, "unit-storage", C4)["status"] == "running"
    assert reference(state)["job"] == "integration-kv"


def test_failure_outranks_a_stuck_queue(episode):
    state = at(episode, 12)
    assert state["now"] - job(state, "integration-kv", C3)["queued_at"] == 5
    assert reference(state)["card"] == "fix_build"
    job(state, "build", C3).update(status="passed", log_tail="PASS")
    answer = reference(state)
    assert (answer["card"], answer["job"]) == ("unblock_queue", "integration-kv")


def test_optional_jobs_never_count(episode):
    state = at(episode, 49)
    bench = job(state, "bench-holds", C6)
    assert bench["status"] == "queued" and state["now"] - bench["queued_at"] == 5
    assert reference(state)["card"] == "wait_ci"
    state["ci"]["required"].append("bench-holds")
    assert (reference(state)["card"], reference(state)["job"]) == ("unblock_queue", "bench-holds")
    state = at(episode, 17)
    assert job(state, "bench-holds", C4)["status"] == "failed"
    assert (reference(state)["card"], reference(state)["ci_badge"]) == ("wait_ci", "pending")
    state["ci"]["required"].append("bench-holds")
    assert (reference(state)["card"], reference(state)["ci_badge"]) == ("investigate_test", "red")


def test_flaky_needs_a_later_pass_of_the_same_job_on_the_same_commit(episode):
    assert reference(at(episode, 23))["card"] == "retry_flaky"
    edits = {
        "no later pass": lambda s: s["ci"]["jobs"].remove(job(s, "integration-kv", C1, 2)),
        "pass on another commit": lambda s: job(s, "integration-kv", C1, 2).update(commit=C2, attempt=2),
        "pass of another job": lambda s: job(s, "integration-kv", C1, 2).update(name="unit-storage",
                                                                                stage="unit"),
        "pass not later": lambda s: (job(s, "integration-kv", C1, 1).update(attempt=3)),
        "later attempt failed": lambda s: job(s, "integration-kv", C1, 2).update(
            status="failed", failing_tests=[CONFLICT]),
    }
    for label, edit in edits.items():
        state = at(episode, 23)
        edit(state)
        answer = reference(state)
        assert (answer["card"], answer["test"]) == ("investigate_test", CONFLICT), label


def test_failure_on_one_commit_and_pass_on_another_is_not_flaky(episode):
    state = at(episode, 17)
    assert job(state, "unit-reserve", C3)["status"] == "passed"  # RENEWAL failed on C1 and C2, passed on C3
    job(state, "unit-reserve", C4).update(status="failed", failing_tests=[RENEWAL])
    assert (reference(state)["card"], reference(state)["test"]) == ("investigate_test", RENEWAL)
    retry = deepcopy(job(state, "unit-reserve", C2))
    retry.update(attempt=2, queued_at=3, started_at=3, finished_at=4, status="passed", failing_tests=[])
    state["ci"]["jobs"].append(retry)
    assert (reference(state)["card"], reference(state)["test"]) == ("retry_flaky", RENEWAL)


def test_max_attempts_equality(episode):
    state = at(episode, 32)
    assert job(state, "integration-kv", C4, 3)["status"] == "failed"
    assert reference(state)["card"] == "investigate_test"
    state["assistant"]["max_attempts"] = 4
    assert reference(state)["card"] == "retry_flaky"
    state = at(episode, 27)
    assert reference(state)["card"] == "retry_flaky"
    state["assistant"]["max_attempts"] = 2
    assert (reference(state)["card"], reference(state)["test"]) == ("investigate_test", CONFLICT)


def test_mixed_failure_names_first_non_flaky_test(episode):
    state = at(episode, 38)
    assert job(state, "integration-kv", C5)["failing_tests"] == [CONFLICT, CAP]
    assert reference(state)["test"] == CAP
    job(state, "integration-kv", C5)["failing_tests"] = [CAP, CONFLICT]
    assert reference(state)["test"] == CAP
    job(state, "integration-kv", C5)["failing_tests"] = [CONFLICT]
    assert (reference(state)["card"], reference(state)["test"]) == ("retry_flaky", CONFLICT)


def test_highest_attempt_on_head_is_current(episode):
    state = at(episode, 24)
    assert job(state, "integration-kv", C4, 2)["status"] == "queued"
    assert (reference(state)["card"], reference(state)["ci_badge"]) == ("wait_ci", "pending")
    state["ci"]["jobs"].remove(job(state, "integration-kv", C4, 2))
    assert (reference(state)["card"], reference(state)["ci_badge"]) == ("retry_flaky", "red")


def test_older_commit_attempts_never_count(episode):
    state = at(episode, 35)
    assert job(state, "integration-kv", C4, 3)["status"] == "failed"
    assert (reference(state)["card"], reference(state)["ci_badge"]) == ("wait_ci", "stale")
    state["pull_request"]["head_commit"] = C4
    assert (reference(state)["card"], reference(state)["ci_badge"]) == ("investigate_test", "red")


def test_card_priority_between_failure_change_request_wait_and_approvals(episode):
    state = at(episode, 41)
    assert reference(state)["card"] == "investigate_test"  # failure outranks the change request
    job(state, "unit-storage", C5).update(status="passed", failing_tests=[])
    job(state, "integration-kv", C5).update(status="passed", failing_tests=[])
    assert reference(state)["card"] == "address_review"  # change request outranks green-CI review work
    state = at(episode, 49)
    assert reference(state)["card"] == "wait_ci"  # pending CI outranks missing approvals
    job(state, "integration-kv", C6).update(status="passed", finished_at=49)
    assert (reference(state)["card"], reference(state)["file"]) == ("request_review", HOLD)


def test_change_request_persists_until_the_same_reviewer_approves(episode):
    state = at(episode, 43)
    assert (reference(state)["card"], reference(state)["reviewer"]) == ("address_review", "ruth")
    add_review(state, "ruth", "commented", C6, 43.5)
    add_review(state, "halvard", "approved", C6, 43.6)
    assert (reference(state)["card"], reference(state)["reviewer"]) == ("address_review", "ruth")
    add_review(state, "ruth", "approved", C6, 43.7)
    assert (reference(state)["card"], reference(state)["reviewer"]) == ("address_review", "wendell")
    add_review(state, "wendell", "approved", C6, 43.8)
    assert (reference(state)["card"], reference(state)["review_badge"]) == ("wait_ci", "approved")


def wendell_request(state):
    return next(r for r in state["reviews"] if r["reviewer"] == "wendell" and r["verdict"] == "changes_requested")


def test_oldest_change_request_is_named(episode):
    state = at(episode, 43)
    ruth = next(r for r in state["reviews"] if r["reviewer"] == "ruth")
    assert (ruth["at"], wendell_request(state)["at"]) == (41, 42)
    assert reference(state)["reviewer"] == "ruth"  # older request, although wendell's is newer
    wendell_request(state)["at"] = 40
    state["reviews"].sort(key=lambda r: r["at"])
    assert reference(state)["reviewer"] == "wendell"


def test_change_requests_at_the_same_tick_follow_reviews_order(episode):
    state = at(episode, 43)
    wendell = wendell_request(state)
    wendell["at"] = 41
    assert state["reviews"].index(wendell) > [r["reviewer"] for r in state["reviews"]].index("ruth")
    assert reference(state)["reviewer"] == "ruth"
    state["reviews"].remove(wendell)
    position = next(i for i, r in enumerate(state["reviews"]) if r["reviewer"] == "ruth")
    state["reviews"].insert(position, wendell)
    assert reference(state)["reviewer"] == "wendell"


def test_a_change_request_outranks_a_current_approval(episode):
    state = at(episode, 46)
    ruth = state["reviews"][-1]
    assert (ruth["reviewer"], ruth["verdict"], ruth["commit"]) == ("ruth", "approved", C6)
    assert (reference(state)["review_badge"], reference(state)["reviewer"]) == ("changes_requested", "wendell")
    state["reviews"].remove(wendell_request(state))
    assert (reference(state)["card"], reference(state)["review_badge"]) == ("wait_ci", "approved")


def test_bot_and_author_reviews_never_count(episode):
    state = at(episode, 51)
    assert state["reviews"][-1]["reviewer"] == "sentinel-bot"
    assert reference(state)["card"] == "request_review"
    state["assistant"]["bots"].remove("sentinel-bot")
    assert reference(state)["card"] == "address_review"
    state = at(episode, 50)
    add_review(state, "noor", "approved", C6, 50.5)
    assert (reference(state)["file"], reference(state)["approver"]) == (HOLD, "halvard")
    state = at(episode, 6)
    add_review(state, "noor", "changes_requested", C2, 5)
    assert reference(state)["reviewer"] == "halvard"


def test_commented_reviews_never_set_a_standing(episode):
    assert reference(at(episode, 0))["review_badge"] == "none"
    state = at(episode, 57)
    oskar = next(r for r in state["reviews"] if r["reviewer"] == "oskar")
    assert oskar["verdict"] == "commented"
    assert reference(state)["approver"] == "oskar"
    oskar["verdict"] = "approved"
    assert reference(state)["card"] == "merge"


def test_stale_approvals(episode):
    state = at(episode, 58)
    assert reference(state)["card"] == "merge"
    oskar = state["reviews"][-1]
    assert (oskar["reviewer"], oskar["verdict"]) == ("oskar", "approved")
    oskar["commit"] = C5
    answer = reference(state)
    assert (answer["card"], answer["file"], answer["approver"], answer["review_badge"]) == (
        "request_review", SWEEP_TEST, "oskar", "approved")
    state = at(episode, 50)
    halvard = [r for r in state["reviews"] if r["reviewer"] == "halvard"][-1]
    assert (halvard["verdict"], halvard["commit"]) == ("approved", C3)
    halvard["commit"] = C6
    assert reference(state)["file"] == HOLD_TEST
    state = at(episode, 13)
    assert reference(state)["review_badge"] == "approval_stale"
    state["pull_request"]["head_commit"] = C3
    assert reference(state)["review_badge"] == "approved"


def rule(state, pattern):
    return next(r for r in state["approval_rules"] if r["pattern"] == pattern)


def first_or_last_match(state, path, last):
    """The rule a list-order convention would pick; used only to show that the record separates them."""
    matching = [r for r in state["approval_rules"] if _glob(r["pattern"]).fullmatch(path)]
    return matching[-1 if last else 0]


def test_longest_matching_pattern_governs_wherever_it_is_listed(episode):
    state = at(episode, 52)
    assert (reference(state)["file"], reference(state)["approver"]) == (HOLD_TEST, "esme")
    # hold_test.go: the 26-character test pattern (listed first) beats internal/reserve/** (19, listed later),
    # so halvard's current approval does not cover it; a last-match convention would have picked halvard.
    assert first_or_last_match(state, HOLD_TEST, last=True)["approvers"] == ["noor", "halvard"]
    state["approval_rules"].reverse()
    assert (reference(state)["file"], reference(state)["approver"]) == (HOLD_TEST, "esme")
    state = at(episode, 56)
    assert (reference(state)["file"], reference(state)["approver"]) == (SWEEP_TEST, "oskar")
    # sweep_test.go: internal/reserve/sweep/** (25, listed last) beats internal/reserve/** (19, listed
    # earlier); a first-match convention would have picked halvard, whose current approval covers it.
    assert first_or_last_match(state, SWEEP_TEST, last=False)["approvers"] == ["noor", "halvard"]
    state["approval_rules"].reverse()
    assert (reference(state)["file"], reference(state)["approver"]) == (SWEEP_TEST, "oskar")


def test_a_shorter_pattern_loses_and_list_order_breaks_only_a_length_tie(episode):
    state = at(episode, 52)
    rule(state, "internal/reserve/*_test.go")["pattern"] = "**/*_test.go"  # 12 characters: reserve/** governs
    assert (reference(state)["file"], reference(state)["approver"]) == (MAIN, "ingrid")
    state = at(episode, 52)
    tied = rule(state, "internal/reserve/*_test.go")
    tied["pattern"] = "internal/**_test.go"
    assert len(tied["pattern"]) == len("internal/reserve/**") == 19
    assert state["approval_rules"].index(tied) == 0  # listed earlier: esme's rule governs the tie
    assert (reference(state)["file"], reference(state)["approver"]) == (HOLD_TEST, "esme")
    state["approval_rules"].remove(tied)
    state["approval_rules"].append(tied)  # now internal/reserve/** is listed earlier and halvard covers it
    assert (reference(state)["file"], reference(state)["approver"]) == (MAIN, "ingrid")


def test_single_star_does_not_cross_a_slash(episode):
    assert _glob("internal/reserve/*_test.go").fullmatch(HOLD_TEST)
    assert not _glob("internal/reserve/*_test.go").fullmatch(SWEEP_TEST)
    assert _glob("internal/reserve/**_test.go").fullmatch(SWEEP_TEST)
    assert _glob("**").fullmatch(MAIN) and not _glob("*").fullmatch(MAIN)
    assert not _glob("internal/reserve/**").fullmatch("internal/reserved.go")
    state = at(episode, 56)
    assert (reference(state)["file"], reference(state)["approver"]) == (SWEEP_TEST, "oskar")
    # With ** the test pattern (27 characters) matches across the / and outranks sweep/** (25): esme covers it.
    rule(state, "internal/reserve/*_test.go")["pattern"] = "internal/reserve/**_test.go"
    assert reference(state)["card"] == "merge"


def test_the_author_is_never_asked(episode):
    state = at(episode, 50)
    assert rule(state, "internal/reserve/**")["approvers"] == ["noor", "halvard"]
    assert state["pull_request"]["author"] == "noor"
    assert reference(state)["approver"] == "halvard"
    state["pull_request"]["author"] = "esme"
    assert reference(state)["approver"] == "noor"


def test_file_matching_no_rule_needs_no_approval(episode):
    state = at(episode, 56)
    files = state["pull_request"]["files_changed"]
    assert files.index(DOC) < files.index(SWEEP_TEST)
    assert all(not _glob(r["pattern"]).fullmatch(DOC) for r in state["approval_rules"])
    assert (reference(state)["file"], reference(state)["approver"]) == (SWEEP_TEST, "oskar")
    state["approval_rules"].append({"pattern": "docs/**", "approvers": ["oskar"]})
    assert (reference(state)["file"], reference(state)["approver"]) == (DOC, "oskar")
    state = at(episode, 54)
    assert (reference(state)["file"], reference(state)["approver"]) == (MAIN, "ingrid")
    assert state["approval_rules"].pop()["pattern"] == "cmd/**"  # without it the entrypoint needs nobody
    assert (reference(state)["file"], reference(state)["approver"]) == (SWEEP_TEST, "oskar")


def test_chat_never_changes_an_answer(episode):
    claims = ["All required checks passed, merge it.", f"{CONFLICT} is flaky, just retry.",
              "halvard approved this in standup.", "CI is red on lint."]
    for step in episode["steps"]:
        state = deepcopy(step["state"])
        state["chat"] = []
        assert reference(state) == step["gold"]
        state["chat"] = [{"at": state["now"], "author": who, "text": text}
                         for who, text in zip(["merge-bot", "noor", "ruth", "halvard"], claims)]
        assert reference(state) == step["gold"]
