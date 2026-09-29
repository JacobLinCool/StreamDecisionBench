"""Inspect reference dwell times without changing data or reading model scores."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/lite/v1"
# Versioned frozen copy of the six episodes the paper recorded on build 60f6a877.
PAPER_EPISODES = ROOT / "runs/lite-v1-jev-latest-retry-v1/episodes.json"
CANDIDATE_INTERVALS = {
    "live_debugging": 1,
    "procedural_coaching": 2,
    "support_call_assist": 1,
    "presenter_voice_control": 1,
}


def summarize(path: Path) -> dict:
    raw = path.read_bytes()
    episode = json.loads(raw)
    spec = episode["decision_spec"]

    def compose(answers: dict) -> dict:
        route = answers[spec["route_question"]]
        keys = [spec["route_question"], *spec["always"], *spec["branches"][route]]
        return {key: answers[key] for key in keys}

    gold = [compose(step["gold"]) for step in episode["steps"]]
    boundaries = [0] + [i for i in range(1, len(gold)) if gold[i] != gold[i - 1]] + [len(gold)]
    dwells = [end - start for start, end in zip(boundaries, boundaries[1:])]
    candidate = CANDIDATE_INTERVALS[episode["task_family"]]
    frozen = {e["episode_id"]: e for e in json.loads(PAPER_EPISODES.read_text())} if PAPER_EPISODES.is_file() else {}
    return {
        "episode_id": episode["episode_id"],
        "task_family": episode["task_family"],
        "source": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "identical_to_paper_dataset": frozen[episode["episode_id"]] == episode if episode["episode_id"] in frozen else None,
        "steps": len(gold),
        "recorded_interval_s": episode["tick_seconds"],
        "candidate_interval_s": candidate,
        "reference_changes": len(dwells) - 1,
        "reference_segments": len(dwells),
        "segment_lengths_ticks": dwells,
        "segment_median_ticks": median(dwells),
        "segment_mean_ticks": mean(dwells),
        "one_tick_segments": dwells.count(1),
        "candidate_segment_median_s": candidate * median(dwells),
        "candidate_horizon_s": candidate * len(gold),
    }


if __name__ == "__main__":
    manifest_path = DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    report = {
        "purpose": "Synthetic reference-segment audit, not human timing data or model performance.",
        "median_definition": "Unweighted median over maximal constant branch-composed reference segments.",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "episodes": [summarize(DATA / (entry["episode_id"] + ".json")) for entry in manifest["episodes"]],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
