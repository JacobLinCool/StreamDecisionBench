"""Assemble the static results site from the verified README figure data; no model calls.

Usage: python3 site/build.py --out _site
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "docs/figures/data.json"


def log_auc(xs, ys):
    """Normalized trapezoidal area on a logarithmic interval axis."""
    lx = [math.log(x) for x in xs]
    area = sum((b - a) * (ya + yb) / 2 for a, b, ya, yb in zip(lx, lx[1:], ys, ys[1:]))
    return area / (lx[-1] - lx[0])


def build(out: Path) -> dict:
    figures = json.loads(FIGURES.read_text())
    keep = [0] + [i for i in range(1, len(figures["intervals_s"]))
                  if figures["intervals_s"][i] - figures["intervals_s"][i - 1] > 1e-9]
    intervals = [figures["intervals_s"][i] for i in keep]
    settings, deviation = [], 0.0
    for series in figures["series"]:
        curve = [series["accuracy_pct"][i] for i in keep]
        deviation = max(deviation, abs(log_auc(intervals, curve) - series["log_auc_pct"]))
        latency = series["latency_s"]
        settings.append({
            "passes": series["passes"], "id": series["id"], "label": series["label"], "deployment": series["deployment"],
            "log_auc_pct": series["log_auc_pct"], "untimed_pct": series["untimed_pct"],
            "log_auc_sd_pct": series["log_auc_sd_pct"],
            "p50_s": latency["p50"], "p95_s": latency["p95"], "curve_pct": curve,
        })
    if deviation > 0.05:
        raise ValueError(f"sampled curves disagree with the published log-AUC by {deviation:.3f} points")
    data = {
        "benchmark": figures["benchmark"], "states": figures["states"],
        "scenarios": figures["scenarios"], "families": figures["families"],
        "passes_per_setting": figures["passes_per_setting"], "recording_interval_s": 2.0,
        "primary_range_s": [0.5, 8.0], "intervals_s": intervals, "settings": settings,
        "sampled_auc_max_deviation_pct": deviation,
        "source": {"path": "docs/figures/data.json", "commit": os.environ.get("GITHUB_SHA")},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, separators=(",", ":")))
    shutil.copy(Path(__file__).with_name("index.html"), out / "index.html")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    result = build(parser.parse_args().out)
    print(f"{len(result['settings'])} settings, {len(result['intervals_s'])} intervals; "
          f"sampled log-AUC within {result['sampled_auc_max_deviation_pct']:.4f} points of published")
