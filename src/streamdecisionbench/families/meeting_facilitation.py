"""Meeting Facilitation: an assistant that nudges a live meeting.

The assistant watches a meeting against its agenda and decides, tick by tick,
which nudge (if any) the facilitator should get and which agenda item it
concerns. Both scenarios share the latent vocabulary (agenda status, item
under discussion, off-agenda talk, missing dependencies, proposals and
objections, clocks) but differ in difficulty:

* ``meeting_a`` (medium) - a 50-minute sprint-planning meeting, 30-second
  ticks. Two questions: the nudge (six options) and the agenda item it names
  (five items + none). Seven prioritised rules, including a per-item timebox
  comparison ("10 min 15 s spent of a 10-minute timebox"). Every state shows
  the same slots (item under discussion, off-agenda talk, dependencies,
  proposal, open objection); only their values change.
* ``meeting_b`` (hard) - a nonprofit board meeting under formal rules of
  order, 45-second ticks. Three questions: the recommendation (seven options),
  the agenda item (six items + none) and how firm the intervention must be
  (a three-level score). Quorum counts, motions, seconds and a speakers' queue;
  several facts are conveyed only implicitly (names to count, a missing
  document described by its consequence).
"""

from __future__ import annotations

import copy
from typing import Any

from streamdecisionbench.authoring import Choice, Scenario, Score, Tick, Timeline, override, pick, span_tags

FAMILY = "meeting_facilitation"


