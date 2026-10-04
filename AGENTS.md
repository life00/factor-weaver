# Factor Weaver — Agent Guide

**Status: data pipeline implemented** (LSEG retrieval, top-50 universe, prices with Yahoo fallback). Models/eval modules stubbed per `PLAN.md` (benchmark + evaluation framework, Phases 1–3 not yet implemented).

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Tentative stack (under consideration): Python, PyTorch, Gymnasium (not FinRL), hand-rolled PPO (CleanRL reference), cross-stock transformer encoder, Dirichlet policy head, scikit-learn + PyPortfolioOpt benchmarks, YAML configs, MLflow tracking, ruff + pyright. See `docs/methodology.md` for rationale.

## Repository structure

```
src/factor_weaver/
├── cli.py            # argparse dispatcher, logging setup (entry point)
├── config.py         # YAML config loading (config/*.yaml merged by workflow)
├── workflows/        # CLI glue: data, train, evaluate
├── data/             # MODULE 1
│   ├── pipeline.py   #   step manifest (Step: phase, ins, outs) + dependency-aware runner
│   ├── store.py      #   shared parquet read/write + cache paths
│   ├── fetch/        #   external I/O only: lseg, yahoo, prices (writes data/raw/ caches)
│   └── build/        #   derived data only: universe, prices, technicals, panel, split
├── models/           # MODULE 2: weight-producing models: simple, optimize, mean_variance, black_litterman, ml_forecast, rl/ (env, model, ppo, policy)
└── eval/             # MODULE 3: backtest (shared engine + metrics)

config/               # YAML configs (data paths, engine params, model params)
data/                 # tracked symlinks → external dir (raw, interim, processed)
docs/                 # planning docs + figures
  figures/            #   PlantUML diagrams (data flow, architecture)
notebooks/            # exploratory quarto notebooks
experiments/          # run outputs (logs, checkpoints, results, mlruns)
tests/                # pytest checks (universe/prices tests synthetic)
PLAN.md               # benchmark + evaluation implementation plan (phases)
```

## Workflows

- `cli.py` dispatches to workflow modules exposing `add_arguments(subparsers)` and `run(cfg, args)`; each subparser registers `run` and its `configs` tuple via `set_defaults(...)`.
- `data/pipeline.py` holds the ordered `STEPS` manifest. `Step(name, run, phase, ins, outs)` declares config-key inputs/outputs; the runner pulls producers of missing inputs and logs each addition. Phases: `fetch` writes only `data/raw/`; `build` writes only `data/interim|processed`.
- `factor-weaver data [fetch|build] [steps ...]`: runs all steps, one phase, or a subset (always manifest order). `--list` shows step/output status; `--refresh` refetches cached data; `-v` enables debug logging.
- Fetch steps are existence-cached: whole-step skip when outputs exist, per-RIC/per-symbol skip inside the price steps; a fully cached run needs no credentials or network.

## Key files

| File                             | Purpose                                                                   |
| -------------------------------- | ------------------------------------------------------------------------- |
| `PLAN.md`                        | Benchmark + evaluation implementation plan: models, engine, phases        |
| `docs/methodology.md`            | Environment setup, model architecture, evaluation plan                    |
| `docs/models.md`                 | Per-model docs: replication targets, methods, configs, engine equivalence |
| `docs/data.md`                   | Variables, sources (LSEG, Yahoo, MarketPsych)                             |
| `docs/literature.md`             | 36 annotated references organized by research point with inline citations |
| `docs/figures/data_flow.puml`    | Data flow: sources → processed tensors (with rendered PNG)                |
| `docs/figures/architecture.puml` | Module architecture: subsystems + workflows (with rendered PNG)           |
| `todo.md`                        | Current pending items                                                     |

## Dependencies

- S&P500 constituent list, joiner/leaver history (since 1994), RIC mapping, and market cap (`TR.CompanyMarketCap`, fallback `TR.F.MktCap`): fetched from LSEG data API, cached in `data/raw/lseg/`; used for top-50 universe selection.
- Price data: LSEG data API daily OHLCV (per-RIC cache in `data/raw/lseg/prices/`); Yahoo Finance (`yfinance`) is the fallback for RICs LSEG cannot serve and the source for extra index/ETF series (per-symbol cache in `data/raw/yahoo/prices/`).
- Fundamentals: planned from LSEG (not yet implemented; the `panel` build step is the integration point).
- Behavioral: planned from MarketPsych (not yet implemented).
- Benchmarks/evaluation (per `PLAN.md`): scikit-learn (GBRT, Ledoit–Wolf), PyPortfolioOpt (tangency optimizer), mlflow (tracking) — declared in `pyproject.toml`; risk-free via `^IRX` (yield series, not a price).
- Dev: pytest via `pip install -e .[dev]`; run checks with `pytest tests/`, `ruff check .`, `pyright src`.

## Conventions

- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- Adding a data source/step: create the module under `data/fetch/` or `data/build/`, add one `Step` entry to `STEPS` in `data/pipeline.py`, add its output keys to `config/data.yaml`.
- The thesis is written in LaTeX in a separate directory (not here).
- Ponytail mode active — prefer stdlib, fewest files, shortest working diff. No unrequested abstractions.

## Git

- No remote configured. Single local branch (`main`).
- Commit history mixes `docs:`, `feat(data):`, `fix`, `refactor`, and `chore` commits.
