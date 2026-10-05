# Factor Weaver — Agent Guide

**Status: data pipeline implemented through prices** (LSEG retrieval, top-50 universe, LSEG prices with Yahoo fallback + extra series); `technicals`, `panel`, `split` are stubs. Models, shared engine, and `train`/`eval` workflows are stubbed per `PLAN.md`.

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Tentative stack (under consideration): Python, PyTorch, Gymnasium (not FinRL), hand-rolled PPO (CleanRL reference), cross-stock transformer encoder, Dirichlet policy head, scikit-learn + PyPortfolioOpt benchmarks, YAML configs, MLflow tracking, ruff + pyright. See `docs/methodology.md` for rationale.

## Repository structure

```
src/factor_weaver/
├── cli.py            # argparse dispatcher, logging setup (entry point)
├── config.py         # YAML config loading (config/*.yaml merged by workflow)
├── output.py         # shared rich consoles (out, err)
├── workflows/        # CLI glue: data, train, evaluate, report
├── data/             # MODULE 1
│   ├── pipeline.py   #   step manifest (Step: phase, ins, outs) + dependency-aware runner
│   ├── store.py      #   shared parquet read/write + cache paths
│   ├── fetch/        #   external I/O only: lseg, yahoo, prices (writes data/raw/ caches)
│   └── build/        #   derived data only: universe, prices, technicals, panel, split
├── models/           # MODULE 2: weight-producing models: simple, optimize, mean_variance, black_litterman, ml_forecast, rl/ (env, model, ppo, policy)
└── eval/             # MODULE 3: backtest (shared engine + metrics)

config/               # YAML configs (data paths, engine params, model params)
data/                 # tracked symlinks → external dir (raw, interim, processed)
docs/                 # documentation (architecture, data, methodology, models, literature)
notebooks/            # exploratory quarto notebooks
experiments/          # run outputs (logs, checkpoints, results, mlruns)
tests/                # pytest checks (universe/prices tests synthetic)
```

## Workflows

- `cli.py` dispatches to workflow modules exposing `add_arguments(subparsers)` and `run(cfg, args)`; each subparser registers `run` and its `configs` tuple via `set_defaults(...)`.
- `data/pipeline.py` holds the ordered `STEPS` manifest. `Step(name, run, phase, ins, outs)` declares config-key inputs/outputs; the runner pulls producers of missing inputs and logs each addition. Phases: `fetch` writes only `data/raw/`; `build` writes only `data/interim|processed`.
- `factor-weaver data [fetch|build] [steps ...]`: runs all steps, one phase, or a subset (always manifest order). `--list` shows step/output status; `--refresh` refetches cached data; `-v` enables debug logging.
- `factor-weaver train [MODEL]` (default `rl`): dispatches through `models.TRAINERS`; `--resume` continues from a checkpoint (stub).
- `factor-weaver eval [MODEL ...]`: runs each selected `models.REGISTRY` provider (default all) through the shared engine; `--start/--end` override the eval window; `--checkpoint` overrides the RL checkpoint. Bare `eval` skips `rl` with a warning when no checkpoint is configured (stub).
- `factor-weaver report [--experiment NAME] [--out PATH]`: queries the shared MLflow experiment (`tags.kind = eval`) into a comparison table or CSV.
- Fetch steps are existence-cached: whole-step skip when outputs exist, per-RIC/per-symbol skip inside the price steps; a fully cached run needs no credentials or network.

## Key files

| File                             | Purpose                                                                   |
| -------------------------------- | ------------------------------------------------------------------------- |
| `README.md`                      | User-facing overview, status, quickstart                                  |
| `PLAN.md`                        | Benchmark + evaluation implementation plan: models, engine, phases        |
| `docs/architecture.md`           | Module architecture, data pipeline, runtime flow (mermaid diagrams)       |
| `docs/methodology.md`            | Environment setup, model architecture, evaluation plan                    |
| `docs/models.md`                 | Per-model docs: replication targets, methods, configs, engine equivalence |
| `docs/data.md`                   | Variables, sources (LSEG, Yahoo, MarketPsych)                             |
| `docs/literature.md`             | 36 annotated references organized by research point with inline citations |
| `todo.md`                        | Current pending items                                                     |

## Dependencies

- S&P500 constituent list, joiner/leaver history (since 1994), RIC mapping, and market cap (`TR.CompanyMarketCap`, fallback `TR.F.MktCap`): fetched from LSEG data API, cached in `data/raw/lseg/`; used for top-50 universe selection.
- Price data: LSEG data API daily OHLCV (per-RIC cache in `data/raw/lseg/prices/`); Yahoo Finance (`yfinance`) is the fallback for RICs LSEG cannot serve and the source for extra index/ETF series (per-symbol cache in `data/raw/yahoo/prices/`).
- Fundamentals: planned from LSEG (not yet implemented; the `panel` build step is the integration point).
- Behavioral: planned from MarketPsych (not yet implemented).
- Benchmarks/evaluation (per `docs/models.md`): scikit-learn (GBRT, Ledoit–Wolf), PyPortfolioOpt (tangency optimizer), mlflow (tracking) — declared in `pyproject.toml`; risk-free via `^IRX` (yield series, not a price).
- Dev: `uv sync` installs the project plus the `dev` dependency group into `.venv`; run checks with `uv run pytest tests/`, `ruff check .`, `pyright src`.

## Conventions

- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- Adding a data source/step: create the module under `data/fetch/` or `data/build/`, add one `Step` entry to `STEPS` in `data/pipeline.py`, add its output keys to `config/data.yaml`.
- Diagrams live inline as mermaid in `docs/`; keep the minimal nested-bullet style of existing docs.
- The thesis is written in LaTeX in a separate directory (not here).
- Ponytail mode active — prefer stdlib, fewest files, shortest working diff. No unrequested abstractions.

## Git

- No remote configured. Single local branch (`main`).
- Commit history mixes `docs:`, `feat(data):`, `fix`, `refactor`, and `chore` commits.
