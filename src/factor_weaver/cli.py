"""factor-weaver CLI: two-level dispatch with dependency resolution."""

import argparse
import sys
from pathlib import Path

import yaml

from factor_weaver.data import (
    align,
    behavior,
    edgar,
    parse_fundamentals,
    prices,
    split,
    technicals,
    universe,
)

_DATA_STEPS = [
    ("parse-fundamentals", parse_fundamentals.parse_fundamentals),
    ("universe", universe.build_universe),
    ("edgar-filing-dates", edgar.fetch_filing_dates),
    ("fetch-prices", prices.fetch_prices),
    ("compute-technicals", technicals.compute_technicals),
    ("load-behavior", behavior.load_behavior),
    ("align", align.align_dataset),
    ("split", split.split_dataset),
]

_DEPS: dict[str, set[str]] = {
    "universe": {"parse-fundamentals"},
    "edgar-filing-dates": {"universe"},
    "fetch-prices": {"universe"},
    "compute-technicals": {"fetch-prices"},
    "align": {
        "parse-fundamentals",
        "edgar-filing-dates",
        "fetch-prices",
        "compute-technicals",
        "load-behavior",
    },
    "split": {"align"},
}


def _resolve(steps: set[str]) -> list[str]:
    all_steps = set(steps)
    changed = True
    while changed:
        changed = False
        for s in list(all_steps):
            for d in _DEPS.get(s, ()):
                if d not in all_steps:
                    all_steps.add(d)
                    changed = True

    result: list[str] = []
    remaining = set(all_steps)
    while remaining:
        batch = {s for s in remaining if _DEPS.get(s, set()).issubset(result)}
        result.extend(sorted(batch))
        remaining -= batch
    return result


def _load_config() -> dict:
    path = Path("config/data.yaml")
    if path.exists():
        with open(path) as f:
            return dict(yaml.safe_load(f) or {})
    return {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factor-weaver")
    sub = parser.add_subparsers(dest="module", required=True, metavar="{data,rl,eval}")

    data_p = sub.add_parser("data", help="Data pipeline steps")
    for name, _ in _DATA_STEPS:
        data_p.add_argument(f"--{name}", action="store_true", help=f"Run {name}")

    rl_p = sub.add_parser("rl", help="RL training")
    rl_p.add_argument("--train", action="store_true")

    eval_p = sub.add_parser("eval", help="Evaluate trained agent")
    eval_p.add_argument("--evaluate", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.module == "data":
        selected = {name for name, _ in _DATA_STEPS if getattr(args, name.replace("-", "_"))}
        if not selected:
            parser.parse_args(["data", "--help"])
        cfg = _load_config()
        step_map = dict(_DATA_STEPS)
        for name in _resolve(selected):
            step_map[name](cfg)
    elif args.module == "rl":
        if args.train:
            print("RL training not yet implemented")
        else:
            parser.parse_args(["rl", "--help"])
    elif args.module == "eval":
        if args.evaluate:
            print("Evaluation not yet implemented")
        else:
            parser.parse_args(["eval", "--help"])
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
