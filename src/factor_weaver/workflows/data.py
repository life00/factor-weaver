"""Data workflow: `factor-weaver data [fetch|build] [steps ...]`."""

import argparse
from typing import Any

from factor_weaver.data import pipeline


def add_arguments(sub: Any) -> None:
    parser = sub.add_parser("data", help="Run the data pipeline (fetch then build)")
    parser.add_argument(
        "steps",
        nargs="*",
        metavar="[fetch|build] [step ...]",
        help="optionally restrict to a phase and/or step names (default: all steps)",
    )
    parser.add_argument("--list", action="store_true", help="list steps and exit")
    parser.add_argument(
        "--refresh", action="store_true", help="refetch data that is already cached"
    )
    parser.set_defaults(func=run, configs=("data",))


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    phase: str | None = None
    steps = list(args.steps)
    if steps and steps[0] in pipeline.PHASES:
        phase, steps = steps[0], steps[1:]
    if args.list:
        pipeline.print_status(cfg, phase)
        return
    pipeline.run(cfg, steps, phase, refresh=args.refresh)
