# Part A bibliography notes: directly related work

Checked on 2026-09-27. BibTeX is in `part_a.bib`. Raw metadata snapshots, the cross-check script and its outputs are in `sources/`.

Each entry below gives the citation key, what the work measures (checked against the paper text, including the sections that `docs/MINIMAL_DESIGN.md` cites), and whether `docs/LITERATURE.md` (LIT) and the comparison table in `docs/MINIMAL_DESIGN.md` (MD) describe it accurately. Problems the paper must not inherit are marked **FLAG**.

## Status at a glance

| Key | Work | Version cited | Metadata | Content checked |
|---|---|---|---|---|
| `froger2026gaia2` | Gaia2 | ICLR 2026 (Oral), OpenReview | verified | §1–5, B.2.1 |
| `kang2025win` | Win Fast or Lose Slow | NeurIPS 2025 | verified | §1, §3.1–3.4, §5.3 |
| `li2026beyond` | STAR / Beyond Scaling | arXiv v1 | verified | §1, §3–4, App. C |
| `cheng2026your` | TicToc | Findings of ACL 2026 | verified | §1, §3–4 |
| `li2026never` | Never Stop Thinking / ReactiveBench | arXiv v1 | verified | §1–3, §7, App. B, G |
| `ding2026proactor` | ProActor | ACL 2026 Long | verified | §1–3.2, App. B.3, C |
| `lin2024streamingbench` | StreamingBench (arXiv, 8 authors) | arXiv v1 | verified | §3–4.1, App. A.2 |
| `lin2026streamingbench` | StreamingBench (ICASSP 2026, 10 authors) | ICASSP 2026 | verified (Crossref) | **UNVERIFIED**: IEEE paywall, full text not read |
| `liu2026streammembench` | StreamMemBench | arXiv v2 | verified | §1–3, Table 4 |
| `wilie2024belief` | Belief Revision / Belief-R | EMNLP 2024 | verified | §1, §3–5 |
| `dhanda2026deltalogic` | DeltaLogic | arXiv v1 (+ workshop note) | verified | full paper (short) |
| `chakrabarti2025cope` | CoPE | arXiv v1 | verified | §1, §3–6 |
| `zentropi2026enabling` | Zentropi, "Enabling Streaming Classification" | blog (@misc) | verified (page + JSON-LD) | full post |

No entry is unverified at the metadata level. Every title and author list matches its source record (`sources/verify_bib_output.txt` ends in `ALL_OK`). All 11 DOIs resolve through doi.org (`sources/doi_resolution_output.txt`). Gaia2 and the Zentropi blog have no DOI, so they carry a URL only.

## Per-work notes

### 1. Gaia2: `froger2026gaia2`

- **Source.** Metadata comes from arXiv:2602.11964 (`/bibtex`, `/abs`) and OpenReview note `9gw03JpKK4`, whose venue is "ICLR 2026 Oral" and whose booktitle is "The Fourteenth International Conference on Learning Representations". The arXiv v1 PDF header reads "Published as a conference paper at ICLR 2026", so the ICLR version is cited. OpenReview spells one author "Pierre Menard"; arXiv and the PDF spell it "Pierre Ménard", and the bib follows the PDF. The arXiv DOI (10.48550/arXiv.2602.11964) is recorded in a bib comment rather than a field, so that the entry does not mix versions.
- **What it measures.** Gaia2 evaluates LLM agents in ARE, an event-driven simulated smartphone environment (12 apps, 101 tools) whose clock keeps advancing while the model generates (§3, "Asynchronicity and time"). It has 1,120 scenarios over Execution, Search, Ambiguity, Adaptability, Time, Noise and Agent2Agent. Each scenario gets a binary pass@1 from the ARE Verifier, which matches every agent write action to an oracle write-action DAG. The verifier checks consistency, causality, a timing tolerance window centred on the oracle's relative time, and completeness (§4.3, B.2.1). §5.2 compares the default mode with an "instant" mode that removes generation latency; the paper reports Time-split gains such as GPT-5 (high) rising from 0.0% to 34.4% and "inverse scaling in the Time capability".
- **LIT.** Accurate. The venue is missing: the entry should say ICLR 2026 (Oral), not just "2026".
- **MD.** Accurate: asynchronous events, causal and time-window checks on write actions, and the default/instant latency analysis are all in the cited sections.
- **FLAG.** (a) Gaia2 is not graded on final outcome only. It verifies each write action, and B.2.1 argues this is equivalent to comparing states after every write and can separate self-corrected trajectories. SDB must not describe Gaia2 as scoring the final answer. What Gaia2 lacks is a *duration* of wrong standing decisions, because a scenario either passes or fails. (b) §5 charges measured generation time to the simulated clock ("simulated generation time — pausing during responses and resuming with a matching time offset"). Gaia2 therefore realises C6 through simulated time, not wall-clock replay. (c) §5.2 already concludes that the results underscore "the need for adaptive compute — using shallow models and performing deeper reasoning only when necessary". The claim that fast models can beat slow reasoners in time-sensitive tasks is prior work.

