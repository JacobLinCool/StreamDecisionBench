# Family reference intervals: evidence review and reporting proposal

**Status: historical research proposal, audited on 2026-09-29.** This review originally covered the three families then in the manuscript, with presenter voice control assessed separately. The current benchmark includes all four families and uses [normalized log-AUC over 0.5–8 s](../../lite/PROTOCOL.md#integrated-evaluation-across-time-scales). The operating points proposed here have **not** replaced that evaluation policy. Current results are in the [results index](../../lite/results/README.md).

## Conclusion and candidate operating points

Family-specific reference points followed by an equal-weight family average are methodologically coherent. The literature supports different interaction time scales, but does not directly establish a unique environment update interval for any SDB family.

The central gap is that human-factors studies usually measure response delay, waiting experience, or task completion time. SDB's interval Δ controls how often the environment releases a state. These quantities are related but distinct. The following are **literature-informed candidate operating points**, not human-tolerance percentiles, deployment SLAs, or calibrated real-world event frequencies.

| Family | Candidate Δ* | Rationale | Unresolved mapping |
|---|---:|---|---|
| IDE debugging | 1 s | Sub-second to one-second evidence for interactive IDE assistance; an aggressive point within the original 1–5 s exploration. | The closest numerical studies concern code completion, rather than rerun/inspect/delegate action cards. |
| Assembly station | 2 s | Step-triggered wearable guidance is the closest task analogue; two seconds is below one study's loose bound. | It is neither an observed step-interval median nor a no-impact waiting threshold; retain one second as a stricter comparison. |
| Support call | 1 s, tentative | Sub-second conversational gaps already affect listener judgments. | Conversational response, desktop guidance, and recorder control have different deadlines; no study calibrates the full family. |
| Presenter voice control | 1 s, tentative | Miller's next-page guidance and general interaction-continuity guidance provide an analogy for slide advance. | Neither is a modern voice-control experiment, and neither calibrates clip pause or speaker routing. |

Distinct numbers are not a requirement. Three one-second candidates can be reasonable. The reviewed evidence does not justify choosing 4–5 s as a primary reference for a current family; 3–5 s can serve as slower-environment sensitivity conditions. Choose points from task semantics and evidence definitions, not from which model wins. This review did not compute model scores.

## What the primary sources support

The findings below come from the cited source versions and sections. The mapping to SDB is our inference. Guidance, experimental conditions, measured latency distributions, and human judgments must retain their different meanings.

### IDE debugging

**E1 — Murali et al. (2024), AI-Assisted Code Authoring at Scale.** [DOI](https://doi.org/10.1145/3643774); [author version v2, §7.2](https://arxiv.org/html/2305.12050v2#S7.SS2).

- Developer feedback describes suggestions arriving in 300–500 ms as acceptable and recommends not exceeding one second; acceptance also decreases as end-to-end latency increases.
- This is deployment experience and mixed-methods feedback, not a distribution showing that half of users tolerate at most one second.
- Inline code suggestions differ from SDB's debugging action cards. The finding supports a candidate interaction scale, not a validated Δ=1 s for this task.

**E2 — Dunay et al. (2024), Multi-line AI-Assisted Code Authoring.** [DOI](https://doi.org/10.1145/3663529.3663836); [author version, §§4.2, 5.1 and Fig. 7](https://arxiv.org/html/2402.04141v1).

- Optimization reduces median single-line suggestion latency from 440 to 280 ms and multi-line latency from 2000 to 750 ms; accepted characters increase by 16% relative to the previous system. File changes can invalidate suggestions.
- These medians describe system latency, not human tolerance or event intervals. The separate rule counting suggestions displayed for more than 750 ms is an acceptance-measurement rule.
- Streaming, parallelism, and batching change together, so the entire improvement cannot be assigned a pure causal coefficient for a fixed delay reduction.

**E3 — Saff & Ernst (2004), An Experimental Evaluation of Continuous Testing During Development.** [DOI](https://doi.org/10.1145/1007512.1007523); [author paper, §§2, 4, 6](https://homes.cs.washington.edu/~mernst/pubs/ct-user-study.pdf).

The study compares background testing with continuous compilation and a control during editing. It supports ongoing regression feedback but does not manipulate 1/2/5 s response-delay conditions to identify an action-card optimum, and cannot numerically justify a three- or five-second setting.

**Assessment:** one second is a plausible aggressive analogy. Two seconds also deserves evaluation if the task is framed as slower test-run orchestration. The reviewed evidence does not establish that one second is superior for this particular task.

### Assembly station

**E4 — Chen et al. (2017), An Empirical Study of Latency in an Emerging Class of Edge Computing Applications for Wearable Cognitive Assistance.** [DOI](https://doi.org/10.1145/3132211.3134458); [author paper, §5.3, Fig. 16, p. 12](https://www.cs.cmu.edu/~zhuoc/papers/latency2017.pdf#page=12). See the [method extraction](assembly-evidence.md).

- A LEGO/Google Glass guidance experiment with 13 participants derives an approximately 600 ms tight bound and 2.7 s loose bound.
- The tight bound subtracts estimated action-initiation time from mean step-completion-to-signal time. The loose bound combines satisfaction under controlled delays with system overhead. Neither is a percentile or a measured interval between steps.
- Step-triggered guidance closely resembles SDB assembly. A two-second operating point is below the reported loose bound, but does not mean every operator can wait two seconds without cost.

**E5 — Olguín Muñoz et al. (2021), Impact of Delayed Response on Wearable Cognitive Assistance.** [Paper and DOI](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0248690), §§3.2, 4, 5 and Figs. 4, 6–7.

- With 40 participants, controlled-delay conditions of 1.65 and 3.0 s increase users' own step-execution time by approximately 12% and 26%. This slowdown excludes directly waiting for the system.
- The delay is a controlled processing/feedback target, not necessarily that many additional seconds on top of baseline end-to-end latency.
- The results argue against a universal comfortable 3–5 s range. A two-second candidate is a relatively lenient research setting, not a no-effect threshold.

**Assessment:** assembly has the closest task and numerical analogues, but translating response delay into an environment interval remains a benchmark-design judgment.

### Support call

**E6 — PCI SSC (2018), Protecting Telephone-Based Payment Card Data, v3.0.** [Official document](https://listings.pcisecuritystandards.org/documents/Protecting_Telephone_Based_Payment_Card_Data_v3-0_nov_2018.pdf), §6.5.1, printed pp. 36–38.

The document describes automated pause/resume using payment fields, screens, submission, and other desktop workflow events. It supplies no 1/2/5 s tolerance threshold for Δ and does not measure speech-driven recorder decisions. It motivates correctly timed integration; it does not establish that stopping recording one second late is acceptable. The transcript-triggered recorder is an SDB design choice.

**E7 — Roberts & Francis (2013), Identifying a Temporal Threshold of Tolerance for Silent Gaps after Requests.** [DOI](https://doi.org/10.1121/1.4802900); [author paper](https://web.ics.purdue.edu/~francisa/Articles/Roberts-Francis_JASAEL13.pdf), §§2–4, EL472–EL475 and Fig. 1.

- 380 participants hear simulated phone conversations between friends, with the same affirmative answer delayed by 200–1200 ms in 100 ms increments.
- Willingness ratings begin decreasing after 600 ms, with a significant decline between 700 and 800 ms. This is a third-party social judgment, not a support-agent suggestion experiment or recording-protection deadline.
- It directionally favors investigating shorter response scales; within the original 1–5 s exploration, one second has a stronger analogy than five seconds.

**E8 — Roberts, Francis & Morgan (2006), The Interaction of Inter-turn Silence with Prosodic Cues in Listener Perceptions of “Trouble” in Conversation.** [DOI](https://doi.org/10.1016/j.specom.2006.02.001); [paper](https://citeseerx.ist.psu.edu/document?doi=1333d86632e61be810091e75d06512b043e5dfef&repid=rep1&type=pdf), abstract and experimental design.

Ratings decrease under 0/600/1200 ms inter-turn silence conditions, consistent with E7. These three conditions are a contextual check, not a basis for estimating an exact threshold or human P50.

**E9 — Stivers et al. (2009), Universals and Cultural Variation in Turn-Taking in Conversation.** [DOI](https://doi.org/10.1073/pnas.0903616106); [institutional record](https://www.mpi.nl/publications/item66202/universals-and-cultural-variation-turn-taking-conversation); [paper](https://cognitionandculture.net/wp-content/uploads/Stivers_2009_universals.pdf), Results: Distribution of Turn Transitions, p. 10588.

Polar-question responses across ten languages have an overall median gap of +100 ms and a mean of +208 ms, with language medians around 0–300 ms. This is a turn-transition distribution, not utterance length, an ASR update interval, inference latency, or an acceptable-waiting distribution.

**Assessment:** support's one-second candidate has directional support but lacks full-family calibration. Recorder control and service/delivery advice especially differ. Recorder error-exposure duration could be a useful future diagnostic; it is not implemented by this review and should not be replaced by an unsupported “one second is safe” claim.

### General guidance and presenter control

**E10 — Miller (1968), Response Time in Man-Computer Conversational Transactions.** [DOI](https://doi.org/10.1145/1476589.1476628); [scanned paper](https://www.yusufarslan.net/sites/yusufarslan.net/files/upload/content/Miller1968.pdf).

- Page 267 explicitly rejects a universal two-second rule; page 269 gives general two-second guidance for a meaningful reply.
- Topic 10, p. 274 recommends displaying at least the first lines within one second of a next-page request. This is an analogy for slide advance, not a controlled experiment or percentile.
- Other situations allow longer waits, including receiving a new assignment after finishing a complete task. A shared “factory/next step” label does not justify transferring that guidance to ongoing assembly assistance.

**E11 — Nielsen (1993), Response Times: The 3 Important Limits.** [Author's book excerpt](https://www.nngroup.com/articles/response-times-3-important-limits/).

The one-second interaction-continuity guidance is supporting context. It supplies neither family-specific event rates nor P50 values and should not override closer empirical task evidence.

**E12 — Gergle, Kraut & Fussell (2006), The Impact of Delayed Visual Feedback on Collaborative Performance.** [DOI](https://doi.org/10.1145/1124772.1124968); [author dissertation reproducing the study as Chapter 4](https://dgergle.soc.northwestern.edu/resources/Gergle_Dissertation2006.pdf), §4.4, printed pp. 57–61; p. 41 explains its relation to the CHI paper.

- The experiments separately manipulate visual-feedback delay and object-change rate. Salient color changes occur about every 6–8 s, 2–3 s, or less than one second; faster environments reduce tolerated delay.
- In the 6–8 s moderate-change condition, the modeled initial delay breakpoint is approximately 431 ms. Environment cadence and allowable information delay therefore need not be equal.
- This strongly motivates studying family-specific cadence, but does not directly calibrate IDE, assembly, or support thresholds.

Presenter decisions also include clip pause and captions speaker routing. Routing selects the displayed audio source; it does not generate caption text. General 3–5 s caption-text latency limits cannot calibrate the complete composed decision. Miller's analogy primarily concerns slide advance.

## What the reported medians mean

P50 is the median; a mean is a different quantity.

| Reported quantity | Measurement | Empirical P50 of a family update interval? |
|---|---|---|
| Dunay: multi-line 2.0 → 0.75 s | Median system suggestion latency | No |
| Chen: 0.6 / 2.7 s | Derived tight/loose latency bounds | No; neither is P50/P95 |
| Olguín: 1.65 / 3 s | Experimental delay conditions | No |
| Roberts: 0.7 → 0.8 s | Significant change between adjacent rating conditions | No |
| Stivers: median 0.1 s, mean 0.208 s | Conversational turn-transition gap | No |
| Miller: 1 / 2 s | Context-dependent design guidance | No |

This audit found no real-world evidence-arrival or reference-change distribution matching SDB's complete composed decisions. It cannot support “we selected 1/2/1 s from each task's published P50.” It supports declaring literature-informed operating points and showing sensitivity.

## Distinguish cadence, latency, budget, and dwell time

If public state $i$ is released at $i\Delta$ and its usable decision takes $L_i$ seconds after receipt:

- **Δ** is the environment state-release interval. The correct action may span several ticks.
- **L** is the decision component's response latency.
- **B** is a human-response budget or tolerance range for a particular interaction.
- **D** is the dwell time of a constant reference decision.

The literature usually measures L or B. Changing Δ in SDB also changes D. B=1 s implies neither Δ=1 s nor D=1 s. A grace window counting delayed decisions as correct would change the evaluation question; this proposal adds no grace window.

### Audit of the synthetic timeline

Maximal constant-reference segments are computed after composing gold answers under the decision specification. These are synthetic dataset statistics, not external human-factors evidence.

| Scenario | Reference changes | Median segment (ticks) | Candidate Δ* | Median dwell at candidate |
|---|---:|---:|---:|---:|
| Debugging A | 20 | 3 | 1 s | 3 s |
| Debugging B | 21 | 2 | 1 s | 2 s |
| Assembly A | 21 | 2 | 2 s | 4 s |
| Assembly B | 23 | 2 | 2 s | 4 s |
| Support A | 22 | 2 | 1 s | 2 s |
| Support B | 24 | 2 | 1 s | 2 s |
| Presenter A | 24 | 2 | 1 s | 2 s |
| Presenter B | 22 | 2 | 1 s | 2 s |

Reproduce with [timeline_audit.py](timeline_audit.py). [timeline-audit.json](timeline-audit.json) contains segment lengths, source hashes, and frozen-data checks. Medians weight segments equally, rather than time instants. The first six scenarios match the earlier frozen build; both presenter scenarios are included separately in this audit.

Changing Δ has additional consequences:

1. Sixty ticks become 60/120/300 s at Δ=1/2/5 s. The environment slows; this is not merely extra waiting time for the model.
2. Tick-valued rules rescale too. Debugging's 2-tick save grace, 4-tick stalled threshold, and 6-tick stop threshold become 2/4/6 s at Δ=1 s and 10/20/30 s at Δ=5 s.
3. Support A's 4-tick hold threshold changes from eight seconds at the recorded Δ=2 s to four seconds at Δ=1 s. These are synthetic rules, not industry standards.
4. Upstream ASR, evidence availability, and UI/actuator time differ from component inference latency. SDB begins at public evidence; a full human-interaction budget cannot be assigned entirely to model computation.

Changing response budgets while preserving environment cadence requires a separate parameter or metric. Calibrating Δ requires measuring evidence arrivals and reference changes.

## Proposed aggregation, not the current primary score

For model $m$, family $f$, and scenario $e$, evaluate in-force accuracy at the declared family point:

$$
A_{mfe}(\Delta_f^*)=\frac{1}{H_{fe}}\int_0^{H_{fe}}
\mathbf{1}\{d_{mfe}(t)=y^*_{fe}(t)\}\,dt.
$$

Then average scenarios within each family and families equally:

$$
A_{mf}^*=\frac{1}{n_f}\sum_e A_{mfe}(\Delta_f^*),
\qquad S_m^*=\frac{1}{F}\sum_f A_{mf}^*.
$$

The original proposed vector is (1,2,1) s for debugging, assembly, and support. Adding presenter at its tentative point gives (1,2,1,1) s and a separately labeled four-family aggregate. Any adoption requires an explicit evaluation-policy version, declared weights and dataset, and recomputed results. No such adoption is claimed here.

This score would mean average time accuracy under the declared family conditions, not real-deployment accuracy or user satisfaction. Do not pool correct seconds across families: for equal scenario counts, (1,2,1) would give assembly half the pooled weight and each other family one quarter. Normalize within scenarios before averaging families. Do not additionally divide accuracy by Δ or multiply it by seconds. Use identical acceptance and clock rules for all models within each family, and retain uncertainty and assumptions for any secondary network estimate.

## Proposed sensitivity analysis

The historical proposal would treat family-specific points as its main table and common intervals as sensitivity conditions. The current primary policy instead integrates a common log-weighted range; this section records an alternative, not instructions to change the leaderboard.

- A common two-second interval is at least as slow as every candidate and matches the recording cadence.
- A common five-second interval is the slow endpoint of the original 1–5 s exploration, not a universal tolerance limit.
- Slower environments can reduce stale exposure, but accuracy need not be pointwise monotonic. Five seconds is not a strict upper bound for every model.

A proposed appendix figure would show one accuracy-versus-Δ panel per family, identical axes, marked family points, and common 2/5 s points. A separate aggregate panel could show the equal-family curve at common Δ. A family-specific vector has no single common x-coordinate and must be displayed separately. Presenter recordings are now available; this historical memo does not fabricate curves or supply new scores.

A robustness table could compare the original (1,2,1), debugging at two seconds, assembly at one or three, support at two, and common (2,2,2)/(5,5,5). The same principle extends to four families with explicit labels. These contrasts test the weakest extrapolations rather than reporting only a favorable operating point.

Replay must retain recorded answers and second-valued latencies while changing event times, or equivalently scale latency by Δ_recorded/Δ_target. Recompute arrival order, acceptance, and horizon clipping; do not scale an old accuracy directly. This relies on open-loop, tick-valued states and an assumption that recorded latency remains representative under a different request rate. It does not measure service performance under that new load.

## Supported claims and calibration gaps

| Claim | Assessment |
|---|---|
| Different interactions need not share a universal two-second latency requirement. | Supported. |
| Declared family points can be evaluated and averaged equally. | Coherent method with explicit points, weights, and replay assumptions. |
| The reviewed papers directly identify optimal SDB update intervals. | Unsupported; latency-to-cadence mapping is uncalibrated. |
| (1,2,1) is a literature-informed candidate benchmark setting. | Defensible proposal with unequal extrapolation strength, especially weak for support. |
| The values are human-tolerance P50s or no-impact thresholds. | Unsupported. |
| 3–5 s is a universally reasonable primary setting. | Unsupported; usable as sensitivity conditions. |

To turn candidate points into empirically calibrated intervals, measure evidence-arrival and reference-change distributions for the actual IDE action card, assembly station, support desktop, and presenter UI, then manipulate decision delay in those interfaces. Estimate event cadence and tolerated response delay separately. The reviewed evidence motivates discussing candidate family points; it does not establish exact seconds as task standards.
