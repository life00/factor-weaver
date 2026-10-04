# Data

## Sample

- criteria
  - avoid selection bias
  - avoid survivorship bias
- frequency
  - daily
- period
  - 1994-2026 (universe build starts 1994, when LSEG joiner/leaver records begin)
- index
  - all S&P500 companies since 1994
- method
  - rolling top 50 companies in S&P500
  - redefine list in each period
  - exclude RICs with no price content (`universe.exclude_rics`); next-ranked company fills the slot
- alignment
  - forward-fill fundamentals with per-group staleness counter
  - time-decay for behavioral features

## Variables

- for each stock
  - current passive weight
  - price
    - daily OHLCV
  - technical (can be excluded?)
    - moving averages
    - volume indicators
  - fundamental
    - financial ratios
    - market info
  - behavioral
    - attention
      - media coverage
      - Google search intensity
    - sentiment
      - positive/negative sentiment based on posts or news
- extra assets
  - risk-free - `^IRX` (T-bill annualized yield, not a price)
  - S&P500 stock index - `^GSPC`
- market-wide indicators
  - VIX - `^VIX`

## Sources

- fundamental
  - <https://financialdatadb.com/> — raw xlsx files (26 `*_tickers.xlsx` A-Z, one sheet per ticker) live in `data/raw/financialdatadb/us_financials/`
- equity universe
  - LSEG data API — S&P500 constituent list, joiner/leaver history, RIC mapping; market cap via `TR.CompanyMarketCap` (fallback `TR.F.MktCap`) for top-50 selection
  - `universe.build_universe` also writes `data/interim/companies.parquet`, the distinct RIC → ticker/name/permid registry used by later steps
- filing dates
  - <https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets> — EDGAR submissions API for 10-Q filing dates (anchors fundamental alignment, avoids look-ahead bias)
- price
  - LSEG data API — daily OHLCV (RTS-adjusted), primary source; per-RIC cache in `data/raw/lseg/prices/`
  - stale RICs retargeted via `lseg.ric_fallbacks` (FSR.N^B01 → USB.N, KHC.OQ → KHC.N), rows relabelled
  - <https://finance.yahoo.com/> via `yfinance` — fallback for remaining gaps (validated against the universe window) plus config index/indicator series (`data/interim/extra_prices.parquet`); per-symbol cache in `data/raw/yahoo/prices/`
- technical
  - computed from prices (moving averages, volume indicators)
- behavioral
  - <https://huggingface.co/datasets/Brianferrell787/financial-news-multisource>
  - sibling repo `market-behavior-archive` (pre-computed sentiment/attention parquet)

## Issues

### Universe

- **Joiner/leaver history starts with a baseline snapshot in 1994**: phantom "Joiner"
  events for companies already in the index pre-1994. Top-50 universe should be unaffected
- **No market cap for some retired RICs**: a few delisted RICs (`^`-suffixed)
  return nothing for `TR.CompanyMarketCap` or `TR.F.MktCap`. Dropped from top-50 ranking in
  their active quarters; only names near the 1999-2001 boundary are affected.
- **Membership ~20 names short pre-2000**: the joiner/leaver file has ~20 more Leaver than
  real Joiner events before 2000, so reconstructed membership counts 477-505 vs. ~500
  (1994: 478). Top-50 universe should be unaffected.

### Prices

- **Retired RICs with no price content**: FSR.N^B01 sourced from USB.N (same PermID,
  `lseg.ric_fallbacks`); ENE.N^A02 has no LSEG or Yahoo content and is excluded
  (`universe.exclude_rics`), next-ranked company backfills its 2 quarters (2000Q3/Q4)
- **Adjustment basis differs across vendors**: LSEG RTS vs Yahoo split/dividend-adjusted
  (back-adjusted on each dividend); Yahoo rows only fill LSEG gaps
- **Existence-based caches**: delete `data/raw/lseg/prices/` and `data/raw/yahoo/prices/`
  to refetch after changing the universe window
