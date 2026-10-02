# Recorded errors: winnow-e4b-pass3

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

## procedural_coaching: lite_assembly_a, tick 7

Wrong active fields: route.

```json
{
  "reference_decision": {
    "route": "advance",
    "stage": "cover",
    "next_step": "fasten"
  },
  "predicted_decision": {
    "route": "repair",
    "stage": "cover",
    "target": "cover",
    "method": "complete_missing"
  },
  "reference_evidence": [
    "a-7-heartbeat"
  ]
}
```

## support_call_assist: lite_support_a, tick 0

Wrong active fields: payment_stage.

```json
{
  "reference_decision": {
    "route": "payment",
    "recorder": "record",
    "payment_stage": "ask_consent",
    "instrument": "unknown"
  },
  "predicted_decision": {
    "route": "payment",
    "recorder": "record",
    "payment_stage": "choose_card",
    "instrument": "unknown"
  },
  "reference_evidence": [
    "telephony.status=connected",
    "The complete public workflow rules are in prepared.rules.",
    "Customer u0-Customer: I'd like to pay the balance, please."
  ]
}
```

## presenter_voice_control: lite_presenter_a, tick 4

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
    "Presenter p3 (final): Next slide, please."
  ]
}
```

For deployment review, inspect routing and its active fields together against the frozen state and recorded evidence. All errors remain in `analysis.json`.
