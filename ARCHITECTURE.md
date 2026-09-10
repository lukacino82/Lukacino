# Trading Hypothesis / Automation System — Architecture

Status: **Step 1 in progress** (Composite Profile Engine, pure Python, no live data yet).
This document is the source of truth for the design agreed in chat; update it as
decisions change instead of relying on chat history.

## Goal

Replace/extend the current manual workflow (trader takes screenshots of Sierra
Chart → AI reads them → writes a hypothesis to Notion) with a system that:

1. Reads VWAP tiers (monthly/MM, weekly/HF, intraday), cumulative delta, and
   volume/market profile composites directly from **Sierra Chart** data (no
   screenshots, no OCR).
2. Draws the same information back into the Sierra Chart window (composite
   zones, VWAP lines, a hypothesis text box) with an exact timestamp.
3. Generates the same style of hypothesis the `trading-vwap-hypotezy` skill
   writes to Notion today — either as **decision support only**, or feeding a
   **fully automated order-management layer** — switchable at runtime, not two
   separate programs.
4. Ships risk/money management, pyramiding, trailing, and a global kill switch
   for the automated path, while the discretionary path only ever shows
   information and never sends orders on its own.

## Components

```
┌──────────────────────────────────────────────────────────────┐
│ SIERRA CHART (ACSIL C++ study)                                │
│  - reads native VWAP/Delta/Volume-at-Price studies            │
│  - draws composite zones, VWAP lines, hypothesis box on chart │
│  - owns order placement (DTC) when mode = FULLY_AUTO          │
└───────────────┬───────────────────────────────┬──────────────┘
                │ export (file/pipe/DTC)         │ orders (DTC)
                ▼                                │
┌──────────────────────────────────────────────┐ │
│ PYTHON ENGINE (this repo: trading_system/)    │ │
│  composite/   → overlap + merge + invalidation│ │
│  hypothesis/  → A/B day classification, H1..Hn│ │
│  risk/        → sizing, RRR, daily loss limits│─┘
│  notion_sync/ → writes Daily Hypotheses rows  │
└──────────────────┬─────────────────────────────┘
                    ▼
              Notion "Daily Hypotheses" DB
```

Each Python package under `trading_system/` is built and tested independently
before it's wired into the ACSIL side, so bugs in the domain logic (especially
the composite overlap math, which is the least standard part of this system)
are caught on synthetic/historical data, not on a live chart.

## Operating modes (one system, one switch)

- `HYPOTHESIS_ONLY` — engine computes everything and writes the hypothesis
  (chart box + Notion), sends no orders. Default / safe mode.
- `SEMI_AUTO` — same as above, plus the engine prepares a concrete order
  (entry/stop/target in ticks) that the trader confirms by hand.
- `FULLY_AUTO` — engine places and manages orders itself under the risk
  limits below, including a "generate hypothesis before London, then let the
  trader read the chart and decide discretionarily" sub-mode where automated
  order placement is simply switched off for that session.

Switching modes never changes the analysis engine — only whether its output
is a display, a suggestion, or an order.

## Composite profile logic (Step 1 — implemented in `trading_system/composite/`)

This is the domain rule set from the user's description, made precise enough
to code and test:

- Each trading day has one **daily volume/market profile**: a price→volume
  histogram plus its value area (VAL/VAH, ~70% of volume) and POC.
- Two consecutive days are merged into (or extend) a **composite** when they
  overlap by **≥60% of transactions**. Overlap is computed from the volume
  histograms when available (volume inside the intersection of the two
  value-area ranges, divided by the *smaller* of the two days' value-area
  volume); if only VAL/VAH/POC are available, it falls back to a pure
  price-range overlap fraction.
- A composite's rectangle is the **union** of its member days' value-area
  ranges (an "extending rectangle" — it grows as more overlapping days are
  added), tagged with `day_count`.
- Tier / styling by `day_count`, exactly the table from the skill:
  | day_count | tier | color | fill transparency |
  |---|---|---|---|
  | 2–3 | `TIER_2_3` | light pink | 75 |
  | 4 | `TIER_4` | darker pink | 45 |
  | 5+ | `TIER_5_PLUS` | darkest pink | 20 |
