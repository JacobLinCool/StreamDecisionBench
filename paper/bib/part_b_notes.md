# part_b.bib: verification notes

Checked 2026-09-27. Covers the 15 entries in `part_b.bib`: methodological foundations and benchmark-design references.

Status labels:
- **VERIFIED**: every BibTeX field was copied from a primary or registry record fetched in this session.
- **VERIFIED (secondary)**: the primary page could not be fetched, and the field was taken from a catalog record.
- **UNVERIFIED**: this session could not confirm the item.

Scratch evidence is kept locally in `paper/notes/scratch-archive/partb/`
(not versioned, since it holds downloaded papers). It holds the downloaded `.bib`, Crossref `.json`, PDFs and `pdftotext` output. The notes refer to it as `SCRATCH/`.

Key convention: last name of the first author, then year, then the first word of the title. Everything is lowercased and punctuation is removed. A leading "The" is skipped, so `maatouk2020age` and `maatouk2023age` stay distinct.

## Summary table

| Key | Venue used | Identifier | Status |
|---|---|---|---|
| `baumann2011evaluation` | Dialogue & Discourse 2(1):113–141, 2011 | doi 10.5087/dad.2011.106 | VERIFIED |
| `ma2019stacl` | ACL 2019, pp. 3025–3036 | doi 10.18653/v1/P19-1289 | VERIFIED |
| `ma2020simulmt` | AACL-IJCNLP 2020, pp. 582–587 | doi 10.18653/v1/2020.aacl-main.58 | VERIFIED |
| `ma2020simuleval` | EMNLP 2020 System Demonstrations, pp. 144–150 | doi 10.18653/v1/2020.emnlp-demos.19 | VERIFIED |
| `maatouk2020age` | IEEE/ACM Trans. Networking 28(5):2215–2228, Oct 2020 | doi 10.1109/TNET.2020.3005549 | VERIFIED (journal version of arXiv:1907.06604) |
| `maatouk2023age` | IEEE Trans. Wireless Communications 22(4):2621–2635, Apr 2023 | doi 10.1109/TWC.2022.3213227 | VERIFIED (journal version of arXiv:2012.13214) |
| `sagduyu2023age` | IEEE INFOCOM 2023 Workshops, pp. 1–6 | doi 10.1109/INFOCOMWKSHPS57453.2023.10226176 | VERIFIED (published version of arXiv:2301.04298) |
| `deshmukh2015robust` | RV 2015, LNCS 9333, pp. 55–70 | doi 10.1007/978-3-319-23820-3_4 | VERIFIED; the LNCS volume number is VERIFIED (secondary) |
| `johnson2017clevr` | CVPR 2017, pp. 1988–1997 (IEEE) | doi 10.1109/CVPR.2017.215 | VERIFIED; see the page-number note |
| `yue2025mmmupro` | ACL 2025 (Long), pp. 15134–15186 | doi 10.18653/v1/2025.acl-long.736 | VERIFIED |
| `white2025livebench` | ICLR 2025, pp. 91595–91631 | url (ICLR has no DOI) | VERIFIED |
| `jimenez2024swebench` | ICLR 2024, pp. 54107–54157 | url (ICLR has no DOI) | VERIFIED |
| `chowdhury2024introducing` | OpenAI blog, 2024-08-13 (updated 2025-02-24) | url | VERIFIED via Wayback snapshot and OpenAI RSS |
| `openai2026why` | OpenAI blog, 2026-02-23 | url | VERIFIED via Wayback snapshot and OpenAI RSS |
| `kahneman2011thinking` | Farrar, Straus and Giroux, New York, 2011 | ISBN 9780374275631 | VERIFIED (secondary) |

A test document ran `\citet` on all 15 keys and was compiled with the paper's own `acl.sty` and `acl_natbib.bst`, using pdflatex, bibtex, then pdflatex twice. The result was 15 `\bibitem`s, `warning$ -- 0` in the `.blg`, and no undefined citations. Files: `SCRATCH/bibtest/t.tex`, `t.blg`, `log.txt`, `t.pdf`.

