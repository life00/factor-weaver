# Factor Weaver — Agent Guide

**Status: scaffolding done.** Directory structure in place. No code beyond `__init__.py` stubs.

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Tentative stack (under consideration): Python, PyTorch, Gymnasium (not FinRL), hand-rolled PPO (CleanRL reference), cross-stock transformer encoder, Dirichlet policy head, YAML configs, MLflow tracking, ruff + pyright. See `docs/methodology.md` for rationale.

## Repository structure

```
src/factor_weaver/
├── cli.py            # argparse subcommand dispatcher (entry point)
├── workflows/        # orchestrators: build_dataset, train, evaluate
├── data/             # MODULE 1: financialdatadb, universe, edgar, prices, technicals, behavior, align
├── rl/               # MODULE 2: env, model, ppo
├── eval/             # MODULE 3: backtest, benchmarks
└── math.py           # financial math helpers (shared)

config/               # YAML configs (data paths, env params, model hparams)
data/                 # gitignored — raw, interim, train, test
docs/                 # planning docs + figures
  figures/            #   PlantUML diagrams (data flow, architecture)
notebooks/            # exploratory quarto notebooks
experiments/          # run outputs (logs, checkpoints, results)
tests/                # pytest checks (data-driven; skip if raw data absent)
```

## Workflows

- `cli.py` dispatches to workflow modules, each exposing `add_arguments(subparsers)` and `run(cfg, args)` (see `workflows/build_dataset.py` for the pattern).
- `workflows/__init__.py` provides the shared step runner (`resolve` + `run_steps`) used by step-based workflows.

## Key files

| File                             | Purpose                                                                   |
| -------------------------------- | ------------------------------------------------------------------------- |
| `docs/methodology.md`            | Environment setup, model architecture, evaluation plan                    |
| `docs/data.md`                   | Variables, sources (financialdatadb, Yahoo Finance, SEC EDGAR, sibling)   |
| `docs/literature.md`             | 24 annotated references organized by research point with inline citations |
| `docs/figures/data_flow.puml`    | Data flow: sources → processed tensors (with rendered PNG)                |
| `docs/figures/architecture.puml` | Module architecture: subsystems + workflows (with rendered PNG)           |
| `todo.md`                        | Current pending items                                                     |

## Dependencies

- Fundamental data: financialdatadb — raw xlsx files live in `data/raw/financialdatadb/` (26 files A-Z, each with one sheet per ticker; row 87 = Market Capitalization).
- S&P500 constituent list: fetched from `fja05680/sp500` GitHub repo, cached locally.
- Price data: Yahoo Finance daily OHLCV via `yfinance`.
- EDGAR filing dates: direct HTTP to SEC EDGAR submissions API (no edgartools dep — just need the report date, not full document parsing).
- Dev: pytest via `pip install -e .[dev]`; run checks with `pytest tests/`, `ruff check .`, `pyright src`.

## Conventions

- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- The thesis is written in LaTeX in a separate directory (not here).
- Ponytail mode active — prefer stdlib, fewest files, shortest working diff. No unrequested abstractions.

## Git

- No remote configured. Single local branch (`main`).
- Commit history is all `docs: ...` prefixed.
