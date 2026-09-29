# SDB log-AUC: Terra low

Primary normalized log-AUC over 1–5 s: **52.60%**; untimed accuracy: 95.42%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 50.17 |
| procedural_coaching | 50.51 |
| support_call_assist | 56.04 |
| presenter_voice_control | 53.66 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000182 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.
## SDB 錄製間距診斷：gpt-5.6-terra low

4 類、8 個獨立情境；各段長度 120 秒，證據釋出間距 2 秒，共 480 個 logical requests；每個狀態取得一份最終成功回覆；連線失敗依設定重試。模型設定為 gpt-5.6-terra、low reasoning；本報告所有模型分數皆來自實際回覆，沒有 placeholder。

**有效決策正確率（不計延遲）：95.42%；正確持續時間比例（排除連線重試）：50.37%。**

移除網路延遲後的正確持續時間（次要估計）：60.90%（範圍 59.05%–62.27%）。

## 各家族結果

| 家族 | 不計延遲：有效決策 | 正確持續時間 | 區段等權重時間分數 | 全部問題全對（診斷） |
|---|---:|---:|---:|---:|
| IDE 除錯 | 99.17% | 48.18% | 42.35% | 99.17% |
| 裝配流程 | 92.50% | 47.97% | 37.80% | 92.50% |
| 客服流程 | 93.33% | 54.92% | 47.39% | 93.33% |
| 簡報語音控制 | 96.67% | 50.39% | 39.11% | 96.67% |

有效決策由模型自己的分類、全域必要答案與該分支必要答案組成；未使用的分支不扣主分數。主分數在重建時間軸上計算：每個成功 attempt 的耗時從該狀態的證據釋出時刻起算，並保留實際後處理至接受檢查的耗時，排除失敗 attempt、重試等待與派送排隊；依重建抵達順序重新判定生效更新。它不是實際部署時鐘的正確時間，原始時鐘結果另外列出。家族與整體分數皆按情境等權重。

## 移除網路延遲後的估計（次要）

假設送出到收到回覆的時間 = 網路 + prefill（正比於未快取輸入 token）+ decode（正比於輸出 token，僅限生成文字的模型），不隨 token 變化的部分全部視為網路。排隊只會增加時間，因此以快速請求的下緣估計網路：第 10 百分位迴歸的截距，token 斜率不為負；範圍來自情境內連續 10 次釋出為一塊的 bootstrap（500 次）。

估計網路 0.673 秒（範圍 0.558–0.754 秒）；prefill 0.0 ms／1k token；decode 12.10 ms／token；最快回應 1.168 秒；扣到零的請求 0 個。

| 範圍 | 主分數 | 移除網路（估計） | 範圍 | 上限（不計延遲） |
|---|---:|---:|---:|---:|
| 整體 | 50.37% | 60.90% | 59.05%–62.27% | 95.42% |
| IDE 除錯 | 48.18% | 59.37% | 57.43%–60.76% | 99.17% |
| 裝配流程 | 47.97% | 58.53% | 56.72%–59.91% | 92.50% |
| 客服流程 | 54.92% | 65.96% | 64.09%–67.35% | 93.33% |
| 簡報語音控制 | 50.39% | 59.73% | 57.97%–61.06% | 96.67% |

這是次要估計，主分數不變。不隨 token 變化的時間也可能包含固定的伺服器時間，因此它是網路影響的上界；範圍只反映估計的不確定性，不含模型重跑的變異。

## 各獨立情境

| 情境 | 有效切換數 | 不計延遲 | 正確時間 | 回應 p50 / p95（秒） | 失敗請求 |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 48.11% | 2.50 / 3.95 | 0 |
| lite_debugging_b | 21 | 98.33% | 48.25% | 2.52 / 4.45 | 0 |
| lite_assembly_a | 21 | 95.00% | 50.89% | 2.54 / 3.41 | 0 |
| lite_assembly_b | 23 | 90.00% | 45.05% | 2.83 / 3.91 | 0 |
| lite_support_a | 22 | 95.00% | 54.32% | 2.26 / 2.97 | 0 |
| lite_support_b | 24 | 91.67% | 55.53% | 2.04 / 2.89 | 0 |
| lite_presenter_a | 24 | 96.67% | 52.80% | 2.41 / 3.24 | 0 |
| lite_presenter_b | 22 | 96.67% | 47.98% | 2.91 / 3.61 | 0 |

## 執行與計分核對

- 完成 480 個狀態、8 個情境；失敗請求 0。
- 成功 attempt延遲 p50 2.439 秒、p95 3.774 秒；包含該次本機 client 與正常網路時間。
- 原始錄製的最大釋出落後 0.0101 秒；最大派送落後 0.0000 秒。
- 有 0 個狀態只有未使用問題答錯，因此有效決策仍正確。
- 重建時間軸接受更新 464 次；未採用回覆：{"older_than_active": 8, "after_horizon": 8}。
- 使用 pipeline：每次釋出都送出一次請求；完整的新來源回覆原子生效，較舊來源晚到不得覆寫。情境間序列執行。
- 不計延遲分數使用同一批回覆，並非另外跑一次模型。SDK retries 為 0，網路 timeout 為 20 秒。
- 執行設定：retry_excluded_successful_attempt_v1，最多 32 個 request workers，情境並行數 1。
- 分數由本次分析以目前的計分程式從原始事件重算；原執行與本次分析的 source manifest 分別保存，僅供追溯。