### 2. Win Fast or Lose Slow: `kang2025win`

- **Source.** NeurIPS 2025 proceedings `.bib` export and abstract page. The DOI is 10.52202/085713-5044, and the volume, which the export gives as "38, Main Conference", is normalised to 38.
- **What it measures.** The paper formalises "latency-sensitive agent decision tasks", in which reward is evaluated on the environment as it stands when the action lands, R(a_{t+Δt} | E_{t+Δt}) (§3.1, Eq. 5). It introduces two benchmarks:
  - **HFTBench** (§3.2) replays historical per-second market data, gives agents observations at 1-second intervals and triggers inference only when the bid–ask margin exceeds a threshold. Execution prices are assigned by response-time rank under a linearly decaying price model, and the score is daily yield.
  - **StreetFighter** (§3.3) runs on DIAMBRA, scores with ELO, and caps the effective rate at about 5 actions per second (§5.3).

  The paper also proposes FPX, a system for mixed FP8/FP4 precision inference.
- **LIT.** Accurate. It omits that FPX, an inference-speed method, is a main contribution, and that the paper claims to be "the first to systematically formulate and investigate the latency–quality trade-off".
- **MD.** "推理期間世界變化，以交付後的收益或策略表現衡量行動" is accurate. **FLAG:** "既有行動具有延續效果" is not stated anywhere in Win Fast §3.1–3.3; it is an inference. It does fit STAR (see 3), so attribute it to STAR only or drop it. Also, in HFTBench latency acts through a response-time price model. "The world keeps moving during inference" is a fair gloss for StreetFighter but only an abstraction for HFTBench.
- **FLAG (tick scale).** HFTBench already uses 1-second observation intervals and StreetFighter about 200 ms per action. SDB's 1–2 s ticks are therefore not a differentiator; the differentiator has to be the scored quantity.

### 3. STAR / Beyond Scaling: `li2026beyond`

- **Source.** arXiv:2603.09337 v1 (10 Mar 2026), with primary class cs.CV as listed. OpenReview holds a record (`ePQDaLk5wd`) with no venue. Crossref and OpenReview show no published version. The author name "Yanxian BI" is capitalised as on arXiv.
- **What it measures.** STAR is a 1v1 zero-sum wargame on a hex grid with fog of war, in two modes. The turn-based mode allows "unlimited deliberation" (§4.2). The real-time mode (§4.3, App. C.2) runs an asynchronous polling loop that "does not await a discrete turn signal", and actions incur latency proportional to their complexity. Metrics are win rate, standard ELO and PWER, an ELO weighted by unit preservation and time efficiency (§3). The headline finding is a "strategy–execution gap": reasoning models lead in turn-based play, while faster instruction-tuned models lead in real time.
- **LIT.** Accurate.
- **MD.** Accurate. App. C.2 (movement delays proportional to path distance, animation locks) supports "既有行動具有延續效果" for STAR. The contrast MD draws is correct: STAR is interactive, agent actions change the world, and scoring is by match outcome, so no per-interval reference action exists.
- **Note.** STAR is an unreviewed preprint.

### 4. TicToc / Your LLM Agents are Temporally Blind: `cheng2026your`

- **Source.** ACL Anthology `.bib` for `2026.findings-acl.1848` (fields copied, key renamed); DOI 10.18653/v1/2026.findings-acl.1848.
- **What it measures.** TicToc asks whether an agent's choice between calling a tool again and answering from context matches human preferences once real time has passed. It has 76 scenarios at low, medium or high time sensitivity and 1,864 trajectories. Each trajectory comes in three versions with a small, medium or large elapsed gap before the final question, giving 5,592 samples, of which 3,016 remain after ambiguous human preferences are dropped (§3.3–3.5). Timestamps are synthetic ISO-8601 strings in the context, and models are evaluated with and without them. The best normalised alignment rate is below 65%.
- **LIT.** Accurate.
- **MD.** Accurate: it studies the refresh decision, not when a correct action takes effect.
- **FLAG (useful contrast for C2).** TicToc's references are aggregated human *preferences*, with uncertain samples excluded, not rule-determined answers. Elapsed time is a static input feature; the model's own latency never enters the score.

