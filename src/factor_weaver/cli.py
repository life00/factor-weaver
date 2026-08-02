"""factor-weaver CLI: two-level dispatch to workflows."""

import argparse
from pathlib import Path
from typing import Any

import yaml

from factor_weaver.workflows import build_dataset, evaluate, train

_WORKFLOWS: dict[str, Any] = {
    "data": build_dataset,
    "rl": train,
    "eval": evaluate,
}


def _load_config() -> dict[str, Any]:
    path = Path("config/data.yaml")
    if path.exists():
        with open(path) as f:
            return dict(yaml.safe_load(f) or {})
    return {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factor-weaver")
    sub = parser.add_subparsers(dest="module", required=True)
    for workflow in _WORKFLOWS.values():
        workflow.add_arguments(sub)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _WORKFLOWS[args.module].run(_load_config(), args)


if __name__ == "__main__":
    main()
