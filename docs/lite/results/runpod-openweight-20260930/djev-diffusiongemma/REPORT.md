# SDB log-AUC: DJev / DiffusionGemma

Primary normalized log-AUC over 0.5–8 s: **20.95%**; untimed accuracy: 21.88%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 22.59 |
| procedural_coaching | 6.15 |
| support_call_assist | 28.63 |
| presenter_voice_control | 26.43 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000262 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.
## SDB 錄製間距診斷：dgemma

4 類、8 個獨立情境；各段長度 120 秒，證據釋出間距 2 秒，共 480 個 logical requests；每個狀態取得一份最終成功回覆；連線失敗依設定重試。模型設定為 dgemma；本報告所有模型分數皆來自實際回覆，沒有 placeholder。

**有效決策正確率（不計延遲）：21.88%；正確持續時間比例（排除連線重試）：21.19%。**

移除網路延遲後的正確持續時間（次要估計）：21.59%（範圍 21.56%–21.64%）。

[錯誤案例與下一步建議](FINDINGS.md)逐項對照公開規則，說明值得補測的判斷需求。

## 各家族結果

| 家族 | 不計延遲：有效決策 | 正確持續時間 | 區段等權重時間分數 | 全部問題全對（診斷） |
|---|---:|---:|---:|---:|
| IDE 除錯 | 23.33% | 22.78% | 18.24% | 16.67% |
| 裝配流程 | 6.67% | 6.29% | 7.09% | 4.17% |
| 客服流程 | 30.00% | 28.99% | 28.31% | 12.50% |
| 簡報語音控制 | 27.50% | 26.71% | 21.08% | 16.67% |

有效決策由模型自己的分類、全域必要答案與該分支必要答案組成；未使用的分支不扣主分數。主分數在重建時間軸上計算：每個成功 attempt 的耗時從該狀態的證據釋出時刻起算，並保留實際後處理至接受檢查的耗時，排除失敗 attempt、重試等待與派送排隊；依重建抵達順序重新判定生效更新。它不是實際部署時鐘的正確時間，原始時鐘結果另外列出。家族與整體分數皆按情境等權重。

## 移除網路延遲後的估計（次要）

假設送出到收到回覆的時間 = 網路 + prefill（正比於未快取輸入 token）+ decode（正比於輸出 token，僅限生成文字的模型），不隨 token 變化的部分全部視為網路。排隊只會增加時間，因此以快速請求的下緣估計網路：第 10 百分位迴歸的截距，token 斜率不為負；範圍來自情境內連續 10 次釋出為一塊的 bootstrap（500 次）。

估計網路 0.141 秒（範圍 0.131–0.160 秒）；prefill 29.1 ms／1k token；不含 decode 項（模型不生成文字）；最快回應 0.084 秒；扣到零的請求 3 個。

| 範圍 | 主分數 | 移除網路（估計） | 範圍 | 上限（不計延遲） |
|---|---:|---:|---:|---:|
| 整體 | 21.19% | 21.59% | 21.56%–21.64% | 21.88% |
| IDE 除錯 | 22.78% | 23.14% | 23.11%–23.18% | 23.33% |
| 裝配流程 | 6.29% | 6.46% | 6.45%–6.49% | 6.67% |
| 客服流程 | 28.99% | 29.64% | 29.59%–29.72% | 30.00% |
| 簡報語音控制 | 26.71% | 27.12% | 27.09%–27.17% | 27.50% |

這是次要估計，主分數不變。不隨 token 變化的時間也可能包含固定的伺服器時間，因此它是網路影響的上界；範圍只反映估計的不確定性，不含模型重跑的變異。

## 各獨立情境

