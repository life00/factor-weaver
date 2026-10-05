"""factor-weaver CLI: subcommand dispatch and logging setup."""

import argparse
import logging
import sys
from importlib.metadata import version
from typing import Any, NoReturn

from rich.logging import RichHandler
from rich.text import Text
from rich.traceback import install
from rich_argparse import RichHelpFormatter

from factor_weaver import config
from factor_weaver.output import err, out
from factor_weaver.workflows import data, evaluate, report, train


class _Parser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", RichHelpFormatter)
        super().__init__(*args, **kwargs)

    def _get_formatter(self) -> argparse.HelpFormatter:
        return RichHelpFormatter(prog=self.prog, console=out)

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        err.print(Text.assemble((f"{self.prog}: error: ", "red"), message), soft_wrap=True)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    parser = _Parser(prog="factor-weaver")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('factor-weaver')}"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(required=True)
    for workflow in (data, train, evaluate, report):
        workflow.add_arguments(sub)
    for workflow_parser in sub.choices.values():
        workflow_parser.add_argument(
            "-v", "--verbose", action="store_true", default=argparse.SUPPRESS
        )

    args = parser.parse_args(argv)
    if err.is_terminal:
        handler: logging.Handler = RichHandler(
            console=err,
            show_path=False,
            rich_tracebacks=True,
            log_time_format="%H:%M:%S",
            markup=False,
        )
        fmt = "%(name)s: %(message)s"
    else:
        handler = logging.StreamHandler(sys.stderr)
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=fmt,
        datefmt="%H:%M:%S",
        handlers=[handler],
    )
    logging.captureWarnings(True)
    install(console=err)

    cfg = config.load(*getattr(args, "configs", ("data",)))
    try:
        args.func(cfg, args)
    except SystemExit as exc:
        if not isinstance(exc.code, str):
            raise
        err.print(Text(exc.code, style="red"), soft_wrap=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