---

## 1. `baumann2011evaluation`: Evaluation and Optimisation of Incremental Processors

**Source.** `curl https://aclanthology.org/2011.dnd-2.10.bib` produced `SCRATCH/2011.dnd-2.10.bib`. The entry copies that file verbatim except for the key. `number = 1` was added from two sources: Crossref `SCRATCH/10.5087_dad.2011.106.json` (issue 1) and the PDF header "Dialogue and Discourse 2(1) (2011) 113-141". The full text is in `SCRATCH/baumann.txt`, extracted with `pdftotext` from `https://aclanthology.org/2011.dnd-2.10.pdf`.

**Contribution.** The article defines how to represent the output of an incremental processor and how to build gold standards for it: an incremental gold and a non-incremental approximation. It then proposes three families of metrics: similarity (correctness, p-/r-correctness, time-adjusted error), timing (first occurrence FO, final decision FD) and diachronic (edit overhead EO, correction time). It demonstrates them on ASR, reference resolution and semantics, and shows post-processing (right context, hypothesis smoothing) that trades delay for stability.

**Exact points relevant to SDB.**
- *Processing delay is assumed negligible (§3.1).* The paper says: "we ignore processing delays imposed by the actual consumption of input and generation of output by the processor … we assume processing times to be bounded … and assume that it is negligible compared to the time spanned by each increment." SDB's C6 and C7 remove exactly this assumption.
- *Keeping the latest output (§3.1).* Citing Zilberstein (1996), the paper notes that "any non-interruptible processor can be made interruptible by caching the most recent result. This holds analogously for incremental processing." In §3.2 the current "total output" is read off the IU network at each instant. This is the precedent for SDB's C8, where the delivered answer holds until it is replaced.
- *Per-stage gold (§4.1.1).* The "current gold standard relative to a given input increment" is derived by stepping backwards from the final gold. This is the analogue of SDB's C2, where y\*(t) is determined by the public state at t.
- *Correctness is a count over increments, not a duration (§4.2.1).* "We simply count how often the output IU network is identical to the current gold standard and divide this by the total number of increments." The paper states that increments can arrive at irregular intervals, so the metric is not weighted by time. SDB's C9 integrates over wall-clock time instead. The time-adjusted error in §4.2.1 ("the more one has seen, the more not making a decision becomes just like making a wrong decision") is close to SDB's rule that the undecided state ⊥ costs 1.
- *Edit overhead and jitter (§4.2.3).* EO is "the proportion of unnecessary or even harmful edits among the overall edits". Frequent changes to earlier hypotheses are called *jitter*.
- *Beat-driven consumer (§6.3, not cited in the SDB docs).* A consumer "polls the ASR at every 200 ms for its most recent result". New output increments are then "delayed on average by β/2 because they are only registered on the next beat". This is the closest precedent for SDB's tick-sampled replay (SPEC §2.3), and it quantifies the discretisation bias that MINIMAL_DESIGN asks to be reported.
- Footnote 5 says a full formalisation would need to express "concurrency of processing components and possible delays in message passing", and leaves this to future work.

**Check against the SDB docs.** MINIMAL_DESIGN's table row cites §3.1 and §4.1–4.2 for keeping the latest output, intermediate gold, correctness and revision, and for computation delay being assumed negligible. The source confirms all of these. One nuance: keeping the latest output is a one-sentence remark about interruptibility, not a formal evaluation setting. The closest formal treatment is the §6.3 beat-driven consumer, so the paper could cite §3.1 and §6.3 together. Separately, the Crossref record for this DOI has malformed author fields ("Timo Baumann" as given name, "Okko Buß" as family name). Use the ACL Anthology author list.

## 2. `ma2019stacl`: STACL

**Source.** `SCRATCH/P19-1289.bib`, copied verbatim except for the key. Full text is in `SCRATCH/stacl.txt`.

