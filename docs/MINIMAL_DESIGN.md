# StreamDecisionBench: design rationale and acceptance criteria

StreamDecisionBench measures whether a model maintains an appropriate next action as a task context changes. Low-latency decision models motivate the benchmark; “System 1” is a motivation, not a diagnosis of a model's internal cognitive mechanism.

The current executable contract is the [Lite protocol](lite/PROTOCOL.md). This document explains nine design conditions and a proposed shortcut-resistance audit. It does **not** claim that the development set has passed a held-out audit. The published primary score is normalized log-AUC over update intervals of 0.5–8 seconds; segment-balanced accuracy below is a design diagnostic, not the leaderboard score.

“Minimal sufficient” has a restricted meaning here: within this task scope and decomposition, the conditions jointly support the measurement, and removing any condition permits a concrete failure of one of its claims. This is not a universal minimum number of benchmark requirements, a novelty claim, or a guarantee of publication quality. C4 requires empirical acceptance; the other conditions define the task and evaluation contract.

## Nine design conditions

| ID | Condition |
|---|---|
| **C1** | Each task asks the model to select a next action under given rules. |
| **C2** | At each instant, the reference action is uniquely determined by those rules and the public state available then. |
| **C3** | The correct action depends on task context beyond the latest observation. |
| **C4** | Prespecified shallow baselines must remain below a registered competence threshold on an untimed evaluation of the complete held-out test set. |
| **C5** | The evaluation includes episodes in which the reference action changes. |
| **C6** | Observation release times do not wait for model inference to finish. |
| **C7** | A new output takes effect only when a usable result is actually delivered. |
| **C8** | An accepted output remains in force until another accepted output replaces it. |
| **C9** | The evaluator accumulates the duration for which the in-force output differs from the contemporaneous reference. |

C1 supplies the action semantics. The remaining conditions constrain the reference, information dependency, acceptance, clock, and scoring. Keeping these separate makes each requirement inspectable.

## Measurement and sufficiency

The current interface presents textual task states, including natural-language messages and structured fields. An episode's external events are fixed in advance. The output recommends the action appropriate now; it neither predicts unseen events nor changes subsequent observations. A standing recommendation to send an email, for example, does not mean that the consumer sends another email every instant.

Let the task rules be $P$, the complete public state at time $t$ be $S(t)$, and the reference action be

$$
y^*(t)=P(S(t)).
$$

This notation does not require a programmatic rule implementation. Executable policies and reproducible human adjudication are both possible, provided the public state actually supports the judgment. C1–C3 define a checkable contextual action task, C4 tests the specified shallow methods, and C5 makes updating a substantive part of the evaluation.

For request $i$, let $q_i$ be its dispatch time, $a_i$ its usable answer, and $c_i\geq q_i$ its delivery time. C6 fixes the external clock; C7 determines when an answer becomes usable; C8 determines the standing output between deliveries. After filtering by the protocol's acceptance rule and ordering accepted commits,

$$
d(t)=a_{k(t)},\qquad k(t)=\max\{i:c_i\leq t\}.
$$

Before the first accepted answer, the output is $\bot$ and incurs unit error. A usable answer meets the format contract; it need not be correct. Invalid outputs do not replace the standing decision. The current four-family harness pipelines requests with 32 workers and rejects completions older than the latest committed source state. The exact dispatch, tie-breaking, and commitment rules are fixed by the [protocol](lite/PROTOCOL.md), rather than inferred from this simplified notation.

C9 gives episode error duration over horizon $T$:

$$
E=\int_0^T\mathbf{1}[d(t)\ne y^*(t)]\,dt,
\qquad A=1-E/T.
$$

Partitioning at reference changes and accepted delivery times yields an exact integral of these piecewise-constant trajectories. An optional diagnostic can balance maximal constant-reference intervals $I_{e,k}$:

$$
L_e=\frac{1}{K_e}\sum_{k=1}^{K_e}
\frac{1}{|I_{e,k}|}\int_{I_{e,k}}
\mathbf{1}[d(t)\ne y^*(t)]\,dt.
$$

This diagnostic prevents a long easy interval from dominating short transitions. The current primary score instead integrates family-balanced in-force accuracy over the registered logarithmic update-interval range. Recording-cadence reports, segment diagnostics, and untimed accuracy answer different questions and must retain their labels.

Transport failures are handled on a documented normalized retry timeline: the successful attempt's duration and recorded commit lag remain, while excluded failed attempts are retained in raw-clock diagnostics. This reconstruction is not a claim that the physical endpoint completed faster. Neither clock permits backdating an answer to its request time.

Together, the conditions define a computable contextual decision measurement. Only a successful C4 audit supports the additional claim about the specified shallow baselines. A finite action set can still be represented as classification; that fact neither invalidates the task nor establishes novelty.

## Necessity through deletion witnesses

