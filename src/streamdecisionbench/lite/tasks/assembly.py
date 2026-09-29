"""Public-event assembly tasks with conditional application decisions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ROUTES = {
    "wait": "Keep the current operation visible; no additional instruction.",
    "advance": "Show the next required operation.",
    "repair": "Show a specific target and corrective method.",
    "escalate": "Request the designated specialist for the selected target.",
    "handoff": "Give control to the specialist whose badge is present.",
    "hold": "Suspend work under an open quality ticket.",
    "release": "Route the completed unit to its order destination.",
}

COMMON_RULES = [
    "This is a synthetic station instruction, not a general manufacturing standard. "
    "At every tick, use only records for this station and this unit. Records are "
    "ordered by tick then list position; a later record supersedes an earlier record "
    "of the same kind and target. Readings include their acceptance endpoints.",
    "A NO_READ scan does not erase a previous scan and does not count as a scan "
    "in any rule. Camera observations below "
    "confidence 0.8 have no effect. Speech, status heartbeats, other stations, and "
    "other unit serials do not change any decision.",
    "Current stage is the stage of the latest recognized productive record, even "
    "when that record reveals a defect. Returning to an earlier target moves the "
    "stage back. Quality tickets, badge records, speech, and NO_READ do not move it.",
    "Apply route precedence: any open quality ticket -> hold; specialist badged in "
    "-> handoff; a tool target with at least two out-of-range completed measurements "
    "since its latest replacement AND a latest out-of-range measurement -> escalate; "
    "otherwise a known defect or skipped earlier requirement -> repair; otherwise "
    "all stages complete -> release; otherwise current stage complete -> advance; "
    "otherwise wait. A later successful measurement withdraws escalation even if "
    "older failures remain. An open ticket outranks a present specialist.",
    "Select defects and repeated-failure targets by procedure stage order then by "
    "target order within that stage. A missing earlier stage is a repair using "
    "complete_missing; a known defect at that stage takes precedence over missing. "
    "Incomplete future stages are not defects. The advance target is the first "
    "incomplete stage. Repair method is determined by the selected defect, not speech.",
    "Quality-ticket state is tracked separately for each ticket identifier; closing "
    "one does not close another. Specialist presence follows the latest badge event. "
    "Snapshot t is published at tick t; the reference is held until the next tick. "
    "There are no hidden timers or changes between ticks.",
]


def _instruction(workflow: str) -> dict[str, Any]:
    if workflow == "gearbox":
        return {
            "workflow": workflow,
            "stage_order": ["intake", "seal", "cover", "fasten", "inspection"],
            "target_order": ["housing", "gasket", "cover", "J1", "J2", "inspection"],
            "torque_nm": {"J1": [9.2, 10.8], "J2": [22.0, 26.0]},
            "specialist": "mechanical_lead",
            "rules": COMMON_RULES + [
                "intake: latest housing scan must equal the order housing code. "
                "seal: latest accepted gasket observation must say present. cover: "
                "latest cover scan must equal the order cover code. Scans move to "
                "their named part's stage; gasket observations move to seal.",
                "fasten: a wrench engagement, rundown, or screw replacement at J1/J2 "
                "moves to fasten. Both joints need an in-range rundown after the "
                "latest cover scan and their own latest screw replacement. Out-of-range "
                "measurements before that reset are obsolete. Below range -> retorque; "
                "above range -> replace_fastener. Screw replacement removes the old "
                "measurement and resets its failure count.",
                "inspection: an inspection-terminal record moves to inspection. "
                "Its latest code must be PASS and its tick strictly later than all "
                "housing/cover scans, accepted gasket observations, rundowns and screw "
                "replacements. A same-tick or older PASS needs complete_missing. "
                "A current FAIL requires reinspect. Wrench engagement alone does not "
                "invalidate inspection. Incorrect housing/cover -> replace_part; "
                "observed absent gasket -> fit_gasket.",
            ],
        }
    if workflow == "cable_module":
        return {
            "workflow": workflow,
            "stage_order": ["intake", "mount", "terminate", "electrical", "label"],
            "target_order": ["connector", "orientation", "P1", "P2", "continuity", "insulation", "label", "accessory"],
            "crimp_height_mm": {"P1": [1.7, 1.9], "P2": [2.1, 2.3]},
            "continuity_max_ohm": 0.4,
            "insulation_min_mohm": 20.0,
            "specialist": "electrical_lead",
            "rules": COMMON_RULES + [
                "intake: latest connector scan must match the order connector code. "
                "mount: latest fixture record key_position must match the order key "
                "position. Connector scans move to intake; fixture records to mount. "
                "Incorrect connector -> replace_part; wrong orientation -> reseat.",
                "terminate: completed crimp-height readings or terminal replacements "
                "at P1/P2 move to terminate. Both need in-range measurements after "
                "the latest fixture record and their own latest replacement. Older "
                "measurements are obsolete. Either low or high height -> recrimp; "
                "replacement clears that target's reading and failure count.",
                "electrical: continuity and insulation meter records move to electrical. "
                "Need both readings strictly later than all connector scans, fixture "
                "records, crimp readings and terminal replacements. Continuity must be "
                "at most the published maximum; insulation at least the minimum. "
                "Outdated readings are missing, not current failures. Excess continuity "
                "-> trace_connection; low insulation -> replace_cable.",
                "label: label scans and accessory counter records move to label. "
                "Need the unit's exact serial code and the order accessory count, both "
                "strictly later than the newest meter reading. Incorrect code -> "
                "replace_label; incorrect count -> adjust_kit. A NO_READ never moves "
                "the stage. All conditions are stated in this instruction; no outside "
                "electrical or production knowledge is needed.",
            ],
        }
    raise ValueError(f"Unknown assembly workflow: {workflow}")


def _events(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event for event in state["station_log"]
        if event["station"] == state["station"]
        and event["serial"] == state["order"]["serial"]
        and event.get("confidence", 1.0) >= 0.8
        and not (event["kind"] == "scan" and event["code"] == "NO_READ")
    ]


def _latest(events: list[dict[str, Any]], kind: str, target: str | None = None) -> dict[str, Any] | None:
    return next((e for e in reversed(events) if e["kind"] == kind and (target is None or e.get("target") == target)), None)


def _stage(event: dict[str, Any], workflow: str) -> str | None:
    kind, target = event["kind"], event.get("target")
    if workflow == "gearbox":
        if kind == "scan":
            return {"housing": "intake", "cover": "cover"}.get(target)
        if kind == "gasket":
            return "seal"
        if kind in {"engage", "rundown", "replace_screw"} and target in {"J1", "J2"}:
            return "fasten"
        if kind == "inspection":
            return "inspection"
    else:
        if kind == "scan":
            return {"connector": "intake", "label": "label"}.get(target)
        if kind == "fixture":
            return "mount"
        if kind in {"crimp", "replace_terminal"} and target in {"P1", "P2"}:
            return "terminate"
        if kind in {"continuity", "insulation"}:
            return "electrical"
        if kind == "accessory_count":
            return "label"
    return None


def reference(state: dict[str, Any]) -> dict[str, str]:
    """Derive all six answers from the same public state, without hidden labels."""
    instruction, order = state["work_instruction"], state["order"]
    workflow = instruction["workflow"]
    if workflow not in {"gearbox", "cable_module"}:
        raise ValueError(f"Unknown assembly workflow: {workflow}")
    events = _events(state)
    stages = instruction["stage_order"]
    stage = next((s for e in reversed(events) if (s := _stage(e, workflow))), stages[0])
    done = dict.fromkeys(stages, False)
    defects: list[tuple[str, str, str]] = []
    repeated: list[str] = []
    default_target: dict[str, str]

    def check_part(target: str, expected: str, step: str) -> dict[str, Any] | None:
        reading = _latest(events, "scan", target)
        done[step] = bool(reading and reading["code"] == expected)
        if reading and not done[step]:
            defects.append((step, target, "replace_part"))
        return reading

    def tool_checks(kind: str, replacement_kind: str, ranges: dict[str, list[float]], reset_tick: int, step: str) -> None:
        passes = []
        for target, (low, high) in ranges.items():
            replacement = _latest(events, replacement_kind, target)
            cutoff = max(reset_tick, replacement["tick"] if replacement else -1)
            readings = [e for e in events if e["kind"] == kind and e.get("target") == target and e["tick"] > cutoff]
            newest = readings[-1] if readings else None
            passing = bool(newest and low <= newest["value"] <= high)
            passes.append(passing)
            if newest and not passing:
                method = "recrimp" if kind == "crimp" else ("retorque" if newest["value"] < low else "replace_fastener")
                defects.append((step, target, method))
                if sum(not low <= e["value"] <= high for e in readings) >= 2:
                    repeated.append(target)
        done[step] = all(passes)

    if workflow == "gearbox":
        default_target = {"intake": "housing", "seal": "gasket", "cover": "cover", "fasten": "J1", "inspection": "inspection"}
        check_part("housing", order["housing_code"], "intake")
        gasket = _latest(events, "gasket")
        done["seal"] = bool(gasket and gasket["observation"] == "present")
        if gasket and not done["seal"]:
            defects.append(("seal", "gasket", "fit_gasket"))
        cover = check_part("cover", order["cover_code"], "cover")
        tool_checks("rundown", "replace_screw", instruction["torque_nm"], cover["tick"] if cover else -1, "fasten")
        for joint in instruction["torque_nm"]:
            replacement = _latest(events, "replace_screw", joint)
            cutoff = max(cover["tick"] if cover else -1, replacement["tick"] if replacement else -1)
            if not any(e["kind"] == "rundown" and e.get("target") == joint and e["tick"] > cutoff for e in events):
                default_target["fasten"] = joint
                break
        changed = [e["tick"] for e in events if e["kind"] in {"scan", "gasket", "rundown", "replace_screw"}]
        inspection = _latest(events, "inspection")
        current = bool(inspection and inspection["tick"] > max(changed, default=-1))
        done["inspection"] = bool(current and inspection["code"] == "PASS")
        if current and not done["inspection"]:
            defects.append(("inspection", "inspection", "reinspect"))
    else:
        default_target = {"intake": "connector", "mount": "orientation", "terminate": "P1", "electrical": "continuity", "label": "label"}
        check_part("connector", order["connector_code"], "intake")
        fixture = _latest(events, "fixture")
        done["mount"] = bool(fixture and fixture["key_position"] == order["key_position"])
        if fixture and not done["mount"]:
            defects.append(("mount", "orientation", "reseat"))
        tool_checks("crimp", "replace_terminal", instruction["crimp_height_mm"], fixture["tick"] if fixture else -1, "terminate")
        for terminal in instruction["crimp_height_mm"]:
            replacement = _latest(events, "replace_terminal", terminal)
            cutoff = max(fixture["tick"] if fixture else -1, replacement["tick"] if replacement else -1)
            if not any(e["kind"] == "crimp" and e.get("target") == terminal and e["tick"] > cutoff for e in events):
                default_target["terminate"] = terminal
                break
        changed = [e["tick"] for e in events if e["kind"] in {"fixture", "crimp", "replace_terminal"} or (e["kind"] == "scan" and e.get("target") == "connector")]
        threshold = max(changed, default=-1)
        electrical_passes = []
        for target, limit, lower, method in [
            ("continuity", instruction["continuity_max_ohm"], False, "trace_connection"),
            ("insulation", instruction["insulation_min_mohm"], True, "replace_cable"),
        ]:
            reading = _latest(events, target)
            current = bool(reading and reading["tick"] > threshold)
            passing = bool(current and (reading["value"] >= limit if lower else reading["value"] <= limit))
            electrical_passes.append(passing)
            if current and not passing:
                defects.append(("electrical", target, method))
        done["electrical"] = all(electrical_passes)
        if electrical_passes[0] and not electrical_passes[1]:
            default_target["electrical"] = "insulation"
        meter_tick = max((e["tick"] for e in events if e["kind"] in {"continuity", "insulation"}), default=-1)
        label = _latest(events, "scan", "label")
        count = _latest(events, "accessory_count")
        label_current = bool(label and label["tick"] > meter_tick)
        count_current = bool(count and count["tick"] > meter_tick)
        label_ok = bool(label_current and label["code"] == order["serial"])
        count_ok = bool(count_current and count["value"] == order["accessory_count"])
        done["label"] = label_ok and count_ok
        if label_current and not label_ok:
            defects.append(("label", "label", "replace_label"))
        if count_current and not count_ok:
            defects.append(("label", "accessory", "adjust_kit"))
        if label_ok and not count_ok:
            default_target["label"] = "accessory"

    for step in stages[:stages.index(stage)]:
        if not done[step] and not any(d[0] == step for d in defects):
            defects.append((step, default_target[step], "complete_missing"))
    defects.sort(key=lambda d: (stages.index(d[0]), instruction["target_order"].index(d[1])))
    tickets: dict[str, str] = {}
    for event in events:
        if event["kind"] == "quality_ticket":
            tickets[event["ticket"]] = event["status"]
    badge = _latest(events, "badge")
    lead_present = bool(badge and badge["direction"] == "in")
    result = {"route": "wait", "stage": stage, "target": "none", "method": "none", "next_step": "none", "destination": "none"}
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
        "complete_missing": "Complete or repeat the required target measurement/operation because evidence is missing or obsolete.",
        "replace_part": "Replace the mismatching scanned part.",
        "fit_gasket": "Fit the missing gasket.",
        "retorque": "Retighten the selected joint whose latest torque is below range.",
        "replace_fastener": "Replace the selected fastener whose latest torque is above range.",
        "reinspect": "Repeat final inspection after its current failure.",
        "reseat": "Reseat the connector in the specified orientation.",
        "recrimp": "Rework the terminal with an out-of-range crimp height.",
        "trace_connection": "Check the connection identified by excessive continuity resistance.",
        "replace_cable": "Replace the cable under the stated low-insulation rule.",
        "replace_label": "Replace the incorrect serial label.",
        "adjust_kit": "Correct the accessory count for this order.",
    }
    used_methods = (["none", "complete_missing", "replace_part", "fit_gasket", "retorque", "replace_fastener", "reinspect"]
                    if instruction["workflow"] == "gearbox" else
                    ["none", "complete_missing", "replace_part", "reseat", "recrimp", "trace_connection", "replace_cable", "replace_label", "adjust_kit"])
    return {
        "route": {"type": "choice", "instructions": "Apply the work_instruction precedence to select the application's route. Infer from public records, not another question's generated answer.", "criteria": deepcopy(ROUTES)},
        "stage": {"type": "choice", "instructions": "Which procedure stage does the newest productive record concern? This answer is always displayed, including holds and handoffs.", "criteria": {s: f"The {s} stage in the public procedure." for s in instruction["stage_order"]}},
        "target": {"type": "choice", "instructions": "Derive the route independently. For repair, select its first-priority defect/missing target. For escalate, select its first-priority repeated-failure target. Otherwise choose none.", "criteria": {"none": "No repair or escalation target.", **{t: f"The {t} target." for t in instruction["target_order"]}}},
        "method": {"type": "choice", "instructions": "Derive the route and selected target from the state. For repair choose the specified remedy; for every other route choose none.", "criteria": {m: methods[m] for m in used_methods}},
        "next_step": {"type": "choice", "instructions": "For advance, select the first incomplete stage in procedure order. For every other route choose none.", "criteria": {"none": "No advance instruction.", **{s: f"Advance to {s}." for s in instruction["stage_order"]}}},
        "destination": {"type": "choice", "instructions": "For hold choose quality_desk; for handoff/escalate the work instruction's specialist; for release the order destination; otherwise none.", "criteria": {"none": "No recipient or destination.", "quality_desk": "The quality review desk.", "mechanical_lead": "The mechanical station lead.", "electrical_lead": "The electrical station lead.", "outbound_lane": "The finished-product outbound lane.", "validation_rack": "The engineering validation rack."}},
    }


def _schedule(workflow: str) -> dict[int, list[dict[str, Any]]]:
    def e(kind: str, **values: Any) -> dict[str, Any]:
        return {"kind": kind, **values}

    if workflow == "gearbox":
        return {
            0: [e("scan", target="housing", code="GH-R")],
            2: [e("gasket", observation="present", confidence=0.95)],
            4: [e("scan", target="cover", code="GC-L")],
            6: [e("scan", target="cover", code="GC-R")],
            8: [e("rundown", target="J1", value=9.2)],
            10: [e("rundown", target="J2", value=21.8)],
            12: [e("inspection", code="PASS")],
            14: [e("engage", target="J2")],
            16: [e("rundown", target="J2", value=26.4)],
            18: [e("speech", speaker="worker", text="The lead is on the way; we can call it finished.")],
            19: [e("badge", direction="in")],
            21: [e("quality_ticket", ticket="Q71", status="open")],
            23: [e("quality_ticket", ticket="Q72", status="open")],
            24: [e("quality_ticket", ticket="Q71", status="closed")],
            25: [e("quality_ticket", ticket="Q72", status="closed")],
            27: [e("replace_screw", target="J2")],
            29: [e("rundown", target="J2", value=26.0)],
            31: [e("badge", direction="out")],
            33: [e("inspection", code="PASS")],
            35: [e("gasket", observation="absent", confidence=0.62)],
            37: [e("gasket", observation="absent", confidence=0.93)],
            39: [e("gasket", observation="present", confidence=0.97)],
            41: [e("inspection", code="PASS")],
            43: [e("scan", target="cover", code="GC-L", serial="UNIT-OTHER")],
            45: [e("rundown", target="J1", value=11.1)],
            47: [e("replace_screw", target="J1")],
            49: [e("rundown", target="J1", value=10.8)],
            51: [e("inspection", code="FAIL")],
            53: [e("inspection", code="PASS")],
            55: [e("scan", target="housing", code="NO_READ")],
            57: [e("rundown", target="J2", value=40.0, station="ST-OTHER")],
        }
    return {
        0: [e("scan", target="connector", code="CN-7")],
        2: [e("fixture", key_position="north")],
        4: [e("fixture", key_position="south")],
        6: [e("crimp", target="P1", value=1.9)],
        8: [e("crimp", target="P2", value=2.05)],
        10: [e("crimp", target="P2", value=2.35)],
        12: [e("quality_ticket", ticket="Q81", status="open")],
        14: [e("badge", direction="in")],
        16: [e("quality_ticket", ticket="Q81", status="closed")],
        18: [e("replace_terminal", target="P2")],
        20: [e("crimp", target="P2", value=2.3)],
        22: [e("badge", direction="out")],
        24: [e("continuity", value=0.5)],
        26: [e("insulation", value=25.0)],
        28: [e("continuity", value=0.4)],
        30: [e("scan", target="label", code="CM-710")],
        32: [e("scan", target="label", code="CM-701")],
        34: [e("accessory_count", value=1)],
        36: [e("accessory_count", value=2)],
        38: [e("crimp", target="P1", value=1.8)],
        40: [e("scan", target="label", code="CM-701")],
        42: [e("continuity", value=0.3)],
        44: [e("insulation", value=19.9)],
        46: [e("insulation", value=20.0)],
        48: [e("scan", target="label", code="CM-701")],
        50: [e("accessory_count", value=2)],
        52: [e("insulation", value=0.0, serial="CM-OTHER")],
        54: [e("scan", target="connector", code="NO_READ")],
        56: [e("speech", speaker="nearby_worker", text="My connector is north-facing; send mine to the outbound lane.")],
        58: [e("quality_ticket", ticket="Q82", status="open")],
        59: [e("quality_ticket", ticket="Q82", status="closed")],
    }


def scenarios() -> list[dict[str, Any]]:
    """Return two independent, 60-tick public-event episodes."""
    episodes = []
    for suffix, workflow, title, order in [
        ("a", "gearbox", "Gearbox cover: mismatched part, joint rework and quality hold", {
            "serial": "GB-4471", "housing_code": "GH-R", "cover_code": "GC-R", "destination": "outbound_lane"}),
        ("b", "cable_module", "Cable module: orientation, crimp repair and stale electrical checks", {
            "serial": "CM-701", "connector_code": "CN-7", "key_position": "south", "accessory_count": 2, "destination": "validation_rack"}),
    ]:
        instruction = _instruction(workflow)
        schedule = _schedule(workflow)
        log: list[dict[str, Any]] = []
        steps = []
        for tick in range(60):
            new_events = []
            for index, raw in enumerate(schedule.get(tick, [])):
                event = {"event_id": f"{suffix}-{tick}-{index}", "tick": tick, "station": f"ST-{suffix.upper()}", "serial": order["serial"], **raw}
                log.append(event)
                new_events.append(event["event_id"])
            if not new_events:
                heartbeat = {"event_id": f"{suffix}-{tick}-heartbeat", "tick": tick, "station": f"ST-{suffix.upper()}", "serial": order["serial"], "kind": "heartbeat", "message": "Station link active; no new device record."}
                log.append(heartbeat)
                new_events.append(heartbeat["event_id"])
            state = {
                "station": f"ST-{suffix.upper()}",
                "clock": {"tick": tick},
                "order": deepcopy(order),
                "work_instruction": deepcopy(instruction),
                "station_log": deepcopy(log),
            }
            steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": new_events})
        episodes.append({
            "episode_id": f"lite_assembly_{suffix}", "task_family": "procedural_coaching",
            "scenario_id": f"assembly_{workflow}", "title": title, "tick_seconds": 2.0,
            "questions": _questions(instruction),
            "decision_spec": {"route_question": "route", "always": ["stage"], "branches": {
                "wait": [], "advance": ["next_step"], "repair": ["target", "method"],
                "escalate": ["target", "destination"], "handoff": ["destination"],
                "hold": ["destination"], "release": ["destination"],
            }},
            "steps": steps,
        })
    return episodes
