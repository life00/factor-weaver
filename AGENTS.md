# Factor Weaver — Agent Guide

**Status: scaffolding done.** Directory structure in place. No code beyond `__init__.py` stubs.

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Tentative stack (under consideration): Python, PyTorch, Gymnasium (not FinRL), hand-rolled PPO (CleanRL reference), cross-stock transformer encoder, Dirichlet policy head, YAML configs, MLflow tracking, ruff + pyright. See `docs/methodology.md` for rationale.

## Repository structure

```
src/factor_weaver/
├── universe/        # S&P500 constituents, top-50 ranking
├── features/        # data loading, feature engineering, transforms
├── env/             # Gymnasium environment, reward functions
├── models/          # torch modules (encoder, actor, critic)
├── agents/          # RL training (PPO)
├── evaluation/      # backtesting, benchmarks, metrics
└── utils/           # financial math, data IO helpers

config/              # YAML configs (data paths, env params, model hparams)
data/                # gitignored — static (constituents), features (processed), external
scripts/             # CLI entrypoints (prepare_universe, prepare_features, train, evaluate)
experiments/         # run outputs (logs, checkpoints, results)
tests/
```

## Key files

| File                  | Purpose                                                                   |
| --------------------- | ------------------------------------------------------------------------- |
| `docs/description.md` | Thesis objective, scope, literature list                                  |
| `docs/methodology.md` | Environment setup, model architecture, evaluation plan                    |
| `docs/data.md`        | Variables, sources (EODHD, Alpha Vantage, SEC EDGAR, HuggingFace)         |
| `docs/literature.md`  | 24 annotated references organized by research point with inline citations |
| `todo.md`             | Current pending items                                                     |

## Dependencies

- Behavior/sentiment data lives in a separate repo (`market-behavior-archive`).
- That repo produces parquet files with columns: `date, ticker, sentiment_score, attention_score, ...`.
- This repo's `data.yaml` points to those files — the interface is just "parquet with aligned timestamps".

## Conventions

- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- The thesis is written in LaTeX in a separate directory (not here).
- Ponytail mode active — prefer stdlib, fewest files, shortest working diff. No unrequested abstractions.

## Git

- No remote configured. Single local branch (`main`).
- Commit history is all `docs: ...` prefixed.
