"""Weight-provider models: everything producing portfolio weights.

A model is a pure function (t, universe members, panel history <= t) ->
weights (dict ric -> weight, sum = 1, long-only; cash is engine-only), evaluated
through the shared engine in eval/backtest.py so accounting (costs, dynamic
universe, delistings) is identical for benchmarks and the RL policy alike.
See PLAN.md and docs/models.md.
"""

from functools import partial
from typing import Any, Callable

import pandas as pd

from factor_weaver.models import black_litterman, mean_variance, ml_forecast, simple

Provider = Callable[[pd.Timestamp, list[str], pd.DataFrame], dict[str, float]]


def _rl(cfg: dict[str, Any]) -> Provider:
    """RL provider factory (lazy: torch is a Phase 3 dependency)."""
    from factor_weaver.models.rl import policy

    return partial(policy.policy, cfg)


# CLI name -> factory(cfg) -> weight-provider. Order defines the `eval` default.
REGISTRY: dict[str, Callable[[dict[str, Any]], Provider]] = {
    "equal_weight": lambda cfg: simple.equal_weight,
    "index_buy_hold": lambda cfg: simple.index_buy_hold,
    "mean_variance": lambda cfg: mean_variance.mean_variance,
    "ml_forecast": lambda cfg: ml_forecast.ml_forecast,
    "black_litterman": lambda cfg: black_litterman.black_litterman,
    "rl": _rl,
}


def _train_rl(cfg: dict[str, Any], args: Any) -> None:
    from factor_weaver.models.rl import ppo

    ppo.train(cfg, args)


# CLI name -> trainer(cfg, args); the RL policy is the only trainable model today.
TRAINERS: dict[str, Callable[[dict[str, Any], Any], None]] = {"rl": _train_rl}
