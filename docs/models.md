# Models

- all weight-producing models live in `src/factor_weaver/models/`
- interface
  - pure function: `(t, universe members, panel history ≤ t) → {ric: weight}`
  - Σweights = 1, long-only; cash is engine-only (forced liquidation)
  - registered by CLI name, evaluated through ONE shared engine (`eval/backtest.py`)
  - identical costs, universe transitions, delistings, accounting across models, including the RL policy (`models/rl/policy.py`)
- implementation plan + phases: `PLAN.md`

## Shared engine (`eval/backtest.py`)

- granularity
  - daily steps for every model; rebalance frequency is a model property (config; benchmarks monthly = GKX horizon, RL daily)
- costs
  - fixed 10 bps per side on turnover (`eval.yaml: fees_bps`)
  - median implementation shortfall (Frazzini, Israel & Moskowitz, 2018)
  - sensitivity bounds: Lesmond et al. (1999), Bikker et al. (2004)
- universe exits
  - quarter boundary: drop below top-50 rank → forced sale to cash at close (costed)
  - delisting: forced liquidation to cash at last available price (costed)
  - entrants get weight at next rebalance
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
- deviations: top-50 quarterly universe; monthly rebalance; net-of-cost engine

## index_buy_hold — S&P500

- passive market baseline
- single `^GSPC` purchase at window start (single cost event), never rebalanced
- `^GSPC` is a price index (no dividends) — footnote in the thesis

## mean_variance

- classical optimization baseline; inherits the estimation-error sensitivity that 1/N exploits
- replicates Markowitz (1952) max-Sharpe tangency, long-only
- rolling lookback (default 5y daily) → sample mean μ, Ledoit-Wolf covariance Σ (sklearn) → shared `optimize.tangency` with per-name weight cap
- config: `lookback_days`, `weight_cap`
- deviations: top-50 quarterly universe; Ledoit-Wolf covariance; monthly rebalance; net-of-cost engine

## black_litterman

- econometric benchmark: factor views integrated into an APT model; Bayesian shrinkage instead of raw estimation error
- replicates Kolm & Ritter (2021) BLB; derivation: Kolm & Ritter (2017); canonical background: He & Litterman (2002)
- inputs: panel factor composites (loadings + views), prices (covariance)
- method (paper eqs. 25–27, 29; numpy)
  - APT: r = Xf + ε, ε ~ N(0, D); loadings X = standardized composites — momentum ← technicals; value + quality ← fundamentals; sentiment + attention ← behavioral; D = winsorized rolling residual variances
  - factor returns: cross-sectional OLS f̂ = (X'X)⁻¹X'r (paper's data-driven route)
  - prior: π_f ~ N(ξ, V); ξ = expanding mean of f̂, V = factor covariance
  - views: q = one-period-ahead AR(1) forecast of each factor premium on an expanding window; Ω = diag(v_ii) (eq. 24; paper uses AICc ARIMA)
  - posterior: eqs. 25–27 → E[r], Cov[r]
  - weights: posterior → shared `optimize.tangency`, long-only + cap (eq. 29)
- no τ: shrinkage controlled by prior covariance V and view uncertainty Ω
- config: `factors`, `prior`, `view_uncertainty`, `risk_aversion`, `winsorize`, `weight_cap`
- deviations: top-50 quarterly universe vs paper's top-2000 daily; 5 composites vs market/size/value/momentum/vol + ~70 industries; monthly vs daily rebalance; net-of-cost engine vs pre-cost
- rejected alternatives
  - de la Torre-Torres et al. (2022): stock-level US, but price-history-only views
  - Dewandaru et al. (2015): US stock-level BL, but Islamic-universe style rotation
  - Soltanabadi et al. (2026): factor views at stock level, but Tehran market
  - Punyaleadtip et al. (2023): ML views — overlaps ml_forecast's role

## ml_forecast

- ML benchmark using the same feature stack as the RL model; tests whether RL adds value over supervised ML + optimization given an identical information set
- replicates Gu, Kelly & Xiu (2020) GBRT (Algorithm 4, Appendix B.2; hyperparameters Internet Appendix Table A.5) + Ma et al. (2021) forecast→mean-variance portfolio step (net of fees)
- method
  - monthly horizon; target = next-month excess return
  - GKX cross-sectional rank standardization of characteristics each month
  - sklearn GradientBoostingRegressor (max_depth=L, learning_rate=ν, n_estimators=B per Table A.5), tuned on a temporally ordered validation split
  - annual refit (GKX cadence), monthly predictions
  - predicted returns → shared `optimize.tangency`
  - training rows strictly < t (no look-ahead; EDGAR-anchored panel)
- config: `horizon`, `refit`, `grid`, `weight_cap`
- deviations: composites vs GKX's 94 characteristics; top-50 large-cap vs all CRSP; sklearn GBRT vs paper's gbm; costs net (GKX gross, Ma net)
- GKX predictability is strongest in microcaps (Jo et al., 2026); the top-50 large-cap universe makes this a conservative test

## rl

- the thesis model; training machinery in `models/rl/` (env, model, ppo) per `docs/methodology.md`
- rebalances daily (native cadence; benchmarks monthly)
- `models/rl/policy.py` adapts the trained policy to the same weight-provider interface → the shared engine treats it identically to benchmarks
