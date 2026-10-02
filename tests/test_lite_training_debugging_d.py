"""Reproduction, conventions, story and counterfactual checks for training variant debugging_d.

debugging_d is a new-specification variant of the live_debugging family: a data-notebook
debugging assistant with its own rules, questions and state layout (per-cell run-time
budgets instead of a silence clock, and owner teams with away status and cover teams).
"""

from copy import deepcopy
import inspect
import json

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.training import debugging_d
from streamdecisionbench.lite.training.audit import eval_scenarios, layout_overlap, leakage, spec_overlap
from streamdecisionbench.lite.training.debugging_d import reference, scenarios

FRAMES = "marine.buoy_frames"
STATIONS = "ref.stations"
CALIBRATION = "ops.sensor_calibration"
TIDES = "marine.tide_gauges"


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def at(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def cell(state, cell_id):
    return next(row for row in state["notebook"]["cells"] if row["cell_id"] == cell_id)


def table(state, name):
    return next(row for row in state["data_sources"] if row["table"] == name)


def team(state, name):
    return next(row for row in state["teams"] if row["team"] == name)


def action(state):
    return reference(state)["next_action"]


# ---------------------------------------------------------------- identity and independence


def test_identity_and_new_specification(episode):
    assert (episode["episode_id"], episode["scenario_id"]) == ("train_debugging_d", "debugging_d")
    assert episode["task_family"] == "live_debugging"
    assert episode["tick_seconds"] == 2.0 and len(episode["steps"]) == 60
    source = inspect.getsource(debugging_d)
    assert "lite.tasks" not in source and "import debugging" not in source
    assert spec_overlap([episode]) == []
    assert leakage([episode]) == []
    assert layout_overlap(episode) <= 0.5
    evaluation = [e for e in eval_scenarios() if e["task_family"] == "live_debugging"]
    for other in evaluation:
        assert set(episode["questions"]).isdisjoint(other["questions"])
        assert set(episode["decision_spec"]["branches"]) & set(other["decision_spec"]["branches"]) == {"wait"}
        for qid, question in episode["questions"].items():
            assert all(question["criteria"] != q["criteria"] for q in other["questions"].values())


def test_option_texts_agree_with_the_numbered_rules(episode):
    criteria = episode["questions"]["next_action"]["criteria"]
    share, wait = criteria["share_results"], criteria["wait"]
    rules = " ".join(debugging_d.RULES)
    assert ("notebook.shared_at is null or some tracked cell has an executed_at strictly later than shared_at "
            "(a cell executed at the tick of shared_at counts as shared) -> share_results") in rules
    assert "never shared" in share and "has started since" in share and "later than shared_at" in share
    assert "no tracked cell has started since" not in share
    assert "memory under 90%" in wait and "no tracked cell started later than shared_at" in wait
    assert "memory is under 90%" in criteria["interrupt_kernel"] and "not restarting" in criteria["restart_kernel"]
    for step in episode["steps"]:  # the option texts hold wherever gold picks them
        state, gold = step["state"], step["gold"]
        shared = state["notebook"]["shared_at"]
        tracked = [row for row in state["notebook"]["cells"] if debugging_d._tracked(row)]
        unshared = shared is None or any(row["executed_at"] > shared for row in tracked)
        if gold["next_action"] == "share_results":
            assert unshared and gold["freshness_badge"] == "fresh"
        if gold["next_action"] == "wait" and state["kernel"]["status"] == "idle":
            assert not unshared and gold["freshness_badge"] == "fresh"


def test_kernel_timer_is_a_budget_not_a_silence_clock():
    text = " ".join(debugging_d.RULES).lower()
    assert "silence" not in text and "silent" not in text
    assert "budget_ticks" in text and "neither extend nor reset a budget" in text


def test_encodes_and_validates(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["routes_unseen"] == []
    assert 18 <= summary["decision_transitions"] <= 32


# ---------------------------------------------------------------- reproduction and conventions


def test_public_only_reproduction(episode):
    spec = episode["decision_spec"]
    for tick, step in enumerate(episode["steps"]):
        assert step["t"] == tick
        assert step["evidence"] and all(isinstance(item, str) and item for item in step["evidence"])
        state = json.loads(json.dumps(step["state"]))
        assert state["now"] == tick
        assert not {"gold", "hidden", "answer", "t", "tick"} & state.keys()
        before = deepcopy(state)
        assert reference(state) == step["gold"]
        assert state == before, "reference must not mutate its input"
        assert set(step["gold"]) == set(episode["questions"])
        for qid, value in step["gold"].items():
            assert value in episode["questions"][qid]["criteria"]
        used = {spec["route_question"], *spec["always"], *spec["branches"][step["gold"]["next_action"]]}
        assert all(value == "none" for qid, value in step["gold"].items() if qid not in used)
        assert all(step["gold"][qid] != "none" for qid in used)


def test_states_are_causal(episode):
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        kernel = state["kernel"]
        times = [kernel["since"], kernel["started_at"], kernel["heartbeat_at"]]
        times += [kernel["last_output_at"], state["notebook"]["shared_at"]]
        times += [row["at"] for row in state["comments"]]
        times += [row[key] for row in state["data_sources"] for key in ("loaded_at", "source_updated_at")]
        for row in state["notebook"]["cells"]:
            times += [row["edited_at"], row["executed_at"]]
        assert all(value <= tick for value in times if value is not None)


def _upstream_ids(state, cell_id):
    seen, stack = set(), list(cell(state, cell_id)["depends_on"])
    while stack:
        dep = stack.pop()
        if dep not in seen:
            seen.add(dep)
            stack.extend(cell(state, dep)["depends_on"])
    return seen


def test_stated_conventions_hold_in_every_state(episode):
    first = episode["steps"][0]["state"]
    order = [row["cell_id"] for row in first["notebook"]["cells"]]
    tables = [row["table"] for row in first["data_sources"]]
    covers = [(row["team"], row["cover"]) for row in first["teams"]]
    budgets = {row["cell_id"]: row["budget_ticks"] for row in first["notebook"]["cells"]}
    previous = None
    for step in episode["steps"]:
        state, tick = step["state"], step["t"]
        kernel, cells = state["kernel"], state["notebook"]["cells"]
        assert [row["cell_id"] for row in cells] == order
        assert [row["table"] for row in state["data_sources"]] == tables
        assert state["rules"] == debugging_d.RULES
        assert [(row["team"], row["cover"]) for row in state["teams"]] == covers
        assert {row["status"] for row in state["teams"]} <= {"available", "away"}
        names = {row["team"] for row in state["teams"]}
        assert all(row["owner"] in names for row in state["data_sources"])
        for row in state["teams"]:  # every cover chain ends at an available team without a cycle
            seen, current = set(), row
            while current["status"] == "away":
                assert current["team"] not in seen and current["cover"] is not None
                seen.add(current["team"])
                current = team(state, current["cover"])
        assert kernel["memory_limit_mb"] == 4000 and 0 <= kernel["memory_mb"] < kernel["memory_limit_mb"]
        statuses = [row["status"] for row in cells]
        if kernel["status"] == "busy":
            assert statuses.count("running") == 1
            running = statuses.index("running")
            assert all(index > running for index, status in enumerate(statuses) if status == "queued")
        else:
            assert "running" not in statuses and "queued" not in statuses
        if kernel["status"] in ("idle", "busy"):
            assert kernel["heartbeat_at"] == tick
        for row in cells:
            assert row["budget_ticks"] == budgets[row["cell_id"]]
            assert (row["budget_ticks"] is None) == (row["kind"] == "markdown")
            assert (row["status"] == "error") == (row["error"] is not None)
            if row["error"] is not None:
                assert cell(state, row["error"]["raised_in_cell"])["kind"] == "code"
            if row["kind"] == "markdown":
                assert row["status"] == "never_run" and row["executed_at"] is None
                assert not row["depends_on"] and not row["reads"]
            assert row["cell_id"] not in _upstream_ids(state, row["cell_id"])
            assert set(row["reads"]) <= set(tables)
            assert all(cell(state, dep)["kind"] == "code" for dep in row["depends_on"])
        if previous is not None:
            assert state["comments"][:len(previous["comments"])] == previous["comments"]
            assert kernel["started_at"] >= previous["kernel"]["started_at"]
            for old, new in zip(previous["notebook"]["cells"], cells):
                assert new["edited_at"] >= old["edited_at"]
                if old["executed_at"] is not None:
                    assert new["executed_at"] >= old["executed_at"]
            for old, new in zip(previous["data_sources"], state["data_sources"]):
                assert new["loaded_at"] >= old["loaded_at"]
                assert new["source_updated_at"] >= old["source_updated_at"]
        previous = state


def test_story_is_internally_consistent(episode):
    final = episode["steps"][-1]["state"]
    # The units constant lives in the bottom cell that helpers depends on, and helpers uses it at top
    # level (outside the function body), so running helpers in a fresh kernel raises the NameError.
    assert "KNOTS_PER_MS =" in cell(final, "unit_table")["source"]
    assert "unit_table" in cell(final, "helpers")["depends_on"]
    for state in (at(episode, 0), final):
        top_level = [line for line in cell(state, "helpers")["source"].splitlines()
                     if line and not line.startswith((" ", "def "))]
        assert any("KNOTS_PER_MS" in line for line in top_level)
    order = [row["cell_id"] for row in final["notebook"]["cells"]]
    assert order.index("unit_table") > order.index("helpers")
    # Every table name a cell reads appears in its source.
    for row in final["notebook"]["cells"]:
        assert all(name in row["source"] for name in row["reads"])
    # The widening comment matches the edit, which was captured by the run it started; outputs computed
    # before it cover the earlier twelve-hour window (30 buoys, one frame a minute).
    first = at(episode, 0)
    assert first["comments"][0]["at"] == cell(first, "load_frames")["edited_at"] == -5
    assert "twelve hours" in first["comments"][0]["text"]
    assert cell(first, "load_frames")["executed_at"] == -5
    assert cell(first, "gusts")["output_rows"] == 30 * 12 * 60 and cell(first, "rollup")["output_rows"] == 30 * 12
    assert cell(at(episode, 12), "load_frames")["output_rows"] == 30 * 6 * 60
    assert "partition 12 of 24" in cell(at(episode, 7), "load_frames")["error"]["message"]  # half the day
    # The interrupted day-long load is narrowed before it is rerun.
    assert "hours=24" in cell(at(episode, 7), "load_frames")["source"]
    assert "hours=6" in cell(at(episode, 9), "load_frames")["source"]
    assert cell(at(episode, 7), "load_frames")["error"]["type"] == "KeyboardInterrupt"
    # Restart & Run All: a new kernel whose execution counts start again at 1, first cell at its start.
    restarted = at(episode, 35)
    assert restarted["kernel"]["started_at"] == 35
    assert cell(restarted, "setup")["execution_count"] == 1 and cell(restarted, "setup")["executed_at"] == 35
    # Dropping retired buoys shrinks the station list and everything built from it.
    assert "in_service" in cell(final, "stations")["source"]
    assert cell(final, "stations")["output_rows"] == cell(final, "summary")["output_rows"] == 27
    assert cell(final, "rollup")["output_rows"] == 27 * 6
    assert final["notebook"]["shared_at"] == 29
    assert "3600 / 1852" in cell(final, "unit_table")["source"]  # the tightened constant


# ---------------------------------------------------------------- key ticks of the story

KEY_TICKS = {
    0: {"next_action": "wait", "kernel_badge": "busy", "freshness_badge": "stale"},
    1: {"next_action": "wait", "kernel_badge": "overrun", "freshness_badge": "stale"},
    4: {"next_action": "wait", "kernel_badge": "overrun", "freshness_badge": "stale"},
    5: {"next_action": "interrupt_kernel", "kernel_badge": "overrun", "freshness_badge": "stale",
        "cell": "load_frames"},
    6: {"next_action": "interrupt_kernel", "kernel_badge": "overrun", "freshness_badge": "stale",
        "cell": "load_frames"},
    7: {"next_action": "fix_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "load_frames"},
    9: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "load_frames"},
    10: {"next_action": "wait", "kernel_badge": "busy", "freshness_badge": "stale"},
    13: {"next_action": "fix_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "helpers"},
    15: {"next_action": "fix_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "helpers"},
    16: {"next_action": "refresh_table", "kernel_badge": "idle", "freshness_badge": "broken", "table": FRAMES},
    18: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "load_frames"},
    22: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "stale", "cell": "rollup"},
    25: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "stale", "cell": "summary"},
    27: {"next_action": "share_results", "kernel_badge": "idle", "freshness_badge": "fresh"},
    28: {"next_action": "share_results", "kernel_badge": "idle", "freshness_badge": "fresh"},
    29: {"next_action": "wait", "kernel_badge": "idle", "freshness_badge": "fresh"},
    31: {"next_action": "restart_kernel", "kernel_badge": "busy", "freshness_badge": "fresh"},
    33: {"next_action": "restart_kernel", "kernel_badge": "dead", "freshness_badge": "stale"},
    34: {"next_action": "wait", "kernel_badge": "restarting", "freshness_badge": "stale"},
    35: {"next_action": "wait", "kernel_badge": "busy", "freshness_badge": "stale"},
    39: {"next_action": "wait", "kernel_badge": "busy", "freshness_badge": "stale"},
    40: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "unit_table"},
    42: {"next_action": "wait", "kernel_badge": "busy", "freshness_badge": "broken"},
    43: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "broken", "cell": "helpers"},
    48: {"next_action": "ask_data_owner", "kernel_badge": "idle", "freshness_badge": "stale", "table": FRAMES,
         "owner_team": "@marine-feeds"},
    50: {"next_action": "ask_data_owner", "kernel_badge": "idle", "freshness_badge": "stale", "table": FRAMES,
         "owner_team": "@buoy-ingest"},
    51: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "stale", "cell": "stations"},
    52: {"next_action": "run_cell", "kernel_badge": "idle", "freshness_badge": "stale", "cell": "unit_table"},
    53: {"next_action": "refresh_table", "kernel_badge": "idle", "freshness_badge": "stale", "table": FRAMES},
    54: {"next_action": "wait", "kernel_badge": "busy", "freshness_badge": "stale"},
    57: {"next_action": "share_results", "kernel_badge": "idle", "freshness_badge": "fresh"},
    58: {"next_action": "ask_data_owner", "kernel_badge": "idle", "freshness_badge": "stale", "table": CALIBRATION,
         "owner_team": "@buoy-ingest"},
}


