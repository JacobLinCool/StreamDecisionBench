# Recorded error witnesses: Laya English

The first untimed decision mismatch in each family is selected deterministically. These examples are observations from this pass; they do not establish a cause or estimate generalization.

## live_debugging: lite_debugging_a, tick 0

Wrong active fields: route, target_result.

```json
{
  "reference_decision": {
    "route": "wait",
    "process": "running",
    "target_result": "original_error"
  },
  "predicted_decision": {
    "route": "ready",
    "process": "running",
    "target_result": "not_run"
  },
  "reference_evidence": [
    "clock advanced to 0; cursor moved to line 30; no relevant event"
  ]
}
```

## procedural_coaching: lite_assembly_a, tick 0

Wrong active fields: route, stage, next_step.

```json
{
  "reference_decision": {
    "route": "advance",
    "stage": "intake",
    "next_step": "seal"
  },
  "predicted_decision": {
    "route": "handoff",
    "stage": "inspection",
    "destination": "none"
  },
  "reference_evidence": [
    "a-0-0"
  ]
}
```

## support_call_assist: lite_support_a, tick 0

Wrong active fields: route, recorder, payment_stage, instrument.

```json
{
  "reference_decision": {
    "route": "payment",
    "recorder": "record",
    "payment_stage": "ask_consent",
    "instrument": "unknown"
  },
  "predicted_decision": {
    "route": "service",
    "recorder": "stop",
    "service_target": "none",
    "service_action": "none"
  },
  "reference_evidence": [
    "telephony.status=connected",
    "The complete public workflow rules are in prepared.rules.",
    "Customer u0-Customer: I'd like to pay the balance, please."
  ]
}
```

## presenter_voice_control: lite_presenter_a, tick 0

Wrong active fields: mode, slide, captions, host_cue.

```json
{
  "reference_decision": {
    "mode": "talk",
    "slide": "s5",
    "captions": "presenter",
    "host_cue": "listen"
  },
  "predicted_decision": {
    "mode": "clip",
    "slide": "s7",
    "captions": "clip",
    "clip_state": "play"
  },
  "reference_evidence": [
    "The complete public rules are in prepared.rules.",
    "Presenter p0 (partial): so the decoder keeps one"
  ]
}
```

All mistakes and active-field accuracies remain available in analysis.json and the original metrics.json. For deployment review, inspect route selection and the active fields together using these frozen states; a wrong route changes which fields the application uses. No additional model pass was selected from these outcomes.
