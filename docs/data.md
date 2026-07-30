# Data

## Sample

- criteria
  - avoid selection bias
  - avoid survivorship bias
- frequency
  - daily
- period
  - 20 years
- index
  - all S&P500 companies in last 20 years
- method
  - rolling top 50 companies in S&P500
  - redefine list in each period
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
  - risk-free
    - price, technical, behavioral
  - S&P500 stock index?
    - price, technical, behavioral
- market-wide indicators
  - VIX
  - ...?

## Sources

- fundamental
  - <https://financialdatadb.com/> — primary entry point: raw xlsx files (26 files A-Z, one sheet per ticker) live in `data/raw/financialdatadb/`
- equity universe
  - <https://github.com/fja05680/sp500> — S&P500 constituent list, compared with financialdatadb market cap (row 87) for top-50 selection
- filing dates
  - <https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets> — EDGAR submissions API for 10-Q filing dates (anchors fundamental alignment, avoids look-ahead bias)
- price
  - <https://finance.yahoo.com/> — daily OHLCV via yfinance
- technical
  - computed from prices (moving averages, volume indicators)
- behavioral
  - <https://huggingface.co/datasets/Brianferrell787/financial-news-multisource>
  - sibling repo `market-behavior-archive` (pre-computed sentiment/attention parquet)
