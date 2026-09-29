"""Incident Response: an on-call assistant deciding the next move in a production incident.

Each tick is one minute of an incident channel. The assistant reads alerts,
metrics against their thresholds, traces, the deploy log, work in progress and
chat, and recommends the next move. Both scenarios share the family's latent
vocabulary (objectives breached or met, a suspect service or component, a
change under way, who holds command) but differ in difficulty:

* ``incident_a`` (medium) - a checkout-latency incident on an online store
  during a launch change freeze; two questions (action with six options, target
  service with five) and a seven-rule priority policy with instant threshold
  comparisons. The saturated service and the service the traces blame differ
  for a while, so the target question cannot be answered by copying the trace.
* ``incident_b`` (hard) - a payment-database failover across teams; three
  questions (categorised action with eight options, target component with six,
  and a SEV3/SEV2/SEV1 severity score), an eight-rule policy with several
  priority conflicts, partly implicit facts (stale lag readings, no writable
  node, a shift end read off the clock) and an incident-commander handoff that
  waits for the incoming commander to join.
"""

from __future__ import annotations

import copy
import json
from typing import Any, ClassVar

from streamdecisionbench.authoring import (
    Choice,
    Scenario,
    Score,
    Tick,
    Timeline,
    override,
    pick,
    span_tags,
)

FAMILY = "incident_response"


def clock(base: int, minute: int) -> str:
    """Wall-clock HH:MM for ``minute`` minutes after ``base`` (minutes after midnight)."""
    total = (base + minute) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def retag_recovery(scenario: Scenario, ticks: list[Tick]) -> list[Tick]:
    """Keep a ``recovery`` tag only where this variant's gold returns to an earlier move.

    A move is the action and its target; a severity level that changed on the
    way does not make the return a new decision.
    """
    golds = [json.dumps({k: v for k, v in scenario.policy(tk.latent).items() if k in ("action", "target")}, sort_keys=True) for tk in ticks]
    for t, tk in enumerate(ticks):
        if "recovery" in tk.tags and (t == 0 or golds[t] == golds[t - 1] or golds[t] not in golds[:t]):
            tk.tags = [tag for tag in tk.tags if tag != "recovery"]
    return ticks


def surface_of(line: tuple[str, str, str]) -> dict[str, str]:
    return dict(zip(("log", "chat", "gist"), line))


# ===========================================================================
# Scenario A - checkout latency on an online store (medium)
# ===========================================================================

A_BASE = 20 * 60  # t=0 is 20:00; one tick is one minute
A_SERVICES = ["checkout-api", "pricing-svc", "cart-cache", "orders-db"]

A_ROLE = (
    "You assist the on-call engineer during a production incident on an online store's checkout. "
    "Each state is a one-minute snapshot of the incident channel: production checkout metrics against "
    "their objectives, traces, CPU per service, the deploy log, any change under way, findings people have "
    "posted, who holds incident command, whether a change freeze is in effect and any rollback approval on "
    "file, and the latest alert and chat lines. Checkout objectives: p95 latency at most 500 ms and error "
    "rate at most 1.0%; an objective is "
    "breached when its current value is above that limit. Only production counts: anything marked staging "
    "is out of scope. Apply the rules exactly as written: when a rule names a service, that service is the "
    "target, even if the traces blame a different one."
)
A_POLICY = [
    "1. If the checkout error rate is 5.0% or higher and no incident commander is engaged: escalate to the incident commander; target: none.",
    "2. Otherwise, if a rollback or scale-out has been started and has not finished: keep watching; target: none.",
    "3. Otherwise, if an incident is open and both objectives have been met continuously for 10 minutes or longer: declare the incident resolved; target: none.",
    "4. Otherwise, if an objective is breached and posted findings tie the problem to a service's latest deploy that the service is still running: roll back that deploy; target: that service. Exception: if a change freeze is in effect and no approval of that rollback by the incident commander is on file (an approval the incident commander gave in advance counts, even if no commander is engaged right now), escalate to the incident commander instead; target: none.",
    "5. Otherwise, if an objective is breached and a service's CPU is at 85% or higher: scale out that service; target: that service.",
    "6. Otherwise, if an objective is breached and traces place the extra latency in a service for which no findings have been posted yet: inspect that service's logs and traces; target: that service.",
    "7. Otherwise: keep watching; target: none.",
]
A_ROLE_P = (
    "You back up the engineer holding the pager while a live incident hits a web shop's checkout. Every "
    "snapshot covers one minute in the incident room: how production checkout is doing next to its targets, "
    "request tracing, processor load per service, recent releases, any fix that is running, what people have "
    "reported finding, who is in charge, whether changes are frozen and any sign-off on record for a revert, "
    "plus the newest alert and messages. Checkout targets: the 95th-percentile time must not exceed 500 ms "
    "and failed requests must not exceed "
    "1.0%; a target is missed when the current figure is over its limit. Only the live production shop "
    "matters; test (staging) systems are to be ignored. Follow the rules to the letter: whenever a rule singles "
    "out a service, that service is the one aimed at, even if request tracing points somewhere else."
)
A_POLICY_P = [
    "1. When at least 5.0% of checkout requests are failing and nobody holds incident command, page the incident commander; no service is aimed at.",
    "2. If not, and a revert or capacity increase was kicked off and is still running, hold and monitor; no service is aimed at.",
    "3. If not, and there is an open incident whose two checkout targets have both been within limits without interruption for 10 minutes or more, mark the incident as fixed; no service is aimed at.",
    "4. If not, and a checkout target is missed while posted findings blame a service's newest release that is still live on that service, revert that release; that service is the one aimed at. Exception: during a change freeze, if no sign-off on that revert from the incident commander is on record (a sign-off the incident commander gave ahead of time counts, even when nobody holds command at the moment), page the incident commander instead; no service is aimed at.",
    "5. If not, and a checkout target is missed while some service's processor load sits at 85% or above, add capacity to that service; that service is the one aimed at.",
    "6. If not, and a checkout target is missed while tracing puts the added time in a service nobody has posted findings about yet, dig into that service's logs and request traces; that service is the one aimed at.",
    "7. In any other case, hold and monitor; no service is aimed at.",
]

A_OPTIONS = {
    "observe": "Keep watching the checkout dashboards without taking a new action.",
    "inspect": "Inspect the logs and traces of the target service.",
    "rollback": "Roll back the most recent deploy of the target service.",
    "scale_out": "Scale out the target service by adding more instances.",
    "escalate": "Escalate to the incident commander by paging them now.",
    "resolve": "Declare the incident resolved and close it out.",
}
A_OPTIONS_P = {
    "observe": "Hold off and continue monitoring; change nothing yet.",
    "inspect": "Dig into the chosen service's logs and request traces.",
    "rollback": "Revert the chosen service to its previous release.",
    "scale_out": "Give the chosen service extra capacity with more copies.",
    "escalate": "Call in the incident commander to take charge.",
    "resolve": "Mark the incident as fixed and wrap it up.",
}
A_TARGETS = {
    "checkout-api": "checkout-api (order submission API)",
    "pricing-svc": "pricing-svc (price and discount engine)",
    "cart-cache": "cart-cache (Redis store for carts)",
    "orders-db": "orders-db (orders database)",
    "none": "No service; the chosen action has no target",
}
A_TARGETS_P = {
    "checkout-api": "checkout-api, where orders are submitted",
    "pricing-svc": "pricing-svc, which works out prices and discounts",
    "cart-cache": "cart-cache, the in-memory cart store",
    "orders-db": "orders-db, the database holding orders",
    "none": "Nothing; this move is not aimed at a service",
}

# Surface content per tick: (log line or "", chat line, third-person gist for the
# paraphrase register). Decision-relevant facts are rendered from the latent
# state; these lines only add the moment's texture and never contradict it.
A_SCRIPT: list[tuple[str, str, str]] = [
    # t0-7 20:00-20:07: evening peak, no incident yet
    ("", "Lina: evening peak is starting, traffic is about 30% above last Tuesday.", "Lina remarks that the evening rush has begun, roughly a third busier than last Tuesday"),
    ("", "Sam: read the day shift's handover, nothing was left open.", "Sam says the day shift handed over with nothing outstanding"),
    ("", "Tom: pricing v4.12 shipped at 19:51 with the new bundle discounts, fingers crossed.", "Tom recalls that the bundle-discount release of the pricing service went live at 19:51"),
    ("[staging] ALERT checkout-api p95 2.4 s on staging-eu (QA load-test cluster)", "Tom: checkout-api at 2.4 seconds?! Somebody look at checkout-api.", "a test-cluster alert about checkout-api on QA's load-test setup has fired, and Tom urges someone to look at checkout-api"),
    ("[staging] ALERT checkout-api p95 2.6 s on staging-eu (QA load-test cluster), still firing", "Tom: it's getting worse, 2.6 s on checkout-api now.", "the checkout-api alert from the staging-eu test cluster keeps going off and Tom says it is getting worse"),
    ("", "Lina: staging-eu is running QA's soak test all evening.", "Lina explains that QA is soaking the test cluster all evening"),
    ("", "Sam: prod p95 is climbing with the traffic, I'm keeping an eye on it.", "Sam notes that live checkout times are rising along with traffic"),
    ("", "Lina: 492 on the last minute, close to the line.", "Lina reads out the newest latency figure and says it is near the line"),
    # t8-14: breach, traces point at pricing-svc, nobody has looked yet
    ("[prod] ALERT checkout p95 above 500 ms for 1 minute; INC-2291 opened automatically", "Sam: prod alert, I'm on it.", "a live latency alert has fired and opened an incident by itself; Sam acknowledges it"),
    ("", "Lina: the trace view has quote calls to pricing-svc over 300 ms; I haven't opened pricing's logs yet.", "Lina sees in the tracing that quote calls to the pricing service take over 300 ms, though she has not opened its logs yet"),
    ("", "Sam: carts load fine but the order button hangs for about a second.", "Sam reports that carts load but placing an order hangs for about a second"),
    ("", "Tom: my money's on orders-db, same as the October outage.", "Tom is betting the orders database is to blame, as it was in October"),
    ("", "Jess (support): two customers on chat say checkout is spinning.", "support relays two customers complaining that checkout keeps spinning"),
    ("", "Ravi (pricing owner): I'm on a train, can someone pull our logs?", "the pricing team's owner, travelling by train, asks someone to pull the pricing logs"),
    ("", "Jess: five chats about slow checkout now.", "support now has five chats about slow checkout"),
    # t15-18: findings tie the problem to pricing v4.12; the launch freeze needs the commander's approval
    ("pricing-svc ERROR RuleEngineTimeout quote_id=88121 after 400 ms", "Sam: pricing-svc logs are full of RuleEngineTimeout since 19:52, a minute after v4.12 went out.", "Sam has read the pricing logs and posts that rule-engine timeouts began at 19:52, a minute after release 4.12"),
    ("", "Ravi: v4.11 never called the rule engine on the quote path, so that fits.", "Ravi confirms the previous pricing build never called the rule engine when quoting"),
    ("", "Tom: can't we just add pods to pricing and ride it out?", "Tom suggests simply giving pricing more pods and riding it out"),
    ("", "Jess: support queue is at 11 chats, mostly about slow checkout.", "support's queue has grown to eleven chats, mostly about slow checkout"),
    # t19-21: the commander joins and approves; the rollback has not started
    ("incident: Priya Raman joined INC-2291 as incident commander", "Priya (incident commander): I have command, and I approve rolling pricing-svc back to v4.11 under the launch freeze.", "Priya has taken charge as incident commander and approved reverting pricing to build 4.11 despite the launch freeze"),
    ("", "Sam: pulling v4.11 from the registry and attaching Priya's approval to the deploy.", "Sam is fetching the previous pricing build and attaching Priya's approval to the deploy"),
    ("", "Ravi: v4.11 is still in the registry and nothing else changed in pricing today.", "Ravi says the previous pricing build is still in the registry and nothing else changed today"),
    # t22-29: rollback under way
    ("deploy: pricing-svc rollback v4.12 -> v4.11 started by sam (freeze approval: priya)", "Sam: taking pricing-svc back to v4.11 now.", "Sam has started returning the pricing service to its previous build"),
    ("deploy: pricing-svc pod 1/6 on v4.11, ready", "Lina: first v4.11 pod is serving and its quotes look normal.", "Lina says the first pod on the old build serves normal quotes"),
    ("deploy: pricing-svc pod 2/6 on v4.11, ready", "Tom: pricing-svc CPU is 86% on the pods still serving. Add pods?", "Tom sees the pricing pods that are still serving at 86% load and suggests adding pods"),
    ("deploy: pricing-svc pod 3/6 on v4.11, draining an old pod", "Lina: errors climbing while old pods drain, 4.6% now.", "Lina reports errors climbing to 4.6% while old pods drain"),
    ("deploy: pricing-svc pod 4/6 on v4.11, ready", "Tom: pricing CPU still 87%, we really should scale it.", "Tom insists that pricing, still at 87% load, should be scaled"),
    ("deploy: pricing-svc pod 5/6 starting", "Sam: 4.9% on the last minute; the drain should finish soon.", "Sam gives 4.9% for the last minute and expects the drain to finish soon"),
    ("deploy: pricing-svc pod 5/6 on v4.11, ready", "Lina: errors easing as the new pods take traffic.", "Lina sees errors easing as the new pods take traffic"),
    ("deploy: pricing-svc pod 6/6 health check pending", "Sam: last pod is warming up.", "Sam says the last pod is warming up"),
    # t30-34: rollback done, latency still high; customers whose checkout hung reload their
    # order pages and the read surge loads orders-db; traces blame cart-cache
    ("deploy: pricing-svc rollback to v4.11 complete (6/6)", "Sam: done, pricing-svc is fully on v4.11. Lina: orders-db just jumped, customers whose checkout hung are reloading their order pages.", "Sam announces the pricing service is fully back on the previous build, and Lina sees the orders database jump as customers whose checkout hung reload their order pages"),
    ("orders-db WARN read query rate far above baseline, mostly order-status lookups", "Lina: pricing spans are back to 60 ms but p95 is still 680.", "the orders database logs a read rate far above normal, mostly order-status lookups, and Lina says pricing is quick again yet checkout as a whole is still slow"),
    ("", "Tom: orders-db is running hot, told you it was the database!", "Tom points at the busy orders database and claims he was right all along"),
    ("", "Lina: the trace view also has cart reads from cart-cache at 155 ms; I haven't opened cart-cache's logs yet.", "Lina adds that cart reads from the cache take about 155 ms in the tracing, though she has not opened the cache's logs yet"),
    ("", "Jess: complaints slowed a little but are still coming in.", "support says complaints have slowed a bit but keep arriving"),
    # t35-40: the read surge is over; cart-cache CPU at or above 85%
    ("orders-db INFO read query rate back near baseline", "Lina: cart-cache is the busiest thing on the board now.", "reads on the orders database are back near their usual rate, and Lina says the cart cache is now the busiest thing on the board"),
    ("", "Tom: cart page loads are slow again on my test account.", "Tom's test account shows slow cart pages again"),
    ("", "Ravi: pricing is healthy from our side now.", "Ravi reports the pricing service is healthy from his side"),
    ("cart-cache WARN hot key cart:prices:* 41k ops/s on node 2", "Lina: cart-cache has hot keys on the cart price entries after a cache-wide price refresh; CPU is pinned.", "Lina posts her finding: a cache-wide refresh of cart prices left hot keys that pin the cache's processors"),
    ("", "Sam: cart-cache has 4 nodes, sized for last week's traffic.", "Sam notes the cart cache runs four nodes sized for last week's load"),
    ("", "Jess: 23 open chats about slow checkout.", "support now has 23 open chats about slow checkout"),
    # t41-46: scale-out under way
    ("infra: cart-cache scale 4 -> 6 nodes requested by sam", "Sam: adding two cart-cache nodes, provisioning started.", "Sam has requested two more cart-cache nodes and provisioning has begun"),
    ("infra: cart-cache node 5 joining cluster", "Lina: node 5 is joining.", "Lina watches the fifth node join"),
    ("infra: cart-cache slot migration 35%", "Tom: CPU dipping on the old nodes as slots move.", "Tom sees load dipping on the original nodes as slots migrate"),
    ("infra: cart-cache node 6 joining cluster", "Sam: node 6 provisioned, waiting on the slot migration.", "Sam reports the sixth node is up and slots are still moving"),
    ("infra: cart-cache slot migration 80%", "Lina: migration at 80%.", "Lina says the slot migration is 80% done"),
    ("infra: cart-cache scale-out complete, 6 nodes serving", "Sam: six nodes serving.", "Sam confirms the cache now runs on six nodes"),
    # t47-55: both objectives met, counting up
    ("", "Lina: p95 470, errors 0.3%, first green minute.", "Lina calls out the first minute with both checkout numbers back inside their limits"),
    ("", "Jess: new chats about slow checkout have stopped.", "support says no new slow-checkout chats are arriving"),
    ("", "Ravi: filing a bug to cap rule-engine calls on the quote path.", "Ravi files a bug to limit rule-engine calls when quoting"),
    ("", "Tom: I owe orders-db an apology.", "Tom jokes that he owes the orders database an apology"),
    ("", "Tom: graphs look great, can we close it?", "Tom thinks the graphs look great and asks whether the incident can be closed"),
    ("", "Sam: posting a summary in #incidents meanwhile.", "Sam is posting a summary in the incidents channel"),
    ("", "Lina: cart-cache CPU settled around 50% across six nodes.", "Lina says the cache has settled at about half load across six nodes"),
    ("", "Jess: keeping the support banner up for now.", "support is leaving its banner up for the moment"),
    ("", "Ravi: pricing dashboards are all green.", "Ravi reports the pricing dashboards all green"),
    # t56-61: ten clean minutes, incident still open
    ("", "Tom: still peak traffic, about 1,900 orders a minute.", "Tom notes traffic is still at peak, about 1,900 orders a minute"),
    ("", "Lina: postmortem doc created, I'm linking the traces.", "Lina has started the postmortem document and is linking traces"),
    ("", "Jess: can I tell customers it's fixed?", "support asks whether customers may be told it is fixed"),
    ("", "Ravi: v4.12 stays blocked in the pipeline until the fix lands.", "Ravi says release 4.12 stays blocked until the fix lands"),
    ("", "Tom: heading off unless someone needs me.", "Tom is heading off unless needed"),
    ("", "Sam: the postmortem timeline is drafted.", "Sam has drafted the postmortem timeline"),
    # t62-66: incident closed
    ("incident: INC-2291 status -> closed by sam", "Sam: INC-2291 closed at 21:02, thanks all. Priya has stood down as commander.", "Sam has closed the incident at 21:02 and thanked everyone, and Priya has stepped down as commander"),
    ("", "Lina: postmortem booked for Thursday 10:00.", "Lina books the postmortem for Thursday morning"),
    ("", "Jess: support banner removed.", "support takes its banner down"),
    ("", "Ravi: rule-engine fix is in review.", "Ravi says the rule-engine fix is in review"),
    ("", "Lina: handing the pager back to Sam for the rest of the night.", "Lina hands the pager back to Sam for the night"),
    # t67-70: reopened, error rate above 5%, nobody in command
    ("[prod] ALERT checkout error rate 5.0%, p95 1,380 ms; INC-2291 reopened", "Sam: it's back and worse. The cart-cache autoscaler removed two nodes at 21:07; its minimum is 4.", "a live alert has fired again and the incident is reopened; Sam says the cache autoscaler dropped two nodes at 21:07 because its minimum is four"),
    ("", "Lina: cart-cache CPU 97% on the four remaining nodes.", "Lina reports the four remaining cache nodes are almost fully loaded"),
    ("", "Jess: chats spiking, customers see 'payment page could not load'.", "support's chats are spiking with customers who cannot load the payment page"),
    ("", "Sam: nobody has picked up command for this yet.", "Sam notes that nobody has taken charge yet"),
    # t71-76: commander back, second scale-out under way
    ("infra: cart-cache scale 4 -> 6 nodes requested by sam (new nodes cc-7, cc-8)", "Priya (incident commander): I have command again. Sam: already requesting two fresh cart-cache nodes.", "Priya is back in charge as incident commander, and Sam has already asked for two fresh cache nodes"),
    ("infra: cart-cache node cc-7 provisioned, joining", "Sam: the autoscaler minimum is 4, so it removed the nodes we added.", "Sam explains the autoscaler's minimum of four undid the added nodes"),
    ("infra: cart-cache slot migration 30%", "Lina: CPU 90%, p95 around 1.2 s.", "Lina reads the cache at 90% load and checkout around 1.2 seconds"),
    ("infra: cart-cache node cc-8 provisioned, joining", "Priya: we pin the autoscaler minimum to 6 once this is over.", "Priya decides the autoscaler minimum will be pinned to six afterwards"),
    ("infra: cart-cache slot migration 75%", "Jess: 41 open chats.", "support has 41 open chats"),
    ("infra: cart-cache slot migration 95%", "Priya: Sam, how long did this take last time? Sam: about five minutes.", "Priya asks how long this took before and Sam says about five minutes"),
    # t77-81: scale-out finished, objectives still breached but easing
    ("infra: cart-cache scale-out complete, cc-7 and cc-8 serving (6 nodes)", "Sam: cc-7 and cc-8 are taking traffic.", "Sam confirms the two fresh nodes are taking traffic"),
    ("", "Tom: back online, saw the alert.", "Tom is back online after seeing the alert"),
    ("", "Lina: the old nodes are cooling off and p95 is falling.", "Lina says the old nodes are cooling off and checkout times are falling"),
    ("", "Jess: chats slowing down.", "support's chats are slowing down"),
    ("", "Sam: 530 on the last minute, nearly there.", "Sam reads 530 ms for the last minute and says it is nearly there"),
    # t82-90: both objectives met again, counting up
    ("", "Lina: p95 460, errors 0.4%.", "Lina reads the first minute back inside both limits"),
    ("", "Priya: nobody touches the autoscaler until Monday.", "Priya orders that nobody touches the autoscaler until Monday"),
    ("", "Ravi: pricing still on v4.11 and healthy.", "Ravi confirms pricing is still on the previous build and healthy"),
    ("", "Jess: chats dropping off.", "support's chats are dropping off"),
    ("orders-db INFO nightly vacuum started 21:25", "Tom: orders-db is at 87% CPU. Scale that out too?", "the orders database has started its nightly vacuum, and Tom notices it at 87% load and asks about adding capacity there too"),
    ("", "Lina: that's the nightly vacuum, it looks like that every night.", "Lina says the orders database load is the vacuum it runs every night"),
    ("", "Priya: I'll own the postmortem for the reopen.", "Priya takes ownership of the postmortem for the reopening"),
    ("", "Sam: cart-cache CPU 49%.", "Sam reads the cache at 49% load"),
    ("orders-db INFO nightly vacuum finished 21:30", "Jess: last open chat closed.", "the vacuum has finished, and support has closed its last open chat"),
    # t91-99: ten clean minutes again, incident open
    ("", "Tom: p95 flat around 440.", "Tom says checkout latency is flat around 440 ms"),
    ("", "Lina: autoscaler minimum change is up for review on Monday.", "Lina says the autoscaler change is queued for review on Monday"),
    ("", "Priya: Ravi, when does the rule-engine fix ship?", "Priya asks Ravi when the rule-engine fix will ship"),
    ("", "Ravi: Tuesday, behind a flag, with a 50 ms timeout on quotes.", "Ravi says the fix ships on Tuesday behind a flag with a 50 ms quote timeout"),
    ("", "Jess: refunding delivery fees for the 14 orders that timed out.", "support is refunding delivery fees on the 14 orders that timed out"),
    ("", "Sam: exporting the evening's graphs for the postmortem.", "Sam is exporting the evening's graphs for the postmortem"),
    ("", "Tom: signing off again; the orders-db vacuum finished at 21:30.", "Tom signs off again, noting the orders database vacuum finished at 21:30"),
    ("", "Lina: timeline doc updated with the reopen.", "Lina updates the timeline with the reopening"),
    ("", "Priya: thanks, everyone; I'll send the leads a summary.", "Priya thanks everyone and will send the leads a summary"),
]
assert len(A_SCRIPT) == 100