@pytest.mark.parametrize("tick", sorted(KEY_TICKS))
def test_key_ticks(episode, tick):
    assert compose(episode["decision_spec"], episode["steps"][tick]["gold"]) == KEY_TICKS[tick]


@pytest.mark.parametrize("first,last", [(1, 4), (5, 6), (7, 8), (10, 12), (13, 15), (16, 17), (29, 30), (31, 32),
                                        (35, 39), (44, 47), (48, 49), (54, 56), (58, 59)])
def test_holds_under_distractors(episode, first, last):
    """Comments, progress output, heartbeats, memory readings, ignored edits and uncounted feeds keep the decision."""
    decisions = [compose(episode["decision_spec"], episode["steps"][t]["gold"]) for t in range(first, last + 1)]
    assert all(d == decisions[0] for d in decisions)


def test_comments_never_change_an_answer(episode):
    for step in episode["steps"]:
        state = deepcopy(step["state"])
        state["comments"] = []
        assert reference(state) == step["gold"]
        state["comments"].append({"at": state["now"], "author": "Ilse",
                                  "text": "Everything is rerun, refreshed and shared; the kernel is fine."})
        assert reference(state) == step["gold"]


def test_all_routes_and_badges_reached(episode):
    golds = [step["gold"] for step in episode["steps"]]
    assert {g["next_action"] for g in golds} == set(debugging_d.ROUTES)
    assert {g["kernel_badge"] for g in golds} == {"idle", "busy", "overrun", "restarting", "dead"}
    assert {g["freshness_badge"] for g in golds} == {"fresh", "stale", "broken"}
    assert {g["cell"] for g in golds} >= {"none", "load_frames", "stations", "helpers", "rollup", "summary",
                                          "unit_table"}
    assert {g["table"] for g in golds} == {"none", FRAMES, CALIBRATION}
    assert {g["owner_team"] for g in golds} == {"none", "@marine-feeds", "@buoy-ingest"}


