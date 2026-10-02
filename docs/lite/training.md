# Training split

`data/lite/train-v1/` (dataset hash `00bc46f6…`, 8 scenarios, 480 states) holds further scenarios of the four task families for training decision
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
<!-- SPEC TABLE -->

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
| `train_debugging_c` | 1 | none (minor only) | 60/60 ticks, all fields | clean |
| `train_debugging_d` | 1 | 2 blocking, 2 major (story beats and a file name reused from evaluation, paraphrased distractors, an inconsistent dependency version; session re-plotted) | 60/60 ticks, all fields | clean |
| `train_assembly_c` | 2 | 3 blocking, 2 major (story beats copied from the evaluation gearbox story; after re-plotting, a repair at a stage later than the current one and an unstated tick-0 stage) | 60/60 ticks, all fields | clean |
| `train_assembly_d` | 2 | 1 blocking, 1 major (beat sequence copied from the evaluation scenarios; after re-plotting, a firmware defect repaired while the stage was back at weld) | 60/60 ticks, all fields | clean |
| `train_support_c` | 1 | 1 blocking (case of the capture phrase unstated) | 60/60 ticks, all fields | clean |
| `train_support_d` | 1 | 1 major (the meter target never left its default) | 60/60 ticks, all fields | clean |
| `train_presenter_c` | 1 | none (minor only) | 60/60 ticks, all fields | clean |
| `train_presenter_d` | 1 | 2 major (story beats too close to evaluation scenario B) | 60/60 ticks, all fields | clean |

The reviews also compared story beats, which the automatic audit cannot see: four first drafts
followed the sequence of evaluation story beats with new nouns and were re-plotted. Remaining minor
notes concern story realism and coverage, not reference answers: for example, two
overlapping quality tickets never occur in `train_assembly_d`, and no close command takes effect in
`train_presenter_d`.

## Variants

| Episode | Family | Rules | Transitions | Routes reached |
|---|---|---|---:|---|
| `train_debugging_c` | `live_debugging` | shared policy | 25 | control, delegate, inspect, ready, rerun, wait |
| `train_debugging_d` | `live_debugging` | shared policy | 24 | control, delegate, inspect, ready, rerun, wait |
| `train_assembly_c` | `procedural_coaching` | new workflow `pump_cartridge` | 23 | advance, escalate, handoff, hold, release, repair, wait |
| `train_assembly_d` | `procedural_coaching` | new workflow `battery_pack` | 25 | advance, escalate, handoff, hold, release, repair, wait |
| `train_support_c` | `support_call_assist` | new workflow `travel_change` | 22 | baggage, closed, hold_return, hold_wait, rebook, refund |
| `train_support_d` | `support_call_assist` | new workflow `energy_account` | 31 | closed, hold_return, hold_wait, meter, outage, plan |
| `train_presenter_c` | `presenter_voice_control` | shared rules | 27 | clip, closed, questions, talk |
| `train_presenter_d` | `presenter_voice_control` | shared rules | 39 | clip, closed, questions, talk |

### `train_debugging_c`: Stock hold expiry hunt

A Go microservice that places time-limited stock holds, with its own team, two external teams, new files, runs and tests. The pinned test fails with its original and then a different message; a two-error compile failure must open the first reported file, not the one just edited; a module run goes quiet, its own terminal line resets the silence while editor-tool output does not, and it must be stopped even with an unsaved relevant buffer. An interrupted run, a green run with too many skips, a test-file save exactly at a run's start, a retry failure delegated to the storage team by the last matching owners rule after five messages that do not count, a `go.mod` bump that forces the full suite, ready, and a commit back to wait.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0 | **wait**; process=idle, target_result=original_error |
| 1 | **rerun**; process=idle, target_result=original_error, rerun_scope=target |
| 2–3 | **wait**; process=running, target_result=original_error |
| 4–5 | **inspect**; process=idle, target_result=different_error, inspect_file=internal/reserve/ttl.go |
| 6–8 | **wait**; process=idle, target_result=different_error |
| 9 | **rerun**; process=idle, target_result=different_error, rerun_scope=module |
| 10–11 | **wait**; process=running, target_result=different_error |
| 12–13 | **inspect**; process=idle, target_result=not_run, inspect_file=internal/reserve/hold.go |
| 14–17 | **wait**; process=idle, target_result=not_run |
| 18 | **rerun**; process=idle, target_result=not_run, rerun_scope=module |
| 19–24 | **wait**; process=running, target_result=not_run |
| 25 | **wait**; process=stalled, target_result=not_run |
| 26–29 | **wait**; process=running, target_result=not_run |
| 30–31 | **wait**; process=stalled, target_result=not_run |
| 32–33 | **control**; process=stalled, target_result=not_run, control_action=stop |
| 34 | **wait**; process=idle, target_result=not_run |
| 35 | **rerun**; process=idle, target_result=not_run, rerun_scope=target |
| 36–37 | **wait**; process=running, target_result=not_run |
| 38–39 | **rerun**; process=idle, target_result=passed, rerun_scope=module |
| 40–41 | **wait**; process=running, target_result=passed |
| 42–47 | **delegate**; process=idle, target_result=passed, owner=@kv-storage |
| 48–51 | **wait**; process=idle, target_result=passed |
| 52 | **rerun**; process=idle, target_result=passed, rerun_scope=full |
| 53–54 | **wait**; process=running, target_result=passed |
| 55–57 | **ready**; process=idle, target_result=passed |
| 58–59 | **wait**; process=idle, target_result=passed |

