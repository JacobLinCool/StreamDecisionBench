"""Workflow / Handoff Control: a controller moving work through a multi-party workflow.

The controller watches one piece of work move through a workflow with several
parties and decides, tick by tick, which action the work should be under right
now, given progress, dependencies, ownership and approvals. Both scenarios share
the same latent vocabulary (current step or stage, what it is waiting on, who
owns it, which approvals are on file, whether it has been stopped) but differ in
difficulty:

* ``workflow_a`` (easy) - a procurement request moving through purchasing over
  two business weeks (one tick = one working hour). One choice question with
  four actions whose texts say when to use them, a four-rule policy and one
  amount threshold (approval strictly above $5,000, quote plus shipping).
* ``workflow_b`` (medium) - a software release train handed between build, QA,
  security review and deploy (one tick = 30 minutes of the working day). Two
  questions per decision (which action, and to whom it is addressed), a
  six-rule policy with an ownership rule (named backups, used twice), an
  approval that expires after 24 hours and a scope check on severity-1 defects.
  The addressee question has eight options, above the 5-6 of the medium band
  (SPEC 3.6): three teams, all three named backups, the approver and nobody,
  so that the two reroutes test the roster lookup.

Actions are standing decisions: an action stays correct for as long as its rule
is the first one that matches, even when it was already started in an earlier
tick (the world does not react to the controller within the tick).

States name decision facts in several phrasings (``pick``), sometimes as plain
events rather than rule preconditions. Every condition a rule tests is stated at
every tick, present or absent: an outstanding dependency or missing input is
named, and its absence is said outright in varied wording (no phrasing pool for
a decision fact contains an empty string). The roles also say that an unnamed
input is absent, as a second safeguard.
Lexical decoys are timestamped log or channel entries about other requests or
trains, mixed into the same stream as the real entries.
"""

from __future__ import annotations

import copy
from typing import Any

from streamdecisionbench.authoring import Choice, Scenario, Tick, Timeline, override, pick, seeded, span_tags

FAMILY = "workflow_handoff"


def money(amount: int) -> str:
    return f"${amount:,}"


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def rotate(pool: list[str], i: int) -> str:
    """A pool line for tick ``i`` that differs from the lines of the two ticks before it."""
    return pool[(7 * i) % len(pool)]


def surface_of(item: Any) -> dict[str, Any]:
    """Normalise a script entry: ``(at, text, gist)`` or ``([(at, text), ...], gist)``."""
    if len(item) == 3 and isinstance(item[0], str):
        at, text, gist = item
        return {"entries": [(at, text)], "gist": gist}
    entries, gist = item
    return {"entries": [tuple(e) for e in entries], "gist": gist}


# ===========================================================================
# Scenario A - procurement request, one question, four actions (easy)
# ===========================================================================

A_THRESHOLD = 5000
A_DAYS = ["Mon 1 Jun", "Tue 2 Jun", "Wed 3 Jun", "Thu 4 Jun", "Fri 5 Jun", "Mon 8 Jun", "Tue 9 Jun", "Wed 10 Jun", "Thu 11 Jun", "Fri 12 Jun"]
A_DAYS_LONG = [
    "Monday 1 June", "Tuesday 2 June", "Wednesday 3 June", "Thursday 4 June", "Friday 5 June",
    "Monday 8 June", "Tuesday 9 June", "Wednesday 10 June", "Thursday 11 June", "Friday 12 June",
]


def a_hour(t: int) -> int:
    return 8 + t % 10


def a_clock(t: int) -> str:
    return f"{A_DAYS[t // 10]}, {a_hour(t):02d}:00"


def a_clock_long(t: int) -> str:
    h = a_hour(t)
    label = f"{h} in the morning" if h < 12 else ("noon" if h == 12 else f"{h - 12} in the afternoon")
    return f"{A_DAYS_LONG[t // 10]}, {label}"


A_ROLE = (
    "You are the workflow controller for purchase request PR-4471 at Kestrel Logistics. The request moves through "
    "intake review, vendor quote, vendor setup, purchase order, delivery and receiving; Priya Nair in Procurement works it. "
    "Luis Ortega (Head of Operations) must approve any request whose total is above $5,000. `status` says whether the "
    "current revision has been cancelled or rejected, gives the vendor quote (or, before any quote, the requester's "
    "estimate) and the approvals on file, and names every input still owed to the request from outside Procurement "
    "(when it names none, nothing is owed). A new revision submitted after a rejection or cancellation is a fresh "
    "request. Every working hour you choose the action the request should be under for that hour. An action stays the "
    "right one for as long as its rule is the first rule that matches, even if the action was already started in an "
    "earlier hour."
)
A_POLICY = [
    "1. If the requester has cancelled the current revision of the request or an approver has rejected it, stop the request. A cancellation or rejection applies to the revision it was made on; a revision submitted afterwards starts open.",
    "2. Otherwise, if the request total is above $5,000 (strictly more than $5,000.00) and no approval on file covers that total, obtain approval from Luis Ortega (send the approval request, or chase it if it is already with him). The request total is the full vendor quote including shipping; until a vendor quote exists, it is the requester's estimate. An approval covers a total only up to the amount approved; an approval that has been asked for but not yet given does not count.",
    "3. Otherwise, if the current step is held up by something that must come from outside Procurement (a vendor quote, a vendor form, a delivery, a vendor's reply) and it has not arrived yet, wait for that dependency.",
    "4. Otherwise, keep processing the current step.",
]
A_QUESTION = "Apply the first rule that matches the current state (`status` holds the facts; `log` shows the latest entries). What should the controller do with PR-4471 this hour?"

A_ROLE_P = (
    "You steer purchase request PR-4471 through the purchasing workflow at Kestrel Logistics: first the intake check, then "
    "the supplier's quote, supplier onboarding, the purchase order, the shipment and finally the goods-in inspection, all "
    "handled by Priya Nair of Purchasing. Any request worth more than $5,000 needs a sign-off from Luis Ortega, who heads "
    "Operations. The hourly digest says whether the present revision has been withdrawn or turned down, gives the "
    "supplier's quote (or, before one exists, the requester's estimate) and the sign-offs on record, and mentions "
    "everything still owed from outside Purchasing (if it mentions nothing, nothing is owed). A revision filed after a "
    "refusal or withdrawal counts as a new request. Once an hour you pick what should be happening to the request during "
    "that hour. A pick remains correct for as long as its rule is the earliest rule that fits, even if the same thing was "
    "already set in motion an hour ago."
)
A_POLICY_P = [
    "1. Should the requester have withdrawn the present revision, or an approver have turned it down, end the request. A withdrawal or refusal belongs to the revision it was made on; a revision filed later begins live.",
    "2. Failing that, when the request's amount exceeds $5,000 (anything over $5,000.00) and no sign-off on record reaches that amount, secure Luis Ortega's sign-off (send it to him, or chase it if he already has it). The amount is the supplier's whole quote, freight included; as long as no supplier quote exists, it is the requester's own estimate. A sign-off reaches an amount only up to the figure that was signed; a sign-off that was asked for but not yet given does not count.",
    "3. Failing that, when the step in progress is stuck on something that has to come from outside Purchasing (a supplier quote, a supplier form, a shipment, a supplier's answer) and it has not come in yet, pause until it lands.",
    "4. In all other cases, carry on with the step in progress.",
]
A_QUESTION_P = "Go down the rules in order and use the earliest one that fits this digest. What should happen to PR-4471 during this hour?"

A_OPTIONS = {
    "continue": "Keep processing the current step - use when no earlier rule applies and nothing is owed from outside Procurement.",
    "wait": "Wait for the outside dependency - use when no earlier rule applies and the current step is held up by something owed from outside Procurement.",
    "request_approval": "Obtain approval from Luis Ortega (send the request, or chase it if already sent) - use when no earlier rule applies and the total is above $5,000 with no approval on file covering it.",
    "stop": "Stop the request - use when the requester has cancelled the current revision or an approver has rejected it.",
}
A_OPTIONS_P = {
    "continue": "Carry on with the step in progress - fits when no earlier rule does and nobody outside Purchasing owes anything.",
    "wait": "Pause until the outside input lands - fits when no earlier rule does and the step in progress is stuck on something owed from outside Purchasing.",
    "request_approval": "Secure Luis Ortega's sign-off (send it to him, or chase it if he already has it) - fits when no earlier rule does and the amount exceeds $5,000 with no sign-off on record reaching it.",
    "stop": "End the request - fits when the requester has withdrawn the present revision or an approver has turned it down.",
}
A_OPTIONS_D = {
    "continue": "Keep processing the current step - use when no earlier rule applies and nothing from outside Procurement is outstanding.",
    "wait": "Wait for the pending outside dependency - use when no earlier rule applies and the current step is held up by something owed from outside Procurement.",
    "request_approval": "Obtain approval from Luis Ortega (send the request, or chase it if it was already sent) - use when no earlier rule applies and the request total is above $5,000 with no approval on file covering it.",
    "stop": "Stop the request - use when the requester has cancelled the current revision or an approver has rejected that revision.",
}

A_STEP = {
    "intake": "intake review (Priya Nair checks the specification)",
    "quote": "vendor quote (Northline Supply is pricing the order)",
    "vendor_setup": "vendor setup (Northline's vendor record has to be activated before any purchase order)",
    "po": "purchase order",
    "delivery": "delivery",
    "receiving": "receiving inspection (Priya Nair and IT check the delivered units)",
}
A_STEP_P = {
    "intake": "the intake check, which is Priya Nair's job",
    "quote": "the supplier quote, which Northline Supply is preparing",
    "vendor_setup": "supplier onboarding, since Northline's record must go live before an order can be raised",
    "po": "the purchase order stage",
    "delivery": "the shipment stage",
    "receiving": "the goods-in inspection by Priya Nair and IT",
}
A_STEP_SHORT = {"intake": "intake review", "quote": "vendor quote", "vendor_setup": "vendor setup", "po": "purchase order", "delivery": "delivery", "receiving": "receiving inspection"}

# Every outside dependency has several phrasings; none of them is a fixed banner.
A_WAIT = {
    "quote": [
        "Owed from outside Procurement: Northline's formal quote, requested Mon 1 Jun 13:25 and not yet received.",
        "Northline has not yet sent the formal quote Priya asked for on Mon 1 Jun at 13:25.",
        "The formal quote from Northline (requested Monday 13:25) has not come in.",
    ],
    "w9": [
        "Owed from outside Procurement: Northline's signed W-9, requested Tue 2 Jun 10:41; the vendor record cannot be activated without it.",
        "Northline has not returned the signed W-9 requested on Tue 10:41, so its vendor record is still inactive.",
        "Vendor setup is held until Northline's signed W-9 arrives (requested Tue 2 Jun 10:41, not received).",
    ],
    "delivery": [
        "Owed from outside Procurement: the delivery; the six scanners have not reached the dock.",
        "Northline's shipment for PO-7724 has not been delivered yet.",
        "The scanners are not at the Reno dock yet.",
    ],
    "replacement": [
        "Owed from outside Procurement: Northline's answer on how units 4 and 5 will be replaced; none yet.",
        "Northline has not said how it will replace units 4 and 5 (asked Thu 11 Jun at 08:45).",
        "Receiving is held until Northline says how it will replace the two wrong units; no answer yet.",
    ],
}
# The absence of an outside dependency is always stated, in varied wording, at every tick (SPEC 3.5).
A_WAIT_NONE = [
    "Nothing is owed from outside Procurement.",
    "Outstanding from outside Procurement: nothing.",
    "No vendor quote, form, delivery or reply is outstanding.",
    "Nobody outside Procurement owes the request anything.",
    "Owed from outside Procurement: none.",
]
A_WAIT_P = {
    "quote": ["Northline still owes its formal quote, requested on Monday at 13:25.", "The supplier has not yet delivered the formal quote asked for on Monday afternoon."],
    "w9": ["Northline still owes its signed W-9, without which the supplier record cannot go live.", "The supplier record stays dormant because Northline has not returned its signed W-9."],
    "delivery": ["The shipment has not been received yet.", "Nothing has arrived at the dock from Northline so far."],
    "replacement": ["Northline has not yet said how it will replace units 4 and 5.", "There is still no word from Northline on swapping out the two wrong units."],
}
A_WAIT_NONE_P = [
    "Nobody outside Purchasing owes anything right now.",
    "No supplier quote, form, shipment or answer is being waited for.",
    "Nothing is owed from outside Purchasing.",
    "The request is not waiting on anyone outside Purchasing.",
]

# How revision B relates to revision A (surface only; rule 1 looks at the current revision).
A_PRIOR = {
    "rev": "Luis Ortega's rejection on Fri 5 Jun was of revision A",
    "rev_p": "Luis Ortega's refusal last Friday applied to revision A only",
    "po": "the PO-7719 draft was cancelled on Fri 5 Jun",
    "po_p": "the old PO-7719 draft was scrapped on Friday",
}
A_PRIOR_MIN = {
    "rev": "revision A was withdrawn on Mon 8 Jun before Luis Ortega decided on it",
    "rev_p": "revision A was pulled on Monday before Luis Ortega had decided on it",
    "po": "the held PO-7719 draft is dropped",
    "po_p": "the held PO-7719 draft is being dropped",
}

A_PO = {
    "7719_draft": "PO-7719 is being prepared and has not been sent.",
    "7719_held": "PO-7719 is drafted but was held back and has not been sent.",
    "7724_none": "No purchase order exists yet for revision B ({po}).",
    "7724_draft": "PO-7724 is being prepared and has not been sent ({po}).",
    "7724_sent": "PO-7724 went to Northline on Mon 8 Jun at 14:32; delivery was promised for Wed 10 Jun, 07:00-11:00.",
}
A_PO_P = {
    "7719_draft": "Order PO-7719 is still being written up and has not gone out.",
    "7719_held": "Order PO-7719 is written but was pulled back before going out.",
    "7724_none": "Revision B has no order written yet ({po}).",
    "7724_draft": "Order PO-7724 is still being written up and has not gone out ({po}).",
    "7724_sent": "Order PO-7724 reached Northline on Monday afternoon with a Wednesday-morning delivery promise.",
}
A_QTY = {6: "six", 5: "five"}
# The hour of the substitution (t39): the revised quote is for Z-45s and Dana has accepted it, but Priya only
# changes the request lines at t40, so the request field says why it still names the Z-40.
A_SWAP_NOTE = " Dana has accepted Northline's substitute, six Z-45s under revised quote Q-2291-R1; the request lines still list the Z-40."
A_SWAP_NOTE_P = " Its line items still name the Z-40, although Dana has agreed to Northline's swap to six Z-45s under the revised quote Q-2291-R1."
A_VENDOR = {
    None: "Vendor: not chosen yet.",
    "new": "Vendor: Northline Supply (new to Kestrel).",
    "new_active": "Vendor: Northline Supply (new to Kestrel; its vendor record has been active since Wed 3 Jun).",
    "existing": "Vendor: Northline Supply (an existing Kestrel vendor; its W-9 has been on file since 2025).",
}
A_VENDOR_P = {
    None: "with the supplier still to be chosen",
    "new": "to be bought from Northline Supply, a supplier new to Kestrel",
    "new_active": "to be bought from Northline Supply, a supplier new to Kestrel whose record went live on Wednesday 3 June",
    "existing": "to be bought from Northline Supply, a long-standing Kestrel supplier whose W-9 has been on record since 2025",
}