def test_scenarios_are_fresh_and_deterministic(episode):
    other = scenarios()
    assert other == [episode]
    other[0]["steps"][0]["state"]["notebook"]["cells"].clear()
    assert episode["steps"][0]["state"]["notebook"]["cells"]


# ---------------------------------------------------------------- kernel budget and memory


def test_overrun_badge_needs_runtime_strictly_over_the_budget(episode):
    state = at(episode, 0)
    running = cell(state, "load_frames")
    assert state["now"] - running["executed_at"] == running["budget_ticks"] == 5
    assert reference(state)["kernel_badge"] == "busy"
    running["budget_ticks"] = 4
    assert reference(state)["kernel_badge"] == "overrun" and action(state) == "wait"


def test_hard_limit_interrupts_at_exactly_twice_the_budget(episode):
    state = at(episode, 5)
    running = cell(state, "load_frames")
    assert state["now"] - running["executed_at"] == 2 * running["budget_ticks"] == 10
    answer = reference(state)
    assert (answer["next_action"], answer["kernel_badge"], answer["cell"]) == ("interrupt_kernel", "overrun", "load_frames")
    running["executed_at"] += 1  # runtime 9
    assert (action(state), reference(state)["kernel_badge"]) == ("wait", "overrun")
    state = at(episode, 5)
    cell(state, "load_frames")["budget_ticks"] = 6  # a larger budget is only asked for in a comment
    assert (action(state), reference(state)["kernel_badge"]) == ("wait", "overrun")
    state = at(episode, 6)  # past the hard limit the card stays
    assert state["now"] - cell(state, "load_frames")["executed_at"] == 11 and action(state) == "interrupt_kernel"


