# StreamDecisionBench literature catalog

Source audit date: 2026-09-27.

This bounded reading set contains 39 research papers and 3 official technical articles used to assess StreamDecisionBench (SDB). It is not an exhaustive survey. Each entry describes the work and then its relationship to SDB; those relationships are our analysis, not claims attributed to the authors.

Years identify the publication or preprint versions listed below. A preprint does not imply peer review. The [design rationale](MINIMAL_DESIGN.md) distinguishes implemented contracts from proposed acceptance audits.

## Real-time action, streaming, and continuous updates

1. **[Gaia2: Benchmarking LLM Agents on Dynamic and Asynchronous Environments](https://arxiv.org/abs/2602.11964)**  
   2026 | Aliases / associated benchmarks: Gaia2

   Gaia2 places agents in independently advancing asynchronous environments and evaluates tool actions with a verifier that includes temporal constraints. It overlaps directly with SDB in changing environments and inference delay; SDB must explain what continuous assessment of the standing decision adds beyond action-trajectory verification.

2. **[Win Fast or Lose Slow: Balancing Speed and Accuracy in Latency-Sensitive Decisions of LLMs](https://proceedings.neurips.cc/paper_files/paper/2025/hash/ddaec864ba433e8889ab08dcf5c26e55-Abstract-Conference.html)**  
   2025 | Aliases / associated benchmarks: Win Fast or Lose Slow / HFTBench、StreetFighter

   Trading and real-time combat tasks test how LLM decision quality and latency jointly affect reward. The speed–quality problem is established prior work; SDB can use prescribed correct actions to identify how long an inappropriate decision persists.

3. **[Beyond Scaling: Assessing Strategic Reasoning and Rapid Decision-Making Capability of LLMs in Zero-sum Environments](https://arxiv.org/abs/2603.09337)**  
   2026 | Aliases / associated benchmarks: STAR

   STAR compares turn-based and real-time versions of zero-sum strategic environments to study the gap between strategic reasoning and action speed. The possibility that stronger reasoning loses because it is slower already has precedent, so SDB needs more specific failure mechanisms and conditions.

4. **[Your LLM Agents are Temporally Blind: The Misalignment Between Tool Use Decisions and Human Time Perception](https://aclanthology.org/2026.findings-acl.1848/)**  
   2026 | Aliases / associated benchmarks: TicToc

   TicToc varies elapsed conversational time to test whether agents refresh information through tool calls at appropriate moments. It shares the problem of stale information, but manipulates time in the input rather than directly integrating the decisions that remain in force during model computation.

5. **[Never Stop Thinking: Continuous-Time Language Agents](https://arxiv.org/abs/2609.17416)**  
   2026 | Aliases / associated benchmarks: Never Stop Thinking / ReactiveBench

   The paper studies language agents that interleave new input, thinking, and output, using ReactiveBench for interactive responsiveness and verifiable streaming tasks. Continuous input and real-time response overlap with SDB; SDB measures whether the externally adopted decision remains appropriate between deliveries.

6. **[ProActor: Timing-Aware Reinforcement Learning for Proactive Task Scheduling Agents](https://aclanthology.org/2026.acl-long.832/)**  
   2026 | Aliases / associated benchmarks: ProActor

   ProActor uses timing-aware reinforcement learning for proactive task scheduling and evaluates both action content and the opportunity to act within a dialogue. Selecting a next action and its timing therefore has direct precedent; SDB must specify measured delivery delay and decision validity between updates.

7. **[StreamingBench: Assessing the Gap for MLLMs to Achieve Streaming Video Understanding](https://arxiv.org/abs/2411.03628)**  
   2024 preprint; 2026 conference version | Aliases / associated benchmarks: StreamingBench

   StreamingBench evaluates real-time video understanding, continuous question answering, and proactive responses. Because response timing is already part of its scope, SDB must distinguish its commitment and duration-scoring contract rather than rely on the difference between text and video.

8. **[StreamMemBench: Streaming Evaluation of Agent Memory for Future-Oriented Assistance](https://arxiv.org/abs/2606.14571)**  
   2026 | Aliases / associated benchmarks: StreamMemBench

   StreamMemBench connects chronological observations to initial and subsequent tasks, testing evidence retention, information use, and reuse of interaction feedback. Both require earlier context to affect later behavior, but its memory and efficiency measurements do not convert latency into standing-decision error duration.

## Evidence revision and rule interpretation

9. **[Belief Revision: The Adaptability of Large Language Models Reasoning](https://aclanthology.org/2024.emnlp-main.586/)**  
   2024 | Aliases / associated benchmarks: Belief Revision / Belief-R

   Belief-R adds evidence to existing premises and tests whether models appropriately revise or preserve conclusions. It directly motivates update-versus-hold controls, while not measuring actual computation delays across a continuous sequence of updates.

10. **[DeltaLogic: Minimal Premise Edits Reveal Belief-Revision Failures in Logical Reasoning Models](https://arxiv.org/abs/2604.02733)**  
   2026; ICLR workshop | Aliases / associated benchmarks: DeltaLogic

   DeltaLogic uses minimal premise edits to test revision under relevant changes and resistance to irrelevant changes. It is direct precedent for paired interventions, so those pairs alone cannot establish SDB novelty.

11. **[CoPE: A Small Language Model for Steerable and Scalable Content Labeling](https://arxiv.org/abs/2512.18027)**  
   2025 | Aliases / associated benchmarks: CoPE

   CoPE trains a small language model to label content under user-specified policies, including contrasting labels for identical content under different policies. Finite labels can require rule interpretation; SDB should establish difficulty through contextual dependence and shortcut audits.

## Temporal evaluation and methodological foundations

12. **[Evaluation and Optimisation of Incremental Processors](https://aclanthology.org/2011.dnd-2.10/)**  
   2011

   The paper develops correctness, timing, and stability measures for incremental language processing, including intermediate revision and unnecessary edits. It is a close methodological precedent: evaluating more than final answers and examining output instability are established ideas.

13. **[STACL: Simultaneous Translation with Implicit Anticipation and Controllable Latency using Prefix-to-Prefix Framework](https://aclanthology.org/P19-1289/)**  
   2019 | Aliases / associated benchmarks: STACL

   STACL introduces prefix-to-prefix translation, wait-k policies, and Average Lagging to control and measure streaming translation delay. Its quality–latency framework is relevant, but the original source-word lag is different from physical time spent holding an incorrect action.

14. **[SimulMT to SimulST: Adapting Simultaneous Text Translation to End-to-End Simultaneous Speech Translation](https://aclanthology.org/2020.aacl-main.58/)**  
   2020 | Aliases / associated benchmarks: SimulMT to SimulST

   This work adapts simultaneous text translation to speech and explicitly compares computation-aware and computation-unaware latency. It provides precedent for separating information waiting from computation time; the citation informs evaluation methodology without expanding SDB input modalities.

15. **[SimulEval: An Evaluation Toolkit for Simultaneous Translation](https://aclanthology.org/2020.emnlp-demos.19/)**  
   2020 | Aliases / associated benchmarks: SimulEval

   SimulEval standardizes simultaneous-translation interaction and quality/latency evaluation. Its relevance is a common model interface and protocol that prevent implementation differences from undermining score comparability.

16. **[The Age of Incorrect Information: A New Performance Metric for Status Updates](https://arxiv.org/abs/1907.06604)**  
   2019 preprint | Aliases / associated benchmarks: Age of Incorrect Information: original metric

   The original AoII work makes status-update cost depend on both receiver-estimation error and the duration of that error. It provides a theoretical basis for distinguishing old information from incorrect information and cautions against claiming all time-based error measures as new.

17. **[The Age of Incorrect Information: an Enabler of Semantics-Empowered Communication](https://arxiv.org/abs/2012.13214)**  
   2020 preprint; 2023 journal version | Aliases / associated benchmarks: Age of Incorrect Information: semantic-communication extension

   This extension compares AoII, information age, and general error costs when choosing status updates. Persistent error is shared motivation, but AoII can penalize the age of an ongoing error and must not be equated with SDB's unweighted accumulated mismatch duration.

18. **[Age of Information in Deep Learning-Driven Task-Oriented Communications](https://arxiv.org/abs/2301.04298)**  
   2023

   The paper studies how communication resources affect downstream classification accuracy and service delay, introducing task-oriented information-age measures. It motivates connecting timing costs to task outcomes rather than reporting model latency alone.

19. **[Robust Online Monitoring of Signal Temporal Logic](https://ptolemy.berkeley.edu/projects/terraswarm/pubs/571.html)**  
   2015

   The work continuously monitors temporal-logic satisfaction before a complete signal is available. It supplies background for executable rules and online verification; SDB still needs a separate measurement connecting language observations to appropriate actions.

## Synthetic data and controlled measurement

20. **[CLEVR: A Diagnostic Dataset for Compositional Language and Elementary Visual Reasoning](https://cs.stanford.edu/people/jcjohns/clevr/)**  
   2017 | Aliases / associated benchmarks: CLEVR

   CLEVR uses synthetic scenes and executable question programs to control visual-question-answering requirements and diagnose shortcuts. It is a central methodological reference for separating context, rules, and language presentation so failures can be localized.

21. **[Kubric: A Scalable Dataset Generator](https://openaccess.thecvf.com/content/CVPR2022/html/Greff_Kubric_A_Scalable_Dataset_Generator_CVPR_2022_paper.html)**  
   2022 | Aliases / associated benchmarks: Kubric

   Kubric combines physical simulation and rendering to generate controllable scenes with rich annotations. It motivates a generator that manipulates research variables; dataset size alone does not establish measurement validity.

22. **[ProcTHOR: Large-Scale Embodied AI Using Procedural Generation](https://proceedings.neurips.cc/paper_files/paper/2022/hash/27c546ab1e4f1d7d638e6a8dfbad9a07-Abstract-Conference.html)**  
   2022 | Aliases / associated benchmarks: ProcTHOR

   ProcTHOR procedurally generates interactive indoor environments and studies scale, diversity, and transfer to external tasks. It primarily supplies training and research environments; SDB can draw on validation beyond the generator, such as independently authored streams.

## Dataset and benchmark design case studies

23. **[Ego4D: Around the World in 3,000 Hours of Egocentric Video](https://openaccess.thecvf.com/content/CVPR2022/html/Grauman_Ego4D_Around_the_World_in_3000_Hours_of_Egocentric_Video_CVPR_2022_paper.html)**  
   2022 | Aliases / associated benchmarks: Ego4D

   Ego4D collects large-scale everyday egocentric video and defines memory, interaction, and prediction tasks. It illustrates defining the required capability before choosing scenario sampling, annotation, and component evaluations.

24. **[LAION-5B: An Open Large-Scale Dataset for Training Next Generation Image-Text Models](https://papers.nips.cc/paper/2022/hash/a1859debfb3b59d094f3504d5ebb6c25-Abstract-Datasets_and_Benchmarks.html)**  
   2022 | Aliases / associated benchmarks: LAION-5B

   LAION-5B constructs large-scale open image–text training data through automated filtering and evaluates its use in downstream models. Its relevance is data infrastructure, filtering bias, and quality validation rather than a direct real-time decision contract.

25. **[SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html)**  
   2024 | Aliases / associated benchmarks: SWE-bench

   SWE-bench asks models to patch real repositories for GitHub issues and uses executable tests to assess resolution. It illustrates turning capability claims into verifiable outcomes and using diagnostic conditions to separate failure sources.

26. **[MathVista: Evaluating Mathematical Reasoning of Foundation Models in Visual Contexts](https://proceedings.iclr.cc/paper_files/paper/2024/hash/663bce02a0050c4a11f1eb8a7f1429d3-Abstract-Conference.html)**  
   2024 | Aliases / associated benchmarks: MathVista

   MathVista combines mathematical reasoning problems in visual contexts and studies the interaction of visual understanding and mathematical ability. It motivates identifying measurement gaps through a capability taxonomy, then adding targeted data and experiments.

27. **[MMMU: A Massive Multi-discipline Multimodal Understanding and Reasoning Benchmark for Expert AGI](https://openaccess.thecvf.com/content/CVPR2024/html/Yue_MMMU_A_Massive_Multi-discipline_Multimodal_Understanding_and_Reasoning_Benchmark_for_CVPR_2024_paper.html)**  
   2024 | Aliases / associated benchmarks: MMMU

   MMMU evaluates expert knowledge and reasoning through college-level multimodal questions across disciplines. It provides a reference for defining coverage and error categories instead of reporting an unexplained aggregate score.

28. **[MMLongBench-Doc: Benchmarking Long-context Document Understanding with Visualizations](https://proceedings.neurips.cc/paper_files/paper/2024/hash/ae0e43289bffea0c1fa34633fc608e92-Abstract-Datasets_and_Benchmarks_Track.html)**  
   2024 | Aliases / associated benchmarks: MMLongBench-Doc

   MMLongBench-Doc tests long-PDF understanding through cross-page evidence, charts, and unanswerable questions. Its diagnostic controls, including visual versus OCR input, illustrate how comparisons can identify a capability bottleneck.

29. **[LiveBench: A Challenging, Contamination-Limited LLM Benchmark](https://proceedings.iclr.cc/paper_files/paper/2025/hash/e4a46394ba5378b3f9a186a5b4c650d1-Abstract-Conference.html)**  
   2025 | Aliases / associated benchmarks: LiveBench

   LiveBench regularly creates objectively scored questions from recent sources to reduce contamination. Its relevance is data updates and version governance; “live” here describes question refreshes rather than an environment advancing during inference.

## Related benchmarks, extensions, and evaluation tools

30. **[MTEB: Massive Text Embedding Benchmark](https://aclanthology.org/2023.eacl-main.148/)**  
   2023 | Aliases / associated benchmarks: MTEB

   MTEB evaluates text embeddings across tasks, datasets, and languages to test generalization. It motivates multiple contexts and capability slices rather than treating success on one task as general decision competence.

31. **[BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models](https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/hash/65b9eea6e1cc6bb9f0cd2a47751a186f-Abstract-round2.html)**  
   2021 | Aliases / associated benchmarks: BEIR

   BEIR combines heterogeneous retrieval tasks and compares multiple methods under zero-shot transfer. It informs scenario diversity and the use of strong simple baselines to test complex capability claims.

32. **[Evaluating Large Language Models Trained on Code](https://arxiv.org/abs/2107.03374)**  
   2021 | Aliases / associated benchmarks: HumanEval / Codex

   The paper introduces Codex and HumanEval, evaluating code generated from function specifications through functional tests. It supplies an executable-scoring precedent, while independent problem solutions do not measure standing-decision duration.

33. **[MMMU-Pro: A More Robust Multi-discipline Multimodal Understanding Benchmark](https://aclanthology.org/2025.acl-long.736/)**  
   2025; 2024 preprint | Aliases / associated benchmarks: MMMU-Pro

   MMMU-Pro reduces multimodal shortcuts by removing text-only-solvable questions, strengthening choices, and changing presentation. It directly motivates testing whether similarity or other unintended cues suffice to score well, rather than merely increasing difficulty.

34. **[Ego4D Goal-Step: Toward Hierarchical Understanding of Procedural Activities](https://papers.neurips.cc/paper_files/paper/2023/hash/7a65606fa1a6849450550325832036e5-Abstract-Datasets_and_Benchmarks.html)**  
   2023 | Aliases / associated benchmarks: Ego4D Goal-Step

   Ego4D Goal-Step annotates goals, steps, and substeps of procedural activities for understanding and next-step prediction. Both it and SDB concern contextual action, but predicting what happens next differs from choosing what should be done now under prescribed rules.

35. **[SWE-smith: Scaling Data for Software Engineering Agents](https://proceedings.neurips.cc/paper_files/paper/2025/hash/8b86cf5ace600c48fd188efbb8dedec8-Abstract-Datasets_and_Benchmarks_Track.html)**  
   2025 | Aliases / associated benchmarks: SWE-smith

   SWE-smith creates executable repository environments and synthesizes test-failing repair tasks for agent training. It motivates executable verification of generated data, while primarily addressing training-data supply.

36. **[SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains?](https://proceedings.iclr.cc/paper_files/paper/2025/hash/07d6332ae36730707fddddba736d7b6c-Abstract-Conference.html)**  
   2025 | Aliases / associated benchmarks: SWE-bench Multimodal

   SWE-bench Multimodal extends software-repair evaluation to interface software with visual information and tests existing systems' generalization. It illustrates using additional conditions to check whether a capability persists and explaining how those conditions change the research question.

37. **[ImageNet: A Large-Scale Hierarchical Image Database](https://www.image-net.org/static_files/papers/imagenet_cvpr09.pdf)**  
   2009 | Aliases / associated benchmarks: ImageNet

   ImageNet builds a large labeled image database organized by the WordNet hierarchy for recognition and classification. In this catalog it serves as data-infrastructure and external-validation background, with no direct overlap in the definition of real-time decisions.

38. **[A Large-scale Study of Representation Learning with the Visual Task Adaptation Benchmark](https://arxiv.org/abs/1910.04867)**  
   2020; 2019 preprint | Aliases / associated benchmarks: VTAB

   VTAB evaluates representation learning on diverse few-shot visual tasks while controlling architecture and tuning budgets. It informs fair comparisons and cross-context generalization; the extended VTAB+ evaluation collection is not counted as a separate paper.

39. **[VLMEvalKit: An Open-Source Toolkit for Evaluating Large Multi-Modality Models](https://arxiv.org/abs/2407.11691)**  
   2024 | Aliases / associated benchmarks: VLMEvalKit

   VLMEvalKit standardizes model interfaces, data processing, and scoring to reproduce multimodal evaluations. It informs a harness that admits new models without changing scoring semantics.

## Official technical articles and dataset versions

40. **[Enabling Streaming Classification](https://blog.zentropi.ai/enabling-streaming-classification/)**  
   2026 | official technical article

   This technical article describes token-by-token classification signals from intermediate model representations before the input is complete. It overlaps with fast streaming output, while SDB must verify actions justified by current evidence rather than simply predict a final label early.

41. **[Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)**  
   2024 | official technical article

   The article introduces a human-verified SWE-bench subset through professional review of issues and tests. It motivates checking description/reference consistency and whether the evaluator accepts reasonable correct outputs, beyond ensuring the scorer executes.

42. **[Why SWE-bench Verified no longer measures frontier coding capabilities](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)**  
   2026 | official technical article

   The article analyzes testing defects and contamination in SWE-bench Verified and explains OpenAI's decision to stop reporting that score. It warns that deterministic scoring does not guarantee measurement validity and that benchmarks need independent audit and maintenance.

## Names and version attribution

- HFTBench and StreetFighter belong to *Win Fast or Lose Slow*. STAR, TicToc, ReactiveBench, and Belief-R are benchmark names within the listed papers, not additional papers.
- [SWE-bench Lite](https://www.swebench.com/lite.html) is the original benchmark's 300-task subset. Verified is a human-reviewed version; its release article is entry 41, not another conference paper.
- IQTest, FunctionQA, and PaperQA are MathVista subsets. This PaperQA is not a separate literature-question-answering system with the same name.
- MMLongBench here means MMLongBench-Doc. VTAB+ is an extended evaluation collection.
- CLIP, GLIDE, Stable Diffusion, OpenCLIP, LoRA, ViT, BM25, and other model/tool names appear as baselines or infrastructure; their original papers are outside this bounded catalog.
- LiveBench uses the formal ICLR 2025 title *Contamination-Limited*. The original AoII metric and its semantic-communication extension remain separate entries to avoid conflating authors and dates.