### 5. Never Stop Thinking / ReactiveBench: `li2026never`

- **Source.** arXiv:2609.17416 v1. The arXiv submission history dates v1 to 11 Jul 2026 even though the identifier is 2609; this is presumably a delayed announcement and does not affect the citation. No venue version was found.
- **What it measures.** The paper builds an interrupt-and-resume orchestrator that lets an unmodified text LLM think while listening or speaking in a voice pipeline (§2). §2.2 and App. B measure live-pipeline latency. ReactiveBench (§3) has two tracks:
  - **Track A** has 120 scripted interactive scenarios scored against 688 pre-registered binary requirements. Its interrupts are "simulated at the transcript level" (§7).
  - **Track B** has 200 verifiable streaming tasks (GSM8K, SQuAD, HotpotQA and early-entity tool tasks), delivered "at speech rate through a discrete-event simulator". It is scored by exact correctness plus behavioural metrics: tool-lead (seconds before the end of the utterance) and speech coverage (§3.2, App. G).

  Most of the paper is a five-stage training study.
- **LIT.** Accurate.
- **MD.** Accurate (partial-input events, interrupt/resume, verifiable completion, early tool calls).
- **FLAG.** (a) ReactiveBench already measures timing in *seconds*, both as tool-lead and as time-to-first-response. SDB cannot claim that prior streaming benchmarks lack second-level timing. The honest distinction is that ReactiveBench scores final correctness plus anticipation timing, not how long a delivered decision stays wrong. (b) §2.1 explicitly uses a dual-process "System 1 reply … System 2 continues reasoning" design. If the SDB paper uses a "System 1" framing, it should cite this work.

### 6. ProActor: `ding2026proactor`

- **Source.** ACL Anthology `.bib` for `2026.acl-long.832` (ACL 2026, Volume 1: Long Papers); DOI 10.18653/v1/2026.acl-long.832.
- **What it measures.** At each dialogue turn, the agent outputs candidate actions, each marked ready or not. These are compared with *reference actions* and *reference-ready ranges*, the sets of turns in which an action is ready (§3.2). Metrics cover action consistency (AC, Max AC, Difference) and timing (Proactive Timing, Fault Trigger Rate, Ready Action Rate). Training uses turn-level GRPO on two auto-annotated datasets, ABCD+ and Home Loan.
- **LIT.** Accurate.
- **MD.** "每個對話回合的 action readiness 及有效機會區間" is accurate for §3.2. **Pointer fix:** App. C describes the baselines (training-free prompting and SFT), which only supports "turn by turn". The metric definitions are in §3.2, which defers further metrics to App. A (not read). Cite §3.2 rather than App. C for the metrics.
- **FLAG (useful contrast for C2).** The references come from "an oracle LLM annotator … with access to the full conversation — including future turns" (hindsight), and the authors call them "not ground truth" (§3.1). Time is measured in dialogue turns; model latency is not a variable.

### 7. StreamingBench: `lin2024streamingbench` (arXiv) and `lin2026streamingbench` (ICASSP 2026)

- **Source.**
  - **arXiv version.** arXiv:2411.03628 v1, with 8 authors.
  - **Conference version.** Found through web search and confirmed through the Crossref record for DOI 10.1109/ICASSP55912.2026.11463959: "ICASSP 2026 - 2026 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)", Barcelona, pp. 12147–12151.
  - **Differences.** The ICASSP version has **10 authors**; it adds Haoxuan Cheng and Ziyue Wang. IEEE's record spells the title "Streamingbench", but the bib keeps the paper's own "StreamingBench".
  - **Access.** The IEEE page returned an empty body (HTTP 202) to direct fetches, and the full text is paywalled. The ICASSP *content* is therefore **UNVERIFIED**. At 5 pages it almost certainly lacks the appendix MD cites.
