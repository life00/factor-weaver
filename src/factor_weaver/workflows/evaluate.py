"""Evaluation workflow: `factor-weaver eval [MODEL ...]` through the shared engine."""

import argparse
import logging
from typing import Any

from factor_weaver import models

log = logging.getLogger(__name__)


def add_arguments(sub: Any) -> None:
    parser = sub.add_parser("eval", help="Evaluate models through the shared backtest engine")
    parser.add_argument(
        "models", nargs="*", metavar="MODEL", help="models to evaluate (default: all registered)"
    )
    parser.add_argument("--start", metavar="DATE", help="override eval.yaml window.start")
    parser.add_argument("--end", metavar="DATE", help="override eval.yaml window.end")
    parser.add_argument("--checkpoint", metavar="PATH", help="RL checkpoint override")
    parser.set_defaults(func=run, configs=("data", "eval", "models"))


def select(args: argparse.Namespace) -> list[str]:
    """Selected model names (all registered by default), validated against the registry."""
    names = args.models or list(models.REGISTRY)
    unknown = [n for n in names if n not in models.REGISTRY]
    if unknown:
        available = ", ".join(models.REGISTRY)
        raise SystemExit(f"unknown model '{unknown[0]}'; available: {available}")
    return names


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    if args.checkpoint:
        cfg.setdefault("rl", {})["checkpoint"] = args.checkpoint
    window = cfg.setdefault("window", {})
    if args.start:
        window["start"] = args.start
    if args.end:
        window["end"] = args.end
    for name in select(args):
        if name == "rl" and not (cfg.get("rl") or {}).get("checkpoint"):
            if args.models:
                raise SystemExit("rl needs a checkpoint; train it or pass --checkpoint")
            log.warning("skipping rl: no checkpoint configured (train it or pass --checkpoint)")
            continue
        log.warning("evaluation not yet implemented (PLAN.md Phase 1): %s", name)