**Contribution.** STACL proposes a prefix-to-prefix framework for simultaneous translation, with a "wait-k" policy that trains the model to emit target words concurrently with the source while staying k words behind. It also introduces Average Lagging (AL), a latency metric for how far the output is "out of sync with the speaker".

**Exact point relevant to SDB.** AL is defined "in terms of the number of source words" (§4.2, Eqs. 8–9) and is averaged only up to the cut-off step. The tail after the full source has been read is excluded "because the tail can be generated instantly without further delay". Latency is therefore measured on the source-token axis, and model computation time is not part of the metric. SDB instead measures in wall-clock time how long a wrong decision stays in force. This matches LITERATURE #13.

## 3. `ma2020simulmt`: SimulMT to SimulST

**Source.** `SCRATCH/2020.aacl-main.58.bib`, copied verbatim except for the key. Full text is in `SCRATCH/simulst.txt`.

**Contribution.** The paper adapts simultaneous text-translation policies (wait-k, monotonic multihead attention) to end-to-end simultaneous speech translation. It does this through a pre-decision module that groups encoder states before each READ/WRITE decision. It also proposes a time-based, computation-aware variant of AL.

**Exact point relevant to SDB.** Section 2 defines two delays for each target token:
- the **computation-aware (CA)** delay d_CA(y_i): "the time that elapses … from the beginning of the process to the prediction of y_i";
- the **non-computation-aware (NCA)** delay d_NCA(y_i) = T_s · n(y_i). The paper notes that "d_NCA is an ideal case for d_CA where the computational time for the model is ignored."

Both delays are measured in milliseconds. The main trade-off curves (Fig. 2) use NCA delay "from a purely algorithmic perspective". The computation-aware section (Fig. 4) finds that the NCA–CA gap shrinks as the step size grows, and it recommends CA latency "as it reflects a more realistic evaluation, especially in low-latency regimes". This is the direct precedent for separating waiting for information from computation time: SDB's C7 corresponds to the CA view. The difference from SDB is that CA delay is still summarised through AL as a per-token lag. It does not score how long a stale output remains in effect. This matches LITERATURE #14.

## 4. `ma2020simuleval`: SimulEval

**Source.** `SCRATCH/2020.emnlp-demos.19.bib`, copied verbatim except for the key. Full text is in `SCRATCH/simuleval.txt`.

**Contribution.** SimulEval is an open-source toolkit for simultaneous text and speech translation. A server sends source input and receives predictions, while a client runs the user's policy. It reports quality (BLEU, TER) and latency (AP, AL, DAL), adapts the latency metrics to speech, and includes a visualisation interface. It was used for the IWSLT 2020 shared task.

