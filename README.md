**Work In Progress**

---

# Factor Weaver

Master's thesis developing a reinforcement learning framework for portfolio management that integrates price, technical, fundamental, and behavioral (attention & sentiment) features across a dynamic equity universe of the top 50 S&P500 constituents. Uses an actor-critic architecture trained via PPO to output portfolio weights (no short-selling) maximizing risk-adjusted returns (Sharpe) under transaction costs, evaluated against benchmarks like equal-weight and minimum-variance.

## Tech stack

Python, PyTorch, Gymnasium, PPO (hand-rolled), cross-stock transformer, Dirichlet policy head. Config via YAML, experiment tracking via MLflow, linting with ruff and pyright, tests with pytest.

## Repository structure

```
├── config/             # YAML configs (data paths, env params, model hparams)
├── data/               # symlinks → /mnt/usb/factor-weaver/data/ (raw, interim, processed)
│   ├── raw/            #   original downloads/API output from vendors
│   ├── interim/        #   cleaned and normalized data in parquet files
│   └── processed/      #   final aligned output for RL training/testing
├── docs/               # thesis planning docs
│   └── figures/        #   PlantUML diagrams (data flow, architecture)
├── notebooks/          # exploratory quarto notebooks
├── src/factor_weaver/
│   ├── cli.py          #   argparse dispatcher (entry point)
│   ├── workflows/      #   orchestrators: build_dataset, train, evaluate
│   ├── data/           #   MODULE 1: data pipeline (parse, lseg, universe, edgar, prices, technicals, behavior, align, split)
│   ├── rl/             #   MODULE 2: env, model, ppo
│   ├── eval/           #   MODULE 3: backtest, benchmarks
│   └── math.py         #   financial math helpers (shared)
├── experiments/        # run outputs (logs, checkpoints, results)
├── tests/
```

## Data pipeline

1. `parse-fundamentals` — financialdatadb xlsx → long parquet
2. `parse-companies` — financialdatadb company list → parquet
3. `lseg-constituents` — current S&P500 snapshot (LSEG chain RIC)
4. `lseg-joiners-leavers` — S&P500 membership changes since 1994 (LSEG)
5. `lseg-mapping` — RIC → ticker/name/PermID crosswalk for all LSEG RICs
6. `lseg-market-cap` — quarterly market cap via `TR.CompanyMarketCap` (fallback `TR.F.MktCap`)
7. `universe` — top-50 S&P500 by market cap per quarter
8. `edgar-filing-dates` — SEC filing dates (no look-ahead bias)
9. `fetch-prices` — LSEG OHLCV
10. `compute-technicals` — rolling indicators from prices
11. `load-behavior` — sibling-repo sentiment/attention parquet
12. `align` — EDGAR-anchored forward-fill + freshness + time-decay
13. `split` — train/test tensors by date window

Architecture and data-flow diagrams: [`docs/figures/`](docs/figures/).
