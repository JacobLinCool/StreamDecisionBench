# Assembly station tasks

Two independent workflows provide 60 observations each, released every two seconds over a 120-second horizon. The decision is a station display: the current procedure stage plus the instruction, target, remedy, or recipient needed by its selected route. These are synthetic work instructions with explicit acceptance rules. They do not evaluate physical execution or claim to encode general manufacturing practice.

The gearbox-cover scenario uses housing and cover scans, camera observations of a gasket, torque measurements, fastener replacement records, inspection results, quality tickets, and specialist badges. The cable-module scenario uses connector scans, fixture orientation, crimp-height measurements, electrical meter readings, serial labels, and accessory counts. The second workflow additionally requires downstream electrical and packaging evidence to be refreshed after rework; it is not a parameter variation of the first workflow.

## Inputs and reference decisions

Each public state includes an order, station identity, release clock, work instruction, and cumulative device log. Work instructions state target acceptance ranges, dependencies, evidence-reset conditions, stage order, and route precedence. The model receives structured tool records as they would be available to the application. No input names the correct route, computes a fault count, marks a step complete, or supplies an interpreted decision summary.

The reference function uses only this public state. It first discards records for other units or stations, low-confidence camera observations, and unreadable scans. It derives the current stage from the latest relevant productive record and derives completion, defects, and evidence freshness from the log. Every input record is released at its recorded tick; each reference decision is held until the next release. The two-second tick defines evidence availability, while model answers can become effective between ticks.

Route precedence is: open quality ticket, present specialist, repeated tool failure, known defect or skipped earlier requirement, completed unit, completed current stage, otherwise wait. Each open quality ticket must be closed separately. A fresh passing measurement withdraws repeated-failure escalation; replacing a fastener or terminal clears its previous measurements. Limits include their endpoints. Speech, heartbeats, other units, and low-confidence observations can add activity without changing the decision.

## Questions and application composition

All six questions read the same public state independently. A question never consumes another generated answer. The application uses `route` to select which answers are relevant after one response is accepted.

| Question | Application role |
|---|---|
| `route` | Instruction class and branch selector |
| `stage` | Always-displayed current procedure stage |
| `target` | Defective, missing, or repeatedly failing component |
| `method` | Corrective method for the selected defect |
| `next_step` | First incomplete procedure stage |
| `destination` | Specialist, quality desk, or completed-unit destination |

| Route | Additional active questions beyond route and stage |
|---|---|
| wait | None |
| advance | next_step |
| repair | target, method |
| escalate | target, destination |
| handoff | destination |
| hold | destination |
| release | destination |

The reference supplies valid answers to every question, using `none` where appropriate. An error in an inactive branch does not change the application decision. Selecting an incorrect route is still an error. The published criteria use semantic names in source; the shared builder may encode these as opaque option labels for model requests.

## Scenario A: gearbox cover

The order requires a right-hand housing and cover. J1 accepts 9.2–10.8 Nm and J2 accepts 22.0–26.0 Nm. A wrong cover is replaced, one joint is first under-tightened and then over-tightened, and two failed measurements trigger a lead request. A badge confirms the handoff; two overlapping quality tickets take priority, and closing only one keeps the hold active. After replacement and a passing measurement, the lead leaves and fresh inspection is required. Later, a reliable missing-gasket observation reverses a released decision, while a low-confidence version does not. A separate J1 rework demonstrates the upper endpoint, replacement reset, and inspection failure recovery.

| Tick | New public evidence | Expected decision consequence |
|---:|---|---|
| 4 | Cover scan disagrees with order | Repair cover by replacement |
| 10 | J2 measures 21.8 Nm | Repair J2 by retorquing |
| 16 | J2 measures 26.4 Nm after its earlier failure | Escalate J2 to mechanical lead |
| 19 | Lead badges in | Handoff replaces escalation |
| 21–24 | Two tickets open; only the first closes | Quality hold remains active |
| 25 | Second ticket closes | Resume handoff |
| 27–31 | Screw replacement, 26.0 Nm, then lead badge-out | Advance to fresh inspection |
| 35 / 37 | Low / high confidence reports of an absent gasket | Hold prior decision / require repair |
| 45–53 | J1 over-limit, replacement, 10.8 Nm, failed then passing inspection | Repair, wait, advance, reinspect, release |

## Scenario B: cable module

The order requires connector CN-7 seated south-facing, P1 height 1.7–1.9 mm, P2 height 2.1–2.3 mm, continuity at most 0.4 ohm, insulation at least 20 megaohm, the exact serial label, and two accessories. An orientation error precedes repeated P2 crimp failures and a quality hold. After specialist rework, electrical evidence and packaging complete the unit. A subsequent P1 rework makes the older electrical tests obsolete; scanning the correct label cannot repair that missing evidence. Once fresh electrical checks pass, the label and accessory checks must also be refreshed. The order sends completed units to a validation rack, which differs from the gearbox outbound lane.

| Tick | New public evidence | Expected decision consequence |
|---:|---|---|
| 2 / 4 | North-facing / south-facing fixture record | Reseat / advance |
| 8 / 10 | P2 height 2.05 / 2.35 mm | Recrimp / escalate |
| 12–16 | Ticket opens, lead arrives, ticket closes | Hold remains until closure, then handoff |
| 24 / 28 | Continuity 0.5 / 0.4 ohm | Trace connection / advance after valid insulation |
| 30–36 | Wrong serial label, corrected label, one accessory, then two | Repair label, wait, adjust kit, release |
| 38 / 40 | New P1 crimp, then label scan | Advance to electrical / repair missing continuity evidence |
| 44 / 46 | Insulation 19.9 / 20 megaohm | Replace cable instruction / advance to packaging |
| 48 / 50 | Fresh correct label / fresh count | Wait / release to validation rack |
| 58 / 59 | Quality ticket opens / closes | Hold / withdraw hold |

## Verification and interpretation

Targeted tests cover independent ticket closure, precedence conflicts, exact numeric endpoints, replacement resets, current-versus-obsolete test records, ignored distractors, and counterfactual changes to the public order or a single measurement. The reference can be recomputed without any hidden annotation. The task source and tests do not assert a model score or tune examples to a desired accuracy.

The two scenarios are development examples for the first SDB recording. Their automatic labels implement the published synthetic rules; passing programmatic checks does not establish deployment validity or replace future independent scenario evaluation. Device logs follow a fixed open-loop stream, so displayed recommendations do not alter subsequent events.
