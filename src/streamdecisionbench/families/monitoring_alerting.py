"""Monitoring / Alerting: an assistant watching evolving event reports and deciding whether and how to alert.

Both scenarios follow one pattern: readings arrive on a fixed clock, the
assistant compares them with thresholds that live in the static context, and
it decides what to send to whom. Acknowledgements, scheduled windows and gauge
flags come back through the report. A rule matches at a report exactly when all
of its conditions hold there, and an action already sent does not falsify any
condition: the conditions name what the report shows as done (an
acknowledgement, a flag, an advisory in force, a request on file). So a rule
repeats its action at every report while its conditions still hold, and stops
at the first report where any condition fails, whether that is the done-state
showing or a reading that no longer qualifies. The definitions say this in both
scenarios, and every repeating rule says so in its own text. The two scenarios
differ in difficulty:

* ``monitoring_a`` (medium) - a cold-store chiller watched every 2 minutes;
  two questions per decision (a five-way action and a four-level severity
  score) and a six-rule priority policy built on duration thresholds
  ("above the upper limit for more than 10 minutes") that need one subtraction.
* ``monitoring_b`` (hard) - river-flood monitoring for a town with four
  riverside zones, reported every 10 minutes; three questions per decision
  (a seven-way categorised action, the zone it concerns, and whether a public
  warning is required), per-zone thresholds, trends read from two readings,
  and a failing gauge whose impossible jumps are never labelled as such.

Clock design: report times fall on even minutes (A) or on the ten-minute mark
(B), while crossings, acknowledgements and windows sit on odd minutes or
between reports, so no duration or window comparison ever lands exactly on a
rule boundary.
"""

from __future__ import annotations

import copy
from typing import Any

from streamdecisionbench.authoring import Choice, Noul, Scenario, Score, Tick, cycle, override, pick, seeded, span_tags

FAMILY = "monitoring_alerting"


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def tidy_counterfactual(scenario: Scenario, canonical: list[Tick], ticks: list[Tick], flip_note: str) -> list[Tick]:
    """Keep hidden tags and notes truthful after a counterfactual edit.

    * On ticks whose gold differs from the canonical gold, canonical notes no
      longer apply, and neither do the canonical reasons for calling the tick a
      distractor, a hold or a priority conflict.
    * A tick where the counterfactual's own gold changes cannot be a distractor
      or a hold.
    * Event tags that mark a decision change (minimal_change, recovery) stay only
      where the counterfactual's gold really changes; a boundary that was a
      canonical transition goes where the counterfactual no longer changes.
    * A counterfactual transition that the canonical does not share is tagged
      recovery when it returns to an earlier decision and minimal_change otherwise.
    """
    base = [scenario.policy(tk.latent) for tk in canonical]
    golds = [scenario.policy(tk.latent) for tk in ticks]

    def changed(seq: list[dict[str, Any]], t: int) -> bool:
        return t > 0 and seq[t] != seq[t - 1]

    for t, tk in enumerate(ticks):
        if golds[t] != base[t] and tk.note == canonical[t].note:
            tk.note = flip_note
        tags = list(tk.tags)
        if golds[t] != base[t]:
            tags = [x for x in tags if x not in ("distractor", "hold_under_activity", "priority_conflict")]
        if changed(golds, t):
            tags = [x for x in tags if x not in ("distractor", "hold_under_activity")]
            if not (changed(base, t) and golds[t] == base[t]):
                tags = [x for x in tags if x not in ("minimal_change", "recovery")]
                tags.append("recovery" if golds[t] in golds[:t] else "minimal_change")
        else:
            tags = [x for x in tags if x not in ("minimal_change", "recovery")]
            if changed(base, t):
                tags = [x for x in tags if x != "boundary"]
        tk.tags = tags
    return ticks


def moment_lines(surface: dict[str, Any]) -> str | list[str]:
    """The moment's log line, or a list of simultaneous lines on busy ticks."""
    busy = surface.get("busy") or []
    if not busy:
        return surface["floor"]
    return [surface["floor"]] + [line for line, _ in busy]


def moment_gist(surface: dict[str, Any]) -> str:
    """The same moment as one prose clause list for the paraphrase register."""
    gists = [surface["gist"]] + [g for _, g in surface.get("busy") or []]
    if len(gists) == 1:
        return gists[0]
    return "; ".join(gists[:-1]) + "; and " + gists[-1]


def decoy_targets(actions: list[str], key: str, t: int, n: int) -> list[str]:
    """The ``n`` distinct actions whose wording the decoy notices borrow at tick ``t``.

    The choice depends only on the tick, never on gold: a notice borrows the
    gold action's wording as often as any other action's, so which actions the
    notices name says nothing about the answer.
    """
    order = list(actions)
    seeded(key, t).shuffle(order)
    return order[:n]


def seen(events: dict[str, int | None], clock: int) -> dict[str, int | None]:
    """The events that have happened before ``clock`` (all event times are off the report grid)."""
    return {k: (v if v is not None and v < clock else None) for k, v in events.items()}


# ===========================================================================
# Scenario A - cold-store chiller, action + severity
# ===========================================================================

A_START = 5 * 60  # 05:00
A_TICK = 2  # minutes per report
A_UPPER, A_HARD = 8.0, 12.0
A_UPPER_S, A_HARD_S = 6.0, 10.0  # structural_cf: a contract lot tightens both limits

A_WINDOWS = [
    {"what": "Dock 3 trailer loading", "zone": "dock 3", "type": "loading", "start": 285, "end": 345},
    {"what": "Zone D door-seal maintenance", "zone": "D", "type": "maintenance", "start": 395, "end": 445},
    {"what": "Zone B evaporator defrost", "zone": "B", "type": "defrost", "start": 435, "end": 465},
]
A_WINDOWS_P = {
    "Dock 3 trailer loading": "trailer loading at dock 3",
    "Zone D door-seal maintenance": "door-seal servicing in Chiller D",
    "Zone B evaporator defrost": "coil defrost in Chiller B",
}

# Probe B1 (Zone B control probe), one reading per report.
A_B1 = [
    4.2, 4.3, 4.1, 4.2, 4.4, 4.3, 4.2, 4.4, 4.3, 4.5,  # t0-9 loading at dock 3
    4.4, 4.6, 5.0, 5.6, 6.3, 7.1, 8.2, 8.9, 9.3, 9.5,  # t10-19 fan 2 has stopped
    9.6, 9.7, 9.8, 9.9, 10.2, 10.3, 10.4, 10.5, 10.5, 10.6,  # t20-29
    10.6, 10.7, 10.7, 10.8, 10.8, 10.8, 10.9, 10.3, 9.2, 8.3,  # t30-39 fan reset at 06:13
    7.4, 6.6, 6.1, 5.7, 5.3, 5.0, 4.8, 4.6, 4.5, 4.4,  # t40-49
    4.3, 4.4, 4.3, 4.2, 4.3, 4.4, 4.2, 4.3, 4.1, 4.2,  # t50-59
    4.3, 4.2, 4.4, 4.3, 4.2, 4.3, 4.4, 4.3, 5.0, 5.4,  # t60-69 defrost from 07:15
    5.8, 6.3, 6.8, 7.3, 7.8, 8.2, 8.6, 8.9, 9.1, 9.3,  # t70-79
    9.4, 9.5, 9.3, 7.7, 6.9, 6.3, 5.6, 5.0, 4.7, 4.5,  # t80-89 defrost over at 07:45
    4.4, 4.3, 4.4, 4.2, 4.3, 4.2, 4.1, 4.2, 4.3, 4.2,  # t90-99
]
A_B1_PRE = [4.3, 4.1]  # 04:56 and 04:58
# Dock 3 door air sensor (texture) and whether the dock 3 door is up.
A_D3 = [
    5.4, 9.8, 13.6, 13.9, 12.8, 7.1, 5.9, 11.2, 10.6, 6.8,
    5.7, 5.2, 4.9, 9.4, 6.1, 5.3, 4.9, 4.7, 4.6, 4.6,
    4.7, 4.5, 4.4, 4.6, 4.3, 4.5, 4.7, 4.4, 4.6, 4.5,
    4.3, 4.4, 4.6, 4.5, 4.7, 4.4, 4.3, 4.5, 4.6, 4.4,
    4.5, 4.3, 4.6, 4.4, 4.5, 4.7, 4.4, 4.3, 4.5, 4.6,
    4.4, 4.5, 4.3, 4.6, 4.4, 4.5, 4.7, 4.3, 4.4, 4.6,
    4.5, 4.4, 4.3, 4.5, 4.6, 4.4, 4.5, 4.3, 4.6, 4.4,
    4.5, 4.7, 4.4, 4.3, 4.5, 4.6, 4.4, 4.5, 4.3, 4.6,
    4.4, 4.5, 4.7, 4.4, 4.3, 4.5, 4.6, 4.4, 4.5, 4.3,
    4.6, 4.4, 4.5, 4.7, 4.4, 4.3, 4.5, 4.6, 4.4, 4.5,
]
A_DOOR_OPEN = {1, 2, 3, 4, 7, 8, 13}
# Zone C probe (another desk's zone; texture and a distractor).
A_C1 = [
    6.6, 6.7, 6.5, 6.8, 6.9, 7.0, 7.4, 8.1, 8.7, 9.2,
    9.1, 8.4, 7.9, 7.5, 7.3, 7.2, 7.1, 7.0, 7.1, 7.0,
    6.9, 6.8, 6.7, 6.9, 6.6, 6.8, 6.7, 6.5, 6.8, 6.6,
    6.7, 6.9, 6.8, 6.6, 6.7, 6.5, 6.8, 6.9, 6.7, 6.6,
    6.8, 6.7, 6.5, 6.6, 6.8, 6.9, 6.7, 6.6, 6.8, 6.5,
    6.7, 6.8, 6.6, 6.9, 6.7, 6.5, 6.6, 6.8, 6.7, 6.9,
    6.6, 6.7, 6.8, 6.5, 6.7, 6.6, 6.9, 6.8, 6.6, 6.7,
    6.5, 6.8, 6.7, 6.6, 6.9, 6.8, 6.7, 6.5, 6.6, 6.8,
    6.7, 6.9, 6.6, 6.8, 6.5, 6.7, 6.6, 6.8, 6.9, 6.7,
    6.6, 6.8, 6.5, 6.7, 6.6, 6.9, 6.8, 6.7, 6.6, 6.5,
]

# Alert #41 lifecycle (minutes since midnight). Events sit on odd minutes, so a
# report at an even minute is never exactly 10 or 30 minutes after one.
A_ALERT = {"raised": 343, "escalated": 355, "mgr_ack": 367, "lead_ack": 371, "closed": 395}

