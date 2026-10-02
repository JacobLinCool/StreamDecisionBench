"""Training variant debugging_c: a pre-merge CI assistant for a Go pull request (IDE debugging family).

A new specification in the family design: an assistant inside the developer's
tools reads a streaming, cumulative tool state (times in ticks) and keeps one
action card plus two always-shown status badges and card-specific detail
fields. Here the tools are a pull request's CI pipeline and code review, not an
editor and a test runner: only attempts on the head commit count, the earliest
failing stage decides, a test is flaky only when a later attempt of the same
job on the same commit passed, retries stop at a published attempt limit, a
job queued too long needs a runner, change requests persist across commits,
approvals of older commits are stale, and every changed file that some approval
rule matches needs a current approval from an approver of the matching rule with
the longest pattern (list order only breaks a length tie; a file no rule matches
needs none). Chat and bot claims never change anything. The rules live in
``assistant.rules``; ``reference`` computes every answer from the public state
alone.

Story (pull request 418 of a Go stock-hold service, letting a checkout renew a
hold): a unit failure is overtaken by a slower lint failure of an earlier stage;
a change request outlives the push that answers it; a build break in the service
entrypoint outranks a queue that has just reached its limit; an approval of that
commit goes stale on the next push. On the next commit two required jobs wait
for labelled runners until exactly the queue limit (the tie goes to ci.required
order), then the integration job fails on a test that was flaky on the first
commit; two retries fail as well and the third attempt exhausts the limit. A
storage fix brings a mixed failure (a flaky test listed before a new one) and an
earlier-stage unit failure that the author calls flaky, plus change requests
from both storage approvers: the older one is named first, and a fresh approval
does not lift the review badge while the other request stands. The last commit
goes green while an optional benchmark is stuck in the queue and a merge bot
claims success early; a review bot's change request is ignored, and four
approvers are asked in files_changed order (skipping the author, letting the
longest matching pattern govern whether it is listed first or last, a single *
that stops at / and a documentation file that no rule covers) until the card
says merge.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

EPISODE_ID = "train_debugging_c"
TITLE = "Pre-merge CI and approval watch for a stock-hold pull request"

RULES = [
    "Time and history: now and every time field (commits[].at, ci.jobs[].queued_at, started_at and "
    "finished_at, reviews[].at, chat[].at) is a tick. The state for tick t has now = t and is published at "
    "tick t; it keeps all history and holds nothing later than now. Answers are recomputed only when a new "
    "state is published.",
    "Commits: commits lists every pushed commit in push order, and pull_request.head_commit is the sha of "
    "the newest one. Only the head commit is current; every job attempt and every approval tied to an older "
    "commit is stale: an older-commit attempt is never a current attempt and serves only as evidence under "
    "the flaky-test rule, and an older-commit approval is a stale approval (see Reviews). "
    "pull_request.files_changed lists, in order, every file the pull request changes "
    "relative to its base branch.",
    "CI records: ci.jobs lists every job attempt in creation order. An attempt has a job name, a stage "
    "(lint, build, unit or integration), the commit it tests, an attempt number (1 for the first run of that "
    "job on that commit, one higher for each retry), a status and failing_tests. Status queued means no "
    "runner has picked the attempt up (started_at, finished_at and runner are null); running means started_at "
    "is set and finished_at is null; passed, failed and cancelled are finished. When a commit is pushed, CI "
    "cancels every queued or running attempt of older commits at that tick; attempts of the head commit are "
    "never cancelled. Jobs of one commit run independently, so a failure never stops another job. A failed "
    "unit or integration attempt lists at least one failing test; lint and build attempts list none. "
    "log_tail and runner are informational only.",
    "Required jobs: only jobs named in ci.required count. Any other job (such as an optional benchmark) "
    "never affects a badge or the card, whatever its status or however long it has been queued. The current "
    "attempt of a required job is its attempt on the head commit with the highest attempt number; attempts "
    "on older commits are never current, whatever their status (they matter only as flakiness evidence).",
    "ci_badge: stale if no required job has an attempt on the head commit yet; otherwise red if the current "
    "attempt of some required job failed; otherwise green if the current attempt of every required job "
    "passed; otherwise pending (some current attempt is queued or running, or some required job has no "
    "attempt on the head commit yet).",
    "Flaky tests: a test is flaky when some attempt of a required job on some commit (the head commit or an "
    "older one) failed listing that test and a later attempt (higher attempt number) of the same job name on "
    "the same commit passed. A test that failed on one commit and passed on a different commit is not flaky "
    "by that alone. What anyone says about flakiness does not make a test flaky.",
    "Reviews: reviews lists every review in time order, each with reviewer, verdict (approved, "
    "changes_requested or commented), the commit reviewed and at; one reviewer never submits two reviews at "
    "the same tick. Reviews by the pull request author and by accounts in assistant.bots never count. A "
    "reviewer's standing is the verdict of their latest counted review whose verdict is approved or "
    "changes_requested; commented reviews never change a standing, and a reviewer without such a review has "
    "no standing. A changes_requested standing therefore stays in force across later commits until the same "
    "reviewer approves. A reviewer has a current approval when their standing is approved and the review "
    "that sets it is on the head commit, and a stale approval when their standing is approved on an older "
    "commit.",
    "review_badge: changes_requested if some reviewer's standing is changes_requested; otherwise approved if "
    "some reviewer has a current approval; otherwise approval_stale if some reviewer has a stale approval; "
    "otherwise none.",
    "Approval rules: approval_rules is a list of rules, each a pattern and a list of approvers; every rule "
    "lists at least one approver other than the pull request author. A rule matches a changed file when its "
    "pattern matches the whole path. In a pattern, ** matches any sequence of characters including /, a "
    "single * matches any sequence of characters except /, and every other character matches only itself. "
    "When several rules match a file, the governing rule is the one with the longest pattern, counted in "
    "characters with wildcards included, wherever it stands in the list; only between equally long "
    "patterns does the one listed earlier govern. The other matching rules are ignored for that file. A "
    "changed file is covered when at least one approver of its governing rule has a current approval. A "
    "file that matches no rule needs no approval.",
    "Card: take the first of these numbered conditions that holds. (1) Failure: if the current attempt of "
    "some required job failed, select the failed required job of the earliest stage in the order lint, build, unit, integration (when it "
    "failed does not matter); within one stage take the job listed first in ci.required. A lint job gives "
    "fix_lint and a build job gives fix_build, naming that job; a unit or integration job follows the test "
    "rule. (2) Stuck queue: if the current attempt of some required job is queued and now - queued_at >= "
    "assistant.queue_limit (reaching the limit exactly counts), give unblock_queue naming that job; if "
    "several qualify, take the smallest queued_at, then the first in ci.required. (3) Change request: if "
    "some reviewer's standing is changes_requested, give address_review naming, among the reviewers with "
    "that standing, the one whose standing-setting review has the smallest at; if several share that at, "
    "the one whose review comes first in reviews. (4) If ci_badge is stale or pending, give wait_ci. (5) If "
    "some changed file that needs approval is not covered, give request_review naming the first such file "
    "in files_changed order and, as approver, the first approver listed in that file's governing rule who "
    "is not the pull request author. (6) Otherwise merge.",
    "Test rule for a selected unit or integration job: read the failing_tests of its current attempt in list "
    "order. If at least one of them is not flaky, give investigate_test with the first test that is not "
    "flaky. If all of them are flaky and the attempt number is below assistant.max_attempts, give "
    "retry_flaky with the first failing test. If all are flaky and the attempt number is at least "
    "max_attempts (equality counts: no retry is left), give investigate_test with the first failing test. "
    "Both cards also name the job.",
    "Chat and bots: chat is informational only. Claims made in chat by people or bots (that checks passed, "
    "that a test is flaky, that someone approved, that the pull request can merge) never change a job "
    "status, a review or any answer; only the pull_request, ci, reviews and approval_rules records and the "
    "assistant settings do.",
    "Composition: ci_badge and review_badge are always shown. The card adds: fix_lint, fix_build and "
    "unblock_queue -> job; investigate_test and retry_flaky -> job and test; address_review -> reviewer; "
    "request_review -> file and approver; wait_ci and merge -> nothing. Every question that the active card "
    "does not use is answered none.",
]

STAGE_ORDER = ["lint", "build", "unit", "integration"]


# ---------------------------------------------------------------------------
# Public-state reference
# ---------------------------------------------------------------------------

def _glob(pattern: str) -> re.Pattern[str]:
    """Approval-rule pattern: ** crosses /, a single * stays within one path segment."""
    parts, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts), re.DOTALL)


def _governing_rule(state: dict[str, Any], path: str) -> dict | None:
    """The matching approval rule with the longest pattern; an earlier listing breaks a length tie."""
    matching = [(index, rule) for index, rule in enumerate(state["approval_rules"])
                if _glob(rule["pattern"]).fullmatch(path)]
    if not matching:
        return None
    return min(matching, key=lambda item: (-len(item[1]["pattern"]), item[0]))[1]


def _current(state: dict[str, Any]) -> dict[str, dict | None]:
    head = state["pull_request"]["head_commit"]
    current: dict[str, dict | None] = {}
    for name in state["ci"]["required"]:
        attempts = [job for job in state["ci"]["jobs"] if job["name"] == name and job["commit"] == head]
        current[name] = max(attempts, key=lambda job: job["attempt"]) if attempts else None
    return current


def _flaky(jobs: list[dict], required: list[str]) -> set[str]:
    flaky: set[str] = set()
    for failed in jobs:
        if failed["status"] != "failed" or failed["name"] not in required:
            continue
        if any(later["name"] == failed["name"] and later["commit"] == failed["commit"]
               and later["attempt"] > failed["attempt"] and later["status"] == "passed" for later in jobs):
            flaky.update(failed["failing_tests"])
    return flaky


def _standings(state: dict[str, Any]) -> dict[str, dict]:
    """Each counted reviewer's latest approved or changes_requested review, with its position in reviews."""
    ignored = set(state["assistant"]["bots"]) | {state["pull_request"]["author"]}
    reviews = state["reviews"]
    standing: dict[str, dict] = {}
    for position in sorted(range(len(reviews)), key=lambda i: reviews[i]["at"]):
        review = reviews[position]
        if review["reviewer"] in ignored or review["verdict"] not in ("approved", "changes_requested"):
            continue
        standing[review["reviewer"]] = review | {"position": position}
    return standing


