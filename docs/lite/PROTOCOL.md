# StreamDecisionBench (SDB): protocol

SDB evaluates the decision an application actually uses while public
evidence changes. Four families contain two independently authored scenarios
each: [IDE debugging](debugging.md), [assembly](assembly.md),
[support workflows](support.md), and [presenter voice control](presenter.md),
whose transcript carries streaming-ASR partial hypotheses that are revised and
finalised. Every scenario has 60 ticks; snapshot t is
published at tick t, and every time the model sees (clocks, utterance and event
times, thresholds, deadlines) is written in ticks. The recording publishes one
tick every `tick_seconds` = 2 s, spanning 120 seconds, and the same recorded
answers and latencies can be evaluated at any other tick duration. There are 480
states in one pass; related states within a scenario are not independent samples.

The current build is `data/lite/v1` (dataset hash `fdfdd55d…`). The public leaderboard includes twelve hosted API settings and seventeen self-hosted open-weight settings, each covering all eight scenarios and 480 states; see the [results index](results/README.md). The manuscript retains six hosted settings: GPT-5.6-Luna and GPT-5.6-Terra at reasoning effort low and none, GPT-6-Astra at low (the model does not accept none), and Jev (`jev-latest`). Cloudflare Clef and Clef Flash, Perplexity Decider v1 27B, GLiDE (Fastino), and Wity auto/off are additional public leaderboard entries.

For Luna, Terra and Jev, the first six scenarios were recorded on 2026-09-28 (UTC) using build `60f6a877…`. Their frozen episode hashes match the corresponding scenarios in the current build. The two presenter scenarios were recorded separately on 2026-09-29 (UTC) and merged after configuration and provenance checks. Astra low recorded all eight scenarios in one session on 2026-09-29; Clef and Clef Flash each recorded a complete eight-scenario pass on 2026-10-02. The current open-weight cohort was recorded on the same RTX PRO 6000 lab host on 2026-10-01. These are descriptive deployment measurements, not controlled hardware comparisons.

This build clarifies two public rule sentences of an earlier v1 build
(`b03d8c9d…`, kept as a local archive in `data/legacy/lite-v1-b03d8c9d/`, not versioned): in debugging, `*` in
scope and owner patterns matches any characters including `/`; in assembly, a
NO_READ scan does not count as a scan in any rule. Events, questions and
reference answers are unchanged. The two historical runs on the earlier build,
GPT-5.6-Luna low and GPT-5.6-Terra low under the original physical wall-clock
protocol without retries, are kept in the local archive
`docs/lite/results/legacy/lite-v1-b03d8c9d/` (not versioned);
Terra's two connection failures remain counted as incorrect there. They are not
compared with current results.

## Public evidence and application decisions

Each request contains only the complete current `state` and typed `questions`.
Prepared rules, real application bookkeeping, tool records, and timestamped
utterances retain their natural structure. No future state, reference answer,
authoring witness, scenario index, or latent interpretation is appended to the
request. Some state clocks and event sequence numbers are legitimately public.
Reference answers are computed by an executable rule evaluator reading that
same public state. This establishes reproducibility within the declared rules;
it is not independent human validation of deployment usefulness.

Each scenario asks six or seven choice questions. A declared `decision_spec`
defines the route question, globally used answers, and answers used by each
branch. Applying this function to a model response preserves the model's own
route. The function is separately applied to the reference answers. The
resulting complete application decisions must agree. Incorrect unused branch
answers do not lower this score; a wrong route is not repaired using gold.
Malformed responses are rejected as a whole.

Every question has a role in at least one branch. Choice labels are opaque,
deterministically shuffled per episode/question and fixed across the episode;
descriptions retain their meanings. The full original answer vector is saved
for diagnostics. Increasing the number of unused questions does not by itself
make the primary criterion harder.

Public events and timer reevaluations occur at declared release boundaries.
Reference decisions persist between releases; this is an observation-driven
application policy. New model responses may become effective anywhere between
boundaries. Reference segments are maximal intervals of the **composed**
reference decision, so an unused answer changing does not create a new segment.

## Execution and transport retries

