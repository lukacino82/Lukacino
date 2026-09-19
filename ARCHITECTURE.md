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
  **Duplicate/conflicting rows for the same date, root-caused and fixed:**
  a real run's file had two rows for both 2026-09-14 and 2026-09-15, one
  pair with noticeably different VAH/VAL/POC and one row that was
  degenerate (val=vah=poc). First suspicion, from the Message Log alone,
  was two concurrent "Trading Hypothesis Display" instances (one left at
  its default `Instrument` after a remove/re-add) each independently
  detecting the same day rollover -- but a follow-up check (searching the
  log for every `Trading Hypothesis Display config: thisChart=...` startup
  line) confirmed only **one** instance was ever actually running. The
  real cause: Sierra Chart periodically tags this chart for a **full
  recalculation** on its own (cross-chart dependencies from other studies/
  charts in the same chartbook), and a full recalculation resets this
  study's persistent storage -- including the persistent int tracking
  "last exported trading day" -- back to 0, even though nothing about the
  trading day changed. Every such recalculation then looked exactly like a
  fresh, never-exported rollover and re-appended a duplicate row for a
  date already in the file. Confirmed directly against a real chart: a
  `daily export firing` log line, and a second real row for 2026-09-16,
  fired again immediately after a logged "Performing a full
  recalculation" message. Fixed in `TradingHypothesisStudy.cpp` by
  checking the file's own last row (`ReadLastDailyProfileDate`) before
  writing -- the persistent int can't survive a recalculation reset, but
  the CSV on disk can, so a match there means the day was already
  exported and the write (and its diagnostic log/subgraph probe) is
  skipped, just resyncing the persistent int. `read_daily_profiles()` was
  also made defensive independently of that C++ fix: it now keeps only
  the **last** row for a given `(instrument, date)` key instead of
  silently taking whichever happened to come first, in case a duplicate
  ever slips through some other way -- belt and suspenders, not a
  substitute for the real fix. See sierra_chart/README.md's "twelfth real
  test" entry for the full story.
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
     **First real backtest run** (a `--history-out` sample from
     2026-09-15, 19:17-19:24 ET) confirmed a real limitation rather than a
     bug: `regime_counts` came back 100% `UNCLEAR` for that window, because
     `session_open` sat *inside* yesterday's value area (`small_gap=True`,
     fixed for the whole session) while `cum_delta` (~4600-4800, one-sided)
     and the tier bias (BEARISH, not neutral) both looked B-day-like —
     `classify_regime` requires all three of `small_gap`/`balanced_delta`/
     `price_between_tiers` to agree, and `small_gap` can never flip mid-
     session once set at the open. This matches the source skill's own
     B-day definition exactly ("gap ven z VA" is one of its three signs) —
     asked the user whether to loosen this for a session that trends
     without an opening gap, and the answer was to **keep the strict,
     gap-required definition as-is**, faithful to the skill, rather than
     inventing a new "intraday trend without a gap" regime. Separately,
     that same sample also showed `delta_imbalance=1000.0` was clearly far
     too low for NQ (real `cum_delta` was already 4.6-4.8x over it within a
     single 7-minute window) — bumped to `5000.0` in `run_live.py`'s
     `INSTRUMENT_CONFIGS` as a less-obviously-wrong placeholder; still not
     a real calibration, which needs a distribution across many real
     days/times-of-day, not one sample.
     **First real hypothesis output** (2026-09-16, once `delta_imbalance`
     and the running process were both fixed) surfaced a genuine
     correctness bug, not a calibration gap: `_a_day_hypothesis`'s
     `invalidation` falls back to `state.session_open` whenever no
     composite gives a real stop level, but nothing ever checked that
     `session_open` actually sits on the correct side of entry (below for
     a long, above for a short). The live output showed an `A_SHORT` with
     `Invalidation: 29286.80` sitting *below both* `Entry: 29452.80` and
     `Targets: T1 29419.80` -- a backwards stop, since price had already
     traded past the session open before the setup fired. Fixed by
     rejecting the hypothesis entirely (returning `None`) whenever the
     computed invalidation lands on the wrong side, same principle as
     B-day's missing-`target_1` case just above -- proposing a trade with
     a broken risk level is worse than proposing none. Two of the existing
     `test_generator.py` fixtures had `session_open` on the wrong side too
     (they just never asserted on `invalidation`, so the bug was invisible
     to them) and needed fixing alongside two new tests reproducing the
     real failure directly.
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
     regime.py's thresholds. Pass `--history-out <path>` to also append
     every new `live_state.csv` snapshot (deduped on timestamp) to a
     growing historical CSV in the same column shape — this is what turns
     into real input for `trading_system/backtest/replay.py` /
     `run_backtest.py` after it's run for a while, since there's still no
     ACSIL-side historical VWAP/delta export to produce that file any other
     way. Omitting the flag runs exactly as before (no history logging).
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
   - **Staged rollout, decided with the user**: build and prove manual
     one-click order triggering first (test thoroughly on the user's real
     Sierra Chart SIM/DTC account), *then* add a Manual/Auto mode switch
     that reuses that same tested order-placement code path for true
     automatic firing. The user explicitly chose this over jumping
     straight to full automation.
   - ~~`order_proposal.csv` bridge format~~ (done, in
     `bridge/csv_bridge.py`): a new machine-readable file, distinct from
     `hypothesis.txt` (free text meant for a human/the chart's drawn text
     box). `OrderProposalSnapshot` carries `direction`
     (`"long"`/`"short"`/`"none"`), `hypothesis_type`, `confluence`,
     `entry`/`stop`/`target_1`/`target_2`/`runner`, `contracts`, and (added
     for the scale-out split below) `contracts_target1`/`contracts_target2`/
     `contracts_runner`. Always
     written every tick by `run_live.py` -- even when nothing is
     tradeable, as a `direction="none"`/`contracts=0` row -- so ACSIL can
     tell "checked, nothing to do right now" apart from "stale/missing
     file" from one read, without a second existence-check file that could
     race against it. `run_live.py` writes it by default to
     `<bridge-dir>/<instrument>/order_proposal.csv` (override with
     `--order-proposal-out`); no opt-in flag like `--history-out`, since
     this file needs to exist continuously once ACSIL's order-placement
     side reads it.
   - ~~ACSIL manual order trigger~~ (done, deployed and running on the
     user's real Sierra Chart against a live NQ chart): `Mode` now
     genuinely switches between `Hypothesis Only`/`Semi Auto`/`Fully Auto`
     (the latter logs a warning and stays inert -- not implemented, per the
     staged rollout). In `Semi Auto`, a self-resetting `Trigger Order Now`
     Yes/No input (flips back to No itself after acting -- ACSIL has no
     native clickable-button Input type) reads `order_proposal.csv` and, if
     every safety check passes, places a market entry with an attached
     stop/target via `sc.BuyEntry`/`sc.SellEntry`. Checks, in order: a data
     row exists; direction is long/short (not none); instrument matches;
     the proposal isn't older than `Max Order Proposal Age`; contracts are
     within a Sierra-Chart-side `Max Contracts Safety Cap` independent of
     Python's own sizing; stop/target_1 are present and on the correct side
     of each other (a second, C++-side check of the same bug class the
     backwards A-day invalidation fix caught in Python); no position is
     already open AND no working (not yet filled) order exists
     (`sc.GetTradePosition`'s `PositionQuantity`/`WorkingOrdersExist`
     fields -- see below). Verified end to end (SetDefaults, a plain tick, a
     fired trigger placing a real `BuyEntry` call, confirmation the trigger
     auto-resets and doesn't re-fire, and a working-order refusal) against a
     stand-in ACSIL header stub compiled with g++ -- no real Sierra Chart
     SDK is available in this environment, so this proves the C++ is
     internally consistent, not that these are the real SDK's exact field
     names; the real Sierra Chart build is the authoritative check, and it
     did succeed on the user's machine for everything above.
     FULLY_AUTO (pyramiding, trailing, kill switch) stays explicitly
     deferred until manual triggering is proven reliable on SIM -- not yet
     started, waiting on the user's first real actionable proposal to test
     the manual trigger against.
   - **Second guard against working (not yet filled) orders, now
     implemented.** A first attempt added a `HasWorkingOrder()` check
     looping a guessed `sc.GetOrders(index, order)` -- this compiled
     cleanly against the local stub (which is exactly the risk of a stub
     not matching the real SDK: it can't catch a function that doesn't
     exist at all), but the real Sierra Chart build failed outright:
     `'struct s_sc' has no member named 'GetOrders'`. Rather than guess
     again, the user pasted the relevant sections of Sierra Chart's own
     `ACSILTrading.html` documentation directly, which confirmed the real
     API: `sc.GetOrderByIndex`/`sc.GetOrderForSymbolAndAccountByIndex` plus
     the free function `IsWorkingOrderStatus(OrderStatusCode)` (not a
     method on `sc`) would work, but the same documentation also revealed a
     much simpler answer -- `s_SCPositionData` (already fetched via the
     existing `sc.GetTradePosition(PositionData)` call for the position
     check) has a `WorkingOrdersExist` member: "set to a nonzero value when
     there are working orders. Otherwise, it will be 0." The manual-trigger
     block now checks `PositionData.WorkingOrdersExist != 0` directly,
     right after the `PositionQuantity != 0` check, with no separate order
     -enumeration loop needed at all. This closes the gap the earlier
     revert left open.
   - **Risk limits, hardened before the first real order ever went out.**
     Discussed with the user which gap to close first while waiting for the
     market to reopen -- chose risk limits over target_2/runner scale-out,
     since no live order had fired yet on Semi Auto. Two limits, both
     enforceable with zero new/unconfirmed ACSIL API:
     - `Trading Enabled` (Yes/No, default Yes) -- a manual kill switch,
       checked first inside the fired-trigger branch, before even reading
       `order_proposal.csv`. Flip to No to hard-block every trigger
       immediately, independent of `Mode`.
     - `Max Trades Per Day` (int, default 3) -- checked last, right before
       order placement, alongside the position/working-order checks. A
       genuine dollar-based daily loss limit is deliberately NOT
       implemented: it would need either a confirmed ACSIL realized-P&L
       field or a new fills bridge, neither of which exists, and guessing
       either risks a repeat of the `sc.GetOrders()` failure. Until that's
       designed, the trader's own Sierra Chart Trade Activity/Account
       Balance window remains the real daily-loss backstop, with `Trading
       Enabled` as the one-click way to act on it.
     The trade count is read from a new append-only `trigger_log.csv`
     (`date,timestamp,direction,contracts`, one row per order this study has
     actually placed, written only after `sc.BuyEntry`/`sc.SellEntry`
     returns success) rather than a persistent int -- deliberately, since a
     persistent int is exactly what the full-recalculation reset above
     already proved unreliable across restarts/recalculations. Counting is
     done by a plain `"YYYY-MM-DD,"` line-prefix match against today's wall-
     clock date (`TodayDateString`), not `sc.GetTradingDayDate()`'s opaque
     comparison value, since a real calendar date is what's needed to
     persist and re-derive from disk. Verified against the local stub: a
     kill-switch refusal, two successful trades, and a third refusal once
     the (default) 3-trade cap is reached, all logged with the expected
     message and `trigger_log.csv` row count.
   - **target_2/runner scale-out, implemented.** Until now, `target_2` and
     `runner` were computed by `hypothesis/generator.py` and carried through
     `OrderProposal`/`order_proposal.csv` but never actually used -- the
     manual trigger only ever placed one bracket order against `target_1`.
     Asked the user how to split `contracts` across the three levels; the
     answer was **by confluence, not a flat 1/3 split**: `A_PLUS` scales out
     across all three (`target_1`/`target_2`/`runner`), `CLEAN` only across
     two (`target_1`/`runner`, deliberately no `target_2` leg), matching how
     the skill already treats A+ as the "full" setup and Clean as the
     reduced one. Implemented as:
     - `risk/order.py`'s `_split_contracts_by_confluence` decides which legs
       a confluence tier uses (dropping a leg back into `target_1` whenever
       its price is `None` or the total is too small to fund every desired
       leg) and `_split_evenly` divides the total across them,
       remainder-first to `target_1` (the closest, most-likely-to-fill
       level, so it's never the one a too-small size drops). `OrderProposal`
       now carries `contracts_target1`/`contracts_target2`/`contracts_runner`
       (always summing to `contracts`), computed once in
       `build_order_proposal` alongside the existing sizing call.
     - `order_proposal.csv` gained three columns for these
       (`bridge/csv_bridge.py`'s `ORDER_PROPOSAL_FIELDS`/
       `OrderProposalSnapshot`) -- Python decides the split, ACSIL just
       executes it, same division of responsibility as everywhere else in
       this bridge.
     - `TradingHypothesisStudy.cpp`'s manual trigger now submits **one
       `sc.BuyEntry`/`sc.SellEntry` bracket order per nonzero leg** (up to
       three), each with its own `Target1Price` but all sharing
       `proposal.stop` -- `s_SCNewOrder` only carries a single target price,
       so a multi-target scale-out needs one order submission per target,
       not one order with several targets. There is deliberately no
       per-leg stop management yet (moving the runner's stop to breakeven
       once target_1 fills, trailing it further) -- that needs fill-event
       tracking this bridge doesn't have, so it's deferred to FULLY_AUTO the
       same way pyramiding/trailing already are. `trigger_log.csv`/`Max
       Trades Per Day` still count the whole trigger as **one** trade
       regardless of how many legs fired, since the cap is about how many
       times the trader has clicked the trigger today, not how many bracket
       orders exist on the account.
     - Two new defensive checks, same principle as the existing backwards
       stop/target_1 re-check: the leg quantities must sum back to
       `contracts` (re-checking Python's own invariant, not trusting it
       blindly), and a leg with contracts but no matching price (`target_2`/
       `runner` empty) is refused rather than submitting an order at
       `Target1Price=0.0`. The backwards-price check was also extended to
       cover any active `target_2`/`runner` leg, not just `target_1`.
     Older `order_proposal.csv` files (an 11-column file from a
     `run_live.py` that hasn't been redeployed yet) are read with a
     fallback: the whole size becomes a single `target_1`-only leg, matching
     this study's pre-scale-out behavior, rather than indexing past the end
     of the parsed row or refusing to trade. Verified against the local
     stub: a 3-contract A+ proposal (target_2/runner both priced) fires
     three separate `BuyEntry` calls (1/1/1) and logs one `trigger_log.csv`
     row with `contracts=3`; a mismatched-sum proposal and a
     price-missing-for-a-funded-leg proposal are both refused with the
     expected message. Also confirmed compiling on the user's real Sierra
     Chart remote build server.
   - **Also fixed along the way (a real hardware finding, not part of the
     original order-trigger design):** `daily_profile_export.csv` was
     gaining duplicate rows for the same date because Sierra Chart
     periodically tags this chart for a full recalculation on its own
     (cross-chart dependencies elsewhere in the chartbook), which resets
     this study's persistent storage -- including the "last exported
     trading day" tracker -- even though the day hasn't changed. Fixed by
     checking the file's own last row before writing instead of trusting
     the persistent int alone; see sierra_chart/README.md's "twelfth real
     test" entry for the full story.
5. Notion sync module (Step 5, in progress) -- reuses the
   `trading-vwap-hypotezy` skill's schema and property names so both paths
   write to the same database ("Trading denik -- hypotezy",
   `53b58aaa-dfc2-4fbd-9b66-5a869047fffe`) consistently.
   - ~~`notion_sync/record.py`~~ (done, schema confirmed against the live
     database via `notion-fetch`, not just the skill's description text):
     `build_notion_record()` maps a live tick's
     `TierReport`/`Regime`/`DeltaSignal`/`Hypothesis`/composites onto the
     exact property names and select values (Nazev/Datum/Instrument/HTF
     bias/Rezim/Primarni setup, VWAP/Supply/Demand/Delta as English text).
     Only builds the record -- no Notion API call. Fetching the real
     schema caught two mismatches the skill's description text alone
     didn't reveal: "HTF bias"'s neutral option is one combined value,
     "Neutral / Balance", not two separate ones; "Rezim" needs
     "Nejasne"'s diacritic exactly.
   - **Resolved:** the live `Instrument` select was missing NQ (only
     ES/S&P500, Gold (XAUUSD), WTI Oil, GBP/USD, EUR/USD, USD/JPY,
     GBP/JPY). Added an "NQ" option to it with the user's explicit
     confirmation before changing a database the `trading-vwap-hypotezy`
     skill also writes to. `record.instrument` passes the raw bridge
     instrument code through unchanged, which now resolves for NQ.
   - **Decided:** the user chose (a) -- I write the record through my own
     Notion connector when asked (a one-off, per instrument/day), not (b)
     `run_live.py` writing it itself via a direct API integration. `record.py`
     works for either path unchanged; only how the record reaches Notion
     differs.
6. ~~Backtest harness~~ (Step 6, done): `trading_system/backtest/replay.py`
   replays a chronological history of `DailyProfile` rows (any real,
   accumulated `daily_profile_export.csv` works unchanged) and
   `LiveMarketState` snapshots (same column shape as `live_state.csv`, but
   many historical rows instead of one) through the exact same `LiveEngine`
   production uses — same `INSTRUMENT_CONFIGS` thresholds, via
   `trading_system/run_backtest.py`'s CLI, so a backtest can never silently
   drift out of sync with what `run_live.py` actually does. Lookahead is
   avoided explicitly (a day's profile only becomes visible once the
   intraday clock has passed it, mirroring the guarantee ACSIL gives
   `run_live.py` for free), and only one trade is tracked open at a time
   (the SEMI_AUTO "one trader, one instrument" model) with outcome judged as
   win/loss against `target_1` vs. the invalidation (stop) — `target_2`/
   `runner` are recorded as "also reached" but don't change the primary
   call, and a hypothesis with no `target_1` at all is counted separately
   (`skipped_no_target`) rather than dropped or force-scored. There is
   deliberately no ACSIL-side historical VWAP/delta export -- `run_live.py`'s
   new `--history-out` flag (see above) is what accumulates a real
   historical CSV over time instead, by logging `live_state.csv` snapshots
   as they happen rather than exporting them retroactively from Sierra
   Chart. Once that's run for a while, it's the direct input this harness
   needs to actually calibrate `regime.py`'s thresholds against real NQ
   history — until then this remains proven only against the harness's own
   synthetic-data tests.
7. News filter, multi-timeframe chart sync — tracked so they aren't
   forgotten, not blocking Step 1–3.
   **Position/state recovery after a restart, investigated and found
   already robust — no code change needed:**
   - **Sierra Chart restart (the DLL/study reloading):** every check the
     manual trigger relies on for correctness is either a live broker query
     or re-derived from disk, never trusted from a persistent int alone.
     `sc.GetTradePosition`'s `PositionQuantity`/`WorkingOrdersExist` come
     straight from Sierra Chart's own Trade Service, which doesn't forget a
     real position or working order just because this study's DLL reloaded.
     `Max Trades Per Day` is counted from `trigger_log.csv` on disk, not a
     persistent int, precisely because persistent ints were already proven
     unreliable across a restart/full-recalculation (the
     `daily_profile_export.csv` duplicate-row story). Even
     `SessionOpenTradingDayYYYYMMDD`/`SessionOpenPrice` (persistent ints/
     doubles) self-heal correctly if reset: the re-scan walks real historical
     bars (`sc.BaseDateTimeIn`) backward to the actual first bar of the
     current trading day and re-reads its real `Open` value, so it
     reconstructs the true session open regardless of when the reset
     happens, not something time- or "now"-dependent that a reset could
     corrupt.
   - **`run_live.py` (the Python process) restart:** `CompositeEngine`
     starts empty and `ingested_dates` starts as an empty set on every
     process start, but every trading day in `daily_profile_export.csv` is
     "not yet ingested" from a fresh process's point of view, so `_tick`
     re-ingests the *entire* history file back into a fresh
     `CompositeEngine` on the very first tick after a restart — full
     composite state rebuilds itself from disk every time, nothing is lost.
     The one real (and deliberately accepted) soft spot: `LiveEngine`'s
     `DeltaHistory` rolling window is in-memory only and starts empty after
     a restart, so `delta.py`'s absorption/divergence read has nothing to
     compare against for the first few polls until the window refills from
     fresh `live_state.csv` snapshots. This degrades gracefully (more
     `UNCLEAR` regime reads for a few minutes, never a wrong-but-confident
     one) rather than failing unsafely, consistent with `regime.py`'s
     existing "no signal beats a wrong signal" design, so it's left as-is
     rather than adding a history-replay-on-startup mechanism for a cold
     start that self-resolves in minutes.
   - **The Windows machine itself restarting, now closed and confirmed
     working on the user's real deployment via `run_live_supervisor.bat`
     (repo root) + a per-user Startup-folder shortcut** -- see the
     "Auto-start run_live.py after a reboot" section of
     `sierra_chart/README.md` for both the shortcut steps and the
     `schtasks` alternative, and the user's real deployment paths
     (`C:\LukacinoGit`, `C:\SierraChart\TradingHypothesisBridge`).
     `schtasks /create` was tried first but failed with "Přístup byl
     odepřen" (access denied) even as a non-admin, limited-privilege task
     on the user's real machine (a locked-down trading VPS) -- the
     Startup-folder shortcut needs no special privileges at all and starts
     at the same point in the login sequence, so it became the primary
     documented method rather than a fallback. Also fixed along the way: the
     `.bat` originally redirected Python's output straight to a log file
     without `-u` (unbuffered), so `run_live.py`'s own startup print sat
     invisible in Python's block-buffered stdout for minutes on the user's
     real run, making a genuinely running process look hung -- confirmed
     both the bug (empty-looking log right after start) and the fix (the
     line appears immediately with `-u`) against the user's real console
     output. The `.bat` is a supervisor loop, not a replacement for
     `run_live.py`'s own resilience (its `while True` already never exits on
     an ordinary tick error) -- it only ever matters when something outside
     `run_live.py`'s control kills the whole process (a stray Ctrl+C, the
     console window closing, a reboot). Deliberately does not `git pull`
     automatically -- code updates stay a manual, reviewed step; a
     `git pull` followed by one Ctrl+C on the running window is enough,
     since each restart launches a fresh process
     that re-reads `trading_system/` from disk. Until now, until
     `run_live.py` was manually restarted after a reboot,
     `order_proposal.csv` would simply go stale and the manual trigger's
     existing `Max Order Proposal Age` check already refused to act on it
     -- a safe failure mode even before this fix, just not a self-healing
     one.

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