# Surface content per tick: (time of the log entry, log entry, third-person gist
# for the paraphrase register), or ([(time, entry), ...], gist) for the hours
# with a burst of activity. One tick = one working hour, 08:00-17:00, ten
# snapshots a day; entries are stamped within the hour before the snapshot.
A_SCRIPT: list[Any] = [
    # Mon 1 Jun (t0-t9)
    ("07:52", "PR-4471 submitted by Dana Whitfield: six Z-40 handheld scanners to replace failing units at the Reno dock, estimated at $4,300.", "Dana Whitfield filed the request before eight, estimating $4,300 for six Z-40 scanners"),
    ("08:41", "Priya Nair (Procurement) picked up PR-4471 for intake review.", "Priya Nair took the request on for the intake check"),
    ("09:37", "PR-4466 (forklift battery, $7,900, Yard team) was sent to Luis Ortega for approval.", "a separate Yard team request, PR-4466 for a $7,900 forklift battery, went to Luis Ortega for sign-off"),
    ("10:48", "Priya confirmed the Z-40 works with the warehouse WMS app and the charging cradles already on site.", "Priya found the Z-40 compatible with the WMS app and the cradles already on site"),
    ("11:30", "Dana confirmed the six units are for dock doors 3 to 8.", "Dana said the six units are meant for dock doors 3 to 8"),
    ("12:44", "Priya shortlisted Northline Supply, which lists the Z-40 as in stock.", "Priya settled on Northline Supply, which shows the Z-40 in stock"),
    ("13:25", "Formal quote for six Z-40 scanners requested from Kevin Marsh at Northline Supply.", "a formal quote was asked of Kevin Marsh at Northline"),
    ("14:36", "Kevin Marsh acknowledged the quote request; nothing attached yet.", "Kevin Marsh confirmed he got the quote request but sent nothing yet"),
    ("15:50", "Priya noted that Northline is a new vendor, so a signed W-9 will be needed before any purchase order.", "Priya noted that Northline, being a new supplier, will have to provide a signed W-9 before any order"),
    ("16:58", "No quote from Northline by end of day; reminder set for 09:00.", "the day ended without a quote from Northline, with a reminder set for nine"),
    # Tue 2 Jun (t10-t19)
    ("07:46", "Northline emailed its summer catalogue, listing the Z-40 at $799 a unit.", "Northline mailed out its summer catalogue, which lists the Z-40 at $799"),
    ("08:58", "Reminder about the PR-4471 quote sent to Kevin Marsh.", "a reminder about the quote went to Kevin Marsh"),
    ("09:55", "Kevin Marsh: 'Our pricing team is finishing the shipping line; the quote follows before lunch.'", "Kevin Marsh wrote that the quote would follow before lunch once shipping was priced"),
    ("10:41", "Quote Q-2291 received from Northline: scanners $4,860, shipping $260. Signed W-9 requested from Northline for vendor setup.", "Northline's quote came in at $4,860 for the scanners and $260 for shipping, and their W-9 was asked for"),
    ("11:20", "PR-4471 routed to Luis Ortega (Head of Operations) for approval.", "the request was put in Luis Ortega's approval queue"),
    ("12:30", "Tom Becker (Finance) confirmed cost centre 4410-OPS has room for PR-4471.", "Tom Becker in Finance confirmed the cost centre can absorb the purchase"),
    ("13:52", "Luis Ortega on chat: 'Looks reasonable. I'll sign PR-4471 after my 2 pm meeting.'", "Luis Ortega said on chat that it looks reasonable and he will sign after his 2 pm meeting"),
    ("14:45", "Priya reminded Northline's accounts team about the W-9.", "Priya nudged Northline's accounts team about the W-9"),
    ("15:40", "Luis's meeting overran; PR-4471 is still unsigned in his queue.", "Luis's meeting ran long and the request still sits unsigned with him"),
    ("16:55", "End of day: PR-4471 still unsigned by Luis; Northline's W-9 still not received.", "the day closed with Luis's signature and Northline's W-9 both still missing"),
    # Wed 3 Jun (t20-t29)
    ("07:58", "Luis Ortega approved PR-4471 for $5,120.", "Luis Ortega signed the request off at $5,120 first thing"),
    ("08:50", "Kevin Marsh: 'Our accounts team will send the signed W-9 today.'", "Kevin Marsh promised the signed W-9 would come today"),
    ("09:34", "Priya drafted the Northline vendor record; it stays inactive until the W-9 arrives.", "Priya drafted the supplier record, which cannot go live without the W-9"),
    ("10:40", "Dana: 'Please cancel Thursday's product demo with Northline, we've seen enough.'", "Dana asked for Thursday's Northline product demo to be called off"),
    ("11:35", "Auto-reply from Northline accounts: W-9 requests are handled within one business day.", "Northline's accounts inbox auto-replied that W-9s take up to a business day"),
    ("12:48", "Priya phoned Northline accounts; the W-9 is promised by mid-afternoon.", "Priya phoned Northline and was promised the W-9 by mid-afternoon"),
    ("13:57", "Still no W-9 from Northline; the vendor record remains inactive.", "the W-9 had still not come, so the supplier record stays inactive"),
    ("14:36", "Signed W-9 received from Northline; vendor record activated. Purchase order drafting started.", "Northline's signed W-9 arrived, the supplier went live and work on the purchase order began"),
    ("15:44", "PO-7719 drafted for six Z-40 scanners, ship-to Reno dock.", "purchase order PO-7719 was drafted for the six scanners"),
    ("16:50", "Priya added asset-tag instructions to PO-7719.", "asset-tag instructions were added to the order"),
    # Thu 4 Jun (t30-t39)
    ("07:59", "Dana asked for delivery between 07:00 and 11:00, before the afternoon truck wave.", "Dana asked for a morning delivery, before the afternoon trucks"),
    ([("08:12", "Marco (dock): door 3 is free most mornings; drivers can call ext. 214."),
      ("08:31", "IT asked Northline to list the scanners' serial numbers on the packing slip."),
      ("08:45", "Delivery window and dock contact (Marco, ext. 214) added to PO-7719.")],
     "Marco offered door 3 and his extension, IT asked for serial numbers on the packing slip, and the delivery window went onto the order"),
    ([("09:05", "Tom Becker (Finance): cost centre 4410-OPS added to every PO-7719 line."),
      ("09:18", "Legal: Northline's standard terms are acceptable for PO-7719."),
      ("09:30", "Payment terms on PO-7719 set to net 30.")],
     "Finance put the cost centre on every line, Legal cleared Northline's terms and payment was set to net 30"),
    ([("10:07", "Dana asked whether wrist straps are included; Kevin Marsh confirmed they come in the box."),
      ("10:29", "Marco (dock): the afternoon truck wave moves to 13:00 next week."),
      ("10:52", "Kevin Marsh: heads-up, Northline's list prices go up 5% from Monday 8 June.")],
     "Kevin Marsh confirmed the wrist straps come in the box and warned that Northline's list prices rise 5% from Monday, while Marco said the truck wave moves to one o'clock next week"),
    ([("11:10", "Priya corrected the PO-7719 ship-to line to 'Reno DC, door 3'."),
      ("11:25", "Marco confirmed a pallet jack will be free at door 3."),
      ("11:40", "Kevin asked whether PO-7719 should include an extended warranty; Dana said no.")],
     "Priya fixed the ship-to line, Marco lined up a pallet jack and Dana turned down Kevin's warranty add-on"),
    ("12:55", "Quote Q-2291 attached to PO-7719.", "the quote was attached to the order"),
    ("13:48", "PO-7719 line check done: quantity, unit price and ship-to address confirmed.", "the order's lines were checked and confirmed"),
    ("14:30", "PO-7719 queued to go out with the 17:00 batch.", "the order was queued for the five o'clock send"),
    ("15:35", "Dana thanked Priya for sorting out the dock details.", "Dana thanked Priya for handling the dock details"),
    ([("16:40", "Northline revised its quote (Q-2291-R1): the Z-40 is out of stock, so they offer six Z-45s at $5,040; shipping stays $260. PO-7719 pulled from the 17:00 batch."),
      ("16:52", "Dana: 'The Z-45 fits the same cradles, fine by me.'")],
     "Northline revised its quote to six Z-45s at $5,040 with the same $260 freight because the Z-40 is out of stock, Dana accepted the swap and the order was pulled from the batch"),
    # Fri 5 Jun (t40-t49)
    ("07:55", "Priya changed the PR-4471 lines to six Z-45 scanners.", "Priya switched the request's lines to six Z-45s"),
    ("08:40", "Revised total for PR-4471 sent to Luis Ortega for approval.", "the new total went to Luis Ortega for sign-off"),
    ("09:50", "PO-7719 updated to six Z-45 scanners; not sent.", "the order was switched to Z-45s but not sent"),
    ("10:35", "Luis asked Finance why PR-4471 went up by $180.", "Luis asked Finance about the $180 increase"),
    ("11:45", "Tom Becker replied: a stock substitution only, nothing else changed.", "Tom Becker explained it was only a stock substitution"),
    ("12:50", "Luis's approval queue still shows the revised PR-4471 as undecided.", "the revised request still sat undecided in Luis's queue"),
    ("13:40", "Luis Ortega rejected PR-4471 at $5,300: 'More than I signed for. Find a cheaper option or cut the quantity.'", "Luis Ortega turned the request down at $5,300, asking for a cheaper option or fewer units"),
    ("14:30", "Priya cancelled the PO-7719 draft.", "Priya scrapped the draft order"),
    ("15:22", "Dana: 'I'll rework it over the weekend.'", "Dana said she would rework it over the weekend"),
    ("16:45", "Northline told that PR-4471 was rejected; no order placed.", "Northline was told the request had been turned down and no order would be placed"),
    # Mon 8 Jun (t50-t59)
    ("07:50", "Dana emailed Priya a draft of revision B (six refurbished Z-40s); not submitted yet.", "Dana mailed Priya a not-yet-submitted draft of a revision B with six refurbished Z-40s"),
    ("08:35", "Dana submitted PR-4471 revision B: six refurbished Z-40s, Northline quote Q-2291-R2 at $4,740 plus $260 shipping.", "Dana submitted revision B for six refurbished Z-40s, quoted at $4,740 with $260 shipping"),
    ("09:40", "PO-7724 drafted for revision B, replacing the cancelled PO-7719.", "a new order, PO-7724, was drafted for revision B"),
    ("10:55", "Northline reserved six refurbished Z-40s for PR-4471.", "Northline set aside six refurbished Z-40s"),
    ("11:30", "Dana: doors 3 to 8 each get one unit, as originally planned.", "Dana said doors 3 to 8 each get one unit, as first planned"),
    ("12:40", "Delivery window and dock contact copied into PO-7724.", "the delivery details were copied into the new order"),
    ("13:50", "PO-7724 line check done: six units at $790, shipping $260.", "the new order's lines checked out at six units of $790 plus shipping"),
    ("14:32", "PO-7724 sent to Northline; delivery promised for Wed 10 Jun, 07:00-11:00.", "the order went to Northline with delivery promised for Wednesday morning"),
    ("15:15", "Northline acknowledged PO-7724.", "Northline acknowledged the order"),
    ("16:40", "Accounts Payable set up the invoice match for PO-7724.", "Accounts Payable prepared to match the invoice"),
    # Tue 9 Jun (t60-t69)
    ([("07:31", "Dock schedule for Wednesday: Northline slot 08:00-09:00 at door 3."),
      ("07:44", "Marco (dock): two other deliveries are booked at door 4 that morning."),
      ("07:56", "Security desk added Northline's carrier to Wednesday's gate list.")],
     "the Wednesday dock plan gives Northline door 3 at eight, with two other deliveries at door 4 and the carrier on the gate list"),
    ([("08:14", "Marco asked where to stage the boxes; answer: the IT cage."),
      ("08:33", "IT: the cage has room for six boxes on the lower shelf."),
      ("08:52", "Facilities lent a cage trolley for Wednesday morning.")],
     "Marco was told to stage the boxes in the IT cage, IT made room on the lower shelf and Facilities lent a trolley"),
    ([("09:08", "Northline shipping notice: PO-7724 left the Sparks depot."),
      ("09:21", "Carrier assigned: Sierra Freight, tracking SF-55120."),
      ("09:44", "Dana forwarded the tracking link to the dock supervisors.")],
     "Northline's shipping notice says the order left Sparks with Sierra Freight, and Dana passed the tracking link to the dock supervisors"),
    ([("10:03", "IT prepared six WMS login profiles for the incoming scanners."),
      ("10:26", "IT: the Z-40 firmware image is staged on the enrolment laptop."),
      ("10:44", "Priya reserved six asset tags, KL-20411 to KL-20416.")],
     "IT set up six WMS profiles and staged the firmware, and Priya reserved six asset tags"),
    ("11:20", "Dana asked whether the old units can be recycled; Facilities will collect them.", "Dana asked about recycling the old units and Facilities agreed to collect them"),
    ("12:35", "Carrier tracking: out for delivery tomorrow morning.", "tracking shows the parcel out for delivery tomorrow morning"),
    ("13:50", "Northline offered a $950 extended warranty for the six units.", "Northline pitched a $950 extended warranty for the six units"),
    ("14:40", "Priya declined the warranty offer by email.", "Priya turned the warranty down by email"),
    ("15:55", "Dana reminded the dock team about the 08:00 Northline slot.", "Dana reminded the dock crew about the morning slot"),
    ("16:50", "Carrier confirmed tomorrow's 08:00-09:00 slot.", "the carrier confirmed the morning slot"),
    # Wed 10 Jun (t70-t79)
    ("07:40", "Carrier: truck left the Sparks hub, ETA 09:00-09:30.", "the carrier says the truck left Sparks and should arrive around nine"),
    ("08:35", "Driver called: 20 minutes out, slowed by roadworks on I-80.", "the driver phoned to say he is twenty minutes out"),
    ("09:25", "Six scanner boxes received at door 3 and signed for by Marco.", "Marco signed for six scanner boxes at door 3"),
    ("10:40", "Priya started the receiving inspection: serial numbers against the packing slip.", "Priya began checking serial numbers against the packing slip"),
    ([("11:06", "Serial number for unit 1 matches the packing slip."),
      ("11:24", "Units 2 and 3 match as well."),
      ("11:47", "Battery health for units 1 to 3 reads 100%.")],
     "the first three serial numbers matched the packing slip and their batteries read full"),
    ([("12:08", "IT enrolled unit 1 in the WMS; scan test passed."),
      ("12:26", "Asset tag KL-20411 applied to unit 1."),
      ("12:49", "Marco tried unit 1 on a live pallet; scans fine.")],
     "unit 1 was enrolled, tagged and tried on a live pallet without trouble"),
    ([("13:05", "Unit 2 enrolled; scan test passed."),
      ("13:22", "Asset tag KL-20412 applied to unit 2."),
      ("13:40", "IT: unit 2 synced to the WMS in 40 seconds.")],
     "unit 2 was enrolled, tagged and synced"),
    ([("14:08", "Unit 3 enrolled; scan test passed."),
      ("14:31", "Northline's delivery note filed with PO-7724."),
      ("14:55", "Invoice INV-8830 for $5,000 received from Northline and matched to PO-7724.")],
     "unit 3 passed its scan test, the delivery note was filed and Northline's $5,000 invoice matched the order"),
    ("15:45", "Units 4 to 6 unpacked for enrolment.", "units 4 to 6 were unpacked"),
    ("16:50", "Unit 6 enrolled; scan test passed. Units 4 and 5 left for the morning.", "unit 6 passed its scan test, with units 4 and 5 left for the morning"),
    # Thu 11 Jun (t80-t89)
    ("07:55", "Receiving inspection moves on to units 4 and 5.", "the inspection moved on to units 4 and 5"),
    ("08:45", "Units 4 and 5 are Z-30 models, not Z-40s. Priya asked Northline how they will replace them.", "units 4 and 5 turned out to be Z-30s, and Priya asked Northline how they will replace them"),
    ("09:50", "Kevin Marsh: 'Checking stock for two refurbished Z-40s, will come back to you.'", "Kevin Marsh said he is checking stock and will come back"),
    ("10:30", "Units 4 and 5 quarantined in the IT cage with a do-not-issue tag.", "the two wrong units were tagged and locked away"),
    ("11:45", "Dana: 'If Northline can't sort this by Friday noon, I'll cancel the whole request.'", "Dana said she would cancel if Northline has not sorted it by Friday noon"),
    ("12:40", "Invoice INV-8830 put on hold until the wrong units are resolved.", "the invoice was put on hold"),
    ("13:35", "Support ticket NS-3318 opened with Northline for the wrong units.", "a support ticket was opened with Northline"),
    ("14:50", "Kevin: still no answer from the refurbishment team.", "Kevin still has no answer from his refurbishment team"),
    ("15:40", "Priya chased Northline again; no replacement date yet.", "Priya chased again without getting a date"),
    ("16:45", "Dana cancelled PR-4471: the Sparks warehouse is sending six spare Z-40s instead. Northline to collect all six units.", "Dana cancelled the request because the Sparks site is sending spare Z-40s, and Northline will collect the six units"),
    # Fri 12 Jun (t90-t99)
    ("07:50", "Priya confirmed the cancellation to Northline, which emailed a prepaid return label for the six units.", "Priya confirmed the cancellation to Northline, which emailed a prepaid return label for the six units"),
    ("08:40", "Accounts Payable voided invoice INV-8830.", "the invoice was voided"),
    ("09:35", "Dana: 'If the Sparks transfer falls through, I'll reopen PR-4471 with Northline on Monday.'", "Dana said she would reopen the request with Northline on Monday if the Sparks transfer falls through"),
    ("10:45", "Facilities booked Northline's pickup of the six units for Monday.", "Facilities booked the return pickup for Monday"),
    ("11:30", "Dana: the Sparks transfer has shipped and arrives Tuesday.", "Dana said the Sparks transfer is on its way for Tuesday"),
    ("12:50", "IT removed the six WMS profiles made for the Northline units.", "IT deleted the six WMS profiles"),
    ("13:40", "Support ticket NS-3318 closed.", "the support ticket was closed"),
    ("14:55", "Luis Ortega acknowledged the cancellation notice.", "Luis Ortega acknowledged the cancellation"),
    ("15:30", "Tom Becker released the $5,000 commitment on cost centre 4410-OPS.", "Finance released the $5,000 commitment"),
    ("16:45", "PR-4471 archived as cancelled by the requester.", "the request was archived as cancelled by the requester"),
]

# Minimal counterfactual surfaces (same slots as A_SCRIPT).
A_MIN_SURFACE: dict[int, Any] = {
    # (1) Luis signs at 13:52 on Tuesday instead of promising to sign later.
    16: ("13:52", "Luis Ortega approved PR-4471 for $5,120 from his phone between meetings.", "Luis Ortega approved the request at $5,120 from his phone between meetings"),
    18: ("15:40", "Priya filed Luis's approval with the PR-4471 record.", "Priya filed Luis's approval with the request"),
    19: ("16:55", "End of day: Northline's W-9 still not received.", "the day closed with Northline's W-9 still missing"),
    20: ("07:58", "Kevin Marsh: 'The W-9 is on our controller's desk for signature.'", "Kevin Marsh said the W-9 is waiting for his controller's signature"),
    # (2) Luis defers the decision on the revised total instead of rejecting it.
    46: ("13:40", "Luis Ortega on PR-4471 at $5,300: 'I'll decide on Monday, once I have seen the Q3 numbers.'", "Luis Ortega said he will decide on the $5,300 request on Monday, after seeing the Q3 numbers"),
    47: ("14:30", "Priya kept the PO-7719 draft on hold.", "Priya kept the draft order on hold"),
    48: ("15:22", "Dana: 'If Luis won't go to $5,300, I'll rework it over the weekend.'", "Dana said she would rework it over the weekend if Luis will not go to $5,300"),
    49: ("16:45", "Northline told that PR-4471 is still undecided; no order placed.", "Northline was told the request is still undecided and no order has been placed"),
    51: ("08:35", "Dana submitted PR-4471 revision B: six refurbished Z-40s, Northline quote Q-2291-R2 at $4,740 plus $260 shipping. It replaces revision A, which was still undecided.", "Dana submitted revision B for six refurbished Z-40s, quoted at $4,740 with $260 shipping, in place of the undecided revision A"),
    52: ("09:40", "PO-7724 drafted for revision B, replacing the held PO-7719.", "a new order, PO-7724, was drafted for revision B in place of the held one"),
    # (3) Dana only checks the Sparks option on Thursday and cancels on Friday morning.
    89: ("16:45", "Dana asked the Sparks warehouse whether they can send six spare Z-40s instead.", "Dana asked the Sparks site whether it can send six spare Z-40s instead"),
    90: ("07:50", "Priya asked Northline for a return label for units 4 and 5.", "Priya asked Northline for a return label for units 4 and 5"),
    91: ("08:40", "Accounts Payable kept invoice INV-8830 on hold.", "the invoice stayed on hold"),
    # The status says nothing is owed from t92 on (the latent drops the wait there), so the same hour tells Northline.
    92: ([("09:35", "Dana cancelled PR-4471: the Sparks warehouse is sending six spare Z-40s instead. Northline to collect all six units."),
          ("09:48", "Priya told Northline the request is cancelled, so no replacement for units 4 and 5 is needed.")],
         "Dana cancelled the request because the Sparks site is sending spare Z-40s, Northline will collect the six units, and Priya told Northline no replacement is needed"),
}