錯誤持續時間另依當時使用的答案來源分類：尚無答案 18.95 秒；答案對原始證據正確、但對當前證據已不正確 416.52 秒；答案對原始證據即不正確，且對當前證據也不正確 41.02 秒。這是各情境的時間總和；來源分類不等同因果歸因。

## 連線可靠性與原始時鐘診斷

- 連線 attempt 錯誤率：0.00% （0 個失敗 attempts／全部 480 個 attempts，包含最終成功）。
- Logical request 重試率：0.00% （0 個曾重試 requests／全部 480 個 logical requests）。
- 失敗 attempt 類別：{}。
- 失敗 attempts 累計耗時 0.000 秒；排除的失敗與重試等待累計 0.000 秒，另外排除派送排隊累計 0.260 秒。各請求可重疊，累計秒數不是整段牆鐘時長。
- 設定最多 5 次 attempts；首次立即重試，後續以 0.5 秒為基礎退避，上限 8 秒；SDK 自動重試關閉。

原始時鐘保留所有實際失敗、等待與晚到交付，只作診斷，不與主分數混合：

| 範圍 | 原始正確時間 | 原始區段等權重時間 |
|---|---:|---:|
| 整體 | 50.36% | 41.65% |
| IDE 除錯 | 48.17% | 42.34% |
| 裝配流程 | 47.96% | 37.79% |
| 客服流程 | 54.91% | 47.38% |
| 簡報語音控制 | 50.38% | 39.10% |

原始 logical request 耗時（含失敗 attempts 與重試等待）p50 2.439 秒、p95 3.774 秒；原始接受更新 464 次。

重試耗盡或非連線錯誤會使整次執行標為 incomplete，不發布完整主分數。成功與否依 API／回應有效性判定，不依答案是否符合 gold 選擇重試。

## 簡單基線

下列為離線執行的本機基線，只比較答案正確性；未測量持續時間分數。

| 家族 | 固定第一選項 | 詞彙重疊 | gpt-5.6-terra low 有效決策 |
|---|---:|---:|---:|
| IDE 除錯 | 0.00% | 0.00% | 99.17% |
| 裝配流程 | 0.00% | 0.00% | 92.50% |
| 客服流程 | 1.67% | 0.00% | 93.33% |
| 簡報語音控制 | 0.00% | 0.00% | 96.67% |

## 錯誤定位

下表統計參考決策中必要答案的錯誤；分類錯誤本身仍使整個決策錯誤。同一時刻可能有多個錯誤問題，因此這裡的數量不能加總成錯誤時間。分支細節錯誤也可能伴隨分類錯誤，不能把各欄低分直接解釋成獨立能力缺陷。

| 情境 | 出錯的有效問題與狀態數 | 首批出錯 tick |
|---|---|---|
| lite_debugging_a | 無 | 無 |
| lite_debugging_b | rerun_scope: 1 | 27 |
| lite_assembly_a | route: 3, next_step: 1 | 31, 47, 48 |
| lite_assembly_b | route: 6 | 32, 33, 42, 43, 48, 49 |
| lite_support_a | recorder: 3 | 17, 42, 50 |
| lite_support_b | route: 5, repair_target: 5, repair_action: 5 | 50, 52, 54, 55, 57 |
| lite_presenter_a | slide: 1, clip_state: 1 | 4, 26 |
| lite_presenter_b | question_card: 1, slide: 1 | 31, 53 |

## 解讀範圍

這是開發資料的一次模型實測。各情境的相鄰狀態不能當作獨立樣本；本次不提供跨模型辨別力、重複實驗穩定性或部署有效性的結論。證據釋出間距為公開的受控設定，未經人類節奏驗證。語言參考求解使用有限的已編寫表達形式，不代表能理解任意自然語言。

時間與不計延遲分數的差值是兩種評估的描述性差異，並非單獨改變模型速度的因果效果。新資料在問題數、組合方式、情境與時間規則上都與舊版（v0）資料不同，不能把新舊分差直接歸因於 fan-out。資料與 gold 在執行前已固定；本輪未依模型錯誤改題或重跑。

## 可重現檔案

- [任務與執行規格](../../../PROTOCOL.md)
- [IDE 除錯問題與規則](../../../debugging.md)、[裝配問題與規則](../../../assembly.md)、[客服問題與規則](../../../support.md)、[簡報語音控制問題與規則](../../../presenter.md)
- [原始完整執行](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/run.json)
- [凍結資料](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/episodes.json)
- [逐次釋出與回覆紀錄](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/events.jsonl)
- [完整分數與每次錯誤](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/metrics.json)
- [原始時鐘診斷分數](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/raw_wallclock_metrics.json)
- [報告用分析資料](analysis.json)

在專案根目錄，從完成的原始紀錄重算報告與本機基線：

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage（含 cached input，不另推估費用；僅加總回覆中取得的 usage，失敗請求未回傳的用量未知）：

```json
{
  "input_tokens": 1476489,
  "cached_tokens": 0,
  "output_tokens": 58236,
  "reasoning_tokens": 35884
}
```