# Per-tick production checkout readings (last minute).
A_P95 = [
    380, 395, 410, 428, 446, 462, 481, 492,  # t0-7
    560, 690, 780, 910, 940, 925, 950,  # t8-14
    960, 955, 948, 962, 958, 952, 950,  # t15-21
    940, 900, 870, 860, 880, 905, 820, 760,  # t22-29
    700, 680, 660, 670, 690,  # t30-34
    720, 760, 800, 830, 810, 820,  # t35-40
    800, 760, 690, 610, 560, 530,  # t41-46
    470, 455, 440, 430, 425, 430, 420, 415, 422,  # t47-55
    418, 412, 420, 416, 410, 414,  # t56-61
    408, 402, 398, 405, 400,  # t62-66
    1380, 1450, 1510, 1420,  # t67-70
    1350, 1290, 1240, 1180, 1100, 990,  # t71-76
    860, 730, 620, 560, 530,  # t77-81
    460, 445, 438, 440, 436, 442, 438, 430, 440,  # t82-90
    435, 432, 428, 430, 426, 431, 429, 425, 427,  # t91-99
]
A_ERR = [
    0.3, 0.3, 0.4, 0.3, 0.4, 0.3, 0.4, 0.4,
    0.4, 0.5, 0.6, 0.6, 0.7, 0.6, 0.7,
    0.7, 0.8, 0.7, 0.8, 0.9, 0.8, 0.9,
    1.4, 2.2, 3.1, 4.6, 4.8, 4.9, 3.1, 2.0,
    1.2, 0.8, 0.7, 0.8, 0.8,
    0.9, 0.9, 0.9, 1.1, 1.2, 1.1,
    0.9, 0.8, 0.7, 0.6, 0.5, 0.5,
    0.3, 0.3, 0.3, 0.2, 0.3, 0.3, 0.2, 0.3, 0.3,
    0.2, 0.3, 0.2, 0.3, 0.3, 0.2,
    0.3, 0.2, 0.3, 0.2, 0.3,
    5.0, 6.8, 7.1, 6.5,  # t67 sits exactly on rule 1's 5.0% line
    6.0, 5.6, 5.1, 4.6, 3.9, 3.1,
    2.4, 1.8, 1.4, 1.2, 0.9,
    0.4, 0.3, 0.3, 0.3, 0.2, 0.3, 0.3, 0.2, 0.3,
    0.2, 0.3, 0.2, 0.2, 0.3, 0.2, 0.3, 0.2, 0.2,
]
A_CART_CPU = [
    34, 35, 36, 38, 39, 40, 41, 42,
    43, 43, 44, 44, 45, 45, 44,
    44, 45, 45, 44, 45, 46, 46,
    47, 49, 52, 55, 58, 62, 66, 69,
    74, 77, 79, 81, 83,
    85, 89, 91, 92, 90, 91,  # t35 sits exactly on rule 5's 85% line
    88, 80, 72, 66, 61, 58,
    55, 54, 53, 52, 52, 51, 52, 50, 51,
    50, 49, 50, 51, 50, 49,
    48, 50, 49, 51, 50,
    96, 97, 97, 96,
    95, 94, 90, 82, 74, 66,
    60, 56, 54, 52, 51,
    52, 51, 50, 50, 51, 50, 50, 49, 49,
    48, 48, 49, 48, 47, 48, 47, 48, 47,
]
assert len(A_P95) == len(A_ERR) == len(A_CART_CPU) == 100
# orders-db CPU during the order-status read surge after the rollback and during the nightly
# vacuum; otherwise 40-46%.
A_ORDERS_CPU = {30: 86, 31: 88, 32: 89, 33: 87, 34: 86, 35: 55, 86: 87, 87: 89, 88: 88, 89: 86, 90: 71}
# pricing-svc CPU while the rollback drains pods (fewer pods carry the load).
A_PRICING_CPU = dict(zip(range(22, 30), [64, 74, 86, 89, 87, 79, 71, 66]))
# p95 of the span that traces blame, while one is blamed (ms).
A_HOT_MS = dict(
    zip(range(8, 30), [260, 330, 380, 430, 440, 430, 450, 450, 445, 440, 455, 450, 452, 448, 420, 380, 340, 300, 260, 220, 170, 120])
)
A_HOT_MS.update(zip(range(30, 47), [120, 140, 150, 155, 160, 175, 190, 205, 220, 210, 215, 205, 170, 120, 80, 50, 35]))
A_HOT_MS.update(zip(range(67, 82), [420, 460, 480, 450, 430, 410, 390, 360, 320, 270, 210, 150, 100, 70, 50]))
A_SPAN = {"pricing-svc": ("quote span", 60), "cart-cache": ("cart read", 3)}
A_SPAN_P = {"pricing-svc": "price-quote step", "cart-cache": "cart lookup"}
A_ROLLBACK_PODS = dict(zip(range(22, 30), [0, 1, 2, 3, 4, 4, 5, 5]))  # pods of 6 already on v4.11
A_SCALE_STEPS = {
    41: "provisioning two new nodes", 42: "node 5 joining", 43: "slot migration at 35%", 44: "node 6 joining", 45: "slot migration at 80%",
    71: "requesting nodes cc-7 and cc-8", 72: "cc-7 joining", 73: "slot migration at 30%", 74: "cc-8 joining", 75: "slot migration at 75%", 76: "slot migration at 95%",
}
A_FINDING_PRICING = {
    "service": "pricing-svc", "deploy": "v4.12", "time": "20:15", "by": "Sam",
    "text": "pricing-svc logs show RuleEngineTimeout on quotes since 19:52, one minute after v4.12 went out; the timeouts come from v4.12",
    "text_p": "Sam traced the rule-engine timeouts in pricing-svc (since 19:52, a minute after build 4.12 shipped) to build 4.12",
}
A_FINDING_CACHE = {
    "service": "cart-cache", "deploy": None, "time": "20:38", "by": "Lina",
    "text": "cart-cache has hot keys on the cart price entries (cart:prices:*) after a cache-wide price refresh, which pinned its CPU; not linked to any service's deploy",
    "text_p": "Lina found that a cache-wide refresh of cart prices left cart-cache with hot keys that drove its processors to the limit, unrelated to any service's release",
}
A_FINDING_AUTOSCALER = {
    "service": "cart-cache", "deploy": None, "time": "21:07", "by": "Sam",
    "text": "the cart-cache autoscaler removed 2 of its 6 nodes at 21:07 because its minimum is 4, undoing the 20:46 scale-out; not linked to any deploy",
    "text_p": "Sam found that the cart-cache autoscaler, set to a minimum of four nodes, took away two of its six at 21:07 and undid the 20:46 capacity increase, with no release involved",
}
A_APPROVAL = {"by": "Priya Raman", "at": "20:19", "pre": False}
A_PRE_APPROVAL = {"by": "Priya Raman", "at": "19:40", "pre": True}
# Every phrasing of the advance approval (structural_cf) keeps the explicit clause that it
# is the incident commander's approval of that rollback, so rule 4's exception reads the
# same in every surface style.
A_PRE_APPROVAL_TEXT = [
    "Approval on file: {b}, tonight's on-call incident commander, pre-approved a rollback of pricing-svc v4.12 at {a}, before the launch; the launch runbook records it as the incident commander's approval of that rollback.",
    "Rollback approval on file: at {a}, before the launch, {b}, tonight's on-call incident commander, approved in advance rolling pricing-svc v4.12 back; the launch runbook counts it as the incident commander's approval of that rollback.",
]
A_PRE_APPROVAL_TEXT_P = [
    "on record is a sign-off that {b}, tonight's on-call incident commander, gave in advance at {a} for reverting pricing build 4.12, which the launch runbook logs as the incident commander's sign-off on that revert.",
    "{b}, the incident commander on call tonight, signed off ahead of time, at {a}, on reverting pricing build 4.12, and the launch runbook treats that as the incident commander's sign-off on that revert.",
]
assert all("incident commander's approval of that rollback" in s for s in A_PRE_APPROVAL_TEXT)
assert all("incident commander's sign-off on that revert" in s for s in A_PRE_APPROVAL_TEXT_P)