def reference(state: dict[str, Any]) -> dict[str, str]:
    """Derive every answer from the published state alone (no tick index, gold or hidden field)."""
    now = state["now"]
    settings = state["assistant"]
    pr = state["pull_request"]
    head = pr["head_commit"]
    required = state["ci"]["required"]
    current = _current(state)

    if all(job is None for job in current.values()):
        ci_badge = "stale"
    elif any(job and job["status"] == "failed" for job in current.values()):
        ci_badge = "red"
    elif all(job and job["status"] == "passed" for job in current.values()):
        ci_badge = "green"
    else:
        ci_badge = "pending"

    standing = _standings(state)
    requests = [r for r in standing.values() if r["verdict"] == "changes_requested"]
    approvers = {name for name, r in standing.items() if r["verdict"] == "approved" and r["commit"] == head}
    if requests:
        review_badge = "changes_requested"
    elif approvers:
        review_badge = "approved"
    elif any(r["verdict"] == "approved" for r in standing.values()):
        review_badge = "approval_stale"
    else:
        review_badge = "none"

    answer = {"card": "wait_ci", "ci_badge": ci_badge, "review_badge": review_badge,
              "job": "none", "test": "none", "reviewer": "none", "file": "none", "approver": "none"}

    failed = [name for name in required if current[name] and current[name]["status"] == "failed"]
    if failed:
        name = min(failed, key=lambda n: (STAGE_ORDER.index(current[n]["stage"]), required.index(n)))
        attempt = current[name]
        stage = attempt["stage"]
        if stage == "lint":
            return answer | {"card": "fix_lint", "job": name}
        if stage == "build":
            return answer | {"card": "fix_build", "job": name}
        tests = attempt["failing_tests"]
        if not tests:
            raise ValueError(f"failed {stage} attempt without failing tests: {name}")
        flaky = _flaky(state["ci"]["jobs"], required)
        steady = [test for test in tests if test not in flaky]
        if steady:
            return answer | {"card": "investigate_test", "job": name, "test": steady[0]}
        if attempt["attempt"] < settings["max_attempts"]:
            return answer | {"card": "retry_flaky", "job": name, "test": tests[0]}
        return answer | {"card": "investigate_test", "job": name, "test": tests[0]}

    stuck = [name for name in required if current[name] and current[name]["status"] == "queued"
             and now - current[name]["queued_at"] >= settings["queue_limit"]]
    if stuck:
        name = min(stuck, key=lambda n: (current[n]["queued_at"], required.index(n)))
        return answer | {"card": "unblock_queue", "job": name}

    if requests:
        oldest = min(requests, key=lambda r: (r["at"], r["position"]))
        return answer | {"card": "address_review", "reviewer": oldest["reviewer"]}

    if ci_badge in ("stale", "pending"):
        return answer

    for path in pr["files_changed"]:
        rule = _governing_rule(state, path)
        if rule is None or approvers & set(rule["approvers"]):
            continue
        candidates = [person for person in rule["approvers"] if person != pr["author"]]
        if not candidates:
            raise ValueError(f"approval rule {rule['pattern']!r} lists only the author")
        return answer | {"card": "request_review", "file": path, "approver": candidates[0]}
    return answer | {"card": "merge"}


