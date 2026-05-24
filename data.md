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
  - all S&P100 companies in last 20 years
- method
  - rolling top 50 companies in S&P100
  - redefine list in each period

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
    - sentiment
- extra assets
  - risk-free
    - price, technical, behavioral
  - S&P100 stock index?
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
  - <https://arxiv.org/abs/2402.06698>
  - <https://www.alphavantage.co/documentation/#intelligence>
- fundamental
  - <https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets>
    - <https://github.com/dgunning/edgartools>
  - <https://www.alphavantage.co/documentation/#fundamentals>
  - <https://financialdatadb.com/> (supposedly available for MUNI students)
