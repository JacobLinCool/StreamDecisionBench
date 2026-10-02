"""Training variant of the assembly family: an e-bike battery pack station.

A new workflow (``battery_pack``) under the family's shared station rules:
carrier intake, two tab welds with resistance ranges, a BMS firmware flash,
an isolation test that rework makes obsolete, and a label/seal-tape pack check
that must be refreshed after every new isolation reading. The common rules,
routes and record filters are the family's published ones; the story, unit,
station, codes and utterances are new.

Story: the board is flashed before the cell carrier arrives; a lead's clean
re-measurement withdraws a tab escalation; repeated isolation failures stay
repairs, then a quality ticket holds the pack and is later reopened over a
wrong label; after release a carrier reseat voids both welds and the isolation
evidence, so the missing weld targets are completed one at a time around a
wrong-version flash (a known firmware defect that stays repairable while the
operator is back at weld) and a tab cut-in.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from streamdecisionbench.lite.tasks.assembly import COMMON_RULES, ROUTES, _events, _latest

EPISODE_ID = "train_assembly_d"
SCENARIO_ID = "assembly_d"
WORKFLOW = "battery_pack"
STATION = "PK-4"
OTHER_STATION = "PK-9"
# The pack built at the neighbouring PK-9 bay; late in the episode it is parked
# on PK-4's conveyor (under PK-4's camera) while PK-9 clears a jam.
NEIGHBOUR_SERIAL = "EB-5326"
TICKET = "QIR-3086"
WELD_TARGETS = ("W1", "W2")

ORDER = {
    "serial": "EB-5318",
    "carrier_code": "HC-36B",
    "firmware_version": "2.4.1",
    "tape_count": 3,
    "destination": "aging_rack",
}

INSTRUCTION = {
    "workflow": WORKFLOW,
    "stage_order": ["intake", "weld", "firmware", "isolation", "pack"],
    "target_order": ["carrier", "W1", "W2", "bms", "isolation", "label", "seal_tape"],
    "weld_resistance_milliohm": {"W1": [0.20, 0.35], "W2": [0.30, 0.45]},
    "isolation_min_megaohm": 50.0,
    "specialist": "battery_lead",
    "rules": COMMON_RULES + [
        "intake: the latest carrier scan (scan with target carrier) must equal "
        "the order carrier code; a different code -> swap_carrier. Carrier scans "
        "move to intake.",
        "weld: probe contacts (probe), tab_resistance readings and tab "
        "replacements (replace_tab) at W1/W2 move to weld. For each of W1 and W2, "
        "the newest reading strictly later than the latest carrier scan and that "
        "target's latest tab replacement must be within its range; readings at or "
        "before either reset are obsolete and do not count as failures. Above "
        "range -> reweld; below range -> inspect_weld. A tab replacement removes "
        "that target's earlier readings and resets its failure count. A probe "
        "contact is not a reading. W1 and W2 are the only tool targets for "
        "repeated failure.",
        "firmware: BMS flash records (flash) move to firmware. The latest flash "
        "version must equal the order firmware version; a different version -> "
        "reflash. No other record invalidates a flash. A wrong-version flash "
        "stays a known firmware defect (reflash) until a later flash matches, "
        "even while the current stage is an earlier one.",
        "isolation: isolation meter readings (isolation) move to isolation. The "
        "latest reading must be strictly later than every carrier scan, "
        "tab_resistance reading, tab replacement and flash record, and at least "
        "the published minimum. An outdated reading is missing, not a current "
        "failure. Below the minimum -> replace_insulator. Probe contacts do not "
        "outdate it.",
        "pack: label scans (scan with target label) and seal-tape counts "
        "(tape_count, camera observations) move to pack. The latest label scan "
        "must equal the unit serial and the latest seal-tape count must equal the "
        "order tape count, both strictly later than the newest isolation reading. "
        "Incorrect label -> relabel; incorrect count -> correct_tape. A label "
        "scan or seal-tape count at or before the newest isolation reading is "
        "missing, not incorrect.",
        "A known defect (a current record with a wrong value, such as a "
        "wrong-version flash) is selected in stage order even when its stage "
        "comes after the current stage; \"incomplete future stages are not "
        "defects\" covers only future stages whose required records are missing "
        "or outdated. complete_missing selects the missing stage's first target, "
        "in target order, without a current passing record. All conditions are "
        "stated in this instruction; no outside battery or electrical knowledge "
        "is needed.",
    ],
}


def _stage(event: dict[str, Any]) -> str | None:
    kind, target = event["kind"], event.get("target")
    if kind == "scan":
        return {"carrier": "intake", "label": "pack"}.get(target)
    if kind in {"probe", "tab_resistance", "replace_tab"} and target in WELD_TARGETS:
        return "weld"
    if kind == "flash":
        return "firmware"
    if kind == "isolation":
        return "isolation"
    if kind == "tape_count":
        return "pack"
    return None


def reference(state: dict[str, Any]) -> dict[str, str]:
    """Derive all six answers from the public state alone (no tick index, gold or hidden fields)."""
    instruction, order = state["work_instruction"], state["order"]
    if instruction["workflow"] != WORKFLOW:
        raise ValueError(f"Unknown assembly workflow: {instruction['workflow']}")
    events = _events(state)
    stages, targets = instruction["stage_order"], instruction["target_order"]
    stage = next((s for e in reversed(events) if (s := _stage(e))), stages[0])
    done = dict.fromkeys(stages, False)
    missing_target: dict[str, str] = {}
    defects: list[tuple[str, str, str]] = []
    repeated: list[str] = []

    # intake: latest carrier scan equals the order carrier code.
    carrier = _latest(events, "scan", "carrier")
    done["intake"] = bool(carrier and carrier["code"] == order["carrier_code"])
    if carrier and not done["intake"]:
        defects.append(("intake", "carrier", "swap_carrier"))
    missing_target["intake"] = "carrier"

    # weld: newest reading after the latest carrier scan and the target's own replacement.
    carrier_tick = carrier["tick"] if carrier else -1
    weld_passes = []
    for target in WELD_TARGETS:
        low, high = instruction["weld_resistance_milliohm"][target]
        replacement = _latest(events, "replace_tab", target)
        cutoff = max(carrier_tick, replacement["tick"] if replacement else -1)
        readings = [e for e in events
                    if e["kind"] == "tab_resistance" and e.get("target") == target and e["tick"] > cutoff]
        newest = readings[-1] if readings else None
        passing = bool(newest and low <= newest["value"] <= high)
        weld_passes.append(passing)
        if newest and not passing:
            defects.append(("weld", target, "reweld" if newest["value"] > high else "inspect_weld"))
            if sum(not low <= e["value"] <= high for e in readings) >= 2:
                repeated.append(target)
        if not passing:
            missing_target.setdefault("weld", target)
    done["weld"] = all(weld_passes)

    # firmware: latest flash version equals the order firmware version.
    flash = _latest(events, "flash")
    done["firmware"] = bool(flash and flash["version"] == order["firmware_version"])
    if flash and not done["firmware"]:
        defects.append(("firmware", "bms", "reflash"))
    missing_target["firmware"] = "bms"

    # isolation: latest reading strictly later than every carrier scan, weld reading,
    # tab replacement and flash; outdated readings are missing, not failures.
    changed = [e["tick"] for e in events
               if (e["kind"] == "scan" and e.get("target") == "carrier")
               or (e["kind"] in {"tab_resistance", "replace_tab"} and e.get("target") in WELD_TARGETS)
               or e["kind"] == "flash"]
    isolation = _latest(events, "isolation")
    isolation_current = bool(isolation and isolation["tick"] > max(changed, default=-1))
    done["isolation"] = bool(isolation_current and isolation["value"] >= instruction["isolation_min_megaohm"])
    if isolation_current and not done["isolation"]:
        defects.append(("isolation", "isolation", "replace_insulator"))
    missing_target["isolation"] = "isolation"

    # pack: label and seal-tape count both strictly later than the newest isolation reading.
    isolation_tick = max((e["tick"] for e in events if e["kind"] == "isolation"), default=-1)
    label = _latest(events, "scan", "label")
    count = _latest(events, "tape_count")
    label_current = bool(label and label["tick"] > isolation_tick)
    count_current = bool(count and count["tick"] > isolation_tick)
    label_ok = bool(label_current and label["code"] == order["serial"])
    count_ok = bool(count_current and count["value"] == order["tape_count"])
    done["pack"] = label_ok and count_ok
    if label_current and not label_ok:
        defects.append(("pack", "label", "relabel"))
    if count_current and not count_ok:
        defects.append(("pack", "seal_tape", "correct_tape"))
    missing_target["pack"] = "label" if not label_ok else "seal_tape"

    for step in stages[:stages.index(stage)]:
        if not done[step] and not any(d[0] == step for d in defects):
            defects.append((step, missing_target[step], "complete_missing"))
    defects.sort(key=lambda d: (stages.index(d[0]), targets.index(d[1])))
    repeated.sort(key=targets.index)

    tickets: dict[str, str] = {}
    for event in events:
        if event["kind"] == "quality_ticket":
            tickets[event["ticket"]] = event["status"]
    badge = _latest(events, "badge")
    lead_present = bool(badge and badge["direction"] == "in")

    result = {"route": "wait", "stage": stage, "target": "none", "method": "none",
              "next_step": "none", "destination": "none"}
    if "open" in tickets.values():
        result.update(route="hold", destination="quality_desk")
    elif lead_present:
        result.update(route="handoff", destination=instruction["specialist"])
    elif repeated:
        result.update(route="escalate", target=repeated[0], destination=instruction["specialist"])
    elif defects:
        result.update(route="repair", target=defects[0][1], method=defects[0][2])
    elif all(done.values()):
        result.update(route="release", destination=order["destination"])
    elif done[stage]:
        result.update(route="advance", next_step=next(s for s in stages if not done[s]))
    return result


def _questions(instruction: dict[str, Any]) -> dict[str, Any]:
    methods = {
        "none": "No repair is selected.",
        "complete_missing": "Complete or repeat the selected target's required record because its evidence is missing or outdated.",
        "swap_carrier": "Swap in the cell carrier that the order specifies.",
        "reweld": "Reweld the selected tab whose latest resistance is above its range.",
        "inspect_weld": "Inspect the selected tab weld whose latest resistance is below its range.",
        "reflash": "Flash the battery management board again with the order firmware version.",
        "replace_insulator": "Replace the insulator sheet under the stated low-isolation rule.",
        "relabel": "Apply a new enclosure label carrying the unit serial.",
        "correct_tape": "Correct the seal-tape strip count for this order.",
    }
    target_text = {
        "carrier": "The cell carrier.",
        "W1": "Weld tab W1.",
        "W2": "Weld tab W2.",
        "bms": "The battery management board firmware.",
        "isolation": "The pack isolation test.",
        "label": "The enclosure serial label.",
        "seal_tape": "The seal-tape strip count.",
    }
    return {
        "route": {"type": "choice", "instructions": "Apply the work_instruction precedence to select the application's route. Infer from public records, not another question's generated answer.", "criteria": deepcopy(ROUTES)},
        "stage": {"type": "choice", "instructions": "Which procedure stage does the newest productive record concern? This answer is always displayed, including holds and handoffs.", "criteria": {s: f"The {s} stage in the public procedure." for s in instruction["stage_order"]}},
        "target": {"type": "choice", "instructions": "Derive the route independently. For repair, select its first-priority defect/missing target. For escalate, select its first-priority repeated-failure target. Otherwise choose none.", "criteria": {"none": "No repair or escalation target.", **{t: target_text[t] for t in instruction["target_order"]}}},
        "method": {"type": "choice", "instructions": "Derive the route and selected target from the state. For repair choose the specified remedy; for every other route choose none.", "criteria": methods},
        "next_step": {"type": "choice", "instructions": "For advance, select the first incomplete stage in procedure order. For every other route choose none.", "criteria": {"none": "No advance instruction.", **{s: f"Advance to {s}." for s in instruction["stage_order"]}}},
        "destination": {"type": "choice", "instructions": "For hold choose quality_desk; for handoff/escalate the work instruction's specialist; for release the order destination; otherwise none.", "criteria": {
            "none": "No recipient or destination.",
            "quality_desk": "The quality review desk.",
            "battery_lead": "The battery pack station lead.",
            "firmware_lead": "The firmware engineering lead.",
            "aging_rack": "The pack aging rack.",
            "shipping_dock": "The finished-goods shipping dock.",
        }},
    }


def _schedule() -> dict[int, list[dict[str, Any]]]:
    def e(kind: str, **values: Any) -> dict[str, Any]:
        return {"kind": kind, **values}

    return {
        0: [e("flash", version="2.4.1")],
        1: [e("speech", speaker="operator", text="Cell cart is running late, so I loaded the board image first.")],
        2: [e("scan", target="carrier", code="HC-48B")],
        4: [e("scan", target="carrier", code="HC-36B")],
        6: [e("probe", target="W1")],
        7: [e("tab_resistance", target="W1", value=0.38)],
        9: [e("tab_resistance", target="W1", value=0.41)],
        12: [e("badge", direction="in")],
        13: [e("speech", speaker="battery_lead", text="Cleaned the probe tips; measuring tab one again before anyone rewelds it.")],
        14: [e("tab_resistance", target="W1", value=0.28)],
        15: [e("tab_resistance", target="W2", value=0.24)],
        16: [e("tab_resistance", target="W2", value=0.30)],
        17: [e("badge", direction="out")],
        19: [e("isolation", value=41.0)],
        20: [e("speech", speaker="operator", text="Swapping in a thicker insulator sheet before the next megaohm test.")],
        21: [e("isolation", value=46.5)],
        22: [e("quality_ticket", ticket=TICKET, status="open")],
        24: [e("isolation", value=50.0)],
        26: [e("quality_ticket", ticket=TICKET, status="closed")],
        28: [e("tape_count", value=4, confidence=0.57)],
        29: [e("tape_count", value=3, confidence=0.86)],
        30: [e("speech", speaker="quality_inspector", text="The insulator incident report still lacks my signature, so I am reopening it briefly.")],
        31: [e("quality_ticket", ticket=TICKET, status="open")],
        32: [e("scan", target="label", code="EB-6042")],
        34: [e("quality_ticket", ticket=TICKET, status="closed")],
        36: [e("scan", target="label", code="EB-5318")],
        38: [e("badge", direction="in", station=OTHER_STATION, serial=NEIGHBOUR_SERIAL)],
        39: [e("speech", speaker="operator", text="Carrier clamp sprang open and tugged the board harness; reseating the carrier and scanning it again.")],
        40: [e("scan", target="carrier", code="NO_READ")],
        41: [e("scan", target="carrier", code="HC-36B")],
        # The PK-9 programming bench, still on the old image, logs a flash under this unit's serial.
        42: [e("flash", version="2.3.9", station=OTHER_STATION)],
        43: [e("isolation", value=61.0)],
        45: [e("tab_resistance", target="W1", value=0.31)],
        46: [e("flash", version="2.3.9")],
        48: [e("tab_resistance", target="W2", value=0.26)],
        49: [e("speech", speaker="operator", text="The strip on tab two is cracked along its edge, so I am cutting in a fresh nickel strip.")],
        50: [e("replace_tab", target="W2")],
        52: [e("tab_resistance", target="W2", value=0.45)],
        53: [e("speech", speaker="operator", text="PK-9 has a jammed conveyor, so their pack is parked on ours for a few minutes.")],
        54: [e("flash", version="2.4.1")],
        55: [e("isolation", value=54.2)],
        56: [e("probe", target="W2")],
        57: [e("scan", target="label", code="EB-5318"), e("tape_count", value=2, confidence=0.80)],
        58: [e("tape_count", value=3, confidence=0.89, serial=NEIGHBOUR_SERIAL)],
        59: [e("tape_count", value=3, confidence=0.94)],
    }


def scenarios() -> list[dict[str, Any]]:
    """Return the single 60-tick public-event episode of this training variant."""
    schedule = _schedule()
    log: list[dict[str, Any]] = []
    steps = []
    for tick in range(60):
        new_events = []
        for index, raw in enumerate(schedule.get(tick, [])):
            event = {"event_id": f"d-{tick}-{index}", "tick": tick, "station": STATION, "serial": ORDER["serial"], **raw}
            log.append(event)
            new_events.append(event["event_id"])
        if not new_events:
            heartbeat = {"event_id": f"d-{tick}-heartbeat", "tick": tick, "station": STATION, "serial": ORDER["serial"],
                         "kind": "heartbeat", "message": "Pack bay controller online; device queue empty."}
            log.append(heartbeat)
            new_events.append(heartbeat["event_id"])
        state = {
            "station": STATION,
            "clock": {"tick": tick},
            "order": deepcopy(ORDER),
            "work_instruction": deepcopy(INSTRUCTION),
            "station_log": deepcopy(log),
        }
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": new_events})
    return [{
        "episode_id": EPISODE_ID,
        "task_family": "procedural_coaching",
        "scenario_id": SCENARIO_ID,
        "title": "E-bike battery pack: early firmware, insulation ticket and carrier reseat",
        "tick_seconds": 2.0,
        "questions": _questions(INSTRUCTION),
        "decision_spec": {"route_question": "route", "always": ["stage"], "branches": {
            "wait": [], "advance": ["next_step"], "repair": ["target", "method"],
            "escalate": ["target", "destination"], "handoff": ["destination"],
            "hold": ["destination"], "release": ["destination"],
        }},
        "steps": steps,
    }]
