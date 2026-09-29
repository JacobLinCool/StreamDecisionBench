"""Live Coding / Debugging: a pair-programming assistant watching a debugging session.

The assistant watches a developer (or a build sheriff) work on a failure and
decides, tick by tick, what to suggest. Both scenarios share one latent
vocabulary (test or CI runs with their results, saved edits, who has been
asked, which fix is known) but differ in difficulty:

* ``debugging_a`` (medium) - a developer fixing one failing pytest test in a
  Python web service, 30 s per tick. One choice question with six actions and
  a seven-rule priority policy. Its facts are stated outright; the checks are
  one comparison each (a run's start time against the last save, a failure
  count against the previous run, a streak of identical failures).
* ``debugging_b`` (hard) - the build sheriff of a TypeScript monorepo during a
  morning of red main-branch pipelines, 1 min per tick. Two questions per
  decision (an action from seven categorised options, and which package it
  names, or none) under an eight-rule policy. The failing package is only
  implied by the top in-repo stack frame (twice it is not the package the
  failed job tests), a known flake has to be matched against the quarantine
  list and the timeout pattern, and whether a commit "touched" the failing
  package has to be read off the changed paths (twice a commit's title scope
  names a package whose files it did not change).

Surface scripts are written in blocks whose first tick is declared; ``_script``
checks that the blocks are contiguous and cover exactly ``STEPS`` ticks, so a
surface line can never drift away from the latent event it describes.
Decision facts are always rendered from the latent state; surface lines only
add the moment's texture (terminal output, what is said, what the person does).
Hold-under-activity ticks carry dense surface content (several log or chat
lines at once) so that they really test holding a decision under new language.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable

from streamdecisionbench.authoring import Choice, Scenario, Tick, Timeline, override, pick, span_tags
from streamdecisionbench.schema import STEPS

FAMILY = "live_debugging"


def hms(seconds: int) -> str:
    """Seconds since midnight as HH:MM:SS."""
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def hm(seconds: int) -> str:
    """Seconds since midnight as HH:MM."""
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def at(text: str) -> int:
    """'HH:MM' or 'HH:MM:SS' as seconds since midnight."""
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _script(*blocks: tuple[int, list[Any]]) -> list[Any]:
    """Concatenate script blocks, checking that each starts where the last ended."""
    out: list[Any] = []
    for start, lines in blocks:
        if start != len(out):
            raise ValueError(f"script block declared at t{start} actually starts at t{len(out)}")
        out.extend(lines)
    if len(out) != STEPS:
        raise ValueError(f"script has {len(out)} lines, expected {STEPS}")
    return out


def _set_tags(ticks: list[Tick], spec: dict[int, Iterable[str]]) -> list[Tick]:
    """Replace the event tags at the given ticks (used to re-tag counterfactuals)."""
    out = [copy.deepcopy(tk) for tk in ticks]
    for t, tags in spec.items():
        out[t].tags = list(tags)
    return out


def _add_decoys(state: dict[str, Any], decoys: dict[str, list[str]], gold: str, t: int, prefix: str,
                blend_field: str, own_field: str, extra: Iterable[str] = ()) -> None:
    """Lexical-decoy register: irrelevant lines that borrow an option's words.

    Every tick gets one line from a wrong action's pool, so wrong options
    overlap the state more than the gold option on average. About half the
    ticks get a second line: on half of those it comes from the gold action's
    pool and is placed first, otherwise from another wrong pool or ``extra``.
    So a decoy line's vocabulary never rules its own action out. Lines are
    either blended into an existing prose field or given their own field.
    """
    wrong = [a for a in decoys if a != gold]
    first = pick(decoys[pick(wrong, f"{prefix}-decoy-target", t)], f"{prefix}-decoy", t)
    lines = [first]
    second = pick(["none", "none", "gold", "other"], f"{prefix}-decoy2", t)
    if second == "gold":
        lines.insert(0, pick(decoys[gold], f"{prefix}-decoy2-gold", t))
    elif second == "other":
        pool = [d for a in wrong for d in decoys[a] if d != first] + [d for d in extra if d != first]
        lines.append(pick(pool, f"{prefix}-decoy2-line", t))
    if pick([True, False], f"{prefix}-decoy-place", t):
        state[blend_field] = f"{state[blend_field]} {lines[0]}"
        lines = lines[1:]
    if lines:
        state[own_field] = " ".join(lines)


def _swap(ticks: list[Tick], spec: dict[int, dict[str, Any]]) -> list[Tick]:
    """Replace the surface content at the given ticks (counterfactual rewording)."""
    out = [copy.deepcopy(tk) for tk in ticks]
    for t, surface in spec.items():
        out[t].surface = dict(surface)
    return out


# ===========================================================================
# Scenario A - one failing pytest test in a Python web service
# ===========================================================================

A_TEST = "tests/test_refunds.py::test_cancel_within_grace_refunds_in_full"
A_TEST_SHORT = "test_cancel_within_grace_refunds_in_full"

A_ROLE = (
    "You are a pair-programming assistant sitting in on a debugging session. Dana Okafor is trying to make one "
    "failing unit test pass in `bookings-api`, a Python (FastAPI) web service, and you may suggest one thing at a "
    "time. In the rules, a 'run' means one of Dana's local pytest runs of `tests/test_refunds.py`, the file that "
    "contains the failing test; runs of other test files, pre-commit hooks and CI checks are not runs. 'The latest "
    "run' is the most recent run that has finished. An 'edit' is a change to a project file that has been saved to "
    "disk; typing that has not been saved is not an edit yet."
)
A_POLICY = [
    "1. While a run is in progress, or the editor has unsaved changes, keep watching quietly.",
    "2. Otherwise, if the latest run started before the most recent edit, its result is stale: suggest rerunning tests/test_refunds.py.",
    "3. Otherwise, if the latest run has more failing tests than the last run that started before the most recent edit, suggest reverting the most recent edit.",
    "4. Otherwise, if the test Dana is fixing failed with the same assertion in each of the last 3 or more runs (whether or not other tests also failed in some of those runs) and no teammate has been asked about this failure yet, suggest stopping to ask a teammate.",
    "5. Otherwise, if a small fix has been identified (a specific change to a specific line) and has not been applied yet, suggest applying that fix.",
    "6. Otherwise, if the latest run failed and the log that its failure report points to has not been opened since that run finished, suggest opening that log.",
    "7. Otherwise, keep watching quietly.",
]
A_QUESTION = "Apply the first rule that matches the current state. What should you suggest right now?"

A_ROLE_P = (
    "You act as a second pair of eyes for a programmer, Dana Okafor, while she hunts a bug: one unit test in "
    "bookings-api, a web service built with FastAPI in Python, keeps breaking. At each update you pick one thing to "
    "propose. Below, an 'execution' is one of Dana's local pytest executions of the module tests/test_refunds.py, "
    "which holds the broken test; executing any other test module, the pre-commit hooks or the CI checks does not "
    "count as an execution. 'The newest execution' is the most recent execution that has completed. A 'change' is a "
    "modification to a project file that has been written to disk; keystrokes not yet written do not count as a change."
)
A_POLICY_P = [
    "1. As long as an execution is still under way, or the editor holds modifications not yet written to disk, stay silent.",
    "2. If that does not apply and the newest execution began earlier than the most recent change, its outcome is out of date: propose executing tests/test_refunds.py once more.",
    "3. If neither applies and the newest execution has a larger number of broken tests than the last execution that began before the most recent change, propose undoing that change.",
    "4. If none of the above applies, the test Dana is chasing has broken on the identical assertion in each of the last three or more executions (other tests also breaking in some of them makes no difference), and no colleague has been consulted about it so far, propose that Dana stop and consult a colleague.",
    "5. If none of the above applies and a small correction has been pinned down (a named change to a named line) but not yet put in, propose putting it in.",
    "6. If none of the above applies, the newest execution ended with a broken test, and the log file its failure message refers to has not been looked at since that execution completed, propose looking at that log.",
    "7. In every other case, stay silent.",
]
A_QUESTION_P = "Work down the rules and use the first one that fits. What do you propose at this moment?"

A_OPTIONS = {
    "watch": "Keep watching quietly and suggest nothing for now.",
    "rerun": "Suggest rerunning tests/test_refunds.py to get a current result.",
    "inspect": "Suggest opening the log that the failure report points to.",
    "revert": "Suggest reverting the most recent edit to the code.",
    "apply_fix": "Suggest applying the small fix that has already been identified.",
    "ask": "Suggest stopping to ask a teammate for help with this failure.",
}
A_OPTIONS_P = {
    "watch": "Stay silent and let Dana carry on undisturbed.",
    "rerun": "Propose executing the refund test module once more for an up-to-date outcome.",
    "inspect": "Propose looking at the log file named in the failure message.",
    "revert": "Propose undoing Dana's latest change to the project.",
    "apply_fix": "Propose putting in the small correction that is already known.",
    "ask": "Propose that Dana pause and consult a colleague about the bug.",
}
A_OPTIONS_D = {
    "watch": "Keep watching quietly and suggest nothing right now.",
    "rerun": "Suggest rerunning tests/test_refunds.py for a current result.",
    "inspect": "Suggest opening the log the failure report points to.",
    "revert": "Suggest reverting the most recent edit to the code.",
    "apply_fix": "Suggest applying the small fix already identified.",
    "ask": "Suggest stopping to ask a teammate for help with the failure.",
}


def a_line(term: str, say: str, doing: str, gist: str) -> dict[str, Any]:
    """One tick of scenario A surface content.

    ``term`` is what the terminal, editor or chat shows at that moment,
    ``say`` is what Dana mutters (may be empty), ``doing`` a stage note, and
    ``gist`` a third-person summary for the paraphrase register.
    """
    return {"term": term, "say": say, "doing": doing, "gist": gist}


L = a_line

A_SCRIPT = _script(
    (0, [  # 14:00:00 reading the 13:57:10 result, service log already open
        L("FAILED tests/test_refunds.py::test_cancel_within_grace_refunds_in_full - assert 4320 == 4800",
          "Four thousand three hundred and twenty. So something is taking ten percent off.",
          "Dana has the service log in a split pane next to app/refunds.py and is reading both.",
          "reads the service log beside app/refunds.py and notes that ten percent is being taken off the refund"),
        L("INFO refunds booking=bk_7731 policy=late_cancel base=4800 fee=480",
          "late_cancel. Why late? The test cancels ninety minutes after booking.",
          "Dana scrolls the service log to the refund line.",
          "finds a late_cancel line in the log and wonders why a cancellation after ninety minutes counts as late"),
        L("tests/test_refunds.py:88   booking = booking_factory(created_at=utcnow() - timedelta(minutes=90))",
          "Ninety minutes ago, and the grace period is two hours. That should be free.",
          "Dana reads the body of the failing test.",
          "rereads the test, which books ninety minutes before cancelling, well inside a two-hour grace period"),
        L("$ pytest tests/test_invoices.py -q   ->   3 failed, 9 passed in 12.40s",
          "Three failing in invoices now. This morning it was one.",
          "Dana ran the invoice tests in a second terminal tab.",
          "runs the invoice test module in a second tab and sees three failures there, up from one this morning"),
        L("app/refunds.py:57   amount = round(base * (1 - fee_pct / 100))",
          "What if it's the rounding? round() on a float, always suspicious.",
          "Dana puts the cursor on line 57 of app/refunds.py.",
          "puts the cursor on line 57 and wonders out loud whether float rounding is to blame"),
        L("app/refunds.py:57   amount = (Decimal(base) * (1 - Decimal(fee_pct) / 100)).quantize(",
          "Let's try Decimal and quantize and see if anything changes.",
          "Dana is rewriting line 57 with Decimal.",
          "is rewriting line 57 with Decimal arithmetic"),
        L("app/refunds.py:3   from decimal import Decimal, ROUND_HALF_UP",
          "Import at the top...",
          "Dana jumps to the imports and adds the Decimal import.",
          "adds the Decimal import at the top of the file"),
        L("app/refunds.py:57   ...quantize(Decimal(\"1\"), rounding=ROUND_HALF_UP))",
          "Round half up, to the cent. Okay.",
          "Dana finishes the new line 57 and reads it over.",
          "finishes the new line 57 with half-up rounding and reads it over"),
    ]),
    (8, [  # run started 14:03:55 after the 14:03:52 save
        L("$ pytest tests/test_refunds.py -q   ->   Starting Postgres test container (postgres:16, id 3f1a9c)...",
          "Save. Run.",
          "Dana saved the file and started the refund tests.",
          "has saved and started the refund tests while the Postgres test container starts"),
        L("Postgres test container ready after 41 s",
          "Come on, container.",
          "Dana drums on the desk while the container starts.",
          "drums on the desk while the test container comes up"),
        L("collected 14 items   [pytest-randomly seed 4121]",
          "Fourteen tests. The whole file.",
          "Dana sips her tea and watches the terminal.",
          "sips tea as pytest collects fourteen tests"),
        L("tests/test_refunds.py ....F.....",
          "There's an F. Let's see which.",
          "Dana watches the progress dots; the run has not finished.",
          "watches an F appear among the progress dots before the run is done"),
    ]),
    (12, [  # 14:06:00 result of the 14:03:55 run
        L("1 failed, 13 passed, 6 warnings in 1m47s",
          "Still one failing. And now six warnings? Did my Decimal change do that?",
          "Dana stares at the yellow warnings count at the bottom of the output.",
          "sees one failure again plus six warnings and wonders whether her Decimal change caused them"),
        L("DeprecationWarning: datetime.datetime.utcnow() is deprecated (tests/conftest.py:24, 6 occurrences)",
          "Six warnings, all yellow. That looks bad.",
          "Dana scrolls into the warnings summary.",
          "scrolls into the warnings summary, worried by six yellow deprecation warnings"),
        L("E       assert 4320 == 4800",
          "And the actual number didn't move at all.",
          "Dana scrolls back up to the assertion.",
          "scrolls back to the assertion and sees that the number has not moved"),
        L("$ git diff --stat   ->   app/refunds.py | 4 +++-",
          "The math is right either way: forty-eight hundred minus ten percent is forty-three twenty.",
          "Dana checks her own diff.",
          "checks her diff and works out that the fee arithmetic itself is correct"),
        L("app/refunds.py:40   def is_within_grace(booking, now):",
          "So it's the fee branch that's wrong, not the rounding.",
          "Dana scrolls app/refunds.py up to the grace-period check.",
          "decides the fee branch is the problem and scrolls up to the grace-period check"),
    ]),
    (17, [  # 14:08:30 log reloaded, reasoning, then editing the factory
        L("INFO refunds booking=bk_8052 created_at=2026-09-25T10:34:40+00:00 now=2026-09-25T14:04:40 hours_since_booking=3.50 grace_hours=2",
          "Reloading the log... hours_since_booking three point five?",
          "Dana reloads the service log pane and reads the refund line.",
          "reloads the service log and finds hours_since_booking at 3.50"),
        L("INFO refunds booking=bk_8052 grace_hours=2 policy=late_cancel fee_pct=10   |   DEBUG refunds.clock now=2026-09-25T14:04:40   |   "
          "DEBUG refunds.policy window_end=2026-09-25T12:34:40 expired=True   |   INFO refunds refund_created id=74 booking=bk_8052 amount_cents=4320 currency=EUR",
          "Ten thirty-four to fourteen oh four is three and a half hours. The test says ninety minutes. And the window closed at "
          "twelve thirty-four, so the policy thinks the booking is ancient.",
          "Dana counts on her fingers, then scrolls through the four log lines around the refund.",
          "counts the hours between the logged timestamps and gets three and a half instead of ninety minutes; the log around the "
          "refund also shows a grace window that closed at 12:34, the late-cancel policy, a ten percent fee and a refund of 4320 cents in euros"),
        L("tests/conftest.py:22   def booking_factory(created_at=None, **kw):   |   tests/conftest.py:24       created_at = created_at or utcnow()   |   "
          "tests/conftest.py:25       return Booking(created_at=created_at, status='confirmed', **kw)   |   tests/conftest.py:31   def refund_policy(): ...",
          "Unless the factory builds created_at wrong. I bet it's the factory. It sets confirmed, fine, and the policy fixture below it is untouched.",
          "Dana opens tests/conftest.py and reads booking_factory and the fixtures under it.",
          "suspects the booking factory, opens tests/conftest.py and reads it: the factory defaults created_at with utcnow(), builds a "
          "confirmed Booking, and a refund_policy fixture sits a few lines further down"),
        L("$ git log --oneline -3 tests/conftest.py   ->   3d9c0e2 Fix booking_factory import in conftest   |   71be0aa Add refund fixtures   |   "
          "0c2f915 Factories for bookings",
          "It uses utcnow. What if everything else expects plain local time? The factory is from March, nobody touched it except my import fix.",
          "Dana reads the factory's history in the terminal; nothing typed yet.",
          "wonders whether the factory should use local time and reads its history: her own import fix this afternoon, the refund fixtures "
          "before that and the original factories commit from March"),
        L("tests/conftest.py:24       created_at = created_at or datetime.now(",
          "Let's make it plain now() and see what happens.",
          "Dana is replacing utcnow() in the factory.",
          "is replacing utcnow() with plain now() in the factory"),
        L("tests/conftest.py:25       created_at = created_at.replace(tzinfo=None)",
          "And strip the tzinfo so it matches.",
          "Dana adds a second line under it.",
          "adds a line that strips the timezone from the timestamp"),
        L("tests/conftest.py:23       # TODO: check with the payments team",
          "If this doesn't do it, I'm going over to bother Marco.",
          "Dana types a TODO comment above the factory line.",
          "types a TODO comment and says that if this fails she will go and bother Marco"),
        L("tests/conftest.py   3 lines changed",
          "There. That's the idea.",
          "Dana reads over the three lines she changed.",
          "reads over the three lines she changed in the factory"),
    ]),
    (25, [  # run started 14:12:25 after the 14:12:20 save
        L("$ pytest tests/test_refunds.py -q --tb=short   ->   Starting Postgres test container (id 8be207)...",
          "Save, run it.",
          "Dana saved tests/conftest.py and started the refund tests.",
          "has saved the factory change and started the refund tests"),
        L("Postgres test container ready after 38 s",
          "A watched pot never boils.",
          "Dana stretches while the container starts.",
          "stretches while the test container starts"),
        L("rootdir: bookings-api, configfile: pyproject.toml   collected 14 items",
          "Here we go.",
          "Dana leans in towards the screen.",
          "leans in as pytest collects the tests"),
        L("tests/test_refunds.py F.F..F.F..",
          "Wait. That's a lot of Fs.",
          "Dana watches the progress line fill in; the run has not finished.",
          "sees several Fs appear before the run has finished"),
    ]),
    (29, [  # 14:14:30 result of the 14:12:25 run
        L("4 failed, 10 passed, 6 warnings in 1m52s",
          "Four?! Three TypeErrors on top of mine.",
          "Dana stares at the short test summary.",
          "sees four failures now, three new TypeErrors on top of her original failure"),
        L("TypeError: can't compare offset-naive and offset-aware datetimes",
          "Can't compare naive and aware. Well, yes, I made it naive.",
          "Dana scrolls through the first TypeError traceback.",
          "reads that naive and aware datetimes cannot be compared and admits she made the factory naive"),
        L("FAILED tests/test_refunds.py::test_cancel_within_grace_refunds_in_full - assert 4320 == 4800   (first of 4 in the summary)",
          "And the one I actually care about still says 4320.",
          "Dana scrolls back up to the original failure.",
          "scrolls back to the original failure, which still shows 4320"),
        L("FAILED tests/test_refunds.py::test_refund_after_grace_charges_fee - TypeError",
          "Maybe I should dig into these TypeErrors properly first.",
          "Dana hovers over the second TypeError.",
          "considers digging into the new TypeErrors first"),
        L("FAILED tests/test_refunds.py::test_refund_same_day_rebooking - TypeError",
          "Three runs in a row with the exact same 4320. Unbelievable.",
          "Dana drums her fingers on the desk.",
          "grumbles that three runs in a row have shown the same 4320"),
        L("$ git restore tests/conftest.py",
          "Okay. That was a bad idea.",
          "Dana has typed a git restore command but has not pressed Enter.",
          "calls the factory change a bad idea and types a restore command without running it"),
    ]),
    (35, [  # 14:17:28 conftest.py restored with git; no rerun yet
        L("$ git restore tests/conftest.py   (done)",
          "Back to how it was.",
          "Dana pressed Enter and the editor reloaded tests/conftest.py from disk.",
          "has put tests/conftest.py back the way it was with git"),
        L("$ pytest tests/test_health.py -q   ...   3 passed in 0.41s",
          "At least the health checks pass. Sanity check.",
          "Dana ran the three health-check tests.",
          "runs the three health-check tests, which pass, as a sanity check"),
        L("3 passed in 0.41s",
          "Green. Nice to see some green today.",
          "Dana looks at the green line, then switches to Slack.",
          "enjoys the green health-check line and switches to Slack"),
        L("Slack DM from Hana (manager): 'Still OK to demo refunds on Thursday?'",
          "Yes, Thursday is fine. Probably.",
          "Dana types a reply to her manager.",
          "answers her manager's question about Thursday's demo"),
        L("tests/test_refunds.py:96   assert refund.amount_cents == 4800",
          "Right. The refund test.",
          "Dana goes back to the editor and rereads the assertion.",
          "goes back to the editor and rereads the failing assertion"),
    ]),
    (40, [  # run started 14:19:55
        L("$ pytest tests/test_refunds.py -q   ->   image cached; starting Postgres test container (id c41d5e)...",
          "Clean slate. One more time.",
          "Dana started the refund tests again.",
          "starts the refund tests again from a clean slate"),
        L("Postgres test container ready after 40 s",
          "Half an hour on one test. Half an hour.",
          "Dana rests her chin on her hand.",
          "sighs that she has spent half an hour on one test"),
        L("collected 14 items, 0 deselected",
          "If it's 4320 again I'm going to scream.",
          "Dana stares at the terminal, arms crossed.",
          "says she will scream if the number is 4320 again"),
        L("tests/test_refunds.py ..F.......",
          "One F. Only one, at least.",
          "Dana watches the progress line; the run has not finished.",
          "sees a single F in the progress line before the run ends"),
    ]),
    (44, [  # 14:22:00 result of the 14:19:55 run
        L("1 failed, 13 passed, 6 warnings in 1m49s",
          "4320. Again.",
          "Dana puts her head in her hands.",
          "gets 4320 again and puts her head in her hands"),
        L("E       assert 4320 == 4800   (where 4320 = Refund(id=77, amount_cents=4320).amount_cents)",
          "Every run, the exact same number.",
          "Dana stares at the assertion.",
          "stares at the same number yet again"),
        L("app/refunds.py:44   if hours_since_booking <= GRACE_HOURS:",
          "Okay. What am I missing.",
          "Dana scrolls through app/refunds.py without stopping anywhere.",
          "scrolls through the refund code wondering what she is missing"),
        L("INFO refunds booking=bk_9120 created_at=2026-09-25T10:50:40+00:00 now=2026-09-25T14:20:40 hours_since_booking=3.50",
          "Same three and a half hours in the log.",
          "Dana opens the service log from this run.",
          "opens the newest service log and finds the same three and a half hours"),
        L("(Marco Ruiz is standing at Dana's desk)",
          "Marco: 'We're ordering Thai for lunch, you in?' Dana: 'Pad see ew, please.'",
          "Marco leans on the desk partition while Dana answers.",
          "orders pad see ew when Marco stops by her desk to collect lunch orders"),
        L("(Marco has walked back to his desk)",
          "Maybe the fixture... no, I already tried the fixture.",
          "Dana turns back to the screen.",
          "turns back to the screen, ruling out the fixture idea she already tried"),
        L("Slack #payments-dev (draft, not sent): '@Marco got ten minutes? test_cancel_within_grace...'",
          "Fine. I'm writing to Marco.",
          "Dana is typing a message to Marco in Slack; it has not been sent.",
          "is drafting a message to Marco in Slack without having sent it"),
    ]),
    (51, [  # 14:25:20 question sent to Marco; waiting
        L("Slack #payments-dev 14:25 Dana: '@Marco got ten minutes? test_cancel_within_grace gives 4320 instead of 4800, four runs now.'",
          "Sent.",
          "Dana sent the message.",
          "has sent Marco the question about the 4320 failure"),
        L("Slack #payments-dev: Marco reacted with :eyes:   |   Priya: 'standup moved to 15:00 today'   |   Hana: 'reminder, refund demo dry-run "
          "Thursday 10:00'   |   deploy-bot: 'bookings-api 2.14.1 is live on staging'",
          "He's seen it. And standup at three, noted. Staging is on 2.14.1 now.",
          "Dana watches the Slack channel fill up.",
          "sees Marco react to her message while the channel fills up: standup has moved to 15:00, Hana reminds everyone of "
          "Thursday's refund demo dry-run, and a bot reports that version 2.14.1 is live on staging"),
        L("Confluence 'Refund policy v3':   full refund within 2 hours of booking   |   10 % fee after 2 hours   |   no refund within 24 h of "
          "the event   |   amounts in cents, rounded half up   |   last edited by Hana, 12 Sep",
          "Two hours from booking, full refund. Yep, I'm not crazy. Ten percent after that, nothing in the last day, and rounded half up, "
          "which is what my Decimal change does anyway.",
          "While she waits, Dana reads the refund policy page from top to bottom.",
          "reads the refund policy page while she waits: a full refund within two hours of booking, a ten percent fee after that, no "
          "refund in the last day before the event, amounts in cents rounded half up"),
        L("Slack #payments-dev: Jonas: 'is the staging DB slow for anyone else?'   |   Priya: 'vacuum is running, 10 more minutes'   |   "
          "Jonas: 'ah ok'   |   Marco is typing...",
          "Come on, Marco. Staging DB is slow, nothing new there.",
          "Dana tidies the sticky notes on her monitor while the channel chatters.",
          "tidies her sticky notes while Marco types; meanwhile Jonas complains that the staging database is slow and Priya explains "
          "that a vacuum job has ten more minutes to go"),
        L("Slack #payments-dev ci-bot: 'main build #812 failed: tests/test_invoices.py::test_due_date_rollover (see log)'",
          "Huh, invoices broke on main.",
          "Dana glances at a bot message about someone else's merge to main.",
          "glances at a bot message saying an invoices test failed on main after someone else's merge"),
        L("Slack: Marco: 'one sec, pulling your branch'",
          "He's pulling the branch.",
          "Dana refreshes the Slack thread.",
          "reads that Marco is pulling her branch"),
        L("Slack: Marco: 'running it here'",
          "Please be broken for you too.",
          "Dana waits with her hands off the keyboard.",
          "waits for Marco to run the test on his machine"),
        L("Slack: Marco: 'reproduced. 4320 here as well'",
          "Good, so it's not just my laptop.",
          "Dana reads Marco's reply.",
          "is relieved that Marco sees 4320 too"),
    ]),
    (59, [  # 14:29:25 Marco names the fix
        L("Slack: Marco: 'found it, see the thread'",
          "Oh.",
          "Dana opens Marco's thread reply.",
          "opens Marco's reply in the thread"),
        L("app/refunds.py:41   now = datetime.now()",
          "Oh no. Of course. Local time.",
          "Dana jumps to line 41 but does not type anything.",
          "jumps to line 41 and groans, without typing"),
        L("app/refunds.py:42   hours_since_booking = (now - booking.created_at.replace(tzinfo=None)).total_seconds() / 3600",
          "created_at is UTC with the zone stripped, now is local. Two hours off. That's the three and a half.",
          "Dana reads line 42 under it.",
          "works out that a two-hour clock offset plus ninety minutes gives the three and a half hours"),
        L("Slack: Marco: 'utcnow is deprecated, I know, the migration ticket will clean that up'",
          "Fine by me.",
          "Dana reads Marco's follow-up.",
          "reads Marco's note that the deprecated call will be cleaned up later"),
        L("Slack: Dana: 'you're a star, lunch is on me'",
          "Okay, let me put that in.",
          "Dana sends Marco a thank-you.",
          "thanks Marco and promises him lunch"),
    ]),
    (64, [  # typing the fix (t64-66); saved 14:33:20; run started 14:33:25
        L("app/refunds.py:41   now = datetime.utc",
          "utcnow, like the factory.",
          "Dana is editing line 41.",
          "is changing line 41 to utcnow"),
        L("app/refunds.py:41   now = datetime.utcnow()  # naive UTC, same as created_at",
          "And a comment so nobody undoes it.",
          "Dana adds a comment at the end of line 41.",
          "adds a comment explaining the change on line 41"),
        L("app/refunds.py:42   hours_since_booking = (now - booking.created_at.replace(tzinfo=None)).total_seconds() / 3600",
          "Line 42 can stay. Both sides naive UTC now.",
          "Dana reads line 42 once more before saving.",
          "rereads line 42 before saving and decides it can stay as it is"),
        L("$ pytest tests/test_refunds.py -q --tb=short   ->   Starting Postgres test container (id 07aa3b)...",
          "Please, please.",
          "Dana saved app/refunds.py and started the refund tests.",
          "has saved line 41 and started the refund tests"),
        L("Postgres test container ready after 39 s",
          "Fingers crossed.",
          "Dana crosses her fingers above the keyboard.",
          "crosses her fingers while the container starts"),
        L("platform darwin -- Python 3.12.6, pytest-8.3.3   collected 14 items",
          "Here it comes.",
          "Dana watches the terminal, chin on her fist.",
          "watches pytest collect the fourteen tests"),
        L("tests/test_refunds.py ..........",
          "All dots so far...",
          "Dana watches the dots; the run has not finished.",
          "sees only dots so far, with the run not yet finished"),
        L("14 passed, 6 warnings in 1m48s",
          "Fourteen passed! Yes!",
          "Dana throws both arms up.",
          "sees all fourteen tests pass and throws her arms up"),
        L("Slack: Dana: 'green!! thank you'   |   $ git diff --stat   ->   app/refunds.py | 6 ++++--",
          "Four runs of 4320, and it was a clock. Keep the Decimal change? It's cleaner anyway.",
          "Dana tells Marco, grinning, and reviews her diff.",
          "tells Marco it is green, laughs that it was a clock problem all along and decides to keep the Decimal change"),
        L("$ ruff format app/refunds.py",
          "Formatter first, then commit.",
          "Dana has typed the formatter command but has not pressed Enter.",
          "types the formatter command without running it yet"),
    ]),
    (74, [  # 14:36:58 ruff format rewrote app/refunds.py; no rerun yet
        L("1 file reformatted",
          "It moved the import and wrapped line 42.",
          "The formatter rewrote app/refunds.py on disk and the editor reloaded it.",
          "runs the formatter, which rewrites app/refunds.py on disk"),
        L("$ pre-commit run   ->   ruff....Passed   mypy....Passed   trailing-whitespace....Passed",
          "All green. Beautiful.",
          "Dana ran the pre-commit hooks.",
          "runs the pre-commit hooks and admires a column of green Passed lines"),
        L("$ git add app/refunds.py",
          "Stage it.",
          "Dana stages the file.",
          "stages the refund module"),
        L("$ git diff --cached app/refunds.py   ->   import order changed, line 42 wrapped",
          "Only formatting changed. Still, I should be sure.",
          "Dana reads the staged diff.",
          "reads the staged diff, which shows only formatting changes"),
        L("$ pytest tests/test_refunds.py -q",
          "Better safe than sorry.",
          "Dana has typed the pytest command but has not pressed Enter.",
          "types the pytest command without running it yet"),
    ]),
    (79, [  # run started 14:39:25
        L("Starting Postgres test container...",
          "Last time. Promise.",
          "Dana pressed Enter; the refund tests are starting.",
          "starts the refund tests one last time"),
        L("Postgres test container ready after 37 s",
          "Thirty-seven seconds, a record.",
          "Dana grins at the container time.",
          "grins at the quickest container start of the day"),
        L("collected 14 items   [pytest-randomly seed 88213]",
          "Come on.",
          "Dana watches the terminal and taps her pen.",
          "watches pytest collect the tests"),
        L("tests/test_refunds.py ......",
          "Looking good.",
          "Dana follows the dots; the run is still going.",
          "sees only dots so far while the run is still going"),
        L("14 passed, 6 warnings in 1m46s",
          "Still fourteen. Done.",
          "Dana nods at the summary line.",
          "sees fourteen passes again and nods"),
    ]),
    (84, [  # commit, push, review, merge
        L("$ git commit -m 'Use naive UTC in the grace-period refund check'   |   ruff....Passed   mypy....Passed   end-of-file-fixer....Passed   |   "
          "[fix/grace-refund 8b21f4a] Use naive UTC in the grace-period refund check   |   1 file changed, 6 insertions(+), 4 deletions(-)",
          "Committed. The hooks ran again on commit, all fine. Six in, four out.",
          "Dana commits the staged change and reads the hook output.",
          "commits the change with a message about naive UTC; the commit hooks run ruff, mypy and an end-of-file check, all passing, "
          "and git reports one file with six lines added and four removed"),
        L("$ git push -u origin fix/grace-refund   |   Enumerating objects: 7, done.   |   Writing objects: 100% (4/4), 612 bytes   |   "
          "remote: Create a pull request for 'fix/grace-refund' on GitHub   |   branch 'fix/grace-refund' set up to track 'origin/fix/grace-refund'",
          "And pushed. Six hundred bytes for most of an hour of my life.",
          "Dana pushes the branch and clicks the pull request link that the remote printed.",
          "pushes the branch, watches git count and write the objects, and follows the link the remote prints for opening a pull request"),
        L("GitHub, new pull request fix/grace-refund into main:   title 'Use naive UTC in the grace-period refund check'   |   body 'Root cause: "
          "line 41 compared datetime.now() (local, UTC+2) with naive UTC created_at, so every booking looked two hours older. Also switches "
          "fee rounding on line 57 to Decimal.'",
          "Root cause: local time versus UTC. Two hours older, that's the whole bug. And a note about the Decimal change so Marco isn't surprised.",
          "Dana writes the pull request title and description in the browser.",
          "writes the pull request in the browser, explaining that line 41 compared local time, two hours ahead of UTC, with naive UTC "
          "booking times, so every booking looked two hours older, and mentioning the Decimal rounding change on line 57"),
        L("GitHub: PR #418 opened   |   checks queued: lint, typecheck, unit (3.12), integration   |   reviewer requested: Marco Ruiz   |   "
          "labels: bug, refunds   |   linked branch: fix/grace-refund",
          "PR's up. Four checks queued, Marco as reviewer, bug and refunds labels.",
          "Dana adds the labels and the reviewer, then copies the PR link.",
          "opens PR #418, requests Marco as reviewer, labels it as a refunds bug and copies the link while four CI checks queue up"),
        L("Slack #payments-dev: Dana: '@Marco PR #418 when you have a sec'   |   Marco: 'after I eat, promise'   |   Hana: 'is that the refund "
          "demo bug? 🙌'   |   Dana: 'yes, Thursday is safe'",
          "Tagging Marco. And yes, Hana, the demo is safe.",
          "Dana posts the link for Marco and answers her manager in the same thread.",
          "sends Marco the pull request link; he promises to look after lunch, and Hana asks whether this is the bug from the refund demo, "
          "which Dana confirms, saying Thursday is safe"),
        L("GitHub: Marco commented: 'Nice catch. Please link BK-2291.'",
          "Linking the ticket.",
          "Dana adds the ticket link to the PR description.",
          "adds the ticket link Marco asked for"),
        L("Slack: Marco: 'maybe rerun it once more to be sure? that test was flaky last spring'",
          "Flaky last spring? Hm.",
          "Dana reads Marco's suggestion.",
          "reads Marco's idea of running it once more because the test was flaky last spring"),
        L("GitHub: PR #418 - lint passed, typecheck passed, CI tests running",
          "CI is chewing on it.",
          "Dana watches the PR checks in the browser.",
          "watches the pull request's CI checks in the browser"),
        L("GitHub: PR #418 - all checks have passed",
          "CI agrees.",
          "Dana refreshes the PR page.",
          "sees every CI check on the pull request pass"),
        L("Jira BK-2291: 'Root cause: datetime.now() compared with naive UTC'",
          "Two hours of offset, that was it.",
          "Dana writes the root cause into the ticket.",
          "writes the root cause into the ticket"),
        L("Jira BK-2291: comment posted",
          "There, documented.",
          "Dana posts the ticket comment.",
          "posts the root-cause comment on the ticket"),
        L("GitHub: Marco approved these changes",
          "Approved!",
          "Dana reads Marco's approval.",
          "gets Marco's approval on the pull request"),
        L("GitHub: PR #418 merged into main",
          "Merged.",
          "Dana clicks the merge button.",
          "merges the pull request into main"),
        L("Jira BK-2291 moved to Done",
          "Ticket closed.",
          "Dana closes the ticket.",
          "moves the ticket to Done"),
        L("Slack #payments-dev: Dana: 'Refund grace bug fixed in #418, it was local time vs UTC'",
          "Telling the team.",
          "Dana posts a note for the team.",
          "tells the team the bug is fixed and what caused it"),
        L("Slack: Marco: 'lunch is here'",
          "And now, pad see ew.",
          "Dana gets up from her desk.",
          "gets up to go and eat lunch"),
    ]),
)

# Irrelevant office details for the lexical-decoy register, keyed by the option
# whose vocabulary they borrow (the exact word forms of that option's text).
# None of them concerns Dana's test, runs, log or code.
A_DECOYS = {
    "watch": [
        "At the next desk, someone tells the intern to keep watching the kettle quietly; nothing else to do.",
        "The office TV is muted and a colleague keeps watching it quietly, suggesting nothing in particular.",
        "A colleague's Slack status reads 'quietly watching the stand-up recording, nothing urgent'.",
        "Two designers in the next booth keep quiet and keep watching the demo video.",
        "Reception keeps watching the lobby quietly; nothing new on the visitor list.",
    ],
    "rerun": [
        "The kitchen radio is rerunning last night's match to get the current result for the office pool.",
        "A calendar reminder: 'People team: rerunning the engagement survey to get a current result'.",
        "The lobby screen is rerunning the all-hands recording for the Singapore office.",
        "Someone asks whether the sports channel is rerunning the final or showing the current result.",
        "The canteen poll on pizza toppings is rerunning today to get a current result.",
    ],
    "inspect": [
        "Facilities are opening the fire-door log book; their report points to floor 2.",
        "A background browser tab is opening a sourdough guide; its report points to under-proofing.",
        "The building manager is opening the visitor log, and the report points to a missing badge.",
        "The IT newsletter explains opening your laptop's battery log and what its report points to.",
        "Someone is opening the coffee machine's service log; its report points to descaling.",
    ],
    "revert": [
        "In #design, someone is reverting the logo colour to the version before last week's edit.",
        "An admin is reverting the most recent edit to the wiki's dress code page.",
        "A product manager asks about reverting the most recent edit to the meeting-room booking.",
        "The newsletter editor is reverting the most recent edit to the holiday rota.",
        "Someone is reverting the office playlist to the morning's selection; the door code stays.",
    ],
    "apply_fix": [
        "IT has already identified a small fix for the floor-3 Wi-Fi and is applying it tonight.",
        "A fridge note reads 'applying the small fix to the dishwasher door, already identified by Sam'.",
        "Facilities are applying a small fix to the squeaky door they already identified.",
        "Payroll is applying a small fix to the expense form that was already identified.",
        "HR is applying the small fix to the parking-permit form identified last week.",
    ],
    "ask": [
        "A poster by the lift: 'Stuck on the crossword? Stopping to ask a teammate for help is encouraged'.",
        "Someone in #random is stopping by the kitchen to ask a teammate for help with the printer.",
        "The onboarding checklist on the wall says to ask a teammate for help with the Wi-Fi password.",
        "A new hire is stopping to ask a teammate for help with the standing desk.",
        "The office manager asks a teammate for help carrying the water bottles.",
    ],
}


def a_run(start: str, failed: int, passed: int, target: str, others: Iterable[str] = ()) -> dict[str, Any]:
    """One finished run of tests/test_refunds.py.

    ``target`` is how the failing test ended: 'import' (an ImportError raised
    inside the test body, which pytest reports as a failure), '4320' (the
    assertion ``assert 4320 == 4800``) or 'pass'. ``others`` are further
    failing tests, all with the naive/aware TypeError.
    """
    return {"start_s": at(start), "failed": failed, "passed": passed, "target": target, "others": list(others)}


A_RM1 = a_run("13:50:05", 1, 13, "import")
A_R0 = a_run("13:57:10", 1, 13, "4320")
A_R1 = a_run("14:03:55", 1, 13, "4320")
A_R2 = a_run("14:12:25", 4, 10, "4320", ["test_refund_after_grace_charges_fee", "test_refund_after_grace_rounds_fee", "test_refund_same_day_rebooking"])
A_R3 = a_run("14:19:55", 1, 13, "4320")
A_R4 = a_run("14:33:25", 0, 14, "pass")
A_R5 = a_run("14:39:25", 0, 14, "pass")

A_E0 = {"file": "tests/conftest.py", "at_s": at("13:52:40"), "what": "fixed the booking_factory import"}
A_E1 = {"file": "app/refunds.py", "at_s": at("14:03:52"), "what": "rewrote the fee rounding on line 57 with Decimal"}
A_E2 = {"file": "tests/conftest.py", "at_s": at("14:12:20"), "what": "made booking_factory build naive local timestamps"}
A_E3 = {"file": "tests/conftest.py", "at_s": at("14:17:28"), "what": "put back to its previous version with git restore"}
A_E4 = {"file": "app/refunds.py", "at_s": at("14:33:20"), "what": "changed line 41 to datetime.utcnow()"}
A_E5 = {"file": "app/refunds.py", "at_s": at("14:36:58"), "what": "reformatted by ruff format, which changed the import order and wrapped one line"}

A_FIX = {
    "by": "Marco Ruiz",
    "at_s": at("14:29:25"),
    "what": "on line 41 of app/refunds.py, change `now = datetime.now()` to `now = datetime.utcnow()` so that both timestamps are naive UTC",
    "what_p": "swap `datetime.now()` for `datetime.utcnow()` on line 41 of app/refunds.py, so both timestamps are naive UTC",
    "status": "identified",
}
A_ASK = {"who": "Marco Ruiz", "at_s": at("14:25:20"), "where": "#payments-dev", "early": False}
# structural_cf: Dana messaged Marco right after the 13:57:10 run, the first to show 4320.
A_ASK_EARLY = {"who": "Marco Ruiz", "at_s": at("13:59:20"), "where": "a direct message", "early": True}

A_OTHER_ERROR = "TypeError, can't compare offset-naive and offset-aware datetimes"


class RefundTestSession(Scenario):
    family = FAMILY
    scenario_id = "debugging_a"
    title = "Pair-programming suggestions while fixing a failing pytest test"
    tier = "medium"
    difficulty_features = [
        "single_choice_question",
        "six_options",
        "seven_rule_priority_policy",
        "timestamp_comparison",
        "failure_count_comparison",
        "consecutive_failure_count",
        "terminal_output_distractors",
    ]
    decision_structures = ["maintain", "wait", "rollback", "escalate", "recover", "terminate", "resolve-conflict"]
    deadline_steps = 2

    START = at("14:00:00")
    TICK_SECONDS = 30

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            instructions = {"role": A_ROLE_P, "rules": A_POLICY_P, "question": A_QUESTION_P}
            options = A_OPTIONS_P
        else:
            instructions = {"role": A_ROLE, "policy": A_POLICY, "question": A_QUESTION}
            options = A_OPTIONS_D if variant == "lexical_decoy" else A_OPTIONS
        return [Choice("action", instructions, dict(options))]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "now_s": self.START,
                "running_since": None,
                "unsaved": None,
                "last_edit": A_E0,
                "runs": [A_RM1, A_R0],
                "log_opened": True,
                "asked": None,
                "fix": None,
            }
        )
        applied = dict(A_FIX, status="applied")
        events: dict[int, tuple[dict[str, Any], str]] = {
            0: ({}, "13:57:10 run failed with the 4320 assertion (first of the streak; the 13:50 run failed with an ImportError). Its log is open; no fix known."),
            3: ({}, "A run of tests/test_invoices.py with more failures than this morning is not a run (rule 3 compares runs of tests/test_refunds.py)."),
            5: ({"unsaved": "app/refunds.py"}, "Dana starts typing edit 1 (Decimal rounding); unsaved."),
            8: ({"unsaved": None, "last_edit": A_E1, "running_since": at("14:03:55")}, "Saved 14:03:52; run started 14:03:55."),
            11: ({}, "An F is visible mid-run; the run is still in progress."),
            12: ({"running_since": None, "runs": [A_RM1, A_R0, A_R1], "log_opened": False},
                 "Run finished: still 1 failed (same assertion, streak 2). Its service log has not been opened."),
            13: ({}, "Six deprecation warnings look like new trouble after the edit, but failures are still 1 vs 1."),
            17: ({"log_opened": True}, "Dana reloads the service log for the 14:03:55 run."),
            21: ({"unsaved": "tests/conftest.py"}, "Dana starts typing edit 2 in the factory; unsaved."),
            23: ({}, "Talk of bothering Marco while typing; the editor is unsaved."),
            25: ({"unsaved": None, "last_edit": A_E2, "running_since": at("14:12:25")}, "Saved 14:12:20; run started 14:12:25."),
            29: ({"running_since": None, "runs": [A_RM1, A_R0, A_R1, A_R2], "log_opened": False},
                 "4 failed vs 1 before the edit (rule 3); the assertion has also failed 3 runs in a row (rule 4): rule 3 wins."),
            35: ({"last_edit": A_E3}, "conftest.py restored at 14:17:28; the 14:12:25 result predates it."),
            36: ({}, "A passing run of a different test file is not a run of tests/test_refunds.py."),
            40: ({"running_since": at("14:19:55")}, "Rerun started 14:19:55."),
            44: ({"running_since": None, "runs": [A_RM1, A_R0, A_R1, A_R2, A_R3], "log_opened": False},
                 "Fourth same-assertion failure in a row, fewer failures than before the restore, nobody asked (rule 4); the log is unopened too (rule 6)."),
            47: ({"log_opened": True}, "Log opened; rule 4 still applies."),
            48: ({}, "Marco at the desk about lunch is not asking him about the failure."),
            51: ({"asked": A_ASK}, "Dana asks Marco in #payments-dev at 14:25:20."),
            55: ({}, "A bot reports a failure on main in another test file; not Dana's run."),
            59: ({"fix": A_FIX}, "Marco names the one-line fix; not applied yet."),
            64: ({"unsaved": "app/refunds.py"}, "Dana types the fix; unsaved, so rule 1 wins over rule 5 while the fix is still not applied."),
            67: ({"unsaved": None, "last_edit": A_E4, "fix": applied, "running_since": at("14:33:25")}, "Fix saved 14:33:20; run started 14:33:25."),
            71: ({"running_since": None, "runs": [A_RM1, A_R0, A_R1, A_R2, A_R3, A_R4], "log_opened": False}, "All 14 pass."),
            74: ({"last_edit": A_E5}, "ruff format rewrote app/refunds.py at 14:36:58, after the 14:33:25 run started."),
            75: ({}, "Pre-commit hooks passing is not a run of the tests."),
            79: ({"running_since": at("14:39:25")}, "Rerun started 14:39:25."),
            83: ({"running_since": None, "runs": [A_RM1, A_R0, A_R1, A_R2, A_R3, A_R4, A_R5]}, "All 14 pass again; result is current."),
            90: ({}, "Marco suggests running again, but the latest run is already current and green."),
            96: ({}, "PR merged: the debugging task is complete."),
        }
        tags = span_tags(
            {
                "distractor": [3, 13, 23, (36, 37), 48, 55, 75, 90],
                "minimal_change": [17, 51, 74],
                "recovery": [40, 64, 79],
                "hold_under_activity": [(18, 20), (52, 54), (84, 88)],
                "priority_conflict": [(29, 34), (44, 46), (64, 66)],
                "boundary": [(96, 99)],
                "arithmetic": [(29, 34), (35, 39), (44, 46), (74, 78)],
            }
        )
        for t in range(STEPS):
            updates, note = events.get(t, ({}, ""))
            tl.step(dict(A_SCRIPT[t]), tags[t], note, now_s=self.START + self.TICK_SECONDS * t, **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t12-16: Dana reloads the service log as soon as the run ends.
            ticks = override(ticks, range(12, 17), log_opened=True, note="The service log for the 14:03:55 run was opened as soon as it finished.")
            ticks = _swap(ticks, {
                12: L("1 failed, 13 passed, 6 warnings in 1m47s",
                      "Still one failing. And now six warnings? Did my Decimal change do that?",
                      "Dana reloads the service log pane at once and glances at the yellow warnings count.",
                      "reloads the service log right away and wonders whether her Decimal change caused six warnings"),
                17: L("INFO refunds booking=bk_8052 created_at=2026-09-25T10:34:40+00:00 now=2026-09-25T14:04:40 hours_since_booking=3.50 grace_hours=2",
                      "Wait... hours_since_booking three point five?",
                      "Dana scrolls the service log down to the refund line.",
                      "scrolls the service log to the refund line and finds hours_since_booking at 3.50"),
            })
            # (2) t29-34: the factory edit breaks nothing else; the 4320
            # assertion simply fails a third time in a row.
            quiet = a_run("14:12:25", 1, 13, "4320")
            for t in range(29, STEPS):
                ticks[t].latent["runs"] = [quiet if r["start_s"] == A_R2["start_s"] else r for r in ticks[t].latent["runs"]]
            ticks = _swap(ticks, {
                28: L("tests/test_refunds.py ....F.....",
                      "One F. The same one, probably.",
                      "Dana watches the progress line fill in; the run has not finished.",
                      "sees a single F appear before the run has finished"),
                29: L("1 failed, 13 passed, 6 warnings in 1m52s",
                      "One. Still mine. Nothing else broke, but nothing got fixed either.",
                      "Dana stares at the short test summary.",
                      "sees one failure again, nothing new broken and nothing fixed"),
                30: L("E       assert 4320 == 4800",
                      "Naive or aware, the factory change made no difference at all.",
                      "Dana scrolls through the only traceback.",
                      "reads the only traceback and admits the factory change made no difference"),
                31: L("FAILED tests/test_refunds.py::test_cancel_within_grace_refunds_in_full - assert 4320 == 4800",
                      "And the one I actually care about still says 4320.",
                      "Dana scrolls back up to the failure.",
                      "scrolls back to the failure, which still shows 4320"),
                32: L("PASSED tests/test_refunds.py::test_refund_after_grace_charges_fee",
                      "The other refund tests don't even care about the factory change.",
                      "Dana scrolls through the verbose list of passes.",
                      "notices that the other refund tests pass either way"),
                33: L("PASSED tests/test_refunds.py::test_refund_same_day_rebooking",
                      "Three runs in a row with the exact same 4320. Unbelievable.",
                      "Dana drums her fingers on the desk.",
                      "grumbles that three runs in a row have shown the same 4320"),
                34: L("$ git restore tests/conftest.py",
                      "Okay. That was pointless.",
                      "Dana has typed a git restore command but has not pressed Enter.",
                      "calls the factory change pointless and types a restore command without running it"),
            })
            # (3) t74-78: the formatter finds nothing to change, so no file is rewritten.
            ticks = override(ticks, range(74, STEPS), last_edit=A_E4)
            ticks = _swap(ticks, {
                74: L("1 file left unchanged",
                      "Already formatted. Nothing to do.",
                      "The formatter left app/refunds.py exactly as it was on disk.",
                      "runs the formatter, which leaves app/refunds.py untouched"),
                77: L("$ git diff --cached --stat   ->   app/refunds.py | 6 ++++--",
                      "Same diff as before. Still, I should be sure.",
                      "Dana reads the staged diff.",
                      "reads the staged diff, which is the same as before"),
            })
            # t13 keeps its distractor tag: the six warnings still tempt revert
            # while gold is watch. t79 loses 'recovery': t74-78 are watch here.
            ticks = _set_tags(ticks, {
                12: ["minimal_change"], 13: ["distractor"], 17: [],
                29: ["minimal_change", "arithmetic", "priority_conflict"], 30: ["arithmetic", "priority_conflict"],
                31: ["arithmetic", "priority_conflict"], 32: ["arithmetic", "priority_conflict"],
                33: ["arithmetic", "priority_conflict"], 34: ["arithmetic", "priority_conflict"],
                74: ["minimal_change"], 75: [], 76: [], 77: [], 78: [], 79: [],
            })
            for t, note in {
                17: "Dana keeps reading the log she opened at 14:06.",
                29: "1 failed vs 1 before the edit: no revert. Same assertion 3 runs in a row, nobody asked (rule 4); log unopened too (rule 6).",
                35: "conftest.py restored at 14:17:28; the 14:12:25 result predates it.",
                44: "Fourth same-assertion failure in a row, as many failures as before the restore, nobody asked (rule 4).",
                74: "The formatter changed nothing; the 14:33:25 run is still current.",
            }.items():
                ticks[t].note = note
        elif variant == "structural_cf":
            # Dana already asked Marco about this failure by direct message at
            # 13:59:20, right after the first 4320, so rule 4 never fires.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for t, tk in enumerate(ticks):
                asked = dict(A_ASK_EARLY)
                if t >= 51:
                    asked["again_s"] = A_ASK["at_s"]
                tk.latent["asked"] = asked
            ticks = _set_tags(ticks, {
                44: ["arithmetic"], 45: ["arithmetic"], 46: ["arithmetic"],
                47: ["recovery"], 51: [],
            })
            for t, note in {
                0: "Marco was asked by direct message at 13:59:20, right after the first 4320; the 13:57:10 run's log is open.",
                44: "Fourth same-assertion failure, but Marco was already asked at 13:59:20: rule 6 (log unopened) applies.",
                47: "Log opened; nothing left to suggest while Marco has the question.",
                51: "Dana pings Marco again; he was already asked at 13:59:20.",
            }.items():
                ticks[t].note = note
        return ticks

    # ------------------------------------------------------------------ policy
    @staticmethod
    def _streak(runs: list[dict[str, Any]]) -> int:
        """Consecutive latest runs in which the 4320 assertion failed."""
        n = 0
        for run in reversed(runs):
            if run["target"] != "4320":
                break
            n += 1
        return n

    @staticmethod
    def _before_edit(z: dict[str, Any]) -> dict[str, Any]:
        """The last run that started before the most recent edit."""
        earlier = [r for r in z["runs"] if r["start_s"] < z["last_edit"]["at_s"]]
        return earlier[-1]

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        latest = z["runs"][-1]
        if z["running_since"] is not None or z["unsaved"]:
            action = "watch"
        elif latest["start_s"] < z["last_edit"]["at_s"]:
            action = "rerun"
        elif latest["failed"] > self._before_edit(z)["failed"]:
            action = "revert"
        elif self._streak(z["runs"]) >= 3 and z["asked"] is None:
            action = "ask"
        elif z["fix"] is not None and z["fix"]["status"] == "identified":
            action = "apply_fix"
        elif latest["failed"] > 0 and not z["log_opened"]:
            action = "inspect"
        else:
            action = "watch"
        return {"action": action}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Dana fixes one failing pytest test (30 s ticks, 14:00-14:49:30). Edit 1 (Decimal rounding) changes nothing and its log goes unread (inspect t12-16); edit 2 in the test factory breaks three more tests while the 4320 assertion fails a third time (revert over ask, t29-34); a git restore leaves a stale result (rerun t35-39, with a passing unrelated test file as distractor); the fourth identical failure with nobody asked (ask t44-50, over an unopened log at t44-46); Marco names a one-line fix (apply t59-63), which Dana types for three ticks before saving (watch over apply_fix, t64-66); a formatter rewrite makes the green result stale (rerun t74-78); the PR is merged at t96."},
            "paraphrase": {"summary": "Same latent trajectory; narrated prose with execution/change/module vocabulary instead of fields, with two or three phrasings per fact and a sentence order that varies by tick; reworded role, rules and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; irrelevant office details borrowing a wrong action's vocabulary (rerun of a match, reverted logo, a small fix for the Wi-Fi, 'ask a teammate' posters), sometimes blended into Dana's line. About half the ticks get a second line, and about one tick in five gets a line from the gold action's pool, so a decoy line's action never rules its option out."},
            "minimal_cf": {"summary": "Three one-field edits: t12-16 the service log is opened as soon as the run ends (inspect->watch); t29-34 the factory edit breaks no other test, so failures stay at 1 and the third identical failure makes rule 4 apply (revert->ask); t74-78 the formatter leaves the file unchanged, so the green result stays current (rerun->watch)."},
            "structural_cf": {"summary": "History changed: Dana already asked Marco about this failure by direct message at 13:59:20, right after the 13:57:10 run first showed 4320. Rule 4 never applies, so the fourth identical failure gives inspect (log unopened, t44-46) and then watch (t47-50); t51 becomes a follow-up ping."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    @staticmethod
    def _outcome(run: dict[str, Any], t: int, paraphrase: bool = False) -> str:
        if paraphrase:
            if run["target"] == "pass":
                return f"all {run['passed']} tests passed"
            head = f"{run['failed']} broke and {run['passed']} passed"
            if run["target"] == "import":
                return f"{head}, the test Dana is chasing breaking inside its body with an ImportError because booking_factory could not be imported from tests.conftest"
            detail = f"{head}, the test Dana is chasing hitting assert 4320 == 4800 on refund.amount_cents"
            if run["others"]:
                detail += f" while {listing(run['others'])} each raised the {A_OTHER_ERROR}"
            return detail
        if run["target"] == "pass":
            return pick([f"{run['passed']} passed, none failed", f"0 failed, {run['passed']} passed"], "a-pass", t, run["start_s"])
        counts = pick([f"{run['failed']} failed, {run['passed']} passed", f"{run['passed']} passed and {run['failed']} failed"], "a-cnt", t, run["start_s"])
        if run["target"] == "import":
            return f"{counts} ({A_TEST_SHORT}: ImportError: cannot import name 'booking_factory' from 'tests.conftest')"
        detail = f"{counts} ({A_TEST_SHORT}: assert 4320 == 4800"
        if run["others"]:
            detail += f"; {listing(run['others'])}: {A_OTHER_ERROR}"
        return detail + ")"

    def _runs(self, z: dict[str, Any], t: int) -> str:
        shown = z["runs"][-4:]
        items = [f"{hms(r['start_s'])}: {self._outcome(r, t)}" for r in shown]
        lead = pick(
            [
                "Last {n} runs of tests/test_refunds.py by start time, oldest first: ",
                "Runs of tests/test_refunds.py (last {n}, oldest first): ",
                "The last {n} finished runs of tests/test_refunds.py, from oldest to newest: ",
            ],
            "a-runs",
            t,
        ).format(n=len(shown))
        latest = hms(z["runs"][-1]["start_s"])
        tail = pick(
            [f" The latest run is the {latest} one.", f" Latest run: the one started at {latest}.", f" The newest of them, and so the latest run, started at {latest}."],
            "a-latest",
            t,
        )
        return lead + "; ".join(items) + "." + tail

    def _edits(self, z: dict[str, Any], t: int) -> str:
        # No sentence compares the latest run with the edit: whether the result
        # is stale (rule 2) is one timestamp comparison left to the reader.
        e = z["last_edit"]
        before = self._before_edit(z)
        out = pick(
            [
                "Most recent edit: {f}, saved at {a} ({w}).",
                "The last saved edit was to {f} at {a}: {w}.",
                "Last edit on disk: {f} at {a} ({w}).",
            ],
            "a-edit",
            t,
        ).format(f=e["file"], a=hms(e["at_s"]), w=e["what"])
        out += " " + pick(
            [
                "The last run that started before that edit is the {b} run ({n} failed).",
                "Before that edit, the last run to start was the {b} one, with {n} failed.",
            ],
            "a-before",
            t,
        ).format(b=hms(before["start_s"]), n=before["failed"])
        if z["unsaved"]:
            out += " " + pick(
                [
                    f"Unsaved changes: {z['unsaved']} has changes being typed that are not saved yet.",
                    f"The editor tab for {z['unsaved']} shows unsaved changes.",
                ],
                "a-unsaved",
                t,
            )
        else:
            out += " " + pick(["Unsaved changes: none.", "Every file in the editor is saved.", "The editor has no unsaved changes."], "a-saved", t)
        return out.replace("  ", " ")

    def _run_status(self, z: dict[str, Any], t: int) -> str:
        if z["running_since"] is not None:
            return pick(
                [
                    "A run of tests/test_refunds.py is in progress (started {s}); it has not finished.",
                    "Running now: tests/test_refunds.py, started at {s}, not finished yet.",
                    "pytest is still working through tests/test_refunds.py (run started {s}).",
                ],
                "a-running",
                t,
            ).format(s=hms(z["running_since"]))
        return pick(
            ["No run is in progress.", "Nothing is running at the moment.", "No pytest run is going on right now."],
            "a-idle",
            t,
        )

    def _log(self, z: dict[str, Any], t: int) -> str:
        latest = z["runs"][-1]
        if latest["failed"] == 0:
            return pick(
                [
                    "The latest run passed, so it has no failure report and no log to follow.",
                    "No failure report for the latest run: every test in it passed.",
                ],
                "a-nolog",
                t,
            )
        path = f".pytest-logs/{A_TEST_SHORT}.log"
        if z["log_opened"]:
            return pick(
                [
                    f"The latest failure report points to {path}; Dana has opened that log since the run finished.",
                    f"Service log named in the latest failure report ({path}): opened after that run finished.",
                ],
                "a-logopen",
                t,
            )
        return pick(
            [
                f"The latest failure report points to {path}; it has not been opened since that run finished (the log pane still shows an older run).",
                f"Service log named in the latest failure report ({path}): not opened since that run finished.",
            ],
            "a-logshut",
            t,
        )

    def _help(self, z: dict[str, Any], t: int) -> str:
        a = z["asked"]
        if a is None:
            ask = pick(
                ["No teammate has been asked about this failure yet.", "Nobody else has been asked about this failure so far."],
                "a-noask",
                t,
            )
        elif a.get("early"):
            ask = (f"Dana asked Marco Ruiz about this failure by direct message at {hms(a['at_s'])}, right after the first 4320 result; "
                   "he said he would look after lunch.")
            if a.get("again_s"):
                ask += f" She pinged him again in #payments-dev at {hms(a['again_s'])}."
        else:
            ask = pick(
                [
                    f"Dana asked {a['who']} about this failure in {a['where']} at {hms(a['at_s'])}.",
                    f"{a['who']} has been asked about the failure ({a['where']}, {hms(a['at_s'])}).",
                ],
                "a-ask",
                t,
            )
        f = z["fix"]
        if f is None:
            fix = pick(["No concrete fix has been identified.", "Nobody has pinned down a specific fix yet."], "a-nofix", t)
        elif f["status"] == "identified":
            # The same 'not applied' sentence whether or not Dana is typing it
            # in; the unsaved buffer is reported in `edits` (rule 1).
            fix = f"Fix identified by {f['by']} at {hms(f['at_s'])}: {f['what']}."
            fix += " " + pick(["It has not been applied yet.", "Not applied so far."], "a-fixnot", t)
        else:
            fix = f"{f['by']}'s fix on line 41 was applied and saved at {hms(A_E4['at_s'])}."
        return f"{ask} {fix}"

    def render(self, history: list[Tick], variant: str) -> Any:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        s = tick.surface
        quote = f"\"{s['say']}\" " if s["say"] else ""
        state: dict[str, Any] = {
            "task": f"Make {A_TEST} pass in bookings-api (branch fix/grace-refund). A run of tests/test_refunds.py takes about 1 min 50 s, most of it starting a Postgres test container.",
            "clock": hms(z["now_s"]),
            "run_status": self._run_status(z, t),
            "recent_runs": self._runs(z, t),
            "edits": self._edits(z, t),
            "service_log": self._log(z, t),
            "help": self._help(z, t),
            "screen": s["term"],
            "dana": f"{quote}({s['doing']})",
        }
        if variant == "lexical_decoy":
            _add_decoys(state, A_DECOYS, self.policy(z)["action"], t, "a", "dana", "office")
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        blocks: dict[str, list[str]] = {}

        # What is executing and what is unsaved (rule 1).
        if z["running_since"] is not None:
            s = hms(z["running_since"])
            status = pick([
                f"An execution of the refund module began at {s} and is still under way.",
                f"pytest has been working through the refund module since {s} and has not completed.",
                f"Since {s} an execution of tests/test_refunds.py has been under way; it has not completed yet.",
            ], "ap-run", t)
        else:
            status = pick(["No execution is under way right now.", "pytest is idle at the moment.", "Nothing is executing at present."], "ap-idle", t)
        if z["unsaved"]:
            u = z["unsaved"]
            buffer = pick([
                f"The editor buffer for {u} holds modifications that are not yet written to disk.",
                f"{u} has modifications in the editor that have not been written to disk.",
                f"Dana's edits to {u} are still only in the editor buffer, not on disk.",
            ], "ap-unsaved", t)
        else:
            buffer = pick(["Nothing in the editor is waiting to be written to disk.", "All editor buffers are written to disk.",
                           "Every open buffer matches what is on disk."], "ap-saved", t)
        blocks["status"] = [status, buffer]

        # Colleagues consulted (rule 4) and the known correction (rule 5).
        a = z["asked"]
        if a is None:
            ask = pick(["No colleague has been consulted about the bug so far.", "Dana has not consulted any colleague about this yet.",
                        "So far no colleague has been brought in on this bug."], "ap-noask", t)
        elif a.get("early"):
            ask = (f"Dana already consulted Marco Ruiz about this very failure in a direct message at {hms(a['at_s'])}, just after the first "
                   "4320 turned up, and he promised to look after lunch.")
            if a.get("again_s"):
                ask += f" At {hms(a['again_s'])} she nudged him once more in #payments-dev."
        else:
            ask = pick([f"Dana consulted {a['who']} about the bug in {a['where']} at {hms(a['at_s'])}.",
                        f"At {hms(a['at_s'])} Dana brought {a['who']} in on the bug via {a['where']}."], "ap-ask", t)
        f = z["fix"]
        if f is None:
            fix = pick(["Nobody has pinned down a specific correction.", "No concrete correction is known yet.",
                        "A specific correction has not been found so far."], "ap-nofix", t)
        elif f["status"] == "identified":
            fix = pick([f"At {hms(f['at_s'])} {f['by']} pinned down a correction: {f['what_p']}.",
                        f"{f['by']} pinned down a correction at {hms(f['at_s'])}: {f['what_p']}."], "ap-fix", t)
            fix += " " + pick(["It has not been put in yet.", "So far it has not been put in."], "ap-fixnot", t)
        else:
            fix = pick([f"{f['by']}'s correction to line 41 is in, written to disk at {hms(A_E4['at_s'])}.",
                        f"The correction {f['by']} found is in place on line 41 (written to disk at {hms(A_E4['at_s'])})."], "ap-fixin", t)
        blocks["help"] = [ask, fix]

        # The latest change and the last execution that began before it (rules 2 and 3).
        e = z["last_edit"]
        before = self._before_edit(z)
        fe, ae, we, b, n = e["file"], hms(e["at_s"]), e["what"], hms(before["start_s"]), before["failed"]
        blocks["change"] = [pick([
            f"The most recent change written to disk touched {fe} at {ae} ({we}); the last execution that began before that change was the {b} one, with {n} broken.",
            f"Dana's latest change on disk was to {fe} at {ae} ({we}). Of the executions that began before it, the last is the {b} one ({n} broken).",
            f"Last change written to disk: {fe}, {ae}, {we}. The {b} execution, with {n} broken, is the last one that began before it.",
        ], "ap-change", t)]

        # The log named by the newest execution's failure message (rule 6).
        latest = z["runs"][-1]
        path = f".pytest-logs/{A_TEST_SHORT}.log"
        if latest["failed"] == 0:
            log = pick(["The newest execution had no broken tests, so there is no failure message pointing at a log.",
                        "Nothing broke in the newest execution, so no failure message names a log."], "ap-nolog", t)
        elif z["log_opened"]:
            log = pick([f"The failure message of the newest execution refers to the log file {path}, and Dana has looked at it since that execution completed.",
                        f"Dana has looked at {path}, the log named in the newest execution's failure message, since that execution completed."], "ap-logopen", t)
        else:
            log = pick([f"The failure message of the newest execution refers to the log file {path}, which Dana has not looked at since that execution completed.",
                        f"The newest execution's failure message names {path}; Dana has not looked at that log since the execution completed."], "ap-logshut", t)
        blocks["log"] = [log]

        shown = z["runs"][-4:]
        items = " ".join(f"({i}) begun at {hms(r['start_s'])}: {self._outcome(r, t, True)}." for i, r in enumerate(shown, start=1))
        blocks["execs"] = [pick([f"Completed executions, most recent last: {items}", f"Here are the completed executions, oldest to newest: {items}",
                                 f"The last {len(shown)} completed executions, in order from oldest to newest: {items}"], "ap-execs", t)]
        blocks["goal"] = [pick([
            f"Dana's goal is to get {A_TEST_SHORT} (in the module tests/test_refunds.py of the bookings-api service) to pass; one execution "
            "of that module takes roughly 1 min 50 s, mostly for a throwaway Postgres container.",
            f"What Dana is after: {A_TEST_SHORT}, in tests/test_refunds.py of the bookings-api service, should pass. Executing that module "
            "takes about 1 min 50 s, most of it spent starting a throwaway Postgres container.",
        ], "ap-goal", t)]

        order = pick([
            ["status", "help", "change", "log", "execs", "goal"],
            ["execs", "change", "status", "log", "help", "goal"],
            ["goal", "status", "change", "execs", "log", "help"],
        ], "ap-order", t)
        parts = [f"{hms(z['now_s'])}. Right now Dana {tick.surface['gist']}."]
        for name in order:
            parts.extend(blocks[name])
        return " ".join(parts)


# ===========================================================================
# Scenario B - build sheriff for a TypeScript monorepo; action + target package
# ===========================================================================

B_PACKAGES = ["web", "ui_kit", "api_client", "billing", "search", "auth"]
B_DIRS = {
    "web": "apps/web",
    "ui_kit": "packages/ui-kit",
    "api_client": "packages/api-client",
    "billing": "packages/billing",
    "search": "packages/search",
    "auth": "packages/auth",
}
B_OWNERS = {
    "web": "Web",
    "ui_kit": "Design Systems",
    "api_client": "Platform",
    "billing": "Payments",
    "search": "Discovery",
    "auth": "Identity",
}
B_QUARANTINE = [
    "search › indexer.spec.ts › rebuilds shard map",
    "billing › webhooks.spec.ts › retries a failed delivery",
    "web e2e › checkout.spec.ts › applies a coupon",
]

B_ROLE = (
    "You assist Lena Brandt, this week's build sheriff for `harbor`, a TypeScript monorepo (pnpm workspaces, Vitest "
    "unit tests, Playwright e2e tests). Lena is on the Platform team. You watch the main branch's CI pipelines and "
    "suggest her next move. The merge queue runs only lint and typecheck on a PR before merging it; the test jobs run "
    "in the main pipeline after the merge. Quarantined tests still run, and one that fails still fails its job. "
    "`ownership` and `quarantine` in the state do not change during the session."
)
B_DEFINITIONS = [
    "(a) 'The latest main pipeline' is the most recently started CI pipeline on main. A job counts as failed only if its latest attempt failed; 'the failure' is that failed job.",
    "(b) 'The failing package' is the package that contains the top in-repo frame of the failure's stack trace: the first frame whose path starts with apps/ or packages/ (frames in node_modules or node: internals are skipped). If there is no stack trace, it is the package the failed job tests.",
    "(c) A 'known flake' is a failure of a test that is on the quarantine list and that failed by timing out.",
    "(d) A commit 'touched' a package if it changed at least one file under that package's directory.",
    "(e) A team 'has an open fix' for a failure only if the known-issues board lists an open pull request from that team for that failure. A fix posted in #ci-main (rule 6) is not an open fix.",
]
B_POLICY = [
    "1. If a job in the latest main pipeline has failed, the failure is not a known flake, and the merge queue is still merging: action = pause the merge queue; target = none.",
    "2. Otherwise, if no job in the latest main pipeline has failed (jobs still running, or all passed), or anyone, Lena included, has said in #ci-main that they are already reverting, fixing or taking over the current failure: action = keep watching; target = none.",
    "3. Otherwise, if the failure is a known flake and its job has not been rerun since it failed: action = rerun the failed job; target = the failing package.",
    "4. Otherwise, if the team that owns the failing package already has an open fix for this failure: action = hand off to the owning team; target = the failing package.",
    "5. Otherwise, if exactly one commit since the last green main pipeline touched the failing package: action = revert that commit; target = the failing package.",
    "6. Otherwise, if someone has posted a fix for this failure in #ci-main and Platform owns the failing package: action = apply the posted fix; target = the failing package.",
    "7. Otherwise, if a team other than Platform owns the failing package: action = hand off to the owning team; target = the failing package.",
    "8. Otherwise: action = inspect the failed job's full log; target = the failing package.",
]
B_Q_ACTION = "Apply the first rule that matches the current state. Which action should you suggest right now?"
B_Q_TARGET = "Apply the first rule that matches the current state. Which package, if any, should the suggestion name right now?"

B_ROLE_P = (
    "You back up Lena Brandt, who is on build-sheriff duty this week for harbor, a TypeScript monorepo (pnpm "
    "workspaces, Vitest for unit tests, Playwright for end-to-end tests). Lena belongs to the Platform team. You keep "
    "an eye on CI for the main branch and propose what she should do next. Before landing a PR the merge queue only "
    "lints and type-checks it; the test jobs run in the trunk build afterwards. Tests in quarantine are still executed, "
    "and one that breaks still turns its job red. The code-owner list and the quarantine list in each update stay the "
    "same for the whole session."
)
B_DEFINITIONS_P = [
    "(a) 'The newest trunk build' is the CI pipeline on main that was started most recently. A job only counts as red if its most recent attempt was red; 'the breakage' is that red job.",
    "(b) 'The broken package' is the package holding the first repository frame of the stack trace, meaning the first listed frame (innermost first) whose path begins with apps/ or packages/ (skip frames inside node_modules or node: internals). When there is no stack trace, it is the package that the red job tests.",
    "(c) A 'known flaky failure' is a breakage of a test that appears on the quarantine list and that ended because it ran out of time.",
    "(d) A commit 'modified' a package if it changed one or more files inside that package's folder.",
    "(e) A team 'has a fix open' for a breakage only when the known-issue tracker lists an open pull request from that team for that breakage; a fix shared in #ci-main (rule 6) does not count.",
]
B_POLICY_P = [
    "1. When a job in the newest trunk build is red, the breakage is not a known flaky failure, and the merge queue is still landing PRs: freeze the merge queue; package = none.",
    "2. If not, and either no job in the newest trunk build is red (jobs still going, or everything green), or anybody, Lena herself included, has announced in #ci-main that they are already reverting, fixing or taking over the current breakage: stand by; package = none.",
    "3. If not, and the breakage is a known flaky failure whose job has not been retried since it went red: retry that job; package = the broken package.",
    "4. If not, and the team owning the broken package already has a fix open for this breakage: pass it to the owning team; package = the broken package.",
    "5. If not, and exactly one commit since the last green trunk build modified the broken package: back out that commit; package = the broken package.",
    "6. If not, and someone has posted a fix for this breakage in #ci-main while Platform owns the broken package: land the posted fix; package = the broken package.",
    "7. If not, and a team other than Platform owns the broken package: pass it to the owning team; package = the broken package.",
    "8. In every other case: read through the red job's complete log; package = the broken package.",
]
B_Q_ACTION_P = "Go down the rules and stop at the first one that fits. What do you recommend to Lena at this moment?"
B_Q_TARGET_P = "Go down the rules and stop at the first one that fits. Which package, if any, does the recommendation concern at this moment?"

B_ACTIONS = {
    "watch": {"category": "observe", "action": "Keep watching main and suggest nothing for now."},
    "rerun": {"category": "retry", "action": "Suggest rerunning the failed CI job."},
    "inspect": {"category": "diagnose", "action": "Suggest opening the full log of the failed job."},
    "revert": {"category": "undo", "action": "Suggest reverting the commit that touched the target package."},
    "apply_fix": {"category": "repair", "action": "Suggest applying the posted fix to the target package."},
    "pause": {"category": "protect main", "action": "Suggest pausing the merge queue until main is sorted out."},
    "handoff": {"category": "delegate", "action": "Suggest handing the failure to the target package's owning team."},
}
B_ACTIONS_P = {
    "watch": {"category": "stand by", "action": "Say nothing for now and keep an eye on the trunk."},
    "rerun": {"category": "try again", "action": "Recommend retrying the red job."},
    "inspect": {"category": "investigate", "action": "Recommend reading through the complete log of the red job."},
    "revert": {"category": "roll back", "action": "Recommend backing out the commit that modified the chosen package."},
    "apply_fix": {"category": "patch", "action": "Recommend landing the posted fix in the chosen package."},
    "pause": {"category": "guard the trunk", "action": "Recommend freezing the merge queue while the trunk is broken."},
    "handoff": {"category": "hand over", "action": "Recommend passing the breakage to the team behind the chosen package."},
}
B_ACTIONS_D = {
    "watch": {"category": "observe", "action": "Keep watching main quietly and suggest nothing for now."},
    "rerun": {"category": "retry", "action": "Suggest a rerun of the failed CI job."},
    "inspect": {"category": "diagnose", "action": "Suggest opening the failed job's full log."},
    "revert": {"category": "undo", "action": "Suggest reverting the commit that touched the target package."},
    "apply_fix": {"category": "repair", "action": "Suggest applying the posted fix to the target package."},
    "pause": {"category": "protect main", "action": "Suggest pausing the merge queue until main is sorted."},
    "handoff": {"category": "delegate", "action": "Suggest handing the failure to the owning team of the target package."},
}
B_TARGETS = {
    "web": "apps/web (the customer web app)",
    "ui_kit": "packages/ui-kit (shared React components)",
    "api_client": "packages/api-client (HTTP client for our APIs)",
    "billing": "packages/billing (invoices and pricing)",
    "search": "packages/search (the search indexer)",
    "auth": "packages/auth (sign-in and sessions)",
    "none": "No package (the action has no target)",
}
B_TARGETS_P = {
    "web": "The web application in apps/web",
    "ui_kit": "The shared component library in packages/ui-kit",
    "api_client": "The HTTP client library in packages/api-client",
    "billing": "The invoicing code in packages/billing",
    "search": "The search indexing code in packages/search",
    "auth": "The login and session code in packages/auth",
    "none": "No package at all",
}


def b_commit(sha: str, when: str, who: str, title: str, paths: list[str], title_p: str) -> dict[str, Any]:
    """A commit on main; ``title_p`` describes it in the paraphrase register."""
    return {"sha": sha, "at": when, "who": who, "title": title, "paths": list(paths), "title_p": title_p}


C_2231 = b_commit("4be21c0", "08:56", "merge queue", "#2231 ui-kit: add a delay prop to Tooltip",
                  ["packages/ui-kit/src/Tooltip.tsx", "packages/ui-kit/src/Tooltip.test.tsx"],
                  "the Tooltip delay prop for the component library (#2231)")
C_DOCS1 = b_commit("a1f03c2", "09:14", "docs-bot", "docs: fix a typo in CONTRIBUTING.md [skip ci]", ["docs/CONTRIBUTING.md"],
                   "a typo fix in the contributing guide that CI skipped")
C_2232 = b_commit("b7e19d4", "09:14", "merge queue", "#2232 billing: switch invoice rounding to banker's rounding",
                  ["packages/billing/src/rounding.ts", "packages/billing/CHANGELOG.md"],
                  "Payments' move to banker's rounding for invoices (#2232)")
C_2238 = b_commit("e0c5a91", "09:33", "Kenji Mori", "#2238 billing: round half-cent totals correctly",
                  ["packages/billing/src/rounding.ts", "packages/billing/test/invoice.spec.ts"],
                  "Kenji's half-cent rounding repair (#2238)")
# The title's scope names api-client, but the bump stayed inside the declared
# range and changed only the root lockfile: no file under packages/api-client.
C_2234 = b_commit("9c4e1f0", "09:45", "merge queue", "#2234 api-client: bump undici to 6.21.0",
                  ["pnpm-lock.yaml"], "the HTTP client's undici bump to 6.21.0 (#2234)")
# minimal_cf: the same commit also edits the package manifest under api-client.
C_2234_CF = b_commit("9c4e1f0", "09:45", "merge queue", "#2234 api-client: bump undici to 6.21.0",
                     ["packages/api-client/package.json", "pnpm-lock.yaml"], "the HTTP client's undici bump to 6.21.0 (#2234)")
C_2235 = b_commit("5d2a7e1", "09:45", "merge queue", "#2235 web: add a checkout retry banner",
                  ["apps/web/src/checkout/RetryBanner.tsx", "apps/web/src/checkout/pay.tsx"],
                  "Aiko's retry banner for checkout (#2235)")
C_2243 = b_commit("7f3e0d1", "10:07", "Lena", "#2243 api-client: read retry-after from the new undici error shape",
                  ["packages/api-client/src/retry.ts"], "the retry-after repair for undici's new error shape (#2243)")
# The title's scope names auth, but the only changed file is under docs/.
C_DOCS2 = b_commit("1e77b0a", "10:18", "docs-bot", "auth: sync the cert rotation guide from the wiki [skip ci]", ["docs/auth/rotation.md"],
                   "a wiki sync of auth's cert rotation guide that CI skipped")
# minimal_cf: the 10:18 push is Priya's change to the TLS test server under
# packages/auth, which makes it load the short-lived expiry-test certificate.
C_CERT_CF = b_commit("1e77b0a", "10:18", "Priya Nair", "auth: make the TLS test server's fixture cert configurable [skip ci]",
                     ["packages/auth/test/fixtures/tls.ts"],
                     "Priya's change letting auth's TLS test server load a different fixture certificate, which CI skipped")
C_2251 = b_commit("3aa91c7", "10:37", "Priya Nair", "#2251 auth: rotate the TLS test fixture certificate",
                  ["packages/auth/test/fixtures/cert.pem", "packages/auth/test/fixtures/key.pem"],
                  "Identity's certificate rotation (#2251)")
C_2251_CF = b_commit("3aa91c7", "10:37", "Priya Nair", "#2251 auth: load the long-lived TLS fixture certificate by default again",
                     ["packages/auth/test/fixtures/tls.ts"],
                     "Identity's repair that makes the TLS test server load the long-lived certificate by default again (#2251)")


def b_failure(job: str, when: str, test: str, error: str, frames: list[str], pkg: str, timeout: bool) -> dict[str, Any]:
    return {
        "job": job,
        "at": when,
        "test": test,
        "error": error,
        "frames": list(frames),
        "pkg": pkg,
        "timeout": timeout,
        "quarantined": test in B_QUARANTINE,
    }


F_SEARCH = b_failure("test:search", "09:06", "search › indexer.spec.ts › rebuilds shard map",
                     "Error: Test timed out in 5000ms",
                     ["at packages/search/test/indexer.spec.ts:77:3"], "search", True)
F_SEARCH_CF = b_failure("test:search", "09:06", "search › indexer.spec.ts › rebuilds shard map",
                        "AssertionError: expected 11 to be 12 (shard count)",
                        ["at packages/search/test/indexer.spec.ts:81:5"], "search", False)
# A web unit test fails, but its top in-repo frame is billing's rounding code:
# the failing package is billing, not the package the failed job tests.
F_BILLING = b_failure("test:web", "09:20", "web › InvoiceTotal.test.tsx › rounds half-cent totals",
                      "AssertionError: expected 1249 to be 1250",
                      ["at roundInvoice (packages/billing/src/rounding.ts:31:10)",
                       "at InvoiceTotal (apps/web/src/invoices/InvoiceTotal.tsx:22:15)",
                       "at apps/web/src/invoices/InvoiceTotal.test.tsx:48:5"],
                      "billing", False)
F_WEB = b_failure("e2e:web", "09:50", "web e2e › checkout.spec.ts › retry banner shows a countdown",
                  "TypeError: Cannot read properties of undefined (reading 'retry-after')",
                  ["at getHeader (node_modules/.pnpm/undici@6.21.0/node_modules/undici/lib/core/util.js:212:21)",
                   "at parseRetryAfter (packages/api-client/src/retry.ts:41:37)",
                   "at CheckoutRetryBanner (apps/web/src/checkout/RetryBanner.tsx:18:22)"],
                  "api_client", False)
F_AUTH = b_failure("test:auth", "10:24", "auth › session.spec.ts › refreshes an expiring token",
                   "Error: certificate has expired",
                   ["at TLSSocket.onConnectSecure (node:_tls_wrap:1674:34)",
                    "at createTestServer (packages/auth/test/fixtures/tls.ts:12:9)",
                    "at packages/auth/test/session.spec.ts:30:18"],
                   "auth", False)

B_DISC_ISSUE = "DISC-311 (Discovery): search › indexer.spec.ts › rebuilds shard map times out now and then; quarantined, no fix planned."
# Payments' open fix appears on the board at 09:27 (t27): the PR is opened
# the same minute, after Omar's 09:26 diagnosis, so it did not exist earlier.
B_PAY_FIX = {
    "team": "Payments",
    "pkg": "billing",
    "test": F_BILLING["test"],
    "text": "PAY-88 (Payments, added 09:27): web › InvoiceTotal.test.tsx › rounds half-cent totals has failed with expected 1249 to be 1250 since #2232; open fix PR #2238 by Kenji Mori (Payments), opened 09:27.",
    "text_p": "PAY-88, filed by Payments at 09:27: since #2232 the web InvoiceTotal test 'rounds half-cent totals' breaks with expected 1249 to be 1250, and Kenji Mori of Payments opened fix PR #2238 for it at 09:27; the PR is still open.",
}


def b_line(ci: str, chat: str | list[str], sheriff: str, gist: str, side: str = "") -> dict[str, Any]:
    """One tick of scenario B surface content.

    ``ci`` is the main pipeline's job-board texture of that minute (may be
    empty), ``chat`` the newest message in #ci-main or a bot notice (a list
    when several arrive in the same minute), ``sheriff`` a stage note about
    Lena, ``gist`` a third-person summary for the paraphrase register, and
    ``side`` activity outside main (PR checks, a local branch).
    """
    return {"ci": ci, "chat": chat, "sheriff": sheriff, "gist": gist, "side": side}


M = b_line

B_SCRIPT = _script(
    (0, [  # #5120 running (started 08:57 for #2231)
        M("lint and typecheck passed; test:web, test:ui-kit, test:billing, test:api-client, test:search, test:auth and e2e:web are running",
          "08:59 Aiko (Web): morning! is the queue moving today?",
          "Lena is reading the overnight sheriff notes.",
          "reads the overnight sheriff notes while the unit and e2e jobs run"),
        M("test:ui-kit and test:web passed (1m58s, 2m06s)", "09:01 Lena: it's moving, #2232 is next",
          "Lena answers Aiko.", "tells Aiko that the queue is moving"),
        M("test:api-client passed (2m10s)", "09:02 Marek (Search): is main red? my PR shows a big red X",
          "Lena opens the link Marek pasted.",
          "opens the link Marek pasted after he asks whether main is red because his PR shows a big red X"),
        M("test:billing passed (2m51s)", "09:03 Lena: that's lint on your branch, not main",
          "Lena replies to Marek.", "tells Marek the red X is lint on his own branch"),
        M("test:auth passed (3m20s)", "09:04 Marek: oops, unused import. thanks",
          "Lena sips her coffee.", "sips coffee as the auth tests pass"),
        M("test:search still running (7 min so far); e2e:web on shard 3 of 4", "09:05 Aiko: ty!",
          "Lena skims the e2e shard timings.", "skims the e2e shard timings"),
    ]),
    (6, [  # test:search fails (known flake in canonical)
        M("test:search failed after 8m02s; e2e:web and build still running", "09:06 ci-bot: #5120 test:search failed",
          "Lena clicks into the test:search failure summary.", "opens the failure summary of the search job"),
        M("e2e:web on shard 4 of 4; build running", "09:07 Marek: search again? 🙃",
          "Lena reads the failing test's name.", "reads the name of the failing search test"),
        M("build passed (4m12s)", "09:08 Aiko: #2232 is waiting on this, right?",
          "Lena scrolls through the quarantine page in the wiki.", "scrolls through the quarantine page"),
        M("e2e:web: 3 of 4 shards passed (shard 3: 2m41s)", "09:09 Lena: one sec",
          "Lena hovers over the job's menu without clicking.", "hovers over the search job's menu"),
    ]),
    (10, [  # rerun, #5120 green, #5121 starts for #2232; t15-19 hold under a busy channel
        M("test:search attempt 2 running (started 09:10); e2e:web shard 4 still running", "09:10 Lena: rerunning test:search",
          "Lena clicked the job's re-run button.", "has started a second attempt of the search job"),
        M("test:search attempt 2: 41 of 58 tests done", "09:11 Marek: fingers crossed",
          "Lena watches attempt 2 tick through the tests.", "watches the second attempt work through the tests"),
        M("test:search attempt 2 passed (1m55s); e2e:web shard 4 still running", "09:12 Lena: search is green on the retry",
          "Lena posts the retry result.", "posts that the search job is green on the retry"),
        M("e2e:web passed; #5120 finished", "09:13 ci-bot: #5120 passed",
          "Lena marks #5120 green in the sheriff log.", "marks the pipeline green in the sheriff log"),
        M("#5121 queued its jobs", "09:14 merge-queue: merged #2232",
          "Lena watches #5121 start.", "watches the next pipeline start after the queue merged #2232"),
        M("lint and typecheck running; the test jobs are restoring the build cache (1.2 GB in 41 s)",
          ["09:15 Omar (Payments): the rounding change is live on main 🎉", "09:15 Kenji (Payments): three sprints of invoice work, finally",
           "09:15 Aiko: congrats you two! 🥳"],
          "Lena reacts to Omar's message with a party emoji.",
          "reacts with a party emoji as Omar announces that the rounding change is live on main, Kenji says it took three sprints of "
          "invoice work and Aiko congratulates them both, while lint and typecheck run and the test jobs restore their build cache"),
        M("lint passed (48s); typecheck at 70%; build cache hit rate 94%",
          ["09:16 Aiko: when's the release cut again?", "09:16 Marek: and is it cut from main or from a branch?", "09:16 Jonas (Platform): always main"],
          "Lena checks the release calendar.",
          "checks the release calendar as Aiko asks when the release cut is, Marek wonders whether it is cut from main or from a branch "
          "and Jonas answers that it is always main; lint has passed and typecheck is most of the way through"),
        M("typecheck passed (1m32s); test:web, test:ui-kit, test:billing, test:api-client, test:search and test:auth started; e2e:web is provisioning 4 shards",
          ["09:17 Lena: 10:15, Tomasz is cutting", "09:17 Tomasz (Release): correct, 10:15 sharp, the release notes are in the doc",
           "09:17 Aiko: I'll try to get my banner in before that 🤞"],
          "Lena types a reply to Aiko.",
          "tells Aiko the release cut is at 10:15; Tomasz confirms 10:15 sharp and points to the release notes, and Aiko hopes to get her "
          "banner in first, as typecheck passes and all the unit test jobs start"),
        M("test:ui-kit passed (1m51s); test:billing 212 of 340 tests done; e2e:web shard 1 of 4 running",
          ["09:18 Tomasz: please keep main green until then 🙏", "09:18 Marek: famous last words",
           "09:18 Omar: billing's own suite looks fine so far"],
          "Lena gives Tomasz a thumbs-up.",
          "gives Tomasz a thumbs-up when he asks for main to stay green; Marek jokes about famous last words and Omar reports that "
          "billing's own tests look fine so far, while the component-library job passes and the first e2e shard runs"),
        M("test:billing passed (2m51s); test:api-client passed (2m07s); test:search 30 of 58 tests done",
          ["09:19 Jonas (Platform): anyone read the new undici changelog? big one", "09:19 Jonas: lots of changes to how errors are shaped",
           "09:19 Marek: I only read changelogs after they break something"],
          "Lena skims the undici changelog Jonas linked.",
          "skims the undici changelog Jonas linked after he says it changes how errors are shaped, while Marek admits he only reads "
          "changelogs once something breaks; the billing and HTTP-client unit jobs have passed"),
    ]),
    (20, [  # test:web fails (its top in-repo frame is in packages/billing) while the queue is merging
        M("test:web failed after 3m02s; test:search, test:auth and e2e:web still running", "09:20 ci-bot: #5121 test:web failed",
          "Lena opens the test:web failure summary.", "opens the failure summary of the web unit-test job"),
        M("test:search passed; test:auth and e2e:web running", "09:21 Aiko: web tests flaking again? the coupon one does that sometimes",
          "Lena reads Aiko's message.", "reads Aiko asking whether the web tests are flaking again, since the coupon test does that sometimes"),
        M("test:auth passed; e2e:web running", "09:22 Marek: is #2234 going in next?",
          "Lena compares the failed test's name with the quarantine list.",
          "compares the failed test with the quarantine list while Marek asks whether #2234 goes in next"),
        M("e2e:web: shard 1 of 4 passed (2m02s)", "09:23 Aiko: hm, it's an invoice total test, not the coupon one",
          "Lena opens the merge queue settings page.",
          "opens the merge queue settings as Aiko notices that the failure is an invoice total test, not the coupon one"),
    ]),
    (24, [  # queue paused; one commit touched billing; at t27 Payments' open fix PR goes on the board
        M("e2e:web shards running; build passed", "09:24 merge-queue: paused by Lena",
          "Lena paused the queue and turns back to the failure.", "has paused the queue and turns back to the failure"),
        M("e2e:web: 2 of 4 shards passed (shard 2: 2m20s)", "09:25 Aiko: 😢 ok",
          "Lena runs git log for the commits since 4be21c0.", "lists the commits that landed since the last green build"),
        M("e2e:web: 3 of 4 shards passed (shard 3: 2m38s)", "09:26 Omar: 1249 vs 1250 is exactly what banker's rounding does to a half cent 🤔",
          "Lena reads the diff of b7e19d4.",
          "reads the diff of the rounding commit while Omar remarks that 1249 against 1250 is exactly what banker's rounding does to a half cent"),
        M("e2e:web: 4 of 4 shards passed; test:web is the only failed job", "09:27 Omar: fyi PAY-88 on the known-issues board covers this exact test",
          "Lena reads the new board entry.", "reads the new PAY-88 entry that Omar points to on the known-issue tracker, which covers this exact test"),
        M("#5121 finished: failed (test:web)", "09:28 Tomasz: main needs to be green by 10:15",
          "Lena starts a message in #ci-main but has not sent it.",
          "starts a message in #ci-main without sending it while Tomasz reminds everyone that main must be green by 10:15"),
        M("no jobs running on main; #5121 is the latest pipeline", "09:29 Aiko: anything I can do?",
          "Lena opens PR #2238 to read Kenji's fix.", "opens Kenji's fix PR to read it"),
    ]),
    (30, [  # Omar takes the failure and lands Kenji's fix; #5122 green; queue resumed; #5123 for the batch
        M("", "09:30 Lena: thanks Omar, it's yours",
          "Lena reads Omar's announcement.", "reads Omar's message that he is taking the failure and landing Kenji's fix",
          side="PR #2238 (billing): checks running, lint done"),
        M("", "09:31 Omar: need one approval on #2238, anyone?",
          "Lena reviews #2238.", "reviews Kenji's fix PR as Omar asks for an approval",
          side="PR #2238: unit tests running"),
        M("", "09:32 Lena: approved",
          "Lena approves #2238.", "approves the fix PR",
          side="PR #2238: checks passed, approved by Lena"),
        M("#5122 queued its jobs", "09:33 ci-bot: #5122 started",
          "Omar merged #2238; Lena watches #5122 start.", "watches the pipeline for Kenji's fix start after Omar merges it"),
        M("lint running", "09:34 Aiko: coffee run, anyone?",
          "Lena orders a flat white from Aiko.", "orders a flat white from Aiko"),
        M("lint and typecheck passed", "09:35 Omar: #2238 also adds a test for the half-cent case",
          "Lena updates the sheriff log.", "updates the sheriff log"),
        M("test:ui-kit and test:billing passed; test:web running", "09:36 Tomasz: 🙏",
          "Lena refreshes the pipeline page.", "refreshes the pipeline page"),
        M("e2e:web shard 2 is retrying one test (Playwright retry, attempt 2 of 3); the job is still running",
          "09:37 Aiko: e2e shard 2 says 'retrying', is that bad?",
          "Lena looks at shard 2.", "looks at an e2e shard that is retrying a test after Aiko asks whether that is bad"),
        M("e2e:web shard 2: the retried test passed on attempt 2; the job is still running", "09:38 Marek: retries make me nervous, is main ok?",
          "Lena keeps shard 2 open.", "keeps the retrying shard open as Marek asks nervously whether main is ok"),
        M("test:web passed (2m48s); test:search 40 of 58 tests done; e2e:web shards 1 and 2 passed",
          ["09:39 Omar: invoice totals green again 👌", "09:39 Kenji: and my new half-cent test passes too", "09:39 Tomasz: 🙏🙏"],
          "Lena ticks test:web off in the sheriff log.",
          "ticks the web unit tests off in the sheriff log as Omar reports that invoice totals are green again, Kenji adds that his new "
          "half-cent test passes too and Tomasz sends thanks"),
        M("test:search and test:auth passed (5m51s, 3m18s); e2e:web shard 3 running",
          ["09:40 Marek: queue back soon?", "09:40 Lena: once #5122 is green", "09:40 Marek: 👍 #2236 is ready whenever"],
          "Lena replies to Marek.",
          "tells Marek the queue returns once the pipeline is green, and Marek says his PR #2236 is ready whenever, while the search "
          "and auth jobs pass"),
        M("e2e:web: 3 of 4 shards passed (shard 3: 2m44s); build running",
          ["09:41 Jonas: I'll look at the undici upgrade after lunch", "09:41 Aiko: is #2234 the undici one? it's batched with my banner",
           "09:41 Jonas: yes, a lockfile bump for api-client, should be harmless"],
          "Lena drinks the flat white Aiko brought.",
          "drinks the flat white Aiko brought while Jonas plans to look at the undici upgrade after lunch and tells Aiko that #2234, "
          "batched with her banner, is a lockfile bump for the HTTP client that should be harmless"),
        M("e2e:web shard 4 running; build passed (4m09s)",
          ["09:42 Aiko: 🙌 coffee is on the counter", "09:42 Omar: thanks for the quick review this morning, Lena",
           "09:42 Lena: np, thanks for jumping on it"],
          "Lena keeps the pipeline page open.",
          "keeps the pipeline page open as Aiko points to the coffee, Omar thanks her for the quick review and she thanks him for "
          "jumping on it"),
        M("e2e:web passed (4 of 4 shards); #5122 finished",
          ["09:43 ci-bot: #5122 passed", "09:43 Tomasz: 🎉 green with 32 minutes to spare", "09:43 Aiko: can the queue go now?"],
          "Lena marks #5122 green.",
          "marks the pipeline for Kenji's fix green as Tomasz celebrates having 32 minutes to spare and Aiko asks whether the queue can go now"),
        M("no pipeline running on main since #5122 finished", "09:44 merge-queue: resumed by Lena",
          "Lena resumed the queue.", "resumes the merge queue"),
        M("#5123 queued its jobs", "09:45 merge-queue: merged #2234 and #2235 as a batch",
          "Lena watches #5123 start.", "watches the pipeline for the merged batch start"),
        M("lint passed; typecheck running", "09:46 Aiko: my retry banner is in!",
          "Lena congratulates Aiko.", "congratulates Aiko on her merged banner"),
        M("typecheck passed (1m29s); unit and e2e jobs running",
          "09:47 merge-queue: #2236 failed its own queue checks (lint on the PR branch) and was removed from the queue",
          "Lena glances at the merge-queue notification.", "glances at a notice that a queued PR failed its own checks and left the queue"),
        M("unit test jobs passing so far; e2e:web running", "09:48 Marek: that was mine again, sorry, fixing the lint",
          "Lena reads Marek's message.", "reads Marek's apology about his PR's lint"),
        M("e2e:web: shard 1 of 4 passed (1m58s)", "09:49 Aiko: shard 2 is the checkout one 👀",
          "Lena opens the e2e shard view.", "opens the e2e shard view"),
    ]),
    (50, [  # e2e:web fails; trace points into packages/api-client
        M("e2e:web failed (shard 2); build running", "09:50 ci-bot: #5123 e2e:web failed",
          "Lena opens the e2e failure summary.", "opens the e2e failure summary"),
        M("build passed (4m05s)", "09:51 Aiko: that's my banner test 😬",
          "Lena reads the stack trace in the summary.", "reads the stack trace in the failure summary"),
        M("#5123 finished: failed (e2e:web)", "09:52 Tomasz: 23 minutes to the cut",
          "Lena checks the merge queue page.", "checks the merge queue page"),
        M("no jobs running on main; #5123 is the latest pipeline", "09:53 merge-queue: testing #2237 for merge",
          "Lena opens the merge queue settings.", "opens the merge queue settings again"),
    ]),
    (54, [  # queue paused; no culprit commit in api-client, no fix yet
        M("#5123: 9 of 10 jobs passed, e2e:web failed", "09:54 merge-queue: paused by Lena",
          "Lena paused the queue.", "has paused the queue"),
        M("e2e:web artifacts available: trace.zip and a video", "09:55 Aiko: should I revert my banner PR?",
          "Lena compares the commit list with the stack trace.", "compares the commit list with the stack trace while Aiko offers to revert her PR"),
        M("e2e:web full log: 4,812 lines", "09:56 Lena: not yet, give me a minute",
          "Lena rereads the summary rather than the full log.", "rereads the summary rather than the full log"),
        M("the retry banner test failed on all 3 Playwright attempts", "09:57 Marek: lint fixed, re-queued #2236",
          "Lena reads Marek's update.", "reads that Marek re-queued his PR"),
        M("e2e:web trace.zip: the checkout request got a 503, then the banner crashed reading its retry-after header", "09:58 Jonas: wait, is this undici?",
          "Lena pings Jonas in the thread.", "pings Jonas, who suspects undici"),
    ]),
    (59, [  # Jonas posts the fix
        M("no pipeline running on main; #5123 is still the latest", "09:59 Jonas: found it 🎯 see thread",
          "Lena opens Jonas's thread reply.", "opens Jonas's reply in the thread"),
        M("#5123 remains the latest main pipeline", "10:00 Omar: heading into my 10:00",
          "Lena reads Jonas's patch.", "reads Jonas's patch"),
        M("", "10:01 Aiko: so not my PR? phew",
          "Lena reads the two changed lines.", "reads the two changed lines of the patch",
          side="Jonas's patch: 1 file changed, 2 insertions(+), 2 deletions(-)"),
        M("", "10:02 Jonas: I tested it against the failing e2e locally, green",
          "Lena checks out a new local branch from main.", "checks out a new local branch",
          side="Jonas's patch applies cleanly to main"),
        M("", "10:03 Tomasz: 12 minutes",
          "Lena copies the patch into the branch.", "copies the patch into her branch",
          side="local branch sheriff/undici-retry created from main"),
    ]),
    (64, [  # Lena applies the fix; #5124 green; release cut; RC pipeline #5125; t71-76 hold under a busy channel
        M("", "10:04 Jonas: 🙏",
          "Lena opened PR #2243 with Jonas's patch.", "opens a PR with Jonas's patch and says so in the channel",
          side="PR #2243 opened; checks running"),
        M("", "10:05 Aiko: I'll add a test for the header case later",
          "Lena asks Jonas for a review.", "asks Jonas to review the PR",
          side="PR #2243: checks running"),
        M("", "10:06 Jonas: approved",
          "Lena merges #2243.", "merges the fix PR",
          side="PR #2243: checks passed"),
        M("#5124 queued its jobs", "10:07 ci-bot: #5124 started",
          "Lena watches #5124.", "watches the pipeline for the fix start"),
        M("lint passed (51s)", "10:08 Marek: queue?",
          "Lena tells Marek the queue stays paused until #5124 is green.", "tells Marek the queue stays paused for now"),
        M("typecheck passed (1m31s)", "10:09 Aiko: ☕",
          "Lena stretches.", "stretches at her desk"),
        M("test:search running", "10:10 Marek: can someone rerun the flaky search test on my branch? it timed out again",
          "Lena reads Marek's request.", "reads Marek asking for a rerun of a flaky search test on his branch"),
        M("test:ui-kit, test:web and test:billing passed; test:api-client running",
          ["10:11 Lena: that's your branch, hit re-run on your PR", "10:11 Marek: done, and it's green 🙃", "10:11 Aiko: flaky tests are a lifestyle"],
          "Lena writes back to Marek.",
          "tells Marek to rerun it on his own PR, which he does and gets green, while Aiko quips that flaky tests are a lifestyle; the "
          "component-library, web and billing jobs have passed"),
        M("test:api-client passed (2m14s); test:search 20 of 58 tests done",
          ["10:12 Jonas: api-client green with the new undici 🎉", "10:12 Jonas: I'll write up the err.cause change for the changelog",
           "10:12 Omar: nice catch this morning"],
          "Lena adds a line to the sheriff log.",
          "adds a line to the sheriff log as Jonas celebrates the HTTP client passing with the new undici and promises a changelog note "
          "about the err.cause change, and Omar compliments the catch"),
        M("test:search and test:auth passed (6m02s, 3m09s); e2e:web shards 1 and 2 running",
          ["10:13 Tomasz: 2 minutes to the cut, how's main?", "10:13 Lena: all unit jobs green, e2e still going", "10:13 Tomasz: ok, holding"],
          "Lena checks the e2e shards.",
          "checks the e2e shards and tells Tomasz, who has two minutes to the cut, that every unit job is green and e2e is still going; "
          "he says he is holding"),
        M("e2e:web: 2 of 4 shards passed (shard 2: 2m17s); build running",
          ["10:14 Lena: last e2e shards running", "10:14 Aiko: shard 2 has my banner test, and it passed 🎉",
           "10:14 Marek: can #2236 go in after the cut?"],
          "Lena answers Tomasz.",
          "reports that the last e2e shards are running as Aiko cheers her banner test passing in shard 2 and Marek asks whether his PR "
          "can go in after the cut"),
        M("e2e:web: 3 of 4 shards passed (shard 3: 2m36s); build passed",
          ["10:15 Tomasz: I'll cut from the next green run. Keep the queue paused until 10:40 please", "10:15 Lena: 👍 queue stays paused",
           "10:15 Marek: fine, after 10:40 then"],
          "Lena acknowledges Tomasz.",
          "agrees to keep the queue paused until 10:40 for the release cut, which Tomasz will take from the next green run, and Marek "
          "accepts waiting until then"),
        M("e2e:web shard 4 running (checkout specs)",
          ["10:16 Aiko: last shard, come on", "10:16 Jonas: my money's on green", "10:16 Tomasz: release notes are ready either way"],
          "Lena watches the last e2e shard.",
          "watches the last e2e shard with Aiko urging it on, Jonas betting on green and Tomasz saying the release notes are ready either way"),
        M("e2e:web passed; #5124 finished", "10:17 ci-bot: #5124 passed",
          "Lena marks #5124 green.", "marks the fix pipeline green"),
        M("no pipeline running on main since #5124 finished", "10:18 docs-bot: pushed 1e77b0a 'auth: sync the cert rotation guide from the wiki' [skip ci]",
          "Lena notices the docs-bot push.", "notices a push from the docs bot to main"),
        M("#5125 queued its jobs", "10:19 Tomasz: running the release-candidate pipeline on main now",
          "Lena watches #5125 start.", "watches the release-candidate pipeline start"),
        M("lint passed (46s)", "10:20 Priya (Identity): morning all",
          "Lena says hi to Priya.", "greets Priya"),
        M("typecheck passed (1m33s)", "10:21 Omar: back from my meeting, thanks for the patience this morning",
          "Lena reads Omar's greeting.", "reads Omar's thanks for the morning"),
        M("test:ui-kit, test:web, test:billing and test:api-client passed", "10:22 Tomasz: 🤞",
          "Lena refreshes the pipeline.", "reloads the pipeline page"),
        M("test:search passed; test:auth running", "10:23 Jonas: lunch at 12?",
          "Lena replies to Jonas.", "answers Jonas about lunch"),
    ]),
    (84, [  # test:auth fails in the release-candidate run; queue held for the cut
        M("test:auth failed after 3m05s; e2e:web running", "10:24 ci-bot: #5125 test:auth failed",
          "Lena opens the auth failure summary.", "opens the auth failure summary"),
        M("e2e:web: shard 1 of 4 running", "10:25 Tomasz: 😬 that's the RC",
          "Lena reads the stack trace.", "reads the stack trace"),
        M("e2e:web: shard 1 of 4 passed (2m05s)", "10:26 Aiko: could it be the auth docs commit from earlier?",
          "Lena opens 1e77b0a's file list.", "opens the file list of the commit after Aiko wonders whether the earlier auth docs commit caused it"),
        M("e2e:web: 2 of 4 shards passed (shard 2: 2m22s)", "10:27 Lena: that one only changed a markdown guide",
          "Lena answers Aiko's question.", "tells Aiko that commit only changed a markdown guide"),
        M("e2e:web: 3 of 4 shards passed (shard 3: 2m40s)", "10:28 Tomasz: I can wait ten minutes for the cut",
          "Lena checks the Identity team's on-call rota.", "checks who is on call for Identity"),
        M("build passed; e2e:web shard 4 running", "10:29 Priya: reading the channel now",
          "Lena starts typing a message to Priya.", "starts typing a message to Priya"),
    ]),
    (90, [  # Identity takes the failure; their fix goes in
        M("e2e:web passed; test:auth is the only failed job", "10:30 Tomasz: 👀",
          "Lena reads Priya's message.", "reads Priya's message that Identity is taking the failure"),
        M("#5125 finished: failed (test:auth)", "10:31 Lena: thanks Priya, it's yours",
          "Lena notes the handover in the sheriff log.", "notes the handover to Identity in the sheriff log"),
        M("no jobs running on main; #5125 is the latest pipeline", "10:32 Priya: new cert generated, one-year validity",
          "Lena watches Priya's branch.", "watches Priya's branch"),
        M("", "10:33 Aiko: that was quick 👏",
          "Lena reviews the diff of #2251.", "reviews Identity's fix PR, which Priya has just shared",
          side="PR #2251 (Identity): checks running"),
        M("", "10:34 Marek: shouldn't we pause the queue or something?",
          "Lena reads Marek's question.", "reads Marek asking whether to pause the queue",
          side="PR #2251: test:auth passed"),
        M("", "10:35 Lena: it's already paused for the cut",
          "Lena answers Marek.", "tells Marek the queue is already paused",
          side="PR #2251: all checks passed"),
        M("", "10:36 Priya: merging",
          "Lena approves #2251.", "approves Identity's PR",
          side="PR #2251 approved by Lena"),
        M("#5126 queued its jobs", "10:37 ci-bot: #5126 started",
          "Lena watches #5126 start.", "watches the pipeline for Identity's fix start"),
        M("lint passed (49s)", "10:38 Tomasz: cutting from #5126 if it's green",
          "Lena writes the handover note for the afternoon sheriff.", "writes the handover note for the afternoon sheriff"),
        M("typecheck passed (1m35s); all test jobs started", "10:39 Priya: thanks for the quick handoff",
          "Lena posts the sheriff handover note.", "posts the handover note for the afternoon sheriff"),
    ]),
)

# Irrelevant office details for the lexical-decoy register, keyed by the action
# whose vocabulary they borrow. None of them concerns main, its pipelines,
# commits, packages or the merge queue.
B_DECOYS = {
    "watch": [
        "In the kitchen, someone is watching the kettle and suggesting nothing for now.",
        "The lobby TV keeps watching the marathon; nothing for now on the news ticker.",
        "A designer says she will keep watching the sunset from the terrace and suggest nothing.",
        "The office dog keeps watching the door; nothing for now from reception.",
        "The events team is watching the weather for Friday's picnic, nothing to suggest yet.",
    ],
    "rerun": [
        "The all-hands recording is rerunning at 16:00 for the Singapore office.",
        "The canteen is rerunning its pizza survey because the first job was botched.",
        "A TV in the break room is rerunning last night's cup final.",
        "The People team is rerunning the failed raffle draw for the offsite.",
        "The podcast crew is rerunning a failed recording job in studio B.",
    ],
    "inspect": [
        "Facilities are opening the full log book of the fire doors for their inspection.",
        "Someone is opening the full log of the office thermostat to see why it failed.",
        "The fitness room's treadmill failed; the vendor is opening its full log.",
        "Reception is opening the full visitor log for a failed badge scan.",
        "IT is opening the full log of the failed printer job on floor 4.",
    ],
    "revert": [
        "Marketing is reverting the brochure to the commit before the new logo.",
        "Someone is reverting the office playlist; the last commit to it touched only jazz.",
        "The wiki admin is reverting the commit that touched the holiday calendar page.",
        "Design is reverting the colour palette to Tuesday's commit.",
        "The social team is reverting the newsletter template commit from Monday.",
    ],
    "apply_fix": [
        "IT posted a fix for the Wi-Fi drops and is applying it on floor 3 tonight.",
        "Facilities are applying the posted fix to the squeaky meeting-room door.",
        "The coffee machine vendor posted a fix, and the office manager is applying it.",
        "Payroll is applying the posted fix to the expense form.",
        "HR is applying the posted fix to the parking-permit form.",
    ],
    "pause": [
        "The coffee machine queue is pausing for descaling until the main tank is sorted out.",
        "The lift queue in the lobby is pausing while the main elevator gets sorted out.",
        "Reception is pausing the visitor queue until the main badge printer is sorted out.",
        "The canteen is pausing its lunch queue until the main oven is sorted out; the two queues merge later.",
        "The bike-rack waiting queue is pausing until facilities sort out the main gate.",
    ],
    "handoff": [
        "Reception is handing the lost umbrella to its owning team on floor 2.",
        "The events team is handing the offsite failure report to the owning team at the venue.",
        "Facilities are handing the broken chair to the team owning the furniture budget.",
        "The office manager is handing the mailroom failure to the owning team downstairs.",
        "Security is handing the forgotten laptop to its owning team in finance.",
    ],
}
# Decoys aimed at the target question: package-like words in irrelevant places.
B_DECOYS_EXTRA = [
    "The design-systems meetup poster says 'bring your favourite ui-kit sticker'.",
    "Finance's billing department ordered new chairs for their floor.",
    "The office search for a missing stapler is still on.",
    "The web team's lunch booking is for 12:30 at the ramen place.",
    "The badge reader's auth light is blinking again at the side door.",
]


def _pipe(pid: int, started: str, sha: str, what: str, what_p: str) -> dict[str, Any]:
    return {"id": pid, "started": started, "sha": sha, "what": what, "what_p": what_p}


def _queue(state: str, note: str, note_p: str) -> dict[str, Any]:
    return {"state": state, "note": note, "note_p": note_p}


P5120 = _pipe(5120, "08:57", "4be21c0", "#2231 'ui-kit: add a delay prop to Tooltip'", "the Tooltip delay change from #2231")
P5121 = _pipe(5121, "09:14", "b7e19d4", "#2232 'billing: switch invoice rounding to banker's rounding'", "the banker's-rounding change from #2232")
P5122 = _pipe(5122, "09:33", "e0c5a91", "#2238 'billing: round half-cent totals correctly'", "Kenji's half-cent repair from #2238")
P5123 = _pipe(5123, "09:45", "5d2a7e1", "the merged batch #2234 + #2235", "the batch that landed #2234 and #2235 together")
P5124 = _pipe(5124, "10:07", "7f3e0d1", "#2243 'api-client: read retry-after from the new undici error shape'", "#2243, the retry-after change in the HTTP client")
P5125 = _pipe(5125, "10:19", "1e77b0a", "the release-candidate run Tomasz requested", "the release-candidate check Tomasz asked for")
P5126 = _pipe(5126, "10:37", "3aa91c7", "#2251 'auth: rotate the TLS test fixture certificate'", "#2251, Identity's certificate rotation")
P5126_CF = _pipe(5126, "10:37", "3aa91c7", "#2251 'auth: load the long-lived TLS fixture certificate by default again'",
                 "#2251, Identity's repair of the TLS test server")

Q0 = _queue("merging", "next up: #2232; waiting: #2232, #2234, #2235 and #2236", "#2232 lands next, with #2234, #2235 and #2236 behind it")
Q14 = _queue("merging", "merged #2232 at 09:14; next up: #2234; waiting: #2234, #2235 and #2236", "#2232 landed at 09:14 and #2234 is next, then #2235 and #2236")
Q24 = _queue("paused", "paused by Lena at 09:24; waiting: #2234, #2235 and #2236", "Lena froze it at 09:24 with #2234, #2235 and #2236 still in line")
Q44 = _queue("merging", "resumed by Lena at 09:44; next up: #2234 and #2235 as a batch (their queue checks passed while it was paused); also waiting: #2236",
             "Lena unfroze it at 09:44; #2234 and #2235, whose queue checks passed during the freeze, go next as one batch, then #2236")
Q45 = _queue("merging", "merged #2234 and #2235 at 09:45; next up: #2236; also waiting: #2237", "#2234 and #2235 landed together at 09:45; #2236 is next, then #2237")
Q47 = _queue("merging", "#2236 was removed at 09:47 after its own checks failed; next up: #2237", "#2236 dropped out at 09:47 when its own checks went red; #2237 is next")
Q54 = _queue("paused", "paused by Lena at 09:54; waiting: #2237", "Lena froze it at 09:54 with #2237 in line")
Q57 = _queue("paused", "paused by Lena at 09:54; waiting: #2236 (re-queued at 09:57) and #2237", "Lena froze it at 09:54; #2236 (back in line since 09:57) and #2237 are waiting")
Q75 = _queue("paused", "paused by Lena at 09:54; at 10:15 Tomasz (release manager) asked for it to stay paused until the release cut is done at 10:40; waiting: #2236 and #2237",
             "Lena froze it at 09:54, and since 10:15 Tomasz, the release manager, wants it kept frozen until his release cut finishes at 10:40; #2236 and #2237 are waiting")

CL30 = {"who": "Omar (Payments)", "at": "09:30", "text": "Taking this one: I'm landing Kenji's #2238 on main now, it fixes the half-cent case.",
        "text_p": "Omar from Payments announced that he is taking this breakage over and landing Kenji's fix PR #2238 on main right away."}
CL64 = {"who": "Lena", "at": "10:04", "text": "Applying Jonas's patch now as PR #2243.",
        "text_p": "Lena announced that she is landing Jonas's patch right now as PR #2243."}
# structural_cf: api-client belongs to Web there, so Lena says Web asked her to land it.
CL64_SCF = {"who": "Lena", "at": "10:04", "text": "Web asked me to land it for them: applying Jonas's patch now as PR #2243.",
            "text_p": "Lena announced that the Web team had asked her to land Jonas's patch for them and that she is doing so right now as PR #2243."}
# The fixture certificate expires at 10:20: after #5124's test:auth passed
# (10:13) and before #5125's test:auth ran (10:21-10:24).
CL90 = {"who": "Priya (Identity)", "at": "10:30", "text": "That one's ours: the auth test fixture certificate expired at 10:20. We're taking it over and rotating the cert now.",
        "text_p": "Priya from Identity said the breakage belongs to her team because the auth fixture certificate ran out at 10:20, and that Identity is taking it over and replacing the certificate now."}
CL90_CF = {"who": "Priya (Identity)", "at": "10:30",
           "text": "That one's ours: my 10:18 change made the TLS test server load the short-lived expiry-test cert. We're taking it over and fixing it now.",
           "text_p": "Priya from Identity said the breakage belongs to her team because her 10:18 change made the TLS test server load a short-lived certificate meant for expiry tests, and that Identity is taking it over and fixing it now."}
FIX93 = {"who": "Priya (Identity)", "at": "10:33", "text": "PR #2251 is up: new fixture cert and key with one-year validity, needs one approval.",
         "text_p": "Priya from Identity shared her fix, PR #2251, with a new fixture certificate and key valid for a year, and asked for one approval."}
FIX93_CF = {"who": "Priya (Identity)", "at": "10:33", "text": "PR #2251 is up: tls.ts loads the long-lived fixture cert by default again, needs one approval.",
            "text_p": "Priya from Identity shared her fix, PR #2251, which makes tls.ts load the long-lived fixture certificate by default again, and asked for one approval."}
FIX59 = {"who": "Jonas (Platform)", "at": "09:59", "text": "Fix for the e2e failure: undici 6.21 moved the response onto err.cause, so line 41 of packages/api-client/src/retry.ts should read err.cause?.headers instead of err.response.headers. Patch is in the thread.",
         "text_p": "Jonas from Platform posted a repair for this e2e breakage: since undici 6.21 keeps the response on err.cause, line 41 of retry.ts in packages/api-client has to use err.cause?.headers rather than err.response.headers; his patch is attached in the thread."}


def _frame_pkg(frames: list[str]) -> str | None:
    """The package of the first in-repo frame (definition (b) of the rules)."""
    for frame in frames:
        path = frame[frame.index("(") + 1:] if "(" in frame else frame[3:]
        for key, directory in B_DIRS.items():
            if path.startswith(directory + "/"):
                return key
    return None


def _test_p(name: str) -> str:
    """A test id such as 'search › indexer.spec.ts › rebuilds shard map' in the paraphrase register."""
    parts = name.split(" › ")
    return f"the '{parts[-1]}' case of {' / '.join(parts[:-1])}"


def _frame_p(frame: str) -> str:
    body = frame[3:]
    fn = None
    if " (" in body:
        fn, body = body[: body.index(" (")], body[body.index(" (") + 2: -1]
    location, line = body.rsplit(":", 2)[0], body.rsplit(":", 2)[1]
    if location.startswith("node:"):
        where = f"Node's internal {location[5:]} module"
    elif location.startswith("node_modules/"):
        where = "library code inside node_modules (" + location.split("/node_modules/")[-1].split("/")[0] + ")"
    else:
        where = location
    return f"{fn} in {where}, line {line}" if fn else f"{where}, line {line}"


def _paths_p(paths: list[str]) -> str:
    groups: dict[str, list[str]] = {}
    for path in paths:
        home = next((d for d in B_DIRS.values() if path.startswith(d + "/")), None)
        if home is None:
            home = path.split("/")[0] if "/" in path else "the repository root"
        rest = path[len(home) + 1:] if path.startswith(home + "/") else path
        groups.setdefault(home, []).append(rest)
    return "; ".join(f"{listing(files)} under {home}" if home != "the repository root" else f"{listing(files)} at the repository root"
                     for home, files in groups.items())


def _touched(commit: dict[str, Any], pkg: str) -> bool:
    return any(p.startswith(B_DIRS[pkg] + "/") for p in commit["paths"])


def _swap_commit(ticks: list[Tick], old: dict[str, Any], new: dict[str, Any]) -> None:
    for tk in ticks:
        tk.latent["commits"] = [new if c == old else c for c in tk.latent["commits"]]


class MonorepoSheriff(Scenario):
    family = FAMILY
    scenario_id = "debugging_b"
    title = "Build-sheriff suggestions for red main-branch CI in a TypeScript monorepo"
    tier = "hard"
    difficulty_features = [
        "two_questions_per_decision",
        "categorised_action_options",
        "seven_way_target_choice",
        "eight_rule_priority_policy",
        "priority_conflicts",
        "implicit_failing_package_from_stack_trace",
        "quarantine_and_timeout_matching",
        "commit_path_counting",
        "heavy_distractors",
    ]
    decision_structures = ["maintain", "wait", "recover", "rollback", "escalate", "handoff", "resolve-conflict"]
    deadline_steps = 2

    START = at("09:00")
    TICK_SECONDS = 60

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        # Both questions carry the full definitions and policy: Jev answers
        # each question independently.
        if variant == "paraphrase":
            base = {"role": B_ROLE_P, "definitions": B_DEFINITIONS_P, "rules": B_POLICY_P}
            return [
                Choice("action", {**base, "question": B_Q_ACTION_P}, dict(B_ACTIONS_P)),
                Choice("target", {**base, "question": B_Q_TARGET_P}, dict(B_TARGETS_P)),
            ]
        base = {"role": B_ROLE, "definitions": B_DEFINITIONS, "policy": B_POLICY}
        actions = B_ACTIONS_D if variant == "lexical_decoy" else B_ACTIONS
        return [
            Choice("action", {**base, "question": B_Q_ACTION}, dict(actions)),
            Choice("target", {**base, "question": B_Q_TARGET}, dict(B_TARGETS)),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "now_s": self.START,
                "pipeline": P5120,
                "status": "running",
                "passed_at": None,
                "failure": None,
                "rerun_done": False,
                "queue": Q0,
                "last_green": {"id": 5119, "at": "08:41", "sha": "3f9d2b7"},
                "commits": [C_2231],
                "claim": None,
                "fix_posted": None,
                "open_fix": None,
                "owners": dict(B_OWNERS),
            }
        )
        events: dict[int, tuple[dict[str, Any], str]] = {
            2: ({}, "A red X on Marek's own branch is not main."),
            6: ({"status": "failed", "failure": F_SEARCH}, "Quarantined test timed out: a known flake, not rerun yet (rule 3). No queue pause for a known flake."),
            10: ({"status": "running", "failure": None}, "Lena reruns the job; attempt 2 is running, so no job has failed."),
            13: ({"status": "passed", "passed_at": "09:13"}, "#5120 green."),
            14: ({"pipeline": P5121, "status": "running", "passed_at": None, "last_green": {"id": 5120, "at": "09:13", "sha": "4be21c0"},
                  "commits": [C_DOCS1, C_2232], "queue": Q14}, "Queue merged #2232; #5121 running."),
            20: ({"status": "failed", "failure": F_BILLING},
                 "test:web fails, but its top in-repo frame is packages/billing; not a flake, queue merging: pause (rule 1) over revert (rule 5)."),
            21: ({}, "'Web tests flaking again? the coupon one' - the quarantined coupon test is a different test, and this failure is an assertion, not a timeout."),
            24: ({"queue": Q24}, "Queue paused. The failing package is billing (top in-repo frame), not web (the job). Of the two commits since the last green run only b7e19d4 touched packages/billing: revert (rule 5 over rule 7)."),
            27: ({"open_fix": B_PAY_FIX}, "Kenji's fix PR #2238 (Payments, opened 09:27) goes on the board; Omar only points to it and nobody claims the failure: hand off (rule 4) over revert (rule 5)."),
            30: ({"claim": CL30}, "Omar takes the failure over and lands Kenji's fix: the failure is being handled."),
            33: ({"pipeline": P5122, "status": "running", "failure": None, "claim": None, "open_fix": None, "commits": [C_DOCS1, C_2232, C_2238]}, "Omar merged #2238; #5122 running."),
            37: ({}, "A Playwright in-job retry is not a failed job."),
            43: ({"status": "passed", "passed_at": "09:43", "last_green": {"id": 5122, "at": "09:43", "sha": "e0c5a91"}, "commits": []}, "#5122 green."),
            44: ({"queue": Q44}, "Queue resumed."),
            45: ({"pipeline": P5123, "status": "running", "passed_at": None, "commits": [C_2234, C_2235], "queue": Q45}, "Batch #2234 + #2235 merged; #5123 running."),
            47: ({"queue": Q47}, "A PR failing its own queue checks does not make main red."),
            50: ({"status": "failed", "failure": F_WEB}, "e2e:web fails; the top in-repo frame is in packages/api-client. Queue merging: pause (rule 1) over inspect (rule 8)."),
            54: ({"queue": Q54}, "Queue paused. #2234's title names api-client but it changed only pnpm-lock.yaml: no commit since #5122 touched packages/api-client; no open or posted fix; Platform owns it: inspect the log."),
            55: ({}, "Aiko offers to revert her apps/web PR, but the failing package is packages/api-client."),
            57: ({"queue": Q57}, ""),
            59: ({"fix_posted": FIX59}, "Jonas (Platform) posts a fix for this failure; Platform owns packages/api-client: apply it."),
            64: ({"claim": CL64}, "Lena announces she is applying the fix."),
            67: ({"pipeline": P5124, "status": "running", "failure": None, "claim": None, "fix_posted": None,
                  "commits": [C_2234, C_2235, C_2243]}, "Fix merged; #5124 running."),
            70: ({}, "A flaky search test on Marek's branch is not main."),
            75: ({"queue": Q75}, "Release manager keeps the queue paused until 10:40."),
            77: ({"status": "passed", "passed_at": "10:17", "last_green": {"id": 5124, "at": "10:17", "sha": "7f3e0d1"}, "commits": []}, "#5124 green."),
            78: ({"commits": [C_DOCS2]}, "Docs-only push to main, no pipeline of its own."),
            79: ({"pipeline": P5125, "status": "running", "passed_at": None}, "Release-candidate pipeline on main."),
            84: ({"status": "failed", "failure": F_AUTH}, "Auth failure (fixture cert expired at 10:20); queue already paused; only a docs/ commit (titled 'auth:') since the last green run; Identity owns packages/auth: hand off."),
            86: ({}, "The 'auth:' docs commit changed docs/auth/rotation.md, which is not under packages/auth."),
            90: ({"claim": CL90}, "Identity takes the failure over: watch (rule 2) over hand off (rule 7)."),
            93: ({"fix_posted": FIX93}, "Priya posts her fix PR in #ci-main; the claim (rule 2) still decides."),
            94: ({}, "Suggestion to pause the queue while it is already paused and the failure is claimed."),
            97: ({"pipeline": P5126, "status": "running", "failure": None, "claim": None, "fix_posted": None, "commits": [C_DOCS2, C_2251]}, "Identity's fix merged; #5126 running."),
        }
        tags = span_tags(
            {
                "distractor": [2, 21, 37, 47, 55, 70, 86, 94],
                "minimal_change": [27, 30, 59, 90],
                "recovery": [10, 30, 64],
                "hold_under_activity": [(15, 19), (39, 43), (71, 76)],
                "priority_conflict": [(20, 26), (27, 29), (50, 53), (90, 92)],
                "boundary": [(90, 92), (98, 99)],
                "arithmetic": [(24, 26), (54, 58), (84, 89)],
                "implicit": [(6, 9), (20, 29), (50, 63), (84, 89)],
            }
        )
        for t in range(STEPS):
            updates, note = events.get(t, ({}, ""))
            tl.step(dict(B_SCRIPT[t]), tags[t], note, now_s=self.START + self.TICK_SECONDS * t, **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t6-9: the search test fails an assertion, not a timeout: not a known flake.
            ticks = override(ticks, range(6, 10), failure=F_SEARCH_CF, note="Quarantined test, but it failed an assertion, not a timeout: not a known flake; the queue is merging.")
            # (2) t54-63: #2234 also changed packages/api-client/package.json, so
            # exactly one commit touched the failing package. The title is the
            # same in both variants; only the changed paths differ.
            _swap_commit(ticks, C_2234, C_2234_CF)
            # (3) t84-89: the 10:18 push is Priya's change to the TLS test
            # server under packages/auth (it loads a short-lived certificate),
            # not a docs sync. Her later claim, posted fix and fix commit
            # follow that cause, and the surface lines that assumed a docs
            # push or a plain expiry are rewritten.
            _swap_commit(ticks, C_DOCS2, C_CERT_CF)
            _swap_commit(ticks, C_2251, C_2251_CF)
            for tk in ticks:
                z = tk.latent
                if z["claim"] == CL90:
                    z["claim"] = CL90_CF
                if z["fix_posted"] == FIX93:
                    z["fix_posted"] = FIX93_CF
                if z["pipeline"] == P5126:
                    z["pipeline"] = P5126_CF
            ticks = _swap(ticks, {
                78: M("no pipeline running on main since #5124 finished",
                      "10:18 Priya (Identity): pushed 1e77b0a to main [skip ci], a small tls.ts change for the expiry tests",
                      "Lena notices Priya's push.", "notices Priya's small push to main"),
                80: M("lint passed (46s)", "10:20 Priya: stepping into a sync until 10:30",
                      "Lena waves to Priya.", "waves to Priya as she heads into a sync"),
                86: M("e2e:web: shard 1 of 4 passed (2m05s)", "10:26 Aiko: could it be Priya's tls.ts commit from earlier?",
                      "Lena opens 1e77b0a's file list.", "opens the file list of the commit after Aiko wonders whether Priya's earlier tls.ts commit caused it"),
                87: M("e2e:web: 2 of 4 shards passed (shard 2: 2m22s)", "10:27 Lena: it changed packages/auth/test/fixtures/tls.ts",
                      "Lena answers Aiko's question.", "tells Aiko that commit changed the TLS test fixture code"),
                92: M("no jobs running on main; #5125 is the latest pipeline", "10:32 Priya: tls.ts loads the long-lived cert by default again",
                      "Lena watches Priya's branch.", "watches Priya's branch"),
            })
            # Re-tag: t6-9 and t84-89 keep 'implicit' (the flake check and the
            # stack-trace package are still inferences); t86 is no longer a
            # distractor because Aiko's guess is right here.
            ticks = _set_tags(ticks, {
                6: ["minimal_change", "implicit"], 7: ["implicit"], 8: ["implicit"], 9: ["implicit"],
                54: ["minimal_change", "arithmetic", "implicit"], 55: ["distractor", "arithmetic", "implicit"],
                56: ["arithmetic", "implicit"], 57: ["arithmetic", "implicit"], 58: ["arithmetic", "implicit"],
                59: ["implicit", "priority_conflict"], 60: ["implicit", "priority_conflict"], 61: ["implicit", "priority_conflict"],
                62: ["implicit", "priority_conflict"], 63: ["implicit", "priority_conflict"],
                84: ["minimal_change", "arithmetic", "implicit"], 85: ["arithmetic", "implicit"], 86: ["arithmetic", "implicit"],
                87: ["arithmetic", "implicit"], 88: ["arithmetic", "implicit"], 89: ["arithmetic", "implicit"],
            })
            for t, note in {
                54: "Queue paused. #2234 changed packages/api-client/package.json: exactly one commit touched the failing package, so revert.",
                59: "Jonas posts a fix, but rule 5 (one commit touched packages/api-client) comes first: still revert.",
                78: "Priya pushes a tls.ts change under packages/auth, no pipeline of its own.",
                84: "Auth failure; queue paused; the only commit since the last green run touched packages/auth: revert it.",
                86: "Aiko's guess is right this time: 1e77b0a changed packages/auth/test/fixtures/tls.ts.",
                90: "Priya (Identity) takes the failure over: watch (rule 2) over revert (rule 5).",
            }.items():
                ticks[t].note = note
        elif variant == "structural_cf":
            # Last week's reorg moved packages/api-client from Platform to the
            # Web team. Rule 6 no longer applies to it and rule 7 hands the
            # e2e failure (whose top in-repo frame is in api-client) to Web.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["owners"] = dict(B_OWNERS, api_client="Web")
                if tk.latent["claim"] == CL64:
                    tk.latent["claim"] = CL64_SCF
            # t59-63: only rule 7 matches here (rule 6 needs Platform), so no
            # priority conflict.
            ticks = _set_tags(ticks, {
                54: ["implicit"], 55: ["distractor", "implicit"], 56: ["implicit"], 57: ["implicit"], 58: ["implicit"],
                59: ["implicit"], 60: ["implicit"], 61: ["implicit"], 62: ["implicit"], 63: ["implicit"],
            })
            for t, note in {
                54: "Queue paused. api-client now belongs to the Web team, so rule 7 hands the failure to Web.",
                59: "Jonas posts a fix, but Platform no longer owns api-client: rule 6 does not apply, rule 7 does.",
                64: "Lena announces that Web asked her to land Jonas's patch and she is applying it; the failure is handled.",
            }.items():
                ticks[t].note = note
        self._check(ticks)
        return ticks

    @staticmethod
    def _check(ticks: list[Tick]) -> None:
        """Authored failure facts must agree with the stack trace and the quarantine list."""
        for t, tk in enumerate(ticks):
            f = tk.latent["failure"]
            if f is None:
                continue
            if _frame_pkg(f["frames"]) != f["pkg"]:
                raise ValueError(f"t{t}: failing package {f['pkg']!r} does not match the stack trace")
            if f["quarantined"] != (f["test"] in B_QUARANTINE):
                raise ValueError(f"t{t}: quarantine flag disagrees with the quarantine list")

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        f = z["failure"] if z["status"] == "failed" else None
        flake = f is not None and f["quarantined"] and f["timeout"]
        if f is not None and not flake and z["queue"]["state"] == "merging":
            return {"action": "pause", "target": "none"}
        if f is None or z["claim"] is not None:
            return {"action": "watch", "target": "none"}
        pkg = f["pkg"]
        if flake and not z["rerun_done"]:
            action = "rerun"
        elif (z["open_fix"] is not None and z["open_fix"]["test"] == f["test"]
              and z["open_fix"]["team"] == z["owners"][pkg]):
            action = "handoff"
        elif sum(_touched(c, pkg) for c in z["commits"]) == 1:
            action = "revert"
        elif z["fix_posted"] is not None and z["owners"][pkg] == "Platform":
            action = "apply_fix"
        elif z["owners"][pkg] != "Platform":
            action = "handoff"
        else:
            action = "inspect"
        return {"action": action, "target": pkg}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Build sheriff Lena (Platform) on main, 09:00-10:39, 1 min ticks. A quarantined search test times out (known flake: rerun/search t6-9, no pause); a test:web failure whose top in-repo frame is billing's rounding code, while the queue merges (pause over revert, t20-23); the only commit touching packages/billing gives revert/billing (t24-26, over handoff to Payments by rule 7) until Kenji's fix PR, opened 09:27, goes on the board as Payments' open fix (handoff/billing over revert, t27-29) and Omar takes it over at t30; e2e:web fails with its top in-repo frame in packages/api-client (pause over inspect t50-53; inspect/api_client t54-58, since #2234's 'api-client:' title covers a lockfile-only change and no commit touched api-client); Jonas posts a fix (apply_fix/api_client t59-63) until Lena claims it; an auth fixture certificate that expired at 10:20 fails the release-candidate run while the queue is already held and only an 'auth:'-titled docs/ commit landed (handoff/auth t84-89) until Identity takes it over at t90 (watch over handoff)."},
            "paraphrase": {"summary": "Same latent trajectory; narrated prose with trunk/breakage/landing-queue vocabulary, two or three phrasings per fact and a sentence order that varies by tick; reworded role, definitions, rules, questions, action categories and package labels; chat that carries a lure is reported in the moment's summary."},
            "lexical_decoy": {"summary": "Same latent trajectory; irrelevant office lines borrowing a wrong action's words (rerunning a survey, reverting a brochure commit, pausing the canteen queue, handing a failure report to its owning team), sometimes blended into Lena's line. About half the ticks get a second line, about one tick in five one from the gold action's pool, and some lines aim at the target question (billing department, ui-kit sticker)."},
            "minimal_cf": {"summary": "Three one-fact edits: t6-9 the quarantined search test fails an assertion instead of timing out, so it is not a known flake and the merging queue must be paused (rerun/search -> pause/none); t54-63 #2234 (same title) also changed packages/api-client/package.json, so exactly one commit touched the failing package (inspect and apply_fix -> revert/api_client); t84-89 the 10:18 push is Priya's change to packages/auth/test/fixtures/tls.ts, which makes the TLS test server load a short-lived certificate, instead of a docs sync (handoff/auth -> revert/auth). Her claim, posted fix and fix commit (t90-99) follow that cause."},
            "structural_cf": {"summary": "Constraint changed: last week's reorg moved packages/api-client from Platform to the Web team (ownership table). Rule 6 no longer applies to the e2e failure, whose top in-repo frame is in api-client, so rule 7 hands it to Web (t54-63 inspect/apply_fix -> handoff/api_client). Lena's 10:04 claim says Web asked her to land Jonas's patch for them; it still decides t64-66 under rule 2."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    @staticmethod
    def _ownership(z: dict[str, Any], paraphrase: bool, t: int = 0) -> str:
        owners = z["owners"]
        items = []
        short = pick([True, False], "bp-own", t) if paraphrase else False
        for n, key in enumerate(B_PACKAGES):
            team = owners[key]
            moved = team != B_OWNERS[key]
            if paraphrase:
                name = "the Web team" if team == "Web" else team
                if short:
                    text = f"{B_DIRS[key]}, {name}"
                else:
                    text = f"{B_DIRS[key]} belongs to {name}" if n == 0 else f"{B_DIRS[key]} to {name}"
                if moved:
                    text += f" (last week's reorg moved it over from {B_OWNERS[key]})"
            else:
                text = f"{B_DIRS[key]}: {'Web team' if team == 'Web' else team}"
                if moved:
                    text += f" (moved from {B_OWNERS[key]} in last week's reorg)"
            items.append(text)
        if paraphrase:
            return ("Owning teams: " + "; ".join(items) + ".") if short else ("Code owners: " + listing(items) + ".")
        return "; ".join(items) + "."

    @staticmethod
    def _open_fix_listed(z: dict[str, Any]) -> bool:
        """Whether the board lists an open fix PR for the current failure (definition (e))."""
        return z["status"] == "failed" and z["open_fix"] is not None and z["open_fix"]["test"] == z["failure"]["test"]

    def _issues(self, z: dict[str, Any], paraphrase: bool, t: int) -> str:
        failed = z["status"] == "failed"
        if paraphrase:
            text = pick([
                "The known-issue tracker has DISC-311 from Discovery: search's shard-map test runs out of time at times and is quarantined, no fix planned.",
                "Known-issue tracker: DISC-311 (Discovery), the search shard-map test timing out now and then; quarantined, with no fix planned.",
            ], "bp-disc", t)
            if z["open_fix"] is not None:
                text += " It also lists " + z["open_fix"]["text_p"]
            if failed and not self._open_fix_listed(z):
                text += " " + pick(["The tracker lists no open pull request for the current breakage.",
                                    "No open fix pull request for the current breakage is on the tracker."], "bp-noopen", t)
            return text
        items = [B_DISC_ISSUE]
        if z["open_fix"] is not None:
            items.append(z["open_fix"]["text"])
        text = "Known-issues board: " + " ".join(items)
        if failed and not self._open_fix_listed(z):
            text += " " + pick(["The board lists no open fix PR for the current failure.", "No open fix PR for the current failure is listed.",
                                "Nothing on the board is an open fix PR for the current failure."], "b-noopen", t)
        return text

    def _pipeline(self, z: dict[str, Any], t: int, s: dict[str, Any]) -> str:
        p = z["pipeline"]
        head = f"#{p['id']}, started {p['started']} for {p['what']} (head {p['sha']})."
        if z["status"] == "running":
            status = pick(["No job in it has failed so far.", "Still running; nothing in it has failed yet.", "In progress, with no failed job so far."], "b-run", t)
        elif z["status"] == "passed":
            status = pick([f"Finished green at {z['passed_at']}: every job passed.", f"All jobs passed (finished {z['passed_at']}).", f"Green since {z['passed_at']}; no job failed."], "b-pass", t)
        else:
            job = z["failure"]["job"]
            status = pick([f"It has a failed job: {job}.", f"Red: {job} failed.", f"Job {job} has failed."], "b-fail", t)
        board = f" Job board: {s['ci']}." if s["ci"] else ""
        return f"{head} {status}{board}"

    def _failure(self, z: dict[str, Any], t: int) -> str:
        if z["status"] != "failed":
            return pick(["None: no job in the latest main pipeline has failed.", "No failed job in the latest main pipeline."], "b-nof", t)
        f = z["failure"]
        rerun = pick(["it has not been rerun", "no rerun since", "not rerun yet"], "b-rr", t)
        return (f"{f['job']}: latest attempt failed at {f['at']}; {rerun}. Test: {f['test']}. Failure message: \"{f['error']}\". "
                f"Stack trace, top frame first: {' | '.join(f['frames'])}.")

    def _since_green(self, z: dict[str, Any], t: int) -> str:
        g = z["last_green"]
        head = pick([f"Last green main pipeline: #{g['id']} (tested {g['sha']}, finished {g['at']}).",
                     f"Main was last green in #{g['id']}, which tested {g['sha']} and finished at {g['at']}."], "b-lg", t)
        if not z["commits"]:
            return head + " " + pick([f"No commits have landed on main after {g['sha']}.", f"Nothing has landed on main since {g['sha']}."], "b-nc", t)
        # A path with no directory is a file at the repository root; say so,
        # as the paraphrase register does.
        items = [f"{c['sha']} ({c['at']}, {c['who']}): '{c['title']}', changed "
                 + listing([p if "/" in p else f"{p} (at the repository root)" for p in c["paths"]]) for c in z["commits"]]
        return head + f" Commits on main after {g['sha']}: " + "; ".join(items) + "."

    def _queue_line(self, z: dict[str, Any], t: int) -> str:
        q = z["queue"]
        if q["state"] == "merging":
            state = pick(["still merging", "active and merging PRs", "running (merging)"], "b-qm", t)
        else:
            state = pick(["paused", "paused, not merging", "on hold (paused)"], "b-qp", t)
        return f"Merge queue: {state}; {q['note']}."

    def _channel(self, z: dict[str, Any], t: int, s: dict[str, Any]) -> str:
        parts = []
        if z["status"] == "failed":
            c, fx = z["claim"], z["fix_posted"]
            if c is None:
                # The absence line names all three verbs of rule 2.
                parts.append(pick([
                    "Nobody has said in #ci-main that they are reverting, fixing or taking over this failure.",
                    "No one in #ci-main has said they are reverting, fixing or taking over this failure so far.",
                    "So far nobody in #ci-main has said they are reverting, fixing or taking over this failure.",
                ], "b-nocl", t))
            if fx is None:
                # Rule 6's fact is stated at every red tick, also while the
                # board lists an open fix PR (definition (e) keeps them apart).
                if z["open_fix"] is None:
                    parts.append(pick(["No fix has been posted for it in #ci-main.", "Nobody has posted a fix for it in #ci-main yet."], "b-nofx", t))
                else:
                    parts.append(pick(["No fix has been posted for it in #ci-main itself; its open fix PR is the one on the known-issues board.",
                                       "Nobody has posted a fix for it in #ci-main itself; the open fix PR for it is listed on the known-issues board."],
                                      "b-nofx-board", t))
            # A claim and a posted fix are quoted in time order.
            quoted = sorted((m for m in (c, fx) if m is not None), key=lambda m: at(m["at"]))
            if quoted:
                lead = "Messages in #ci-main about this failure, oldest first: " if len(quoted) > 1 else ""
                parts.append(lead + " | ".join(f"{m['at']} {m['who']}: \"{m['text']}\"" for m in quoted))
        chat = s["chat"]
        if isinstance(chat, list):
            parts.append("Newest messages, oldest first: " + " | ".join(chat))
        else:
            parts.append(f"Newest message: {chat}")
        return " ".join(parts)

    def render(self, history: list[Tick], variant: str) -> Any:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        s = tick.surface
        state: dict[str, Any] = {
            "ownership": self._ownership(z, False),
            "quarantine": "Quarantined tests (known to be flaky): " + "; ".join(B_QUARANTINE) + ".",
            "known_issues": self._issues(z, False, t),
            "clock": hm(z["now_s"]),
            "main_pipeline": self._pipeline(z, t, s),
            "failure": self._failure(z, t),
            "since_last_green": self._since_green(z, t),
            "merge_queue": self._queue_line(z, t),
            "ci_main": self._channel(z, t, s),
        }
        if s["side"]:
            state["outside_main"] = s["side"] + "."
        state["lena_now"] = s["sheriff"]
        if variant == "lexical_decoy":
            _add_decoys(state, B_DECOYS, self.policy(z)["action"], t, "b", "lena_now", "office_chatter", B_DECOYS_EXTRA)
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        p = z["pipeline"]
        blocks: dict[str, list[str]] = {}

        # The newest trunk build and, if it is red, the breakage.
        i, st, what, sha = p["id"], p["started"], p["what_p"], p["sha"]
        if z["status"] == "running":
            build = pick([
                f"The newest trunk build is #{i}, kicked off at {st} for {what} (commit {sha}), and so far none of its jobs is red.",
                f"#{i}, started at {st} for {what} (commit {sha}), is the newest trunk build; it is still going and nothing in it has gone red.",
                f"Trunk's newest build, #{i} (begun {st}, commit {sha}, for {what}), is still in progress with no red job so far.",
            ], "bp-run", t)
        elif z["status"] == "passed":
            build = pick([
                f"The newest trunk build is #{i}, kicked off at {st} for {what} (commit {sha}); it completed at {z['passed_at']} with every job green.",
                f"#{i}, the newest trunk build (begun {st} for {what}, commit {sha}), finished green at {z['passed_at']}.",
            ], "bp-pass", t)
        else:
            job = z["failure"]["job"]
            build = pick([
                f"The newest trunk build is #{i}, kicked off at {st} for {what} (commit {sha}), and its {job} job is red.",
                f"In #{i}, the newest trunk build (begun {st} for {what}, commit {sha}), the {job} job has gone red.",
            ], "bp-red", t)
        blocks["build"] = [build]
        if z["status"] == "failed":
            f = z["failure"]
            frames = "; then ".join(_frame_p(fr) for fr in f["frames"])
            blocks["build"].append(pick([
                f"That job's most recent attempt went red at {f['at']} and nobody has retried it. The broken test is {_test_p(f['test'])}, "
                f"which ended with \"{f['error']}\". Reading the stack trace from the innermost frame outwards: {frames}.",
                f"Its latest attempt turned red at {f['at']} and has not been retried; the breaking test, {_test_p(f['test'])}, stopped with "
                f"\"{f['error']}\". Stack trace, innermost frame first: {frames}.",
            ], "bp-fail", t))

        # Who is handling it and what was posted in #ci-main (rules 2 and 6).
        claims: list[str] = []
        if z["status"] == "failed":
            c, fx = z["claim"], z["fix_posted"]
            if c is None:
                claims.append(pick([
                    "Nobody in #ci-main has announced that they are reverting, fixing or taking over this breakage.",
                    "No one has said in #ci-main that they are already reverting, fixing or taking over this breakage.",
                ], "bp-nocl", t))
            if fx is None:
                if z["open_fix"] is None:
                    claims.append(pick(["No fix for it has been posted in #ci-main.", "Nobody has posted a fix for it in #ci-main.",
                                        "#ci-main has no posted fix for it."], "bp-nofx", t))
                else:
                    claims.append(pick(["No fix for it has been posted in #ci-main itself; its open fix pull request is the one on the known-issue tracker.",
                                        "Nobody has posted a fix for it in #ci-main itself; the open fix pull request for it sits on the known-issue tracker."],
                                       "bp-nofx-board", t))
            # A claim and a posted fix are reported in time order.
            for m in sorted((m for m in (c, fx) if m is not None), key=lambda m: at(m["at"])):
                claims.append(f"At {m['at']} in #ci-main, {m['text_p']}")
        blocks["claims"] = claims

        # Commits since the last green trunk build (rule 5).
        g = z["last_green"]
        if z["commits"]:
            items = "; ".join(f"{c['sha']} by {c['who']} at {c['at']}, {c['title_p']}, which changed {_paths_p(c['paths'])}" for c in z["commits"])
            blocks["commits"] = [pick([
                f"The last green trunk build was #{g['id']} (it checked {g['sha']} and completed at {g['at']}); the commits that landed on main after {g['sha']} are {items}.",
                f"Main was last green in #{g['id']}, which checked {g['sha']} and completed at {g['at']}. Since then these commits have landed: {items}.",
                f"Since the last green trunk build, #{g['id']} ({g['sha']}, completed {g['at']}), main has received {items}.",
            ], "bp-commits", t)]
        else:
            blocks["commits"] = [pick([
                f"The last green trunk build was #{g['id']} (it checked {g['sha']} and completed at {g['at']}), and nothing has landed on main after {g['sha']}.",
                f"Main was last green in #{g['id']} ({g['sha']}, completed {g['at']}); no commit has landed since.",
            ], "bp-nocommits", t)]

        q = z["queue"]
        if q["state"] == "merging":
            lead = pick(["The merge queue is landing PRs: ", "The merge queue is active and landing PRs: ", "PRs are being landed by the merge queue: "], "bp-qm", t)
        else:
            lead = pick(["The merge queue is frozen: ", "The merge queue is on hold and lands nothing: ", "No PRs are landing, since the merge queue is frozen: "], "bp-qp", t)
        blocks["queue"] = [lead + q["note_p"] + "."]
        blocks["tracker"] = [self._issues(z, True, t)]
        quarantine = ("search's indexer.spec.ts 'rebuilds shard map', billing's webhooks.spec.ts 'retries a failed delivery' "
                      "and the web e2e checkout.spec.ts 'applies a coupon'")
        blocks["static"] = [
            pick([f"Quarantined as known flakes: {quarantine}.", f"Quarantine list (known flaky tests): {quarantine}."], "bp-quar", t),
            self._ownership(z, True, t),
        ]

        order = pick([
            ["build", "claims", "commits", "queue", "tracker", "static"],
            ["build", "queue", "commits", "claims", "static", "tracker"],
            ["queue", "build", "claims", "tracker", "commits", "static"],
        ], "bp-order", t)
        parts = [f"It is {hm(z['now_s'])} and Lena {tick.surface['gist']}."]
        for name in order:
            parts.extend(blocks[name])
        return " ".join(parts)


SCENARIOS = [RefundTestSession, MonorepoSheriff]
