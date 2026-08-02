"""factor-weaver CLI: two-level dispatch to workflows."""

import argparse
from pathlib import Path
from typing import Any

import yaml

from factor_weaver.workflows import build_dataset, evaluate, train


def _load_config() -> dict[str, Any]:
    path = Path("config/data.yaml")
    if not path.is_file():
        return {}
    with open(path) as f:
        return dict(yaml.safe_load(f) or {})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="factor-weaver")
    sub = parser.add_subparsers(required=True)
    for workflow in (build_dataset, train, evaluate):
        workflow.add_arguments(sub)
    args = parser.parse_args(argv)
    args.func(_load_config(), args)


if __name__ == "__main__":
    main()
