"""Training scenarios: further variants of the four task families, kept out of the evaluation build.

Each module defines one 60-tick scenario of an existing family and its own
public-state ``reference``. Modules may reuse a family's published rules and
helpers, but no evaluation scenario's instance content (names, identifiers,
utterances, decks, logs or states); ``audit.leakage`` enforces this.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

MODULES = [
    "debugging_c", "debugging_d",
    "assembly_c", "assembly_d",
    "support_c", "support_d",
    "presenter_c", "presenter_d",
]


def modules() -> list[ModuleType]:
    """The training modules in build order; each exports ``scenarios()`` and ``reference(state)``."""
    return [import_module(f"{__name__}.{name}") for name in MODULES]
