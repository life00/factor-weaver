**Work In Progress**

---

# Factor Weaver

Master's thesis developing a reinforcement learning framework for portfolio management that integrates price, technical, fundamental, and behavioral (attention & sentiment) features across a dynamic equity universe of the top 50 S&P500 constituents. Uses an actor-critic architecture trained via PPO to output portfolio weights (no short-selling) maximizing risk-adjusted returns (Sharpe) under transaction costs, evaluated against benchmarks like equal-weight and minimum-variance.

## Tech stack

Python, PyTorch, Gymnasium, PPO (hand-rolled), cross-stock transformer, Dirichlet policy head. Config via YAML, experiment tracking via MLflow, linting with ruff and pyright, tests with pytest.

## Repository structure

```
├── config/             # YAML configs (data paths, env params, model hparams)
├── data/               # gitignored; created on first data run
│   ├── raw/            #   vendor downloads (financialdatadb xlsx, etc.)
│   ├── processed/      #   one parquet per pipeline step (cacheable)
│   ├── train/          #   env-ready tensors for the training window
│   └── test/           #   env-ready tensors for the test window
├── docs/               # thesis planning docs
│   └── figures/        #   PlantUML diagrams (data flow, architecture)
├── notebooks/          # exploratory notebooks (tracked, outputs stripped)
├── src/factor_weaver/
│   ├── cli.py          #   argparse dispatcher (entry point)
│   ├── workflows/      #   orchestrators: build_dataset, train, evaluate
│   ├── data/           #   MODULE 1: data pipeline (parse, universe, edgar, prices, technicals, behavior, align)
│   ├── rl/             #   MODULE 2: env, model, ppo
│   ├── eval/           #   MODULE 3: backtest, benchmarks
│   └── math.py         #   financial math helpers (shared)
├── experiments/        # run outputs (logs, checkpoints, results)
├── tests/
```

## Data pipeline

1. `parse-fundamentals` — financialdatadb xlsx → long parquet
2. `universe` — top-50 S&P500 by market cap per quarter
3. `edgar-filing-dates` — SEC filing dates (no look-ahead bias)
4. `fetch-prices` — Yahoo Finance OHLCV
5. `compute-technicals` — rolling indicators from prices
6. `load-behavior` — sibling-repo sentiment/attention parquet
7. `align` — EDGAR-anchored forward-fill + freshness + time-decay
8. `split` — train/test tensors by date window

Architecture and data-flow diagrams: [`docs/figures/`](docs/figures/).
