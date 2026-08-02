"""Evaluate a trained agent (not yet implemented)."""

import argparse
import sys
from typing import Any

_parser: argparse.ArgumentParser | None = None


def add_arguments(subparsers: Any) -> None:
    """Register the `eval` subcommand."""
    global _parser
    parser = subparsers.add_parser("eval", help="Evaluate trained agent")
    parser.add_argument("--evaluate", action="store_true")
    _parser = parser


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    if not args.evaluate:
        assert _parser is not None
        _parser.print_help()
        sys.exit(0)
    print("Evaluation not yet implemented")
