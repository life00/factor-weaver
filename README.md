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
│   ├── raw/            #   vendor downloads + sibling-repo behavioral parquet
│   ├── processed/      #   cleaned/aligned features (ffill + staleness + decay)
│   ├── train/          #   env-ready tensors for the training window
│   └── test/           #   env-ready tensors for the test window
├── notebooks/          # exploratory notebooks (tracked, outputs stripped)
├── src/factor_weaver/
│   ├── cli.py          #   argparse subcommand dispatcher (entry point)
│   ├── data/           #   universe ranking, feature prep, dataset build, IO
│   ├── env.py          #   Gymnasium environment & reward
│   ├── model.py        #   encoder + actor + critic
│   ├── ppo.py          #   PPO training loop
│   ├── evaluation/     #   backtesting, benchmarks, metrics
│   └── math.py         #   financial math helpers
├── experiments/        # run outputs (logs, checkpoints, results)
├── tests/              # test suite
└── docs/               # thesis planning docs (methodology, data, literature)
```

## Data pipeline

raw sources → `prepare-universe` builds rolling top-50 history → `prepare-features`
aligns price/funda/behavioral features (forward-fill + staleness counter for
fundamentals, time-decay for behavioral) into `data/processed/` → `build-dataset`
splits and tensorizes processed features into `data/train/` and `data/test/` →
`train` trains the PPO agent → `evaluate` benchmarks against 1/N and min-variance.
Behavior features arrive as pre-computed parquet from the sibling repo
`market-behavior-archive`.
