# Methodology

## Environment

- total data
  - ~2005-2025 daily
  - $250 \times 20 = 5000$ steps
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
  - calculate transaction fees, slippage (based on average daily traded volume?), $V_{t+1}$, $w_{i,t}^+$
- libraries
  - <https://github.com/AI4Finance-Foundation/FinRL> or <https://github.com/farama-foundation/gymnasium>

## Model architecture

- encoder
  - transformer or convolutional NN or autoencoder or deep belief network
- output
  - vector of 100 (+extra assets) weights $\sum w_i = 1$, no short-selling
- RL type
  - actor-critic model
  - proximal policy optimization (PPO) training
- explainable architecture?
  - attention
- crucial features
  - permutation equivariance
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
- benchmark
  - compare to more traditional portfolio optimization models and strategies
    - min variance
    - 1/N
    - ...
  - compare metrics with other papers
