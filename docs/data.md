# Data

## Data layout

```
data/
├── raw/        # untouched vendor downloads + sibling-repo behavioral parquet
├── processed/  # cleaned + aligned (ffill, staleness counter, time-decay); full date range
├── train/      # env-ready tensors/arrays for the training window
└── test/       # env-ready tensors/arrays for the test window
```

Transformations:
- `raw → processed` via `prepare-features` (alignment, ffill, staleness, time-decay)
- `processed → train/ + test/` via `build-dataset` (date-window split, tensorization for the env)

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

- <https://gemini.google.com/share/27db8be7a6bd>
- paid platforms
  - <http://eodhd.com/>
  - <https://data.nasdaq.com/databases/SF1>
- price
  - daily prices can be easily found anywhere
- technical
  - technical indicators can be calculated from prices
- behavioral
  - <https://huggingface.co/datasets/Brianferrell787/financial-news-multisource>
  - <https://www.alphavantage.co/documentation/#intelligence>
- fundamental
  - <https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets>
    - <https://github.com/dgunning/edgartools>
  - <https://www.alphavantage.co/documentation/#fundamentals>
  - <https://financialdatadb.com/> (supposedly available for MUNI students)
