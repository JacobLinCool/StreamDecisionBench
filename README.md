# StreamDecisionBench

StreamDecisionBench evaluates the decision an application actually uses while
public evidence changes: an answer takes effect when it arrives, so both its
correctness and its timing count.

## Current benchmark

The paper and citations call the current benchmark SDB. In paths, module names and
run names it goes by its internal name `lite` (`data/lite/v1`, `streamdecisionbench.lite`,
`runs/lite-v1-*`); that name marks the current version, not a reduced subset.

Four families (IDE debugging, assembly, support workflows, presenter voice
control with streaming ASR), two independently authored scenarios each, 60
evidence releases at a two-second recording cadence per scenario. The paper summarizes in-force accuracy over 1–5 s by normalized log-AUC, averaging scenarios within each family and then families equally; see [current results](docs/lite/results/four-family/README.md). Each release asks six or
seven choice questions; a declared
composition turns the answers into the decision the application consumes, so
unused branch answers do not count. See [the protocol](docs/lite/PROTOCOL.md)
for data, execution and scoring, and [the results index](docs/lite/results/README.md)
for current runs.

```bash
# a new pass (paid requests) needs a fresh output folder; runs/my-* stays local
uv run python -m streamdecisionbench.lite run --data data/lite/v1 \
  --out runs/my-luna-low --model gpt-5.6-luna --effort low
uv run python -m streamdecisionbench.lite run --data data/lite/v1 \
  --out runs/my-jev --provider typesafe --model jev-latest
# rescore and report a recorded pass without model calls (the report goes to a scratch folder)
uv run python -m streamdecisionbench.lite score --run runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1
uv run python scripts/lite/lite_report.py --run runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1 \
  --out /tmp/sdb-luna-low-report
```

A new pass needs `OPENAI_API_KEY` (GPT settings, the default provider) or `TYPESAFE_API_KEY`
(Jev, `--provider typesafe`): run `cp .env.example .env` and fill it in, or export the variable.
The recorded passes cover six settings: GPT-5.6-Luna and GPT-5.6-Terra at reasoning effort low and
none, GPT-6-Astra at low (the model does not accept none), and Jev (`jev-latest`); see
[runs](runs/README.md). Run the tests with `uv run pytest`. The paper builds with `latexmk` in
`paper/` (see [paper/README.md](paper/README.md)). Cite SDB with [CITATION.cff](CITATION.cff);
code and data are released under the [MIT license](LICENSE).

The per-run reports under `docs/lite/results/` and some design notes are mostly in Traditional
Chinese; [the protocol](docs/lite/PROTOCOL.md) and the paper are the English references.

## Repository map

| Status | Paths |
|---|---|
| **Current** | `data/lite/v1/`, `src/streamdecisionbench/lite/`, `scripts/lite/`, `docs/lite/`, `paper/` (SDB paper), `tests/test_lite_*.py`, `runs/lite-v1-*` |
| Shared | `src/streamdecisionbench/{jev.py,adapters/,mock_server.py,schema.py,authoring/}`, `docs/LITERATURE.md`, `docs/MINIMAL_DESIGN.md` |
| Legacy data, runs, docs and draft (not in active use; local only, not versioned) | `data/legacy/`, `runs/legacy/`, `docs/legacy/`, `docs/lite/results/legacy/`, `paper/legacy/` (earlier draft) |
| Legacy code (not in active use; versioned) | the `sdb` CLI and its modules (see [package map](src/streamdecisionbench/README.md)) and their tests |

Indexes: [data](data/README.md), [package](src/streamdecisionbench/README.md),
[tests](tests/README.md), [runs](runs/README.md), [paper](paper/README.md). Git versions the current recorded passes
(`runs/lite-v1-*-retry-v1/`) with their index; ad-hoc runs, logs and every `legacy/` folder
(`data/`, `docs/`, `docs/lite/results/`, `paper/`, `runs/`) stay local and are not versioned.

## Legacy: `sdb` CLI pipeline (v0 and `sdb/0.2`)

> **Not in active use.** This section documents the earlier ten-family dataset and replay pipeline, kept so the `sdb` CLI, its tests and the earlier paper draft (`paper/legacy/`) still run. Its data and runs are in `data/legacy/v0` and `runs/legacy/v0`, which are local only and not versioned. In a fresh clone the tests that read `data/legacy/v0` skip until `uv run sdb build` regenerates it (about 2 s). The `docs/legacy/` files named below are local only as well. Its all-question correctness and one-to-three-question limit do not describe the current benchmark.

