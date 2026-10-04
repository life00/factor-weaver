"""Assemble the long-tidy panel: prices, technicals, fundamentals, behavior."""

import logging

log = logging.getLogger(__name__)


def build_panel(cfg: dict) -> None:
    """Merge all features into a single long-tidy panel, strictly without look-ahead.

    Fundamentals: as-reported values forward-filled from their report date
    (LSEG source to be added); freshness counter for quarterly data.
    Behavioral: time-decayed MarketPsych features (to be added).

    Reads: <prices.out>, <technicals.out> (+ fundamentals/behavior when implemented)
    Writes: <panel.out> (columns: date, ric, *features)
    """
    log.warning("panel: not implemented yet; no output written")
