# SDB log-AUC: Luna low

Primary normalized log-AUC over 0.5–8 s: **45.26%**; untimed accuracy: 88.75%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 46.70 |
| procedural_coaching | 43.28 |
| support_call_assist | 45.72 |
| presenter_voice_control | 45.36 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000537 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.
## SDB 錄製間距診斷：gpt-5.6-luna low

4 類、8 個獨立情境；各段長度 120 秒，證據釋出間距 2 秒，共 480 個 logical requests；每個狀態取得一份最終成功回覆；連線失敗依設定重試。模型設定為 gpt-5.6-luna、low reasoning；本報告所有模型分數皆來自實際回覆，沒有 placeholder。

**有效決策正確率（不計延遲）：88.75%；正確持續時間比例（排除連線重試）：47.70%。**

移除網路延遲後的正確持續時間（次要估計）：56.04%（範圍 52.08%–57.62%）。

## 各家族結果

| 家族 | 不計延遲：有效決策 | 正確持續時間 | 區段等權重時間分數 | 全部問題全對（診斷） |
|---|---:|---:|---:|---:|
| IDE 除錯 | 84.17% | 51.63% | 45.54% | 84.17% |
| 裝配流程 | 87.50% | 44.00% | 33.83% | 85.83% |
| 客服流程 | 86.67% | 49.74% | 41.71% | 80.83% |
| 簡報語音控制 | 96.67% | 45.45% | 33.73% | 96.67% |

有效決策由模型自己的分類、全域必要答案與該分支必要答案組成；未使用的分支不扣主分數。主分數在重建時間軸上計算：每個成功 attempt 的耗時從該狀態的證據釋出時刻起算，並保留實際後處理至接受檢查的耗時，排除失敗 attempt、重試等待與派送排隊；依重建抵達順序重新判定生效更新。它不是實際部署時鐘的正確時間，原始時鐘結果另外列出。家族與整體分數皆按情境等權重。

## 移除網路延遲後的估計（次要）

假設送出到收到回覆的時間 = 網路 + prefill（正比於未快取輸入 token）+ decode（正比於輸出 token，僅限生成文字的模型），不隨 token 變化的部分全部視為網路。排隊只會增加時間，因此以快速請求的下緣估計網路：第 10 百分位迴歸的截距，token 斜率不為負；範圍來自情境內連續 10 次釋出為一塊的 bootstrap（500 次）。

估計網路 0.585 秒（範圍 0.310–0.694 秒）；prefill 59.5 ms／1k token；decode 8.34 ms／token；最快回應 1.432 秒；扣到零的請求 0 個。

| 範圍 | 主分數 | 移除網路（估計） | 範圍 | 上限（不計延遲） |
|---|---:|---:|---:|---:|
| 整體 | 47.70% | 56.04% | 52.08%–57.62% | 88.75% |
| IDE 除錯 | 51.63% | 59.27% | 55.53%–60.63% | 84.17% |
| 裝配流程 | 44.00% | 52.42% | 48.32%–54.10% | 87.50% |
| 客服流程 | 49.74% | 58.80% | 54.66%–60.45% | 86.67% |
| 簡報語音控制 | 45.45% | 53.69% | 49.80%–55.30% | 96.67% |

這是次要估計，主分數不變。不隨 token 變化的時間也可能包含固定的伺服器時間，因此它是網路影響的上界；範圍只反映估計的不確定性，不含模型重跑的變異。

## 各獨立情境

| 情境 | 有效切換數 | 不計延遲 | 正確時間 | 回應 p50 / p95（秒） | 失敗請求 |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 83.33% | 52.31% | 2.18 / 3.55 | 0 |
| lite_debugging_b | 21 | 85.00% | 50.95% | 2.31 / 3.76 | 0 |
| lite_assembly_a | 21 | 91.67% | 50.55% | 2.44 / 3.59 | 0 |
| lite_assembly_b | 23 | 83.33% | 37.45% | 3.17 / 5.02 | 0 |
| lite_support_a | 22 | 81.67% | 48.67% | 1.91 / 2.86 | 0 |
| lite_support_b | 24 | 91.67% | 50.80% | 2.18 / 3.39 | 0 |
| lite_presenter_a | 24 | 100.00% | 47.18% | 2.73 / 3.76 | 0 |
| lite_presenter_b | 22 | 93.33% | 43.73% | 3.14 / 4.17 | 0 |

## 執行與計分核對

- 完成 480 個狀態、8 個情境；失敗請求 0。
- 成功 attempt延遲 p50 2.405 秒、p95 4.099 秒；包含該次本機 client 與正常網路時間。
- 原始錄製的最大釋出落後 0.0053 秒；最大派送落後 0.0000 秒。
- 有 9 個狀態只有未使用問題答錯，因此有效決策仍正確。
- 重建時間軸接受更新 464 次；未採用回覆：{"older_than_active": 7, "after_horizon": 9}。
- 使用 pipeline：每次釋出都送出一次請求；完整的新來源回覆原子生效，較舊來源晚到不得覆寫。情境間序列執行。
- 不計延遲分數使用同一批回覆，並非另外跑一次模型。SDK retries 為 0，網路 timeout 為 20 秒。
- 執行設定：retry_excluded_successful_attempt_v1，最多 32 個 request workers，情境並行數 1。
- 分數由本次分析以目前的計分程式從原始事件重算；原執行與本次分析的 source manifest 分別保存，僅供追溯。

