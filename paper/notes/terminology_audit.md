# Terminology audit (2026-09-28)

Compares the main terms of `main.tex` + `appendix.tex` (comments and LaTeX commands stripped, 9,934 words) with full texts of prior papers (reference sections removed). Counts are regex matches; rates are per 10,000 words; "docs" is how many papers use the term at least once.

Corpus:
- **Time-aware evaluation (22 papers, 179k words)**: streaming perception (Li et al. 2020), StreamYOLO, Win Fast or Lose Slow, Gaia2/ARE, Never Stop Thinking, Beyond Scaling, Temporally Blind agents, ProActor, StreamingBench, OVO-Bench, StreamMemBench, Baumann et al. 2011, STACL, SimulEval, SimulMT→SimulST, Age of Incorrect Information, early revocable TSC, real-time RL, RealTimeQA, Full-Duplex-Bench, FreshLLMs, StreamBench.
- **LLM benchmarks (11 papers, 220k words)**: SWE-bench, LiveBench, MMMU-Pro, AppWorld, τ-bench, τ²-bench, AbsenceBench, GAIA, OSWorld, CLEVR, HELM.
- **LLM serving (2 papers)**: DistServe, vLLM.
- **Award abstracts (20)**: the abstracts of 20 award papers, analysed sentence by sentence (the study is not distributed because it reproduces third-party text).

The counting script was not retained.

| Term | Ours n (/10k) | Time-aware /10k (docs) | Benchmarks /10k (docs) | Reading |
|---|---:|---:|---:|---|
| evaluate* | 18 (18.1) | 44.3 (21/22) | 38.3 (11/11) | standard verb; we under-use it |
| score, verb | 10 (10.1) | 1.2 (7/22) | 0.9 (2/11) | rare; 0 of 20 award abstracts use it (evaluate: 37 uses in 16) |
| score, noun | 25 (25.2) | 10.3 (17/22) | 8.1 (9/11) | normal |
| measure* | 13 (13.1) | 10.5 (19/22) | 8.1 (10/11) | normal |
| metric | 0 | 21.4 (20/22) | 9.9 (9/11) | we never call in-force accuracy a metric; Li et al.: "a single metric … streaming accuracy" |
| untimed | 37 (37.2) | 0 | 0 | our coinage; the established contrast is "offline" (Li 2020: 20, OVO-Bench 47, StreamingBench 16, StreamYOLO 18) |
| in force | 92 | 0 | 0 | our concept (title); related established term: streaming accuracy |
| latency | 15 (15.1) | 18.2 (15/22) | 0.0 | standard for response time (serving: 89 uses) |
| delay | 49 (49.3) | 4.8 (14/22) | 0.2 | we use it 3× more than latency; literature is the reverse |
| response time | 10 (10.1) | 0.3 (4/22) | 0.0 | a third synonym for the same quantity |
| release (state published) | 77 (77.5) | 2.1 (9/22) | 4.1 (10/11) | elsewhere means a dataset/code release; in our paper it also names an assembly route option and the MIT-license release |
| frame / time step / status update | 0 | frame 72+66+31…; time step 10 papers; status update (AoI) | — | established names for periodic inputs |
| pace | 35 (35.2) | 0.4 (5/22) | 0 | no standard; frame rate / update rate / interval are used |
| timing ceiling | 6 | ceiling 0.1 (1/22) | 0 | the usual word is oracle (11/35 papers; SimulST: "an oracle system … perfect … latency and quality") |
| replay | 33 (33.2) | 0.4 (3/22) | 0.0 | Li et al. call their counterfactual timing runs "simulation" (simulat*: 17/22) |
| stale | 19 | 0.4 (3/22) | 0 | rare but used in exactly our sense (Li 2020 frames "become stale"; FreshLLMs) — keep |
| reference decision | 30 | reference answer 0.2; ground truth 3.6 (11/22) | ground truth 4.2; gold 3.8 | both conventions exist; reference is standard in MT and for program-computed labels |
| judgment | 25 | 1.0 (7/22) | 0.5 | the trade-off is usually named accuracy/quality vs latency |
| delivery | 15 | — | — | our name for the latency factor |
| trajectory | 7 | 10.3 (5/22, agent action sequences) | 2.0 | may be read as an agent trajectory |
| prefill / decode | 10 / 10 | — | serving 161 / 170 | matches the serving literature |
| episode vs scenario | 7 / 62 | — | — | we use both for the same unit |

Other finding fixed on the way: the appendix still said "the three recorded passes"; it now says "the recorded pass of every setting".
