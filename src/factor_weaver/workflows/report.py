"""Report workflow: `factor-weaver report` — compare tracked eval runs (MLflow)."""

import argparse
import logging
from typing import Any

from rich.table import Table

from factor_weaver.output import out

log = logging.getLogger(__name__)

METRICS = ("cagr", "volatility", "sharpe", "sortino", "max_drawdown", "calmar", "avg_turnover")


def add_arguments(sub: Any) -> None:
    parser = sub.add_parser("report", help="Compare tracked eval runs (MLflow) in a table")
    parser.add_argument("--experiment", metavar="NAME", help="override eval.yaml experiment")
    parser.add_argument("--out", metavar="PATH", help="write the table as CSV")
    parser.set_defaults(func=run, configs=("eval",))


def _label(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def run(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    import mlflow
    from mlflow.exceptions import MlflowException

    mlflow.set_tracking_uri(cfg["mlflow"]["tracking_uri"])
    experiment = args.experiment or cfg["mlflow"]["experiment"]
    try:
        runs = mlflow.search_runs(experiment_names=[experiment], filter_string="tags.kind = 'eval'")
    except MlflowException as exc:
        log.warning("cannot read MLflow experiment '%s': %s", experiment, exc)
        return
    if runs.empty:
        log.warning("no eval runs in experiment '%s'", experiment)
        return
    id_col = "tags.model" if "tags.model" in runs.columns else "run_id"
    metric_cols = [f"metrics.{m}" for m in METRICS if f"metrics.{m}" in runs.columns]
    table = runs[[id_col, *metric_cols]].copy()
    table.columns = ["model", *(c.removeprefix("metrics.") for c in metric_cols)]
    if args.out:
        table.to_csv(args.out, index=False)
    rich_table = Table(*(col.replace("_", " ") for col in table.columns))
    for _, row in table.iterrows():
        rich_table.add_row(*(_label(value) for value in row))
    out.print(rich_table)
