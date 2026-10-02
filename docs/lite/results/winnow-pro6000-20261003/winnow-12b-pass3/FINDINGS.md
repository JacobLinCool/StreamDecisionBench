# Recorded errors: winnow-12b-pass3

The first untimed mismatch in each family is selected deterministically. These observations do not establish a cause or estimate generalization.

## live_debugging: lite_debugging_a, tick 0

Wrong active fields: route.

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
    "target_result": "original_error"
  },
  "reference_evidence": [
    "clock advanced to 0; cursor moved to line 30; no relevant event"
  ]
}
```

## procedural_coaching: lite_assembly_a, tick 1

Wrong active fields: route.

```json
{
  "reference_decision": {
    "route": "advance",
    "stage": "intake",
    "next_step": "seal"
  },
  "predicted_decision": {
    "route": "repair",
    "stage": "intake",
    "target": "gasket",
    "method": "fit_gasket"
  },
  "reference_evidence": [
    "a-1-heartbeat"
  ]
}
```

## support_call_assist: lite_support_a, tick 29

Wrong active fields: hold_action.

```json
{
  "reference_decision": {
    "route": "hold",
    "recorder": "record",
    "hold_action": "wait"
  },
  "predicted_decision": {
    "route": "hold",
    "recorder": "record",
    "hold_action": "return_customer"
  },
  "reference_evidence": [
    "telephony.status=hold",
    "The complete public workflow rules are in prepared.rules.",
    "Customer u27-Customer: Check my router first; we can come back to the line fault."
  ]
}
```

## presenter_voice_control: lite_presenter_a, tick 7

Wrong active fields: slide.

```json
{
  "reference_decision": {
    "mode": "talk",
    "slide": "s6",
    "captions": "presenter",
    "host_cue": "listen"
  },
  "predicted_decision": {
    "mode": "talk",
    "slide": "s7",
    "captions": "presenter",
    "host_cue": "listen"
  },
  "reference_evidence": [
    "The complete public rules are in prepared.rules.",
    "Presenter p5 (final): Next slide shows the demo, but first one more number."
  ]
}
```

For deployment review, inspect routing and its active fields together against the frozen state and recorded evidence. All errors remain in `analysis.json`.
