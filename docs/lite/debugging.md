# IDE debugging tasks

The debugging family evaluates an IDE decision component that maintains two
status badges and one action card while developer and tool events arrive. It
does not execute a repair. Two independent sessions each contain 60 releases
spaced two seconds apart, covering 120 seconds. Public evidence and timer
thresholds determine the reference at each release; there are no hidden
speech-act, stale-result, owner or failure-category annotations.

## Decisions and questions

Each snapshot includes the public policy, runner results, editor buffers,
timestamped writes, debugger events, terminal output, repository ownership rules,
and teammate messages. Structured fields represent observations an IDE or test
reporter can supply. Failure selection, result freshness, scope, priority,
ownership and handoff interpretation remain decisions to be inferred.

| Question | Use in the application |
|---|---|
| `route` | Select wait, rerun, inspect, control, delegate or ready |
| `process` | Always visible: idle, running, paused or stalled |
| `target_result` | Always visible: last completed target result |
| `rerun_scope` | Used only by rerun: target, module or full suite |
| `inspect_file` | Used only by inspect: the relevant compiler or failure file |
| `control_action` | Used only by control: continue paused run or stop silent run |
| `owner` | Used only by delegate: the team owning the selected failure frame |

The effective decision includes the selected route, both badges and its active
branch field. Inactive fields are ignored. Each question sees the same state;
its answer does not depend on another generated answer. The raw reference fills
inactive branch fields with `none`, but scoring must ignore those fields instead
of demanding that a model also return `none`.

## Public policy

The complete executable policy is included as `session.policy` in every state.
The action priority is: overdue run control; active run, unsaved edits or save
grace; changes after a run started; compiler errors; target not executed;
selected test failure and ownership; incomplete test coverage; readiness.
An eight-second silence changes the process badge; twelve seconds enables the
stop action. An eight-second pause without debugger interaction enables continue.
Saves, speech and unrelated terminal output cannot reset those debugger/process
timers. The four-second save grace is strict: exactly four seconds permits a
rerun. A save exactly at a run's start is included in that run.

The latest *finished* run supplies the target badge even while another run is
active. Compiler failure, interruption and a skipped or absent target are not
passes. Selection among failures first identifies a newly failing test, then the
pinned target, then list order. Ownership uses the innermost in-project frame and
the last matching ownership pattern. A positive final commitment to contact the
correct team about the correct run clears delegation; tentative suggestions,
partial transcripts and mismatched teams or runs do not.

## Independent sessions

**Refund watch loop.** A TypeScript refund calculation first fails differently,
then a new fee regression takes priority over the still-failing pinned test.
Unsaved edits and save grace suppress action, a compiler error prevents tests
from executing, and a focused green run is incomplete because it skipped too
many tests. A complete green run becomes ready. A later configuration write
requires the full suite, which exposes an external runtime failure. A message
about an older run and a partial commitment leave delegation active; the final
matching commitment clears it. Documentation edits preserve the current action.

**Settlement integration session.** The current failure first selects its local
raising file. A new integration test starts, pauses and receives a code edit;
evaluating variables resets the pause timer while the save does not. A
continue action outranks an unsaved buffer, and continuing resets run silence.
The subsequent result predates the edit and needs rerunning. A later silent run
first becomes stalled and then requires stopping, despite unrelated terminal
activity. The ensuing run exposes an FX-owned error; wrong-team and tentative
messages do not resolve handoff. A later failure in shared infrastructure has a
different owner, and a final full-suite pass becomes ready before a commit clears
the action.

The two sessions exercise all six action routes, all four process states, all
four target-result states, all three rerun scopes, both run-control actions and
three external owners. They deliberately retain periods of unchanged decisions
under cursor motion, irrelevant edits and speech. Those releases are correlated
observations of one session, not independent examples.

## Reproduction and validation

`scenarios()` returns the two episode dictionaries; `reference(state)` accepts
only their public state. Tests independently assert boundary and conflict cases,
including minimal counterfactual changes to timestamps, failure history,
ownership frames and transcript wording. They check public-only round trips,
absence of future timestamps, option membership and deterministic generation.
These checks establish conformance to the disclosed synthetic policy; they do
not establish general language understanding or deployed IDE utility. Handoff
utterances use a bounded grammar of natural first-person commitments; broader
paraphrase coverage is a future data extension.