StreamDecisionBench measures whether a model can make **fast, correct and temporally
stable decisions over a live stream, within the time a real-time system allows**.
Each episode is a 50-500 s window of one continuous situation (a talk, an interview,
a support call, a bedside monitor...) observed as 100 ticks of 0.5, 1, 2, 3 or 5 s.
At every tick the model receives the state a deployed system would have at that
moment (prepared material, bookkeeping, and raw live signals such as timestamped
speech recognition, telemetry and logs, under one fixed JSON Schema per family) and
a fixed set of typed questions, and decides what should be in force *now*: change
course when the situation calls for it, and hold steady when only the wording
changes. The response budget is one tick: in the real-time replay an answer that
arrives late leaves the previous decision in force for the ticks it missed.

The target is **100 episodes x 100 ticks = 10,000 decisions** over ten application
families, built as twenty base scenarios with five contrast variants each.

**Status.** The dataset is being rebuilt family by family for this real-time design,
presentation_navigation first (`docs/legacy/REALTIME_FAMILIES.md`, local only).
The other nine families are still v0 pilot episodes (`sdb/0.1`, ticks of 12 s to 1 h),
kept only so the repository builds and runs end to end. The v0 pilot numbers in
`docs/legacy/VALIDATION.md` (local only) are superseded.