The following witnesses retain finite outputs, public rules, observations, delivery records, and an evaluator while relaxing only the indicated condition. C1 is the condition that gives the output its next-action meaning. The preceding equations describe the complete construction; they are not additional axioms silently retained in a deletion test.

| Removed condition | Counterexample permitted by the remaining conditions | Lost claim |
|---|---|---|
| **C1** | Keep context and timing, but output a topic label. | Correct input understanding need not imply an appropriate next action. |
| **C2** | Give different references to the same public state using hidden facts. | Measured errors mix decision failures with unavailable information. |
| **C3** | Every new message contains a complete independent problem. | The stream may be difficult without requiring accumulated context. |
| **C4** | A context field exposes a keyword-to-answer lookup. | Context dependency holds, yet a specified shallow method can achieve perfect untimed accuracy. |
| **C5** | The reference never changes within an episode. | One correct initial answer can remain appropriate indefinitely. |
| **C6** | Pause the world whenever inference starts. | Inference cannot make a decision stale. |
| **C7** | Backdate an answer delivered two seconds later to its dispatch time. | The evaluator erases delivery delay. |
| **C8** | Clear an answer immediately after delivery. | Almost all integrated loss becomes unanswered time, obscuring the consequences of holding a decision. |
| **C9** | Record the full trajectory but score only individual answers. | A wrong decision lasting 0.1 seconds and one lasting 1 second can receive the same score. |

These witnesses establish scoped irreducibility, not the inferiority of other research contracts. C4 can be omitted when the claim is limited to timed accuracy. C8 describes the chosen standing-decision interface; decisions with explicit expiry can support a different valid task.

### A trajectory that separates answer accuracy from duration

Suppose A is initially in force, the reference changes to B at one second, and changes back to A at two seconds.

| Interval (s) | Reference | In-force decision | Error duration (s) |
|---|---|---|---:|
| 0–1 | A | A | 0 |
| 1–1.8 | B | A | 0.8 |
| 1.8–2 | B | B | 0 |
| 2–2.2 | A | B | 0.2 |
| 2.2–3 | A | A | 0 |

The model answers both changed states correctly, both answers are correct when delivered, and the final answer is correct. Nevertheless, one of the three seconds uses an incorrect standing decision: in-force accuracy is 66.7%. This illustrates C6–C9 without assuming that prior work scores only final answers.

## Auditing contextual dependence and shallow methods

### C3: demonstrate contextual dependence

Hold the rules, choices, and latest message fixed while changing relevant task state. For example, the same request to reset an account should require different actions before and after identity verification. This is a way to verify C3, not an additional mandatory generation method.

Let $\phi(x)$ expose the fixed rules, choices, and latest message but omit the relevant context. Within each group $g$ having identical $\phi(x)$, let $n_{g,a}$ count examples whose semantic reference action is $a$. A deterministic predictor restricted to $\phi(x)$ has maximum accuracy

$$
U_\phi=\frac{\sum_g\max_a n_{g,a}}{\sum_g\sum_a n_{g,a}}.
$$

Two equally weighted cases with identical restricted inputs and different actions yield a 50% bound, also bounding expected randomized accuracy. This applies to the controlled slice, not the whole dataset. Pair identifiers, ordering, option encodings, and other channels must not leak the omitted context; labels must align by semantic action.

### C4: test prespecified shallow methods on complete inputs

A retriever that sees the full state is not subject to the preceding restricted-input bound. Its performance requires a separate empirical audit. Fix the baseline set $B$ before sealing the test set, covering lexical matching, BM25 or literal nearest neighbors, embedding nearest neighbors over full inputs, and formatting or fixed-label cues. Record model versions, accessible fields, retrieval corpus, and tuning. Exclude test scenarios and their variants from the retrieval corpus. Efficient solvers that genuinely parse state and execute the policy are valid competitors.

Split by base scenario, keeping paraphrases and counterfactual variants together. Evaluate the complete held-out test set rather than a selected difficult slice. The original C4 proposal uses an untimed, reference-interval-balanced state accuracy $A_b$, averaged across episodes. That acceptance diagnostic is distinct from the current log-AUC leaderboard and its separately reported untimed state accuracy.

Register a competence threshold $\tau$, grouped uncertainty procedure, and multiple-comparison control before testing. A proposed acceptance condition is

$$
\max_{b\in B}\operatorname{UCB}^{\mathrm{sim}}_{95\%}(A_b)<\tau,
$$

where the upper bounds have simultaneous coverage over the fixed baseline set. No universal threshold follows from the word “decision.” Without a registered threshold and completed test, C4 remains unverified. If a baseline reaches the threshold, narrow the claim or repair the deficient task construction; do not remove the baseline. Report its actual timed performance separately: an old answer can become correct again, so untimed state accuracy is not a universal upper bound on every timed trajectory.

