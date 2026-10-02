"""Training variant support_c: an island-airline travel-change desk (support call assist).

A new workflow (``travel_change``) in the support family design: telephony
priority (ended > hold > latest final Customer request), only final Customer
speech changes the route, segment or bag, requests persist until replaced, the
desktop tool records are authoritative over spoken claims and inactive branch
answers are none. Branches rebook and refund share the selected flight segment;
baggage uses the selected bag and its tracer deadline. A global recorder pauses
during passport capture (which here stays open across a hold and a route
change) or a live partial passport-digit utterance and stops when the call
ends. Every gold answer is computed by ``reference`` from the
public state alone; the rules text in ``prepared.rules`` states all of it.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from streamdecisionbench.lite.tasks.support import _choice, _finals, _merge, _say

WORKFLOW = "travel_change"
EPISODE_ID = "train_support_c"

# Fixed request phrases (case-insensitive, whole words) -> (route, target).
REQUESTS = [
    ("rebook my island flight", "rebook", "island"),
    ("rebook my return flight", "rebook", "return"),
    ("refund the island ticket", "refund", "island"),
    ("refund the return ticket", "refund", "return"),
    ("trace my suitcase", "baggage", "suitcase"),
    ("trace my guitar case", "baggage", "guitar_case"),
]
NEGATED = re.compile(r"(?:\bnot|\bdon['’]t|\bdo not|\bnever)\s+$", re.IGNORECASE)
QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
CAPTURE_OPEN = "read your passport number"
CAPTURE_CLOSE = "passport capture is complete"
PASSPORT_DIGITS = re.compile(
    r"\bpassport\b.*?(?:\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine)\b)",
    re.IGNORECASE)

RULES = [
    "Timing and transcript: clock.now, telephony.since, promised_at and every utterance 'at' are ticks; "
    "snapshot t is published at tick t and decisions change only at published ticks. The transcript keeps "
    "every utterance. A final utterance replaces the earlier partial with the same utterance_id and keeps "
    "that partial's 'at'. Only FINAL Customer utterances can change the route, the segment or the bag; "
    "partial utterances, Agent speech and Background speech never do, whatever they say. A request stays "
    "in force until a later final Customer request replaces it.",
    "Request recognition: a request is one of these exact phrases, matched case-insensitively as whole "
    "words anywhere inside a final Customer utterance: 'rebook my island flight' or 'rebook my return "
    "flight' (rebook request); 'refund the island ticket' or 'refund the return ticket' (refund request); "
    "'trace my suitcase' or 'trace my guitar case' (baggage request). Surrounding words do not matter. A "
    "phrase inside double quotes (straight or curly), or immediately preceded by 'not', 'don't', 'do not' or "
    "'never' (these negating words are also matched case-insensitively), is not a request. Each utterance "
    "contains at most one counted request. Any other wording (agreeing to a waitlist, thanks, remarks about "
    "a bag or a fare, similar but different phrasings) is not a request and changes nothing.",
    "Route priority: telephony ended -> closed; telephony hold with clock.now minus telephony.since >= "
    "hold_check_ticks -> hold_return (equality counts); any shorter hold -> hold_wait; otherwise the "
    "latest request: rebook request -> rebook, refund request -> refund, baggage request -> baggage. "
    "Default rebook before any request. Returning from hold resumes the latest request.",
    "segment is the flight named in the latest rebook or refund request: island or return. It serves both "
    "the rebook and the refund branch. Default island. Baggage requests do not change it. bag is the item "
    "named in the latest baggage request: suitcase or guitar_case. Default suitcase. Rebook and refund "
    "requests do not change it.",
    "Desktop tool records are authoritative: what the Agent or Background says about seats, fares, "
    "refunds, bags or couriers never overrides them. desktop.alerts and the tracer's last_scan notes are "
    "informational only; only the status, seats_left, fare_difference, fare_type, flight_status and "
    "promised_at fields named below decide. A record for the other segment or the other bag never "
    "substitutes for the selected one.",
    "Rebook action, from the booking tool record desktop.booking.segments[segment].change_option of the "
    "selected segment: status confirmed -> confirm_change; status waitlisted -> await_waitlist (even if "
    "seats_left later rises above 0); otherwise seats_left 0 -> offer_waitlist; otherwise fare_difference "
    "above 0 -> collect_difference; otherwise change_free.",
    "Refund action, for the selected segment: the refund tool status desktop.refunds[segment] issued -> "
    "confirm_refund; pending -> await_refund; otherwise (none) the booking record "
    "desktop.booking.segments[segment] with flight_status cancelled (cancelled by the airline) -> "
    "submit_refund for any fare type; otherwise by its fare_type: flex -> submit_refund; saver -> "
    "offer_credit; basic -> explain_nonrefundable.",
    "Bag action, from the selected bag's tracer record desktop.tracer[bag]: status delivered -> "
    "confirm_delivery; otherwise clock.now >= promised_at -> open_claim (equality counts as late); "
    "otherwise unlocated -> keep_tracing; located -> arrange_delivery; forwarding -> share_eta.",
    "Recorder (applies in every branch, including hold and closed): telephony ended -> stop. Otherwise "
    "pause while passport capture is open, or while the Customer's newest utterance (greatest 'at', "
    "partial or final) is partial and contains the word 'passport' (any case) followed later in that "
    "utterance by a digit, written (0-9) or spoken as a whole digit word (zero, one, two, three, four, "
    "five, six, seven, eight, nine, in any case; a digit word joined by a hyphen, as in 'thirty-five', "
    "also counts). Otherwise record. Passport capture opens on a final Agent utterance containing 'read "
    "your passport number' and closes on a later final Agent utterance containing 'passport capture is "
    "complete' (both phrases matched case-insensitively); the latest opening or closing utterance wins; "
    "default closed. Only final Agent utterances open or close capture: Agent partials, Customer speech and "
    "Background speech never do, and Background speech never affects the recorder. Final Customer speech "
    "never pauses by itself, and digits without the word 'passport' before them (booking references, "
    "flight numbers, fares) are not passport data.",
    "Composition: the applied decision is route + recorder + the active branch's fields: rebook -> "
    "segment + rebook_action; refund -> segment + refund_action; baggage -> bag + bag_action; hold_wait, "
    "hold_return and closed add nothing. Every question of an inactive branch is answered none.",
]

DEPLOYMENT = (
    "Gullwing Air, a fictional island-hopper airline, travel-change desk. Observation-only simulation: "
    "answers drive the agent's guidance panel and the call recorder; no booking, refund, courier or "
    "recording command is executed. The Customer is the verified booking holder, a touring musician; the "
    "Background speaker is a bandmate who is not on the booking. Neither the Agent nor the Background "
    "speaker can request a change or choose a segment or bag for the Customer."
)


def _request(text: str) -> tuple[str, str] | None:
    """The one counted request in a final Customer utterance, or None."""
    text = QUOTED.sub(" ", text)
    found = []
    for phrase, route, target in REQUESTS:
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
            if not NEGATED.search(text[:match.start()]):
                found.append((route, target))
    if len(found) > 1:
        raise ValueError(f"more than one request in one utterance: {text!r}")
    return found[0] if found else None


def _capture_open(state: dict) -> bool:
    open_ = False
    for line in _finals(state, "Agent"):
        text = line["text"].lower()
        opens, closes = CAPTURE_OPEN in text, CAPTURE_CLOSE in text
        if opens and closes:
            raise ValueError(f"capture instruction is ambiguous: {line['text']!r}")
        if opens:
            open_ = True
        elif closes:
            open_ = False
    return open_


def reference(state: dict) -> dict[str, str]:
    """Derive every answer from the published state alone (no tick index, gold or hidden field)."""
    if state["workflow"] != WORKFLOW:
        raise ValueError(f"Unknown support workflow: {state['workflow']}")
    now = state["clock"]["now"]
    phone = state["telephony"]
    desktop = state["desktop"]

    latest, segment, bag = None, "island", "suitcase"
    for line in _finals(state):
        request = _request(line["text"])
        if request is None:
            continue
        latest, target = request
        if latest == "baggage":
            bag = target
        else:
            segment = target
    route = latest or "rebook"
    if phone["status"] == "ended":
        route = "closed"
    elif phone["status"] == "hold":
        route = ("hold_return" if now - phone["since"] >= state["prepared"]["hold_check_ticks"]
                 else "hold_wait")

    customer = [u for u in state["transcript"] if u["speaker"] == "Customer"]
    newest = max(customer, key=lambda u: u["at"], default=None)
    live_passport = bool(newest and not newest["final"] and PASSPORT_DIGITS.search(newest["text"]))
    if phone["status"] == "ended":
        recorder = "stop"
    elif _capture_open(state) or live_passport:
        recorder = "pause"
    else:
        recorder = "record"

    flight = desktop["booking"]["segments"][segment]
    option = flight["change_option"]
    if option["status"] == "confirmed":
        rebook_action = "confirm_change"
    elif option["status"] == "waitlisted":
        rebook_action = "await_waitlist"
    elif option["seats_left"] == 0:
        rebook_action = "offer_waitlist"
    elif option["fare_difference"] > 0:
        rebook_action = "collect_difference"
    else:
        rebook_action = "change_free"

    refund_status = desktop["refunds"][segment]
    if refund_status == "issued":
        refund_action = "confirm_refund"
    elif refund_status == "pending":
        refund_action = "await_refund"
    elif flight["flight_status"] == "cancelled" or flight["fare_type"] == "flex":
        refund_action = "submit_refund"
    elif flight["fare_type"] == "saver":
        refund_action = "offer_credit"
    elif flight["fare_type"] == "basic":
        refund_action = "explain_nonrefundable"
    else:
        raise ValueError(f"unknown fare type: {flight['fare_type']}")

    record = desktop["tracer"][bag]
    if record["status"] == "delivered":
        bag_action = "confirm_delivery"
    elif now >= record["promised_at"]:
        bag_action = "open_claim"
    elif record["status"] == "unlocated":
        bag_action = "keep_tracing"
    elif record["status"] == "located":
        bag_action = "arrange_delivery"
    elif record["status"] == "forwarding":
        bag_action = "share_eta"
    else:
        raise ValueError(f"unknown tracer status: {record['status']}")

    return {
        "route": route,
        "recorder": recorder,
        "segment": segment if route in {"rebook", "refund"} else "none",
        "rebook_action": rebook_action if route == "rebook" else "none",
        "refund_action": refund_action if route == "refund" else "none",
        "bag": bag if route == "baggage" else "none",
        "bag_action": bag_action if route == "baggage" else "none",
    }


def _questions() -> dict[str, Any]:
    return {
        "route": _choice(
            "Which branch is active now? Apply telephony priority (ended, then hold time against "
            "hold_check_ticks with equality counting as reached), otherwise the latest final Customer "
            "request recognised by the published phrases. A request stays active until a later one "
            "replaces it.",
            rebook="Change a flight segment", refund="Refund a flight segment",
            baggage="Trace a delayed bag", hold_wait="On hold, below the hold threshold",
            hold_return="On hold, threshold reached: return to the Customer", closed="Call ended"),
        "recorder": _choice(
            "What should the call recorder do now? This applies in every branch: stop once the call has "
            "ended; pause while passport capture is open or while the Customer's newest utterance is "
            "partial and contains passport digits; otherwise record.",
            record="Keep recording", pause="Pause recording", stop="Stop: the call has ended"),
        "segment": _choice(
            "Which flight segment did the latest final Customer rebook or refund request name? Used by "
            "both the rebook and the refund branch; none in every other branch.",
            island="Island flight", **{"return": "Return flight"},
            none="Neither rebook nor refund branch active"),
        "rebook_action": _choice(
            "For the rebook branch, apply the selected segment's change_option in the booking tool "
            "(status, then seats_left, then fare_difference). Otherwise none.",
            confirm_change="Confirm the completed change", await_waitlist="Wait for the waitlist to clear",
            offer_waitlist="No seats: offer the waitlist", collect_difference="Collect the fare difference",
            change_free="Change at no extra charge", none="Rebook branch inactive"),
        "refund_action": _choice(
            "For the refund branch, use the selected segment's refund tool status, then an airline "
            "cancellation, then the fare type. Otherwise none.",
            confirm_refund="Confirm the issued refund", await_refund="Wait for the pending refund",
            submit_refund="Submit a cash refund", offer_credit="Offer travel credit instead of cash",
            explain_nonrefundable="Explain the fare is non-refundable", none="Refund branch inactive"),
        "bag": _choice(
            "Which bag did the latest final Customer trace request name? Relevant only in the baggage "
            "branch; none otherwise.",
            suitcase="Suitcase", guitar_case="Guitar case", none="Baggage branch inactive"),
        "bag_action": _choice(
            "For the selected bag, apply its tracer status and promised_at deadline (reaching the deadline "
            "exactly counts as late). Otherwise none.",
            confirm_delivery="Confirm the bag was delivered", open_claim="Open a delayed-bag claim",
            keep_tracing="Keep tracing an unlocated bag", arrange_delivery="Arrange courier delivery",
            share_eta="Share the courier arrival estimate", none="Baggage branch inactive"),
    }


DECISION_SPEC = {
    "route_question": "route", "always": ["recorder"],
    "branches": {"rebook": ["segment", "rebook_action"], "refund": ["segment", "refund_action"],
                 "baggage": ["bag", "bag_action"], "hold_wait": [], "hold_return": [], "closed": []},
}


def _initial() -> dict[str, Any]:
    return {
        "workflow": WORKFLOW,
        "prepared": {"deployment": DEPLOYMENT, "hold_check_ticks": 5, "rules": RULES},
        "clock": {"now": 0},
        "telephony": {"status": "connected", "since": 0},
        "transcript": [],
        "desktop": {
            "booking": {
                "locator": "WREN8K",
                "segments": {
                    "island": {"flight": "Gullwing 314", "departs": "Fri 09:40", "fare_type": "saver",
                               "flight_status": "scheduled",
                               "change_option": {"flight": "Gullwing 318", "departs": "Sun 09:40",
                                                 "seats_left": 4, "fare_difference": 0, "status": "none"}},
                    "return": {"flight": "Gullwing 902", "departs": "Mon 18:15", "fare_type": "basic",
                               "flight_status": "scheduled",
                               "change_option": {"flight": "Gullwing 906", "departs": "Tue 18:15",
                                                 "seats_left": 0, "fare_difference": 0, "status": "none"}},
                },
            },
            "refunds": {"island": "none", "return": "none"},
            "tracer": {
                "suitcase": {"tag": "GULL-550913", "status": "unlocated", "last_scan": "none",
                             "promised_at": 24},
                "guitar_case": {"tag": "GULL-550914", "status": "forwarding",
                                "last_scan": "Courier depot, loaded on van", "promised_at": 40},
            },
            "alerts": [],
        },
    }


def _schedule() -> dict[int, dict[str, Any]]:
    """Tick -> public updates. 'note' is an authoring witness kept out of the state."""
    return {
        0: {"utterances": [_say(0, "Hi, I'm calling about my trip to the island folk festival next week.")],
            "note": "No request yet: default route rebook and default segment island."},
        1: {"utterances": [_say(1, "I need to rebook my island flight; the festival moved my set to Sunday.")],
            "note": "Customer requests a rebook of the island segment; Sunday option has seats, no difference."},
        2: {"utterances": [_say(2, "I can see a Sunday island flight with four seats left.", "Agent")]},
        3: {"desktop": {"booking": {"segments": {"island": {"change_option": {"fare_difference": 35}}}}},
            "note": "Booking tool reprices the Sunday island option: fare difference 35."},
        4: {"desktop": {"booking": {"segments": {"return": {"change_option": {"fare_difference": 20}}}}},
            "note": "A return-segment reprice does not change the island rebook decision."},
        5: {"utterances": [_say(5, "The Sunday seat now costs thirty-five more than your ticket.", "Agent")]},
        6: {"utterances": [_say(6, "Thirty-five extra is too much. Refund the island ticket instead; "
                                   "I'll take the ferry.")],
            "note": "Final Customer refund request for the island segment (saver fare)."},
        7: {"desktop": {"alerts": ["Weather watch for island routes this weekend"]}},
        8: {"utterances": [_say(8, "Saver tickets always come back as cash, so you're covered.", "Agent")],
            "note": "Agent's claim does not override the saver fare type."},
        9: {"desktop": {"booking": {"segments": {"island": {"flight_status": "cancelled"}}},
                        "alerts": ["Weather watch for island routes this weekend",
                                   "Friday island departures cancelled by operations"]},
            "note": "Airline cancels the Friday island flight: cash refund for any fare."},
        10: {"utterances": [_say(10, "Ask them to trace my guitar case as well, my bass is in it.", "Background")],
             "note": "The bandmate's request phrase does not change the decision."},
        11: {"utterances": [_say(11, "Could you also refund the return ticket while you're at it? "
                                     "I might take the ferry back as well.")],
             "note": "Final Customer refund request switches the segment to return (basic fare)."},
        12: {"utterances": [_say(12, "That return fare is a basic one, so there's no money back on it.", "Agent")]},
        13: {"utterances": [_say(13, "Fine, then rebook my return flight", final=False, utterance_id="u13-turn")],
             "desktop": {"refunds": {"island": "pending"}},
             "note": "Partial rebook hypothesis and the island refund record do not change the decision."},
        14: {"utterances": [_say(13, "Fine, then we'll book my return flight later; first trace my suitcase, "
                                     "it never turned up last night.", utterance_id="u13-turn")],
             "note": "The partial is finalised differently: only the suitcase trace is a counted request."},
        16: {"desktop": {"tracer": {"suitcase": {"status": "located",
                                                 "last_scan": "Transfer hub, lost-property shelf"}}},
             "note": "Tracer locates the suitcase."},
        17: {"utterances": [_say(17, "It's already on a courier van, it'll be with you within the hour.", "Agent")],
             "note": "Agent's courier claim does not override the located status."},
        18: {"utterances": [_say(18, "Trace my guitar case too, it was on the same flight.")],
             "note": "Customer switches the bag to the guitar case (forwarding)."},
        19: {"desktop": {"tracer": {"guitar_case": {
                 "last_scan": "Driver note: maybe left with a neighbour (unconfirmed)"}}},
             "note": "An unconfirmed scan note is informational; status stays forwarding."},
        20: {"desktop": {"tracer": {"suitcase": {"status": "forwarding",
                                                 "last_scan": "Handed to courier at transfer hub"}}},
             "note": "The suitcase record changes while the guitar case is selected."},
        21: {"utterances": [_say(21, "What about my suitcase? Trace my suitcase, the guitar case can wait.")],
             "note": "Customer reselects the suitcase, now forwarding before its deadline."},
        24: {"note": "Suitcase deadline reached exactly (promised_at 24): late."},
        25: {"utterances": [_say(25, "That's past the promised time, so I'll open a delayed-bag claim. "
                                     "Please read your passport number for the claim form.", "Agent")],
             "note": "Agent opens passport capture for the claim."},
        26: {"utterances": [_say(26, "Okay, it starts with K R seven seven and ends four three.")],
             "note": "Final Customer digits during open capture."},
        27: {"telephony": {"status": "hold", "since": 27},
             "note": "Agent places the call on hold while passport capture is still open."},
        29: {"utterances": [_say(29, "While the caller is holding, can someone check whether that claim went through?",
                                 "Agent")]},
        30: {"desktop": {"tracer": {"suitcase": {"status": "delivered", "last_scan": "Delivered to hotel front desk"}}},
             "note": "The suitcase is delivered during the hold."},
        32: {"note": "Hold reaches hold_check_ticks exactly: return to the Customer; capture still open."},
        34: {"telephony": {"status": "connected", "since": 34},
             "note": "Back from hold: the latest request (trace the suitcase) resumes."},
        35: {"utterances": [_say(35, "The front desk just rang, my suitcase is here. Thank you!")]},
        36: {"utterances": [_say(36, "Now rebook my return flight to Tuesday, please.")],
             "note": "Route changes to the return rebook while capture is open; Tuesday option has no seats."},
        37: {"utterances": [_say(37, "Noted. I'll withdraw the bag claim too; passport capture is complete.",
                                 "Agent")],
             "note": "Agent closes passport capture."},
        38: {"utterances": [_say(38, "Tuesday looks wide open, there are plenty of seats on it.", "Agent")],
             "note": "Agent's seat claim does not override seats_left 0."},
        39: {"utterances": [_say(39, "Or I could refund the return ticket for you instead.", "Agent")],
             "note": "Agent's phrase is not a Customer request."},
        40: {"utterances": [_say(40, "Yes, please put me on the waitlist for Tuesday.")]},
        41: {"desktop": {"booking": {"segments": {"return": {"change_option": {"status": "waitlisted"}}}}},
             "note": "Booking tool shows the return change waitlisted."},
        42: {"utterances": [_say(42, "Do you need my passport again for the waitlist?")],
             "note": "Final Customer mention of the passport without digits does not pause."},
        43: {"utterances": [_say(43, "No, the number from the claim form is already on file.", "Agent")]},
        44: {"desktop": {"tracer": {"guitar_case": {"status": "delivered",
                                                    "last_scan": "Delivered to hotel front desk"}}},
             "note": "The guitar case record changes while the rebook branch is active."},
        46: {"utterances": [_say(46, "Sorry, the passport number ends four", final=False, utterance_id="u46-fix")],
             "note": "Live partial with passport digits."},
        47: {"utterances": [_say(46, "Sorry, the passport number ends four two, not four three.",
                                 utterance_id="u46-fix")],
             "note": "The correction becomes final."},
        48: {"utterances": [_say(48, "Two seats just opened on Tuesday's flight.", "Agent")],
             "desktop": {"booking": {"segments": {"return": {"change_option": {"seats_left": 2}}}}},
             "note": "Seats reopen but the change is still waitlisted."},
        49: {"desktop": {"booking": {"segments": {"return": {"change_option": {"status": "confirmed",
                                                                                "seats_left": 1}}}}},
             "note": "Waitlist clears: the return change is confirmed."},
        50: {"utterances": [_say(50, 'Your app shows a button that says "refund the return ticket"; '
                                     "I haven't touched it.")],
             "note": "A quoted phrase is not a request."},
        51: {"utterances": [_say(51, "Last thing: please refund the island ticket if it isn't done yet.")],
             "note": "Customer returns to the island refund, which is pending."},
        53: {"desktop": {"refunds": {"island": "issued"}},
             "note": "Refund tool issues the island refund."},
        54: {"utterances": [_say(54, "Please don't refund the return ticket, I still need it for Tuesday.")],
             "note": "A negated phrase is not a request."},
        55: {"utterances": [_say(55, "The receipt should mention booking five nine", final=False,
                                 utterance_id="u55-receipt")],
             "note": "Partial digits without 'passport' do not pause."},
        56: {"utterances": [_say(55, "The receipt should mention booking five nine, thanks.",
                                 utterance_id="u55-receipt")]},
        57: {"telephony": {"status": "ended", "since": 57},
             "note": "Call ends: closed and recorder stop."},
    }


def _build() -> dict[str, Any]:
    live = _initial()
    schedule = _schedule()
    steps = []
    for tick in range(60):
        live["clock"]["now"] = tick
        update = deepcopy(schedule.get(tick, {}))
        lines = update.pop("utterances", [])
        note = update.pop("note", None)
        _merge(live, update)
        for line in lines:
            if line["at"] > tick:
                raise ValueError(f"utterance from the future at tick {tick}")
            live["transcript"] = [u for u in live["transcript"] if u["utterance_id"] != line["utterance_id"]]
            live["transcript"].append(line)
        customer_ats = [u["at"] for u in live["transcript"] if u["speaker"] == "Customer"]
        if len(customer_ats) != len(set(customer_ats)):
            raise ValueError(f"two Customer utterances share a time at tick {tick}")
        state = deepcopy(live)
        evidence = [f"telephony.status={state['telephony']['status']} since {state['telephony']['since']}",
                    "The complete public travel-change rules are in prepared.rules."]
        requests = [u for u in _finals(state) if _request(u["text"])]
        if requests:
            evidence.append(f"Latest Customer request {requests[-1]['utterance_id']}: {requests[-1]['text']}")
        if note:
            evidence.append(note)
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": evidence})
    return {"episode_id": EPISODE_ID, "task_family": "support_call_assist", "scenario_id": "support_c",
            "title": "Island trip changes, bag tracing and passport recorder control",
            "tick_seconds": 2.0, "questions": _questions(), "decision_spec": deepcopy(DECISION_SPEC),
            "steps": steps}


def scenarios() -> list[dict[str, Any]]:
    """One 60-tick travel-change call."""
    return [_build()]
