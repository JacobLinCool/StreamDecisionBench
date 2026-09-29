# 各 task family 的 reference interval：文獻核對與呈現建議

> 歷史紀錄（2026-09-29）：撰寫時 presenter voice control 尚未納入論文；目前四個 family 的結果見 `docs/lite/results/four-family/`。

查核日期：2026-09-29。範圍是 paper 的 IDE debugging、assembly station、support call，另列目前資料集已新增、尚未納入 paper 結果的 presenter voice control。

## 1. 結論與候選設定

**依 family 選定 reference point，再對 family 分數等權平均，方法上合理。文獻支持不同互動情境需要不同時間尺度，但尚不能直接推出每個 family「應該使用」的唯一 time-step interval。**

主要缺口是：人因研究通常測量回應延遲、等待感受或工作完成速度；SDB 的 Δ 則控制環境發布狀態的間隔。兩者有關，卻不是同一個量。以下是 **literature-informed reference operating points**，不是實測的人類 P50、部署 SLA 或已校準的真實事件頻率。

| Family | 建議先討論的 Δ* | 選擇理由與證據強度 | 尚未建立的部分 |
|---|---:|---|---|
| IDE debugging | **1 s** | 即時 IDE 輔助已有 sub-second 至 1 s 的證據；1 s 可作為在使用者指定 1–5 s 範圍內的積極參考點。 | 最接近的數值研究是 code completion，並非本 benchmark 的 rerun／inspect／delegate action card；精確 Δ 的外推弱。 |
| Assembly station | **2 s** | 步驟完成後顯示下一指令，與 wearable cognitive assistance 最接近；2 s 可作為較寬鬆的整秒參考點。 | 2 s 不代表沒有負面影響，也不是組裝事件間隔的實測中位數；1 s 應保留為較嚴格比較。 |
| Support call | **1 s，暫定且證據較弱** | 對話研究顯示 sub-second 停頓已改變聽者感受，支持優先檢查較短的時間尺度。 | 對話回應、agent desktop 更新與 recorder control 是不同事情；找不到能直接校準整個 family 的秒數。 |
| Presenter voice control（另列） | **1 s，暫定** | Miller 的下一頁顯示建議比一般 2 s 規則更接近換投影片；可與 1 s 的互動連續性 guidance 交叉支持。 | 不是現代語音簡報控制實驗；不能涵蓋所有 pause／speaker-routing 動作的期限。 |

這組候選不是為了讓每個 family 都有不同數字；三個 1 s 也合理。**目前查到的證據沒有足夠理由將任一現有 family 的主要 reference point 放到 4–5 s。** 3–5 s 適合作為較慢環境的 sensitivity comparison。

選點原則：先看使用情境與研究量測的時間定義，再選容易解釋的整秒 operating point；不根據哪個模型在該秒數勝出來選。此筆記未重新計算模型分數。

## 2. 原始文獻實際支持什麼

以下標示「原文結果」與「本研究推論」。既有 introduction 的文獻優先，補充文獻只用來處理更貼近任務或數值仍缺證據的地方。每列的 DOI／全文連結可直接追查。

### IDE debugging

