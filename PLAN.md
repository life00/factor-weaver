# PLAN — Benchmark Models & Evaluation Framework

> Status: planned; module skeletons stubbed. Phase 1 runs on existing
> price/universe data; Phase 2 additionally needs the panel data file (§2).
> Detailed per-model documentation: `docs/models.md`.

## 1. Goal

Evaluate the RL portfolio policy against 5 benchmark models inside ONE
identical simulated trading environment:

| # | Model             | Type        | Replication target                        | Factors used                  |
|---|-------------------|-------------|-------------------------------------------|-------------------------------|
| 1 | `equal_weight`    | naive       | DeMiguel et al. (2009)                    | none                          |
| 2 | `index_buy_hold`  | market      | S&P500 (`^GSPC`)                          | none                          |
| 3 | `mean_variance`   | classical   | Markowitz (1952)                          | prices                       |
| 4 | `ml_forecast`     | ML          | Gu, Kelly & Xiu (2020) + Ma et al. (2021) | technical, fundamental, behavioral |
| 5 | `black_litterman` | econometric | Kolm, Ma, Mulvey & Iyengar (2020)         | technical, fundamental, behavioral |

Equivalence guarantees — the central design decision:

- one shared backtest engine (`eval/backtest.py`); the trained RL policy is
  evaluated as just another weight-provider through it (`models/rl/policy.py`)
- identical transaction costs: 10 bps per side on turnover (median
  implementation shortfall of Frazzini, Israel & Moskowitz; Lesmond et al.
  1999 and Bikker et al. 2004 as sensitivity bounds), `eval.yaml: fees_bps`
- identical dynamic universe: quarterly top-50 reconstitution; exit below
  rank 50 → forced sale to cash (costed); delisting → cash at last price
- identical accounting granularity: the engine steps daily; rebalance
  frequency is a model property (config, default monthly = GKX horizon)

## 2. Prerequisites (data phase — separate work)

1. Panel file (name/path TBD; placeholder `data/processed/panel.parquet` in
   `config/eval.yaml`): long-tidy `(date, ric, *features)` for all universe
   members 1994–2026 — technical, fundamental (EDGAR-anchored forward-fill),
   behavioral (time-decayed) — strictly no look-ahead.
2. `data/interim/extra_prices.parquet`: `^GSPC`, `^VIX` + add `^IRX` to
   `yahoo.extra_symbols` in `config/data.yaml`. `^IRX` is a 13-week T-bill
   annualized YIELD, not a price — the engine converts it to a daily cash
   return (yield / 100 / 252).
3. Already present: `data/interim/universe.parquet` (quarter_end, ric,
   ticker, delisted, marketcap, rank), `data/interim/prices.parquet`
   (daily OHLCV).

## 3. Architecture

```
src/factor_weaver/
├── cli.py, math.py
├── workflows/              # build_dataset, train, evaluate
├── data/                   # MODULE 1: raw sources -> panel file
├── models/                 # MODULE 2: ALL weight-producing models
│   ├── __init__.py         # weight-provider interface + registry (name -> factory)
│   ├── simple.py           # equal_weight (1/N), index_buy_hold (^GSPC)
│   ├── optimize.py         # shared tangency(mu, cov, rf, cap) via PyPortfolioOpt
│   ├── mean_variance.py    # rolling mu + Ledoit-Wolf cov -> tangency
│   ├── black_litterman.py # Kolm et al. (2020) BLB
│   ├── ml_forecast.py     # GKX GBRT -> shared tangency
│   └── rl/                 # RL model
│       ├── env.py          # Gymnasium environment
│       ├── model.py        # cross-stock transformer + actor-critic
│       ├── ppo.py          # training loop
│       └── policy.py       # trained-policy adapter (weight-provider)
└── eval/                   # MODULE 3: evaluation only
    └── backtest.py         # shared daily engine + metrics
```

A model is a pure function: `(t, universe members, panel history ≤ t) →
{ric: weight}` with Σweights ≤ 1 (remainder = risk-free cash). `models/rl/`
absorbs the previous top-level `rl/` module so that everything producing
weights lives under `models/`.

Configs: `config/eval.yaml` (engine: fees, window, rebalance default, rf,
panel path, MLflow) + `config/models.yaml` (per-model params).

## 4. Shared backtest engine — `eval/backtest.py`

- daily loop over the evaluation window
- at rebalance dates (per-model config, default monthly): model → target
  weights over current members; cost = Σ|Δw| × `fees_bps`; weights drift with
  prices between rebalances
- quarter boundary: members exiting the top-50 → forced sale to cash at
  close, costed at the same rate; entrants receive weight at the next
  rebalance
- delisting → position converted to cash at last available price
- cash yields the `^IRX`-derived daily return
- metrics: CAGR, annualized volatility, Sharpe, Sortino, max drawdown,
  Calmar, average turnover; outputs: equity curve, weights history, metrics

## 5. Models

### 5.1 `simple.py` — equal_weight, index_buy_hold

