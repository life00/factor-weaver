# Models

- all weight-producing models live in `src/factor_weaver/models/`
- interface
  - pure function: `(t, universe members, panel history ≤ t) → {ric: weight}`
  - Σweights ≤ 1, remainder = risk-free cash
  - registered by CLI name, evaluated through ONE shared engine (`eval/backtest.py`)
  - identical costs, universe transitions, delistings, accounting across models, including the RL policy (`models/rl/policy.py`)
- implementation plan + phases: `PLAN.md`

## Shared engine (`eval/backtest.py`)

- granularity
  - daily steps for every model; rebalance frequency is a model property (config, default monthly = GKX horizon)
- costs
  - fixed 10 bps per side on turnover (`eval.yaml: fees_bps`)
  - median implementation shortfall (Frazzini, Israel & Moskowitz, 2018)
  - sensitivity bounds: Lesmond et al. (1999), Bikker et al. (2004)
- universe exits
  - quarter boundary: drop below top-50 rank → forced sale to cash at close (costed)
  - entrants get weight at next rebalance
- delisting
  - position converted to cash at last available price
- cash
  - daily risk-free return from `^IRX` yield (yield / 100 / 252)
- metrics
  - CAGR, annualized volatility, Sharpe, Sortino, max drawdown, Calmar, average turnover
- outputs
  - equity curve, weights history, metrics → `experiments/` + MLflow run

## equal_weight — 1/N

- naive diversification baseline; the hardest simple benchmark
- replicates DeMiguel et al. (2009)
- 1/N on each current member at each rebalance; no factor inputs
- config (`models.yaml`): rebalance frequency override only

## index_buy_hold — S&P500

- passive market baseline
- single `^GSPC` purchase at window start (single cost event), never rebalanced
- `^GSPC` is a price index (no dividends) — footnote in the thesis

## mean_variance

- classical optimization baseline; inherits the estimation-error sensitivity that 1/N exploits
- replicates Markowitz (1952) max-Sharpe tangency, long-only
- rolling lookback (default 5y daily) → sample mean μ, Ledoit-Wolf covariance Σ (sklearn) → shared `optimize.tangency` with per-name weight cap
- config: `lookback_days`, `weight_cap`

## black_litterman

- econometric benchmark: factor information integrated into a market-consistent portfolio; estimation-error robust via Bayesian shrinkage toward equilibrium
- replicates Kolm, Ma, Mulvey & Iyengar (2020) BLB; canonical background: He & Litterman (2002)
- inputs: top-50 market caps (prior), panel factor composites (views), prices (covariance)
- method
  - prior: reverse optimization from cap weights (π = δΣw_mkt), shrinkage covariance
  - views: factor risk-premium views mapped to stock-level expected returns via the paper's APT-style structure
    - momentum ← technicals; value + quality ← fundamentals; sentiment + attention ← behavioral (additional factor views, the framework is generic in factor choice)
  - posterior: the paper's closed-form E[r], covariance (numpy)
  - weights: posterior → shared `optimize.tangency`, long-only + cap; cap-weighted prior = implicit benchmark
- config: `tau`, `delta`, `factor_views`, `weight_cap`
- no single BL paper matches this data exactly; BLB is the closest (US cross-sectional equity factors, closed-form posterior, cap-weight benchmark priors)
- rejected alternatives
  - de la Torre-Torres et al. (2022): stock-level US, but price-history-only views
  - Dewandaru et al. (2015): US stock-level BL, but Islamic-universe style rotation
  - Soltanabadi et al. (2026): factor views at stock level, but Tehran market
  - Punyaleadtip et al. (2023): ML views — overlaps ml_forecast's role

## ml_forecast

- ML benchmark using the same feature stack as the RL model; tests whether RL adds value over supervised ML + optimization given an identical information set
- replicates Gu, Kelly & Xiu (2020) GBRT forecasting + Ma et al. (2021) forecast→mean-variance portfolio step (net of fees)
- method
  - monthly horizon; target = next-month excess return
  - GKX cross-sectional rank standardization of characteristics each month
  - sklearn HistGradientBoostingRegressor; grid (leaves, shrinkage, trees) per GKX Internet Appendix B.2, tuned on a temporally ordered validation split
  - annual refit (GKX cadence), monthly predictions
  - predicted returns → shared `optimize.tangency`
  - training rows strictly < t (no look-ahead; EDGAR-anchored panel)
- config: `horizon`, `refit`, `grid`, `weight_cap`
- GKX predictability is strongest in microcaps (Jo et al., 2026); the top-50 large-cap universe makes this a conservative test

## rl

- the thesis model; training machinery in `models/rl/` (env, model, ppo) per `docs/methodology.md`
- `models/rl/policy.py` adapts the trained policy to the same weight-provider interface → the shared engine treats it identically to benchmarks
