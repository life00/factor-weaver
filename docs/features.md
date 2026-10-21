# Features

One stock-level feature set shared by all models (RL, `ml_forecast`, `black_litterman`). Papers in `papers/` are cited as `[slug]` (notes in `papers/notes/<slug>.md`); papers outside the corpus as Author (Year), with full references in `docs/literature.md`.

## Selection

- why: standard characteristics of the canonical factor and ML literature, with evidence they predict returns in large stocks
  - [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns], [medhat-2022-short-term-momentum]
- behavioral: required by the research question; anchored on the most-cited firm-level news studies (the peer-reviewed MarketPsych studies found are index- or sector-level)
  - [tetlock-2008-more-than-words], [heston-2017-news-vs-sentiment], [da-2011-in-search-of-attention]
- literature only: no screening on the project's own returns ([bartram-2021-navigating-factor-zoo], [yan-2017-fundamental-data-mining])
- rule: standard, predictive, ≥2 sources, one per theme, computable for every model
  - exception: sales-to-price backs up book-to-market when book equity ≤ 0
- stock-level only: market-wide series (VIX, T-bill, S&P500) take the same value for every stock on a date; they remain engine and benchmark inputs
- rank: project assessment of large-stock evidence and source credibility; not a model weight

## Summary

t-statistics from Lewellen (2015) Table 2 (stocks above the NYSE median, 15-variable model) unless noted.

|rank|feature|group|sources|evidence|
|---|---|---|---|---|
|1|Momentum (12-1 month return)|technical|Lewellen (2015); Gu et al. (2020)|t = 5.05; strongest among large stocks (Gu et al.)|
|2|Volatility (12 months)|technical|Lewellen (2015); Gu et al. (2020)|t = −3.76; low-volatility effect strongest among large stocks (Gu et al.)|
|3|Net share issuance (36 months)|fundamental|Lewellen (2015); Gu et al. (2020)|t = −3.23; stronger among large stocks|
|4|Size (log market cap)|technical|Fama & French (2015); Gu et al. (2020); Lewellen (2015)|t = −3.84 with controls, −1.33 alone|
|5|Book-to-market|fundamental|Fama & French (2015); Lewellen (2015)|t = 2.31–3.62; big-stock value premium t = 1.69 (Fama & French)|
|6|Operating profitability|fundamental|Fama & French (2015); Gu et al. (2020)|return on assets as proxy, t = 2.89; big-stock premium 0.17%/month (Fama & French)|
|7|Short-term reversal (1-month return)|technical|Gu et al. (2020); Medhat & Schmeling (2022)|alone −0.03%/month in the largest size decile; high-turnover winners +0.53%/month in megacaps, t = 2.53 (Medhat & Schmeling)|
|8|Share turnover (1 month)|technical|Gu et al. (2020); Medhat & Schmeling (2022)|alone t = −0.26 (12-month version); conditions reversal|
|9|News sentiment|behavioral|Tetlock et al. (2008); Heston & Sinha (2017)|S&P 500 firms: next-day return −3.2 bps per SD of negative words (Tetlock et al.); weekly sentiment spread +2.15% over the next 13 weeks, not explained by momentum (Heston & Sinha)|
|10|Media attention (abnormal buzz)|behavioral|Da et al. (2011); Heston & Sinha (2017)|+18.7 bps next week per SD of abnormal attention, largely reversed within a year, present only in the smaller half of the Russell 3000 (Da et al.); news vs. no news insignificant in the largest size decile, t = 0.18 (Heston & Sinha)|
|11|Asset growth|fundamental|Fama & French (2015); Gu et al. (2020)|t = −0.82; big-stock premium t = 1.03–2.00 (Fama & French)|
|12|Sales-to-price|fundamental|Gu et al. (2020); Lewellen (2015)|t = 1.16|

## Conventions

