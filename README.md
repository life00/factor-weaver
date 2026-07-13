**Work In Progress**

---

# Factor Weaver

Master's thesis developing a reinforcement learning framework for portfolio management that integrates price, technical, fundamental, and behavioral (attention & sentiment) features across a dynamic equity universe of the top 50 S&P500 constituents. Uses an actor-critic architecture trained via PPO to output portfolio weights (no short-selling) maximizing risk-adjusted returns (Sharpe) under transaction costs, evaluated against benchmarks like equal-weight and minimum-variance.

## Repository structure

```
├── config/          # YAML configs (data paths, env params, model hparams)
├── data/            # gitignored; see data.yaml for sources
│   ├── external/    #   behavior features from market-behavior-archive
│   ├── features/    #   processed aligned feature parquet files
│   └── static/      #   S&P500 constituents, market-cap histories
├── scripts/         # CLI entrypoints (prepare, train, evaluate)
├── src/factor_weaver/
│   ├── universe/    #   S&P500 constituents & top-50 ranking
│   ├── features/    #   data loading & feature engineering
│   ├── env/         #   Gymnasium environment & reward functions
│   ├── models/      #   torch modules (encoder, actor, critic)
│   ├── agents/      #   RL training (PPO)
│   ├── evaluation/  #   backtesting, benchmarks, metrics
│   └── utils/       #   financial math, data IO
├── experiments/     # run outputs (logs, checkpoints, results)
├── tests/           # test suite
└── docs/            # thesis planning docs (methodology, data, literature)
```

Data pipeline: raw sources → `prepare_universe.py` builds rolling top-50 history → `prepare_features.py` aligns price/funda/behavior features → `train.py` trains PPO agent → `evaluate.py` benchmarks against 1/N and min-variance. Behavior features arrive as pre-computed parquet from the sibling repo `market-behavior-archive`.