def test_output_and_heartbeats_neither_extend_nor_reset_the_budget(episode):
    state = at(episode, 6)
    kernel = state["kernel"]
    assert kernel["last_output_at"] == kernel["heartbeat_at"] == state["now"]  # printing every tick
    kernel["last_output_at"] = None
    assert action(state) == "interrupt_kernel"
    kernel["last_output_at"] = cell(state, "load_frames")["executed_at"]
    assert action(state) == "interrupt_kernel"


def test_runtime_counts_from_the_running_cell_not_the_whole_run(episode):
    state = at(episode, 39)
    helpers = cell(state, "helpers")
    assert helpers["status"] == "running" and helpers["executed_at"] == 39
    assert state["now"] - state["kernel"]["since"] >= 2 * helpers["budget_ticks"]  # the run began at 35
    assert (action(state), reference(state)["kernel_badge"]) == ("wait", "busy")
    state["now"] = 43  # helpers itself at runtime 4 = twice its budget
    answer = reference(state)
    assert (answer["next_action"], answer["cell"]) == ("interrupt_kernel", "helpers")


def test_interrupt_names_a_running_scratch_cell(episode):
    state = at(episode, 32)
    state["kernel"]["memory_mb"] = 3000
    plot = cell(state, "explore_plot")
    plot["executed_at"] = state["now"] - 2 * plot["budget_ticks"]
    answer = reference(state)
    assert (answer["next_action"], answer["cell"], answer["freshness_badge"]) == ("interrupt_kernel", "explore_plot", "fresh")


