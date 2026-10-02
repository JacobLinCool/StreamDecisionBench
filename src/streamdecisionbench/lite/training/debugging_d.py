"""Training variant debugging_d: a data-notebook debugging assistant (live_debugging family).

New-specification variant. It keeps the family design (an assistant inside a
developer's tools reads a streaming, cumulative tool state measured in ticks and
keeps an action card, always-shown status badges and route-specific detail
fields) but writes its own rules, questions and state layout: a Jupyter-style
notebook (cells with dependencies, run-time budgets, edit and execution ticks,
statuses and errors), its kernel (status, start, memory), the data snapshots the
cells read (with feed cadences and owner teams), the teams with their away
status and cover teams, and comments. The kernel timer is a per-cell run-time
budget, not a silence clock: output never resets it. Nothing is imported from
the evaluation family; every gold answer is computed by ``reference`` from the
public state alone, and the rule text in ``rules`` states all of it.

Story (north-shelf buoy gust QC notebook, Ilse and Ruairi): a frame load widened
from twelve hours to the full storm day (older partitions come back from the
archive) keeps printing partition progress, yet its runtime passes the cell's
budget (overrun badge) and reaches twice the budget, so for two ticks the card
asks to interrupt it. The interrupted cell is an open failure until its source
changes (the widening edit was captured by that very run). Narrowed to six hours
it loads, but the gust cell then fails with an error raised in the helpers cell
above it. While the failure is open a feed update waits; once helpers is edited
the stale frames snapshot is refreshed before any rerun. A run-below stops at the
scratch plot's error (ignored by every cell rule), leaving the summary to run;
the summary is rerun within the share tick and the results are shared (a start
at the share tick is not later than the share). Rerunning the plot pushes memory
exactly to 90% of the limit, the kernel dies, and Restart & Run All starts the
new kernel's first cell at its start tick; helpers fails with a NameError that
needs the units cell at the bottom of the notebook run first, not a fix. With
all cells current the frames feed is overdue and its owner is asked; when that
team goes off shift its cover is asked instead. An edit to the stations cell
asks for a run ahead of the overdue feed; once stations has rerun, rollup needs
a run, but a tightened constant in the units cell blocks it through its upstream
chain (rollup, gusts, helpers, units), so the units cell is the first runnable
cell although both of rollup's direct dependencies are current. The feed
resumes, the snapshot is refreshed in the same tick as the reruns start, and the
results are ready to share again (equality with the calibration cadence is not
yet overdue). One tick later the calibration feed is overdue; its owner and that
owner's cover are both away, so the cover's cover is asked.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

EPISODE_ID = "train_debugging_d"
TITLE = "North-shelf gust QC notebook: cell budgets, freshness and feed cover"
NOTEBOOK = "north_shelf_gust_qc.ipynb"

HARD_LIMIT_FACTOR = 2
MEMORY_RESTART_PERCENT = 90
MEMORY_LIMIT_MB = 4000

ROUTES = ("wait", "run_cell", "fix_cell", "interrupt_kernel", "restart_kernel",
          "refresh_table", "ask_data_owner", "share_results")
CELL_ROUTES = ("run_cell", "fix_cell", "interrupt_kernel")
IN_FLIGHT = ("queued", "running")

RULES = [
    "Clock and history: every time field is an integer tick and 'now' is the current tick. The snapshot "
    "for tick t is complete and holds nothing later than t. comments keep every entry; the notebook, "
    "kernel, data_sources and teams fields hold their latest values. Each question is answered "
    "independently from this one snapshot.",

    "Cells: notebook.cells lists the cells in notebook order, top to bottom. Tracked cells are the cells "
    "of kind code without the tag 'scratch'. Markdown cells and scratch cells are untracked: whatever "
    "their fields say, they are never outdated, current, open failures, in need of a run or runnable, "
    "never count as dependencies and never affect the freshness badge; only the kernel rules see a "
    "scratch cell, because it occupies the kernel while it runs. depends_on lists a "
    "cell's direct dependencies; its upstream cells are its tracked dependencies, their tracked "
    "dependencies, and so on. A dependency can sit below the cell in notebook order; dependencies never "
    "form a cycle. reads lists the data_sources tables the cell reads.",

    "Cell fields: edited_at is the tick of the cell's latest source edit. executed_at is the tick at "
    "which its latest execution STARTED, or null if it never started. The kernel captures a cell's "
    "source when its execution starts, so an edit whose edited_at equals the executed_at was captured "
    "by that execution. budget_ticks is the run time a code cell is "
    "expected to need (null for markdown). status is never_run, queued, running, ok or error; a queued "
    "cell keeps the executed_at of its previous execution. error is non-null exactly when status is "
    "error and gives type, message and raised_in_cell, the cell whose code raised the error, which can "
    "differ from the cell showing it. source, execution_count, output_rows, error.type and "
    "error.message are informational and decide nothing.",

    "Kernel: kernel.status is idle, busy, restarting or dead, and kernel.started_at is the tick at which "
    "the current kernel process started. While the kernel is busy exactly one cell has status running "
    "(the running cell, of any kind); at other times no cell is running or queued. A multi-cell run "
    "executes its queued cells in notebook order, starting each one at the tick the previous one "
    "finishes, and stops at the first error; queued cells it does not reach get their previous fields "
    "back. A quick cell can start and finish within one tick, so two cells can share an executed_at. A "
    "cell has run in the current kernel when the kernel is idle or busy and the cell's executed_at is "
    "not null and not earlier than kernel.started_at. While the kernel is dead or restarting no cell "
    "has run in the current kernel, and results left from an earlier kernel (status, error, output) "
    "count as never run. kernel.since (when the kernel entered its status, for a busy kernel the start "
    "of the whole multi-cell run), kernel.last_output, kernel.last_output_at and kernel.heartbeat_at "
    "are informational.",

    "Cell budget: while the kernel is busy, runtime is now minus the running cell's own executed_at, "
    "not the start of the multi-cell run. The running cell is over budget when its runtime is more than "
    "its budget_ticks (exactly budget_ticks is not yet over), and it has reached its hard limit when "
    "its runtime is at least twice its budget_ticks (exactly twice counts). Printed output, progress "
    "lines, heartbeats, memory readings, edits and comments neither extend nor reset a budget. "
    "kernel_badge: dead -> dead; restarting -> restarting; idle -> idle; busy with the running cell "
    "over budget -> overrun; any other busy kernel -> busy.",

    "Outdated: a tracked cell that has run in the current kernel is outdated when (a) its edited_at is "
    "later than its executed_at; (b) one of its upstream cells has an executed_at later than its "
    "executed_at, or has not run in the current kernel; (c) a table it reads has a loaded_at later than "
    "its executed_at; or (d) its status is error and the cell named by its error.raised_in_cell has an "
    "edited_at later than its executed_at. Later means strictly later: equal ticks never make a cell "
    "outdated.",

    "Cell states: a tracked cell is current when it has run in the current kernel, its status is ok and "
    "it is not outdated. It is an open failure when it has run in the current kernel, its status is "
    "error and it is not outdated, so nothing has changed since then that could have fixed it. It needs "
    "a run when its status is neither queued nor running and it has not run in the current kernel or is "
    "outdated. A cell is runnable when it needs a run and all of its upstream cells are current.",

    "Tables: a data_sources table counts only when some tracked cell reads it; a table read only by "
    "markdown or scratch cells is ignored. A counted table is behind when its source_updated_at is later "
    "than its loaded_at (a snapshot loaded at the same tick as the source update includes it). It is "
    "overdue when now minus its source_updated_at is more than its update_every (exactly update_every is "
    "not yet overdue). Refreshing a snapshot sets loaded_at to the refresh tick.",

    "Teams: each data_sources row names its owner team. teams lists every team once with a status, "
    "available or away, and a cover team or null. The team asked about a table is its owner when the "
    "owner is available; when the owner is away its cover is asked instead, and when that cover is away "
    "too, the cover's own cover, and so on until an available team is reached. Only status decides: the "
    "cover of an available team is never used. Covers never form a cycle and every chain ends at an "
    "available team.",

    "freshness_badge: broken when some tracked cell that has run in the current kernel has status error, "
    "whether or not that failure is still open; otherwise stale when some tracked cell is not current or "
    "some counted table is behind or overdue; otherwise fresh.",

    "next_action is decided by the FIRST rule that applies: (1) kernel dead -> restart_kernel. (2) kernel "
    "restarting -> wait. (3) memory_mb at least 90% of memory_limit_mb (exactly 90% counts) -> "
    "restart_kernel, also while busy. (4) kernel busy: the running cell has reached its hard limit -> "
    "interrupt_kernel; otherwise wait. (5) an open failure exists -> fix_cell. (6) a counted table is "
    "behind -> refresh_table. (7) a tracked cell needs a run -> run_cell. (8) a counted table is overdue "
    "-> ask_data_owner. (9) the results are unshared, meaning notebook.shared_at is null or some tracked "
    "cell has an executed_at strictly later than shared_at (a cell executed at the tick of shared_at counts as shared) -> share_results. (10) otherwise wait.",

    "Selections: interrupt_kernel names the running cell. fix_cell names the error.raised_in_cell of the "
    "first open failure in notebook order. run_cell names the first runnable cell in notebook order (one "
    "always exists when rule 7 applies). refresh_table names the first behind counted table in "
    "data_sources order; ask_data_owner names the first overdue counted table in data_sources order "
    "together with the team asked about it under the teams rule.",

    "Comments are discussion only: claims in them (that a load is progressing, a budget should be "
    "different, a snapshot is current, results were shared, a cell is broken, a team is away or owns a "
    "feed) never change an answer. Only the notebook, kernel, data_sources and teams fields do, and "
    "notebook.shared_at changes only when the results are actually shared.",

    "Applied decision: next_action, kernel_badge and freshness_badge always; plus cell for run_cell, "
    "fix_cell and interrupt_kernel; table for refresh_table; table and owner_team for ask_data_owner. "
    "Every field the chosen action does not use is answered none.",
]


def _tracked(cell: dict[str, Any]) -> bool:
    return cell["kind"] == "code" and "scratch" not in cell["tags"]


def _asked(state: dict[str, Any], owner: str) -> str:
    teams = {row["team"]: row for row in state["teams"]}
    team, seen = owner, set()
    while teams[team]["status"] == "away":
        if team in seen or teams[team]["cover"] is None:
            raise ValueError(f"the cover chain from {owner!r} never reaches an available team")
        seen.add(team)
        team = teams[team]["cover"]
    return team


def reference(state: dict[str, Any]) -> dict[str, str]:
    """Derive every answer from the public state alone (no tick index, gold or hidden field)."""
    now = state["now"]
    kernel = state["kernel"]
    cells = state["notebook"]["cells"]
    by_id = {cell["cell_id"]: cell for cell in cells}
    tracked = [cell for cell in cells if _tracked(cell)]
    alive = kernel["status"] in ("idle", "busy")
    running = [cell for cell in cells if cell["status"] == "running"]
    if kernel["status"] == "busy" and len(running) != 1:
        raise ValueError("a busy kernel runs exactly one cell")
    if kernel["status"] != "busy" and any(cell["status"] in IN_FLIGHT for cell in cells):
        raise ValueError("cells run or queue only while the kernel is busy")
    for cell in cells:
        if (cell["status"] == "error") != (cell["error"] is not None):
            raise ValueError(f"{cell['cell_id']}: error must be set exactly when status is error")
        if cell["kind"] == "code" and not cell["budget_ticks"]:
            raise ValueError(f"{cell['cell_id']}: a code cell needs a positive budget_ticks")

    def ran(cell: dict[str, Any]) -> bool:
        return alive and cell["executed_at"] is not None and cell["executed_at"] >= kernel["started_at"]

    def upstream(cell: dict[str, Any]) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        stack = list(cell["depends_on"])
        while stack:
            dep = by_id[stack.pop()]
            if not _tracked(dep) or dep["cell_id"] in found:
                continue
            if dep is cell:
                raise ValueError(f"dependency cycle through {cell['cell_id']}")
            found[dep["cell_id"]] = dep
            stack.extend(dep["depends_on"])
        return list(found.values())

    sources = {row["table"]: row for row in state["data_sources"]}

    def outdated(cell: dict[str, Any]) -> bool:
        start = cell["executed_at"]
        if cell["edited_at"] > start:
            return True
        if any(not ran(dep) or dep["executed_at"] > start for dep in upstream(cell)):
            return True
        if any(sources[table]["loaded_at"] > start for table in cell["reads"]):
            return True
        return cell["status"] == "error" and by_id[cell["error"]["raised_in_cell"]]["edited_at"] > start

    def current(cell: dict[str, Any]) -> bool:
        return ran(cell) and cell["status"] == "ok" and not outdated(cell)

    counted = [row for row in state["data_sources"] if any(row["table"] in cell["reads"] for cell in tracked)]
    behind = [row for row in counted if row["source_updated_at"] > row["loaded_at"]]
    overdue = [row for row in counted if now - row["source_updated_at"] > row["update_every"]]

    hard_limit = False
    if kernel["status"] == "busy":
        runtime = now - running[0]["executed_at"]
        budget = running[0]["budget_ticks"]
        hard_limit = runtime >= HARD_LIMIT_FACTOR * budget
        badge = "overrun" if runtime > budget else "busy"
    else:
        badge = kernel["status"]

    if any(ran(cell) and cell["status"] == "error" for cell in tracked):
        freshness = "broken"
    elif all(current(cell) for cell in tracked) and not behind and not overdue:
        freshness = "fresh"
    else:
        freshness = "stale"

    answer = {"next_action": "wait", "kernel_badge": badge, "freshness_badge": freshness,
              "cell": "none", "table": "none", "owner_team": "none"}
    if kernel["status"] == "dead":
        return answer | {"next_action": "restart_kernel"}
    if kernel["status"] == "restarting":
        return answer
    if 100 * kernel["memory_mb"] >= MEMORY_RESTART_PERCENT * kernel["memory_limit_mb"]:
        return answer | {"next_action": "restart_kernel"}
    if kernel["status"] == "busy":
        if hard_limit:
            return answer | {"next_action": "interrupt_kernel", "cell": running[0]["cell_id"]}
        return answer
    failures = [cell for cell in tracked if ran(cell) and cell["status"] == "error" and not outdated(cell)]
    if failures:
        return answer | {"next_action": "fix_cell", "cell": failures[0]["error"]["raised_in_cell"]}
    if behind:
        return answer | {"next_action": "refresh_table", "table": behind[0]["table"]}
    needs = [cell for cell in tracked if not ran(cell) or outdated(cell)]
    if needs:
        runnable = [cell for cell in needs if all(current(dep) for dep in upstream(cell))]
        if not runnable:
            raise ValueError("cells need a run but none is runnable")
        return answer | {"next_action": "run_cell", "cell": runnable[0]["cell_id"]}
    if overdue:
        row = overdue[0]
        return answer | {"next_action": "ask_data_owner", "table": row["table"],
                         "owner_team": _asked(state, row["owner"])}
    shared = state["notebook"]["shared_at"]
    if shared is None or any(cell["executed_at"] > shared for cell in tracked):
        return answer | {"next_action": "share_results"}
    return answer


# ---------------------------------------------------------------- questions

CELL_IDS = ["setup", "load_frames", "stations", "helpers", "gusts", "rollup", "explore_plot", "summary",
            "unit_table"]
TABLES = ["marine.buoy_frames", "ref.stations", "ops.sensor_calibration", "marine.tide_gauges"]
TEAMS = ["@marine-feeds", "@buoy-ingest", "@sensor-lab", "@station-registry", "@data-platform"]


def _questions() -> dict[str, dict[str, Any]]:
    def choice(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
        return {"type": "choice", "instructions": instructions, "criteria": criteria}

    return {
        "next_action": choice(
            "Which action card should the notebook assistant show now? Go through the numbered next_action "
            "rules in order and take the first one that applies; comments never count.",
            {"wait": "Show no action card: the kernel is restarting; or it is busy below the hard limit with "
                     "memory under 90% of the limit; or nothing is left to fix, refresh, run or ask about and "
                     "the results were shared with no tracked cell started later than shared_at",
             "run_cell": "Run the selected runnable cell",
             "fix_cell": "Fix the code of the cell that raised the open failure",
             "interrupt_kernel": "Interrupt the running cell: memory is under 90% of the limit and its runtime "
                                 "reached twice its budget",
             "restart_kernel": "Restart the kernel: it is dead, or it is not restarting and memory reached 90% "
                               "of the limit",
             "refresh_table": "Refresh the local snapshot of the selected table",
             "ask_data_owner": "Ask the selected team why the selected table's feed is overdue",
             "share_results": "Share the results: every tracked cell is current, no counted table is behind or "
                              "overdue, and the results were never shared or some tracked cell has started since "
                              "they were last shared (an executed_at later than shared_at)"}),
        "kernel_badge": choice(
            "Which kernel badge is displayed now? It is always shown, whatever the action card; derive it "
            "from kernel.status and, for a busy kernel, the running cell's runtime against its budget_ticks.",
            {"idle": "Kernel alive and not running a cell",
             "busy": "Running a cell whose runtime is within its budget",
             "overrun": "Running a cell whose runtime is more than its budget",
             "restarting": "Kernel is restarting",
             "dead": "Kernel process has died"}),
        "freshness_badge": choice(
            "Which notebook freshness badge is displayed now? It is always shown; apply the broken, stale "
            "and fresh definitions over tracked cells and counted tables.",
            {"broken": "A tracked cell shows an error from the current kernel",
             "stale": "No such error, but a tracked cell is not current or a counted table is behind or overdue",
             "fresh": "Every tracked cell current and every counted table neither behind nor overdue"}),
        "cell": choice(
            "Which cell does the action card name? interrupt_kernel: the running cell. fix_cell: the "
            "raised_in_cell of the first open failure in notebook order. run_cell: the first runnable cell "
            "in notebook order. Answer none for every other action.",
            {"none": "The action card names no cell",
             **{cell_id: f"Cell {cell_id}" for cell_id in CELL_IDS}}),
        "table": choice(
            "Which table does the action card name? refresh_table: the first behind counted table; "
            "ask_data_owner: the first overdue counted table; both in data_sources order. Answer none for "
            "every other action.",
            {"none": "The action card names no table", **{table: f"Table {table}" for table in TABLES}}),
        "owner_team": choice(
            "For ask_data_owner, which team is asked about the selected table: its owner team if available, "
            "otherwise the first available team along the chain of cover teams? Answer none for every other "
            "action.",
            {"none": "No team is asked", **{team: f"Ask {team}" for team in TEAMS}}),
    }


DECISION_SPEC = {
    "route_question": "next_action",
    "always": ["kernel_badge", "freshness_badge"],
    "branches": {"wait": [], "run_cell": ["cell"], "fix_cell": ["cell"], "interrupt_kernel": ["cell"],
                 "restart_kernel": [], "refresh_table": ["table"], "ask_data_owner": ["table", "owner_team"],
                 "share_results": []},
}


# ---------------------------------------------------------------- story

FRAMES_DAY = "frames = read_table('marine.buoy_frames', hours=24)"
FRAMES_SIX = "frames = read_table('marine.buoy_frames', hours=6)"
STATIONS_OLD = "stations = read_table('ref.stations')"
STATIONS_NEW = "stations = read_table('ref.stations').query('in_service')  # drop retired buoys"
HELPERS_OLD = ("cal = read_table('ops.sensor_calibration')\n"
               "GUST_ALERT_MS = 60 / KNOTS_PER_MS\n"
               "def to_knots(raw, dt):\n    return raw * KNOTS_PER_MS * cal.gain / dt")
HELPERS_NEW = ("cal = read_table('ops.sensor_calibration')\n"
               "GUST_ALERT_MS = 60 / KNOTS_PER_MS\n"
               "def to_knots(raw, dt):\n    return raw * KNOTS_PER_MS * cal.gain / dt if dt else float('nan')")
PLOT_OLD = "tides = read_table('marine.tide_gauges')\nhourly.unstack(0).plot()\ntides.plot(y='tide_m')"
PLOT_NEW = "tides = read_table('marine.tide_gauges')\nhourly.unstack(0).plot()\ntides.plot(y='level_m')"
UNITS_OLD = "KNOTS_PER_MS = 1.943844  # metres per second to knots"
UNITS_NEW = "KNOTS_PER_MS = 3600 / 1852  # metres per second to knots, exact"
NOTES_OLD = "## Notes\n- Gust peaks above 60 kn go to the forecast desk."
NOTES_NEW = NOTES_OLD + "\n- Re-check the outer-shelf buoy after its mast repair."

TIDE_ERROR = {"type": "ValueError", "message": "column 'tide_m' not found in the tide gauge snapshot",
              "raised_in_cell": "explore_plot"}
RUN_FIELDS = ("status", "executed_at", "execution_count", "output_rows", "error")


def _cell(cell_id: str, kind: str, source: str, edited_at: int, *, budget: int | None = None,
          tags: tuple[str, ...] = (), depends_on: tuple[str, ...] = (), reads: tuple[str, ...] = (),
          executed_at: int | None = None, count: int | None = None, status: str = "never_run",
          error: dict | None = None, rows: int | None = None) -> dict[str, Any]:
    return {"cell_id": cell_id, "kind": kind, "tags": list(tags), "source": source,
            "depends_on": list(depends_on), "reads": list(reads), "budget_ticks": budget,
            "edited_at": edited_at, "executed_at": executed_at, "execution_count": count, "status": status,
            "error": deepcopy(error), "output_rows": rows}


def _initial() -> dict[str, Any]:
    cells = [
        _cell("intro", "markdown", "# North-shelf gust QC\nHourly peak gusts per buoy, checked before the "
              "morning forecast.", -60),
        _cell("setup", "code", "import pandas as pd\nfrom shelfkit import read_table", -45, budget=2,
              executed_at=-39, count=1, status="ok"),
        _cell("load_frames", "code", FRAMES_DAY, -5, budget=5, depends_on=("setup",),
              reads=("marine.buoy_frames",), executed_at=-5, status="running"),
        _cell("stations", "code", STATIONS_OLD, -44, budget=2, depends_on=("setup",),
              reads=("ref.stations",), executed_at=-33, count=5, status="ok", rows=30),
        _cell("helpers", "code", HELPERS_OLD, -43, budget=2, depends_on=("setup", "unit_table"),
              reads=("ops.sensor_calibration",), executed_at=-36, count=3, status="ok"),
        _cell("gusts", "code", "gusts = frames.assign(knots=[to_knots(r, d) for r, d in zip(frames.raw, frames.dt)])",
              -42, budget=3, depends_on=("load_frames", "helpers"), executed_at=-31, count=6, status="ok",
              rows=21600),
        _cell("rollup", "code", "hourly = gusts.merge(stations, on='buoy').groupby(['buoy', 'hour']).knots.max()",
              -41, budget=2, depends_on=("gusts", "stations"), executed_at=-30, count=7, status="ok", rows=360),
        _cell("explore_plot", "code", PLOT_OLD, -29, budget=3, tags=("scratch",), depends_on=("rollup",),
              reads=("marine.tide_gauges",), executed_at=-27, count=9, status="error", error=TIDE_ERROR),
        _cell("summary", "code", "summary = hourly.groupby(level='buoy').describe()", -40, budget=2,
              depends_on=("rollup",), executed_at=-28, count=8, status="ok", rows=30),
        _cell("unit_table", "code", UNITS_OLD, -38, budget=2,
              depends_on=("setup",), executed_at=-37, count=2, status="ok"),
        _cell("notes", "markdown", NOTES_OLD, -58),
    ]
    return {
        "now": 0,
        "rules": list(RULES),
        "notebook": {"name": NOTEBOOK, "shared_at": None, "cells": cells},
        "kernel": {"status": "busy", "since": -5, "started_at": -40, "last_output": "partition 4 of 24 loaded",
                   "last_output_at": -1, "heartbeat_at": 0, "memory_mb": 2380,
                   "memory_limit_mb": MEMORY_LIMIT_MB},
        "data_sources": [
            {"table": "marine.buoy_frames", "owner": "@marine-feeds", "loaded_at": -7, "source_updated_at": -7,
             "update_every": 30},
            {"table": "ref.stations", "owner": "@station-registry", "loaded_at": -41, "source_updated_at": -60,
             "update_every": 240},
            {"table": "ops.sensor_calibration", "owner": "@sensor-lab", "loaded_at": -42,
             "source_updated_at": -43, "update_every": 100},
            {"table": "marine.tide_gauges", "owner": "@data-platform", "loaded_at": -46,
             "source_updated_at": -50, "update_every": 10},
        ],
        "teams": [
            {"team": "@marine-feeds", "status": "available", "cover": "@buoy-ingest"},
            {"team": "@buoy-ingest", "status": "available", "cover": "@data-platform"},
            {"team": "@sensor-lab", "status": "away", "cover": "@marine-feeds"},
            {"team": "@station-registry", "status": "available", "cover": "@data-platform"},
            {"team": "@data-platform", "status": "available", "cover": None},
        ],
        "comments": [{"at": -5, "author": "Ilse",
                      "text": "Widened load_frames from twelve hours to the full storm day; the older hourly "
                              "partitions come back from the archive."}],
    }


# Authoring witnesses for ticks whose decision turns on an ordering rule, a boundary or a distractor.
NOTES = {
    0: "load_frames started at -5 with budget 5: runtime 5 is exactly the budget, not over it",
    1: "runtime 6 is more than the budget: overrun badge; the hard limit is 10",
    2: "progress output every tick does not reset the budget",
    5: "runtime 10 is exactly twice the budget: interrupt the running load_frames",
    6: "runtime 11 is past the hard limit, still printing progress: the interrupt card stays",
    7: "the widening edit at -5 was captured by the run started at -5: not outdated, so an open failure; "
       "fix load_frames",
    9: "load_frames edited after its failed run: outdated, so it needs a run instead of a fix; the frames "
       "snapshot loaded at the source update tick is not behind",
    13: "gusts shows the error but helpers raised it: fix helpers",
    15: "frames source updated after the snapshot: behind, but the open failure outranks the refresh",
    16: "helpers edited after gusts failed: no open failure; the behind snapshot is refreshed before any run",
    18: "snapshot loaded after load_frames ran: load_frames is the first runnable cell",
    22: "gusts reran after rollup: rollup is the first runnable cell",
    24: "memory 3596 is below 90% of 4000",
    25: "the scratch plot's error is ignored; summary is outdated by rollup's rerun",
    27: "every tracked cell current, counted tables neither behind nor overdue, never shared",
    28: "a comment about sharing does not set notebook.shared_at",
    29: "summary started at the share tick, which is not later than shared_at: the results count as shared",
    31: "memory exactly 3600 = 90% of 4000: restart outranks the busy kernel",
    33: "dead kernel: no cell has run in the current kernel",
    35: "Restart & Run All: setup started and finished at the new kernel's start tick 35, and load_frames "
        "started in the same tick",
    39: "helpers started at 39 with budget 2: runtime 0, although the run began at 35",
    40: "helpers failed while its upstream unit_table had not run in this kernel: not an open failure; "
        "unit_table (bottom of the notebook) is the first runnable cell; setup started at the kernel start "
        "tick and load_frames at setup's tick, so both count as current",
    43: "unit_table ran after helpers failed: helpers is outdated and runnable",
    48: "frames feed overdue (48 - 15 > 30); @marine-feeds is available, so its cover is not used",
    49: "a comment says @marine-feeds is off shift, but teams still lists it as available",
    50: "@marine-feeds is now away: its cover @buoy-ingest is asked",
    51: "stations edited after its run, nothing else changed: the run card outranks the overdue feed",
    52: "stations reran, so rollup needs a run; its direct dependencies gusts and stations are current, but "
        "unit_table, upstream of rollup through gusts and helpers, was edited: unit_table is the first "
        "runnable cell, whatever the comment says",
    53: "frames source updated after the snapshot: behind; refresh outranks the pending runs",
    54: "snapshot refreshed in the same tick as the rerun of load_frames starts; unit_table is quick: it "
        "starts and finishes within the tick before the chain starts",
    57: "load_frames started at the refresh tick, so it is current; calibration exactly at its cadence "
        "(57 + 43 = 100): not yet overdue; results changed since the share",
    58: "calibration overdue (101 > 100); @sensor-lab and its cover @marine-feeds are away: ask @buoy-ingest",
}


def _build() -> dict[str, Any]:
    state = _initial()
    cells = state["notebook"]["cells"]
    kernel = state["kernel"]
    queue: list[str] = []
    saved: dict[str, dict[str, Any]] = {}
    counter = 9
    now = 0
    evidence: list[str] = []

    def cell(cell_id: str) -> dict[str, Any]:
        return next(row for row in cells if row["cell_id"] == cell_id)

    def table(name: str) -> dict[str, Any]:
        return next(row for row in state["data_sources"] if row["table"] == name)

    def say(author: str, text: str) -> None:
        state["comments"].append({"at": now, "author": author, "text": text})
        evidence.append(f"comment {author}: {text}")

    def edit(cell_id: str, source: str) -> None:
        cell(cell_id).update(source=source, edited_at=now)
        evidence.append(f"edited {cell_id}")

    def start(cell_id: str) -> None:
        cell(cell_id).update(status="running", executed_at=now, execution_count=None, output_rows=None, error=None)

    def run(*cell_ids: str) -> None:
        for cell_id in cell_ids:
            saved[cell_id] = {key: deepcopy(cell(cell_id)[key]) for key in RUN_FIELDS}
        start(cell_ids[0])
        for cell_id in cell_ids[1:]:
            cell(cell_id).update(status="queued", error=None)
        queue[:] = cell_ids[1:]
        kernel.update(status="busy", since=now)
        evidence.append("run started: " + ", ".join(cell_ids))

    def stop_queue() -> None:
        for cell_id in queue:
            cell(cell_id).update(deepcopy(saved[cell_id]))
        if queue:
            evidence.append("queue stopped; not reached: " + ", ".join(queue))
        queue.clear()
        kernel.update(status="idle", since=now)

    def running() -> dict[str, Any]:
        return next(row for row in cells if row["status"] == "running")

    def output(text: str) -> None:
        kernel.update(last_output=text, last_output_at=now)
        evidence.append(f"{running()['cell_id']} printed: {text}")

    def finish(rows: int | None = None, error: dict | None = None) -> None:
        nonlocal counter
        done = running()
        counter += 1
        done["execution_count"] = counter
        if rows is not None:
            kernel.update(last_output=f"{rows} rows", last_output_at=now)
        if error is not None:
            kernel.update(last_output=f"{error['type']}: {error['message']}", last_output_at=now)
            done.update(status="error", error=dict(error))
            evidence.append(f"{done['cell_id']} failed: {error['type']}: {error['message']}")
            stop_queue()
            return
        done.update(status="ok", output_rows=rows)
        evidence.append(f"{done['cell_id']} finished ok" + ("" if rows is None else f", {rows} rows"))
        if queue:
            start(queue.pop(0))
        else:
            kernel.update(status="idle", since=now)

    def interrupt(where: str) -> None:
        nonlocal counter
        stopped = running()
        counter += 1
        stopped.update(status="error", execution_count=counter,
                       error={"type": "KeyboardInterrupt", "message": f"interrupted while reading {where}",
                              "raised_in_cell": stopped["cell_id"]})
        kernel.update(last_output="KeyboardInterrupt", last_output_at=now)
        evidence.append(f"kernel interrupted; {stopped['cell_id']} raised KeyboardInterrupt")
        stop_queue()

    def die() -> None:
        lost = running()
        lost.update(status="error", error={"type": "DeadKernelError", "message": "kernel died while this cell was running",
                                           "raised_in_cell": lost["cell_id"]})
        stop_queue()
        kernel.update(status="dead", since=now, memory_mb=0)
        evidence.append("kernel died (out of memory)")

    def restart() -> None:
        kernel.update(status="restarting", since=now)
        evidence.append("Restart & Run All requested")

    def kernel_ready() -> None:
        nonlocal counter
        counter = 0
        kernel.update(status="idle", since=now, started_at=now, last_output=None, last_output_at=None,
                      memory_mb=160)
        evidence.append(f"new kernel started at {now}")

    def memory(mb: int) -> None:
        kernel["memory_mb"] = mb
        evidence.append(f"memory {mb} MB of {MEMORY_LIMIT_MB}")

    def source_update(name: str) -> None:
        table(name)["source_updated_at"] = now
        evidence.append(f"source of {name} updated")

    def refresh(name: str) -> None:
        table(name)["loaded_at"] = now
        evidence.append(f"snapshot of {name} refreshed")

    def team_status(team: str, status: str) -> None:
        next(row for row in state["teams"] if row["team"] == team)["status"] = status
        evidence.append(f"{team} is now {status}")

    def share() -> None:
        state["notebook"]["shared_at"] = now
        evidence.append("results shared with the forecast desk")

    steps = []
    for tick in range(60):
        now = tick
        evidence = []
        state["now"] = tick
        # Act 1: the day-long frame load keeps printing progress but runs past its budget.
        if tick <= 6: output(f"partition {tick + 5} of 24 loaded")
        if tick == 2: say("Ruairi", "Memory is flat at about 2.4 GB, so that load is healthy.")
        if tick == 3: memory(2410)
        if tick == 4: say("Ilse", "Could we bump its budget to 24 so the badge goes away?")
        if tick == 6: memory(2430)
        if tick == 7:
            interrupt("partition 12 of 24")
            memory(2400)
        if tick == 8: say("Ruairi", "Half the day had already loaded; just rerun it unchanged.")
        if tick == 9: edit("load_frames", FRAMES_SIX)
        if tick == 10: run("load_frames", "gusts")
        if tick == 11: output("loaded 4 of 6 hourly partitions (recent hours, none archived)")
        if tick == 12:
            finish(rows=10800)
            memory(2650)
        if tick == 13:
            finish(error={"type": "ZeroDivisionError", "message": "float division by zero in to_knots",
                          "raised_in_cell": "helpers"})
            memory(2700)
        # Act 2: helpers is fixed, the snapshot refreshed, the chain rerun and shared.
        if tick == 14: say("Ilse", "The traceback is printed under gusts, so the bug has to be in gusts.")
        if tick == 15: source_update("marine.buoy_frames")
        if tick == 16: edit("helpers", HELPERS_NEW)
        if tick == 17: say("Ruairi", "I pulled fresh frames this morning; that snapshot is already current.")
        if tick == 18: refresh("marine.buoy_frames")
        if tick == 19: run("load_frames", "helpers", "gusts")
        if tick == 20:
            finish(rows=10800)
            memory(2900)
        if tick == 21: finish()
        if tick == 22:
            finish(rows=10800)
            memory(3100)
        if tick == 23: run("rollup", "explore_plot", "summary", "unit_table")
        if tick == 24:
            finish(rows=180)
            memory(3596)
            source_update("marine.tide_gauges")
        if tick == 25:
            finish(error=TIDE_ERROR)
            memory(3420)
        if tick == 26: run("summary")
        if tick == 27:
            finish(rows=30)
            memory(3440)
        if tick == 28: say("Ilse", "Sharing these numbers with the forecast desk now.")
        if tick == 29:
            run("summary")
            finish(rows=30)
            share()
        # Act 3: the plot exhausts memory, the kernel dies; Restart & Run All exposes the units cell.
        if tick == 30: edit("explore_plot", PLOT_NEW)
        if tick == 31:
            run("explore_plot")
            memory(3600)
        if tick == 32:
            say("Ruairi", "Plots always spike the memory; it will drop again by itself.")
            memory(3720)
        if tick == 33: die()
        if tick == 34: restart()
        if tick == 35:
            kernel_ready()
            run("setup", "load_frames", "stations", "helpers", "gusts", "rollup", "explore_plot",
                "summary", "unit_table")
            finish()
            memory(240)
        if tick == 36: memory(700)
        if tick == 37: output("loaded 5 of 6 hourly partitions")
        if tick == 38:
            finish(rows=10800)
            memory(1150)
        if tick == 39:
            finish(rows=30)
            memory(1210)
        if tick == 40:
            finish(error={"type": "NameError", "message": "name 'KNOTS_PER_MS' is not defined",
                          "raised_in_cell": "helpers"})
        if tick == 41: say("Ruairi", "NameError means helpers itself is broken, so fix that cell first.")
        if tick == 42: run("unit_table")
        if tick == 43: finish()
        if tick == 44: run("helpers", "gusts", "rollup", "summary")
        if tick == 45:
            finish()
            memory(1300)
        if tick == 46:
            finish(rows=10800)
            memory(1700)
        if tick == 47:
            finish(rows=180)
            memory(2150)
        if tick == 48: finish(rows=30)
        # Act 4: an overdue feed and its cover teams; edits to stations and to the units constant upstream
        # of rollup; the refreshed chain is ready to share again.
        if tick == 49:
            say("Ruairi", "Marine feeds are off shift for the rest of the day, so ask @buoy-ingest.")
            edit("notes", NOTES_NEW)
        if tick == 50: team_status("@marine-feeds", "away")
        if tick == 51: edit("stations", STATIONS_NEW)
        if tick == 52:
            run("stations")
            finish(rows=27)
            edit("unit_table", UNITS_NEW)
            say("Ruairi", "Tightened KNOTS_PER_MS; rollup sits above the units cell, so run rollup first.")
        if tick == 53: source_update("marine.buoy_frames")
        if tick == 54:
            refresh("marine.buoy_frames")
            run("unit_table")
            finish()
            run("load_frames", "helpers", "gusts", "rollup", "summary")
        if tick == 55:
            finish(rows=10800)
            finish()
            memory(2400)
        if tick == 56:
            finish(rows=10800)
            finish(rows=162)
            memory(2600)
        if tick == 57: finish(rows=27)
        if tick == 59: say("Ruairi", "Calibration is @sensor-lab's feed, so just ask them directly.")
        if kernel["status"] in ("idle", "busy"):
            kernel["heartbeat_at"] = tick
        if tick in NOTES:
            evidence.append(NOTES[tick])
        if not evidence:
            evidence = [f"tick {tick}: heartbeat only, kernel {kernel['status']}; no new event"]
        public = deepcopy(state)
        steps.append({"t": tick, "state": public, "gold": reference(public), "evidence": evidence})
    return {
        "episode_id": EPISODE_ID, "task_family": "live_debugging", "scenario_id": "debugging_d",
        "title": TITLE, "tick_seconds": 2.0, "questions": _questions(),
        "decision_spec": deepcopy(DECISION_SPEC), "steps": steps,
    }


def scenarios() -> list[dict[str, Any]]:
    """One 60-tick notebook debugging session of the training split."""
    return [_build()]
