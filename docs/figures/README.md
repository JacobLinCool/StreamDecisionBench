# StreamDecisionBench README figures

These two vector figures use Apache ECharts 6.1.0. The leaderboard includes all twenty-eight
completed single-model settings: eleven hosted API settings and seventeen self-hosted open-weight settings,
including Perplexity Decider v1 27B, Wity auto/off, Cloudflare Clef and Clef Flash, Winnow-12B, Winnow-E4B and all six Decision 2.0 models.
Bars start at zero and rank settings by normalized log-AUC over 0.5–8 seconds.

The second figure plots **in-force accuracy against the time-step interval**, on a logarithmic
horizontal axis. Its curves are the functions summarized by the leaderboard's log-AUC values;
they are not cumulative AUC curves. Lines connect independently evaluated interval points
without smoothing. All settings retain their original recorded release clocks, successful-attempt
latencies and commit lag. Scenarios receive equal weights within each family, then families receive
equal weights. Primary areas come from the verified published analyses, independently of the display grid.

Wity auto/off each have one pass; scores and curves average three passes for all other settings. Wity uses 16 workers and Retry-After recovery; other hosted providers use 32. Single-pass SD is unavailable. Latency summaries average within-pass quantiles. [Hosted repeat results](../lite/results/hosted-api-repeats-20261003/README.md) preserve individual scores and variation. Retiming assumes latency remains fixed when request rates
change. Winnow and Decision 2.0 use RunPod RTX PRO 6000; the other self-hosted settings use the lab RTX PRO 6000.
Hosted API and same-host GPU latency describe different deployments; these figures do
not isolate architecture speed. Qwen uses direct option logits, and Nimble processes fields sequentially.

Regenerate from the repository root, using Python 3.12/3.13, uv and Node.js:

```bash
uv run python paper/analysis/lite_hosted.py --reports
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

## Leaderboard update animation

Generate a six-second MP4 of a measured result entering the leaderboard. The video uses
verified figure data and shared model colors, with a brief anticipation, fast insertion,
and restrained settling. Only the source is versioned; generated videos are Git-ignored.

Install FFmpeg with the `libx264` encoder and the pinned Node dependencies above, then run:

```bash
npm run --prefix docs/figures animate -- --setting Perplexity --seconds 6
```

Use any registered setting ID and a duration from 5 to 6 seconds. Rebuild `data.json` first
after changing the leaderboard. The default output is `docs/figures/leaderboard-update.mp4`;
`--out <path.mp4>` writes to another existing directory. Frames are rendered directly from
SVG and encoded as H.264 at 1440 × 1080, 60 fps, with `yuv420p` and fast-start metadata.