# Structural counterfactual: Northline has been an active Kestrel vendor since
# 2025 with its W-9 on file, so there is no vendor-setup wait after the quote.
A_STRUCT_SURFACE: dict[int, Any] = {
    8: ("15:50", "Priya checked Northline's vendor record: an existing Kestrel vendor, W-9 on file since 2025.", "Priya found Northline already set up as a Kestrel vendor, with its W-9 on file since 2025"),
    13: ("10:41", "Quote Q-2291 received from Northline: scanners $4,860, shipping $260. Priya started the PO-7719 draft.", "Northline's quote came in at $4,860 for the scanners and $260 for shipping, and Priya began drafting the order"),
    17: ("14:45", "Priya added the six Z-40 lines to the PO-7719 draft.", "Priya put the six scanner lines on the draft order"),
    19: ("16:55", "End of day: PR-4471 still unsigned by Luis.", "the day closed without Luis's signature"),
    21: ("08:50", "Kevin Marsh confirmed PO-7719 should go to Northline's orders desk.", "Kevin Marsh said the order should go to Northline's orders desk"),
    22: ("09:34", "Priya copied Northline's remit-to address from the vendor record into PO-7719.", "Priya copied Northline's remit-to address into the order"),
    24: ("11:35", "Priya set the PO-7719 ship-to address to the Reno dock.", "Priya set the order's ship-to address to the Reno dock"),
    25: ("12:48", "Priya checked the PO-7719 unit prices against quote Q-2291.", "Priya checked the order's unit prices against the quote"),
    26: ("13:57", "Tom Becker (Finance) confirmed PO-7719 can go out this week.", "Tom Becker in Finance cleared the order to go out this week"),
    27: ("14:36", "PO-7719 draft passed Priya's first review.", "the draft order passed Priya's first review"),
    28: ("15:44", "Priya added Kevin Marsh as the Northline contact on PO-7719.", "Priya put Kevin Marsh on the draft order as Northline's contact"),
}

# Log entries about other requests for the lexical-decoy register, keyed by the
# action whose vocabulary they borrow. Each entry is about its own request (a
# fresh PR number per tick and slot, all older than PR-4471), so no request is
# ever logged in two states or has the same event logged twice.
A_DECOYS = {
    "continue": [
        "PR-{pr} ({item}): Priya keeps processing the purchase order; nothing is outstanding from the vendor.",
        "PR-{pr} ({item}) is open and needs no new approval; its intake review continues.",
        "PR-{pr} ({item}): processing continues at the purchase order step.",
        "PR-{pr} ({item}): the current step is receiving, and processing continues as normal.",
        "PR-{pr} ({item}): the purchase order step continues; the vendor owes nothing.",
        "PR-{pr} ({item}): Priya keeps processing the intake review.",
    ],
    "wait": [
        "PR-{pr} ({item}) is held up waiting for Coastline Packaging's vendor form.",
        "PR-{pr} ({item}): waiting for the pending delivery from the vendor; it has not arrived.",
        "PR-{pr} ({item}) is waiting on a quote from outside Procurement.",
        "PR-{pr} ({item}): the vendor's reply is still pending.",
        "PR-{pr} ({item}) is held up until the vendor's W-9 arrives.",
        "PR-{pr} ({item}): waiting for the pending vendor delivery.",
    ],
    "request_approval": [
        "PR-{pr} ({big}, {amt}) sent to Luis Ortega to request approval.",
        "PR-{pr} ({big}): the {amt} total is above $5,000, so approval was requested from Luis Ortega.",
        "PR-{pr} ({big}): the approval on file does not cover the new {amt} total; approval requested again.",
        "PR-{pr} ({big}, {amt}) is with Luis Ortega for approval.",
        "PR-{pr} ({big}): approval requested from Luis Ortega for the {amt} total.",
        "PR-{pr} ({big}): the approval on file covers $4,000, so the {amt} total went to Luis for approval.",
    ],
    "stop": [
        "PR-{pr} ({item}) was cancelled by its requester.",
        "PR-{pr} ({item}) was rejected by its approver and stopped.",
        "PR-{pr} ({item}) cancelled; Facilities found stock.",
        "PR-{pr} ({item}) was rejected by Finance and closed.",
        "PR-{pr} ({item}) was cancelled by the requester and archived.",
        "PR-{pr} ({item}) stopped after its approver rejected it.",
    ],
}
A_DECOY_ITEMS = [
    "label printer ribbons", "dock mats", "safety vests", "cable ties", "shrink-wrap film", "pallet labels", "pallet wrap",
    "hand trucks", "office chairs", "first-aid kits", "ear defenders", "desk lamps", "toner cartridges", "breakroom chairs",
    "printer paper", "spare batteries", "walkie-talkies", "tape guns", "box cutters", "hi-vis jackets", "cold-store gloves",
    "strapping tools", "stretch hoods", "anti-fatigue mats", "dock bumpers",
]
A_DECOY_BIG = [
    "loading-dock fans", "forklift tyres", "racking repair", "conveyor belt", "security cameras", "dock leveller",
    "pallet wrapper", "yard lighting", "reach-truck service", "cold-room door", "label printers", "mezzanine gate",
]
# Two request numbers per tick (first and second decoy entry), all distinct.
A_DECOY_PR = seeded("workflow_a-decoy-pr").sample(range(4200, 4460), 200)
# The action that competes with gold under the priority order, most of the time.
A_RIVAL = {"continue": ["wait", "request_approval"], "wait": ["continue", "request_approval"], "request_approval": ["wait", "continue"], "stop": ["continue", "wait"]}
# Ticks where the quote is always shown without its total: the quote, substitution and revision-B hours.
A_SUM_ONLY = {13, 14, 39, 40, 51, 52}
A_DECOY_MIN = [3, 9, 16, 22, 27, 33, 38, 44, 49, 57]