**E1 — Murali et al. (2024), AI-Assisted Code Authoring at Scale: Fine-Tuning, Deploying, and Mixed Methods Evaluation.** 已在 introduction 引用。DOI [10.1145/3643774](https://doi.org/10.1145/3643774)；查核 [作者全文 v2，§7.2](https://arxiv.org/html/2305.12050v2#S7.SS2)。

- 原文結果：作者依 developer feedback 報告，建議在 300–500 ms 出現是可接受的，且不應超過 1 s；也觀察到 end-to-end latency 上升時 acceptance 下降。
- 證據型態：部署經驗、混合方法研究中的使用者回饋；這不是「50% 使用者最多能等 1 s」的分布估計。
- 適用範圍：即時 inline code suggestion。SDB debugging 顯示的是測試／除錯狀態和下一步動作，並不在每次按鍵時產生要採用的程式碼。
- 推論：支持將 1 s 列為即時 IDE 元件的候選尺度，無法單獨驗證 debugging Δ=1 s。

**E2 — Dunay et al. (2024), Multi-line AI-Assisted Code Authoring.** 已在 introduction 引用。DOI [10.1145/3663529.3663836](https://doi.org/10.1145/3663529.3663836)；[作者全文，§4.2、§5.1、Fig. 7](https://arxiv.org/html/2402.04141v1)。

- 原文結果：優化後，single-line suggestion 的 median latency 由 440 降至 280 ms，multi-line 由 2000 降至 750 ms；作者報告 accepted characters 相對增加 16%。建議會隨檔案狀態失效。
- 這裡確實有 **P50（median）**，但它是系統建議延遲，不是人類容忍度或事件間距。另有「顯示超過 750 ms 才納入 acceptance」的量測規則，不能混為同一個 750 ms。
- 限制：streaming、parallelism、batching 等一起改善；不應把全部效果解讀成固定減少某段延遲的純因果係數。

**E3 — Saff & Ernst (2004), An Experimental Evaluation of Continuous Testing During Development.** 補充更接近 debugging 的情境。DOI [10.1145/1007512.1007523](https://doi.org/10.1145/1007512.1007523)；[作者全文，§2、§4、§6](https://homes.cs.washington.edu/~mernst/pubs/ct-user-study.pdf)。

- 原文研究：在編輯過程背景執行測試並顯示 regression 狀態，比較 continuous testing、continuous compilation 與 control。
- 此研究支持持續測試回饋的用途，但沒有用 1／2／5 s 的受控回應延遲條件來辨識 action-card 的最佳秒數。因此不能用它替 3 s 或 5 s 做數值背書。

**判斷：** IDE 1 s 是合理、但較積極的類比選擇。若作者將任務明確定位成較慢的 test-run orchestration，2 s 也是應檢查的替代值；目前沒有證據能說 1 s 在這個具體任務上已被驗證優於 2 s。

### Assembly station

**E4 — Chen et al. (2017), An Empirical Study of Latency in an Emerging Class of Edge Computing Applications for Wearable Cognitive Assistance.** 已在 introduction 引用。DOI [10.1145/3132211.3134458](https://doi.org/10.1145/3132211.3134458)；[作者全文，§5.3、Fig. 16，p. 12](https://www.cs.cmu.edu/~zhuoc/papers/latency2017.pdf#page=12)。方法核對詳見 [assembly 證據記錄](assembly-evidence.md)。

- 13 位參與者的 LEGO／Google Glass 指導實驗提出約 **600 ms tight bound、2.7 s loose bound**。
- 600 ms 來自 step-completion-to-signal 的平均時間扣除估計動作啟動時間；2.7 s 結合受控延遲條件的滿意度和系統 overhead。兩者都不是 P50，也不是觀察到的步驟間距。
- 推論：同樣是判斷步驟已完成後更新指導，情境接近；2 s 可作為低於該寬鬆界線的候選，不能解讀成所有操作員都能無損等待 2 s。

**E5 — Olguín Muñoz et al. (2021), Impact of Delayed Response on Wearable Cognitive Assistance.** 已在 introduction 引用。DOI／[全文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0248690)，§3.2、§4、§5，Fig. 4、6–7。

- 40 位參與者；在 **1.65 s 與 3.0 s controlled-delay conditions** 下，使用者自己的步驟執行時間平均增加約 12% 與 26%，這個 slowdown 已排除直接等系統的時間。
- 延遲是受控 processing／feedback target，不能簡寫成「在原本 end-to-end latency 上再加同樣秒數」。
- 推論：這是反對把 3–5 s 稱為普遍舒適區的直接證據。它也提醒我們：選 2 s operating point 是較寬鬆的研究設定，不是無影響門檻。

**判斷：** 三個主要 family 中，assembly 的使用情境與數值依據最接近，但「回應延遲」到「Δ」的轉換仍是 benchmark 設計判斷。

### Support call

**E6 — PCI SSC (2018), Protecting Telephone-Based Payment Card Data, v3.0.** 已在 introduction 引用。[官方全文](https://listings.pcisecuritystandards.org/documents/Protecting_Telephone_Based_Payment_Card_Data_v3-0_nov_2018.pdf)，§6.5.1，印刷頁 36–38。

- 原文以付款欄位、付款畫面和 submit 等 desktop workflow events 說明自動 pause-and-resume；有效性取決於流程整合及正確時機。
- **該節沒有提供可拿來設定 Δ 的 1、2 或 5 s 數值容忍門檻，也未測量 speech-driven recorder decisions。**
- 推論：這份文件支持問題的重要性，無法證明「延後一秒停止錄音可接受」。SDB 的 transcript-triggered recorder 是本 benchmark 的設計。

**E7 — Roberts & Francis (2013), Identifying a Temporal Threshold of Tolerance for Silent Gaps after Requests.** 補充數值證據。DOI [10.1121/1.4802900](https://doi.org/10.1121/1.4802900)；[作者全文](https://web.ics.purdue.edu/~francisa/Articles/Roberts-Francis_JASAEL13.pdf)，§2–4，EL472–EL475、Fig. 1。

- 380 位受試者聽模擬朋友間的電話對話；request 後的相同肯定答覆被設為 200–1200 ms、每 100 ms 一個條件。
- willingness 評分在 600 ms 後開始下降；700 與 800 ms 間的下降達顯著。這是第三方聽者的社會判斷，不是客服員等待建議的實驗，也不是錄音保護時限。
- 推論：支持 support 相關互動可能需要 sub-second responsiveness；在限定 1–5 s 的探索內先看 1 s，比以 5 s 為主要設定有較好的方向性依據。

**E8 — Roberts, Francis & Morgan (2006), The Interaction of Inter-turn Silence with Prosodic Cues in Listener Perceptions of “Trouble” in Conversation.** DOI [10.1016/j.specom.2006.02.001](https://doi.org/10.1016/j.specom.2006.02.001)；[原文 PDF](https://citeseerx.ist.psu.edu/document?doi=1333d86632e61be810091e75d06512b043e5dfef&repid=rep1&type=pdf)，摘要與方法設計。

- 原文操弄 0／600／1200 ms 的 inter-turn silence，評分隨停頓增加而降低。它與 E7 方向一致；E7 的較密條件更適合討論轉折位置。
- 本次只作補充核對，不用這三個條件推算精確門檻或人類 P50。

**E9 — Stivers et al. (2009), Universals and Cultural Variation in Turn-Taking in Conversation.** DOI [10.1073/pnas.0903616106](https://doi.org/10.1073/pnas.0903616106)；[研究機構紀錄](https://www.mpi.nl/publications/item66202/universals-and-cultural-variation-turn-taking-conversation)／[原文](https://cognitionandculture.net/wp-content/uploads/Stivers_2009_universals.pdf)，Results: Distribution of Turn Transitions，p. 10588。

- 跨十語言的 polar-question responses：overall median gap **+100 ms**，mean **+208 ms**；各語言 median 約 0–300 ms。
- 這是實測的對話 turn-transition 分布；不是每句話的長度、ASR 更新間隔、客服系統推理時間或可接受等待的分布。

**判斷：** support 1 s 的方向性理由存在，完整 family 的校準證據仍不足。不能宣稱整個 family 遵循同一個自然人類時限；recorder 與 service／delivery guidance 的需求尤其不同。額外報 recorder 錯誤暴露時間會比聲稱「1 s 安全」更有意義，但它是未來的診斷項目，並非本次變更。

### 一般原則，以及 presenter 的補充依據

**E10 — Miller (1968), Response Time in Man-Computer Conversational Transactions.** 已在 introduction 引用。DOI [10.1145/1476589.1476628](https://doi.org/10.1145/1476589.1476628)；[原文掃描全文](https://www.yusufarslan.net/sites/yusufarslan.net/files/upload/content/Miller1968.pdf)。

- p. 267 明確反對把 2 s 當成所有情境的通則；p. 269 的 2 s 是 meaningful reply 的一般 guidance。
- **Topic 10，p. 274：請求下一頁後，至少最前面幾行應在 1 s 內顯示。** 這是 presenter 換頁的相關設計類比，不是受控實驗或 percentile。
- 同篇的其他情境允許更長等待；例如完整工作任務結束後領取下一份 assignment。不能只因也叫「工廠／下一步」就移用到持續組裝中的即時指導。

**E11 — Nielsen (1993), Response Times: The 3 Important Limits.** [作者書籍摘錄](https://www.nngroup.com/articles/response-times-3-important-limits/)。1 s 維持思考連續性的 guidance 可以作旁證；它不提供各 family 的事件頻率或 P50，亦不應勝過更貼近情境的實證。

**E12 — Gergle, Kraut & Fussell (2006), The Impact of Delayed Visual Feedback on Collaborative Performance.** 已在 introduction 引用。DOI [10.1145/1124772.1124968](https://doi.org/10.1145/1124772.1124968)；查核 [作者博士論文重刊的 Chapter 4](https://dgergle.soc.northwestern.edu/resources/Gergle_Dissertation2006.pdf)，§4.4，印刷頁 57–61；p. 41 註明與 CHI 論文的關係。

- 研究分別操弄 **visual-feedback delay** 與 **object change rate**。物件顯著變色約每 6–8 s、2–3 s、或 1 s 以下一次；環境變快時，可容忍的延遲縮短。
- 例如 6–8 s 的 moderate-change condition，模型識別的初始 delay breakpoint 約 431 ms。這正好說明「世界多久變一次」與「訊息可以晚多久」並不相等。
- 推論：強力支持 family-specific 環境節奏的研究動機，卻不能把該 puzzle 的 breakpoint 直接指定給 IDE、組裝或客服。

Presenter 的完整輸出還包括 clip pause 與 captions speaker routing；其中 captions 是決定顯示哪個聲源，不是產生字幕文字。因此不能拿一般字幕文字延遲的 3–5 s 上限，替這個完整 composed decision 設定寬鬆 reference。Miller 的 1 s 類比主要支持換頁分支。

## 3. P50／median 到底能不能找

P50 就是 median；mean 則是平均值，三者名稱不可互換。這次找到的數值是不同測量對象：

| 數值 | 測的是什麼 | 能否當 family Δ 的實測 P50？ |
|---|---|---|
| Dunay：multi-line 2.0 → 0.75 s | 系統 suggestion latency 的 median | 否 |
| Chen：0.6／2.7 s | 由行為與滿意度推導的 tight／loose latency bounds | 否；也不是 P50／P95 |
| Olguín：1.65／3 s | 實驗的 delay conditions | 否 |
| Roberts：0.7 → 0.8 s | 評分曲線相鄰條件的顯著變化 | 否 |
| Stivers：0.1 s median、0.208 s mean | 問答之間的 turn-transition gap | 否 |
| Miller：1／2 s | 使用情境相關的設計 guidance | 否 |

**目前未找到與 SDB 這些具體 composed decisions 匹配的真實事件／reference-change 間距分布。** 因此無法誠實地聲稱「我們從各任務的文獻 P50 選了 1／2／1 s」。能說的是：文獻提供互動尺度，據此宣告 benchmark reference points，並完整呈現 sensitivity。

## 4. 先確定 reference interval 的語意

設第 i 個 public state 在 iΔ 發布，元件收到完整可用 state 後花 L_i 秒交付決策。

- **Δ：** 環境 state 發布間隔；相同決策可能跨多個 ticks 不變。
- **L：** decision component 的回應延遲。
- **B：** 某種互動的人因回應預算／容忍範圍。
- **D：** 一個 reference decision 持續有效的時間，即 segment dwell time。

文獻通常測 L 或 B；本 benchmark 改 Δ，同時改變 D。**B=1 s 並不推出 Δ=1 s，也不推出 D=1 s。** 若新增一個「1 s 內都算對」的 grace window，則是改了評估問題，不是現在的 in-force accuracy；此建議不需要加入 grace window。

### 現有資料的時間結構核對

以公開 gold 經 `decision_spec` 組合後，計算 maximal constant reference segments。這些數字來自合成資料，不能當作外部人因證據。

| Scenario | Reference 變化次數 | Segment median（ticks） | 候選 Δ* | 候選下 median dwell |
|---|---:|---:|---:|---:|
| Debugging A | 20 | 3 | 1 s | 3 s |
| Debugging B | 21 | 2 | 1 s | 2 s |
| Assembly A | 21 | 2 | 2 s | 4 s |
| Assembly B | 23 | 2 | 2 s | 4 s |
| Support A | 22 | 2 | 1 s | 2 s |
| Support B | 24 | 2 | 1 s | 2 s |
| Presenter A | 24 | 2 | 1 s | 2 s |
| Presenter B | 22 | 2 | 1 s | 2 s |

重現：[timeline_audit.py](timeline_audit.py)；完整 segment lengths、來源 hash 與 frozen-data 一致性在 [timeline-audit.json](timeline-audit.json)。中位數對 segments 等權，非按每個時間瞬間加權。前六個 scenario 與 paper 使用的 frozen build 相同；presenter 另列。

改 Δ 還有以下實際含義：

1. 60 ticks 在 1／2／5 s 下成為 60／120／300 s 的 scenario；不是只讓模型多等幾秒。
2. ticks 表達的政策時間一起改變。例如 debugging 的 2-tick save grace、4-tick stalled threshold、6-tick stop threshold，在 Δ=1 s 是 2／4／6 s，在 Δ=5 s 是 10／20／30 s。
3. Support A 的 4-tick hold threshold 也從 recorded Δ=2 s 的 8 s，變成候選 Δ=1 s 的 4 s。這些是合成規則，不能誤稱產業標準。
4. 語音任務的 upstream ASR、evidence availability 與實際 UI／actuator 的時間，不等於 component inference latency。SDB 的現有輸入從 public evidence 開始；不能直接將完整人類互動 latency budget 全數當作模型可用時間。

若未來希望「環境節奏不變，只改合理回應預算」，必須另定參數／指標；若希望校準真實 Δ，則要量測 evidence arrivals 和 reference changes。兩者都不是單純修改表格標題。

## 5. 建議的主結果與平均方法

對模型 m、family f、scenario e，先在指定 Δ_f* 下計算原本的 in-force accuracy：

\[
A_{mfe}(\Delta_f^*)=\frac{1}{H_{fe}}\int_0^{H_{fe}}\mathbf{1}\{d_{mfe}(t)=y^*_{fe}(t)\}\,dt.
\]

再先平均同 family 的 scenarios，最後平均 families：

\[
A_{mf}^*=\frac{1}{n_f}\sum_{e=1}^{n_f}A_{mfe}(\Delta_f^*),\qquad
S_m^*=\frac{1}{F}\sum_{f=1}^{F}A_{mf}^*.
\]

主表欄位可直接寫成：

| Model | IDE A@1 s | Assembly A@2 s | Support A@1 s | Family macro-average |
|---|---|---|---|---|
| 每個 model setting 一列 | 待後續決定採用後計算 | 待計算 | 待計算 | 前三欄等權平均 |

表註必須宣告 `Δ*=(1, 2, 1) s`、family 權重和 dataset version。加入 presenter 時是四-family aggregate，應用新的版本／標籤；不可和舊三-family overall 當同一項比較。

這樣的平均表示「在各 family 宣告的環境條件下，平均正確的時間比例」，不是跨所有真實部署秒數的正確率，也不是使用者滿意度分數。

**不要將各 family 的 correct seconds 直接加總再除總秒數。** 相同 scenario 數量下，候選 `(1,2,1)` 會讓 assembly 因 horizon 加倍而取得 1/2 權重，另外兩個 family 各只有 1/4。先做 scenario 的時間正規化，再做 family macro-average，才符合各 family 等權的意圖。現在每 family 都有兩個 scenarios，兩階段等權平均恰好等同六個 scenario accuracy 的平均；未來樣本數不同就不一定。

不必再除以 Δ，也不要將 accuracy 乘上秒數做額外修正。保持同 family 內所有模型使用相同 Δ、同 acceptance policy 和同 network 處理方式。若另報 network-removed 結果，沿用現有不確定性區間與假設。

## 6. 共同設定與 appendix figure

**主結果採 family reference points；共同設定作 sensitivity。** 兩種比較回答的問題不同，不能因為所有模型都用相同秒數，就宣稱該設定已達成部署情境上的公平校準。

- 若希望一個「至少和各 family reference 一樣寬鬆」的共同 interval，先用 `Δ_common=max_f Δ_f*=2 s`。這也保留與現有三-family結果對照的價值。
- 另列 **共同 5 s**，作為使用者指定 1–5 s 範圍的慢端比較。它不是文獻證明的普遍容忍值。
- 5 s 意味環境變慢；一般會減少 stale exposure，但完整模型 accuracy 不必然處處單調，因此不能稱為所有模型的嚴格 score upper bound。

建議一張 appendix figure，以三個 family panels 加一個 common-interval aggregate panel 組成：

1. 每個 family panel：x 軸為 Δ（1–5 s），y 軸為 in-force accuracy，各模型一條曲線；用垂直線與曲線上的點標示該 family 的 Δ_f*。
2. 各 family panel 共享座標尺度，並標出共同 2 s 與 5 s，讀者可比較採同一 interval 的差異。
3. 第四 panel 顯示 `S_m(common Δ)=mean_f A_mf(Δ)`；family-specific macro-average 是 reference vector 上的值，不能假裝它對應某個單一共同 x 座標。可在 panel 旁列小表或獨立點欄。
4. Presenter 在有相應 recorded runs 之後加入同類型 panel；目前只提供 reference 建議，不補造曲線。

可再補一個簡短 robustness table：基準 `(1,2,1)`，逐一將 IDE 改 2、assembly 改 1 或 3、support 改 2，以及共同 `(2,2,2)`／`(5,5,5)`。這幾個對照優先檢查最薄弱的外推，避免只報選中 operating point 的排名。

Replay 時保持 recorded answers 和以秒表示的 latency 不變，改事件時間軸；或使用現有 scorer 的等價 latency scaling `c_f=Δ_recorded/Δ_f*`，重新計算 arrival order、acceptance 和 horizon clipping。不能直接從舊 accuracy 用比例換算。這依賴原本的 open-loop、tick-valued state 與 latency 對 request rate 不變的假設；不能將 replay 當成已量測新負載下的服務表現。

## 7. 哪些說法已足夠、哪些仍需補證據

| 擬採說法 | 查核判斷 |
|---|---|
| 不同互動情境對 latency 的要求不同，無需全部固定 2 s。 | **支持。** |
| 在宣告的 family reference points 評估後等權平均。 | **方法成立。** 同時交代各點、權重和 replay 假設。 |
| 現有文獻直接量出我們各 family 最適合的 Δ。 | **不支持。** 最關鍵的 latency-to-cadence mapping 尚未校準。 |
| 1／2／1 s 是文獻啟發、事先宣告的 benchmark 設定。 | **可辯護，但外推強度不一。** Support 最需保留語氣。 |
| 這些數字是 human tolerance P50 或無損等待門檻。 | **不支持。** |
| 3–5 s 可以一律視為合理的寬鬆主要設定。 | **不支持。** 可以作共同慢端的敏感度比較。 |

若要把「候選 operating points」提升成「經驗校準的 reference intervals」，最有價值的補充是：量測真實 IDE action-card、assembly evidence、support desktop、presenter control 的 evidence arrival／reference-change 分布，並在相應 UI 上操弄決策延遲。事件節奏與可容忍延遲應分開估計；才有可對應的 P50／P90 和效能或體驗曲線。

本次文獻結果足以支持先討論 `(1,2,1)` 的 family-specific reporting 方案；尚不足以把這三個精確秒數寫成文獻已確立的任務標準。