The runner uses the OpenAI Responses adapter with strict structured outputs,
TypeSafe's SDK for Jev (`--provider typesafe`), or Clef's native Workers AI REST
endpoint (`--provider cloudflare`), preserving its probability distributions; the provider, requested model
and any reasoning effort are recorded in each run. This uses
pipelined requests: one logical request is dispatched at every
evidence release even if an earlier response is pending. Episodes run serially,
with a worker ceiling of 32 within an episode. This is a declared execution
policy, not a requirement on benchmark submissions or a single-in-flight claim.

A monotonic wall clock drives releases. The log records the scheduled release,
actual release, request start, response receipt, validated completion, and
acceptance time. A complete valid response becomes active atomically only if
its source index is newer than the currently active response and it arrives
before the episode horizon. Older responses cannot overwrite newer decisions.
Before the first accepted answer there is no decision, which counts as wrong.
After the horizon, responses are retained for answer-quality diagnostics but
cannot improve the time score.

The current execution protocol is `retry_excluded_successful_attempt_v1`.
Connection errors and network timeouts trigger a retry of exactly the same
public input, questions, model, and settings. The first retry is immediate;
subsequent retries use delays of 0.5, 1, and 2 seconds by default. A logical
request allows at most five physical attempts. The SDK's internal retries are
disabled so every attempt can be recorded. Its network timeout is 20 seconds,
which is not a global request deadline or a guarantee of exactly 20 seconds of
total execution.

A valid response ends retries even when its decision is incorrect. Authentication,
model rejection, schema errors, and other non-transport failures stop the run.
Exhausting transport retries also makes the run incomplete: a complete primary
score requires a valid response for every released state. Failed attempts and
their error types remain in the event log. The runner refuses to overwrite an
existing run directory.

## Scores and interpretation

