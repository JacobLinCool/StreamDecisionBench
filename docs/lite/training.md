# Training split

`data/lite/train-v1/` (dataset hash `50d2ee35…`, 8 scenarios, 480 states) holds further scenarios of the four task families for training decision
components. They are **never part of an evaluation score**: the benchmark remains the eight
scenarios of `data/lite/v1/` (dataset hash `fdfdd55d…`), whose files and hashes this split does not
change.

| Family | Evaluation (`data/lite/v1`) | Training (`data/lite/train-v1`) |
|---|---|---|
| `live_debugging` | `lite_debugging_a`, `lite_debugging_b` | `train_debugging_c`, `train_debugging_d` |
| `procedural_coaching` | `lite_assembly_a`, `lite_assembly_b` | `train_assembly_c`, `train_assembly_d` |
| `support_call_assist` | `lite_support_a`, `lite_support_b` | `train_support_c`, `train_support_d` |
| `presenter_voice_control` | `lite_presenter_a`, `lite_presenter_b` | `train_presenter_c`, `train_presenter_d` |

Each training scenario has the evaluation format: 60 ticks of 2 s, choice questions with opaque
labels, a `decision_spec`, and reference answers computed by an executable function of the public
state alone. The files load with `load_dataset` and run with the same commands, for example
`uv run python -m streamdecisionbench.lite run --data data/lite/train-v1 ...`.

```bash
uv run python -m streamdecisionbench.lite build --split train --data <empty dir>   # rebuild the split
uv run python -m streamdecisionbench.lite.training check                            # validate and audit every module
uv run pytest -q tests/test_lite_training*.py
```

## Separation from evaluation

Training scenarios share neither instance content nor, with one declared exception, specification
with evaluation. Both the build and the tests run the two audits in
`streamdecisionbench.lite.training.audit`.

**Content (`leakage`).** Outside the `rules`/`policy` fields and question instructions, a training
state may not repeat an evaluation state, an evaluation string of four or more words, any six-word
run of evaluation text, or an evaluation identifier (paths, file names, `@teams`, codes containing
digits, codes such as `ST-A`). Positional record ids such as `u12-Customer` and test-runner summary
lines are exempt. Projects, people, organisations, files, tests, decks, orders, codes, utterances and
story beats are all new; the reviews also compared story beats, which the audit cannot see.

**Specification (`spec_overlap`, `layout_overlap`).** Each variant writes its own rule text,
questions and state layout and is a different design within its family's application type: no
evaluation rule paragraph, question instruction or option set; no ten-word run of evaluation rules or
instructions; a different set of question ids; and a state layout whose key paths have a Jaccard
similarity of at most 0.5 with every evaluation scenario of the family. The exception is
`SHARED_SPEC`: the two assembly variants define new workflows (stages, targets, ranges, methods and
workflow rules) but keep the family's six common station rules and its question ids and instructions.

| Variant | Own rules | Own questions | State layout overlap with evaluation |
|---|---|---|---:|
| `train_debugging_c` | 13 new paragraphs | `card`, `ci_badge`, `review_badge`, `job`, `test`, `reviewer`, `file`, `approver` | 0.00 |
| `train_debugging_d` | 14 new paragraphs | `next_action`, `kernel_badge`, `freshness_badge`, `cell`, `table`, `owner_team` | 0.00 |
| `train_assembly_c` | 12 paragraphs: 6 shared common station rules + 6 new workflow rules | `route`, `stage`, `target`, `method`, `next_step`, `destination`: the family's ids and instructions, new option sets except `route` | 0.67 |
| `train_assembly_d` | 12 paragraphs: 6 shared common station rules + 6 new workflow rules | `route`, `stage`, `target`, `method`, `next_step`, `destination`: the family's ids and instructions, new option sets except `route` | 0.67 |
| `train_support_c` | 10 new paragraphs | `route`, `recorder`, `segment`, `rebook_action`, `refund_action`, `bag`, `bag_action` (the ids `recorder` and `route` also occur in evaluation, with new instructions and options) | 0.24 |
| `train_support_d` | 10 new paragraphs | `route`, `priority_register`, `meter_target`, `meter_action`, `plan_stage`, `instalments`, `outage_site`, `outage_action` (the id `route` also occurs in evaluation, with new instructions and options) | 0.32 |
| `train_presenter_c` | 12 new paragraphs | `stage_mode`, `projected_slide`, `recording_light`, `timer_cue`, `pointer`, `media_state`, `poll_panel` | 0.02 |
| `train_presenter_d` | 12 new paragraphs | `scene`, `stop`, `caption_source`, `guide_prompt`, `screen_warmup`, `film_audio`, `question_queue`, `held_scene` | 0.00 |