def test_memory_restart_at_exactly_ninety_percent(episode):
    state = at(episode, 31)
    assert state["kernel"]["memory_mb"] == 3600
    assert action(state) == "restart_kernel"
    state["kernel"]["memory_mb"] = 3599
    assert action(state) == "wait"
    state = at(episode, 24)
    assert state["kernel"]["memory_mb"] == 3596 and action(state) == "wait"
    state["kernel"]["memory_mb"] = 3600
    assert action(state) == "restart_kernel"
    idle = at(episode, 30)
    idle["kernel"]["memory_mb"] = 3600
    assert action(idle) == "restart_kernel" and reference(idle)["freshness_badge"] == "fresh"
    overrun = at(episode, 3)
    overrun["kernel"]["memory_mb"] = 3600  # memory outranks the budget rule
    assert (action(overrun), reference(overrun)["kernel_badge"]) == ("restart_kernel", "overrun")


def test_dead_and_restarting_kernels(episode):
    dead = at(episode, 33)
    assert cell(dead, "summary")["status"] == "ok"
    assert reference(dead)["freshness_badge"] == "stale"  # nothing has run in a dead kernel
    dead["kernel"]["memory_mb"] = 3900
    assert action(dead) == "restart_kernel"
    restarting = at(episode, 34)
    restarting["kernel"]["memory_mb"] = 3900
    assert (action(restarting), reference(restarting)["kernel_badge"]) == ("wait", "restarting")


def test_a_cell_started_at_the_kernel_start_tick_has_run_in_it(episode):
    state = at(episode, 40)
    assert cell(state, "setup")["executed_at"] == state["kernel"]["started_at"] == 35
    assert reference(state)["cell"] == "unit_table"
    state["kernel"]["started_at"] = 36  # setup and load_frames would be leftovers of an earlier kernel
    answer = reference(state)
    assert (answer["next_action"], answer["cell"]) == ("run_cell", "setup")


