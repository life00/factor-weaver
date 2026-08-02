"""Build the aligned dataset: parse raw sources, build universe, align features."""

import argparse
from collections.abc import Callable
from typing import Any

from factor_weaver.data import (
    align,
    behavior,
    edgar,
    financialdatadb,
    lseg,
    prices,
    split,
    technicals,
    universe,
)

# Insertion order == run order (already topologically sorted).
STEPS: dict[str, Callable[[dict[str, Any]], None]] = {
    "parse-fundamentals": financialdatadb.parse_fundamentals,
    "parse-companies": financialdatadb.parse_companies,
    "lseg-constituents": lseg.fetch_constituents,
    "lseg-joiners-leavers": lseg.fetch_joiners_leavers,
    "lseg-mapping": lseg.fetch_mapping,
    "universe": universe.build_universe,
    "edgar-filing-dates": edgar.fetch_filing_dates,
    "fetch-prices": prices.fetch_prices,
    "compute-technicals": technicals.compute_technicals,
    "load-behavior": behavior.load_behavior,
    "align": align.align_dataset,
    "split": split.split_dataset,
}


def add_arguments(sub: Any) -> None:
    parser = sub.add_parser("data", help="Run the data pipeline")
    parser.add_argument(
        "steps",
        nargs="*",
        choices=list(STEPS),
        help="steps to run, in order (empty = all)",
    )
    parser.set_defaults(func=run)


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    for name in args.steps or STEPS:
        print(f"[data] {name}")
        STEPS[name](cfg)