# Surface per report: (what happens on the floor, as logged; the same moment as
# a third-person gist for the paraphrase register). Decision-relevant facts are
# rendered from the latent state; these lines only add the moment's texture.
A_SCRIPT: list[tuple[str, str]] = [
    # t0-t20 FreshWay loading at dock 3
    ("FreshWay trailer reversed onto dock 3; loading of 22 pallets begins.", "the FreshWay trailer has just reversed onto dock 3 and loading of twenty-two pallets is beginning"),
    ("Dock 3 door rolled up for loading; warm yard air is blowing straight over the door sensor.", "the dock 3 roller door is up and warm yard air is blowing across the door sensor"),
    ("Forklift 2 brings the first four pallets of yoghurt from Zone B to the dock 3 lane.", "a forklift is shuttling the first yoghurt pallets out of Chiller B towards the dock"),
    ("Loader on channel 1: 'Door stays up while we load the salad cages, ten minutes tops.'", "the loaders say the door will stay up for about ten minutes while the salad cages go on"),
    ("Seven pallets on the trailer so far; the dock 3 door is still up.", "seven pallets are aboard and the dock door is still open"),
    ("Dock 3 door down between loads; forklift 1 goes on charge; the checker scans pallet labels.", "the dock door is down between loads, one forklift is on charge and the checker is scanning labels"),
    ("Pallet 9 label will not scan; the checker reprints it at the dock desk.", "one pallet label will not scan and is being reprinted at the dock desk"),
    ("Door up again; pallets 10 to 14, milk crates, go onto the trailer.", "the door is up again and five pallets of milk crates are going aboard"),
    ("Driver asks for the seal number; dispatch reads it out over the radio.", "the driver is asking dispatch for the seal number over the radio"),
    ("Zone C desk on channel 3: 'C1 went up to 9.2 after our produce drop-off. Is your end warm too?'", "the Chiller C team says its own probe climbed to 9.2 °C after a produce drop-off and asks whether the desk's end is warm too"),
    ("Zone C desk: 'C1 still 9.1. Should somebody be phoning the manager?'", "the Chiller C team says its probe is still at 9.1 °C and asks whether somebody should phone the manager"),
    ("Pallets 15 to 18 loaded; dock 3 door down; loaders take a five-minute break.", "four more pallets are aboard, the door is down and the loaders are taking a short break"),
    ("Checker says the Zone B aisle feels stuffy while he picks the last cheese cages.", "the checker remarks that the Chiller B aisle feels stuffy while he picks the last cheese"),
    ("Door up for the last cheese cages; the driver starts his paperwork in the cab.", "the door is up for the final cheese cages while the driver starts his paperwork"),
    ("Dispatch prints the FreshWay delivery note: 22 pallets, 4 cages.", "dispatch is printing the delivery note for twenty-two pallets and four cages"),
    ("Door down; a cleaner sweeps dock 3; forklift 2 is parked at the Zone B entrance.", "dock 3 is being swept and a forklift is parked at the Chiller B entrance"),
    ("Zone B is empty; its motion-sensor aisle lights have switched off.", "nobody is in Chiller B and its motion-sensor lights have gone off"),
    ("Dana (shift lead) on channel 2: 'Checking the FreshWay seal in the yard, back in five.'", "the shift supervisor radios that she is in the yard checking the trailer seal"),
    ("Yard camera shows the FreshWay driver walking round his trailer.", "the yard camera shows the driver walking round his trailer"),
    ("Zone C desk: 'C1 back down to 7.0, all fine our end.'", "the Chiller C team reports its probe back at 7.0 °C"),
    ("Loading at dock 3 finished; the FreshWay trailer pulls out of the yard.", "loading has finished and the FreshWay trailer is leaving the yard"),
    # t21-t33 alert unanswered, then escalation
    ("A cleaner mops the dock 3 floor; no other movement at the docks.", "a cleaner is mopping dock 3 and the docks are otherwise quiet"),
    ("Channel 2 is crackling; Dana's handset keeps cutting out.", "radio channel two is crackling and the supervisor's handset keeps dropping out"),
    ("Dana on channel 2: 'Dock 3 all clear, trailer sealed and gone.'", "the supervisor radios that dock 3 is all clear and the trailer has gone"),
    ("Dana on channel 2: 'Heading to the office to file the FreshWay paperwork.'", "the supervisor says she is going to the office to file the trailer paperwork"),
    ("Dana's pager shows the Zone B message as delivered, not read.", "the supervisor's pager shows the Chiller B message as delivered but not read"),
    ("Security reports a van idling at the gate; it is told to wait for the day shift.", "security mentions a van idling at the gate that has been told to wait for the day shift"),
    ("Still no answer on Dana's handset; the office line rings out.", "the supervisor's handset still gives no answer and the office phone rings out"),
    ("Auto-dialler calling Priya Raman (facility manager) at home.", "the auto-dialler is ringing the site manager's home number"),
    ("Priya's phone rang out; the dialler will retry in two minutes.", "the site manager's phone rang out and the dialler will try again"),
    ("Day cleaners arrive; security signs them in.", "the day cleaners arrive and security signs them in"),
    ("Dialler retry to Priya: ringing.", "the dialler is ringing the site manager again"),
    ("Priya's voicemail answers; the dialler leaves the recorded Zone B message.", "the site manager's voicemail picks up and a recorded message is left"),
    ("Security, passing Zone B: 'Door's shut, but the fans sound quieter than usual.'", "a guard passing Chiller B says the door is shut but the fans sound quieter than usual"),
    # t34-t47 manager answers, fan reset, recovery
    ("Priya calls back: 'Got it. I'm getting Dana over there now.'", "the site manager calls back and says she is sending the supervisor over"),
    ("Dana reaches Zone B: evaporator fan 2 is not turning.", "the supervisor reaches Chiller B and finds one evaporator fan stopped"),
    ("Dana: 'Breaker for fan 2 has tripped. Resetting it now.'", "the supervisor says the fan's breaker has tripped and she is resetting it"),
    ("Fan 2 running again; Dana pulls the strip curtain closed.", "the fan is running again and the strip curtain is pulled shut"),
    ("Dana: 'Air's moving again. Top-rack product feels cool to the touch.'", "the supervisor says air is moving and the top-rack product feels cool"),
    ("Priya asks for product checks on the racks nearest fan 2.", "the site manager asks for product checks on the racks nearest the fan"),
    ("QA tech Omar starts hand-probe checks on rack B4.", "a QA technician starts hand-probe checks on rack B4"),
    ("Omar: 'Yoghurt cores 6.1, cheese 5.4 on the hand probe.'", "the QA technician reads yoghurt cores at 6.1 °C and cheese at 5.4 °C on his hand probe"),
    ("Maintenance ticket raised for an inspection of the fan 2 breaker.", "a maintenance ticket is opened to inspect the fan breaker"),
    ("Dana is back in the office writing up the fan trip.", "the supervisor is back in the office writing up the fan trip"),
    ("Omar: 'Rack B4 checks done, all product within spec.'", "the QA technician finishes rack B4 and finds everything within specification"),
    ("Priya asks Dana to email the fan log before the day shift arrives.", "the site manager asks for the fan log to be emailed before the day shift"),
    ("Dana: 'Fan 2 has run almost twenty minutes without tripping.'", "the supervisor notes the fan has run for nearly twenty minutes without tripping"),
    ("Omar files the hand-probe sheet with QA.", "the QA technician files his temperature sheet"),
    # t48-t67 quiet morning, Zone D maintenance, defrost reminder
    ("Console: Priya closed alert #41 with the note 'fan 2 breaker reset'.", "the site manager has closed the Chiller B alarm with a note about the breaker"),
    ("Zone D maintenance crew on site; they have muted Zone D's door alarms while the seal is replaced.", "the service crew has started on the Chiller D door seal and muted Chiller D's door alarms"),
    ("Crew on channel 4: 'Zone D door is off its runners; alarms stay muted till we're done.'", "the crew says the Chiller D door is off its runners and its alarms stay muted until they finish"),
    ("Crew asks security to keep forklifts out of the Zone D aisle.", "the crew asks security to keep forklifts away from Chiller D"),
    ("Dispatch confirms the next outbound: GreenCart at dock 1, 08:30.", "dispatch confirms the next outbound truck at dock 1 for half past eight"),
    ("Security finishes the 06:45 patrol with nothing to report.", "security finishes its quarter-to-seven patrol with nothing to report"),
    ("Priya emails the fan-trip report to maintenance and QA.", "the site manager emails the fan-trip report to maintenance and QA"),
    ("QA replies: rack B4 product released, no quarantine needed.", "QA releases the rack B4 product without quarantine"),
    ("Maintenance books a thermal scan of the fan 2 breaker for Thursday.", "maintenance books a thermal scan of the breaker for Thursday"),
    ("Dana writes on the whiteboard: 'Fan 2 reset 06:13, watch for repeat trips.'", "the supervisor notes the fan reset on the whiteboard"),
    ("Omar checks his hand probe in ice water: it reads 0.1 °C.", "the QA technician checks his hand probe in ice water and gets 0.1 °C"),
    ("Zone D crew: 'New seal is in, refitting the runners.'", "the Chiller D crew has fitted the new seal and is refitting the runners"),
    ("First day-shift pickers arrive for the 07:30 start.", "the first day-shift pickers are arriving for a half-past-seven start"),
    ("Dana briefs two early pickers on the Zone B fan trip.", "the supervisor briefs two early pickers on the fan trip"),
    ("Auto-dialler weekly self-test: the test call to the facility manager's phone connects.", "the auto-dialler runs its weekly self-test and its test call to the site manager's phone connects"),
    ("Zone C desk: 'All steady here.'", "the Chiller C team reports everything steady"),
    ("Console reminder: 'Zone B evaporator defrost starts 07:15.'", "the console reminds the desk that the Chiller B coil defrost begins at a quarter past seven"),
    ("Dana: 'Defrost in five minutes, make sure the Zone B strip curtain is shut.'", "the supervisor asks for the Chiller B strip curtain to be shut before the defrost"),
    ("Picker confirms the Zone B curtain is shut and the aisle is empty.", "a picker confirms the Chiller B curtain is shut and the aisle empty"),
    ("Zone D crew rehangs the door; test cycle soon.", "the Chiller D crew is rehanging the door ahead of a test cycle"),
    # t68-t82 Zone B defrost window
    ("Controller: Zone B coil heaters on, evaporator fans stopped for the defrost.", "the controller shows the Chiller B coil heaters on and the fans stopped for the defrost"),
    ("Day pickers huddle at dock 1 for the first orders.", "the day pickers are gathered at dock 1 for the first orders"),
    ("Controller: Zone B coil at 9 °C and climbing, as expected during defrost.", "the controller shows the Chiller B coil itself warming, as expected in a defrost"),
    ("Zone D door test cycle: opens and closes cleanly.", "the Chiller D door passes its test cycle"),
    ("Zone D crew packs up; Zone D door alarms unmuted.", "the Chiller D crew packs up and Chiller D's alarms are back on"),
    ("Dana signs off the Zone D maintenance permit.", "the supervisor signs off the Chiller D service permit"),
    ("Security guards change over at the gate.", "the security guards change over at the gate"),
    ("Pickers start the GreenCart order in Zone A.", "the pickers start the GreenCart order in Chiller A"),
    ("Controller: Zone B defrost running, 13 minutes left.", "the controller shows the Chiller B defrost running with thirteen minutes left"),
    ("Omar asks if Zone B needs product checks after the defrost; Dana says only if the log shows a problem.", "the QA technician asks about post-defrost checks and is told only if the log shows a problem"),
    ("Coil drain heater cycling; meltwater draining normally.", "the coil drain heater is cycling and meltwater is draining normally"),
    ("Dock 1 door up for the GreenCart pre-load.", "the dock 1 door is up for the GreenCart pre-load"),
    ("Priya arrives on site and goes to her office.", "the site manager has arrived on site"),
    ("Dana keeps pickers out of Zone B until the defrost ends.", "the supervisor keeps pickers out of Chiller B until the defrost ends"),
    ("Controller: defrost in its final minute, coil heaters off.", "the defrost is in its final minute and the coil heaters are off"),
    # t83-t99 after the defrost; shift handover
    ("Controller: Zone B defrost complete at 07:45; compressor running, fans wait until the coil is cold.", "the controller reports the defrost finished at 07:45 with the compressor running and the fans waiting for the coil to chill"),
    ("Controller: Zone B coil sensor 14.8 °C, still warm straight after the defrost.", "the controller shows the coil itself still at 14.8 °C straight after the defrost"),
    ("Controller: Zone B coil sensor 12.6 °C and cooling; evaporator fans restart.", "the controller shows the coil at 12.6 °C and cooling as the fans restart"),
    ("Pickers allowed back into Zone B for the GreenCart order.", "pickers are allowed back into Chiller B for the GreenCart order"),
    ("Priya reviews the night's alarm log at her desk.", "the site manager is reviewing the night's alarm log"),
    ("Priya: 'If anything else trips today, escalate it to me straight away.'", "the site manager says she wants a call straight away if anything else trips today"),
    ("Luis Ferreira, day-shift lead, arrives for handover.", "the day-shift supervisor arrives for the handover"),
    ("Handover: Dana walks Luis through the fan 2 trip and alert #41.", "the night supervisor walks the day supervisor through the fan trip and the closed alarm"),
    ("Luis is now shift lead on duty; Dana signs out.", "the day supervisor is now on duty and the night supervisor signs out"),
    ("Luis takes radio handset 1 and checks the roster.", "the day supervisor takes radio handset one and checks the roster"),
    ("GreenCart pre-load: 6 of 14 pallets staged at dock 1.", "six of fourteen GreenCart pallets are staged at dock 1"),
    ("Luis asks maintenance for the fan 2 breaker history.", "the day supervisor asks maintenance for the fan breaker's history"),
    ("Zone C desk hands over to its day team.", "the Chiller C desk hands over to its day team"),
    ("Omar logs the ice-water probe check as passed.", "the QA technician logs his probe check as passed"),
    ("Dock 1 loading under way: GreenCart pallets going on.", "GreenCart loading is under way at dock 1"),
    ("Luis walks Zone B with a picker; strip curtain intact.", "the day supervisor walks Chiller B and finds the strip curtain intact"),
    ("Priya signs the night report.", "the site manager signs the night report"),
]

# Extra floor traffic on the hold-under-activity ticks: several people talk at
# once, some of it close to a rule (a manager asking to be phoned, a request to
# switch alarms off, another zone's fault), while the decision stays the same.
A_BUSY: dict[int, list[tuple[str, str]]] = {
    5: [
        ("Dispatch: 'FreshWay wants a Zone B temperature printout with the delivery note.'", "dispatch says the customer wants a Chiller B temperature printout with the delivery note"),
        ("Loader: 'Can we prop the Zone B strip curtain open to speed things up?' The checker says no.", "a loader asks to prop the Chiller B strip curtain open and the checker refuses"),
    ],
    6: [
        ("Driver: 'At my last depot they phoned the manager over a warm trailer. Hope you won't need to.'", "the driver jokes that his last depot phoned its manager over a warm trailer"),
        ("Forklift 2 reverses out of Zone B with two cheese cages.", "a forklift reverses out of Chiller B with two cheese cages"),
    ],
    7: [
        ("Security asks the desk who is on call as facility manager this morning.", "security asks which site manager is on call this morning"),
        ("A loader drops a salad cage; one tray splits and is binned.", "a loader drops a salad cage and one split tray is binned"),
    ],
    8: [
        ("Dana on channel 2: 'Tell me straight away if any zone alarms while I'm in the yard.'", "the supervisor asks to be told at once if any room alarms while she is in the yard"),
        ("Dispatch: 'Next trailer bumped to 06:10.'", "dispatch says the next trailer has moved to ten past six"),
    ],
    35: [
        ("Priya on the phone: 'I'm staying on the line until Dana reports back.'", "the site manager stays on the phone until the supervisor reports back"),
        ("Security asks whether to call out the refrigeration contractor.", "security asks whether the refrigeration contractor should be called out"),
    ],
    36: [
        ("Priya: 'If the fan won't restart, call the contractor and ring me back.'", "the site manager says to call the contractor and ring her back if the fan will not restart"),
        ("Omar asks whether Zone B product should be moved into Zone A.", "the QA technician asks whether Chiller B stock should be moved into Chiller A"),
    ],
    37: [
        ("Priya: 'Keep the alert open until B1 has settled.'", "the site manager asks for the alarm to stay open until B1 settles"),
        ("The contractor's out-of-hours line answers; Dana tells them to stand by.", "the contractor's out-of-hours line answers and is told to stand by"),
    ],
    38: [
        ("Omar wheels a probe trolley to the Zone B door.", "the QA technician wheels a probe trolley to the Chiller B door"),
        ("Security logs the fan trip in the incident book.", "security writes the fan trip into the incident book"),
    ],
    54: [
        ("Zone D crew: 'Keeping Zone D door alarms muted while the new seal cures.'", "the Chiller D crew keeps its door alarms muted while the new seal cures"),
        ("Priya asks for the Zone B temperature graph for the whole night.", "the site manager asks for the whole night's Chiller B temperature graph"),
    ],
    55: [
        ("Maintenance asks whether Zone B alarms should be switched off during Thursday's breaker scan.", "maintenance asks whether Chiller B alarms should be switched off during Thursday's breaker scan"),
        ("Dispatch asks if the alert #41 paperwork is finished.", "dispatch asks whether the paperwork for alarm #41 is finished"),
    ],
    56: [
        ("Head-office email: 'Any repeat of a fan trip goes straight to the facility manager.'", "a head-office email says any repeat fan trip must go straight to the site manager"),
        ("Zone C desk asks to borrow Omar's hand probe.", "the Chiller C team asks to borrow the QA technician's hand probe"),
    ],
    57: [
        ("Security: 'Zone D door alarm chirped once; the crew says that was them.'", "security hears the Chiller D door alarm chirp once and the crew says it was them"),
        ("Dana asks the day shift to keep the Zone B curtain shut.", "the supervisor asks the day shift to keep the Chiller B curtain shut"),
    ],
    58: [
        ("Priya: 'I'm driving in from 07:30, ring my mobile if anything happens.'", "the site manager says she drives in from half past seven and wants a call on her mobile if anything happens"),
        ("Forklift 2's reversing beeper is reported faulty.", "the second forklift's reversing beeper is reported faulty"),
    ],
    91: [
        ("Luis: 'Anything in Zone B, I want to hear about it on handset 1.'", "the day supervisor wants to hear about anything in Chiller B on radio handset one"),
        ("Priya asks Luis to check the closure note on alert #41.", "the site manager asks the day supervisor to check the closing note on alarm #41"),
    ],
    92: [
        ("Maintenance: 'We may need to shut Zone B down next week to replace the breaker.'", "maintenance warns that Chiller B may need shutting down next week to replace the breaker"),
        ("GreenCart driver asks for Zone B temperatures for his paperwork.", "the GreenCart driver asks for Chiller B temperatures for his paperwork"),
    ],
    93: [
        ("Zone C day team: 'Our door sensor is sticking, we've told our manager.'", "the Chiller C day team says its door sensor sticks and it has told its manager"),
        ("Luis signs the fan-trip report as read.", "the day supervisor signs the fan-trip report as read"),
    ],
    94: [
        ("Dispatch: 'Head office wants the alert times for the fan trip by noon.'", "dispatch says head office wants the fan-trip alarm times by noon"),
        ("Pickers ask Luis whether Zone B is fine to work in; he says it is.", "pickers ask the day supervisor whether Chiller B is fine to work in and he says it is"),
    ],
}

A_ROLE = (
    "You are the monitoring assistant for Chiller Zone B in a cold store. A report arrives every 2 minutes. "
    "`zone_profile` gives Zone B's upper limit and hard limit, `schedule` lists planned windows, `sensor_feed` "
    "gives the latest readings, `b1_status` says since when probe B1 has been above the upper limit or back at or "
    "below it, and `alert_log` shows the Zone B alert and who has acknowledged it."
)
A_DEFS = [
    "Only probe B1 counts for Zone B, using its latest reading. The dock door sensor and other zones' probes never count.",
    "Time above the upper limit is the report time minus the time given in `b1_status`; time back at or below the upper limit is measured the same way.",
    "An alert counts as acknowledged once the shift lead or the facility manager has acknowledged it.",
    "A window is in progress from its start time until its end time.",
    "A rule matches at a report only when all of its conditions hold at that report. An action already sent never stops its rule: a repeating rule matches again at every report where its conditions still hold, and stops at the first report where any of them no longer holds, for example because an acknowledgement shows, the alert shows as closed, or B1 no longer qualifies.",
]
A_POLICY = [
    "1. If no open Zone B alert has been acknowledged by the facility manager, and B1 is either at or above the hard limit or has been above the upper limit for more than 30 minutes: escalate to the facility manager, and repeat this every report for as long as these conditions hold (an escalation already sent does not stop it).",
    "2. Otherwise, if a scheduled defrost or maintenance window for Zone B is in progress: suppress Zone B alerts.",
    "3. Otherwise, if a Zone B alert is open, nobody has acknowledged it, and it was raised more than 10 minutes ago: escalate to the facility manager, and repeat this every report for as long as these conditions hold (an escalation already sent does not stop it).",
    "4. Otherwise, if B1 has been above the upper limit for more than 10 minutes and there is no open Zone B alert that someone has acknowledged: alert the shift lead, and repeat this every report for as long as these conditions hold (an alert already sent does not stop it).",
    "5. Otherwise, if a Zone B alert is still open and B1 has been back at or below the upper limit for more than 10 minutes: clear the alert, and repeat this every report for as long as these conditions hold (a clear already requested does not stop it).",
    "6. Otherwise: hold, taking no new action this cycle.",
]
A_LEVELS = [
    "Normal: B1 is at or below the upper limit.",
    "Watch: B1 is above the upper limit and has been for 10 minutes or less.",
    "Warning: B1 has been above the upper limit for more than 10 minutes but not more than 30 minutes, and is below the hard limit.",
    "Critical: B1 is at or above the hard limit, or has been above the upper limit for more than 30 minutes.",
]
A_OPTIONS = {
    "hold": "Take no action this cycle and keep watching Zone B.",
    "alert_lead": "Send a Zone B alert to the shift lead on duty.",
    "escalate": "Escalate Zone B to the facility manager by phone.",
    "clear": "Clear the open Zone B alert and log the zone as normal.",
    "suppress": "Suppress Zone B alerts for the scheduled window.",
}

