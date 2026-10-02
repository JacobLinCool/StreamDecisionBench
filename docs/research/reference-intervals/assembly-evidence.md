# Assembly reference-interval evidence

## Scope and definitions

Source audit dated 2026-09-29, supporting the [historical reference-interval proposal](README.md).
This record compares Chen et al. (2017) and Olguín Muñoz et al. (2021): what their 600 ms,
2.7 s, 1.65 s and 3 s quantities measure, and how far they can justify a candidate two-second
environment interval. Task, delay definition, human outcome, percentile meaning and transfer to
synthetic event cadence are assessed separately. The proposal is not the current primary evaluation policy.

## Original-source records

### Chen et al. (2017)

- `paper_id`: `chen2017empirical`; SEC 2017, DOI 10.1145/3132211.3134458.
- `primary_url`: [Author-hosted paper](https://www.cs.cmu.edu/~zhuoc/papers/latency2017.pdf#page=12).
- `read_depth`: methods/results-focused; §5, especially §5.3; visually checked Figure 16 (p. 12).
- `core_claims`: the authors propose a 600 ms tight bound and 2.7 s loose bound for stepwise guidance, expressly as guidelines.
- `evidence_notes`: 13 college students; LEGO/Google Glass; four tasks of 7–9 steps. Wizard-of-Oz recognition isolated delay from recognition errors. Injected delays were 0/1/1.5/2/3/4/5 s, with approximately 0.7 s additional expert/network/rendering latency. Satisfaction remained near 4/5 through 2 s injected delay: hence 2.7 s total. Separately, approximately 0.7 s **mean** completion-to-gesture time minus 0.1 s motor initiation yielded 0.6 s.
- `limitation_notes`: small convenience sample; subjective satisfaction and inferred ideal timing; no percentile tolerance estimate or natural event-interval distribution. Bounds were transferred from LEGO to drawing/sandwich.
- `relevance_notes`: direct precedent for feedback after inferred assembly-step completion.
- `confidence_notes`: high extraction confidence; low confidence in a universal threshold.
- `open_questions`: uncertainty around individual bounds; transfer to real assembly stations.

### Olguín Muñoz et al. (2021)

- `paper_id`: `olguin2021impact`; PLOS ONE 16(3):e0248690, DOI 10.1371/journal.pone.0248690.
- `primary_url`: [Publisher full text](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0248690).
- `read_depth`: experimental design and execution-time results; §3.1–3.2, §4.1, §5; visually checked Figures 4 and 6 (PDF pp. 9, 13); Table 2 (p. 13).
- `core_claims`: mean participant execution slowed 12% under the 1.65 s condition and 26% under 3 s, excluding system waiting (§5).
- `evidence_notes`: 40 undergraduates; desktop LEGO addition/removal task. Conditions: no added delay, 0.6/1.125/1.65/2.175/2.7/3 s; blocks of 4/8/12 steps. Figure 4b's target delay spans **processing plus holding**, not simply extra sleep; zero means no added holding. Execution estimation corrects for completion-detection sampling. Figure 6 reports means/SEM, with physical execution roughly 4.5–7 s; Table 2's delay effect: F(6,234)=15.52, p<0.0001.
- `limitation_notes`: simple, error-free laboratory task; no latency-tolerance P50, ecological event cadence, or tested 2 s condition.
- `relevance_notes`: latency changes human work pace; satisfaction alone misses this cost.
- `confidence_notes`: high extraction confidence; benchmark transfer indirect.
- `open_questions`: consequences for skilled workers, complex rework, and independent sensor streams.

## Implication for the benchmark (our inference)

**A 2-second assembly interval is defensible as a deliberately permissive research operating point, not as an empirically estimated event interval or a no-harm threshold.** The studies motivate the relevant response-time scale but do not identify a unique benchmark tick.

| Candidate | Interpretation |
|---|---|
| 1 s | Stricter sensitivity setting; better suited if the declared goal is prompt guidance. These papers do not establish it as harmless or optimal. |
| 2 s | Reasonable primary candidate within the broadly studied seconds-scale region, while retaining a visible speed requirement. Declare it as a benchmark choice. |
| 3 s | Useful lenient sensitivity point; evidence does not justify calling it adequate for preserving performance. |
| 4–5 s | Appendix stress/sensitivity settings only; these sources provide no affirmative basis for adopting them as the normal assembly reference. |

Response latency, physical action duration, input sampling period, and benchmark event spacing are different quantities. Here, Δ determines when synthetic evidence becomes available and rescales all tick-valued events. Therefore neither paper alone calibrates Δ; a direct empirical calibration would require task/event traces or a user study matching this benchmark's interaction model. Equal-weight family aggregation does not remove that calibration limitation.

The papers' findings are compatible: tolerable subjective waiting can coexist with slower physical performance. Neither result should be presented as an assembly P50/median environmental update rate.