def test_results_from_an_earlier_kernel_count_as_never_run(episode):
    state = at(episode, 40)
    assert cell(state, "unit_table")["executed_at"] < state["kernel"]["started_at"]
    assert (action(state), reference(state)["cell"]) == ("run_cell", "unit_table")
    cell(state, "unit_table")["executed_at"] = state["kernel"]["started_at"]  # as if run in this kernel
    assert (action(state), reference(state)["cell"]) == ("fix_cell", "helpers")


# ---------------------------------------------------------------- failures, edits and runs


def test_fix_targets_the_cell_that_raised_the_error(episode):
    state = at(episode, 13)
    assert cell(state, "gusts")["status"] == "error"
    assert reference(state)["cell"] == "helpers"
    cell(state, "gusts")["error"]["raised_in_cell"] = "gusts"
    assert reference(state)["cell"] == "gusts"


def test_edit_in_the_same_tick_as_the_run_start_belongs_to_that_run(episode):
    state = at(episode, 7)
    load = cell(state, "load_frames")
    assert load["edited_at"] == load["executed_at"] == -5
    assert (action(state), reference(state)["cell"]) == ("fix_cell", "load_frames")
    load["edited_at"] = -4
    assert (action(state), reference(state)["cell"]) == ("run_cell", "load_frames")


def test_interrupted_cell_needs_a_fix_until_it_is_edited(episode):
    assert (action(at(episode, 8)), reference(at(episode, 8))["cell"]) == ("fix_cell", "load_frames")
    state = at(episode, 9)
    assert (action(state), reference(state)["cell"]) == ("run_cell", "load_frames")


def test_editing_the_failing_cell_asks_for_a_rerun_not_a_fix(episode):
    state = at(episode, 14)
    cell(state, "gusts")["edited_at"] = 14
    answer = reference(state)
    assert (answer["next_action"], answer["cell"], answer["freshness_badge"]) == ("run_cell", "gusts", "broken")
    cell(state, "gusts")["edited_at"] = cell(state, "gusts")["executed_at"]  # same tick: included in that run
    assert reference(state)["cell"] == "helpers" and action(state) == "fix_cell"


def test_raised_in_edit_closes_the_failure_only_when_strictly_later(episode):
    state = at(episode, 16)
    assert action(state) == "refresh_table"
    cell(state, "helpers")["edited_at"] = cell(state, "gusts")["executed_at"]
    assert (action(state), reference(state)["cell"]) == ("fix_cell", "helpers")


def test_an_edited_cell_needs_a_run_ahead_of_an_overdue_feed(episode):
    state = at(episode, 51)
    stations = cell(state, "stations")
    assert stations["edited_at"] == 51 > stations["executed_at"]
    assert (action(state), reference(state)["cell"]) == ("run_cell", "stations")
    stations["edited_at"] = stations["executed_at"]
    answer = reference(state)
    assert (answer["next_action"], answer["table"], answer["owner_team"]) == ("ask_data_owner", FRAMES, "@buoy-ingest")


def test_open_failure_outranks_a_behind_table_and_refresh_outranks_runs(episode):
    state = at(episode, 15)
    assert table(state, FRAMES)["source_updated_at"] > table(state, FRAMES)["loaded_at"]
    assert action(state) == "fix_cell"
    state = at(episode, 16)
    table(state, FRAMES)["loaded_at"] = 15  # same tick as the source update: not behind
    answer = reference(state)
    assert (answer["next_action"], answer["cell"]) == ("run_cell", "load_frames")
    table(state, FRAMES)["loaded_at"] = 14
    assert reference(state)["table"] == FRAMES
    state = at(episode, 53)
    assert cell(state, "unit_table")["edited_at"] > cell(state, "unit_table")["executed_at"]
    assert (action(state), reference(state)["table"]) == ("refresh_table", FRAMES)
    table(state, FRAMES)["source_updated_at"] = table(state, FRAMES)["loaded_at"]  # not behind, still overdue
    assert (action(state), reference(state)["cell"]) == ("run_cell", "unit_table")


def test_snapshot_loaded_at_the_source_update_tick_is_not_behind(episode):
    state = at(episode, 9)
    frames = table(state, FRAMES)
    assert frames["loaded_at"] == frames["source_updated_at"] == -7
    assert action(state) == "run_cell"
    frames["source_updated_at"] = -6
    assert (action(state), reference(state)["table"]) == ("refresh_table", FRAMES)


