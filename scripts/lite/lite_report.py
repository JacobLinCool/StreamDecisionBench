"""Reproduce a frozen SDB run report and local baseline diagnostics; no API calls."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np

from streamdecisionbench.adapters.local import FirstOptionAdapter, LexicalAdapter
from streamdecisionbench.jev import committed_answer
from streamdecisionbench.lite.core import compose, decode, digest, request_for, sources
from streamdecisionbench.lite.__main__ import PHYSICAL_PROTOCOL, RETRY_PROTOCOL, rescore_run
from network import network_adjustment


NAMES = {"live_debugging": "IDE 除錯", "procedural_coaching": "裝配流程", "support_call_assist": "客服流程",
         "presenter_voice_control": "簡報語音控制"}
ROOT = Path(__file__).resolve().parents[2]


def model_label(config: dict) -> str:
    return " ".join(part for part in (config["model"], config["reasoning_effort"]) if part)


def relative_link(target: Path, output: Path) -> str:
    return Path(os.path.relpath(target.resolve(), output.resolve())).as_posix()


def command_path(path: Path) -> str:
    """Repository-relative path (relative even outside the repository), so reports name no machine path."""
    return Path(os.path.relpath(path.resolve(), ROOT)).as_posix()


def _combined_from(run: Path, parts: list[dict] | None) -> list[dict] | None:
    """Merge parts with repository-relative paths; run.json stores them relative to the merged run folder."""
    if parts is None:
        return None
    return [{**part, "run": command_path(run / part["run"])} for part in parts]


def _latencies(records: list[dict], *, successful_attempt: bool = False) -> dict:
    timed = [r["attempts"][-1] for r in records] if successful_attempt else records
    values = [r["completed_s"] - r["started_s"] for r in timed]
    return {"p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95)), "max": max(values)}


def _retry_report_lines(data: dict) -> list[str]:
    reliability = data["retry_reliability"]
    raw, latency = data["raw_wallclock_scores"], data["raw_wallclock_latency_s"]
    return [
        "## 連線可靠性與原始時鐘診斷", "",
        f"- 連線 attempt 錯誤率：{reliability['attempt_error_rate']:.2%} "
        f"（{reliability['failed_attempts']} 個失敗 attempts／全部 {reliability['attempts']} 個 attempts，包含最終成功）。",
        f"- Logical request 重試率：{reliability['retried_logical_rate']:.2%} "
        f"（{reliability['retried_logical_requests']} 個曾重試 requests／全部 {reliability['logical_requests']} 個 logical requests）。",
        f"- 失敗 attempt 類別：{json.dumps(reliability['attempt_errors_by_type'], ensure_ascii=False)}。",
        f"- 失敗 attempts 累計耗時 {reliability['failed_attempt_duration_s']:.3f} 秒；"
        f"排除的失敗與重試等待累計 {reliability['excluded_retry_s']:.3f} 秒，"
        f"另外排除派送排隊累計 {reliability['excluded_dispatch_s']:.3f} 秒。各請求可重疊，累計秒數不是整段牆鐘時長。",
        f"- 設定最多 {data['config']['max_attempts']} 次 attempts；首次立即重試，後續以 {data['config']['retry_delay_s']:g} 秒為基礎退避，上限 8 秒；SDK 自動重試關閉。",
        "", "原始時鐘保留所有實際失敗、等待與晚到交付，只作診斷，不與主分數混合：", "",
        "| 範圍 | 原始正確時間 | 原始區段等權重時間 |", "|---|---:|---:|",
        f"| 整體 | {raw['overall']['time_accuracy']:.2%} | {raw['overall']['segment_time_accuracy']:.2%} |",
        *[f"| {NAMES.get(family, family)} | {row['time_accuracy']:.2%} | {row['segment_time_accuracy']:.2%} |"
          for family, row in raw["by_family"].items()],
        "", f"原始 logical request 耗時（含失敗 attempts 與重試等待）p50 {latency['p50']:.3f} 秒、"
        f"p95 {latency['p95']:.3f} 秒；原始接受更新 {sum(row['accepted_updates'] for row in raw['per_episode'])} 次。",
        "", "重試耗盡或非連線錯誤會使整次執行標為 incomplete，不發布完整主分數。"
        "成功與否依 API／回應有效性判定，不依答案是否符合 gold 選擇重試。", "",
    ]


def _network_report_lines(net: dict) -> list[str]:
    pct = lambda x: f"{100*x:.2f}%"
    n, s = net["network_s"], net["scores"]
    decode = (f"decode {1000 * net['decode_s_per_output_token']:.2f} ms／token"
              if net["decode_s_per_output_token"] is not None else "不含 decode 項（模型不生成文字）")
    lines = ["## 移除網路延遲後的估計（次要）", "",
             "假設送出到收到回覆的時間 = 網路 + prefill（正比於未快取輸入 token）+ decode（正比於輸出 token，僅限生成文字的模型），"
             "不隨 token 變化的部分全部視為網路。排隊只會增加時間，因此以快速請求的下緣估計網路："
             "第 10 百分位迴歸的截距，token 斜率不為負；範圍來自情境內連續 10 次釋出為一塊的 bootstrap（500 次）。", "",
             f"估計網路 {n['estimate']:.3f} 秒（範圍 {n['low']:.3f}–{n['high']:.3f} 秒）；"
             f"prefill {1000 * net['prefill_s_per_1k_input_tokens']:.1f} ms／1k token；{decode}；"
             f"最快回應 {net['latency_floor_s']:.3f} 秒；扣到零的請求 {s['estimate']['clamped_requests']} 個。", "",
             "| 範圍 | 主分數 | 移除網路（估計） | 範圍 | 上限（不計延遲） |", "|---|---:|---:|---:|---:|"]
    scopes = [("整體", lambda block: block["overall"])]
    scopes += [(NAMES.get(f, f), lambda block, f=f: block["by_family"][f]) for f in s["estimate"]["by_family"]]
    for name, pick in scopes:
        lines.append(f"| {name} | {pct(pick(net['observed']))} | {pct(pick(s['estimate'])['time_accuracy'])} | "
                     f"{pct(pick(s['low'])['time_accuracy'])}–{pct(pick(s['high'])['time_accuracy'])} | "
                     f"{pct(pick(net['untimed_ceiling']))} |")
    if net["negative_intercept_projected"]:
        raw = net["unconstrained_intercept_s"]
        lines += ["", f"未限制截距為 {raw['estimate']:.6f} 秒（範圍 {raw['low']:.6f}–{raw['high']:.6f} 秒）。"
                  "截距是對零 token 的外推，可能為負值；負值不能當作可移除延遲，因此重放時投影為零。"
                  "原始估計保留在 analysis.json，主要分數與錄製資料不變。"]
    lines += ["", "這是次要估計，主分數不變。不隨 token 變化的時間也可能包含固定的伺服器時間，因此它是網路影響的上界；"
              "範圍只反映估計的不確定性，不含模型重跑的變異。", ""]
    return lines


def analyze(run: Path) -> dict:
    verified = rescore_run(run)
    frozen, episodes = verified["frozen"], verified["episodes"]
    episode_hashes = {e["episode_id"]: digest(e) for e in episodes}
    responses = verified["responses"]
    recomputed = verified["scores"]
    per = recomputed["per_episode"]
    normalized = frozen["config"]["protocol"] == RETRY_PROTOCOL
    baselines = {}
    for name, adapter_type in (("first_option", FirstOptionAdapter), ("lexical_overlap", LexicalAdapter)):
        rows = []
        for e in episodes:
            adapter = adapter_type()
            adapter.start_episode(e["episode_id"])
            correct = []
            for s in e["steps"]:
                request = request_for(e, s)
                answer = adapter.system_one(request)["answers"]
                wire = {k: committed_answer(q, answer[k]) for k, q in e["questions"].items()}
                pred = decode(e, wire)
                correct.append(compose(e["decision_spec"], pred) == compose(e["decision_spec"], s["gold"]))
            adapter.close()
            rows.append({"episode_id": e["episode_id"], "family": e["task_family"], "accuracy": mean(correct)})
        baselines[name] = {"overall": mean(r["accuracy"] for r in rows), "per_episode": rows,
                           "by_family": {f: mean(r["accuracy"] for r in rows if r["family"] == f) for f in recomputed["by_family"]}}
    records = [r for rows in responses.values() for r in rows]
    family_for = {e["episode_id"]: e["task_family"] for e in episodes}
    usage = {k: sum((r.get("usage") or {}).get(k, 0) for r in records)
             for k in ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")}
    data = {"run": command_path(run), "config": frozen["config"], "dataset_hash": frozen["dataset_manifest"]["dataset_hash"],
            "time_basis": recomputed["time_basis"] if normalized else PHYSICAL_PROTOCOL,
            "episode_hashes": episode_hashes, "run_sources": frozen["run_sources"], "events_sha256": frozen["events_sha256"],
            "analysis_sources": {**sources(), "scripts/lite/lite_report.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "episode_order": [e["episode_id"] for e in episodes],
            "episode_specs": [{"episode_id": e["episode_id"], "title": e["title"], "tick_seconds": e["tick_seconds"],
                               "duration_s": len(e["steps"]) * e["tick_seconds"]} for e in episodes],
            "started_at_utc": frozen["started_at_utc"], "finished_at_utc": frozen["finished_at_utc"],
            "combined_from": _combined_from(run, frozen.get("combined_from")),
            "scores": recomputed, "baselines": baselines, "usage": usage,
            "raw_wallclock_scores": verified["raw_wallclock_scores"],
            "raw_wallclock_latency_s": _latencies(records) if normalized else None,
            "retry_reliability": recomputed["retry_reliability"] if normalized else None,
            "network_adjustment": (network_adjustment(episodes, responses, verified["releases"],
                                                      generates_text=frozen["config"].get("provider", "openai") == "openai")
                                   if normalized else None),
            "models_returned": dict(Counter(r.get("model") for r in records if r["ok"])),
            "latency_s": _latencies(records, successful_attempt=normalized),
            "latency_by_family_s": {f: _latencies([r for r in records if family_for[r["episode_id"]] == f], successful_attempt=normalized)
                                    for f in recomputed["by_family"]},
            "environment": {"python": platform.python_version(), "system": platform.system(),
                            "openai_sdk": importlib.metadata.version("openai")},
            "total_failed": sum(not r["ok"] for r in records),
            "accepted_updates": sum(r["accepted_updates"] for r in per),
            "discarded_updates": dict(sum((Counter(r["discarded_updates"]) for r in per), Counter())),
            "error_seconds": {k: sum(r["error_seconds"][k] for r in per)
                              for k in ("no_decision", "source_correct", "source_incorrect")},
            "max_release_lag_s": max(r["max_release_lag_s"] for r in per),
            "max_dispatch_lag_s": max(r["max_dispatch_lag_s"] for r in per)}
    return data



def report(data: dict, output: Path) -> None:
    scores, rows = data["scores"], data["scores"]["per_episode"]
    config, label = data["config"], model_label(data["config"])
    normalized = config["protocol"] == RETRY_PROTOCOL
    timing_label = "正確持續時間比例（排除連線重試）" if normalized else "正確持續時間比例（原始時鐘）"
    request_description = ("每個狀態取得一份最終成功回覆；連線失敗依設定重試。" if normalized else "每個狀態僅查詢一次。")
    durations = sorted({e["duration_s"] for e in data["episode_specs"]})
    ticks = sorted({e["tick_seconds"] for e in data["episode_specs"]})
    duration_text = "／".join(f"{duration:g}" for duration in durations)
    tick_text = "／".join(f"{tick:g}" for tick in ticks)
    command = shlex.join(["uv", "run", "python", "scripts/lite/lite_report.py", "--run", command_path(ROOT / data["run"]),
                          "--out", command_path(output)])
    task_docs = ROOT / "docs" / "lite"
    pct = lambda x: f"{100*x:.2f}%"
    heading = "SDB 錄製間距診斷"
    lines = [f"# {heading}：{label}", "",
             f"{len(scores['by_family'])} 類、{scores['episodes']} 個獨立情境；各段長度 {duration_text} 秒，"
             f"證據釋出間距 {tick_text} 秒，共 {scores['states']} 個 logical requests；{request_description}"
             f"模型設定為 {config['model']}" + (f"、{config['reasoning_effort']} reasoning" if config["reasoning_effort"] else "")
             + "；本報告所有模型分數皆來自實際回覆，沒有 placeholder。", "",
             f"**有效決策正確率（不計延遲）：{pct(scores['overall']['untimed_decision_accuracy'])}；"
             f"{timing_label}：{pct(scores['overall']['time_accuracy'])}。**", "",
             *([f"移除網路延遲後的正確持續時間（次要估計）：{pct(net['scores']['estimate']['overall']['time_accuracy'])}"
                f"（範圍 {pct(net['scores']['low']['overall']['time_accuracy'])}–{pct(net['scores']['high']['overall']['time_accuracy'])}）。", ""]
               if (net := data.get("network_adjustment")) else []),
             *(["[錯誤案例與下一步建議](FINDINGS.md)逐項對照公開規則，說明值得補測的判斷需求。", ""]
               if (output / "FINDINGS.md").exists() else []),
             "## 各家族結果", "",
             "| 家族 | 不計延遲：有效決策 | 正確持續時間 | 區段等權重時間分數 | 全部問題全對（診斷） |",
             "|---|---:|---:|---:|---:|"]
    for family, r in scores["by_family"].items():
        lines.append(f"| {NAMES.get(family, family)} | {pct(r['untimed_decision_accuracy'])} | {pct(r['time_accuracy'])} | {pct(r['segment_time_accuracy'])} | {pct(r['all_questions_exact_accuracy'])} |")
    timing_description = ("主分數在重建時間軸上計算：每個成功 attempt 的耗時從該狀態的證據釋出時刻起算，並保留實際後處理至接受檢查的耗時，"
                          "排除失敗 attempt、重試等待與派送排隊；依重建抵達順序重新判定生效更新。"
                          "它不是實際部署時鐘的正確時間，原始時鐘結果另外列出。" if normalized else
                          "時間分數精確積分實際釋出與接受更新的時刻。")
    lines += ["", "有效決策由模型自己的分類、全域必要答案與該分支必要答案組成；未使用的分支不扣主分數。"
              + timing_description + "家族與整體分數皆按情境等權重。", "",
              *(_network_report_lines(data["network_adjustment"]) if data.get("network_adjustment") else []),
              "## 各獨立情境", "",
              "| 情境 | 有效切換數 | 不計延遲 | 正確時間 | 回應 p50 / p95（秒） | 失敗請求 |",
              "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['episode_id']} | {r['reference_transitions']} | {pct(r['untimed_decision_accuracy'])} | {pct(r['time_accuracy'])} | {r['latency_s_p50']:.2f} / {r['latency_s_p95']:.2f} | {r['failed_requests']} |")
    lines += ["", "## 執行與計分核對", "",
              f"- 完成 {scores['states']} 個狀態、{scores['episodes']} 個情境；失敗請求 {data['total_failed']}。",
              f"- {'成功 attempt' if normalized else '全部回應'}延遲 p50 {data['latency_s']['p50']:.3f} 秒、p95 {data['latency_s']['p95']:.3f} 秒；"
              + ("包含同機原生函式呼叫、排隊與推論。" if config.get('transport') == 'native_library' else "包含該次本機 client 與正常網路時間。"),
              f"- 原始錄製的最大釋出落後 {data['max_release_lag_s']:.4f} 秒；最大派送落後 {data['max_dispatch_lag_s']:.4f} 秒。",
              f"- 有 {scores['inactive_only_error_states']} 個狀態只有未使用問題答錯，因此有效決策仍正確。",
              f"- {'重建時間軸' if normalized else '原始時鐘'}接受更新 {data['accepted_updates']} 次；未採用回覆：{json.dumps(data['discarded_updates'], ensure_ascii=False)}。",
              "- 使用 pipeline：每次釋出都送出一次請求；完整的新來源回覆原子生效，較舊來源晚到不得覆寫。情境間序列執行。",
              "- 不計延遲分數使用同一批回覆，並非另外跑一次模型。"
              + (f"使用同機原生函式，無網路 timeout；單一設定的程序逾時為 {config['setting_process_timeout_s']:g} 秒。"
                 if config.get('transport') == 'native_library'
                 else f"SDK retries 為 {config['sdk_retries']}，網路 timeout 為 {config['request_timeout_s']:g} 秒。"),
              f"- 執行設定：{config['protocol']}，最多 {config['workers']} 個 request workers，情境並行數 {config['episode_concurrency']}。",
              "- 分數由本次分析以目前的計分程式從原始事件重算；原執行與本次分析的 source manifest 分別保存，僅供追溯。", "",
              "錯誤持續時間另依當時使用的答案來源分類：尚無答案 "
              f"{data['error_seconds']['no_decision']:.2f} 秒；答案對原始證據正確、但對當前證據已不正確 "
              f"{data['error_seconds']['source_correct']:.2f} 秒；答案對原始證據即不正確，且對當前證據也不正確 "
              f"{data['error_seconds']['source_incorrect']:.2f} 秒。這是各情境的時間總和；來源分類不等同因果歸因。", "",
              *(_retry_report_lines(data) if normalized else []),
              "## 簡單基線", "", "下列為離線執行的本機基線，只比較答案正確性；未測量持續時間分數。", "",
              f"| 家族 | 固定第一選項 | 詞彙重疊 | {label} 有效決策 |", "|---|---:|---:|---:|"]
    for f in scores["by_family"]:
        lines.append(f"| {NAMES.get(f, f)} | {pct(data['baselines']['first_option']['by_family'][f])} | {pct(data['baselines']['lexical_overlap']['by_family'][f])} | {pct(scores['by_family'][f]['untimed_decision_accuracy'])} |")
    lines += ["", "## 錯誤定位", "",
              "下表統計參考決策中必要答案的錯誤；分類錯誤本身仍使整個決策錯誤。"
              "同一時刻可能有多個錯誤問題，因此這裡的數量不能加總成錯誤時間。"
              "分支細節錯誤也可能伴隨分類錯誤，不能把各欄低分直接解釋成獨立能力缺陷。", "",
              "| 情境 | 出錯的有效問題與狀態數 | 首批出錯 tick |", "|---|---|---|"]
    for r in rows:
        counts = Counter(q for m in r["mistakes"] for q in m["wrong_active_questions"])
        kinds = ", ".join(f"{q}: {n}" for q, n in counts.most_common()) or "無"
        ticks = ", ".join(str(m["t"]) for m in r["mistakes"][:12]) or "無"
        lines.append(f"| {r['episode_id']} | {kinds} | {ticks} |")
    lines += ["", "## 解讀範圍", "",
              "這是開發資料的一次模型實測。各情境的相鄰狀態不能當作獨立樣本；"
              "本次不提供跨模型辨別力、重複實驗穩定性或部署有效性的結論。證據釋出間距為公開的受控設定，未經人類節奏驗證。"
              "語言參考求解使用有限的已編寫表達形式，不代表能理解任意自然語言。", "",
              "時間與不計延遲分數的差值是兩種評估的描述性差異，並非單獨改變模型速度的因果效果。"
              "新資料在問題數、組合方式、情境與時間規則上都與舊版（v0）資料不同，不能把新舊分差直接歸因於 fan-out。"
              "資料與 gold 在執行前已固定；本輪未依模型錯誤改題或重跑。", "",
              "## 可重現檔案", "",
              f"- [任務與執行規格]({relative_link(task_docs / 'PROTOCOL.md', output)})",
              f"- [IDE 除錯問題與規則]({relative_link(task_docs / 'debugging.md', output)})、"
              f"[裝配問題與規則]({relative_link(task_docs / 'assembly.md', output)})、"
              f"[客服問題與規則]({relative_link(task_docs / 'support.md', output)})"
              + (f"、[簡報語音控制問題與規則]({relative_link(task_docs / 'presenter.md', output)})"
                 if "presenter_voice_control" in scores["by_family"] else ""),
              f"- [原始完整執行]({relative_link(ROOT / data['run'] / 'run.json', output)})",
              f"- [凍結資料]({relative_link(ROOT / data['run'] / 'episodes.json', output)})",
              f"- [逐次釋出與回覆紀錄]({relative_link(ROOT / data['run'] / 'events.jsonl', output)})",
              f"- [完整分數與每次錯誤]({relative_link(ROOT / data['run'] / 'metrics.json', output)})",
              *([f"- [原始時鐘診斷分數]({relative_link(ROOT / data['run'] / 'raw_wallclock_metrics.json', output)})"]
                if normalized else []),
              "- [報告用分析資料](analysis.json)", "",
              "在專案根目錄，從完成的原始紀錄重算報告與本機基線：", "", "```sh", command,
              "```", "",
              "Token usage（含 cached input，不另推估費用；僅加總回覆中取得的 usage，失敗請求未回傳的用量未知）：", "", "```json",
              json.dumps(data["usage"], indent=2), "```", ""]
    output.mkdir(parents=True, exist_ok=True)
    (output / "REPORT.md").write_text("\n".join(lines))
    (output / "analysis.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report(analyze(args.run), args.out)
