# Latency grounding and judgment/latency decomposition (2026-09-28)

Evidence for two reviewer questions:
1. Is latency important in these applications, or did the benchmark design make it important?
2. Are judgment and latency really decoupled?

Every source was opened and checked by an independent second pass: does the work exist, does the quote appear verbatim, and does the source support the claim? Wording below follows the verifier's corrections. "(inference)" marks a step that is ours and not stated by the source.

## 1. Literature: latency harms users in real-time, stream-inferred applications

### General limits and closed-loop interaction

- **Miller (1968)**, AFIPS FJCC 33:267-277, doi:10.1145/1476589.1476628.
  - Miller *argues* (reasoned guidance, not measurement) that efficiency drops in steps once a delay passes a threshold, with about 2 s for meaningful replies. He also argues that waiting mid-task causes forgetting and errors.
  - He gives the tightest limit (0.1-0.2 s) to feedback on the user's own ongoing actions.
- **Nielsen (1993)**, Usability Engineering ch. 5 (NN/g excerpt). Design guidance:
  - about 0.1 s feels instantaneous;
  - about 1 s keeps the flow of thought;
  - about 10 s keeps attention.
- **MacKenzie & Ware (1993)**, INTERCHI, doi:10.1145/169059.169431.
  - Task: closed-loop target acquisition.
  - A 75 ms lag has a measurable effect.
  - At 225 ms, movement time rises 64% and errors rise 214%.
- **Liu & Heer (2014)**, IEEE TVCG 20(12), doi:10.1109/TVCG.2014.2346452.
  - An extra 500 ms on four interactive operations reduced activity, data coverage, and the rate of insight.
  - The effect carried over to later low-latency use.
- **O'Hara et al. (2002)**, NUREG-0700 Rev. 2, US NRC human-system interface guidelines.
  - "Information on next procedure": maximum 5.0 s, preferred under 2.0 s.
  - A display that updates slowly relative to the plant "could present data that is not representative of the current state of the plant". This parallels a stale decision in force (analogy is ours).

### Latency tolerance depends on how fast the state changes (supports our rate-of-change parameter)

- **Gergle, Kraut & Fussell (2006)**, CHI, doi:10.1145/1124772.1124968.
  - Task: a collaborative puzzle modelling remote physical collaboration.
  - Delaying the helper's view by 939-1798 ms cost 2.3 s of completion time per extra 100 ms.
  - Tolerated delay shrank as task objects changed faster: 939 ms static, 431 ms moderate, 191 ms fast (trend only), 154 ms very fast.
  - The authors expect that tighter coupling lowers tolerance further. They argue this but did not test it.

### IDE (debugging family)

- **Dunay et al. (2024)**, FSE Companion, doi:10.1145/3663529.3663836 (Meta CodeCompose).
  - Each suggestion "aligns with a given state of the active file" and is invalidated when the user types. This is the decision-in-force situation.
  - 47% of generated suggestions were never displayed.
  - Cutting median latency (multi-line 2000→750 ms, single-line 440→280 ms) raised characters accepted by 16% relative.
- **Murali et al. (2024)**, Proc. ACM SE 1(FSE), doi:10.1145/3643774.
  - "Coding assistants operate in a real-time environment with strict requirements on latency."
  - Developers "were fine with suggestions appearing within 300ms - 500ms, and certainly not beyond 1s".
  - Acceptance fell as latency rose.
- **Saff & Ernst (2004)**, ISSTA, doi:10.1145/1007512.1007523.
  - Continuous background test feedback while editing made student participants three times as likely to finish before the deadline.
  - Participants did not find it distracting.
- Tabachnyk & Nikolov (2022), Google Research blog. Industry report: under 100 ms end-to-end completion budget.
- Usable with corrected wording:
  - Wang et al. (2023), ESEC/FSE, doi:10.1145/3611643.3616280: 44% plurality want under 0.5 s per line; 83% want under 1 s.
  - Mozannar et al. (2024), CHI: waiting and latency costs, hedged.

### Assembly station (procedural guidance inferred from a stream)