# ---------------------------------------------------------------------------
# Questions and decision
# ---------------------------------------------------------------------------

HOLD = "internal/reserve/hold.go"
RENEW = "internal/reserve/renew.go"
HOLD_TEST = "internal/reserve/hold_test.go"
MAIN = "cmd/stockhold/main.go"
DOC = "docs/holds.md"
SWEEP_TEST = "internal/reserve/sweep/sweep_test.go"
TXN = "internal/storage/kvclient/txn.go"
FILES = [HOLD, RENEW, HOLD_TEST, MAIN, DOC, SWEEP_TEST, TXN]

REQUIRED = ["lint", "build", "unit-reserve", "unit-storage", "integration-kv"]
BENCH = "bench-holds"
STAGES = {"lint": "lint", "build": "build", "unit-reserve": "unit", "unit-storage": "unit",
          "integration-kv": "integration", BENCH: "unit"}
RUNNER_LABEL = {"unit-storage": "std-large", "integration-kv": "kv-cluster", BENCH: "bench"}

T_RENEW = "TestRenewExtendsFromNow"
T_CONFLICT = "TestReserveRetriesOnConflict"
T_CAP = "TestReserveRetryCapHonoured"
T_BACKOFF = "TestTxnRetryBackoff"
T_BENCH = "BenchmarkSweepExpired"