| 情境 | 有效切換數 | 不計延遲 | 正確時間 | 回應 p50 / p95（秒） | 失敗請求 |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 6.67% | 6.68% | 0.26 / 3.30 | 0 |
| lite_debugging_b | 21 | 40.00% | 38.89% | 0.24 / 0.29 | 0 |
| lite_assembly_a | 21 | 5.00% | 4.99% | 0.31 / 0.40 | 0 |
| lite_assembly_b | 23 | 8.33% | 7.58% | 0.32 / 0.44 | 0 |
| lite_support_a | 22 | 13.33% | 13.15% | 0.24 / 0.28 | 0 |
| lite_support_b | 24 | 46.67% | 44.83% | 0.23 / 0.27 | 0 |
| lite_presenter_a | 24 | 31.67% | 31.03% | 0.26 / 0.31 | 0 |
| lite_presenter_b | 22 | 23.33% | 22.39% | 0.26 / 0.30 | 0 |

## 執行與計分核對

- 完成 480 個狀態、8 個情境；失敗請求 0。
- 成功 attempt延遲 p50 0.257 秒、p95 0.403 秒；包含該次本機 client 與正常網路時間。
- 原始錄製的最大釋出落後 0.0004 秒；最大派送落後 0.0000 秒。
- 有 45 個狀態只有未使用問題答錯，因此有效決策仍正確。
- 重建時間軸接受更新 480 次；未採用回覆：{}。
- 使用 pipeline：每次釋出都送出一次請求；完整的新來源回覆原子生效，較舊來源晚到不得覆寫。情境間序列執行。
- 不計延遲分數使用同一批回覆，並非另外跑一次模型。SDK retries 為 0，網路 timeout 為 90 秒。
- 執行設定：retry_excluded_successful_attempt_v1，最多 32 個 request workers，情境並行數 1。
- 分數由本次分析以目前的計分程式從原始事件重算；原執行與本次分析的 source manifest 分別保存，僅供追溯。

錯誤持續時間另依當時使用的答案來源分類：尚無答案 5.65 秒；答案對原始證據正確、但對當前證據已不正確 8.71 秒；答案對原始證據即不正確，且對當前證據也不正確 742.20 秒。這是各情境的時間總和；來源分類不等同因果歸因。

## 連線可靠性與原始時鐘診斷

- 連線 attempt 錯誤率：0.00% （0 個失敗 attempts／全部 480 個 attempts，包含最終成功）。
- Logical request 重試率：0.00% （0 個曾重試 requests／全部 480 個 logical requests）。
- 失敗 attempt 類別：{}。
- 失敗 attempts 累計耗時 0.000 秒；排除的失敗與重試等待累計 0.000 秒，另外排除派送排隊累計 0.195 秒。各請求可重疊，累計秒數不是整段牆鐘時長。
- 設定最多 3 次 attempts；首次立即重試，後續以 0.5 秒為基礎退避，上限 8 秒；SDK 自動重試關閉。

原始時鐘保留所有實際失敗、等待與晚到交付，只作診斷，不與主分數混合：

| 範圍 | 原始正確時間 | 原始區段等權重時間 |
|---|---:|---:|
| 整體 | 21.19% | 18.68% |
| IDE 除錯 | 22.78% | 18.24% |
| 裝配流程 | 6.29% | 7.09% |
| 客服流程 | 28.99% | 28.31% |
| 簡報語音控制 | 26.70% | 21.08% |

原始 logical request 耗時（含失敗 attempts 與重試等待）p50 0.257 秒、p95 0.403 秒；原始接受更新 480 次。

重試耗盡或非連線錯誤會使整次執行標為 incomplete，不發布完整主分數。成功與否依 API／回應有效性判定，不依答案是否符合 gold 選擇重試。

## 簡單基線

下列為離線執行的本機基線，只比較答案正確性；未測量持續時間分數。

| 家族 | 固定第一選項 | 詞彙重疊 | dgemma 有效決策 |
|---|---:|---:|---:|
| IDE 除錯 | 0.00% | 0.00% | 23.33% |
| 裝配流程 | 0.00% | 0.00% | 6.67% |
| 客服流程 | 1.67% | 0.00% | 30.00% |
| 簡報語音控制 | 0.00% | 0.00% | 27.50% |

## 錯誤定位

