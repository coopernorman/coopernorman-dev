# The hard part was never the model: building a leak-proof data pipeline from six vendors

*Portfolio case study for coopernorman.dev. Public-safe: describes methodology and architecture only; no secrets, no vendor keys, no realized P&L.*

---

## TL;DR
Everyone talks about the model. In practice, the LightGBM model that prices ShareShark's options is the *tractable* part: an off-the-shelf library and a tuning loop that, however careful, was a well-understood problem. (That tuning was real work in its own right, see the [QuantShark case study](quantshark.html); the point is it was a *solved kind* of problem.) The part that actually decided whether the model worked was the **data pipeline that fed it**: six data sources from three different vendors, three incompatible timestamp formats, well over a million API pulls, and a wall of point-in-time-correctness rules built to close every leakage path I could find, so the model never trained on information it wouldn't have had at the time. That pipeline is **342 tickers, ~8 years (2018-2026), 21.5M training rows, 167 engineered features**, and it is where the real engineering lives. This case study is about the unglamorous 80%, because that 80% is the moat.

---

## The thesis
A model is only as honest as the data behind it. You can have a well-tuned gradient-boosted model and still ship something worthless, if even one feature quietly leaks a future value into a training row. On a real-money pricing product, that is not a small bug: a model that "knows" the answer in backtest looks brilliant and then loses money the moment it goes live on data it hasn't already peeked at.

So the work that mattered most wasn't choosing an algorithm. It was: **get clean data from messy vendors, line it up across time without leaking, and prove the lineup is honest.** Three layers, each with its own traps.

## Layer 1: acquisition, where the data fights back
Six sources, and not one of them agreed on anything:

- **Options chains, stock prices, earnings** come from one market-data API as compressed column-arrays (parallel `t`/`c` arrays you zip yourself, timestamps as Unix epoch seconds).
- **28 ETFs** (broad market, sectors, credit, growth, small-cap) come from a *second* vendor with nanosecond ISO-8601 timestamps and a stacked long format.
- **Treasury yields and fed funds** come from a *third* source (FRED), which encodes market holidays as a literal `.` character in an otherwise-numeric column.

That is three timestamp formats and three schema conventions before a single feature exists. The ETF cleaner alone exists mostly to reshape one vendor's stacked feed into the exact wide column layout (`{SYMBOL}_open/high/low/close/volume`) the rest of the pipeline already expected, a pure schema-reconciliation job.

**Scale forces real engineering.** The options pull dominates everything: 342 tickers, two option chains each (a weekly and a longer-dated one), every trading day for eight years is well over a million HTTP requests on trading days alone. You cannot run that naively and hope. So the collector has:

- **Retry loops on every source** (bounded attempts, fixed backoff), catching both network errors and JSON-decode failures on truncated bodies, with **per-ticker isolation** so one dead ticker returns an empty frame instead of killing the whole run.
- **Batch sharding** (`--batch N --total-batches M`) that splits the ticker universe evenly across processes, so the million-call job can fan out across machines.
- **Resume checkpoints** that read the dates already on disk and restart from the day after, so a crash four hours in costs four hours, not the whole run.

None of that is glamorous. All of it is the difference between a pipeline that finishes and one that doesn't.

## Layer 2: cleaning, where "missing" has ten meanings
Raw market data is full of values that *look* like numbers but mean "no data," and getting that wrong is how you poison a model.

**The weekend gap.** Markets close, but options still need to be priced over the weekend. Treasury and fed-funds rates simply don't exist on Saturdays, and FRED writes holidays as `.`. The fix is disciplined forward-fill: coerce the `.` to `NaN`, then carry the last *known* rate forward across the gap (never interpolate, which would pull a future value backward). The daily effective fed-funds rate is used as-is; the separate monthly fed-funds series is resampled to daily and forward-filled, broadcasting one figure across the month without ever looking ahead.

**The trading calendar is not the calendar.** Every earnings-timing feature is counted in *trading days* off the real NYSE schedule (via `pandas_market_calendars`), not naive date arithmetic. "Five days before earnings" has to skip weekends and holidays or the feature is wrong.

**Zero is not missing (this one cost me a production bug).** 17 option features depend on live bid/ask, which the vendor returns as `0.0` when the market is closed. In the training history, `0.0` had only ever appeared as a *real* deep-in-the-money value, so the model learned `0.0 means near-certain`. On weekends, `0.0` meant *missing*. Same value, opposite meaning. That single ambiguity mispriced near-the-money weekend contracts at 76-83% when the truth was 42%. (The full diagnosis and fix is its own story in the [QuantShark case study](quantshark.html); the lesson here is that the *data layer* is where that class of bug is born and where it has to be killed.)

