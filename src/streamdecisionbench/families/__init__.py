"""Scenario registry: ten task families, two base scenarios each."""

from __future__ import annotations

import importlib
from typing import Iterable

from streamdecisionbench.authoring import Scenario
from streamdecisionbench.schema import TASK_FAMILIES


def load_scenarios(families: Iterable[str] | None = None, strict: bool = False) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for family in families or TASK_FAMILIES:
        try:
            module = importlib.import_module(f"streamdecisionbench.families.{family}")
        except ModuleNotFoundError as error:
            if strict or error.name != f"streamdecisionbench.families.{family}":
                raise
            continue
        for cls in module.SCENARIOS:
            scenarios.append(cls())
    return scenarios