# Irrelevant chatter for the lexical-decoy register, keyed by the action whose
# vocabulary it borrows. None of it concerns production checkout, and a tick never
# borrows its own gold action.
A_DECOYS = {
    "observe": [
        "#marketing: the newsletter team will keep watching their dashboards without taking a new action until Monday.",
        "#design: 'keep watching the icon dashboards, no new action on the palette yet', says the design lead.",
    ],
    "inspect": [
        "#frontend: a new hire was asked to inspect the logs and traces of last week's style-guide build as practice.",
        "#learning: this month's brown-bag session teaches how to inspect logs and traces of any toy service.",
    ],
    "rollback": [
        "#facilities: they will roll back the most recent deploy of the meeting-room kiosk firmware tomorrow morning.",
        "#it-help: the laptop fleet team plans to roll back the recent deploy of the wallpaper tool on Friday.",
    ],
    "scale_out": [
        "#analytics: the notebook team plans to scale out their service by adding more instances next quarter.",
        "#hr-tools: the holiday-request form may scale out by adding more instances before December.",
    ],
    "escalate": [
        "#social: the parking question will escalate to the building manager by paging her at lunch.",
        "#office: the coffee-machine complaint is being escalated to the landlord by paging his assistant.",
    ],
    "resolve": [
        "#design: the font-licensing ticket was declared resolved and they will close it out on Friday.",
        "#finance: the expense-tool bug was declared resolved; accounting will close it out tomorrow.",
    ],
}
# On distractor ticks the decoy borrows the wrong action the distractor tempts.
A_DECOY_TEMPTS = {3: "inspect", 4: "inspect", 11: "scale_out", 17: "scale_out", 24: "scale_out", 25: "scale_out", 26: "scale_out", 51: "resolve", 86: "scale_out", 87: "scale_out", 88: "scale_out", 89: "scale_out"}
# Where a distractor tempts a wrong target rather than a wrong action (t11: Tom blames
# orders-db while gold is to inspect pricing-svc), the decoy also names that target in an
# unrelated context.
A_DECOY_NAMED = {
    11: "#hackathon: the team behind last year's toy orders-db, a pretend orders database, will scale out their demo by adding more instances.",
}


