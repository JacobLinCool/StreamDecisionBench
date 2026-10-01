"""Paper's integrated metrics and sensitivity conditions, all from frozen replay."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from streamdecisionbench.lite.interval_scoring import integrate_intervals

POLICY_PATH = ROOT / "paper/analysis/evaluation_policy.json"


def compute_auc(run):
    policy = json.loads(POLICY_PATH.read_text())
    options = policy["integration"]
    primary = integrate_intervals(run, **policy["primary"], **options)
    sensitivity = {
        item["name"]: integrate_intervals(
            run, **{k: v for k, v in item.items() if k != "name"}, **options
        )
        for item in policy["sensitivity"]
    }
    sources = [
        "paper/analysis/evaluation_policy.json",
        "paper/analysis/lite_auc.py",
        "src/streamdecisionbench/lite/interval_scoring.py",
        "src/streamdecisionbench/lite/retry_scoring.py",
        "src/streamdecisionbench/lite/scoring.py",
        "src/streamdecisionbench/lite/core.py",
    ]
    return {
        "primary": primary,
        "sensitivity": sensitivity,
        "sources_sha256": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources
        },
        "events_sha256": run["frozen"]["events_sha256"],
    }


def auc_macros(m, models):
    from lite_numbers import FAMILIES, SCENARIOS, pct, points, _dec, fixed

    changes = []
    product_deviations = []
    product_gaps = []
    lucky = []
    ucur_gaps = []
    for p, model in models.items():
        auc = model["analysis"].data["auc"]
        primary = auc["primary"]
        overall = primary["overall"]
        # Exact path is retained by Source; all emitted primary quantities refer to this artifact.
        src = model["analysis"].ref("auc", "primary")
        scopes = [("", overall)] + [(fp, primary["by_family"][f]) for fp, f in FAMILIES]
        by_id = {row["episode_id"]: row for row in primary["per_episode"]}
        scopes += [(sp, by_id[eid]) for sp, _, eid in SCENARIOS]
        for suffix, row in scopes:
            m.add(f"{p}{suffix}Auc", pct(row["accuracy"]), src)
        m.add(
            f"{p}AucGap",
            points(_dec(overall["untimed"] - overall["accuracy"]) * 100),
            src,
        )
        m.add(f"{p}AucOracle", pct(overall["oracle"]), src)
        m.add(f"{p}AucProduct", pct(overall["product"]), src)
        ucur = (
            overall["current_correct"] / overall["oracle"] if overall["oracle"] else 0
        )
        m.add(f"{p}AucUCurrent", pct(ucur), src)
        for suffix, key in [
            ("Stale", "stale"),
            ("Judgment", "judgment"),
            ("Compound", "compound"),
            ("None", "no_decision"),
            ("Lucky", "outdated_correct"),
        ]:
            m.add(f"{p}Auc{suffix}", pct(overall[key]), src)
        product_deviations += [
            abs(row["accuracy"] - row["product"]) for row in primary["per_episode"]
        ]
        product_gaps.append(overall["accuracy"] - overall["product"])
        lucky.append(overall["outdated_correct"])
        ucur_gaps.append(abs(ucur - overall["untimed"]))
        for name, result in auc["sensitivity"].items():
            m.add(
                f"{p}Auc{name}",
                pct(result["overall"]["accuracy"]),
                model["analysis"].ref("auc", "sensitivity", name),
            )
        changes += [
            r["quadrature"]["max_successive_change"]
            for r in [primary, *auc["sensitivity"].values()]
        ]
    low_stale = [models[p]["analysis"].data["auc"]["primary"]["overall"]["stale"] for p in ("Luna", "Terra", "Astra")]
    m.add("LowEffortStaleRoundedMin", fixed(100 * min(low_stale), 0), "minimum primary stale share of low-effort GPT settings, rounded to whole percent")
    m.add("LowEffortStaleRoundedMax", fixed(100 * max(low_stale), 0), "maximum primary stale share of low-effort GPT settings, rounded to whole percent")
    m.add("JevJudgmentRounded", fixed(100 * models["Jev"]["analysis"].data["auc"]["primary"]["overall"]["judgment"], 0), "Jev primary judgment share, rounded to whole percent")
    m.add(
        "AucMaxRefinementChange",
        fixed(100 * max(changes), 4),
        "max successive quadrature-grid change, all integrated scenario metrics and sensitivity conditions (points)",
    )
    m.add(
        "AucProductMaxDeviation",
        points(_dec(max(product_deviations)) * 100),
        "max per-scenario absolute difference: log-AUC minus U times oracle log-AUC (points)",
    )
    m.add(
        "AucProductGapMin",
        points(_dec(min(product_gaps)) * 100),
        "min macro log-AUC minus mean per-scenario U times oracle log-AUC (points)",
    )
    m.add(
        "AucProductGapMax",
        points(_dec(max(product_gaps)) * 100),
        "max of the same (points)",
    )
    m.add("AucLuckyMax", pct(max(lucky)), "max integrated lucky share over settings")
    m.add(
        "AucUCurrentMaxDiff",
        points(_dec(max(ucur_gaps)) * 100),
        "max integrated current-correct/current-source share minus untimed accuracy, absolute (points)",
    )
    from lite_numbers import shown  # differences of the printed values, as for every other stated gap

    for first, second in [("Jev", "TerraNone"), ("Jev", "Luna"), ("Jev", "Terra"), ("Jev", "Astra")]:
        acc = lambda p: models[p]["analysis"].data["auc"]["primary"]["overall"]["accuracy"]
        delta = shown(acc(first)) - shown(acc(second))
        if delta < 0:
            raise ValueError(f"{first}Minus{second}Auc would be negative")
        m.add(
            f"{first}Minus{second}Auc",
            points(delta),
            f"\\{first}Auc minus \\{second}Auc (points, from the printed values)",
        )


def auc_tables(models):
    from lite_numbers import FAMILIES

    row = lambda cells: " & ".join(cells) + r" \\"
    main = [
        row(
            [
                f"\\{p}RowLabel",
                *[f"\\{p}{fp}Auc" for fp, _ in FAMILIES],
                f"\\{p}Auc",
                f"\\{p}Untimed",
            ]
        )
        for p in models
    ]
    sensitivity = [
        row(
            [
                f"\\{p}RowLabel",
                f"\\{p}Auc",
                f"\\{p}AucLinear",
                f"\\{p}AucNarrow",
                f"\\{p}AucHalfFour",
                f"\\{p}AucOneEight",
                f"\\{p}AucTenthFour",
                f"\\{p}AucTenthEight",
                f"\\{p}CommonTwo",
            ]
        )
        for p in models
    ]
    decomp = [
        row(
            [
                f"\\{p}RowLabel",
                f"\\{p}AucOracle",
                f"\\{p}AucUCurrent",
                f"\\{p}AucLucky",
                f"\\{p}AucProduct",
                f"\\{p}Auc",
            ]
        )
        for p in models
    ]
    return [
        (
            "TabAucBody",
            "Normalized log-AUC 0.5--8 s per family, macro mean, and untimed accuracy (%).",
            main,
        ),
        (
            "TabAucSensitivityBody",
            "Primary log-AUC 0.5--8, linear 0.5--8, log 1--4, 0.5--4, 1--8, 0.1--4, 0.1--8, and in-force accuracy at 2 s (%).",
            sensitivity,
        ),
        (
            "TabAucDecompositionBody",
            "Integrated timing, current-source judgment, lucky share, U times timing, and log-AUC (%).",
            decomp,
        ),
    ]