- **Chen et al. (2017)**, SEC, doi:10.1145/3132211.3134458.
  - Wearable step-by-step guidance in which "the system infers when a step is completed".
  - The loose bound is 2.7 s (from injected-delay satisfaction ratings).
  - The tight bound is 600 ms (from users' own step-to-signal time).
- **Olguín Muñoz et al. (2021)**, PLoS ONE 16(3), doi:10.1371/journal.pone.0248690.
  - 40 participants, injected delays of 0-3 s.
  - Users slowed their own step execution by 12% at 1.65 s and 26% at 3.0 s, with the added delay itself excluded.
  - The slowdown persisted for a few steps after responsiveness returned.
- **Li et al. (2025)** Satori, CHI, doi:10.1145/3706598.3714188.
  - LLM-driven AR assistant.
  - Users waited about 3 s after each action, which interrupted the interaction.
  - The remaining 2-3 s latency limits it to "non-rapid performance".
- **Xu et al. (2026)** Pro²Assist, IMWUT 10(3), doi:10.1145/3832022.
  - Step-aware timeliness is critical, and later responses are scored lower.
  - 35% of users wanted assistance within 1 s, although most accepted longer.
- **Lee et al. (2002)**, Human Factors 44(2), doi:10.1518/0018720024497844.
  - Collision warning for distracted drivers.
  - An early warning cut collisions by 80.7%; a late warning cut them by 50.0%.
  - The same advice is worth less when late.

### Support call (live speech, agent desktop)

- **PCI SSC (2018)**, Protecting Telephone-Based Payment Card Data v3.0, §6.5.1.
  - Automated pause-and-resume is "integrated with a desktop application used by staff".
  - Its effectiveness relies on the correct steps "at the correct time".
  - A missed pause captures cardholder data that PCI DSS then requires to be protected or deleted. This is a compliance exposure, not an automatic failure.
  - PCI triggers are UI events. The idea that the decision comes from the conversation is our task design, not PCI's.
- **Brynjolfsson, Li & Raymond (2025)**, QJE 140(2), doi:10.1093/qje/qjae044.
  - Deployed LLM agent assist gives "real-time suggestions" during live customer chats (chat, not voice).
  - Productivity rose 15%. The data cover 5,172 agents.
- **Roberts, Francis & Morgan (2006)**, Speech Communication 48(9), doi:10.1016/j.specom.2006.02.001.
  - In simulated phone calls, each increase in the reply gap (0/600/1200 ms) lowered perceived willingness and agreement.
- **Roberts & Francis (2013)**, JASA 133(6) EL471, doi:10.1121/1.4802900.
  - Willingness ratings drop after 600 ms, with a significant step at 700-800 ms.
- **Stivers et al. (2009)**, PNAS 106(26), doi:10.1073/pnas.0903616106.
  - Across 10 languages, speakers minimize silence between turns.
  - Language means lie within about 250 ms of the cross-language mean (+208 ms), measured on polar-question responses.
- **Skantze (2021)**, Computer Speech & Language 67, doi:10.1016/j.csl.2020.101178.
  - Conversational systems "typically have problems with frequent interruptions and long response delays".
- **ITU-T G.114 (2003)**: one-way delay under 150 ms is essentially transparent; 400 ms is the planning limit; highly interactive tasks are affected at lower delays.

### Speech alignment and captions (planned ASR family; the author's typology)

- **Stuart et al. (2002)**, JASA 111(5), doi:10.1121/1.1466868. Hearing one's own speech delayed by 200 ms produced two to three times more disfluencies.
- **Aschersleben & Prinz (1997)**, J. Motor Behavior 29(1), doi:10.1080/00222899709603468. Asynchrony between one's actions and an external stream grows linearly with feedback delay.
- **Chafe, Cáceres & Gurevich (2010)**, Perception 39(7), doi:10.1068/p6465. Joint rhythmic action through a delayed channel (3-78 ms) lags, slows, and then deteriorates.
- **Thompson et al. (2026)**, ASSETS, doi:10.1145/3797867.3829032.
  - Caption delay significantly lowered rated quality and understanding, most for the 7-12 s TV delays. The 2 s ASR drop was small.
  - Hard-of-hearing viewers, who follow the audio, penalized delay more.
- **Ofcom (2013)**, live subtitling statement.
  - User organisations name latency as the biggest problem.
  - The 2013 guidance aimed for no more than 3 s. Measured practice was about 6-8 s.
- **47 CFR §79.1(j)(2)(ii), (j)(3)(ii)**: caption synchronicity is a quality requirement, and lag must not "interfere with the ability of viewers to follow the program".
- Usable with corrected wording:
  - Chesters et al. (2015), JASA 137(2): visual feedback delayed by 200 or 400 ms (not 600 ms) increased errors under delayed auditory feedback.
  - Lee (2002), Meta 47(4): ear-voice span above 4 s was associated with lower quality of the current and next sentence.

### How the literature grounds the paper

- **Typology** (author's hypothesis, grounded).
  - Latency is critical when the state keeps changing while the component computes (Gergle 2006: tolerance shrinks with the rate of change).
  - It is also critical when the person acts on the output in a closed loop or produces output that must stay aligned with it (MacKenzie & Ware; Olguín Muñoz; DAF and synchronization studies; Dunay's state-bound suggestions).
  - All three Lite families and the planned ASR family have both properties.
- **Scale.**
  - Guidance tolerance is 0.6-2.7 s (Chen 2017).
  - The preferred next-procedure response is under 2 s (NUREG-0700).
  - Miller's rule is about 2 s.
  - Conversational gaps become troubling at 0.6-0.8 s.
  - Caption guidance aimed for 3 s or less.
  - Lite's 2 s time step, and the 1-4 s range of the latency-scaling results, sit inside this range.

## 2. Computation from the recorded runs (no model calls)

The exploratory scripts behind this section were not retained; numbers the paper uses are recomputed in `paper/analysis/`.

### Two-factor structure

Let S(answers, latencies) be in-force accuracy.

- S(A, 0) = untimed accuracy U, exactly. At zero latency each answer is in force for exactly its own time step; the maximum difference is 1e-4, from publication jitter.
- S(R, L) = oracle in-force accuracy O.
- S(R, 0) = 1.

### Instant-level partition (exact, not an approximation)

At each instant the decision in force has a source time step j and a current time step i. Two questions classify it:

1. Is the source current (y_j = y_i)?
2. Was the answer right for its source?

Exact results:

- The share of time with a current source equals O (maximum difference 1e-16).
- Stale time equals the time that is outdated but right for its source: pure latency error.
- Incorrect-for-source time equals judgment-only error (current source, wrong answer) plus compound error (outdated source, wrong answer).
- Identity: A = O · U_cur + lucky.
  - U_cur is the accuracy while the source is current.
  - "lucky" is outdated, wrong-for-source time that happens to match the current reference.
- U_cur is close to U (Luna 88.2 vs 87.5).

Share of observed time (%), mean over the six scenarios:

| Setting | Correct | Lucky | Judgment only | Latency only (stale + none) | Both | O | U_cur | U |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Luna low | 51.7 | 1.2 | 7.1 | 35.6 (33.9 + 1.7) | 4.3 | 58.8 | 88.2 | 87.5 |
| Luna none | 29.4 | 0.9 | 43.9 | 11.3 | 14.5 | 73.3 | 40.6 | 39.7 |
| Terra low | 58.3 | 0.5 | 3.7 | 35.1 | 2.5 | 61.9 | 94.2 | 93.3 |
| Terra none | 56.5 | 0.5 | 15.4 | 21.7 | 5.9 | 71.9 | 78.7 | 78.1 |
| Jev | 49.0 | 0.2 | 46.4 | 2.4 | 2.0 | 95.4 | 51.3 | 51.4 |

### Separability

- A / (U·O) lies between 1.004 and 1.051 per setting.
- A − U·O lies between +0.2 and +1.6 points per setting, with a maximum of 4.1 points over the 30 setting-scenario pairs.
- The additive residual U + O − A − 1 (−2 to −17 points) is not the right null. It is negative by construction, because an instant lost to both factors is counted twice.
- The positive deviation from U·O has two sources:
  1. lucky time (0.2-1.2%);
  2. U_cur − U (at most 0.8 points): U_cur weights each answer by its time in force while current, which is short for answers to the last time step before a change. (An earlier note attributed the excess to errors at segment starts; that mechanism was wrong, because the time latency costs after a change holds the answer to the last step before it.)

### Exact crossovers

These come from evaluating the recorded answers at other time-step intervals.

| Pair | Crossover interval |
|---|---:|
| Jev passes Luna low | 1.75 s |
| Jev passes Terra low | 1.52 s |
| Jev passes Terra none | 1.40 s |
| Terra none passes Terra low | 1.77 s |
| Terra none passes Luna low | 3.11 s |

- At 2 s Jev still trails the low-effort settings, but Terra none already leads Luna low (57.1 vs 52.9).
- Above 3.11 s (the last crossing) the order equals the untimed order; checked on the grid up to 20 s.

### Temporal-structure projection

Method:
- O is computed exactly from each model's resampled latencies on synthetic reference schedules of 60 time steps (2 s each).
- Projected A = U × O.
- The tick-level scorer matches the benchmark scorer exactly on all runs.
- The projection of Lite's own schedules gives Luna 52.7 vs 52.9 observed.

| Schedule | K | Luna low | Terra low | Terra none | Jev | Leader |
|---|---:|---:|---:|---:|---:|---|
| sparse | 5 | 78.3 | 84.3 | 72.4 | 50.8 | Terra |
| medium | 11 | 69.2 | 75.5 | 66.8 | 50.2 | Terra |
| uniform, Lite-like | 22 | 52.2 | 59.3 | 56.4 | 49.1 | Terra |
| dense | 40 | 28.5 | 35.4 | 39.9 | 47.3 | Jev |
| bursty | 22 | 55.4 | 61.5 | 56.8 | 49.1 | Terra |
| long-tail dwell | 21 | 55.9 | 62.4 | 57.6 | 49.2 | Terra |
| recurrent A-B-A | 22 | 52.2 | 59.3 | 56.5 | 49.1 | Terra |

Findings:
- The rate of change dominates.
- Bursty and long-tail schedules help slow components by about 3 points, because a short segment can lose at most its own length.
- Recurrence has no effect at these latencies.

Caveat: this is a projection. It assumes that separability holds and that U does not change with the schedule.