class CheckoutLatency(Scenario):
    family = FAMILY
    scenario_id = "incident_a"
    title = "Next-move calls during a checkout-latency incident"
    tier = "medium"
    difficulty_features = [
        "two_questions_per_decision",
        "six_action_options",
        "five_target_options",
        "seven_rule_priority_policy",
        "threshold_comparisons",
        "duration_threshold",
        "change_freeze_exception",
        "target_differs_from_traced_service",
        "staging_vs_production_distractor",
    ]
    decision_structures = ["maintain", "wait", "rollback", "escalate", "recover", "terminate", "resolve-conflict"]
    deadline_steps = 2

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            base = {"role": A_ROLE_P, "rules": A_POLICY_P}
            q_action = "Work down the rules and use the first that fits this minute. What is the next move?"
            q_target = "Work down the rules and use the first that fits this minute. Which service is that move aimed at, if any?"
            options, targets = A_OPTIONS_P, A_TARGETS_P
        else:
            base = {"role": A_ROLE, "policy": A_POLICY}
            q_action = "Apply the first rule that matches the current state. What should the on-call engineer do next?"
            q_target = "Apply the first rule that matches the current state. Which service, if any, is the target of that next action?"
            options, targets = A_OPTIONS, A_TARGETS
        return [
            Choice("action", {**base, "question": q_action}, dict(options)),
            Choice("target", {**base, "question": q_target}, dict(targets)),
        ]

    # ------------------------------------------------------------------ latent
    @staticmethod
    def _latent_at(t: int) -> dict[str, Any]:
        if t < 8:
            incident: dict[str, Any] = {"status": "none"}
        elif t < 62:
            incident = {"status": "open", "opened": "20:08"}
        elif t < 67:
            incident = {"status": "closed", "opened": "20:08", "closed": "21:02"}
        else:
            incident = {"status": "open", "opened": "20:08", "closed": "21:02", "reopened": "21:07"}
        if 8 <= t <= 29:
            hot = "pricing-svc"
        elif 30 <= t <= 46 or 67 <= t <= 81:
            hot = "cart-cache"
        else:
            hot = None
        if t < 8:
            pricing_cpu = 41 + (t * 5) % 6
        elif t < 22:
            pricing_cpu = 55 + (t * 3) % 8
        elif t < 30:
            pricing_cpu = A_PRICING_CPU[t]
        else:
            pricing_cpu = 38 + (t * 5) % 7
        cpu = {
            "checkout-api": 38 + (t * 7) % 9,
            "pricing-svc": pricing_cpu,
            "cart-cache": A_CART_CPU[t],
            "orders-db": A_ORDERS_CPU.get(t, 40 + (t * 4) % 7),
        }
        findings = []
        if t >= 15:
            findings.append(dict(A_FINDING_PRICING))
        if t >= 38:
            findings.append(dict(A_FINDING_CACHE))
        if t >= 67:
            findings.append(dict(A_FINDING_AUTOSCALER))
        change = None
        if 22 <= t <= 29:
            change = {"kind": "rollback", "service": "pricing-svc", "started": "20:22", "pods": A_ROLLBACK_PODS[t]}
        elif 41 <= t <= 45 or 71 <= t <= 76:
            change = {"kind": "scale_out", "service": "cart-cache", "started": "20:41" if t <= 45 else "21:11",
                      "detail": A_SCALE_STEPS[t]}
        if t < 30:
            last = None
        elif t < 46:
            last = "pricing-svc rollback to v4.11 finished at 20:30"
        elif t < 67:
            last = "cart-cache scale-out from 4 to 6 nodes finished at 20:46"
        elif t < 77:
            last = "the cart-cache autoscaler removed 2 nodes at 21:07 (6 -> 4)"
        else:
            last = "cart-cache scale-out from 4 to 6 nodes finished at 21:17"
        # met_since is the minute the current streak started: the first good
        # one-minute reading at t covers minute t-1 to t.
        if 47 <= t <= 66:
            met_since: int | None = 46
        elif t >= 82:
            met_since = 81
        else:
            met_since = None
        if 19 <= t <= 61:
            ic: dict[str, str] | None = {"name": "Priya Raman", "since": "20:19"}
        elif t >= 71:
            ic = {"name": "Priya Raman", "since": "21:11"}
        else:
            ic = None
        return {
            "minute": t,
            "incident": incident,
            "p95_ms": A_P95[t],
            "err_pct": A_ERR[t],
            "met_since": met_since,
            "hot": hot,
            "hot_ms": A_HOT_MS.get(t),
            "cpu": cpu,
            "nodes": 6 if (46 <= t <= 66 or t >= 77) else 4,
            "versions": {"pricing-svc": "v4.12" if t < 30 else "v4.11"},
            "findings": findings,
            "change": change,
            "last_change": last,
            "ic": ic,
            "freeze": True,
            "approved": dict(A_APPROVAL) if t >= 19 else None,
        }

    def _canonical(self) -> list[Tick]:
        tags = span_tags(
            {
                "distractor": [(3, 4), 11, 17, (24, 26), 51, (86, 89)],
                "minimal_change": [8, 35, 56],
                "recovery": [22, 41, 71],
                "hold_under_activity": [(27, 29), (42, 45), (72, 76)],
                "boundary": [(56, 64), (91, 99)],
                "priority_conflict": [(22, 29), (30, 37), 41, (67, 73)],
                "arithmetic": [(6, 7), (24, 26), (30, 31), 35, (54, 56), 67, (86, 91)],
            }
        )
        notes = {
            3: "Staging-only checkout-api alert; production objectives met, so no inspection.",
            6: "p95 481 ms, still within the 500 ms objective.",
            7: "p95 492 ms, still within the objective.",
            8: "p95 crosses 500 ms; traces blame pricing-svc and nobody has posted findings.",
            11: "Speculation about orders-db without evidence; traces still blame pricing-svc.",
            15: "Findings tie the timeouts to pricing-svc v4.12, still running; the launch freeze needs the commander's approval and none is on file: escalate.",
            17: "Suggestion to add pricing pods; pricing CPU is far below 85%.",
            19: "Priya takes command and approves the rollback under the freeze: roll back pricing-svc.",
            22: "Rollback started; rule 2 outranks rule 4 while it runs.",
            24: "pricing-svc CPU 86-89% on the pods still serving, but the rollback is running: rule 2 outranks rule 5.",
            25: "Error rate 4.6-4.9%: below 5.0%, and a commander is engaged anyway.",
            9: "Lina reads the traces in chat but says she has not opened the logs; no findings are posted, so rule 6 holds.",
            30: "Rollback finished; p95 still breached; customers reloading their order pages push orders-db to 86-89% while traces blame cart-cache: rule 5 outranks rule 6, target orders-db. Rule-literal by design (the role says a rule's named service is the target even when the traces blame another).",
            35: "Read surge over; cart-cache CPU at exactly 85% meets rule 5's '85% or higher': scale out cart-cache (not inspect).",
            38: "Findings on cart-cache posted; rule 5 still applies.",
            41: "Scale-out started; cart-cache still at 88% but rule 2 outranks rule 5.",
            46: "Scale-out finished; p95 530 ms still breached; cart-cache is explained by a finding and no service is at 85%.",
            47: "Both objectives met from 20:46 (first good reading).",
            51: "'Can we close it?' after 5 clean minutes; resolve needs 10.",
            54: "8 clean minutes.",
            55: "9 clean minutes: still short of 10.",
            56: "10 clean minutes with the incident open: declare resolved.",
            62: "Incident closed; objectives met but no incident is open.",
            67: "Autoscaler removed nodes; error rate exactly 5.0% meets rule 1's '5.0% or higher' with no incident commander: escalate outranks scale-out.",
            71: "Commander back and a second scale-out already requested: keep watching (cart-cache CPU 95% but rule 2 outranks rule 5).",
            77: "Scale-out finished; p95 still breached; cart-cache is explained by the 21:07 finding.",
            82: "Both objectives met from 21:21.",
            86: "orders-db at 87-89% CPU (nightly vacuum) while both objectives are met: rule 5 needs a breach.",
            90: "9 clean minutes.",
            91: "10 clean minutes with the reopened incident open: declare resolved.",
        }
        tl = Timeline(self._latent_at(0))
        for t in range(100):
            tl.step(surface_of(A_SCRIPT[t]), tags[t], notes.get(t, ""), **self._latent_at(t))
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t30-34: the order-status read surge is lighter, so orders-db stays
            #     under 85% and the traces send us to inspect cart-cache.
            for t, value in {30: 80, 31: 83, 32: 84, 33: 82, 34: 79}.items():
                cpu = dict(ticks[t].latent["cpu"], **{"orders-db": value})
                ticks = override(ticks, [t], cpu=cpu, tags=["minimal_change", "arithmetic"],
                                 note="orders-db under 85% and no findings on cart-cache yet: inspect cart-cache.")
            ticks = override(ticks, [32], surface=lambda tk, i: dict(
                tk.surface, chat="Tom: orders-db is busy too, told you it was the database!",
                gist="Tom notes the orders database is busy too and claims he was right all along"))
            # (2) t52: a one-minute error blip restarts the clean streak at 20:52, so the
            #     ten clean minutes arrive only at 21:02, when Sam closes the incident.
            ticks = override(ticks, [52], err_pct=1.3, met_since=None,
                             note="One bad minute (errors 1.3%) breaks the clean streak.",
                             surface=lambda tk, i: surface_of(("", "Lina: one bad minute, errors 1.3% from a burst of card retries.", "Lina reports one bad minute with 1.3% errors from a burst of card retries")))
            ticks = override(ticks, range(53, 67), met_since=52)
            ticks = override(ticks, [53], note="1 clean minute since the blip.")
            ticks = override(ticks, [54], note="2 clean minutes since the blip.")
            ticks = override(ticks, [55], note="3 clean minutes since the blip: far short of 10.")
            ticks = override(ticks, range(56, 62), tags=["minimal_change", "arithmetic"],
                             note="Clean streak restarted at 20:52: under 10 minutes, keep watching.")
            # The team closes INC-2291 in the very minute the restarted streak reaches 10
            # (21:02), so this variant has no resolve tick for the first incident: the
            # 21:02 snapshot already shows it closed. Sam's closing line says so.
            ticks = override(ticks, [62], note="Sam closed the incident at 21:02, the minute the restarted streak reached 10; no incident is open, so rule 3 does not apply.",
                             surface=lambda tk, i: surface_of((
                                 "incident: INC-2291 status -> closed by sam",
                                 "Sam: that's ten clean minutes since the 20:52 blip, so INC-2291 is closed at 21:02; thanks all. Priya has stood down as commander.",
                                 "Sam has closed the incident at 21:02, as soon as ten clean minutes had passed since the blip, and Priya has stepped down as commander")))
            # (3) t67-70: Priya took command the moment the incident reopened.
            ticks = override(ticks, range(67, 100), ic={"name": "Priya Raman", "since": "21:07"})
            surf3 = {
                67: ("[prod] ALERT checkout error rate 5.0%, p95 1,380 ms; INC-2291 reopened", "Sam: it's back and worse. The cart-cache autoscaler removed two nodes at 21:07; its minimum is 4. Priya: I have command.", "a live alert has fired again and the incident is reopened; Sam says the cache autoscaler dropped two nodes, and Priya takes charge at once"),
                70: ("", "Priya: Sam, keep posting numbers every couple of minutes.", "Priya asks Sam to keep posting numbers every couple of minutes"),
                71: ("infra: cart-cache scale 4 -> 6 nodes requested by sam (new nodes cc-7, cc-8)", "Priya: Sam, add two fresh nodes. Sam: already requesting them.", "Priya asks Sam for two fresh cache nodes and Sam has already requested them"),
            }
            ticks = override(ticks, [67, 70, 71], surface=lambda tk, i: surface_of(surf3[i]))
            ticks = override(ticks, [71], note="Second scale-out requested: keep watching (cart-cache CPU 95% but rule 2 outranks rule 5).")
            ticks = override(ticks, range(67, 71), tags=["minimal_change"],
                             note="Incident commander already engaged, so rule 1 does not fire; cart-cache CPU >= 85%: scale out.")
        elif variant == "structural_cf":
            # The launch plan already holds the commander's approval for rolling back
            # pricing v4.12, so nobody has to page her; she first joins at the reopen.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for t, tk in enumerate(ticks):
                tk.latent["approved"] = dict(A_PRE_APPROVAL)
                if t <= 70:
                    tk.latent["ic"] = None
                if 15 <= t <= 18:
                    tk.note = "The commander's pre-approval of this rollback is on file, so the rule-4 exception does not apply even with no commander engaged: roll back pricing-svc."
            ticks[19].note = "Still no rollback started; the pre-approval stands: roll back pricing-svc."
            ticks[71].note = "Priya takes command and a second scale-out is already requested: keep watching (cart-cache CPU 95% but rule 2 outranks rule 5)."
            ticks[19].surface = surface_of(("", "Lina: the quote timeouts line up exactly with the 19:51 release.", "Lina notes that the quote timeouts line up exactly with the 19:51 release"))
            ticks[20].surface = surface_of(("", "Sam: pulling v4.11 from the registry; the launch plan's rollback approval is attached.", "Sam is fetching the previous pricing build with the launch plan's rollback approval attached"))
            ticks[22].surface = dict(ticks[22].surface, log="deploy: pricing-svc rollback v4.12 -> v4.11 started by sam (freeze approval on file: priya, 19:40)")
            ticks[27].surface = surface_of(("deploy: pricing-svc pod 5/6 starting", "Sam: 4.9% on the last minute. Tom: that's basically five percent, should someone page an IC?", "Sam gives 4.9% for the last minute and Tom, calling it basically five percent, wonders about paging an incident commander"))
            for t in (25, 26, 27):
                ticks[t].tags = sorted(set(ticks[t].tags) | {"distractor", "arithmetic"})
                ticks[t].note = "Error rate 4.6-4.9% with nobody in command: still below the 5.0% escalation line; the rollback is running."
            ticks[62].surface = surface_of(("incident: INC-2291 status -> closed by sam", "Sam: INC-2291 closed at 21:02, thanks all.", "Sam has closed the incident at 21:02 and thanked everyone"))
            ticks[71].surface = dict(ticks[71].surface, chat="Priya (incident commander): I have command. Sam: already requesting two fresh cart-cache nodes.",
                                     gist="Priya takes charge as incident commander, and Sam has already asked for two fresh cache nodes")
        return retag_recovery(self, ticks)

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        breached = z["p95_ms"] > 500 or z["err_pct"] > 1.0
        met_minutes = z["minute"] - z["met_since"] if z["met_since"] is not None else -1
        tied = [f["service"] for f in z["findings"] if f["deploy"] and z["versions"].get(f["service"]) == f["deploy"]]
        saturated = [s for s in A_SERVICES if z["cpu"][s] >= 85]
        explained = {f["service"] for f in z["findings"]}
        if z["err_pct"] >= 5.0 and z["ic"] is None:
            action, target = "escalate", "none"
        elif z["change"] is not None:
            action, target = "observe", "none"
        elif z["incident"]["status"] == "open" and met_minutes >= 10:
            action, target = "resolve", "none"
        elif breached and tied:
            if z["freeze"] and not z["approved"]:
                action, target = "escalate", "none"
            else:
                action, target = "rollback", tied[0]
        elif breached and saturated:
            assert len(saturated) == 1, saturated
            action, target = "scale_out", saturated[0]
        elif breached and z["hot"] is not None and z["hot"] not in explained:
            action, target = "inspect", z["hot"]
        else:
            action, target = "observe", "none"
        return {"action": action, "target": target}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "A change freeze for the bundle-discount launch is in effect all evening. Checkout p95 creeps up with the evening peak and breaches at 20:08 (t8); traces blame pricing-svc (inspect); findings tie it to v4.12 but no commander has approved a rollback under the freeze (escalate, t15); Priya takes command and approves (roll back, t19); the rollback runs while pricing CPU spikes to 86-89% on the remaining pods (watch, t22); after it, customers whose checkout hung reload their order pages and the read surge saturates orders-db while the traces blame cart-cache (scale out orders-db, t30), then the surge fades as cart-cache reaches exactly 85% (scale out cart-cache, t35); the scale-out runs and ten clean minutes lead to resolve (t56) and closure (t62); the autoscaler undoes the fix and the incident reopens with errors at exactly 5.0% and nobody in command (escalate, t67); the commander is back and a second scale-out already runs (watch, t71); the nightly vacuum pushes orders-db to 87-89% while objectives are met (t86-89); ten clean minutes lead to resolve again (t91)."},
            "paraphrase": {"summary": "Same latent trajectory; reworded role, rules and options; states become one prose paragraph (command and freeze first, then work, findings, releases and the numbers) instead of labelled fields."},
            "lexical_decoy": {"summary": "Same latent trajectory; each state adds one line of chatter from an unrelated channel that borrows the wording of a wrong action (roll back a kiosk deploy, scale out a notebook service, declare a ticket resolved...), never the gold one. On distractor ticks it borrows the wrong action the distractor tempts; at t11, where Tom tempts the wrong target orders-db, it also names a toy orders-db in a hackathon demo. Elsewhere it is drawn per tick from the non-gold actions."},
            "minimal_cf": {"summary": "Three local edits: t30-34 a lighter read surge leaves orders-db CPU at 79-84% instead of 86-89% (scale_out orders-db -> inspect cart-cache); a one-minute error blip at t52 restarts the clean streak at 20:52 (t56-61 resolve -> observe); the team closes INC-2291 at 21:02 (t62), the very minute the restarted streak reaches 10, so in this variant the first incident has no resolve tick: the 21:02 snapshot already shows it closed and Sam's closing line ties the closure to the ten clean minutes; t67-70 the incident commander took command at 21:07 when the incident reopened (escalate -> scale_out cart-cache)."},
            "structural_cf": {"summary": "The launch plan already holds Priya's approval (19:40) for rolling back pricing v4.12, on file as the incident commander's approval, so at t15-18 the rule-4 exception does not apply and the rollback is due at once; nobody pages her, so no commander is engaged until the reopen, which turns the 4.6-4.9% error rate at t25-27 into a live escalation temptation. The policy text is unchanged."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _incident_line(self, z: dict[str, Any], t: int) -> str:
        inc = z["incident"]
        if inc["status"] == "none":
            return pick(["No incident is open.", "No open incident; normal evening operations."], "a-inc0", t)
        if inc["status"] == "closed":
            return pick(["INC-2291 (slow checkout) was closed at {c}; no incident is open.", "No incident is open: INC-2291 (slow checkout) was closed at {c}."], "a-incc", t).format(c=inc["closed"])
        if "reopened" in inc:
            return pick(
                ["INC-2291 (slow checkout) reopened at {r} and is open (first opened {o}, closed {c}).", "INC-2291 (slow checkout) is open again since {r} (first opened {o}, closed {c})."],
                "a-incr", t,
            ).format(r=inc["reopened"], o=inc["opened"], c=inc["closed"])
        return pick(["INC-2291 (slow checkout) open since {o}.", "Incident INC-2291, slow checkout, opened {o} and still open."], "a-inc", t).format(o=inc["opened"])

    def _checkout_line(self, z: dict[str, Any], t: int) -> str:
        return pick(
            [
                "Production p95 latency {p:,} ms (objective 500 ms); error rate {e}% (objective 1.0%).",
                "Production error rate {e}% against a 1.0% objective; p95 latency {p:,} ms against 500 ms.",
                "Production p95 latency {p:,} ms (objective 500 ms); {n} of every 1,000 production checkout requests failed (objective 1.0%).",
            ],
            "a-met",
            t,
        ).format(p=z["p95_ms"], e=z["err_pct"], n=round(z["err_pct"] * 10))

    @staticmethod
    def _breached(z: dict[str, Any]) -> bool:
        return z["p95_ms"] > 500 or z["err_pct"] > 1.0

    def _streak_line(self, z: dict[str, Any], t: int) -> str:
        # Rule 3 tests the clean streak, so it is stated at every tick, present or absent.
        # With no incident open (before the first one, t0-7, and after the closure,
        # t62-66) both states read alike: no streak is counted.
        inc = z["incident"]
        if inc["status"] == "none":
            return pick(
                ["No clean streak is being counted: no incident has been opened.", "Clean streak: not counted, since no incident is open."],
                "a-streakn", t,
            )
        if inc["status"] == "closed":
            return pick(
                ["No clean streak is being counted: INC-2291 was closed at {c} and no incident is open.", "Clean streak: not counted, since no incident is open (INC-2291 was closed at {c})."],
                "a-streakc", t,
            ).format(c=inc["closed"])
        if z["met_since"] is None:
            # An open incident without a streak always has a breach in the latest minute.
            assert self._breached(z), z["minute"]
            return pick(
                ["No clean streak: an objective was breached in the latest minute.", "Clean streak: none running; the latest minute breached an objective."],
                "a-streak0", t,
            )
        n = z["minute"] - z["met_since"]
        return pick(
            ["Both objectives met continuously since {s} ({n} min).", "{m} in a row with both objectives met (since {s})."],
            "a-streak",
            t,
        ).format(s=clock(A_BASE, z["met_since"]), n=n, m=plural(n, "minute"))

    def _traces_line(self, z: dict[str, Any], t: int) -> str:
        if z["hot"] is None:
            return pick(["No service stands out in the traces; spans at their usual times.", "Traces: every service's spans look normal."], "a-tr0", t)
        span, usual = A_SPAN[z["hot"]]
        return pick(
            [
                "Traces put the extra checkout time in {s}: {span} p95 {ms} ms (usual {u} ms).",
                "Most of the added latency sits in {s} ({span} p95 {ms} ms against a usual {u} ms).",
            ],
            "a-tr",
            t,
        ).format(s=z["hot"], span=span, ms=z["hot_ms"], u=usual)

    def _cpu_line(self, z: dict[str, Any], t: int) -> str:
        cpu = z["cpu"]
        return pick(
            [
                "checkout-api {a}%, pricing-svc {b}%, cart-cache {c}% ({n} nodes), orders-db {d}%.",
                "orders-db {d}%, cart-cache {c}% on {n} nodes, pricing-svc {b}%, checkout-api {a}%.",
            ],
            "a-cpu",
            t,
        ).format(a=cpu["checkout-api"], b=cpu["pricing-svc"], c=cpu["cart-cache"], d=cpu["orders-db"], n=z["nodes"])

    def _deploys_line(self, z: dict[str, Any], t: int) -> str:
        c = z["change"]
        if z["versions"]["pricing-svc"] == "v4.12" and c is not None and c["kind"] == "rollback":
            pricing = f"pricing-svc v4.12 deployed 19:51; rollback to v4.11 in progress ({c['pods']} of 6 pods back on v4.11, the rest still on v4.12)"
        elif z["versions"]["pricing-svc"] == "v4.12":
            pricing = pick(["pricing-svc v4.12 deployed 19:51 (running)", "pricing-svc v4.12 went out at 19:51 and is running"], "a-dep", t)
        else:
            pricing = "pricing-svc v4.12 deployed 19:51, rolled back to v4.11 at 20:30 (v4.12 no longer running)"
        return f"{pricing}; checkout-api v88 deployed yesterday 16:20; cart-cache config change on Monday; orders-db no deploy this week."

    def _findings_line(self, z: dict[str, Any], t: int) -> str:
        if not z["findings"]:
            return pick(["No findings posted yet.", "None posted so far."], "a-find0", t)
        return " ".join(f"{f['by']} at {f['time']}: {f['text']}." for f in z["findings"])

    def _work_line(self, z: dict[str, Any], t: int) -> str:
        c = z["change"]
        if c is None:
            text = pick(["No rollback or scale-out under way.", "Nothing is being rolled back or scaled right now."], "a-work0", t)
            if z["last_change"]:
                text += f" Last change: {z['last_change']}."
            return text
        if c["kind"] == "rollback":
            return pick(
                ["Rollback of {s} from v4.12 to v4.11 started {st}, not finished: {p} of 6 pods on v4.11.", "{s} rollback to v4.11 running since {st}: {p} of 6 pods switched so far."],
                "a-work", t,
            ).format(s=c["service"], st=c["started"], p=c["pods"])
        return pick(
            ["Scale-out of {s} from 4 to 6 nodes started {st}, not finished: {d}.", "{s} scale-out (4 to 6 nodes) running since {st}: {d}."],
            "a-work", t,
        ).format(s=c["service"], st=c["started"], d=c["detail"])

    def _command_line(self, z: dict[str, Any], t: int) -> str:
        ic = z["ic"]
        if ic:
            return pick(["Incident commander: {n}, engaged since {s}.", "{n} holds incident command (since {s})."], "a-ic", t).format(n=ic["name"], s=ic["since"])
        return pick(["Incident commander: none engaged.", "Nobody holds incident command."], "a-ic0", t)

    def _freeze_line(self, z: dict[str, Any], t: int) -> str:
        if not z["freeze"]:
            return "No change freeze in effect."
        head = pick(
            [
                "Change freeze for the bundle-discount launch in effect: any rollback needs the incident commander's approval (a rollback can pull the advertised discounts); scale-outs are pre-approved in the launch runbook.",
                "Bundle-discount launch change freeze on: rollbacks need the incident commander's approval because they can pull the advertised discounts; scale-outs are pre-approved in the launch runbook.",
            ],
            "a-frz", t,
        )
        a = z["approved"]
        if not a:
            return head + " " + pick(["No rollback approval on file.", "No approval of any rollback is on file."], "a-frz0", t)
        if a["pre"]:
            return head + " " + pick(A_PRE_APPROVAL_TEXT, "a-frzp", t).format(b=a["by"], a=a["at"])
        # Rule 4's exception asks for the incident commander's approval, so every
        # phrasing says in what capacity it was given.
        return head + " " + pick(
            ["Approval on file: {b}, as incident commander, approved the pricing-svc rollback at {a}.", "Rollback approval on file: {b} approved rolling pricing-svc back at {a}, acting as incident commander."],
            "a-frza", t,
        ).format(b=a["by"], a=a["at"])

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        s = tick.surface
        fields: dict[str, Any] = {
            "time": clock(A_BASE, z["minute"]),
            "incident": self._incident_line(z, t),
            "checkout_last_minute": self._checkout_line(z, t),
            "clean_streak": self._streak_line(z, t),
        }
        fields["traces"] = self._traces_line(z, t)
        fields["cpu"] = self._cpu_line(z, t)
        fields["deploys"] = self._deploys_line(z, t)
        fields["findings"] = self._findings_line(z, t)
        fields["in_progress"] = self._work_line(z, t)
        fields["command"] = self._command_line(z, t)
        fields["change_freeze"] = self._freeze_line(z, t)
        order = pick(
            [
                ["time", "incident", "checkout_last_minute", "clean_streak", "traces", "cpu", "deploys", "findings", "in_progress", "command", "change_freeze"],
                ["time", "incident", "command", "change_freeze", "in_progress", "checkout_last_minute", "clean_streak", "traces", "cpu", "findings", "deploys"],
            ],
            "a-order",
            t,
        )
        state = {k: fields[k] for k in order if k in fields}
        state["latest_log"] = s["log"] or pick(["No new alert or log line this minute.", "Alert feed: nothing new this minute."], "a-log", t)
        state["chat"] = s["chat"]
        if variant == "lexical_decoy":
            state["other_channels"] = self._decoy_line(z, t)
        return state

    def _decoy_line(self, z: dict[str, Any], t: int) -> str:
        """Unrelated chatter that borrows a wrong action's wording, never the gold action's."""
        gold = self.policy(z)["action"]
        borrowed = A_DECOY_TEMPTS.get(t) or pick([a for a in A_OPTIONS if a != gold], "a-decoy-action", t)
        assert borrowed != gold, (t, borrowed)
        return A_DECOY_NAMED.get(t) or pick(A_DECOYS[borrowed], "a-decoy", t)

    _LAST_P: ClassVar[dict[str, str]] = {
        "pricing-svc rollback to v4.11 finished at 20:30": "pricing-svc finished reverting to build 4.11 at 20:30",
        "cart-cache scale-out from 4 to 6 nodes finished at 20:46": "cart-cache grew from four to six nodes, done at 20:46",
        "the cart-cache autoscaler removed 2 nodes at 21:07 (6 -> 4)": "at 21:07 the cart-cache autoscaler took it from six nodes back to four",
        "cart-cache scale-out from 4 to 6 nodes finished at 21:17": "cart-cache grew from four to six nodes again, done at 21:17",
    }

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        s = tick.surface
        cpu = z["cpu"]
        inc = z["incident"]
        # The narrative deliberately runs in a different order from the canonical
        # fields: the moment first, then command, freeze, work, findings and
        # releases, and the numbers last.
        parts = [f"{clock(A_BASE, z['minute'])} in the incident room: {s['gist']}."]
        ic = z["ic"]
        if ic:
            parts.append(pick(["{n} has led the incident as commander from {s}.", "{n} has been running the incident as its commander since {s}."], "p-ic", t).format(n=ic["name"], s=ic["since"]))
        else:
            parts.append(pick(["Nobody is acting as incident commander.", "No one is in charge as incident commander."], "p-ic0", t))
        if z["freeze"]:
            a = z["approved"]
            if not a:
                sign = pick(["no such sign-off is on record.", "no sign-off for any revert has been recorded."], "p-frz0", t)
            elif a["pre"]:
                sign = pick(A_PRE_APPROVAL_TEXT_P, "p-frzp", t).format(b=a["by"], a=a["at"])
            else:
                sign = pick(
                    ["on record is {b}'s sign-off for the pricing revert, given as incident commander at {a}.", "{b}'s sign-off on the pricing revert, given at {a} in her role as incident commander, is on record."],
                    "p-frza", t,
                ).format(b=a["by"], a=a["at"])
            parts.append("A change freeze for the bundle-discount launch is on: capacity increases were cleared in advance in the launch runbook, but any revert could take the advertised discounts away and needs the incident commander's sign-off; " + sign)
        else:
            parts.append("There is no change freeze.")
        c = z["change"]
        if c is not None and c["kind"] == "rollback":
            parts.append(f"A revert of pricing-svc to build 4.11 began at {c['started']} and is still going ({c['pods']} of its 6 pods switched).")
        elif c is not None:
            parts.append(f"Two extra cart-cache nodes were requested at {c['started']} and are still being added ({c['detail']}).")
        else:
            text = pick(["Nothing is being reverted or resized right now.", "No revert or capacity increase is running at the moment."], "p-work0", t)
            if z["last_change"]:
                text += f" Latest change: {self._LAST_P[z['last_change']]}."
            parts.append(text)
        if z["findings"]:
            parts.append("Reported so far: " + "; ".join(f"at {f['time']}, {f['text_p']}" for f in z["findings"]) + ".")
        else:
            parts.append(pick(["No one has reported any findings.", "Nobody has written up what they found yet."], "p-find0", t))
        if z["versions"]["pricing-svc"] == "v4.12" and c is not None and c["kind"] == "rollback":
            rel = f"pricing-svc received build 4.12 at 19:51, and the revert has so far moved {c['pods']} of its 6 pods back to 4.11 while the rest still run 4.12"
        elif z["versions"]["pricing-svc"] == "v4.12":
            rel = "pricing-svc received build 4.12 at 19:51 and still runs it"
        else:
            rel = "pricing-svc's build 4.12 (shipped 19:51) was reverted to 4.11 at 20:30 and runs nowhere now"
        parts.append(f"As for releases, {rel}; checkout-api's build 88 went out yesterday at 16:20; cart-cache had a settings tweak on Monday; orders-db has had no release this week.")
        if inc["status"] == "none":
            parts.append("Nobody has raised an incident tonight.")
        elif inc["status"] == "closed":
            parts.append(f"The slow-checkout incident, INC-2291, was shut at {inc['closed']}, so there is no open incident.")
        elif "reopened" in inc:
            parts.append(f"INC-2291, the slow-checkout incident first raised at {inc['opened']}, was shut at {inc['closed']}, brought back at {inc['reopened']} and is open again.")
        else:
            parts.append(pick(["INC-2291 about slow checkout was raised at {o} and remains open.", "An incident about slow checkout (INC-2291) has been open from {o}."], "p-inc", t).format(o=inc["opened"]))
        parts.append(
            pick(
                [
                    "In the live shop over the past minute, the 95th-percentile checkout took {p:,} ms against the 500 ms target, and {e}% of checkout requests failed against the 1.0% ceiling.",
                    "Live checkout, past minute: {e}% of requests failed (ceiling 1.0%), and the 95th-percentile time came to {p:,} ms (target 500 ms).",
                ],
                "p-met",
                t,
            ).format(p=z["p95_ms"], e=z["err_pct"])
        )
        # As in the fields, no run is counted while no incident is open (t0-7 and t62-66).
        if inc["status"] == "none":
            parts.append(pick(
                ["With no incident raised, nobody is counting minutes with both targets met.",
                 "No incident has been raised, so no run of minutes with both targets met is being counted."],
                "p-streakn", t,
            ))
        elif inc["status"] == "closed":
            parts.append(pick(
                ["With INC-2291 shut at {c} and no incident open, nobody is counting minutes with both targets met.",
                 "No incident is open after INC-2291 was shut at {c}, so no run of minutes with both targets met is being counted."],
                "p-streakc", t,
            ).format(c=inc["closed"]))
        elif z["met_since"] is not None:
            n = z["minute"] - z["met_since"]
            parts.append(pick(
                ["Both targets have held without a break from {s} onward, {m} so far.",
                 "Since {s}, both targets have been met every minute without a break: {m} so far."],
                "p-streak", t,
            ).format(s=clock(A_BASE, z["met_since"]), m=plural(n, "minute")))
        else:
            assert self._breached(z), z["minute"]
            parts.append(pick(
                ["There is no unbroken run of both targets being met, since at least one was missed in the past minute.",
                 "No run of minutes with both targets met is going: the past minute missed at least one."],
                "p-streak0", t,
            ))
        if z["hot"] is None:
            parts.append(pick(["Tracing shows nothing slower than normal.", "Request tracing does not single out any service."], "p-tr0", t))
        else:
            parts.append(
                f"Request tracing pins the added time on {z['hot']}, whose {A_SPAN_P[z['hot']]} takes {z['hot_ms']} ms at the 95th percentile (normally about {A_SPAN[z['hot']][1]})."
            )
        parts.append(
            f"Processor load: orders-db {cpu['orders-db']}%, cart-cache {cpu['cart-cache']}% over its {z['nodes']} nodes, "
            f"pricing-svc {cpu['pricing-svc']}%, checkout-api {cpu['checkout-api']}%."
        )
        return " ".join(parts)


# ===========================================================================
# Scenario B - payment-database failover across teams (hard)
# ===========================================================================

B_BASE = 2 * 60 + 5  # t=0 is 02:05; one tick is one minute
B_HOSTS = ["pay-db-01", "pay-db-02", "pay-db-03"]
B_ZONE = {"pay-db-01": "zone a", "pay-db-02": "zone b", "pay-db-03": "zone c"}
B_WRITERS = ["payments-api", "ledger-batch", "other"]  # fixed display order

B_ROLE = (
    "You support the incident commander during a night-time payments incident. Card payments are stored in a "
    "database cluster of three hosts, pay-db-01, pay-db-02 and pay-db-03: one is the primary, which takes all "
    "writes, and the others are read-only replicas. Each state is the incident board at one minute (the clock "
    "is on the first line): who holds command and when their shift ends, the primary and its write latency, "
    "each component's share of writes, the payment failure rate, the latest replica-lag reading and when it was "
    "taken, the database on-call's status, the status page, any failover under way, and the newest log and chat "
    "lines."
)
B_POLICY = [
    "1. If a failover is running (started and not yet finished): keep watching; target: none.",
    "2. Otherwise, if the primary is unreachable and the database on-call has not acknowledged any page during this incident (an acknowledged earlier page in this incident counts, whatever it was about; a page still waiting for acknowledgement does not): page the database on-call, again if a page already sent is still unacknowledged, even one sent this same minute; target: the unreachable primary host.",
    "3. Otherwise, if the primary is unreachable: fail over to a replica whose latest lag reading was taken 5 or fewer minutes ago and shows less than 10 s of lag (if both replicas qualify, the one with less lag); target: that replica. If no replica qualifies, run a replication-lag check; target: none.",
    "4. Otherwise, if the current commander's shift has ended (the clock is at or past the shift-end time) and the incoming commander is in the channel right now: hand command to the incoming commander; target: none.",
    "5. Otherwise, if 2% or more of payment attempts are failing and no status-page update for this incident has been posted in the last 30 minutes (none at all, or the latest is 30 or more minutes old): post a status-page update; target: none.",
    "6. Otherwise, if the primary's write latency is above 200 ms: throttle writes from the component with the largest share of writes; target: that component.",
    "7. Otherwise, if under 0.5% of payment attempts have been failing continuously for 15 minutes or longer: close the incident; target: none.",
    "8. Otherwise: keep watching; target: none.",
]
B_SEVERITY = (
    "Severity describes the situation right now. A database node accepts writes only if it is a reachable "
    "primary: replicas are read-only, and a replica being promoted takes no writes until its failover has "
    "finished. The payment failure rate is the share of payment attempts that failed in the last minute."
)
B_ROLE_P = (
    "You are the aide to whoever is running a payments outage overnight. Card transactions live in a three-machine "
    "database group (pay-db-01, pay-db-02, pay-db-03); exactly one machine is the writer that accepts every write, "
    "while the others are read-only copies that follow it. Each snapshot describes one minute and opens with the "
    "time: who is in charge and when their duty ends, which machine is the writer and how slow its writes are, how "
    "the write traffic splits between components, how many payments fail, the most recent measurement of how far "
    "each copy trails and when it was measured, what the on-call database engineer is doing, the public status "
    "site, any switch-over in progress, and the newest system line and message."
)
B_POLICY_P = [
    "1. While a switch-over to a copy is in progress (begun, not complete): stay on the dashboards; no target.",
    "2. If not, and the writer machine cannot be reached while the on-call database engineer has not confirmed any page at all during this outage (confirming an earlier page in this outage counts, whatever that page concerned; a page nobody has confirmed yet does not): call in the on-call database engineer, once more if a page already sent is still unconfirmed, even one sent in this same minute; target: the writer machine that cannot be reached.",
    "3. If not, and the writer machine cannot be reached: promote a copy whose newest trail measurement is at most 5 minutes old and under 10 s (if both copies qualify, the one trailing less); target: that copy. If neither qualifies, measure how far the copies trail; no target.",
    "4. If not, and the person in charge has reached the end of their duty (the time shown is that time or later) while their successor is present in the channel at this moment: pass the commander role to the successor; no target.",
    "5. If not, and at least 2% of payments are failing while the public status site has had no notice about this outage in the last 30 minutes (never, or the newest is 30 minutes old or older): publish a notice; no target.",
    "6. If not, and writes to the writer machine take more than 200 ms: rate-limit the component producing the biggest share of writes; target: that component.",
    "7. If not, and fewer than 0.5% of payments have failed without interruption for 15 minutes or more: end the incident; no target.",
    "8. In any other case: stay on the dashboards; no target.",
]
B_SEVERITY_P = (
    "Grade how serious things are at this moment. Only a reachable writer machine accepts writes: copies are "
    "read-only, and a copy mid-promotion accepts nothing until the switch-over is complete. The failure rate "
    "means the share of payment attempts that failed during the last minute."
)

B_ACTIONS = {
    "watch": {"category": "observe", "action": "Keep watching the incident without starting anything new."},
    "lag_check": {"category": "diagnose", "action": "Run a replication-lag check against both replicas."},
    "page_dba": {"category": "diagnose", "action": "Page the database on-call about the target host."},
    "failover": {"category": "mitigate", "action": "Fail over by promoting the target replica to primary."},
    "throttle": {"category": "mitigate", "action": "Throttle the writes coming from the target component."},
    "status": {"category": "communicate", "action": "Post a customer-facing update on the status page."},
    "handoff": {"category": "communicate", "action": "Hand incident command to the incoming commander."},
    "close": {"category": "communicate", "action": "Close the incident and stand the responders down."},
}
B_ACTIONS_P = {
    "watch": {"category": "monitor", "action": "Stay on the dashboards and hold off on any new step."},
    "lag_check": {"category": "investigate", "action": "Measure how far each read-only copy trails the writer."},
    "page_dba": {"category": "investigate", "action": "Call in the on-call database engineer for the named machine."},
    "failover": {"category": "remediate", "action": "Make the named copy the new writer machine."},
    "throttle": {"category": "remediate", "action": "Rate-limit the write traffic of the named component."},
    "status": {"category": "inform", "action": "Publish a fresh notice for customers on the public status site."},
    "handoff": {"category": "inform", "action": "Pass the commander role to the person taking over."},
    "close": {"category": "inform", "action": "End the incident and release everyone who is responding."},
}
B_TARGETS = {
    "pay-db-01": "pay-db-01 (database host, zone a)",
    "pay-db-02": "pay-db-02 (database host, zone b)",
    "pay-db-03": "pay-db-03 (database host, zone c)",
    "payments-api": "payments-api (card payment service)",
    "ledger-batch": "ledger-batch (nightly settlement job)",
    "none": "None: the chosen action has no target",
}
B_TARGETS_P = {
    "pay-db-01": "pay-db-01, the database machine in zone a",
    "pay-db-02": "pay-db-02, the database machine in zone b",
    "pay-db-03": "pay-db-03, the database machine in zone c",
    "payments-api": "payments-api, which takes card payments",
    "ledger-batch": "ledger-batch, the overnight settlement writer",
    "none": "No target; the move is not aimed at a component",
}
B_LEVELS = [
    "SEV3: a database node accepts writes and fewer than 2% of payment attempts fail.",
    "SEV2: a database node accepts writes and 2% or more, but fewer than 10%, of payment attempts fail.",
    "SEV1: no database node accepts writes, or 10% or more of payment attempts fail.",
]
B_LEVELS_P = [
    "SEV3 - some machine is accepting writes and under 2% of payments fail.",
    "SEV2 - some machine is accepting writes and from 2% up to just under 10% of payments fail.",
    "SEV1 - no machine is accepting writes, or at least 10% of payments fail.",
]

# Surface content per tick: (log line or "", chat line, third-person gist).
B_SCRIPT: list[tuple[str, str, str]] = [
    # t0-6 02:05-02:11: slow writes, primary up, below every threshold
    ("", "Dana: INC-7730 is open for slow payment writes; I'm watching pay-db-01.", "Dana, in charge, says the incident is open for slow payment writes and she is watching the writer"),
    ("", "Priti (finance): the ledger-batch settlement run started at 02:00 as scheduled.", "Priti from finance confirms the settlement job began on schedule at 02:00"),
    ("", "Jonah (payments): payments-api p99 is up a little, nothing alarming.", "Jonah from payments sees the payment service a little slower, nothing alarming"),
    ("WARN pay-db-03 replication lag 12 s (warning threshold 10 s)", "Jonah: lag warning on pay-db-03, should we check the replicas?", "a warning says pay-db-03 trails by 12 seconds and Jonah wonders about checking the copies"),
    ("", "Kofi (support): no merchant complaints so far.", "support has no merchant complaints yet"),
    ("", "Dana: write latency is creeping toward 200.", "Dana sees write times creeping toward 200 ms"),
    ("INFO lag probe: pay-db-02 2 s, pay-db-03 7 s", "Priti: the batch is 40% through the settlement files.", "a routine probe finds both copies close behind, and the settlement job is 40% through its files"),
    # t7-13: write latency above 200 ms, ledger-batch the biggest writer
    ("", "Jonah: payments-api timeouts creeping up.", "Jonah reports timeouts creeping up in the payment service"),
    ("", "Dana: ledger-batch has overtaken payments-api as the biggest writer.", "Dana observes that the settlement job now writes more than the payment service"),
    ("", "Priti: the batch has to finish before the 06:00 bank cut-off.", "Priti stresses the batch must finish before the 06:00 bank cut-off"),
    ("", "Jonah: payments-api is the one timing out, let's throttle payments-api.", "Jonah wants to rein in the payment service because that is where the timeouts show"),
    ("INFO lag probe: pay-db-02 3 s, pay-db-03 5 s", "Kofi: first merchant ticket: 'card payments failing intermittently'.", "a routine probe finds both copies close behind, and support logs the first merchant ticket about intermittent card failures"),
    ("", "Dana: failures nearly at 2%.", "Dana says failures are nearly at 2%"),
    ("", "Priti: the settlement files are bigger than usual, it's month-end.", "Priti explains the files are larger than usual at month-end"),
    # t14-17: failures over 2%, nothing on the status page
    ("", "Kofi: three more merchants reporting declined cards.", "three more merchants report declined cards"),
    ("", "Jonah: the payments-api error budget is burning fast.", "Jonah warns the payment service's error budget is burning fast"),
    ("INFO lag probe: pay-db-02 3 s, pay-db-03 6 s", "Dana: failures around 3% now.", "a routine probe finds both copies close behind, and Dana puts failures around 3%"),
    ("", "Kofi: merchants are asking whether there is an outage notice.", "merchants are asking support whether there is an outage notice"),
    # t18-22: status posted, still slow writes
    ("statuspage: incident posted 'Some card payments are failing; we are investigating.'", "Ana (comms): status page is up.", "Ana from comms has published a public notice saying some card payments fail"),
    ("", "Priti: found the ledger-batch rate setting, waiting on my lead's OK.", "Priti has found the settlement job's rate setting and awaits her lead's approval"),
    ("CRIT pay-db-01 disk I/O utilisation 98%", "Jonah: if 01 keeps choking we should just fail over.", "the writer's disk is 98% busy and Jonah suggests switching to a copy"),
    ("INFO lag probe: pay-db-02 3 s, pay-db-03 12 s", "Dana: write latency is above 400 ms.", "a routine probe finds pay-db-02 close behind and pay-db-03 trailing under the batch load, and Dana reads write times above 400 ms"),
    ("", "Priti: my lead still isn't answering.", "Priti's lead still has not answered"),
    # t23-26: primary unreachable, database on-call not acknowledged
    ("CRIT pay-db-01 health check failed: connection timed out", "Jonah: payments-api can't get a write connection at all.", "the writer has stopped answering health checks and the payment service cannot write at all"),
    ("PAGE sent to database on-call Leo Brandt (automatic)", "Dana: pay-db-01 is not answering.", "an automatic page has gone to Leo, the on-call database engineer, and Dana confirms the writer is silent"),
    ("", "Kofi: merchants report card payments failing left and right.", "merchants report card payments failing left and right"),
    ("", "Dana: still nothing back from Leo.", "Dana still has no answer from Leo"),
    # t27-30: on-call engaged, last lag reading is old
    ("PAGE acknowledged by Leo Brandt", "Leo (database on-call): here, logging in to the console.", "Leo has confirmed the page and is logging in"),
    ("", "Leo: pay-db-01's storage controller is hung; it won't come back quickly.", "Leo says the writer's storage controller is hung and will not return soon"),
    ("", "Jonah: 02 was only 3 seconds behind at 02:26, just promote it.", "Jonah argues pay-db-02 was only three seconds behind at 02:26 and should simply be promoted"),
    ("", "Dana: Leo, what do you need from us?", "Dana asks Leo what he needs"),
    # t31-34: fresh lag reading, both replicas under 10 s
    ("INFO lag probe (manual, leo): pay-db-02 4 s, pay-db-03 7 s behind pay-db-01's last write", "Leo: fresh lag numbers are in.", "Leo has fresh trail measurements from a manual probe"),
    ("", "Jonah: 03 was still replaying batch writes when 01 died; it's at 7 s now.", "Jonah says pay-db-03 was still replaying batch writes when the writer died and now trails by seven seconds"),
    ("", "Priti: ledger-batch paused itself when its writes started failing.", "Priti says the settlement job paused itself when its writes failed"),
    ("", "Dana: Leo, you have the runbook open?", "Dana checks that Leo has the runbook open"),
    # t35-44: failover running
    ("failover: promote pay-db-02 started (step 1/5: fence pay-db-01)", "Leo: starting the promotion of pay-db-02.", "Leo has begun promoting pay-db-02, first fencing the old writer"),
    ("statuspage: update 'Card payments are down; recovery is in progress.'", "Ana: status page updated: payments down, recovery under way.", "Ana has updated the public notice to say card payments are down and recovery is under way"),
    ("failover: step 2/5 replaying WAL on pay-db-02", "Leo: replaying the last WAL segments.", "Leo is replaying the final log segments on pay-db-02"),
    ("", "Jonah: payments-api is buffering authorisations in its outbox.", "Jonah says the payment service is buffering authorisations in its outbox"),
    ("", "Kofi: a large merchant is on the phone, looping in their account manager.", "a large merchant has phoned support, who are looping in the account manager"),
    ("", "Kofi: can we update the status page? merchants keep asking.", "support wants the public notice refreshed because merchants keep asking"),
    ("failover: step 3/5 promote", "Leo: promotion running.", "Leo says the promotion itself is running"),
    ("", "Dana: Marcus, join the channel when you can.", "Dana asks Marcus to join the channel when he can"),
    ("failover: step 4/5 repoint connection pooler", "Leo: repointing the connection pooler.", "Leo is repointing the connection pooler"),
    ("failover: step 5/5 verify writes", "Leo: verifying writes.", "Leo is checking that writes work"),
    # t45-58: new primary, retry replay floods writes; Marcus reads in early, drops off to drive in; Dana's shift ends at 03:00
    ("failover: step 5/5 done; pooler repointed, writes verified on pay-db-02", "Leo: pay-db-02 is primary and taking writes.", "Leo announces pay-db-02 is now the writer and accepts writes"),
    ("", "Jonah: outbox replay started, flushing the buffered payments.", "Jonah has started replaying the buffered payments"),
    ("", "Marcus (incoming commander): joined from my phone, reading back through the channel.", "Marcus, next in charge, has joined from his phone and is reading back"),
    ("", "Dana: write latency on 02 is about 270.", "Dana sees write times on the new writer around 270 ms"),
    ("", "Kofi: some payments are going through again.", "support hears that some payments go through again"),
    ("", "Dana: Marcus, I'll hand over when my shift ends at 03:00.", "Dana tells Marcus she will hand over when her duty ends at 03:00"),
    ("", "Jonah: 40,000 buffered payments still to replay.", "Jonah says 40,000 buffered payments remain to replay"),
    ("", "Marcus: dropping off while I drive in; back on as soon as I'm parked.", "Marcus leaves the channel to drive in and will be back once he has parked"),
    ("", "Leo: pay-db-01 is fenced; it can't take writes even if it comes back.", "Leo confirms the old writer is fenced and cannot take writes"),
    ("", "Jonah: the replay rate-limit change is building.", "Jonah's change to rate-limit the replay is building"),
    ("", "Dana: my shift just ended; Marcus is still driving in.", "Dana says her duty has just finished while Marcus is still driving in"),
    ("", "Ana: the next status update would be due around 03:11.", "Ana notes the next public notice would be due around 03:11"),
    ("", "Jonah: the replay limiter build passed its tests.", "Jonah's replay limiter has passed its tests"),
    ("", "Kofi: merchant tickets are slowing down.", "merchant tickets are slowing down"),
    # t59-61: Marcus is back in the channel, handover due
    ("", "Marcus: back in the channel, parked and ready.", "Marcus is back in the channel, parked and ready"),
    ("deploy: payments-api replay limiter enabled", "Jonah: replay limiter is live.", "Jonah has switched on the replay limiter"),
    ("", "Marcus: ready when you are, Dana.", "Marcus tells Dana he is ready when she is"),
    # t62-89: Marcus in command, recovery, long quiet tail
    ("", "Dana: Marcus, you have command. Marcus: I have command.", "Dana has passed the lead to Marcus, who confirms"),
    ("", "Marcus: thanks, Dana. Leo, what's the plan for pay-db-01?", "Marcus thanks Dana and asks Leo about the old writer"),
    ("INFO pay-db-01 health check passed", "Jonah: 01 is back! Should we fail back to it?", "the old writer answers health checks again and Jonah suggests moving back to it"),
    ("", "Jonah: it has the most memory of the three, it should be primary.", "Jonah insists the old writer has the most memory and should lead"),
    ("statuspage: update 'Payments are recovering; we are monitoring.'", "Ana: status page now says payments are recovering.", "Ana updates the public notice to say payments are recovering"),
    ("", "Leo: rebuild 01 as a replica once the storage vendor replies.", "Leo plans to rebuild the old writer as a copy after the storage vendor replies"),
    ("", "Dana: signing off, my notes are in the doc.", "Dana signs off, leaving notes in the document"),
    ("", "Jonah: replay 60% done, latency fine.", "Jonah says the replay is 60% done"),
    ("", "Priti: can ledger-batch resume? The bank cut-off is 06:00. Marcus: yes, at half rate, and we'll watch latency.", "Priti asks whether the settlement job can resume and Marcus allows it at half rate"),
    ("", "Priti: ledger-batch resumed at half rate.", "the settlement job is running again at half rate"),
    ("", "Kofi: all but two merchant tickets closed.", "support has closed all but two merchant tickets"),
    ("", "Leo: pay-db-03 lag down to 2 s.", "Leo says pay-db-03 trails by two seconds"),
    ("", "Ana: should the status page say 'monitoring' now?", "Ana asks whether the notice should now say monitoring"),
    ("WARN acquirer gateway timeouts spiking (one acquirer)", "Jonah: burst of gateway timeouts from one acquirer.", "one acquirer has produced a burst of gateway timeouts"),
    ("", "Jonah: the acquirer burst is over.", "Jonah says the acquirer burst is over"),
    ("", "Jonah: replay finished, outbox is empty.", "the replay has finished and the outbox is empty"),
    ("", "Marcus: write latency looks fine on 02.", "Marcus is happy with write times on the new writer"),
    ("", "Leo: vendor ticket open for the pay-db-01 controller.", "Leo has opened a vendor ticket for the old writer's controller"),
    ("", "Priti: settlement files 80% through; they'll be done well before 04:00.", "the settlement job is 80% through and should be done well before 04:00"),
    ("", "Kofi: last two merchant tickets closed.", "support has closed the last merchant tickets"),
    ("", "Jonah: feels like nothing has failed for 20 minutes, can we close?", "Jonah feels nothing has failed for about 20 minutes and wants to end it"),
    ("statuspage: update 'A fix is in place; we are monitoring.'", "Ana: posted 'monitoring'.", "Ana posts a monitoring notice"),
    ("", "Priti: nine-tenths of the settlement files are posted.", "nine-tenths of the settlement files are posted"),
    ("", "Marcus: pay-db-03 is keeping up with 02.", "Marcus sees pay-db-03 keeping up"),
    ("INFO lag probe: pay-db-03 1 s", "Leo: pay-db-03 steady at about 1 s behind.", "Leo says pay-db-03 trails steadily by about a second"),
    ("", "Priti: settlement files done, well ahead of the cut-off.", "the settlement job has finished well before the cut-off"),
    ("", "Leo: connection pooler healthy, 212 connections.", "Leo reports the connection pooler healthy"),
    ("", "Leo: pay-db-01 rebuild scheduled for 09:00.", "Leo schedules the rebuild for 09:00"),
    # t90-99: fifteen clean minutes
    ("", "Kofi: support volume back to normal.", "support volume is back to normal"),
    ("", "Jonah: payments-api error rate is flat.", "the payment service's error rate is flat"),
    ("", "Marcus: summary drafted in the doc.", "Marcus has drafted a summary"),
    ("", "Marcus: Dana agreed to own the postmortem.", "Marcus says Dana will own the postmortem"),
    ("", "Leo: I'll stay on until the storage vendor replies.", "Leo will stay on until the storage vendor replies"),
    ("", "Jonah: going to bed unless you need me.", "Jonah is going to bed unless needed"),
    ("", "Kofi: the large merchant from 02:44 confirms their payments are flowing.", "the large merchant who phoned at 02:44 confirms their payments are flowing"),
    ("", "Ana: drafting the closing text for the status page, for Marcus to approve.", "Ana is drafting closing text for the public notice, for Marcus to approve"),
    ("", "Leo: pay-db-02 CPU 35%.", "the new writer's processors are 35% busy"),
    ("", "Marcus: thanks, everyone; Dana gets the timeline in the morning.", "Marcus thanks everyone and says Dana gets the timeline in the morning"),
]
assert len(B_SCRIPT) == 100

# Primary write latency p95 (ms); None while no primary is reachable.
B_WRITE_MS: list[int | None] = (
    [120, 135, 150, 165, 178, 188, 196]  # t0-6
    + [214, 236, 262, 288, 305, 318, 322]  # t7-13
    + [331, 344, 356, 368]  # t14-17
    + [372, 385, 398, 410, 420]  # t18-22
    + [None] * 22  # t23-44
    + [280, 276, 272, 268, 262, 256, 250, 246, 240, 236, 232, 228, 221, 214, 209, 205]  # t45-60
    + [176]  # t61: replay limiter effective
    + [168, 160, 152, 147, 143, 140, 138, 136, 135]  # t62-70
    + [178, 188, 194, 185]  # t71-74: batch resumed at half rate
    + [170, 166, 162, 160, 158, 157, 155, 156, 154, 153, 152, 150, 151, 149, 150, 148, 147, 149, 146, 145, 147, 140, 132, 128, 126]  # t75-99
)
# Share of payment attempts failing in the last minute (%).
B_FAIL: list[float] = (
    [0.6, 0.7, 0.6, 0.8, 0.7, 0.8, 0.9]
    + [1.1, 1.2, 1.4, 1.5, 1.7, 1.9, 1.9]
    + [2.0, 2.6, 3.0, 3.2]  # t14 sits exactly on rule 5's 2% line
    + [3.3, 3.5, 3.6, 3.8, 4.1]
    + [18, 24, 31, 36, 38, 39, 40, 41, 41, 40, 39, 38, 37, 30, 22, 12, 8.4, 7.9, 7.5, 7.2, 7.0, 6.8]
    + [3.6, 3.4, 3.2, 3.0, 2.9, 2.8, 2.7, 2.6, 2.5, 2.5, 2.4, 2.4, 2.3, 2.3, 2.2, 2.2, 2.1]  # t45-61
    + [1.4, 0.9, 0.7, 0.6]  # t62-65
    + [0.4, 0.3, 0.3, 0.4, 0.3, 0.2, 0.3, 0.3, 0.2]  # t66-74
    + [0.6]  # t75: acquirer burst
    + [0.3, 0.2, 0.3, 0.2, 0.2, 0.3, 0.2, 0.3, 0.2, 0.2, 0.3, 0.2, 0.2, 0.3, 0.2, 0.2, 0.3, 0.2, 0.2, 0.2, 0.3, 0.2, 0.2, 0.2]
)
# ledger-batch share of writes before the outage; payments-api is larger until t7.
B_LEDGER_SHARE = [40, 42, 43, 44, 45, 46, 47, 50, 52, 55, 58, 61, 64, 66, 68, 70, 71, 72, 72, 73, 73, 74, 74]  # t0-22
B_REPLAY_SHARE = [81, 83, 84, 85, 86, 86, 85, 84, 84, 83, 83, 82, 82, 81, 80, 80, 79]  # t45-61 payments-api
B_FAILOVER_STEP = [1, 1, 2, 2, 2, 2, 3, 3, 4, 5]  # t35-44
# Latest replica-lag reading as (tick taken, {replica: seconds}).
B_LAG = (
    [(0, {"pay-db-02": 2, "pay-db-03": 4})] * 3
    + [(3, {"pay-db-02": 2, "pay-db-03": 12})] * 3
    + [(6, {"pay-db-02": 2, "pay-db-03": 7})] * 5
    + [(11, {"pay-db-02": 3, "pay-db-03": 5})] * 5
    + [(16, {"pay-db-02": 3, "pay-db-03": 6})] * 5
    + [(21, {"pay-db-02": 3, "pay-db-03": 12})] * 10
    + [(31, {"pay-db-02": 4, "pay-db-03": 7})] * 14
    + [(45, {"pay-db-03": 11})] * 6
    + [(51, {"pay-db-03": 5})] * 5
    + [(56, {"pay-db-03": 3})] * 5
    + [(61, {"pay-db-03": 2})] * 10
    + [(71, {"pay-db-03": 2})] * 15
    + [(86, {"pay-db-03": 1})] * 14
)
assert len(B_WRITE_MS) == len(B_FAIL) == len(B_LAG) == 100
B_OUTAGE = 23  # pay-db-01 stops answering at 02:28
B_BATCH_P = {"paused": "on hold", "finished": "done for the night", "half rate": "running at half speed"}

# Unrelated chatter for the lexical-decoy register, keyed by the action whose wording
# it borrows; a tick never borrows its own gold action.
B_DECOYS = {
    "watch": [
        "#facilities: the night guard will keep watching the car-park cameras without starting anything new.",
        "#design: the team will keep watching the survey results without starting anything new this week.",
    ],
    "lag_check": [
        "#video: the streaming crew will run a lag check against both replicas of the town-hall video feed.",
        "#gaming-club: someone proposes a replication lag check against both replicas of the club's game server.",
    ],
    "page_dba": [
        "#facilities: the night guard will page the building's on-call electrician about the flickering lobby lights.",
        "#events: the planners paged the venue's on-call technician because the host's microphone keeps cutting out.",
    ],
    "failover": [
        "#it-help: the office Wi-Fi will fail over tonight by promoting the spare router to primary.",
        "#it-help: the badge-reader server will fail over on Saturday, promoting its spare unit to primary.",
    ],
    "throttle": [
        "#ci: the build admins will throttle the writes coming from the flaky docs build, a test component.",
        "#ci: the artifact store will throttle writes coming from the target component of the nightly UI tests.",
    ],
    "status": [
        "#vendors: the email provider posted a customer-facing update on its status page about the newsletter tool.",
        "#office: the canteen's status page has an update about the new coffee beans.",
    ],
    "handoff": [
        "#book-club: the organiser will hand command of the snack table to the incoming organiser next month.",
        "#football: the team captain hands command to the incoming captain after the season.",
    ],
    "close": [
        "#office: the manager will close the stationery order and stand the volunteers down after lunch.",
        "#charity: the bake sale will close at noon and stand the helpers down.",
    ],
}
# On distractor ticks the decoy borrows the wrong action the distractor tempts.
B_DECOY_TEMPTS = {3: "lag_check", 10: "handoff", 20: "failover", 29: "failover", 50: "handoff", 55: "handoff", 56: "handoff", 57: "handoff", 58: "handoff", 64: "failover", 65: "failover", 82: "close"}
# Where a distractor tempts a wrong target rather than a wrong action (t10: Jonah wants to
# throttle payments-api while gold throttles ledger-batch), the decoy names that target in an
# unrelated context and borrows a different wrong action.
B_DECOY_NAMED = {
    10: "#hackathon: the team behind last year's toy payments-api, a pretend card payment service, will hand command of their demo booth to the incoming team.",
}


class PaymentDbFailover(Scenario):
    family = FAMILY
    scenario_id = "incident_b"
    title = "Command decisions during a payment-database failover"
    tier = "hard"
    difficulty_features = [
        "three_questions_per_decision",
        "categorised_action_options",
        "eight_action_options",
        "six_target_options",
        "severity_score",
        "eight_rule_priority_policy",
        "stale_reading_arithmetic",
        "implicit_write_availability",
        "shift_end_against_clock",
        "commander_shift_handoff",
    ]
    decision_structures = ["maintain", "wait", "escalate", "recover", "handoff", "terminate", "resolve-conflict"]
    deadline_steps = 2

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            base = {"role": B_ROLE_P, "rules": B_POLICY_P}
            q_action = "Go down the rules and take the first that fits this minute. What is the next move?"
            q_target = "Go down the rules and take the first that fits this minute. Which machine or component is that move aimed at, if any?"
            sev = {"role": B_ROLE_P, "grading": B_SEVERITY_P, "question": "Which grade fits the outage at this moment?"}
            actions, targets, levels = B_ACTIONS_P, B_TARGETS_P, B_LEVELS_P
        else:
            base = {"role": B_ROLE, "policy": B_POLICY}
            q_action = "Apply the first rule that matches the current state. Which action should be taken now?"
            q_target = "Apply the first rule that matches the current state. Which host or component, if any, is the target of that action?"
            sev = {"role": B_ROLE, "severity": B_SEVERITY, "question": "What is the incident's severity right now?"}
            actions, targets, levels = B_ACTIONS, B_TARGETS, B_LEVELS
        return [
            Choice("action", {**base, "question": q_action}, copy.deepcopy(actions)),
            Choice("target", {**base, "question": q_target}, dict(targets)),
            Score("severity", sev, list(levels)),
        ]

    # ------------------------------------------------------------------ latent
    @staticmethod
    def _latent_at(t: int) -> dict[str, Any]:
        if t < 23:
            ledger = B_LEDGER_SHARE[t]
            other = 2 if t % 3 else 3
            writers: dict[str, int] | None = {"payments-api": 100 - ledger - other, "ledger-batch": ledger, "other": other}
            batch = "running"
        elif t < 45:
            writers, batch = None, "paused"
        elif t < 62:
            p = B_REPLAY_SHARE[t - 45]
            writers, batch = {"payments-api": p, "ledger-batch": 0, "other": 100 - p}, "paused"
        elif t < 71:
            writers, batch = {"payments-api": 90, "ledger-batch": 0, "other": 10}, "paused"
        elif t < 87:
            writers, batch = {"payments-api": 51, "ledger-batch": 45, "other": 4}, "half rate"
        else:
            writers, batch = {"payments-api": 92, "ledger-batch": 0, "other": 8}, "finished"
        if t < 23:
            dba: dict[str, Any] = {"state": "idle"}
        elif t == 23:
            dba = {"state": "not_paged"}
        elif t < 27:
            dba = {"state": "paged", "paged": "02:29"}
        else:
            dba = {"state": "acked", "paged": "02:29", "acked": "02:32"}
        if t < 35:
            failover = None
        elif t < 45:
            failover = {"state": "running", "started": "02:40", "step": B_FAILOVER_STEP[t - 35]}
        else:
            failover = {"state": "done", "at": "02:50"}
        if t < 62:
            cmd = {"name": "Dana Okafor", "shift_end": 55}
        else:
            cmd = {"name": "Marcus Webb", "shift_end": 295, "since": "03:07", "from": "Dana Okafor"}
        # Marcus reads in from his phone at 02:52, drops off at 02:57 to drive in
        # and is back in the channel at 03:04.
        if 47 <= t <= 51:
            incoming: dict[str, Any] | None = {"name": "Marcus Webb", "present": True, "since": "02:52"}
        elif 52 <= t <= 58:
            incoming = {"name": "Marcus Webb", "present": False, "left": "02:57"}
        elif 59 <= t <= 61:
            incoming = {"name": "Marcus Webb", "present": True, "since": "03:04"}
        else:
            incoming = None
        if t < 18:
            status = None
        else:
            status = {"at": max(a for a in (18, 36, 66, 83) if a <= t)}
        # clean_since is the minute the current under-0.5% streak started: the
        # first good one-minute reading at t covers minute t-1 to t.
        if 66 <= t <= 74:
            clean: int | None = 65
        elif t >= 76:
            clean = 75
        else:
            clean = None
        lag_at, lag_values = B_LAG[t]
        return {
            "minute": t,
            "primary": "pay-db-01" if t < 45 else "pay-db-02",
            "primary_up": not 23 <= t <= 44,
            "old_primary": None if t < 45 else ("fenced_down" if t < 64 else "fenced_back"),
            "write_ms": B_WRITE_MS[t],
            "writers": writers,
            "batch": batch,
            "fail_pct": B_FAIL[t],
            "clean_since": clean,
            "lag": {"at": lag_at, "values": dict(lag_values)},
            "dba": dba,
            "failover": failover,
            "cmd": cmd,
            "incoming": incoming,
            "status": status,
        }

    def _canonical(self) -> list[Tick]:
        tags = span_tags(
            {
                "distractor": [3, 10, 20, 29, 50, (55, 58), (64, 65), 82],
                "minimal_change": [7, 14, 27, 90],
                "recovery": [18, 62],
                "hold_under_activity": [(36, 39), (46, 49), (66, 69)],
                "boundary": [(59, 61), (90, 99)],
                "priority_conflict": [(14, 17), (35, 44), (59, 60)],
                "arithmetic": [(5, 6), (12, 14), (27, 31), (47, 51), (55, 59), (71, 73), (87, 90)],
                "implicit": [(39, 44), (45, 47)],
            }
        )
        notes = {
            3: "Replica lag warning while the primary is up: lag only matters when the primary is unreachable.",
            5: "Write latency 188-196 ms: still at or under 200 ms.",
            7: "Write latency crosses 200 ms; ledger-batch (50%) has just overtaken payments-api (48%).",
            10: "Suggestion to throttle payments-api, but ledger-batch has the largest share.",
            12: "Failures 1.9%: still under 2%, SEV3.",
            14: "Failures reach exactly 2%, which meets rule 5's '2% or more', with no status post: rule 5 outranks rule 6; SEV2.",
            18: "Status posted 02:23; the move returns to throttling ledger-batch (severity stays SEV2).",
            20: "Disk alert and failover talk while the primary is still reachable.",
            23: "Primary unreachable; database on-call not paged: page; no node takes writes -> SEV1.",
            27: "On-call acknowledged at 02:32; the latest lag reading (02:26) is 6 minutes old: lag check.",
            29: "Suggestion to promote pay-db-02 on the 02:26 reading, now 8 minutes old.",
            31: "Fresh reading: pay-db-02 4 s and pay-db-03 7 s both qualify; the one with less lag is pay-db-02.",
            35: "Failover running: rule 1 outranks rule 3; still no writable node.",
            39: "Failures fall below 10% while no node takes writes: still SEV1.",
            40: "Support asks for a status update while the failover runs; one was posted at 02:41.",
            45: "Failover done (pay-db-02 promoted, writes verified); payments-api replay has the largest write share and latency > 200 ms; failures 3.6% -> SEV2.",
            47: "Marcus is in the channel but Dana's shift runs to 03:00: no handoff yet.",
            50: "Dana mentions the handover while Marcus is in the channel, but her shift has not ended.",
            52: "Marcus drops off to drive in.",
            55: "Dana's shift ended at 03:00 but Marcus is not in the channel: no handoff yet; keep throttling.",
            59: "Shift over and Marcus is back in the channel: hand over (outranks throttling).",
            62: "Handed over; replay limited; failures 1.4% -> SEV3.",
            64: "Old primary answers again; the current primary is healthy, so no failover.",
            66: "First minute under 0.5% (streak from 03:10).",
            75: "Acquirer burst: 0.6% resets the under-0.5% streak.",
            82: "Claim of 20 clean minutes; the board shows 7.",
            87: "ledger-batch finished at 03:32.",
            89: "14 clean minutes.",
            90: "15 clean minutes: close the incident.",
        }
        tl = Timeline(self._latent_at(0))
        for t in range(100):
            tl.step(surface_of(B_SCRIPT[t]), tags[t], notes.get(t, ""), **self._latent_at(t))
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t7-9: write latency stays at or under 200 ms (exactly 200 at t9), then
            #     rises more gently.
            for t, ms in {7: 184, 8: 191, 9: 200}.items():
                ticks = override(ticks, [t], write_ms=ms, tags=["minimal_change", "arithmetic"],
                                 note="Write latency at or under 200 ms: nothing to throttle yet.")
            ticks = override(ticks, [9], note="Write latency exactly 200 ms is not above 200 ms: nothing to throttle yet.")
            # t10 is now the transition to throttling, so Jonah's wrong-target
            # suggestion there is no longer a distractor (gold changes on it).
            ticks = override(ticks, [10], write_ms=226, tags=[],
                             note="Write latency passes 200 ms (226 ms): throttle ledger-batch, the largest writer, not payments-api as Jonah suggests.")
            ticks = override(ticks, [11], write_ms=268)
            # (2) t14-17: failures stay just under 2%, then rise more gently.
            for t, pct in {14: 1.7, 15: 1.8, 16: 1.9, 17: 1.9}.items():
                ticks = override(ticks, [t], fail_pct=pct, tags=["minimal_change", "arithmetic"],
                                 note="Failures under 2%: no status rule, SEV3; throttle ledger-batch.")
            ticks = override(ticks, [18], fail_pct=2.3,
                             note="Failures reach 2.3% (SEV2) in the minute the first status notice goes out (02:23), so rule 5 does not fire: keep throttling ledger-batch.")
            ticks = override(ticks, [19], fail_pct=3.0)
            ticks = override(ticks, [16], surface=lambda tk, i: dict(tk.surface, chat="Dana: failures just under 2%.",
                                                                        gist="a routine probe finds both copies close behind, and Dana puts failures just under 2%"))
            # (3) Marcus is back in the channel at 03:01 instead of 03:04, so the handover is due from t56.
            ticks = override(ticks, range(56, 62), incoming={"name": "Marcus Webb", "present": True, "since": "03:01"})
            ticks = override(ticks, range(56, 59), tags=["minimal_change", "arithmetic"],
                             note="Shift over and Marcus is back in the channel: hand over.")
            ticks = override(ticks, [56], surface=lambda tk, i: surface_of(B_SCRIPT[59]))
            ticks = override(ticks, [59], surface=lambda tk, i: surface_of(("", "Dana: Marcus, anything you need before I hand over?", "Dana asks Marcus whether he needs anything before she hands over")))
        elif variant == "structural_cf":
            # The payments roster pages the database on-call whenever a payments
            # incident opens: Leo acknowledged at 02:04 and is engaged all along.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["dba"] = {"state": "acked", "paged": "02:03", "acked": "02:04", "on_open": True}
            ticks[24].surface = surface_of(("", "Leo (database on-call): pay-db-01 just dropped off; I'm on the console.", "Leo, the on-call database engineer who has been on the incident all along, says the writer just dropped off"))
            ticks[26].surface = surface_of(("", "Dana: Leo, how long until pay-db-01 is back?", "Dana asks Leo how long the writer will be gone"))
            ticks[27].surface = surface_of(("", "Leo: pay-db-01's storage controller is hung; it won't come back quickly.", "Leo says the writer's storage controller is hung and will not return soon"))
            ticks[28].surface = surface_of(("", "Leo: pulling up the failover runbook.", "Leo is pulling up the failover runbook"))
            for t in range(23, 27):
                ticks[t].tags = sorted(set(ticks[t].tags) | {"arithmetic"})
                ticks[t].note = "Database on-call already engaged; the 02:26 lag reading is 5 or fewer minutes old and pay-db-02 shows 3 s: fail over to pay-db-02."
            ticks[27].note = "The 02:26 lag reading is now 6 minutes old (one fact changes: its age passes 5 minutes): lag check."
            ticks[31].tags = sorted(set(ticks[31].tags) | {"recovery"})
            ticks[31].note = "Fresh reading: pay-db-02 4 s and pay-db-03 7 s both qualify; back to failing over to pay-db-02 after the lag-check detour."
        return retag_recovery(self, ticks)

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        m = z["minute"]
        fail = z["fail_pct"]
        if z["failover"] is not None and z["failover"]["state"] == "running":
            action, target = "watch", "none"
        elif not z["primary_up"] and z["dba"]["state"] != "acked":
            action, target = "page_dba", z["primary"]
        elif not z["primary_up"]:
            lag = z["lag"]
            fresh = m - lag["at"] <= 5
            ok = sorted((v, h) for h, v in lag["values"].items() if fresh and v < 10 and h != z["primary"])
            action, target = ("failover", ok[0][1]) if ok else ("lag_check", "none")
        elif m >= z["cmd"]["shift_end"] and z["incoming"] is not None and z["incoming"]["present"]:
            action, target = "handoff", "none"
        elif fail >= 2.0 and (z["status"] is None or m - z["status"]["at"] >= 30):
            action, target = "status", "none"
        elif z["write_ms"] is not None and z["write_ms"] > 200:
            writers = z["writers"]
            top = max(writers, key=lambda k: writers[k])
            assert top != "other"
            action, target = "throttle", top
        elif z["clean_since"] is not None and m - z["clean_since"] >= 15:
            action, target = "close", "none"
        else:
            action, target = "watch", "none"
        if not z["primary_up"] or fail >= 10:
            severity = 2
        elif fail >= 2.0:
            severity = 1
        else:
            severity = 0
        return {"action": action, "target": target, "severity": severity}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Settlement writes overtake payment writes (50% vs 48%) as the primary passes 200 ms (throttle ledger-batch, t7); failures reach exactly 2% with no status notice (post status, t14); the primary becomes unreachable (page the database on-call, t23), the on-call acknowledges while the 02:26 lag reading is 6+ minutes old (lag check, t27), a fresh reading with both replicas under 10 s allows failover to the less-lagged pay-db-02 (t31), the failover runs (watch, t35-44; SEV1 even as failures fall under 10%), the new primary is flooded by payments-api replay (throttle payments-api, t45); the incoming commander reads in from 02:52 while the commander's shift still runs (t47-51), drops off at 02:57 to drive in, so when the shift ends at 03:00 nobody can take over (keep throttling t55-58), and he is back at 03:04 (hand over, t59); and after an acquirer blip resets the clock, 15 clean minutes allow closing (t90)."},
            "paraphrase": {"summary": "Same latent trajectory; writer/copy/switch-over vocabulary, reworded rules, options, target labels and severity grades; states become a prose paragraph instead of board lines."},
            "lexical_decoy": {"summary": "Same latent trajectory; each board gains one line from an unrelated channel that borrows the wording of a wrong action (Wi-Fi fail-over, a vendor's status page, a lag check on a video feed...), never the gold one. On distractor ticks it borrows the wrong action the distractor tempts; at t10, where Jonah tempts the wrong target payments-api, it names a toy payments-api in a hackathon demo and borrows the handoff wording. Elsewhere it is drawn per tick from the non-gold actions."},
            "minimal_cf": {"summary": "Three local edits: t7-9 write latency 184-200 ms, exactly 200 at t9 (throttle -> watch); t14-17 failures 1.7-1.9% (status/SEV2 -> throttle/SEV3); Marcus is back in the channel at 03:01 instead of 03:04 (t56-58 throttle payments-api -> handoff). Neighbouring minutes are smoothed so the numbers stay realistic."},
            "structural_cf": {"summary": "A different on-call roster: the database on-call is paged whenever a payments incident opens, so Leo acknowledged at 02:04 and rule 2 never fires. When the primary dies at 02:28 the routine 02:26 lag reading is still fresh (5 or fewer minutes old) with pay-db-02 at 3 s, so t23-26 fail over to pay-db-02 instead of paging; from t27 the reading is stale and the story matches canonical."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _header(self, z: dict[str, Any], t: int) -> str:
        return pick(
            ["{c} | INC-7730 card payments degraded, open since 02:03", "{c} | INC-7730 (card payments degraded), opened 02:03"],
            "b-head", t,
        ).format(c=clock(B_BASE, z["minute"]))

    def _command_line(self, z: dict[str, Any], t: int) -> str:
        c = z["cmd"]
        end = clock(B_BASE, c["shift_end"])
        if "since" in c:
            # Rule 4 also asks about an incoming commander, so his absence is stated too.
            return pick(
                [
                    "Command: {n} since {s} (took over from {f}); his shift runs to {e}. No incoming commander is waiting to take over.",
                    "Incident commander {n}, in command since {s} (took over from {f}), on shift until {e}; nobody is lined up to take over from him.",
                ],
                "b-cmd2", t,
            ).format(n=c["name"], s=c["since"], f=c["from"], e=end)
        head = pick(
            ["Command: {n}, shift ends {e}.", "Incident commander {n}, on shift until {e}.", "IC: {n}, rostered until {e}."],
            "b-cmd", t,
        ).format(n=c["name"], e=end)
        inc = z["incoming"]
        if inc and inc["present"]:
            tail = pick(
                ["Incoming commander {n} is in the channel (since {j}).", "{n}, the incoming commander, has been in the channel since {j}."],
                "b-inc", t,
            ).format(n=inc["name"], j=inc["since"])
        elif inc:
            tail = pick(
                ["Incoming commander {n} left the channel at {l} and is not in it now.", "{n}, the incoming commander, is not in the channel (left at {l})."],
                "b-inc1", t,
            ).format(n=inc["name"], l=inc["left"])
        else:
            tail = pick(
                ["Incoming commander Marcus Webb has not joined the channel yet.", "Marcus Webb, the incoming commander, is not in the channel yet."],
                "b-inc0", t,
            )
        return f"{head} {tail}"

    def _db_line(self, z: dict[str, Any], t: int) -> str:
        f = z["failover"]
        if f is not None and f["state"] == "running":
            return pick(
                [
                    "Failover running since {s} (step {k} of 5): pay-db-02 is being promoted; pay-db-01 is fenced and unreachable; pay-db-03 is a read-only replica.",
                    "Promotion of pay-db-02 under way since {s}, step {k} of 5, not finished; pay-db-01 fenced and unreachable; pay-db-03 read-only replica.",
                ],
                "b-fo", t,
            ).format(s=f["started"], k=f["step"])
        if not z["primary_up"]:
            return pick(
                [
                    "Primary pay-db-01 (zone a) is unreachable: health checks timing out since 02:28. pay-db-02 and pay-db-03 are read-only replicas. No failover has been started.",
                    "Primary pay-db-01 (zone a) has not answered a health check since 02:28 and is unreachable; pay-db-02 and pay-db-03 are read-only replicas, and nobody has started a failover.",
                ],
                "b-down",
                t,
            )
        p = z["primary"]
        if p == "pay-db-01":
            # Rule 1 asks whether a failover is running, so its absence is stated too.
            return pick(
                ["Primary: pay-db-01 (zone a), reachable, write latency p95 {w} ms; no failover under way.", "pay-db-01 (zone a) is primary and reachable; write p95 {w} ms; no failover has been started."],
                "b-up", t,
            ).format(w=z["write_ms"])
        old = ("pay-db-01 is fenced and down" if z["old_primary"] == "fenced_down"
               else "pay-db-01 answers health checks again but stays fenced out of the cluster")
        return pick(
            [
                "Primary: pay-db-02 (zone b), reachable, write latency p95 {w} ms. It became primary in the 02:50 failover; {o}.",
                "pay-db-02 (zone b) was promoted at 02:50 and takes writes (verified); write p95 {w} ms; {o}.",
            ],
            "b-up2", t,
        ).format(w=z["write_ms"], o=old)

    def _writes_line(self, z: dict[str, Any], t: int) -> str:
        w = z["writers"]
        if w is None:
            return pick(["Write share: nothing recorded this minute.", "No writes were recorded this minute."], "b-w0", t)
        parts = []
        for k in B_WRITERS:
            text = f"{'other components' if k == 'other' else k} {w[k]}%"
            if k == "ledger-batch" and z["batch"] != "running":
                text += f" ({z['batch']})"
            parts.append(text)
        return pick(["Write share (last minute): ", "Writes by component, last minute: "], "b-w", t) + ", ".join(parts) + "."

    def _fail_line(self, z: dict[str, Any], t: int) -> str:
        pct = z["fail_pct"]
        return pick(
            [
                f"Payment attempts failing: {pct:g}% over the last minute.",
                f"{round(pct * 10):,} of 1,000 payment attempts failed in the last minute.",
                f"Last minute: {pct:g}% of payment attempts failed.",
            ],
            "b-fail",
            t,
        )

    def _clean_line(self, z: dict[str, Any], t: int) -> str:
        # Rule 7 tests the under-0.5% streak, so it is stated at every tick, present or absent.
        if z["clean_since"] is None:
            assert z["fail_pct"] >= 0.5, z["minute"]
            return pick(
                ["No clean streak: failures were at or above 0.5% in the latest minute.", "Clean streak (failures under 0.5%): none running; the latest minute was at or above 0.5%."],
                "b-clean0", t,
            )
        n = z["minute"] - z["clean_since"]
        return pick(
            ["Failure rate under 0.5% continuously since {s} ({n} min).", "{m} in a row with failures under 0.5% (since {s})."],
            "b-clean", t,
        ).format(s=clock(B_BASE, z["clean_since"]), n=n, m=plural(n, "minute"))

    def _lag_line(self, z: dict[str, Any], t: int) -> str:
        lag = z["lag"]
        vals = ", ".join(f"{h} {v} s" for h, v in lag["values"].items())
        at = clock(B_BASE, lag["at"])
        if z["primary"] == "pay-db-02":
            return pick(
                ["Replica lag behind pay-db-02, last reading taken at {a}: {v}.", "Latest lag reading behind pay-db-02, taken {a}: {v}."],
                "b-lag2", t,
            ).format(a=at, v=vals)
        if lag["at"] > B_OUTAGE:
            return f"Replica lag behind pay-db-01's last write, manual reading taken at {at}: {vals}."
        if not z["primary_up"]:
            return pick(
                ["Replica lag, last reading taken at {a}, before pay-db-01 went down: {v}.", "Latest replica-lag reading, taken {a} (before the primary went down): {v}."],
                "b-lag1", t,
            ).format(a=at, v=vals)
        return pick(
            ["Replica lag, last reading taken at {a}: {v}.", "Latest replica-lag reading, taken {a}: {v}."],
            "b-lag", t,
        ).format(a=at, v=vals)

    def _dba_line(self, z: dict[str, Any], t: int) -> str:
        d = z["dba"]
        if d.get("on_open") and not z["primary_up"]:
            # While the primary is down, say outright that the on-call's engagement covers it.
            options = [
                "Database on-call Leo Brandt: acknowledged the incident-open page at {a} and is on the console working the pay-db-01 outage.",
                "Leo Brandt (database on-call) has been engaged since acknowledging the incident-open page at {a}; he is working the pay-db-01 outage.",
            ]
        elif d.get("on_open"):
            options = [
                "Database on-call Leo Brandt: paged automatically when the incident opened at {p}, acknowledged at {a}, working the incident.",
                "Leo Brandt (database on-call) acknowledged the incident-open page at {a} and has been engaged since.",
            ]
        else:
            # Rule 2 asks whether ANY page in this incident was acknowledged, so every
            # phrasing says it outright: no page yet, or the first page, unacknowledged.
            options = {
                "idle": ["Database on-call Leo Brandt: not paged during this incident; not involved so far.", "Leo Brandt (database on-call) has not been paged during this incident; not needed so far."],
                "not_paged": ["Database on-call Leo Brandt: not paged during this incident yet.", "No page has gone to Leo Brandt, the database on-call, during this incident yet."],
                "paged": [
                    "Database on-call Leo Brandt: paged at {p} (automatic), the first page of this incident; no acknowledgement yet.",
                    "Leo Brandt (database on-call) was paged automatically at {p}, his first page in this incident, and has not acknowledged it.",
                    "Database on-call Leo Brandt: first page of this incident sent {p}, still unacknowledged.",
                ],
                "acked": [
                    "Database on-call Leo Brandt: acknowledged at {a} and working the incident.",
                    "Leo Brandt (database on-call) acknowledged his page at {a} and is on the console.",
                    "Database on-call Leo Brandt: page answered at {a}; engaged.",
                ],
            }[d["state"]]
        return pick(options, "b-dba", t).format(p=d.get("paged", ""), a=d.get("acked", ""))

    def _status_line(self, z: dict[str, Any], t: int) -> str:
        if z["status"] is None:
            return pick(
                ["Status page: nothing posted for this incident yet.", "No status-page notice has gone out for this incident.", "Status page: still blank for INC-7730."],
                "b-st0", t,
            )
        # Rule 5 counts only updates for this incident, so every phrasing says whose it is.
        return pick(
            ["Status page: latest update for this incident posted at {a}.", "Last public status notice for INC-7730 went out at {a}.", "Status page: most recent update on INC-7730 {a}."],
            "b-st", t,
        ).format(a=clock(B_BASE, z["status"]["at"]))

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        s = tick.surface
        board = {
            "command": self._command_line(z, t),
            "db": self._db_line(z, t),
            "writes": self._writes_line(z, t),
            "fail": self._fail_line(z, t),
            "clean": self._clean_line(z, t),
            "lag": self._lag_line(z, t),
            "dba": self._dba_line(z, t),
            "status": self._status_line(z, t),
        }
        order = pick(
            [
                ["command", "db", "writes", "fail", "clean", "lag", "dba", "status"],
                ["db", "fail", "clean", "writes", "command", "lag", "dba", "status"],
                ["command", "fail", "clean", "db", "writes", "status", "dba", "lag"],
            ],
            "b-order",
            t,
        )
        lines = [self._header(z, t)] + [board[k] for k in order]
        if s["log"]:
            lines.append(f"log: {s['log']}")
        lines.append(f"chat: {s['chat']}")
        if variant == "lexical_decoy":
            lines.append("elsewhere: " + self._decoy_line(z, t))
        return lines

    def _decoy_line(self, z: dict[str, Any], t: int) -> str:
        """Unrelated chatter that borrows a wrong action's wording, never the gold action's."""
        gold = self.policy(z)["action"]
        borrowed = B_DECOY_TEMPTS.get(t) or pick([a for a in B_ACTIONS if a != gold], "b-decoy-action", t)
        assert borrowed != gold, (t, borrowed)
        return B_DECOY_NAMED.get(t) or pick(B_DECOYS[borrowed], "b-decoy", t)

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        s = tick.surface
        m = z["minute"]
        c = z["cmd"]
        end = clock(B_BASE, c["shift_end"])
        if "since" in c:
            command = pick(
                ["{n} took charge from {f} at {s} and is on duty until {e}; no successor is waiting to take over from him.",
                 "Since {s}, {n} has been in charge (he took over from {f}) and his duty runs until {e}; nobody is waiting to succeed him."],
                "bp-cmd2", t,
            ).format(n=c["name"], f=c["from"], s=c["since"], e=end)
        else:
            command = pick(["{n} is in charge; her duty runs until {e}.", "{n} is running the incident, on duty until {e}."], "bp-cmd", t).format(n=c["name"], e=end)
            inc = z["incoming"]
            if inc and inc["present"]:
                command += pick([" Her successor, {n}, has been in the channel since {j}.", " {n}, next in line to take charge after her, has been present in the channel since {j}."], "bp-inc", t).format(n=inc["name"], j=inc["since"])
            elif inc:
                command += pick([" Her successor, {n}, dropped out of the channel at {l} and has not come back.", " {n}, next in line to take charge after her, left the channel at {l} and is absent from it now."], "bp-inc1", t).format(n=inc["name"], l=inc["left"])
            else:
                command += pick([" Her successor, Marcus Webb, has not appeared in the channel yet.", " Marcus Webb, next in line to take charge after her, has not shown up in the channel so far."], "bp-inc0", t)
        f = z["failover"]
        if f is not None and f["state"] == "running":
            database = pick(
                [
                    "A switch-over began at {s} and is still going (stage {k} of 5): pay-db-02 is being turned into the writer, pay-db-01 is fenced off and cannot be reached, and pay-db-03 is a read-only copy.",
                    "pay-db-02 has been mid-promotion since {s}, at stage {k} of 5 and not done; pay-db-01 is fenced off and out of reach, and pay-db-03 is a read-only copy.",
                ],
                "bp-fo", t,
            ).format(s=f["started"], k=f["step"])
        elif not z["primary_up"]:
            database = pick(
                [
                    "The writer, pay-db-01 in zone a, cannot be reached: it has failed every health check since 02:28; pay-db-02 and pay-db-03 are only read-only copies, and no switch-over has begun.",
                    "pay-db-01, the writer in zone a, has been out of reach since 02:28, failing every health check; no switch-over has begun, so pay-db-02 and pay-db-03 remain read-only copies.",
                ],
                "bp-down", t,
            )
        else:
            p = z["primary"]
            database = f"{p} in {B_ZONE[p]} is the writer and can be reached; its writes take {z['write_ms']} ms at the 95th percentile."
            if z["old_primary"] == "fenced_down":
                database += " It took over in the 02:50 switch-over, and pay-db-01 is fenced off and dead."
            elif z["old_primary"] == "fenced_back":
                database += " It took over in the 02:50 switch-over; pay-db-01 passes health checks again but remains fenced off."
            else:
                database += pick([" No switch-over is in progress.", " Nobody has begun a switch-over."], "bp-nofo", t)
        w = z["writers"]
        if w is None:
            writes = "No write traffic was measured this minute."
        else:
            shares = []
            for k in B_WRITERS:
                text = f"{w[k]}% from " + ("other components" if k == "other" else k)
                if k == "ledger-batch" and z["batch"] != "running":
                    text += f" ({B_BATCH_P[z['batch']]})"
                shares.append(text)
            writes = "Write traffic splits as " + listing(shares) + "."
        pct = z["fail_pct"]
        fails = pick(
            [f"{pct:g}% of payments failed in the last minute.", f"In the last minute, {round(pct * 10)} out of every 1,000 payment attempts failed."],
            "bp-fail",
            t,
        )
        if z["clean_since"] is not None:
            n = m - z["clean_since"]
            clean = [f"Failures have stayed below half a percent without a break from {clock(B_BASE, z['clean_since'])}, {plural(n, 'minute')} so far."]
        else:
            clean = [pick(
                ["There is no unbroken run of minutes with failures under half a percent: the last minute was at or above that.",
                 "Failures have not been under half a percent in the last minute, so no clean run is going."],
                "bp-clean0", t,
            )]
        lag = z["lag"]
        trail = listing([f"{h} {plural(v, 'second')} behind" for h, v in lag["values"].items()])
        lag_text = pick(
            ["The newest measurement of how far the copies trail was made at {a} and found {r}.", "At {a}, the latest check of how far the copies trail found {r}."],
            "bp-lag", t,
        ).format(a=clock(B_BASE, lag["at"]), r=trail)
        d = z["dba"]
        # Rule 2 asks whether ANY page in this outage was confirmed, so every sentence says it outright.
        if d.get("on_open"):
            dba_options = [
                "Leo Brandt, the on-call database engineer, was paged when the outage was raised and confirmed at {a}; he has been on it ever since.",
                "Leo Brandt, the on-call database engineer, confirmed at {a} the page sent when the outage was raised, and he has been on it since then.",
            ]
        else:
            dba_options = {
                "idle": [
                    "Leo Brandt, the on-call database engineer, has not been paged during this outage and has not been drawn in.",
                    "No page has gone to Leo Brandt, the on-call database engineer, during this outage; he has not been needed.",
                ],
                "not_paged": [
                    "Nobody has paged Leo Brandt, the on-call database engineer, during this outage yet.",
                    "Leo Brandt, the on-call database engineer, has had no page during this outage so far.",
                ],
                "paged": [
                    "Leo Brandt, the on-call database engineer, was paged automatically at {p}, the first page of this outage, and has not confirmed it.",
                    "An automatic page, the first of this outage, reached Leo Brandt, the on-call database engineer, at {p}; he has not confirmed it yet.",
                ],
                "acked": [
                    "Leo Brandt, the on-call database engineer, confirmed his page at {a} and is on the case.",
                    "Leo Brandt, the on-call database engineer, has been on the case since confirming his page at {a}.",
                ],
            }[d["state"]]
        dba = pick(dba_options, "bp-dba", t).format(p=d.get("paged", ""), a=d.get("acked", ""))
        if z["status"] is None:
            status = pick(
                ["The public status site carries no notice about this outage.", "Nothing about this outage has been published on the public status site yet."],
                "bp-st0", t,
            )
        else:
            status = pick(
                ["The newest notice about this outage on the public status site went up at {a}.", "The public status site's latest notice about this outage was published at {a}."],
                "bp-st", t,
            ).format(a=clock(B_BASE, z["status"]["at"]))
        # Narrate in a different order from the board: the moment first, then the
        # people and the page, then the database, and command last.
        ordered = [f"{clock(B_BASE, m)}: {s['gist']}.", dba, status, lag_text, database, fails] + clean + [writes, command]
        ordered.append("Outage INC-7730 (card payments degraded), raised at 02:03, is still open.")
        return " ".join(ordered)


SCENARIOS = [CheckoutLatency, PaymentDbFailover]
