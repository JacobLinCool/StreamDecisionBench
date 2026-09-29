"""Interview Navigation: a copilot that tells an interviewer what to do next.

The copilot sees the prepared question list (or discussion guide), what has
been covered so far and the latest turns of the conversation, and decides the
interviewer's next move. Both scenarios share the same latent vocabulary
(current item, whether the interviewee is still answering, what is still
owed, clock) but differ in difficulty:

* ``interview_a`` (easy) - a 35-minute structured interview for a backend
  engineer; one choice question with four options whose "use when" clauses
  follow the rule priority, a four-rule policy, a plan whose marks state what
  is done and whether the follow-up was asked, and one clock subtraction.
  As an easy-tier scenario it states every phase fact in words: every camera
  line (and every narrated moment in the paraphrase) says whether the
  candidate is still answering or has finished his answer (waiting alone
  never carries it), and the current question's plan line says whether it is
  done yet.
* ``interview_b`` (medium) - a 60-minute user-research discovery interview for
  a budgeting app; two questions per decision (the moderator's move and which
  of five guide topics it concerns), a six-rule policy with a clock threshold,
  a 60-second off-guide threshold read from timestamps, an instant relatedness
  judgement, and must-cover points that are sometimes covered only in the
  transcript because the live notes lag behind by up to a minute. Every state
  says whether the session is paused and, outside the pause, whether Dana is
  still talking or has stopped talking.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from typing import Any

from streamdecisionbench.authoring import Choice, Scenario, Tick, Timeline, override, pick, span_tags

FAMILY = "interview_navigation"


def mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _set_tags(ticks: list[Tick], spec: dict[int, Iterable[str]], notes: dict[int, str] | None = None) -> list[Tick]:
    """Replace event tags (and optionally hidden notes) at the given ticks of a variant."""
    out = [copy.deepcopy(tk) for tk in ticks]
    for t, tags in spec.items():
        out[t].tags = list(tags)
    for t, note in (notes or {}).items():
        out[t].note = note
    return out


def _decoy_lines(decoys: dict[str, list[str]], gold: str, t: int, prefix: str) -> list[str]:
    """Lexical-decoy register: irrelevant lines that borrow an action's words.

    On about two thirds of the ticks the first line borrows a wrong action's
    vocabulary; on the rest its action is drawn from all of them, gold
    included, so a decoy's category never rules the gold action out. About a
    third of the ticks get a second line from any pool.
    """
    actions = list(decoys)
    if pick([False, False, True], f"{prefix}-decoy-free", t):
        target = pick(actions, f"{prefix}-decoy-target", t)
    else:
        target = pick([a for a in actions if a != gold], f"{prefix}-decoy-target", t)
    first = pick(decoys[target], f"{prefix}-decoy", t)
    lines = [first]
    if pick([True, False, False], f"{prefix}-decoy2", t):
        pool = [d for a in actions for d in decoys[a] if d != first]
        lines.append(pick(pool, f"{prefix}-decoy2-line", t))
    return lines


# ===========================================================================
# Scenario A - structured backend-engineer interview, one question, four moves
# ===========================================================================

A_ORDER = ["q1", "q2", "q3", "q4"]
A_FU_REQ = {"q1": True, "q2": True, "q3": False, "q4": True}
A_PLAN = {
    "q1": ("A backend service you owned end to end", "What would you change about its design today?"),
    "q2": ("Design a rate limiter for a public API", "What happens when the limiter's datastore goes down?"),
    "q3": ("A production incident you debugged", None),
    "q4": ("Changing the schema of a busy table without downtime", "How would you roll back a migration that half-applied?"),
}
A_PLAN_P = {
    "q1": ("a system you ran from design through to on-call", "what you would do differently in its design now"),
    "q2": ("throttling requests to a public API: your design", "how the throttle behaves when its data store is unavailable"),
    "q3": ("an outage you tracked down in production", None),
    "q4": ("altering a heavily used table's structure with no downtime", "undoing a migration that only partly ran"),
}
A_SLOT = 2100
A_STRUCTURAL_SKIP = "q4"

A_DEFS = [
    "A question is done once the candidate has finished answering it and its required follow-up, if it has one, has been asked and answered. A question marked skip in the plan needs nothing more, not even its follow-up, even if the interviewer raises it anyway.",
    "The current question is the one asked most recently (marked [current] in the plan), even if the plan also marks it skip.",
    "The candidate has finished when they have stopped and handed the turn back. Waiting while the interviewer types notes or reads the plan, or chatting about something other than the question (logistics, the team, small talk), is not working on the question.",
]
A_DEFS_P = [
    "An item is complete when the interviewee has wrapped up their reply and, if the item carries a mandatory probe, that probe has been put and replied to as well. An item flagged to be left out needs nothing further, its probe included, even if the interviewer brings it up anyway.",
    "The item in play is the one raised most recently, even if it is also flagged to be left out.",
    "The interviewee is through once they have stopped and passed the turn back. Sitting and waiting while notes are typed or the sheet is read, or small talk about anything other than the item (next steps, the team, the weather), does not count as working on the item.",
]
A_RULES = [
    "1. If the candidate is still working on the current question or its follow-up (thinking it over, asking a clarifying question, or talking through the answer), let them keep answering, even if time is short.",
    "2. Otherwise, if every question in the plan is done or marked skip, or fewer than 5 minutes of the 35-minute slot remain, close the interview (or keep closing it).",
    "3. Otherwise, if the current question has a required follow-up that has not been asked yet, ask that follow-up.",
    "4. Otherwise, move on to the next prepared question.",
]
A_RULES_P = [
    "1. While the interviewee is still busy with the item in play or with its probe (mulling it over, checking what is meant, or talking it through), give them room to carry on, however little time is left.",
    "2. If not, and either every item on the sheet is complete or flagged to be left out, or under five minutes of the 35-minute booking are left, bring the conversation to a close, or continue closing it.",
    "3. If not, and the item in play comes with a mandatory probe that nobody has put to the interviewee yet, put that probe now.",
    "4. In every other case, go to the following item on the sheet.",
]

# The "use when" clauses follow the rule priority, so exactly one of them holds at any moment.
A_OPTIONS = {
    "let_answer": "Say nothing yet and let the candidate keep going (use when they are still working on the question or its follow-up, even if time is short).",
    "follow_up": "Ask the prepared follow-up for the current question (use when the answer is finished, some question is still open, 5 or more minutes remain and a required follow-up is unasked).",
    "next_question": "Move on to the next prepared question (use when the answer is finished, some question is still open, 5 or more minutes remain and nothing more is owed on the current one).",
    "close": "Close the interview (or keep closing it) and thank the candidate (use when the candidate is not mid-answer and either every question is done or skipped, or under 5 minutes remain).",
}
A_OPTIONS_P = {
    "let_answer": "Stay quiet so the interviewee can carry on - for moments when they are mid-reply on the item or its probe, however little time is left.",
    "follow_up": "Put the mandatory probe that belongs to this item - for moments when the reply is over, some item is incomplete, five or more minutes are left and that probe has not been put.",
    "next_question": "Go to the following item on the sheet - for moments when the reply is over, some item is incomplete, five or more minutes are left and the item in play owes nothing further.",
    "close": "Wrap up (or continue the wrap-up) and end the conversation - for moments when the interviewee is not mid-reply and either every item is complete or flagged, or less than five minutes are left.",
}
A_OPTIONS_D = {
    "let_answer": "Keep quiet and let the candidate keep going (use when they are still working on the question or its follow-up, even if time is short).",
    "follow_up": "Ask the prepared follow-up for the current question now (use when the answer is finished, some question is still open, 5 or more minutes remain and its required follow-up is unasked).",
    "next_question": "Move on to the next prepared question (use when the answer is finished, some question is still open, 5 or more minutes remain and nothing more is owed on the current one).",
    "close": "Close the interview (or keep closing it) and thank the candidate (use when they are not mid-answer and either every question is done or skipped, or under 5 minutes remain).",
}

# Surface content per tick: (lines, stage, gist). ``lines`` are what is said in
# this 20-second window ("C" candidate, "I" interviewer); ``stage`` is what can
# be seen on the call and always says in words whether the candidate is still
# answering or has finished his answer (``_check_a_phase_cues`` enforces it at
# every tick of every variant); ``gist`` is a third-person summary in item/probe/sheet
# vocabulary, used by the paraphrase register, and carries the same cue. The
# plan facts (asked, done, skip) are rendered from the latent state.
A_SCRIPT: list[tuple[tuple[tuple[str, str], ...], str, str]] = [
    # t0-t5: Q1 main answer (asked at 1:20)
    ((("C", "The service I owned longest was the ledger service at my last job. Every balance change for about two million wallets went through it."),), "Tomás is on camera, still answering, speaking steadily.", "is still answering, describing the ledger service he owned, which handled balance changes for two million wallets"),
    ((("C", "It was a Go service in front of Postgres, and every entry was also published to Kafka for the reporting team."),), "Tomás sketches boxes in the air and carries on with his answer.", "is explaining, mid-flow, that the ledger was a Go service on Postgres that also published every entry to Kafka"),
    ((("C", "When I inherited it there were no tests on the write path, so my first quarter was mostly adding those."),), "Tomás keeps going with the ledger story.", "keeps going: his first quarter went into adding tests to the untested write path"),
    ((("C", "The nastiest bug class was double writes on client retries. We fixed it with an idempotency-key table and a unique constraint."),), "Tomás speeds up a little and keeps talking, clearly into it.", "goes on to describe fixing double writes on client retries with an idempotency-key table"),
    ((("C", "So, in short, that's the service. But the part I'm proudest of is the on-call work, so let me get to that."),), "Tomás carries on without a pause.", "says 'in short, that's the service' but carries straight on to the on-call work he is proudest of"),
    ((("C", "We cut pages from about fifteen a week to two by deleting noisy alerts and writing a runbook for every alert we kept."),), "Tomás counts the numbers off on his fingers, still mid-answer.", "carries on, explaining how he cut pages from fifteen a week to two"),
    # t6-t11: follow-up asked at once, candidate answering it
    ((("C", "And that's the ledger, more or less."), ("I", "Nice. Looking back, what would you change about its design today?")), "The interviewer put the follow-up straight away; Tomás frowns, thinking about it.", "wraps up the ledger story, the interviewer at once puts item 1's probe about what he would change today, and he frowns, thinking it over"),
    ((("C", "Hm, good one. First thing: I'd split reads from writes much earlier."),), "Tomás starts answering the follow-up, leaning forward.", "is answering the probe: he would separate reads from writes much earlier"),
    ((("C", "Month-end reporting queries were hitting the primary and causing lock waits on the hottest accounts."),), "Tomás goes on explaining, one hand flat on the desk.", "is still explaining that reporting queries on the primary caused lock contention"),
    ((("C", "Second, I'd publish to Kafka through an outbox table instead of inside the request."),), "Tomás holds up two fingers for his second point and carries on.", "carries on to a second point: he would publish through an outbox table rather than inside the request"),
    ((("C", "We lost a handful of events during a broker outage once, and an outbox would have made that impossible."),), "Tomás sounds rueful as he talks on.", "continues, recalling losing a handful of events during a broker outage"),
    ((("C", "And honestly, I'd write the runbooks on day one instead of in year two."),), "Tomás smiles at the camera and talks on.", "talks on, adding that he would write the runbooks from day one"),
    # t12-t31: Q2 asked at once; clarifications and the design
    ((("C", "That's what I'd change."), ("I", "Great, thanks. Next one: how would you design a rate limiter for a public API?")), "The interviewer went straight to the second prepared question; Tomás is already thinking it over.", "ends his reply to the probe, the interviewer goes straight on to item 2, a rate limiter for a public API, and he is now thinking it over"),
    ((("C", "Quick clarifying question: is the limit per API key, per user, or per IP?"), ("I", "Per API key, with a few premium tiers.")), "Tomás asks a clarifying question before starting his answer and is still thinking it over.", "asks a clarifying question, whether the limit is per key, per user or per IP, hears it is per API key with premium tiers, and is still mulling the item over before he replies"),
    ((("C", "And roughly what traffic are we talking about?"), ("I", "Say fifty thousand requests a second at peak, across three regions.")), "Tomás jots the numbers on a notepad after a second clarifying question; he has not handed the turn back and is still thinking the question over before he starts his answer.", "asks a second clarifying question, about traffic, hears fifty thousand requests a second across three regions and notes it down; he has not passed the turn back and is still mulling the item over before starting his reply"),
    ((("C", "Right. I'd start with a token bucket per key, since it allows short bursts but caps the average rate."),), "Tomás swivels round to the whiteboard behind his chair and starts answering.", "starts answering at the whiteboard, beginning the design with a token bucket per API key"),
    ((("C", "The bucket state lives in Redis: a count and a last-refill timestamp, updated atomically with a small script."),), "Tomás draws a Redis box on the whiteboard and carries on.", "carries on at the whiteboard, putting the bucket state in Redis, updated atomically by a script"),
    ((("C", "Premium tiers just get a bigger bucket and a faster refill, looked up from a config service."),), "Tomás adds a box labelled 'tiers', still explaining.", "keeps explaining as he sketches: premium tiers get bigger buckets looked up from a config service"),
    ((("C", "Now, the part I need to think about is where the check runs. Give me a second."),), "Tomás goes quiet and studies the whiteboard, still thinking it over.", "says he needs a second to think about where the check should run, then goes quiet, studying the board and still thinking it over"),
    ((), "About twenty seconds of silence; Tomás is still thinking through his answer, studying his diagram, marker in hand, lips moving.", "is silent for about twenty seconds but still thinking through his answer, studying his diagram with the marker in hand, lips moving"),
    ((("C", "Okay. I'd run it in the API gateway, so bad traffic never reaches the services behind it."),), "Tomás resumes his answer, pointing at the gateway box.", "resumes his answer, deciding the check should run in the API gateway"),
    ((("C", "Right, and I should say something about running this across three regions."),), "Tomás draws three circles for the regions and goes on.", "presses on to running the limiter across three regions"),
    ((("C", "Each region keeps its own... sorry, that's the doorbell, and now the dog."),), "The doorbell rings and a dog barks loudly in Tomás's room; he mutes for a moment in the middle of his answer.", "is cut off mid-sentence by his doorbell and barking dog, and mutes briefly in the middle of his answer"),
    ((("C", "Sorry about that, it was the delivery driver. Where was I... right, each region keeps its own buckets."),), "Tomás unmutes, apologises and carries on with his design.", "apologises for the delivery driver and carries on with per-region buckets"),
    ((("C", "Each key's budget is split across regions, say forty, forty and twenty percent, based on where its traffic comes from."),), "The doorbell rings again behind him; Tomás ignores it and talks on.", "ignores a second doorbell and keeps explaining how each key's budget is split across regions"),
    ((("C", "A small aggregator rebalances those budgets every minute, so a key whose traffic moves doesn't get starved."),), "Tomás adds an arrow to the diagram as he goes on.", "goes on to describe a small aggregator rebalancing regional budgets every minute"),
    ((("C", "That means a key can briefly go a few percent over its global limit, which I think is fine here."),), "Tomás glances up to check the interviewer is following, then continues.", "goes on, accepting a slight global overshoot as the trade-off"),
    ((("C", "I'm conscious I'm going long. Do you want me to move on?"), ("I", "No, take your time, keep going.")), "The interviewer waves him on, and Tomás continues his answer.", "offers to move on because he is running long, but the interviewer waves him on and he continues"),
    ((("C", "Okay. Rejected calls get a 429 with a Retry-After header, plus the remaining quota in the headers so clients can pace themselves."),), "Tomás writes header names on the board, still talking.", "carries on with the 429 response and the quota headers"),
    ((("C", "I'd also log every rejection with the key and tier, so support can answer the 'why was I throttled' tickets."),), "Tomás taps the logging box and keeps explaining.", "is adding, mid-answer, logging of every rejection for the support team"),
    ((("C", "And I'd ship it in shadow mode first: count what would be rejected, without rejecting anything, for a week."),), "Tomás underlines 'shadow mode' and goes on.", "continues: a week of shadow mode before enforcing anything"),
    ((("C", "Then turn enforcement on tier by tier, starting with the free tier."),), "Tomás writes 'enforce' on the board and talks on, marker still moving.", "carries on, marker moving: enforcement is switched on tier by tier, free tier first"),
    # t32-t34: Q2 answer finished, follow-up owed
    ((("C", "And that's my design."),), "Tomás puts the marker down, his answer finished, and waits; the interviewer is typing notes.", "says 'that's my design' and, his reply finished, puts the marker down and waits while the interviewer types"),
    ((("I", "Thanks. Give me a moment to get this down."),), "A chat message from the recruiter pops up on the interviewer's screen: 'Your next candidate has arrived early and is waiting in the lobby.' Tomás, his answer finished, sips his coffee and waits while the interviewer types.", "sips his coffee and waits, his reply finished, while the interviewer types, and a recruiter message says the next candidate has arrived early and is waiting in the lobby"),
    ((("C", "Take your time."),), "Tomás leans back, arms folded, his answer over, and waits while the interviewer keeps typing.", "tells the interviewer to take their time and waits, done with his reply, leaning back with his arms folded"),
    # t35-t37: candidate resumes to add a point
    ((("C", "Sorry, actually, one more thing on bursts. I'd cap each bucket at two seconds of traffic so a key can't dump a huge burst at once."),), "Tomás picks the marker back up and resumes his answer, adding to the design.", "picks the marker back up and resumes his answer, adding a cap on burst size to his design"),
    ((("C", "Otherwise a premium key that's been idle for an hour could hit a backend with its whole allowance in one go."),), "Tomás keeps adding to his answer at the board.", "keeps adding: an idle premium key could otherwise flood a backend"),
    ((("C", "So bucket size is the burst cap and refill rate is the sustained limit: two separate knobs per tier."),), "Tomás writes 'burst' and 'sustained' next to the tier box, still explaining.", "is still explaining at the board, describing burst size and refill rate as two separate settings per tier"),
    # t38-t40: finished again, follow-up still owed
    ((("C", "Okay, now I'm done. Promise."),), "Tomás sits back and waits, his answer over; the interviewer is typing again.", "says he is done now, promise, and sits back, his reply over, waiting while the interviewer types"),
    ((("C", "I'll just have some coffee while you write."), ("I", "Sure, go ahead.")), "Tomás, his answer finished, drinks from his mug and waits; the interviewer is typing.", "has stopped answering, says he will have some coffee while the interviewer writes, and waits"),
    ((("I", "One more line of notes and I'm with you."), ("C", "No rush. Ready when you are.")), "Tomás, done with his answer, sits back in his chair, waiting; the interviewer finishes a sentence in the notes.", "hears the interviewer ask for one more line of notes, says there is no rush, and waits, his reply over"),
    # t41-t49: follow-up asked and answered
    ((("I", "Here's a follow-up: what happens when the limiter's Redis goes down?"), ("C", "Ah, the fun part.")), "Tomás is thinking about the follow-up.", "hears the interviewer put item 2's probe to him, about the limiter's Redis going down, calls it the fun part and is thinking it over"),
    ((("C", "First decision is fail open or fail closed. For a public API I'd fail open, because rejecting everyone is worse than letting some abuse through."),), "Tomás starts answering, launching into the failure case.", "starts answering: he would fail open rather than reject every request"),
    ((("C", "But fail open with a local fallback: each gateway node keeps an in-memory bucket per key at about a third of the normal limit."),), "Tomás draws small boxes inside each gateway node as he goes on.", "goes on to add an in-memory fallback limit on every gateway node"),
    ((("C", "So abuse is still bounded, just more loosely, while Redis is out."),), "Tomás talks through the fallback, gesturing at the boxes.", "is still explaining that abuse stays bounded while Redis is out"),
    ((("C", "I'd alert when the fallback has been active for more than a minute, and page if it's more than ten."),), "Tomás writes the two thresholds on the board, still talking.", "carries on, setting alert and paging thresholds for the fallback"),
    ((("C", "Redis itself would be a cluster with replicas in each region, so a full outage should be rare."),), "Tomás carries on, now about the Redis setup.", "continues: Redis would be a replicated cluster in each region"),
    ((("C", "When it comes back, the buckets start full. Slightly generous, but much simpler than rebuilding state."),), "Tomás takes a sip of coffee, shrugs at the trade-off and continues.", "keeps explaining, between sips of coffee, that buckets start full when Redis comes back"),
    ((("C", "One risk is a thundering herd when every gateway reconnects at once, so I'd add jitter to the reconnects."),), "Tomás talks on quickly about the reconnect problem.", "talks on about jittered reconnects to avoid a thundering herd"),
    ((("C", "And I'd prove all of this with a game day where we actually kill Redis in staging."),), "Tomás adds another point, marker in hand, still mid-answer.", "carries on, mid-answer, adding a game day that kills Redis in staging"),
    # t50-t53: Q2 done; small talk while the interviewer types
    ((("C", "So yes: fail open, bounded locally, loud alerts. That's it for that one."),), "Tomás stops, his answer to the follow-up finished, and waits; the interviewer starts typing notes.", "sums up his reply to the probe as fail open, locally bounded, with loud alerts, and stops, his reply over"),
    ((("C", "While you type, out of curiosity: is the team on Go or Java these days?"), ("I", "Mostly Go, some Kotlin.")), "His answer done, Tomás leans back and chats about the team while the interviewer types notes.", "has stopped answering and chats while the interviewer types, asking whether the team uses Go or Java, and hears mostly Go"),
    ((("C", "Nice. I've been wanting to use Kotlin coroutines properly; I've only played with them on a side project."),), "Tomás, done with his answer, is making small talk; the interviewer is still typing.", "waits, done with his reply, making small talk about wanting to try Kotlin coroutines while the interviewer keeps typing"),
    ((("I", "Okay, nearly done with my notes."),), "The interviewer is finishing a line of notes; Tomás, his answer finished, waits.", "waits, his reply finished, while the interviewer says the notes are nearly done"),
    # t54-t66: Q3 asked and answered
    ((("I", "Next: tell me about a production incident you debugged."), ("C", "Sure, I've got a good one.")), "Tomás gathers his thoughts, thinking over the new question.", "hears the interviewer raise item 3, a production incident he debugged, says he has a good one and is thinking over how to start"),
    ((("C", "It was a Friday evening, and payouts to one bank started failing with timeouts, maybe one in five."),), "Tomás starts answering with the incident story.", "starts answering: one in five payouts to one bank timing out on a Friday evening"),
    ((("C", "Our dashboards looked fine. Latency to the bank's API was normal for everything except payouts."),), "Tomás leans towards the camera and carries on with the story.", "talks on: the dashboards looked fine except for payouts"),
    ((("C", "I pulled traces for the failing requests and saw they all went through one egress proxy."),), "Tomás mimes scrolling through traces as he goes on.", "goes on: traces showed every failure going through one egress proxy"),
    ((("C", "That proxy had been upgraded that afternoon, and its connection pool to the bank was capped at ten."),), "Tomás raises an eyebrow at the twist in his own story and keeps talking.", "carries on: the proxy had been upgraded that afternoon with a pool of ten connections"),
    ((("C", "Payouts are batchy. At six o'clock we send thousands, so they were queueing on those ten connections."),), "Tomás talks on, animated, clearly enjoying the story.", "is still explaining, animated, that the six o'clock payout batch queued on ten connections"),
    ((("C", "We rolled the pool size back to two hundred and the timeouts vanished within a minute."),), "Tomás talks through the fix, nodding to himself.", "continues: rolling the pool back fixed it within a minute"),
    ((("C", "The interesting part was why nobody caught it: the config diff was generated, so the reviewer never saw the pool change."),), "Tomás carries on to the part about the review process.", "keeps going: the pool change was hidden in a generated config diff"),
    ((("C", "So afterwards I added a check that fails the build when a generated config changes a limit by more than half."),), "Tomás goes on to what they changed afterwards, still answering.", "presses on to the check he built against large limit changes in generated configs"),
    ((("C", "We also added a saturation alert per destination on the proxy, which would have fired in the first two minutes."),), "Tomás lists the alert they added, counting on his fingers as he goes on.", "is listing, mid-answer, a per-destination saturation alert that would have fired early"),
    ((("C", "And we spread the bank payout batch over fifteen minutes instead of one burst at six."),), "Tomás adds another change they made and keeps talking.", "talks on, mentioning spreading the payout batch over fifteen minutes"),
    ((("C", "The postmortem was blameless. The engineer who did the upgrade ran the action items, which I think was the right call."),), "Tomás describes the postmortem, still talking steadily.", "carries on with a blameless postmortem led by the engineer who did the upgrade"),
    ((("C", "Total impact was about forty minutes and three hundred delayed payouts, all retried successfully."),), "Tomás gives the impact figures, mid-sentence.", "is still mid-answer, giving the impact: forty minutes and three hundred delayed payouts, all retried"),
    # t67-t69: Q3 finished (no follow-up planned)
    ((("C", "That's the incident."),), "Tomás stops, his answer finished, and waits; the interviewer is typing notes.", "says 'that's the incident', his reply over, and waits while the interviewer types"),
    ((("C", "Happy to go deeper on the postmortem or the tracing setup if that's useful."),), "The interviewer nods and keeps typing; Tomás, done with his answer, waits.", "offers to go deeper on the postmortem or the tracing, then waits, his reply finished, while the interviewer keeps typing"),
    ((("I", "Thanks, that's really clear. One second."),), "The interviewer is scrolling the plan; Tomás waits, his answer finished.", "waits, his reply over, while the interviewer thanks him and scrolls the sheet"),
    # t70-t82: Q4 asked and answered
    ((("I", "Next one: how would you change the schema of a busy table without downtime?"), ("C", "Say, adding a column that needs a backfill?"), ("I", "Sure, go with that.")), "After a clarifying question, Tomás starts answering, setting up his approach.", "hears the interviewer raise item 4, changing a busy table's schema without downtime, scopes it with a clarifying question about adding a backfilled column, and starts answering"),
    ((("C", "Rule one: never do it in one step. It's expand, migrate, contract."),), "Tomás is answering, starting with the overall shape.", "is answering, opening with expand, migrate, contract"),
    ((("C", "Expand: add the new column as nullable with no default, so Postgres doesn't rewrite the table."),), "Tomás writes 'expand' on the whiteboard and goes on.", "goes on: add the new column as nullable so the table is not rewritten"),
    ((("C", "Then deploy code that writes to both the old and new columns but still reads the old one."),), "Tomás draws two columns side by side, still talking.", "continues with dual writes while reading the old column"),
    ((("C", "Backfill in small batches, a few thousand rows at a time with a sleep, watching replication lag."),), "Tomás mimes a slow batch loop as he keeps explaining.", "keeps explaining backfills in small batches while watching replication lag"),
    ((("C", "When the backfill's done, verify it with a checksum on a sample, then switch reads to the new column behind a flag."),), "Tomás writes 'checksum' and 'flag' under the columns and carries on.", "carries on: verify the backfill and switch reads behind a flag"),
    ((("C", "Only then add the NOT NULL, via a check constraint created as NOT VALID and validated afterwards."),), "Tomás talks through the constraint step carefully.", "is talking through adding the not-null rule in two steps"),
    ((("C", "Contract comes last: stop writing the old column, wait a release, then drop it. And two more rules."),), "Tomás writes 'contract' at the end of the row and carries straight on.", "goes on to the contract step (stop writing, wait a release, drop), then carries straight on: two more rules"),
    ((("C", "Indexes always go in concurrently, and every migration gets a lock timeout so it can't queue behind a long transaction."),), "Tomás taps the board twice for emphasis and keeps going.", "keeps adding: concurrent index builds and lock timeouts on every migration"),
    ((("C", "At my last job a migration without a lock timeout took the ledger down for four minutes, so I'm a bit religious about it."),), "Tomás laughs at himself and goes on.", "is recalling, mid-answer, a migration without a lock timeout taking the ledger down for four minutes"),
    ((("C", "After that, all our migrations went through a bot that refused anything without a lock timeout."),), "Tomás keeps talking, now about the migration bot.", "keeps going, now about a bot that refused migrations without a lock timeout"),
    ((("C", "And every step was its own deploy, so any one of them could be reverted on its own."),), "Tomás draws one box per deploy and talks on.", "continues: every step was its own deploy"),
    ((("C", "It's slower, but it's boring, and boring is what you want on a busy table."),), "Tomás keeps talking, tapping the board.", "keeps talking, tapping the board: the slow way is boring, which is what a busy table needs"),
    # t83-t85: Q4 finished, follow-up owed, clock near the line
    ((("C", "That's how I'd do it."),), "Tomás stops and waits, his answer over; the interviewer is typing notes.", "says that is how he would do it and, his reply finished, waits while the interviewer types"),
    ((("C", "I know we're almost out of time, so no worries if we need to stop."),), "The interviewer keeps typing; Tomás, his answer finished, waits.", "remarks that he knows they are almost out of time, and waits, his reply over"),
    ((("I", "Just a second, finishing this bit."),), "The interviewer is typing; Tomás, done with his answer, sips his coffee and waits.", "has finished his reply and sips his coffee, waiting, while the interviewer finishes typing"),
    # t86-t88: under 5 minutes left, follow-up still unasked
    ((("I", "Okay..."),), "The interviewer glances at the clock and at the plan; Tomás, his answer over, waits.", "waits, his reply over, while the interviewer glances at the clock and the sheet"),
    ((), "The interviewer is reading the plan; Tomás, done with his answer, straightens the papers on his desk, waiting.", "has passed the turn back and straightens his papers, waiting, while the interviewer reads the sheet"),
    ((("I", "Let me just check one thing on the sheet."),), "The interviewer is scrolling the plan; Tomás has stopped answering and is waiting.", "has stopped answering and waits while the interviewer checks something on the sheet"),
    # t89-t92: interviewer asks the follow-up anyway; candidate answers
    ((("I", "We're nearly at time, but quickly: if that migration half-applies, how would you roll back?"), ("C", "Quick version, then.")), "Tomás starts answering the follow-up.", "hears the interviewer put item 4's probe on rolling back to him despite the time, and starts answering with a quick version"),
    ((("C", "Because every step is its own deploy, you roll back one step: turn the read flag off and you're on the old column again."),), "Tomás is answering quickly, pointing at the flag on the board.", "is answering: roll back one step by turning the read flag off"),
    ((("C", "If the backfill only half ran, you just leave it. The new column is nullable and nothing reads it."),), "Tomás keeps it brief but carries on.", "keeps it brief but carries on: a half-run backfill can simply be left alone"),
    ((("C", "The only step you can't undo is the drop, which is why it goes last and waits a full release."),), "Tomás talks on, pointing at the drop step on the board.", "carries on, pointing at the drop step: only the drop cannot be undone, which is why it goes last"),
    # t93-t99: everything done; closing
    ((("C", "That's my quick version."),), "Tomás stops, his answer to the follow-up over; the interviewer is noting it down.", "says that is his quick version and stops, his reply over"),
    ((("I", "Great. Thanks, Tomás, that's all my questions for today."),), "The interviewer is wrapping up; Tomás, his answer over, smiles and waits.", "waits, his reply finished, and hears the interviewer thank him and say those were all the questions"),
    ((("C", "Thanks! Can I ask what the next steps look like?"), ("I", "You'll hear from the recruiter within a week; the next round is system design.")), "Tomás has stopped answering questions and asks about next steps; the interviewer answers.", "has stopped answering questions, asks about next steps and hears the recruiter will be in touch within a week"),
    ((("C", "And is the team mostly on the payouts side or the ledger side?"), ("I", "Both, but this role is mostly payouts.")), "Tomás, done with his answers, is chatting with the interviewer about the team.", "chats, done with his answer, asking whether the team works on payouts or the ledger, and hears this role is mostly payouts"),
    ((("C", "Payouts is the part I'd enjoy most, honestly."), ("I", "Good to hear.")), "They are chatting; Tomás has stopped answering questions.", "has stopped answering and chats, saying payouts is the part he would enjoy most"),
    ((("I", "Thanks again for your time today."), ("C", "Thank you, this was fun.")), "They are saying goodbye; Tomás has finished answering.", "has finished answering and exchanges thanks and goodbyes with the interviewer"),
    ((("C", "Bye now!"),), "Tomás, done with his answers, waves and reaches for the button to leave the call.", "is done with his answers, waves goodbye and reaches to leave the call"),
]

# Irrelevant background lines for the lexical-decoy register, keyed by the
# action whose vocabulary they borrow. None of them concerns the interview.
A_DECOYS = {
    "let_answer": [
        "Behind the interviewer, someone tells a colleague to let the printer keep going; it is still working through a long job.",
        "A colleague passing the interviewer's desk says she will say nothing yet about the offsite and let the planning keep going.",
        "A teammate's chat on the second monitor says the nightly build is still working and to let it keep going.",
    ],
    "follow_up": [
        "An email preview from a furniture vendor reads: 'Quick follow-up on the quote we prepared for your current order.'",
        "A calendar reminder for tomorrow says: 'Follow up with facilities about the required desk move.'",
        "A colleague's chat status says: 'Preparing follow-up questions for Friday's pub quiz.'",
    ],
    "next_question": [
        "The office pub-quiz organiser posts: 'Next week's questions are prepared; nothing is owed from last week's round.'",
        "A coworker nearby asks the team to move on to the next item on the lunch order.",
        "A trivia app on the interviewer's phone lights up: 'Ready for the next question?'",
    ],
    "close": [
        "An IT banner in the corner of the screen says: 'Please close all windows tonight; thank you for your patience during maintenance.'",
        "A facilities email announces that the kitchen will close early today and thanks everyone for keeping it tidy.",
        "A note on the meeting-room door reads: 'Close the door when you leave, and thank you for booking through the panel.'",
    ],
}
A_DECOY_LABELS = ["Around the interviewer:", "In the interviewer's office:", "Also nearby:"]

# Minimal counterfactual surfaces: same moment, one fact changed.
A_CF_FU_WAIT = {
    6: ((("C", "And that's the ledger, more or less."),), "Tomás stops, his answer finished, and waits; the interviewer is typing notes and has not asked anything yet.", "wraps up the ledger story, his reply over, and waits while the interviewer types, with no probe put yet"),
    7: ((("I", "Sorry, just getting that down."),), "The interviewer is still typing; Tomás, done with his answer, sips his coffee, waiting.", "has finished his reply and sips his coffee, waiting while the interviewer apologises and keeps typing"),
    8: ((("C", "No rush."),), "Tomás, his answer over, is waiting; the interviewer is still typing notes.", "says there is no rush and waits, his reply over, while the interviewer types"),
    9: ((("I", "Looking back, what would you change about its design today?"), ("C", "Hm. I'd publish to Kafka through an outbox table instead of inside the request.")), "Tomás starts answering the follow-up, leaning forward.", "hears the interviewer put item 1's probe to him and starts answering: he would publish through an outbox table"),
}
A_CF_DESIGN_DONE = {
    18: ((("C", "And that's the core of my design, really."),), "Tomás puts the marker down and waits, his answer over; the interviewer is typing notes.", "says that is the core of his design and, his reply finished, puts the marker down and waits while the interviewer types"),
    19: ((), "About twenty seconds of quiet; the interviewer is typing and Tomás, done with his answer, is waiting, marker on the desk.", "waits quietly for about twenty seconds, his reply over, while the interviewer types, marker on the desk"),
    20: ((("I", "Sorry, still catching up on my notes."),), "Tomás, done with his answer, waits for the interviewer to finish typing.", "has finished his design and waits while the interviewer says they are still catching up on notes"),
    # Same words as canonical t21, but he had stopped, so the camera line says he resumes rather than goes on.
    21: ((("C", "Right, and I should say something about running this across three regions."),), "Tomás picks the marker back up and resumes his answer, drawing three circles for the regions.", "picks the marker back up and resumes his answer, turning to running the limiter across three regions"),
}
A_CF_STILL_FU = {
    50: ((("C", "So yes: fail open, bounded locally. Oh, and one more piece: the fallback limits need to follow the tiers too."),), "Tomás keeps going on the follow-up; the interviewer is listening.", "sums up fail open, locally bounded, then carries on: the fallback limits must follow the tiers"),
    51: ((("C", "Otherwise a premium key gets the same third-of-normal limit as a free key, which would break their integrations."),), "Tomás talks on; the interviewer is listening.", "goes on to explain that premium keys would otherwise get the same fallback as free keys"),
    52: ((("C", "So the tier table is pushed to every gateway node every few minutes and cached there."),), "Tomás draws the tier table next to the gateway nodes as he talks on.", "keeps explaining that the tier table is pushed to and cached on every gateway node"),
    53: ((("C", "That way even a long Redis outage keeps the tiers right, and..."),), "Tomás is mid-sentence, still on the follow-up.", "is mid-sentence, explaining that tiers stay right even in a long Redis outage"),
    54: ((("C", "...so the tiers stay right. That's everything on that."), ("I", "Thanks. Next: tell me about a production incident you debugged."), ("C", "Sure, I've got a good one.")), "Tomás gathers his thoughts, thinking over the new question.", "finishes his reply to the probe, hears the interviewer raise item 3, a production incident he debugged, and is thinking over how to start"),
}


def _a_surface(entry: tuple[Any, str, str]) -> dict[str, Any]:
    lines, stage, gist = entry
    return {"lines": [list(x) for x in lines], "stage": stage, "gist": gist}


# Phase cues for the easy tier. Rule 1 comes first, so the candidate's phase
# decides the gold at every tick: every stage line and every gist must say it in
# words. ``A_ONGOING`` marks a candidate still working on the question (talking
# it through, thinking it over, not yet handing the turn back); ``A_DONE`` marks
# one who has stopped. An answering tick's stage line carries only the first,
# a finished tick's only the second. A bare mention of a clarifying question
# does not count: once it has been answered, the line must still say that he is
# thinking the question over or has not handed the turn back. Waiting alone
# ("sips his coffee and waits") does not count either: a finished tick's stage
# line and gist must both also say that the answer itself is over
# (``A_ANSWER_OVER``: "his answer finished", "done with his reply", "has
# stopped answering", "has passed the turn back").
A_ONGOING = re.compile(
    r"\b(still (answering|talking|thinking|explaining|mid-\w+|on the follow-up)|is (answering|replying)|starts answering|resumes"
    r"|carr(y|ies|ying) (straight )?on|goes on|talks on|talk(s|ing) through|keeps (talking|going|explaining|adding)"
    r"|continu\w*|presses on|mid-(answer|sentence|flow|story)|in the middle of his answer"
    r"|thinking (it |the question |the item )?(over|about|through)|mulling|not (handed|passed) the turn back)",
    re.I,
)
A_DONE = re.compile(
    r"\b(stops|stopped|waits|waiting|has finished|his answers? (is |are )?(finished|over|done)|done with his answers?)",
    re.I,
)
A_ANSWER_OVER = re.compile(
    r"\b(his (answers?|repl(y|ies))( to the (follow-up|probe))? (is |are )?(finished|over|done)"
    r"|done with his (answers?|repl(y|ies))|has (stopped|finished) answering|has finished his (answer|reply|design)"
    r"|has passed the turn back)",
    re.I,
)


def _check_a_phase_cues(variant: str, ticks: list[Tick]) -> None:
    """Refuse a tick whose stage line or gist does not state the candidate's phase in words."""
    for t, tk in enumerate(ticks):
        stage, gist = tk.surface["stage"], tk.surface["gist"]
        if tk.latent["phase"] == "answering":
            ok = bool(A_ONGOING.search(stage)) and not A_DONE.search(stage) and not A_ANSWER_OVER.search(stage) and bool(A_ONGOING.search(gist))
        else:
            ok = (bool(A_DONE.search(stage)) and bool(A_ANSWER_OVER.search(stage)) and not A_ONGOING.search(stage)
                  and bool(A_ANSWER_OVER.search(gist)))
        if not ok:
            raise ValueError(f"interview_a/{variant} t={t}: phase '{tk.latent['phase']}' is not stated in words: {stage!r} / {gist!r}")


