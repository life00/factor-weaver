"""Workflow orchestration: shared machinery for CLI-dispatched step pipelines."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

Step = Callable[[dict[str, Any]], None]


def resolve(steps: set[str], deps: Mapping[str, set[str]]) -> list[str]:
    """Order selected steps so every dependency runs first."""
    all_steps = set(steps)
    changed = True
    while changed:
        changed = False
        for s in list(all_steps):
            for d in deps.get(s, ()):
                if d not in all_steps:
                    all_steps.add(d)
                    changed = True

    result: list[str] = []
    remaining = set(all_steps)
    while remaining:
        batch = {s for s in remaining if deps.get(s, set()).issubset(result)}
        result.extend(sorted(batch))
        remaining -= batch
    return result


def run_steps(
    cfg: dict[str, Any],
    steps: Sequence[tuple[str, Step]],
    deps: Mapping[str, set[str]],
    selected: set[str],
) -> None:
    """Run the selected steps in dependency order."""
    step_map = dict(steps)
    for name in resolve(selected, deps):
        step_map[name](cfg)