Paraphrases, single-fact changes, and irrelevant updates can support this audit. A paraphrase that changes when evidence arrives need not preserve the entire reference trajectory. These are useful controls rather than additional irreducible conditions. The current eight development scenarios and single-pass model results do not establish held-out shortcut resistance.

## Relationship to prior evaluation contracts

The [literature catalog](LITERATURE.md) provides the wider bounded reading set. These comparisons concern the cited evaluation contracts; absence of a measure in those sections is not evidence that an author's entire system lacks the corresponding capability.

| Work | Established contract | Specific relationship to SDB |
|---|---|---|
| [Incremental processors](https://aclanthology.org/2011.dnd-2.10.pdf), §§3.1, 6.3 | Latest-output storage, intermediate correctness and revision, and timed consumer polling. | Holding the latest output has precedent. SDB applies measured delivery times to standing next-action decisions. |
| [Belief-R](https://aclanthology.org/2024.emnlp-main.586.pdf) / [DeltaLogic](https://arxiv.org/pdf/2604.02733) | Updating or preserving conclusions under added premises or controlled edits. | SDB measures how long an old action remains inappropriate before its replacement arrives. |
| [CoPE](https://arxiv.org/html/2512.18027) | Policy-conditioned finite labels and contrastive policy interpretation. | Action terminology alone is not a distinction; SDB needs the changing-context and delivery contract in C5–C9. |
| [Gaia2](https://arxiv.org/html/2602.11964v1) | Asynchronous events and a write-action trajectory verifier checking causal and temporal constraints, with default/instant latency analysis. | Its action verification differs from a continuously prescribed action and integrated mismatch duration. Real-time events and latency ablations already have precedent. |
| [Win Fast or Lose Slow](https://proceedings.neurips.cc/paper_files/paper/2025/file/ddaec864ba433e8889ab08dcf5c26e55-Paper-Conference.pdf) / [STAR](https://arxiv.org/pdf/2603.09337) | Evolving environments and reward or strategic performance after delayed actions. | SDB fixes external events and scores time spent following a specified policy, rather than complete strategic control. |
| [ProActor](https://aclanthology.org/2026.acl-long.832.pdf) | Action readiness and valid opportunity intervals measured in dialogue turns. | SDB converts delivery delay into physical time spent holding an inappropriate decision. |
| [StreamingBench](https://arxiv.org/html/2411.03628) | Proactive-output first-trigger timing under per-second polling. | First-trigger timing does not by itself measure a standing action between deliveries. |
| [ReactiveBench / Never Stop Thinking](https://arxiv.org/html/2609.17416v1) | Partial-input events, interruption/resumption, verifiable completion, anticipation, and time-to-first-response measurements in seconds. | Seconds-based timing is shared prior art. SDB explicitly measures delivery, holding, and mismatch duration. |
| [TicToc](https://aclanthology.org/2026.findings-acl.1848.pdf) | Whether elapsed conversational time warrants refreshing information. | SDB asks when an action based on already released evidence actually takes effect. |
| [Age of Incorrect Information](https://arxiv.org/pdf/2012.13214) | Time-average mismatch and age-weighted costs of persistent error. | Integrated mismatch has precedent. SDB's error duration is not itself the age-weighted AoII quantity. |

An inspectable distinction is whether identical per-state answers, delivered at different times, leave different amounts of incorrect standing-decision time. SDB labels that interval directly under a prescribed policy. This distinction does not depend on input modality and does not support a global-first claim.

## Evidence needed for each condition

| Condition | Evidence a reviewer can inspect |
|---|---|
| C1 | Concrete examples connecting task rules to next actions; acknowledgment that finite actions can be encoded as classification. |
| C2 | Rule/reference consistency checks and release times of decisive evidence. |
| C3 | Controlled context pairs and the restricted-input predictor bound, with leakage checks. |
| C4 | Complete held-out baseline results, registered threshold, and uncertainty procedure. |
| C5 | Reference transitions and dwell-time distributions. |
| C6 | Release logs showing that inference does not pause external events. |
| C7 | Dispatch, receipt, and commit records, plus checks against backdating. |
| C8 | Standing-output traces between accepted commits and the consumer contract. |
| C9 | Exact integral checks, identical-answer/different-delivery controls, and justification of the task's time scale. |

## Connection to the implementation

The Lite evaluator computes exact piecewise-constant duration rather than the retired tick-sampled prototype's approximation. The [protocol](lite/PROTOCOL.md), task definitions, frozen runs, and [results index](lite/results/README.md) are the authoritative implementation evidence. This rationale does not supersede their versioned contracts.

Retiming fixed recorded answers can isolate the effect of delivery delay under the declared replay assumptions. It does not establish the complete online counterfactual for a memoryful model whose future answers would change after skipped or reordered states. New data, new clocks, new acceptance rules, and new online runs require separately identified evidence.