class BackendInterview(Scenario):
    family = FAMILY
    scenario_id = "interview_a"
    title = "Next-move copilot for a structured backend-engineer interview"
    tier = "easy"
    difficulty_features = [
        "single_choice_question",
        "four_options_with_use_when_clauses",
        "four_rule_priority_policy",
        "explicit_plan_marks",
        "phase_stated_explicitly",
        "clock_subtraction",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "terminate", "resolve-conflict"]
    deadline_steps = 2

    TICK_SECONDS = 20
    CLOCK_OFFSET = 100  # t85 sits exactly on the 5-minute line (30:00 elapsed)

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            instructions = {
                "role": "You advise the person conducting a 35-minute structured hiring conversation for a server-side software role, telling them their next move at every moment. `question_sheet` gives the planned items in order, each with its standing (complete, in play, not reached yet or flagged to be left out) and its probe; the item in play also says whether it is complete yet. `timing` gives the time used. `just_before` and `happening_now` describe the conversation, and `happening_now` says in words whether the interviewee is still busy with the item or has finished the reply and passed the turn back.",
                "definitions": A_DEFS_P,
                "rules": A_RULES_P,
                "question": "Work down the rules and use the first one that fits this moment. What is the interviewer's next move?",
            }
            options = A_OPTIONS_P
        else:
            instructions = {
                "role": "You are a copilot for an interviewer running a structured 35-minute interview for a backend engineer role; at every moment you say what the interviewer should do next. The state shows the interview plan (prepared questions in order, each marked [done], [current], [ ] for not asked yet, or [skip]; the [current] question also says whether it is done yet and whether its follow-up has been asked), the clock, the latest exchange, and what can be seen on the call, which says in words whether the candidate is still answering or has finished his answer.",
                "definitions": A_DEFS,
                "policy": A_RULES,
                "question": "Apply the first rule that matches the current state. What should the interviewer do right now?",
            }
            options = A_OPTIONS_D if variant == "lexical_decoy" else A_OPTIONS
        return [Choice("action", instructions, dict(options))]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "q": "q1",
                "done": [],
                "phase": "answering",
                "fu_asked": False,
                "fu_req": dict(A_FU_REQ),
                "skip": [],
                "elapsed_s": 0,
                "slot_s": A_SLOT,
            }
        )
        events: dict[int, tuple[dict[str, Any], str]] = {
            4: ({}, "'In short, that's the service' is a lead-in; he carries straight on."),
            6: ({"fu_asked": True}, "Q1 follow-up asked at once; he is thinking about it."),
            12: ({"q": "q2", "done": ["q1"], "fu_asked": False}, "Q1 done; Q2 asked at once; he is thinking it over."),
            18: ({}, "'Give me a second' and silence: still thinking about Q2."),
            22: ({}, "Doorbell and dog interrupt, but he is still mid-answer."),
            27: ({}, "Offer to move on is waved off; still answering."),
            32: ({"phase": "finished"}, "Q2 answer finished; its required follow-up not asked."),
            33: ({}, "Recruiter says the next candidate has arrived early, but 22:20 remain: the follow-up is still owed."),
            35: ({"phase": "answering"}, "Candidate resumes to add a point."),
            38: ({"phase": "finished"}, "Finished again; the follow-up is still owed."),
            41: ({"phase": "answering", "fu_asked": True}, "Q2 follow-up asked; he is thinking about it."),
            50: ({"phase": "finished", "done": ["q1", "q2"]}, "Q2 follow-up answered: Q2 done; Q3 not asked yet."),
            51: ({}, "Small talk while the interviewer types is not working on a question."),
            54: ({"q": "q3", "phase": "answering", "fu_asked": False}, "Q3 asked."),
            67: ({"phase": "finished", "done": ["q1", "q2", "q3"]}, "Q3 finished; no follow-up planned, so Q3 is done."),
            68: ({}, "An offer to go deeper is not a planned follow-up."),
            70: ({"q": "q4", "phase": "answering", "fu_asked": False}, "Q4 asked."),
            83: ({"phase": "finished"}, "Q4 finished; follow-up owed; 5:40 left."),
            84: ({}, "'Almost out of time', but 5:20 remain."),
            85: ({}, "Exactly 5:00 left is not fewer than 5 minutes: the follow-up is still owed."),
            86: ({}, "4:40 left: the clock rule outranks the owed follow-up."),
            89: ({"phase": "answering", "fu_asked": True}, "Interviewer asks the follow-up anyway: letting him answer outranks the clock."),
            93: ({"phase": "finished", "done": ["q1", "q2", "q3", "q4"]}, "Every question done; 2:20 left."),
        }
        tags = span_tags(
            {
                "distractor": [4, (18, 19), 27, 33, (51, 52), 68, 84],
                "minimal_change": [32, 67, 86],
                "recovery": [35, 38, 93],
                "hold_under_activity": [(6, 8), (12, 14), (22, 24), (95, 97)],
                "priority_conflict": [(86, 92)],
                "boundary": [(93, 99)],
                "arithmetic": [(83, 88)],
            }
        )
        for t in range(100):
            updates, note = events.get(t, ({}, ""))
            tl.step(_a_surface(A_SCRIPT[t]), tags[t], note, elapsed_s=self.TICK_SECONDS * t + self.CLOCK_OFFSET, **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t6-8: the interviewer has not put the Q1 follow-up yet (let_answer -> follow_up).
            ticks = override(ticks, [6, 7, 8], phase="finished", fu_asked=False, tags=["minimal_change"],
                             note="Q1 answer finished; follow-up not asked yet.",
                             surface=lambda tk, i: _a_surface(A_CF_FU_WAIT[i]))
            ticks = override(ticks, [9], note="Follow-up asked at the start of this window.",
                             surface=lambda tk, i: _a_surface(A_CF_FU_WAIT[i]))
            # (2) t18-20: the candidate declares the design finished instead of pausing to think (let_answer -> follow_up).
            ticks = override(ticks, [18, 19, 20], phase="finished", tags=["minimal_change"],
                             note="Candidate says the design is finished; Q2 follow-up owed.",
                             surface=lambda tk, i: _a_surface(A_CF_DESIGN_DONE[i]))
            # t21 keeps its latent state; its camera line shows him resuming after the stop.
            ticks = override(ticks, [21], note="He resumes his answer on his own before the follow-up is asked.",
                             surface=lambda tk, i: _a_surface(A_CF_DESIGN_DONE[i]))
            # (3) t50-53: still answering the follow-up instead of small talk (next_question -> let_answer).
            ticks = override(ticks, [50, 51, 52, 53], phase="answering", done=["q1"], tags=["minimal_change"],
                             note="Still answering the Q2 follow-up.",
                             surface=lambda tk, i: _a_surface(A_CF_STILL_FU[i]))
            # t54 keeps its latent state; its surface shows him finishing before Q3 is asked.
            ticks = override(ticks, [54], note="He finishes the follow-up answer and Q3 is asked in the same window.",
                             surface=lambda tk, i: _a_surface(A_CF_STILL_FU[i]))
        elif variant == "structural_cf":
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["skip"] = [A_STRUCTURAL_SKIP]
                # A skipped question owes nothing, its follow-up included.
                tk.latent["fu_req"][A_STRUCTURAL_SKIP] = False
            ticks = _set_tags(
                ticks,
                {67: [], 68: ["distractor"], 69: [], 83: [], 84: [], 85: [], 86: [], 87: [], 88: []},
                {
                    67: "Q3 finished; Q1-Q3 done and Q4 marked skip: the plan is exhausted.",
                    68: "An offer to go deeper tempts a follow-up, but the plan is exhausted.",
                    69: "Plan still exhausted.",
                    70: "Q4 asked although it is marked skip; it is the current question while he answers.",
                    83: "Q4 finished; Q4 is marked skip, so it needs nothing more: the plan is exhausted.",
                    84: "Plan exhausted; the time remark changes nothing.",
                    85: "Plan exhausted (and exactly 5:00 left).",
                    86: "Plan exhausted and under 5 minutes left.",
                    89: "Interviewer asks the Q4 follow-up anyway; letting him answer outranks the exhausted plan and the clock.",
                    93: "Follow-up answered; plan exhausted and 2:20 left.",
                },
            )
        _check_a_phase_cues(variant, ticks)
        return ticks

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        remaining = z["slot_s"] - z["elapsed_s"]
        if z["phase"] == "answering":
            action = "let_answer"
        elif all(q in z["done"] or q in z["skip"] for q in A_ORDER) or remaining < 300:
            action = "close"
        elif z["fu_req"][z["q"]] and not z["fu_asked"]:
            action = "follow_up"
        else:
            action = "next_question"
        return {"action": action}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Structured interview with four prepared questions. The plan marks what is done (the current question included) and whether the current follow-up was asked; the camera line says in words whether the candidate is still answering or has stopped. Follow-ups asked at once and after a note-taking pause, a thinking silence, a candidate who resumes after saying he is done, a recruiter ping while a follow-up is owed, small talk while notes are typed, a question with no planned follow-up, a clock that reaches exactly 5:00 left and then crosses the line while a follow-up is owed, and a late follow-up the candidate is allowed to finish."},
            "paraphrase": {"summary": "Same latent trajectory; item/probe/booking vocabulary, JSON fields with each item's standing on the sheet (the item in play says whether it is complete) and narrated moments that say whether he is still busy with the item, instead of a marked list, reworded definitions, rules and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; each state adds one or two irrelevant office details borrowing an action's vocabulary (mostly a wrong action's, a third of the time any action's), placed on their own line, before the exchange or inside the camera line."},
            "minimal_cf": {"summary": "Three minimal edits: t6-8 the Q1 follow-up is not asked straight away (let_answer->follow_up); t18-20 the candidate declares the design finished instead of pausing to think (let_answer->follow_up), and at t21 the camera line shows him resuming on his own; t50-53 he is still answering the Q2 follow-up instead of making small talk (next_question->let_answer), finishing it at t54 as Q3 is asked."},
            "structural_cf": {"summary": "The plan marks Q4 (schema migration) as skip because the phone screen covered it, so it owes nothing, its follow-up included. With Q1-Q3 done, the plan is exhausted once Q3 finishes (t67-69 next_question->close) and again when the Q4 answer the interviewer asked anyway finishes (t83-85 follow_up->close). While he answers Q4 it is marked [current, marked skip]."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    @staticmethod
    def _asked_at(history: list[Tick], q: str, follow_up: bool = False) -> int:
        """Elapsed seconds at which the current question (or its follow-up) was asked."""
        for i, tk in enumerate(history):
            z = tk.latent
            if z["q"] == q and (z["fu_asked"] if follow_up else True):
                return z["elapsed_s"] - (20 if i == 0 else 10)
        return history[-1].latent["elapsed_s"]

    def _plan(self, history: list[Tick]) -> list[str]:
        z = history[-1].latent
        t = len(history) - 1
        lines = []
        for i, q in enumerate(A_ORDER, start=1):
            text, fu = A_PLAN[q]
            label = f"Q{i}"
            skip = q in z["skip"]
            current = q == z["q"]
            if current:
                mark = "[current, marked skip]" if skip else "[current]"
                if skip:
                    status = " although it is marked skip"
                elif q in z["done"]:
                    status = "; " + pick(["now done", "done"], "a-cur-done", t)
                else:
                    status = "; " + pick(["not done yet", "not yet done"], "a-cur-open", t)
                head = f"{mark} {label} (asked at {mmss(self._asked_at(history, q))}{status}). {text}."
            else:
                mark = "[skip]" if skip else "[done]" if q in z["done"] else "[ ]"
                head = f"{mark} {label}. {text}."
            if fu is None:
                tail = "Follow-up: none planned."
            elif skip:
                tail = f"Follow-up (not needed, since {label} is marked skip"
                if current and z["fu_asked"]:
                    tail += f"; the interviewer asked it anyway at {mmss(self._asked_at(history, q, True))}"
                tail += f"): {fu}"
            elif current:
                if z["fu_asked"]:
                    tail = f"Follow-up (required, asked at {mmss(self._asked_at(history, q, True))}): {fu}"
                else:
                    tail = f"Follow-up (required, not asked yet): {fu}"
            elif q in z["done"]:
                tail = f"Follow-up (required, asked): {fu}"
            else:
                tail = f"Follow-up (required): {fu}"
            line = f"{head} {tail}"
            if skip:
                line += " Marked skip: fully covered in his phone screen on 12 September."
            lines.append(line)
        return lines

    @staticmethod
    def _exchange(history: list[Tick]) -> list[list[str]]:
        """This window's lines, preceded (if fewer than two) by the last line spoken before it, past any silent window."""
        lines = list(history[-1].surface["lines"])
        if len(lines) < 2:
            spoken = next((tk.surface["lines"] for tk in reversed(history[:-1]) if tk.surface["lines"]), None)
            if spoken:
                lines = [spoken[-1]] + lines
        return lines

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        clock = pick(
            ["Clock: {e} elapsed of the 35-minute slot.", "Time: {e} into the 35:00 slot.", "Elapsed: {e} (slot: 35 minutes)."],
            "a-clock",
            t,
        ).format(e=mmss(z["elapsed_s"]))
        said = " / ".join(f"{'Candidate' if s == 'C' else 'Interviewer'}: \"{x}\"" for s, x in self._exchange(history))
        stage = tick.surface["stage"]
        exchange = f"Last exchange: {said or '(nobody is speaking)'}"
        head = ["Backend engineer interview (structured, 35-minute slot). Candidate: Tomás Ferreira.", "Plan:", *self._plan(history), clock]
        tail = [exchange, f"On the call: {stage}"]
        if variant == "lexical_decoy":
            lines = _decoy_lines(A_DECOYS, self.policy(z)["action"], t, "a")
            place = pick(["line", "before", "camera"], "a-decoy-place", t)
            if place == "camera":
                tail[-1] += f" (Off camera: {lines[0][0].lower()}{lines[0][1:]})"
                lines = lines[1:]
            if lines:
                extra = f"{pick(A_DECOY_LABELS, 'a-decoy-label', t)} {' '.join(lines)}"
                if place == "before":
                    head.append(extra)
                else:
                    tail.append(extra)
        return "\n".join(head + tail)

    def _sheet_p(self, history: list[Tick]) -> str:
        z = history[-1].latent
        items = []
        for i, q in enumerate(A_ORDER, start=1):
            text, fu = A_PLAN_P[q]
            skip = q in z["skip"]
            if q == z["q"]:
                standing = f"in play, raised at {mmss(self._asked_at(history, q))}"
                if skip:
                    standing += " although it is flagged to be left out"
                elif q in z["done"]:
                    standing += pick([", now complete", ", and complete"], "p-cur-done", len(history) - 1)
                else:
                    standing += pick([", not complete yet", ", not yet complete"], "p-cur-open", len(history) - 1)
            elif skip:
                standing = "flagged to be left out"
            elif q in z["done"]:
                standing = "complete"
            else:
                standing = "not reached yet"
            if fu is None:
                probe = "no probe planned"
            elif skip:
                probe = f"probe ({fu}) not needed, as the item is flagged"
                if q == z["q"] and z["fu_asked"]:
                    probe += f", though the interviewer put it anyway at {mmss(self._asked_at(history, q, True))}"
            elif q == z["q"]:
                probe = f"mandatory probe: {fu}, " + (f"put at {mmss(self._asked_at(history, q, True))}" if z["fu_asked"] else "not put yet")
            elif q in z["done"]:
                probe = f"mandatory probe: {fu}, put"
            else:
                probe = f"mandatory probe: {fu}"
            item = f"item {i} ({standing}): {text}; {probe}"
            if skip:
                item += " - flagged because the phone screen on 12 September already dealt with it"
            items.append(item)
        return "; ".join(items) + "."

    def _render_paraphrase(self, history: list[Tick]) -> dict[str, Any]:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        e = z["elapsed_s"]
        timing = pick(
            [
                "{m} min {s:02d} s of the 35-minute booking have gone by.",
                "The booking runs 35 minutes; {m} min {s:02d} s are behind us.",
            ],
            "p-time",
            t,
        ).format(m=e // 60, s=e % 60)
        now = pick(["Tomás {g}.", "At this moment Tomás {g}.", "The interviewee {g}.", "Right now he {g}."], "p-now", t).format(g=tick.surface["gist"])
        state: dict[str, Any] = {"question_sheet": self._sheet_p(history), "timing": timing}
        if len(history) > 1:
            state["just_before"] = pick(["Twenty seconds earlier: he {g}.", "The twenty seconds before: Tomás {g}."], "p-before", t).format(g=history[-2].surface["gist"])
        state["happening_now"] = now
        return state


# ===========================================================================
# Scenario B - user-research discovery interview; action + guide topic
# ===========================================================================

B_ORDER = ["overspend", "shared", "saving", "alerts", "switching"]
B_SLOT = 3600
B_START = 14 * 3600  # the session is booked 14:00-15:00
B_WARMUP = "money routines today"
B_WARMUP_P = "how they keep track of money at the moment"
B_TOPICS = {
    "overspend": ("When spending got away from them", "what the overspend was on", "how they found out"),
    "shared": ("Shared costs", "how bills are split", "where splitting causes friction"),
    "saving": ("Saving goals", "a specific goal", "what gets in the way"),
    "alerts": ("Alerts and nudges", "one they find useful", "one they ignore or turned off"),
    "switching": ("Switching apps", "what would make them try a new app", "what would make them abandon one"),
}
B_TOPICS_P = {
    "overspend": ("The month that went over budget", "what the extra spending went on", "how they discovered it"),
    "shared": ("Splitting bills with others", "the way costs get divided", "what causes tension over the split"),
    "saving": ("Putting money aside", "a concrete thing they are saving towards", "what stops them saving"),
    "alerts": ("Notifications", "a notification they value", "one they ignore or have switched off"),
    "switching": ("Changing to a new app", "what would get them to try one", "what would make them drop one"),
}
B_NOTES = {
    "overspend": {"a": "trains, hotel and hospital cafe during dad's surgery", "b": "card declined at Leeds station"},
    "shared": {"a": "shared phone note, settled monthly", "b": "Mia pays rent late, Dana covers it"},
    "saving": {"a": "deposit for a flat of her own", "b": "takeaways and birthday presents"},
    "alerts": {"a": "low-balance text", "b": "ignores per-purchase bank pings"},
    "switching": {"a": "a friend uses it, no linking accounts up front", "b": "deletes any app that shows ads"},
}
B_NOTES_P = {
    "overspend": {"a": "travel, a hotel and hospital food while her father was in for surgery", "b": "her card bounced at the station in Leeds"},
    "shared": {"a": "a note shared on their phones, squared up monthly", "b": "Mia is late with her share of rent, so Dana fronts it"},
    "saving": {"a": "a deposit on a place of her own", "b": "takeaway food and presents"},
    "alerts": {"a": "the warning when her balance runs low", "b": "the per-purchase messages she tunes out"},
    "switching": {"a": "a friend's recommendation and no linking of accounts up front", "b": "any app with adverts gets deleted"},
}
# Structural counterfactual: the screener survey already answered these points.
B_STRUCTURAL_SCREENER = {"alerts": ["a", "b"], "switching": ["b"]}
B_SCREENER = {
    "alerts": {"a": "screener: likes the low-balance text", "b": "screener: tunes out the per-purchase pings"},
    "switching": {"b": "screener: deletes any app that shows ads"},
}
B_SCREENER_P = {
    "alerts": {"a": "from the screener: values the low-balance warning", "b": "from the screener: ignores the per-purchase messages"},
    "switching": {"b": "from the screener: deletes any app that shows adverts"},
}
B_OFFTOPIC = {"running club": "talking about her Saturday running club"}
B_OFFTOPIC_P = {"running club": "going on about her Saturday running group"}

B_POLICY = [
    "1. If the session is paused because the participant is on another call, has stepped away, or has asked for a moment: action = stay quiet, topic = no topic.",
    "2. Otherwise, if fewer than 8 minutes of the 60-minute session remain, or every must-cover point of all five topics is covered: action = wrap up (or keep wrapping up) and end the session, topic = no topic.",
    "3. Otherwise, if the participant is still talking, or is still thinking about a question just put to them: action = stay quiet, topic = no topic. Exception: talk that has nothing to do with the warm-up or any guide topic stops counting once it has lasted 60 seconds or more; from then on treat the participant as finished and apply rules 4-6.",
    "4. Otherwise, if the current topic still has an uncovered must-cover point: action = probe deeper, topic = the current topic.",
    "5. Otherwise, if a topic that comes earlier in the guide than the current topic still has an uncovered must-cover point (it was skipped or cut short): action = return to it, topic = the earliest such topic.",
    "6. Otherwise: action = move on, topic = the first topic after the current one, in guide order, that still has an uncovered must-cover point.",
]
B_COVERAGE = "A must-cover point counts as covered when the coverage notes or the guide mark it covered, or when the participant clearly addresses it in the transcript shown. The notes are typed live and can lag behind the transcript. Topics are numbered T1-T5 in guide order. The warm-up comes before T1 and has no must-cover points, so while it is the current topic rules 4 and 5 cannot apply."
B_POLICY_P = [
    "1. When the session is on pause because the interviewee is on another call, has left the room, or has asked for a minute: say nothing, subject = none.",
    "2. If not, and under 8 minutes of the 60-minute booking are left, or both key points of all five subjects have been captured: begin or carry on with the wrap-up, subject = none.",
    "3. If not, and the interviewee is still speaking or still mulling over a question just asked: say nothing, subject = none. Exception: talk unconnected to the warm-up and to every guide subject stops counting as soon as it has run for 60 seconds or more; from then on treat the interviewee as through and go to rules 4 to 6.",
    "4. If not, and the subject in play still has a key point not captured: dig further, subject = the one in play.",
    "5. If not, and a subject placed before the one in play still has a key point not captured (it was passed over or left unfinished): go back to it, subject = the first such one in guide order.",
    "6. Otherwise: advance, subject = the first subject after the one in play, in guide order, that still has a key point not captured.",
]
B_COVERAGE_P = "A key point is captured when the note-taker's record or the guide itself marks it so, or when the interviewee plainly speaks to it in the recent exchange described. The record is typed live and may trail the conversation. The warm-up comes before subject 1 and has no key points, so while it is under way rules 4 and 5 cannot apply."

B_ACTIONS = {
    "quiet": "Stay quiet for now and give the participant room.",
    "probe": "Probe deeper on the current guide topic.",
    "return": "Return to an earlier guide topic that still has gaps.",
    "next": "Move on to a later guide topic that still has gaps.",
    "end": "Wrap up (or keep wrapping up) and bring the session to an end.",
}
B_ACTIONS_P = {
    "quiet": "Say nothing and leave the space to the interviewee.",
    "probe": "Dig further into the guide subject in play at the moment.",
    "return": "Go back to a guide subject from before that is still incomplete.",
    "next": "Advance to a guide subject further down that is still incomplete.",
    "end": "Begin or carry on with the wrap-up and close the session.",
}
B_ACTIONS_D = {
    "quiet": "Stay quiet and give the participant room for now.",
    "probe": "Probe deeper on the guide topic that is current right now.",
    "return": "Return to an earlier guide topic that still has gaps.",
    "next": "Move on to a later guide topic that still has gaps.",
    "end": "Wrap up (or keep wrapping up) and end the session.",
}

# Surface content per tick: (turns, stage, gist[, thread]). Speakers: "D" Dana,
# "M" moderator, "N" note-taker (chat), "P" Dana speaking into her phone. The
# stage line is what the copilot sees on video, and it is where whether Dana is
# still talking shows. At every tick outside the phone-call pause the stage line
# (and the paraphrase gist) says it in words: a gesture alone ("Dana counts the
# bills on her fingers") after a complete-sounding sentence reads either way.
# ``_check_phase_cues`` enforces this. ``thread`` = (start tick, what she has
# been talking about) marks a long stretch on one subject that the state times
# from its start; whether that subject relates to the guide is left to the reader.
B_SCRIPT: list[tuple[Any, ...]] = [
    # t0-t11: warm-up (money routines; asked at 14:07:15)
    ((("D", "Okay, so how I keep track of money... it's a bit of a patchwork, honestly."),), "Dana is on video from her kitchen table, mug in hand, talking.", "starts describing how she keeps track of money, calling it a patchwork"),
    ((("D", "The main thing is a spreadsheet my sister set up for me when I moved out, one tab per month."),), "Dana talks easily, mug in hand.", "goes on: her main tool is a spreadsheet her sister set up, one tab per month"),
    ((("D", "I paste in my bank export and colour-code everything: green for bills, orange for food, red for 'why did I buy that'."),), "Dana laughs at herself and goes on.", "is describing, mid-flow, how she pastes in her bank export and colour-codes every line"),
    ((("D", "Rent and bills are fine. It's the small stuff that gets away from me: coffees, delivery fees, that kind of thing."),), "Dana keeps going with her routine.", "carries on: the small stuff, like coffees and delivery fees, is what gets away from her"),
    ((("D", "I sit down with it every Sunday night with a cup of tea. It's kind of my ritual."),), "Dana smiles as she talks.", "is in full flow: she sits down with the spreadsheet every Sunday night with tea, as a ritual"),
    ((("D", "Some Sundays I skip it, and then the next one is twice as painful because there are two weeks to paste in."),), "Dana pulls a face and carries on.", "admits, still going, that skipping a Sunday makes the next one twice as painful"),
    ((("M", "Mm-hm."), ("D", "My sister checks hers every single day, which I think is a bit much.")), "Dana is going strong; the moderator nods along.", "keeps talking: her sister checks her own sheet daily, which she finds a bit much"),
    ((("D", "The sheet has formulas that total each category, but half of them break whenever I add a row."),), "Dana rolls her eyes and keeps talking.", "complains, mid-sentence, that the category formulas break whenever she adds a row"),
    ((("D", "Anyway, that's probably more than you wanted to know about my spreadsheet. Oh, but the budget tab is the interesting bit."),), "Dana carries straight on.", "says that is probably more than they wanted to know, then carries straight on to the budget tab"),
    ((("D", "That's where I set a limit per category at the start of the month and see how far over I went."),), "Dana mimes a table with her hands and keeps explaining.", "is explaining the budget tab, where she sets a limit per category each month"),
    ((("D", "Food is always over. Always. Like thirty or forty percent over."),), "Dana shakes her head, mid-sentence.", "is on to food, which she says is always thirty or forty percent over, and continues"),
    ((("D", "I've tried a couple of apps before, but I always drift back to the sheet because I trust it more."),), "Dana keeps talking about apps she has tried.", "is still talking, saying she has tried apps but drifts back to the sheet because she trusts it more"),
    # t12-t25: T1 raised at once; the story of March
    ((("D", "So yeah, that's the system."), ("M", "That's really helpful. Can you tell me about the last time your spending got away from you?")), "The moderator went straight to the first guide topic; Dana is thinking.", "wraps up her system, the moderator at once asks about the last time her spending got away from her, and she thinks"),
    ((("D", "Oof. Okay. That would be March, probably."),), "Dana puts her mug down, thinking.", "says that would probably be March, and puts her mug down to think"),
    ((("D", "Let me think how to explain it... it wasn't a normal month."),), "Dana is gathering her thoughts.", "is working out how to explain it, saying it was not a normal month"),
    ((("D", "My dad had heart surgery in March, back home in Leeds, and I live in Bristol."),), "Dana's tone has changed; she talks on more quietly.", "begins to explain that her dad had heart surgery in Leeds while she lives in Bristol"),
    ((("D", "I went up four weekends in a row: trains, a hotel near the hospital because my mum's place is tiny, eating at the hospital cafe."),), "Dana counts the weekends on her fingers as she goes on.", "is listing four weekends of trains, a hotel near the hospital and meals at the hospital cafe"),
    ((("D", "And I just wasn't looking at anything. I wasn't doing my Sunday spreadsheet, obviously."),), "Dana looks away from the camera as she talks.", "goes on that she stopped looking at her money and skipped the Sunday spreadsheet"),
    ((("D", "The thing I remember most is sitting in the hospital car park crying, because he looked so small in that bed."),), "Dana's voice is unsteady, but she keeps talking.", "is remembering, voice unsteady, crying in the hospital car park because her dad looked so small in the bed", (15, "telling the story of the month her dad had heart surgery")),
    ((("D", "He used to be the one who did all the money stuff in our family. He taught me to keep receipts in an envelope."),), "Dana wipes her eyes and keeps going.", "goes on that her dad used to handle the family money and taught her to keep receipts", (15, "telling the story of the month her dad had heart surgery")),
    ((("D", "And there I was, spending all that without a clue, while he was the one lying there."),), "Dana goes on with the story.", "continues: she was spending without a clue while he was the one in hospital", (15, "telling the story of the month her dad had heart surgery")),
    ((("D", "He's fine now, by the way. Back on his allotment, growing far too many courgettes."),), "Dana laughs a little, then carries on.", "adds that her dad is fine now and back on his allotment, and keeps going", (15, "telling the story of the month her dad had heart surgery")),
    ((("D", "But that month I went something like six hundred pounds over, mostly on the travel."),), "Dana is composed again, talking.", "carries on: she went about six hundred pounds over that month, mostly on travel"),
    ((("D", "And the cafe. So much cafe."),), "A small laugh; she keeps going.", "adds, laughing and talking on, that a lot of it went on the cafe"),
    ((("D", "It still makes me a bit shaky to talk about, sorry."), ("M", "Please don't apologise; take all the time you need.")), "Dana takes a breath and goes on talking, still in the middle of the story of the month she overspent.", "apologises for getting shaky, the moderator reassures her, and she takes a breath and carries on, still in the middle of the story of the month she went over budget"),
    ((("D", "It's fine. It's good to say it out loud, actually."),), "Dana nods to herself and keeps talking, still on the month she overspent.", "keeps talking, still on the month she went over budget, saying it is good to say it out loud"),
    # t26-t28: story over; how she found out is still open
    ((("D", "So... yeah."),), "Dana has stopped talking; she looks up from her tea at the moderator and waits.", "trails off with 'so... yeah', stops talking, looks up at the moderator and waits"),
    ((("D", "Anyway, that's the story of that month."),), "Done talking, she sits back and waits, looking at the moderator expectantly.", "says that is the story of that month, stops and sits back to wait"),
    ((("M", "Thank you for sharing that."),), "Dana, finished talking, sips her tea and waits.", "has stopped talking, sips her tea and waits after the moderator thanks her"),
    # t29-t32: probe answered
    ((("M", "When did you realise it had gone over? What tipped you off?"), ("D", "Honestly? The card.")), "Dana starts answering the moderator's question.", "is asked what tipped her off and starts answering: 'honestly, the card'"),
    ((("D", "My card got declined buying a sandwich at Leeds station, in front of a whole queue of people."),), "Dana winces as she tells it, and keeps going.", "is explaining she found out when her card was declined buying a sandwich at Leeds station"),
    ((("D", "I stood there doing sums in my head and realised I must have gone way over."),), "Dana keeps going, shaking her head.", "keeps going, describing standing there realising she had gone way over"),
    ((("D", "I paid with my credit card, then sat on the train and finally opened my banking app."),), "Dana carries on with the story.", "goes on that she paid by credit card and finally opened her banking app on the train"),
    # t33-t37: moderator jumps to T3 (T2 skipped)
    ((("D", "That's when I saw it all laid out. Not fun."), ("M", "That sounds really stressful. Let's talk about saving: are you saving for anything at the moment?")), "The moderator jumped ahead to guide topic 3; Dana is thinking about the question.", "says seeing it all laid out was not fun, the moderator jumps ahead to ask whether she is saving for anything, which is guide subject 3, and she thinks"),
    ((("D", "Saving... yes, in theory."),), "Dana starts to answer.", "starts answering: yes, in theory"),
    ((("D", "I'm trying to save for a deposit on a flat of my own."),), "Dana talks about her flat plans.", "is talking about saving for a deposit on a flat of her own"),
    ((("D", "The target is fifteen thousand, and I'm at about four and a half."),), "Dana gives the numbers, nodding, and goes on.", "goes on with the numbers: a target of fifteen thousand with about four and a half saved"),
    ((("D", "I've got a separate savings account for it, and I move money over on payday."),), "Dana explains her payday routine and keeps talking.", "goes on that she has a separate account and moves money over on payday"),
    # t38-t42: off-guide running club
    ((("D", "Oh, this is random, but I've also started running with a club on Saturday mornings. We do a loop along the river."),), "Dana grins as she talks.", "drifts, still talking, onto her Saturday running club and its loop along the river"),
    ((("D", "It starts at the suspension bridge, goes out to the old docks and back. Six miles, and there's a horrible hill at the end."),), "Dana traces the route in the air, still talking.", "keeps describing the six-mile route from the suspension bridge to the old docks and the hill at the end"),
    ((("D", "The club captain makes us do hill repeats on it. Last week I nearly cried."),), "Dana groans about the hill repeats and keeps talking.", "goes on, now complaining about the captain's hill repeats"),
    ((("D", "There's a heron that stands by the docks every Saturday. We've named him Gerald."),), "Dana grins and talks on, telling the heron story.", "is talking about a heron by the docks that the club has named Gerald"),
    ((("D", "Honestly, Gerald has more fans in the club than the captain does."),), "Dana is laughing, mid-story.", "is joking, mid-story, that the heron is more popular than the club captain"),
    # t43-t49: moderator steers back; saving
    ((("M", "Ha, I love Gerald. Coming back to the flat: how is the saving going, month to month?"), ("D", "Slower than I'd like.")), "Dana is back on saving, talking.", "is steered back to the flat by the moderator and starts: saving is slower than she would like"),
    ((("D", "Some months I put in four hundred, some months nothing."),), "Dana shrugs and goes on.", "carries on: some months she puts in four hundred and some months nothing"),
    ((("D", "I did the maths once, and at this rate it's about three more years."),), "Dana talks through her maths.", "goes on that at this rate it is about three more years"),
    ((("D", "Which feels like forever when all my friends are buying places."),), "Dana sighs, mid-thought.", "sighs, talking on, that it feels like forever while her friends are buying places"),
    ((("D", "I've looked at a couple of one-beds in Easton, just to see, and it made me want it more."),), "Dana keeps going about the viewings.", "has viewed a couple of one-bed flats and wants one even more, she continues"),
    ((("D", "The mortgage adviser said I need to show six months of steady saving, too."),), "Dana carries on about the mortgage adviser.", "is explaining that the mortgage adviser wants six months of steady saving"),
    ((("D", "So apparently consistency matters more than big one-off amounts."),), "Dana goes on, thinking aloud.", "reasons, still talking, that consistency matters more than big one-off amounts"),
    # t50-t52: T3 complete; T2 still open
    ((("D", "Honestly, the thing that eats into it is takeaways and birthday presents. There's always a birthday. Yeah, that's it, really."),), "Dana stops and waits for the next question.", "says what eats into her saving is takeaways and birthday presents, then stops and waits"),
    ((("M", "That's so relatable."),), "Dana laughs, then goes quiet and waits.", "laughs, then goes quiet and waits while the moderator looks at the guide"),
    ((("N", "Mic is picking up a little echo on her side; fine for the recording."),), "The moderator is reading the guide; Dana has stopped talking and is waiting.", "has stopped talking and waits while the note-taker mentions a little echo on her microphone"),
    # t53-t61: return to T2
    ((("M", "I skipped something earlier: do you share any costs with other people, like rent or bills?"), ("D", "Oh, yes, loads.")), "Dana starts answering.", "is asked the skipped question about sharing costs and starts: yes, loads"),
    ((("D", "I live with two housemates, Mia and Josh."),), "Dana holds up two fingers for her housemates and keeps going.", "is explaining she lives with two housemates, Mia and Josh"),
    ((("D", "Rent and bills go in a shared note on our phones. Whoever pays something writes it down, and we settle up at the end of the month."),), "Dana goes on to explain the shared note.", "goes on: rent and bills go in a shared phone note and they settle up monthly"),
    ((("D", "Josh pays the internet, I pay the energy, Mia pays the council tax, and then we even it out."),), "Dana counts the bills on her fingers, still talking.", "carries on: each housemate pays one bill and they even it out"),
    ((("D", "It mostly works, because Josh is basically a human spreadsheet."),), "Dana laughs and keeps going.", "keeps talking: it mostly works because Josh is a human spreadsheet"),
    ((("N", "We're behind on the guide, lots left!"), ("D", "Before the note we had a whiteboard on the fridge, which was very student house.")), "Dana talks on, unaware of the chat.", "is recalling the whiteboard on the fridge they used before, while the note-taker writes that they are behind on the guide"),
    ((("D", "The note's better because it's on everyone's phone anyway."),), "Dana keeps talking about the note.", "continues that the note is better because it is on everyone's phone"),
    ((("D", "Josh does a little summary on the last day of the month and posts it in our group chat."),), "Dana carries on, describing Josh's summaries.", "goes on that Josh posts a monthly summary in their group chat"),
    ((("D", "Josh even adds a little chart, which I secretly love."),), "Dana pauses for breath and goes on.", "adds that Josh even includes a little chart, which she secretly loves, and is still going"),
    # t62-t64: T2 complete
    ((("D", "The only real friction is Mia paying her share of the rent late. I end up covering it and then chasing her. Anyway."),), "Dana stops there and looks at the moderator.", "says the only real friction is Mia paying her rent share late, so Dana covers it and chases her, then stops"),
    ((("D", "Oh, and going back to saving for a second: the flat deposit is still the thing I'm most focused on. That's all."), ("M", "Got it, thank you.")), "Dana stops and waits while the moderator reads the guide.", "adds, going back to saving for a second, that the flat deposit is still her main focus, then stops and waits"),
    ((("D", "Sorry, I've been talking loads."), ("M", "No, this is exactly what we want.")), "Dana is done talking and is waiting for the next question.", "apologises for talking so much, is told it is exactly what they want, and waits, done talking"),
    # t65-t69: phone call
    ((("D", "Oh, sorry, that's my landlord calling. I have to take this, it's about the boiler. Two minutes?"), ("M", "Of course, go ahead.")), "Dana picks up her phone to take her landlord's call; the moderator pauses the session.", "has to take a call from her landlord about the boiler, and the moderator pauses the session"),
    ((("P", "Hi, yes... no, it's still making that noise."),), "Dana is on the phone with her landlord, turned slightly away from the camera; the session is paused.", "is on the phone telling her landlord the boiler is still making a noise"),
    ((("P", "Thursday morning works. Josh will be in, he can let them in."),), "Dana is on her call; the session stays paused.", "is on the call, arranging a Thursday visit"),
    ((("P", "Yes, the one by the bathroom. The pressure drops every night."),), "Dana is on the phone; the moderator waits with the session paused.", "is on the call, describing the pressure dropping every night"),
    ((("P", "Great, thank you so much. Bye."),), "Dana is ending her phone call; the session is still paused.", "is saying goodbye to her landlord, phone at her ear"),
    # t70-t72: back from the call, waiting
    ((("D", "Sorry about that! The boiler saga continues."),), "Dana is back, has stopped talking and is waiting for the next question.", "is back from the call, apologises, then stops talking and waits"),
    ((("M", "No problem at all."), ("D", "Where were we?")), "Dana stops talking and waits while the moderator looks at the guide.", "asks where they were, then stops and waits while the moderator looks at the guide"),
    ((("N", "Recording's still running fine."),), "Dana, finished talking, is waiting; the moderator scrolls the guide.", "has stopped talking and waits while the moderator scrolls the guide"),
    # t73-t79: T4
    ((("M", "Let's talk about alerts. Does your bank or any app send you notifications about money?"), ("D", "Oh, constantly.")), "Dana starts answering.", "is asked about money notifications and starts: she gets them constantly"),
    ((("D", "My bank pings me every single time I spend anything, and I've stopped even seeing them."),), "Dana rolls her eyes at the pings, still talking.", "is explaining that her bank pings her on every purchase and she no longer even sees them"),
    ((("D", "They also send marketing ones about loans, which go straight in the bin."),), "Dana mimes throwing something in a bin and keeps going.", "goes on that the loan marketing messages go straight in the bin"),
    ((("D", "The one I actually like is the low-balance text: when I drop under a hundred pounds, it warns me."),), "Dana brightens and goes on explaining.", "carries on: the alert she likes is the low-balance text when she drops under a hundred pounds"),
    ((("D", "That one has saved me from going overdrawn a few times."),), "Dana goes on about the overdraft.", "keeps going: the low-balance text has saved her from going overdrawn"),
    ((("D", "I'd love one that warned me before a direct debit that's going to push me under."),), "Dana thinks aloud about what she'd want.", "wishes aloud, mid-thought, for a warning before a direct debit pushes her under"),
    ((("D", "Like a heads-up two days before, not after the fact."),), "Dana keeps going, mid-thought.", "is explaining she wants that heads-up two days ahead"),
    # t80-t88: T5 raised at once
    ((("M", "That's a great example. Last area: what would make you try a new money app?"), ("D", "Hmm, good question.")), "The moderator moved straight on to guide topic 5; Dana is thinking.", "is asked, as the last area, what would make her try a new money app, and is thinking"),
    ((("D", "If a friend used it, and it didn't make me link all my accounts on day one."),), "Dana is still answering, counting off two conditions.", "is answering: she would try one a friend used if it did not make her link all her accounts on day one"),
    ((("D", "Being able to just try it before handing over my banking details, that's the big one for me."),), "Dana stresses the point, tapping the table, and keeps going.", "goes on, stressing being able to try it before handing over her banking details"),
    ((("D", "My friend Priya uses one where you just type in your spending, and she swears by it."),), "Dana talks about her friend Priya.", "carries on about her friend Priya's app, where you type in your spending"),
    ((("D", "Oh wait, going back to the savings thing for a second: Priya's app has savings pots, which I'd love for the flat."),), "Dana carries on, now about savings pots.", "keeps talking, going back to savings for a moment: Priya's app has savings pots she would love for the flat", (84, "describing the savings pots in her friend Priya's app")),
    ((("D", "You can name them. She's got one called 'Lisbon'."),), "Dana keeps talking about the pots.", "is explaining that the pots can be named, like Priya's 'Lisbon' pot", (84, "describing the savings pots in her friend Priya's app")),
    ((("D", "I think watching a pot fill up would actually motivate me."),), "Dana goes on, animated.", "goes on that watching a pot fill up would motivate her", (84, "describing the savings pots in her friend Priya's app")),
    ((("D", "I'd probably try something like that if it worked with my sheet somehow."),), "Dana keeps talking, thinking aloud.", "continues that she would try something like that if it worked with her spreadsheet"),
    ((("D", "Import from the spreadsheet, or at least export to it, so I'm not starting from zero."),), "Dana carries on talking, mid-thought.", "carries on, still talking, asking for import from or export to her spreadsheet"),
    # t89-t99: under 8 minutes; wrap-up
    ((("D", "And the other thing is my friend Dev, who switched apps because his old one..."),), "Dana is mid-sentence.", "starts telling how her friend Dev switched away from his old app, mid-sentence"),
    ((("D", "...kept pushing upgrades at him. He said it felt like being sold to by his own money."),), "Dana keeps talking.", "goes on that Dev's old app kept pushing upgrades at him"),
    ((("M", "I'm so sorry to jump in, I want to respect your time: we've got about six and a half minutes left."), ("D", "Oh gosh, of course!")), "Dana stops.", "stops when the moderator interrupts to say there are about six and a half minutes left"),
    ((("M", "Is there anything else you'd want the team building this app to know?"), ("D", "Hmm.")), "Dana is thinking.", "is asked if there is anything else the team should know, and thinks"),
    ((("D", "Just make it feel less like homework. The spreadsheet feels like homework."),), "Dana is still answering the moderator's question.", "is answering: she asks for it to feel less like homework than her spreadsheet"),
    ((("D", "Oh, and ads. If an app shows me ads, I delete it the same day."),), "Dana adds one more thing and keeps talking.", "goes on to add that she deletes any app that shows her ads the same day"),
    ((("M", "That's really useful. Your gift voucher will arrive by email within two days."), ("D", "Oh, lovely, thank you.")), "Dana has stopped answering and is smiling.", "has stopped answering and hears that her gift voucher will arrive by email within two days"),
    ((("D", "Can I ask, will I get to see what you end up building?"), ("M", "We'll send a short summary to everyone who took part.")), "Dana, done answering, asks what happens next, then waits for the moderator's reply.", "done answering, asks whether she will see the result, then waits and hears a summary will be sent"),
    ((("D", "Amazing. Good luck with it."), ("M", "Thank you so much, Dana, this was incredibly helpful.")), "Both are smiling; Dana has stopped answering.", "wishes the team luck, then stops and is thanked"),
    ((("D", "Thanks for listening to all my spreadsheet chat!"),), "Dana laughs, thanks the moderator and stops there.", "thanks the moderator for listening to her spreadsheet chat, then stops"),
    ((("M", "Bye, Dana!"),), "Dana stops and waves goodbye; the moderator reaches for the stop button.", "stops and waves goodbye as the moderator reaches for the stop button"),
]
B_THREADS_P = {
    "telling the story of the month her dad had heart surgery": "recounting the month her father had heart surgery",
    "describing the savings pots in her friend Priya's app": "describing the savings pots in her friend Priya's app",
}

# Irrelevant research-office details for the lexical-decoy register, keyed by
# the action whose vocabulary they borrow. None of them concerns Dana.
B_DECOYS = {
    "quiet": [
        "A sign on the door of the podcast booth next door reads: 'Please stay quiet, recording in progress.'",
        "The office chat asks everyone to stay quiet for now near the phone room.",
        "The facilities bot reminds staff to leave the participant parking bays free and give the delivery vans room.",
    ],
    "probe": [
        "The lab channel reports that the temperature probe in the server room needs a deeper look.",
        "A colleague in the observation room is reading an article titled 'Probing deeper into soil sensors'.",
        "The IT channel asks who can probe deeper into the flaky office Wi-Fi.",
    ],
    "return": [
        "Facilities posts: 'Please return the loaner headsets from the earlier batch to the shelf.'",
        "The shared calendar shows 'Return library books' for Friday, carried over from an earlier week.",
        "Someone asks the team channel to return the umbrellas borrowed earlier from reception.",
    ],
    "next": [
        "Research ops asks whether Friday's workshop can move on to a later room booking.",
        "The office quiz channel says it will move on to a later topic next week.",
        "A reminder pops up: 'Move the later printouts to the new shelf.'",
    ],
    "end": [
        "The office chat announces that the bake sale will end at four and asks people to bring back any wrapping paper.",
        "A colleague's out-of-office reply says her yoga session will end early today and she will wrap up emails tomorrow.",
        "The gym next door posts that its lunchtime spin session will end ten minutes early.",
    ],
}

# Minimal counterfactual surfaces.
B_CF_STILL_STORY = {
    26: ((("D", "So that month, honestly, I kept telling myself I'd sort it out the next Sunday."),), "Dana keeps talking, voice unsteady; the moderator is listening.", "keeps going, saying she kept telling herself she would sort it out the next Sunday"),
    27: ((("D", "And every Sunday came and went, and the spreadsheet just sat there."),), "Dana goes on, looking at her tea.", "goes on that every Sunday came and went while the spreadsheet sat there"),
    28: ((("D", "It was a lot, that month. A lot of everything."),), "Dana talks on, slowly; the moderator is listening.", "says, slowly and still talking, that it was a lot of everything that month"),
}
B_CF_NO_DISCOVERY = {
    29: ((("M", "How do you feel about that month now, money-wise?"), ("D", "Honestly? A bit guilty.")), "Dana starts answering the moderator's question.", "is asked how she feels about that month now, money-wise, and starts answering: a bit guilty"),
    30: ((("D", "Not about my dad, obviously. About being so careless with everything else."),), "Dana winces as she says it, and goes on.", "is explaining that the guilt is about being careless with everything else, not about her dad"),
    31: ((("D", "My sister says I shouldn't beat myself up about it, and she's probably right."),), "Dana keeps going, shaking her head.", "keeps going: her sister says she should not beat herself up about it"),
    32: ((("D", "I think I just needed a month off from being sensible."),), "Dana carries on, a little calmer.", "goes on that she needed a month off from being sensible"),
    33: ((("D", "So, mixed feelings. Not fun."), ("M", "That's really honest, thank you. Let's talk about saving: are you saving for anything at the moment?")), "The moderator jumped ahead to guide topic 3; Dana is thinking about the question.", "calls it mixed feelings, not fun, the moderator jumps ahead to ask whether she is saving for anything, which is guide subject 3, and she thinks"),
}
B_CF_NO_FRICTION = {
    62: ((("D", "Plus we split the streaming subscriptions the same way, one each. Anyway, that's how we split things."),), "Dana stops there and looks at the moderator.", "adds that they split the streaming subscriptions the same way, one each, says that is how they split things, and stops"),
}
B_CF_PAUSE = {
    86: ((("D", "I think watching a pot fill up would actually motivate me. That's probably my main thing."),), "Dana stops and waits for the next question.", "says watching a pot fill up would motivate her, that this is her main thing, and stops"),
    87: ((("M", "Mm, that's a lovely idea."),), "Dana has stopped talking and is waiting; the moderator glances at the clock.", "has stopped talking and waits while the moderator glances at the clock"),
    88: ((("N", "Recording fine, audio clear."),), "Dana, done talking, is waiting for the moderator.", "is done talking and waits while the note-taker confirms the audio is clear"),
}

B_SPEAKERS = {"D": "Dana", "M": "Moderator", "N": "Note-taker (chat)", "P": "Dana (on the phone)"}
B_LAGS = [1, 1, 2, 0, 1, 2]  # how many 30-second ticks the live notes trail the conversation


def hms(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def hms12(seconds: int) -> str:
    h = seconds // 3600
    return f"{h - 12 if h > 12 else h}:{seconds % 3600 // 60:02d}:{seconds % 60:02d} pm"


def _b_surface(entry: tuple[Any, ...]) -> dict[str, Any]:
    turns, stage, gist = entry[:3]
    thread = entry[3] if len(entry) > 3 else None
    return {"turns": [list(x) for x in turns], "stage": stage, "gist": gist, "thread": list(thread) if thread else None}


def _uncovered(z: dict[str, Any], topic: str) -> bool:
    return any(p not in z["covered"][topic] for p in "ab")


# Phase cues. Outside the pause, ``B_TALKING`` must appear in the stage line of
# every tick where Dana is still talking or thinking, and ``B_STOPPED`` in the
# stage line and gist of every tick where she has stopped, whether or not her
# phase decides the gold there. Waiting alone ("sips her tea and waits") does
# not count: a stopped tick says she stops, has stopped, goes quiet or is done
# talking. Gists (the paraphrase register) of talking ticks may also use a
# progressive verb ("is listing").
B_TALKING = re.compile(
    r"\b(talk\w*|keeps? \w+ing|go(es)? on\b|going (on|strong)|carr(y|ies|ying) (straight )?on|mid-\w+"
    r"|still (talking|answering|going|thinking)|think\w*|starts? (answering|to answer)|gathering her thoughts)",
    re.I,
)
B_TALKING_GIST = re.compile(B_TALKING.pattern + r"|\bis (?!waiting\b)\w+ing\b|\bcontinu\w*|\bstarts\b|\bbegins\b|in full flow", re.I)
B_WAITING = re.compile(r"\b(stop\w*|wait\w*)", re.I)
B_STOPPED = re.compile(r"\b(stop(s|ped)\b|goes quiet|(done|finished) (talking|answering))", re.I)


def _check_phase_cues(variant: str, ticks: list[Tick]) -> None:
    """Refuse a tick whose surface does not say in words whether Dana is still talking.

    Rule 3 tests her phase, so every tick states it, whether or not it decides
    the gold there. Paused ticks are exempt: they say she is on another call,
    and rule 1 comes first.
    """
    for t, tk in enumerate(ticks):
        z = tk.latent
        if z["hold"] is not None:
            continue
        stage, gist = tk.surface["stage"], tk.surface["gist"]
        if z["phase"] == "answering":
            ok = (bool(B_TALKING.search(stage)) and not B_WAITING.search(stage) and not B_STOPPED.search(stage)
                  and bool(B_TALKING_GIST.search(gist)))
        else:
            ok = bool(B_STOPPED.search(stage)) and bool(B_STOPPED.search(gist))
        if not ok:
            raise ValueError(f"interview_b/{variant} t={t}: phase '{z['phase']}' decides the gold but is not stated: {stage!r} / {gist!r}")


class DiscoveryInterview(Scenario):
    family = FAMILY
    scenario_id = "interview_b"
    title = "Moderator copilot for a budgeting-app discovery interview"
    tier = "medium"
    difficulty_features = [
        "two_questions_per_decision",
        "five_action_options",
        "six_way_topic_choice",
        "six_rule_priority_policy",
        "clock_subtraction",
        "duration_threshold_from_timestamps",
        "relatedness_judgement",
        "implicit_coverage_in_transcript",
        "lagging_notes",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "reroute", "terminate", "resolve-conflict"]
    deadline_steps = 2

    TICK_SECONDS = 30
    CLOCK_OFFSET = 480  # t88 sits exactly on the 8-minute line (14:52:00)

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            role = "You support a UX researcher (the moderator) during a one-to-one discovery session for a budgeting app, recommending their next move and which guide subject it is about. The state describes the booking, the clock and whether the session is on pause, the topic guide (a short warm-up, then five subjects in order with two key points each), the note-taker's record, the subject in play (the warm-up or the guide subject the moderator raised last, which stays in play through any tangent) and the last two half-minutes of the conversation, which say whether the interviewee is still speaking or has stopped."
            base = {"role": role, "rules": B_POLICY_P, "captured": B_COVERAGE_P}
            q1 = "Go through the rules in order and use the first that fits. What should the moderator do at this moment?"
            q2 = "Go through the rules in order and use the first that fits. Which guide subject is the moderator's move about at this moment?"
            actions = B_ACTIONS_P
            topics = {k: f"Subject {i}: {B_TOPICS_P[k][0]}" for i, k in enumerate(B_ORDER, start=1)}
            topics["none"] = "No subject from the guide"
        else:
            role = "You are a live copilot for a user researcher (the moderator) running a one-to-one discovery interview for a budgeting app. At every moment you recommend the moderator's next move and the guide topic it concerns. `session` gives the booking, the current clock time and whether the session is paused; `guide` lists a short warm-up and then five topics (T1-T5) in order, each with two must-cover points; `coverage_notes` are the note-taker's live notes; `current_topic` is the warm-up or the guide topic the moderator raised most recently, which stays current through any digression; `transcript` holds the latest turns, each stamped with the time it started; `right_now` is what can be seen on video, including whether the participant is still talking or has stopped."
            base = {"role": role, "policy": B_POLICY, "coverage": B_COVERAGE}
            q1 = "Apply the first rule that matches. What should the moderator do right now?"
            q2 = "Apply the first rule that matches. Which guide topic does the moderator's move concern right now?"
            actions = B_ACTIONS_D if variant == "lexical_decoy" else B_ACTIONS
            topics = {k: f"Topic {i}: {B_TOPICS[k][0]}" for i, k in enumerate(B_ORDER, start=1)}
            topics["none"] = "No guide topic"
        return [
            Choice("action", {**base, "question": q1}, dict(actions)),
            Choice("topic", {**base, "question": q2}, topics),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "topic": "warmup",
                "started": [],
                "covered": {k: [] for k in B_ORDER},
                "phase": "answering",
                "offtopic": None,
                "offtopic_s": 0,
                "hold": None,
                "screener": {},
                "elapsed_s": 0,
                "slot_s": B_SLOT,
            }
        )
        events: dict[int, tuple[dict[str, Any], str]] = {
            8: ({}, "'More than you wanted to know', but she carries straight on with the warm-up."),
            12: ({"topic": "overspend", "started": ["overspend"]}, "Warm-up over; T1 raised at once; she is thinking."),
            16: ({"cover": ("overspend", "a")}, "T1 point a: travel, hotel and cafe."),
            18: ({}, "The story of her dad's surgery has run for two minutes and sounds like a digression, but it is the overspend month itself (T1)."),
            26: ({"phase": "finished"}, "Story over; T1 point b (how she found out) is still open."),
            27: ({}, "'That's the story of that month', but point b is still open."),
            29: ({"phase": "answering"}, "Moderator probes; she answers."),
            30: ({"cover": ("overspend", "b")}, "Card declined: T1 complete."),
            33: ({"topic": "saving", "started": ["overspend", "saving"]}, "Moderator jumps to T3, skipping T2; she is thinking."),
            34: ({}, "T2 was skipped, but she is answering T3: staying quiet outranks returning."),
            35: ({"cover": ("saving", "a")}, "T3 point a: flat deposit."),
            38: ({"offtopic": "running club", "offtopic_s": 30}, "Off-guide talk since the start of this window (30 s)."),
            39: ({"offtopic_s": 60}, "Off-guide talk reaches exactly 60 s ('or more'): probe T3, which outranks returning to T2."),
            40: ({"offtopic_s": 90}, "Off-guide talk at 90 s."),
            41: ({"offtopic_s": 120}, ""),
            42: ({"offtopic_s": 150}, ""),
            43: ({"offtopic": None, "offtopic_s": 0}, "Moderator steers back to saving."),
            50: ({"cover": ("saving", "b"), "phase": "finished"}, "Obstacles named in her last turn: T3 complete; the skipped T2 comes before any later topic."),
            53: ({"topic": "shared", "started": ["overspend", "saving", "shared"], "phase": "answering"}, "Moderator returns to the skipped T2."),
            55: ({"cover": ("shared", "a")}, "T2 point a: shared phone note."),
            58: ({}, "Note-taker says they are behind, but 23:00 remain."),
            62: ({"cover": ("shared", "b"), "phase": "finished"}, "Friction named in her last turn: T2 complete; next open topic is T4."),
            63: ({}, "She goes back to saving for a moment, but T3 is complete: next is still T4."),
            65: ({"hold": "phone_call"}, "Phone call pauses the session."),
            70: ({"hold": None}, "Call over; she is waiting."),
            73: ({"topic": "alerts", "started": ["overspend", "saving", "shared", "alerts"], "phase": "answering"}, "T4 raised."),
            74: ({"cover": ("alerts", "b")}, "T4 point b."),
            76: ({"cover": ("alerts", "a")}, "T4 point a."),
            80: ({"topic": "switching", "started": ["overspend", "saving", "shared", "alerts", "switching"]}, "T5 raised at once; she is thinking."),
            81: ({"cover": ("switching", "a")}, "T5 point a."),
            84: ({}, "She goes back to savings pots, which belong to guide topics, so the off-guide exception can never apply."),
            85: ({}, "The savings-pot talk has run a full minute, but it is about guide topics (T3, T5): she is still talking."),
            88: ({}, "Exactly 8:00 left is not fewer than 8 minutes; she is still talking."),
            89: ({}, "7:30 left: ending outranks letting her finish."),
            91: ({"phase": "finished"}, "Moderator interrupts to wrap up."),
            92: ({"phase": "answering"}, "Closing question."),
            94: ({"cover": ("switching", "b")}, "T5 point b; every point now covered."),
            95: ({"phase": "finished"}, "Goodbyes."),
        }
        tags = span_tags(
            {
                "distractor": [8, (18, 21), 27, 58, 63, (85, 86)],
                "minimal_change": [39, 62, 89],
                "recovery": [43, 53, 70],
                "hold_under_activity": [(12, 14), (66, 69), (80, 82)],
                "priority_conflict": [(33, 35), (39, 42), (50, 52), (89, 91)],
                "boundary": [(89, 99)],
                "arithmetic": [(38, 42), (86, 91)],
            }
        )
        covered: dict[str, list[str]] = {k: [] for k in B_ORDER}
        for t in range(100):
            updates, note = events.get(t, ({}, ""))
            updates = dict(updates)
            point = updates.pop("cover", None)
            if point:
                topic, p = point
                covered[topic] = sorted(covered[topic] + [p])
            tl.step(_b_surface(B_SCRIPT[t]), tags[t], note, elapsed_s=self.TICK_SECONDS * t + self.CLOCK_OFFSET,
                    covered=copy.deepcopy(covered), **updates)
        return tl.ticks

    def _tag_implicit(self, ticks: list[Tick]) -> list[Tick]:
        """Tag the ticks whose gold depends on coverage that only the transcript shows."""
        out = [copy.deepcopy(tk) for tk in ticks]
        for t, tk in enumerate(out):
            lag = self._lag(ticks[: t + 1])
            seen = copy.deepcopy(tk.latent)
            seen["covered"] = copy.deepcopy(ticks[t - lag].latent["covered"])
            tk.tags = [x for x in tk.tags if x != "implicit"]
            if self.policy(seen) != self.policy(tk.latent):
                tk.tags.append("implicit")
        return out

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t26-28: she keeps telling the story instead of stopping (probe T1 -> quiet).
            ticks = override(ticks, [26, 27, 28], phase="answering", tags=["minimal_change"],
                             note="Still telling the story; nothing to probe yet.",
                             surface=lambda tk, i: _b_surface(B_CF_STILL_STORY[i]))
            # (2) t29-33: the moderator's T1 probe asks how she feels about the month, not how she
            # found out, so T1 point b stays open. At t50-52 two earlier topics are open and rule 5
            # picks the earliest (return T2 -> return T1).
            ticks = override(ticks, [29, 30, 31, 32, 33], surface=lambda tk, i: _b_surface(B_CF_NO_DISCOVERY[i]))
            # (3) t62: her last line names no friction, so T2 point b stays open (next T4 -> probe T2).
            ticks = override(ticks, [62], note="No friction named: T2 point b still open; probing the current T2 outranks returning to T1.",
                             surface=lambda tk, i: _b_surface(B_CF_NO_FRICTION[i]))
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for i, tk in enumerate(ticks):
                if i >= 30:
                    tk.latent["covered"]["overspend"] = ["a"]
                if i >= 62:
                    tk.latent["covered"]["shared"] = ["a"]
            # (4) t86-88: she stops with 9:00-8:00 left, so the clock rule has not fired (quiet -> probe T5).
            ticks = override(ticks, [86, 87, 88], phase="finished",
                             note="She stops with 8 or more minutes left (exactly 8:00 at t88 is not fewer than 8); T5 point b open, and probing it outranks returning to T1.",
                             surface=lambda tk, i: _b_surface(B_CF_PAUSE[i]))
            ticks = _set_tags(
                ticks,
                {
                    50: ["minimal_change", "priority_conflict"],
                    62: ["minimal_change", "priority_conflict"],
                    63: ["distractor", "priority_conflict"],
                    64: ["priority_conflict"],
                    70: ["recovery", "priority_conflict"],
                    71: ["priority_conflict"],
                    72: ["priority_conflict"],
                    86: ["minimal_change", "priority_conflict", "arithmetic"],
                    87: ["minimal_change", "priority_conflict", "arithmetic"],
                    88: ["minimal_change", "priority_conflict", "arithmetic"],
                },
                {
                    29: "The moderator's T1 probe asks how she feels about the month, not how she found out; she answers.",
                    30: "T1 point b (how she found out) stays open; she is still answering.",
                    33: "Moderator jumps to T3, skipping T2, with T1 point b still open; she is thinking.",
                    39: "Off-guide talk reaches exactly 60 s ('or more'): probe T3, which outranks returning to T1.",
                    50: "T3 complete; T1 point b and all of T2 are open earlier in the guide: return to the earliest, T1.",
                    53: "Moderator returns to T2 rather than T1; she answers.",
                    63: "She goes back to saving for a moment (T3 complete); T2 point b is still open: probe T2, which outranks returning to T1.",
                    70: "Call over; T2 point b still open: probe T2, which outranks returning to T1.",
                    94: "T5 point b covered; T1 and T2 point b never were, but the clock rule already applies.",
                },
            )
        elif variant == "structural_cf":
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["screener"] = copy.deepcopy(B_STRUCTURAL_SCREENER)
                for topic, points in B_STRUCTURAL_SCREENER.items():
                    tk.latent["covered"][topic] = sorted(set(tk.latent["covered"][topic]) | set(points))
            ticks = _set_tags(
                ticks,
                {
                    81: ["minimal_change", "priority_conflict"],
                    82: ["priority_conflict"],
                    83: ["priority_conflict"],
                    85: [],
                    86: [],
                    87: [],
                    88: [],
                    89: ["priority_conflict", "boundary"],
                },
                {
                    62: "T2 complete; T3 complete, and the screener covered T4 fully and T5 point b: the next open topic is T5.",
                    63: "She goes back to saving for a moment, but T3 is complete: next is still T5.",
                    70: "Call over; the next open topic is T5.",
                    73: "Moderator raises T4 anyway, though the screener covered it; she answers.",
                    80: "T5 raised; point a is the only point still open.",
                    81: "T5 point a named in her last turn; with the screener's points every must-cover point is covered, so ending outranks letting her talk.",
                    84: "Every point covered: end.",
                    85: "Every point covered: end.",
                    88: "Every point covered: end.",
                    89: "Every point covered and 7:30 left: end.",
                    94: "T5 point b named again (the screener already covered it).",
                },
            )
        _check_phase_cues(variant, ticks)
        return self._tag_implicit(ticks)

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        remaining = z["slot_s"] - z["elapsed_s"]
        current = z["topic"]
        if z["hold"] is not None:
            action, topic = "quiet", "none"
        elif remaining < 480 or not any(_uncovered(z, k) for k in B_ORDER):
            action, topic = "end", "none"
        elif z["phase"] == "answering" and not (z["offtopic"] is not None and z["offtopic_s"] >= 60):
            action, topic = "quiet", "none"
        elif current in B_ORDER and _uncovered(z, current):
            action, topic = "probe", current
        else:
            i = B_ORDER.index(current) if current in B_ORDER else -1  # the warm-up comes before T1
            earlier = [k for k in B_ORDER[:i] if _uncovered(z, k)] if i > 0 else []
            if earlier:
                action, topic = "return", earlier[0]
            else:
                action, topic = "next", [k for k in B_ORDER[i + 1:] if _uncovered(z, k)][0]
        return {"action": action, "topic": topic}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Discovery interview: a warm-up, then five guide topics. The session line says whether the session is paused, and the video line says in words whether Dana is still talking or has stopped; long stretches on one subject are timed from their start. An emotional two-minute story that sounds like a digression but is the topic itself, a probe for a missing point, a skipped topic, an off-guide story that reaches exactly 60 s, a return to the skipped topic, points covered only in the latest turns while the live notes lag by 0-2 ticks, a remark about a finished topic, a phone-call pause, a minute-long aside about another guide topic, and a clock that reaches exactly 8:00 left and then crosses the line while she is mid-sentence."},
            "paraphrase": {"summary": "Same latent trajectory; subject/key-point/captured vocabulary, a narrated 12-hour-clock summary of the last two moments instead of JSON with a transcript array, reworded rules, options and topic names."},
            "lexical_decoy": {"summary": "Same latent trajectory; each state adds one or two irrelevant research-office details borrowing an action's vocabulary (mostly a wrong action's, a third of the time any action's), either inside the video line or in their own field."},
            "minimal_cf": {"summary": "Four minimal edits: t26-28 she keeps telling the story (probe T1 -> quiet); t29-33 the moderator's T1 probe asks how she feels about the month instead of how she found out, so T1 point b stays open for the rest of the session and at t50-52 two earlier topics are open (return T2 -> return T1, the earliest); t62 her last line names no friction, so T2 stays open (next T4 -> probe T2, also t70-72 after the call; probing the current topic outranks returning to T1); t86-88 she stops with 9:00-8:00 left (quiet -> probe T5; exactly 8:00 at t88 is not fewer than 8)."},
            "structural_cf": {"summary": "The screener survey already answered T4 (alerts) in full and T5 point b (she deletes apps with ads). After T2 is complete the next open topic is T5, not T4 (t62-64 and t70-72: next T4 -> next T5), and once she names T5 point a at t81 every must-cover point is covered, so the session should end while she is still talking (t81-88: quiet -> end)."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    @staticmethod
    def _turns(history: list[Tick], limit: int = 3) -> list[tuple[int, str, str, str]]:
        """The latest turns as (tick, start time, speaker, text); turns start 10 s apart in a 30 s window."""
        out = []
        for i in range(max(0, len(history) - limit), len(history)):
            tk = history[i]
            clock = B_START + tk.latent["elapsed_s"]
            for j, (spk, text) in enumerate(tk.surface["turns"]):
                out.append((i, hms(clock - 30 + 10 * j), spk, text))
        return out[-limit:]

    def _lag(self, history: list[Tick]) -> int:
        """How many ticks the live notes trail; never hides a turn the transcript does not show."""
        t = len(history) - 1
        lag = min(B_LAGS[t % len(B_LAGS)] if t not in (50, 62, 81) else 1, t)
        shown = self._turns(history)
        first_shown = min((i for i, *_ in shown), default=t + 1)
        full = {i for i in range(t + 1) if i > first_shown or not history[i].surface["turns"]}
        if shown:
            counts: dict[int, int] = {}
            for i, *_ in shown:
                counts[i] = counts.get(i, 0) + 1
            for i, n in counts.items():
                if n == len(history[i].surface["turns"]):
                    full.add(i)
        while lag > 0 and not all(i in full for i in range(t - lag + 1, t + 1)):
            lag -= 1
        return lag

    def _thread(self, history: list[Tick]) -> tuple[int, str, str] | None:
        """(start time, subject, paraphrase subject) of a long stretch on one subject, if any."""
        tk = history[-1]
        z = tk.latent
        clock = B_START + z["elapsed_s"]
        if z["hold"] is None and z["phase"] == "answering" and z["offtopic"] is not None:
            return clock - z["offtopic_s"], B_OFFTOPIC[z["offtopic"]], B_OFFTOPIC_P[z["offtopic"]]
        if tk.surface.get("thread"):
            start_t, subject = tk.surface["thread"]
            return B_START + history[start_t].latent["elapsed_s"] - 30, subject, B_THREADS_P[subject]
        return None

    def _since(self, history: list[Tick], t: int) -> str:
        thread = self._thread(history)
        if thread is None:
            return ""
        start, subject, _ = thread
        seconds = B_START + history[-1].latent["elapsed_s"] - start
        if seconds == 60:
            return f"Dana has been {subject} for a full minute now, since {hms(start)}. "
        return pick(["Since {s}, Dana has been {x}. ", "Dana has been {x} since {s}. "], "b-since", t).format(s=hms(start), x=subject)

    def _notes(self, zn: dict[str, Any], z: dict[str, Any]) -> str:
        parts = []
        for i, k in enumerate(B_ORDER, start=1):
            cov = zn["covered"][k]
            pre = z["screener"].get(k, [])
            if not cov and k not in zn["started"]:
                parts.append(f"T{i} not started")
                continue
            if cov == ["a", "b"]:
                parts.append(f"T{i} a, b covered" + (" (screener)" if pre == ["a", "b"] else ""))
                continue
            names = {p: (B_SCREENER[k][p] if p in pre else B_NOTES[k][p]) for p in "ab"}
            pts = [f"{p} covered ({names[p]})" if p in cov else f"{p} not yet" for p in "ab"]
            parts.append(f"T{i} " + ", ".join(pts))
        return "; ".join(parts) + "."

    def _guide(self, z: dict[str, Any]) -> str:
        items = [f"Warm-up (no must-cover points): {B_WARMUP}."]
        for i, k in enumerate(B_ORDER, start=1):
            name, pa, pb = B_TOPICS[k]
            item = f"T{i} {name}: (a) {pa}; (b) {pb}"
            pre = z["screener"].get(k, [])
            if pre == ["a", "b"]:
                item += " [both points pre-answered in the screener survey]"
            elif pre:
                item += f" [point {pre[0]} pre-answered in the screener survey]"
            items.append(item)
        return items[0] + " Then " + " | ".join(items[1:]) + "."

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        lag = self._lag(history)
        zn = history[t - lag].latent
        wall = hms(B_START + z["elapsed_s"])
        session = pick(
            [
                "Discovery interview for a budgeting app with Dana (participant P7). Booked 14:00-15:00 (60 minutes); clock: {w}.",
                "Budgeting-app discovery session, participant P7 (Dana). Slot 14:00 to 15:00; it is now {w}.",
                "One-to-one discovery interview with Dana (P7) for a budgeting app, booked 60 minutes from 14:00. Current time {w}.",
            ],
            "b-session",
            t,
        ).format(w=wall)
        session += " " + pick(
            ["Paused: Dana is on a phone call.", "On pause while Dana takes a call."]
            if z["hold"] is not None
            else ["Not paused.", "Running, not paused.", "Live, no pause."],
            "b-status",
            t,
        )
        current = f"T{B_ORDER.index(z['topic']) + 1} {B_TOPICS[z['topic']][0]}" if z["topic"] in B_ORDER else f"Warm-up: {B_WARMUP}"
        state: dict[str, Any] = {
            "session": session,
            "guide": self._guide(z),
            "coverage_notes": f"(typed live, last updated {hms(B_START + zn['elapsed_s'])}) " + self._notes(zn, z),
            "current_topic": current,
            "transcript": [f"[{stamp}] {B_SPEAKERS[spk]}: {text}" for _, stamp, spk, text in self._turns(history)],
            "right_now": self._since(history, t) + tick.surface["stage"],
        }
        if variant == "lexical_decoy":
            lines = _decoy_lines(B_DECOYS, self.policy(z)["action"], t, "b")
            if pick([True, False], "b-decoy-place", t):
                state["right_now"] += f" Meanwhile in the research office: {lines[0][0].lower()}{lines[0][1:]}"
                lines = lines[1:]
            if lines:
                state["background"] = " ".join(lines)
        return state

    def _record_p(self, zn: dict[str, Any], z: dict[str, Any]) -> str:
        out = []
        for i, k in enumerate(B_ORDER, start=1):
            cov = zn["covered"][k]
            pre = z["screener"].get(k, [])
            notes = {p: (B_SCREENER_P[k][p] if p in pre else B_NOTES_P[k][p]) for p in "ab"}
            if not cov and k not in zn["started"]:
                out.append(f"subject {i} not reached")
            elif cov == ["a", "b"]:
                out.append(f"subject {i} both captured" + (" (from the screener)" if pre == ["a", "b"] else ""))
            elif cov == ["a"]:
                out.append(f"subject {i} first captured ({notes['a']}), second open")
            elif cov == ["b"]:
                out.append(f"subject {i} second captured ({notes['b']}), first open")
            else:
                out.append(f"subject {i} opened, neither key point captured")
        return "; ".join(out)

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        lag = self._lag(history)
        zn = history[t - lag].latent
        parts = [
            f"One-to-one discovery session for a budgeting app with participant P7, Dana. It is booked for the hour from 2 pm to 3 pm, and the clock says {hms12(B_START + z['elapsed_s'])}.",
            pick(
                ["The session is on pause while she takes a phone call.", "Everything is on pause: she is on a phone call."]
                if z["hold"] is not None
                else ["Nothing is on pause.", "The session is live, not paused."],
                "p-status",
                t,
            ),
        ]
        guide = []
        for i, k in enumerate(B_ORDER, start=1):
            name, pa, pb = B_TOPICS_P[k]
            item = f"({i}) {name}: {pa}; {pb}"
            pre = z["screener"].get(k, [])
            if pre == ["a", "b"]:
                item += " (both already answered on the screener survey, so they count as captured)"
            elif pre:
                item += " (the second already answered on the screener survey, so it counts as captured)"
            guide.append(item)
        parts.append(f"Topic guide: a warm-up on {B_WARMUP_P} with no key points, then " + " | ".join(guide) + ".")
        parts.append(f"The note-taker's record, typed live and last updated at {hms12(B_START + zn['elapsed_s'])}: {self._record_p(zn, z)}.")
        if z["topic"] in B_ORDER:
            parts.append(f"The subject in play is number {B_ORDER.index(z['topic']) + 1}, {B_TOPICS_P[z['topic']][0].lower()}.")
        else:
            parts.append(f"The warm-up about {B_WARMUP_P} is still in play.")
        if len(history) > 1:
            parts.append(f"Half a minute earlier: Dana {history[-2].surface['gist']}. This moment: Dana {tick.surface['gist']}.")
        else:
            parts.append(f"This moment: Dana {tick.surface['gist']}.")
        thread = self._thread(history)
        if thread is not None:
            start, _, subject_p = thread
            seconds = B_START + z["elapsed_s"] - start
            if seconds == 60:
                parts.append(f"She has been {subject_p} for exactly one minute, since {hms12(start)}.")
            else:
                parts.append(f"She has been {subject_p} since {hms12(start)}.")
        return " ".join(parts)


SCENARIOS = [BackendInterview, DiscoveryInterview]