def test_staleness_through_upstream_runs_is_strict(episode):
    state = at(episode, 29)
    assert action(state) == "wait"
    cell(state, "load_frames")["executed_at"] = cell(state, "gusts")["executed_at"]
    assert action(state) == "wait"  # equal ticks never make gusts outdated
    cell(state, "load_frames")["executed_at"] += 1
    assert (action(state), reference(state)["cell"]) == ("run_cell", "gusts")


def test_runnable_needs_every_transitive_upstream_cell_current(episode):
    # Gold at 52: rollup needs a run and both of its direct dependencies are current, but unit_table
    # (rollup -> gusts -> helpers -> unit_table) was edited, so the bottom cell is the first runnable one.
    state = at(episode, 52)
    rollup = cell(state, "rollup")
    assert rollup["executed_at"] < cell(state, "stations")["executed_at"] == 52
    assert "unit_table" not in rollup["depends_on"] and "unit_table" in _upstream_ids(state, "rollup")
    assert cell(state, "unit_table")["edited_at"] == 52 > cell(state, "unit_table")["executed_at"]
    assert (action(state), reference(state)["cell"]) == ("run_cell", "unit_table")
    assert "run rollup first" in state["comments"][-1]["text"]
    cell(state, "unit_table")["edited_at"] = cell(state, "unit_table")["executed_at"]
    assert (action(state), reference(state)["cell"]) == ("run_cell", "rollup")
    # The same at 48, where unit_table sits two hops below rollup: a direct-only reading would pick rollup.
    state = at(episode, 48)
    cell(state, "unit_table")["edited_at"] = cell(state, "rollup")["edited_at"] = 48
    assert (action(state), reference(state)["cell"]) == ("run_cell", "unit_table")


def test_scratch_cells_never_count_as_dependencies(episode):
    state = at(episode, 30)
    assert action(state) == "wait"
    cell(state, "summary")["depends_on"].append("explore_plot")
    cell(state, "explore_plot")["executed_at"] = 30  # later than summary's 29, but untracked
    assert cell(state, "explore_plot")["executed_at"] > cell(state, "summary")["executed_at"]
    assert action(state) == "wait" and reference(state)["freshness_badge"] == "fresh"
    cell(state, "summary")["executed_at"] = 28  # a tracked upstream (rollup, 23) still does not outdate it
    assert action(state) == "wait"
    cell(state, "rollup")["executed_at"] = 29
    assert (action(state), reference(state)["cell"]) == ("run_cell", "summary")


def test_cells_started_in_the_same_tick_do_not_outdate_each_other(episode):
    state = at(episode, 48)
    assert cell(state, "setup")["executed_at"] == cell(state, "load_frames")["executed_at"] == 35
    assert action(state) == "ask_data_owner"
    cell(state, "setup")["executed_at"] = 36
    assert (action(state), reference(state)["cell"]) == ("run_cell", "load_frames")


def test_table_loaded_after_a_run_outdates_its_readers_strictly(episode):
    state = at(episode, 57)
    assert table(state, FRAMES)["loaded_at"] == cell(state, "load_frames")["executed_at"] == 54
    assert action(state) == "share_results"
    table(state, FRAMES)["loaded_at"] += 1
    assert (action(state), reference(state)["cell"]) == ("run_cell", "load_frames")
    state = at(episode, 18)
    assert table(state, FRAMES)["loaded_at"] > cell(state, "load_frames")["executed_at"]
    started = cell(state, "load_frames")["executed_at"]
    table(state, FRAMES).update(loaded_at=started, source_updated_at=started)
    assert reference(state)["cell"] == "helpers"  # without the refresh only the helpers edit remains


def test_run_selection_skips_cells_with_upstream_not_current(episode):
    state = at(episode, 40)
    helpers = cell(state, "helpers")
    assert helpers["status"] == "error" and helpers["error"]["type"] == "NameError"
    assert reference(state)["cell"] == "unit_table"  # helpers needs a run first but is blocked
    helpers["depends_on"].remove("unit_table")  # without the dependency the NameError is an open failure
    assert (action(state), reference(state)["cell"]) == ("fix_cell", "helpers")