class ProcurementRequest(Scenario):
    family = FAMILY
    scenario_id = "workflow_a"
    title = "Controlling a procurement request through purchasing and approval"
    tier = "easy"
    difficulty_features = [
        "single_choice_question",
        "four_options_with_use_when",
        "four_rule_priority_policy",
        "amount_threshold",
        "strict_threshold_boundary",
        "one_step_addition",
        "approval_coverage_comparison",
    ]
    decision_structures = ["maintain", "wait", "escalate", "terminate", "recover", "resolve-conflict"]
    deadline_steps = 2

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
                "rev": "A",
                "qty": 6,
                "model": "Z-40",
                "vendor": None,
                "quote": None,
                "items": None,
                "shipping": None,
                "estimate": 4300,
                "total": 4300,
                "step": "intake",
                "po": None,
                "waiting_on": None,
                "approval": {"granted": None, "pending": None},
                "stopped": None,
            }
        )
        approved = {"amount": 5120, "when": "Wed 3 Jun 07:58", "kind": "approval"}
        events: dict[int, tuple[dict[str, Any], str]] = {
            2: ({}, "Another request going to Luis for approval is not this request."),
            5: ({"vendor": "new"}, ""),
            6: ({"step": "quote", "waiting_on": "quote"}, "Quote requested from Northline; nothing to do until it arrives."),
            10: ({}, "A catalogue with list prices is not the formal quote."),
            13: ({"quote": "Q-2291", "items": 4860, "shipping": 260, "total": 5120, "step": "vendor_setup", "waiting_on": "w9"},
                 "Quote in: 4,860 + 260 = 5,120 (the items alone are below 5,000), above 5,000 with no approval; W-9 also outstanding, but the approval rule comes first."),
            14: ({"approval": {"granted": None, "pending": "Tue 2 Jun 11:20"}}, "Approval asked for but not given: still no approval on file."),
            16: ({}, "A promise to sign later is not an approval on file."),
            20: ({"approval": {"granted": approved, "pending": None}}, "Approval for 5,120 on file covers the total; the W-9 is still outstanding."),
            23: ({}, "Cancelling a product demo is not cancelling the request."),
            27: ({"step": "po", "po": "7719_draft", "waiting_on": None, "vendor": "new_active"}, "W-9 in; nothing outstanding; back to processing."),
            33: ({}, "A list-price rise from next Monday does not change quote Q-2291, which sets the total."),
            39: ({"quote": "Q-2291-R1", "items": 5040, "total": 5300, "po": "7719_held"},
                 "Revised quote: 5,040 + 260 = 5,300, more than the 5,120 approved (the items alone are below it)."),
            40: ({"model": "Z-45"}, "The request lines now show the Z-45; the revised total is still not covered."),
            41: ({"approval": {"granted": approved, "pending": "Fri 5 Jun 08:40"}}, "Revised total with Luis, undecided."),
            46: ({"stopped": {"kind": "rejected", "by": "Luis Ortega", "when": "Fri 5 Jun at 13:40"}, "approval": {"granted": approved, "pending": None}},
                 "Luis rejects the revised request."),
            51: ({"rev": "B", "qty": 6, "model": "refurbished Z-40", "quote": "Q-2291-R2", "items": 4740, "shipping": 260, "total": 5000,
                  "po": "7724_none", "approval": {"granted": None, "pending": None}, "stopped": None},
                 "Revision B: 4,740 + 260 = 5,000.00 exactly, which is not above 5,000; a new revision starts open."),
            52: ({"po": "7724_draft"}, ""),
            57: ({"step": "delivery", "po": "7724_sent", "waiting_on": "delivery"}, "PO sent; waiting for the delivery."),
            66: ({}, "A warranty offer is not on the order; the total stays 5,000."),
            72: ({"step": "receiving", "waiting_on": None}, "Delivery received; receiving inspection is Procurement's own work."),
            81: ({"waiting_on": "replacement"}, "Wrong units; waiting for Northline's answer."),
            84: ({}, "A conditional threat to cancel is not a cancellation."),
            89: ({"stopped": {"kind": "cancelled", "by": "Dana Whitfield", "when": "Thu 11 Jun at 16:45"}},
                 "Requester cancels; the pending Northline reply no longer matters (rule 1 before rule 3)."),
            90: ({"waiting_on": None}, ""),
            92: ({}, "A conditional plan to reopen is not a new revision; the cancellation stands."),
        }
        tags = span_tags(
            {
                "distractor": [2, 10, 16, 23, 33, 66, 84, 92],
                "minimal_change": [13, 20, 39],
                "recovery": [27, 51, 72],
                "hold_under_activity": [(31, 34), (60, 63), (74, 77)],
                "priority_conflict": [(13, 19), 89],
                "boundary": [(46, 50), (89, 99)],
            }
        )
        for t in range(100):
            updates, note = events.get(t, ({}, ""))
            surface = surface_of(A_SCRIPT[t])
            # The quote is shown as items and shipping without a total at the ticks where the sum decides the
            # answer, and at about one in five other quote ticks so that the phrasing does not signpost them.
            surface["sum_only"] = t in A_SUM_ONLY or (t >= 13 and pick([True, False, False, False, False], "a-sum-extra", t))
            if t >= 51:
                surface["prior"] = A_PRIOR
            surface["swap_note"] = t == 39
            tl.step(surface, tags[t], note, **updates)
        return tl.ticks

    @staticmethod
    def _resurface(ticks: list[Tick], table: dict[int, Any], indices: list[int]) -> list[Tick]:
        def make(tk: Tick, i: int) -> dict[str, Any]:
            return {**tk.surface, **surface_of(table[i])}

        return override(ticks, indices, surface=make)

    @staticmethod
    def _tag_arithmetic(ticks: list[Tick]) -> list[Tick]:
        """Tag every open-request tick whose quote is shown without its total: the reader adds items and shipping."""
        for tk in ticks:
            tk.tags = [g for g in tk.tags if g != "arithmetic"]
            if tk.surface.get("sum_only") and tk.latent["stopped"] is None:
                tk.tags.append("arithmetic")
        return ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t16-19: Luis signs on Tuesday afternoon; the W-9 is still outstanding (request_approval -> wait).
            early = {"amount": 5120, "when": "Tue 2 Jun 13:52", "kind": "approval"}
            ticks = override(ticks, range(16, 20), approval={"granted": early, "pending": None}, tags=["minimal_change"],
                             note="Approval signed at 13:52 on Tuesday; W-9 still outstanding.")
            for tk in ticks[20:51]:
                if tk.latent["approval"]["granted"] and tk.latent["approval"]["granted"]["when"] == "Wed 3 Jun 07:58":
                    tk.latent["approval"]["granted"] = dict(early)
            ticks = self._resurface(ticks, A_MIN_SURFACE, [16, 18, 19, 20])
            ticks = override(ticks, [20], tags=[], note="Approval on file since Tuesday; still waiting for the W-9.")
            # (2) t46-50: Luis defers his decision instead of rejecting (stop -> request_approval).
            ticks = override(ticks, range(46, 51), stopped=None, approval={"granted": early, "pending": "Fri 5 Jun 08:40"}, tags=["minimal_change"],
                             note="Decision deferred to Monday; the revised total is still not covered by an approval.")
            ticks = self._resurface(ticks, A_MIN_SURFACE, [46, 47, 48, 49, 51, 52])
            ticks = override(ticks, range(51, 100), surface=lambda tk, i: {**tk.surface, "prior": A_PRIOR_MIN})
            # (3) t89-91: Dana only asks Sparks on Thursday and cancels on Friday at 09:35 (stop -> wait).
            ticks = override(ticks, range(89, 92), stopped=None, waiting_on="replacement", tags=["minimal_change"],
                             note="Not cancelled yet; Northline's answer is still outstanding.")
            ticks = override(ticks, range(92, 100), stopped={"kind": "cancelled", "by": "Dana Whitfield", "when": "Fri 12 Jun at 09:35"})
            ticks = self._resurface(ticks, A_MIN_SURFACE, [89, 90, 91, 92])
            ticks = override(ticks, [92], tags=["boundary"], note="Dana cancels on Friday morning.")
        elif variant == "structural_cf":
            # Northline is an existing vendor: after the quote the request goes straight to the purchase order.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for t, tk in enumerate(ticks):
                if t >= 5:
                    tk.latent["vendor"] = "existing"
                if 13 <= t <= 26:
                    tk.latent.update({"step": "po", "po": "7719_draft", "waiting_on": None})
            ticks = self._resurface(ticks, A_STRUCT_SURFACE, sorted(A_STRUCT_SURFACE))
            ticks = override(ticks, [13, 14], tags=[],
                             note="4,860 + 260 = 5,120 is above 5,000 with no approval; nothing is owed by Northline, whose W-9 is on file.")
            ticks = override(ticks, range(15, 20), tags=[], note="Approval still not given; PO drafting goes on meanwhile.")
            ticks = override(ticks, [16], tags=["distractor"], note="A promise to sign later is not an approval on file.")
            ticks = override(ticks, [20], tags=[], note="Approval for 5,120 on file; no W-9 is needed, so processing continues.")
            ticks = override(ticks, range(21, 27), note="Processing the purchase order; nothing is owed from outside Procurement.")
            ticks = override(ticks, [27], tags=[], note="")
        return self._tag_arithmetic(ticks)

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        granted = z["approval"]["granted"]
        approved = granted["amount"] if granted else 0
        if z["stopped"] is not None:
            action = "stop"
        elif z["total"] > A_THRESHOLD and approved < z["total"]:
            action = "request_approval"
        elif z["waiting_on"] is not None:
            action = "wait"
        else:
            action = "continue"
        return {"action": action}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Scanner purchase over two business weeks: intake, a quote wait, a quote whose items are below $5,000 but whose total with shipping is above it while the vendor W-9 is also outstanding (approval first), approval then a W-9 wait, PO drafting, a substitution whose total with shipping exceeds the approved amount, a rejection, a revision B at exactly $5,000.00 (not above the threshold), a delivery wait, receiving, wrong units and a requester cancellation."},
            "paraphrase": {"summary": "Same latent trajectory; purchasing/sign-off/supplier vocabulary, an hourly narrative digest instead of fields, reworded rules and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; the log gains timestamped entries about other purchase requests that borrow an action's wording (keep processing, pending, request approval, cancelled/rejected), mostly the action that competes with gold, sometimes any action."},
            "minimal_cf": {"summary": "t16-19 Luis signs on Tuesday instead of promising to (request_approval->wait); t46-50 Luis defers instead of rejecting (stop->request_approval); t89-91 Dana only asks Sparks and cancels on Friday morning (stop->wait)."},
            "structural_cf": {"summary": "Northline has been an active Kestrel vendor since 2025 with its W-9 on file, so the quote leads straight to the purchase order: t13-19 stay request_approval, and t20-26 become continue instead of a W-9 wait."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _approval(self, z: dict[str, Any], t: int) -> str:
        ap, pend = z["approval"]["granted"], z["approval"]["pending"]
        if ap is None and pend is None:
            if z["rev"] == "B":
                return pick(
                    [
                        "No approval on file for revision B.",
                        "Approval on file: none for revision B (the $5,120 approval was for revision A).",
                        "Luis Ortega has not approved revision B.",
                    ],
                    "a-ap0b",
                    t,
                )
            return pick(["Approval on file: none.", "No approval from Luis Ortega is on file.", "Luis Ortega has not approved anything for this request."], "a-ap0", t)
        if ap is None:
            return pick(
                [
                    f"Approval: sent to Luis Ortega on {pend}; he has not given it yet.",
                    f"The approval request has sat in Luis Ortega's queue since {pend}, unsigned.",
                    f"Approval requested from Luis Ortega on {pend}; still unsigned.",
                ],
                "a-append",
                t,
            )
        text = pick(
            [
                f"Approval on file: Luis Ortega approved {money(ap['amount'])} on {ap['when']}.",
                f"Luis Ortega signed an approval for {money(ap['amount'])} on {ap['when']}.",
                f"On file: Luis Ortega's approval of {money(ap['amount'])} ({ap['when']}).",
            ],
            "a-apok",
            t,
        )
        if pend:
            text += pick(
                [
                    f" The revised total was sent to him on {pend}; no decision yet.",
                    f" He has had the revised total since {pend} and has not decided.",
                    f" A request to approve the revised total has been waiting with him since {pend}.",
                ],
                "a-append2",
                t,
            )
        return text

    def _amount(self, z: dict[str, Any], t: int, sum_only: bool) -> str:
        if z["quote"] is None:
            return pick(
                [
                    f"Total: {money(z['estimate'])} (the requester's estimate; no vendor quote yet).",
                    f"No vendor quote yet, so the total is Dana's estimate of {money(z['estimate'])}.",
                ],
                "a-est",
                t,
            )
        if sum_only:
            return pick(
                [
                    f"Quote {z['quote']}: scanners {money(z['items'])}, shipping {money(z['shipping'])}.",
                    f"Quote {z['quote']} lists {money(z['items'])} for the scanners and {money(z['shipping'])} for shipping.",
                ],
                "a-sum",
                t,
            )
        return pick(
            [
                f"Total: {money(z['total'])} (quote {z['quote']}: scanners {money(z['items'])} + shipping {money(z['shipping'])}).",
                f"Request total {money(z['total'])}, per quote {z['quote']}.",
                f"Quote {z['quote']} totals {money(z['total'])} including {money(z['shipping'])} shipping.",
            ],
            "a-tot",
            t,
        )

    def _status(self, z: dict[str, Any], t: int, surface: dict[str, Any]) -> str:
        stop = z["stopped"]
        prior = surface.get("prior") or {}
        if stop is None:
            if z["rev"] == "A":
                parts = [
                    pick(
                        [
                            "Request open; nobody has cancelled or rejected it.",
                            "Open: not cancelled, not rejected.",
                            "Revision A is live; nobody has cancelled or rejected it.",
                            "Status: open (neither cancelled nor rejected).",
                        ],
                        "a-open",
                        t,
                    )
                ]
            else:
                parts = [
                    pick(
                        [
                            "Revision B is open; nobody has cancelled or rejected it.",
                            f"Revision B is open, not cancelled or rejected; {prior['rev']}.",
                            f"Open: revision B has not been cancelled or rejected ({prior['rev']}).",
                        ],
                        "a-openb",
                        t,
                    )
                ]
            step = pick(["Current step: {}.", "Step: {}.", "The request is at {}."], "a-step", t).format(A_STEP[z["step"]])
            if z["step"] in ("po", "delivery") and z["po"]:
                step += " " + A_PO[z["po"]].format(po=prior.get("po", ""))
            parts.append(step)
        else:
            rev, when, by = z["rev"], stop["when"], stop["by"]
            if stop["kind"] == "rejected":
                line = pick(
                    [
                        f"{by} rejected revision {rev} on {when}.",
                        f"Rejected by {by} on {when}: 'More than I signed for.'",
                        f"Revision {rev} was turned down by {by} ({when}).",
                    ],
                    "a-rej",
                    t,
                )
            else:
                line = pick(
                    [
                        f"{by} withdrew the request on {when}.",
                        f"Cancelled by the requester, {by}, on {when}.",
                        f"The requester, {by}, cancelled revision {rev} on {when}.",
                    ],
                    "a-can",
                    t,
                )
            parts = [line, pick([f"It had reached the {A_STEP_SHORT[z['step']]} step.", f"Work had got as far as {A_STEP_SHORT[z['step']]}."], "a-reach", t)]
        parts.append(self._amount(z, t, surface.get("sum_only", False)))
        parts.append(self._approval(z, t))
        # Rule 3's condition is stated at every tick, the stopped ones included.
        if z["waiting_on"]:
            parts.append(pick(A_WAIT[z["waiting_on"]], "a-wait", t))
        else:
            parts.append(pick(A_WAIT_NONE, "a-wait0", t))
        return " ".join(parts)

    @staticmethod
    def _decoy_line(target: str, i: int, slot: int) -> str:
        # Strides keep every item distinct within the three hours a log shows; amounts vary per request.
        pr = A_DECOY_PR[2 * i + slot]
        big = A_DECOY_BIG[(i + 3 * slot) % len(A_DECOY_BIG)]
        item = A_DECOY_ITEMS[(7 * i + 12 * slot) % len(A_DECOY_ITEMS)]
        amt = money(5100 + (pr * 37) % 40 * 100)
        return rotate(A_DECOYS[target], i + 3 * slot).format(pr=pr, item=item, big=big, amt=amt)

    def _decoys(self, tick: Tick, i: int) -> list[tuple[str, str]]:
        gold = self.policy(tick.latent)["action"]
        if pick([True, True, False], "a-rival-on", i):
            target = pick(A_RIVAL[gold], "a-rival", i)
        else:
            target = pick([a for a in A_OPTIONS if a != gold], "a-decoy-target", i)
        hour = a_hour(i) - 1
        m1 = pick(A_DECOY_MIN, "a-dmin", i)
        out = [(f"{hour:02d}:{m1:02d}", self._decoy_line(target, i, 0))]
        if pick([True, False, False], "a-decoy2", i):
            # Any action's wording, the gold action's included, so its absence is no cue.
            second = pick(list(A_DECOYS), "a-decoy2-target", i)
            m2 = pick([m for m in A_DECOY_MIN if m != m1], "a-dmin2", i)
            out.append((f"{hour:02d}:{m2:02d}", self._decoy_line(second, i, 1)))
        return out

    def _log(self, history: list[Tick], t: int, variant: str) -> list[str]:
        lines = []
        for i in range(max(0, t - 2), t + 1):
            entries = list(history[i].surface["entries"])
            if variant == "lexical_decoy":
                entries += self._decoys(history[i], i)
            for at, text in sorted(entries):
                lines.append(f"{A_DAYS[i // 10][:3]} {at} {text}")
        return lines

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        return {
            "time": a_clock(t),
            "request": f"PR-4471, revision {z['rev']}: {A_QTY[z['qty']]} {z['model']} handheld barcode scanners for the Reno warehouse dock.{A_SWAP_NOTE if tick.surface.get('swap_note') else ''} Requester: Dana Whitfield (warehouse supervisor). {A_VENDOR[z['vendor']]}",
            "status": self._status(z, t, tick.surface),
            "log": self._log(history, t, variant),
        }

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        s = tick.surface
        prior = s.get("prior") or {}
        parts = [f"Purchasing digest for {a_clock_long(t)}."]
        parts.append(
            f"Request PR-4471 (revision {z['rev']}) is Dana Whitfield's order for {A_QTY[z['qty']]} {z['model']} hand-held scanners for the Reno dock, {A_VENDOR_P[z['vendor']]}."
            + (A_SWAP_NOTE_P if s.get("swap_note") else "")
        )
        stop = z["stopped"]
        if stop is None:
            if z["rev"] == "A":
                parts.append(
                    pick(
                        ["It is still live; nobody has withdrawn it or turned it down.", "Nobody has withdrawn it or turned it down.", "It remains active, neither withdrawn nor turned down."],
                        "ap-open",
                        t,
                    )
                )
            else:
                parts.append(
                    pick(
                        [
                            "Revision B is live; nobody has withdrawn or turned it down.",
                            f"Revision B is live and has not been withdrawn or turned down; {prior['rev_p']}.",
                            f"Nobody has withdrawn or turned down revision B, which took the place of revision A ({prior['rev_p']}).",
                        ],
                        "ap-openb",
                        t,
                    )
                )
            line = f"It is at {A_STEP_P[z['step']]}."
            if z["step"] in ("po", "delivery") and z["po"]:
                line += " " + A_PO_P[z["po"]].format(po=prior.get("po_p", ""))
            parts.append(line)
        elif stop["kind"] == "rejected":
            parts.append(
                pick(
                    [
                        f"{stop['by']} turned revision {z['rev']} down on {stop['when']}, when it had reached {A_STEP_P[z['step']]}.",
                        f"Revision {z['rev']} was refused by {stop['by']} on {stop['when']}; it had got as far as {A_STEP_P[z['step']]}.",
                    ],
                    "ap-rej",
                    t,
                )
            )
        else:
            parts.append(
                pick(
                    [
                        f"The requester, {stop['by']}, withdrew it on {stop['when']}, when it had reached {A_STEP_P[z['step']]}.",
                        f"{stop['by']} called the request off on {stop['when']}; it had got as far as {A_STEP_P[z['step']]}.",
                    ],
                    "ap-can",
                    t,
                )
            )
        if z["quote"] is None:
            parts.append(f"No supplier quote exists yet; Dana put the cost at {money(z['estimate'])}.")
        elif s.get("sum_only"):
            parts.append(f"Northline's quote {z['quote']} lists {money(z['items'])} for the units and {money(z['shipping'])} for freight.")
        else:
            parts.append(f"Northline's quote {z['quote']} comes to {money(z['total'])}: {money(z['items'])} for the units plus {money(z['shipping'])} for freight.")
        ap, pend = z["approval"]["granted"], z["approval"]["pending"]
        if ap is None and pend is None:
            if z["rev"] == "B":
                parts.append(pick(["Luis Ortega has signed nothing for revision B.", "No sign-off is on record for revision B; the $5,120 one belonged to revision A."], "ap-ap0b", t))
            else:
                parts.append(pick(["Luis Ortega has signed nothing for it.", "No sign-off is on record yet."], "ap-ap0", t))
        elif ap is None:
            parts.append(pick([f"It has sat with Luis Ortega for sign-off since {pend}, still unsigned.", f"Luis Ortega has had it for sign-off since {pend} and has not signed."], "ap-append", t))
        else:
            line = pick(
                [f"Luis Ortega signed off {money(ap['amount'])} on {ap['when']}.", f"A sign-off from Luis Ortega for {money(ap['amount'])} dates from {ap['when']}."],
                "ap-apok",
                t,
            )
            if pend:
                line += f" The new amount went to him on {pend} and he has not decided."
            parts.append(line)
        if z["waiting_on"]:
            parts.append(pick(A_WAIT_P[z["waiting_on"]], "ap-wait", t))
        else:
            parts.append(pick(A_WAIT_NONE_P, "ap-wait0", t))
        gist = s["gist"]
        parts.append(f"Latest entry: {gist[0].upper() + gist[1:]}.")
        if t > 0:
            parts.append(f"Before that, {history[-2].surface['gist']}.")
        return " ".join(p for p in parts if p)


# ===========================================================================
# Scenario B - release train with handoffs; two questions per decision (medium)
# ===========================================================================

B_DAYS = ["Mon 15 Jun", "Tue 16 Jun", "Wed 17 Jun", "Thu 18 Jun", "Fri 19 Jun"]
B_DAYS_LONG = ["Monday 15 June", "Tuesday 16 June", "Wednesday 17 June", "Thursday 18 June", "Friday 19 June"]
B_TICK_MIN = 30
B_VALID_MIN = 24 * 60


def b_now(t: int) -> int:
    """Minutes since Monday 00:00; twenty half-hour snapshots a day from 08:00 to 17:30."""
    return (t // 20) * 1440 + 8 * 60 + B_TICK_MIN * (t % 20)


def b_hhmm(minutes: int) -> str:
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def b_stamp(minutes: int) -> str:
    return f"{B_DAYS[minutes // 1440][:3]} {b_hhmm(minutes)}"


def b_hours(minutes: int) -> str:
    """An age such as '26 hours', '27.5 hours', '35 minutes' or '1 hour 5 minutes'."""
    h, m = divmod(minutes, 60)
    if h == 0:
        return f"{m} minutes"
    unit = "hour" if h == 1 else "hours"
    if m == 0:
        return f"{h} {unit}"
    if m == 30:
        return f"{h}.5 hours"
    return f"{h} {unit} {m} minutes"


B_SCOPE = ["checkout-api", "payment-widget", "receipts-export", "promo-engine"]
B_STAGE = {"build": "Build", "qa": "QA", "security": "Security review", "deploy": "Deploy"}
B_STAGE_P = {"build": "compile", "qa": "testing", "security": "security sign-off", "deploy": "production rollout"}
B_NEXT = {"build": "qa_team", "qa": "security_team", "security": "deploy_team"}
B_NEXT_NAME = {"build": "the QA team", "qa": "the security review team", "security": "the deploy team"}
B_NEXT_NAME_P = {"build": "the testing group", "qa": "the security sign-off group", "security": "the rollout group"}
# Regular owner and named backup per stage; the backup ids are q2 options.
B_ROSTER_ROWS = [
    ("build", "Arjun Mehta", "Divya Rao"),
    ("qa", "Sofia Marin", "Tiago Reis"),
    ("security", "Rafael Moreno", "Anika Shah"),
    ("deploy", "Olu Adeyemi", "Tom Keller"),
]
B_BACKUP_TARGET = {"Sofia Marin": "tiago", "Rafael Moreno": "anika", "Olu Adeyemi": "tom"}
B_PRONOUN = {"Sofia Marin": "she", "Rafael Moreno": "he", "Anika Shah": "she", "Tiago Reis": "he"}
B_NUM = {3: "three", 4: "four"}
B_DONE = {
    "build": "{n} signed artifacts published on Mon 12:58",
    "qa": "signed off on Tue 17:24 with every suite green",
    "security": "all three checklists signed on Thu 09:24",
}
B_PROGRESS = {
    "build": ["compiling and testing the {n} components", "build running on the release branch", "in progress"],
    "qa": ["regression runs going on staging", "test runs in progress", "in progress"],
    "security": ["review in progress", "checks under way", "in progress"],
}
B_BLOCK = {
    "pentest": [
        "blocked: every check still to do needs Bastion Labs' pen-test report on receipts-export, which has not arrived.",
        "the remaining checks all depend on Bastion Labs' receipts-export pen-test report, which has not come in.",
        "cannot go further until Bastion Labs delivers its pen-test report on receipts-export (not received yet).",
    ],
}
B_BLOCK_P = {
    "pentest": [
        "cannot move until Bastion Labs delivers its receipts-export pen-test report, which every remaining check needs",
        "is stuck: all that is left to check hangs on Bastion Labs' pen-test report on receipts-export, still not delivered",
    ],
}

B_ROLE = (
    "You are the controller of the Checkout 7.4 release train at Larkspur. The train passes through four stages in a fixed "
    "order: build, QA, security review, deploy. `roster` lists each stage's regular owner and named backup; `stage` names "
    "the current stage, who owns it right now and whether that person is at work, how far it has got, and anything it is "
    "waiting for from outside the stage (when it names nothing missing, nothing is). Once a backup has taken a stage over, "
    "the backup is that stage's owner. The deploy team may only take the train with a production change approval from "
    "Grace Liu that is at most 24 hours old. Every half hour you decide which action the train should be under right now "
    "and to whom that action is addressed; an action stays right for as long as its rule is the first rule that matches, "
    "even if it was already started earlier."
)
B_POLICY = [
    "1. If the release manager has cancelled Checkout 7.4, or a severity-1 defect is open against a component in the release scope: action = terminate the release; addressee = nobody.",
    "2. Otherwise, if the current owner of the current stage (the owner named in `stage`) is unavailable (on leave or off sick) and the stage is not finished: action = reroute; addressee = the backup named for that stage in `roster`. Once that backup has taken the stage over, the backup is its owner and this rule no longer applies while the backup is at work.",
    "3. Otherwise, if the security review is finished, the deploy team has not taken the train, and no production change approval has been granted in the last 24 hours (compare the grant time in `change_approval` with `clock`; an approval expires 24 hours after it is granted; one exactly 24 hours old still counts; a request that has not been granted is not an approval): action = request approval; addressee = Grace Liu.",
    "4. Otherwise, if the current stage is finished and the next stage's team has not taken the train yet: action = hand off; addressee = the team that runs the next stage.",
    "5. Otherwise, if the current stage cannot make progress because it is waiting for something from outside the stage (an artifact, an environment, a report, a fix) that has not arrived: action = wait; addressee = nobody.",
    "6. Otherwise: action = continue the current stage; addressee = nobody.",
]
B_FIELDS = "(`clock`, `train`, `roster`, `stage`, `change_approval`, `defects`; `channel` shows the latest messages)"
B_Q_ACTION = f"Apply the first rule that matches the current state {B_FIELDS}. Which action should the train be under right now?"
B_Q_OWNER = f"Apply the first rule that matches the current state {B_FIELDS}. To whom should the controller's action be addressed right now?"

B_ROLE_P = (
    "You run the Checkout 7.4 release pipeline at Larkspur. It goes through four stages, always in this order: compile, "
    "testing, security sign-off, production rollout. The owner list gives each stage's regular owner and the stand-in named "
    "for that stage; the account of the present stage says who owns it right now, whether that person can work, how far it "
    "has got and anything it lacks from outside the stage (if it mentions nothing missing, nothing is). A stand-in who has "
    "taken a stage over owns it from then on. The rollout group may only take the pipeline if Grace Liu gave a production "
    "change approval no more than 24 hours ago. Each half hour you settle what should be happening to the pipeline and who "
    "that move goes to; a move stays correct as long as its rule is the earliest one that fits, even if it was already set "
    "going earlier."
)
B_POLICY_P = [
    "1. When the release manager has called off Checkout 7.4, or a severity-1 bug is open against one of the components this release ships: kill the train; addressee: nobody.",
    "2. If not, and the person who owns the stage the train is in right now cannot work (on leave, off sick) while that stage is unfinished: reassign it; addressee: the stand-in named for that stage. Once the stand-in has taken the stage over, the stand-in owns it and this rule stops applying while the stand-in is at work.",
    "3. If not, and security sign-off is done, the rollout group has not taken the train, and no production change approval was given within the past 24 hours (approvals lapse 24 hours after they are given; one given exactly 24 hours ago still holds; an ungranted request is not an approval): seek approval; addressee: Grace Liu.",
    "4. If not, and the stage the train is in is done while the group running the next stage has not taken it yet: give it to that group; addressee: the group that runs the next stage.",
    "5. If not, and the stage the train is in cannot move because it lacks something owed from outside the stage (an artifact, an environment, a report, a fix) that has not come: pause; addressee: nobody.",
    "6. Anything else: keep the present stage going; addressee: nobody.",
]
B_Q_ACTION_P = "Work down the rules and take the earliest that fits the situation described. What should happen to the pipeline at this moment?"
B_Q_OWNER_P = "Work down the rules and take the earliest that fits the situation described. Who should that move go to at this moment?"

B_ACTIONS = {
    "continue": "Let the current stage carry on with its owner.",
    "wait": "Hold the train until the missing input arrives.",
    "request_approval": "Ask (or chase) the change approver to sign the production change.",
    "reroute": "Move the current stage to a different owner.",
    "handoff": "Pass the train to the team running the next stage.",
    "terminate": "Terminate the train and cancel this release.",
}
B_ACTIONS_P = {
    "continue": "Keep the present stage going as it is.",
    "wait": "Pause the pipeline for the input it lacks.",
    "request_approval": "Seek (or chase) a signature on the production change.",
    "reroute": "Reassign the present stage to someone else.",
    "handoff": "Give the pipeline to the next stage's group.",
    "terminate": "Kill the pipeline and call off the release.",
}
B_ACTIONS_D = {
    "continue": "Let the current stage carry on with its present owner.",
    "wait": "Hold the train until the missing input has arrived.",
    "request_approval": "Ask (or chase) the change approver to sign off the production change.",
    "reroute": "Move the current stage over to a different owner.",
    "handoff": "Pass the train on to the team running the next stage.",
    "terminate": "Terminate the release train and cancel this release.",
}
B_OWNERS = {
    "qa_team": "The QA team, led by Sofia Marin",
    "security_team": "The security review team, led by Rafael Moreno",
    "deploy_team": "The deploy team, led by Olu Adeyemi",
    "tiago": "Tiago Reis, the named QA backup",
    "anika": "Anika Shah, the named security review backup",
    "tom": "Tom Keller, the named deploy backup",
    "grace": "Grace Liu, the production change approver",
    "none": "Nobody; this action has no addressee",
}
B_OWNERS_P = {
    "qa_team": "Sofia Marin's testing group",
    "security_team": "Rafael Moreno's security sign-off group",
    "deploy_team": "Olu Adeyemi's rollout group",
    "tiago": "Tiago Reis, stand-in for testing",
    "anika": "Anika Shah, stand-in for security sign-off",
    "tom": "Tom Keller, stand-in for the rollout",
    "grace": "Grace Liu, who signs production changes",
    "none": "No addressee for this move",
}

# Surface content per tick: (minute stamp, channel message, third-person gist),
# or ([(stamp, message), ...], gist) for the half hours with a burst of messages.
B_SCRIPT: list[Any] = [
    # Mon 15 Jun (t0-t19)
    ("07:55", "Arjun Mehta: 7.4 build started from the release branch, four components queued.", "Arjun Mehta started the 7.4 build with four components queued"),
    ("08:26", "Arjun Mehta: checkout-api compiled, unit tests running.", "Arjun reports checkout-api compiled and its unit tests running"),
    ("08:57", "Divya Rao: payment-widget bundle is 3% smaller than in 7.3.", "Divya Rao notes the payment-widget bundle shrank by 3% against 7.3"),
    ("09:24", "Arjun Mehta: receipts-export tests green, 412 of 412.", "Arjun says all 412 receipts-export tests passed"),
    ("09:58", "Release bot: Mobile 5.1 train terminated after a severity-1 bug in the iOS login screen.", "the release bot announced that the separate Mobile 5.1 train was terminated over an iOS login bug"),
    ("10:21", "Arjun Mehta: promo-engine build started; it's the slow one, roughly two hours.", "Arjun kicked off the slow promo-engine build, about two hours"),
    ("10:52", "Divya Rao: last week's signing-key rotation causes no issues on 7.4 so far.", "Divya confirms last week's signing-key rotation is not bothering 7.4"),
    ("11:27", "Arjun Mehta: promo-engine at 60%, no warnings.", "Arjun says promo-engine is 60% built with no warnings"),
    ("11:58", "Olu Adeyemi: the deploy team has pencilled in Thursday afternoon for 7.4.", "Olu Adeyemi says the deploy team pencilled 7.4 in for Thursday afternoon"),
    ("12:25", "Arjun Mehta: promo-engine done, packaging all four artifacts.", "Arjun finished promo-engine and is packaging the artifacts"),
    ("12:58", "Arjun Mehta: build finished; four signed artifacts published to the release repo.", "Arjun announced the build finished with four signed artifacts published"),
    ("13:22", "Arjun Mehta: build manifest posted in the train doc.", "Arjun posted the build manifest in the train doc"),
    ("13:55", "Sofia Marin: QA is finishing the 7.3.2 hotfix run; we'll take 7.4 right after.", "Sofia Marin says QA will take 7.4 once the 7.3.2 hotfix run is done"),
    ("14:28", "Release bot: 7.4 build artifacts have waited 90 minutes for pickup.", "the release bot flags the artifacts as waiting ninety minutes for pickup"),
    ("14:57", "Sofia Marin: QA has taken 7.4; regression suite starting on staging.", "Sofia says QA has taken 7.4 and started regression on staging"),
    ([("15:06", "Tiago Reis: 1,240 regression cases queued across the four components."),
      ("15:14", "Sofia Marin: checkout-api goes first, the other suites after it."),
      ("15:24", "Release bot: staging capacity reserved for 7.4 until Wednesday.")],
     "Tiago queued 1,240 regression cases, Sofia put checkout-api first and the bot reserved staging for 7.4"),
    ([("15:38", "Sofia Marin: checkout-api regression 30% through, all passing."),
      ("15:47", "Tiago Reis: promo-engine test fixtures refreshed from production data."),
      ("15:56", "Sofia Marin: payment-widget smoke tests passed on staging.")],
     "Sofia reports checkout-api regression 30% done and passing, Tiago refreshed the promo-engine fixtures and the payment-widget smoke tests passed"),
    ([("16:05", "Tiago Reis: two payment-widget visual diffs reviewed; both expected."),
      ("16:14", "Sofia Marin: checkout-api regression 60% through."),
      ("16:25", "Divya Rao: staging logs are clean for the last hour.")],
     "Tiago cleared two expected visual diffs, checkout-api regression reached 60% and Divya found the staging logs clean"),
    ([("16:38", "Sofia Marin: checkout-api regression done, 410 of 410."),
      ("16:46", "Tiago Reis: payment-widget suite loaded for tomorrow."),
      ("16:54", "Sofia Marin: exploratory session on the promo codes screen booked for 09:00 tomorrow.")],
     "Sofia finished the checkout-api regression, Tiago loaded the payment-widget suite and a promo-codes session was booked for the morning"),
    ("17:26", "Tiago Reis: overnight suite scheduled, results by 08:00.", "Tiago scheduled the overnight suite"),
    # Tue 16 Jun (t20-t39)
    ("07:52", "Sofia Marin: heads-up, I'm on leave from Monday 22 Jun for two weeks; Tiago covers QA from then.", "Sofia Marin gave notice that she is on leave for two weeks from next Monday, with Tiago covering QA then"),
    ("08:24", "Sofia Marin: overnight suite: 1,198 passed, 42 still running.", "Sofia reports 1,198 overnight cases passed and 42 still running"),
    ("08:58", "Tiago Reis: promo codes exploratory session under way.", "Tiago started the promo-codes exploratory session"),
    ("09:27", "Sofia Marin: overnight suite finished, three failures to triage.", "Sofia says the overnight suite finished with three failures to triage"),
    ("09:55", "Tiago Reis: logged DEF-881, severity 2, promo-engine: stacked codes show the wrong discount label. Fix in progress.", "Tiago logged a severity-2 promo-engine bug about wrong discount labels, with a fix in progress"),
    ("10:23", "Sofia Marin: the other two failures were flaky tests; reruns passed.", "Sofia found the other two failures were flaky and passed on rerun"),
    ("10:56", "Arjun Mehta: DEF-881 fix merged to the release branch.", "Arjun merged the DEF-881 fix"),
    ("11:25", "Tiago Reis: DEF-881 fix verified on staging; defect closed.", "Tiago verified the fix and closed DEF-881"),
    ("11:54", "Sofia Marin: migraine, I have to go home now and won't be back before Thursday. My notes are in the train doc.", "Sofia went home with a migraine and will not be back before Thursday"),
    ("12:20", "Release bot: 7.4 QA is still assigned to Sofia Marin; 180 payment-widget cases not started.", "the bot shows QA still assigned to Sofia with 180 payment-widget cases not started"),
    ("12:55", "Tiago Reis: finishing the Mobile 5.2 smoke tests first, then I can look at 7.4.", "Tiago is finishing the Mobile 5.2 smoke tests before he can look at 7.4"),
    ("13:26", "Tiago Reis: I've taken over 7.4 QA from Sofia; starting the 180 payment-widget cases.", "Tiago took QA over from Sofia and started the 180 payment-widget cases"),
    ("13:58", "Tiago Reis: payment-widget cases 40 of 180 passed.", "Tiago has 40 of 180 payment-widget cases passing"),
    ("14:24", "Divya Rao: the Payments 3.2 train is blocked on an expired vendor certificate.", "Divya mentioned that the separate Payments 3.2 train is blocked on an expired vendor certificate"),
    ("14:56", "Tiago Reis: payment-widget cases 90 of 180 passed.", "Tiago has 90 of 180 payment-widget cases passing"),
    ("15:27", "Tiago Reis: checkout-api contract tests passed against the payments sandbox.", "Tiago's checkout-api contract tests passed"),
    ("15:58", "Release bot: staging health check failed at 15:55.", "the bot logged a failed staging health check at 15:55"),
    ("16:26", "Release bot: staging health check green again since 16:04. Tiago Reis: payment-widget 180 of 180 passed.", "the staging health check is green again and Tiago finished all 180 payment-widget cases"),
    ("16:55", "Tiago Reis: filling in the QA sign-off checklist.", "Tiago is completing the QA sign-off checklist"),
    ("17:24", "Tiago Reis: QA signed off 7.4, all suites green, report attached.", "Tiago signed QA off with every suite green"),
    # Wed 17 Jun (t40-t59)
    ("07:41", "Release bot: Grace Liu approved production change CHG-5520 for Checkout 7.4 at 07:30.", "the bot announced Grace Liu's 07:30 approval of production change CHG-5520"),
    ("08:22", "Tiago Reis: QA report linked in the train doc for the security review team.", "Tiago linked the QA report for the security team"),
    ("08:51", "Rafael Moreno: saw Tiago's QA report; security will take 7.4 once our stand-up is over, around 09:20.", "Rafael says security will take 7.4 once their stand-up is over, around twenty past nine"),
    ("09:26", "Rafael Moreno: security review started. The static checks were done during QA week; everything left needs Bastion Labs' pen-test report on receipts-export, which hasn't arrived.", "Rafael started the security review, but everything left needs Bastion Labs' receipts-export pen-test report, which has not come"),
    ("09:57", "Rafael Moreno: pinged Bastion Labs; the report is in final QA on their side.", "Rafael heard from Bastion Labs that the report is in their final QA"),
    ("10:24", "Bastion Labs (email): report expected early afternoon.", "Bastion Labs expects to send it early afternoon"),
    ("10:55", "Anika Shah: happy to be a second pair of eyes once the report lands.", "Anika Shah offered to help once the report lands"),
    ("11:26", "Rafael Moreno: still waiting on Bastion; nothing else I can check until then.", "Rafael has nothing he can check until Bastion delivers"),
    ("11:57", "Rafael Moreno: feeling awful, going home sick now; off for the rest of the week.", "Rafael went home sick for the rest of the week"),
    ("12:25", "Release bot: 7.4 security review is still assigned to Rafael Moreno.", "the bot shows the review still assigned to Rafael"),
    ("12:54", "Olu Adeyemi: is 7.4 still on for tomorrow's deploy window?", "Olu asked whether 7.4 still makes tomorrow's window"),
    ("13:22", "Bastion Labs (email): report slipping to about 15:00.", "Bastion Labs says the report slips to around three"),
    ("13:56", "Tiago Reis: QA is on standby in case security needs a retest.", "Tiago says QA is on standby for retests"),
    ("14:27", "Release bot: 7.4 security review idle for 2.5 hours; assignee out sick.", "the bot flags the review idle for two and a half hours with its assignee out sick"),
    ("14:58", "Anika Shah: I've taken over the 7.4 security review from Rafael. Bastion's pen-test report arrived at 14:50; reading it now.", "Anika took over the review from Rafael and is reading Bastion's report, which came at 14:50"),
    ("15:26", "Anika Shah: pen-test report: no critical findings on receipts-export, two low ones.", "Anika found no critical findings in the report, only two low ones"),
    ("15:57", "Anika Shah: checking the two low findings against the threat model.", "Anika is checking the low findings against the threat model"),
    ("16:24", "Anika Shah: both low receipts-export findings accepted; notes added to the threat model.", "Anika accepted both low receipts-export findings and noted them in the threat model"),
    ("16:55", "Anika Shah: two of the three security checklists signed; data handling is left for tomorrow morning.", "Anika signed two of three checklists and left data handling for the morning"),
    ("17:25", "Anika Shah: parking the data-handling checklist overnight; I'll start it first thing tomorrow.", "Anika parked the last checklist overnight, to start it first thing tomorrow"),
    # Thu 18 Jun (t60-t79)
    ("07:58", "Anika Shah: starting the data-handling checklist.", "Anika started the data-handling checklist"),
    ("08:27", "Anika Shah: receipts-export masks customer addresses in its logs; confirmed.", "Anika confirmed address masking in the receipts-export logs"),
    ("08:56", "Anika Shah: retention settings look right; writing the summary.", "Anika is writing the summary after checking retention settings"),
    ("09:24", "Anika Shah: security review complete, all three checklists signed; 7.4 is cleared on security.", "Anika completed the security review with all three checklists signed"),
    ("09:52", "Anika Shah: security summary posted to the train doc.", "Anika posted the security summary"),
    ("10:22", "Grace Liu: in the change board meeting until 12:00; unavailable until then.", "Grace Liu is in the change board meeting and unavailable until noon"),
    ("10:56", "Olu Adeyemi: the deploy team is ready for 7.4 whenever it comes over.", "Olu says the deploy team is ready whenever 7.4 comes over"),
    ("11:23", "Tiago Reis: QA stood down from 7.4 standby.", "Tiago stood QA down from standby"),
    ("11:55", "Grace Liu: the board is running ten minutes late.", "Grace says the board is running late"),
    ("12:26", "Grace Liu: approved production change CHG-5520 for Checkout 7.4 at 12:25.", "Grace approved production change CHG-5520 at 12:25"),
    ("12:54", "Anika Shah: deploy handoff note is in the train doc.", "Anika put the deploy handoff note in the train doc"),
    ("13:25", "Olu Adeyemi: finishing the 13:00 infrastructure change first, then 7.4.", "Olu is finishing an infrastructure change before taking 7.4"),
    ("13:58", "Release bot: 7.4 has sat in the deploy queue since Grace's 12:25 approval.", "the bot says 7.4 has sat in the deploy queue since the 12:25 approval"),
    ("14:26", "Olu Adeyemi: infrastructure change done; the deploy team will take 7.4 before 15:00.", "Olu finished the infrastructure change and says his team will take 7.4 before three"),
    ("14:58", "Olu Adeyemi: the deploy team has taken 7.4; canary at 5% of traffic started.", "Olu's team took 7.4 and started a 5% canary"),
    ("15:24", "Tom Keller: 5% canary: error rate 0.2%, latency flat.", "Tom Keller sees a 0.2% error rate and flat latency at 5%"),
    ("15:55", "Olu Adeyemi: receipts-export workers rolled onto the canary pods.", "Olu rolled receipts-export workers onto the canary pods"),
    ("16:26", "Tom Keller: canary checkout conversion within 0.1 points of control.", "Tom says canary conversion is within 0.1 points of control"),
    ("16:54", "Olu Adeyemi: holding the canary at 5% overnight, per the runbook.", "Olu is holding the canary at 5% overnight as the runbook says"),
    ("17:22", "Release bot: DEF-902 opened, severity 1, search-service: autocomplete timeouts. Owner: Search team.", "the bot opened a severity-1 search-service defect for autocomplete timeouts, owned by the Search team"),
    # Fri 19 Jun (t80-t99)
    ([("07:41", "Tom Keller: overnight canary clean: 0.2% errors, no alerts on 7.4 components."),
      ("07:49", "Release bot: DEF-902 (search-service) still open with the Search team."),
      ("07:57", "Olu Adeyemi: morning checks done; plan is 25% after 08:15.")],
     "Tom reports a clean overnight canary, DEF-902 is still with the Search team and Olu plans to go to 25% after quarter past eight"),
    ([("08:06", "Tom Keller: payment-widget p95 latency 180 ms, same as 7.3."),
      ("08:17", "Olu Adeyemi: raising the canary to 25%."),
      ("08:25", "Release bot: canary weight now 25%.")],
     "Tom sees payment-widget latency unchanged and Olu raised the canary to 25%"),
    ([("08:36", "Tom Keller: 25% canary: checkout conversion within 0.1 points of control."),
      ("08:47", "Search team: DEF-902 mitigated with a config rollback; their own 2.8 rollout is halted until Monday."),
      ("08:54", "Olu Adeyemi: checkout-api latency normal at 25%.")],
     "conversion holds at 25%, the Search team mitigated DEF-902 and halted their own 2.8 rollout until Monday, and checkout-api latency is normal"),
    ([("09:05", "Tom Keller: 25% canary: payment success rate 99.6%, same as control."),
      ("09:16", "Divya Rao: no new crash reports from the payment-widget SDK."),
      ("09:27", "Olu Adeyemi: next step 50% at about 10:25 if this holds.")],
     "payment success matches control at 25%, Divya sees no new crash reports and Olu plans 50% for about 10:25"),
    ([("09:38", "Tom Keller: error budget for the week still 92% unspent."),
      ("09:47", "Search team: DEF-902 closed after their fix deployed."),
      ("09:55", "Olu Adeyemi: canary dashboards shared with Support.")],
     "the error budget is barely touched, the Search team closed DEF-902 and Olu shared the canary dashboards with Support"),
    ("10:24", "Olu Adeyemi: raising the canary to 50%.", "Olu raised the canary to 50%"),
    ("10:57", "Tom Keller: 50% canary steady; receipts-export queue depth normal.", "Tom says the 50% canary is steady"),
    ("11:23", "Tom Keller: DEF-907 opened, severity 1, receipts-export: exported receipts show another customer's address.", "Tom opened a severity-1 receipts-export defect: receipts show another customer's address"),
    ("11:52", "Olu Adeyemi: canary halted at 50%; routing receipts traffic back to 7.3.", "Olu halted the canary and is routing receipts traffic back to 7.3"),
    ("12:26", "Arjun Mehta: DEF-907 reproduced on the release branch; root cause in the address cache.", "Arjun reproduced DEF-907 and traced it to the address cache"),
    ("12:58", "Marcus Webb (release manager): Checkout 7.4 is cancelled. The fix goes to the 7.5 train.", "release manager Marcus Webb cancelled 7.4 and moved the fix to 7.5"),
    ("13:25", "Olu Adeyemi: rollback to 7.3 complete on all canary pods.", "Olu finished rolling the canary pods back to 7.3"),
    ([("13:34", "Tom Keller: all canary pods report 7.3 again."),
      ("13:45", "Sofia Marin: QA is adding an address-cache test to the 7.5 regression suite."),
      ("13:56", "Support: first customer ticket about a wrong address on a receipt.")],
     "every canary pod is back on 7.3, Sofia is adding an address-cache test for 7.5 and Support has its first ticket about a wrong receipt address"),
    ([("14:05", "Arjun Mehta: 7.4 release branch frozen; nothing more merges there."),
      ("14:16", "Support: two more tickets about wrong receipt addresses."),
      ("14:24", "Grace Liu: CHG-5520 closed as cancelled.")],
     "Arjun froze the 7.4 branch, Support logged two more tickets and Grace closed CHG-5520 as cancelled"),
    ([("14:38", "Tom Keller: 37 receipts were affected during the canary; Support has the list."),
      ("14:47", "Marcus Webb: customer notices go out through Support, not this channel."),
      ("14:55", "Olu Adeyemi: canary pods scaled down to zero.")],
     "Tom counted 37 affected receipts, Marcus routed customer notices through Support and Olu scaled the canary pods to zero"),
    ([("15:06", "Anika Shah: privacy review of the 37 affected receipts opened."),
      ("15:14", "Legal: the privacy review needs the receipt IDs by Monday."),
      ("15:26", "Tom Keller: receipt IDs exported for Legal.")],
     "Anika opened a privacy review of the affected receipts and Tom exported the receipt IDs Legal asked for"),
    ("15:58", "Arjun Mehta: DEF-907 fix is in review on the 7.5 branch; tests pass.", "Arjun's DEF-907 fix is in review for 7.5 with tests passing"),
    ("16:24", "Marcus Webb: post-incident review booked for Monday 10:00.", "Marcus booked a post-incident review for Monday"),
    ("16:55", "Olu Adeyemi: the deploy team released the Friday window.", "Olu released the Friday deploy window"),
    ("17:26", "Release bot: train 7.4 archived.", "the bot archived the 7.4 train"),
]
# How far the current stage has got, for ticks where the generic phrasing would
# hide a relevant detail (the sick owner's unfinished work, the two-of-three
# checklist distractor, the review after the handover).
B_PROGRESS_TICK = {
    28: "the 180 payment-widget cases have not been started",
    29: "the 180 payment-widget cases have not been started",
    30: "the 180 payment-widget cases have not been started",
    31: "Tiago has started the 180 payment-widget cases",
    32: "payment-widget cases 40 of 180 passed",
    34: "payment-widget cases 90 of 180 passed",
    36: "payment-widget cases still running on staging through the 15:55 health-check alert, about 150 of 180 passed",
    37: "all 180 payment-widget cases passed; sign-off paperwork next",
    38: "the QA sign-off checklist is being filled in",
    54: "Anika is reading Bastion's pen-test report, which arrived at 14:50",
    55: "the pen-test report shows no critical findings and two low ones",
    56: "Anika is checking the two low findings against the threat model",
    57: "low findings accepted; the three security checklists are next",
    58: "two of the three security checklists signed; data handling is left for tomorrow morning",
    59: "two of three checklists signed; the data-handling checklist is parked until tomorrow morning",
    60: "the data-handling checklist, the last of three, is under way",
    61: "data-handling checklist nearly done: log masking confirmed",
    62: "retention settings checked; Anika is writing the summary before signing the last checklist",
}
# The paraphrase digest's account of how far the stage has got while a stand-in
# owns it (t31-38, t54-62). Each entry is a reworded B_PROGRESS_TICK line (or the
# generic phrasing where there is none) that leaves the unfinished part explicit.
B_PROGRESS_TICK_P = {
    31: "Tiago has only just begun on the 180 payment-widget cases",
    32: "so far 40 of the 180 payment-widget cases have gone green",
    33: "test runs on staging are under way",
    34: "half of the 180 payment-widget cases, 90 of them, have gone green so far",
    35: "Tiago's test runs are going ahead on staging",
    36: "roughly 150 of the 180 payment-widget cases are green and the rest keep running on staging in spite of the failed health check",
    37: "every one of the 180 payment-widget cases is green, but the sign-off paperwork remains to be done",
    38: "Tiago is working through the sign-off checklist, which he has not completed",
    54: "Anika has only begun reading the pen-test report Bastion delivered at 14:50",
    55: "Anika has been through the report, which holds two low findings and nothing critical, and none of the three checklists is signed",
    56: "Anika is weighing the two low findings against the threat model, and no checklist has been signed",
    57: "both low findings have been accepted, and all three checklists remain to be signed",
    58: "only two of the three checklists carry a signature, and the data-handling one waits for tomorrow morning",
    59: "the data-handling checklist, the third of three, is unsigned and set aside until the morning",
    60: "Anika is working on the data-handling checklist, the only one of the three without a signature",
    61: "log masking has been confirmed and the data-handling checklist is close to done, though not signed",
    62: "retention settings are checked and Anika is drafting the summary; the last checklist awaits her signature",
}
B_PROGRESS_P = {
    "qa": ["test runs on staging are under way", "testing work is going ahead"],
    "security": ["the review work is going on", "checks are under way"],
}

B_MIN_SURFACE: dict[int, Any] = {
    # (1) Rafael is still at his desk at noon and goes home sick at 13:22 instead.
    48: ("11:57", "Rafael Moreno: eating lunch at my desk, still watching for Bastion's report.", "Rafael is eating lunch at his desk and watching for Bastion's report"),
    49: ("12:25", "Release bot: 7.4 security review assigned to Rafael Moreno, waiting on Bastion.", "the bot shows the review assigned to Rafael and waiting on Bastion"),
    51: ("13:22", "Rafael Moreno: feeling awful, going home sick now; off for the rest of the week. Bastion now says about 15:00 for the report.", "Rafael went home sick for the rest of the week, and Bastion now expects to deliver around three"),
    53: ("14:27", "Release bot: 7.4 security review idle since 13:22; assignee out sick.", "the bot flags the review idle since 13:22 with its assignee out sick"),
    # (2) Grace re-approves at 10:30 on Wednesday, so the approval is exactly 24 hours old at Thu 10:30.
    45: ([("10:24", "Bastion Labs (email): report expected early afternoon."),
          ("10:30", "Release bot: Grace Liu re-approved production change CHG-5520 for Checkout 7.4 at 10:30, after the rollback plan was updated.")],
         "Bastion Labs expects the report early afternoon, and Grace Liu re-approved CHG-5520 at 10:30 after the rollback plan was updated"),
    # (3) DEF-907 is first filed at severity 2 with a harmless symptom and raised to severity 1 at 12:41.
    87: ("11:23", "Tom Keller: DEF-907 opened, severity 2 pending triage, receipts-export: the receipt PDF footer shows the wrong support phone number.", "Tom opened DEF-907 at severity 2 pending triage: receipt footers show the wrong support number"),
    88: ("11:52", "Olu Adeyemi: canary continues at 50% as scheduled; DEF-907 triage runs in parallel.", "Olu keeps the canary at 50% as scheduled while DEF-907 is triaged"),
    89: ("12:26", "Arjun Mehta: DEF-907 reproduced on the release branch; root cause in the address cache, checking what else it affects.", "Arjun reproduced DEF-907, traced it to the address cache and is checking what else it affects"),
    90: ([("12:41", "Tom Keller: DEF-907 raised to severity 1: the same cache bug puts another customer's address on some receipts."),
          ("12:49", "Olu Adeyemi: canary halted at 50%; routing receipts traffic back to 7.3."),
          ("12:58", "Marcus Webb (release manager): Checkout 7.4 is cancelled. The fix goes to the 7.5 train.")],
         "DEF-907 was raised to severity 1 because some receipts show another customer's address, Olu halted the canary and release manager Marcus Webb cancelled 7.4"),
}

# Structural counterfactual: receipts-export was removed from the 7.4 scope on
# Fri 12 Jun (moved to 7.5). No pen-test report is needed for the security
# review, and DEF-907 in receipts-export is a 7.5 problem.
B_STRUCT_SURFACE: dict[int, Any] = {
    0: ("07:55", "Arjun Mehta: 7.4 build started from the release branch, three components queued.", "Arjun Mehta started the 7.4 build with three components queued"),
    3: ("09:24", "Arjun Mehta: payment-widget tests green, 388 of 388.", "Arjun says all 388 payment-widget tests passed"),
    9: ("12:25", "Arjun Mehta: promo-engine done, packaging all three artifacts.", "Arjun finished promo-engine and is packaging the artifacts"),
    10: ("12:58", "Arjun Mehta: build finished; three signed artifacts published to the release repo.", "Arjun announced the build finished with three signed artifacts published"),
    15: ([("15:06", "Tiago Reis: 960 regression cases queued across the three components."),
          ("15:14", "Sofia Marin: checkout-api goes first, the other suites after it."),
          ("15:24", "Release bot: staging capacity reserved for 7.4 until Wednesday.")],
         "Tiago queued 960 regression cases, Sofia put checkout-api first and the bot reserved staging for 7.4"),
    21: ("08:24", "Sofia Marin: overnight suite: 918 passed, 42 still running.", "Sofia reports 918 overnight cases passed and 42 still running"),
    43: ("09:26", "Rafael Moreno: security review started on the three 7.4 components; no pen-test report is needed this time.", "Rafael started the security review of the three components, with no pen-test report needed this time"),
    44: ("09:57", "Rafael Moreno: checkout-api static analysis reviewed, clean.", "Rafael found checkout-api's static analysis clean"),
    45: ("10:24", "Rafael Moreno: payment-widget token handling reviewed, no findings.", "Rafael reviewed payment-widget token handling without findings"),
    46: ("10:55", "Anika Shah: happy to be a second pair of eyes if you want one.", "Anika Shah offered a second pair of eyes"),
    47: ("11:26", "Rafael Moreno: moving on to the promo-engine dependency scan.", "Rafael moved on to the promo-engine dependency scan"),
    51: ("13:22", "Divya Rao: receipts-export changes are parked on the 7.5 branch as planned.", "Divya confirms the receipts-export changes are parked on the 7.5 branch"),
    54: ("14:58", "Anika Shah: I've taken over the 7.4 security review from Rafael; picking up at the promo-engine dependency scan.", "Anika took over the review from Rafael and picked up at the promo-engine scan"),
    55: ("15:26", "Anika Shah: promo-engine dependency scan: no critical findings, two low ones.", "Anika's promo-engine scan found no critical issues, only two low ones"),
    57: ("16:24", "Anika Shah: payment-widget content security headers checked, fine.", "Anika checked the payment-widget security headers"),
    61: ("08:27", "Anika Shah: checkout-api masks customer addresses in its logs; confirmed.", "Anika confirmed address masking in the checkout-api logs"),
    76: ("15:55", "Olu Adeyemi: payment-widget assets rolled onto the canary pods.", "Olu rolled payment-widget assets onto the canary pods"),
    86: ("10:57", "Tom Keller: 50% canary steady; checkout-api latency normal.", "Tom says the 50% canary is steady"),
    87: ("11:23", "Release bot: DEF-907 opened, severity 1, receipts-export: exported receipts show another customer's address. Found by the 7.5 test team.", "the 7.5 test team opened a severity-1 receipts-export defect: receipts show another customer's address"),
    88: ("11:52", "Olu Adeyemi: the 7.4 canary pods do not run receipts-export; canary stays at 50% as scheduled.", "Olu notes the 7.4 canary pods do not run receipts-export and keeps the canary at 50%"),
    89: ("12:26", "Arjun Mehta: DEF-907 reproduced on the 7.5 branch only; root cause in the address cache.", "Arjun reproduced DEF-907 on the 7.5 branch only"),
    90: ("12:58", "Marcus Webb (release manager): the DEF-907 fix will land in the 7.5 train.", "release manager Marcus Webb says the DEF-907 fix lands in 7.5"),
    91: ("13:25", "Olu Adeyemi: raising the canary to 75%.", "Olu raised the canary to 75%"),
    92: ([("13:34", "Tom Keller: 75% canary: error rate 0.2%, latency flat."),
          ("13:45", "Sofia Marin: QA is adding an address-cache test to the 7.5 regression suite."),
          ("13:56", "Divya Rao: the 7.5 branch builds green with the DEF-907 fix.")],
         "Tom sees a clean 75% canary, Sofia is adding an address-cache test for 7.5 and the 7.5 branch builds green with the fix"),
    93: ([("14:05", "Tom Keller: payment success 99.6% at 75%, same as control."),
          ("14:16", "Olu Adeyemi: checkout-api autoscaling behaving at 75%."),
          ("14:24", "Grace Liu: CHG-5520 stays open for the rest of the 7.4 rollout.")],
         "payment success matches control at 75%, autoscaling behaves and Grace keeps CHG-5520 open for the rollout"),
    94: ([("14:38", "Tom Keller: 75% canary: no alerts in the last hour."),
          ("14:47", "Marcus Webb: 7.5 planning moves to Tuesday."),
          ("14:55", "Olu Adeyemi: canary dashboards shared with Support.")],
         "the 75% canary has been quiet for an hour, 7.5 planning moved to Tuesday and Olu shared the dashboards with Support"),
    95: ([("15:06", "Anika Shah: privacy review opened for DEF-907 on the 7.5 branch."),
          ("15:14", "Tom Keller: promo-engine cache hit rate normal at 75%."),
          ("15:26", "Olu Adeyemi: weekend rollout plan posted.")],
         "Anika opened a privacy review for DEF-907 on 7.5, the promo-engine cache looks normal and Olu posted the weekend plan"),
    96: ("15:58", "Arjun Mehta: DEF-907 fix is in review on the 7.5 branch; tests pass.", "Arjun's DEF-907 fix is in review for 7.5 with tests passing"),
    97: ("16:24", "Olu Adeyemi: holding at 75% over the weekend; full rollout planned for Monday.", "Olu holds the canary at 75% over the weekend"),
    98: ("16:55", "Tom Keller: weekend on-call for the 7.4 canary confirmed.", "Tom confirmed weekend on-call for the canary"),
    99: ("17:26", "Release bot: 7.4 canary at 75%; next step Monday.", "the bot reports the canary at 75% until Monday"),
}
B_STRUCT_PROGRESS = {
    43: "review started on the three components; no pen-test report is needed",
    44: "checkout-api static analysis reviewed, clean",
    45: "payment-widget token handling reviewed",
    47: "promo-engine dependency scan under way",
    48: "the promo-engine dependency scan is half done",
    49: "the promo-engine dependency scan is half done",
    50: "the promo-engine dependency scan is half done",
    51: "the promo-engine dependency scan is half done",
    52: "the promo-engine dependency scan is half done",
    53: "the promo-engine dependency scan is half done",
    54: "Anika has picked the review up at the promo-engine dependency scan",
    55: "the promo-engine scan shows no critical findings and two low ones",
    57: "payment-widget security headers checked; the three checklists are next",
    61: "data-handling checklist nearly done: checkout-api log masking confirmed",
}

# Channel lines about other trains for the lexical-decoy register, keyed by the
# action whose vocabulary they borrow. None of them concerns Checkout 7.4 or its
# people; B_DECOYS_OWNER borrows the addressee options' wording. They are the
# release board's status lines, and every other train keeps one state all week
# (Loyalty 2.3, Inventory 4.1 and Admin Console 5.0 in progress; Payments 3.2,
# Wallet 1.4 and Data Sync 1.9 on hold; Reporting 3.0, Identity 6.1 and Gift
# Cards 1.2 waiting for a change approval; Notifications 2.6, Catalog 8.2 and
# Pricing 3.4 with a backup owner; Shipping 1.7, Tax Engine 2.0 and Reviews 2.1
# handed on last Friday; Search 2.7, the Payments 3.1 hotfix and Data Sync 1.8
# terminated last week), so repeated lines never contradict. Each action pool
# names three trains, so no train has to be posted in two consecutive ticks.
B_DECOYS = {
    "continue": [
        "Release board: Loyalty 2.3 QA carries on with its present owner, Lena Park; nothing is missing there.",
        "Release board: the Inventory 4.1 build stage carries on with its owner, Kofi Mensah.",
        "Release board: Admin Console 5.0's security review carries on with its current owner; nothing is missing.",
        "Release board: Loyalty 2.3's current stage carries on normally with Lena Park as owner.",
        "Release board: Inventory 4.1's current stage, build, carries on as planned with its owner.",
        "Release board: the Admin Console 5.0 review carries on; its owner has everything needed.",
    ],
    "wait": [
        "Release board: Payments 3.2 is on hold until its missing vendor certificate arrives.",
        "Release board: Wallet 1.4 is held until the missing App Store review arrives.",
        "Release board: Data Sync 1.9 is on hold, waiting for its missing input from Finance.",
        "Release board: the Payments 3.2 security review is held until the renewed vendor certificate arrives.",
        "Release board: Wallet 1.4 stays on hold until its App Store review arrives.",
        "Release board: Data Sync 1.9 is held until the missing Finance input arrives.",
    ],
    "request_approval": [
        "Release board: Reporting 3.0's production change CHG-5563 is waiting for its change approver to sign.",
        "Release board: Identity 6.1 needs its change approver to sign production change CHG-5568 before it can deploy.",
        "Release board: Gift Cards 1.2 has asked its change approver to sign production change CHG-5571; not signed yet.",
        "Release board: the Reporting 3.0 production change still has no signature from its change approver.",
        "Release board: Identity 6.1's production change CHG-5568 still needs the approver's signature.",
        "Release board: approval of the Gift Cards 1.2 production change has been requested and not yet given.",
    ],
    "reroute": [
        "Release board: Notifications 2.6 QA has moved to a different owner, Hana Ito, while Omar Haddad is on leave.",
        "Release board: Catalog 8.2's deploy stage has moved to a different owner, Mei Chen, while Jonas Berg is off sick.",
        "Release board: Pricing 3.4's build stage has moved to a different owner while its lead is on leave.",
        "Release board: Notifications 2.6's current stage stays with a different owner until Omar Haddad is back from leave.",
        "Release board: the Catalog 8.2 deploy stays with a different owner while its lead is off sick.",
        "Release board: Pricing 3.4's stage owner is on leave, so the stage stays moved to her backup.",
    ],
    "handoff": [
        "Release board: Shipping 1.7's build finished on Fri 12 Jun and it was passed to the team running its next stage, QA.",
        "Release board: Tax Engine 2.0 QA finished on Fri 12 Jun; the train was passed to its security review team.",
        "Release board: Reviews 2.1 was passed on to the team running the next stage, deploy, on Fri 12 Jun.",
        "Release board: Shipping 1.7 has been with the team running its next stage since Fri 12 Jun.",
        "Release board: Tax Engine 2.0 was handed on to its security review team after QA sign-off on Fri 12 Jun.",
        "Release board: Reviews 2.1 was handed to its deploy team on Fri 12 Jun after security sign-off.",
    ],
    "terminate": [
        "Release board: the Search 2.7 train was terminated and its release cancelled on Fri 12 Jun after a data bug.",
        "Release board: the Payments 3.1 hotfix train stays terminated; its release was cancelled on Thu 11 Jun.",
        "Release board: Data Sync 1.8 was terminated on Wed 10 Jun; its release manager cancelled the release.",
        "Release board: Search 2.7 remains terminated, its release cancelled.",
        "Release board: the Payments 3.1 hotfix release is cancelled for good; the train is terminated.",
        "Release board: Data Sync 1.8's release was cancelled and its train terminated last week.",
    ],
}
B_DECOYS_OWNER = [
    "Release board: on Notifications 2.6, Hana Ito, the named QA backup, owns QA while Omar Haddad is on leave.",
    "Release board: on Catalog 8.2, the named deploy backup, Mei Chen, runs the rollout while Jonas Berg is off sick.",
    "Release board: Reporting 3.0's change approver, Ken Obi, has not signed its production change yet.",
    "Release board: Shipping 1.7 has been with its QA team, led by Ravi Kumar, since Fri 12 Jun.",
    "Release board: Tax Engine 2.0 has been with its security review team, led by Elena Sousa, since Fri 12 Jun.",
    "Release board: Inventory 4.1's deploy team, led by Yusuf Ali, has it pencilled in for next week.",
]
B_RIVAL = {
    "continue": ["wait", "reroute", "handoff"],
    "wait": ["continue", "reroute"],
    "reroute": ["wait", "continue"],
    "request_approval": ["handoff", "wait"],
    "handoff": ["request_approval", "continue"],
    "terminate": ["continue", "wait"],
}
B_DECOY_OFFSET = [3, 7, 11, 16, 19, 23, 27]
B_DECOY_TRAINS = [
    "Loyalty 2.3", "Inventory 4.1", "Admin Console 5.0", "Payments 3.2", "Wallet 1.4", "Data Sync 1.9", "Reporting 3.0",
    "Identity 6.1", "Gift Cards 1.2", "Notifications 2.6", "Catalog 8.2", "Pricing 3.4", "Shipping 1.7", "Tax Engine 2.0",
    "Reviews 2.1", "Search 2.7", "Payments 3.1", "Data Sync 1.8",
]


def decoy_train(line: str) -> str:
    return next(name for name in B_DECOY_TRAINS if name in line)


def decoy_line(pool: list[str], index: int, avoid: set[str]) -> str:
    """The pool line at ``index``, or the next one about a train not in ``avoid`` (no train is posted twice in a row)."""
    for k in range(len(pool)):
        line = pool[(index + k) % len(pool)]
        if decoy_train(line) not in avoid:
            return line
    return pool[index % len(pool)]
B_DESCOPED = "receipts-export was removed from 7.4 on Fri 12 Jun and moved to the 7.5 train"
B_DESCOPED_P = "receipts-export was taken out of 7.4 last Friday and moved to the 7.5 train"


class ReleaseTrain(Scenario):
    family = FAMILY
    scenario_id = "workflow_b"
    title = "Controlling handoffs, ownership and approvals on a software release train"
    tier = "medium"
    difficulty_features = [
        "two_questions_per_decision",
        "six_action_options",
        "eight_way_owner_choice",
        "six_rule_priority_policy",
        "approval_expiry_arithmetic",
        "ownership_change_to_named_backup",
        "backup_lookup_in_roster",
        "scope_check",
    ]
    decision_structures = ["maintain", "wait", "handoff", "reroute", "escalate", "terminate", "recover", "resolve-conflict"]
    deadline_steps = 2

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            role, rules, key = B_ROLE_P, B_POLICY_P, "rules"
            qa, qo = B_Q_ACTION_P, B_Q_OWNER_P
            actions, owners = B_ACTIONS_P, B_OWNERS_P
        else:
            role, rules, key = B_ROLE, B_POLICY, "policy"
            qa, qo = B_Q_ACTION, B_Q_OWNER
            actions = B_ACTIONS_D if variant == "lexical_decoy" else B_ACTIONS
            owners = B_OWNERS
        return [
            Choice("action", {"role": role, key: rules, "question": qa}, dict(actions)),
            Choice("owner", {"role": role, key: rules, "question": qo}, dict(owners)),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "now_min": 0,
                "stage": "build",
                "done": False,
                "blocked": None,
                "owner": "Arjun Mehta",
                "owner_out": None,
                "covering_for": None,
                "approval_min": None,
                "approval_closed": None,
                "defects": [],
                "scope": list(B_SCOPE),
                "descoped": None,
                "cancelled": False,
                "halted": False,
                "canary": None,
            }
        )
        wed_0730 = 2 * 1440 + 7 * 60 + 30
        thu_1225 = 3 * 1440 + 12 * 60 + 25
        events: dict[int, tuple[dict[str, Any], str]] = {
            4: ({}, "Another train was terminated; 7.4 is unaffected."),
            10: ({"done": True}, "Build finished; QA has not taken the train."),
            14: ({"stage": "qa", "owner": "Sofia Marin", "done": False}, "QA takes the train."),
            20: ({}, "The current owner announces leave that starts next week; she is at work now."),
            24: ({"defects": [{"id": "DEF-881", "sev": 2, "component": "promo-engine"}]}, "A severity-2 defect does not terminate the release."),
            27: ({"defects": []}, ""),
            28: ({"owner_out": {"day": "Tue", "time": "11:54", "back": "Thursday"}},
                 "QA owner off sick while QA is unfinished: reroute to the named QA backup, Tiago Reis."),
            31: ({"owner": "Tiago Reis", "covering_for": "Sofia Marin", "owner_out": None},
                 "Tiago has taken QA over and owns it now; QA carries on."),
            36: ({}, "A failed staging health check while the test runs keep going is not a blocker."),
            39: ({"done": True}, "QA finished; security has not taken the train."),
            40: ({"approval_min": wed_0730}, "Approval granted now; the train is still with QA, so this does not mean hand off to deploy."),
            43: ({"stage": "security", "owner": "Rafael Moreno", "covering_for": None, "done": False, "blocked": "pentest"},
                 "Security review blocked on an external pen-test report."),
            48: ({"owner_out": {"day": "Wed", "time": "11:57", "back": "next week"}},
                 "Owner off sick while the stage is unfinished and still blocked: reroute outranks wait."),
            54: ({"owner": "Anika Shah", "covering_for": "Rafael Moreno", "owner_out": None, "blocked": None},
                 "Anika has taken the review over and owns it; the report has arrived."),
            58: ({}, "Two of three checklists is not a finished stage."),
            63: ({"done": True}, "Security finished; approval granted Wed 07:30 is 26 hours old at Thu 09:30, so expired."),
            66: ({}, "Deploy team ready, but the approval is expired: rule 3 before rule 4."),
            69: ({"approval_min": thu_1225}, "Fresh approval: hand off to the deploy team."),
            74: ({"stage": "deploy", "owner": "Olu Adeyemi", "covering_for": None, "done": False, "canary": 5}, "Deploy team takes the train."),
            79: ({"defects": [{"id": "DEF-902", "sev": 1, "component": "search-service"}]}, "Severity 1, but search-service is not in the 7.4 scope."),
            81: ({"canary": 25}, ""),
            84: ({"defects": []}, ""),
            85: ({"canary": 50}, ""),
            87: ({"defects": [{"id": "DEF-907", "sev": 1, "component": "receipts-export"}]}, "Severity-1 defect in an in-scope component: terminate."),
            88: ({"halted": True}, ""),
            90: ({"cancelled": True}, "Release manager cancels the release."),
            93: ({"approval_closed": "Fri 19 Jun at 14:24"}, ""),
        }
        tags = span_tags(
            {
                "distractor": [4, 20, (24, 26), 36, 40, 58, 66, (79, 83)],
                "minimal_change": [28, 48, 63, 87],
                "recovery": [31, 54],
                "hold_under_activity": [(15, 18), (80, 84), (92, 95)],
                "priority_conflict": [(48, 53), (63, 68)],
                "boundary": [(10, 13), (69, 73), (87, 99)],
                "arithmetic": [(63, 68)],
            }
        )
        for t in range(100):
            updates, note = events.get(t, ({}, ""))
            surface = surface_of(B_SCRIPT[t])
            surface["progress"] = B_PROGRESS_TICK.get(t)
            surface["progress_p"] = B_PROGRESS_TICK_P.get(t)
            tl.step(surface, tags[t], note, now_min=b_now(t), **updates)
        return tl.ticks

    @staticmethod
    def _resurface(ticks: list[Tick], table: dict[int, Any], indices: list[int], progress: dict[int, str] | None = None) -> list[Tick]:
        def make(tk: Tick, i: int) -> dict[str, Any]:
            out = {**tk.surface, **surface_of(table[i])} if i in table else dict(tk.surface)
            if progress and i in progress:
                out["progress"] = progress[i]
            return out

        return override(ticks, indices, surface=make)

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t48-50: Rafael is still available; the stage is only blocked (reroute/anika -> wait/none).
            ticks = override(ticks, range(48, 51), owner_out=None, tags=["minimal_change"], note="Owner still at work; the stage is blocked on the report: wait.")
            ticks = override(ticks, range(51, 54), owner_out={"day": "Wed", "time": "13:22", "back": "next week"},
                             note="Rafael went home sick at 13:22 with the stage unfinished: reroute to Anika.")
            ticks = self._resurface(ticks, B_MIN_SURFACE, [48, 49, 51, 53])
            # (2) Grace re-approves at Wed 10:30, so at Thu 09:30-10:30 the approval is 23-24 hours old and still
            # counts (request_approval/grace -> handoff/deploy_team at t63-65); from Thu 11:00 it has expired.
            wed_1030 = 2 * 1440 + 10 * 60 + 30
            ticks = override(ticks, range(45, 69), approval_min=wed_1030)
            ticks = self._resurface(ticks, B_MIN_SURFACE, [45])
            ticks = override(ticks, [45], note="Grace re-approves CHG-5520 at Wed 10:30.")
            ticks = override(ticks, range(63, 66), tags=["minimal_change", "arithmetic"],
                             note="Approval from Wed 10:30 is 23 to 24 hours old (exactly 24 at Thu 10:30 still counts): hand off to deploy.")
            ticks = override(ticks, range(66, 69), tags=["priority_conflict", "arithmetic"],
                             note="Approval from Wed 10:30 is now more than 24 hours old: request approval outranks hand off.")
            # (3) t87-89: DEF-907 is filed at severity 2 and only raised to 1 at 12:41 (terminate -> continue).
            ticks = override(ticks, range(87, 90), defects=[{"id": "DEF-907", "sev": 2, "component": "receipts-export"}],
                             tags=["minimal_change"], note="Severity 2 pending triage; deploy continues.")
            ticks = override(ticks, [88, 89], halted=False)
            ticks = self._resurface(ticks, B_MIN_SURFACE, [87, 88, 89, 90])
            ticks = override(ticks, [90], tags=["boundary"], note="DEF-907 raised to severity 1, canary halted, release cancelled.")
        elif variant == "structural_cf":
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for t, tk in enumerate(ticks):
                z = tk.latent
                z["scope"] = [c for c in B_SCOPE if c != "receipts-export"]
                z["descoped"] = "receipts-export"
                if z["blocked"] == "pentest":
                    z["blocked"] = None
                if t >= 88:
                    z["halted"] = False
                    z["cancelled"] = False
                    z["approval_closed"] = None
                if t >= 91:
                    z["canary"] = 75
            indices = sorted(set(B_STRUCT_SURFACE) | set(B_STRUCT_PROGRESS))
            ticks = self._resurface(ticks, B_STRUCT_SURFACE, indices, B_STRUCT_PROGRESS)
            ticks = override(ticks, range(43, 48), tags=[], note="No pen-test report is needed once receipts-export is out of scope; review in progress.")
            ticks = override(ticks, [48], tags=["minimal_change"], note="Owner off sick while the stage is unfinished: reroute.")
            ticks = override(ticks, range(49, 54), tags=[], note="")
            ticks = override(ticks, [54], note="Anika has taken the review over and owns it; the review carries on.")
            ticks = override(ticks, [87], tags=["distractor"], note="Severity 1, but receipts-export is not in the 7.4 scope: deploy continues.")
            ticks = override(ticks, range(88, 100), tags=[], note="")
            ticks = override(ticks, range(92, 96), tags=["hold_under_activity"])
        return ticks

    # ------------------------------------------------------------------ policy
    def _fresh(self, z: dict[str, Any]) -> bool:
        return z["approval_min"] is not None and z["now_min"] - z["approval_min"] <= B_VALID_MIN

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        sev1_in_scope = any(d["sev"] == 1 and d["component"] in z["scope"] for d in z["defects"])
        if z["cancelled"] or sev1_in_scope:
            action, owner = "terminate", "none"
        elif z["owner_out"] is not None and not z["done"]:
            action, owner = "reroute", B_BACKUP_TARGET[z["owner"]]
        elif z["stage"] == "security" and z["done"] and not self._fresh(z):
            action, owner = "request_approval", "grace"
        elif z["done"]:
            action, owner = "handoff", B_NEXT[z["stage"]]
        elif z["blocked"] is not None:
            action, owner = "wait", "none"
        else:
            action, owner = "continue", "none"
        return {"action": action, "owner": owner}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Release train Mon-Fri: build, handoff to QA, the QA owner going home sick (reroute to Tiago Reis) and Tiago taking QA over, handoff to security, a security review blocked on an external pen-test report, the security owner going home sick (reroute to Anika Shah outranks waiting) and Anika taking the review over, an approval that is 26 hours old when security finishes (request approval outranks handoff), a fresh approval and handoff to deploy, a canary, an out-of-scope severity-1 defect, then an in-scope severity-1 defect and cancellation. The addressee question has eight options (three teams, three named backups, the approver, nobody), above the 5-6 of the medium band, so that the two reroutes test the roster lookup."},
            "paraphrase": {"summary": "Same latent trajectory; pipeline/stand-in/rollout vocabulary, narrative prose instead of fields, reworded rules, actions and addressees. Every account of an unfinished stage, the rollout included (running or halted), says that it is not finished, and every unblocked one (the running rollout included) says that it lacks nothing from outside, naming any open defect's fix; while a stand-in owns the stage, it also says how far the stage has got."},
            "lexical_decoy": {"summary": "Same latent trajectory; the channel gains timestamped messages about other trains that borrow an action's wording (carry on, on hold, change approver, different owner, next stage, terminated), mostly the action that competes with gold, plus occasional lines borrowing the addressee options' wording."},
            "minimal_cf": {"summary": "t48-50 Rafael still at work (reroute/anika -> wait/none); Grace re-approves at Wed 10:30, so at t63-65 the approval is 23-24 hours old, exactly 24 at t65 (request_approval/grace -> handoff/deploy_team), and it expires from t66; t87-89 DEF-907 first filed at severity 2 with a harmless symptom (terminate -> continue)."},
            "structural_cf": {"summary": "receipts-export was removed from the 7.4 scope the previous Friday: the security review needs no pen-test report (t43-47 wait -> continue) and the severity-1 DEF-907 in receipts-export is a 7.5 problem, so the deploy continues instead of terminating (t87-99)."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _train(self, z: dict[str, Any], t: int) -> str:
        text = f"Checkout 7.4. Stages in order: build, QA, security review, deploy. Release scope: {', '.join(z['scope'])}"
        text += f" ({B_DESCOPED})." if z["descoped"] else "."
        if z["cancelled"]:
            text += pick(
                [
                    " Release status: cancelled by release manager Marcus Webb on Fri 19 Jun at 12:58.",
                    " Marcus Webb, the release manager, cancelled Checkout 7.4 on Fri 19 Jun at 12:58.",
                    " Called off: Marcus Webb cancelled the release at 12:58 on Friday.",
                ],
                "b-can",
                t,
            )
        else:
            text += pick([" Release status: active.", " Release status: active, not cancelled.", " Nobody has cancelled the release.", " Marcus Webb has not cancelled it."], "b-rel", t)
        return text

    def _roster(self, z: dict[str, Any]) -> str:
        rows = []
        for stage, owner, backup in B_ROSTER_ROWS:
            row = f"{B_STAGE[stage]}: {owner} (backup {backup})"
            if z["covering_for"] == owner and z["stage"] == stage:
                row = f"{B_STAGE[stage]}: {owner} (backup {backup}, who has taken it over while {owner.split()[0]} is off sick)"
            rows.append(row)
        return ". ".join(rows) + ". Production change approver: Grace Liu. Release manager: Marcus Webb."

    def _stage(self, z: dict[str, Any], t: int, s: dict[str, Any]) -> str:
        name = B_STAGE[z["stage"]]
        owner = z["owner"]
        if z["owner_out"]:
            o = z["owner_out"]
            head = pick(
                [
                    f"owner {owner}: off sick since {o['day']} {o['time']}, unavailable",
                    f"owner {owner}, who went home sick at {o['time']} and is out until {o['back']}",
                    f"owner {owner}, off sick since {o['day']} {o['time']} (back {o['back']})",
                ],
                "b-out",
                t,
            )
        elif z["covering_for"]:
            cf = z["covering_for"]
            head = pick(
                [
                    f"owner {owner}, at work; {B_PRONOUN[owner]} has taken it over from {cf}, who is off sick",
                    f"now owned by {owner}, available, who took it over from {cf} while {B_PRONOUN[cf]} is off sick",
                    f"owner {owner}, the named backup, at work in place of {cf}, who is off sick and unavailable",
                ],
                "b-cover",
                t,
            )
        else:
            head = f"owner {owner}, {pick(['at work today', 'available', 'on shift', 'in the office'], 'b-avail', t)}"
        n = B_NUM[len(z["scope"])]
        if z["done"]:
            nxt = B_NEXT_NAME[z["stage"]]
            detail = B_DONE[z["stage"]].format(n=n)
            body = pick(
                [
                    f"finished; {nxt} has not taken the train yet.",
                    f"complete ({detail}); {nxt} has not picked it up.",
                    f"finished: {detail}; the train is waiting for {nxt}, who have not taken it yet.",
                ],
                "b-done",
                t,
            )
        elif z["stage"] == "deploy":
            c = z["canary"]
            # The rollout says it is unfinished in every phrasing, running or halted (rules 2 and 4 read it).
            if z["halted"]:
                body = pick(
                    [
                        "halted, not finished: the canary was stopped at 50% and traffic moved back to 7.3.",
                        "unfinished; canary pulled at 50% and traffic is back on 7.3.",
                        "not finished: stopped at 50% of traffic and rolled back to 7.3.",
                    ],
                    "b-halt",
                    t,
                )
            else:
                body = pick(
                    [
                        f"in progress, not finished; canary at {c}% of traffic",
                        f"not finished; canary running at {c}% of traffic",
                        f"unfinished, still rolling out: {c}% of traffic is on 7.4",
                    ],
                    "b-canary",
                    t,
                )
                body += f"; {self._clear(z, t)}."
        else:
            # Every unfinished stage says it is unfinished (rules 2 and 4 read it) and, unless it is blocked,
            # that nothing from outside is missing (rule 5), in varied wording but never left out.
            progress = s.get("progress") or pick(B_PROGRESS[z["stage"]], "b-prog", t).format(n=n)
            if z["blocked"]:
                body = pick(["not finished; ", "unfinished; ", "not done; "], "b-open", t) + pick(B_BLOCK[z["blocked"]], "b-block", t)
            else:
                body = pick(["not finished; ", "unfinished: ", "not done yet; "], "b-open", t) + f"{progress}; {self._clear(z, t)}."
        return f"{name} ({head}): {body}"

    @staticmethod
    def _clear(z: dict[str, Any], t: int) -> str:
        """Rule 5's absence for a stage that is not blocked; names an open defect so its fix is not read as an input."""
        if z["defects"]:
            ids = listing([d["id"] for d in z["defects"]])
            return pick(
                [
                    f"not waiting on the {ids} fix or on anything else from outside the stage",
                    f"nothing it needs from outside the stage is missing, and it is not held for the {ids} fix",
                    f"not blocked, and not held up waiting for the {ids} fix",
                ],
                "b-clear-def",
                t,
            )
        return pick(
            ["not blocked", "nothing it needs is missing", "not waiting on anything from outside the stage", "it lacks no outside input"],
            "b-clear",
            t,
        )

    def _approval(self, z: dict[str, Any], t: int) -> str:
        if z["approval_min"] is None:
            return pick(
                [
                    "CHG-5520 (production change for 7.4): not approved yet.",
                    "No production change approval granted yet; CHG-5520 is with Grace Liu.",
                    "CHG-5520 is still with Grace Liu, unapproved.",
                ],
                "b-ap0",
                t,
            )
        stamp = b_stamp(z["approval_min"])
        if z["approval_closed"]:
            return pick(
                [
                    f"CHG-5520 (approved by Grace Liu on {stamp}) was closed as cancelled on {z['approval_closed']}.",
                    f"Grace Liu closed CHG-5520 as cancelled on {z['approval_closed']}; she had approved it on {stamp}.",
                ],
                "b-apclosed",
                t,
            )
        if z["stage"] == "deploy":
            return pick(
                [
                    f"CHG-5520 approved by Grace Liu on {stamp}; the deploy team took the train on Thu 18 Jun at 14:58 under this approval.",
                    f"Grace Liu approved CHG-5520 on {stamp}, and the deploy team took the train under it at 14:58 that day.",
                ],
                "b-apdeploy",
                t,
            )
        text = pick([f"CHG-5520 approved by Grace Liu on {stamp}", f"Grace Liu approved production change CHG-5520 on {stamp}"], "b-apok", t)
        # The age is never printed once it decides rule 3: the reader subtracts the grant time from the clock.
        if not (z["stage"] == "security" and z["done"]) and z["now_min"] > z["approval_min"] and pick([True, False], "b-age", t):
            text += f" ({b_hours(z['now_min'] - z['approval_min'])} ago)"
        return text + "."

    def _defects(self, z: dict[str, Any], t: int) -> str:
        if not z["defects"]:
            return pick(["Open defects: none.", "No open defects.", "Defect tracker: nothing open."], "b-def0", t)
        return "Open defects: " + "; ".join(f"{d['id']} (severity {d['sev']}, {d['component']})" for d in z["defects"]) + "."

    def _decoys(self, tick: Tick, i: int, avoid: set[str]) -> list[tuple[str, str]]:
        """Decoy lines for tick ``i``; ``avoid`` holds the trains posted at tick ``i - 1``."""
        gold = self.policy(tick.latent)["action"]
        if pick([True, True, False], "b-rival-on", i):
            target = pick(B_RIVAL[gold], "b-rival", i)
        else:
            target = pick([a for a in B_ACTIONS if a != gold], "b-decoy-target", i)
        first = decoy_line(B_DECOYS[target], 7 * i, avoid)
        snap = b_now(i) % 1440
        off1 = pick(B_DECOY_OFFSET, "b-doff", i)
        out = [(b_hhmm(snap - off1), first)]
        if pick([True, False, False], "b-decoy2", i):
            # Any action's wording (the gold action's included) or the addressee options' wording.
            pools = {**B_DECOYS, "owner": B_DECOYS_OWNER}
            pool = pools[pick(list(B_DECOYS) + ["owner", "owner"], "b-decoy2-target", i)]
            second = decoy_line(pool, 7 * (i + 3), avoid | {decoy_train(first)})
            if decoy_train(second) not in avoid | {decoy_train(first)}:
                off2 = pick([o for o in B_DECOY_OFFSET if o != off1], "b-doff2", i)
                out.append((b_hhmm(snap - off2), second))
        return out

    def _channel(self, history: list[Tick], t: int, variant: str) -> list[str]:
        decoys: dict[int, list[tuple[str, str]]] = {}
        if variant == "lexical_decoy":
            # Computed from the start so every tick's decoys are the same in every later state.
            avoid: set[str] = set()
            for i in range(t + 1):
                decoys[i] = self._decoys(history[i], i, avoid)
                avoid = {decoy_train(text) for _, text in decoys[i]}
        lines = []
        for i in range(max(0, t - 1), t + 1):
            msgs = list(history[i].surface["entries"]) + decoys.get(i, [])
            for at, text in sorted(msgs):
                lines.append(f"{B_DAYS[i // 20][:3]} {at} {text}")
        return lines

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        return {
            "clock": f"{B_DAYS[t // 20]}, {b_hhmm(z['now_min'])}",
            "train": self._train(z, t),
            "roster": self._roster(z),
            "stage": self._stage(z, t, tick.surface),
            "change_approval": self._approval(z, t),
            "defects": self._defects(z, t),
            "channel": self._channel(history, t, variant),
        }

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        day = B_DAYS_LONG[z["now_min"] // 1440]
        parts = [f"{day}, {b_hhmm(z['now_min'])}."]
        ships = listing(z["scope"])
        extra = f"; {B_DESCOPED_P}" if z["descoped"] else ""
        parts.append(f"The Checkout 7.4 pipeline runs compile, then testing, then security sign-off, then production rollout, and ships {ships}{extra}.")
        if z["cancelled"]:
            parts.append(pick(["Release manager Marcus Webb called the release off on Friday at 12:58.", "The release was called off by Marcus Webb, its release manager, at 12:58 on Friday."], "bp-can", t))
        else:
            parts.append(pick(["Nobody has called the release off.", "The release is still on."], "bp-rel", t))
        rows = []
        for stage, owner, backup in B_ROSTER_ROWS:
            if z["covering_for"] == owner and z["stage"] == stage:
                rows.append(f"{B_STAGE_P[stage]} {owner} ({backup}, in charge now while {owner.split()[0]} is off sick)")
            else:
                rows.append(f"{B_STAGE_P[stage]} {owner} ({backup})")
        parts.append("Regular stage owners, stand-ins in brackets: " + ", ".join(rows) + "; Grace Liu signs production changes.")
        sp = B_STAGE_P[z["stage"]]
        sp_cap = sp[0].upper() + sp[1:]
        # The role promises that the digest says whether the stage owner can work, so every branch says it.
        at_work = pick(["at work", "on duty", "in today"], "bp-avail", t)
        if z["owner_out"]:
            o = z["owner_out"]
            line = pick(
                [
                    f"The train is in {sp}, which is unfinished; its owner {z['owner']} went off sick ({o['day']} {o['time']}) and cannot work.",
                    f"{z['owner']}, who owns {sp}, went home ill at {o['time']} and is away until {o['back']}; {sp} is not done.",
                ],
                "bp-out",
                t,
            )
            if z["blocked"]:
                line += f" The stage also {pick(B_BLOCK_P[z['blocked']], 'bp-block', t)}."
            else:
                line += " " + self._clear_p(z, t)
        elif z["done"]:
            nxt = pick([B_NEXT_NAME_P[z["stage"]], "the group running the following stage"], "bp-done", t)
            line = f"{sp_cap} is done; its owner, {z['owner']}, is {at_work}, and {nxt} has not taken the train yet."
        elif z["stage"] == "deploy":
            if z["halted"]:
                line = pick(
                    [
                        f"The production rollout, owned by {z['owner']}, who is {at_work}, is halted before finishing: the canary was stopped at 50% and traffic went back to 7.3.",
                        f"{z['owner']} owns the production rollout and is {at_work}, but the rollout is unfinished: the canary was pulled at half of traffic, which went back to 7.3.",
                    ],
                    "bp-halt",
                    t,
                )
            else:
                line = f"The production rollout is under way with {z['owner']}'s group ({z['owner']} is {at_work}) and is not finished; the canary carries {z['canary']}% of traffic."
                line += " " + self._clear_p(z, t)
        elif z["blocked"]:
            line = f"The train is in {sp} with {z['owner']}, who is {at_work}, but the stage is unfinished and {pick(B_BLOCK_P[z['blocked']], 'bp-block', t)}."
        elif z["covering_for"]:
            cf = z["covering_for"]
            pr = B_PRONOUN[z["owner"]]
            line = pick(
                [
                    f"{z['owner']} now owns {sp}: {pr} took it over from {cf}, who is off sick, and {pr} is at work.",
                    f"{sp_cap} belongs to {z['owner']} now; {pr} stepped in for {cf}, who is off sick, and is on duty.",
                ],
                "bp-cover",
                t,
            )
            # Always say how far the stage has got, that it is not finished (rule 4 reads it) and that it
            # lacks nothing from outside (rule 5 reads it).
            progress = tick.surface.get("progress_p") or pick(B_PROGRESS_P[z["stage"]], "bp-prog2", t)
            line += " " + pick(
                [f"{sp_cap} is not finished yet: {progress}.", f"{sp_cap} is still unfinished; {progress}.", f"It is not done yet: {progress}."],
                "bp-cover-prog",
                t,
            )
            line += " " + self._clear_p(z, t)
        else:
            # Say plainly that the stage is unfinished: the channel line may report a finished part of it.
            state = pick(["it is unfinished and moving along", "it is not done yet and is going ahead normally", "it is still in progress, not yet finished"], "bp-prog", t)
            line = f"The train is in {sp} with {z['owner']}, who is {at_work}; {state}. " + self._clear_p(z, t)
        parts.append(line)
        if z["approval_min"] is None:
            parts.append(pick(["Grace Liu has not yet given production change approval CHG-5520.", "CHG-5520 is still waiting for Grace Liu's approval."], "bp-ap0", t))
        else:
            m = z["approval_min"]
            when = f"{B_DAYS_LONG[m // 1440].split()[0]} at {b_hhmm(m)}"
            if z["approval_closed"]:
                parts.append(f"Grace Liu gave production change approval CHG-5520 on {when} and closed it as cancelled on Friday at 14:24.")
            elif z["stage"] == "deploy":
                parts.append(f"Grace Liu gave production change approval CHG-5520 on {when}, and the rollout group took the train under it on Thursday at 14:58.")
            elif not (z["stage"] == "security" and z["done"]) and z["now_min"] > m and pick([True, False], "bp-age", t):
                parts.append(f"Grace Liu gave production change approval CHG-5520 on {when}, {b_hours(z['now_min'] - m)} before now.")
            else:
                parts.append(f"Grace Liu gave production change approval CHG-5520 on {when}.")
        if z["defects"]:
            parts.append("Open bugs: " + "; ".join(f"{d['id']}, severity {d['sev']}, in {d['component']}" for d in z["defects"]) + ".")
        else:
            parts.append(pick(["No bugs are open.", "The bug list is empty."], "bp-def0", t))
        parts.append(f"Newest in the release channel: {tick.surface['gist']}.")
        return " ".join(parts)

    @staticmethod
    def _clear_p(z: dict[str, Any], t: int) -> str:
        """The paraphrase digest's sentence for rule 5's absence (a stage that is not blocked)."""
        if z["defects"]:
            ids = listing([d["id"] for d in z["defects"]])
            return pick(
                [f"It is not waiting on the {ids} fix or on any other outside input.", f"It lacks nothing from outside the stage and is not held up by the {ids} fix."],
                "bp-clear-def",
                t,
            )
        return pick(["Nothing it needs is missing.", "It lacks nothing from outside the stage.", "It is not waiting on any outside input."], "bp-clear", t)


SCENARIOS = [ProcurementRequest, ReleaseTrain]
