# Methodology

## Environment

- total data
  - ~1994-2026 daily (universe build starts 1994, see `config/data.yaml`)
  - $250 \times 32 \approx 8000$ steps
- initial state
  - in $t=0$ everything is in risk-free
- stock selection
  - dynamic equity universe construction
  - top ranked 50 companies in S&P500 in each period
    - if company falls below rank 50 $\to$ assets converted to risk-free
  - bankruptcies, mergers, delistings, etc. is handled appropriately
    - bankruptcies $\to$ loss
    - mergers, delistings, $\to$ risk-free
- transaction costs
  - fixed fee per side on turnover: 10 bps (median implementation shortfall; Frazzini, Israel & Moskowitz, 2018)
  - sensitivity bounds: Lesmond et al. (1999), Bikker et al. (2004)
  - identical accounting for the RL model and all benchmarks via the shared engine (see `docs/models.md`)
- stack (tentative)
  - RL environment: Gymnasium gives full control over step logic compared to FinRL
  - Deep learning: PyTorch has strong RL ecosystem support and provides MultiheadAttention and Dirichlet distributions
  - PPO: hand-rolled with CleanRL as reference since we need custom encoder and policy heads
  - Encoder: cross-stock transformer with MultiheadAttention over the stock dimension
  - Policy head: Dirichlet to enforce the simplex constraint (no short-selling), as described in Andre & Coqueret (2020)
  - Benchmarks: scikit-learn (GBRT, Ledoit-Wolf covariance) and PyPortfolioOpt (tangency optimizer) for the non-RL models (see `docs/models.md`)
  - Data: pandas with parquet storage
  - Config: YAML files
  - Tracking: MLflow for experiment tracking and resumption
  - Linting and typing: ruff and pyright

## Model architecture

- encoder
  - transformer or convolutional NN or autoencoder or deep belief network
- output
  - vector of 50 weights $\sum w_i = 1$, no short-selling
- RL type
  - actor-critic model
  - proximal policy optimization (PPO) training
- explainable architecture
  - attention
- crucial features
  - transformer cross-stock attention
  - regularization
    - dropout
- reward function
  - maximize sharpe or sortino ratio
  - accounts for transaction costs and slippage costs
  - requires minimum $r_f+$ excess return requirement (based on risk preference)
    - otherwise penalizes

## Evaluation

- metrics
  - RL-specific
  - financial
    - return, sharpe, sortino
    - train and test periods
- benchmarks (see `docs/models.md` and `PLAN.md`)
  - all models evaluated through one shared backtest engine: identical costs, dynamic universe, and accounting
  - standard: mean-variance (max-Sharpe tangency), 1/N, S&P500 buy and hold
  - factor-based: ml_forecast (Gu, Kelly & Xiu, 2020 GBRT + Ma et al., 2021 mean-variance), black_litterman (Kolm et al., 2020)
  - MLflow tracking shared with the RL runs
  - compare metrics with other papers
