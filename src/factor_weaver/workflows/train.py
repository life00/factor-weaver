"""Training workflow: `factor-weaver train [MODEL]`."""

import argparse
from typing import Any

from factor_weaver import models


def add_arguments(sub: Any) -> None:
    parser = sub.add_parser("train", help="Train a registered model (default: rl)")
    parser.add_argument("model", nargs="?", default="rl", metavar="MODEL", help="model to train")
    parser.add_argument("--resume", metavar="PATH", help="resume from a checkpoint")
    parser.add_argument("--seed", type=int, help="override the configured seed")
    parser.set_defaults(func=run, configs=("data", "eval", "models"))


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    if args.model not in models.TRAINERS:
        available = ", ".join(models.TRAINERS)
        raise SystemExit(f"'{args.model}' is not trainable; available: {available}")
    models.TRAINERS[args.model](cfg, args)
