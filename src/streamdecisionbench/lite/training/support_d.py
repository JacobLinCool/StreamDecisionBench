"""Training variant support_d: a home-energy account desk (meter reading, instalment plan, power cut).

A new workflow (``energy_account``) in the support-call-assist family design:
telephony priority (ended > hold > latest counted final Customer request), only
final Customer speech changes route, selections, agreement and the register flag,
desktop tool records are authoritative over speech, and inactive branch answers
are none. Every rule the reference applies is published in
``state["prepared"]["rules"]``. Both values of every selection question
(meter_target electricity/gas, outage_site home/cottage) are gold on the
trajectory, each with quoted, partial, refused or non-Customer distractors.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from streamdecisionbench.lite.tasks.support import _choice, _merge

EPISODE_ID = "train_support_d"
WORKFLOW = "energy_account"
HOLD_CHECK_TICKS = 4

# Counted phrases, exactly as the published rules quote them.
ROUTE_PHRASES = [
    ("submit my electricity reading", "meter"), ("submit my gas reading", "meter"),
    ("set up an instalment plan", "plan"), ("back to the instalment plan", "plan"),
    ("report a power cut at home", "outage"), ("report a power cut at the cottage", "outage"),
]
METER_PHRASES = [("submit my electricity reading", "electricity"), ("submit my gas reading", "gas")]
SITE_PHRASES = [("report a power cut at home", "home"), ("report a power cut at the cottage", "cottage")]
COUNT_PHRASES = [("three monthly instalments", "three"), ("six monthly instalments", "six"),
                 ("twelve monthly instalments", "twelve")]
AGREEMENT_PHRASES = [("I agree to the plan terms", "yes"), ("I withdraw my agreement to the plan", "no")]
REGISTER_PHRASES = [("add me to the priority services register", "register"),
                    ("take me off the priority services register", "none")]

METER_ACTIONS = {"missing": "take_reading", "validating": "await_check",
                 "implausible": "confirm_digits", "accepted": "confirm_bill"}

QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
REFUSAL = re.compile(r"\b(?:not|never|don't|don’t)\s+$", re.IGNORECASE)

RULES = [
    "Timing: clock.now, telephony.since, desktop.plan.terms_read_at, outage-map estimated_restore_at and "
    "utterance at values are ticks; snapshot t is published at tick t. The transcript keeps every utterance; "
    "a revised utterance replaces the earlier partial with the same utterance_id and keeps its at. "
    "Utterances are ordered by at.",
    "Who counts: only final Customer utterances can change the route, the meter, the outage site, the "
    "instalment count, plan agreement or the priority-services register. Partial utterances, Agent speech and "
    "Background speech never count, even when they contain a counted phrase. Desktop tool records are "
    "authoritative: readings, eligibility, restore estimates, restoration or plan set-up claimed in speech do "
    "not override them.",
    "Phrase recognition: the counted phrases are exactly the request, instalment-count, agreement and "
    "register phrases quoted in the route, plan-branch and register rules below, matched case-insensitively "
    "as a whole word sequence anywhere in an utterance; no other wording counts. A phrase inside double "
    "quotation marks is a quotation and does not count. A phrase immediately preceded by the word not, do "
    "not, don't or never is a refusal and does not count; it neither makes nor withdraws anything. Only "
    "those words make a refusal: other negative wording before a phrase, such as 'do not want to' or 'won't', "
    "does not stop it counting, and a phrase that directly follows a quotation is not preceded by a refusal "
    "word placed before that quotation. If one "
    "utterance contains several counted phrases of the same kind (request, meter, site, count, agreement or "
    "register), the one appearing last in that utterance counts. For each kind the latest counted utterance "
    "wins, and a choice persists until a later counted phrase of that kind replaces it.",
    "Route priority: telephony ended -> closed; telephony on hold (telephony.status hold) whose elapsed time (clock.now - "
    "telephony.since) is >= hold_check_ticks -> hold_return (equality counts); any shorter telephony hold -> hold_wait; otherwise the latest counted request "
    "phrase decides: 'submit my electricity reading' or 'submit my gas reading' -> meter; 'set up an "
    "instalment plan' or 'back to the instalment plan' -> plan; 'report a power cut at home' or 'report a "
    "power cut at the cottage' -> outage. Default meter. Agreement, instalment counts, register statements, "
    "spoken readings and acknowledgements do not change the route. When the call is connected again after a "
    "hold, the latest counted request applies again.",
    "Meter branch: meter_target is the meter named in the latest counted meter phrase (electricity or gas); "
    "default electricity. Use only desktop.meter_reads for that meter: status missing -> take_reading; "
    "validating -> await_check; implausible -> confirm_digits; accepted -> confirm_bill. The other meter's "
    "record does not substitute.",
    "Plan branch: instalments is the count in the latest counted phrase 'three monthly instalments', 'six "
    "monthly instalments' or 'twelve monthly instalments'; default unknown. Agreement is current only if "
    "desktop.plan.terms_read_at is set and, among final Customer utterances with at >= terms_read_at, the "
    "latest counted agreement phrase is 'I agree to the plan terms' rather than 'I withdraw my agreement to "
    "the plan'. Agreement given before the latest terms reading is stale; changing the instalment count does "
    "not by itself withdraw agreement.",
    "Plan stage priority: desktop.plan.status active -> confirm_active; otherwise "
    "desktop.account.plan_eligibility ineligible -> explain_ineligible; checking -> await_eligibility; "
    "otherwise terms_read_at null -> read_terms; no current agreement -> ask_consent; instalments unknown -> "
    "ask_count; otherwise set_up.",
    "Outage branch: outage_site is the site in the latest counted outage phrase (home or cottage); default "
    "home. Use only desktop.outage_map for that site: restored -> confirm_restored; outage with clock.now >= "
    "estimated_restore_at -> escalate_overdue (equality counts as overdue); outage before "
    "estimated_restore_at -> share_estimate; clear -> log_report. Area notices and the other site's entry do "
    "not substitute.",
    "Priority-services register (applies in every branch, including hold and after the call ends): register "
    "after a counted 'add me to the priority services register', none after a counted 'take me off the "
    "priority services register'; latest wins; default none.",
    "Composition: route and priority_register are always part of the applied decision. Meter adds "
    "meter_target and meter_action; plan adds plan_stage and instalments; outage adds outage_site and "
    "outage_action; hold_wait, hold_return and closed add nothing. Answers for inactive branch questions "
    "should be none.",
]

DEPLOYMENT = (
    "Fictional home-energy supplier, account desk. Answers are guidance for the agent's screen; this "
    "simulation submits no reading, sets up no plan, files no fault report and changes no register. The "
    "caller labelled Customer has passed security; Agent and Background voices cannot choose, agree or "
    "register anything for them."
)


def _customer_finals(state: dict) -> list[dict]:
    return sorted((u for u in state["transcript"] if u["speaker"] == "Customer" and u["final"]),
                  key=lambda u: u["at"])


def _counted(text: str, phrases: list[tuple[str, str]]) -> str | None:
    """The value of the last counted phrase in one utterance, or None."""
    # A quotation becomes a placeholder word, so a refusal word before it cannot reach the phrase after it.
    text = QUOTED.sub(" QUOTATION ", text)
    found: tuple[int, str] | None = None
    for phrase, value in phrases:
        for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", text, re.IGNORECASE):
            if REFUSAL.search(text[:match.start()]):
                continue
            if found is None or match.start() > found[0]:
                found = (match.start(), value)
    return None if found is None else found[1]


def _latest(lines: list[dict], phrases: list[tuple[str, str]], default: str) -> str:
    value = default
    for line in lines:
        counted = _counted(line["text"], phrases)
        if counted is not None:
            value = counted
    return value


def _plan_stage(state: dict, customer: list[dict], instalments: str) -> str:
    plan = state["desktop"]["plan"]
    eligibility = state["desktop"]["account"]["plan_eligibility"]
    if plan["status"] == "active":
        return "confirm_active"
    if plan["status"] != "draft":
        raise ValueError(f"unknown plan status: {plan['status']}")
    if eligibility == "ineligible":
        return "explain_ineligible"
    if eligibility == "checking":
        return "await_eligibility"
    if eligibility != "eligible":
        raise ValueError(f"unknown plan eligibility: {eligibility}")
    terms = plan["terms_read_at"]
    if terms is None:
        return "read_terms"
    agreement = _latest([u for u in customer if u["at"] >= terms], AGREEMENT_PHRASES, "no")
    if agreement != "yes":
        return "ask_consent"
    if instalments == "unknown":
        return "ask_count"
    return "set_up"


def _outage_action(state: dict, site: str) -> str:
    entry = state["desktop"]["outage_map"][site]
    if entry["status"] == "restored":
        return "confirm_restored"
    if entry["status"] == "outage":
        if entry["estimated_restore_at"] is None:
            raise ValueError("an outage entry must publish estimated_restore_at")
        return ("escalate_overdue" if state["clock"]["now"] >= entry["estimated_restore_at"]
                else "share_estimate")
    if entry["status"] == "clear":
        return "log_report"
    raise ValueError(f"unknown outage status: {entry['status']}")


def reference(state: dict) -> dict[str, str]:
    """Derive every answer from the published state alone (no tick index, gold or hidden field)."""
    if state["workflow"] != WORKFLOW:
        raise ValueError(f"Unknown support workflow: {state['workflow']}")
    customer = _customer_finals(state)
    phone = state["telephony"]
    route = _latest(customer, ROUTE_PHRASES, "meter")
    if phone["status"] == "ended":
        route = "closed"
    elif phone["status"] == "hold":
        elapsed = state["clock"]["now"] - phone["since"]
        route = "hold_return" if elapsed >= state["prepared"]["hold_check_ticks"] else "hold_wait"
    elif phone["status"] != "connected":
        raise ValueError(f"unknown telephony status: {phone['status']}")

    register = _latest(customer, REGISTER_PHRASES, "none")
    meter = _latest(customer, METER_PHRASES, "electricity")
    meter_action = METER_ACTIONS[state["desktop"]["meter_reads"][meter]["status"]]
    instalments = _latest(customer, COUNT_PHRASES, "unknown")
    stage = _plan_stage(state, customer, instalments)
    site = _latest(customer, SITE_PHRASES, "home")
    outage_action = _outage_action(state, site)
    return {
        "route": route,
        "priority_register": register,
        "meter_target": meter if route == "meter" else "none",
        "meter_action": meter_action if route == "meter" else "none",
        "plan_stage": stage if route == "plan" else "none",
        "instalments": instalments if route == "plan" else "none",
        "outage_site": site if route == "outage" else "none",
        "outage_action": outage_action if route == "outage" else "none",
    }


QUESTIONS = {
    "route": _choice(
        "Which branch applies now? Telephony comes first: ended -> closed; on hold, compare clock.now minus "
        "telephony.since with hold_check_ticks (equality counts as reached). Otherwise the latest counted final "
        "Customer request decides and stays active until another request replaces it.",
        meter="Meter reading submission", plan="Instalment plan set-up", outage="Power cut report",
        hold_wait="On hold, below the hold check threshold",
        hold_return="On hold, threshold reached or passed", closed="Call ended"),
    "priority_register": _choice(
        "Does the Customer currently want to be on the priority services register? Apply the latest counted "
        "final Customer add or take-off statement. This applies in every branch, including hold and after the "
        "call ends. Default none.",
        register="Customer asked to be added", none="Not asked, or the Customer asked to be taken off"),
    "meter_target": _choice(
        "In the meter branch, which meter did the latest counted final Customer reading request name (quoted, "
        "refused, partial and non-Customer phrases do not count)? Default electricity. Otherwise none.",
        electricity="Electricity meter", gas="Gas meter", none="Meter branch inactive"),
    "meter_action": _choice(
        "In the meter branch, map the selected meter's meter-read tool status to the next step. Spoken readings "
        "do not replace the tool record. Otherwise none.",
        take_reading="Tool has no reading: take the reading and enter it",
        await_check="Tool is validating the reading: wait",
        confirm_digits="Tool flags the reading as implausible: confirm the digits",
        confirm_bill="Tool accepted the reading: confirm the bill will use it",
        none="Meter branch inactive"),
    "plan_stage": _choice(
        "In the plan branch, choose the next step from plan status, account eligibility, the terms reading, "
        "current Customer agreement and the chosen instalment count, in the published priority order. "
        "Otherwise none.",
        confirm_active="Plan tool shows the plan active: confirm it",
        explain_ineligible="Account tool says ineligible: explain",
        await_eligibility="Account tool is still checking eligibility: wait",
        read_terms="Eligible, terms not yet read: read the plan terms",
        ask_consent="Terms read, no current agreement: ask for agreement",
        ask_count="Agreement current, no count chosen: ask for the instalment count",
        set_up="Agreement current and count chosen: set up the plan",
        none="Plan branch inactive"),
    "instalments": _choice(
        "In the plan branch, which instalment count did the Customer most recently choose? Otherwise none.",
        three="Three monthly instalments", six="Six monthly instalments", twelve="Twelve monthly instalments",
        unknown="No count chosen yet", none="Plan branch inactive"),
    "outage_site": _choice(
        "In the outage branch, which site did the latest counted final Customer power-cut report name (quoted, "
        "refused, partial and non-Customer phrases do not count)? Default home. Otherwise none.",
        home="Home address", cottage="The cottage", none="Outage branch inactive"),
    "outage_action": _choice(
        "In the outage branch, apply the selected site's outage-map entry and its estimated_restore_at "
        "(equality counts as overdue). Spoken estimates do not count. Otherwise none.",
        log_report="Map shows no fault: log a new fault report",
        share_estimate="Known outage before its estimate: share the estimate",
        escalate_overdue="Known outage at or past its estimate: escalate as overdue",
        confirm_restored="Map shows supply restored: confirm restoration",
        none="Outage branch inactive"),
}

DECISION_SPEC = {
    "route_question": "route", "always": ["priority_register"],
    "branches": {"meter": ["meter_target", "meter_action"], "plan": ["plan_stage", "instalments"],
                 "outage": ["outage_site", "outage_action"],
                 "hold_wait": [], "hold_return": [], "closed": []},
}


def _say(at: int, text: str, speaker: str = "Customer", *, final: bool = True, uid: str | None = None) -> dict:
    return {"utterance_id": uid or f"{speaker.lower()}-{at}", "at": at, "speaker": speaker,
            "text": text, "final": final}


def _initial() -> dict:
    return {
        "workflow": WORKFLOW,
        "prepared": {"deployment": DEPLOYMENT, "hold_check_ticks": HOLD_CHECK_TICKS, "rules": list(RULES)},
        "clock": {"now": 0},
        "telephony": {"status": "connected", "since": 0},
        "transcript": [],
        "desktop": {
            "account": {"balance_due": "412.30", "plan_eligibility": "checking"},
            "plan": {"terms_read_at": None, "status": "draft"},
            "meter_reads": {"electricity": {"status": "missing", "reading": None},
                            "gas": {"status": "missing", "reading": None}},
            "outage_map": {"home": {"status": "clear", "estimated_restore_at": None},
                           "cottage": {"status": "clear", "estimated_restore_at": None}},
            "area_notices": [],
        },
    }


NOTICE = "Thistlecombe village: planned cable work, supply off until 15:30."

SCHEDULE: dict[int, dict[str, Any]] = {
    0: {"utterances": [_say(0, "Morning. I'm standing at the meter box and want to submit my electricity "
                               "reading.")],
        "note": "Customer requests the electricity reading; tool has none -> meter/electricity/take_reading"},
    1: {"utterances": [_say(1, "Of course. Read me the digits whenever the display is in front of you.", "Agent")]},
    2: {"utterances": [_say(2, "The display shows zero four eight one six.")],
        "note": "Spoken reading only; the tool record is still missing"},
    3: {"desktop": {"meter_reads": {"electricity": {"status": "validating", "reading": "04816"}}},
        "note": "Meter tool validating the entered reading -> await_check"},
    4: {"utterances": [_say(4, "That reading is definitely right; it's what the display says.")],
        "note": "Customer's claim does not change the validating tool status"},
    5: {"desktop": {"meter_reads": {"electricity": {"status": "implausible"}}},
        "utterances": [_say(5, "The system flags that as far above your usual use; could you check the display "
                               "again?", "Agent")],
        "note": "Meter tool flags the reading implausible -> confirm_digits"},
    6: {"utterances": [_say(6, "Tell them to submit my gas reading too while you're on.", "Background")],
        "note": "Background gas request is not a Customer request"},
    7: {"utterances": [_say(7, "Sorry, I misread it: zero four one eight six.")],
        "note": "Corrected digits spoken; tool still implausible"},
    8: {"desktop": {"meter_reads": {"electricity": {"status": "accepted", "reading": "04186"}}},
        "note": "Meter tool accepts the corrected reading -> confirm_bill"},
    9: {"utterances": [_say(9, "Then submit my gas reading", final=False, uid="gas-change")],
        "note": "Partial gas request does not count"},
    10: {"utterances": [_say(9, "Then don't submit my gas reading yet; the cupboard key is missing.",
                             uid="gas-change")],
         "note": "Final revision refuses the gas reading; electricity stays selected"},
    11: {"utterances": [_say(11, "The cupboard key was hanging in the shed after all, so submit my gas reading "
                                 "now: zero two seven seven three.")],
         "note": "Counted gas request; the gas tool record is missing and the accepted electricity record does "
                 "not substitute -> meter/gas/take_reading"},
    12: {"utterances": [_say(12, "Please add me to the priority services register; my father uses an oxygen "
                                 "concentrator.")],
         "note": "Customer asks to be added -> priority_register register; gas still take_reading"},
    13: {"desktop": {"meter_reads": {"gas": {"status": "validating", "reading": "02773"}}},
         "utterances": [_say(13, "Thank you, I'll pass that on to the register team.", "Agent")],
         "note": "Gas tool validating the entered reading -> meter/gas/await_check"},
    14: {"utterances": [_say(14, "Next, I want to set up an instalment plan for the winter balance.")],
         "note": "Plan request; account tool still checking eligibility -> await_eligibility"},
    15: {"utterances": [_say(15, "You'll qualify, nearly everyone does.", "Agent")],
         "note": "Agent's eligibility claim does not replace the account tool"},
    16: {"desktop": {"account": {"plan_eligibility": "ineligible"}},
         "utterances": [_say(16, "Ah, the account check came back ineligible while the gas reading is still being "
                                 "validated. I'll re-run it once that clears.", "Agent")],
         "note": "Account tool: ineligible -> explain_ineligible, despite the Agent's earlier claim"},
    17: {"desktop": {"account": {"plan_eligibility": "eligible"},
                     "meter_reads": {"gas": {"status": "accepted"}}},
         "note": "Gas reading accepted and the re-run account check says eligible; terms not read -> read_terms"},
    19: {"desktop": {"plan": {"terms_read_at": 19}},
         "utterances": [_say(19, "The standard plan terms: equal monthly direct debits, no interest, and two "
                                 "missed payments end the plan.", "Agent")],
         "note": "Terms read at 19 -> ask_consent"},
    20: {"utterances": [_say(20, "I agree to the plan terms, just say it!", "Background")],
         "note": "Background agreement does not count"},
    21: {"utterances": [_say(21, "Yes, I agree to the plan terms.")],
         "note": "Customer agrees after the terms reading; no count yet -> ask_count"},
    23: {"utterances": [_say(23, "Six monthly instalments, please.")],
         "note": "Count six chosen -> set_up/six"},
    24: {"utterances": [_say(24, "Take me off the priority services register, I don't want a fuss.",
                             "Background")],
         "note": "Background take-off statement does not change the register flag"},
    25: {"utterances": [_say(25, "Actually make it three monthly instalments", final=False, uid="count-change")],
         "note": "Partial count change does not count"},
    26: {"utterances": [_say(25, "Actually make it twelve monthly instalments.", uid="count-change")],
         "note": "Final revision chooses twelve; agreement still current -> set_up/twelve"},
    27: {"desktop": {"plan": {"terms_read_at": 27}},
         "utterances": [_say(27, "Twelve months needs the extended terms, so I'll read them again: twelve direct "
                                 "debits of 34.36, no interest, and two missed payments end the plan.", "Agent")],
         "note": "Terms re-read at 27; agreement at 21 is stale -> ask_consent"},
    28: {"utterances": [_say(28, "Before I agree to that, report a power cut at the cottage; my guests have no "
                                 "lights.")],
         "note": "Outage request for the cottage; map shows clear -> log_report"},
    29: {"utterances": [_say(29, "Shall I also report a power cut at home, just in case?", "Agent")],
         "note": "Agent's suggestion does not select the home site"},
    30: {"telephony": {"status": "hold", "since": 30},
         "utterances": [_say(30, "One moment, I'm placing you on hold to check the network map.", "Agent")],
         "note": "Hold starts at 30 -> hold_wait"},
    31: {"desktop": {"area_notices": [NOTICE]},
         "note": "Area notice for another village is not the cottage's map entry"},
    32: {"desktop": {"outage_map": {"cottage": {"status": "outage", "estimated_restore_at": 38}}},
         "note": "Map lists a cottage outage with estimate 38 while the call is on hold"},
    33: {"note": "Hold elapsed 3 < 4 -> hold_wait"},
    34: {"telephony": {"status": "connected", "since": 34},
         "utterances": [_say(34, "Thanks for holding. The network has a fault listed for the cottage.", "Agent")],
         "note": "Back from hold below threshold; outage resumes -> share_estimate"},
    35: {"utterances": [_say(35, "The crew say it'll be back within ten minutes, so there's no need to chase it.",
                             "Agent")],
         "note": "Spoken estimate does not replace estimated_restore_at"},
    36: {"utterances": [_say(36, 'My neighbour keeps texting "report a power cut at home" to me, but she means '
                                 'her own house, not mine.')],
         "note": "Quoted home report does not count; the cottage stays selected"},
    37: {"utterances": [_say(37, "One of my guests thinks the lights flickered back on.")],
         "note": "Spoken restoration claim; map still shows the outage"},
    38: {"note": "clock.now equals estimated_restore_at 38 -> escalate_overdue"},
    40: {"desktop": {"outage_map": {"cottage": {"status": "restored"}}},
         "note": "Map shows the cottage restored -> confirm_restored"},
    41: {"utterances": [_say(41, "Lovely, the guests will be relieved. Now our own kitchen has gone dark, so "
                                 "report a power cut at home as well.")],
         "note": "Counted home report; home map entry clear, the cottage's restored entry does not substitute "
                 "-> outage/home/log_report"},
    42: {"utterances": [_say(42, "While you log that, can we go back to the instalment plan?")],
         "note": "Plan resumes; no agreement since terms at 27 -> ask_consent/twelve"},
    43: {"utterances": [_say(43, "Dad is right, so take me off the priority services register.")],
         "note": "Customer takes the register request off -> none"},
    44: {"utterances": [_say(44, "I agree to the plan terms.")],
         "note": "Agreement after the re-read -> set_up/twelve"},
    45: {"utterances": [_say(45, "Hold on, I withdraw my agreement to the plan; the first collection falls before "
                                 "my payday.")],
         "note": "Customer withdraws agreement -> ask_consent; 'hold on' is speech, not telephony hold"},
    46: {"telephony": {"status": "hold", "since": 46},
         "utterances": [_say(46, "Let me put you on hold while I see whether the first collection can move.",
                             "Agent")],
         "note": "Hold starts at 46 -> hold_wait"},
    49: {"utterances": [_say(49, "Can billing confirm the twenty-eighth? I need to get back to the caller.",
                             "Agent")],
         "note": "Hold elapsed 3 < 4 -> hold_wait; the Agent's intention to return is not a status change"},
    50: {"note": "Hold elapsed 4 = threshold -> hold_return"},
    51: {"telephony": {"status": "connected", "since": 51},
         "utterances": [_say(51, "Thanks for waiting. The first collection can move to the twenty-eighth.",
                             "Agent")],
         "note": "Back from hold; plan resumes with agreement withdrawn -> ask_consent"},
    52: {"utterances": [_say(52, "Actually, add me to the priority services register", final=False,
                             uid="register-again")],
         "note": "Partial register request does not count"},
    53: {"utterances": [_say(52, "Actually, add me to the priority services register after all; his concentrator "
                                 "has no battery backup.", uid="register-again")],
         "note": "Final register request -> register"},
    54: {"utterances": [_say(54, "The twenty-eighth works for me. I agree to the plan terms.")],
         "note": "Agreement re-granted -> set_up/twelve"},
    55: {"utterances": [_say(55, "That's your plan all set up.", "Agent")],
         "note": "Agent's set-up claim; plan tool still draft -> set_up"},
    56: {"desktop": {"plan": {"status": "active"}},
         "note": "Plan tool shows the plan active -> confirm_active"},
    57: {"telephony": {"status": "ended", "since": 57},
         "note": "Call ended -> closed; the register request persists"},
}


def _build() -> dict:
    live = _initial()
    steps = []
    for tick in range(60):
        live["clock"]["now"] = tick
        update = deepcopy(SCHEDULE.get(tick, {}))
        note = update.pop("note", "No decision-relevant change published at this tick")
        lines = update.pop("utterances", [])
        _merge(live, update)
        for line in lines:
            live["transcript"] = [u for u in live["transcript"] if u["utterance_id"] != line["utterance_id"]]
            live["transcript"].append(deepcopy(line))
        state = deepcopy(live)
        phone = state["telephony"]
        evidence = [f"telephony.status={phone['status']} since {phone['since']}",
                    "Published rules: prepared.rules", f"Witness: {note}"]
        newest = next(reversed(_customer_finals(state)), None)
        if newest:
            evidence.append(f"Latest final Customer {newest['utterance_id']}: {newest['text']}")
        steps.append({"t": tick, "state": state, "gold": reference(deepcopy(state)), "evidence": evidence})
    return {"episode_id": EPISODE_ID, "task_family": "support_call_assist", "scenario_id": "support_d",
            "title": "Energy account desk: meter reading, instalment plan and power cut",
            "tick_seconds": 2.0, "questions": deepcopy(QUESTIONS), "decision_spec": deepcopy(DECISION_SPEC),
            "steps": steps}


def scenarios() -> list[dict]:
    """One 60-tick training trajectory for the energy account desk."""
    return [_build()]
