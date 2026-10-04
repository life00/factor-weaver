"""factor-weaver CLI: subcommand dispatch and logging setup."""

import argparse
import logging
from importlib.metadata import version

from factor_weaver import config
from factor_weaver.workflows import data, evaluate, train


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="factor-weaver")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('factor-weaver')}"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(required=True)
    for workflow in (data, train, evaluate):
        workflow.add_arguments(sub)
    for workflow_parser in sub.choices.values():
        workflow_parser.add_argument(
            "-v", "--verbose", action="store_true", default=argparse.SUPPRESS
        )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = config.load(*getattr(args, "configs", ("data",)))
    args.func(cfg, args)


if __name__ == "__main__":
    main()