- clock: daily per (date, RIC); monthly models sample on rebalance dates
- windows: trading days for prices (21 = 1 month, 252 = 12 months, 756 = 36 months); calendar days for behavioral data (MarketPsych publishes on weekends)
- prices: LSEG split-, spin-off- and dividend-adjusted closes, Yahoo fallback on the same basis → close ratios are total returns
- volume: LSEG consolidated volume (company queried by PermID; 10 retired companies keep exchange volume, `docs/data.md`); NASDAQ before 2004 not halved for double counting
- market equity: `ME_t` = last quarter-end market cap × `close_t / close_q`
  - shortcut: ignores share changes and counts dividends since quarter end (≤ ~1%)
- shares outstanding: split-adjusted; LSEG field to identify
- fundamentals: LSEG `TR.F.*`, quarterly; flows over the trailing twelve months (TTM), stocks at the latest quarter
- availability
  - fundamentals: from the LSEG report date, else 4 months after period end [gu-2020-empirical-asset-pricing-ml]
  - behavioral: MarketPsych day d covers the 24 h to 15:30 ET → usable at the close of d (the 3:30 pm news cutoff of [tetlock-2008-more-than-words]); no row = zero buzz
- financials: kept; every feature is defined for banks and insurers

## Features (rank order)

- 1 Momentum (12-1 month return) — momentum
  - `close_{t−21} / close_{t−252} − 1`: months −12 to −2, skipping the reversal month
  - data: daily closes
  - sources: [lewellen-2015-cross-section-expected-returns], [gu-2020-empirical-asset-pricing-ml]
- 2 Volatility (12 months) — low risk
  - `std(r_{t−251..t}) · √21`, r = daily total return
  - data: daily closes
  - sources: [lewellen-2015-cross-section-expected-returns], [gu-2020-empirical-asset-pricing-ml]
- 3 Net share issuance (36 months) — issuance
  - `log(shares_t / shares_{t−756})`
  - data: shares outstanding
  - sources: [lewellen-2015-cross-section-expected-returns] (the 12-month version is insignificant), [gu-2020-empirical-asset-pricing-ml] (1-year version; standard input, importance not reported)
- 4 Size (log market cap) — size
  - `log ME_t`
  - data: LSEG market cap, daily closes
  - sources: [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]
  - narrow spread within the top 50; mainly a control
- 5 Book-to-market — value
  - `BE / ME_t`, BE = common equity `TR.F.ShHoldEqCom`; missing if BE ≤ 0
  - sources: [fama-2015-five-factor], [lewellen-2015-cross-section-expected-returns] (latest book equity over current market equity, as here)
- 6 Operating profitability — profitability
  - `(revenue − COGS − SG&A − interest expense)_TTM / BE`; missing if BE ≤ 0
  - missing expense items = 0 (project rule; revenue required), so banks are defined
  - fields: `TR.F.TotRevenue`, `TR.F.COGSTot`, `TR.F.SGATot`, `TR.F.IntrExpn`
  - sources: [fama-2015-five-factor] (definition), [gu-2020-empirical-asset-pricing-ml]; large-stock evidence is for return on assets [lewellen-2015-cross-section-expected-returns]
- 7 Short-term reversal (1-month return) — reversal
  - `close_t / close_{t−21} − 1`
  - read together with share turnover
  - sources: [gu-2020-empirical-asset-pricing-ml] (top predictor; only after positive months in large stocks), [medhat-2022-short-term-momentum]
- 8 Share turnover (1 month) — liquidity
  - `Σ volume_{t−20..t} / shares_t`
  - data: LSEG volume, shares outstanding
  - sources: [gu-2020-empirical-asset-pricing-ml], [medhat-2022-short-term-momentum]