下表統計參考決策中必要答案的錯誤；分類錯誤本身仍使整個決策錯誤。同一時刻可能有多個錯誤問題，因此這裡的數量不能加總成錯誤時間。分支細節錯誤也可能伴隨分類錯誤，不能把各欄低分直接解釋成獨立能力缺陷。

| 情境 | 出錯的有效問題與狀態數 | 首批出錯 tick |
|---|---|---|
| lite_debugging_a | route: 54, target_result: 11, rerun_scope: 8, inspect_file: 4, owner: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 24, target_result: 10, process: 8, rerun_scope: 7, control_action: 4, owner: 4, inspect_file: 1 | 0, 7, 8, 11, 12, 18, 19, 20, 21, 22, 23, 26 |
| lite_assembly_a | route: 35, stage: 30, destination: 22, target: 11, next_step: 10, method: 8 | 0, 1, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13 |
| lite_assembly_b | route: 39, stage: 33, next_step: 11, destination: 11, target: 7, method: 6 | 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_support_a | recorder: 41, payment_stage: 16, service_target: 7, instrument: 5, hold_action: 4, service_action: 2, route: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | route: 24, repair_target: 17, repair_action: 8, delivery_action: 1 | 0, 1, 2, 3, 5, 6, 7, 8, 9, 18, 19, 20 |
| lite_presenter_a | mode: 20, captions: 18, slide: 15, host_cue: 9, clip_state: 6, question_card: 6 | 0, 1, 4, 5, 6, 7, 8, 14, 17, 18, 19, 20 |
| lite_presenter_b | mode: 31, slide: 23, captions: 14, question_card: 12, clip_state: 6, host_cue: 2 | 0, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17 |

## 解讀範圍

這是開發資料的一次模型實測。各情境的相鄰狀態不能當作獨立樣本；本次不提供跨模型辨別力、重複實驗穩定性或部署有效性的結論。證據釋出間距為公開的受控設定，未經人類節奏驗證。語言參考求解使用有限的已編寫表達形式，不代表能理解任意自然語言。

時間與不計延遲分數的差值是兩種評估的描述性差異，並非單獨改變模型速度的因果效果。新資料在問題數、組合方式、情境與時間規則上都與舊版（v0）資料不同，不能把新舊分差直接歸因於 fan-out。資料與 gold 在執行前已固定；本輪未依模型錯誤改題或重跑。

## 可重現檔案

- [任務與執行規格](../../../PROTOCOL.md)
- [IDE 除錯問題與規則](../../../debugging.md)、[裝配問題與規則](../../../assembly.md)、[客服問題與規則](../../../support.md)、[簡報語音控制問題與規則](../../../presenter.md)
- [原始完整執行](../../../../../runs/runpod-openweight-20260930/runs/djev-diffusiongemma/run.json)
- [凍結資料](../../../../../runs/runpod-openweight-20260930/runs/djev-diffusiongemma/episodes.json)
- [逐次釋出與回覆紀錄](../../../../../runs/runpod-openweight-20260930/runs/djev-diffusiongemma/events.jsonl)
- [完整分數與每次錯誤](../../../../../runs/runpod-openweight-20260930/runs/djev-diffusiongemma/metrics.json)
- [原始時鐘診斷分數](../../../../../runs/runpod-openweight-20260930/runs/djev-diffusiongemma/raw_wallclock_metrics.json)
- [報告用分析資料](analysis.json)

在專案根目錄，從完成的原始紀錄重算報告與本機基線：

```sh
uv run python paper/analysis/lite_reports.py --run runs/runpod-openweight-20260930/runs/djev-diffusiongemma --out docs/lite/results/runpod-openweight-20260930/djev-diffusiongemma --label 'DJev / DiffusionGemma'
```

Token usage（含 cached input，不另推估費用；僅加總回覆中取得的 usage，失敗請求未回傳的用量未知）：

```json
{
  "input_tokens": 1427008,
  "cached_tokens": 0,
  "output_tokens": 17820,
  "reasoning_tokens": 0
}
```
