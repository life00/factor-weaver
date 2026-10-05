**Work In Progress**
---

# Factor Weaver

Master's thesis developing a reinforcement learning framework for portfolio management that integrates price, technical, fundamental, and behavioral (attention & sentiment) features across a dynamic equity universe of the top 50 S&P500 constituents. Uses an actor-critic architecture trained via PPO to output portfolio weights (no short-selling) maximizing risk-adjusted returns (Sharpe) under transaction costs, evaluated against benchmarks like equal-weight and minimum-variance.

## Status

- Data pipeline implemented: LSEG constituents/market cap, top-50 universe, LSEG prices with Yahoo fallback and extra series.
- Models and evaluation stubbed per [`PLAN.md`](PLAN.md) (Phases 1 to 3).

## Tech stack

- Implemented: Python, pandas, pyarrow, lseg-data, yfinance, scikit-learn, PyPortfolioOpt, MLflow, YAML configs, ruff + pyright, pytest.
- Planned: PyTorch, Gymnasium, hand-rolled PPO, cross-stock transformer, Dirichlet policy head.

## Usage

```sh
uv sync                                    # create/update .venv from uv.lock
uv run factor-weaver data                  # run all steps (fetch then build)
uv run factor-weaver data fetch [steps]    # raw data acquisition only (cached)
uv run factor-weaver data build [steps]    # derived datasets only
uv run factor-weaver data --list           # step/output status
uv run factor-weaver data fetch --refresh  # refetch cached raw data
uv run factor-weaver train rl              # train the RL policy (stub, Phase 3)
uv run factor-weaver eval [models ...]     # backtest models via the shared engine (stub)
uv run factor-weaver report                # compare tracked eval runs (stub)
```

Run from the repository root so the relative `config/` and `data/` paths resolve.
Fetch steps are existence-cached (whole outputs and per-RIC/per-symbol price caches);
`-v` logs every cache hit/fetch.

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
│   ├── config.py
│   ├── workflows/          # data, train, evaluate, report
│   ├── data/
│   │   ├── pipeline.py     # ordered Step manifest + runner
│   │   ├── store.py
│   │   ├── fetch/          # LSEG, Yahoo (writes data/raw/)
│   │   └── build/          # universe, prices, technicals, panel, split
│   ├── models/
│   │   └── rl/
│   └── eval/
├── experiments/
└── tests/
```

## Data pipeline

Fetch (writes `data/raw/` only):

1. `lseg-constituents`
2. `lseg-joiners-leavers`
3. `lseg-mapping`
4. `lseg-market-cap`
5. `lseg-prices` (per-RIC caches, LSEG `ric_fallbacks` applied)
6. `yahoo-prices` (fallback RICs + extra index/ETF series)

Build (writes `data/interim|processed` only):

7. `universe` (top-50 membership + company registry)
8. `prices` (canonical OHLCV + extra series)
9. `technicals` (stub)
10. `panel` (stub)
11. `split` (stub)

Architecture and data-flow diagrams: [`docs/figures/`](docs/figures/).
