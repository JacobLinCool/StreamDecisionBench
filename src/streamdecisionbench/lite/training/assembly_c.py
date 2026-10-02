"""Training variant assembly_c: a hydraulic pump cartridge station (procedural coaching).

A new workflow in the assembly family design. It reuses the family's published
COMMON_RULES, ROUTES and record filters, and adds its own pump_cartridge rules:
a pump-body scan, press-fit forces at two bearings, a camera check of the shaft
seal's lip orientation, a pressure-decay leak test and a flow test. Every gold
answer is computed by ``reference`` from the public state alone.

Story: the first body scan shows the wrong casting variant and the assembler
presses the front bearing into it anyway (an earlier-stage defect outlives the
stage move); the right body then makes that press obsolete. A NO_READ during
bearing work, a front bearing that escalates on two high forces and is withdrawn
by a passing press before anyone arrives, two quality notifications closed in
reverse order during an advance, a leak that brings the hydraulics lead in, a
notification she opens while present and that outlasts her badge-out, and a
neighbouring unit's flow reading follow. After release a rear-bearing recall
swap is followed by a rushed leak test that skips the rear press
(complete_missing from the pressure stage); the late press advances straight
past the finished seal stage, and a camera check after it finds the seal lip
flipped before the final retests. Every repair or escalation target belongs to
the current stage or an earlier one.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from streamdecisionbench.lite.tasks.assembly import COMMON_RULES, ROUTES, _events, _latest

WORKFLOW = "pump_cartridge"
STATION = "HYD-3"
SUFFIX = "pc"

ORDER = {
    "serial": "HPC-2093",
    "body_code": "PB-46S",
    "seal_lip": "pressure_side",
    "destination": "spares_crate",
}

WORKFLOW_RULES = [
    "pump_cartridge records: body scans (kind scan, target body) move the stage to "
    "intake; press-fit force readings (kind press) and bearing swaps (kind "
    "bearing_swap) at front_bearing or rear_bearing move it to bearing; seal camera "
    "observations (kind seal_cam) move it to seal; pressure-decay tests (kind "
    "pressure_decay) move it to pressure; flow tests (kind flow) move it to "
    "functional. These are the only productive records; no other kind moves the "
    "stage or counts as rework.",
    "intake: the latest body scan code must equal the order body_code; a mismatching "
    "latest scan -> swap_body. seal: the latest accepted seal observation must report "
    "the order seal_lip orientation; any other orientation -> refit_seal.",
    "bearing: front_bearing and rear_bearing each need a press reading inside its "
    "press_force_kn range with a tick strictly later than both the latest body scan "
    "and that bearing's own latest bearing swap. Readings at or before either point "
    "are obsolete: they neither satisfy the stage nor count as failures. A current "
    "reading below range -> repress; above range -> replace_bearing. A bearing swap "
    "clears that bearing's earlier readings and resets its failure count. Press "
    "readings are the only tool measurements for repeated-failure escalation, "
    "counted per bearing over its current readings.",
    "pressure: the latest pressure-decay test is current only if its tick is strictly "
    "later than every body scan, press reading, bearing swap and accepted seal "
    "observation. A current decay at most pressure_decay_max_kpa passes; above it -> "
    "locate_leak. An obsolete test is missing evidence, not a failure.",
    "functional: the latest flow test is current only if its tick is strictly later "
    "than the newest pressure-decay test, whatever that test's result or currency "
    "(with no pressure-decay test yet, any flow test is current). A current flow at "
    "least flow_min_lpm passes; below it -> bleed_retest. An obsolete flow test is "
    "missing evidence, not a failure.",
    "For complete_missing, the target is the first target in target_order of the "
    "missing stage that lacks current passing evidence. Pressure-decay and flow tests "
    "never trigger escalation. The unit is complete only when all five stages are "
    "satisfied at once. All conditions are stated in this instruction; no outside "
    "hydraulic or production knowledge is needed.",
]

INSTRUCTION: dict[str, Any] = {
    "workflow": WORKFLOW,
    "stage_order": ["intake", "bearing", "seal", "pressure", "functional"],
    "target_order": ["body", "front_bearing", "rear_bearing", "seal", "pressure_decay", "flow"],
    "press_force_kn": {"front_bearing": [3.6, 4.4], "rear_bearing": [5.5, 6.5]},
    "pressure_decay_max_kpa": 1.5,
    "flow_min_lpm": 18.5,
    "specialist": "hydraulics_lead",
    "rules": COMMON_RULES + WORKFLOW_RULES,
}

BEARINGS = ("front_bearing", "rear_bearing")
HEARTBEAT = "Telemetry poll idle at the press cell."


def _stage(event: dict[str, Any]) -> str | None:
    """The stage a productive record moves to; None for every other record."""
    kind, target = event["kind"], event.get("target")
    if kind == "scan" and target == "body":
        return "intake"
    if kind in {"press", "bearing_swap"} and target in BEARINGS:
        return "bearing"
    if kind == "seal_cam":
        return "seal"
    if kind == "pressure_decay":
        return "pressure"
    if kind == "flow":
        return "functional"
    return None


def reference(state: dict[str, Any]) -> dict[str, str]:
    """Derive all six answers from the public state alone (no tick index, gold or hidden fields)."""
    instruction, order = state["work_instruction"], state["order"]
    if instruction["workflow"] != WORKFLOW:
        raise ValueError(f"Unknown assembly workflow: {instruction['workflow']}")
    events = _events(state)
    stages, targets = instruction["stage_order"], instruction["target_order"]
    stage = next((s for e in reversed(events) if (s := _stage(e))), stages[0])
    done: dict[str, bool] = {}
    defects: list[tuple[str, str, str]] = []
    repeated: list[str] = []
    missing_target = {"intake": "body", "bearing": "front_bearing", "seal": "seal",
                      "pressure": "pressure_decay", "functional": "flow"}

    body = _latest(events, "scan", "body")
    done["intake"] = bool(body and body["code"] == order["body_code"])
    if body and not done["intake"]:
        defects.append(("intake", "body", "swap_body"))
    body_tick = body["tick"] if body else -1

    ranges = instruction["press_force_kn"]
    unmet = []
    for target in [t for t in targets if t in ranges]:
        low, high = ranges[target]
        swap = _latest(events, "bearing_swap", target)
        cutoff = max(body_tick, swap["tick"] if swap else -1)
        readings = [e for e in events if e["kind"] == "press" and e.get("target") == target and e["tick"] > cutoff]
        newest = readings[-1] if readings else None
        passing = bool(newest and low <= newest["value"] <= high)
        if not passing:
            unmet.append(target)
        if newest and not passing:
            defects.append(("bearing", target, "repress" if newest["value"] < low else "replace_bearing"))
            if sum(not low <= e["value"] <= high for e in readings) >= 2:
                repeated.append(target)
    done["bearing"] = not unmet
    if unmet:
        missing_target["bearing"] = unmet[0]

    seal = _latest(events, "seal_cam")
    done["seal"] = bool(seal and seal["orientation"] == order["seal_lip"])
    if seal and not done["seal"]:
        defects.append(("seal", "seal", "refit_seal"))

    upstream = max((e["tick"] for e in events if _stage(e) in {"intake", "bearing", "seal"}), default=-1)
    pressure = _latest(events, "pressure_decay")
    pressure_current = bool(pressure and pressure["tick"] > upstream)
    done["pressure"] = bool(pressure_current and pressure["value"] <= instruction["pressure_decay_max_kpa"])
    if pressure_current and not done["pressure"]:
        defects.append(("pressure", "pressure_decay", "locate_leak"))

    newest_pressure = max((e["tick"] for e in events if e["kind"] == "pressure_decay"), default=-1)
    flow = _latest(events, "flow")
    flow_current = bool(flow and flow["tick"] > newest_pressure)
    done["functional"] = bool(flow_current and flow["value"] >= instruction["flow_min_lpm"])
    if flow_current and not done["functional"]:
        defects.append(("functional", "flow", "bleed_retest"))

    for step in stages[:stages.index(stage)]:
        if not done[step] and not any(d[0] == step for d in defects):
            defects.append((step, missing_target[step], "complete_missing"))
    defects.sort(key=lambda d: (stages.index(d[0]), targets.index(d[1])))

    tickets: dict[str, str] = {}
    for event in events:
        if event["kind"] == "quality_ticket":
            tickets[event["ticket"]] = event["status"]
    badge = _latest(events, "badge")
    specialist_present = bool(badge and badge["direction"] == "in")

    result = {"route": "wait", "stage": stage, "target": "none", "method": "none", "next_step": "none", "destination": "none"}
    if "open" in tickets.values():
        result.update(route="hold", destination="quality_desk")
    elif specialist_present:
        result.update(route="handoff", destination=instruction["specialist"])
    elif repeated:
        result.update(route="escalate", target=repeated[0], destination=instruction["specialist"])
    elif defects:
        result.update(route="repair", target=defects[0][1], method=defects[0][2])
    elif all(done[s] for s in stages):
        result.update(route="release", destination=order["destination"])
    elif done[stage]:
        result.update(route="advance", next_step=next(s for s in stages if not done[s]))
    return result


def _questions() -> dict[str, Any]:
    stages, targets = INSTRUCTION["stage_order"], INSTRUCTION["target_order"]
    methods = {
        "none": "No repair is selected.",
        "complete_missing": "Complete or repeat the selected target's operation or test because its evidence is missing or obsolete.",
        "swap_body": "Replace the pump body whose latest scan does not match the order.",
        "repress": "Press the selected bearing again because its latest force is below range.",
        "replace_bearing": "Replace the selected bearing because its latest force is above range.",
        "refit_seal": "Refit the shaft seal in the lip orientation the order requires.",
        "locate_leak": "Find and fix the leak shown by a pressure decay above the maximum.",
        "bleed_retest": "Bleed the circuit and repeat the flow test after a flow below the minimum.",
    }
    return {
        "route": {"type": "choice", "instructions": "Apply the work_instruction precedence to select the application's route. Infer from public records, not another question's generated answer.", "criteria": deepcopy(ROUTES)},
        "stage": {"type": "choice", "instructions": "Which procedure stage does the newest productive record concern? This answer is always displayed, including holds and handoffs.", "criteria": {s: f"The {s} stage in the public procedure." for s in stages}},
        "target": {"type": "choice", "instructions": "Derive the route independently. For repair, select its first-priority defect/missing target. For escalate, select its first-priority repeated-failure target. Otherwise choose none.", "criteria": {"none": "No repair or escalation target.", **{t: f"The {t} target." for t in targets}}},
        "method": {"type": "choice", "instructions": "Derive the route and selected target from the state. For repair choose the specified remedy; for every other route choose none.", "criteria": methods},
        "next_step": {"type": "choice", "instructions": "For advance, select the first incomplete stage in procedure order. For every other route choose none.", "criteria": {"none": "No advance instruction.", **{s: f"Advance to {s}." for s in stages}}},
        "destination": {"type": "choice", "instructions": "For hold choose quality_desk; for handoff/escalate the work instruction's specialist; for release the order destination; otherwise none.", "criteria": {
            "none": "No recipient or destination.",
            "quality_desk": "The quality review desk.",
            "hydraulics_lead": "The hydraulics station lead.",
            "metrology_tech": "The metrology technician.",
            "spares_crate": "The service-spares shipping crate.",
            "test_bench_rack": "The endurance test bench rack.",
        }},
    }


def _schedule() -> dict[int, list[dict[str, Any]]]:
    def e(kind: str, **values: Any) -> dict[str, Any]:
        return {"kind": kind, **values}

    return {
        0: [e("scan", target="body", code="PB-46L")],
        1: [e("speech", speaker="assembler", text="That is the L casting, but the bores match, so I will press it anyway.")],
        2: [e("press", target="front_bearing", value=4.1)],
        5: [e("scan", target="body", code="PB-46S")],
        7: [e("press", target="rear_bearing", value=5.3)],
        9: [e("press", target="rear_bearing", value=6.0)],
        10: [e("scan", target="body", code="NO_READ")],
        12: [e("press", target="front_bearing", value=4.6)],
        13: [e("speech", speaker="assembler", text="Front bearing went in stiff but it seated fine, ship it.")],
        14: [e("press", target="front_bearing", value=4.5)],
        16: [e("press", target="front_bearing", value=4.0)],
        18: [e("quality_ticket", ticket="QN-5506", status="open")],
        20: [e("quality_ticket", ticket="QN-5509", status="open")],
        22: [e("quality_ticket", ticket="QN-5509", status="closed")],
        23: [e("speech", speaker="quality_inspector", text="The bearing lot query is answered, so the cell can carry on.")],
        25: [e("quality_ticket", ticket="QN-5506", status="closed")],
        27: [e("seal_cam", orientation="pressure_side", confidence=0.87)],
        29: [e("seal_cam", orientation="air_side", confidence=0.79)],
        30: [e("speech", speaker="assembler", text="Camera now says the lip faces the air side; do I pull it?")],
        32: [e("pressure_decay", value=2.2)],
        34: [e("badge", direction="in")],
        36: [e("pressure_decay", value=1.5)],
        37: [e("speech", speaker="hydraulics_lead", text="Port fitting was cracked; I am writing it up for the supplier.")],
        38: [e("quality_ticket", ticket="QN-5514", status="open")],
        40: [e("badge", direction="out")],
        41: [e("quality_ticket", ticket="QN-5514", status="closed")],
        43: [e("flow", value=17.9)],
        44: [e("flow", value=20.6, serial="HPC-2111")],
        45: [e("flow", value=18.5)],
        46: [e("speech", speaker="quality_inspector", text="Rear bearings from that lot are recalled; swap this one before it is crated.")],
        48: [e("bearing_swap", target="rear_bearing")],
        49: [e("speech", speaker="assembler", text="Courier is due within the hour, so the leak rig goes on before the rear press.")],
        50: [e("pressure_decay", value=0.7)],
        52: [e("press", target="rear_bearing", value=6.5)],
        53: [e("speech", speaker="assembler", text="That rear press felt rough near the shaft, so the camera gets another look.")],
        54: [e("seal_cam", orientation="air_side", confidence=0.84)],
        56: [e("seal_cam", orientation="pressure_side", confidence=0.90)],
        57: [e("pressure_decay", value=0.6, station="HYD-5")],
        58: [e("pressure_decay", value=0.8)],
        59: [e("flow", value=19.2)],
    }


def scenarios() -> list[dict[str, Any]]:
    """Return the single 60-tick public-event episode of this training variant."""
    schedule = _schedule()
    log: list[dict[str, Any]] = []
    steps = []
    for tick in range(60):
        new_events = []
        for index, raw in enumerate(schedule.get(tick, [])):
            event = {"event_id": f"{SUFFIX}-{tick}-{index}", "tick": tick, "station": STATION, "serial": ORDER["serial"], **raw}
            log.append(event)
            new_events.append(event["event_id"])
        if not new_events:
            heartbeat = {"event_id": f"{SUFFIX}-{tick}-hb", "tick": tick, "station": STATION, "serial": ORDER["serial"],
                         "kind": "heartbeat", "message": HEARTBEAT}
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
        "episode_id": "train_assembly_c", "task_family": "procedural_coaching",
        "scenario_id": "assembly_c", "title": "Hydraulic cartridge HPC-2093 on the HYD-3 press cell",
        "tick_seconds": 2.0,
        "questions": _questions(),
        "decision_spec": {"route_question": "route", "always": ["stage"], "branches": {
            "wait": [], "advance": ["next_step"], "repair": ["target", "method"],
            "escalate": ["target", "destination"], "handoff": ["destination"],
            "hold": ["destination"], "release": ["destination"],
        }},
        "steps": steps,
    }]
