"""Compare two verified SDB recordings with the same frozen data and protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from collections import Counter
from pathlib import Path

from lite_report import NAMES, ROOT, RETRY_PROTOCOL, analyze, command_path, model_label, relative_link


METRICS = (
    "untimed_decision_accuracy", "untimed_segment_accuracy", "time_accuracy",
    "segment_time_accuracy", "all_questions_exact_accuracy",
)
PAIR_KEYS = ("both_correct", "baseline_only_correct", "candidate_only_correct", "both_wrong")
# The compared model identity; every other config field must match.
MODEL_KEYS = ("provider", "model", "reasoning_effort")


def _score_comparison(baseline: dict, candidate: dict, latency_a: dict, latency_b: dict) -> dict:
    return {
        "baseline": {**{key: baseline[key] for key in METRICS}, "latency_s": latency_a},
        "candidate": {**{key: candidate[key] for key in METRICS}, "latency_s": latency_b},
        "candidate_minus_baseline": {
            **{f"{key}_pp": 100 * (candidate[key] - baseline[key]) for key in METRICS},
            **{f"latency_{key}_s": latency_b[key] - latency_a[key] for key in ("p50", "p95")},
        },
    }


def _paired_counts(a: dict, b: dict) -> dict[str, int]:
    if a["states"] != b["states"] or a["scenario_id"] != b["scenario_id"] or a["task_family"] != b["task_family"]:
        raise ValueError("paired episodes have different states, scenario, or family")
    n = a["states"]
    wrong_a = {m["t"] for m in a["mistakes"]}
    wrong_b = {m["t"] for m in b["mistakes"]}
    if not wrong_a <= set(range(n)) or not wrong_b <= set(range(n)):
        raise ValueError("mistake index is outside paired episode")
    return {
        "both_correct": n - len(wrong_a | wrong_b),
        "baseline_only_correct": len(wrong_b - wrong_a),
        "candidate_only_correct": len(wrong_a - wrong_b),
        "both_wrong": len(wrong_a & wrong_b),
    }


def _network_comparison(baseline: dict, candidate: dict) -> dict | None:
    """Both runs' network-removed estimates side by side; never rejects a comparison."""
    a, b = baseline.get("network_adjustment"), candidate.get("network_adjustment")
    if not a or not b:
        return None

    def scope(pick) -> dict:
        ranges = [[pick(net["scores"][k])["time_accuracy"] for k in ("estimate", "low", "high")] for net in (a, b)]
        (ea, la, ha), (eb, lb, hb) = ranges
        return {"baseline": {"estimate": ea, "low": la, "high": ha}, "candidate": {"estimate": eb, "low": lb, "high": hb},
                "candidate_minus_baseline_pp": 100 * (eb - ea), "ranges_overlap": la <= hb and lb <= ha}

    return {"method": a["method"],
            "network_s": {"baseline": a["network_s"], "candidate": b["network_s"]},
            "overall": scope(lambda block: block["overall"]),
            "by_family": {f: scope(lambda block, f=f: block["by_family"][f]) for f in a["scores"]["estimate"]["by_family"]}}


