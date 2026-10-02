# StreamDecisionBench README figures

These two vector figures use Apache ECharts 6.1.0. The leaderboard includes all nineteen
completed single-model settings: eight hosted APIs and eleven self-hosted open-weight settings,
including Cloudflare Clef and Clef Flash, Winnow-12B and Winnow-E4B.
Bars start at zero and rank settings by normalized log-AUC over 0.5–8 seconds.

The second figure plots **in-force accuracy against the time-step interval**, on a logarithmic
horizontal axis. Its curves are the functions summarized by the leaderboard's log-AUC values;
they are not cumulative AUC curves. Lines connect independently evaluated interval points
without smoothing. All settings retain their original recorded release clocks, successful-attempt
latencies and commit lag. Scenarios receive equal weights within each family, then families receive
equal weights. Primary areas come from the verified published analyses, independently of the display grid.

Hosted settings have one recorded pass; self-hosted scores and curves average three passes. Retiming assumes latency remains fixed when request rates
change. Winnow uses RunPod RTX PRO 6000; the other self-hosted settings use the lab RTX PRO 6000.
Hosted API and same-host GPU latency describe different deployments; these figures do
not isolate architecture speed. Qwen uses direct option logits, and Nimble processes fields sequentially.

Regenerate from the repository root, using Python 3.12/3.13, uv and Node.js:

```bash
uv run --group paper python paper/analysis/lite_openweight.py
uv run python docs/figures/prepare.py
npm ci --prefix docs/figures --ignore-scripts
npm run --prefix docs/figures render
```

Preparation checks source and recording hashes, frozen dataset coverage, primary metric compatibility
and agreement with recorded-cadence evaluation. It makes no model or API calls. The renderer checks
the exported data's provenance and produces SVGs using ECharts' server-side renderer.

- [Leaderboard](leaderboard.svg)
- [Interval curves](interval-curves.svg)
- [Full-precision figure data and provenance](data.json)
- [Verified source analysis](../research/openweight-hybrids/analysis.json)