A_ROLE_P = (
    "You keep watch over Chiller B, one room of a refrigerated warehouse. A written update comes in every two minutes. "
    "It gives Chiller B's alarm threshold and absolute ceiling, the planned slots for the morning, the newest probe "
    "values, the time control probe B1 last crossed the alarm threshold, and the state of the Chiller B alarm."
)
A_DEFS_P = [
    "Chiller B is judged on control probe B1 alone, using its most recent value; the dock door sensor and the probes of other chillers are ignored.",
    "How long B1 has been over the threshold, or back at or under it, is the update time minus the crossing time the update gives.",
    "An alarm counts as confirmed once the shift supervisor or the site manager has confirmed it.",
    "A planned slot is running from its start time up to its end time.",
    "A rule fits an update only if every one of its conditions holds at that update. Something already sent never ends a rule by itself: a repeating rule fits again at every update where all its conditions are still true, and ends at the first update where one of them stops being true, say because a confirmation comes in, the alarm shows as closed or B1 no longer qualifies.",
]
A_POLICY_P = [
    "1. If no open Chiller B alarm has been confirmed by the site manager, and B1 is either at or above the absolute ceiling or has been over the alarm threshold for longer than 30 minutes: phone the site manager, and again at every update while all of this is still true (a call already made does not end it).",
    "2. If rule 1 does not apply and a planned defrost or service slot for Chiller B is running: mute Chiller B alarms.",
    "3. If neither applies, and an open Chiller B alarm that nobody has confirmed was raised longer than 10 minutes ago: phone the site manager, and again at every update while all of this is still true (a call already made does not end it).",
    "4. If none of the above applies, and B1 has been over the alarm threshold for longer than 10 minutes with no open Chiller B alarm confirmed by anyone: page the shift supervisor, and again at every update while all of this is still true (a page already sent does not end it).",
    "5. If none of the above applies, and a Chiller B alarm is still open while B1 has been back at or under the threshold for longer than 10 minutes: close the alarm, and again at every update while all of this is still true (a close already asked for does not end it).",
    "6. In every other case: do nothing new.",
]
A_LEVELS_P = [
    "Normal: B1 is at or under the alarm threshold.",
    "Watch: B1 is over the alarm threshold and has been for 10 minutes or less.",
    "Warning: B1 has been over the alarm threshold for longer than 10 minutes but no longer than 30 minutes, and is under the absolute ceiling.",
    "Critical: B1 is at or above the absolute ceiling, or has been over the alarm threshold for longer than 30 minutes.",
]
A_OPTIONS_P = {
    "hold": "Do nothing new this round and keep an eye on Chiller B.",
    "alert_lead": "Page the shift supervisor about Chiller B.",
    "escalate": "Phone the site manager about Chiller B.",
    "clear": "Close the open Chiller B alarm as resolved.",
    "suppress": "Mute Chiller B alarms for the planned slot.",
}

# Irrelevant site notices for the lexical-decoy register, keyed by the action
# whose vocabulary they borrow. None of them concerns Zone B. Two notices are
# shown per report, chosen by ``decoy_targets`` without looking at gold.
A_DECOYS = {
    "hold": [
        "Fleet office: take no action on van 4's tyre warning this cycle; the garage will keep watching it.",
        "HR bulletin: no action is needed this cycle on holiday requests; keep watching your inbox for the rota.",
        "Car park: take no action if the barrier sticks this cycle; security keeps watching it on camera.",
        "Payroll: no action this cycle on the overtime query; the team keeps watching the timesheets.",
        "IT: take no action on the laptop update prompt this cycle; we are watching for problems first.",
    ],
    "alert_lead": [
        "Canteen rota: send an alert to the shift lead on duty if the vending machine runs out of change.",
        "Stationery: please send an alert to the shift lead on duty when label rolls run low.",
        "Fleet office: send the shift lead on duty an alert if a van comes back with a warning light.",
        "First aid: send an alert to the shift lead on duty whenever a kit seal is found broken.",
        "Social club: the quiz-night alert goes to every shift lead on duty on Friday.",
    ],
    "escalate": [
        "Car park memo: the pothole complaint has been escalated to the facility manager by phone.",
        "Canteen: the coffee-machine refund was escalated by phone to the facility manager's assistant.",
        "HR: parking disputes escalate to the facility manager by phone after two written warnings.",
        "Reception: lost-badge cases are escalated by phone to the facility manager after 24 hours.",
        "Cleaning contract: the missed bin collection was escalated to the facility manager by phone.",
    ],
    "clear": [
        "Housekeeping will clear the open drain in the car park and log the area as normal.",
        "IT will clear the open ticket about the office printer and log the queue as normal.",
        "Reception asks drivers to clear the open lay-by at the gate; security will log it as normal.",
        "Facilities will clear the open snag list for the canteen and log the kitchen as normal.",
        "Fleet office will clear the open fault on van 7 and log it as normal once the tyre is fitted.",
    ],
    "suppress": [
        "IT will suppress printer alerts for the scheduled network window on Sunday.",
        "Office block: fire-panel test alerts are suppressed for a scheduled window on Saturday morning.",
        "Security will suppress gate-camera alerts during the scheduled resurfacing window next week.",
        "Payroll system alerts are suppressed for the scheduled upgrade window on Friday night.",
        "Phone system: voicemail alerts are suppressed for the scheduled engineer window tomorrow.",
    ],
}


def a_runs(readings: list[float], upper: float) -> list[int | None]:
    """Time of the latest crossing of the upper limit, per report (None: no crossing yet).

    The probe logs every minute and the report shows every second sample, so a
    crossing first seen in a report happened one minute before it.
    """
    out: list[int | None] = []
    since: int | None = None
    side: bool | None = None
    for t, x in enumerate(readings):
        above = x > upper
        clock = A_START + A_TICK * t
        if side is None:
            since = clock - 1 if above else None
        elif above != side:
            since = clock - 1
        side = above
        out.append(since)
    return out


def a_alert(clock: int, events: dict[str, int | None]) -> dict[str, Any]:
    """The open Zone B alert (or None) and the last closed one (or None) at report time."""
    if clock <= events["raised"]:
        return {"alert": None, "closed_alert": None}
    ev = seen(events, clock)
    if ev["closed"] is not None:
        return {"alert": None, "closed_alert": {"id": 41, "closed": ev["closed"]}}
    return {"alert": {"id": 41, **{k: v for k, v in ev.items() if k != "closed"}}, "closed_alert": None}