The interface is TypeSafe's **System One** format, so System One models such as
[Jev](https://docs.typesafe.ai/introduction) run natively, and any other model can
take part through an adapter:

```json
{
  "state": {"talk": {...}, "script": [...], "clock": {"now": "09:22.0", "to_hard_out": "02:38.0"},
            "slides": {...}, "channels": [...],
            "voice": [{"channel": "lapel", "state": "silent", "since": "09:16.8"}, ...],
            "mic_log": [...],
            "segments": [..., {"start": "09:13.0", "end": "09:16.8", "channel": "lapel", "text": "Okay, thanks. So, where... where was I, the, um"}],
            "partials": [], "media": {...}},
  "questions": {
    "q1": {"type": "choice", "instructions": {"role": "...", "conventions": ["..."], "rules": ["1. ...", "2. ..."]},
           "criteria": {"K4": "...", "M2": "...", "...": "..."}},
    "q2": {"type": "choice", "instructions": {...}, "criteria": {"K8": "Bridge-back line into the section in progress", "...": "..."}}
  }
}
```

A decision combines one to three questions (choice with 2-10 options, or score with
3-5 levels); a tick is correct only when every answer is.

### Quick start

```bash
uv sync
uv run sdb build                            # regenerate the local-only data/legacy/v0 (about 2 s)
uv run sdb validate                         # structural checks over all 100 episodes
uv run sdb eval --model random              # chance floor
uv run sdb eval --model oracle              # metric ceiling (uses gold; harness test only)

# Jev (TypeSafe): put the key in .env (git-ignored; see .env.example) or export it
cp .env.example .env   # then fill in TYPESAFE_API_KEY
uv run sdb eval --model jev:jev-latest --concurrency 8 --out runs/jev-latest

# OpenAI models (Responses API): OPENAI_API_KEY in .env; optional @<reasoning effort>
uv run sdb eval --model openai:gpt-5.6-luna --concurrency 16 --out runs/gpt-5.6-luna
uv run sdb eval --model openai:gpt-5.6-luna@low --concurrency 16 --out runs/gpt-5.6-luna-low

# Per-question accuracy of a run, per episode or per scenario
uv run sdb questions --run runs/jev-latest --by scenario --prior

# Any Jev-compatible endpoint, or the local mock server
uv run sdb serve-mock --backend lexical --port 8787 --latency-ms 40 --jitter-ms 8 &
TYPESAFE_API_KEY=local uv run sdb eval --model "jev:jev-latest@http://127.0.0.1:8787" --out runs/mock
```

Other adapters: `http:<base_url>`, `anthropic:<model>` (Anthropic API; the
`anthropic` package is not a project dependency, so run it as
`uv run --with anthropic sdb eval --model anthropic:<model>`),
`claude-cli:<model>` (local Claude Code CLI, small runs only), and local
references `random`, `first`, `sticky`, `lexical`, `oracle-noisy:<p>`,
`oracle-lag:<k>`, and the baselines that must miss most language-driven
transitions: `lagged-sticky:<k>` (the previous gold, k ticks late) and
`copy-human` (the decision the humans' own latest actions imply; families with
a human-action map only, e.g. `--family presentation_navigation`).
Generative models (OpenAI, Anthropic, Claude CLI) answer with one committed
answer per question, which the adapter wraps as a one-hot System One answer,
so calibration metrics do not apply to them. The OpenAI adapter uses Structured
Outputs, so its replies are always one of the request's own labels or levels. It
stores no responses, and a rejected key or unknown model stops the run (finished
episodes stay saved, so rerunning the command resumes).

### Metrics

No single overall score. Every metric is reported for the **untimed** run (every
tick answered in order, timing ignored) and for a **real-time replay** built from
the same answers and their measured latencies: tick t's state is released at
t x tick, the model has one request in flight and gets the newest state when idle,
a request older than max(3 ticks, the deadline) is abandoned, the decision in
force when each tick ends is scored, and ticks with none are wrong. The gap
between the two is the cost of latency (when no response fails: the untimed run
scores a failure wrong, the replay keeps the previous decision). A pipelined
replay (overlapping requests allowed) is reported as a secondary view, and each
replay also gives mean ± sd over 20 redraws of the run's own latencies. The
leaderboard reports:

| Metric | Meaning |
|---|---|
| **SBA** | Segment-balanced accuracy: accuracy inside each constant gold segment, averaged, so long stable regions do not dominate |
| **Transition F1@2** | Did the model switch to the right new decision within 2 ticks (a tolerance relative to the tick) and hold it for 2? |
| **RD** (median, p90) | Reaction delay for detected transitions, in seconds (wall-clock in the replays) and ticks |
| **ESR** | Excess (unmatched, held) switches per tick: the stability measure |
| **DSR** | Share of transitions settled within the scenario's deadline, set in seconds; early switches (before the evidence) are not on time, and the early-switch rate is shown beside it |
| **p95 latency** | Wall-clock per sent request, failed ones included (p50/p99 also reported) |
| **CSA** | Contrast-set accuracy: a scenario counts only if every counterfactual probe is solved across its variants |

Secondary: time-weighted accuracy, per-question accuracy beside the majority share,
Transition F1@0 (no tolerance), raw switch rate, CSA-probe, failed-request rate,
late rate (requests that take a full tick or more), stale and timeout rates in
the replays, calibration (NLL / Brier / ECE) for probabilistic models, and
breakdowns by family, variant, tier, event tag and decision structure. See
`docs/legacy/SPEC.md` (local only) for exact definitions.

### How the data is built

Each base scenario is a small latent state machine written in Python
(`src/streamdecisionbench/families/`): a timed, open-loop script (utterances with
start and end times, device and log events, human clicks), a deterministic policy
that implements the natural-language rules rule for rule, and a renderer that
produces, at each read time, exactly what the deployed system would see:
finalized speech segments after the declared recognition lag, current partials,
voice activity, rolling windows of events, prepared context. The system's own
outputs never appear in the state, and nothing in it interprets the situation
("stuck", "finished"); the model infers events from the signals. The five
variants of a scenario share the state schema:

| Variant | What changes |
|---|---|
| canonical | the scenario as designed |
| paraphrase | every free-text value (speech, prose, log wording, rules, options), same timings, latent states and gold |
| lexical_decoy | irrelevant content in existing carriers that borrows the vocabulary of wrong options, same gold |
| minimal_cf | two to four small factual edits that flip the decision |
| structural_cf | a changed history, plan or constraint with the same surface story |

Quality control: every timeline is simulated from its design before it is coded;
`sdb validate` checks schema conformance, the temporal budget, evidence timing,
threshold margins, renderer guarantees and variant consistency; blind solvers
follow each stream in order without gold; shortcut audits (`sdb audit`, with
family heuristics such as presentation's "latest content phrase -> nearest
unit", reported per question) and reference baselines (including copy-human and
lagged-sticky) check that surface cues do not give the answer away.

### Layout of the legacy pipeline

```
docs/legacy/DESIGN.md          original benchmark design
docs/legacy/SPEC.md            specification, sdb/0.2 (format, protocol, metrics, authoring contract)
docs/legacy/REALTIME_FAMILIES.md  per-family real-time designs and the author's decision record
docs/legacy/realtime-design/   design simulators and example states
docs/legacy/VALIDATION.md      v0 pilot validation (superseded)
docs/legacy/families/*.md      v0 pilot design notes per task family
src/streamdecisionbench/
  jev.py                       System One wire format and response contract
  schema.py                    episode format, request construction
  authoring/                   latent -> policy -> renderer framework; stream.py: clocks, speech, windows
  families/                    the ten task families (two scenarios each)
  evaluator.py, metrics.py     evaluation loop and leaderboard metrics
  adapters/                    Jev / HTTP / LLM / local reference models
  mock_server.py               local Jev-compatible server
  validate.py, blind.py        structural and blind semantic validation
  audit/                       shortcut audits; heuristics.py: family heuristics and human-action maps
data/legacy/v0/episodes/       the built episodes (public requests + hidden gold)
data/legacy/v0/manifest.json   episode hashes
```
