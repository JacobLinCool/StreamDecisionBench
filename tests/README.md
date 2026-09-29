# Tests

Run them with `uv run pytest` from the repository root; no test makes a paid model request.

| Status | Files |
|---|---|
| **Current** (SDB; internal name `lite`) | `test_lite_*.py` |
| Shared adapters | `test_openai.py` (OpenAI adapter), `test_pipeline.py` (TypeSafe SDK through the mock Jev server) |
| Legacy (`sdb` CLI, v0 and `sdb/0.2`) | `test_metrics.py`, `test_replay.py`, `test_realtime.py`, `test_presentation_navigation.py`, `test_baselines.py` |

Some shared and legacy tests read `data/legacy/v0` from disk. That folder is local only and not versioned, so in a fresh clone these tests skip until `uv run sdb build` regenerates it (about 2 s, byte-identical episodes).
