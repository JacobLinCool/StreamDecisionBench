"""Two public-evidence support workflows for the first Lite measurement."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


def _choice(instructions: str, **criteria: str) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _finals(state: dict, speaker: str = "Customer", since: float = -1) -> list[dict]:
    return sorted(
        (u for u in state["transcript"]
         if u["speaker"] == speaker and u["final"] and u["at"] >= since),
        key=lambda u: u["at"],
    )


def _latest_value(lines: list[dict], patterns: list[tuple[str, str]], default: str) -> str:
    value = default
    for line in lines:
        text = re.sub(r'"[^"]*"|“[^”]*”', "", line["text"])
        for pattern, candidate in patterns:
            matches = [match for match in re.finditer(pattern, text, re.IGNORECASE)
                       if not re.search(r"(?:do not|don't|never|not)\s+$",
                                        text[:match.start()], re.IGNORECASE)]
            if matches:
                value = candidate
                break
    return value


def _payment_reference(state: dict) -> dict[str, str]:
    customer = _finals(state)
    payment = state["desktop"]["payment"]
    service = state["desktop"]["service"]
    phone = state["telephony"]
    route = _latest_value(customer, [
        (r"help me get connected|check (?:the |my )?router|work on (?:the |my )?connection", "service"),
        (r"pay the balance|(?:back to|continue with|retry) the payment", "payment"),
    ], "payment")
    if phone["status"] == "ended":
        route = "wrap"
    elif phone["status"] == "hold":
        route = "hold"

    current = _finals(state, since=payment["attempt_started_at"])
    instrument = _latest_value(current, [
        (r"use (?:my |the )?credit card", "credit"),
        (r"use (?:my |the )?debit card", "debit"),
    ], "unknown")
    consent_lines = ([] if payment["statement_read_at"] is None else
                     _finals(state, since=payment["statement_read_at"]))
    consent = _latest_value(
        consent_lines,
        [(r"withdraw (?:my |that )?authorisation", "no"),
         (r"I authorise this one-off payment", "yes")], "no",
    )
    capture = _latest_value(
        _finals(state, "Agent", payment["attempt_started_at"]),
        [(r"stop taking card details", "closed"),
         (r"read (?:out )?the long card number", "open")], "closed",
    ) == "open" and payment["status"] == "draft"
    caller_lines = [u for u in state["transcript"] if u["speaker"] == "Customer"]
    newest = max(caller_lines, key=lambda u: u["at"], default=None)
    speech = newest["text"] if newest else ""
    digit = r"(?:\d|zero|one|two|three|four|five|six|seven|eight|nine)"
    ending_only = re.search(r"card(?: number)?(?: is)? (?:ends in|ending)\b", speech, re.IGNORECASE)
    has_number = re.search(r"card number.*" + digit, speech, re.IGNORECASE) and not ending_only
    has_expiry_or_code = re.search(r"(?:expiry|security code).*" + digit, speech, re.IGNORECASE)
    speaking_card_data = bool(
        newest and not newest["final"] and (has_number or has_expiry_or_code)
    )
    recorder = "pause" if capture or speaking_card_data else "record"
    if phone["status"] == "ended":
        recorder = "stop"

    if payment["status"] in {"approved", "declined"}:
        stage = "result"
    elif payment["status"] == "pending":
        stage = "wait"
    elif consent != "yes":
        stage = "ask_consent"
    elif instrument == "unknown":
        stage = "choose_card"
    elif payment["fields_for_card"] != instrument or not all(payment["fields"].values()):
        stage = "collect"
    else:
        stage = "submit"

    target = _latest_value(customer, [
        (r"check (?:the |my )?router", "router"),
        (r"help me get connected|work on (?:the |my )?connection", "connection"),
    ], "connection")
    if target == "router":
        action = "confirm_online" if service["router"] == "online" else "check_power"
    elif service["line_test"] == "running":
        action = "wait_test"
    elif service["line_test"] == "not_run":
        action = "run_test"
    elif service["line_result"] == "down":
        action = "escalate_line"
    else:
        action = "explain_restored"
    hold_action = "none"
    if route == "hold":
        hold_action = ("return_customer" if state["clock"]["now"] - phone["since"] >=
                       state["prepared"]["hold_check_ticks"] else "wait")
    return {
        "route": route, "recorder": recorder,
        "payment_stage": stage if route == "payment" else "none",
        "instrument": instrument if route == "payment" else "none",
        "service_target": target if route == "service" else "none",
        "service_action": action if route == "service" else "none",
        "hold_action": hold_action,
    }


def _equipment_reference(state: dict) -> dict[str, str]:
    customer = _finals(state)
    phone = state["telephony"]
    route = _latest_value(customer, [
        (r"cancel the (?:replacement|original) parcel", "cancel"),
        (r"track the (?:replacement|original) parcel", "delivery"),
        (r"check (?:the |my )?(?:base unit|handset)", "repair"),
    ], "delivery")
    if phone["status"] == "ended":
        route = "closed"
    elif phone["status"] == "hold":
        route = ("hold_return" if state["clock"]["now"] - phone["since"] >=
                 state["prepared"]["hold_check_ticks"] else "hold_wait")
    channel = _latest_value(customer, [
        (r"do not send (?:any )?messages|withdraw.*(?:email|text|messages)", "none"),
        (r"send.*by text|text me.*instead", "sms"),
        (r"send.*by email", "email"),
    ], "none")
    shipment = _latest_value(customer, [
        (r"(?:track|cancel) the replacement parcel", "replacement"),
        (r"(?:track|cancel) the original parcel", "original"),
    ], "original")
    parcel = state["desktop"]["shipments"][shipment]
    if parcel["status"] == "address_mismatch":
        delivery_action = "correct_address"
    elif parcel["status"] == "delivered":
        delivery_action = "confirm_delivery"
    elif parcel["status"] == "cancelled":
        delivery_action = "confirm_cancelled"
    elif state["clock"]["now"] >= parcel["promised_at"]:
        delivery_action = "open_case"
    elif parcel["status"] == "pre_advice":
        delivery_action = "check_tracking"
    else:
        delivery_action = "wait"
    cancellation = ("confirm_cancelled" if parcel["status"] == "cancelled" else
                    "explain_locked" if parcel["status"] in {"in_transit", "delivered"} else
                    "cancel_request")
    target = _latest_value(customer, [
        (r"check (?:the |my )?base unit", "base"),
        (r"check (?:the |my )?handset", "handset"),
    ], "base")
    device = state["desktop"]["diagnostics"][target]
    access = _latest_value(customer, [
        (r"withdraw.*remote access|do not connect remotely", "no"),
        (r"you may connect remotely", "yes"),
    ], "no")
    if device["status"] == "not_run":
        repair_action = "diagnose"
    elif device["status"] == "running":
        repair_action = "await_result"
    elif device["result"] == "power_fault":
        repair_action = "send_part" if state["desktop"]["spares"][target] else "book_visit"
    elif device["result"] == "network_fault":
        repair_action = "remote_check" if access == "yes" else "request_access"
    else:
        repair_action = "explain_clear"
    return {
        "route": route, "contact_channel": channel,
        "delivery_target": shipment if route in {"delivery", "cancel"} else "none",
        "delivery_action": delivery_action if route == "delivery" else "none",
        "repair_target": target if route == "repair" else "none",
        "repair_action": repair_action if route == "repair" else "none",
        "cancellation_action": cancellation if route == "cancel" else "none",
    }


def reference(state: dict) -> dict[str, str]:
    """Derive all answers from published state, never a step index or hidden label."""
    workflow = state["workflow"]
    if workflow == "payment_support":
        return _payment_reference(state)
    if workflow == "equipment_support":
        return _equipment_reference(state)
    raise ValueError(f"Unknown support workflow: {workflow}")


def _say(at: int, text: str, speaker: str = "Customer", *, final: bool = True,
         utterance_id: str | None = None) -> dict:
    return {"utterance_id": utterance_id or f"u{at}-{speaker}", "at": at,
            "speaker": speaker, "text": text, "final": final}


def _merge(target: dict, patch: dict) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _build(initial: dict, schedule: dict[int, dict], *, episode_id: str,
           title: str, questions: dict, decision_spec: dict) -> dict:
    live = deepcopy(initial)
    steps = []
    for tick in range(60):
        live["clock"]["now"] = tick
        update = deepcopy(schedule.get(tick, {}))
        lines = update.pop("utterances", [])
        _merge(live, update)
        for line in lines:
            live["transcript"] = [u for u in live["transcript"]
                                  if u["utterance_id"] != line["utterance_id"]]
            live["transcript"].append(line)
        state = deepcopy(live)
        newest_final = next(reversed(_finals(state)), None)
        evidence = [f"telephony.status={state['telephony']['status']}",
                    "The complete public workflow rules are in prepared.rules."]
        if newest_final:
            evidence.append(f"Customer {newest_final['utterance_id']}: {newest_final['text']}")
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": evidence})
    return {"episode_id": episode_id, "task_family": "support_call_assist",
            "scenario_id": episode_id.removeprefix("lite_"), "title": title,
            "tick_seconds": 2.0, "questions": questions,
            "decision_spec": decision_spec, "steps": steps}


def _payment_scenario() -> dict:
    questions = {
        "route": _choice("Which workflow branch is currently active? Apply telephony priority, then the most recent final Customer request. A request remains active until replaced.",
                         payment="Payment workflow", service="Connection or router support", hold="Customer on hold", wrap="Call ended"),
        "recorder": _choice("What should the recorder do now? This decision applies in every branch. Apply the capture and live-card-speech rules, including the call-ended rule.",
                            record="Record", pause="Pause", stop="Stop after the call ends"),
        "payment_stage": _choice("For the active payment branch, select the required next payment step using tool status, current consent, selected card and field completeness. Otherwise choose none.",
                                 ask_consent="Obtain current authorisation", choose_card="Ask which card", collect="Collect missing details for the selected card", submit="Ready to submit", wait="Wait for the tool result", result="Explain the result", none="Payment branch inactive"),
        "instrument": _choice("Which card has the Customer most recently selected for this payment attempt? Other speakers and partial utterances do not select a card. Otherwise none outside payment.",
                              debit="Debit card", credit="Credit card", unknown="Customer has not selected a card", none="Payment branch inactive"),
        "service_target": _choice("For the service branch, which target did the Customer last request? Otherwise none.",
                                  router="Router", connection="Network connection", none="Service branch inactive"),
        "service_action": _choice("Choose the prescribed action for the active service target from current tool observations. Otherwise none.",
                                  check_power="Check router power", confirm_online="Confirm router is online", run_test="Run line test", wait_test="Wait for line test", escalate_line="Escalate failed line", explain_restored="Explain restored line", none="Service branch inactive"),
        "hold_action": _choice("During hold, return to the customer when elapsed hold time reaches the published threshold, including equality. Otherwise wait; none outside hold.",
                               wait="Wait while under threshold", return_customer="Return to the customer", none="Hold branch inactive"),
    }
    initial = {
        "workflow": "payment_support",
        "prepared": {
            "deployment": "Fictional broadband contact centre. This is an observation-only simulation; decisions describe UI and recorder commands, without executing any external action. Customer is the verified account holder; Background and Agent cannot authorise or choose on the customer's behalf.",
            "hold_check_ticks": 4,
            "rules": [
                "Clock, telephony.since, attempt_started_at, statement_read_at and utterance times are ticks; snapshot t is published at tick t. All changes become observable only at published ticks. The full transcript remains visible. An updated utterance replaces its earlier partial. For route, card choice and consent, only final Customer speech counts. Agent promises and background speech do not change tool facts.",
                "Route priority: ended -> wrap; hold -> hold; otherwise the last explicit final Customer request controls. A request to pay the balance or return/continue/retry payment selects payment. A request to get connected, work on the connection or check the router selects service. Default payment. A side question, card choice, authorisation, partial request or acknowledgement alone does not change route.",
                "Within payment, select the latest final Customer instruction to use a debit or credit card since attempt_started_at. Default unknown. Negated alternatives are not selections. Consent is granted only by an explicit Customer authorisation of this one-off payment at or after statement_read_at, and revoked by an explicit withdrawal. Latest grant/withdrawal wins; default no consent.",
                "Payment stage priority: approved or declined -> result; pending -> wait; otherwise no consent -> ask_consent; no selected card -> choose_card; fields_for_card differs from the selected card or any field is missing -> collect; otherwise submit. Switching cards makes another card's entered fields insufficient. Fields are normal payment-tool completion indicators, not card values.",
                "Recorder: ended -> stop; otherwise pause while capture is open or while the Customer's newest utterance is partial and actually contains card-number, expiry or security-code digits (written or spoken). Capture opens on a final Agent request to read the long card number at or after attempt start; closes on a later final Agent instruction to stop taking card details, or when tool status is no longer draft. Latest capture instruction wins. Card choice, account numbers, payment references and a card's ending digits alone are not card data. Final old card speech does not independently require a pause. No other case pauses.",
                "Service target: latest final Customer request to check the router -> router; get connected/work on the connection -> connection. Default connection. Router online -> confirm_online, otherwise check_power. Connection test running -> wait_test; not_run -> run_test; completed/down -> escalate_line; completed/up -> explain_restored. UI page titles and words in another speaker's speech do not override these rules.",
                "During hold, now minus telephony.since >= hold_check_ticks -> return_customer, otherwise wait. Payment and service details are inactive during hold. The recorder remains applicable in every branch. Inactive branch answers should be none; only the route, recorder and the active branch's questions compose the applied decision.",
            ],
        },
        "clock": {"now": 0}, "telephony": {"status": "connected", "since": 0},
        "transcript": [],
        "desktop": {
            "payment": {"attempt_id": "P-17", "attempt_started_at": 0, "statement_read_at": None,
                        "amount": "86.40", "status": "draft", "fields_for_card": "none",
                        "fields": {"number": False, "expiry": False, "code": False}},
            "service": {"router": "offline", "line_test": "not_run", "line_result": "unknown"},
        },
    }
    schedule = {
        0: {"utterances": [_say(0, "I'd like to pay the balance, please.")]},
        2: {"utterances": [_say(2, "The statement is: this is a one-off payment of 86.40 for this account. Do you authorise it?", "Agent")],
            "desktop": {"payment": {"statement_read_at": 2}}},
        4: {"utterances": [_say(4, "I authorise this one-off payment of 86.40.")]},
        6: {"utterances": [_say(6, "Use my credit card, that's what I would do.", "Background")]},
        8: {"utterances": [_say(8, "Use my debit card, not the credit one.")]},
        10: {"utterances": [_say(10, "My account number is five five zero one", final=False, utterance_id="account")]},
        11: {"utterances": [_say(10, "My account number is five five zero one.", utterance_id="account")]},
        12: {"utterances": [_say(12, "Please read the long card number.", "Agent")]},
        14: {"utterances": [_say(14, "The card number is four two four two", final=False, utterance_id="card")]},
        16: {"utterances": [_say(14, "The test card number is four two four two.", utterance_id="card")],
             "desktop": {"payment": {"fields_for_card": "debit", "fields": {"number": True}}}},
        18: {"utterances": [_say(18, "The expiry is zero nine twenty eight.")],
             "desktop": {"payment": {"fields": {"expiry": True}}}},
        20: {"utterances": [_say(20, "Leave the payment for a moment; help me get connected first.")]},
        22: {"utterances": [_say(22, "We will stop taking card details for now.", "Agent")],
             "desktop": {"service": {"line_test": "running"}}},
        24: {"utterances": [_say(24, "Check the router! Mine was broken yesterday.", "Background")]},
        25: {"desktop": {"service": {"line_test": "complete", "line_result": "down"}}},
        27: {"utterances": [_say(27, "Check my router first; we can come back to the line fault.")]},
        29: {"telephony": {"status": "hold", "since": 29},
             "utterances": [_say(29, "The customer has waited long enough already.", "Agent")]},
        34: {"telephony": {"status": "connected", "since": 34},
             "desktop": {"service": {"router": "online"}}},
        36: {"utterances": [_say(36, "Let's go back to the payment now.")]},
        38: {"utterances": [_say(38, "Actually use my credit card", final=False, utterance_id="change-card")]},
        40: {"utterances": [_say(38, "Actually use my credit card instead of the debit one.", utterance_id="change-card")]},
        42: {"utterances": [_say(42, "Please read the long card number for that card.", "Agent")]},
        44: {"utterances": [_say(44, "I withdraw my authorisation until I've checked the amount.")]},
        46: {"utterances": [_say(46, "That's the right amount. I authorise this one-off payment.")]},
        48: {"desktop": {"payment": {"fields_for_card": "credit", "fields": {"number": True, "expiry": True, "code": True}}}},
        50: {"desktop": {"payment": {"status": "pending"}}},
        51: {"utterances": [_say(51, "Was my expiry zero nine twenty eight", final=False, utterance_id="late-expiry")]},
        52: {"utterances": [_say(51, "Was my expiry zero nine twenty eight?", utterance_id="late-expiry")]},
        54: {"desktop": {"payment": {"status": "approved"}}},
        56: {"utterances": [_say(56, "Now check the router for me, please.")]},
        58: {"telephony": {"status": "ended", "since": 58}},
    }
    return _build(initial, schedule, episode_id="lite_support_a",
                  title="Payment, reconnection and recorder control",
                  questions=questions,
                  decision_spec={"route_question": "route", "always": ["recorder"],
                                 "branches": {"payment": ["payment_stage", "instrument"],
                                              "service": ["service_target", "service_action"],
                                              "hold": ["hold_action"], "wrap": []}})


def _equipment_scenario() -> dict:
    questions = {
        "route": _choice("Select the active branch from telephony state and the latest final Customer request. Hold timing overrides the remembered request; ending overrides hold.",
                         delivery="Parcel support", repair="Device repair", cancel="Parcel cancellation", hold_wait="Hold below threshold", hold_return="Hold at or beyond threshold", closed="Call ended"),
        "contact_channel": _choice("Which follow-up channel is currently authorised by the Customer? Apply latest final permission or withdrawal, including during hold. Default none.",
                                   email="Email", sms="Text message", none="No follow-up messages authorised"),
        "delivery_target": _choice("Which parcel is selected by the latest final Customer instruction to track or cancel a parcel? Relevant in delivery AND cancel branches; none otherwise.",
                                   original="Original parcel", replacement="Replacement parcel", none="Neither delivery nor cancel branch"),
        "delivery_action": _choice("For the delivery branch, apply carrier status and the published promised_at deadline to the selected parcel. Otherwise none.",
                                   correct_address="Correct the address", confirm_delivery="Confirm delivery", confirm_cancelled="Confirm cancellation", open_case="Open a late-parcel case", check_tracking="Check tracking for a label-only parcel", wait="Wait while in transit before the deadline", none="Delivery branch inactive"),
        "repair_target": _choice("Which device did the Customer most recently ask to check? Relevant only in repair.",
                                 base="Base unit", handset="Handset", none="Repair branch inactive"),
        "repair_action": _choice("For the selected repair target, combine its diagnostic status/result, spare availability and current remote-access consent. Otherwise none.",
                                 diagnose="Start diagnosis", await_result="Await the running diagnosis", send_part="Send the available replacement part", book_visit="Book a visit because no spare is available", request_access="Request remote-access consent", remote_check="Perform the consented remote check", explain_clear="Explain that no fault was found", none="Repair branch inactive"),
        "cancellation_action": _choice("For cancellation, use the selected parcel's actual carrier status. An agent's statement does not replace a callback. Otherwise none.",
                                       confirm_cancelled="Cancellation callback confirms success", explain_locked="Already dispatched or delivered; cancellation is locked", cancel_request="Request cancellation; not yet dispatched or confirmed cancelled", none="Cancellation branch inactive"),
    }
    initial = {
        "workflow": "equipment_support",
        "prepared": {
            "deployment": "Fictional home-intercom support desk. Output is guidance only: no shipment, cancellation or remote-access operation is actually performed. Customer is the verified account holder; Agent and Background speech do not request actions or grant permission on their behalf.",
            "hold_check_ticks": 4,
            "rules": [
                "Clock, promised_at, telephony.since and utterance times are ticks; snapshot t is published at tick t. Reference decisions update only at published ticks. The full transcript remains visible; revised utterances replace their earlier partial. Only final Customer instructions change route, target, contact permission or remote-access consent. Partial speech never does. Instructions persist until replaced; mentions, quoted alternatives and other speakers' instructions do not count.",
                "Route priority: ended -> closed; hold with clock.now minus telephony.since >= hold_check_ticks -> hold_return; any shorter hold -> hold_wait; otherwise latest final Customer request to track a parcel -> delivery, cancel a parcel -> cancel, check a base unit or handset -> repair. Default delivery. A permission change alone does not change route. Returning from hold resumes the latest Customer request, not a new default.",
                "The latest final Customer request to track/cancel the original or replacement parcel selects delivery_target for BOTH delivery and cancellation. Default original. Select the requested object, not a negated alternative in the same utterance.",
                "Delivery action priority: address_mismatch -> correct_address; delivered -> confirm_delivery; cancelled -> confirm_cancelled; otherwise now >= promised_at -> open_case; otherwise pre_advice (label only) -> check_tracking; otherwise in_transit -> wait. Equality at the deadline counts as late. The carrier callback is authoritative over the agent's verbal estimate.",
                "Cancellation action: cancelled callback -> confirm_cancelled; in_transit or delivered -> explain_locked; pre_advice or address_mismatch -> cancel_request. An agent saying cancelled does not confirm cancellation. Requests are recommendations; no real operation is executed.",
                "Repair target is the device in the latest final Customer request to check it: base unit or handset. Default base. For that target only: diagnostic not_run -> diagnose; running -> await_result; complete/power_fault -> send_part if a spare for that target is available, else book_visit; complete/network_fault -> remote_check if consented, else request_access; complete/no_fault -> explain_clear. Another device's diagnostic result or spare does not substitute.",
                "Remote-access consent defaults to no: final Customer permission to connect remotely grants it, and withdrawal or a request not to connect revokes it; latest wins. This is separate from follow-up contact consent. Contact permission defaults to none: Customer requests by email -> email; by text or text instead -> sms; do not send messages or withdrawal -> none. Latest applicable final Customer instruction wins. Contact channel always contributes to the applied decision, even on hold or after ending, as the retained follow-up preference.",
                "Only route, contact_channel and active branch questions compose the applied decision. Delivery uses delivery_target + delivery_action; cancellation uses delivery_target + cancellation_action; repair uses repair_target + repair_action. Hold and closed have no branch-specific fields. Inactive branch answers should be none.",
            ],
        },
        "clock": {"now": 0}, "telephony": {"status": "connected", "since": 0},
        "transcript": [],
        "desktop": {
            "shipments": {"original": {"status": "in_transit", "promised_at": 20},
                          "replacement": {"status": "pre_advice", "promised_at": 50}},
            "diagnostics": {"base": {"status": "not_run", "result": "unknown"},
                            "handset": {"status": "not_run", "result": "unknown"}},
            "spares": {"base": True, "handset": False},
        },
    }
    schedule = {
        0: {"utterances": [_say(0, "Please track the original parcel first.")]},
        2: {"utterances": [_say(2, "You can send the follow-up by email.")]},
        4: {"utterances": [_say(4, "Cancel the original parcel! That's what I told my seller.", "Background")]},
        6: {"utterances": [_say(6, "Actually track the replacement parcel, not the original one.")]},
        8: {"desktop": {"shipments": {"replacement": {"status": "address_mismatch"}}}},
        10: {"utterances": [_say(10, "Cancel the replacement parcel", final=False, utterance_id="cancel")]},
        12: {"utterances": [_say(10, "Cancel the replacement parcel, please.", utterance_id="cancel")]},
        14: {"utterances": [_say(14, "It's cancelled now; I have clicked the button.", "Agent")]},
        16: {"desktop": {"shipments": {"replacement": {"status": "cancelled"}}}},
        18: {"utterances": [_say(18, "Leave that cancelled parcel alone. Track the original parcel again.")]},
        19: {"utterances": [_say(19, "It's not late yet; we've got a bit more time.", "Agent")]},
        22: {"desktop": {"shipments": {"original": {"status": "delivered"}}}},
        24: {"utterances": [_say(24, "Now check the base unit; it will not power up.")]},
        26: {"utterances": [_say(26, "Actually check the handset", final=False, utterance_id="device")]},
        28: {"utterances": [_say(26, "Actually check the handset, not the base unit.", utterance_id="device")]},
        30: {"utterances": [_say(30, "The diagnostic finished and found no fault on my device.", "Background")]},
        32: {"desktop": {"diagnostics": {"handset": {"status": "running"}}}},
        34: {"desktop": {"diagnostics": {"handset": {"status": "complete", "result": "power_fault"}}}},
        36: {"utterances": [_say(36, "Text me the follow-up instead of sending email.")]},
        38: {"desktop": {"spares": {"handset": True}}},
        40: {"utterances": [_say(40, "Leave the handset there; check the base unit now.")]},
        42: {"desktop": {"diagnostics": {"base": {"status": "running"}}}},
        44: {"telephony": {"status": "hold", "since": 44}},
        46: {"utterances": [_say(46, "She has already been on hold for quite a while.", "Agent")]},
        49: {"telephony": {"status": "connected", "since": 49},
             "desktop": {"diagnostics": {"base": {"status": "complete", "result": "network_fault"}}}},
        51: {"utterances": [_say(51, "You may connect remotely to check the base unit.")]},
        53: {"utterances": [_say(53, "Do not send any messages afterwards. Keep the remote check going.")]},
        54: {"desktop": {"diagnostics": {"base": {"status": "running", "result": "unknown"}}}},
        56: {"desktop": {"diagnostics": {"base": {"status": "complete", "result": "no_fault"}}}},
        58: {"telephony": {"status": "ended", "since": 58}},
    }
    return _build(initial, schedule, episode_id="lite_support_b",
                  title="Intercom delivery, cancellation and repair guidance",
                  questions=questions,
                  decision_spec={"route_question": "route", "always": ["contact_channel"],
                                 "branches": {"delivery": ["delivery_target", "delivery_action"],
                                              "cancel": ["delivery_target", "cancellation_action"],
                                              "repair": ["repair_target", "repair_action"],
                                              "hold_wait": [], "hold_return": [], "closed": []}})


def scenarios() -> list[dict]:
    """Return two independent 60-tick observation trajectories."""
    return [_payment_scenario(), _equipment_scenario()]