def hms(seconds: int, start_hour: int = 10) -> str:
    """Wall clock ``H:MM:SS`` for a meeting that starts at ``start_hour``:00."""
    total = start_hour * 3600 + seconds
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def minsec(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    if m == 0:
        return f"{s} s"
    return f"{m} min {s} s" if s else f"{m} min"


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def said(lines: list[tuple[str | None, str]]) -> str:
    out = []
    for speaker, text in lines:
        out.append(f"({text})" if speaker is None else f"{speaker}: \"{text}\"")
    return " ".join(out)


def decoy_option(options: list[str], gold: str, t: int, key: str) -> str:
    """The wrong option a lexical-decoy line borrows from at tick ``t``.

    The choice follows a fixed per-tick rotation over the non-continue
    options and only moves on when it would hit the gold option, so which
    decoy appears does not depend on gold except on those collisions.
    """
    pool = [a for a in options if a != "continue"]
    start = pick(range(len(pool)), key, t)
    for k in range(len(pool)):
        option = pool[(start + k) % len(pool)]
        if option != gold:
            return option
    raise ValueError("no decoy option available")


# ===========================================================================
# Scenario A - sprint planning, two questions (nudge, agenda item)
# ===========================================================================

A_TICK = 30
A_OFFSET = 10  # tick t happens 30 t + 10 seconds into the meeting (10:00:10 at t=0)

# name, timebox in minutes
A_ITEMS = {
    1: ("Sprint goal", 6),
    2: ("Carry-over from sprint 41", 7),
    3: ("Payments webhook migration: estimate", 10),
    4: ("Flaky-test quarantine list", 8),
    5: ("Sprint commitment", 6),
}
A_ITEMS_P = {
    1: "what the sprint is for",
    2: "unfinished tickets left from the previous sprint",
    3: "sizing the webhook move",
    4: "which unreliable tests to sideline",
    5: "how much work the team signs up for",
}

A_DECISIONS = {
    1: "Sprint goal: Apple Pay behind a feature flag, with a kill switch, for 5% of web checkout.",
    2: "Carry-over: PAY-311 and PAY-318 carry over; PAY-322 goes back to the backlog.",
    3: "Webhook migration: 13 points, split into an adapter-and-retry ticket and a dashboards ticket.",
    4: "Flaky tests: quarantine five for one week and fix two; Dana takes the sandbox-clock fix.",
    5: "Commitment: 36 points; the dashboards ticket and the Apple Pay admin report move to sprint 43.",
}
A_DECISIONS_P = {
    1: "the sprint is about getting Apple Pay out to one in twenty web shoppers behind a switch that can turn it off",
    2: "tickets 311 and 318 roll forward while 322 returns to the backlog",
    3: "the webhook move is sized at 13 points across two tickets",
    4: "five shaky tests are sidelined for a week, two get fixed, and Dana repairs the sandbox clock",
    5: "the team signs up for 36 points, with the dashboards and the Apple Pay admin report deferred",
}
# Items set aside before the meeting (structural variant only).
A_PARK_REASONS = {4: "moved here in Monday's async thread to keep this meeting short; pencilled in for sprint 43"}

# proposal key -> (text, proposer)
A_PROPOSALS = {
    "goal": ("ship Apple Pay behind a feature flag for 5% of web checkout", "Maya"),
    "goal_ks": ("ship Apple Pay behind a feature flag, with a kill switch, for 5% of web checkout", "Maya"),
    "carry": ("carry PAY-311 and PAY-318 over and send PAY-322 back to the backlog", "Maya"),
    "estimate": ("13 points, split into an adapter-and-retry ticket and a dashboards ticket", "Dana"),
    "quarantine": ("quarantine five flaky tests and fix the other two this sprint", "Leo"),
    "commit42": ("commit to all 42 planned points", "Maya"),
    "commit36": ("commit to 36 points", "Maya"),
}
A_PROPOSALS_P = {
    "goal": "Maya wants the sprint to put Apple Pay in front of 5% of web shoppers behind a switch",
    "goal_ks": "Maya wants the sprint to put Apple Pay in front of 5% of web shoppers behind a switch that can turn it off within a minute",
    "carry": "Maya wants 311 and 318 rolled forward and 322 returned to the backlog",
    "estimate": "Dana suggests 13 points over two tickets",
    "quarantine": "Leo suggests sidelining five tests and repairing the remaining two",
    "commit42": "Maya wants the team to sign up for the full 42 points",
    "commit36": "Maya now suggests signing up for 36 points",
}
A_OBJECTIONS = {
    "leo_rollout": "Leo objects that 5% is too large for a first rollout and wants 1%",
    "tariq_322": "Tariq objects to dropping PAY-322 because of the yen launch",
    "ines_padding": "Ines objects that 13 is padded and argues for 8",
    "sam_smoke": "Sam objects to quarantining the checkout-smoke test",
    "leo_qa": "Leo objects that QA cannot test that much with one tester on holiday",
}
A_OBJECTIONS_P = {
    "leo_rollout": "Leo disputes the size, calling 5% too big for a first release and asking for 1%",
    "tariq_322": "Tariq disputes dropping 322, citing the yen launch",
    "ines_padding": "Ines disputes the figure, calling it padded and preferring 8",
    "sam_smoke": "Sam disputes sidelining the checkout smoke test",
    "leo_qa": "Leo disputes it because QA is one tester down",
}
A_OBJECTORS = {
    "leo_rollout": ("Leo", "his"),
    "tariq_322": ("Tariq", "his"),
    "ines_padding": ("Ines", "her"),
    "sam_smoke": ("Sam", "his"),
    "leo_qa": ("Leo", "his"),
}
# What an item depends on: missing (the latent blocker), resolved (read from
# earlier ticks), or a tick-specific note about something that is absent but
# not needed. The slot is filled at every tick, so its presence says nothing.
A_BLOCKERS = {
    "vendor_limits": [
        "Item 3 is waiting on the vendor's API rate limits, which have not arrived and are promised only by end of day, after this meeting ends; Dana says no estimate is possible without them.",
        "The vendor's API rate limits are still missing and are not due until end of day, after the meeting; without them, Dana says, any estimate for item 3 would be a guess.",
    ],
    "ingrid_call": [
        "Which tests get quarantined is Ingrid's call, not the team's, and she is on leave until Monday and not answering messages.",
        "Item 4 needs Ingrid: the quarantine list is her call, and she is on leave until Monday and not answering messages.",
    ],
}
A_BLOCKERS_P = {
    "vendor_limits": [
        "the vendor has still not sent its API rate limits and has promised them only for the end of the day, after the session is over, and Dana cannot size the work without them",
        "it hinges on API rate limits the vendor has yet to send and that are not due before the session ends; without them, Dana says, any figure would be guesswork",
    ],
    "ingrid_call": [
        "which tests to sideline is Ingrid's decision, not the team's, and she is on leave until Monday and not replying",
        "the choice belongs to Ingrid rather than the team, and she is away until Monday and not answering",
    ],
}
A_RESOLVED = {
    "vendor_limits": [
        "The vendor's API rate limits came in early, at {time}; nothing item 3 depends on is missing now.",
        "Nothing is missing for item 3 any more: the vendor's rate limits arrived at {time}, earlier than promised.",
    ],
    "ingrid_call": [
        "Nothing is missing for item 4 any more: since {time} it is settled that the list is the team's call, not Ingrid's.",
    ],
}
A_RESOLVED_P = {
    "vendor_limits": "the vendor's limits came through early, at {time}, so nothing it needs is unavailable now",
    "ingrid_call": "since {time} it is settled that the list is the team's call, so nothing it needs is unavailable",
}
# tick -> (item, note): something absent that the item does not depend on.
A_DEP_NOTES: dict[int, tuple[int, str]] = {
    **{t: (2, "Only a ticket is blocked (PAY-318 waits on the bank's sandbox); nothing the carry-over decision depends on has been reported missing.") for t in (12, 13, 14)},
    **{t: (4, "Ingrid is on leave until Monday, but the team has owned the quarantine list since June, so nothing about item 4 waits for her, and nothing else it depends on has been reported missing.") for t in range(56, 66)},
}
A_DEP_NOTES_P: dict[int, tuple[int, str]] = {
    **{t: (2, "only a ticket is stuck (318, waiting on the bank's sandbox), and nothing the leftovers decision needs is unavailable") for t in (12, 13, 14)},
    **{t: (4, "Ingrid is away until Monday, yet the list has been the team's call since June, so nothing waits on her and nothing else it needs is unavailable") for t in range(56, 66)},
}
A_OFF_TOPICS = {
    "office_move": "the office move to the fourth floor",
    "keyboard": "Sam's new mechanical keyboard",
    "lunch": "where to go for lunch",
}
A_OFF_TOPICS_P = {
    "office_move": "desks on the fourth floor after the office move",
    "keyboard": "the keyboard Sam just bought",
    "lunch": "lunch plans",
}

A_POLICY = [
    "1. If every agenda item is closed (decided, or moved to the parking lot), the business is done: suggest wrapping up the meeting and name no item.",
    "2. Otherwise, if the item under discussion is itself already closed (its decision is in the decisions log, the agenda marks it as decided before the meeting, or it is in the parking lot), advance to the next agenda item and name the earliest agenda item that is still open.",
    "3. Otherwise, if the group has been off the agenda (talking about something other than the item under discussion) for 60 seconds or longer, steer the conversation back and name the item under discussion.",
    "4. Otherwise, if the item under discussion cannot be decided in this meeting because a person or a piece of information it depends on is missing and is not expected before the meeting ends, move it to the parking lot and name that item.",
    "5. Otherwise, if the time spent on the item under discussion is more than its timebox (exactly equal does not count), ask for a decision and name that item.",
    "6. Otherwise, if a concrete proposal for the item under discussion is on the table and nobody has an open objection to it, ask for a decision and name that item.",
    "7. Otherwise, let the discussion run and name no item.",
]
A_POLICY_P = [
    "1. When every point on the running order is settled (agreed, or shelved on the held-over list), the formal business is over: propose ending the session and point to nothing on the running order.",
    "2. If not, and the point being talked about is itself already settled (its outcome appears among the agreed outcomes, the running order says it was agreed ahead of the meeting, or it sits on the held-over list), open the following point and point to the first entry on the running order that is still unsettled.",
    "3. If not, and the talk has strayed from the point being talked about onto something else for a minute or more (exactly 60 seconds counts), pull the talk back and point to the point being talked about.",
    "4. If not, and the point being talked about cannot be concluded in this meeting because someone or some information it relies on is unavailable and will not turn up before the session ends, shelve it on the held-over list and point to it.",
    "5. If not, and the point being talked about has used more time than its allowance (using exactly the allowance does not count), press for a conclusion and point to it.",
    "6. If not, and a specific suggestion for the point being talked about has been put forward and nobody is still disputing it, press for a conclusion and point to it.",
    "7. In all other cases, stay silent and point to nothing on the running order.",
]

A_OPTIONS = {
    "continue": "Let the discussion run on without any nudge.",
    "steer_back": "Steer the conversation back to the agenda.",
    "ask_decision": "Ask the group to settle the item with a decision.",
    "park": "Move the item to the parking lot for later.",
    "advance": "Advance the meeting to the next agenda item.",
    "wrap_up": "Suggest wrapping up the meeting now.",
}
A_OPTIONS_P = {
    "continue": "Stay silent and leave the talk to the team.",
    "steer_back": "Pull the talk back onto the planned topics.",
    "ask_decision": "Press the team to reach a conclusion now.",
    "park": "Shelve the point on the held-over list.",
    "advance": "Open the following point on the running order.",
    "wrap_up": "Propose that the session end here.",
}
A_OPTIONS_D = {
    "continue": "Let the discussion carry on with no nudge.",
    "steer_back": "Steer the conversation back to the agenda.",
    "ask_decision": "Ask the group to settle the item with a decision now.",
    "park": "Put the item in the parking lot until later.",
    "advance": "Move the meeting forward to the next agenda item.",
    "wrap_up": "Suggest that the meeting wraps up now.",
}

A_TARGETS = {
    "item1": "Item 1, the sprint goal",
    "item2": "Item 2, carry-over from sprint 41",
    "item3": "Item 3, the webhook migration estimate",
    "item4": "Item 4, the flaky-test quarantine list",
    "item5": "Item 5, the sprint commitment",
    "none": "No agenda item is named",
}
A_TARGETS_P = {
    "item1": "Point one, what the sprint is for",
    "item2": "Point two, leftovers from the previous sprint",
    "item3": "Point three, sizing the webhook move",
    "item4": "Point four, sidelining unreliable tests",
    "item5": "Point five, how much the team signs up for",
    "none": "Nothing on the running order",
}
A_TARGETS_D = {
    "item1": "Item 1, the goal for the sprint",
    "item2": "Item 2, tickets carried over from sprint 41",
    "item3": "Item 3, estimating the webhook migration",
    "item4": "Item 4, quarantining flaky tests",
    "item5": "Item 5, the team's sprint commitment",
    "none": "No agenda item named at all",
}

# Surface content per tick: the lines said at that moment (speaker None marks a
# stage note) and a third-person gist used by the paraphrase register.
A_SCRIPT: list[tuple[list[tuple[str | None, str]], str]] = [
    # t0-t9: item 1, sprint goal
    ([("Priya", "Morning, everyone. This is sprint 42 planning; Maya, do you want to start us off with the goal?")], "Priya opens the session and hands the floor to Maya for the goal"),
    ([("Maya", "Sure. Card-on-file shipped last sprint, and the loudest request from sales now is wallet payments before Black Friday.")], "Maya recaps that card-on-file went out and says sales want wallet payments before Black Friday"),
    ([("Tariq", "Maya, can you move on to the next slide? We're all still staring at your title slide.")], "Tariq asks Maya to click past the title slide she is still sharing"),
    ([("Maya", "Sorry, here's the roadmap slide: Apple Pay first, Google Pay in sprint 43, both behind a feature flag.")], "Maya brings up the roadmap slide, which shows Apple Pay first and Google Pay a sprint later, both behind a switch"),
    ([("Maya", "So my proposal for the goal: ship Apple Pay behind a flag to 5% of web checkout."), ("Leo", "I object to 5% for a first rollout; wallets are new to us. Start at 1%.")], "Maya puts forward the Apple Pay goal and Leo immediately pushes back, wanting 1% instead of 5% for a first release"),
    ([("Dana", "At 1% we'd see maybe forty wallet payments a day. That's hardly a signal.")], "Dana points out that one percent would give only about forty wallet payments a day"),
    ([("Maya", "Then let me amend it: the flag gets a kill switch, so we can drop to zero within a minute.")], "Maya amends her proposal with a kill switch that can turn the feature off within a minute"),
    ([("Leo", "With a kill switch, 5% is fine by me. I withdraw my objection.")], "Leo accepts five percent now that there is a kill switch and drops his objection"),
    ([("Ines", "Does 5% mean new customers only, or anyone who reaches checkout?")], "Ines asks whether the five percent covers only new customers"),
    ([("Sam", "Anyone, randomised per session; the flag service already does that.")], "Sam explains that the five percent is picked at random per session by the existing switch service"),
    # t10-t23: item 2, carry-over
    ([("Priya", "Good, I'm logging the goal as proposed, kill switch included. Next up, carry-over from sprint 41.")], "Priya records the goal and moves to the leftover tickets"),
    ([("Sam", "Three tickets rolled over: PAY-311 refund emails, PAY-318 3-D Secure retry and PAY-322 yen rounding.")], "Sam lists the three unfinished tickets"),
    ([("Dana", "PAY-318 is blocked on the bank's sandbox, by the way; it's been down since Tuesday.")], "Dana notes that ticket 318 is stuck because the bank's test sandbox has been down since Tuesday"),
    ([("Sam", "PAY-311 is about eighty percent done; only the Spanish templates are left.")], "Sam says the refund-email ticket is mostly finished apart from the Spanish templates"),
    ([("Leo", "PAY-322 has no test cases yet, so it isn't close.")], "Leo points out that the rounding ticket has no test cases yet"),
    ([("Tariq", "Unrelated, but has anyone seen the floor plan for the move to the fourth floor?")], "Tariq asks, off topic, whether anyone has seen the floor plan for the office move"),
    ([("Ines", "We're next to the kitchen, apparently. Either great or terrible.")], "Ines says their new desks are beside the kitchen"),
    ([("Tariq", "Terrible. Microwaved fish every day at noon.")], "Tariq jokes about microwaved fish at lunchtime"),
    ([("Ines", "Could we ask facilities for the window side instead?")], "Ines wonders whether facilities would give them window desks"),
    ([("Tariq", "I'll email them. And the move lands in release week, which is lovely planning.")], "Tariq offers to email facilities and grumbles that the move falls in release week"),
    ([("Maya", "Okay, back to carry-over. I'd really like PAY-322 settled today.")], "Maya brings everyone back to the leftover tickets"),
    ([("Maya", "Proposal: carry PAY-311 and PAY-318 over, and send PAY-322 back to the backlog."), ("Tariq", "I object to dropping 322; the yen launch depends on it.")], "Maya suggests rolling two tickets forward and dropping the rounding one; Tariq pushes back because of the yen launch"),
    ([("Maya", "Is the yen launch date even confirmed?")], "Maya asks whether the yen launch date is confirmed"),
    ([("Tariq", "Give me a second, I'm opening the launch calendar.")], "Tariq opens the launch calendar to check"),
    # t24-t51: item 3, webhook migration estimate
    ([("Tariq", "The yen launch slipped to January. Fine, drop 322."), ("Priya", "Logged. Now the webhook migration.")], "Tariq finds the yen launch moved to January and gives way; Priya records the outcome and opens the webhook sizing"),
    ([("Dana", "We're moving payment webhooks from the old queue to the vendor's v2 events.")], "Dana outlines moving the payment webhooks onto the vendor's new events"),
    ([("Sam", "The adapter is the easy part; the real question is whether we need a batching layer.")], "Sam says the open question is whether a batching layer is needed"),
    ([("Dana", "And that depends on the vendor's rate limits, which they still haven't sent; they're promised for end of day. Without them any number now would be a guess.")], "Dana says the answer hinges on rate limits the vendor has not sent and has promised only for the end of the day, so she cannot size the work"),
    ([("Sam", "I pushed their account manager this morning; end of day is the earliest they'll commit to.")], "Sam says the vendor's account manager will not commit to anything earlier than the end of the day"),
    ([("Leo", "Could we size both cases, with and without batching?"), ("Dana", "Two numbers isn't an estimate, it's a shrug.")], "Leo asks whether they could size both cases, with and without batching, and Dana waves that off as no answer at all"),
    ([("Dana", "Oh, they came early after all, the email just landed: 1,000 requests a minute, bursts of 200. No batching needed.")], "Dana reads out the vendor's limits, which have arrived earlier than promised, and says no batching is needed"),
    ([("Sam", "So the work is the adapter, the retry queue and the dashboards."), ("Priya", "Let's do a planning-poker round. Cards ready?")], "Sam lists the pieces of work and Priya starts a round of planning poker"),
    ([("Priya", "Votes are in: Dana 8, Sam 13, Ines 5, Tariq 8, Leo 13.")], "Priya reads out votes ranging from 5 to 13"),
    ([("Ines", "I went with 5 because the adapter is mostly generated code.")], "Ines explains her low vote: the adapter is mostly generated"),
    ([("Leo", "13 from me: the retry queue needs a soak test, two days at least.")], "Leo explains his high vote with a two-day soak test"),
    ([("Sam", "Same, and dashboards always take longer than we think.")], "Sam backs the high vote, saying dashboards always overrun"),
    ([("Priya", "Second round: Dana 8, Sam 13, Ines 8, Tariq 8, Leo 13.")], "Priya reads out a second round of votes"),
    ([("Tariq", "Didn't we already agree 8 for this migration in Tuesday's refinement?"), ("Dana", "That was a rough guess; nothing was logged.")], "Tariq thinks the migration was already agreed at 8 in Tuesday's refinement, and Dana says that was only a rough guess that was never logged"),
    ([("Dana", "Proposal: 13 points, split into an adapter-and-retry ticket and a dashboards ticket."), ("Ines", "I object; 13 is padded. I'd say 8.")], "Dana suggests 13 points over two tickets and Ines pushes back, calling it padded"),
    ([("Leo", "The soak test isn't padding, Ines.")], "Leo defends the soak test"),
    ([("Ines", "Maybe, but the dashboards can reuse the card-on-file ones.")], "Ines argues that the dashboards can be reused"),
    ([("Sam", "The panels, sure, but every alert is new.")], "Sam replies that the alerts would still be new"),
    ([("Ines", "I still think 13 is too much.")], "Ines repeats that 13 is too high"),
    ([("Dana", "Tariq built the old queue; let's hear from him.")], "Dana invites Tariq, who built the old queue, to weigh in"),
    ([("Tariq", "For what it's worth, the old queue took us three sprints.")], "Tariq says the old queue took three sprints"),
    ([("Ines", "Three sprints because nobody wrote a spec.")], "Ines blames the old overrun on the missing spec"),
    ([("Dana", "We do have a spec this time. Two pages, reviewed.")], "Dana notes that there is a reviewed spec this time"),
    ([("Ines", "Fine. If the dashboards are their own ticket, I can live with 13.")], "Ines stops disputing 13 as long as the dashboards are a separate ticket"),
    ([("Priya", "Logged: 13 points, two tickets."), ("Sam", "Totally unrelated, but my new keyboard arrived: split layout, blue switches.")], "Priya records the estimate and Sam starts talking about his new keyboard"),
    ([("Dana", "Blue switches in an open-plan office? Brave.")], "Dana teases Sam about the noisy switches"),
    ([("Sam", "I'll get dampening rings, I promise.")], "Sam promises to fit dampening rings"),
    ([("Dana", "Bring it in on Friday, I want to try it.")], "Dana asks Sam to bring the keyboard in on Friday"),
    # t52-t65: item 4, flaky-test quarantine
    ([("Priya", "Next is the flaky-test list. Leo, it's yours.")], "Priya opens the unreliable-tests point and hands it to Leo"),
    ([("Leo", "Seven tests failed at random last sprint. I want the worst ones quarantined so the pipeline stops crying wolf.")], "Leo says seven tests failed at random and wants the worst ones sidelined"),
    ([("Sam", "Quarantined means they still run but don't block merges, right?")], "Sam checks what sidelining a test means"),
    ([("Leo", "Right: they run nightly and post to the QA channel.")], "Leo confirms that sidelined tests run nightly and report to QA"),
    ([("Tariq", "Doesn't Ingrid have to sign off on quarantines? She's away until Monday."), ("Leo", "Not since June; the team owns the list now.")], "Tariq asks whether the absent manager must approve, and Leo says the team has owned the list since June"),
    ([("Ines", "The checkout-smoke test is the one that bites me every single day.")], "Ines complains about the checkout smoke test"),
    ([("Dana", "That one fails because of the shared sandbox clock, not our code.")], "Dana blames the smoke test's failures on the sandbox clock"),
    ([("Leo", "Proposal: quarantine five and fix the other two this sprint."), ("Sam", "Objection: checkout-smoke must keep blocking merges; it's our only end-to-end guard.")], "Leo suggests sidelining five tests and Sam pushes back on including the smoke test"),
    ([("Maya", "Isn't this list already settled? I thought we signed it off last week."), ("Leo", "That was last sprint's list. This one is new.")], "Maya wonders whether the list was already signed off last week, and Leo says that was last sprint's list"),
    ([("Sam", "Whichever list it is, checkout-smoke has to keep blocking merges.")], "Sam repeats that the smoke test must keep blocking merges"),
    ([("Ines", "What if it's quarantined for one week only while the clock gets fixed?")], "Ines asks whether the smoke test could be sidelined for just one week while the clock gets fixed"),
    ([("Sam", "One week I could accept, but only once the clock fix is a ticket with an owner.")], "Sam says he could accept one week, but only once the clock fix is a ticket with an owner"),
    ([("Tariq", "Who even owns the sandbox clock?"), ("Dana", "Platform, but anyone can patch it; it's half a day.")], "Tariq asks who owns the sandbox clock and Dana says anyone can patch it in half a day"),
    ([("Sam", "Then put it on the board with someone's name on it, and I'm there.")], "Sam repeats that he wants a ticket with a name on it before he agrees"),
    # t66-t83: item 5, commitment
    ([("Dana", "Done: the clock-fix ticket is up, and it's mine."), ("Sam", "Then I withdraw my objection."), ("Priya", "Logged: quarantine five for one week, fix two, Dana on the clock. Last one, the commitment.")], "Dana creates the clock-fix ticket and takes it, Sam drops his objection, and Priya records the plan for the tests and opens the commitment"),
    ([("Maya", "Capacity first: Tariq is on call this sprint and Ines is out Thursday and Friday.")], "Maya lists who is short on time this sprint"),
    ([("Sam", "Last sprint's velocity says about 42 points.")], "Sam puts capacity at about 42 points from last sprint's pace"),
    ([("Ines", "Velocity was 44 with a holiday in it, so 42 is a fair capacity estimate.")], "Ines remarks that last sprint's velocity makes 42 look about right as an estimate of capacity"),
    ([("Tariq", "On-call usually eats half my week, so count me at half.")], "Tariq says on-call duty halves his time"),
    ([("Maya", "Planned so far: Apple Pay 21, webhooks 13, carry-over 5, flaky fixes 3. That's 42.")], "Maya adds up the planned work to 42 points"),
    ([("Maya", "So I propose we commit to all 42."), ("Leo", "I object: QA can't test 42 points with one tester on holiday.")], "Maya suggests signing up for all 42 points and Leo pushes back on QA capacity"),
    ([("Maya", "What if Sam helps with the webhook soak test?")], "Maya asks whether Sam could help with the soak test"),
    ([("Sam", "I can pair on the soak, sure.")], "Sam agrees to pair on the soak test"),
    ([("Leo", "That helps, but I'm still not comfortable above 36.")], "Leo says he is still uneasy above 36 points"),
    ([("Maya", "36 means cutting 6 points somewhere.")], "Maya notes that 36 means cutting six points"),
    ([("Dana", "The dashboards ticket could slip to next sprint.")], "Dana mentions that the dashboards ticket could slip to next sprint"),
    ([("Maya", "Would that be enough, Leo?"), ("Leo", "Let me look at the test plan before I answer.")], "Maya asks Leo if that is enough and he wants to check the test plan first"),
    ([("Ines", "The dashboards ticket is 3 points, so that only gets us to 39.")], "Ines points out that dropping the dashboards only reaches 39"),
    ([("Leo", "Right, and 39 is still more than I can test.")], "Leo says 39 is still more than QA can test"),
    ([("Maya", "Then the Apple Pay admin report moves out as well. That's 36; I propose we commit 36.")], "Maya also pushes out the admin report and suggests 36"),
    ([("Leo", "36 I can live with.")], "Leo accepts 36"),
    ([("Sam", "So: Apple Pay without the admin report, the webhook adapter and retry, and the carry-over.")], "Sam restates what is in the sprint"),
    # t84-t99: after the last item
    ([("Priya", "Logged: commit 36 points; dashboards and the admin report move to sprint 43.")], "Priya records the 36-point commitment"),
    ([("Priya", "That's everything on the agenda. Anything to flag for next time?")], "Priya notes the agenda is done and asks for anything to flag for next time"),
    ([("Maya", "I'll send the sprint goal to sales this afternoon.")], "Maya says she will send the goal to sales"),
    ([("Leo", "Can someone book the soak-test environment today?"), ("Dana", "I'll book it after this.")], "Leo asks for the soak-test environment to be booked and Dana takes it on"),
    ([("Tariq", "So, lunch: the new ramen place on Fifth?")], "Tariq brings up lunch at a new ramen place"),
    ([("Ines", "Their queue is forty minutes at noon.")], "Ines warns about the long lunch queue there"),
    ([("Tariq", "Then we go at 11:30. I'll book for six.")], "Tariq says they should go at 11:30 and that he will book a table for six"),
    ([("Sam", "Make it seven, Leo's coming.")], "Sam says to book a table for seven, since Leo is coming too"),
    ([("Leo", "Only if they do a vegetarian broth.")], "Leo says he will come only if the place serves a vegetarian broth"),
    ([("Priya", "Quick check-out round before we go: one word each on this plan.")], "Priya asks everyone for a single word on how they feel about the plan before they go"),
    ([("Dana", "Realistic."), ("Sam", "Tight.")], "Dana calls the plan realistic and Sam calls it tight"),
    ([("Ines", "Clear."), ("Tariq", "Hungry.")], "Ines calls the plan clear, and Tariq just says he is hungry"),
    ([("Leo", "Testable, finally."), ("Maya", "Good.")], "Leo says the plan is finally testable and Maya calls it good"),
    ([("Priya", "Thanks, all. I'll post the decisions log in the team channel.")], "Priya thanks everyone and promises to post the outcomes"),
    ([("Maya", "And I'll tidy the board so the sprint starts clean.")], "Maya offers to tidy the ticket board"),
    ([("Priya", "See you at stand-up tomorrow."), ("Tariq", "Bye! Ramen at 11:30.")], "Priya closes with a stand-up reminder as people start leaving the call"),
]
# Seconds before the tick at which each line was said (default 0). An item
# opens, and an aside starts, at the moment of its first line.
A_AGO = {10: [15], 15: [25], 24: [20, 15], 48: [28, 25], 52: [15], 66: [25, 20, 15], 88: [25]}

# Irrelevant company notices for the lexical-decoy register, keyed by the wrong
# action whose vocabulary they borrow. None of them concerns this meeting.
A_DECOYS = {
    "steer_back": [
        "Bike club: ride leaders will steer the group back along the canal; the conversation and the ride agenda are in the club channel.",
        "Facilities: the conversation pods are back on floor 3; reception will steer visitors there and post the pod agenda.",
    ],
    "ask_decision": [
        "HR: we ask each group to settle the holiday-party item with a decision by Friday.",
        "Social committee: we ask every group to settle the coffee-bean item with a decision now.",
    ],
    "park": [
        "Facilities: put your car in the level-3 parking lot until later this week; the item printed on your permit will change.",
        "Reception: put visitor bikes by the parking lot gate until later; the lost-item box has moved.",
    ],
    "advance": [
        "All-hands: move your questions forward; the next agenda item at Thursday's meeting is booking travel in advance.",
        "Finance: move travel requests forward before the next all-hands meeting; the advance agenda item is at the end.",
    ],
    "wrap_up": [
        "Events team: we suggest the quiz-night meeting wraps up by nine now that the room is booked for cleaning.",
        "Book club: the organisers suggest wrapping up each meeting by eight, as the room is needed afterwards.",
    ],
}


class SprintPlanning(Scenario):
    family = FAMILY
    scenario_id = "meeting_a"
    title = "Facilitation nudges for a sprint-planning meeting"
    tier = "medium"
    difficulty_features = [
        "two_questions_per_decision",
        "six_action_options",
        "six_way_item_target",
        "seven_rule_priority_policy",
        "timebox_comparison",
        "duration_threshold",
        "closed_item_bookkeeping",
    ]
    decision_structures = ["maintain", "advance", "recover", "reroute", "resolve-conflict", "terminate"]
    deadline_steps = 2

    # meeting second at which each item was opened (never whole minutes, so the
    # time spent on an item is never exactly equal to its timebox)
    ITEM_STARTS = {1: 0, 2: 295, 3: 715, 4: 1555, 5: 1975}

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            role = (
                "You help Priya, who is running the checkout squad's sprint-42 planning session. Every half minute you may pass her "
                "one prompt. The situation text gives the running order (the points in sequence, each with its time allowance and "
                "whether it is settled), the outcomes agreed so far, the held-over list of shelved points, the point being talked "
                "about, whether the talk has strayed from it and for how long, what that point relies on, any specific suggestion "
                "on the table and whether anyone still disputes it, and finally what was just said. Anything the point lacks is "
                "reported in the sentence on what it relies on as soon as someone raises it; if that sentence reports nothing "
                "unavailable, nothing is. The sentences on what is on the table and who disputes it are the record: an idea or "
                "figure that comes up only in the closing line on what was just said is not a suggestion on the table unless "
                "those sentences say it is."
            )
            body = {"role": role, "rules": A_POLICY_P}
            q1 = "Work down the rules and use the first one that fits this moment. Which prompt should Priya get now?"
            q2 = "Work down the rules and use the first one that fits this moment. Which point on the running order should the prompt refer to?"
            options, targets = A_OPTIONS_P, A_TARGETS_P
        else:
            role = (
                "You are the facilitation assistant for a software team's sprint-planning meeting. Every 30 seconds you may send "
                "the facilitator, Priya, one nudge. `agenda` lists the items in order with their timeboxes and status, "
                "`decisions_log` records what the group has decided, `parking_lot` holds items set aside for a later meeting, and "
                "`item_under_discussion` is the agenda item the meeting is on. `off_agenda_talk` says whether the group is talking "
                "about something other than that item, and for how long. `dependencies` reports any person or piece of information "
                "the item is missing as soon as someone raises it; when it reports nothing missing, nothing is missing. `proposal` "
                "is the concrete proposal formally on the table for the item (None when there is none) and `open_objection` is any "
                "objection to it that still stands. These fields are authoritative: `recent_remarks` quotes the latest lines for "
                "context, and a figure or plan mentioned there is not a proposal on the table unless the `proposal` field shows it."
            )
            if variant == "lexical_decoy":
                role += " `company_notices` is general office news that has nothing to do with this meeting."
            body = {"role": role, "policy": A_POLICY}
            q1 = "Apply the first rule that matches the current state. Which nudge should the facilitator get right now?"
            q2 = "Apply the first rule that matches the current state. Which agenda item should the nudge name?"
            if variant == "lexical_decoy":
                options, targets = A_OPTIONS_D, A_TARGETS_D
            else:
                options, targets = A_OPTIONS, A_TARGETS
        return [
            Choice("action", {**body, "question": q1}, dict(options)),
            Choice("target", {**body, "question": q2}, dict(targets)),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "item": 1,
                "status": {str(n): "open" for n in A_ITEMS},
                "decided_at": {},
                "timebox_min": {str(n): A_ITEMS[n][1] for n in A_ITEMS},
                "item_start_s": 0,
                "elapsed_s": 0,
                "off_s": 0,
                "off_topic": None,
                "blocker": None,
                "proposal": None,
                "objection": None,
            }
        )
        S = self.ITEM_STARTS
        # "decide": (item, meeting second of the logging remark)
        events: dict[int, tuple[dict[str, Any], str]] = {
            2: ({}, "'Move on to the next slide' is about the shared screen, not the agenda."),
            4: ({"proposal": "goal", "objection": "leo_rollout"}, "Goal proposed; Leo objects to the rollout size, a disagreement on substance, not a missing dependency."),
            6: ({"proposal": "goal_ks"}, "Maya amends the goal with a kill switch; Leo's objection is still open."),
            7: ({"objection": None}, "Objection to the amended goal withdrawn: an unopposed proposal is on the table (rule 6)."),
            10: ({"decide": (1, S[2]), "item": 2, "item_start_s": S[2], "proposal": None}, "Goal logged at 10:04:55, the moment carry-over opens."),
            12: ({}, "A ticket being blocked is not the agenda item missing anything."),
            15: ({"off_s": 25, "off_topic": "office_move"}, "Off-agenda aside started at 10:07:15."),
            16: ({"off_s": 55}, "Aside at 55 s: still under 60 s."),
            17: ({"off_s": 85}, "Aside passes 60 s."),
            18: ({"off_s": 115}, ""),
            19: ({"off_s": 145}, ""),
            20: ({"off_s": 0, "off_topic": None}, "Back on carry-over."),
            21: ({"proposal": "carry", "objection": "tariq_322"}, "Carry-over proposal with an open objection."),
            22: ({}, "6 min 15 s of a 7-minute timebox: not over."),
            23: ({}, "6 min 45 s of a 7-minute timebox: not over."),
            24: ({"decide": (2, S[3]), "item": 3, "item_start_s": S[3], "proposal": None, "objection": None}, "Carry-over logged at 10:11:55 as the webhook item opens."),
            27: ({"blocker": "vendor_limits"}, "Estimate impossible without the vendor's rate limits, promised only by end of day, after the meeting ends."),
            30: ({"blocker": None}, "Vendor figures arrive early, against the promise; nothing missing any more."),
            37: ({}, "Tuesday's rough guess of 8 was never logged: item 3 is still open."),
            38: ({"proposal": "estimate", "objection": "ines_padding"}, "Estimate proposed with an open objection."),
            43: ({}, "9 min 45 s of a 10-minute timebox: not over."),
            44: ({}, "10 min 15 s of a 10-minute timebox: over."),
            47: ({"objection": None}, "Objection withdrawn; the timebox rule already applies."),
            48: ({"decide": (3, 1422), "proposal": None, "off_s": 25, "off_topic": "keyboard"}, "Estimate logged at 10:23:42 but the next item is not opened; chatter starts at 10:23:45."),
            49: ({"off_s": 55}, ""),
            50: ({"off_s": 85}, "Chatter past 60 s, but the closed-item rule comes first."),
            51: ({"off_s": 115}, ""),
            52: ({"off_s": 0, "off_topic": None, "item": 4, "item_start_s": S[4]}, "Flaky-test item opened at 10:25:55."),
            56: ({}, "Ingrid is on leave, but the team owns the list: nothing item 4 depends on is missing."),
            59: ({"proposal": "quarantine", "objection": "sam_smoke"}, "Quarantine proposal with an open objection."),
            60: ({}, "Last sprint's list was signed off, not this one: item 4 is still open."),
            65: ({}, "Sam's condition (a ticket with an owner) is not met yet: his objection stays open."),
            66: ({"decide": (4, S[5]), "item": 5, "item_start_s": S[5], "proposal": None, "objection": None}, "Clock-fix ticket created, objection withdrawn, plan logged at 10:32:55 as the commitment opens."),
            72: ({"proposal": "commit42", "objection": "leo_qa"}, "Commitment proposal with an open objection."),
            77: ({}, "5 min 45 s of a 6-minute timebox: not over."),
            78: ({}, "6 min 15 s of a 6-minute timebox: over, although the objection is still open."),
            81: ({"proposal": "commit36", "objection": None}, "Revised to 36, which Leo said he could accept (his objection was to anything above 36); over the timebox, so rules 5 and 6 agree."),
            84: ({"decide": (5, 2530), "proposal": None}, "Last item logged: every agenda item is closed (rule 1: wrap up)."),
            88: ({"off_s": 25, "off_topic": "lunch"}, "Lunch chatter after the business is done."),
            89: ({"off_s": 55}, ""),
            90: ({"off_s": 85}, "Chatter past 60 s, but every item is closed, so rule 1 (wrap up) wins."),
            91: ({"off_s": 115}, ""),
            92: ({"off_s": 145}, ""),
            93: ({"off_s": 0, "off_topic": None}, ""),
        }
        tags = span_tags(
            {
                "distractor": [2, 12, 16, (22, 23), 37, 56, 60],
                "minimal_change": [7, 17, 44],
                "recovery": [20, 30],
                "hold_under_activity": [(31, 36), (61, 65), (67, 71)],
                "boundary": [(84, 87)],
                "priority_conflict": [(50, 51), (90, 92)],
                "arithmetic": [(16, 17), (22, 23), (43, 44), (77, 78)],
            }
        )
        for t in range(100):
            lines, gist = A_SCRIPT[t]
            updates, note = events.get(t, ({}, ""))
            updates = dict(updates)
            elapsed = A_TICK * t + A_OFFSET
            if "decide" in updates:
                n, when = updates.pop("decide")
                status = dict(tl.latent["status"])
                status[str(n)] = "decided"
                decided_at = dict(tl.latent["decided_at"])
                decided_at[str(n)] = hms(when)[:-3]
                updates["status"] = status
                updates["decided_at"] = decided_at
            surface = {"lines": lines, "gist": gist, "ago": A_AGO.get(t, [])}
            tl.step(surface, tags[t], note, elapsed_s=elapsed, **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            def swap(new: dict[int, tuple]):
                def fn(tk: Tick, i: int) -> dict[str, Any]:
                    if i not in new:
                        return tk.surface
                    entry = new[i]
                    return {"lines": entry[0], "gist": entry[1], "ago": entry[2] if len(entry) > 2 else []}
                return fn

            # (1) t7-9: Leo still objects to the rollout size, so there is no unopposed proposal.
            m1 = {7: ([("Leo", "A kill switch helps, but I still object: 1% for the first week, then we talk.")],
                      "Leo welcomes the kill switch but keeps objecting, still wanting one percent for the first week")}
            ticks = override(ticks, [7, 8, 9], objection="leo_rollout", surface=swap(m1), tags=["minimal_change"],
                             note="Leo's objection to the rollout size stays open: rule 7 (continue).")
            ticks = override(ticks, [10], surface=swap({10: (
                [("Leo", "Alright, 5% with the kill switch; I can live with that."), ("Priya", "Logging the goal. Next up, carry-over from sprint 41.")],
                "Leo finally accepts five percent with the kill switch, and Priya records the goal and opens the leftover tickets", [20, 15])}),
                note="Leo concedes; the goal is logged at 10:04:55 as carry-over opens.")
            # (2) t30-32: the vendor's figures have not arrived yet and are still
            # not due before the meeting ends.
            m2 = {
                30: ([("Dana", "Still nothing from the vendor. I chased their account manager again, and it's still end of day at the earliest.")],
                     "Dana says the vendor's figures have still not come and will not come before the end of the day"),
                31: ([("Sam", "If the limits turn out low, it's the adapter, the retry queue, the dashboards and batching."), ("Priya", "So we won't have those numbers before we finish here.")],
                     "Sam lists the work with batching in case the limits are low, and Priya notes the numbers will not come before the meeting ends"),
                32: ([("Leo", "Whatever the limits say, the retry queue needs a soak test.")], "Leo notes the retry queue needs a soak test either way"),
            }
            ticks = override(ticks, [30, 31, 32], blocker="vendor_limits", surface=swap(m2), tags=["minimal_change"],
                             note="Vendor figures still missing and not due before the meeting ends: rule 4 (park item 3).")
            ticks = override(ticks, [33], tags=["recovery", "hold_under_activity"], surface=swap({33: (
                [("Dana", "Wait, they came early after all: 1,000 a minute, no batching."), ("Priya", "Cards, then. Votes: Dana 8, Sam 13, Ines 5, Tariq 8, Leo 13.")],
                "Dana reads out the limits, which have arrived earlier than promised, and Priya reads out the first planning-poker votes", [25])}),
                note="Vendor figures arrive early, at 10:16: nothing missing any more.")
            # (3) t56-58: the quarantine list is the absent manager's call.
            m3 = {56: ([("Tariq", "Isn't the quarantine list Ingrid's call? She's away until Monday."), ("Leo", "It is, and she isn't answering messages.")],
                       "Tariq asks whether the list is the absent manager's call, and Leo confirms it is and that she is not answering")}
            ticks = override(ticks, [56, 57, 58], blocker="ingrid_call", surface=swap(m3), tags=["minimal_change"],
                             note="The decision belongs to Ingrid, who is on leave and unreachable: rule 4 (park item 4).")
            ticks = override(ticks, [59], tags=["recovery"], surface=swap({59: (
                [("Leo", "Found the June note: ownership moved to the team, so it's our call after all. Proposal: quarantine five and fix the other two."), ("Sam", "Objection: checkout-smoke must keep blocking merges.")],
                "Leo finds a June note that makes the list the team's call, then suggests sidelining five tests; Sam pushes back on the smoke test")}),
                note="The June note makes the list the team's call: nothing missing; the new proposal has an open objection.")
        elif variant == "structural_cf":
            # Monday's async thread settled carry-over (item 2) and moved the
            # flaky-test list (item 4) to the parking lot; the agenda, log and
            # parking lot say so. The group re-discusses both anyway.
            out = []
            for tk in ticks:
                tk = copy.deepcopy(tk)
                tk.latent["status"]["2"] = "decided_async"
                tk.latent["decided_at"]["2"] = "Monday, async"
                tk.latent["status"]["4"] = "parked"
                tk.latent["decided_at"].pop("4", None)
                out.append(tk)

            def lines(new: list[tuple[str | None, str]], ago: list[int]):
                return lambda tk, i: {"lines": new, "gist": tk.surface["gist"], "ago": ago}

            note2 = "Item 2 was decided before the meeting (Monday's async thread): rule 2 gives advance to the earliest open item, 3."
            out = override(out, list(range(10, 24)), tags=[], note=note2)
            out = override(out, [17, 18, 19], tags=["priority_conflict", "arithmetic"],
                           note=note2 + " The aside is past 60 s, but rule 2 comes before rule 3.")
            out = override(out, [10], surface=lines(
                [("Priya", "Logging the goal, kill switch included. Carry-over was settled in Monday's async thread."), ("Tariq", "Hang on, can we go over carry-over again? I'm not happy about 322.")], [15, 5]))
            # Maya's canonical "I'd really like PAY-322 settled today" would read
            # as if carry-over were still open; here she only returns to the
            # reopened question.
            out = override(out, [20], surface=lines(
                [("Maya", "Okay, back to carry-over, since Tariq has reopened it. Let's get through 322 quickly.")], []))
            out = override(out, [24], surface=lines(
                [("Tariq", "The yen launch slipped to January. Fine, drop 322, same as Monday's thread said."), ("Priya", "So Monday's call stands. Now the webhook migration.")], [20, 15]),
                note="Monday's carry-over outcome stands; the webhook item opens.")
            note4 = "Item 3 is logged and item 4 has been in the parking lot since Monday, so the earliest open item is 5: advance to item 5."
            out = override(out, [48, 49], tags=[], note=note4)
            out = override(out, [50, 51], tags=["priority_conflict"], note=note4 + " The chatter is past 60 s, but rule 2 comes before rule 3.")
            out = override(out, list(range(52, 66)), tags=[],
                           note="The group re-discusses item 4, which is in the parking lot: rule 2 gives advance to the earliest open item, 5.")
            out = override(out, [52], surface=lines(
                [("Priya", "The flaky-test list is next on the agenda, but Monday's thread parked it."), ("Leo", "Can we go through the flaky tests anyway? They hurt us every day.")], [20, 15]))
            out = override(out, [60], surface=lines(
                [("Maya", "Remind me why this was parked on Monday?"), ("Priya", "To keep today short; it's pencilled in for sprint 43.")], []))
            ticks = override(out, [66], surface=lines(
                [("Sam", "Fine, let's leave it parked, then."), ("Priya", "Agreed: the list stays in the parking lot, as Monday's thread said. Last one, the commitment.")], [20, 15]),
                note="Item 4 stays parked; the commitment opens.")
            # The flaky-test fixes were parked with item 4, so the plan counts other work.
            ticks = override(ticks, [71], surface=lines(
                [("Maya", "Planned so far: Apple Pay 21, webhooks 13, carry-over 5, the payments SDK upgrade 3. That's 42.")], []))
            ticks = override(ticks, list(range(84, 100)), note="Every item is closed (1, 3 and 5 decided in the meeting, 2 decided on Monday, 4 in the parking lot): rule 1, wrap up.")
            ticks = override(ticks, [90, 91, 92], note="Every item is closed, item 4 by parking: rule 1 (wrap up) beats the lunch chatter past 60 s.")
        return ticks

    # ------------------------------------------------------------------ policy
    @staticmethod
    def _open_items(z: dict[str, Any]) -> list[int]:
        return [n for n in A_ITEMS if z["status"][str(n)] == "open"]

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        item = z["item"]
        open_items = self._open_items(z)
        spent = z["elapsed_s"] - z["item_start_s"]
        if not open_items:
            action, target = "wrap_up", "none"
        elif z["status"][str(item)] != "open":
            action, target = "advance", f"item{open_items[0]}"
        elif z["off_s"] >= 60:
            action, target = "steer_back", f"item{item}"
        elif z["blocker"] is not None:
            action, target = "park", f"item{item}"
        elif spent > z["timebox_min"][str(item)] * 60:
            action, target = "ask_decision", f"item{item}"
        elif z["proposal"] is not None and z["objection"] is None:
            action, target = "ask_decision", f"item{item}"
        else:
            action, target = "continue", "none"
        return {"action": action, "target": target}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Sprint planning: an objection to the rollout size withdrawn (ask for a decision), an office-move aside crossing 60 s (steer back), a missing vendor figure, not due until after the meeting, that then arrives early (park, then recover), an estimate running past its 10-minute timebox (ask), a logged decision followed by chatter before the next item is opened (advance beats steer back), a commitment past its 6-minute timebox with an objection still open (ask), and wrap-up once every item is closed, held through lunch chatter (rule 1 beats steer back)."},
            "paraphrase": {"summary": "Same latent trajectory; running-order/held-over-list vocabulary, one prose paragraph instead of fields, reworded rules, options and item names."},
            "lexical_decoy": {"summary": "Same latent trajectory; each state adds an irrelevant company notice borrowing the vocabulary of a wrong nudge, chosen by a gold-independent rotation; option texts lightly reworded."},
            "minimal_cf": {"summary": "Three one-field edits: t7-9 Leo keeps objecting to the rollout size (ask->continue); t30-32 the vendor figures have not arrived and are still not due before the meeting ends (continue->park item 3); t56-58 the quarantine list is the absent manager's call and she cannot be reached (continue->park item 4)."},
            "structural_cf": {"summary": "Monday's async thread settled item 2 (carry-over) and moved item 4 (flaky-test list) to the parking lot; the agenda, log and parking lot say so. The group re-discusses item 2 from t10 to t23 (advance to item 3, over the aside too) and item 4 from t52 to t65 (advance to item 5); after item 3 is logged (t48-51) the earliest open item is 5, not 4. Rule 1 still fires at t84 because a parked item counts as closed."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    @staticmethod
    def _remarks(history: list[Tick]) -> list[str]:
        out: list[str] = []
        for tk in history[-2:]:
            ago = tk.surface.get("ago", [])
            for k, (speaker, text) in enumerate(tk.surface["lines"]):
                stamp = hms(tk.latent["elapsed_s"] - (ago[k] if k < len(ago) else 0))
                out.append(f"[{stamp}] {speaker}: {text}" if speaker else f"[{stamp}] ({text})")
        return out[-3:]

    def _agenda(self, z: dict[str, Any], t: int) -> str:
        parts = []
        for n, (name, box) in A_ITEMS.items():
            st = z["status"][str(n)]
            if st == "decided_async":
                s = "decided before the meeting (async in the team channel, Monday)"
            elif st == "decided":
                s = f"decided at {z['decided_at'][str(n)]}"
            elif st == "parked":
                s = "in the parking lot"
            elif n == z["item"]:
                spent = minsec(z["elapsed_s"] - z["item_start_s"])
                s = pick([f"under discussion, {spent} spent so far", f"under discussion for {spent}", f"in progress, {spent} used"], "a-spent", t)
            else:
                s = "not started"
            parts.append(f"{n}. {name} (timebox {box} min): {s}")
        return " | ".join(parts)

    @staticmethod
    def _log(z: dict[str, Any]) -> str:
        entries = []
        for n in A_ITEMS:
            st = z["status"][str(n)]
            if st == "decided_async":
                entries.insert(0, f"Before the meeting (async, Monday): {A_DECISIONS[n]}")
            elif st == "decided":
                entries.append(f"{z['decided_at'][str(n)]} {A_DECISIONS[n]}")
        return " | ".join(entries) if entries else "No decisions recorded yet."

    @staticmethod
    def _resolved(history: list[Tick]) -> tuple[str, int] | None:
        """The dependency of the current item that was missing earlier and has since arrived."""
        item = history[-1].latent["item"]
        found = None
        prev = None
        for tk in history:
            z = tk.latent
            if z["item"] == item and prev is not None and prev["item"] == item and prev["blocker"] and not z["blocker"]:
                found = (prev["blocker"], z["elapsed_s"])
            prev = z
        return found

    @staticmethod
    def _withdrawn(history: list[Tick]) -> tuple[str, int, bool] | None:
        """(objection key, second, same proposal?) for the last objection that stopped being open."""
        found = None
        prev = None
        for tk in history:
            z = tk.latent
            if z["proposal"] is None:
                found = None
            elif prev is not None and prev["objection"] and not z["objection"]:
                found = (prev["objection"], z["elapsed_s"], prev["proposal"] == z["proposal"])
            prev = z
        return found

    def _dependencies(self, history: list[Tick], z: dict[str, Any], t: int) -> str:
        n = z["item"]
        if z["blocker"]:
            return pick(A_BLOCKERS[z["blocker"]], "a-blk", t)
        if t in A_DEP_NOTES and A_DEP_NOTES[t][0] == n:
            return A_DEP_NOTES[t][1]
        res = self._resolved(history)
        if res:
            return pick(A_RESOLVED[res[0]], "a-res", t).format(time=hms(res[1])[:-3])
        return pick([
            f"Nothing item {n} depends on has been reported missing.",
            f"Nobody has reported a missing person or piece of information for item {n}.",
            f"No one has said that item {n} lacks a person or information it needs.",
        ], "a-nob", t)

    def _objection(self, history: list[Tick], z: dict[str, Any], t: int) -> str:
        if z["objection"]:
            return A_OBJECTIONS[z["objection"]] + "."
        if z["proposal"] is None:
            return pick(["None.", "None; there is no proposal to object to."], "a-obj0", t)
        w = self._withdrawn(history)
        if w and pick([True, False], "a-obj-w", t):
            who, their = A_OBJECTORS[w[0]]
            if w[2]:
                return f"None; {who} withdrew {their} objection at {hms(w[1])[:-3]}."
            return f"None to this proposal; {who}'s objection was to the earlier one."
        return pick(["None.", "Nobody has an open objection to it."], "a-noobj", t)

    def _off_agenda(self, z: dict[str, Any], t: int) -> str:
        if not z["off_s"]:
            return pick(["None right now.", "Nobody has drifted off the agenda."], "a-off0", t)
        n = z["item"]
        closed = z["status"][str(n)] != "open"
        what = "not on the agenda" if closed else f"not item {n}"
        topic = A_OFF_TOPICS[z["off_topic"]]
        start = hms(z["elapsed_s"] - z["off_s"])
        return pick([
            f"{topic[0].upper() + topic[1:]} ({what}), for {z['off_s']} seconds so far.",
            f"The talk drifted onto {topic} ({what}) at {start}; {z['off_s']} seconds so far.",
        ], "a-off", t)

    @staticmethod
    def _parking(z: dict[str, Any], t: int, reasons: dict[int, str]) -> list[str]:
        return [f"Item {k}, {A_ITEMS[k][0]}: {reasons[k]}" for k in A_ITEMS if z["status"][str(k)] == "parked"]

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        n = z["item"]
        parked = self._parking(z, t, A_PARK_REASONS)
        if z["proposal"]:
            text, by = A_PROPOSALS[z["proposal"]]
            proposal = f"{by}'s proposal: {text}."
        else:
            proposal = pick(["None.", "No concrete proposal is on the table."], "a-noprop", t)
        state: dict[str, Any] = {
            "meeting": pick([
                "Checkout squad, sprint 42 planning, 10:00-10:50, facilitated by Priya. Attending: Maya (product owner), Dana, Sam, Ines and Tariq (developers) and Leo (QA). Ingrid, the engineering manager, is on leave this week.",
                "Sprint 42 planning for the checkout squad (10:00-10:50). Facilitator: Priya. Present: Maya (product owner), developers Dana, Sam, Ines and Tariq, and Leo from QA. Ingrid (engineering manager) is on leave.",
            ], "a-meet", t),
            "clock": hms(z["elapsed_s"]),
            "agenda": self._agenda(z, t),
            "decisions_log": self._log(z),
            "parking_lot": "; ".join(parked) + "." if parked else pick(["Empty.", "Nothing parked."], "a-pl", t),
            "item_under_discussion": pick([f"Item {n} ({A_ITEMS[n][0]}).", f"{A_ITEMS[n][0]} (agenda item {n})."], "a-cur", t),
            "off_agenda_talk": self._off_agenda(z, t),
            "dependencies": self._dependencies(history, z, t),
            "proposal": proposal,
            "open_objection": self._objection(history, z, t),
            "recent_remarks": self._remarks(history),
        }
        if variant == "lexical_decoy":
            decoy = decoy_option(list(A_OPTIONS), self.policy(z)["action"], t, "a-decoy-target")
            state["company_notices"] = pick(A_DECOYS[decoy], "a-decoy", t)
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        n = z["item"]
        closed = z["status"][str(n)] != "open"
        parts = [
            (
                f"It is {hms(z['elapsed_s'])} in the checkout squad's sprint-42 planning, booked until 10:50 with Priya in the chair; "
                "Maya (product owner), four engineers and Leo from QA are there, while their manager Ingrid is away on leave."
            )
        ]
        order = []
        for k, (_, box) in A_ITEMS.items():
            st = z["status"][str(k)]
            if st == "decided_async":
                s = "already agreed ahead of the meeting in Monday's async thread"
            elif st == "decided":
                s = f"agreed at {z['decided_at'][str(k)]}"
            elif st == "parked":
                s = "shelved on the held-over list"
            elif k == n:
                s = f"being talked about, {minsec(z['elapsed_s'] - z['item_start_s'])} used"
            else:
                s = "not reached"
            order.append(f"({k}) {A_ITEMS_P[k]}, {box}-minute allowance, {s}")
        parts.append("Running order: " + "; ".join(order) + ".")
        agreed = [A_DECISIONS_P[k] for k in A_ITEMS if z["status"][str(k)] in ("decided", "decided_async")]
        parts.append(("Agreed outcomes: " + "; ".join(agreed) + ".") if agreed else "Nothing has been agreed yet.")
        shelved = [k for k in A_ITEMS if z["status"][str(k)] == "parked"]
        if shelved:
            parts.append("Shelved on the held-over list: " + ", ".join(f"point {k}" for k in shelved) + ".")
        else:
            parts.append(pick(["The held-over list is empty.", "Nothing has been shelved on the held-over list."], "ap-pl", t))
        parts.append(pick([f"The point being talked about is point {n}.", f"The team is on point {n}."], "ap-cur", t))
        if z["off_s"]:
            what = "not a point of business at all" if closed else f"not point {n}"
            parts.append(f"For {z['off_s']} seconds now the talk has been about {A_OFF_TOPICS_P[z['off_topic']]} ({what}).")
        else:
            parts.append(pick(["Nobody has strayed from it.", "No one is off topic."], "ap-off0", t))
        if z["blocker"]:
            dep = pick(A_BLOCKERS_P[z["blocker"]], "ap-blk", t)
        elif t in A_DEP_NOTES_P and A_DEP_NOTES_P[t][0] == n:
            dep = A_DEP_NOTES_P[t][1]
        elif (res := self._resolved(history)) is not None:
            dep = A_RESOLVED_P[res[0]].format(time=hms(res[1])[:-3])
        else:
            dep = pick(["nobody has said that anyone or anything it needs is unavailable", "no one has raised a gap in the people or facts it needs"], "ap-nob", t)
        parts.append(f"As for what point {n} relies on, {dep}.")
        if z["proposal"]:
            parts.append("On the table: " + A_PROPOSALS_P[z["proposal"]] + ".")
            if z["objection"]:
                parts.append(A_OBJECTIONS_P[z["objection"]] + ".")
            else:
                w = self._withdrawn(history)
                if w and w[2]:
                    who, their = A_OBJECTORS[w[0]]
                    parts.append(f"{who} has since dropped {their} objection, and nobody else is disputing it.")
                elif w:
                    parts.append(f"{A_OBJECTORS[w[0]][0]}'s objection was to the earlier figure; nobody is disputing this one.")
                else:
                    parts.append("No one is disputing it.")
        else:
            parts.append(pick(["No specific suggestion is on the table, so nothing is being disputed.", "Nobody has put a specific suggestion forward."], "ap-noprop", t))
        parts.append(f"Just now, {tick.surface['gist']}.")
        text = " ".join(parts)
        return text[0].upper() + text[1:]


# ===========================================================================
# Scenario B - nonprofit board meeting under formal rules; three questions
# ===========================================================================

B_TICK = 45
B_OFFSET = 20  # tick t happens 45 t + 20 seconds after 7:00:00 pm
B_QUORUM = 5
B_MEMBERS = ["Rosa", "Tom", "Mei", "Grace", "Aaron", "Fatima", "Hector", "Jonah", "Keisha"]

B_ITEMS = {
    1: "September minutes",
    2: "Treasurer's report",
    3: "Warehouse lease renewal",
    4: "County grant application",
    5: "Volunteer background-check policy",
    6: "Executive director's report",
}
B_ITEMS_LC = {
    1: "the September minutes",
    2: "the treasurer's report",
    3: "the warehouse lease renewal",
    4: "the county grant application",
    5: "the volunteer background-check policy",
    6: "the executive director's report",
}
B_ITEMS_P = {
    1: "signing off last month's record",
    2: "the finance update",
    3: "renewing the storage building's rental",
    4: "the county funding bid",
    5: "screening rules for volunteers",
    6: "the director's update",
}
B_OUTCOMES = {
    "approved_5_0": "approved 5-0",
    "received": "received",
    "approved_4_1": "approved 4-1",
    "postponed": "postponed to the November meeting",
    "adopted_6_0": "adopted 6-0",
}
B_OUTCOMES_P = {
    "approved_5_0": "signed off five votes to none",
    "received": "taken as read",
    "approved_4_1": "passed four votes to one",
    "postponed": "put off until November",
    "adopted_6_0": "passed six votes to none",
}
# motion key -> (text, mover)
B_MOTIONS = {
    "minutes": ("approve the September minutes", "Tom"),
    "lease": ("approve the three-year warehouse lease renewal at $4,200 a month", "Grace"),
    "grant": ("authorise Dev to submit the county grant application", "Tom"),
    "policy": ("adopt the volunteer background-check policy as drafted", "Mei"),
}
B_MOTIONS_P = {
    "minutes": "sign off last month's record",
    "lease": "renew the storage building for three years at $4,200 a month",
    "grant": "let Dev file the county funding bid",
    "policy": "take on the volunteer screening rules as written",
}
# The missing document is stated by its consequence for the board, never as
# "the item cannot be settled".
B_BLOCKERS = {
    "budget_sheet": [
        "under the board's grants policy, the finance committee's approved budget sheet must be before the board before it authorises any grant application; the committee has not sent one and does not meet again until next Tuesday.",
        "the board's grants policy bars it from authorising a grant application until the finance committee's approved budget sheet is in front of it; no sheet has come, and the committee next meets on Tuesday.",
    ],
}
B_BLOCKERS_P = {
    "budget_sheet": [
        "the food bank's grants policy says the board may not approve any funding bid until the finance committee's signed-off budget sheet is in its hands; none has arrived, and that committee does not meet before Tuesday",
        "no funding bid may be approved by the board, under its own grants policy, before the finance committee's signed-off budget sheet reaches it; the committee has sent nothing and next sits on Tuesday",
    ],
}
# Papers that are present or not needed, in the same slot as the blocker.
B_PAPER_NOTES = {
    1: "the September minutes went out with the agenda and are in the board pack",
    2: "Mei's September statements, reviewed by the finance committee, are in the board pack",
    3: "the landlord's draft lease and Dev's comparison of two other warehouses are in the board pack",
    4: "Dev's draft application is in the board pack",
    5: "Grace's draft policy went out last week and is in the board pack",
    6: "the director's report is for information only and needs no papers",
}
B_PAPER_NOTES_P = {
    1: "last month's record went out with the agenda and is in the pack",
    2: "Mei's September statements, checked by the finance committee, are in the pack",
    3: "the landlord's draft contract and Dev's comparison with two other buildings are in the pack",
    4: "Dev's draft bid is in the pack",
    5: "Grace's draft rules went out last week and are in the pack",
    6: "the director's update is for information and needs no paperwork",
}
# tick -> (item, note), always shown: something absent that the item does not need.
B_PAPER_SPECIAL = {
    **{t: (3, "the signed lease will only exist after tonight's vote, and the auditors want a copy in January; everything the vote itself needs is in the board pack.") for t in (44, 45)},
    **{t: (6, "the city's permit for the mobile-pantry pilot is still outstanding, but the pilot is not before the board tonight, and the report needs no papers.") for t in (73, 74, 75)},
}
B_PAPER_SPECIAL_P = {
    **{t: (3, "the signed contract will only exist once tonight's vote is done, and the auditors want it in January; the vote itself needs nothing more") for t in (44, 45)},
    **{t: (6, "the city has still not issued the permit for the mobile-pantry trial, but that trial is not up for a decision tonight, and the update needs no paperwork") for t in (73, 74, 75)},
}
B_OFF_TOPICS = {
    "harvest_market": "chat that started with the new Harvest Market store opening",
    "school_week": "the school district's switch to a four-day week",
    "fun_run": "next month's 10K fun run",
}
B_OFF_TOPICS_P = {
    "harvest_market": "a supermarket opening and everything it led to",
    "school_week": "the local schools moving to four-day weeks",
    "fun_run": "a charity 10K race next month",
}

B_POLICY = [
    "1. If every agenda item is closed (decided by a vote, received as a report, or postponed to a later meeting): adjourn the meeting; item = none.",
    "2. Otherwise, if the voting members present, plus any written proxies the bylaws count toward quorum, are fewer than the quorum (non-voting staff never count): note the lack of quorum and pause decisions; item = none.",
    "3. Otherwise, if the item under discussion is itself already closed: move to the next item; item = the earliest agenda item that is still open.",
    "4. Otherwise, if the board has been off the agenda (on a subject other than the item under discussion) for 90 seconds or longer: return to the agenda; item = the item under discussion.",
    "5. Otherwise, if the item under discussion cannot be settled tonight because a document it requires is missing: postpone the item to the next meeting; item = that item.",
    "6. Otherwise, if a motion on the item under discussion has been moved and seconded, its vote has not been called, and no member is waiting to speak: call the vote; item = that item.",
    "7. Otherwise: let the discussion continue; item = none.",
]
B_POLICY_P = [
    "1. Once every point of business is finished (settled by a vote, taken as read, or put off to a future meeting): close the meeting; point = none.",
    "2. If not, and the directors with a vote who are in the room, together with any signed proxy forms the constitution lets count toward the minimum attendance, number less than that minimum (staff without a vote are never counted): flag the missing minimum and hold off on any decisions; point = none.",
    "3. If not, and the point the board is on has itself already been finished: open the following point; point = the first point of business not yet finished.",
    "4. If not, and the board has strayed from the point it is on to some other subject for a minute and a half or more (exactly 90 seconds counts): bring the board back to its business; point = the point it is on.",
    "5. If not, and the point the board is on cannot be finished tonight because a paper it needs is unavailable: defer it to the next meeting; point = that point.",
    "6. If not, and a proposal on the point the board is on has been formally put and backed by a second director, the chair has not yet asked for the vote, and no director is still queued to speak: have the chair put it to a vote; point = that point.",
    "7. In any other case: say nothing and let the talk go on; point = none.",
]
B_FIRMNESS = (
    "Level 0 exactly when rule 7 applies (no intervention). For any other recommendation, adjourning included: level 2 if (a) "
    "the quorum is not met (counted as in rule 2) while a seconded motion is still undecided, including while its vote is being "
    "taken, or (b) the board has been off the agenda for 4 minutes (240 seconds) or longer (a side conversation reported on "
    "the Off the agenda line still counts after every item is closed); otherwise level 1."
)
B_FIRMNESS_P = (
    "Choose 0 if and only if rule 7 is the one that applies (stay out of it). For every other recommendation, closing the "
    "session included, choose 2 if either (a) the minimum attendance is not met (counted as in rule 2) while a proposal that has "
    "been seconded is still waiting to be settled, even mid-vote, or (b) the board has been off its business for 240 seconds or "
    "more (talk the side-talk entry reports still counts once every point is finished); otherwise choose 1."
)

B_ACTIONS = {
    "continue": "Let the discussion continue without comment.",
    "return": "Remind the board to return to the agenda.",
    "call_vote": "Advise the chair to call the vote.",
    "note_quorum": "Note the missing quorum and pause decisions.",
    "postpone": "Postpone the item to the next board meeting.",
    "next_item": "Move the board on to the next item.",
    "adjourn": "Advise the chair to adjourn the meeting.",
}
B_ACTIONS_P = {
    "continue": "Say nothing and let the talk go on.",
    "return": "Bring the directors back to their business.",
    "call_vote": "Have the chair put the proposal to a vote.",
    "note_quorum": "Flag the missing minimum and hold decisions.",
    "postpone": "Defer this point to a future session.",
    "next_item": "Open the following point of business.",
    "adjourn": "Suggest the chair close the session.",
}
B_ACTIONS_D = {
    "continue": "Let the discussion continue with no comment.",
    "return": "Remind the board to return to its agenda.",
    "call_vote": "Advise the chair to call for the vote.",
    "note_quorum": "Note that quorum is missing and pause decisions.",
    "postpone": "Postpone this item until the next board meeting.",
    "next_item": "Move the board on to its next item.",
    "adjourn": "Advise the chair to adjourn this meeting.",
}
B_TARGETS = {
    "item1": "Item 1, the September minutes",
    "item2": "Item 2, the treasurer's report",
    "item3": "Item 3, the warehouse lease renewal",
    "item4": "Item 4, the county grant application",
    "item5": "Item 5, the background-check policy",
    "item6": "Item 6, the director's report",
    "none": "No agenda item is named",
}
B_TARGETS_P = {
    "item1": "Point one, signing off last month's record",
    "item2": "Point two, the finance update",
    "item3": "Point three, the storage building rental",
    "item4": "Point four, the county funding bid",
    "item5": "Point five, screening rules for volunteers",
    "item6": "Point six, the director's update",
    "none": "No point of business",
}
B_TARGETS_D = {
    "item1": "Item 1, minutes of September",
    "item2": "Item 2, the treasurer's figures",
    "item3": "Item 3, renewing the warehouse lease",
    "item4": "Item 4, the county's grant application",
    "item5": "Item 5, volunteer background checks",
    "item6": "Item 6, the executive director's report",
    "none": "No agenda item named at all",
}
B_LEVELS = [
    "No intervention: pass the chair nothing.",
    "Gentle reminder: a quiet note the chair can act on at the next pause.",
    "Firm interruption: the chair should stop the proceedings at once.",
]
B_LEVELS_P = [
    "Stay out of it: the chair receives nothing.",
    "Soft prompt: a discreet note for the chair to use when there is a lull.",
    "Hard stop: the chair must break in at once, whatever is under way.",
]

# Surface per tick: lines said (speaker None = stage note), the secretary's
# minute for that moment ("" if none), and a third-person gist for the
# paraphrase register.
B_SCRIPT: list[tuple[list[tuple[str | None, str]], str, str]] = [
    # t0-t4: item 1, September minutes
    ([("Rosa", "It's just after seven, so I'll call the October meeting to order. Thank you all for coming out on a wet night.")], "Called to order by the chair.", "Rosa opens the October meeting and thanks everyone for braving the rain"),
    ([("Rosa", "Jonah and Keisha both sent regrets, Aaron texted that he's still parking, and Fatima and Hector are running late, so five of us are missing for now.")], "", "Rosa reports two apologies, one director still parking and two latecomers, so five are missing for now"),
    ([("Tom", "I move that we approve the September minutes as circulated.")], "Tom moved approval of the September minutes.", "Tom proposes signing off last month's record"),
    ([(None, "Aaron hurries in and sits down."), ("Grace", "Second."), ("Mei", "Before we vote, I have one correction, please.")], "Aaron arrived. Grace seconded.", "Aaron hurries in, Grace backs the proposal, and Mei asks to make a correction before any vote"),
    ([("Mei", "Page two says the freezer grant was $1,520; it was $1,250."), ("Rosa", "Noted. All in favour of the minutes as corrected?")], "Correction accepted; vote called.", "Mei fixes a figure and Rosa asks for a show of hands on the corrected record"),
    # t5-t20: item 2, treasurer's report
    ([("Grace", "Five in favour, none against."), ("Fatima", "Sorry I'm late, the bridge was a car park."), ("Rosa", "Welcome, Fatima. On to the treasurer's report. Mei?")], "Minutes approved 5-0. Fatima arrived. Treasurer's report begun.", "the record is signed off five to none, Fatima arrives, and Rosa hands over to Mei for the finance update"),
    ([("Mei", "September income was $48,300 against $51,900 of spending, a $3,600 gap, which is normal before the holiday drive.")], "", "Mei reports a small September shortfall, which is usual before the holiday drive"),
    ([("Mei", "The operating reserve stands at $112,000, a bit over two months of costs.")], "", "Mei gives the size of the reserve"),
    ([("Aaron", "What's the $3,400 under vehicles?")], "", "Aaron asks about a vehicle expense"),
    ([("Mei", "The van's transmission. It's fixed, and the warranty covered part of it.")], "", "Mei explains the van repair"),
    ([("Fatima", "Are grocery-rescue donations still down?"), ("Mei", "Down 8% on last year, mostly bread.")], "", "Fatima asks about rescued groceries and Mei says they are down, mostly bread"),
    ([("Tom", "Bread reminds me: did anyone make it to the Harvest Market opening on Saturday?")], "", "Tom, prompted by the bread remark, asks who went to a supermarket opening"),
    ([("Tom", "They had a string quartet in the produce aisle. A string quartet!")], "", "Tom describes a string quartet at the store opening"),
    ([("Aaron", "I heard the parking there was a nightmare.")], "", "Aaron chimes in about the store's parking"),
    ([("Tom", "Forty minutes to find a spot. I gave up and used the church lot.")], "", "Tom describes giving up and parking at the church"),
    ([("Grace", "Isn't the church lot where the new bus stop is going?")], "", "Grace asks about a new bus stop by the church"),
    ([("Tom", "No, that's on Elm. The church is getting a mural instead.")], "", "Tom corrects her and mentions a mural"),
    ([("Aaron", "The high-school art club is painting it; my niece is in the club.")], "", "Aaron says his niece is helping paint the mural"),
    ([("Tom", "Then we should all turn up for the unveiling.")], "", "Tom suggests everyone go to the mural unveiling"),
    ([("Mei", "May I finish the report? Last point: the annual audit starts in January.")], "", "Mei asks to finish her update and mentions the January audit"),
    ([("Mei", "That's everything, and it's for information only."), ("Rosa", "Thank you, Mei; the report is received. Next, the warehouse lease. Dev?")], "Treasurer's report received. Lease renewal introduced by Dev.", "Mei finishes, the update is taken as read, and Rosa turns to the storage-building rental with Dev"),
    # t21-t45: item 3, warehouse lease
    ([("Dev", "The landlord offers three years at $4,200 a month, up from $3,900, with a 3% yearly escalator.")], "", "Dev sets out the landlord's terms"),
    ([("Aaron", "And the loading dock?"), ("Dev", "They'll replace the dock leveller before January.")], "", "Aaron asks about the loading dock and Dev says it will be fixed"),
    ([("Dev", "I priced two other warehouses; both were over $5,000 and further from the bus line.")], "", "Dev reports that the alternatives cost more and are further away"),
    ([("Grace", "I move that we approve the three-year renewal at $4,200 a month.")], "Grace moved to approve the three-year lease renewal.", "Grace formally proposes renewing the rental"),
    ([("Rosa", "Is there a second?"), ("Tom", "I'd like to hear about the roof before I second anything.")], "", "Rosa asks whether anyone backs it and Tom wants roof details first"),
    ([("Dev", "The roof was redone in May at the landlord's cost."), ("Tom", "Then I second it."), (None, "Aaron and Fatima raise their hands to speak.")], "Tom seconded.", "Dev answers about the roof, Tom backs the proposal, and Aaron and Fatima put their hands up asking to speak"),
    ([("Aaron", "My worry is the escalator: by year three we're close to $4,500.")], "", "Aaron worries about the yearly increase"),
    ([("Fatima", "The dock froze twice last winter. Is heating covered in the new terms?"), (None, "Mei raises her hand to speak.")], "", "Fatima asks about heating and Mei puts her hand up to speak"),
    ([("Dev", "Heating stays with us, but the new leveller seals much better.")], "", "Dev answers the heating question"),
    ([(None, "Mei lowers her hand and steps into the hallway to take a call from the bank; Tom raises his hand to speak.")], "Mei stepped out.", "Mei leaves the room to take a call from the bank and Tom puts his hand up to speak"),
    ([("Tom", "For the record, $4,200 is still below market. I'm in favour."), (None, "Grace raises her hand to speak.")], "", "Tom says the rent is still below market and Grace puts her hand up to speak"),
    ([("Grace", "Could we ask for two years instead of three?"), ("Dev", "They said three or nothing."), (None, "Aaron raises his hand to speak again.")], "", "Grace asks about a shorter term, Dev says it is three years or nothing, and Aaron puts his hand up to speak again"),
    ([(None, "Mei comes back in and sits down."), ("Aaron", "If it's three or nothing, I'd still like the escalator capped."), (None, "Fatima raises her hand to speak.")], "Mei returned.", "Mei comes back, Aaron asks for a cap on the increase, and Fatima puts her hand up to speak"),
    ([("Fatima", "Could Dev at least try to negotiate the escalator after we approve?"), (None, "Mei raises her hand to speak.")], "", "Fatima asks Dev to try negotiating the increase later, and Mei puts her hand up to speak"),
    ([("Mei", "Budget-wise we can absorb it; the reserve covers two months."), (None, "Aaron raises his hand for one more question.")], "", "Mei says the budget can absorb the rent, and Aaron wants one more question"),
    ([("Aaron", "Just confirming: the dock leveller is in writing?"), ("Dev", "It's clause 14.")], "", "Aaron checks that the dock repair is in the contract and Dev confirms it"),
    ([(None, "Fatima steps out to move her car before the meter runs out."), ("Rosa", "Grace, could you read the motion back for us?")], "Fatima stepped out.", "Fatima slips out to move her car while Rosa asks Grace to read the proposal back"),
    ([("Grace", "The motion is to approve a three-year renewal at $4,200 a month with a 3% yearly escalator.")], "", "Grace reads the proposal back word for word"),
    ([("Aaron", "I'm so sorry, my sitter just cancelled; I have to go home now."), (None, "Aaron gathers his coat and leaves.")], "Aaron left the meeting.", "Aaron apologises that his babysitter cancelled and leaves for the night"),
    ([(None, "Rosa looks around the table, counting."), ("Tom", "Fatima's only moving her car, isn't she?")], "", "Rosa looks around the table and Tom wonders aloud where Fatima is"),
    ([("Grace", "She said five minutes."), ("Mei", "Should we just go ahead?")], "", "Grace says Fatima promised five minutes and Mei asks whether to press on"),
    ([(None, "Fatima comes back in, shaking off her umbrella."), ("Fatima", "Sorry, sorry. The meter was about to run out.")], "Fatima returned.", "Fatima comes back in from the rain"),
    ([("Tom", "Fatima, we're just about to vote on the lease."), ("Fatima", "Good, I'm ready."), (None, "No hands are up.")], "", "Tom tells Fatima a vote is next, she says she is ready, and no hands are up"),
    ([("Mei", "Housekeeping only: I'll need the signed lease for the auditors in January.")], "", "Mei mentions she will need the signed contract for the auditors"),
    ([("Rosa", "All those in favour of the lease renewal? Against?")], "Vote called on the lease renewal.", "Rosa asks for hands for and against the rental"),
    # t46-t58: item 5, background-check policy, taken ahead of item 4 while Dev is out
    ([("Grace", "Four in favour, one against: Fatima."), (None, "Dev slips out to take a phone call."), ("Rosa", "The lease is approved. While Dev is out, we'll take item 5 ahead of the grant: the background-check policy. Grace, you drafted it.")], "Lease renewal approved 4-1 (Fatima against). Background-check policy taken ahead of the grant while Dev is out; introduced by Grace.", "the rental passes four to one, Dev slips out for a call, and Rosa takes the volunteer screening rules ahead of the funding bid, handing over to Grace"),
    ([(None, "Hector arrives and takes a seat."), ("Hector", "Apologies, my shift ran late."), ("Grace", "The draft requires checks for anyone working with children or seniors.")], "Hector arrived.", "Hector arrives late from work while Grace explains who the screening would cover"),
    ([("Mei", "I move we adopt the policy as drafted.")], "Mei moved to adopt the policy.", "Mei formally proposes taking on the screening rules"),
    ([("Rosa", "Is there a second?"), ("Fatima", "First, what does each check cost?"), ("Grace", "Eighteen dollars.")], "", "Rosa asks for a seconder, Fatima asks the cost of a check, and Grace says eighteen dollars"),
    ([("Grace", "About 140 volunteers would need one, so roughly $2,500 in the first year.")], "", "Grace estimates the first-year cost"),
    ([("Tom", "I'll second."), (None, "Hector and Fatima raise their hands to speak.")], "Tom seconded.", "Tom backs the proposal, and Hector and Fatima put their hands up asking to speak"),
    ([("Hector", "I support it, but who stores the results? That's sensitive information.")], "", "Hector asks who keeps the sensitive results"),
    ([("Grace", "The screening company keeps them; we only receive pass or fail. The school-backpack volunteers would be screened the same way.")], "", "Grace explains that only a pass or fail comes back, including for the school-backpack volunteers"),
    ([("Hector", "Speaking of schools, did everyone see the district is moving to a four-day week?")], "", "Hector brings up the school district's four-day week"),
    ([("Tom", "My neighbour teaches there; she's delighted.")], "", "Tom says his neighbour, a teacher, is delighted"),
    ([("Fatima", "Anyway, my question on the policy: does it cover our drivers?"), (None, "Tom raises his hand to speak.")], "", "Fatima asks her question about drivers and Tom puts his hand up to speak"),
    ([("Grace", "Yes, drivers are included because they go into clients' homes.")], "", "Grace confirms drivers are covered"),
    ([("Tom", "Then it's a sound policy and I'm ready to vote."), ("Rosa", "Seeing no other hands: all in favour?")], "Vote called on the policy.", "Tom says he is ready and Rosa asks for hands on the screening rules"),
    # t59-t66: item 4, county grant
    ([("Grace", "Six in favour, none against."), (None, "Dev comes back in."), ("Rosa", "Adopted. Welcome back, Dev: now item 4, the county grant.")], "Policy adopted 6-0. County grant introduced.", "the screening rules pass six to none, Dev comes back, and Rosa turns to the county funding bid"),
    ([("Dev", "It's the county's food-security grant, $25,000, due Friday, and the board has to authorise the submission."), ("Tom", "I move we authorise Dev to submit it."), ("Grace", "Second."), (None, "Mei raises her hand to speak.")], "Tom moved to authorise the grant submission; Grace seconded.", "Dev explains the county bid, Tom formally proposes filing it, Grace backs him, and Mei puts her hand up to speak"),
    ([("Mei", "There's a snag: our grants policy says the board can't authorise an application until the finance committee's approved budget sheet is in front of us, and the committee hasn't sent it. They don't meet until next Tuesday.")], "", "Mei points out that the board's own policy needs a budget sheet the finance committee has not produced"),
    ([("Dev", "Could the board authorise it tonight and I attach the sheet afterwards?"), ("Mei", "Not under our policy; the sheet has to be before the board first."), (None, "No hands are up.")], "", "Dev asks whether the board could approve first and add the sheet later, Mei says the policy does not allow it, and nobody has a hand up"),
    ([("Tom", "Could the committee meet by phone tomorrow?"), ("Grace", "Not with two of them travelling.")], "", "Tom asks whether the finance committee could meet by phone tomorrow, and Grace says two of its members are travelling"),
    ([("Rosa", "Then, without objection, the grant item is postponed to the November meeting."), (None, "No one objects.")], "County grant item postponed to November by general consent.", "Rosa puts the funding bid off to November and nobody objects"),
    ([("Dev", "The county runs the same grant again in the spring, so it isn't lost for good.")], "", "Dev says the county offers the same grant again in spring"),
    ([("Fatima", "Could the finance committee have its sheet ready well before spring, then?"), ("Mei", "I'll put it on their list.")], "", "Fatima asks for the budget sheet to be ready for spring and Mei agrees to raise it"),
    # t67-t89: item 6, executive director's report
    ([("Rosa", "Right. Dev, over to you for your report."), ("Dev", "Thanks, Rosa; I'll keep it brisk.")], "Executive director's report begun.", "Rosa hands over to Dev for his update and he promises to be brief"),
    ([("Dev", "Visits are up 14% on last October; we served 2,310 households.")], "", "Dev reports a rise in visits"),
    ([("Dev", "The new cold-storage unit arrives on November 3rd.")], "", "Dev gives the delivery date for new cold storage"),
    ([("Dev", "Volunteers logged 3,150 hours, our best month this year.")], "", "Dev reports a record month of volunteer hours"),
    ([("Fatima", "Is the school backpack programme still running?"), ("Dev", "Yes, 180 backpacks every Friday.")], "", "Fatima asks about the school backpack programme and Dev says it continues"),
    ([("Dev", "The holiday food drive runs from November 15th to December 20th.")], "", "Dev gives the dates of the holiday food drive"),
    ([("Dev", "We're still waiting on the city's permit for the mobile pantry route, so that pilot may slip to January.")], "", "Dev says a city permit for a mobile pantry is still pending and the pilot may slip"),
    ([("Tom", "Who at the city is sitting on the permit?"), ("Dev", "Parks. I'll keep chasing them.")], "", "Tom asks who is holding up the permit and Dev names the parks department"),
    ([("Dev", "The gala is confirmed for February 7th at the Riverside Hotel.")], "", "Dev confirms the date and venue of the gala"),
    ([("Hector", "Are we doing the silent auction again?"), ("Dev", "Yes, and forty items are already pledged.")], "", "Hector asks about the silent auction and Dev says forty lots are pledged"),
    ([("Mei", "The auction raised $18,000 last year, so it's worth the effort.")], "", "Mei recalls what the auction raised last year"),
    ([("Dev", "Staff news: we've hired a warehouse coordinator, Luis, who starts on Monday.")], "", "Dev announces a new warehouse coordinator"),
    ([("Grace", "Welcome to Luis. Could he come to the November meeting?"), ("Dev", "I'll bring him.")], "", "Grace welcomes the new hire and asks him to attend in November"),
    ([("Dev", "Next, the new client-intake tablets.")], "", "Dev moves to the intake tablets"),
    ([("Dev", "They've cut intake time from nine minutes to four.")], "", "Dev says the tablets have cut intake time"),
    ([("Rosa", "We have about thirteen minutes of room time left, so let's start wrapping things up. Dev, can you finish in two or three minutes?")], "", "Rosa, watching the clock, says it is time to start wrapping things up and asks Dev to finish within a few minutes"),
    ([("Dev", "Will do. On the tablets: twelve volunteers are trained so far, and more next week.")], "", "Dev agrees and says twelve volunteers are trained on the tablets"),
    ([("Dev", "Last thing: the county health inspection passed with no findings.")], "", "Dev reports a clean health inspection"),
    ([("Tom", "That's a relief after last year's."), ("Dev", "We fixed every item on last year's list.")], "", "Tom is relieved and Dev says last year's issues were all fixed"),
    ([("Mei", "The inspection report should go to the auditors, please."), ("Dev", "I'll send it tomorrow.")], "", "Mei asks for the inspection report to go to the auditors"),
    ([("Rosa", "Any other questions for Dev?"), ("Hector", "Just thanks; the numbers are impressive.")], "", "Rosa asks for questions and Hector thanks Dev"),
    ([("Grace", "Could your slides go into the board pack?"), ("Dev", "Tonight.")], "", "Grace asks for Dev's slides and he promises them tonight"),
    ([("Fatima", "One more: how many families are on the backpack waiting list?"), ("Dev", "About thirty.")], "", "Fatima asks about the backpack waiting list"),
    # t90-t99: agenda finished
    ([("Rosa", "Thank you, Dev; the report is received. That's the whole agenda.")], "Executive director's report received.", "Rosa takes Dev's update as read and notes the business is finished"),
    ([("Tom", "Before anyone leaves: the next meeting is November 18th?"), ("Grace", "Yes, same room.")], "", "Tom checks the date of the next meeting"),
    ([("Fatima", "Not for the minutes, but is anyone doing the 10K fun run next month?")], "", "Fatima asks, off the record, who is running a 10K next month"),
    ([("Hector", "I am, slowly.")], "", "Hector says he is running it"),
    ([("Tom", "I'll be at the water table handing out cups.")], "", "Tom says he will staff a water table"),
    ([("Fatima", "We should enter a food-bank team next year, matching T-shirts and all.")], "", "Fatima suggests a team entry next year"),
    ([("Mei", "Only if the T-shirts are donated.")], "", "Mei jokes that the shirts must be donated"),
    ([("Rosa", "Right, reminders: the gala volunteer sign-up is on the shared drive.")], "", "Rosa reminds everyone about the gala volunteer sign-up"),
    ([("Grace", "Draft minutes will go out within a week.")], "", "Grace says the draft record will go out within a week"),
    ([("Tom", "And the parking passes for the gala come from Dev."), ("Rosa", "Thank you all for a productive evening.")], "", "Tom mentions gala parking passes and Rosa thanks everyone for the evening"),
]

# Irrelevant background for the lexical-decoy register, keyed by the wrong
# action whose vocabulary it borrows. Every line is about some other group.
B_DECOYS = {
    "return": [
        "A sign by the coat rack asks the choir committee to remind members to return hymn books to the agenda shelf.",
        "Library notice on the side table: remind borrowers to return the agenda binders from the housing forum.",
    ],
    "call_vote": [
        "Through the wall, the chess club's chair can be heard asking members to call the vote on new clocks now.",
        "Through the wall, the residents' association chair can be heard saying she will call the vote on paint colours now.",
    ],
    "note_quorum": [
        "A flyer in the hall notes that the parish choir is missing a quorum of tenors and will pause its decisions.",
        "The neighbourhood newsletter on the side table notes a missing quorum at the garden society and paused decisions.",
    ],
    "postpone": [
        "A poster in the lobby: the library friends will postpone their book-sale item to the next board meeting in December.",
        "A sticky note on the refreshments table reads: garden club raffle item postponed until the next board meeting.",
    ],
    "next_item": [
        "From the auction rehearsal next door: 'Move on, next item, the handmade quilt!' and the bidders laugh.",
        "The caretaker asks the choir to move the next item of lost property on to the office.",
    ],
    "adjourn": [
        "The church secretary looks in to say the choir will adjourn its meeting in the hall at nine.",
        "A poster advises that the library's evening meeting will adjourn early on public holidays.",
    ],
}


def pm(seconds: int, with_suffix: bool = True) -> str:
    """Evening clock for a meeting that starts at 7:00 pm, to the minute."""
    total = 19 * 3600 + seconds
    h, m = total // 3600 - 12, total % 3600 // 60
    return f"{h}:{m:02d} pm" if with_suffix else f"{h}:{m:02d}"


B_SECONDERS = {"minutes": "Grace", "lease": "Tom", "grant": "Grace", "policy": "Tom"}
# Ticks where the speakers' queue is conveyed only by the moment's stage note
# (hands raised to speak, or no hands up); the floor line then points to the
# hands in the room with the same neutral sentence whether the queue is empty
# (t43, t62) or not (t26, t28, t51).
B_IMPLICIT_QUEUE = {26, 28, 43, 51, 62}
# Ticks where attendance is given as names only, never as a count.
B_IMPLICIT_COUNT = {0, 1, 2, 39, 40, 41}


class BoardMeeting(Scenario):
    family = FAMILY
    scenario_id = "meeting_b"
    title = "Chair's assistant for a nonprofit board meeting under rules of order"
    tier = "hard"
    difficulty_features = [
        "three_questions_per_decision",
        "seven_action_options",
        "seven_way_item_target",
        "three_level_firmness_score",
        "seven_rule_priority_policy",
        "quorum_counting",
        "motion_and_speakers_queue_state",
        "duration_thresholds",
        "implicit_facts",
        "several_priority_conflicts",
        "out_of_order_agenda",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "escalate", "reroute", "terminate", "resolve-conflict"]
    deadline_steps = 2

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            role = (
                "You sit beside the chair of a food bank's board of directors during a formally run meeting and can slip her one "
                "recommendation every 45 seconds. The situation lists the points of business in order and how each stands, which "
                "directors with a vote are in the room against the minimum attendance the constitution requires, any formal "
                "proposal and who is queued to speak, the paperwork for the point the board is on, any side talk and how long it "
                "has lasted, and what was just said. While a point is being debated, a hand in the air means a director is asking "
                "to speak; it is not a vote. The paperwork entry reports any paper the point needs that is unavailable as soon as "
                "someone raises it; if it reports nothing unavailable, nothing is. The side-talk entry reports any talk away from "
                "the business and how long it has lasted; if it reports none, there is none."
            )
            policy_key, rules, firm = "rules", B_POLICY_P, B_FIRMNESS_P
            q1 = "Work down the rules and act on the first that fits. What should you recommend to the chair now?"
            q2 = "Work down the rules and act on the first that fits. Which point of business should the recommendation refer to?"
            q3 = "How forcefully should the recommendation be delivered right now?"
            actions, targets, levels = B_ACTIONS_P, B_TARGETS_P, B_LEVELS_P
        else:
            role = (
                "You assist the chair of a nonprofit board meeting run under formal rules of order. Every 45 seconds you may pass "
                "the chair one recommendation. The state gives the agenda with each item's status, the item under discussion, the "
                "voting members present, any proxies and the quorum, the motion on the floor and who is waiting to speak, the "
                "papers, any off-agenda talk and how long it has run, and the latest minutes and remarks. During debate, a raised "
                "hand is a request to speak, not a vote. The Papers line reports any document the item under discussion requires "
                "that is missing as soon as someone raises it; when it reports nothing missing, nothing is. The Off the agenda line "
                "reports any side conversation and how long it has run; when it reports none, the board is not off the agenda."
            )
            if variant == "lexical_decoy":
                role += " The line on what is happening elsewhere in the building is about other groups and has nothing to do with this meeting."
            policy_key, rules, firm = "policy", B_POLICY, B_FIRMNESS
            q1 = "Apply the first rule that matches the current state. Which recommendation should the chair get right now?"
            q2 = "Apply the first rule that matches the current state. Which agenda item should the recommendation name?"
            q3 = "How firm should the intervention be right now?"
            if variant == "lexical_decoy":
                actions, targets, levels = B_ACTIONS_D, B_TARGETS_D, B_LEVELS
            else:
                actions, targets, levels = B_ACTIONS, B_TARGETS, B_LEVELS
        base = {"role": role, policy_key: rules}
        return [
            Choice("action", {**base, "question": q1}, dict(actions)),
            Choice("target", {**base, "question": q2}, dict(targets)),
            Score("firmness", {**base, "firmness": firm, "question": q3}, list(levels)),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "item": 1,
                "closed": {},
                "present": ["Rosa", "Tom", "Mei", "Grace"],
                "quorum": B_QUORUM,
                "proxies": [],
                "motion": None,
                "queue": [],
                "off_s": 0,
                "off_topic": None,
                "blocker": None,
                "elapsed_s": 0,
            }
        )

        def motion(key: str, seconded: bool = False, voting: bool = False) -> dict[str, Any]:
            return {"key": key, "seconded": seconded, "voting": voting}

        events: dict[int, tuple[dict[str, Any], str]] = {
            0: ({}, "Four voting members present (names only) against a quorum of five."),
            2: ({"motion": motion("minutes")}, "Motion moved without quorum; not seconded, so the reminder stays gentle."),
            3: ({"join": "Aaron", "motion": motion("minutes", True), "queue": ["Mei"]}, "Aaron arrives: quorum met; seconded motion with Mei waiting to speak."),
            4: ({"motion": motion("minutes", True, True), "queue": []}, "Chair calls the vote herself."),
            5: ({"close": (1, "approved_5_0"), "motion": None, "join": "Fatima", "item": 2}, "Minutes approved; treasurer's report opened; Fatima arrives."),
            7: ({}, "Irrelevant arithmetic: a $112,000 reserve is a bit over two months of $51,900 spending."),
            11: ({"off_s": 25, "off_topic": "harvest_market"}, "Off-agenda chat starts."),
            12: ({"off_s": 70}, "70 s off the agenda: under 90 s."),
            13: ({"off_s": 115}, "Off the agenda for 90 s or more."),
            14: ({"off_s": 160}, ""),
            15: ({"off_s": 205}, "205 s: still under 4 minutes, so a gentle reminder."),
            16: ({"off_s": 250}, "Off the agenda for 4 minutes or more: firm."),
            17: ({"off_s": 295}, ""),
            18: ({"off_s": 340}, ""),
            19: ({"off_s": 0, "off_topic": None}, "Back to the report."),
            20: ({"close": (2, "received"), "item": 3}, "Report received; lease opened."),
            24: ({"motion": motion("lease")}, "Lease motion moved but not seconded."),
            26: ({"motion": motion("lease", True), "queue": ["Aaron", "Fatima"]}, "Seconded; two members waiting to speak, shown only by raised hands."),
            27: ({"queue": ["Fatima"]}, ""),
            28: ({"queue": ["Mei"]}, ""),
            30: ({"leave": "Mei", "queue": ["Tom"]}, "Mei steps out: five present still meets the quorum."),
            31: ({"queue": ["Grace"]}, ""),
            32: ({"queue": ["Aaron"]}, ""),
            33: ({"join": "Mei", "queue": ["Fatima"]}, "Mei back."),
            34: ({"queue": ["Mei"]}, ""),
            35: ({"queue": ["Aaron"]}, ""),
            36: ({"queue": []}, "Nobody left waiting to speak on a seconded motion."),
            37: ({"leave": "Fatima"}, "Fatima steps out: five present still meets the quorum."),
            39: ({"leave": "Aaron"}, "Aaron leaves: four names present, below the quorum, with a seconded motion pending."),
            42: ({"join": "Fatima"}, "Fatima back: quorum restored, the motion is still waiting for its vote."),
            43: ({}, "No hands are up, shown only in the stage note: nobody is waiting to speak."),
            44: ({}, "The signed lease comes after the vote: nothing the vote needs is missing."),
            45: ({"motion": motion("lease", True, True)}, "Chair calls the vote herself."),
            46: ({"close": (3, "approved_4_1"), "motion": None, "item": 5}, "Lease approved; with Dev out, the chair takes item 5 ahead of item 4."),
            47: ({"join": "Hector"}, "Hector arrives: six present."),
            48: ({"motion": motion("policy")}, "Policy motion moved but not seconded."),
            51: ({"motion": motion("policy", True), "queue": ["Hector", "Fatima"]}, "Seconded; two members waiting, shown only by raised hands."),
            52: ({"queue": ["Fatima"]}, ""),
            54: ({"off_s": 25, "off_topic": "school_week"}, "Short aside."),
            55: ({"off_s": 70}, "Aside at 70 s: under 90 s."),
            56: ({"off_s": 0, "off_topic": None, "queue": ["Tom"]}, "Back on the policy."),
            58: ({"motion": motion("policy", True, True), "queue": []}, "Chair calls the vote herself."),
            59: ({"close": (5, "adopted_6_0"), "motion": None, "item": 4}, "Policy adopted; Dev is back and item 4 is opened."),
            60: ({"motion": motion("grant", True), "queue": ["Mei"]}, "Grant motion seconded; Mei waiting to speak."),
            61: ({"queue": [], "blocker": "budget_sheet"}, "The board's own grants policy requires a budget sheet that is missing: postponing outranks calling the vote."),
            64: ({"close": (4, "postponed"), "motion": None}, "Grant postponed, but the chair has not opened another item. Item 5 is already closed, so the earliest open item is 6. The sheet is still missing, but rule 3 comes before rule 5."),
            67: ({"item": 6, "blocker": None}, "Director's report opened."),
            73: ({}, "A missing city permit concerns a future pilot, not this information item."),
            82: ({}, "'Start wrapping things up' is about the clock: item 6 is still open, so the agenda is not finished."),
            90: ({"close": (6, "received")}, "Last item received: every item is closed."),
            92: ({"off_s": 25, "off_topic": "fun_run"}, ""),
            93: ({"off_s": 70}, ""),
            94: ({"off_s": 115}, "Off the agenda past 90 s, but rule 1 comes first."),
            95: ({"off_s": 160}, ""),
            96: ({"off_s": 205}, ""),
            97: ({"off_s": 0, "off_topic": None}, ""),
        }
        tags = span_tags(
            {
                "distractor": [12, (24, 25), (30, 32), (37, 38), 55, 73, 82],
                "minimal_change": [13, 16, 39],
                "recovery": [19, 42],
                "hold_under_activity": [(6, 10), (68, 72), (76, 81)],
                "boundary": [(90, 91)],
                "priority_conflict": [(39, 41), (61, 66), (94, 96)],
                "arithmetic": [(0, 3), (12, 13), (15, 16), (30, 32), (37, 42), 55, (93, 94)],
                "implicit": [(0, 2), 26, 28, 43, 51, (39, 41), (61, 63)],
            }
        )
        for t in range(100):
            lines, minute, gist = B_SCRIPT[t]
            updates, note = events.get(t, ({}, ""))
            updates = dict(updates)
            if "close" in updates:
                n, outcome = updates.pop("close")
                closed = dict(tl.latent["closed"])
                closed[str(n)] = outcome
                updates["closed"] = closed
            if "join" in updates:
                who = updates.pop("join")
                updates["present"] = [m for m in B_MEMBERS if m in tl.latent["present"] or m == who]
            if "leave" in updates:
                who = updates.pop("leave")
                updates["present"] = [m for m in tl.latent["present"] if m != who]
            surface = {"lines": lines, "minute": minute, "gist": gist}
            if t in B_IMPLICIT_QUEUE:
                surface["implicit_queue"] = True
            tl.step(surface, tags[t], note,
                    elapsed_s=B_TICK * t + B_OFFSET, **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            def swap(new: dict[int, tuple[list[tuple[str | None, str]], str, str]]):
                return lambda tk, i: {"lines": new[i][0], "minute": new[i][1], "gist": new[i][2]} if i in new else tk.surface

            # (1) t0-2: Aaron is there from the start, so five voting members meet the quorum.
            m1 = {
                1: ([("Rosa", "Jonah and Keisha both sent regrets, and Fatima and Hector are running late, so four of us are missing for now.")], "",
                    "Rosa reports two apologies and two latecomers, so four directors are missing for now"),
            }
            ticks = override(ticks, [0, 1, 2], present=["Rosa", "Tom", "Mei", "Grace", "Aaron"], surface=swap(m1), tags=["minimal_change"],
                             note="Aaron on time: five names present meets the quorum of five; nothing else applies.")
            ticks = override(ticks, [3], surface=swap({3: (
                [("Grace", "Second."), ("Mei", "Before we vote, I have one correction, please.")],
                "Grace seconded.", "Grace backs the proposal and Mei asks to make a correction before any vote")}),
                note="Seconded motion with Mei waiting to speak.")
            # (2) t36-38: Tom still has his hand up, so the vote cannot be called yet.
            m2 = {
                36: ([("Aaron", "Just confirming: the dock leveller is in writing?"), ("Dev", "It's clause 14."), (None, "Tom raises his hand to speak.")], "",
                     "Aaron checks the dock repair is in the contract, Dev confirms it, and Tom puts his hand up to speak"),
                37: ([(None, "Fatima steps out to move her car before the meter runs out."), ("Rosa", "Tom, you're next. Grace, could you read the motion back first?")], "Fatima stepped out.",
                     "Fatima slips out to move her car while Rosa tells Tom he is next and asks Grace to read the proposal back"),
            }
            ticks = override(ticks, [36, 37, 38], queue=["Tom"], surface=swap(m2), tags=["minimal_change"],
                             note="Tom is still waiting to speak: rule 6 does not apply (continue).")
            ticks = override(ticks, [39], surface=swap({39: (
                [("Tom", "I'll pass; Aaron's question covered it."), ("Aaron", "I'm so sorry, my sitter just cancelled; I have to go home now."), (None, "Aaron gathers his coat and leaves.")],
                "Aaron left the meeting.", "Tom gives up his turn, and Aaron apologises that his babysitter cancelled and leaves")}))
            # (3) t49-51: Tom seconds the policy motion at once and nobody asks to speak.
            m3 = {
                49: ([("Rosa", "Is there a second?"), ("Tom", "Second.")], "Tom seconded.", "Rosa asks for a seconder and Tom backs the proposal at once"),
                50: ([("Grace", "For the record, each check costs eighteen dollars; about 140 volunteers would need one, so roughly $2,500 in the first year.")], "",
                     "Grace gives the cost of a check and the first-year total for the record"),
                51: ([("Grace", "For reference, the checks would be renewed every three years.")], "", "Grace adds that checks would be renewed every three years"),
            }
            ticks = override(ticks, [49, 50, 51], motion={"key": "policy", "seconded": True, "voting": False}, queue=[], surface=swap(m3),
                             tags=["minimal_change"], note="Policy motion already seconded and nobody waiting to speak: call the vote on item 5.")
            ticks = override(ticks, [52], surface=swap({52: (
                [(None, "Hector and Fatima raise their hands to speak."), ("Hector", "I support it, but who stores the results? That's sensitive information.")], "",
                "Hector and Fatima put their hands up to speak, and Hector asks who keeps the sensitive results")}),
                note="Hands go up: Fatima is waiting to speak after Hector.")
        elif variant == "structural_cf":
            # Keisha's written proxy is on file and the bylaws count written proxies
            # toward quorum, so the count never drops below five.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["proxies"] = ["Keisha"]
            ticks = override(ticks, [0, 1], note="Four names present plus Keisha's proxy = 5: quorum met; nothing else applies.")
            ticks = override(ticks, [2], note="Four present plus Keisha's proxy = 5: quorum met; the motion is not seconded, so continue.")
            ticks = override(ticks, [3], note="Aaron arrives; seconded motion with Mei waiting to speak.")
            ticks = override(ticks, [39, 40, 41], tags=["arithmetic", "implicit"],
                             note="Aaron leaves: four names present plus Keisha's proxy = 5, so the quorum holds; seconded motion, nobody waiting: call the vote (gentle).")
            ticks = override(ticks, [42], tags=["arithmetic"], note="Fatima back; the motion is still waiting for its vote.")
        return ticks

    # ------------------------------------------------------------------ policy
    @staticmethod
    def _open_items(z: dict[str, Any]) -> list[int]:
        return [n for n in B_ITEMS if str(n) not in z["closed"]]

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        item = z["item"]
        open_items = self._open_items(z)
        counted = len(z["present"]) + len(z["proxies"])
        no_quorum = counted < z["quorum"]
        m = z["motion"]
        pending = m is not None and m["seconded"]
        if not open_items:
            action, target = "adjourn", "none"
        elif no_quorum:
            action, target = "note_quorum", "none"
        elif str(item) in z["closed"]:
            action, target = "next_item", f"item{open_items[0]}"
        elif z["off_s"] >= 90:
            action, target = "return", f"item{item}"
        elif z["blocker"] is not None:
            action, target = "postpone", f"item{item}"
        elif pending and not m["voting"] and not z["queue"]:
            action, target = "call_vote", f"item{item}"
        else:
            action, target = "continue", "none"
        if action == "continue":
            level = 0
        elif (no_quorum and pending) or z["off_s"] >= 240:
            level = 2
        else:
            level = 1
        return {"action": action, "target": target, "firmness": level}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Board meeting: it opens one voting member short of quorum while a motion is moved (gentle quorum note) until Aaron arrives; an off-agenda chat that crosses 90 s (gentle return) and then 4 minutes (firm return) during the treasurer's report; a lease motion whose speakers' queue (sometimes shown only as hands raised to speak) empties (call the vote), then a departure that drops attendance to 4 of a quorum of 5 with the motion pending (firm quorum note, outranks the vote), a return that restores quorum (call the vote again); with Dev out, the chair takes item 5 before item 4; a seconded grant motion whose budget sheet, required by the board's own grants policy, is missing (postpone outranks the vote), then lingering after the postponement while the sheet is still missing (next item, which is 6 because 5 is already closed; rule 3 outranks rule 5); and an adjourn recommendation once every item is closed, held through off-agenda chatter."},
            "paraphrase": {"summary": "Same latent trajectory; constitution/minimum-attendance/points-of-business vocabulary, prose fields under different keys, reworded rules, options and item names and score levels."},
            "lexical_decoy": {"summary": "Same latent trajectory; each state adds an irrelevant note from elsewhere in the building borrowing the vocabulary of a wrong recommendation, chosen by a gold-independent rotation; option texts lightly reworded."},
            "minimal_cf": {"summary": "Three one-field edits: t0-2 Aaron is there from the start, five present (note quorum->continue); t36-38 Tom is still waiting to speak (call vote->continue); t49-51 the policy motion is seconded at once with nobody waiting (continue->call vote on item 5)."},
            "structural_cf": {"summary": "Keisha's written proxy is on file and the bylaws count written proxies toward quorum. Before Aaron arrives (t0-2) and after he leaves (t39-41) the count is 4 present + 1 proxy = 5, so the quorum holds: t0-2 note quorum -> continue, and t39-41 note quorum (firm) -> call the lease vote (gentle)."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    @staticmethod
    def _minutes(history: list[Tick], k: int = 3) -> list[str]:
        out = []
        for tk in history:
            if tk.surface["minute"]:
                out.append(f"{pm(tk.latent['elapsed_s'], False)} {tk.surface['minute']}")
        return out[-k:]

    @staticmethod
    def _duration(seconds: int, t: int) -> str:
        return pick([f"{seconds} seconds", minsec(seconds)], "b-dur", t)

    def _attendance(self, z: dict[str, Any], t: int) -> str:
        present = z["present"]
        proxy = (
            "Keisha's written proxy is on file, and the bylaws count written proxies toward quorum."
            if z["proxies"] else "No proxies are on file."
        )
        if t in B_IMPLICIT_COUNT or (len(present) <= 5 and pick([True, False], "b-att-fmt", t)):
            head = f"Voting members in the room: {listing(present)}."
        else:
            head = f"Voting members present: {len(present)} of 9 ({listing(present)})."
        return f"{head} Quorum under the bylaws: {z['quorum']} voting members. {proxy} Dev, as staff, has no vote."

    def _floor(self, z: dict[str, Any], t: int, implicit_queue: bool = False) -> str:
        m = z["motion"]
        if m is None:
            return pick(["No motion is pending.", "Nothing is on the floor."], "b-nomot", t)
        text, mover = B_MOTIONS[m["key"]]
        if m["voting"]:
            return f"The chair has called the vote on {mover}'s motion to {text}; hands are being counted."
        if not m["seconded"]:
            return pick([f"{mover} has moved to {text}; nobody has seconded it yet.", f"Motion by {mover} to {text}: not yet seconded."], "b-unsec", t)
        out = f"{mover}'s motion to {text}, seconded by {B_SECONDERS[m['key']]}, is on the floor; the vote has not been called."
        q = z["queue"]
        if implicit_queue:
            return out + " " + pick([
                "Speakers' queue: whoever has a hand up in the room at this moment.",
                "The speakers' queue is simply whoever has a hand up right now.",
            ], "b-qimp", t)
        if q:
            out += " " + pick([f"Waiting to speak: {listing(q)}.", f"Hands up to speak: {listing(q)}."], "b-q", t)
        else:
            out += " " + pick(["No member is waiting to speak.", "No hands are up to speak."], "b-noq", t)
        return out

    @staticmethod
    def _papers(z: dict[str, Any], t: int) -> str:
        n = z["item"]
        if z["blocker"]:
            return pick(B_BLOCKERS[z["blocker"]], "b-blk", t)
        if t in B_PAPER_SPECIAL and B_PAPER_SPECIAL[t][0] == n:
            return B_PAPER_SPECIAL[t][1]
        # The absence is stated at every tick; the note on what is in the pack
        # is optional texture in front of it.
        absent = pick([f"no document item {n} requires has been reported missing", f"nobody has said a paper for item {n} is missing"], "b-pap", t)
        if pick([True, False], "b-pap-note", t):
            return f"{B_PAPER_NOTES[n]}; {absent}."
        return absent + "."

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        n = z["item"]
        agenda = []
        for k, name in B_ITEMS.items():
            if str(k) in z["closed"]:
                s = B_OUTCOMES[z["closed"][str(k)]]
            elif k == n:
                s = "under discussion"
            else:
                s = "not yet reached"
            agenda.append(f"{k}. {name} [{s}]")
        lines = [
            "Riverside Community Food Bank, board of directors, October meeting (7:00-8:15 pm). Chair: Rosa Delgado. Executive director Dev Patel attends as staff.",
            f"Time: {pm(z['elapsed_s'])}.",
            "Agenda: " + " | ".join(agenda),
            pick([f"Item under discussion: {n} ({B_ITEMS[n]}).", f"The board is on item {n}: {B_ITEMS_LC[n]}."], "b-cur", t),
            "Attendance: " + self._attendance(z, t),
            "Floor: " + self._floor(z, t, bool(tick.surface.get("implicit_queue"))),
            "Papers: " + self._papers(z, t),
        ]
        if z["off_s"]:
            what = "not an agenda item" if str(n) in z["closed"] else f"not item {n}"
            lines.append(f"Off the agenda: {B_OFF_TOPICS[z['off_topic']]} ({what}), for {self._duration(z['off_s'], t)} so far.")
        else:
            lines.append(pick(["Off the agenda: nothing at the moment.", "Off the agenda: no side conversation."], "b-off0-txt", t))
        lines.append("Minutes, latest entries: " + " / ".join(self._minutes(history)))
        if variant == "lexical_decoy":
            decoy = decoy_option(list(B_ACTIONS), self.policy(z)["action"], t, "b-decoy-target")
            lines.append("Elsewhere in the building: " + pick(B_DECOYS[decoy], "b-decoy", t))
        lines.append("Just now: " + said(tick.surface["lines"]))
        return lines

    def _render_paraphrase(self, history: list[Tick]) -> dict[str, str]:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        n = z["item"]
        order = []
        for k, name in B_ITEMS_P.items():
            if str(k) in z["closed"]:
                s = B_OUTCOMES_P[z["closed"][str(k)]]
            elif k == n:
                s = "the board is on it"
            else:
                s = "still to come"
            order.append(f"({k}) {name}, {s}")
        present = z["present"]
        if t in B_IMPLICIT_COUNT:
            head = f"In the room with a vote: {', '.join(present)}; the constitution sets the minimum at {z['quorum']}. "
        else:
            head = (
                f"{len(present)} of the nine directors with a vote are in the room ({', '.join(present)}); the constitution sets the minimum at "
                f"{z['quorum']}. "
            )
        people = head + (
            "A signed proxy from Keisha has been lodged, and the constitution lets signed proxies count toward the minimum."
            if z["proxies"] else "Nobody has lodged a proxy."
        ) + " Dev is staff and cannot vote."
        m = z["motion"]
        if m is None:
            proposal = "There is no formal proposal in front of the board."
        else:
            text, mover = B_MOTIONS_P[m["key"]], B_MOTIONS[m["key"]][1]
            if m["voting"]:
                proposal = f"Rosa is taking the show of hands on {mover}'s proposal to {text}."
            elif not m["seconded"]:
                proposal = f"{mover} has formally proposed to {text}, and no second director has backed it."
            else:
                proposal = f"{mover} has formally proposed to {text}, {B_SECONDERS[m['key']]} backed it, and Rosa has not asked for the vote. "
                if tick.surface.get("implicit_queue"):
                    proposal += pick([
                        "The queue to speak is whoever has a hand in the air at this moment.",
                        "Anyone with a hand in the air right now is queued to speak.",
                    ], "bp-qimp", t)
                elif z["queue"]:
                    proposal += f"Queued to speak: {', '.join(z['queue'])}."
                else:
                    proposal += "Nobody is queued to speak."
                proposal = proposal.strip()
        if z["blocker"]:
            paper = pick(B_BLOCKERS_P[z["blocker"]], "bp-blk", t)
        elif t in B_PAPER_SPECIAL_P and B_PAPER_SPECIAL_P[t][0] == n:
            paper = B_PAPER_SPECIAL_P[t][1]
        else:
            absent = pick(["nobody has reported a paper this point needs as lacking", "no one has said any document for this point is unavailable"], "bp-pap", t)
            paper = f"{B_PAPER_NOTES_P[n]}, and {absent}" if pick([True, False], "bp-pap-note", t) else absent
        state = {
            "occasion": f"October board session of the Riverside Community Food Bank, chaired by Rosa; the clock reads {pm(z['elapsed_s'])} of a session planned to end at 8:15 pm.",
            "order_of_business": "; ".join(order) + ". " + pick([f"The board is on point {n}.", f"Point {n} is the one the directors are on."], "bp-cur", t),
            "who_is_here": people,
            "formal_proposal": proposal,
            "paperwork": paper[0].upper() + paper[1:] + ".",
        }
        if z["off_s"]:
            state["side_talk"] = f"For {z['off_s']} seconds now the directors have been talking about {B_OFF_TOPICS_P[z['off_topic']]}, which is outside the business at hand."
        else:
            state["side_talk"] = pick(["No side talk right now.", "Nobody has drifted into side talk."], "bp-off0", t)
        state["this_moment"] = tick.surface["gist"][0].upper() + tick.surface["gist"][1:] + "."
        return state


SCENARIOS = [SprintPlanning, BoardMeeting]