def compare(baseline: dict, candidate: dict) -> dict:
    """Compare outputs of analyze; never infer matching conditions from scores."""
    # Only conditions that change what a paired comparison means are required;
    # code versions are recorded per run, not matched.
    for key in ("time_basis", "episode_hashes"):
        if baseline[key] != candidate[key]:
            raise ValueError(f"runs differ in {key}; not a matched SDB comparison")
    protocol_a = {key: value for key, value in baseline["config"].items() if key not in MODEL_KEYS}
    protocol_b = {key: value for key, value in candidate["config"].items() if key not in MODEL_KEYS}
    if protocol_a != protocol_b:
        differences = sorted(key for key in protocol_a.keys() | protocol_b.keys() if protocol_a.get(key) != protocol_b.get(key))
        raise ValueError(f"run configurations differ beyond model: {', '.join(differences)}")
    rows_a = {row["episode_id"]: row for row in baseline["scores"]["per_episode"]}
    rows_b = {row["episode_id"]: row for row in candidate["scores"]["per_episode"]}
    if set(rows_a) != set(rows_b) or set(rows_a) != set(baseline["episode_order"]):
        raise ValueError("score episode sets do not match frozen data")
    pairs_by_family: dict[str, Counter] = {}
    pairs_overall: Counter = Counter()
    episodes = []
    for eid in baseline["episode_order"]:
        a, b = rows_a[eid], rows_b[eid]
        paired = _paired_counts(a, b)
        pairs_overall.update(paired)
        pairs_by_family.setdefault(a["task_family"], Counter()).update(paired)
        row = _score_comparison(
            a, b,
            {"p50": a["latency_s_p50"], "p95": a["latency_s_p95"]},
            {"p50": b["latency_s_p50"], "p95": b["latency_s_p95"]},
        )
        episodes.append({"episode_id": eid, "task_family": a["task_family"], "states": a["states"],
                         "paired_decision_counts": paired, **row})
    families = {}
    for family, a in baseline["scores"]["by_family"].items():
        b = candidate["scores"]["by_family"][family]
        families[family] = {
            "episodes": a["episodes"], "paired_decision_counts": dict(pairs_by_family[family]),
            **_score_comparison(a, b, baseline["latency_by_family_s"][family], candidate["latency_by_family_s"][family]),
        }

    def identity(data: dict) -> dict:
        identity = {key: data[key] for key in ("run", "config", "run_sources", "started_at_utc", "finished_at_utc", "models_returned",
                                             "events_sha256", "total_failed", "accepted_updates", "discarded_updates", "usage",
                                             "analysis_sources", "retry_reliability", "raw_wallclock_latency_s")}
        identity["raw_wallclock_overall"] = (data["raw_wallclock_scores"]["overall"] if data["raw_wallclock_scores"] is not None else None)
        return identity

    return {
        "baseline": identity(baseline), "candidate": identity(candidate),
        "time_basis": baseline["time_basis"],
        "same_recording": baseline["events_sha256"] == candidate["events_sha256"],
        "dataset_hash": baseline["dataset_hash"], "episode_hashes": baseline["episode_hashes"],
        "matched_config_excluding_model": protocol_a,
        "comparison_analysis_sources": {"scripts/lite/lite_compare.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "verification": "Both complete runs re-scored from their own events with the current scorer; identical time basis, frozen episodes, and config except model identity (provider, model, reasoning effort). Each run's recorded source versions are kept in its identity.",
        "overall": {
            "episodes": baseline["scores"]["episodes"], "states": baseline["scores"]["states"],
            "paired_decision_counts": dict(pairs_overall),
            **_score_comparison(baseline["scores"]["overall"], candidate["scores"]["overall"], baseline["latency_s"], candidate["latency_s"]),
        },
        "by_family": families, "per_episode": episodes,
        "network_adjustment": _network_comparison(baseline, candidate),
        "interpretation": "Descriptive single-recording comparison. Adjacent states are dependent. Score and latency differences do not establish statistical significance, stable rankings, or causal effects of speed or model changes.",
    }


def report(data: dict, output: Path) -> None:
    a, b = data["baseline"], data["candidate"]
    label_a, label_b = model_label(a["config"]), model_label(b["config"])
    normalized = a["config"]["protocol"] == RETRY_PROTOCOL
    pct = lambda value: f"{100 * value:.2f}%"

    def table_row(name: str, row: dict) -> str:
        first, second = row["baseline"], row["candidate"]
        return (f"| {name} | {pct(first['untimed_decision_accuracy'])} | {pct(second['untimed_decision_accuracy'])} "
                f"| {pct(first['time_accuracy'])} | {pct(second['time_accuracy'])} |")

    headings = [
        "| 範圍 | 基準：不計延遲 | 比較：不計延遲 | 基準：正確時間 | 比較：正確時間 |",
        "|---|---:|---:|---:|---:|",
    ]
    lines = [f"# SDB 對照：{label_a} 與 {label_b}", "",
             f"比較同一凍結資料的 {data['overall']['episodes']} 個情境、{data['overall']['states']} 個相同狀態。"
             "兩份紀錄均以目前的計分程式從各自的原始事件重算；逐情境資料與除模型身分（provider、模型、reasoning effort）外的執行設定相同。兩次執行的程式版本分別記錄於對照 JSON。", ""]
    lines += [
        ("主比較採排除連線重試的重建時間軸：成功 attempt 由證據釋出時刻起算，保留後處理耗時；"
         "失敗 attempts、重試等待與派送排隊不計入。原始時鐘另列診斷，不能與歷史原始時鐘主分數混比。"
         if normalized else "主比較採兩次執行各自的原始時鐘，未排除失敗請求或等待時間。"), "",
    ]
    if data["same_recording"]:
        lines += ["這是同一份紀錄的自我核對，用於驗證比較工具；不構成兩模型實驗。", ""]
    delta = data["overall"]["candidate_minus_baseline"]
    lines += [f"下表的「基準」為 **{label_a}**；「比較」為 **{label_b}**。", "",
              f"整體不計延遲正確率的差值為 **{delta['untimed_decision_accuracy_pp']:+.2f} 個百分點**，"
              f"正確持續時間比例的差值為 **{delta['time_accuracy_pp']:+.2f} 個百分點**，皆以比較模型減基準模型計算。"
              "家族與整體分數按情境等權重。完整差值保留於對照 JSON。", "",
              "## 整體與家族", "", *headings, table_row("整體", data["overall"])]
    for family, row in data["by_family"].items():
        lines.append(table_row(NAMES.get(family, family), row))
    if (net := data.get("network_adjustment")):
        pct = lambda value: f"{100 * value:.2f}%"
        span = lambda r: f"{pct(r['estimate'])}（{pct(r['low'])}–{pct(r['high'])}）"
        na, nb = net["network_s"]["baseline"], net["network_s"]["candidate"]
        lines += ["", "## 移除網路延遲後的估計（次要）", "",
                  "各自以本次紀錄估計網路延遲（不隨 token 變化的時間，取快速請求的下緣），再從每個回覆扣除後重播；"
                  f"估計網路：基準 {na['estimate']:.3f} 秒（{na['low']:.3f}–{na['high']:.3f}），"
                  f"比較 {nb['estimate']:.3f} 秒（{nb['low']:.3f}–{nb['high']:.3f}）。"
                  "括號為 bootstrap 範圍；主分數與上表不變。", "",
                  "| 範圍 | 基準：移除網路 | 比較：移除網路 | 差值（估計） | 範圍重疊 |", "|---|---:|---:|---:|---|"]
        for name, row in [("整體", net["overall"]), *[(NAMES.get(f, f), r) for f, r in net["by_family"].items()]]:
            lines.append(f"| {name} | {span(row['baseline'])} | {span(row['candidate'])} | "
                         f"{row['candidate_minus_baseline_pp']:+.2f} 個百分點 | {'是' if row['ranges_overlap'] else '否'} |")
    lines += ["", "## 相同情境", "", *headings]
    for row in data["per_episode"]:
        lines.append(table_row(row["episode_id"], row))
    lines += ["", "## 回應延遲", "",
              ("各範圍只使用最終成功 attempt 的耗時，不包含失敗與重試等待。" if normalized else "各範圍使用完整請求耗時。")
              + "分位數直接由該範圍全部請求計算，不是各情境分位數的平均。單位為秒；含該次本機 client 與正常網路時間。", "",
              "| 範圍 | 基準 p50 / p95 | 比較 p50 / p95 |", "|---|---:|---:|"]
    for name, row in [("整體", data["overall"]), *[(NAMES.get(f, f), r) for f, r in data["by_family"].items()]]:
        first, second = row["baseline"]["latency_s"], row["candidate"]["latency_s"]
        lines.append(f"| {name} | {first['p50']:.2f} / {first['p95']:.2f} | {second['p50']:.2f} / {second['p95']:.2f} |")
    lines += ["", "## 同一狀態的有效決策配對", "",
              "以下比較忽略交付時間的有效決策，保留模型自己選擇的分支；未使用的答案不影響此判定。"
              "四欄互斥且涵蓋全部狀態，僅描述這次紀錄的配對數量，不將相鄰狀態視為獨立樣本。", "",
              "| 範圍 | 兩者皆對 | 只有基準對 | 只有比較對 | 兩者皆錯 |", "|---|---:|---:|---:|---:|"]
    for name, row in [("整體", data["overall"]), *[(NAMES.get(f, f), r) for f, r in data["by_family"].items()]]:
        values = row["paired_decision_counts"]
        lines.append(f"| {name} | " + " | ".join(str(values[key]) for key in PAIR_KEYS) + " |")
    config = data["matched_config_excluding_model"]
    if normalized:
        lines += ["", "## 連線可靠性與原始時鐘", "",
                  "Attempt 錯誤率的分母是所有實際 attempts（包含最終成功）；logical 重試率的分母是所有釋出狀態。"
                  "原始時鐘診斷保留失敗、等待與實際交付順序，和主比較使用不同時間基準。", "",
                  "| 指標 | 基準 | 比較 |", "|---|---:|---:|"]
        rel_a, rel_b = a["retry_reliability"], b["retry_reliability"]
        for name, key, numerator, denominator in [
            ("Attempt 錯誤率", "attempt_error_rate", "failed_attempts", "attempts"),
            ("Logical 重試率", "retried_logical_rate", "retried_logical_requests", "logical_requests"),
        ]:
            lines.append(f"| {name} | {rel_a[key]:.2%}（{rel_a[numerator]}/{rel_a[denominator]}） | {rel_b[key]:.2%}（{rel_b[numerator]}/{rel_b[denominator]}） |")
        lines.append(f"| 原始正確時間 | {a['raw_wallclock_overall']['time_accuracy']:.2%} | {b['raw_wallclock_overall']['time_accuracy']:.2%} |")
        la, lb = a["raw_wallclock_latency_s"], b["raw_wallclock_latency_s"]
        lines.append(f"| 原始 request p50 / p95（秒） | {la['p50']:.2f} / {la['p95']:.2f} | {lb['p50']:.2f} / {lb['p95']:.2f} |")
    lines += ["", "## 執行紀錄與解讀", "",
              f"- 協議：{config['protocol']}；"
              f"workers：{config['workers']}；timeout：{config['request_timeout_s']:g} 秒；SDK retries：{config['sdk_retries']}。",
              f"- {label_a}：失敗請求 {a['total_failed']}，接受更新 {a['accepted_updates']}。",
              f"- {label_b}：失敗請求 {b['total_failed']}，接受更新 {b['accepted_updates']}。",
              f"- API 回傳模型：{json.dumps(a['models_returned'], ensure_ascii=False)}；{json.dumps(b['models_returned'], ensure_ascii=False)}。", "",
              "每個模型在每個情境只有一次紀錄。這些差異不代表統計顯著性、跨情境族群的穩定排序，或模型速度的因果效果。"
              "兩次執行發生於不同時間，服務端與網路條件可能不同。時間分數同時取決於答案、交付延遲、更新接受規則和參考狀態持續時間。"
              "不計延遲分數使用同一批回覆，沒有另外查詢模型，也沒有依此比較修改題目。", "",
              "## 可重現檔案", "",
              *(["- [逐項錯誤案例與解讀](FINDINGS.md)"] if (output / "FINDINGS.md").exists() else []),
              *(["- [比較模型的完整單輪報告](REPORT.md)"] if (output / "REPORT.md").exists() else []),
              f"- [{label_a} 原始執行]({relative_link(ROOT / a['run'] / 'run.json', output)})",
              f"- [{label_b} 原始執行]({relative_link(ROOT / b['run'] / 'run.json', output)})",
              "- [完整對照資料](comparison.json)", "",
              "在專案根目錄重算：", "", "```sh",
              shlex.join(["uv", "run", "python", "scripts/lite/lite_compare.py", "--baseline", command_path(ROOT / a["run"]),
                          "--candidate", command_path(ROOT / b["run"]), "--out", command_path(output)]),
              "```", ""]
    output.mkdir(parents=True, exist_ok=True)
    (output / "COMPARISON.md").write_text("\n".join(lines))
    (output / "comparison.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report(compare(analyze(args.baseline), analyze(args.candidate)), args.out)