def test_scratch_and_markdown_cells_are_untracked(episode):
    state = at(episode, 25)
    assert cell(state, "explore_plot")["status"] == "error"
    assert (reference(state)["freshness_badge"], reference(state)["cell"]) == ("stale", "summary")
    cell(state, "explore_plot")["tags"] = []
    answer = reference(state)
    assert (answer["next_action"], answer["cell"], answer["freshness_badge"]) == ("fix_cell", "explore_plot", "broken")
    state = at(episode, 49)
    assert cell(state, "notes")["edited_at"] == 49
    assert reference(state) == episode["steps"][48]["gold"]


# ---------------------------------------------------------------- tables, teams and sharing


def test_tables_read_only_by_scratch_cells_are_ignored(episode):
    state = at(episode, 57)
    tides = table(state, TIDES)
    assert tides["source_updated_at"] > tides["loaded_at"]
    assert state["now"] - tides["source_updated_at"] > tides["update_every"]
    assert reference(state)["freshness_badge"] == "fresh" and action(state) == "share_results"
    cell(state, "summary")["reads"].append(TIDES)
    answer = reference(state)
    assert (answer["next_action"], answer["table"], answer["freshness_badge"]) == ("refresh_table", TIDES, "stale")


def test_overdue_is_strictly_more_than_update_every(episode):
    state = at(episode, 57)
    calibration = table(state, CALIBRATION)
    assert state["now"] - calibration["source_updated_at"] == calibration["update_every"] == 100
    assert action(state) == "share_results"
    calibration["source_updated_at"] -= 1
    answer = reference(state)
    assert (answer["next_action"], answer["table"], answer["owner_team"]) == (
        "ask_data_owner", CALIBRATION, "@buoy-ingest")
    state = at(episode, 58)
    table(state, CALIBRATION)["source_updated_at"] += 1
    assert action(state) == "share_results"


def test_ask_names_the_first_overdue_table_in_data_sources_order(episode):
    state = at(episode, 58)
    table(state, FRAMES)["source_updated_at"] = 20
    table(state, FRAMES)["loaded_at"] = 20
    for name in ("load_frames", "gusts", "rollup", "summary"):
        assert cell(state, name)["executed_at"] > 20
    answer = reference(state)
    assert (answer["table"], answer["owner_team"]) == (FRAMES, "@buoy-ingest")
    team(state, "@marine-feeds")["status"] = "available"
    assert reference(state)["owner_team"] == "@marine-feeds"


def test_cover_of_an_available_owner_is_never_used(episode):
    state = at(episode, 48)
    owner = team(state, "@marine-feeds")
    assert owner["status"] == "available" and owner["cover"] == "@buoy-ingest"
    assert reference(state)["owner_team"] == "@marine-feeds"
    state = at(episode, 49)
    assert "@buoy-ingest" in state["comments"][-1]["text"]  # a claim that the team is off shift
    assert reference(state)["owner_team"] == "@marine-feeds"
    owner = team(state, "@marine-feeds")
    owner["status"] = "away"
    assert reference(state)["owner_team"] == "@buoy-ingest"


def test_cover_chain_is_followed_until_an_available_team(episode):
    state = at(episode, 58)
    assert team(state, "@sensor-lab")["status"] == team(state, "@marine-feeds")["status"] == "away"
    assert reference(state)["owner_team"] == "@buoy-ingest"  # two hops: sensor-lab -> marine-feeds -> buoy-ingest
    team(state, "@buoy-ingest")["status"] = "away"
    assert reference(state)["owner_team"] == "@data-platform"
    team(state, "@sensor-lab")["status"] = "available"
    assert reference(state)["owner_team"] == "@sensor-lab"
    broken = at(episode, 58)
    team(broken, "@buoy-ingest").update(status="away", cover="@sensor-lab")
    with pytest.raises(ValueError):
        reference(broken)


def test_sharing_is_recorded_only_by_shared_at_and_compared_strictly(episode):
    state = at(episode, 28)
    assert state["comments"][-1]["at"] == 28 and state["notebook"]["shared_at"] is None
    assert action(state) == "share_results"
    state = at(episode, 29)  # summary was rerun within the share tick
    assert state["notebook"]["shared_at"] == cell(state, "summary")["executed_at"] == 29
    assert action(state) == "wait"  # an execution at the share tick is not later than the share
    state["notebook"]["shared_at"] = 28
    assert action(state) == "share_results"
    state = at(episode, 57)
    state["notebook"]["shared_at"] = max(row["executed_at"] for row in state["notebook"]["cells"]
                                         if debugging_d._tracked(row))
    assert action(state) == "wait"
