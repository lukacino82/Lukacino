# LUKACINO FLOW INTELLIGENCE — development specification v0.1

Status: research prototype, NOT verified for live trading. Target: Sierra Chart ACSIL, ES futures, full Bid/Ask Volume-at-Price data.

## Architecture
- `LukacinoFlowIntelligence.cpp`: existing ACSIL dashboard and signals (renamed from OrderFlowCompass.cpp).
- `ES_OrderFlow_Absorption_v2.cpp`: legacy comparison baseline; do not silently merge signals.
- `SignalRelay.cpp`: cross-chart visualization.
- Future isolated module: Price-Level Absorption Engine, with deterministic historical tests and separately timestamped live updates.

## Price-Level Absorption Engine (next implementation)
For each instrument, session, price tick and evaluation window store:
1. aggressive bid volume, aggressive ask volume, total volume, net delta;
2. distinct visits to price zone (re-entry requires leaving the zone by a configurable number of ticks);
3. price displacement in ticks after each visit over fixed event-time horizons;
4. volume per tick of favorable price displacement, normalized against prior comparable windows;
5. repeated rejection, hold duration, breakthrough, retest and acceptance/rejection status;
6. proximity to prior-known VWAP, POC, VAH, VAL and composite boundaries.

**Important:** Bid/Ask trade volume does not reveal trader identities, true resting liquidity, outstanding positions, or actual stop orders. Absorption and trapped positions are inferred hypotheses, never directly observed facts.

## Detection state machine
OBSERVING -> PRESSURE -> STALLED -> REJECTION_CANDIDATE -> CONFIRMED_REVERSAL or FAILED/EXPIRED.
- PRESSURE: signed aggressive flow above rolling baseline, measured on a fixed time window (not Renko bar count alone).
- STALLED: directional price progress per unit aggressive volume below baseline; repeated touches are supporting evidence.
- REJECTION_CANDIDATE: price fails to accept beyond a tested zone and rotates away.
- CONFIRMED_REVERSAL: subsequent observable price/flow confirmation, with no future information at signal timestamp.
- FAILED/EXPIRED: acceptance beyond zone or timeout.

Separate watch/candidate/confirmation events; never display a candidate as a confirmed trade.

## Multi-window analysis
30m, 1h, 2h, 3h, 4h, 5h, session. Compute price movement, bid/ask delta, normalized effort-vs-result, volume concentration and regime for each. Compare with equal-duration historical windows matched by session time; do not compare a 30m window directly to a 5h raw volume.

## Backtest safeguards
- Generate signals on closed data only; execution earliest next available trade after confirmation, with spread/slippage/fees.
- Tick replay for stop/target order; OHLC stop-first convention is a conservative fallback, not tick-level truth.
- Record signal timestamp, actionable timestamp, fill price, target/stop, adverse/favorable excursion, time-to-resolution, and regime.
- No lookahead from future VWAP/value-area/composite values. Preserve rollover rules and ES2008 data provenance.
- Split chronological train/validation/out-of-sample periods and report by session, volatility regime, signal class and year.
- Include no-signal periods, timeouts, trading costs, sample sizes, confidence intervals and parameter sensitivity.

## Implementation sequence
1. Rename current study without changing trading logic (completed).
2. Build isolated per-price accumulator with synthetic deterministic unit tests.
3. Add repeated-visit and effort/result state machine, record audit trail.
4. Integrate historically correct VWAP/POC/VAH/VAL and composite boundaries.
5. Replace bar-based win/loss estimates with tick-replay execution simulator.
6. Benchmark computational load, replay consistency and historical/live parity.
7. Only then consider live alerts. No automated order submission by default.

## Acceptance criteria for next code phase
- All event timestamps are nondecreasing and signals never depend on later events.
- Repeat tests count independent zone visits, not multiple prints in one visit.
- Zero-volume, missing-VAP, session resets and rollover boundaries are explicit.
- Same tick stream produces identical state transitions in replay and batch mode.
- Runtime limits and data gaps are surfaced as diagnostics rather than hidden.