- **equal_weight**: 1/N over current universe members at each rebalance; the
  hardest naive baseline (DeMiguel et al. 2009).
- **index_buy_hold**: single `^GSPC` purchase at window start (single cost
  event), never rebalanced. `^GSPC` is a price index (no dividends) —
  footnoted in the thesis.

### 5.2 `optimize.py` — shared tangency optimizer

`max_sharpe` long-only with per-name weight cap via PyPortfolioOpt, used
unchanged by `mean_variance`, `ml_forecast`, `black_litterman` — optimizer
equivalence across the family.

### 5.3 `mean_variance.py` — Markowitz (1952)

Rolling lookback (default 5y daily) → sample mean μ, Ledoit–Wolf covariance Σ
→ shared tangency. Classical baseline; same optimizer inputs shape as the
other optimizer-based models, differing only in how μ (and Σ) is produced.

### 5.4 `ml_forecast.py` — Gu, Kelly & Xiu (2020) GBRT + Ma et al. (2021) MV

Replicates the GKX forecasting methodology on our panel characteristics:

- monthly horizon; target = next-month excess return
- features = panel characteristics (technical, fundamental, behavioral
  composites); GKX cross-sectional rank standardization each month
- GBRT = `sklearn.HistGradientBoostingRegressor`; grid (leaves L, shrinkage
  ν, trees B) per GKX Internet Appendix B.2, tuned on a temporally ordered
  validation split; annual refit, monthly predictions
- predicted returns → shared tangency optimizer (Ma et al. forecast→MV
  pipeline, evaluated net of transaction fees)
- no look-ahead: training rows strictly < t (EDGAR-anchored panel)
- note: GKX predictability is strongest in microcaps (Jo et al. 2026); the
  top-50 large-cap universe makes this a conservative test

### 5.5 `black_litterman.py` — Kolm et al. (2020) Black-Litterman-Bayes

Single-paper replication of the BLB framework on US cross-sectional equity
factor views:

- prior: benchmark/equilibrium prior from top-50 cap weights (reverse
  optimization π = δΣw_mkt), shrinkage covariance
- views: factor risk-premium views mapped to stock-level expected returns
  via the paper's APT-style structure — momentum (technical), value +
  quality (fundamental), sentiment/attention (behavioral; additional factor
  views — the framework is generic in factor choice)
- posterior: the paper's closed-form E[r] and covariance (numpy; formulas
  replicated, not reinvented)
- weights: posterior → shared tangency, long-only + weight cap; the
  cap-weighted prior is the implicit benchmark
- τ/δ defaults per paper, in `config/models.yaml`

### 5.6 `models/rl/` — the thesis model

Gymnasium env, cross-stock transformer encoder, Dirichlet policy head,
hand-rolled PPO (per `docs/methodology.md`); `policy.py` exposes the trained
policy through the same weight-provider interface, so the engine treats it
identically to benchmarks.

## 6. Workflow & tracking — `workflows/evaluate.py`

`factor-weaver eval [--models ...] [--start --end]` — loads configs, panel,
prices, universe, rf; runs each selected model through the shared engine.
MLflow: one run per model/window — params (model, fees, window, key
hyperparams), metrics (engine metrics), artifacts (equity curve, weights
history, config snapshot) — under a shared experiment; later RL runs join the
same experiment, so the final comparison table is one query.

## 7. Dependencies

Added to `pyproject.toml`: `scikit-learn` (GBRT, Ledoit–Wolf),
`PyPortfolioOpt` (tangency optimizer, risk models), `mlflow` (tracking —
already in the tentative stack). RL training deps (torch, gymnasium) are
added with `models/rl/` (Phase 3).

## 8. Tests

- `tests/test_backtest.py` (synthetic): cost math, forced exit at quarter
  boundary, delisting → cash, `^IRX` yield conversion, 1/N weight sums
- `tests/test_models.py` (synthetic panel): providers return valid simplex
  weights; tangency respects long-only + cap; BLB posterior sanity (zero
  views → prior); `ml_forecast` training cutoff strictly < t, rank
  preprocessing correctness

## 9. Phases

- **Phase 0 (data, separate)**: complete the data pipeline → panel file +
  `^IRX` in `extra_prices.parquet`.
- **Phase 1** (needs only prices/universe/extra_prices): engine + `simple` +
  `mean_variance` + `optimize` + workflow + MLflow + tests.
- **Phase 2** (blocked on panel): `ml_forecast` + `black_litterman` + tests.
- **Phase 3** (blocked on RL training): `models/rl/` env/model/ppo +
  `policy.py` adapter; final comparison table.

## 10. References

Full citations in `docs/literature.md` (Sources). Replication targets and
cost sources: DeMiguel et al. (2009); Markowitz (1952); Gu, Kelly & Xiu
(2020); Ma et al. (2021); Kolm, Ma, Mulvey & Iyengar (2020); He & Litterman
(2002); Frazzini, Israel & Moskowitz (2018); Lesmond et al. (1999); Bikker
et al. (2004); Jo et al. (2026); Drobetz et al. (2020).
