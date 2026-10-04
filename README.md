**Work In Progress**
---

# Factor Weaver

Master's thesis developing a reinforcement learning framework for portfolio management that integrates price, technical, fundamental, and behavioral (attention & sentiment) features across a dynamic equity universe of the top 50 S&P500 constituents. Uses an actor-critic architecture trained via PPO to output portfolio weights (no short-selling) maximizing risk-adjusted returns (Sharpe) under transaction costs, evaluated against benchmarks like equal-weight and minimum-variance.

## Status

- Data pipeline implemented: financialdatadb fundamentals, LSEG constituents/market cap, top-50 universe, prices with Yahoo fallback.
- Models and evaluation stubbed per [`PLAN.md`](PLAN.md) (Phases 1 to 3).

## Tech stack

- Implemented: Python, pandas, pyarrow, lseg-data, yfinance, scikit-learn, PyPortfolioOpt, MLflow, YAML configs, ruff + pyright, pytest.
- Planned: PyTorch, Gymnasium, hand-rolled PPO, cross-stock transformer, Dirichlet policy head.

## Usage

```sh
pip install -e .[dev]
factor-weaver data [steps ...]   # empty = run all steps in order
```

## Repository structure

```
├── config/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── docs/
│   └── figures/
├── notebooks/
├── src/factor_weaver/
│   ├── cli.py
│   ├── workflows/
│   ├── data/
│   ├── models/
│   │   └── rl/
│   ├── eval/
│   └── math.py
├── experiments/
└── tests/
```

## Data pipeline

1. `parse-fundamentals`
2. `parse-companies`
3. `lseg-constituents`
4. `lseg-joiners-leavers`
5. `lseg-mapping`
6. `lseg-market-cap`
7. `universe`
8. `edgar-filing-dates` (stub)
9. `fetch-prices`
10. `compute-technicals` (stub)
11. `load-behavior` (stub)
12. `align` (stub)
13. `split` (stub)

Architecture and data-flow diagrams: [`docs/figures/`](docs/figures/).
