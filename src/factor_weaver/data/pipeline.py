"""Ordered data-step manifest and dependency-aware runner.

Each step declares the config keys it reads and writes. `select` pulls in the
producers of missing inputs transitively; `run` executes the result in manifest
order. Fetch steps whose outputs all exist are skipped unless `refresh`; steps
with per-item caches (prices) always run so new items get fetched, and honour
`refresh` through the private `_refresh` config key.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from rich.text import Text

from factor_weaver.data.build import panel, split, technicals, universe
from factor_weaver.data.build import prices as build_prices
from factor_weaver.data.fetch import lseg
from factor_weaver.data.fetch import prices as fetch_prices
from factor_weaver.output import out

log = logging.getLogger(__name__)

Phase = Literal["fetch", "build"]
PHASES: tuple[Phase, ...] = ("fetch", "build")


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[dict[str, Any]], None]
    phase: Phase
    ins: tuple[str, ...] = ()
    outs: tuple[str, ...] = ()
    per_item: bool = False  # outs is a cache directory; always run to fill gaps


STEPS: tuple[Step, ...] = (
    Step(
        "lseg-constituents",
        lseg.fetch_constituents,
        "fetch",
        outs=("lseg.constituents_out",),
    ),
    Step(
        "lseg-joiners-leavers",
        lseg.fetch_joiners_leavers,
        "fetch",
        outs=("lseg.joiners_leavers_out",),
    ),
    Step(
        "lseg-mapping",
        lseg.fetch_mapping,
        "fetch",
        ins=("lseg.constituents_out", "lseg.joiners_leavers_out"),
        outs=("lseg.mapping_out",),
    ),
    Step(
        "lseg-market-cap",
        lseg.fetch_market_cap,
        "fetch",
        ins=("lseg.constituents_out", "lseg.joiners_leavers_out"),
        outs=("lseg.market_cap_out",),
    ),
    Step(
        "universe",
        universe.build_universe,
        "build",
        ins=(
            "lseg.constituents_out",
            "lseg.joiners_leavers_out",
            "lseg.mapping_out",
            "lseg.market_cap_out",
        ),
        outs=("universe.universe_out", "universe.assets_out"),
    ),
    Step(
        "lseg-prices",
        fetch_prices.fetch_lseg_prices,
        "fetch",
        ins=("universe.assets_out",),
        outs=("lseg.prices_out",),
        per_item=True,
    ),
    Step(
        "yahoo-prices",
        fetch_prices.fetch_yahoo_prices,
        "fetch",
        ins=("universe.assets_out", "lseg.prices_out"),
        outs=("yahoo.prices_out",),
        per_item=True,
    ),
    Step(
        "prices",
        build_prices.build_prices,
        "build",
        ins=("universe.assets_out", "lseg.prices_out", "yahoo.prices_out"),
        outs=("prices.out", "yahoo.extra_prices_out"),
    ),
    Step(
        "technicals",
        technicals.compute_technicals,
        "build",
        ins=("prices.out",),
        outs=("technicals.out",),
    ),
    Step(
        "panel",
        panel.build_panel,
        "build",
        ins=("prices.out", "technicals.out"),
        outs=("panel.out",),
    ),
    Step(
        "split",
        split.split_dataset,
        "build",
        ins=("panel.out",),
        outs=("split.train_out", "split.test_out"),
    ),
)


def _path(cfg: dict[str, Any], key: str) -> Path:
    """Resolve a dotted config key to a path."""
    value: Any = cfg
    for part in key.split("."):
        value = value[part]
    return Path(value)


def _exists(cfg: dict[str, Any], key: str) -> bool:
    try:
        return _path(cfg, key).exists()
    except (KeyError, TypeError):
        return False


def select(
    cfg: dict[str, Any], only: tuple[str, ...] | list[str] = (), phase: str | None = None
) -> list[Step]:
    """Manifest-ordered steps to run, including producers of missing inputs."""
    pool = [s for s in STEPS if phase is None or s.phase == phase]
    unknown = [n for n in only if n not in {s.name for s in pool}]
    if unknown:
        available = ", ".join(s.name for s in pool)
        raise SystemExit(
            f"unknown {phase or 'pipeline'} step '{unknown[0]}'; available: {available}"
        )
    selected = {s.name: s for s in pool if not only or s.name in only}
    while True:
        missing = {k for s in selected.values() for k in s.ins if not _exists(cfg, k)}
        produced = {k for s in selected.values() for k in s.outs}
        pending = missing - produced
        if not pending:
            break
        producer = next(
            (s for s in STEPS if s.name not in selected and set(s.outs) & pending), None
        )
        if producer is None:
            raise SystemExit(f"missing inputs with no producing step: {', '.join(sorted(pending))}")
        log.info("+ %s (required by selected steps)", producer.name)
        selected[producer.name] = producer
    return [s for s in STEPS if s.name in selected]


def run(
    cfg: dict[str, Any],
    only: tuple[str, ...] | list[str] = (),
    phase: str | None = None,
    refresh: bool = False,
) -> list[str]:
    """Execute selected steps in manifest order; returns the executed step names."""
    steps = select(cfg, only, phase)
    cfg["_refresh"] = refresh
    executed: list[str] = []
    try:
        for step in steps:
            if (
                step.phase == "fetch"
                and not refresh
                and not step.per_item
                and all(_exists(cfg, k) for k in step.outs)
            ):
                log.info("step %s (%s): cached, skipped", step.name, step.phase)
                continue
            log.info("step %s (%s) start", step.name, step.phase)
            start = time.monotonic()
            step.run(cfg)
            log.info("step %s done in %.1fs", step.name, time.monotonic() - start)
            executed.append(step.name)
    finally:
        cfg.pop("_refresh", None)
    return executed


def print_status(cfg: dict[str, Any], phase: str | None = None) -> None:
    """Print each step's phase, outputs and whether the outputs exist."""
    for step in STEPS:
        if phase is not None and step.phase != phase:
            continue
        exists = all(_exists(cfg, k) for k in step.outs)
        paths = ", ".join(str(_path(cfg, k)) for k in step.outs)
        line = Text()
        line.append("ok" if exists else "--", style="green" if exists else "red")
        line.append(f" {step.name:<20} ")
        line.append(f"{step.phase:<5}", style="cyan")
        line.append(f" {paths}", style="dim")
        out.print(line)