**Recompute, don't trust.** Vendor-supplied Greeks and implied vol are inconsistent, so the pipeline recomputes them: Greeks from the closed-form Black-Scholes derivatives, implied vol by inverting Black-Scholes per row with Brent's-method root-finding (bracketed search from a small positive floor up to 1000% vol, since Black-Scholes degenerates exactly at zero vol). Every one of those functions guards the singularities (`T<=0`, `sigma` near zero) and returns a clean null rather than an `inf` that would silently corrupt a feature. The Black-Scholes probability feature is vectorized across the whole frame, roughly 100x faster than a row-wise `apply`, because at 21.5M rows the naive version simply doesn't finish.

## Layer 3: leakage prevention, the whole game
This is the part that separates a financial ML pipeline from a generic one. Three mechanisms, all aimed at the same enemy: a training row that knows something it couldn't have known at the time.

**Point-in-time joins.** When a weekend option row needs the latest stock data, a naive join could grab the *next* trading day's prices, a future leak. Instead it uses `merge_asof(direction="backward")`, which pulls the most recent *prior* trading day and nothing newer, and it fills only genuinely missing cells so real data is never overwritten.

**The earnings reaction-date guard.** An earnings report released after the close on Monday isn't "known" to the market until Tuesday. A separate pass computes the actual market-reaction date (same session for before-open reports, the next trading day for after-close reports) and only flips the "has the market seen this earnings event" flag on from that date forward. That is textbook point-in-time correctness, and skipping it is one of the most common silent leaks in financial ML.

**The label can never share a row with its features.** The outcome (did the option finish in-the-money) lives only on the expiry-day (`dte==0`) row. A first pass scans every file reading just three columns, extracts those expiry outcomes into a cached label map, and a second pass maps that label back onto the 1-to-5-days-to-expiry feature rows. Features are always pre-expiry; the label is always the future outcome; they are physically separated by construction. Contracts that don't have both a valid expiry row and a pre-expiry row are dropped, so there are no half-formed training pairs.

**Purged and embargoed splitting, with a self-check.** The train/validation/test split is not a random shuffle (which would be catastrophic for time-series) and not even a plain date cut. It is *purged and embargoed*:

- An option is assigned to a split only if it was both *observed* and *expired* before the boundary, so no contract's lifetime straddles the cut and leaks its outcome across it (the purge).
- A 7-day no-man's-land before each boundary is dropped entirely, so autocorrelation can't leak information across the seam (the embargo).
- Then the pipeline measures the actual gap between the last training date and the first validation date and asserts it, printing `PASS, no temporal leakage` only if the gap holds. The pipeline checks its own honesty.

## Schema discipline (so 342 tickers stay identical)
A subtle failure mode at this scale is *drift*: ticker 200's feature table quietly having a different shape than ticker 1's. The pipeline pins this down with a single config as the source of truth: a 167-feature manifest with expected counts the build self-validates against, ~40 domain-aware clip rules (an open-interest concentration ratio bounded to [0,1], an implied-to-realized vol ratio kept in a sane positive range, and so on) instead of a blanket clip, a strict column whitelist so raw inputs like bid/ask/volume are used for computation and then *deliberately excluded* from the model, and a float32 downcast that halves disk and memory across 21.5M rows. Every ticker comes out the other end with the exact same schema, or the build complains.

## What this demonstrates
- **Data-centric judgment.** I treated the data, not the model, as the product, because in applied ML it is.
- **Point-in-time correctness end to end.** Backward `merge_asof`, earnings reaction-date logic, expiry-only labels, and a purged-and-embargoed split that verifies itself. This is the hardest thing to get right in financial ML and the easiest to get silently wrong.
- **Engineering at awkward scale.** Retries, sharding, resume checkpoints, vectorization, float32, and a self-validating schema, the things that make a million-call, 21.5M-row pipeline actually finish and stay consistent.
- **Vendor reality.** Three sources, three formats, holidays as dots, zeros that mean missing. Real data is hostile, and most of the work is making it behave.

## Tech stack
Python · pandas (`merge_asof`, resample/ffill, groupby) · NumPy (vectorized Black-Scholes & Greeks) · SciPy (`brentq` IV solver, `norm`) · pandas_market_calendars (NYSE trading calendar) · multi-vendor REST ingestion with retry/backoff/resume · purged + embargoed temporal splitting.

## Honest notes
This describes the offline training-data pipeline; the live serving path reuses the same calculation utilities so training and production stay consistent. All figures (342 tickers, 167 features, 21.5M rows, ~8-year span) are dataset facts, not performance claims; the model-quality results live in the [QuantShark](quantshark.html) and [model-consolidation](model-consolidation.html) case studies. The heavy numerical lifting uses standard libraries; the contribution is the acquisition resilience, the cleaning rules, the leakage prevention, and the schema discipline that hold it all together.