The underlying measure is correct decision duration divided by observed duration.
The primary leaderboard summary integrates this accuracy over update intervals;
see [integrated evaluation](#integrated-evaluation-across-time-scales). Fixed-cadence
and segment-balanced scores are diagnostics.
In the current protocol it is computed on a reconstructed timeline that excludes
retry and dispatch-queue delays. For each logical request, its reconstructed
arrival is its actual evidence release plus the final successful attempt's
duration plus its measured postprocessing commit lag. Failed attempts, retry
waits, and worker queue waits contribute no model latency. Arrival order and
latest-source acceptance are recomputed on this timeline, including the episode
horizon. Thus a successful response that physically arrives after the horizon
can still contribute to the reconstructed score if its normalized arrival is
within the horizon.

This score is labeled `release_anchored_successful_attempt_replay`. It is distinct
from observed deployment behavior. The original physical trace and a separate
`raw_wallclock_metrics.json` retain actual elapsed time and update acceptance.
Segment-balanced duration accuracy is reported on both timelines.

Reports add a secondary sensitivity analysis using each run's own records. A
10th-percentile quantile regression models the time before receipt with a fitted
intercept, a prefill term proportional to uncached input tokens and, for
text-generating models, a decode term proportional to output tokens. Token
slopes are nonnegative. The intercept is a non-token remainder that may include
network transfer, fixed server time and omitted processing costs; it neither
identifies network delay nor guarantees an upper bound on it. Every response is
replayed with this remainder removed, clamping the send-to-receipt duration at
zero while retaining postprocessing and commit lag.
A moving-block bootstrap within each scenario gives the reported fit-uncertainty
range. This analysis never replaces the primary score or rejects a run. The
observable episode starts at the first actual evidence release and ends at the
scheduled 120-second horizon.

The scorer classifies every observed instant by two conditions of the decision in
force: whether its source state is still current (its reference decision equals
the one in force now) and whether its answer was right for that source. Error
time is a judgment error (current source, wrong answer), stale (outdated source,
right answer), compound (outdated source, wrong answer) or no decision; stale time
equals `error_seconds.source_correct`, and judgment plus compound equals
`error_seconds.source_incorrect`. An outdated wrong answer that happens to match
the current reference is counted as correct and reported as `outdated_correct`.
The per-scenario `time_partition_seconds` holds these classes, and
`current_source_share` is the share of observed time with a current source, which
equals the in-force accuracy of the reference answers at the same arrival times
(the oracle in-force accuracy). In-force accuracy is exactly that share times the
accuracy while the source is current, plus the `outdated_correct` share; at zero
latency it equals untimed decision accuracy.

Untimed decision accuracy applies the same composition to every state's final
valid response and ignores its delivery time. Incorrect decisions count as
incorrect; transport errors are separately reported and cannot silently remove
states from the denominator. It is a diagnostic on the same run, not a separately
measured untimed execution.
Untimed segment-balanced accuracy supports comparison of weighting choices.
All-question exact match, active-question accuracy, response latency, update
rejections, and concrete errors are additional diagnostics. In particular,
all-question exact match is not the application decision score.

Reliability is reported with explicit denominators: failed physical attempts
divided by all physical attempts, and logical requests needing a retry divided
by all logical requests. Counts, error types, and excluded durations accompany
these rates. For example, a 30-second failed connection followed by a two-second
successful attempt contributes two seconds of attempt latency, one failed
attempt out of two, and one retried logical request out of one. It does not
become a 32-second model response.

Raw recording summaries use equal episode means. The paper integrates each scenario's in-force accuracy over 0.5–8 s with normalized log weighting, then averages scenarios within each family and families equally; this build has two scenarios per family. Each scenario's time fractions are normalized before integration; seconds from different horizons are never pooled. This first
dataset has the same episode count and nominal duration in every family.
The reported results contain one pass per setting and two independent scenarios
per family, with no confidence interval claim and no assertion that the sample
represents all applications.
The two-second recording interval is a controlled setting, not independently
validated human behavior; because states are written in ticks, results at other
tick durations follow from the same recording. The amount and difficulty of language may differ by family.

The benchmark sets no target score or expected ranking for any model, and
reference answers are never changed to match a model's output. Data and rules
are frozen for each model pass. During development `data/lite/v1` was rebuilt
in place; the dataset hash recorded in every run identifies the build, and only
runs on the same data are compared. Code changes do not invalidate earlier runs:
scores are recomputed from each run's own events, and recorded source versions
serve traceability only. Execution changes receive a distinct
protocol version. Models compared
under the retry policy must use that same policy; historical physical-clock
scores and retry-excluded scores are not interchangeable. Successful-attempt
timing still includes ordinary network and service delay, and normalization does
not remove every effect of concurrent service load.

## Reproduction

```sh
# a new pass (paid requests) into a fresh folder
uv run python -m streamdecisionbench.lite run --data data/lite/v1 \
  --out runs/my-terra-low \
  --model gpt-5.6-terra --effort low --max-attempts 5 --retry-delay 0.5
uv run python -m streamdecisionbench.lite run --data data/lite/v1 \
  --out runs/my-jev \
  --provider typesafe --model jev-latest --max-attempts 5 --retry-delay 0.5
# rescore a recorded pass and write its diagnostics report to a scratch folder
uv run python -m streamdecisionbench.lite score \
  --run runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1
uv run python scripts/lite/lite_report.py \
  --run runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1 --out /tmp/sdb-terra-low-report
```

A new pass must use a fresh `--out` outside the versioned `runs/lite-v1-*-retry-v1`
pattern; reports of recorded passes go to a scratch folder. `lite_report.py` writes
the recording-cadence diagnostics only. The published reports in
`docs/lite/results/four-family/` come from `paper/analysis/lite_reports.py` (see
[Integrated evaluation across time scales](#integrated-evaluation-across-time-scales)).

A run can record part of a build: `--families live_debugging,support_call_assist` or
`--episodes lite_support_a` records only those episodes, and the selection is
stored in the run's configuration. Family names are the episodes' `task_family`
values: `live_debugging`, `procedural_coaching` (assembly), `support_call_assist`
and `presenter_voice_control`. `merge` combines complete runs of one setting
into a single run directory that is scored and reported like any other run:

```sh
uv run python -m streamdecisionbench.lite merge --data data/lite/v1 \
  --runs runs/my-jev-part1 runs/my-jev-presenter \
  --out runs/my-jev-merged
```

The parts must cover every episode of the build exactly once, each episode must
equal the build's episode (same hash), and execution settings must match. Parts
answered by different served model versions are refused unless
`--allow-served-model-change` is given. Each episode keeps its own recorded
timeline, so the merged run scores exactly as its parts do; `combined_from` in its
`run.json` lists every part (by its path relative to the merged run folder) with its episodes,
recording times, dataset hash and served models. Adding a family therefore needs runs of the new episodes only.

The builder stores episode/public-input hashes and generator source hashes.
The run stores a complete frozen dataset, source hashes, execution settings,
safe response metadata, token usage, all decisions, release records, intervals,
and per-state mistakes. Credentials are loaded from the existing environment or
ignored `.env`; they are never written to the run artifacts.

The build command requires an empty destination: rebuild into a new directory
(for example `--data /tmp/sdb-rebuild`) and compare its `dataset_hash` with
`data/lite/v1/manifest.json` (`fdfdd55d…`). The recorded `generator_sources`
digests may differ when code changed after the build. The score and report
commands require no API calls. A new model run requires a new output directory
and makes another set of paid requests.

The earlier `sdb` CLI pipeline (the v0 data and runs, and its design documents,
including the `sdb/0.2` presentation_navigation rebuild) remains a separate research artifact under
`data/legacy/v0`, `runs/legacy/v0` and `docs/legacy`, kept locally and not versioned. Its old all-question metrics are not silently reinterpreted as
branch-composed scores.

The question batching follows TypeSafe's documented
[speculative fan-out](https://docs.typesafe.ai/patterns/fan-out). Its
[State documentation](https://docs.typesafe.ai/concepts/state) supports named,
structured application inputs. Application-decision projection and time scoring
here are SDB's evaluation specification, not a scoring claim made by those docs.


## Integrated evaluation across time scales

All frozen requests use a 2 s recording cadence. The paper's primary summary is normalized log-AUC over the common 0.5–8 s interval range, as declared in `paper/analysis/evaluation_policy.json`. For each family, integrate mean scenario accuracy against `dΔ / (Δ ln 16)`, then average the four family scores equally. The domain spans update rates four times faster and slower than the 2 s recording cadence, assigning each side half the log weight. Equal multiplicative ranges receive equal weight; additivity and continuity determine this logarithmic measure. This is an evaluation principle, not an empirical event-rate distribution or human delay tolerance.

`interval_scoring.evaluate_interval` changes the ratio of each measured response delay to the evaluation interval. This is equivalent to scaling releases, the horizon and tick-valued policies while keeping each successful-attempt duration and postprocessing lag in seconds. Acceptance is recomputed, with dispatch/retry waits excluded under the existing protocol. This replay does not measure service latency under the changed request load or predict another response draw.

The integration uses nested trapezoidal grids in log interval, starting at 128 subintervals and doubling until every scenario metric changes by at most 0.001 percentage point. Nonconvergence at 4096 subintervals is an error. The same normalized weights apply to error partitions and oracle metrics. Current-source judgment in the integrated factorization is the ratio of integrated current-correct and current-source shares. The approximation averages the scenario-wise untimed-times-oracle product, not the product of two overall means.

Main-text figures show both aggregate and family curves. Appendix sensitivity conditions use linear weighting over 0.5–8 s and the five other log ranges formed by lower bounds 0.1, 0.5 and 1 s and upper bounds 4 and 8 s. Fixed 2 s and 8 s comparisons remain diagnostic. A larger interval need not improve accuracy for arbitrary wrong predictions, and 8 s is a controlled slow-update condition, not a validated response budget. The aggregation rule was adopted after inspecting the original hosted passes. The current manuscript averages three complete passes for each of its fifteen settings; the repeats measure variation on the same fixed scenarios, not generalization to new scenarios.

Reproduce the manuscript results without model requests:

```sh
uv run --group paper python paper/analysis/lite_repeated.py
```

Each current `analysis.json` contains `auc.primary` and `auc.sensitivity`. Its `scores`, `raw_wallclock_scores` and `network_adjustment` remain separately labelled 2 s diagnostics. The network estimator fits physical token/latency observations and is used only for supplementary fixed-cadence estimates. `scripts/lite/lite_report.py` generates the recorded-cadence diagnostics; the paper's `lite_reports.py` adds the integrated evaluation and source digests.
