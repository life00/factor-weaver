# Features

Shared technical and fundamental features for all models (RL, `ml_forecast`, `black_litterman`). Behavioral features: `docs/data.md`. Paper notes: `papers/notes/<slug>.md`.

## Selection

- why: standard characteristics of the canonical factor and ML literature, with evidence they predict returns in large stocks
  - [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns], [medhat-2022-short-term-momentum]
- literature only: no screening on the project's own returns ([bartram-2021-navigating-factor-zoo], [yan-2017-fundamental-data-mining])
- rule: standard, predictive, ≥2 anchors, one per theme, computable for every model
- one feature set for all models; normalization is model-specific
- rank: project assessment of large-stock evidence and usefulness; not a model weight

## Summary

Anchors: FF = [fama-2015-five-factor], GKX = [gu-2020-empirical-asset-pricing-ml], L = [lewellen-2015-cross-section-expected-returns], MS = [medhat-2022-short-term-momentum]. Large-stock t-stats from L Table 2 unless noted.

|rank|feature|group|BLB|anchors|large-stock evidence|note|
|---|---|---|---|---|---|---|
|1|`mom12_1`|technical|momentum|GKX, L|t = 5.05|strongest slope; Carhart factor|
|2|`vol`|technical|—|GKX, L|t = −3.76|low-vol strongest in large stocks (GKX)|
|3|`nsi`|fundamental|quality|GKX, L|t = −3.23|stronger among large stocks|
|4|`size`|technical|—|FF, GKX, L|t = −3.84|narrow spread in top 50|
|5|`bm`|fundamental|value|FF, L|t = 2.31–3.62|FF big-stock HML weak|
|6|`op`|fundamental|quality|FF, GKX|ROA t = 2.89|evidence is for ROA|
|7|`rev1m`|technical|—|GKX, MS|≈0 alone; 0.53%/m with `turnover` (MS)|use with `turnover`; high trading|
|8|`turnover`|technical|—|GKX, MS|not significant alone|conditions `rev1m`|
|9|`agr`|fundamental|quality|FF, GKX|not significant|weak in big stocks|
|10|`sp`|fundamental|value|GKX, L|not significant|second value feature|

## Conventions

- clock: daily per (date, ric); monthly models sample on rebalance dates
- windows: trading days, 21 = 1m, 252 = 12m, 756 = 36m
- prices: RTS-adjusted (splits + dividends) → price ratios are total returns
- market equity: `ME_t` = last quarter-end `marketcap` × `close_t / close_q`
  - shortcut: ignores share changes within the quarter
- shares: split-adjusted, not dividend-adjusted; LSEG field to identify
- fundamentals: LSEG `TR.F.*`, quarterly; flows TTM, stocks at latest quarter
- availability: from LSEG announcement date; else 4 months after period end [gu-2020-empirical-asset-pricing-ml]
- financials: kept; all features defined for banks and insurers

## Features (rank order)

- 1 `mom12_1` — momentum
  - `close_{t−21} / close_{t−252} − 1`
  - anchors: [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]
- 2 `vol` — low risk
  - `std(r_{t−251..t}) · √21`, r = daily return
  - anchors: [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]
- 3 `nsi` — net share issuance
  - `log(shares_t / shares_{t−756})`
  - anchors: [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]
- 4 `size`
  - `log ME_t`
  - anchors: [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]
- 5 `bm` — value
  - `BE / ME_t`, BE = `TR.F.ShHoldEqCom`; NaN if BE ≤ 0
  - anchors: [fama-2015-five-factor], [lewellen-2015-cross-section-expected-returns]
- 6 `op` — profitability
  - `(revenue − COGS − SG&A − interest)_TTM / BE`
  - missing expense items = 0 (FF rule), so defined for banks
  - fields: `TR.F.TotRevenue`, `TR.F.COGSTot`, `TR.F.SGATot`, `TR.F.IntrExpn`
  - anchors: [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml]
- 7 `rev1m` — short-term reversal
  - `close_t / close_{t−21} − 1`
  - read together with `turnover`
  - anchors: [gu-2020-empirical-asset-pricing-ml], [medhat-2022-short-term-momentum]
- 8 `turnover` — liquidity
  - `Σ volume_{t−20..t} / shares_t`
  - anchors: [gu-2020-empirical-asset-pricing-ml], [medhat-2022-short-term-momentum]
- 9 `agr` — investment
  - `assets_q / assets_{q−4} − 1`, `TR.F.TotAssets`
  - anchors: [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml]
- 10 `sp` — value (second)
  - `revenue_TTM / ME_t`, `TR.F.TotRevenue`
  - anchors: [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]

## Rejected

- `beta` — same theme as `vol`, weaker
- Amihud illiquidity — not scale-free, covered by `turnover`
- `ep` — single anchor
- gross profitability — undefined for banks
- ROE / ROA — same theme as `op`
- accruals — anchors conflict, undefined for banks
- leverage, dividend yield — not significant
- RSI, MACD, Bollinger, SMA ratios — no independent anchor, duplicate momentum