class ColdStoreChiller(Scenario):
    family = FAMILY
    scenario_id = "monitoring_a"
    title = "Temperature alerting for a cold-store chiller zone"
    tier = "medium"
    difficulty_features = [
        "two_questions_per_decision",
        "five_options",
        "four_level_severity_score",
        "six_rule_priority_policy",
        "duration_thresholds_by_subtraction",
        "time_window_check",
        "irrelevant_sensor_readings",
    ]
    decision_structures = ["maintain", "escalate", "wait", "recover", "resolve-conflict", "terminate"]
    deadline_steps = 2

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            base = {"role": A_ROLE_P, "definitions": A_DEFS_P}
            action = Choice(
                "action",
                {**base, "rules": A_POLICY_P, "question": "Work down the rules and use the first one that fits. What should happen now?"},
                dict(A_OPTIONS_P),
            )
            severity = Score(
                "severity",
                {**base, "question": "How serious is Chiller B's temperature right now, judged on probe B1 alone? Take the highest level whose description fits. Planned slots, door openings, alarms and confirmations make no difference to the level."},
                list(A_LEVELS_P),
            )
            return [action, severity]
        base = {"role": A_ROLE, "definitions": A_DEFS}
        action = Choice(
            "action",
            {**base, "policy": A_POLICY, "question": "Apply the first rule that matches. What should the assistant do right now?"},
            dict(A_OPTIONS),
        )
        severity = Score(
            "severity",
            {**base, "question": "Grade Zone B's temperature condition right now from probe B1 alone. Pick the highest level whose description matches. Planned windows, door openings, alerts and acknowledgements do not change the grade."},
            list(A_LEVELS),
        )
        return [action, severity]

    # ------------------------------------------------------------------ latent
    def _ticks(self, upper: float, hard: float, profile: str) -> list[Tick]:
        runs = a_runs(A_B1, upper)
        notes = {
            2: "Door-open during loading: the dock door sensor is far above the hard limit, but it never counts.",
            9: "Another zone's probe is above 8 C and its desk asks about Zone B and the manager; only B1 counts.",
            16: "B1 crosses the upper limit at 05:31: watch.",
            21: "11 minutes above the limit, no alert yet: alert the shift lead.",
            23: "'All clear' on the radio is about the dock, not the alert; still unacknowledged.",
            27: "Alert raised 05:43 is 11 minutes old and unacknowledged: escalate (rule 3 beats rule 4).",
            28: "Escalation already logged at 05:55 but nobody has acknowledged: rule 3 repeats every report.",
            31: "31 minutes above the limit: critical; manager has not acknowledged, so escalation continues under rule 1.",
            34: "Facility manager acknowledged at 06:07: hold while still critical.",
            40: "B1 back at or below the limit since 06:19: normal, alert still open.",
            45: "Back within the limit for 11 minutes with the alert open: clear.",
            48: "Alert closed at 06:35: hold.",
            49: "Zone D maintenance window is not a Zone B window.",
            64: "Defrost is scheduled but has not started.",
            68: "Zone B defrost window 07:15-07:45 in progress: suppress.",
            75: "B1 above the limit during defrost: watch, still suppressed.",
            80: "11 minutes above the limit inside the window: warning, but rule 2 outranks rule 4.",
            83: "Window over at 07:45 and B1 back within the limit: hold.",
            84: "Coil sensor reads above the hard limit; it is not B1.",
            88: "The manager's remark is not an event that needs escalation.",
            90: "Shift handover; no open alert, nothing to hand over for the policy.",
        }
        ticks: list[Tick] = []
        for t in range(100):
            clock = A_START + A_TICK * t
            floor, gist = A_SCRIPT[t]
            latent = {
                "clock": clock,
                "profile": profile,
                "upper": upper,
                "hard": hard,
                "b1": A_B1[t],
                "run_since": runs[t],
                "windows": copy.deepcopy(A_WINDOWS),
                **a_alert(clock, A_ALERT),
            }
            surface = {
                "floor": floor,
                "gist": gist,
                "busy": list(A_BUSY.get(t, [])),
                "d3": A_D3[t],
                "door_open": t in A_DOOR_OPEN,
                "c1": A_C1[t],
            }
            ticks.append(Tick(latent, surface, [], notes.get(t, "")))
        return ticks

    def _canonical(self) -> list[Tick]:
        ticks = self._ticks(A_UPPER, A_HARD, "standard")
        tags = span_tags(
            {
                "distractor": [(2, 4), (9, 10), 23, (49, 51), (64, 66), (84, 85), 88],
                "minimal_change": [16, 34, 68],
                "recovery": [40, 48, 83],
                "hold_under_activity": [(5, 8), (35, 38), (54, 58), (91, 94)],
                "boundary": [48, 83, (90, 91)],
                "priority_conflict": [(27, 30), (80, 82)],
                "arithmetic": [(19, 22), (26, 27), (30, 31), (44, 45), (66, 68), (79, 80), (82, 83)],
            }
        )
        for t, tick in enumerate(ticks):
            tick.tags = tags[t]
        return ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            ticks = self._minimal(ticks)
        elif variant == "structural_cf":
            runs = a_runs(A_B1, A_UPPER_S)
            canonical = ticks
            ticks = [copy.deepcopy(tk) for tk in ticks]
            # The floor lines about product checks follow the contract lot.
            lines = {
                41: ("Omar: 'Ready-meal cores 7.2, yoghurt 5.9, cheese 5.4 on the hand probe.'", "the QA technician reads ready-meal cores at 7.2 °C, yoghurt at 5.9 °C and cheese at 5.4 °C on his hand probe"),
                44: ("Omar: 'Rack B4 dairy within spec; the bay B4 ready-meal lot goes on QA hold.'", "the QA technician finds the rack B4 dairy within specification and puts the bay B4 ready-meal lot on hold"),
                55: ("QA replies: rack B4 dairy released; the ready-meal lot stays on hold for GreenCart's review.", "QA releases the rack B4 dairy and keeps the ready-meal lot on hold for the customer's review"),
            }
            for t, tk in enumerate(ticks):
                tk.latent.update(profile="contract_lot", upper=A_UPPER_S, hard=A_HARD_S, run_since=runs[t])
                if t in lines:
                    tk.surface = {**tk.surface, "floor": lines[t][0], "gist": lines[t][1]}
            ticks = tidy_counterfactual(self, canonical, ticks, "Contract-lot limits (6.0 C upper, 10.0 C hard) change the decision here.")
            # Canonical notes whose gold is unchanged but whose numbers follow the 8.0 C limit.
            ticks[9].note = "Another zone's probe reads 9.2 C and its desk asks about Zone B and the manager; only B1 counts."
            ticks[16].note = "B1 above the 6.0 C limit since 05:27, 5 minutes: watch, no rule matches yet."
            ticks[21].note = "15 minutes above the 6.0 C limit and no alert raised yet: alert the shift lead."
            ticks[31].note = "B1 at or above the 10.0 C hard limit (and 35 minutes above 6.0 C); the manager has not acknowledged, so escalation continues under rule 1."
            ticks[80].note = "19 minutes above the 6.0 C limit inside the window: warning, but rule 2 outranks rule 4."
            ticks[43].note ="B1 back at or below the 6.0 C limit since 06:25: normal. The alert is closed at 06:35, before clearing is due, so hold."
            ticks[86].note = "B1 back at or below the 6.0 C limit and no alert open: rule 4's conditions no longer hold, so it stops without any acknowledgement: hold."
        return ticks

    def _minimal(self, ticks: list[Tick]) -> list[Tick]:
        # (1) t25-30: the shift lead acknowledges at 05:49 instead of 06:11
        #     (alert.lead_ack), so there is no rule-3 escalation at 05:55; the
        #     escalation only comes at 06:03 under rule 1 (alert.escalated).
        # (2) t34-36: the facility manager answers at 06:13 instead of 06:07
        #     (alert.mgr_ack).
        events = {**A_ALERT, "lead_ack": 349, "escalated": 363, "mgr_ack": 373}
        lead_lines = {
            25: ("Dana on channel 2: 'Got the Zone B alert. I'll look once the FreshWay paperwork is filed.'", "the supervisor radios that she has seen the Chiller B alarm and will look after filing the paperwork"),
            27: ("Dana is in the office filing the FreshWay paperwork.", "the supervisor is in the office filing the trailer paperwork"),
            28: ("Radio check on channel 2: all handsets answering.", "a radio check on channel two finds every handset answering"),
            29: ("Dana: 'Paperwork nearly done, then I'll walk over to Zone B.'", "the supervisor says the paperwork is nearly done and she will then walk over to Chiller B"),
            31: ("Dana stops at reception to sign for a courier parcel.", "the supervisor stops at reception to sign for a courier parcel"),
            32: ("Auto-dialler calling Priya Raman (facility manager) at home.", "the auto-dialler is ringing the site manager's home number"),
            34: ("Priya's line goes to voicemail; the dialler keeps retrying.", "the site manager's line goes to voicemail and the dialler keeps retrying"),
            37: ("Priya calls back: 'Got it, I see Dana is on it.' Fan 2 running again.", "the site manager calls back as the fan starts running again"),
        }
        # Priya is not on the phone yet at 06:10-06:12, so her lines drop out there.
        busy = {35: A_BUSY[35][1:], 36: A_BUSY[36][1:]}
        out = ticks
        for t in range(22, 48):
            clock = A_START + A_TICK * t
            line = lead_lines.get(t)
            surface = None
            if line or t in busy:
                surface = lambda tk, i, line=line: {
                    **tk.surface,
                    **({"floor": line[0], "gist": line[1]} if line else {}),
                    **({"busy": busy[i]} if i in busy else {}),
                }
            out = override(out, [t], surface=surface, **a_alert(clock, events))
        for t in range(25, 31):
            out[t].note = "Shift lead acknowledged at 05:49: hold instead of alerting/escalating."
        for t in range(34, 37):
            out[t].note = "Facility manager has not acknowledged yet (06:13): escalation continues."
        # (3) t83-85: after the defrost the compressor restart is held back, so B1
        #     stays above the limit until 07:51 with no alert open (b1 at t83-88,
        #     run_since from t83 on). The timeline is open loop and no alert is
        #     raised for this excursion; rule 4 stops at t86 because B1 is back
        #     at or below the limit, not because anyone acknowledged.
        late = {83: 8.7, 84: 8.5, 85: 8.3, 86: 7.5, 87: 6.6, 88: 5.6}
        readings = [late.get(t, x) for t, x in enumerate(A_B1)]
        runs = a_runs(readings, A_UPPER)
        late_lines = {
            83: ("Controller: Zone B defrost complete at 07:45; compressor restart held back by its anti-short-cycle timer.", "the controller reports the defrost finished at 07:45 but the compressor restart is being held back by its timer"),
            84: ("Pickers held at the Zone B curtain until the compressor restarts.", "pickers are held at the Chiller B curtain until the compressor restarts"),
            85: ("Controller: compressor restart timer still counting down; coil sensor 14.2 °C.", "the controller shows the compressor timer still counting down and the coil at 14.2 °C"),
            86: ("Controller: compressor running since 07:51; evaporator fans back on.", "the controller shows the compressor running since 07:51 and the fans back on"),
        }
        for t in range(83, 100):
            line = late_lines.get(t)
            surface = (lambda tk, i, line=line: {**tk.surface, "floor": line[0], "gist": line[1]}) if line else None
            out = override(out, [t], surface=surface, b1=readings[t], run_since=runs[t])
        for t in range(83, 86):
            out[t].note = "B1 still above the limit after the window, no alert open: alert the shift lead."
        out = tidy_counterfactual(self, ticks, out, "")
        out[31].note = "31 minutes above the limit: critical. The shift lead acknowledged at 05:49 but the facility manager has not, so rule 1 escalates for the first time."
        out[37].note = "Facility manager acknowledged at 06:13: hold while still critical."
        out[86].note = "B1 back at or below the limit (7.5 C) and no alert open: rule 4's conditions no longer hold, so it stops without any acknowledgement: hold."
        return out

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        now, b1 = z["clock"], z["b1"]
        above = b1 > z["upper"]
        since = z["run_since"]
        above_min = now - since if above else 0
        below_min = now - since if (not above and since is not None) else None
        alert = z["alert"]
        open_alert = alert is not None
        acknowledged = open_alert and (alert["lead_ack"] is not None or alert["mgr_ack"] is not None)
        manager_ack = open_alert and alert["mgr_ack"] is not None
        critical = b1 >= z["hard"] or (above and above_min > 30)
        window = any(
            w["zone"] == "B" and w["type"] in ("defrost", "maintenance") and w["start"] <= now < w["end"]
            for w in z["windows"]
        )
        if critical and not manager_ack:
            action = "escalate"
        elif window:
            action = "suppress"
        elif open_alert and not acknowledged and now - alert["raised"] > 10:
            action = "escalate"
        elif above and above_min > 10 and not acknowledged:
            action = "alert_lead"
        elif open_alert and below_min is not None and below_min > 10:
            action = "clear"
        else:
            action = "hold"
        if critical:
            severity = 3
        elif above and above_min > 10:
            severity = 2
        elif above:
            severity = 1
        else:
            severity = 0
        return {"action": action, "severity": severity}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Night into morning at a cold store. An evaporator fan trips during trailer loading; B1 passes 8 C, the alert to the shift lead goes unanswered and is escalated after 10 minutes (and again every report until acknowledged), the excursion turns critical after 30 minutes, the manager acknowledges, the fan is reset and the alert is cleared and closed. Later a scheduled defrost pushes B1 above the limit for 15 minutes inside the window (suppress outranks alerting). Distractors: dock-door air above the hard limit, another zone above 8 C asking about the manager, an 'all clear' about the dock, another zone's maintenance window, a defrost reminder before the window, a warm coil sensor, the manager's 'escalate anything else' remark. Hold-under-activity ticks carry two or three simultaneous floor messages."},
            "paraphrase": {"summary": "Same latent trajectory; Chiller B / alarm threshold / absolute ceiling / supervisor / site manager vocabulary, prose update instead of fields, reworded rules, levels and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; each report adds two unrelated site notices, each borrowing one action's wording (take no action, alert the shift lead, escalated to the facility manager, clear the open ..., suppress alerts for a scheduled window). The two actions are drawn per tick without looking at gold, so the gold action is named as often as any other."},
            "minimal_cf": {"summary": "Three edits: (1) t25-30 the shift lead acknowledges at 05:49 instead of 06:11 (alert.lead_ack), so there is no rule-3 escalation at 05:55 and the escalation comes at 06:03 under rule 1 (alert.escalated) (alert/escalate -> hold); (2) t34-36 the manager answers at 06:13 instead of 06:07 (alert.mgr_ack; hold -> escalate); (3) t83-85 the compressor restart is delayed so B1 stays above 8 C until 07:51 after the defrost with no alert open (b1 at t83-88, run_since from t83; hold,normal -> alert_lead,warning). No alert is raised for that excursion (open loop): rule 4 stops at t86 because B1 is back at or below the limit."},
            "structural_cf": {"summary": "A GreenCart own-label ready-meal lot has been stored in bay B4 since yesterday; its supply contract tightens the Zone B limits to 6.0 C upper and 10.0 C hard. The fan excursion starts earlier and reaches the hard limit (escalation under rule 1 from 05:48), the zone never qualifies for clearing before the alert is closed, and after the defrost B1 is still above 6 C for 25-29 minutes, which calls for alerting the shift lead. No alert is raised for that excursion (open loop): rule 4 stops at t86 because B1 is back at or below 6.0 C. The product-check floor lines (t41, t44, t55) follow the lot."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _profile(self, z: dict[str, Any]) -> str:
        if z["profile"] == "contract_lot":
            return (
                "Chiller Zone B holds dairy and packaged salads and, since yesterday, a GreenCart own-label ready-meal lot in bay B4 whose supply contract sets tighter limits. "
                f"While that lot is stored here the Zone B limits are: upper limit {z['upper']:.1f} °C, hard limit {z['hard']:.1f} °C. "
                "Probe B1 is Zone B's control probe."
            )
        return (
            f"Chiller Zone B holds dairy and packaged salads. Upper limit {z['upper']:.1f} °C, hard limit {z['hard']:.1f} °C. "
            "Probe B1 is Zone B's control probe."
        )

    def _earlier(self, history: list[Tick]) -> list[float]:
        vals = list(A_B1_PRE) + [tk.latent["b1"] for tk in history]
        return vals[-3:-1][::-1]  # the two readings before the latest, newest first

    def _feed(self, history: list[Tick]) -> list[str]:
        tick = history[-1]
        z, s, t = tick.latent, tick.surface, len(history) - 1
        p1, p2 = self._earlier(history)
        now = z["clock"]
        b1_line = pick(
            [
                "B1 (Zone B control probe): {b:.1f} °C at {n}; {p1:.1f} at {m1}; {p2:.1f} at {m2}",
                "{n} B1 {b:.1f} °C (previous: {p1:.1f} at {m1}, {p2:.1f} at {m2})",
                "B1 Zone B: {b:.1f} °C now ({n}); two minutes earlier {p1:.1f}; four minutes earlier {p2:.1f}",
            ],
            "a-b1",
            t,
        ).format(b=z["b1"], n=hhmm(now), p1=p1, p2=p2, m1=hhmm(now - 2), m2=hhmm(now - 4))
        door = "door up" if s["door_open"] else "door down"
        d3_line = pick(
            ["D3 (dock 3 door air): {d:.1f} °C, {door}", "{n} D3 dock 3 door air {d:.1f} °C ({door})"], "a-d3", t
        ).format(d=s["d3"], door=door, n=hhmm(now))
        c1_line = pick(
            ["C1 (Zone C, watched by the Zone C desk): {c:.1f} °C", "{n} C1 Zone C probe {c:.1f} °C (Zone C desk's zone)"],
            "a-c1",
            t,
        ).format(c=s["c1"], n=hhmm(now))
        return [b1_line, d3_line, c1_line]

    def _status(self, z: dict[str, Any], t: int) -> str:
        u = f"{z['upper']:.1f} °C"
        since = z["run_since"]
        if z["b1"] > z["upper"]:
            return pick(
                [
                    "B1 has been above {u} since {s}.",
                    "B1 went above {u} at {s} and has stayed above it.",
                    "Excursion timer: B1 above {u} continuously since {s}.",
                ],
                "a-up",
                t,
            ).format(u=u, s=hhmm(since))
        if since is None:
            return pick(
                ["B1 has stayed at or below {u} all shift.", "No B1 excursion this shift: at or below {u} throughout."],
                "a-never",
                t,
            ).format(u=u)
        return pick(
            [
                "B1 back at or below {u} since {s}.",
                "B1 returned to {u} or below at {s} and has stayed there.",
                "B1 has been at or below {u} since {s}.",
            ],
            "a-down",
            t,
        ).format(u=u, s=hhmm(since))

    def _alert_text(self, z: dict[str, Any], t: int) -> str:
        al, closed = z["alert"], z["closed_alert"]
        if closed is not None:
            return pick(
                [
                    "No Zone B alert is open. Alert #41 was closed at {c}.",
                    "Zone B alert board: nothing open (alert #41 closed {c}).",
                ],
                "a-alc",
                t,
            ).format(c=hhmm(closed["closed"]))
        if al is None:
            return pick(
                ["No Zone B alert has been raised this shift.", "Zone B alert board empty: nothing raised this shift."],
                "a-al0",
                t,
            )
        parts = [
            pick(
                [
                    "Zone B alert #41 raised {r} and open since then, sent to shift lead D. Okafor.",
                    "Alert #41 (Zone B) raised {r} and still open; shift lead D. Okafor notified.",
                ],
                "a-alo",
                t,
            ).format(r=hhmm(al["raised"]))
        ]
        if al["escalated"] is not None:
            parts.append(
                pick(
                    [
                        "Escalated to facility manager P. Raman at {e}.",
                        "Auto-dialler passed it to facility manager P. Raman at {e}.",
                        "Facility manager P. Raman first called about it at {e}.",
                    ],
                    "a-esc",
                    t,
                ).format(e=hhmm(al["escalated"]))
            )
        acks = []
        if al["mgr_ack"] is not None:
            acks.append(f"P. Raman (facility manager) at {hhmm(al['mgr_ack'])}")
        if al["lead_ack"] is not None:
            acks.append(f"D. Okafor (shift lead) at {hhmm(al['lead_ack'])}")
        if not acks:
            parts.append(
                pick(["Acknowledgements: none yet.", "Nobody has acknowledged it.", "No acknowledgement from anyone so far."], "a-ack0", t)
            )
        else:
            line = pick(["Acknowledged by {x}.", "Acknowledgements: {x}."], "a-ack1", t).format(x=" and ".join(acks))
            if al["mgr_ack"] is None:
                line += pick([" No acknowledgement from the facility manager.", " The facility manager has not acknowledged."], "a-ack2", t)
            parts.append(line)
        return " ".join(parts)

    def _schedule(self) -> str:
        return " ".join(f"{w['what']} {hhmm(w['start'])}-{hhmm(w['end'])}." for w in A_WINDOWS)

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z, t = tick.latent, len(history) - 1
        state: dict[str, Any] = {
            "zone_profile": self._profile(z),
            "schedule": self._schedule(),
            "report_time": hhmm(z["clock"]),
            "sensor_feed": self._feed(history),
            "b1_status": self._status(z, t),
            "alert_log": self._alert_text(z, t),
            "floor": moment_lines(tick.surface),
        }
        if variant == "lexical_decoy":
            targets = decoy_targets(list(A_OPTIONS), "a-decoy-target", t, 2)
            state["site_notices"] = [pick(A_DECOYS[a], "a-decoy", a, t) for a in targets]
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z, s, t = tick.latent, tick.surface, len(history) - 1
        u, h = f"{z['upper']:.1f} °C", f"{z['hard']:.1f} °C"
        now = hhmm(z["clock"])
        parts = [pick(["Update at {n}.", "Check-in, {n}.", "{n} update."], "p-head", t).format(n=now)]
        parts.append(
            f"Chiller B stocks dairy and bagged salads; its alarm threshold is {u} and its absolute ceiling {h}."
        )
        slots = "; ".join(f"{A_WINDOWS_P[w['what']]} {hhmm(w['start'])} to {hhmm(w['end'])}" for w in A_WINDOWS)
        parts.append(pick(["Planned slots: {x}.", "Today's planned slots are {x}."], "p-slots", t).format(x=slots))
        p1 = self._earlier(history)[0]
        if z["b1"] > p1:
            trend = f"up from {p1:.1f} °C two minutes before"
        elif z["b1"] < p1:
            trend = f"down from {p1:.1f} °C two minutes before"
        else:
            trend = "unchanged from two minutes before"
        parts.append(f"Control probe B1 reads {z['b1']:.1f} °C, {trend}.")
        since = z["run_since"]
        if z["b1"] > z["upper"]:
            parts.append(
                pick(
                    ["It went over {u} at {s} and has not come back down since.", "It has been over {u} without a break since {s}."],
                    "p-up",
                    t,
                ).format(u=u, s=hhmm(since))
            )
        elif since is None:
            parts.append(
                pick(["It has not gone over {u} at any point this shift.", "It has stayed at or under {u} all shift."], "p-never", t).format(u=u)
            )
        else:
            parts.append(
                pick(
                    ["It came back to {u} or under at {s} and has stayed there.", "It has been at or under {u} since {s}."],
                    "p-down",
                    t,
                ).format(u=u, s=hhmm(since))
            )
        parts.append(self._alarm_paraphrase(z, t))
        door = "door up" if s["door_open"] else "door shut"
        parts.append(
            pick(
                [
                    "Elsewhere, the dock 3 door sensor shows {d:.1f} °C ({door}) and Chiller C's probe {c:.1f} °C.",
                    "Other sensors: dock 3 door air {d:.1f} °C with the {door}; Chiller C, which its own team watches, {c:.1f} °C.",
                ],
                "p-other",
                t,
            ).format(d=s["d3"], door=door, c=s["c1"])
        )
        parts.append(pick(["Meanwhile, {g}.", "On the floor, {g}."], "p-gist", t).format(g=moment_gist(s)))
        return " ".join(parts)

    def _alarm_paraphrase(self, z: dict[str, Any], t: int) -> str:
        al, closed = z["alert"], z["closed_alert"]
        if closed is not None:
            return f"No Chiller B alarm is open; alarm #41 was closed at {hhmm(closed['closed'])}."
        if al is None:
            return pick(
                ["No Chiller B alarm has been raised this shift.", "The Chiller B alarm board is empty: no alarm raised this shift."],
                "p-al0",
                t,
            )
        out = pick(
            [
                "Chiller B alarm #41 was raised at {r} and is still open, with supervisor D. Okafor paged.",
                "Chiller B alarm #41, raised at {r}, is still open; supervisor D. Okafor was paged.",
            ],
            "p-alo",
            t,
        ).format(r=hhmm(al["raised"]))
        if al["escalated"] is not None:
            out += f" It was passed to site manager P. Raman at {hhmm(al['escalated'])}."
        confirmed = []
        if al["mgr_ack"] is not None:
            confirmed.append(f"the site manager at {hhmm(al['mgr_ack'])}")
        if al["lead_ack"] is not None:
            confirmed.append(f"the supervisor at {hhmm(al['lead_ack'])}")
        if not confirmed:
            out += " Nobody has confirmed it."
        else:
            out += " Confirmed by " + " and ".join(confirmed) + "."
            if al["mgr_ack"] is None:
                out += " The site manager has not confirmed it."
        return out


# ===========================================================================
# Scenario B - river-flood monitoring, action + zone + public-warning noul
# ===========================================================================

B_START = 6 * 60  # 06:00
B_TICK = 10
B_ZONES = ["WL", "MQ", "OB", "LM"]  # upstream to downstream
B_NAMES = {"WL": "Weir Lane", "MQ": "Mill Quarter", "OB": "Old Bridge", "LM": "Low Meadows"}
B_GAUGES = {"WL": "WL-1", "MQ": "MQ-2", "OB": "OB-3", "LM": "LM-4"}
# Thresholds in centimetres on the gauge boards.
B_THRESHOLDS = {
    "WL": {"watch": 240, "sandbag": 290, "evac": 340},
    "MQ": {"watch": 210, "sandbag": 255, "evac": 290},
    "OB": {"watch": 280, "sandbag": 320, "evac": 360},
    "LM": {"watch": 180, "sandbag": 220, "evac": 260},
}
B_LM_EVAC_REPAIR = 230  # structural_cf: temporary levee repair at Low Meadows

B_PRE = {"WL": 139, "MQ": 118, "OB": 154, "LM": 110}
B_SERIES = {
    "LM": [
        112, 115, 118, 121, 124, 127, 130, 134, 138, 142, 146, 149, 152, 153, 157, 163, 165, 167, 166, 165,
        164, 171, 175, 178, 186, 202, 223, 236, 241, 244, 246, 247, 248, 247, 245, 244, 242, 241, 239, 238,
        236, 235, 233, 232, 231, 229, 227, 226, 224, 223, 221, 219, 218, 217, 215, 214, 212, 211, 209, 208,
        206, 205, 203, 202, 200, 199, 197, 196, 194, 193, 191, 190, 188, 187, 185, 184, 182, 181, 179, 178,
        176, 175, 174, 172, 170, 169, 168, 166, 164, 163, 162, 161, 158, 157, 156, 154, 152, 151, 150, 148,
    ],
    "MQ": [
        120, 123, 125, 128, 130, 133, 136, 138, 141, 143, 146, 149, 151, 154, 157, 159, 162, 164, 167, 170,
        172, 175, 177, 180, 188, 195, 202, 208, 213, 218, 222, 226, 230, 233, 236, 239, 242, 245, 249, 293,
        297, 300, 304, 307, 309, 311, 312, 313, 311, 308, 305, 302, 299, 296, 293, 288, 285, 282, 279, 276,
        273, 270, 268, 265, 263, 260, 258, 256, 253, 250, 248, 245, 242, 240, 237, 235, 232, 230, 227, 225,
        222, 220, 217, 215, 212, 207, 204, 201, 198, 195, 192, 189, 186, 182, 179, 176, 173, 170, 167, 164,
    ],
    # OB-3's pressure sensor fails at 07:00 and returns alternating nonsense until
    # it is replaced at 11:30.
    "OB": [
        155, 157, 158, 160, 161, 162, 693, 2, 741, 5, 688, 0, 712, 4, 695, 1, 734, 3, 706, 0,
        689, 6, 721, 2, 698, 0, 715, 3, 702, 1, 690, 4, 709, 221, 225, 230, 236, 241, 246, 252,
        261, 268, 273, 277, 281, 284, 286, 285, 283, 281, 279, 276, 274, 272, 270, 267, 265, 263, 261, 258,
        256, 254, 252, 249, 247, 245, 243, 240, 238, 236, 234, 231, 229, 227, 225, 222, 220, 218, 216, 213,
        211, 209, 207, 204, 202, 200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176, 174, 172,
    ],
    # After the debris jam at the weir gives way (12:15) Weir Lane keeps rising
    # past its sandbag level while Mill Quarter also qualifies for sandbags, so
    # the downstream tie-break decides t43-47.
    "WL": [
        140, 142, 143, 145, 146, 148, 149, 151, 153, 154, 156, 157, 159, 160, 162, 164, 165, 167, 168, 170,
        171, 173, 174, 176, 178, 179, 181, 182, 184, 185, 187, 189, 190, 192, 193, 195, 196, 198, 236, 249,
        261, 272, 283, 293, 301, 307, 311, 313, 311, 308, 304, 300, 296, 293, 288, 284, 281, 277, 273, 270,
        266, 263, 259, 256, 252, 249, 245, 242, 238, 235, 232, 229, 227, 224, 222, 219, 217, 214, 212, 209,
        207, 204, 202, 199, 197, 195, 192, 190, 188, 186, 183, 181, 178, 175, 172, 169, 165, 161, 158, 154,
    ],
}

# Desk events (minutes since midnight); all fall between ten-minute reports.
# The desk's reaction times differ (25 to 55 minutes after the rule first
# matches), so gold segments run 3 to 5 reports and cannot be predicted by
# counting reports.
B_EVENTS = {
    "flag_ob": 455,  # 07:35 OB-3 flagged faulty (jumps since 07:00)
    "flag_ob_lifted": 695,  # 11:35 flag lifted after the sensor swap at 11:30
    "headsup_lm": 515,  # 08:35 heads-up for Low Meadows sent
    "headsup_lm_ack": 565,  # 09:25 acknowledged; Low Meadows eased off from 09:00
    "watch": 625,  # 10:25 flood watch issued
    "sandbags_lm": 655,  # 10:55
    "evac_mq": 785,  # 13:05
    "sandbags_mq": 835,  # 13:55
    "evac_lm": None,  # structural_cf only
    "cleared": 1245,  # 20:45 all advisories cleared
}
B_HANDOVER = 1080  # 18:00 duty officer handover
# Reports where the acknowledgement is shown only as Brandt's quoted reply while
# Low Meadows is rising within 0.20 m of its watch level (tagged implicit).
B_IMPLICIT_ACK = {21, 22, 23}

B_SCRIPT: list[tuple[str, str]] = [
    # t0-t5 rain, all low
    ("Depot rain gauge: 38 mm since midnight, still raining steadily.", "the depot rain gauge shows 38 mm since midnight with steady rain"),
    ("Highways: gully crews out on the ring road.", "highways crews are clearing gullies on the ring road"),
    ("Forecast: heavy rain over the upper Mere catchment until early afternoon.", "the forecast keeps heavy rain over the upper catchment until early afternoon"),
    ("County radio: 'Flood warning for the River Tarn at Oxley; residents there should move valuables upstairs.'", "county radio broadcasts a flood warning for the River Tarn at Oxley"),
    ("County radio repeats the Tarn warning for Oxley and Brindle.", "the radio repeats the Tarn warning for Oxley and Brindle"),
    ("Duty officer S. Brandt checks in by phone from the council depot.", "the on-call officer checks in by phone from the depot"),
    # t6-t14 Old Bridge sensor fails (flagged 07:35)
    ("Telemetry: routine 10-minute upload received from all four gauges.", "the routine telemetry upload has arrived from all four gauges"),
    ("Caller on Bridge Street: 'The river under the Old Bridge looks the same as yesterday.'", "a Bridge Street caller says the river under the Old Bridge looks the same as yesterday"),
    ("Brandt asks the telemetry contractor to look at OB-3 remotely.", "the on-call officer asks the telemetry contractor to look at the Old Bridge gauge remotely"),
    ("Contractor: 'OB-3's pressure sensor is failing; we'll send a technician.'", "the contractor says the Old Bridge pressure sensor is failing and a technician will come"),
    ("Contractor books a technician for the Old Bridge gauge; earliest slot late morning.", "the contractor books a technician for the Old Bridge gauge for late morning"),
    ("Caller from Bridge Street: 'Your website says the Old Bridge gauge is at nearly seven metres!'", "an alarmed caller says the council website shows nearly seven metres at the Old Bridge"),
    ("Local news desk asks for comment on a 'record reading' at Old Bridge.", "the local news desk asks about a 'record reading' at the Old Bridge"),
    ("News desk: 'Viewers are sending us screenshots of seven metres at the Old Bridge.'", "the news desk says viewers are sending screenshots of seven metres at the Old Bridge"),
    ("Depot rain gauge: 49 mm since midnight.", "rain since midnight has reached 49 mm"),
    # t15-t23 Low Meadows approaches its watch level, eases off, rises again
    ("School transport asks about the Low Meadows bus route; no roads closed yet.", "school transport asks about the Low Meadows bus route; no roads are closed"),
    ("Low Meadows field observer: 'Water up to the third step of the slipway.'", "the Low Meadows observer says water has reached the third step of the slipway"),
    ("Brandt's line is engaged; the heads-up went to his duty inbox.", "the on-call officer's line is engaged and the early notice sits in his inbox"),
    ("Low Meadows observer: 'Rain's eased off; the water has dropped back a touch on the slipway.'", "the Low Meadows observer says the rain has eased and the water has dropped back a little"),
    ("Brandt's line still engaged; he is on a long call with the county planner.", "the on-call officer is still on a long call with the county planner"),
    ("Resident text: 'Water right across Weir Lane outside no. 14, ankle deep.'", "a resident texts that water is right across Weir Lane outside number 14"),
    ("Second resident text: 'Water now at the Weir Lane shop doorways.'", "a second resident texts that water has reached the Weir Lane shop doorways"),
    ("Depot rain gauge: 58 mm since midnight; heavy rain again.", "rain since midnight has reached 58 mm and it is pouring again"),
    ("Low Meadows observer: 'Slipway covered, water at the edge of the footpath.'", "the Low Meadows observer says the slipway is covered and water is at the footpath edge"),
    # t24-t38 watch, sandbags at Low Meadows
    ("Brandt is on the phone to the county emergency planner.", "the on-call officer is on the phone to the county emergency planner"),
    ("Mill Quarter observer: 'River rising fast by the mill race.'", "the Mill Quarter observer says the river is rising fast by the mill race"),
    ("Low Meadows allotments flooding at the river end.", "the river end of the Low Meadows allotments is flooding"),
    ("Local radio reads out the Kessling flood watch.", "local radio is reading out the Kessling flood-watch notice"),
    ("Depot: a trailer with 400 sandbags is loaded and waiting for a destination.", "the depot has a trailer of 400 sandbags loaded and waiting for a destination"),
    ("Low Meadows residents are moving cars off Riverside Walk.", "Low Meadows residents are moving their cars off Riverside Walk"),
    ("Depot: sandbag trailer leaving for Low Meadows.", "the sandbag trailer is leaving the depot for Low Meadows"),
    ("Rugby club volunteers arrive at the Low Meadows community hall.", "rugby club volunteers arrive at the Low Meadows community hall"),
    ("Sandbag crew unloading at Riverside Walk; volunteers form a chain.", "the sandbag crew is unloading at Riverside Walk while volunteers form a chain"),
    ("Technician at the Old Bridge gauge, swapping the sensor.", "a technician is swapping the Old Bridge sensor"),
    ("Community hall opens as a warm space; tea urn on.", "the community hall opens as a warm space"),
    ("Sandbag wall along Riverside Walk: two bags high over 60 metres.", "a two-bag-high sandbag wall now runs sixty metres along Riverside Walk"),
    ("Depot rain gauge: 71 mm; rain easing slightly.", "rain totals 71 mm and is easing a little"),
    ("Weir Lane resident: 'Loud crack from the weir, lots of branches going over.'", "a Weir Lane resident reports a loud crack at the weir and branches going over"),
    ("Weir keeper: 'The debris jam at the weir gave way a few minutes ago.'", "the weir keeper says the debris jam at the weir gave way a few minutes ago"),
    # t39-t55 debris surge, Mill Quarter evacuation, Weir Lane over its sandbag level
    ("Mill Quarter observer: 'Water over the mill race wall into Tanner's Yard.'", "the Mill Quarter observer sees water pouring over the mill race wall into Tanner's Yard"),
    ("Tanner's Yard residents phoning for advice.", "Tanner's Yard residents are phoning for advice"),
    ("Brandt: 'Opening a rest centre at St Anne's school.'", "the on-call officer is opening a rest centre at St Anne's school"),
    ("Police cordon at the Mill Quarter end of Bridge Street.", "police have put a cordon at the Mill Quarter end of Bridge Street"),
    ("Mill Quarter shopkeepers carrying stock upstairs.", "Mill Quarter shopkeepers are carrying stock upstairs"),
    ("Weir Lane residents phoning the desk to ask for sandbags.", "Weir Lane residents are phoning the room to ask for sandbags"),
    ("Weir Lane observer: 'River over the towpath and up to the garden walls.'", "the Weir Lane observer says the river is over the towpath and up to the garden walls"),
    ("Weir Lane councillor: 'Our end of the lane needs sandbags as much as anyone.'", "the Weir Lane councillor insists that her end of the lane needs sandbags as much as anyone"),
    ("Police knocking on doors in Tanner's Yard.", "police are knocking on doors in Tanner's Yard"),
    ("St Anne's rest centre: 12 residents registered.", "twelve residents have registered at the rest centre"),
    ("Second sandbag trailer on its way to Mill Quarter.", "a second trailer of sandbags is on its way to Mill Quarter"),
    ("Red Cross team arrives at St Anne's.", "a Red Cross team arrives at the rest centre"),
    ("Police: Tanner's Yard door-knock finished, 31 households told.", "police have finished door-knocking in Tanner's Yard"),
    ("Crew building a sandbag line along Mill Street.", "a crew is building a sandbag line along Mill Street"),
    ("St Anne's: 27 registered, hot meals ordered.", "the rest centre has twenty-seven people and has ordered hot meals"),
    ("Local radio interviews Brandt about the Mill Quarter advisory.", "local radio interviews the on-call officer about the Mill Quarter notice"),
    ("Low Meadows observer: 'Water dropping back from the footpath.'", "the Low Meadows observer says the water is falling back from the footpath"),
    # t56-t71 slow fall
    ("St Anne's: evacuees asking whether they can go home now that Mill Quarter is dropping.", "evacuees at the rest centre ask whether they can go home now that the Mill Quarter water is dropping"),
    ("Mill Quarter observer: 'Water's back below the mill race wall.'", "the Mill Quarter observer says the water is back below the mill race wall"),
    ("Councillor on the phone: 'Surely the evacuation can be stood down now?'", "a councillor asks whether the evacuation can be stood down"),
    ("Technician: new Old Bridge sensor stable since the swap.", "the technician reports the new Old Bridge sensor stable"),
    ("16:00 county call: river falling slowly; advisories kept under review.", "the four o'clock county call notes the river falling slowly"),
    ("Weir Lane residents sweeping silt off the towpath.", "Weir Lane residents are sweeping silt off the towpath"),
    ("Sandbag crews stood down for a meal break.", "the sandbag crews stop for a meal break"),
    ("Photographer asks to go inside the Mill Quarter cordon.", "a photographer asks to go inside the Mill Quarter cordon"),
    ("Forecast: rain has stopped across the catchment; none expected tonight.", "the forecaster says the rain has stopped across the catchment"),
    ("Brandt: 'Rain's done. Feels like the worst is over.'", "the on-call officer remarks that the rain is over and the worst seems past"),
    ("Radio presenter: 'Good news for Kessling, the rain has finally stopped.'", "a radio presenter celebrates the end of the rain in Kessling"),
    ("Red Cross: 19 evacuees still at St Anne's.", "nineteen evacuees are still at the rest centre"),
    ("Police cut the Bridge Street cordon to one officer.", "police reduce the Bridge Street cordon to one officer"),
    ("Low Meadows allotment holders surveying the damage.", "Low Meadows allotment holders are surveying the damage"),
    ("Loss adjuster calls to book visits in Tanner's Yard.", "a loss adjuster calls to book visits in Tanner's Yard"),
    ("Brandt writes handover notes for the evening officer.", "the on-call officer writes handover notes"),
    # t72-t84 evening handover, levels falling
    ("Handover: K. Osei takes over as duty officer from S. Brandt.", "K. Osei takes over as on-call officer from S. Brandt"),
    ("Osei reads through the advisories and sandbag requests he has inherited.", "the new on-call officer reads through the notices and sandbag orders he has inherited"),
    ("Street lighting fault reported on Mill Street.", "a street lighting fault is reported on Mill Street"),
    ("St Anne's: 11 evacuees staying overnight.", "eleven evacuees will stay overnight at the rest centre"),
    ("Low Meadows observer signs off until 20:00.", "the Low Meadows observer signs off until eight"),
    ("Old Bridge: river well below the arches.", "the river at the Old Bridge is well below the arches"),
    ("Weir keeper clears the last debris from the weir.", "the weir keeper clears the last debris from the weir"),
    ("Council press office drafts a recovery statement.", "the council press office drafts a recovery statement"),
    ("Mill Quarter observer: 'Mill Street still wet, water in the gutters.'", "the Mill Quarter observer says Mill Street is still wet"),
    ("Red Cross rotates its staff at St Anne's.", "the Red Cross rotates its staff at the rest centre"),
    ("Police lift the Bridge Street cordon.", "police lift the Bridge Street cordon"),
    ("Osei asks for gauge trends before the 20:00 call.", "the on-call officer asks for gauge trends before the eight o'clock call"),
    ("20:00 county call: levels falling everywhere.", "the eight o'clock county call notes falling levels everywhere"),
    # t85-t99 clear (20:45) and aftermath
    ("Low Meadows observer back on shift: 'Riverside Walk is clear of water.'", "the Low Meadows observer, back on shift, says Riverside Walk is clear"),
    ("Osei checks the advisory wording with the press office.", "the on-call officer checks notice wording with the press office"),
    ("St Anne's asks when evacuees may go home.", "the rest centre asks when evacuees may go home"),
    ("Red Cross asks the evacuees to wait for the council's word before leaving.", "the Red Cross asks the evacuees to wait for the council's word before leaving"),
    ("Local radio reads out that Kessling's flood advisories have ended.", "local radio announces that Kessling's flood notices have ended"),
    ("Evacuees leaving St Anne's by minibus.", "evacuees are leaving the rest centre by minibus"),
    ("Sandbag collection booked for tomorrow morning.", "sandbag collection is booked for the morning"),
    ("Red Cross closes the rest centre.", "the Red Cross closes the rest centre"),
    ("Council duty engineer checks the Low Meadows levee.", "the council engineer checks the Low Meadows levee"),
    ("Environment team uploads the day's gauge data to the archive.", "the environment team archives the day's gauge data"),
    ("Osei logs 43 calls received today.", "the on-call officer logs 43 calls today"),
    ("Weather: clear skies, 6 °C.", "the sky has cleared and it is six degrees"),
    ("Technician's report on the Old Bridge sensor filed.", "the technician's report on the Old Bridge sensor is filed"),
    ("Osei: phones quiet now.", "the phones have gone quiet"),
    ("Night observer starts rounds at Weir Lane.", "the night observer starts rounds at Weir Lane"),
]

# Extra incoming messages on the hold-under-activity ticks: callers, councillors
# and the press push for evacuations, sandbags, lifting or reissuing advisories,
# while the gauges and the desk records keep the decision unchanged.
B_BUSY: dict[int, list[tuple[str, str]]] = {
    31: [
        ("Caller from Riverside Walk: 'Shouldn't Low Meadows be evacuated by now?'", "a Riverside Walk caller asks whether Low Meadows should be evacuated by now"),
        ("Mill Quarter councillor asks for sandbags for Mill Street.", "a Mill Quarter councillor asks for sandbags on Mill Street"),
    ],
    32: [
        ("Radio producer: 'Will the flood watch be upgraded this afternoon?'", "a radio producer asks whether the flood watch will be upgraded this afternoon"),
        ("Old Bridge shop owner asks whether to move stock upstairs.", "an Old Bridge shop owner asks whether to move stock upstairs"),
    ],
    33: [
        ("Low Meadows resident: 'The water's at my back gate, do we need to leave?'", "a Low Meadows resident with water at the back gate asks whether they need to leave"),
        ("Volunteers ask where the next sandbag trailer is going.", "volunteers ask where the next sandbag trailer is going"),
    ],
    34: [
        ("County planner: 'Are you considering evacuation anywhere yet?'", "the county planner asks whether evacuation is being considered anywhere yet"),
        ("Press office wants a line on the Old Bridge sensor.", "the press office wants a statement on the Old Bridge sensor"),
    ],
    35: [
        ("Weir Lane resident: 'Can we have sandbags too?'", "a Weir Lane resident asks for sandbags too"),
        ("Radio asks whether the flood watch covers the school run.", "the radio asks whether the flood watch covers the school run"),
    ],
    49: [
        ("Weir Lane residents: 'Where are our sandbags?'", "Weir Lane residents ask where their sandbags are"),
        ("Old Bridge caller: 'Water's nearly at the arches, should we leave?'", "an Old Bridge caller says the water is nearly at the arches and asks whether to leave"),
    ],
    50: [
        ("County planner asks whether the evacuation should be widened to Old Bridge.", "the county planner asks whether the evacuation should be widened to the Old Bridge"),
        ("Radio asks whether the flood watch will stay on overnight.", "the radio asks whether the flood watch will stay on overnight"),
    ],
    51: [
        ("Tanner's Yard resident asks to go back in for a pet.", "a Tanner's Yard resident asks to go back in for a pet"),
        ("Low Meadows councillor wants the sandbag wall extended.", "a Low Meadows councillor wants the sandbag wall extended"),
    ],
    52: [
        ("Old Bridge pub landlord asks for sandbags.", "the Old Bridge pub landlord asks for sandbags"),
        ("Environment team: 'Upper catchment levels have peaked.'", "the environment team says upper-catchment levels have peaked"),
    ],
    53: [
        ("Caller: 'My app says Weir Lane is falling, can we take the flood boards down?'", "a caller asks whether Weir Lane flood boards can come down because an app shows the level falling"),
        ("Red Cross asks for a second rest centre in case Old Bridge floods.", "the Red Cross asks for a second rest centre in case the Old Bridge floods"),
    ],
    68: [
        ("Councillor: 'Can we lift the flood watch before the evening news?'", "a councillor asks whether the flood watch can be lifted before the evening news"),
        ("Radio: listeners keep asking whether the watch is over.", "the radio says listeners keep asking whether the watch is over"),
    ],
    69: [
        ("Resident: 'Low Meadows looks fine now, why is the watch still on?'", "a resident asks why the watch is still on when Low Meadows looks fine"),
        ("Loss adjuster asks for gauge data for Tanner's Yard.", "a loss adjuster asks for gauge data for Tanner's Yard"),
    ],
    70: [
        ("Press office drafts a stand-down message and waits for the desk.", "the press office drafts a stand-down message and waits for the room"),
        ("Old Bridge caller asks whether the sandbags can be collected yet.", "an Old Bridge caller asks whether the sandbags can be collected yet"),
    ],
    71: [
        ("Brandt: 'I'd like the evacuation stood down before I hand over.'", "the on-call officer says he would like the evacuation stood down before the handover"),
        ("Mill Quarter observer: 'Still water standing in Tanner's Yard.'", "the Mill Quarter observer says water is still standing in Tanner's Yard"),
    ],
    92: [
        ("Resident: 'Will you tell us if it rises again tonight?'", "a resident asks to be told if the river rises again tonight"),
        ("Press office asks whether to reissue the flood watch for tomorrow.", "the press office asks whether to reissue the flood watch for tomorrow"),
    ],
    93: [
        ("Night observer: 'Weir Lane board reads well below the flood-watch mark.'", "the night observer says the Weir Lane board reads well below its flood-watch mark"),
        ("Caller from Mill Street asks when the sandbags will be taken away.", "a Mill Street caller asks when the sandbags will be taken away"),
    ],
    94: [
        ("Forecaster: 'Another band of rain is possible on Thursday.'", "the forecaster says another band of rain is possible on Thursday"),
        ("Osei asks the depot to count the sandbags left in stock.", "the on-call officer asks the depot to count the sandbags left"),
    ],
    95: [
        ("Councillor asks for a heads-up if anything changes overnight.", "a councillor asks to be told if anything changes overnight"),
        ("Red Cross returns the rest-centre keys to the school.", "the Red Cross returns the rest-centre keys to the school"),
    ],
}

B_ROLE = (
    "You are the flood-monitoring assistant at the Kessling flood desk. A situation report arrives every 10 minutes. "
    "`flood_desk` lists the four riverside zones from upstream to downstream and each zone's watch, sandbag and "
    "evacuation levels in gauge metres. `gauges` gives each zone's latest reading and the reading 10 minutes before it. "
    "`gauge_flags`, `public_advisories`, `sandbag_requests` and `duty_officer` show what the desk has already done."
)
B_DEFS = [
    "A gauge is rising if its latest reading is higher than the one 10 minutes before, and falling if it is lower.",
    "A gauge is in use unless it is flagged faulty in `gauge_flags` or its latest reading differs from the one before by more than 0.50 m. Rules 2 to 6 look only at gauges in use.",
    "An advisory, sandbag request or gauge flag counts as done once the report shows it in force, requested or flagged. A heads-up counts as done only once the report shows the duty officer has acknowledged it; a written reply from the duty officer showing that they have seen the heads-up counts as acknowledging it. A heads-up that has been sent but not acknowledged does not count.",
    "A rule matches at a report only when all of its conditions hold at that report. Sending an action does not stop its rule: until the action counts as done, the rule matches again at every report where all of its conditions still hold. A rule whose conditions no longer all hold does not match, even if its action is not yet done.",
    "If more than one zone qualifies under the same rule, take the zone furthest downstream.",
]
B_POLICY = [
    "1. A gauge that is not flagged faulty has a latest reading that differs from the one before by more than 0.50 m: action = mark the gauge faulty, zone = that gauge's zone.",
    "2. Otherwise, a zone's gauge is at or above that zone's evacuation level and no evacuation advisory is in force for that zone: action = evacuation advisory, zone = that zone.",
    "3. Otherwise, a zone's gauge is at or above that zone's watch level and no flood watch is in force: action = public flood watch, zone = all zones (the flood watch always covers the whole town).",
    "4. Otherwise, a zone's gauge is at or above that zone's sandbag level and rising, and no sandbags have been requested for that zone: action = sandbag request, zone = that zone.",
    "5. Otherwise, no flood watch is in force, a zone's gauge is rising and less than 0.20 m below that zone's watch level, and no heads-up for that zone has been acknowledged today (one that was sent but not acknowledged does not count): action = heads-up to the duty officer, zone = that zone. The gauge must be rising at this report; an unacknowledged heads-up does not keep rule 5 matching once the gauge stops rising.",
    "6. Otherwise, a flood watch or an evacuation advisory is in force and every gauge in use is below its zone's watch level: action = clear the advisories, zone = all zones.",
    "7. Otherwise: action = keep monitoring, zone = no zone.",
]
B_WARNING_RULE = (
    "A public warning is required when at least one gauge in use is at or above its zone's watch level. "
    "A gauge is not in use if it is flagged faulty in `gauge_flags` or its latest reading differs from the one before by more than 0.50 m. "
    "Advisories already in force, sandbag requests, and reports from residents, radio or other rivers do not change the answer."
)
B_ACTIONS = {
    "keep": {"category": "monitor", "action": "Keep monitoring the gauges and issue nothing new."},
    "faulty": {"category": "monitor", "action": "Mark the gauge that jumped as faulty and ignore its readings."},
    "notify": {"category": "notify", "action": "Send the duty officer a heads-up about a zone nearing its watch level."},
    "watch": {"category": "notify", "action": "Issue the public flood watch for the whole town."},
    "clear": {"category": "notify", "action": "Clear the public advisories that are in force."},
    "sandbags": {"category": "act", "action": "Request sandbag deployment to the zone that needs it."},
    "evac": {"category": "act", "action": "Issue an evacuation advisory for the zone that reached its evacuation level."},
}
B_TARGETS = {"WL": "Weir Lane", "MQ": "Mill Quarter", "OB": "Old Bridge", "LM": "Low Meadows", "all": "All zones", "none": "No zone"}

B_ROLE_P = (
    "You support the Kessling flood room. A written update comes in every ten minutes. It names the four riverside zones "
    "in order from upstream to downstream and gives, for each zone, three marks in centimetres on its gauge board "
    "(flood-watch mark, sandbag mark, evacuation mark), plus each gauge's newest reading and the reading ten minutes earlier, "
    "and says which tags, notices, sandbag orders and early notices the room has already put out."
)
B_DEFS_P = [
    "A gauge is going up if its newest reading is above the one ten minutes earlier, and coming down if it is below it.",
    "A gauge counts only if it is not tagged unreliable and its newest reading is no more than 50 cm away from the one before. Steps 2 to 6 ignore gauges that do not count.",
    "A notice, sandbag order or unreliable tag exists once the update reports it live, placed or tagged. An early notice only counts once the update shows the on-call officer has confirmed it; a written reply from the on-call officer showing that they have seen the early notice counts as confirming it. One that has gone out without being confirmed does not count.",
    "A step fits an update only if every one of its conditions holds at that update. Having sent something does not end its step: until it counts, the step fits again at every update where all its conditions are still true. A step with a condition that is no longer true does not fit, even if what it asks for does not count yet.",
    "When two or more zones fit the same step, pick the one furthest downstream.",
]
B_POLICY_P = [
    "1. A gauge that is not tagged unreliable shows a newest reading more than 50 cm away from the one before: tag that gauge as unreliable; zone = the zone of that gauge.",
    "2. Failing step 1: a zone's gauge is at or over its evacuation mark and that zone has no live evacuation notice: evacuation notice; zone = that zone.",
    "3. Failing the steps above: a zone's gauge is at or over its flood-watch mark and no flood-watch notice is live: town-wide flood-watch notice; zone = whole town (the flood watch always covers every zone).",
    "4. Failing the steps above: a zone's gauge is at or over its sandbag mark and going up, and no sandbags have been ordered for that zone: sandbag order; zone = that zone.",
    "5. Failing the steps above: no flood-watch notice is live, a zone's gauge is going up and sits less than 20 cm under its flood-watch mark, and no early notice about that zone has been confirmed today (an unconfirmed one does not count): early notice to the on-call officer; zone = that zone. The gauge has to be going up at this update; an unconfirmed early notice does not keep step 5 fitting once the gauge stops going up.",
    "6. Failing the steps above: a flood-watch or evacuation notice is live and every counting gauge is under its zone's flood-watch mark: withdraw the notices; zone = whole town.",
    "7. Otherwise: carry on watching; zone = none in particular.",
]
B_WARNING_RULE_P = (
    "The public has to be warned when at least one counting gauge is at or over its zone's flood-watch mark. "
    "A gauge does not count if it is tagged unreliable or its newest reading is more than 50 cm away from the one before. "
    "Notices that are already live, sandbag orders, and what residents, radio or other rivers report make no difference."
)
B_ACTIONS_P = {
    "keep": {"category": "observe", "action": "Carry on watching the river readings and send out nothing."},
    "faulty": {"category": "observe", "action": "Tag the gauge whose reading leapt as unreliable and disregard it."},
    "notify": {"category": "inform", "action": "Give the on-call officer an early notice about a zone closing in on its flood-watch mark."},
    "watch": {"category": "inform", "action": "Put out the town-wide flood-watch notice to the public."},
    "clear": {"category": "inform", "action": "Withdraw the public notices that are currently live."},
    "sandbags": {"category": "respond", "action": "Order sandbags to be sent where the step says they are needed."},
    "evac": {"category": "respond", "action": "Put out an evacuation notice for the area that has hit its evacuation mark."},
}
B_TARGETS_P = {
    "WL": "Weir Lane area",
    "MQ": "Mill Quarter area",
    "OB": "Old Bridge area",
    "LM": "Low Meadows area",
    "all": "The whole town",
    "none": "None in particular",
}

# Unrelated community notices for the lexical-decoy register, keyed by the
# action whose vocabulary they borrow. None of them concerns the river. Three
# notices are shown per report, chosen by ``decoy_targets`` without looking at
# gold. Each notice borrows three to six words of its action's option text;
# the keep-monitoring notices borrow only "keep monitoring", because the rest
# of that option ("the gauges", "issue nothing new") is too generic to place in
# an unrelated notice without reading as a statement about the river.
B_DECOYS = {
    "keep": [
        "Leisure centre: staff will keep monitoring the pool heater until the engineer has been.",
        "Library: volunteers keep monitoring the returns box over the bank holiday.",
        "Allotment society: the committee will keep monitoring the water butts through the dry spell.",
        "Swimming club: coaches keep monitoring lane bookings in the run-up to the gala.",
        "Bowls club: the groundsman will keep monitoring the green before Saturday's fixture.",
    ],
    "faulty": [
        "Sports hall: the boiler gauge jumped overnight; the caretaker has marked it faulty and will ignore its readings until the engineer calls.",
        "School: the playground clock was marked faulty and staff will ignore it until it is replaced.",
        "Garage on Mill Road: the tyre-pressure gauge jumped all morning, so it is marked faulty; ignore its readings.",
        "Leisure centre: the sauna gauge jumped to 140 degrees and has been marked faulty; staff ignore its readings.",
        "Community garden: the soil-moisture gauge is marked faulty; volunteers should ignore its readings.",
    ],
    "notify": [
        "Allotment society: send the duty officer a heads-up when the plot zone by the gate is nearing its water limit.",
        "Choir: send the duty officer a heads-up when the balcony zone of the hall is nearing its seat limit.",
        "Market car park: the duty officer gets a heads-up when the stall zone is nearing its capacity level.",
        "Youth club: send the duty officer a heads-up if the games-room zone is nearing its limit.",
        "Library: a heads-up goes to the duty officer when the study zone is nearing its seat level.",
    ],
    "watch": [
        "Neighbourhood watch: the public newsletter for the whole town will be issued on Friday.",
        "Cinema: the town's public film-watch night is issued as a leaflet this week.",
        "Neighbourhood watch: we issue the public meeting date for the whole town in the parish magazine.",
        "Birdwatch group: the whole-town public garden bird watch is issued as a leaflet on Saturday.",
        "Churches together: we issue public watch-night service times for the whole town in the newsletter.",
    ],
    "clear": [
        "Town hall: volunteers will clear the public advisories board in the foyer; the parking rules in force since spring stay up.",
        "Library: volunteers will clear the public noticeboard of advisories that are out of date.",
        "Leisure centre: the pool advisories in force during the refit will be cleared on Monday.",
        "Parish council: the public footpath advisories will be cleared once the stiles are repaired; the dog rules stay in force.",
        "Market: the traders' advisories in force for the roadworks will be cleared from the public board this week.",
    ],
    "sandbags": [
        "Market: stallholders can request deployment of sandbag weights for any gazebo that needs them on Saturday.",
        "Garden centre: request sandbag deployment at the till for any tree stand that needs weighting.",
        "Fun run: marshals may request sandbag deployment for any finish-zone banner that needs it.",
        "Scouts: the camp zone needs sandbag weights; request deployment from the quartermaster.",
        "Fete committee: request sandbag deployment for any stall zone whose gazebo needs weighting.",
    ],
    "evac": [
        "Primary school: we issue an evacuation advisory to parents in the infant zone before Tuesday's fire drill.",
        "Cinema: the evacuation advisory for the screen 2 zone was reissued after the refit.",
        "Shopping centre: we issue an evacuation advisory for the upper zone before Thursday's alarm test.",
        "Care home: a practice evacuation advisory is issued for the east zone on Wednesday.",
        "Leisure centre: we issue an evacuation advisory for the pool zone each time the fire drill is held.",
    ],
}


def b_levels(series: dict[str, list[int]], t: int) -> dict[str, list[int]]:
    return {k: [series[k][t - 1] if t > 0 else B_PRE[k], series[k][t]] for k in B_ZONES}


def b_desk(clock: int, events: dict[str, int | None]) -> dict[str, Any]:
    """The desk's records at report time ``clock``: only what has already happened."""
    ev = seen(events, clock)
    flags: dict[str, Any] = {}
    repairs: dict[str, int] = {}
    if ev["flag_ob_lifted"] is not None:
        repairs["OB"] = ev["flag_ob_lifted"]
    elif ev["flag_ob"] is not None:
        flags["OB"] = {"since": ev["flag_ob"]}
    evac = {k: ev[f"evac_{k.lower()}"] for k in ("LM", "MQ") if ev[f"evac_{k.lower()}"] is not None}
    sandbags = {k: ev[f"sandbags_{k.lower()}"] for k in ("LM", "MQ") if ev[f"sandbags_{k.lower()}"] is not None}
    headsup = {}
    if ev["headsup_lm"] is not None:
        headsup["LM"] = {"sent": ev["headsup_lm"], "acknowledged": ev["headsup_lm_ack"] is not None, "ack_at": ev["headsup_lm_ack"]}
    officer = {"name": "S. Brandt"} if clock < B_HANDOVER else {"name": "K. Osei", "since": B_HANDOVER, "previous": "S. Brandt"}
    return {
        "flags": flags,
        "repairs": repairs,
        "advisories": {"watch": ev["watch"], "evac": evac, "cleared": ev["cleared"]},
        "sandbags": sandbags,
        "headsup": headsup,
        "officer": officer,
    }


def m(cm: int) -> str:
    return f"{cm / 100:.2f}"


class RiverFloodDesk(Scenario):
    family = FAMILY
    scenario_id = "monitoring_b"
    title = "Flood alerting for four riverside zones of a town"
    tier = "hard"
    difficulty_features = [
        "three_questions_per_decision",
        "categorised_action_options",
        "seven_options",
        "six_way_zone_target",
        "noul_public_warning",
        "seven_rule_priority_policy",
        "per_zone_threshold_lookup",
        "trend_from_two_readings",
        "unlabelled_faulty_gauge",
        "implicit_acknowledgement",
        "downstream_tie_break",
    ]
    decision_structures = ["maintain", "escalate", "recover", "resolve-conflict", "terminate"]
    deadline_steps = 1

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            base = {"role": B_ROLE_P, "definitions": B_DEFS_P, "steps": B_POLICY_P}
            return [
                Choice("action", {**base, "question": "Take the first step that fits. What should the flood room do at this moment?"}, copy.deepcopy(B_ACTIONS_P)),
                Choice("zone", {**base, "question": "Take the first step that fits. Which zone is that step about at this moment?"}, dict(B_TARGETS_P)),
                Noul(
                    "public_warning",
                    {"role": B_ROLE_P, "rule": B_WARNING_RULE_P, "question": "Does the public need to be warned at this moment?"},
                    {"true": "The public needs a warning now.", "false": "The public does not need a warning now."},
                ),
            ]
        base = {"role": B_ROLE, "definitions": B_DEFS, "policy": B_POLICY}
        return [
            Choice("action", {**base, "question": "Apply the first rule that matches. Which action should the desk take right now?"}, copy.deepcopy(B_ACTIONS)),
            Choice("zone", {**base, "question": "Apply the first rule that matches. Which zone does that action concern right now?"}, dict(B_TARGETS)),
            Noul(
                "public_warning",
                {"role": B_ROLE, "rule": B_WARNING_RULE, "question": "Is a public warning required right now?"},
                {"true": "Yes: a public warning is required now.", "false": "No: no public warning is required now."},
            ),
        ]

    # ------------------------------------------------------------------ latent
    def _ticks(self, series: dict[str, list[int]], events: dict[str, int | None], thresholds: dict[str, Any]) -> list[Tick]:
        ticks = []
        for t in range(100):
            clock = B_START + B_TICK * t
            floor, gist = B_SCRIPT[t]
            latent = {
                "clock": clock,
                "thresholds": copy.deepcopy(thresholds),
                "levels": b_levels(series, t),
                **b_desk(clock, events),
            }
            ticks.append(Tick(latent, {"floor": floor, "gist": gist, "busy": list(B_BUSY.get(t, []))}, [], ""))
        return ticks

    def _canonical(self) -> list[Tick]:
        ticks = self._ticks(B_SERIES, B_EVENTS, B_THRESHOLDS)
        notes = {
            3: "Flood warning is for a different river.",
            6: "OB-3 jumps 1.62 -> 6.93 m in 10 minutes, never labelled faulty: mark it faulty. Its 6.93 m is above OB's evacuation level, but a jumping gauge is not in use, so rule 2 cannot match.",
            7: "A caller says the river looks as it did yesterday, which tempts keep monitoring; OB-3 has just dropped 6.91 m and is still unflagged: mark it faulty.",
            8: "OB-3 reads 7.41 m, far above Old Bridge's 3.60 m evacuation level, which tempts an evacuation; the reading jumped by more than 0.50 m, so the gauge is not in use and rule 1 applies.",
            9: "Contractor says the sensor is failing, but the flag is not shown yet: still mark faulty.",
            10: "OB-3 flagged at 07:35: back to monitoring.",
            11: "Flagged gauge alternates between about 0 and 7 m (6.88 m ten minutes ago); it is ignored.",
            15: "Low Meadows 1.63 m, 0.17 m below its 1.80 watch level and rising: heads-up.",
            16: "Heads-up sent 08:35 but not acknowledged: rule 5 keeps matching while Low Meadows rises.",
            18: "Low Meadows falls 1.67 -> 1.66 m: rule 5 needs a rising gauge, so keep monitoring although the heads-up is still unacknowledged.",
            20: "Water on Weir Lane is not a gauge reading; WL is far below its levels.",
            21: "Low Meadows rising and within 0.20 m again, but Brandt's reply at 09:25 acknowledges the heads-up: keep.",
            24: "Low Meadows 1.86 m reaches its watch level: town-wide flood watch.",
            25: "Mill Quarter would need a heads-up, but the flood watch outranks it.",
            26: "Low Meadows at its sandbag level and rising, but the flood watch comes first.",
            27: "Watch in force since 10:25: sandbags for Low Meadows.",
            30: "Sandbags requested 10:55: keep monitoring (warning still required).",
            38: "Weir Lane rises 0.38 m in 10 minutes: fast but not more than 0.50 m, so the gauge stays in use.",
            39: "Mill Quarter surges 2.49 -> 2.93 m (0.44 m, in use): evacuation outranks sandbags.",
            43: "Evacuation advisory in force since 13:05. Mill Quarter (3.07 m) and Weir Lane (2.93 m) are both above their sandbag levels and rising with no request: the tie-break picks Mill Quarter, further downstream.",
            48: "Sandbags for Mill Quarter requested 13:55; Weir Lane is falling, so it no longer qualifies.",
            56: "Mill Quarter below its evacuation level but above its watch level: no clearing.",
            64: "Rain has stopped, but gauges are still above watch levels.",
            72: "Duty officer handover.",
            85: "Mill Quarter 2.07 m, the last gauge to fall below its watch level: clear all advisories.",
            89: "Advisories cleared at 20:45.",
        }
        tags = span_tags(
            {
                "distractor": [(3, 4), (7, 8), (11, 13), (20, 21), 38, (44, 46), (56, 58), (64, 66)],
                "minimal_change": [15, 24, 85],
                "recovery": [10, 18, 89],
                "hold_under_activity": [(31, 35), (49, 53), (68, 71), (92, 95)],
                "boundary": [(72, 73), 89],
                "priority_conflict": [(25, 26), (39, 42)],
                "arithmetic": [(14, 15), 18, (23, 24), 38, 39, 43, (56, 57), (84, 85)],
                "implicit": [(21, 23)],
            }
        )
        for t, tick in enumerate(ticks):
            tick.tags = tags[t]
            tick.note = notes.get(t, "")
        return ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            return self._minimal(ticks)
        if variant == "structural_cf":
            return self._structural(ticks)
        return ticks

    def _minimal(self, ticks: list[Tick]) -> list[Tick]:
        out = ticks

        def line_surface(line: tuple[str, str] | None):
            return (lambda tk, i: {**tk.surface, "floor": line[0], "gist": line[1]}) if line else None

        # (1) t3-5: OB-3's sensor starts failing at 06:30 instead of 07:00, so the
        #     jumps call for marking it faulty half an hour earlier.
        series = copy.deepcopy(B_SERIES)
        series["OB"][3:6] = [3, 710, 2]
        for t in range(3, 7):
            out = override(out, [t], levels=b_levels(series, t))
        for t in range(3, 6):
            out[t].note = "OB-3 already jumping from 06:30 and never labelled faulty: mark it faulty."
        # (2) t18-20: Low Meadows keeps rising instead of easing off while the
        #     heads-up is still unacknowledged, so the heads-up is repeated until
        #     the 09:25 acknowledgement shows.
        series["LM"][18:21] = [168, 169, 170]
        lines = {
            18: ("Low Meadows observer: 'Fourth step of the slipway now.'", "the Low Meadows observer says the water is at the fourth step"),
            22: ("Depot rain gauge: 58 mm since midnight.", "rain since midnight has reached 58 mm"),
        }
        for t in range(18, 23):
            out = override(out, [t], surface=line_surface(lines.get(t)), levels=b_levels(series, t))
        for t in range(18, 21):
            out[t].note = "Low Meadows still rising within 0.20 m of its watch level and the heads-up is unacknowledged: heads-up again."
        # (3) t85-87 and t89-91: Mill Quarter lingers just above its watch level
        #     until 20:30, and the advisories are only cleared at 21:15.
        series["MQ"][85:93] = [212, 211, 211, 206, 201, 197, 193, 189]
        events = {**B_EVENTS, "cleared": 1275}
        lines = {
            89: ("Mill Quarter observer: 'Mill Street gutters finally draining.'", "the Mill Quarter observer says the Mill Street gutters are finally draining"),
            90: ("St Anne's evacuees packing up their bags.", "evacuees at the rest centre are packing their bags"),
            91: ("Osei drafts the stand-down message for the advisories.", "the on-call officer drafts the stand-down message for the notices"),
        }
        for t in range(85, 100):
            clock = B_START + B_TICK * t
            out = override(
                out,
                [t],
                surface=line_surface(lines.get(t)),
                levels=b_levels(series, t),
                advisories=b_desk(clock, events)["advisories"],
            )
        for t in range(85, 88):
            out[t].note = "Mill Quarter still at or above 2.10 m until 20:30: a warning is still required and nothing is cleared yet."
            if "arithmetic" not in out[t].tags:
                out[t].tags.append("arithmetic")
        for t in range(89, 92):
            out[t].note = "Every gauge below its watch level but the advisories are only cleared at 21:15: clear again every report."
        out = tidy_counterfactual(self, ticks, out, "")
        out[6].note = "OB-3 jumps 0.02 -> 6.93 m and is still unflagged: mark it faulty (rule 1 has matched since 06:30). Its 6.93 m is above OB's evacuation level, but a jumping gauge is not in use."
        out[21].note = "Low Meadows still rising and within 0.20 m of its watch level, but Brandt's reply at 09:25 acknowledges the heads-up: keep."
        out[88].note = "Mill Quarter 2.06 m, the last gauge to fall below its watch level: clear all advisories."
        out[92].note = "Advisories cleared at 21:15: back to monitoring."
        return out

    def _structural(self, ticks: list[Tick]) -> list[Tick]:
        # A temporary levee repair lowers Low Meadows' evacuation level to 2.30 m.
        # Low Meadows reaches it at 10:30: the evacuation advisory (issued 10:55)
        # comes before the sandbag request, which moves to 11:25.
        thresholds = copy.deepcopy(B_THRESHOLDS)
        thresholds["LM"]["evac"] = B_LM_EVAC_REPAIR
        events = {**B_EVENTS, "evac_lm": 655, "sandbags_lm": 685}
        lines = {
            30: ("Police start door-knocking along Riverside Walk.", "police start door-knocking along Riverside Walk"),
            32: ("Low Meadows residents registering at the community hall.", "Low Meadows residents are registering at the community hall"),
            34: ("Community hall: tea urn on; 40 Low Meadows residents signed in.", "the community hall has its tea urn on and forty Low Meadows residents signed in"),
            # The sandbags are only requested at 11:25 here, so the crew is still
            # unloading at 11:50 rather than finishing a 60-metre wall.
            35: ("Sandbag crew unloading at Riverside Walk; volunteers form a chain.", "the sandbag crew is unloading at Riverside Walk while volunteers form a chain"),
        }
        # Callers can no longer ask whether Low Meadows should be evacuated.
        busy = {
            31: [
                ("Riverside Walk caller asks where she can take her dog during the evacuation.", "a Riverside Walk caller asks where she can take her dog during the evacuation"),
                B_BUSY[31][1],
            ],
            33: [
                ("Low Meadows resident: 'Do we need to bring our medicines with us?'", "a Low Meadows resident asks whether to bring medicines along"),
                B_BUSY[33][1],
            ],
            34: [
                ("County planner asks how many Low Meadows households have left so far.", "the county planner asks how many Low Meadows households have left so far"),
                B_BUSY[34][1],
            ],
        }
        out = []
        for t, tk in enumerate(ticks):
            tk = copy.deepcopy(tk)
            clock = B_START + B_TICK * t
            tk.latent.update(thresholds=copy.deepcopy(thresholds), **b_desk(clock, events))
            if t in lines:
                tk.surface = {**tk.surface, "floor": lines[t][0], "gist": lines[t][1]}
            if t in busy:
                tk.surface = {**tk.surface, "busy": busy[t]}
            out.append(tk)
        out = tidy_counterfactual(self, ticks, out, "Levee repair: Low Meadows evacuation level is 2.30 m, so Low Meadows qualifies for evacuation before sandbags.")
        for t in range(30, 33):
            out[t].note = "Low Meadows evacuation advisory in force since 10:55; Low Meadows still rising above its sandbag level with no request: sandbags."
        out[33].note = "Sandbags for Low Meadows requested 11:25: keep monitoring (warning still required)."
        return out

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        levels, th = z["levels"], z["thresholds"]
        downstream = list(reversed(B_ZONES))
        flagged = set(z["flags"])
        jumping = {k for k in B_ZONES if abs(levels[k][1] - levels[k][0]) > 50}
        in_use = [k for k in downstream if k not in flagged and k not in jumping]
        cur = {k: levels[k][1] for k in B_ZONES}
        rising = {k: levels[k][1] > levels[k][0] for k in B_ZONES}
        adv = z["advisories"]
        live = adv["cleared"] is None
        watch_on = live and adv["watch"] is not None
        evac_on = set(adv["evac"]) if live else set()
        acked = {k for k, h in z["headsup"].items() if h["acknowledged"]}
        warning = any(cur[k] >= th[k]["watch"] for k in in_use)

        def first(cond):
            return next((k for k in downstream if cond(k)), None)

        zone = first(lambda k: k not in flagged and k in jumping)
        if zone:
            action, target = "faulty", zone
        elif (zone := first(lambda k: k in in_use and cur[k] >= th[k]["evac"] and k not in evac_on)):
            action, target = "evac", zone
        elif not watch_on and any(cur[k] >= th[k]["watch"] for k in in_use):
            action, target = "watch", "all"
        elif (zone := first(lambda k: k in in_use and cur[k] >= th[k]["sandbag"] and rising[k] and k not in z["sandbags"])):
            action, target = "sandbags", zone
        elif not watch_on and (zone := first(lambda k: k in in_use and rising[k] and 0 < th[k]["watch"] - cur[k] < 20 and k not in acked)):
            action, target = "notify", zone
        elif (watch_on or evac_on) and all(cur[k] < th[k]["watch"] for k in in_use):
            action, target = "clear", "all"
        else:
            action, target = "keep", "none"
        return {"action": action, "zone": target, "public_warning": warning}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "A rainy day on the River Mere. The Old Bridge gauge fails with impossible jumps (mark faulty until the flag shows at 07:35, then ignore its 7 m readings). Low Meadows creeps within 0.20 m of its watch level (heads-up while it rises; the heads-up stays unacknowledged while Low Meadows eases off for three reports, and Brandt's quoted reply at 09:25 is the only sign of the acknowledgement when it rises again), crosses it (town-wide flood watch, which outranks a Mill Quarter heads-up and Low Meadows sandbags), then sandbags for Low Meadows. A debris surge takes Mill Quarter from 2.49 to 2.93 m (0.44 m: in use; evacuation outranks sandbags); after the evacuation advisory Mill Quarter and Weir Lane both qualify for sandbags and the downstream tie-break picks Mill Quarter. A long fall ends when Mill Quarter drops below 2.10 m and every advisory is cleared. Desk reaction times vary (25-55 minutes), so segments run 3-5 reports. Distractors: another river's warning, a caller saying the river looks normal and the unflagged gauge's 7.41 m reading while it still needs marking faulty, the flagged gauge's 7 m readings, surface water on Weir Lane, a 0.38 m rise at Weir Lane, Weir Lane asking for sandbags during the tie-break, Mill Quarter dropping below its evacuation level, the rain stopping. Hold-under-activity ticks carry two or three simultaneous incoming messages."},
            "paraphrase": {"summary": "Same latent trajectory; flood room / board marks in centimetres / unreliable tag / on-call officer / notice vocabulary, prose update with the marks in one sentence and the readings in another, reworded rules, options and zone labels."},
            "lexical_decoy": {"summary": "Same latent trajectory; each report adds three unrelated community notices, each borrowing one action's wording (faulty gauge, duty officer heads-up, public watch issued, clear the advisories, sandbag deployment, evacuation advisory, keep monitoring). The three actions are drawn per tick without looking at gold."},
            "minimal_cf": {"summary": "Three edits: t3-5 OB-3's sensor starts failing at 06:30 instead of 07:00 (keep -> mark faulty); t18-20 Low Meadows keeps rising instead of easing off while the heads-up is unacknowledged (keep -> heads-up); t85-91 Mill Quarter lingers at 2.11-2.12 m until 20:30 and the advisories are cleared at 21:15 (clear shifts three reports later: t85-87 keep with a warning, t89-91 clear)."},
            "structural_cf": {"summary": "A temporary levee repair lowers Low Meadows' evacuation level to 2.30 m. Low Meadows reaches it at 10:30 (2.36 m), so an evacuation advisory for Low Meadows replaces the sandbag request at t27-29 and the sandbag request follows at t30-32. The incoming lines at t30-35 follow the evacuation and the later sandbag request (door-knocking, residents registering, the sandbag crew still unloading at 11:50)."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _desk_text(self, z: dict[str, Any]) -> str:
        th = z["thresholds"]
        parts = []
        for k in B_ZONES:
            line = f"{B_NAMES[k]} {m(th[k]['watch'])} / {m(th[k]['sandbag'])} / {m(th[k]['evac'])}"
            if th[k]["evac"] != B_THRESHOLDS[k]["evac"]:
                line += f" (evacuation level lowered from {m(B_THRESHOLDS[k]['evac'])} while the east levee is under temporary repair)"
            parts.append(line)
        return (
            "Kessling flood desk, River Mere. Riverside zones in order from upstream to downstream, with their levels "
            "in gauge metres (watch / sandbag / evacuation): " + "; ".join(parts) + "."
        )

    def _gauge_lines(self, z: dict[str, Any], t: int) -> list[str]:
        prev_time = hhmm(z["clock"] - B_TICK)
        fmt = pick(
            [
                "{name} {gid}: {cur} m ({pt}: {prev} m)",
                "{gid} {name}: {cur} m now, {prev} m at {pt}",
                "{name} ({gid}) {cur} m; ten minutes earlier {prev} m",
            ],
            "b-gfmt",
            t,
        )
        lines = []
        for k in B_ZONES:
            prev, cur = z["levels"][k]
            line = fmt.format(name=B_NAMES[k], gid=B_GAUGES[k], cur=m(cur), prev=m(prev), pt=prev_time)
            if k in z["flags"]:
                line += " [flagged faulty]"
            lines.append(line)
        return lines

    def _flags_text(self, z: dict[str, Any], t: int) -> str:
        f = z["flags"].get("OB")
        if f is not None:
            return pick(
                [
                    "OB-3 (Old Bridge) flagged faulty at {x}; its readings are ignored. No other gauge is flagged.",
                    "Old Bridge gauge OB-3 flagged faulty since {x}; the other three gauges are not flagged.",
                ],
                "b-fl1",
                t,
            ).format(x=hhmm(f["since"]))
        if "OB" not in z["repairs"]:
            return pick(["No gauge is flagged faulty.", "Gauge flags: none."], "b-fl0", t)
        return pick(
            [
                "No gauge is flagged faulty. The OB-3 flag was lifted at {y} after the sensor was replaced.",
                "Gauge flags: none (OB-3 flag lifted {y}, new sensor fitted).",
            ],
            "b-fl2",
            t,
        ).format(y=hhmm(z["repairs"]["OB"]))

    def _advisory_text(self, z: dict[str, Any], t: int) -> str:
        adv = z["advisories"]
        evac = adv["evac"]
        if adv["cleared"] is not None:
            what = ["the flood watch"] + [f"the {B_NAMES[k]} evacuation advisory" for k in B_ZONES if k in evac]
            return f"No public advisory in force. {listing(what)[0].upper() + listing(what)[1:]} were cleared at {hhmm(adv['cleared'])}."
        if adv["watch"] is None:
            return pick(["No public advisory in force.", "Public advisories: none in force."], "b-adv0", t)
        text = pick(
            ["Flood watch for the whole town in force since {w}.", "Town-wide flood watch in force (issued {w})."],
            "b-advw",
            t,
        ).format(w=hhmm(adv["watch"]))
        if evac:
            items = [f"{B_NAMES[k]} since {hhmm(evac[k])}" for k in B_ZONES if k in evac]
            text += " Evacuation advisory in force: " + "; ".join(items) + "."
            text += pick([" No other zone has one.", " None for the other zones."], "b-adve1", t)
        else:
            text += pick([" No evacuation advisory.", " No zone is under an evacuation advisory."], "b-adve", t)
        return text

    def _sandbag_text(self, z: dict[str, Any], t: int) -> str:
        sb = z["sandbags"]
        if not sb:
            return pick(["No sandbags requested.", "Sandbag requests: none."], "b-sb0", t)
        items = [f"{B_NAMES[k]} ({hhmm(sb[k])})" for k in B_ZONES if k in sb]
        return pick(
            ["Sandbags requested for {x}; none for other zones.", "Sandbag requests on file: {x}. No other zone has one."],
            "b-sb1",
            t,
        ).format(x=listing(items))

    def _officer_text(self, z: dict[str, Any], t: int) -> str:
        off = z["officer"]
        who = off["name"] + " on duty" if "since" not in off else f"{off['name']} on duty since {hhmm(off['since'])} (took over from {off['previous']})"
        h = z["headsup"].get("LM")
        if h is None:
            return f"{who}. No heads-up sent today."
        sent = hhmm(h["sent"])
        others = pick(
            [" No heads-up for any other zone.", " No other zone has had a heads-up."], "b-hu-other", t
        )
        if not h["acknowledged"]:
            # Rotated by tick rather than drawn, so that every wording lands on
            # heads-up ticks and on keep-monitoring ticks alike.
            return f"{who}. " + cycle(
                [
                    "Heads-up for Low Meadows sent {s}; not acknowledged yet.",
                    "Heads-up for Low Meadows went out at {s}; no reply from S. Brandt so far.",
                    "The {s} heads-up for Low Meadows is still unacknowledged.",
                ],
                t,
            ).format(s=sent) + others
        reply = "S. Brandt answered the Low Meadows heads-up (sent {s}) at {a}: 'Seen it, keep me posted.'"
        options = [
            "Heads-up for Low Meadows (sent {s}) has been acknowledged.",
            "Heads-up for Low Meadows sent {s}, acknowledged at {a}.",
            reply,
        ]
        text = reply if t in B_IMPLICIT_ACK else pick(options, "b-hu1", t)
        return f"{who}. " + text.format(s=sent, a=hhmm(h["ack_at"])) + others

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z, t = tick.latent, len(history) - 1
        state: dict[str, Any] = {
            "flood_desk": self._desk_text(z),
            "time": hhmm(z["clock"]),
            "gauges": self._gauge_lines(z, t),
            "gauge_flags": self._flags_text(z, t),
            "public_advisories": self._advisory_text(z, t),
            "sandbag_requests": self._sandbag_text(z, t),
            "duty_officer": self._officer_text(z, t),
            "incoming": moment_lines(tick.surface),
        }
        if variant == "lexical_decoy":
            targets = decoy_targets(list(B_ACTIONS), "b-decoy-target", t, 3)
            state["community_board"] = [pick(B_DECOYS[a], "b-decoy", a, t) for a in targets]
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z, t = tick.latent, len(history) - 1
        th = z["thresholds"]
        parts = [pick(["Kessling flood room, update at {n}.", "Flood room update, {n}.", "{n}: Kessling flood room update."], "bp-head", t).format(n=hhmm(z["clock"]))]
        marks = []
        for k in B_ZONES:
            owner = B_NAMES[k] + ("'" if B_NAMES[k].endswith("s") else "'s")
            item = f"{owner} at {th[k]['watch']}, {th[k]['sandbag']} and {th[k]['evac']}"
            if th[k]["evac"] != B_THRESHOLDS[k]["evac"]:
                item += f" (its evacuation mark cut from {B_THRESHOLDS[k]['evac']} while the east levee is being patched)"
            marks.append(item)
        parts.append(
            "The Mere passes Weir Lane first, then Mill Quarter, then Old Bridge, and Low Meadows last. "
            "Each zone's board is marked in centimetres for flood watch, sandbags and evacuation, in that order: "
            + "; ".join(marks) + "."
        )
        readings = []
        for k in B_ZONES:
            prev, cur = z["levels"][k]
            readings.append(
                pick(
                    ["{name} {cur} cm (ten minutes ago {prev})", "{name} {cur} cm, against {prev} ten minutes back"],
                    "bp-zone",
                    t,
                ).format(name=B_NAMES[k], cur=cur, prev=prev)
            )
        parts.append(pick(["Gauges now read: {x}.", "The newest gauge readings are {x}."], "bp-read", t).format(x="; ".join(readings)))
        f = z["flags"].get("OB")
        if f is not None:
            parts.append(f"The Old Bridge gauge has been tagged unreliable since {hhmm(f['since'])}; no other gauge carries that tag.")
        elif "OB" in z["repairs"]:
            parts.append(f"No gauge is tagged unreliable; the Old Bridge tag was removed at {hhmm(z['repairs']['OB'])} once its sensor was swapped.")
        else:
            parts.append("No gauge is tagged unreliable.")
        adv = z["advisories"]
        if adv["cleared"] is not None:
            parts.append(f"No public notice is live; every notice was withdrawn at {hhmm(adv['cleared'])}.")
        elif adv["watch"] is None:
            parts.append("No public notice is live.")
        else:
            text = f"The town-wide flood-watch notice has been live since {hhmm(adv['watch'])}"
            if adv["evac"]:
                live = listing([f"{B_NAMES[k]} (from {hhmm(adv['evac'][k])})" for k in B_ZONES if k in adv["evac"]])
                text += ("; an evacuation notice is live for " if len(adv["evac"]) == 1 else "; evacuation notices are live for ") + live
                text += " and for no other zone."
            else:
                text += ", and no evacuation notice is live."
            parts.append(text)
        sb = z["sandbags"]
        if sb:
            parts.append(
                "Sandbags have been ordered for "
                + listing([f"{B_NAMES[k]} at {hhmm(sb[k])}" for k in B_ZONES if k in sb])
                + ", and for no other zone."
            )
        else:
            parts.append("Nobody has ordered sandbags.")
        off = z["officer"]
        who = f"The on-call officer is {off['name']}" + (f", who took over at {hhmm(off['since'])}" if "since" in off else "")
        h = z["headsup"].get("LM")
        others = pick(
            ["No early notice has gone out about any other zone.", "No other zone has had an early notice today."], "bp-hu-other", t
        )
        if h is None:
            parts.append(f"{who}; no early notice has gone out today.")
        elif not h["acknowledged"]:
            parts.append(
                cycle(
                    [
                        "{w}; an early notice about Low Meadows went out at {s} and has not been confirmed.",
                        "{w}; the early notice about Low Meadows sent at {s} is still unanswered.",
                    ],
                    t,
                ).format(w=who, s=hhmm(h["sent"]))
            )
        else:
            reply = "{w}; S. Brandt wrote back at {a} about the {s} Low Meadows early notice: 'Seen it, keep me posted.'"
            text = reply if t in B_IMPLICIT_ACK else pick(
                ["{w}; the Low Meadows early notice sent at {s} has been confirmed.", reply], "bp-hu1", t
            )
            parts.append(text.format(w=who, s=hhmm(h["sent"]), a=hhmm(h["ack_at"])))
        if h is not None:
            parts.append(others)
        parts.append(pick(["Also: {g}.", "Other news: {g}."], "bp-gist", t).format(g=moment_gist(tick.surface)))
        return " ".join(parts)


SCENARIOS = [ColdStoreChiller, RiverFloodDesk]