- **What it measures.** StreamingBench tests streaming video understanding in MLLMs. It has 18 tasks, 900 videos and 4,500 QA pairs, with five questions per video at different timestamps. Protocol (§4.1, App. A.2):
  - Every task except Proactive Output (PO) is converted to an offline one: the video is clipped at the question's timestamp and scored by multiple-choice accuracy.
  - PO polls the model every second in a [-4, 4] s window around the ground-truth moment (up to 10 polls). A question counts as solved if the first "yes" lands within two seconds of the ground truth.
  - Model compute time plays no part in scoring.
- **LIT.** The task description is accurate. However, "即時理解" is the name of a task category ("real-time visual understanding"), and the protocol is offline, so the paper must not imply that StreamingBench charges inference latency. The version note "2026 會議版本" is correct but should read ICASSP 2026 and mention the changed author list.
- **MD.** Accurate: PO is scored by the gap between the first trigger and the reference moment, measured on polling seconds in video time.
- **Recommendation.** Cite `lin2024streamingbench` (arXiv) for any protocol detail. Add `lin2026streamingbench` only as the archival version, and cite both together if venue status matters.

### 8. StreamMemBench: `liu2026streammembench`

- **Source.** arXiv:2606.14571, v1 of 12 Jun 2026 and v2 of 26 Aug 2026. The v2 arXiv comment says "Accepted to Findings of EMNLP 2026". `aclanthology.org/events/emnlp-2026/` and `/volumes/2026.findings-emnlp/` returned 404 on 2026-09-27, so the entry is cited through arXiv; replace it with the Anthology entry once published. OpenReview also shows an anonymous ACL ARR May 2026 submission with the same title.
- **What it measures.** Memory systems ingest a chronological stream of five-minute EgoLife segments (egocentric narrations and dialogue transcripts). Around each evidence anchor they then answer an initial task, receive simulated user feedback, and answer a related follow-up task. Four checklist metrics are scored by an LLM evaluation agent: Fidelity (evidence retained), Initial Evidence Use, Feedback Incorporation and Follow-up Reuse (§3). Storage, latency (seconds to ingest one segment and answer the first task) and token cost are reported separately as efficiency (Table 4).
- **LIT.** Accurate. Latency appears only as an efficiency cost, which is consistent with "沒有將其延遲報告轉成目前生效決策的錯誤時間". The Findings of EMNLP 2026 acceptance should be added.
- **MD.** Not in the comparison table.
- **FLAG.** In this paper "streaming" means chronological ingestion, not observations released on a wall clock, and there is no time axis in the scores. v2 contradicts itself: the abstract says "two backbones" and the contributions list says "three backbones". Do not quote a backbone count.

### 9. Belief Revision / Belief-R: `wilie2024belief`

- **Source.** ACL Anthology `.bib` for `2024.emnlp-main.586` (EMNLP 2024 main conference); DOI 10.18653/v1/2024.emnlp-main.586.
- **What it measures.** In the delta-reasoning (ΔR) framework (§3), step *t* gives two premises that support modus ponens or modus tollens. Step *t+1* adds a third premise that may or may not require retracting the earlier conclusion. The Belief Update and Belief Maintain subsets are scored separately (BU-Acc, BM-Acc), and BREU averages the two equally. Labels are human-annotated by majority vote (§4). About 30 LMs are evaluated (§5), and the paper finds a trade-off between updating and maintaining.
- **LIT.** Accurate: it separates "should update" from "should not update" and measures no latency.
- **MD.** "以新增前提或受控編輯評估更新與維持" is accurate for Belief-R.
- **Note.** BREU's equal weighting of update and maintain cases is a direct precedent for scoring change and no-change cases evenly. It is worth acknowledging next to SDB's per-interval balanced score. Belief-R involves a single update, not a continuing episode.

### 10. DeltaLogic: `dhanda2026deltalogic`