- 9 News sentiment — sentiment
  - `Σ_k w_k · buzz_{d−k} · sentiment_{d−k} / Σ_k w_k · buzz_{d−k}`, k = 0..29 days, `w_k = 0.5^{k/7}`; missing if no buzz in the window
  - half-life 7 days: weekly sentiment predicts returns for 13 weeks, daily for 1–2 days; biweekly and monthly aggregation work too [heston-2017-news-vs-sentiment]
  - data: MarketPsych daily `sentiment` (net positive references / buzz, in [−1, 1]) and `buzz`, news + social
  - sources: [tetlock-2008-more-than-words] (negative news words also predict low earnings), [heston-2017-news-vs-sentiment] (negative news drifts for a quarter, positive within a week)
- 10 Media attention (abnormal buzz) — attention
  - `log(1 + B_d) − log(1 + median(B_{d−7}, B_{d−14}, …, B_{d−56}))`, `B_d` = buzz summed over the 7 days ending d
  - abnormal search-volume construction of [da-2011-in-search-of-attention]: this week against the median of the prior 8 weeks, which removes trends and is comparable across stocks
  - abnormal, not level: every top-50 firm is covered, buzz tracks size, and median buzz rose 2.9× from 1998 to 2022
  - data: MarketPsych daily `buzz` (count of news + social references)
  - sources: [da-2011-in-search-of-attention], [heston-2017-news-vs-sentiment]
  - effects are concentrated in smaller stocks; expect little in the top 50
- 11 Asset growth — investment
  - `assets_q / assets_{q−4} − 1`, `TR.F.TotAssets`
  - sources: [fama-2015-five-factor], [gu-2020-empirical-asset-pricing-ml]
  - weak in big stocks
- 12 Sales-to-price — value (backup)
  - `revenue_TTM / ME_t`, `TR.F.TotRevenue`
  - sources: [gu-2020-empirical-asset-pricing-ml], [lewellen-2015-cross-section-expected-returns]
  - defined when book equity ≤ 0 (buyback-heavy firms), where book-to-market is missing

## Normalization

- one scheme for all models: per date, across that date's top-50 members
- rank each feature, map to [−1, 1]: `2 · (rank − 1) / (N − 1) − 1`, ties averaged [gu-2020-empirical-asset-pricing-ml]
  - robust to outliers and skew (buzz, turnover, volatility) without winsorizing
  - removes common trends: media volume growth, the falling primary-exchange volume share, volatility regimes
  - scale-free across features; bounded input for the RL network
  - cost: drops magnitudes and market-wide level shifts; acceptable for cross-sectional allocation
- missing → 0 after ranking, i.e. the cross-sectional median [gu-2020-empirical-asset-pricing-ml]
- `black_litterman` composites: mean of the ranked features per theme, z-scored per date
  - momentum: momentum
  - value: book-to-market, sales-to-price
  - quality: operating profitability, negated asset growth, negated net share issuance
  - sentiment: news sentiment
  - attention: media attention
  - volatility, size, reversal, turnover: unused
- rejected: z-scores after 1%/99% winsorizing ([lewellen-2015-cross-section-expected-returns]); keeps magnitudes, but with 50 stocks a single outlier shifts the mean and SD

## Rejected

- beta — same theme as volatility, weaker (t = 1.73)
- Amihud illiquidity — not scale-free, covered by share turnover
- earnings-to-price — single source
- gross profitability — undefined for banks
- return on equity / return on assets — same theme as operating profitability
- accruals — sources conflict (t = −3.75 vs. zero effect in Gu et al.), undefined for banks
- leverage, dividend yield — not significant (t = 0.65, 0.34)
- RSI, MACD, Bollinger bands, moving-average ratios — no independent source, duplicate momentum
- media coverage level — every top-50 firm is covered; tracks size
- Google search volume (Vozlyublennaia 2014) — index-level evidence; not in the pipeline
- LLM sentiment on FNSPID news (Dong et al. 2024) — duplicates vendor sentiment; FNSPID ends in 2023
- MarketPsych emotion indices (fear, joy, gloom, stress) — no firm-level evidence
- market state (VIX, T-bill, index return), passive cap weight — no cross-sectional variation / monotone in size
