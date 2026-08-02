"""Train the RL agent (not yet implemented)."""

import argparse
import sys
from typing import Any

_parser: argparse.ArgumentParser | None = None


def add_arguments(subparsers: Any) -> None:
    """Register the `rl` subcommand."""
    global _parser
    parser = subparsers.add_parser("rl", help="RL training")
    parser.add_argument("--train", action="store_true")
    _parser = parser


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    if not args.train:
        assert _parser is not None
        _parser.print_help()
        sys.exit(0)
    print("RL training not yet implemented")
