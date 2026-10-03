# Factor Weaver — Agent Guide

**Status: data pipeline implemented** (financialdatadb parsing, LSEG retrieval, top-50 universe). Models/eval modules stubbed per `PLAN.md` (benchmark + evaluation framework, Phases 1–3 not yet implemented).

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Tentative stack (under consideration): Python, PyTorch, Gymnasium (not FinRL), hand-rolled PPO (CleanRL reference), cross-stock transformer encoder, Dirichlet policy head, scikit-learn + PyPortfolioOpt benchmarks, YAML configs, MLflow tracking, ruff + pyright. See `docs/methodology.md` for rationale.

## Repository structure

```
src/factor_weaver/
├── cli.py            # argparse subcommand dispatcher (entry point)
├── workflows/        # orchestrators: build_dataset, train, evaluate
├── data/             # MODULE 1: financialdatadb, lseg, tickers, universe, edgar, prices, yahoo, technicals, behavior, align, split
├── models/           # MODULE 2: weight-producing models: simple, optimize, mean_variance, black_litterman, ml_forecast, rl/ (env, model, ppo, policy)
├── eval/             # MODULE 3: backtest (shared engine + metrics)
└── math.py           # financial math helpers (shared)

config/               # YAML configs (data paths, engine params, model params)
data/                 # tracked symlinks → /mnt/usb/factor-weaver/data/ (raw, interim, processed)
docs/                 # planning docs + figures
  figures/            #   PlantUML diagrams (data flow, architecture)
notebooks/            # exploratory quarto notebooks
experiments/          # run outputs (logs, checkpoints, results, mlruns)
tests/                # pytest checks (universe tests synthetic; xlsx tests skip if raw data absent)
PLAN.md               # benchmark + evaluation implementation plan (phases)
```

## Workflows

- `cli.py` dispatches to workflow modules, each exposing `add_arguments(subparsers)` and `run(cfg, args)`; each subparser registers its own `run` via `set_defaults(func=...)` (see `workflows/build_dataset.py` for the pattern).
- `build_dataset.py` orders pipeline steps in the `STEPS` dict (insertion order == run order); `factor-weaver data [steps ...]` runs the listed steps in order, or all if empty.

## Key files

| File                             | Purpose                                                                   |
| -------------------------------- | ------------------------------------------------------------------------- |
| `PLAN.md`                        | Benchmark + evaluation implementation plan: models, engine, phases        |
| `docs/methodology.md`            | Environment setup, model architecture, evaluation plan                    |
| `docs/models.md`                | Per-model docs: replication targets, methods, configs, engine equivalence |
| `docs/data.md`                   | Variables, sources (financialdatadb, LSEG, SEC EDGAR, sibling)            |
| `docs/literature.md`             | 36 annotated references organized by research point with inline citations |
| `docs/figures/data_flow.puml`    | Data flow: sources → processed tensors (with rendered PNG)                |
| `docs/figures/architecture.puml` | Module architecture: subsystems + workflows (with rendered PNG)           |
| `todo.md`                        | Current pending items                                                     |

## Dependencies

- Fundamental data: financialdatadb — raw xlsx files live in `data/raw/financialdatadb/us_financials/` (26 `*_tickers.xlsx` files A-Z, one sheet per ticker; row 87 = Market Capitalization).
- S&P500 constituent list, joiner/leaver history (since 1994), RIC mapping, and market cap (`TR.CompanyMarketCap`, fallback `TR.F.MktCap`): fetched from LSEG data API, cached in `data/raw/lseg/`; used for top-50 universe selection.
- Price data: LSEG data API daily OHLCV.
- EDGAR filing dates: direct HTTP to SEC EDGAR submissions API (no edgartools dep — just need the report date, not full document parsing).
- Benchmarks/evaluation (per `PLAN.md`): scikit-learn (GBRT, Ledoit–Wolf), PyPortfolioOpt (tangency optimizer), mlflow (tracking) — declared in `pyproject.toml`; risk-free via `^IRX` (yield series, not a price).
- Dev: pytest via `pip install -e .[dev]`; run checks with `pytest tests/`, `ruff check .`, `pyright src`.

## Conventions

- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- The thesis is written in LaTeX in a separate directory (not here).
- Ponytail mode active — prefer stdlib, fewest files, shortest working diff. No unrequested abstractions.

## Git

- No remote configured. Single local branch (`main`).
- Commit history mixes `docs:`, `feat(data):`, `fix`, `refactor`, and `chore` commits.
