"""Build the aligned dataset: parse raw sources, build universe, align features."""

import argparse
import sys
from typing import Any

from factor_weaver.data import (
    align,
    behavior,
    edgar,
    financialdatadb,
    prices,
    split,
    technicals,
    universe,
)
from factor_weaver.workflows import Step, run_steps

DATA_STEPS: list[tuple[str, Step]] = [
    ("parse-fundamentals", financialdatadb.parse_fundamentals),
    ("parse-companies", financialdatadb.parse_companies),
    ("universe", universe.build_universe),
    ("edgar-filing-dates", edgar.fetch_filing_dates),
    ("fetch-prices", prices.fetch_prices),
    ("compute-technicals", technicals.compute_technicals),
    ("load-behavior", behavior.load_behavior),
    ("align", align.align_dataset),
    ("split", split.split_dataset),
]

DEPS: dict[str, set[str]] = {
    "universe": {"parse-fundamentals", "parse-companies"},
    "edgar-filing-dates": {"universe"},
    "fetch-prices": {"universe"},
    "compute-technicals": {"fetch-prices"},
    "align": {
        "parse-fundamentals",
        "parse-companies",
        "edgar-filing-dates",
        "fetch-prices",
        "compute-technicals",
        "load-behavior",
    },
    "split": {"align"},
}

_parser: argparse.ArgumentParser | None = None


def add_arguments(subparsers: Any) -> None:
    """Register the `data` subcommand, one --flag per pipeline step."""
    global _parser
    parser = subparsers.add_parser("data", help="Data pipeline steps")
    for name, _ in DATA_STEPS:
        parser.add_argument(f"--{name}", action="store_true", help=f"Run {name}")
    _parser = parser


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    """Execute the steps selected via --flags, resolving dependencies."""
    selected = {name for name, _ in DATA_STEPS if getattr(args, name.replace("-", "_"))}
    if not selected:
        assert _parser is not None
        _parser.print_help()
        sys.exit(0)
    run_steps(cfg, DATA_STEPS, DEPS, selected)
