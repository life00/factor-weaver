"""Weight-provider models: everything producing portfolio weights.

A model is a pure function (t, universe members, panel history <= t) ->
weights (dict ric -> weight, sum <= 1, remainder = risk-free cash), evaluated
through the shared engine in eval/backtest.py so accounting (costs, dynamic
universe, delistings) is identical for benchmarks and the RL policy alike.
See PLAN.md and docs/models.md.
"""

REGISTRY: dict = {}  # CLI name -> model factory (populated in Phase 1, PLAN.md)