</details>

### `train_debugging_d`: Buoy telemetry decoder session

A Rust crate that decodes buoy telemetry, with its own team, three external teams and new files, runs and tests. A build stalls until its own compiler output resumes and fails with two call-site errors (the first compiler file wins over tooling and a teammate); a module rerun fails differently; a paused debugger is stepped, so the continue card appears four ticks after the last step; the resumed run goes silent, reaches the stop card and is interrupted. Then a green target-only run that skips too many tests, a write exactly at a run's start, a newly failing test owned by the serial team by the last nested owners rule, near-miss commitments before a valid one, a pulled fix with a lock-file bump that forces the full suite, and ready interrupted by an unsaved edit.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0 | **wait**; process=running, target_result=original_error |
| 1 | **wait**; process=stalled, target_result=original_error |
| 2–3 | **wait**; process=running, target_result=original_error |
| 4–5 | **inspect**; process=idle, target_result=not_run, inspect_file=crates/decoder/src/fields/heading.rs |
| 6–9 | **wait**; process=idle, target_result=not_run |
| 10 | **rerun**; process=idle, target_result=not_run, rerun_scope=module |
| 11–13 | **wait**; process=running, target_result=not_run |
| 14–15 | **inspect**; process=idle, target_result=different_error, inspect_file=crates/decoder/src/fields/gust.rs |
| 16 | **wait**; process=running, target_result=different_error |
| 17–26 | **wait**; process=paused, target_result=different_error |
| 27–28 | **control**; process=paused, target_result=different_error, control_action=continue |
| 29–33 | **wait**; process=running, target_result=different_error |
| 34–35 | **wait**; process=stalled, target_result=different_error |
| 36–37 | **control**; process=stalled, target_result=different_error, control_action=stop |
| 38 | **rerun**; process=idle, target_result=not_run, rerun_scope=target |
| 39–40 | **wait**; process=running, target_result=not_run |
| 41–42 | **rerun**; process=idle, target_result=passed, rerun_scope=module |
| 43–45 | **wait**; process=running, target_result=passed |
| 46–49 | **delegate**; process=idle, target_result=passed, owner=@serial-io |
| 50–52 | **wait**; process=idle, target_result=passed |
| 53 | **rerun**; process=idle, target_result=passed, rerun_scope=full |
| 54–55 | **wait**; process=running, target_result=passed |
| 56 | **ready**; process=idle, target_result=passed |
| 57–58 | **wait**; process=idle, target_result=passed |
| 59 | **ready**; process=idle, target_result=passed |

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

### `train_presenter_c`: Marine acoustics guest lecture with a narrated dive clip and a reef recording

A marine-acoustics guest lecture with a narrated whale-dive clip and a silent reef recording, a new 13-slide deck starting on a clip slide, and a new presenter and chair. Early pauses that lapse when the partial is revised into talk, final pause, resume, close, a slide command that closes the clip, go-to commands by number and by name, command-like talk, an echo question that is not a repetition, the 'the question is' repetition, a non-question remark, a near-miss handback and a real one, the Host's thanks, and slide commands after closing, including next at the last slide.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–2 | **talk**; slide=s4, captions=presenter, host_cue=listen |
| 3 | **clip**; slide=s4, captions=presenter, clip_state=play |
| 4 | **clip**; slide=s4, captions=clip, clip_state=play |
| 5 | **clip**; slide=s4, captions=presenter, clip_state=pause |
| 6–7 | **clip**; slide=s4, captions=presenter, clip_state=play |
| 8–11 | **clip**; slide=s4, captions=presenter, clip_state=pause |
| 12–13 | **clip**; slide=s4, captions=presenter, clip_state=play |
| 14–15 | **talk**; slide=s4, captions=presenter, host_cue=listen |
| 16–21 | **talk**; slide=s6, captions=presenter, host_cue=listen |
| 22 | **talk**; slide=s9, captions=presenter, host_cue=listen |
| 23–25 | **clip**; slide=s9, captions=presenter, clip_state=play |
| 26–28 | **talk**; slide=s10, captions=presenter, host_cue=listen |
| 29 | **talk**; slide=s10, captions=host, host_cue=listen |
| 30–31 | **questions**; slide=s10, captions=host, question_card=waiting, host_cue=listen |
| 32–33 | **questions**; slide=s10, captions=audience, question_card=listening, host_cue=listen |
| 34 | **questions**; slide=s10, captions=audience, question_card=repeat, host_cue=listen |
| 35–36 | **questions**; slide=s10, captions=presenter, question_card=repeat, host_cue=listen |
| 37–38 | **questions**; slide=s9, captions=presenter, question_card=repeat, host_cue=listen |
| 39–41 | **questions**; slide=s9, captions=presenter, question_card=answer, host_cue=listen |
| 42 | **questions**; slide=s9, captions=audience, question_card=answer, host_cue=listen |
| 43–44 | **talk**; slide=s9, captions=presenter, host_cue=listen |
| 45–46 | **talk**; slide=s11, captions=presenter, host_cue=listen |
| 47 | **talk**; slide=s11, captions=presenter, host_cue=stand_by |
| 48 | **talk**; slide=s11, captions=presenter, host_cue=listen |
| 49–51 | **talk**; slide=s11, captions=presenter, host_cue=stand_by |
| 52 | **talk**; slide=s11, captions=host, host_cue=listen |
| 53–55 | **closed**; slide=s11, captions=host |
| 56–59 | **closed**; slide=s13, captions=presenter |