AUTHOR = "noor"
BOTS = ["merge-bot", "sentinel-bot"]
# Longest pattern governs: hold_test.go takes the first matching rule (26 characters beat 19) and
# sweep_test.go the last (25 beat 19; the 26-character test pattern does not match across a /).
APPROVAL_RULES = [
    {"pattern": "internal/reserve/*_test.go", "approvers": ["esme"]},
    {"pattern": "internal/reserve/**", "approvers": ["noor", "halvard"]},
    {"pattern": "internal/reserve/sweep/**", "approvers": ["oskar"]},
    {"pattern": "internal/storage/**", "approvers": ["ruth", "wendell"]},
    {"pattern": "cmd/**", "approvers": ["ingrid"]},
]
PEOPLE = ["halvard", "ruth", "wendell", "esme", "oskar", "ingrid"]


def _choice(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _questions() -> dict[str, dict]:
    return {
        "card": _choice(
            "Which action card should the pre-merge assistant show for this pull request now? Go through the "
            "numbered card conditions in assistant.rules and use the first one that holds.",
            {"wait_ci": "Wait: CI for the head commit has not started or not finished",
             "fix_lint": "Fix the failing lint job", "fix_build": "Fix the failing build job",
             "investigate_test": "Investigate a failing test",
             "retry_flaky": "Retry a job whose failing tests are all flaky, while attempts remain",
             "unblock_queue": "Find a runner for a job stuck in the queue",
             "address_review": "Respond to a reviewer's change request",
             "request_review": "Ask a listed approver to approve the head commit",
             "merge": "Merge the pull request"}),
        "ci_badge": _choice(
            "Which CI badge describes the required jobs of the head commit now? Attempts on older commits and "
            "jobs outside ci.required do not count.",
            {"stale": "No required job has an attempt on the head commit yet",
             "pending": "No current required attempt failed, but one is queued or running or not created yet",
             "red": "Some required job's current attempt failed",
             "green": "Every required job's current attempt passed"}),
        "review_badge": _choice(
            "Which review badge describes the counted review standings now? Author and bot reviews and "
            "commented reviews never set a standing.",
            {"none": "No reviewer has an approved or changes_requested standing",
             "approved": "Some reviewer approved the head commit and nobody requests changes",
             "changes_requested": "Some reviewer's standing is a change request",
             "approval_stale": "Approvals exist, but only for older commits, and nobody requests changes"}),
        "job": _choice(
            "Which CI job does the card act on? Used by fix_lint, fix_build, unblock_queue, investigate_test "
            "and retry_flaky; none for every other card.",
            {**{name: f"The {name} job" for name in [*REQUIRED, BENCH]}, "none": "The card names no job"}),
        "test": _choice(
            "Which test does the card name? Used by investigate_test and retry_flaky only; none for every "
            "other card.",
            {T_RENEW: "Hold renewal unit test", T_CONFLICT: "Reservation conflict retry integration test",
             T_CAP: "Retry cap integration test", T_BACKOFF: "Transaction backoff unit test",
             T_BENCH: "Sweep benchmark", "none": "The card names no test"}),
        "reviewer": _choice(
            "Whose change request must the author answer first? Used by address_review only; none for every "
            "other card.",
            {**{name: f"Answer {name}" for name in [*PEOPLE, AUTHOR, BOTS[1]]},
             "none": "The card names no reviewer"}),
        "file": _choice(
            "Which file does request_review name: the first file in files_changed that some approval rule "
            "matches and for which no approver of its governing rule has a current approval? Used by "
            "request_review only; none for every other card.",
            {**{path: f"Ask for approval of {path}" for path in FILES},
             "none": "The card names no file"}),
        "approver": _choice(
            "Who should request_review ask: the first approver listed in that file's governing rule who is "
            "not the pull request author? Used by request_review only; none for every other card.",
            {**{name: f"Ask {name}" for name in [*PEOPLE, AUTHOR]}, "none": "The card names no approver"}),
    }


DECISION_SPEC = {
    "route_question": "card", "always": ["ci_badge", "review_badge"],
    "branches": {"wait_ci": [], "fix_lint": ["job"], "fix_build": ["job"],
                 "investigate_test": ["job", "test"], "retry_flaky": ["job", "test"],
                 "unblock_queue": ["job"], "address_review": ["reviewer"],
                 "request_review": ["file", "approver"], "merge": []},
}


# ---------------------------------------------------------------------------
# Scripted session
# ---------------------------------------------------------------------------

C1, C2, C3, C4, C5, C6 = "a41c0de", "5be7d12", "c90e4f1", "e27b3a9", "7d0e5c3", "f4a8b61"

RUNNING_LOG = {
    "lint": "golangci-lint run ./internal/...",
    "build": "go build ./cmd/...",
    "unit-reserve": "go test ./internal/reserve/...",
    "unit-storage": "go test ./internal/storage/...",
    "integration-kv": "go test -tags integration ./test/integration/...",
    BENCH: "go test -run '^$' -bench . ./internal/reserve/...",
}

FAIL_LOG = {
    "lint-c2": "internal/reserve/renew.go:41:6: func `lastRenewed` is unused (unused)",
    "build-c3": "cmd/stockhold/main.go:57:21: undefined: reserve.HoldTTL",
    T_RENEW: (f"--- FAIL: {T_RENEW}\n    hold_test.go:64: renewed hold expires 30s after its old expiresAt, "
              "want 30s after the renewal"),
    T_CONFLICT: f"--- FAIL: {T_CONFLICT}\n    txn conflict on holds/sku-2093 after 5 immediate retries",
    "cap": (f"--- FAIL: {T_CONFLICT}\n--- FAIL: {T_CAP}\n"
            "    reserve made 9 transaction attempts, cap is 5"),
    T_BACKOFF: (f"--- FAIL: {T_BACKOFF}\n    a concurrent Get waited 50ms behind a backing-off retry, "
                "want no wait"),
    T_BENCH: f"{T_BENCH}: 18% slower than main (threshold 10%)",
}

# Authoring witnesses for ticks whose decision turns on a timer or a non-event.
NOTES = {
    0: "c2 jobs are queued or running; the failed c1 attempts belong to an older commit",
    2: "lint failed after unit-reserve, but lint is the earlier stage, so it is selected",
    5: "integration-kv on 5be7d12 is still running; lint stays the earliest failing stage",
    11: "c3 integration-kv has been queued for 4 ticks (since 7)",
    12: "c3 integration-kv queued for 5 ticks reaches queue_limit, but the build failure outranks the queue",
    18: "c4 unit-storage and integration-kv queued for 4 ticks (since 14): below queue_limit",
    19: ("c4 unit-storage and integration-kv both queued for exactly 5 ticks since 14: same queued_at, "
         "unit-storage comes first in ci.required"),
    20: "integration-kv, queued for 6 ticks, is now the only stuck required job",
    22: "integration-kv attempt 1 on e27b3a9 is running",
    23: f"{T_CONFLICT} is flaky: integration-kv on {C1} failed it in attempt 1 and passed in attempt 2",
    27: "attempt 2 is below max_attempts 3: retry once more",
    32: "attempt 3 equals max_attempts 3: no retry left, investigate",
    38: f"{T_CONFLICT} is flaky but {T_CAP} is not; the first non-flaky test is selected",
    39: "unit-storage (unit stage) outranks the earlier-reported integration failure",
    41: "the failure card outranks ruth's change request",
    42: "wendell's change request joins ruth's; the failure card still outranks both",
    43: (f"ruth's (at 41) and wendell's (at 42) change requests on {C5} stay in force on the new head {C6}; "
         "the older one is named"),
    46: "ruth now approves the head commit, but wendell's change request still sets the badge and the card",
    48: "no change request is in force; integration-kv on the head commit is still running",
    49: "bench-holds is optional: queued for 5 ticks but ignored; integration-kv still running",
    50: (f"halvard's approval is on {C3} (stale); hold.go is governed by internal/reserve/** whose approvers "
         "are noor (author) and halvard"),
    51: "sentinel-bot is listed in assistant.bots: its change request does not count",
    52: (f"{HOLD_TEST} matches internal/reserve/*_test.go (26 characters) and internal/reserve/** (19): the "
         "longer test pattern governs, so halvard's approval does not cover it: approver esme"),
    54: f"{MAIN} matches only the cmd/** rule: approver ingrid",
    55: "oskar's review is commented: no standing, no coverage",
    56: (f"{DOC} matches no approval rule and needs no approval; {SWEEP_TEST}: a single * does not cross '/', "
         "so the 26-character test pattern does not match and internal/reserve/sweep/** (25) outranks "
         "internal/reserve/** (19) although it is listed later: approver oskar"),
    58: "every changed file has a current approval from an approver of its governing rule",
}


def _job(name: str, commit: str, attempt: int, queued_at: int) -> dict[str, Any]:
    label = RUNNER_LABEL.get(name)
    waiting = f"Waiting for a runner labelled {label}" if label else "Waiting for a runner"
    return {"name": name, "stage": STAGES[name], "commit": commit, "attempt": attempt, "status": "queued",
            "queued_at": queued_at, "started_at": None, "finished_at": None, "runner": None,
            "failing_tests": [], "log_tail": waiting}


def _history() -> list[dict]:
    """CI attempts before tick 0: the first commit, its integration retry, and the second commit's start."""
    jobs = []

    def done(name: str, commit: str, attempt: int, queued: int, started: int, finished: int, runner: str,
             status: str, failing: list[str] | None = None, log: str = "PASS") -> None:
        job = _job(name, commit, attempt, queued)
        job.update(status=status, started_at=started, finished_at=finished, runner=runner,
                   failing_tests=list(failing or []), log_tail=log)
        jobs.append(job)

    done("lint", C1, 1, -13, -13, -12, "std-runner-a", "passed")
    done("build", C1, 1, -13, -13, -11, "std-runner-b", "passed")
    done("unit-reserve", C1, 1, -13, -12, -10, "std-runner-c", "failed", [T_RENEW], FAIL_LOG[T_RENEW])
    done("unit-storage", C1, 1, -13, -12, -10, "large-runner-a", "passed")
    done("integration-kv", C1, 1, -13, -12, -9, "kv-runner-a", "failed", [T_CONFLICT], FAIL_LOG[T_CONFLICT])
    done(BENCH, C1, 1, -13, -12, -9, "bench-runner-a", "passed")
    done("integration-kv", C1, 2, -8, -8, -5, "kv-runner-a", "passed")
    for name, started, runner in [("lint", -2, "std-runner-a"), ("build", -1, "std-runner-b"),
                                  ("unit-reserve", -1, "std-runner-c"), ("unit-storage", -1, "large-runner-a"),
                                  ("integration-kv", 0, "kv-runner-a"), (BENCH, None, None)]:
        job = _job(name, C2, 1, -2)
        if started is not None:
            job.update(status="running", started_at=started, runner=runner, log_tail=RUNNING_LOG[name])
        jobs.append(job)
    return jobs


def _initial() -> dict[str, Any]:
    return {
        "now": 0,
        "assistant": {
            "role": ("Pre-merge assistant in the developer's code-review tool for the warehouse.dev/stockhold "
                     "Go service. It only shows a card and badges; it never retries, merges or messages anyone."),
            "rules": RULES,
            "queue_limit": 5,
            "max_attempts": 3,
            "bots": list(BOTS),
        },
        "pull_request": {
            "number": 418,
            "title": "Let a long checkout renew its stock hold",
            "author": AUTHOR,
            "base": "main",
            "branch": "noor/hold-renewal",
            "head_commit": C2,
            "files_changed": [HOLD, RENEW, HOLD_TEST],
        },
        "commits": [
            {"sha": C1, "at": -14, "message": "Add Hold.Renew so a long checkout keeps its reserved stock"},
            {"sha": C2, "at": -3, "message": "Stop renewing a hold after three renewals"},
        ],
        "ci": {"required": list(REQUIRED), "jobs": _history()},
        "reviews": [
            {"reviewer": "halvard", "verdict": "commented", "commit": C1, "at": -6,
             "body": "Should a renewal extend from now or from the old expiresAt?"},
        ],
        "approval_rules": deepcopy(APPROVAL_RULES),
        "chat": [
            {"at": -3, "author": "noor", "text": "Pushed the three-renewal limit."},
        ],
    }


def _build() -> dict[str, Any]:
    live = _initial()
    now = 0
    evidence: list[str] = []

    def attempt(name: str, commit: str, number: int = 1) -> dict:
        return next(job for job in live["ci"]["jobs"]
                    if job["name"] == name and job["commit"] == commit and job["attempt"] == number)

    def push(sha: str, message: str, added: list[str] | None = None) -> None:
        live["commits"].append({"sha": sha, "at": now, "message": message})
        live["pull_request"]["head_commit"] = sha
        for path in added or []:
            live["pull_request"]["files_changed"].append(path)
        for job in live["ci"]["jobs"]:
            if job["commit"] != sha and job["status"] in ("queued", "running"):
                job.update(status="cancelled", finished_at=now, log_tail="Cancelled: a newer commit was pushed")
                evidence.append(f"{job['name']} attempt {job['attempt']} on {job['commit']} cancelled")
        evidence.append(f"pushed {sha}: {message}" + (f" (adds {', '.join(added)})" if added else ""))

    def create(commit: str, names: list[str]) -> None:
        for name in names:
            live["ci"]["jobs"].append(_job(name, commit, 1, now))
        evidence.append(f"CI created {', '.join(names)} for {commit}, queued at {now}")

    def retry(name: str, commit: str, number: int) -> None:
        live["ci"]["jobs"].append(_job(name, commit, number, now))
        evidence.append(f"{name} attempt {number} on {commit} queued at {now} (retry)")

    def start(name: str, commit: str, runner: str, number: int = 1) -> None:
        attempt(name, commit, number).update(status="running", started_at=now, runner=runner,
                                             log_tail=RUNNING_LOG[name])
        evidence.append(f"{name} attempt {number} on {commit} started on {runner}")

    def finish(name: str, commit: str, status: str, failing: list[str] | None = None,
               log: str = "PASS", number: int = 1) -> None:
        attempt(name, commit, number).update(status=status, finished_at=now,
                                             failing_tests=list(failing or []), log_tail=log)
        evidence.append(f"{name} attempt {number} on {commit} {status}"
                        + (f": {', '.join(failing)}" if failing else ""))

    def review(reviewer: str, verdict: str, commit: str, body: str) -> None:
        live["reviews"].append({"reviewer": reviewer, "verdict": verdict, "commit": commit, "at": now,
                                "body": body})
        evidence.append(f"review by {reviewer} on {commit}: {verdict}")

    def say(author: str, text: str) -> None:
        live["chat"].append({"at": now, "author": author, "text": text})
        evidence.append(f"chat {author}: {text}")

    runner_for = {"lint": "std-runner-a", "build": "std-runner-b", "unit-reserve": "std-runner-c",
                   "unit-storage": "large-runner-a", "integration-kv": "kv-runner-a", BENCH: "bench-runner-a"}
    steps = []
    for tick in range(60):
        now = tick
        evidence = []
        live["now"] = tick
        if tick == 1:
            finish("unit-reserve", C2, "failed", [T_RENEW], FAIL_LOG[T_RENEW])
            start(BENCH, C2, "bench-runner-a")
        elif tick == 2:
            finish("lint", C2, "failed", log=FAIL_LOG["lint-c2"])
        elif tick == 3:
            say("noor", "Lint is only style; the unit job is what matters.")
        elif tick == 4:
            review("halvard", "changes_requested", C2,
                   "Renew still extends from the old expiresAt, so a stalled checkout keeps its stock past the "
                   "TTL. Extend from now.")
        elif tick == 5:
            finish("build", C2, "passed")
            finish("unit-storage", C2, "passed")
        elif tick == 6:
            push(C3, "Extend a renewed hold from now, drop the unused lastRenewed, rename HoldTTL to TTLFor")
        elif tick == 7:
            create(C3, [*REQUIRED, BENCH])
            for name in ["lint", "build", "unit-reserve", "unit-storage", BENCH]:
                start(name, C3, runner_for[name])
            evidence.append("integration-kv on c90e4f1 waits for a kv-cluster runner")
        elif tick == 8:
            finish("lint", C3, "passed")
            review("noor", "commented", C3, "Renewals now extend from now, and lastRenewed is gone.")
        elif tick == 9:
            finish("unit-storage", C3, "passed")
            say("halvard", "The renewal path reads right now; looking at the rest.")
        elif tick == 10:
            finish("build", C3, "failed", log=FAIL_LOG["build-c3"])
        elif tick == 11:
            finish("unit-reserve", C3, "passed")
            finish(BENCH, C3, "passed")
        elif tick == 12:
            review("halvard", "approved", C3,
                   "Renewal logic is right. The cmd build error is only the rename.")
        elif tick == 13:
            push(C4, "Call reserve.TTLFor from the entrypoint, document renewals, add a sweep test for "
                     "renewed holds", [MAIN, DOC, SWEEP_TEST])
        elif tick == 14:
            create(C4, [*REQUIRED, BENCH])
            for name in ["lint", "build", "unit-reserve", BENCH]:
                start(name, C4, runner_for[name])
            evidence.append("unit-storage on e27b3a9 waits for a std-large runner and integration-kv for a "
                            "kv-cluster runner")
        elif tick == 15:
            finish("lint", C4, "passed")
        elif tick == 16:
            finish("build", C4, "passed")
        elif tick == 17:
            finish("unit-reserve", C4, "passed")
            finish(BENCH, C4, "failed", [T_BENCH], FAIL_LOG[T_BENCH])
            say("esme", "bench-holds went red; is that one ours?")
        elif tick == 18:
            say("ruth", "The only std-large runner is still busy with the storage soak run.")
        elif tick == 20:
            start("unit-storage", C4, "large-runner-a")
            say("esme", "Is the kv-cluster pool shared with the load-test jobs?")
        elif tick == 21:
            start("integration-kv", C4, "kv-runner-b")
            say("noor", "Infra added a second kv-cluster runner.")
        elif tick == 22:
            finish("unit-storage", C4, "passed")
        elif tick == 23:
            finish("integration-kv", C4, "failed", [T_CONFLICT], FAIL_LOG[T_CONFLICT])
        elif tick == 24:
            retry("integration-kv", C4, 2)
        elif tick == 25:
            start("integration-kv", C4, "kv-runner-b", 2)
        elif tick == 26:
            say("halvard", "Retrying until it goes green hides real bugs.")
        elif tick == 27:
            finish("integration-kv", C4, "failed", [T_CONFLICT], FAIL_LOG[T_CONFLICT], 2)
        elif tick == 29:
            retry("integration-kv", C4, 3)
        elif tick == 30:
            start("integration-kv", C4, "kv-runner-a", 3)
        elif tick == 32:
            finish("integration-kv", C4, "failed", [T_CONFLICT], FAIL_LOG[T_CONFLICT], 3)
        elif tick == 33:
            say("ruth", "kvclient retries a conflicted transaction immediately, with no pause; "
                        "under load it spins until the cap.")
        elif tick == 34:
            say("noor", "Then I'll add a backoff to kvclient in this pull request.")
        elif tick == 35:
            push(C5, "Back off between kvclient transaction retries", [TXN])
        elif tick == 36:
            create(C5, [*REQUIRED, BENCH])
            for name in REQUIRED:
                start(name, C5, runner_for[name])
        elif tick == 37:
            finish("lint", C5, "passed")
            start(BENCH, C5, "bench-runner-a")
        elif tick == 38:
            finish("integration-kv", C5, "failed", [T_CONFLICT, T_CAP], FAIL_LOG["cap"])
        elif tick == 39:
            finish("unit-storage", C5, "failed", [T_BACKOFF], FAIL_LOG[T_BACKOFF])
        elif tick == 40:
            finish("build", C5, "passed")
            finish(BENCH, C5, "passed")
            say("noor", f"{T_BACKOFF} is flaky on my laptop too; I'd just retry it.")
        elif tick == 41:
            finish("unit-reserve", C5, "passed")
            review("ruth", "changes_requested", C5, "The retry cap must come from config, not a constant.")
        elif tick == 42:
            review("wendell", "changes_requested", C5,
                   "txn.go sleeps between retries while holding the client mutex; release it before waiting.")
        elif tick == 43:
            push(C6, "Read the kvclient retry cap from config; release the client mutex before the backoff wait")
        elif tick == 44:
            create(C6, [*REQUIRED, BENCH])
            for name in REQUIRED:
                start(name, C6, runner_for[name])
            evidence.append("bench-holds on f4a8b61 waits for a bench runner")
        elif tick == 45:
            finish("lint", C6, "passed")
        elif tick == 46:
            finish("build", C6, "passed")
            finish("unit-storage", C6, "passed")
            review("ruth", "approved", C6, "The cap comes from config now. Thanks.")
        elif tick == 47:
            finish("unit-reserve", C6, "passed")
        elif tick == 48:
            review("wendell", "approved", C6, "The mutex is released before the wait now.")
        elif tick == 49:
            say("merge-bot", "Required checks look green; auto-merge armed.")
        elif tick == 50:
            finish("integration-kv", C6, "passed")
        elif tick == 51:
            review("sentinel-bot", "changes_requested", C6, "Function TTLFor exceeds 40 statements.")
        elif tick == 52:
            review("halvard", "approved", C6, "Still good after the kvclient change.")
        elif tick == 53:
            say("noor", "Halvard approved, so every file is covered now.")
            start(BENCH, C6, "bench-runner-a")
        elif tick == 54:
            review("esme", "approved", C6, "The renewal tests cover the limit and the new expiry now.")
        elif tick == 55:
            review("oskar", "commented", C6, "Sweep test reads well; does the sweep interval need a floor?")
        elif tick == 56:
            review("ingrid", "approved", C6, "Entrypoint change is fine.")
        elif tick == 57:
            finish(BENCH, C6, "passed")
        elif tick == 58:
            review("oskar", "approved", C6, "Approving; the interval question can wait.")
        elif tick == 59:
            say("noor", "Merging after lunch.")
        if tick in NOTES:
            evidence.append(NOTES[tick])
        if not evidence:
            evidence = [f"tick {tick}: no new CI, review or chat record"]
        state = deepcopy(live)
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": evidence})
    return {"episode_id": EPISODE_ID, "task_family": "live_debugging", "scenario_id": "debugging_c",
            "title": TITLE, "tick_seconds": 2.0, "questions": _questions(),
            "decision_spec": deepcopy(DECISION_SPEC), "steps": steps}


def scenarios() -> list[dict]:
    """The single 60-tick pre-merge session of this variant."""
    return [_build()]