**Relation to SDB (caution).** The paper states: "the term latency is overloaded and sometimes refers to the actual system speed. In this paper, latency refers to the simultaneous ability, which is how much partial source information is needed to start the translation process." In this paper, SimulEval should therefore be cited for a standardised server–client evaluation protocol (LITERATURE #15), not for measuring wall-clock latency. The 2020 paper does not mention computation-aware latency; `grep -i computation` finds only reference-list hits.

## 5. `maatouk2020age`: The Age of Incorrect Information: A New Performance Metric for Status Updates

**Source.**
- Crossref search, then `api.crossref.org/works/10.1109/tnet.2020.3005549`, saved as `SCRATCH/10.1109_tnet.2020.3005549.json`. The record is a journal article in IEEE/ACM Transactions on Networking, volume 28, issue 5, pp. 2215–2228, October 2020, with the same four authors and the same title as arXiv.
- The arXiv API (`SCRATCH/arxiv.xml`) has no `journal_ref` or `doi` for 1907.06604.
- The text was read from arXiv v2 (2020-07-09), in `pdftotext` output of `SCRATCH/aoii1.pdf`. The journal PDF was not read.

**Contribution.** The paper introduces the Age of Incorrect Information (AoII). The penalty is zero while the monitor's estimate is correct and grows with how long the estimate has been wrong. The authors then derive AoII-optimal transmission policies for a Markovian source over an unreliable channel: "always update" when there is no constraint, and a mixture of two Lagrange policies under a power budget.

**Exact point relevant to SDB.** Section II contrasts three penalties:
- the age Δ_age(t) = t − U(t) (Eq. 1), which keeps growing even when the monitor is correct;
- the error penalty Δ_err(t) = 1{X̂(t) ≠ X(t)} (Eq. 2), whose average equals the prediction error. Its stated flaw is that "the same penalty is paid for being in an erroneous state no matter how long the monitor has been in it", so "the long-time average error penalty due to a burst error is the same as the one resulting from several isolated errors of the same duration";
- AoII, Δ_AoII(t) = f(t) × g(X(t), X̂(t)) (Eq. 3), with g_ind the indicator (Eq. 4).

Time is discrete (time slots) in this paper. SDB's C9 loss is the continuous-time integral of the Eq. 2 indicator, not AoII.

## 6. `maatouk2023age`: The Age of Incorrect Information: an Enabler of Semantics-Empowered Communication

**Source.**
- Crossref record `SCRATCH/10.1109_twc.2022.3213227.json`: IEEE Transactions on Wireless Communications, volume 22, issue 4, pp. 2621–2635, April 2023. The journal capitalises the title as "An Enabler". The arXiv title has "an Enabler"; the bib follows the journal.
- The text was read from arXiv v3 (2022-10-11), `SCRATCH/aoii2.pdf`. The PDF footnote says a preliminary version appeared at IEEE ICC 2022; Crossref lists it as 10.1109/icc45855.2022.9838737, "Semantics-Empowered Communications Through the Age of Incorrect Information".

**Contribution.** The paper positions AoII as a metric for semantics-empowered communication. It proves that the optimal transmission strategy for minimising average AoII is a randomized threshold policy and gives an algorithm for its parameters. It compares AoII with error-based metrics theoretically: for the adopted source model the AoII-optimal policy is also error-optimal, but the converse does not necessarily hold.

**Exact point relevant to SDB (Eq. 2–4, §II).**
- Eq. 2, Δ_err = 1{X̂_t ≠ X_t}, and Eq. 3, Δ_sq = (X_t − X̂_t)², are the "error-based metrics framework". The paper says: "By minimizing the time-average of the metrics found in (2) and (3), we obtain the celebrated Minimum Prediction Error (MPE) and the Minimum Mean Squared Error (MMSE) policies." It attributes these to earlier work (its refs [12], [23], [24]).
- The paper's criticism is that "the system's error penalty due to two bursts of errors of one timeslot is equivalent to that resulting from a single error of two timeslots".
- Eq. 4 defines AoII = f(t) × g(X_t, X̂_t), with f non-decreasing. The examples are f_linear(t) = t − V_t (Eq. 8), where V_t is the last time the estimate was correct, and a grace-period form f_threshold(t) = 1{t − V_t ≥ ζ} (Eq. 9). The indicator g_ind is Eq. 5.
- AoI (Eq. 1) is penalised even while X_t = X̂_t. AoII and the error metrics are zero in that case.
- The model section uses slotted time.

**Consequence for SDB.** SDB's error time E = ∫1[d(t) ≠ y\*(t)]dt is exactly the continuous-time counterpart of the time-average of Eq. 2, the MPE-type error penalty. It has the burst-equivalence property that this paper criticises. The per-interval normalised score L_e is neither Eq. 2 nor AoII. The paper should therefore say that C9 adopts the time-averaged mismatch reviewed in the AoII papers, and that AoII is an alternative that weights by age. AoII with f_linear or f_threshold could be reported as a sensitivity variant, but should not be claimed as SDB's metric.

## 7. `sagduyu2023age`: Age of Information in Deep Learning-Driven Task-Oriented Communications

**Source.**
- Crossref `SCRATCH/10.1109_infocomwkshps57453.2023.10226176.json`: IEEE INFOCOM 2023 Workshops (INFOCOM WKSHPS), Hoboken NJ, 2023-05-20, pp. 1–6, authors Yalin E. Sagduyu, Sennur Ulukus, Aylin Yener.
- The arXiv API shows no `journal_ref`.
- Text from arXiv v2, `SCRATCH/aoitask.pdf`.

**Contribution.** The transmitter and receiver are modelled as a jointly trained encoder–decoder that performs classification (MNIST, CIFAR-10) instead of reconstruction. Accuracy rises with the number of channel uses, but so does service time. To analyse this accuracy–latency trade-off, the paper introduces the **peak age of task information (PAoTI)**, where age grows "unless a received signal is classified correctly". It also gives a dynamic update mechanism that adapts the number of channel uses.

**Relation to SDB.** This is a neighbouring precedent for tying a time cost to task correctness rather than raw delay, which matches LITERATURE #18. The setting is communications, with a queueing model and image classification. It does not involve language decisions.

## 8. `deshmukh2015robust`: Robust Online Monitoring of Signal Temporal Logic

**Source.**
- The page linked from LITERATURE, `https://ptolemy.berkeley.edu/projects/terraswarm/pubs/571.html`, was read with WebFetch. It says "Runtime Verification '15, Vienna, September 22, 2015" and "Winner of the best paper award". It misspells the first author as "Deshmukhh", so its BibTeX was not used.
- Metadata came from the Springer citation export (`citation-needed.springer.com/v2/references/10.1007/978-3-319-23820-3_4?format=bibtex`) and from Crossref (`SCRATCH/10.1007_978-3-319-23820-3_4.json`, with editors Bartocci and Majumdar from the book DOI).
- LNCS volume 9333 is taken from the Open Library record for ISBN 9783319238197, which gives the source title "(Lecture Notes in Computer Science (9333))". A web search summary agreed. Springer and dblp pages were blocked (303 to login, and an anti-bot wall), so the volume number is VERIFIED (secondary).
- An extended journal version exists: Formal Methods in System Design 51(1):5–30, 2017, doi 10.1007/s10703-017-0286-7 (Crossref `SCRATCH/10.1007_s10703-017-0286-7.json`). It is not in the bib because LITERATURE links the RV 2015 paper.

**Contribution.** The abstract (from the Springer export) formalises robust online monitoring of Signal Temporal Logic (STL) over partial signal traces through "robust satisfaction intervals (RoSIs)". It gives an efficient algorithm to compute them, demonstrated on automotive and online CPS-education case studies. Online monitoring allows early termination once satisfaction or violation is determined.

**Relation to SDB.** It is background for evaluating an executable specification while the signal is still arriving. It does not address language inputs or mapping observations to actions. This matches LITERATURE #19.

## 9. `johnson2017clevr`: CLEVR

**Source.**
- CVF open access page `openaccess.thecvf.com/content_cvpr_2017/html/Johnson_CLEVR_A_Diagnostic_CVPR_2017_paper.html` (`SCRATCH/clevr.html`) for its BibTeX block and abstract.
- Crossref search for DOI 10.1109/cvpr.2017.215, which gives pages 1988–1997 and the author "C. Lawrence Zitnick".
- **Page discrepancy:** the CVF page prints "pp. 2901-2910", but the IEEE/Crossref record gives 1988–1997. The bib uses the DOI-backed IEEE pages.
- The CVF export writes the author as "Lawrence Zitnick, C."; the bib uses "Zitnick, C. Lawrence".

**Contribution.** CLEVR is a synthetic diagnostic VQA dataset. It "contains minimal biases and has detailed annotations describing the kind of reasoning each question requires". Questions "are represented as functional programs that can be executed to answer the question", and question-conditional bias is controlled "via rejection sampling". These quotes were checked in the CVF PDF text, `SCRATCH/clevr2.txt`. This supports LITERATURE #20.

## 10. `yue2025mmmupro`: MMMU-Pro

**Source.** `SCRATCH/2025.acl-long.736.bib`, verbatim except for the key and a widened brace group, `{MMMU-Pro}`, so that `acl_natbib` does not print "MMMU-pro". The abstract is in `SCRATCH/mmmupro.txt`.

**Contribution.** MMMU-Pro hardens MMMU in three steps: "(1) filtering out questions answerable by text-only models, (2) augmenting candidate options, and (3) introducing a vision-only input setting where questions are embedded within images". The abstract reports that model performance falls by 16.8% to 26.9% compared with MMMU. This matches LITERATURE #33.

## 11. `white2025livebench`: LiveBench

**Source.**
- The ICLR proceedings abstract page, and the BibTeX file at `…/2025/file/e4a46394ba5378b3f9a186a5b4c650d1-Bibtex-Conference.bib`, fetched with curl.
- The author list matches the page exactly. "Shubh-Agrawal" is one hyphenated token on both the page and the export, and is kept as `{Shubh-Agrawal}`.
- The export's `volume = {2025}` was dropped because `acl_natbib` prints it as "volume 2025". The `url` field points to the abstract page instead of the PDF.

**Contribution.** LiveBench is a benchmark with "frequently-updated questions from recent information sources". It scores answers "automatically according to objective ground-truth values" and spans math, coding, reasoning, language, instruction following and data analysis. Questions are added and updated monthly to limit test-set contamination. "Live" refers to how the question pool is refreshed, not to a real-time environment, which is consistent with LITERATURE #29.

## 12. `jimenez2024swebench`: SWE-bench

**Source.**
- The ICLR 2024 proceedings page, and the BibTeX file at `…/2024/file/edac78c3e300629acfe6cbe9ca88fb84-Bibtex-Conference.bib`.
- The title as given there is "SWE-bench: Can Language Models Resolve Real-world Github Issues?", with lowercase "world" and "Github". LITERATURE #25 writes "Real-World GitHub", which is the arXiv form. The bib keeps the proceedings casing.
- The export's `volume = {2024}` was dropped, and the initial in "Carlos E" was given a period.

**Contribution.** SWE-bench is "an evaluation framework consisting of 2,294 software engineering problems drawn from real GitHub issues and corresponding pull requests across 12 popular Python repositories". Solutions are judged by executing tests. The best model in the paper, Claude 2, resolves 1.96%. This matches LITERATURE #25.

## 13. `chowdhury2024introducing`: Introducing SWE-bench Verified

**Source.**
- openai.com returned HTTP 403 to both curl and WebFetch.
- The page was read from the Wayback snapshot `web.archive.org/web/20260915162530id_/https://openai.com/index/introducing-swe-bench-verified/`, saved as `SCRATCH/oa_intro.dec.html.txt`.
- The title and date were cross-checked against the live `https://openai.com/news/rss.xml` item: "Introducing SWE-bench Verified", Tue, 13 Aug 2024.
- The page shows "August 13, 2024" and "Updated February 24, 2025". Its "Authors" section lists Neil Chowdhury, James Aung, Chan Jun Shern, Oliver Jaffe, Dane Sherburn, Giulio Starace, Evan Mays, Rachel Dias, Marwan Aljubeh, Mia Glaese, Carlos E. Jimenez, John Yang, Leyton Ho, Tejal Patwardhan, Kevin Liu and Aleksander Madry. "Chan Jun Shern" is kept as the page writes it, braced as one name.

**Contribution.** OpenAI and the SWE-bench authors released a human-validated subset of 500 samples, "verified to be non-problematic by our human annotators". To build it, 93 Python developers screened 1,699 random SWE-bench test samples for underspecified problem statements (38.3% flagged) and unfair unit tests (61.1% flagged). In total, 68.3% of samples were filtered out. This matches LITERATURE #41.

## 14. `openai2026why`: Why SWE-bench Verified no longer measures frontier coding capabilities

**Source.**
- The Wayback snapshot `…/20260915162530id_/https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/`, saved as `SCRATCH/oa_why.dec.html.txt`.
- The `<title>`, `og:title` and headline all read "Why SWE-bench Verified no longer measures frontier coding capabilities". The page date is February 23, 2026, and the author line is "OpenAI".
- The URL slug and the RSS item title read "Why we no longer evaluate SWE-bench Verified" (RSS date Mon, 23 Feb 2026). The bib uses the page headline, which matches LITERATURE #42.

**Contribution.** An audit covered 138 Verified problems that o3 did not consistently solve over 64 runs. It found that 59.4% had material issues in test design or problem description:
- 35.5% had "narrow" tests;
- 18.8% had "wide" tests;
- 5.1% had other issues.

The post also reports that frontier models could reproduce gold patches or task-specific details, which is evidence of contamination. OpenAI has stopped reporting SWE-bench Verified and recommends SWE-bench Pro. Among the lessons it draws: "automated scoring is tricky to get right". This matches LITERATURE #42.

## 15. `kahneman2011thinking`: Thinking, Fast and Slow

**Source.** The Open Library edition record `openlibrary.org/isbn/9780374275631.json`: Farrar, Straus and Giroux; New York; 2011; ISBN-10 0374275637; 499 pages. The publisher page (us.macmillan.com) returned 403, so the entry is VERIFIED (secondary). The book's official title casing is "Thinking, Fast and Slow".

**Contribution and terminology.** The book popularised the distinction between an automatic, fast "System 1" and an effortful, deliberate "System 2". A book excerpt published by Scientific American on 2012-06-15, read with WebFetch, quotes: "I adopt terms originally proposed by the psychologists Keith Stanovich and Richard West, and will refer to two systems in the mind, System 1 and System 2." It defines System 1 as operating "automatically and quickly, with little or no effort and no sense of voluntary control".

The paper can cite Kahneman for the terminology and say that the labels originate with Stanovich and West. Their original paper was not fetched here and has no entry in this bib; it is **UNVERIFIED** if the paper adds it. MINIMAL_DESIGN already says that "System 1" is motivation only and makes no claim about the model's internal mechanism. That position is consistent with using the book as a terminology reference only.

---

## Where the sources contradict or refine docs/LITERATURE.md and docs/MINIMAL_DESIGN.md

1. **C9 vs. AoII (MINIMAL_DESIGN reviewer table, C9 row; comparison table AoII row).** The comparison-table wording "討論時間平均 mismatch，並以 AoII 進一步考慮錯誤延續的代價" is accurate. The C9 answer "時間平均 mismatch 已有 AoII 文獻脈絡" is only accurate if it is read as follows: the time-averaged indicator mismatch (Eq. 2 in 2012.13214) is the *error-based / MPE* framework that the AoII papers review from earlier work and then critique. SDB's E is that quantity, and it inherits the burst-equivalence property the AoII papers point out. AoII itself (Eq. 4) weights by age and is not what SDB computes. The per-interval normalised L_e is neither. LITERATURE #17 already states that AoII "不能直接等同於單純累計錯誤時間", which the sources confirm.
2. **LITERATURE #16 year and venue.** The entry lists only the "2019 預印本". A peer-reviewed journal version exists: IEEE/ACM Transactions on Networking 28(5):2215–2228, October 2020, doi 10.1109/TNET.2020.3005549. The bib cites that version.
3. **LITERATURE #18 venue.** The entry is listed as an arXiv 2023 paper. It was published at IEEE INFOCOM 2023 Workshops, doi 10.1109/INFOCOMWKSHPS57453.2023.10226176, and the bib cites that.
4. **LITERATURE #19 link.** The RV '15 page the entry links misspells the first author as "Deshmukhh". The correct spelling, from Springer and Crossref, is "Deshmukh". An extended FMSD 2017 version exists (51(1):5–30).
5. **LITERATURE #25 title casing.** The ICLR proceedings title is "…Real-world Github Issues?". The catalog uses "Real-World GitHub".
6. **Baumann et al. and C8 (MINIMAL_DESIGN C8 row, "Incremental processing 已有保留最新輸出的設定").** The claim is supported, but only by a one-sentence remark about caching the most recent result for interruptibility in §3.1. §6.3, the beat-driven consumer that polls the most recent result every β = 200 ms with an average β/2 registration delay, is a closer and uncited precedent for SDB's hold-and-sample replay. Baumann's correctness is also a per-increment count, not a time-weighted integral, which supports the claim that C9's time integral is different from their metrics.
7. **SimulEval (LITERATURE #15).** The catalog does not state this, but it should not be implied: the SimulEval paper explicitly defines latency as "simultaneous ability" (how much partial source is needed), *not* system speed. The computation-aware precedent is SimulMT-to-SimulST (#14), not SimulEval.
8. **STACL (LITERATURE #13) and SimulMT-to-SimulST (LITERATURE #14).** The sources confirm both claims: AL counts source words and treats the tail as instantaneous, and the CA and NCA delays are defined and compared, with CA recommended.
9. **CLEVR pages.** The CVF open-access page (pp. 2901–2910) and IEEE Xplore/Crossref (pp. 1988–1997) disagree. This is not a catalog error, but the paper should use one version consistently. The bib uses the DOI version.

No other contradictions were found. LITERATURE #12, #14, #15, #17, #20, #29, #33, #41 and #42 agree with what the sources say.

## UNVERIFIED or partially verified items

- **Equation numbers in the journal versions** of the two AoII papers. Eq. 1–4 of 1907.06604 (arXiv v2) and Eq. 1–9 of 2012.13214 (arXiv v3) were read from arXiv. The IEEE journal PDFs are paywalled and were not compared.
- **LNCS volume 9333** for RV 2015: from Open Library and a web-search summary, because Springer and dblp could not be fetched.
- **Kahneman book metadata**: from Open Library. The publisher page returned 403.
- **OpenAI posts**: read from a 2026-09-15 Wayback snapshot, not the live page (403). The titles and dates were cross-checked against the live OpenAI RSS feed.
- **Stanovich and West (2000)**: not fetched and not in the bib. Mark it UNVERIFIED if it is cited.

## Commands used (all outputs in SCRATCH/)

- `curl -sL https://aclanthology.org/{2011.dnd-2.10,P19-1289,2020.aacl-main.58,2020.emnlp-demos.19,2025.acl-long.736}.bib`
- `curl https://export.arxiv.org/api/query?id_list=1907.06604,2012.13214,2301.04298` → `arxiv.xml`
- `curl https://api.crossref.org/works?query.bibliographic=…` and `…/works/<doi>` → `*.json`
- `curl https://citation-needed.springer.com/v2/references/10.1007/978-3-319-23820-3_4?format=bibtex`
- `curl https://openlibrary.org/isbn/{9783319238197,9780374275631}.json`
- `curl https://openaccess.thecvf.com/content_cvpr_2017/html/Johnson_CLEVR_A_Diagnostic_CVPR_2017_paper.html` → `clevr.html`; PDF → `clevr2.txt`
- `curl https://proceedings.iclr.cc/paper_files/paper/{2025,2024}/file/<hash>-Bibtex-Conference.bib`
- `curl https://openai.com/news/rss.xml` → `rss.xml`; Wayback `id_` snapshots → `oa_intro.dec.html.txt`, `oa_why.dec.html.txt`
- `pdftotext` on the ACL and arXiv PDFs → `baumann.txt`, `stacl.txt`, `simulst.txt`, `simuleval.txt`, `aoii1.txt`, `aoii2.txt`, `aoitask.txt`, `mmmupro.txt`
- WebFetch: the ptolemy RV '15 page and the Scientific American Kahneman excerpt
- Compile check: `pdflatex t && bibtex t && pdflatex t && pdflatex t` in `SCRATCH/bibtest/`
