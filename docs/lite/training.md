# Training split

`data/lite/train-v1/` holds further scenarios of the four task families for training decision
components. They are **never part of an evaluation score**: the benchmark remains the eight
scenarios of `data/lite/v1/` (dataset hash `fdfdd55d…`), whose files and hashes this split does not
change.

| Family | Evaluation (`data/lite/v1`) | Training (`data/lite/train-v1`) |
|---|---|---|
| `live_debugging` | `lite_debugging_a`, `lite_debugging_b` | `train_debugging_c`, `train_debugging_d` |
| `procedural_coaching` | `lite_assembly_a`, `lite_assembly_b` | `train_assembly_c`, `train_assembly_d` |
| `support_call_assist` | `lite_support_a`, `lite_support_b` | `train_support_c`, `train_support_d` |
| `presenter_voice_control` | `lite_presenter_a`, `lite_presenter_b` | `train_presenter_c`, `train_presenter_d` |

Each training scenario has the evaluation format: 60 ticks of 2 s, choice questions with opaque
labels, a `decision_spec`, and reference answers computed by an executable function of the public
state alone. The files load with `load_dataset` and run with the same commands, for example
`uv run python -m streamdecisionbench.lite run --data data/lite/train-v1 ...`.

```bash
uv run python -m streamdecisionbench.lite build --split train --data <empty dir>   # rebuild the split
uv run python -m streamdecisionbench.lite.training check                            # validate and audit every module
uv run pytest -q tests/test_lite_training*.py
```

## Separation from evaluation

A family's published rules are its task specification: the debugging policy, the presenter rules
and the assembly station's common rules are shared, as they are between the two evaluation scenarios
of a family. Everything else is new instance content: projects, people, organisations, files, tests,
decks, slide names, orders, codes, utterances and story beats. The assembly and support variants go
further and define new workflows with their own rules, questions and references.

`streamdecisionbench.lite.training.audit.leakage` enforces the separation, and both the build and the
tests run it. Outside the `rules`/`policy` fields and question instructions, a training state may not
repeat an evaluation state, an evaluation string of four or more words, any six-word run of
evaluation text, or an evaluation identifier (paths, `@teams`, codes containing digits, codes such as
`ST-A`); positional record ids such as `u12-Customer` are exempt. Test-runner summary lines are tool
output formats, not authored content, and are exempt too.

## Verification

Every variant was checked like the evaluation scenarios (see `paper/notes/audit_summary.md`), by LLM
agents rather than human validation:

- **Executable reference.** The stored answers equal `reference(state)` at every tick; the reference is
  pure and reads no tick index or hidden field; every answer is a declared option.
- **Blind re-derivation.** An agent that never read the module or the family's reference code wrote
  an independent program from the public rule text and question instructions alone and compared it
  with the stored answers at all 60 ticks, then hand-walked every decision change.
- **Adversarial review.** A second agent checked the reference line by line against the rule text,
  the family's state conventions (for example the streaming-ASR transcript conventions), causality,
  coverage and leakage.
- Findings were fixed and both checks repeated until no blocking or major finding remained.

<!-- VARIANTS -->
