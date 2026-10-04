"""Rolling technical indicators computed from daily OHLCV."""

import logging

log = logging.getLogger(__name__)


def compute_technicals(cfg: dict) -> None:
    """Compute rolling technical indicators from daily OHLCV.

    Reads: <prices.out>
    Writes: <technicals.out> (columns: date, ric, ma_20, ma_50, rsi_14, ...)
    """
    log.warning("technicals: not implemented yet; no output written")