- **Source.** arXiv:2604.02733 v1 (single author). OpenReview `1QKsa7mKNd` shows venue "ICLR 2026 Workshop LLM Reasoning" and booktitle "ICLR 2026 Workshop on Logical Reasoning of Large Language Models". Because ICLR workshops are non-archival, the entry cites arXiv, with the arXiv DOI, and puts the workshop in `note`.
- **What it measures.** DeltaLogic turns FOLIO and ProofWriter items into revision episodes. The model answers under premises P, sees a minimal edit δ(P), and answers again (§2). There are four edit types: support insertion, defeating-fact insertion, support removal, and irrelevant-fact addition as a control. Metrics are initial and revised accuracy, inertia (keeping an outdated answer), over-flip (changing the answer after an irrelevant edit) and abstention (§3). Scoring uses closed-label log-likelihood on small models.
- **LIT.** Accurate ("是否被無關變化誤導" corresponds to over-flip on irrelevant additions). "ICLR workshop" is correct.
- **MD.** "DeltaLogic 聚焦單步修訂" is accurate; the authors say the benchmark "targets single-step revision".
- **FLAG (evidence strength).** The paper builds 100 episodes but reports only completed 30-episode and 20-episode subsets, on small models (Qwen3-0.6B/1.7B/4B and Phi-4-mini-instruct). Cite it as a design precedent (minimal-edit pairs, the inertia/over-flip taxonomy), not as strong empirical evidence. The inertia/over-flip terms map neatly onto SDB's two failure modes, a stale decision and a spurious switch.

### 11. CoPE: `chakrabarti2025cope`

- **Source.** arXiv:2512.18027 v1 (19 Dec 2025). No venue version was found in OpenReview or Crossref.
- **What it does.** CoPE fine-tunes Gemma 2 9B with LoRA into a policy-conditioned content labeler that outputs "a single token (0 or 1)". Training uses Contradictory Example Training, in which identical content receives different labels under different policies (§4, §5.3). Binocular Labeling is used to make policies unambiguous, with at least 0.9 F1 inter-rater agreement (§5). Evaluation uses held-out content and held-out policy variations across seven harm areas and reports precision, recall and F1 (§6). The authors report sub-200 ms latency on an A100.
- **LIT.** Accurate.
- **MD.** "依給定政策進行內容標記，並以矛盾配對訓練政策解讀" is accurate. **Pointer fix:** in the arXiv HTML numbering, §3 is Objectives and §4 is Contradictory Example Training. The construction that gives the same content different labels is §5.3, and the evaluation is §6. Cite §4–6 rather than §3–4.
- **FLAG.** CoPE and the Zentropi blog (12) come from the same organisation: CoPE's first two authors are at Zentropi, and the blog says its contrastive data is "as detailed in our CoPE paper". Present them as one line of work, not two independent precedents. CoPE is a method paper: a single-shot binary classifier with no temporal component.

### 12. Zentropi, "Enabling Streaming Classification": `zentropi2026enabling`

- **Source.** The blog page, which the task specifies as `@misc` with a URL. The byline and JSON-LD give author "Zentropi Team" and publication on 2026-03-10T18:37:19Z. It is a technical article, not peer-reviewed.
- **What it describes.** A logistic-regression linear probe reads CoPE's final-layer hidden state at each token. It is trained with *onset-aligned span labels*: "Tokens before the onset are labeled 0; tokens from the onset onward are labeled 1". There are about 10,000 positive examples with onset annotations, trained on policy-contrastive data. For streaming alarms the post recommends an EMA with decay ~0.3. The evidence is one worked 64-token example, in which the EMA crosses 0.5 at token 32, and the statement that the probe's F1 at the ANSWER position "essentially matches CoPE's F1"; no number is given.
- **LIT.** The first sentence is accurate. **FLAG: the second sentence mischaracterises the method.** "不能只將最終分類結果提前預測" implies Zentropi merely predicts the final label early. The post explicitly rejects labelling every token with the final label and trains on onset-aligned labels, so its per-token target is "has violating content appeared yet?". That is already a current-evidence target, closer to SDB's y\*(t) = P(S(t)) than LIT suggests. (The post is internally inconsistent: it also glosses the score as the probability "that a policy violation will occur by the end of the content sample".) The defensible differences are these:
  - the target flips at most once per sample (0→1);
  - time is the token position in generated text, not wall-clock time;
  - computation latency is not charged;
  - there is no quantitative streaming metric.
- **MD.** Not in the comparison table.

## Cross-cutting points the paper should respect

