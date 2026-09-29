# StreamDecisionBench 文獻目錄

核對日期：2026-09-27。

本目錄收錄附件正文具名討論的研究、評測工具，以及為釐清 StreamDecisionBench（SDB）定位而補充的文獻，共 39 篇研究論文與 3 篇官方技術文章；不宣稱涵蓋整個領域。來源「附件」包括 Deep Research 報告和兩份貼上文字，「補充」表示本輪研究補入；每篇的關係說明是針對目前 SDB 設計的分析。

每項先說明研究內容，再說明與 SDB 的關係；年份採下列列明的發表或預印本版本，預印本不代表通過同儕審查。

**直接相關：即時行動、串流與持續更新**

1. **[Gaia2: Benchmarking LLM Agents on Dynamic and Asynchronous Environments](https://arxiv.org/abs/2602.11964)**  
   2026｜附件｜簡稱／相關 benchmark：Gaia2

   讓 agent 在獨立推進的非同步環境中操作工具，並以包含時序限制的動作驗證器評估表現。它與我們直接重疊於環境變化和推論延遲，因此我們要具體說明如何逐時刻評估目前生效的決策，以及這比動作驗證多提供什麼資訊。

2. **[Win Fast or Lose Slow: Balancing Speed and Accuracy in Latency-Sensitive Decisions of LLMs](https://proceedings.neurips.cc/paper_files/paper/2025/hash/ddaec864ba433e8889ab08dcf5c26e55-Abstract-Conference.html)**  
   2025｜附件｜簡稱／相關 benchmark：Win Fast or Lose Slow／HFTBench、StreetFighter

   透過交易與即時對戰測試 LLM 的決策品質和延遲如何共同影響收益。它已建立即時決策的速度—品質問題；我們可進一步用已知規則下的正確行動，定位錯誤決策持續了多久。

3. **[Beyond Scaling: Assessing Strategic Reasoning and Rapid Decision-Making Capability of LLMs in Zero-sum Environments](https://arxiv.org/abs/2603.09337)**  
   2026｜附件｜簡稱／相關 benchmark：STAR

   以同一套零和策略環境比較回合制與即時制，研究策略能力和行動速度的落差。它使「推理較強的模型可能因為較慢而輸掉」成為既有發現，我們需要提供更細的失效原因和發生條件。

4. **[Your LLM Agents are Temporally Blind: The Misalignment Between Tool Use Decisions and Human Time Perception](https://aclanthology.org/2026.findings-acl.1848/)**  
   2026｜附件｜簡稱／相關 benchmark：TicToc

   改變對話中經過的時間，測試 agent 是否在適當時機重新呼叫工具取得資訊。它與我們共享資訊過時的問題，但主要操弄輸入中的時間間隔，並非直接量測模型運算期間持續生效的決策。

5. **[Never Stop Thinking: Continuous-Time Language Agents](https://arxiv.org/abs/2609.17416)**  
   2026｜附件｜簡稱／相關 benchmark：Never Stop Thinking／ReactiveBench

   研究能在接收新輸入、思考及輸出之間交錯運作的語言 agent，並以 ReactiveBench 評估互動反應與可驗證的串流任務。它與我們重疊於連續輸入和即時回應，而我們的評估對象是外部目前採用的決策是否持續適切。

6. **[ProActor: Timing-Aware Reinforcement Learning for Proactive Task Scheduling Agents](https://aclanthology.org/2026.acl-long.832/)**  
   2026｜補充｜簡稱／相關 benchmark：ProActor

   以具有時機意識的強化學習訓練主動任務排程 agent，評估行動內容及在對話中的出手時機。它提醒我們「判斷下一步和何時執行」已有直接前例，我們需要進一步明確處理實際交付延遲與更新間隔中的決策有效性。

7. **[StreamingBench: Assessing the Gap for MLLMs to Achieve Streaming Video Understanding](https://arxiv.org/abs/2411.03628)**  
   2024 預印本；2026 會議版本｜附件｜簡稱／相關 benchmark：StreamingBench

   評估模型對串流影片的即時理解、連續問答及主動回應能力。它已涉及何時回應，因此我們與它的區別必須落在決策如何生效及如何隨時間計分，不能只訴諸文字和影片的差別。

8. **[StreamMemBench: Streaming Evaluation of Agent Memory for Future-Oriented Assistance](https://arxiv.org/abs/2606.14571)**  
   2026｜附件｜簡稱／相關 benchmark：StreamMemBench

   將連續觀察連接到初始及後續任務，檢查 agent 能否保存證據、利用資訊並重用互動回饋。它與我們共同要求過去情境影響後續行為，但主要測記憶的使用與重用，沒有將其延遲報告轉成目前生效決策的錯誤時間。

**證據更新與規則理解**

9. **[Belief Revision: The Adaptability of Large Language Models Reasoning](https://aclanthology.org/2024.emnlp-main.586/)**  
   2024｜附件｜簡稱／相關 benchmark：Belief Revision／Belief-R

   在既有前提之後加入新證據，測試模型是否適當修改或保留結論。它直接支持我們區分「該更新」與「不該更新」的設計，但沒有測量多次更新過程中的實際運算延遲。

10. **[DeltaLogic: Minimal Premise Edits Reveal Belief-Revision Failures in Logical Reasoning Models](https://arxiv.org/abs/2604.02733)**  
   2026；ICLR workshop｜附件｜簡稱／相關 benchmark：DeltaLogic

   透過最小前提修改，檢查模型是否因相關變化修正結論，以及是否被無關變化誤導。它是我們設計成對干預的直接前例，這類配對本身不足以成為新穎性主張。

11. **[CoPE: A Small Language Model for Steerable and Scalable Content Labeling](https://arxiv.org/abs/2512.18027)**  
   2025｜補充｜簡稱／相關 benchmark：CoPE

   訓練小型語言模型依使用者提供的政策標記內容，包含讓相同內容在不同政策下得到不同標籤的訓練。它提醒我們有限類別輸出也可以需要規則理解，因此要用情境依賴和捷徑測試界定任務難度。

**時間評估與方法基礎**

12. **[Evaluation and Optimisation of Incremental Processors](https://aclanthology.org/2011.dnd-2.10/)**  
   2011｜附件

   為增量語言處理建立正確率、時機與穩定性評估，並討論中途修正和不必要編輯。它是我們最直接的方法前例之一，代表「不能只看最後答案」和「要評估輸出抖動」早已有完整研究。

13. **[STACL: Simultaneous Translation with Implicit Anticipation and Controllable Latency using Prefix-to-Prefix Framework](https://aclanthology.org/P19-1289/)**  
   2019｜補充｜簡稱／相關 benchmark：STACL

   提出 prefix-to-prefix 翻譯、wait-k 策略與 Average Lagging，控制並衡量串流翻譯的輸出落後程度。它提供品質—延遲評估的基礎，但原始 lag 以來源詞進度衡量，不等於我們要計算的實際錯誤行動持續時間。

14. **[SimulMT to SimulST: Adapting Simultaneous Text Translation to End-to-End Simultaneous Speech Translation](https://aclanthology.org/2020.aacl-main.58/)**  
   2020｜補充｜簡稱／相關 benchmark：SimulMT to SimulST

   將同步文字翻譯方法延伸至語音，明確比較計入與不計入運算時間的延遲。它是我們區分資訊等待與計算耗時的前例，這個引用服務於評估方法而不增加目前的輸入模態。

15. **[SimulEval: An Evaluation Toolkit for Simultaneous Translation](https://aclanthology.org/2020.emnlp-demos.19/)**  
   2020｜補充｜簡稱／相關 benchmark：SimulEval

   提供統一的同步翻譯互動介面與品質、延遲評分工具。它對我們的價值在於將模型接入方式與評測協議標準化，避免不同實作使分數失去可比性。

16. **[The Age of Incorrect Information: A New Performance Metric for Status Updates](https://arxiv.org/abs/1907.06604)**  
   2019 預印本｜補充｜簡稱／相關 benchmark：Age of Incorrect Information：原始指標

   提出 AoII，讓狀態更新的成本同時反映接收端估計是否錯誤，以及錯誤持續的時間。它提供「資訊舊不代表資訊錯」的理論背景，也要求我們避免把所有時間化錯誤指標都宣稱為新概念。

17. **[The Age of Incorrect Information: an Enabler of Semantics-Empowered Communication](https://arxiv.org/abs/2012.13214)**  
   2020 預印本；2023 期刊｜補充｜簡稱／相關 benchmark：Age of Incorrect Information：語義通訊延伸

   比較 AoII、資訊年齡與一般錯誤成本，分析何時傳送更新才能改善接收端狀態。它與我們同樣關注持續存在的錯誤，但 AoII 可額外懲罰錯誤已延續的年齡，不能直接等同於單純累計錯誤時間。

18. **[Age of Information in Deep Learning-Driven Task-Oriented Communications](https://arxiv.org/abs/2301.04298)**  
   2023｜補充

   研究通訊資源如何同時影響下游分類正確率與服務延遲，並提出任務資訊年齡指標。它是速度與任務正確性共同評估的鄰近研究，對我們的啟發是讓時間成本對應任務結果，而非只報模型耗時。

19. **[Robust Online Monitoring of Signal Temporal Logic](https://ptolemy.berkeley.edu/projects/terraswarm/pubs/571.html)**  
   2015｜補充

   研究如何在訊號尚未完整到達時，持續監測時序邏輯規格的滿足程度。它是可執行規則和線上驗證的方法背景，我們仍需單獨建立從語言觀察到適當行動的測量。

**合成資料與受控測量**

20. **[CLEVR: A Diagnostic Dataset for Compositional Language and Elementary Visual Reasoning](https://cs.stanford.edu/people/jcjohns/clevr/)**  
   2017｜附件｜簡稱／相關 benchmark：CLEVR

   以合成場景和可執行的問題程序，控制視覺問答需要的推理能力並診斷捷徑。它是我們使用合成資料的核心方法參照：把情境、規則與文字呈現分開控制，使錯誤可以定位。

21. **[Kubric: A Scalable Dataset Generator](https://openaccess.thecvf.com/content/CVPR2022/html/Greff_Kubric_A_Scalable_Dataset_Generator_CVPR_2022_paper.html)**  
   2022｜附件｜簡稱／相關 benchmark：Kubric

   提供結合物理模擬與影像渲染的生成框架，產生可控制的場景和豐富標註。對我們的啟發是把生成器做成能操弄研究變因的工具，而資料量本身不能證明測量有效。

22. **[ProcTHOR: Large-Scale Embodied AI Using Procedural Generation](https://proceedings.neurips.cc/paper_files/paper/2022/hash/27c546ab1e4f1d7d638e6a8dfbad9a07-Abstract-Conference.html)**  
   2022｜附件｜簡稱／相關 benchmark：ProcTHOR

   程序化生成可互動的室內環境，研究環境規模、多樣性與外部任務遷移的關係。它主要提供訓練和研究環境；我們可借鏡其生成器以外的驗證方式，例如使用獨立撰寫的串流檢查泛化。

**Deep Research 報告的七篇核心案例**

23. **[Ego4D: Around the World in 3,000 Hours of Egocentric Video](https://openaccess.thecvf.com/content/CVPR2022/html/Grauman_Ego4D_Around_the_World_in_3000_Hours_of_Egocentric_Video_CVPR_2022_paper.html)**  
   2022｜附件｜簡稱／相關 benchmark：Ego4D

   建立大規模第一人稱日常影片資料，並設計記憶、互動和預測等評估任務。對我們的參考是先界定實際需要的能力，再決定情境抽樣、標註與分項評價。

24. **[LAION-5B: An Open Large-Scale Dataset for Training Next Generation Image-Text Models](https://papers.nips.cc/paper/2022/hash/a1859debfb3b59d094f3504d5ebb6c25-Abstract-Datasets_and_Benchmarks.html)**  
   2022｜附件｜簡稱／相關 benchmark：LAION-5B

   以自動篩選建立大規模開放圖文訓練資料，並透過下游模型實驗驗證用途。它屬於訓練資料基礎設施，對我們最有用的是資料管線、篩選偏差與品質驗證的經驗。

25. **[SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html)**  
   2024｜附件｜簡稱／相關 benchmark：SWE-bench

   要求模型根據真實 GitHub issue 和程式庫產生補丁，以執行測試判定是否解決問題。它對我們最重要的參考是把能力主張轉成可驗證結果，以及用診斷條件分離失敗來源。

26. **[MathVista: Evaluating Mathematical Reasoning of Foundation Models in Visual Contexts](https://proceedings.iclr.cc/paper_files/paper/2024/hash/663bce02a0050c4a11f1eb8a7f1429d3-Abstract-Conference.html)**  
   2024｜附件｜簡稱／相關 benchmark：MathVista

   整合視覺情境中的數學推理題，分析視覺理解與數學能力的交互作用。對我們的參考是先用能力分類找出測量缺口，再補上有針對性的資料與實驗。

27. **[MMMU: A Massive Multi-discipline Multimodal Understanding and Reasoning Benchmark for Expert AGI](https://openaccess.thecvf.com/content/CVPR2024/html/Yue_MMMU_A_Massive_Multi-discipline_Multimodal_Understanding_and_Reasoning_Benchmark_for_CVPR_2024_paper.html)**  
   2024｜附件｜簡稱／相關 benchmark：MMMU

   以大學程度的多學科圖文問題評估專業知識和推理。對我們的參考是如何建立能力涵蓋範圍與錯誤分類，避免只給一個難以解釋的總分。

28. **[MMLongBench-Doc: Benchmarking Long-context Document Understanding with Visualizations](https://proceedings.neurips.cc/paper_files/paper/2024/hash/ae0e43289bffea0c1fa34633fc608e92-Abstract-Datasets_and_Benchmarks_Track.html)**  
   2024｜附件｜簡稱／相關 benchmark：MMLongBench-Doc

   透過長 PDF 的跨頁證據、圖表和不可回答問題，測試長文件理解。它對我們的主要啟發是設計有診斷力的對照，例如比較視覺輸入和 OCR 文字輸入來辨認能力瓶頸。

29. **[LiveBench: A Challenging, Contamination-Limited LLM Benchmark](https://proceedings.iclr.cc/paper_files/paper/2025/hash/e4a46394ba5378b3f9a186a5b4c650d1-Abstract-Conference.html)**  
   2025｜附件｜簡稱／相關 benchmark：LiveBench

   定期從近期來源建立可客觀判分的題目，以降低測試污染。它對我們的參考是資料更新和版本治理，其中 live 指題庫更新，不等於模型推論期間的即時環境。

**報告另外點名的 benchmark、延伸研究與工具**

30. **[MTEB: Massive Text Embedding Benchmark](https://aclanthology.org/2023.eacl-main.148/)**  
   2023｜附件｜簡稱／相關 benchmark：MTEB

   跨任務、資料集及語言評估文字嵌入，檢查表現能否泛化。它提醒我們用多種情境和能力切片支持研究主張，避免把單一任務上的成功概括成一般決策能力。

31. **[BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models](https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/hash/65b9eea6e1cc6bb9f0cd2a47751a186f-Abstract-round2.html)**  
   2021｜附件｜簡稱／相關 benchmark：BEIR

   整合不同領域的檢索任務，評估零樣本泛化並比較多類檢索方法。它對我們的參考是異質情境的抽樣，以及用強而簡單的 baseline 檢驗複雜能力主張。

32. **[Evaluating Large Language Models Trained on Code](https://arxiv.org/abs/2107.03374)**  
   2021｜附件｜簡稱／相關 benchmark：HumanEval／Codex

   提出 Codex 與 HumanEval，根據函式說明生成程式並以測試衡量功能正確性。它提供可執行評分的參考，但每題的獨立解答評估沒有包含我們關注的決策持續時間。

33. **[MMMU-Pro: A More Robust Multi-discipline Multimodal Understanding Benchmark](https://aclanthology.org/2025.acl-long.736/)**  
   2025；2024 預印本｜附件｜簡稱／相關 benchmark：MMMU-Pro

   藉由排除僅靠文字可答的題目、強化選項和改變呈現形式，降低原有多模態測試的捷徑。它直接支持我們檢查相似度或其他非目標線索是否足以得分，而不只是把題目變難。

34. **[Ego4D Goal-Step: Toward Hierarchical Understanding of Procedural Activities](https://papers.neurips.cc/paper_files/paper/2023/hash/7a65606fa1a6849450550325832036e5-Abstract-Datasets_and_Benchmarks.html)**  
   2023｜附件｜簡稱／相關 benchmark：Ego4D Goal-Step

   為程序性活動建立目標、步驟和子步驟標註，支援活動理解與下一步預測。它與我們都關注行動的情境依賴，但預測接下來會發生什麼，與依指定規則判斷現在應做什麼，是需要明確區分的任務。

35. **[SWE-smith: Scaling Data for Software Engineering Agents](https://proceedings.neurips.cc/paper_files/paper/2025/hash/8b86cf5ace600c48fd188efbb8dedec8-Abstract-Datasets_and_Benchmarks_Track.html)**  
   2025｜附件｜簡稱／相關 benchmark：SWE-smith

   自動建立可執行的程式庫環境，合成會造成測試失敗的修復任務作為 agent 訓練資料。它對我們的參考是讓生成資料經過可執行驗證，而它主要解決訓練資料供應問題。

36. **[SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains?](https://proceedings.iclr.cc/paper_files/paper/2025/hash/07d6332ae36730707fddddba736d7b6c-Abstract-Conference.html)**  
   2025｜附件｜簡稱／相關 benchmark：SWE-bench Multimodal

   將軟體修復評估擴展到包含視覺資訊的使用者介面軟體，檢查既有系統的泛化。它對我們的啟發是用新增條件檢驗原本能力是否仍成立，並具體說明那些條件改變了什麼研究問題。

37. **[ImageNet: A Large-Scale Hierarchical Image Database](https://www.image-net.org/static_files/papers/imagenet_cvpr09.pdf)**  
   2009｜附件｜簡稱／相關 benchmark：ImageNet

   依 WordNet 語義階層建立大規模標註影像資料，支援辨識與分類研究。它在這份目錄中主要是資料基礎設施與外部驗證的背景，對我們的即時決策定義沒有直接的新穎性衝突。

38. **[A Large-scale Study of Representation Learning with the Visual Task Adaptation Benchmark](https://arxiv.org/abs/1910.04867)**  
   2020；2019 預印本｜附件｜簡稱／相關 benchmark：VTAB

   以多種少樣本視覺任務評估表示學習，並控制架構和調參預算等干擾因素。對我們的參考是公平比較與跨情境泛化；附件中的 VTAB+ 是延伸評測集合，不能另算一篇獨立論文。

39. **[VLMEvalKit: An Open-Source Toolkit for Evaluating Large Multi-Modality Models](https://arxiv.org/abs/2407.11691)**  
   2024｜附件｜簡稱／相關 benchmark：VLMEvalKit

   提供統一模型介面、資料處理和評分流程，以重現多模態模型的評估結果。它對我們的參考是評測工具的設計，使新模型容易接入且不改變評分語義。

**官方技術文章與資料版本**

40. **[Enabling Streaming Classification](https://blog.zentropi.ai/enabling-streaming-classification/)**  
   2026｜補充；技術文章

   介紹從模型中間表示逐 token 產生分類訊號，讓內容尚未完整到達時就能做出判斷。它與我們重疊於快速串流輸出，但我們需要驗證模型依當前證據選出的行動，而不能只將最終分類結果提前預測。

41. **[Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)**  
   2024｜附件；技術文章

   透過專業開發者審查題目和測試，建立 SWE-bench 的人工驗證子集。它提醒我們除了 scorer 能執行，也要檢查任務描述與正確答案是否一致，以及評分能否接受合理的正確輸出。

42. **[Why SWE-bench Verified no longer measures frontier coding capabilities](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)**  
   2026｜附件；技術文章

   分析 SWE-bench Verified 的測試缺陷與污染，說明 OpenAI 停止報告其分數的理由。它對我們的直接警示是確定性評分不保證測量有效，benchmark 仍需要獨立審核及維護。

**名稱與版本歸屬**

- HFTBench 和 StreetFighter 屬於 *Win Fast or Lose Slow*；STAR、TicToc、ReactiveBench、Belief-R 分別是上列論文中的 benchmark 名稱，不另計論文。
- [SWE-bench Lite](https://www.swebench.com/lite.html) 是原 benchmark 的 300 題子集；Verified 是人工篩選版本，其發布文章列於第 41 項，不當成另一篇會議論文。
- IQTest、FunctionQA、PaperQA 是 MathVista 建立的資料子集，引用 MathVista 即可；此處 PaperQA 不是其他同名文獻問答系統。
- 報告中的 MMLongBench 指 MMLongBench-Doc；VTAB+ 是延伸評測集合。
- CLIP、GLIDE、Stable Diffusion、OpenCLIP、LoRA、ViT、BM25 和其他模型名稱，在附件中作為 baseline 或工具出現；本目錄不據此展開它們各自的原始論文。
- LiveBench 採正式 ICLR 2025 版本的標題 *Contamination-Limited*；AoII 的原始指標論文與語義通訊延伸論文分列，避免混同作者和年代。