## Verification

Every variant was checked like the evaluation scenarios (see `paper/notes/audit_summary.md`), by LLM
agents rather than human validation:

- **Executable reference.** The stored answers equal `reference(state)` at every tick; the reference is
  pure and reads no tick index or hidden field; every answer is a declared option.
- **Blind re-derivation.** An agent that never read the module or the family's reference code wrote
  an independent program from the public rule text and question instructions alone and compared it
  with the stored answers at all 60 ticks, then hand-walked every decision change.
- **Adversarial review.** A second agent checked the reference line by line against the rule text,
  the family's state conventions (for example the streaming-ASR transcript conventions), causality,
  coverage and leakage.
- Findings were fixed and both checks repeated until no blocking or major finding remained.

| Variant | Fix rounds | Blocking or major findings fixed | Final blind re-derivation | Final review |
|---|---:|---|---|---|
| `train_debugging_c` | 2 | 2 major (a person's name from evaluation; a question id from evaluation) | 60/60 ticks, all fields | clean |
| `train_debugging_d` | 2 | 1 blocking, 4 major (an option description contradicting its rule; a timer beat mirroring evaluation; an impossible notebook beat; rules never decisive) | 60/60 ticks, all fields | clean |
| `train_assembly_c` | 2 | 3 blocking, 2 major (story beats copied from the evaluation gearbox story; after re-plotting, a repair at a stage later than the current one and an unstated tick-0 stage) | 60/60 ticks, all fields | clean |
| `train_assembly_d` | 2 | 1 blocking, 1 major (beat sequence copied from the evaluation scenarios; after re-plotting, a firmware defect repaired while the stage was back at weld) | 60/60 ticks, all fields | clean |
| `train_support_c` | 1 | 1 blocking (case of the capture phrase unstated) | 60/60 ticks, all fields | clean |
| `train_support_d` | 1 | 1 major (the meter target never left its default) | 60/60 ticks, all fields | clean |
| `train_presenter_c` | 2 | 3 major (an early-pause rule and story beat mirroring evaluation; a question id from evaluation) | 60/60 ticks, all fields | clean |
| `train_presenter_d` | 1 | 3 major (input conventions paraphrasing the evaluation rules; evaluation distractor beats; rules never decisive) | 60/60 ticks, all fields | clean |

The debugging and presenter variants were first written on their family's published rules and then
rewritten with their own specification; the table shows the rewrite. The reviews also compared what
the audits cannot see: four first drafts followed evaluation story beats with new nouns, and in the
rewrite round reviewers rejected rule text that paraphrased evaluation conventions with renamed
fields, reused question ids and a reused person's name; all were reworked. After the last review,
small wording edits to six modules (settling a tie, removing a contradiction, restructuring two
convention paragraphs, rewording phrases that shared ten words with evaluation rules) were checked by
a separate agent against the references. Remaining minor notes concern story realism and coverage,
not reference answers; for example, two overlapping quality tickets never occur in
`train_assembly_d`.

## Variants

| Episode | Family | Rules | Transitions | Routes reached |
|---|---|---|---:|---|
| `train_debugging_c` | `live_debugging` | own rules (pre-merge CI) | 31 | address_review, fix_build, fix_lint, investigate_test, merge, request_review, retry_flaky, unblock_queue, wait_ci |
| `train_debugging_d` | `live_debugging` | own rules (data notebook) | 31 | ask_data_owner, fix_cell, interrupt_kernel, refresh_table, restart_kernel, run_cell, share_results, wait |
| `train_assembly_c` | `procedural_coaching` | new workflow `pump_cartridge` | 23 | advance, escalate, handoff, hold, release, repair, wait |
| `train_assembly_d` | `procedural_coaching` | new workflow `battery_pack` | 25 | advance, escalate, handoff, hold, release, repair, wait |
| `train_support_c` | `support_call_assist` | new workflow `travel_change` | 22 | baggage, closed, hold_return, hold_wait, rebook, refund |
| `train_support_d` | `support_call_assist` | new workflow `energy_account` | 31 | closed, hold_return, hold_wait, meter, outage, plan |
| `train_presenter_c` | `presenter_voice_control` | own rules (wake-word console) | 30 | break, ended, lecture, media, poll |
| `train_presenter_d` | `presenter_voice_control` | own rules (gallery tour) | 35 | at_stop, film, finished, paused, questions |

### `train_debugging_c`: Pre-merge CI and approval watch for a stock-hold pull request

A pre-merge CI and review assistant for a pull request of a Go stock-hold service. The state holds the pull request, its commits, CI job attempts by stage and commit, reviews, path-based approval rules and chat; the card has nine routes, with CI and review badges and job, test, reviewer, file and approver fields. Only head-commit attempts are current, the earliest failing stage decides, a test is flaky only when a later attempt of the same job on the same commit passed, retries stop at a published limit, a queued job reaching the queue limit needs a runner, change requests persist across commits, older approvals are stale, and the approval rule with the longest matching pattern governs a file. Story: a slower lint failure overtaking a unit failure, a queue at exactly its limit, flaky retries up to the cap, a test wrongly called flaky in chat, bots claiming success, and approvers asked in turn until merge.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0 | **wait_ci**; ci_badge=pending, review_badge=none |
| 1 | **investigate_test**; ci_badge=red, review_badge=none, job=unit-reserve, test=TestRenewExtendsFromNow |
| 2–3 | **fix_lint**; ci_badge=red, review_badge=none, job=lint |
| 4–5 | **fix_lint**; ci_badge=red, review_badge=changes_requested, job=lint |
| 6 | **address_review**; ci_badge=stale, review_badge=changes_requested, reviewer=halvard |
| 7–9 | **address_review**; ci_badge=pending, review_badge=changes_requested, reviewer=halvard |
| 10–11 | **fix_build**; ci_badge=red, review_badge=changes_requested, job=build |
| 12 | **fix_build**; ci_badge=red, review_badge=approved, job=build |
| 13 | **wait_ci**; ci_badge=stale, review_badge=approval_stale |
| 14–18 | **wait_ci**; ci_badge=pending, review_badge=approval_stale |
| 19 | **unblock_queue**; ci_badge=pending, review_badge=approval_stale, job=unit-storage |
| 20 | **unblock_queue**; ci_badge=pending, review_badge=approval_stale, job=integration-kv |
| 21–22 | **wait_ci**; ci_badge=pending, review_badge=approval_stale |
| 23 | **retry_flaky**; ci_badge=red, review_badge=approval_stale, job=integration-kv, test=TestReserveRetriesOnConflict |
| 24–26 | **wait_ci**; ci_badge=pending, review_badge=approval_stale |
| 27–28 | **retry_flaky**; ci_badge=red, review_badge=approval_stale, job=integration-kv, test=TestReserveRetriesOnConflict |
| 29–31 | **wait_ci**; ci_badge=pending, review_badge=approval_stale |
| 32–34 | **investigate_test**; ci_badge=red, review_badge=approval_stale, job=integration-kv, test=TestReserveRetriesOnConflict |
| 35 | **wait_ci**; ci_badge=stale, review_badge=approval_stale |
| 36–37 | **wait_ci**; ci_badge=pending, review_badge=approval_stale |
| 38 | **investigate_test**; ci_badge=red, review_badge=approval_stale, job=integration-kv, test=TestReserveRetryCapHonoured |
| 39–40 | **investigate_test**; ci_badge=red, review_badge=approval_stale, job=unit-storage, test=TestTxnRetryBackoff |
| 41–42 | **investigate_test**; ci_badge=red, review_badge=changes_requested, job=unit-storage, test=TestTxnRetryBackoff |
| 43 | **address_review**; ci_badge=stale, review_badge=changes_requested, reviewer=ruth |
| 44–45 | **address_review**; ci_badge=pending, review_badge=changes_requested, reviewer=ruth |
| 46–47 | **address_review**; ci_badge=pending, review_badge=changes_requested, reviewer=wendell |
| 48–49 | **wait_ci**; ci_badge=pending, review_badge=approved |
| 50–51 | **request_review**; ci_badge=green, review_badge=approved, file=internal/reserve/hold.go, approver=halvard |
| 52–53 | **request_review**; ci_badge=green, review_badge=approved, file=internal/reserve/hold_test.go, approver=esme |
| 54–55 | **request_review**; ci_badge=green, review_badge=approved, file=cmd/stockhold/main.go, approver=ingrid |
| 56–57 | **request_review**; ci_badge=green, review_badge=approved, file=internal/reserve/sweep/sweep_test.go, approver=oskar |
| 58–59 | **merge**; ci_badge=green, review_badge=approved |

</details>

### `train_debugging_d`: North-shelf gust QC notebook: cell budgets, freshness and feed cover

A data-notebook debugging assistant for a buoy gust quality-control notebook. The state holds cells with dependencies, run-time budgets, edit and execution ticks, statuses and errors; the kernel's status, start and memory; data snapshots with feed cadences and owner teams; teams with away status and cover teams; and comments. The card has eight routes, with kernel and freshness badges and cell, table and owner-team fields. A cell's run-time budget (not a silence clock) decides interruption, results from an earlier kernel count as never run, a failure is fixed in the cell that raised it, the first runnable cell is gated by its whole upstream chain, memory at 90% of the limit restarts the kernel, a snapshot behind its source is refreshed, an overdue feed goes to its owner or to the cover of an away owner, and comments never change an answer.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 1–4 | **wait**; kernel_badge=overrun, freshness_badge=stale |
| 5–6 | **interrupt_kernel**; kernel_badge=overrun, freshness_badge=stale, cell=load_frames |
| 7–8 | **fix_cell**; kernel_badge=idle, freshness_badge=broken, cell=load_frames |
| 9 | **run_cell**; kernel_badge=idle, freshness_badge=broken, cell=load_frames |
| 10–12 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 13–15 | **fix_cell**; kernel_badge=idle, freshness_badge=broken, cell=helpers |
| 16–17 | **refresh_table**; kernel_badge=idle, freshness_badge=broken, table=marine.buoy_frames |
| 18 | **run_cell**; kernel_badge=idle, freshness_badge=broken, cell=load_frames |
| 19–21 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 22 | **run_cell**; kernel_badge=idle, freshness_badge=stale, cell=rollup |
| 23–24 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 25 | **run_cell**; kernel_badge=idle, freshness_badge=stale, cell=summary |
| 26 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 27–28 | **share_results**; kernel_badge=idle, freshness_badge=fresh |
| 29–30 | **wait**; kernel_badge=idle, freshness_badge=fresh |
| 31–32 | **restart_kernel**; kernel_badge=busy, freshness_badge=fresh |
| 33 | **restart_kernel**; kernel_badge=dead, freshness_badge=stale |
| 34 | **wait**; kernel_badge=restarting, freshness_badge=stale |
| 35–39 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 40–41 | **run_cell**; kernel_badge=idle, freshness_badge=broken, cell=unit_table |
| 42 | **wait**; kernel_badge=busy, freshness_badge=broken |
| 43 | **run_cell**; kernel_badge=idle, freshness_badge=broken, cell=helpers |
| 44–47 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 48–49 | **ask_data_owner**; kernel_badge=idle, freshness_badge=stale, table=marine.buoy_frames, owner_team=@marine-feeds |
| 50 | **ask_data_owner**; kernel_badge=idle, freshness_badge=stale, table=marine.buoy_frames, owner_team=@buoy-ingest |
| 51 | **run_cell**; kernel_badge=idle, freshness_badge=stale, cell=stations |
| 52 | **run_cell**; kernel_badge=idle, freshness_badge=stale, cell=unit_table |
| 53 | **refresh_table**; kernel_badge=idle, freshness_badge=stale, table=marine.buoy_frames |
| 54–56 | **wait**; kernel_badge=busy, freshness_badge=stale |
| 57 | **share_results**; kernel_badge=idle, freshness_badge=fresh |
| 58–59 | **ask_data_owner**; kernel_badge=idle, freshness_badge=stale, table=ops.sensor_calibration, owner_team=@buoy-ingest |

</details>

### `train_assembly_c`: Hydraulic cartridge HPC-2093 on the HYD-3 press cell

A hydraulic pump cartridge station: pump-body scan, press-fit forces at two bearings (low: repress; high: replace the bearing, which resets its readings), a camera check of the shaft-seal lip, a pressure-decay leak test that must be newer than every rework record and a flow test newer than the leak test. A wrong casting with a bearing pressed into it, NO_READ scans, a bearing escalated on two high forces and withdrawn by a passing press, two quality notifications closed in reverse order, the hydraulics lead badging in over a leak, a notification that outlasts her badge-out, another unit's reading, and after release a bearing recall swap whose rushed leak test skips the rear press (complete_missing) before a flipped seal lip and the final retests.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–1 | **repair**; stage=intake, target=body, method=swap_body |
| 2–4 | **repair**; stage=bearing, target=body, method=swap_body |
| 5–6 | **advance**; stage=intake, next_step=bearing |
| 7–8 | **repair**; stage=bearing, target=rear_bearing, method=repress |
| 9–11 | **wait**; stage=bearing |
| 12–13 | **repair**; stage=bearing, target=front_bearing, method=replace_bearing |
| 14–15 | **escalate**; stage=bearing, target=front_bearing, destination=hydraulics_lead |
| 16–17 | **advance**; stage=bearing, next_step=seal |
| 18–24 | **hold**; stage=bearing, destination=quality_desk |
| 25–26 | **advance**; stage=bearing, next_step=seal |
| 27–31 | **advance**; stage=seal, next_step=pressure |
| 32–33 | **repair**; stage=pressure, target=pressure_decay, method=locate_leak |
| 34–37 | **handoff**; stage=pressure, destination=hydraulics_lead |
| 38–40 | **hold**; stage=pressure, destination=quality_desk |
| 41–42 | **advance**; stage=pressure, next_step=functional |
| 43–44 | **repair**; stage=functional, target=flow, method=bleed_retest |
| 45–47 | **release**; stage=functional, destination=spares_crate |
| 48–49 | **wait**; stage=bearing |
| 50–51 | **repair**; stage=pressure, target=rear_bearing, method=complete_missing |
| 52–53 | **advance**; stage=bearing, next_step=pressure |
| 54–55 | **repair**; stage=seal, target=seal, method=refit_seal |
| 56–57 | **advance**; stage=seal, next_step=pressure |
| 58 | **advance**; stage=pressure, next_step=functional |
| 59 | **release**; stage=functional, destination=spares_crate |

</details>

### `train_assembly_d`: E-bike battery pack: early firmware, insulation ticket and carrier reseat

An e-bike battery pack station: cell-carrier scan, tab-weld resistance at W1/W2 (high: reweld; low: inspect the weld; a tab replacement resets the target), a BMS firmware flash that must match the order, an isolation test that rework makes obsolete, and a label and seal-tape count that must be refreshed after every new isolation reading. A flash before the carrier arrives, a lead's clean re-measurement withdrawing a tab escalation, repeated isolation failures that stay repairs, a quality ticket that closes and reopens, a wrong label, and after release a carrier reseat that voids both welds and the isolation evidence, completed target by target around a wrong-version flash and a tab cut-in.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–1 | **repair**; stage=firmware, target=carrier, method=complete_missing |
| 2–3 | **repair**; stage=intake, target=carrier, method=swap_carrier |
| 4–5 | **advance**; stage=intake, next_step=weld |
| 6 | **wait**; stage=weld |
| 7–8 | **repair**; stage=weld, target=W1, method=reweld |
| 9–11 | **escalate**; stage=weld, target=W1, destination=battery_lead |
| 12–16 | **handoff**; stage=weld, destination=battery_lead |
| 17–18 | **advance**; stage=weld, next_step=isolation |
| 19–21 | **repair**; stage=isolation, target=isolation, method=replace_insulator |
| 22–25 | **hold**; stage=isolation, destination=quality_desk |
| 26–28 | **advance**; stage=isolation, next_step=pack |
| 29–30 | **wait**; stage=pack |
| 31–33 | **hold**; stage=pack, destination=quality_desk |
| 34–35 | **repair**; stage=pack, target=label, method=relabel |
| 36–40 | **release**; stage=pack, destination=aging_rack |
| 41–42 | **advance**; stage=intake, next_step=weld |
| 43–44 | **repair**; stage=isolation, target=W1, method=complete_missing |
| 45 | **wait**; stage=weld |
| 46–47 | **repair**; stage=firmware, target=W2, method=complete_missing |
| 48–49 | **repair**; stage=weld, target=W2, method=inspect_weld |
| 50–53 | **repair**; stage=weld, target=bms, method=reflash |
| 54 | **advance**; stage=firmware, next_step=isolation |
| 55 | **advance**; stage=isolation, next_step=pack |
| 56 | **advance**; stage=weld, next_step=pack |
| 57–58 | **repair**; stage=pack, target=seal_tape, method=correct_tape |
| 59 | **release**; stage=pack, destination=aging_rack |

</details>

### `train_support_c`: Island trip changes, bag tracing and passport recorder control

An island airline's travel-change desk: rebook and refund branches share the selected flight segment (seat availability, fare difference, waitlist status, fare type, refund status); the baggage branch uses the selected bag and its tracer deadline, where equality counts as late. A recorder pauses during passport capture (open across a hold and a route change) or while a live partial utterance holds passport digits, and stops when the call ends. Requests are fixed phrases with explicit quotation and negation rules; Agent and Background requests and false claims, scan notes and another unit's records do not count; holds below and at the threshold resume the latest request.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–2 | **rebook**; recorder=record, segment=island, rebook_action=change_free |
| 3–5 | **rebook**; recorder=record, segment=island, rebook_action=collect_difference |
| 6–8 | **refund**; recorder=record, segment=island, refund_action=offer_credit |
| 9–10 | **refund**; recorder=record, segment=island, refund_action=submit_refund |
| 11–13 | **refund**; recorder=record, segment=return, refund_action=explain_nonrefundable |
| 14–15 | **baggage**; recorder=record, bag=suitcase, bag_action=keep_tracing |
| 16–17 | **baggage**; recorder=record, bag=suitcase, bag_action=arrange_delivery |
| 18–20 | **baggage**; recorder=record, bag=guitar_case, bag_action=share_eta |
| 21–23 | **baggage**; recorder=record, bag=suitcase, bag_action=share_eta |
| 24 | **baggage**; recorder=record, bag=suitcase, bag_action=open_claim |
| 25–26 | **baggage**; recorder=pause, bag=suitcase, bag_action=open_claim |
| 27–31 | **hold_wait**; recorder=pause |
| 32–33 | **hold_return**; recorder=pause |
| 34–35 | **baggage**; recorder=pause, bag=suitcase, bag_action=confirm_delivery |
| 36 | **rebook**; recorder=pause, segment=return, rebook_action=offer_waitlist |
| 37–40 | **rebook**; recorder=record, segment=return, rebook_action=offer_waitlist |
| 41–45 | **rebook**; recorder=record, segment=return, rebook_action=await_waitlist |
| 46 | **rebook**; recorder=pause, segment=return, rebook_action=await_waitlist |
| 47–48 | **rebook**; recorder=record, segment=return, rebook_action=await_waitlist |
| 49–50 | **rebook**; recorder=record, segment=return, rebook_action=confirm_change |
| 51–52 | **refund**; recorder=record, segment=island, refund_action=await_refund |
| 53–56 | **refund**; recorder=record, segment=island, refund_action=confirm_refund |
| 57–59 | **closed**; recorder=stop |

</details>

### `train_support_d`: Energy account desk: meter reading, instalment plan and power cut

A home-energy supplier's account desk: a meter branch (submitting electricity and gas readings through a meter tool that validates, flags implausible readings and accepts), an instalment-plan branch (eligibility from the account tool, agreement only after the latest terms reading, a chosen instalment count) and an outage branch (outage map for the home or the cottage, overdue at exactly the estimated restore tick). An always-used priority-services register flag is set and withdrawn only by final Customer statements and persists through holds and after the call. Quoted, refused, partial and non-Customer phrases are distractors; one hold stays below the threshold and a second reaches it exactly.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–2 | **meter**; priority_register=none, meter_target=electricity, meter_action=take_reading |
| 3–4 | **meter**; priority_register=none, meter_target=electricity, meter_action=await_check |
| 5–7 | **meter**; priority_register=none, meter_target=electricity, meter_action=confirm_digits |
| 8–10 | **meter**; priority_register=none, meter_target=electricity, meter_action=confirm_bill |
| 11 | **meter**; priority_register=none, meter_target=gas, meter_action=take_reading |
| 12 | **meter**; priority_register=register, meter_target=gas, meter_action=take_reading |
| 13 | **meter**; priority_register=register, meter_target=gas, meter_action=await_check |
| 14–15 | **plan**; priority_register=register, plan_stage=await_eligibility, instalments=unknown |
| 16 | **plan**; priority_register=register, plan_stage=explain_ineligible, instalments=unknown |
| 17–18 | **plan**; priority_register=register, plan_stage=read_terms, instalments=unknown |
| 19–20 | **plan**; priority_register=register, plan_stage=ask_consent, instalments=unknown |
| 21–22 | **plan**; priority_register=register, plan_stage=ask_count, instalments=unknown |
| 23–25 | **plan**; priority_register=register, plan_stage=set_up, instalments=six |
| 26 | **plan**; priority_register=register, plan_stage=set_up, instalments=twelve |
| 27 | **plan**; priority_register=register, plan_stage=ask_consent, instalments=twelve |
| 28–29 | **outage**; priority_register=register, outage_site=cottage, outage_action=log_report |
| 30–33 | **hold_wait**; priority_register=register |
| 34–37 | **outage**; priority_register=register, outage_site=cottage, outage_action=share_estimate |
| 38–39 | **outage**; priority_register=register, outage_site=cottage, outage_action=escalate_overdue |
| 40 | **outage**; priority_register=register, outage_site=cottage, outage_action=confirm_restored |
| 41 | **outage**; priority_register=register, outage_site=home, outage_action=log_report |
| 42 | **plan**; priority_register=register, plan_stage=ask_consent, instalments=twelve |
| 43 | **plan**; priority_register=none, plan_stage=ask_consent, instalments=twelve |
| 44 | **plan**; priority_register=none, plan_stage=set_up, instalments=twelve |
| 45 | **plan**; priority_register=none, plan_stage=ask_consent, instalments=twelve |
| 46–49 | **hold_wait**; priority_register=none |
| 50 | **hold_return**; priority_register=none |
| 51–52 | **plan**; priority_register=none, plan_stage=ask_consent, instalments=twelve |
| 53 | **plan**; priority_register=register, plan_stage=ask_consent, instalments=twelve |
| 54–55 | **plan**; priority_register=register, plan_stage=set_up, instalments=twelve |
| 56 | **plan**; priority_register=register, plan_stage=confirm_active, instalments=twelve |
| 57–59 | **closed**; priority_register=register |

</details>

### `train_presenter_c`: Wake-word lecture console: whale clicks, a class poll and a reef recording

A wake-word lecture console in a marine-acoustics evening lecture. Speech recognition publishes segments on four channels with word confidences and a stable flag; only a stable lecturer or moderator segment that starts with the wake word, says exactly one phrase from that speaker's list and has every word at or above the confidence threshold is a command, and commands replay in order of segment end. The route is the stage mode (lecture, media, poll, break, ended); the projected slide, recording light and countdown cue apply in every mode, with pointer, media state and poll panel as branch fields. A student using the wake word from the seats, a confident hypothesis that settles with one word under the threshold, a slide command locked out during a clip, a class poll that holds the clip, a title command at exactly the threshold, an unpublished slide that pauses the capture until cleared, and an ending only the moderator can give.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–2 | **lecture**; projected_slide=slide_1, recording_light=on, timer_cue=none, pointer=off |
| 3–8 | **lecture**; projected_slide=slide_2, recording_light=on, timer_cue=none, pointer=off |
| 9–11 | **lecture**; projected_slide=slide_3, recording_light=on, timer_cue=none, pointer=off |
| 12–13 | **lecture**; projected_slide=slide_3, recording_light=on, timer_cue=none, pointer=zoom |
| 14–16 | **lecture**; projected_slide=slide_3, recording_light=on, timer_cue=none, pointer=off |
| 17 | **lecture**; projected_slide=slide_4, recording_light=on, timer_cue=none, pointer=off |
| 18–22 | **media**; projected_slide=slide_4, recording_light=on, timer_cue=none, media_state=playing |
| 23–25 | **poll**; projected_slide=slide_4, recording_light=on, timer_cue=none, poll_panel=collecting |
| 26 | **poll**; projected_slide=slide_4, recording_light=on, timer_cue=none, poll_panel=results |
| 27 | **media**; projected_slide=slide_4, recording_light=on, timer_cue=none, media_state=paused |
| 28–29 | **media**; projected_slide=slide_4, recording_light=on, timer_cue=none, media_state=playing |
| 30 | **lecture**; projected_slide=slide_4, recording_light=on, timer_cue=none, pointer=off |
| 31–33 | **lecture**; projected_slide=slide_6, recording_light=on, timer_cue=none, pointer=off |
| 34 | **lecture**; projected_slide=slide_6, recording_light=on, timer_cue=none, pointer=spotlight |
| 35–36 | **lecture**; projected_slide=slide_6, recording_light=on, timer_cue=wrap_up, pointer=spotlight |
| 37–38 | **lecture**; projected_slide=slide_6, recording_light=on, timer_cue=none, pointer=spotlight |
| 39–41 | **lecture**; projected_slide=slide_8, recording_light=on, timer_cue=none, pointer=off |
| 42 | **lecture**; projected_slide=slide_8, recording_light=paused, timer_cue=none, pointer=off |
| 43–45 | **media**; projected_slide=slide_8, recording_light=paused, timer_cue=none, media_state=playing |
| 46 | **media**; projected_slide=slide_8, recording_light=paused, timer_cue=wrap_up, media_state=playing |
| 47 | **media**; projected_slide=slide_8, recording_light=paused, timer_cue=wrap_up, media_state=paused |
| 48 | **lecture**; projected_slide=slide_8, recording_light=paused, timer_cue=wrap_up, pointer=off |
| 49 | **lecture**; projected_slide=slide_8, recording_light=on, timer_cue=wrap_up, pointer=off |
| 50 | **break**; projected_slide=slide_8, recording_light=paused, timer_cue=wrap_up |
| 51 | **break**; projected_slide=slide_9, recording_light=paused, timer_cue=wrap_up |
| 52–53 | **lecture**; projected_slide=slide_9, recording_light=paused, timer_cue=wrap_up, pointer=off |
| 54 | **lecture**; projected_slide=slide_9, recording_light=paused, timer_cue=overtime, pointer=off |
| 55 | **lecture**; projected_slide=slide_9, recording_light=on, timer_cue=overtime, pointer=off |
| 56 | **lecture**; projected_slide=slide_10, recording_light=on, timer_cue=overtime, pointer=off |
| 57 | **lecture**; projected_slide=slide_9, recording_light=paused, timer_cue=overtime, pointer=off |
| 58–59 | **ended**; projected_slide=slide_9, recording_light=off, timer_cue=none |

</details>

### `train_presenter_d`: After-hours gallery tour of a raised oyster smack, run by the guide's voice

An after-hours gallery tour of a raised oyster smack, controlled by the guide's voice. The recogniser publishes one live slot per role (guide, visitor, staff radio, film) and a log of finished turns already cut into phrases with a question flag. The route is the scene (at_stop, film, questions, paused, finished); the stop and caption source are always shown, with a time-based guide prompt, a screen warm-up from the guide's stable live words, film ducking, a question queue and the scene held by a staff pause as branch fields. Filler words are removed from command phrases, staff pauses hold and restore the scene, a film accepts only the guide's stop command, the end of the tour is final, and both the dwell time and the wrap-up tick count equality.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0 | **at_stop**; stop=estuary, caption_source=blank, guide_prompt=on_time, screen_warmup=idle |
| 1–4 | **at_stop**; stop=estuary, caption_source=guide, guide_prompt=on_time, screen_warmup=idle |
| 5 | **at_stop**; stop=estuary, caption_source=guide, guide_prompt=on_time, screen_warmup=bell |
| 6–8 | **at_stop**; stop=bell, caption_source=guide, guide_prompt=on_time, screen_warmup=idle |
| 9–10 | **at_stop**; stop=bell, caption_source=visitor, guide_prompt=on_time, screen_warmup=idle |
| 11 | **film**; stop=bell, caption_source=guide, film_audio=full |
| 12–13 | **film**; stop=bell, caption_source=film, film_audio=full |
| 14 | **film**; stop=bell, caption_source=visitor, film_audio=full |
| 15 | **film**; stop=bell, caption_source=guide, film_audio=ducked |
| 16 | **film**; stop=bell, caption_source=film, film_audio=full |
| 17 | **paused**; stop=bell, caption_source=film, held_scene=film |
| 18–19 | **paused**; stop=bell, caption_source=guide, held_scene=film |
| 20 | **film**; stop=bell, caption_source=guide, film_audio=full |
| 21–22 | **film**; stop=bell, caption_source=film, film_audio=full |
| 23–24 | **at_stop**; stop=bell, caption_source=guide, guide_prompt=move_along, screen_warmup=idle |
| 25–26 | **at_stop**; stop=bell, caption_source=guide, guide_prompt=move_along, screen_warmup=terrace |
| 27 | **at_stop**; stop=bell, caption_source=guide, guide_prompt=move_along, screen_warmup=idle |
| 28 | **at_stop**; stop=bell, caption_source=guide, guide_prompt=move_along, screen_warmup=hull |
| 29–33 | **at_stop**; stop=hull, caption_source=guide, guide_prompt=on_time, screen_warmup=idle |
| 34–36 | **questions**; stop=hull, caption_source=visitor, question_queue=empty, guide_prompt=on_time, screen_warmup=idle |
| 37 | **questions**; stop=hull, caption_source=guide, question_queue=one, guide_prompt=on_time, screen_warmup=idle |
| 38 | **questions**; stop=hull, caption_source=visitor, question_queue=several, guide_prompt=on_time, screen_warmup=idle |
| 39–40 | **questions**; stop=hull, caption_source=guide, question_queue=empty, guide_prompt=move_along, screen_warmup=idle |
| 41–43 | **at_stop**; stop=hull, caption_source=guide, guide_prompt=move_along, screen_warmup=idle |
| 44 | **at_stop**; stop=hull, caption_source=guide, guide_prompt=move_along, screen_warmup=lab |
| 45 | **at_stop**; stop=lab, caption_source=guide, guide_prompt=on_time, screen_warmup=idle |
| 46–48 | **paused**; stop=lab, caption_source=guide, held_scene=at_stop |
| 49–50 | **at_stop**; stop=lab, caption_source=guide, guide_prompt=on_time, screen_warmup=idle |
| 51 | **questions**; stop=lab, caption_source=guide, question_queue=empty, guide_prompt=on_time, screen_warmup=idle |
| 52 | **questions**; stop=lab, caption_source=visitor, question_queue=empty, guide_prompt=wrap_up, screen_warmup=idle |
| 53 | **questions**; stop=lab, caption_source=visitor, question_queue=one, guide_prompt=wrap_up, screen_warmup=idle |
| 54 | **questions**; stop=lab, caption_source=guide, question_queue=empty, guide_prompt=wrap_up, screen_warmup=idle |
| 55–56 | **at_stop**; stop=terrace, caption_source=guide, guide_prompt=wrap_up, screen_warmup=idle |
| 57 | **finished**; stop=terrace, caption_source=guide |
| 58 | **finished**; stop=terrace, caption_source=visitor |
| 59 | **finished**; stop=terrace, caption_source=guide |

</details>
