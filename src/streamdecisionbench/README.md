# Package map

| Status | Modules |
|---|---|
| **Current** (SDB; internal name `lite`) | `lite/`: `build`/`run`/`score`/`merge` CLI (`__main__`), `tasks/` generators, `core`, `runtime`, `scoring`, `retry_scoring`, `interval_scoring`, `reference_scoring` |
| Shared | `jev.py` (System One contract), `adapters/` (OpenAI, TypeSafe/Jev, local references), `mock_server.py` (local Jev-compatible server), `schema.py` and `authoring/` (used by the local reference adapters), `cli.load_dotenv` |
| Legacy (`sdb` CLI, v0 and `sdb/0.2`) | `cli.py`, `families/`, `evaluator.py`, `metrics.py`, `validate.py`, `blind.py`, `audit/` |

Legacy modules still build and test the data in `data/legacy/v0` (local only, not versioned); apart from
`cli.load_dotenv`, the current benchmark does not import them. Their designs are in `docs/legacy/` (local
only, not versioned).
