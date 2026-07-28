# Factor Weaver — Agent Guide

**Status: scaffolding done.** Directory structure in place. No code beyond `__init__.py` stubs.

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Tentative stack (under consideration): Python, PyTorch, Gymnasium (not FinRL), hand-rolled PPO (CleanRL reference), cross-stock transformer encoder, Dirichlet policy head, YAML configs, MLflow tracking, ruff + pyright. See `docs/methodology.md` for rationale.

## Repository structure

```
src/factor_weaver/
├── cli.py            # argparse subcommand dispatcher (entry point)
├── data/             # universe ranking, feature prep, dataset build, IO
├── env.py            # Gymnasium environment, reward functions
├── model.py          # torch modules (encoder + actor + critic)
├── ppo.py            # PPO training loop
├── evaluation/       # backtesting, benchmarks, metrics
└── math.py           # financial math helpers

config/               # YAML configs (data paths, env params, model hparams)
data/                 # gitignored — raw, processed, train, test
notebooks/            # exploratory notebooks (tracked, outputs stripped)
experiments/          # run outputs (logs, checkpoints, results)
tests/
```

## Key files

| File                  | Purpose                                                                   |
| --------------------- | ------------------------------------------------------------------------- |
| `docs/methodology.md` | Environment setup, model architecture, evaluation plan                    |
| `docs/data.md`        | Variables, sources (EODHD, Alpha Vantage, SEC EDGAR, HuggingFace)         |
| `docs/literature.md`  | 24 annotated references organized by research point with inline citations |
| `todo.md`             | Current pending items                                                     |

## Dependencies

- Behavior/sentiment data lives in a separate repo (`market-behavior-archive`).
- That repo produces parquet files with columns: `date, ticker, sentiment_score, attention_score, ...`.
- The sibling-repo parquet lands in `data/raw/behavioral/`; `data.yaml` points to it — the interface is just "parquet with aligned timestamps".
- Data flows through four stages on disk: `data/raw/` (untouched vendor downloads + sibling-repo parquet) → `data/processed/` (cleaned/aligned, full date range) → `data/train/` + `data/test/` (env-ready tensors split by date window).

## Conventions

- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- The thesis is written in LaTeX in a separate directory (not here).
- Ponytail mode active — prefer stdlib, fewest files, shortest working diff. No unrequested abstractions.

## Git

- No remote configured. Single local branch (`main`).
- Commit history is all `docs: ...` prefixed.