</details>

### `train_presenter_d`: Maritime museum lecture with two clips, a floor comment and a floor request for an earlier slide

A maritime museum's livestreamed lecture on raising a sunken oyster smack, with a diver video with radio talk and a silent lift animation on a new 12-slide deck. Clip speech that sounds like a command, an early pause that lapses, a final pause and resume, a close command phrased as a question, a close command ignored in questions mode, questions opened from clip mode, a floor comment that needs no repeat, a floor request for an earlier slide that does not move it, two floor questions where the second resets the repeat card, a stand-by revised away, a handback ended by the Host's first sound, the thanks command, and a slide command after closing.

<details><summary>Reference decision timeline</summary>

| Ticks | Applied decision |
|---|---|
| 0–2 | **talk**; slide=s2, captions=presenter, host_cue=listen |
| 3–4 | **talk**; slide=s3, captions=presenter, host_cue=listen |
| 5 | **clip**; slide=s3, captions=presenter, clip_state=play |
| 6–8 | **clip**; slide=s3, captions=clip, clip_state=play |
| 9 | **clip**; slide=s3, captions=presenter, clip_state=pause |
| 10 | **clip**; slide=s3, captions=presenter, clip_state=play |
| 11–13 | **clip**; slide=s3, captions=presenter, clip_state=pause |
| 14–16 | **clip**; slide=s3, captions=presenter, clip_state=play |
| 17 | **clip**; slide=s3, captions=host, clip_state=play |
| 18–19 | **clip**; slide=s3, captions=presenter, clip_state=play |
| 20–21 | **talk**; slide=s4, captions=presenter, host_cue=listen |
| 22–23 | **talk**; slide=s6, captions=presenter, host_cue=listen |
| 24–26 | **clip**; slide=s6, captions=presenter, clip_state=play |
| 27 | **clip**; slide=s6, captions=host, clip_state=play |
| 28 | **questions**; slide=s6, captions=host, question_card=waiting, host_cue=listen |
| 29–30 | **questions**; slide=s6, captions=presenter, question_card=waiting, host_cue=listen |
| 31 | **questions**; slide=s6, captions=audience, question_card=listening, host_cue=listen |
| 32 | **questions**; slide=s6, captions=audience, question_card=answer, host_cue=listen |
| 33 | **questions**; slide=s6, captions=presenter, question_card=answer, host_cue=listen |
| 34 | **talk**; slide=s6, captions=presenter, host_cue=listen |
| 35 | **talk**; slide=s6, captions=presenter, host_cue=stand_by |
| 36–37 | **talk**; slide=s6, captions=presenter, host_cue=listen |
| 38–39 | **talk**; slide=s6, captions=presenter, host_cue=stand_by |
| 40–41 | **talk**; slide=s6, captions=host, host_cue=listen |
| 42–43 | **questions**; slide=s6, captions=host, question_card=waiting, host_cue=listen |
| 44–45 | **questions**; slide=s6, captions=audience, question_card=listening, host_cue=listen |
| 46 | **questions**; slide=s6, captions=audience, question_card=repeat, host_cue=listen |
| 47 | **questions**; slide=s6, captions=presenter, question_card=repeat, host_cue=listen |
| 48 | **questions**; slide=s2, captions=presenter, question_card=answer, host_cue=listen |
| 49 | **questions**; slide=s2, captions=audience, question_card=listening, host_cue=listen |
| 50 | **questions**; slide=s2, captions=audience, question_card=answer, host_cue=listen |
| 51 | **questions**; slide=s2, captions=presenter, question_card=answer, host_cue=listen |
| 52 | **questions**; slide=s4, captions=presenter, question_card=answer, host_cue=listen |
| 53 | **questions**; slide=s4, captions=audience, question_card=listening, host_cue=listen |
| 54 | **questions**; slide=s4, captions=audience, question_card=repeat, host_cue=listen |
| 55 | **questions**; slide=s4, captions=presenter, question_card=repeat, host_cue=listen |
| 56 | **questions**; slide=s4, captions=presenter, question_card=repeat, host_cue=stand_by |
| 57 | **closed**; slide=s4, captions=host |
| 58 | **closed**; slide=s4, captions=presenter |
| 59 | **closed**; slide=s3, captions=presenter |

</details>