1. **Priority claims.** The speed–quality trade-off (Win Fast, which claims to be "the first to systematically" study it), asynchronous real-time evaluation (Gaia2, STAR), the "remove latency" counterfactual (Gaia2's instant mode) and the finding that fast models beat reasoning models under time pressure (Gaia2 §5.2, STAR §4.3) are all established. MD already says so; keep it that way in the paper.
2. **Second-level timing is not new.** HFTBench (1 s observations), StreetFighter (~200 ms/action), StreamingBench PO (2 s window, 1 s polling), ReactiveBench tool-lead (seconds) and Gaia2 timing windows all measure time at this scale. SDB's contribution has to be stated as the quantity scored: how long a *delivered, standing* decision deviates from the rule-determined reference (C7–C9).
3. **Reference-label provenance (for the C2 argument).** The works differ in where their references come from:
   - TicToc: aggregated human preference;
   - ProActor: hindsight LLM annotator, "not ground truth";
   - StreamMemBench: LLM-built anchors scored by an LLM evaluation agent;
   - Gaia2: human-annotated oracle write-action DAGs;
   - Belief-R: human majority vote;
   - DeltaLogic: deterministic edit semantics;
   - CoPE: policies engineered for ≥ 0.9 inter-rater F1.

   Among these, SDB's rule-determined reference is closest to DeltaLogic and CoPE.
4. **Version updates LIT should adopt.**
   - Gaia2 is ICLR 2026 (Oral).
   - The StreamingBench conference version is ICASSP 2026, with 10 authors.
   - StreamMemBench is accepted to Findings of EMNLP 2026 but not yet in the Anthology.
   - DeltaLogic's workshop is "ICLR 2026 Workshop on Logical Reasoning of Large Language Models".
5. **MD section pointers.** Every cited section exists and supports the claim, with three refinements:
   - CoPE: §3–4 → §4–6.
   - ProActor: the metrics are in §3.2; App. C covers baselines.
   - Win Fast: "既有行動具有延續效果" is not in Win Fast.

## Verification method and reproduction

All commands were run on 2026-09-27. Files under `sources/` are in this directory; the downloaded PDFs and their text extractions are not distributed.

- **arXiv metadata.**
  - Command: `curl -sL https://arxiv.org/bibtex/<id>` and `curl -sL https://arxiv.org/abs/<id>`.
  - Output: `sources/arxiv_<id>.bib` and `sources/arxiv_abs_metadata.json` (title, authors, comments, submission history).
- **ACL Anthology.**
  - Command: `curl -sL https://aclanthology.org/<id>.bib`.
  - Output: `sources/acl_<id>.bib`.
- **NeurIPS.**
  - Command: `curl -sL https://proceedings.neurips.cc/paper_files/paper/2025/file/ddaec864ba433e8889ab08dcf5c26e55-Bibtex-Conference.bib`.
  - Output: `sources/neurips_winfast.bib`.
- **ICASSP StreamingBench.**
  - Command: `curl -s https://api.crossref.org/works/10.1109/icassp55912.2026.11463959`.
  - Output: `sources/crossref_sb_doi.json`.
  - The version was found by WebSearch, which pointed to ieeexplore document 11463959.
- **OpenReview.**
  - Command: `curl -s "https://api2.openreview.net/notes/search?term=..."`.
  - Output: `sources/openreview_gaia2.json` and `sources/openreview_deltalogic.json`.
- **Zentropi blog.**
  - Command: `curl -sL https://blog.zentropi.ai/enabling-streaming-classification/`.
  - Output: `sources/zentropi_jsonld.json`.
- **Title and author cross-check.**
  - Command: `uv run python paper/bib/sources/verify_bib.py paper/bib/part_a.bib paper/bib/sources`.
  - Output: `sources/verify_bib_output.txt`. All 12 comparable entries match on title and full author list, the 4 ACL and NeurIPS DOIs and page ranges match, and the file ends in `ALL_OK`.
- **DOI resolution.**
  - Command: `curl -s https://doi.org/api/handles/<doi>` for each DOI in the bib.
  - Output: `sources/doi_resolution_output.txt`. All 11 return responseCode 1.
- **Paper content.**
  - Method: `pdftotext` (poppler) on the PDFs from arxiv.org/pdf, aclanthology.org and proceedings.neurips.cc, then `grep`.
  - Output: `sources/paper_quotes.txt`, which holds the verbatim lines behind every number and quoted phrase above.
- **BibTeX build check.**
  - Command: in a scratch directory, `pdflatex` + `bibtex` of a test document that uses `acl.sty` / `acl_natbib.bst` and `\citet` for every key.
  - Result: 0 `Warning--` lines in the BibTeX log, and 13 `\bibitem`s in the `.bbl`. All 13 entries render; the Gaia2 author list is truncated to "and 5 others" by the ACL style.
