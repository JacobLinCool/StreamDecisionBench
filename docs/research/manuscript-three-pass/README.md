# Three-pass manuscript evidence

The manuscript uses six hosted and nine self-hosted settings, each with three complete recordings. The public leaderboard can contain further settings.

From the repository root, regenerate with:

```sh
uv run --group paper python paper/analysis/lite_repeated.py
```

This reads immutable recordings and published reports, checks their hashes and independent reference replay, and writes `analysis.json`, manuscript macros and figures. No model or network call is made.

Scores average independently evaluated passes equally, after equal scenario and family weighting. Latency summaries average per-pass quantiles; request, token and cost totals sum the three passes. Primary-score SD is the sample standard deviation across passes. The network ranges average the per-pass endpoints and are not confidence intervals for the mean.

Compositions pair matching ordinal passes before averaging; the components were recorded separately. Individual paths are retained, with pass 1 used for Figure 1 and the detailed stale-override example. Repeated evaluations do not increase the eight unique scenarios or 480 unique states.

For Kev-27B/Terra-none, Jev/Terra-none and Jev/Terra-low, the manifest also reports every one-to-one matching of the three component passes under freshest-source arbitration. These six alternative matchings describe pairing sensitivity, not additional independent recordings. Laya diagnostics separately count correct routes, correct reference-consumed fields (including the route, pooled over those fields), and exact composed decisions. The compute summary sums the 27 measured local run durations; setup, audits, warmups and other experiments are excluded.

The frozen evaluation policy's statement that no recording was repeated describes the original AUC-selection stage. The current manuscript subsequently includes all three complete passes per setting; its `selection_annotation` makes that scope explicit without altering the frozen policy or original reports.

The manifest retains per-pass statistical evidence and exact recording/report hashes; full response paths stay in the referenced recordings. The earlier public composition reports remain separate, with their original hosted controls.