錯誤持續時間另依當時使用的答案來源分類：尚無答案 21.55 秒；答案對原始證據正確、但對當前證據已不正確 386.34 秒；答案對原始證據即不正確，且對當前證據也不正確 94.15 秒。這是各情境的時間總和；來源分類不等同因果歸因。

## 連線可靠性與原始時鐘診斷

- 連線 attempt 錯誤率：0.00% （0 個失敗 attempts／全部 480 個 attempts，包含最終成功）。
- Logical request 重試率：0.00% （0 個曾重試 requests／全部 480 個 logical requests）。
- 失敗 attempt 類別：{}。
- 失敗 attempts 累計耗時 0.000 秒；排除的失敗與重試等待累計 0.000 秒，另外排除派送排隊累計 0.219 秒。各請求可重疊，累計秒數不是整段牆鐘時長。
- 設定最多 5 次 attempts；首次立即重試，後續以 0.5 秒為基礎退避，上限 8 秒；SDK 自動重試關閉。

原始時鐘保留所有實際失敗、等待與晚到交付，只作診斷，不與主分數混合：

| 範圍 | 原始正確時間 | 原始區段等權重時間 |
|---|---:|---:|
| 整體 | 47.70% | 38.70% |
| IDE 除錯 | 51.62% | 45.53% |
| 裝配流程 | 43.99% | 33.83% |
| 客服流程 | 49.73% | 41.70% |
| 簡報語音控制 | 45.45% | 33.73% |

原始 logical request 耗時（含失敗 attempts 與重試等待）p50 2.405 秒、p95 4.099 秒；原始接受更新 464 次。

重試耗盡或非連線錯誤會使整次執行標為 incomplete，不發布完整主分數。成功與否依 API／回應有效性判定，不依答案是否符合 gold 選擇重試。

## 簡單基線

下列為離線執行的本機基線，只比較答案正確性；未測量持續時間分數。

| 家族 | 固定第一選項 | 詞彙重疊 | gpt-5.6-luna low 有效決策 |
|---|---:|---:|---:|
| IDE 除錯 | 0.00% | 0.00% | 84.17% |
| 裝配流程 | 0.00% | 0.00% | 87.50% |
| 客服流程 | 1.67% | 0.00% | 86.67% |
| 簡報語音控制 | 0.00% | 0.00% | 96.67% |

## 錯誤定位

下表統計參考決策中必要答案的錯誤；分類錯誤本身仍使整個決策錯誤。同一時刻可能有多個錯誤問題，因此這裡的數量不能加總成錯誤時間。分支細節錯誤也可能伴隨分類錯誤，不能把各欄低分直接解釋成獨立能力缺陷。

| 情境 | 出錯的有效問題與狀態數 | 首批出錯 tick |
|---|---|---|
| lite_debugging_a | route: 10, rerun_scope: 3, inspect_file: 2 | 7, 8, 14, 18, 23, 26, 28, 29, 30, 58 |
| lite_debugging_b | route: 8, rerun_scope: 3, owner: 3, target_result: 1 | 25, 26, 28, 31, 32, 40, 44, 49, 50 |
| lite_assembly_a | route: 4, stage: 1, next_step: 1 | 14, 20, 31, 47, 48 |
| lite_assembly_b | route: 9, stage: 1, target: 1, method: 1, destination: 1 | 6, 7, 33, 40, 41, 42, 43, 48, 49, 51 |
| lite_support_a | recorder: 11 | 12, 13, 18, 20, 21, 43, 45, 46, 47, 48, 49 |
| lite_support_b | route: 5, repair_target: 2, repair_action: 2, delivery_target: 1, delivery_action: 1 | 5, 19, 40, 53, 55 |
| lite_presenter_a | 無 | 無 |
| lite_presenter_b | slide: 3, question_card: 1 | 41, 45, 47, 54 |

## 解讀範圍

這是開發資料的一次模型實測。各情境的相鄰狀態不能當作獨立樣本；本次不提供跨模型辨別力、重複實驗穩定性或部署有效性的結論。證據釋出間距為公開的受控設定，未經人類節奏驗證。語言參考求解使用有限的已編寫表達形式，不代表能理解任意自然語言。

時間與不計延遲分數的差值是兩種評估的描述性差異，並非單獨改變模型速度的因果效果。新資料在問題數、組合方式、情境與時間規則上都與舊版（v0）資料不同，不能把新舊分差直接歸因於 fan-out。資料與 gold 在執行前已固定；本輪未依模型錯誤改題或重跑。

## 可重現檔案

- [任務與執行規格](../../../PROTOCOL.md)
- [IDE 除錯問題與規則](../../../debugging.md)、[裝配問題與規則](../../../assembly.md)、[客服問題與規則](../../../support.md)、[簡報語音控制問題與規則](../../../presenter.md)
- [原始完整執行](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/run.json)
- [凍結資料](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/episodes.json)
- [逐次釋出與回覆紀錄](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/events.jsonl)
- [完整分數與每次錯誤](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/metrics.json)
- [原始時鐘診斷分數](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/raw_wallclock_metrics.json)
- [報告用分析資料](analysis.json)

在專案根目錄，從完成的原始紀錄重算報告與本機基線：

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1 --out docs/lite/results/four-family/gpt-5.6-luna-low --label 'Luna low'
```

Token usage（含 cached input，不另推估費用；僅加總回覆中取得的 usage，失敗請求未回傳的用量未知）：

```json
{
  "input_tokens": 1476489,
  "cached_tokens": 0,
  "output_tokens": 80072,
  "reasoning_tokens": 57632
}
```