- **Invalidation**: when a *newer* composite (or day) overlaps an older,
  already-closed composite's range by **≥10%** (price-range overlap of the
  two rectangles), the older composite is marked `invalidated` as of that
  date. It is not deleted — the sub-range of the old rectangle that the new
  one does *not* cover is kept as a plain reference level (price still reacts
  to old boundaries), while the overlapped part is considered superseded.

**Open point, needs your confirmation against real screenshots**: the 60%
merge test and the 10% invalidation test above are my best-effort reading of
your description. I have not seen the actual composite screenshots yet, so
before wiring this into ACSIL we should validate the merge/invalidation
behavior against a handful of real multi-day examples from your Notion
screenshots or Sierra Chart history — the formulas are easy to adjust once
we see a case where the output doesn't match what you'd draw by hand.

## ACSIL <-> Python bridge (Step 2 decision)

Sierra Chart's ACSIL environment has no JSON library available by default,
and hand-rolling a JSON parser in C++ just to talk to a local Python process
is unnecessary complexity for what is, for now, a same-machine, low-frequency
(end-of-day / per-recalc) handoff. Instead the two sides exchange **plain
CSV/text files** on disk, in `trading_system/bridge/`'s format:

- `daily_profile_export.csv` (ACSIL writes, Python reads) — one row per
  session close: `date,instrument,val,vah,poc`. ACSIL sources these values
  via `sc.GetStudyArrayUsingID` from a **"Volume Value Area Lines"** study
  (Time Period Type = Days, Draw Developing Value Area Lines = No) added to
  the chart specifically for this — not from whatever "Volume Profile" /
  TPO Profile study the trader uses for their own visual analysis, which
  only exposes Color subgraphs over ACSIL, not the numeric POC/VAH/VAL
  arrays (confirmed against a real chart's Subgraphs tab and Sierra
  Chart's own support board). ACSIL does not compute VAL/VAH/POC itself
  either way.
- `composites.csv` (Python writes, ACSIL reads) — one row per composite,
  refreshed after each new daily profile is ingested:
  `instrument,start_date,end_date,val,vah,day_count,tier,active,invalidated_on,remaining_ranges`
  where `remaining_ranges` is `lo:hi` pairs separated by `;` (both
  `invalidated_on` and `remaining_ranges` are empty while the composite is
  still active).
- `hypothesis.txt` (Python writes, ACSIL reads) — plain text, first line
  `instrument|generated_at_iso`, the rest is the hypothesis body verbatim;
  ACSIL just displays the file's contents in a text drawing.
- `live_state.csv` (ACSIL writes, Python reads) — Step 3: the current VWAP
  tiers and cumulative delta for the still-open trading day. Unlike
  `daily_profile_export.csv`, this file is **overwritten in place** on
  every refresh (`RefreshIntervalSeconds` input, default 5s), not
  appended to — it's a live snapshot, not a history. One header row plus
  exactly one data row:
  `timestamp,instrument,last_price,session_open,vwap_monthly,vwap_weekly,vwap_intraday,cum_delta`
  where `timestamp` is a naive local ISO datetime
  (`datetime.fromisoformat`-compatible). ACSIL sources these values from
  three separate native "VWAP" study instances (one per Time Period Type:
  Month, Week, Day — Sierra Chart's VWAP study only computes one tier per
  instance) and one cumulative-delta study, all added to the chart and
  pointed to via Study ID inputs, the same pattern as the Volume Value
  Area Lines study in Step 2. `session_open` is the current trading day's
  opening price (captured once per session, not re-derived every refresh)
  — added for the `hypothesis/regime.py` A-day/B-day gap check, since the
  skill's "small gap vs. gap outside value area" test needs the session
  open, which `last_price` alone can't give.

Each instrument gets its own subfolder under a shared bridge directory —
`<bridge_dir>/<INSTRUMENT>/daily_profile_export.csv` etc. — so the ACSIL
study (one instance per chart/instrument) never has to filter rows by
instrument; it only ever reads its own subfolder.

If this later proves too slow or too polling-heavy for intraday use, the
DTC protocol is the documented upgrade path (Step 4 already assumed a DTC
bridge for order placement) — but plain files are the simplest thing that
can possibly work for Step 2, and are trivial to inspect by hand while
debugging.

## Not built yet (next steps, in order)

1. ~~Composite Profile Engine~~ (Step 1, done)
2. ~~ACSIL C++ skeleton~~ (Step 2, done): Volume-Profile reader, daily
   profile CSV export, composite zone + hypothesis text box drawing from
   the Python-written bridge files.
3. ~~VWAP tiers + cumulative delta~~ (Step 3, done): ACSIL reads three VWAP
   study instances (Monthly/Weekly/Intraday) and a cumulative-delta study,
   writing a live snapshot to `live_state.csv` on the refresh interval.
   Verified against a real chart: `vwap_monthly`/`vwap_weekly` now read
   genuinely distinct values and `cum_delta` a real nonzero figure (a
   cross-chart array indexing bug and a Study ID/Subgraph misconfiguration
   both made these read as 0 before).
   `hypothesis/` package (Step 3b, in progress): reads `LiveMarketState`
   and classifies it the way the `trading-vwap-hypotezy` skill reads a
   screenshot.
   - ~~`tiers.py`~~ (done): position of price vs. each VWAP tier
     (above/at/below) and a structural bias (bullish/bearish/neutral) from
     all three tiers agreeing or not. Only reads the VWAP centerlines —
     the skill's +-2 standard deviation band edges around each closed
     period aren't exposed over the bridge yet.
   - ~~`delta.py`~~ (done): absorption/divergence/confirming reading from
     a rolling window of `LiveMarketState` snapshots (strong delta move
     with no price move = absorption; price move with no delta
     confirmation, or delta disagreeing with price, = divergence).
   - ~~`regime.py`~~ (done, thresholds unvalidated): A-day/B-day
     classification from `session_open` vs. yesterday's `DailyProfile`
     value area (gap size), `cum_delta` magnitude (balanced vs. one-sided),
     and `tiers.py`'s structural bias (price between tiers vs. accepted
     outside them). Returns `UNCLEAR` unless all three signs agree, rather
     than forcing a call on a mixed read. `gap_threshold_fraction` and
     `delta_imbalance` are best-effort defaults, not calibrated numbers —
     like the composite merge/invalidation percentages above, check them
     against real NQ chart examples (cum_delta magnitude especially varies
     wildly by instrument) before trusting this for a real hypothesis.
   - ~~`generator.py`~~ (done): one concrete `Hypothesis` (type, thesis,
     entry, target_1/target_2/runner, invalidation, confluence) from the
     current regime + tier + delta read + active composites. A-day reads
     as mean reversion toward the intraday VWAP; B-day as momentum
     continuation in the direction of acceptance beyond monthly/weekly
     VWAP — per the skill's section 4/6. Only ever produces the one setup
     consistent with the *live* regime, not the full four-type table the
     skill lays out from a static screenshot. Confluence
     (`A_PLUS`/`CLEAN`/`WEAK`, full/half/pass sizing per the skill's
     section 6) is read from delta agreeing or disagreeing with the
     thesis and whether a composite target exists — no new unvalidated
     numeric thresholds here, unlike `regime.py`.
   - ~~`formatter.py`~~ (done): renders a `Hypothesis` + `OrderProposal`
     as the plain-text body `hypothesis.txt` already carries -- reuses the
     existing ACSIL text-drawing pipe (see "4. Draw the hypothesis text
     box" in TradingHypothesisStudy.cpp) instead of adding a new file
     format or touching ACSIL again.
   - ~~`engine.py`~~ (`LiveEngine`, done): per-tick orchestration --
     `live_state.csv` snapshot + yesterday's `DailyProfile` + active
     composites -> tier report -> delta signal (its `DeltaHistory` persists
     across ticks on the same instance) -> regime -> hypothesis -> order
     proposal -> formatted text. Pure logic, no file I/O, unit-tested with
     in-memory data.
   - ~~`run_live.py`~~ (done, confirmed running live): the actual polling
     loop -- reads `live_state.csv`/`daily_profile_export.csv`, feeds new
     closed days into `CompositeEngine`, writes `composites.csv` (nothing
     wrote this before now -- ACSIL's composite-zone drawing was reading a
     file nothing produced) and `hypothesis.txt` every `LiveEngine.tick()`.
     Run as a long-lived process on the same Windows machine as Sierra
     Chart (`python -m trading_system.run_live --bridge-dir ... --instrument
     NQ`) -- confirmed end to end on a real chart, including the drawn text
     box (see the text color fix in README.md's "sixth real test").
     Every threshold (price/delta move, gap fraction, delta imbalance) and
     the sizing tick specs are instrument-specific, so they're keyed by
     instrument in `INSTRUMENT_CONFIGS`; an instrument with no entry fails
     loudly at startup rather than silently reusing another instrument's
     numbers (NQ's tick_size/tick_value would badly mis-size a position on
     anything else). Only `NQ` has an entry so far -- add one per new
     instrument, same as the ACSIL Study ID/Chart Number setup. All
     threshold values (not the NQ tick specs, which are real contract
     facts) are still marked "not calibrated" — same open item as
     `regime.py`'s thresholds.
   Order management / mode switching inputs are declared but not wired to
   any order logic yet (Step 4).
4. Order management (Step 4, in progress) -- built to SEMI_AUTO first
   (engine proposes, trader confirms by hand), per the user's explicit
   choice over jumping straight to FULLY_AUTO. `trading_system/risk/`:
   - ~~`sizing.py`~~ (done): confluence -> contract count, per the skill's
     section 6 (A+ = full risk, clean A = half size, weak = pass). Both
     `FIXED_CONTRACTS` (a flat count per tier) and `PERCENT_RISK` (% of
     account equity, converted via the instrument's real tick size/value)
     are implemented, at the user's request -- unlike regime.py's
     thresholds, tick size/value are real contract specs, not guesses
     (the user trades E-mini NQ: tick_size=0.25, tick_value=$5).
   - ~~`order.py`~~ (done): `OrderProposal` (instrument, direction,
     entry/stop/targets, sized contracts) from a `Hypothesis` + sizing
     config. Computes what SEMI_AUTO would show the trader; places
     nothing.
   - ~~Surfacing the proposal on the chart~~ (done, via `formatter.py` +
     `run_live.py` above): the user chose drawing it on the chart over a
     separate bridge file, and since `hypothesis.txt`'s ACSIL-side drawing
     already existed, no ACSIL/C++ change was needed for this.
   - Not yet built: the DTC order-placement bridge itself (the user has a
     Sierra Chart SIM account over DTC ready to test against once this is
     needed), and FULLY_AUTO (pyramiding, trailing, kill switch) after
     SEMI_AUTO is validated.
5. Notion sync module (Step 5, in progress) -- reuses the
   `trading-vwap-hypotezy` skill's schema and property names so both paths
   write to the same database ("Trading denik -- hypotezy",
   `53b58aaa-dfc2-4fbd-9b66-5a869047fffe`) consistently.
   - ~~`notion_sync/record.py`~~ (done): `build_notion_record()` maps a
     live tick's `TierReport`/`Regime`/`DeltaSignal`/`Hypothesis`/
     composites onto the skill's exact property names and select values
     (Nazev/Datum/Instrument/HTF bias/Rezim/Primarni setup, VWAP/Supply/
     Demand/Delta as English text). Only builds the record -- no Notion
     API call.
   - **Open item, not guessed past:** the skill's `Instrument` select only
     lists ES/S&P500, Gold (XAUUSD), WTI Oil, GBP/USD, EUR/USD, USD/JPY,
     GBP/JPY -- NQ isn't among them. `record.instrument` passes the raw
     bridge instrument code through unchanged; check the live Notion
     database's actual select options before writing a real NQ record, a
     strict select rejects a value that isn't already a choice.
   - Not yet built and needs a decision, not a guess: how the record
     actually reaches Notion. Two different things could both be called
     "Notion sync" -- (a) I write it through my own Notion connector when
     asked (a one-off, per instrument/day), or (b) `run_live.py` writes it
     itself via a direct Notion API integration (its own token, an HTTP
     client dependency, running unattended on the user's machine). These
     have very different setup costs; pick one before building further.
6. Backtest harness over historical Sierra Chart exports, before anything
   trades on a live or even sim account
7. News filter, position recovery after Sierra Chart restart, multi-timeframe
   chart sync — tracked so they aren't forgotten, not blocking Step 1–3

## Repo layout

```
trading_system/
  composite/
    models.py   — DailyProfile, Composite, tier classification
    overlap.py  — overlap fraction calculations
    engine.py   — CompositeEngine: ingest daily profiles, merge, invalidate
  tests/
    test_composite_engine.py
```
