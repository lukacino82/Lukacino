# TradingHypothesisStudy.cpp — build notes

## Install

1. Copy `TradingHypothesisStudy.cpp` into your Sierra Chart `ACS_Source`
   folder.
2. In Sierra Chart: Analysis → Build Custom Studies DLL (or add this file to
   your existing custom studies DLL project) and build.
3. Add a **"Volume Value Area Lines"** study to the same chart (this is
   separate from whatever "Volume Profile" / TPO Profile study you use for
   your own visual analysis — that one only exposes Color subgraphs over
   ACSIL, not numeric POC/VAH/VAL; confirmed both from Sierra Chart's own
   docs/support board and from a real chart's Subgraphs tab). **Confirmed by
   a real test: this must be a regular OHLC or volume-bar chart, not a TPO /
   Market Profile chart type** — a TPO-type chart's own native "Highlight
   TPO Value Area"/"Highlight TPO POC" display looks identical on screen but
   is baked into the chart engine with no subgraphs at all, and a Volume
   Value Area Lines study added to that same TPO chart never computes
   anything (stays 0 forever). Check the chart's own Settings dialog title
   bar first — if it reads like "... Period: 1 Days, TPOs: 0.50 x 30 min",
   it's a TPO chart; use a different chart of the same instrument instead.
   Configure the study:
   - `Draw Developing Value Area Lines` = No
   - `Time Period Type` = Days, `Time Period Length` = 1
   - Optionally check `Hide Study` — it only needs to exist for ACSIL to
     read, not to be visible.
   Its Subgraphs tab should show `Vol POC (SG1)`, `Vol Value Area High
   (SG2)`, `Vol Value Area Low (SG3)` — confirmed on a real chart.
4. Add three **"VWAP"** study instances to the same chart — Sierra Chart's
   native VWAP study only computes one time-period tier per instance, so
   you need one each for:
   - `Time Period Type` = Month (the "MM"/monthly tier)
   - `Time Period Type` = Week (the "HF"/weekly tier)
   - `Time Period Type` = Day (the intraday tier)
   Each has a `VWAP` subgraph (SG1, index 0 by default) — leave the
   defaults unless you've customized the study (e.g. reordered subgraphs
   by adding standard-deviation bands ahead of it).
5. Add whichever **cumulative-delta study** you already use on this chart
   (e.g. a "Numbers Bars - Bid vs Ask Volume Difference" or a Cumulative
   Delta Bars study). Check its Subgraphs tab for the right index — this
   one varies by which delta study you use, unlike VWAP/Volume Value Area
   Lines where the layout is standard.
6. Add the study ("Trading Hypothesis Display") to the same chart, or to
   whichever chart will be the single instance that writes the bridge
   files (see "Cross-chart Study IDs" below if your VWAP tiers live on
   different charts).
7. Set its inputs: `Instrument` (must match the subfolder name the Python
   engine writes to), `Bridge Folder`, and the five Study ID inputs
   (`Volume Value Area Lines Study ID`, the three `VWAP Study ID: ... Tier`
   inputs, `Cumulative Delta Study ID`). **These are plain numbers you
   type in, not a dropdown** — open each target study's own Settings
   dialog and read the number after "ID:" in its title bar (e.g. "Study
   Settings: Main VWAP. ID:1" means you type `1`). A dropdown picker
   isn't used here because it would only ever list studies on the current
   chart, which breaks as soon as a tier lives on a different chart. The
   VAH/VAL/POC subgraph index inputs already default to the confirmed
   values (VAH=1, VAL=2, POC=0 — i.e. SG2/SG3/SG1), so leave them unless
   your Subgraphs tab shows a different order.
8. **Only if you intend to place real orders (Step 4):** leave `Mode` at
   `Hypothesis Only` until you've read "Manual order trigger (Step 4)"
   below and are ready to test on a SIM/demo account. Sierra Chart's own
   Trade → "Enable Trading" / AutoTrading switch must also be on for this
   chart's Trade Service, and the chart's own Trade Account must be a real
   (or SIM) account — none of that is something this study can turn on
   for you.

`Bridge Folder` is just a path typed into that Input — the study now
creates it (and the `<Instrument>` subfolder under it) on disk itself the
first time it needs to write, so you don't need to create it by hand
first. If it still can't write there (e.g. permissions), you'll now see a
message in Sierra Chart's **Message Log** (Window → Message Log) saying
exactly which path it failed to open, instead of silently doing nothing.

The study also logs its resolved config once right after you add it (no
need to wait for end-of-day rollover to check it): the bridge file paths,
every Study ID it resolved to, and each one's array size.

**Corrected after a real test run:** the array-size numbers are informational
only, not proof of a working connection — a real log showed
`sc.GetStudyArrayUsingID` returning a *non-empty*, non-trivial-sized array
even when a Study ID input was left at its unconfigured default of `0`
(the array's size didn't match anything meaningful in that case, and even
varied between chart instances). So `...ArraySize` being non-zero does
**not** mean that particular Study ID is pointing at a real study — the
only reliable check is whether you've actually typed a real Study ID
number into the input yourself (leaving it unset keeps it at `0`).
Exporting/writing is now gated on the Study ID inputs being non-zero
directly, not on array size, so nothing gets written with garbage
zero/default values before you've configured all the required studies.

## What live_state.csv is and when it appears

`live_state.csv` is the Step 3 addition: the current VWAP tiers and
cumulative delta for the still-open trading day. Unlike
`daily_profile_export.csv` (one row per closed session), it's overwritten
in place on every refresh (`Bridge File Refresh Interval` input, 5s by
default) — check it any time, no need to wait for a session rollover. It
only starts appearing once all three VWAP Study IDs and the Delta Study ID
resolve to real, already-calculated studies (same "array size 0" check as
above); until then it's simply not written yet, with no error, since
nothing is actually broken — you just haven't pointed all four inputs at
real studies yet.

## Manual order trigger (Step 4) — confirmed building and running on real hardware

The core trigger (reading `order_proposal.csv`, placing a bracket order,
the position/working-order/kill-switch/trade-count checks below) has
compiled successfully on the user's real Sierra Chart remote build server
and run against a live NQ chart. Some field/return-value assumptions in
`s_SCNewOrder`/`sc.BuyEntry`/`sc.SellEntry` are still only checked against
the local g++ stub, not the real SDK header directly — see the
"VERIFICATION STATUS" comment directly above the manual-trigger block in
`TradingHypothesisStudy.cpp` for exactly which ones, and double-check them
against your installed SDK header if a future change to this block fails
to build or behaves oddly.

This reads `order_proposal.csv` (written every tick by `run_live.py` — see
`trading_system/bridge/csv_bridge.py`'s `OrderProposalSnapshot`) and places
one or more real bracket orders (entry + attached stop + attached target)
via `sc.BuyEntry`/`sc.SellEntry` — but only when you explicitly ask it to,
never on its own. This is the first, deliberately manual stage of Step 4;
a Manual/Auto switch that fires automatically comes later, only once this
stage is proven reliable on a SIM account (the user's explicit staged
choice over building full automation straight away).

**Scale-out across target_1/target_2/runner:** `contracts` splits across
up to three separate bracket orders depending on confluence —
`A+` scales out across all three (`target_1`/`target_2`/`runner`), `Clean`
only across two (`target_1`/`runner`, no `target_2` leg), decided in
`risk/order.py`'s `_split_contracts_by_confluence` (Python decides the
split; this study just executes it, reading the leg sizes straight from
`order_proposal.csv`'s `contracts_target1`/`contracts_target2`/
`contracts_runner` columns). Each leg is its own `sc.BuyEntry`/`sc.SellEntry`
call — `s_SCNewOrder` only has one target price, so there's no single-order
way to attach three different targets — but all legs share the same
`stop`; there's no per-leg stop management yet (moving the runner's stop to
breakeven once `target_1` fills, trailing it further), since that needs
fill-event tracking this bridge doesn't have. A leg with zero contracts
(e.g. `Clean` never funds a `target_2` leg, or the total was too small to
fund every leg the confluence tier calls for) is simply skipped.

**How to fire an order:**
1. Set `Mode` to `Semi Auto`.
2. Check the drawn hypothesis text box (or `order_proposal.csv` directly)
   for a real, actionable proposal — `direction` must be `long`/`short`,
   not `none`.
3. Flip `Trigger Order Now` to `Yes`. The study acts once on its next
   recalculation and immediately flips the input back to `No` itself —
   there's no native clickable-button Input type in ACSIL, so this
   self-resetting toggle is the standard idiom for a one-shot manual
   action instead.
4. Check Sierra Chart's **Message Log** (Window → Message Log) for the
   outcome — either a confirmation with the order details and
   `sc.BuyEntry`/`sc.SellEntry`'s return value, or a specific reason it
   refused to act (stale proposal, no position risk level, a position
   already open, etc. — see the checks below).

**Safety checks before any order is submitted** (in order, first failure
wins — nothing after it is checked, and the order is never placed):
- `Trading Enabled` must be `Yes` — the manual kill switch, checked before
  anything else. Flip it to `No` to instantly block every trigger
  regardless of `Mode` or how valid the current proposal is.
- A data row must actually exist in `order_proposal.csv` yet.
- `direction` must be `long` or `short` (not `none` — nothing tradeable).
- `instrument` in the file must match this study's own `Instrument` input.
- The proposal's `timestamp` must be newer than `Max Order Proposal Age`
  seconds ago (default 30s) — refuses to act on a stale file left behind
  by a crashed or stopped `run_live.py`.
- `contracts` must be greater than 0 and no more than `Max Contracts
  Safety Cap` (default 5, independent of whatever sizing `risk/sizing.py`
  computed — a second, Sierra-Chart-side limit you control directly).
- Both `stop` and `target_1` must be present.
- `contracts_target1 + contracts_target2 + contracts_runner` must equal
  `contracts` — a defensive re-check of the same invariant
  `_split_contracts_by_confluence` guarantees on the Python side, not
  trusted blindly.
- A leg with contracts assigned (`contracts_target2`/`contracts_runner` > 0)
  must have a matching price (`target_2`/`runner` not empty) — otherwise
  that leg would submit a bracket order at `Target1Price=0.0`, refused
  instead.
- `stop` must be on the correct side of `target_1`, and of `target_2`/
  `runner` too whenever their leg is funded (long: stop below target;
  short: stop above target) — a second, independent check in C++ of the
  same class of bug the backwards A-day invalidation fix caught in Python
  (`hypothesis/generator.py`). `run_live.py` already refuses to write a
  backwards proposal in the first place, so this should never actually
  trigger; if it does, that's a bug to fix, not something to work around
  here.
- No position may already be open for this chart's symbol/account
  (`sc.GetTradePosition`'s `PositionQuantity != 0`) — the one-trade-at-a-
  time guard, matching the backtest harness's own model.
- No working (not yet filled) order may already exist for this chart's
  symbol/account either (`sc.GetTradePosition`'s `WorkingOrdersExist != 0`)
  — so a stale limit/stop entry sitting unfilled is caught too, not just an
  already-filled open position. An earlier attempt guessed a nonexistent
  `sc.GetOrders` function and failed a real build; the fix uses the
  `WorkingOrdersExist` field Sierra Chart's own `ACSILTrading.html` docs
  confirm on the same `s_SCPositionData` struct already fetched for the
  position check above, with no separate order-enumeration loop needed —
  see ARCHITECTURE.md's Step 4 notes.
- Today's trade count (from `trigger_log.csv`, this study's own append-only
  record of every order it has actually placed) must be below `Max Trades
  Per Day` (default 3) — a hard cap on worst-case daily exposure, checked
  last, right before the order actually goes out. Counted from the log
  file itself rather than a persistent int, since a persistent int is
  exactly what a Sierra Chart full recalculation was already found to
  silently reset (see the `daily_profile_export.csv` duplicate-row story
  above) — that reset would otherwise defeat this cap without any visible
  error. There is deliberately no automated dollar-based daily loss limit
  yet (no confirmed ACSIL realized-P&L field, no fills bridge) — watch your
  own Sierra Chart Trade Activity/Account Balance window for that, and use
  `Trading Enabled` above to act on it. One trigger counts as **one** trade
  here no matter how many scale-out legs it places — the cap is about how
  many times you've clicked the trigger today, not how many bracket orders
  exist on the account.

The entry order type is a plain market order (`SCT_ORDERTYPE_MARKET`) —
deliberately simple for this first manual-trigger stage, rather than a
limit order at the proposal's stale `entry` price, which could sit unfilled
indefinitely if price has already moved on by the time you click. The stop
and target are attached as absolute prices (`Target1Price`/`Stop1Price`),
not offsets, since the proposal already carries real price levels.

## Fully Auto mode — implemented, reuses the exact same checks

`Fully Auto` now fires automatically instead of waiting for `Trigger Order
Now` — it reuses the identical `TryFireOrderFromProposal` function Semi Auto's
manual trigger calls (extracted into a shared helper specifically so Fully
Auto couldn't drift into a second, divergent copy of the safety checks), so
every check above (kill switch, staleness, contracts cap, stop/target
sanity, leg-sum/leg-price checks, position/working-order guard, Max Trades
Per Day) applies identically — the only difference is *when* it's evaluated:
- **Semi Auto**: once, the instant you flip `Trigger Order Now` to `Yes`.
- **Fully Auto**: on a timer, every `Bridge File Refresh Interval` input
  (same cadence the bridge files themselves refresh on, since
  `order_proposal.csv` only actually changes that often anyway) — not every
  recalculation, which can fire many times a second via `sc.UpdateAlways`.

**Message Log stays readable even when nothing changes for a while.** A
real, successful order placement is always logged (the same per-leg lines
Semi Auto produces). A *refusal* reason (no signal right now, already in a
trade, today's cap reached, etc.) is logged once on the transition into it,
then suppressed on every following attempt that hits the exact same reason —
otherwise Fully Auto would print e.g. "a position is already open" every
`Refresh Interval` seconds for as long as a trade stays open. The moment the
reason changes (the trade closes and it goes back to "nothing tradeable", or
a new signal appears), that gets its own fresh log line.

**Entries and exits both come from Sierra Chart's own order management —
no separate exit logic exists or is needed.** Fully Auto's only job is
deciding *when to submit* a bracket order (entry + attached stop + attached
target); once submitted, each leg's stop/target is a normal Sierra Chart
order that the Trade Service manages and fills against replayed or live
price action on its own, exactly as it would for an order you placed by
hand. There is still no per-leg stop management (moving the runner's stop to
breakeven once `target_1` fills, trailing it further) — deferred the same
way pyramiding/trailing already are, since that needs fill-event tracking
this bridge doesn't have yet.

**Before switching to Fully Auto, even on a Replay/SIM session:** confirm
Semi Auto has actually placed at least one real order successfully first
(the staged rollout this was built around) — Fully Auto shares 100% of that
code path, so anything wrong with the proposal, the chart's Trade Service
setup, or the account would show up identically either way, just without
you having clicked anything.

## Testing in Sierra Chart's Replay mode

Sierra Chart's Replay feature re-feeds historical bars through the chart as
if they were arriving live — this study doesn't know or care whether its
chart is live or replaying, so `Fully Auto` (or Semi Auto, clicked by hand)
places real (SIM-account) bracket orders against replayed price action the
same way it would against a live market. This is the intended way to watch
the whole loop — hypothesis → order → entry → bracket exit → back to
hypothesis — end to end in minutes instead of waiting for real setups to
show up live.

**Setup:**
1. Make sure `run_live.py` is running (as normal, real-time — see "Auto-start
   run_live.py after a reboot" below for the supervisor, or just run it
   manually in a console) *before* you start the replay, watching the same
   `--bridge-dir`/`--instrument` this chart's `Bridge Folder`/`Instrument`
   inputs point at.
2. Set this chart's Trade Account to a **Simulation account** (Sierra
   Chart's Trade menu), and confirm Trading/AutoTrading is enabled for it —
   Replay mode does not bypass or require anything different from this
   study's own checks, it only changes where the price data comes from.
3. Start Replay (Trade menu → Replay, or the Replay toolbar) at a **slow-ish
   speed — 1x real-time or a bit faster, not "instant"/fast-forward** (see
   why below), pointed at a past date range you want to test against.
4. Temporarily raise `Max Trades Per Day` (e.g. to 20-50) for the test run —
   the default of 3 is a real production safety limit and will cut a replay
   test short almost immediately once a few setups fire in quick succession.
   **Set it back to a sane real value before ever running this live.**
5. Set `Mode` to `Fully Auto` (or `Semi Auto` if you'd rather click each
   trigger by hand and just watch the bracket exits happen automatically —
   either tests the exit side; only Fully Auto also tests the automatic
   entry side).
6. Watch Sierra Chart's Message Log for entry/refusal lines (see above) and
   its Trade Activity / Orders / Positions windows for the actual fills,
   P&L, and stop/target exits as replayed bars pass through those levels.

**Why replay speed matters here, specifically:** `run_live.py` polls the
bridge files on a **real wall-clock** timer (every 5 seconds, `--history-out`
dedup and all), and this study's own bridge-file writes (`live_state.csv`,
`order_proposal.csv`) are throttled by `Bridge File Refresh Interval`
against **real wall-clock time** too (`time(nullptr)`, not the chart's
simulated replay clock) — neither side has any notion of Sierra Chart's
replay speed. At a fast/instant replay speed, hours of replayed bars can
fly past between two real-world 5-second polls, so `run_live.py` only ever
sees a coarse, aliased sample of what actually happened — most intraday
structure the hypothesis engine would react to in real time simply never
gets seen. Running the replay at roughly 1x (or a modest multiple) keeps
enough real wall-clock time between bars for the bridge's 5-second sampling
to actually track the session the way it would live. This is a real
limitation of the file-polling bridge design (see ARCHITECTURE.md's "ACSIL
<-> Python bridge" section on why plain files were chosen over a
lower-latency protocol like DTC), not a bug to fix before testing — it's
simply the same tradeoff live trading already accepts, carried over to
replay.

**What this test does and doesn't validate:** it proves the *mechanics* —
does a valid proposal actually turn into a real bracket order, does that
order actually fill and later exit via its stop or target, does the daily
trade cap and kill switch actually stop new entries, does the scale-out
split actually submit the right number of separate orders. It does **not**
validate whether the underlying hypothesis/regime signals are *good* trades
— `regime.py`'s thresholds are still explicitly uncalibrated (see
ARCHITECTURE.md), so don't read a replay test's win/loss record as a
verdict on the strategy, only as a check that the automation faithfully does
what the proposal says.

**Fixed after an eleventh real test:** even with "Draw Developing Value Area
Lines" switched to Yes (ruling out the tenth test's hypothesis), VAH/VAL/POC
still came back 0 -- but `live_state.csv`'s VWAP/delta columns (read via the
exact same cross-chart array function) had real, non-zero values the whole
time, proving the read mechanism itself was fine. The real cause: the chart
the Volume Value Area Lines study was attached to (Chart Studies dialog,
`ID:1`) turned out to be a native **TPO / Market Profile chart type**
(Settings dialog titled "... Period: 1 Days, TPOs: 0.50 x 30 min"), not a
regular OHLC chart -- its own "Highlight TPO Value Area" / "Highlight TPO
POC" inputs are what actually drew the value-area rows and POC line the
chart visibly showed. That native TPO profile display is baked into the
chart engine itself and has no subgraphs at all; it is not the same thing as
a "Volume Value Area Lines" study and can't be read via ACSIL. The Volume
Value Area Lines study instance living on that same TPO chart (a genuinely
separate, second item in the Chart Studies list) really was just never
computing anything. **Fix: add/use the Volume Value Area Lines study on a
normal (non-TPO) OHLC or volume-bar chart of the same instrument instead**,
and point `Volume Value Area Lines Chart Number`/`...Study ID` at that chart
and its `ID:` there. Confirmed working on a real test: switching to a plain
"5000 Volume" chart's own Volume Value Area Lines instance made
`live VAH subgraph value` immediately report real prices (`29488.8`,
`29489.2`) instead of `0`.

Updated the Install section above (step 3) to call this out explicitly:
double-check that whatever chart you add Volume Value Area Lines to is a
regular price/volume chart, not a TPO or Market/Volume Profile chart type --
those have their own native value-area display that looks identical at a
glance but is architecturally unrelated and unreadable from ACSIL.

**Fixed after a twelfth real test:** `daily_profile_export.csv` gained
duplicate rows for the same date days after the eleventh test's fix, even
though only one study instance was confirmed running (checked via the
`Trading Hypothesis Display config: thisChart=...` startup log line -- only
one chart number ever appeared). The Message Log explained it directly:
Sierra Chart periodically tags this chart for a **full recalculation** on
its own (cross-chart dependencies from other studies/charts in the same
chartbook -- `Chart #1 has tagged chart #5 for full recalculation`), and a
full recalculation resets this study's persistent storage, including
`LastExportedDateYYYYMMDD` back to 0 -- even though the trading day hasn't
actually changed. Every such recalculation then looked exactly like a
fresh, never-exported day rollover and re-appended a duplicate row for the
same date (confirmed directly: a `daily export firing` log line, and a
second real row for 2026-09-16, immediately after a logged "Performing a
full recalculation" message). Fixed by checking the file's own last row
before writing (`ReadLastDailyProfileDate`) -- the persistent int can't
survive a recalculation reset, but the file on disk can, so a match there
means this day was already exported and the write (and its diagnostic
log/subgraph probe) is skipped, just resyncing the persistent int instead.
`trading_system/bridge/csv_bridge.py`'s `read_daily_profiles()` also now
defensively keeps the *last* row per date if a duplicate ever does slip
through some other way, rather than silently trusting whichever came
first -- belt and suspenders, not a substitute for this fix.

**Diagnosing a tenth real test:** even with the ninth test's full backward
scan in place, VAH/VAL/POC still exported as 0. A raw dump of the array at a
spread of indices (`0, 300, 800, 1300, 1600, ..., 1799`) came back 0.0 at
*every single one*, including index 0 -- the oldest bar in the whole
1800-bar history. That rules out a scan bug: subgraph index 1 ("Vol Value
Area High") is simply never populated under this study's current settings,
even though the chart visibly draws real, non-zero value-area lines. The
likely cause: "Draw Developing Value Area Lines = No" disables the
developing subgraphs (0-2) entirely, and the actual non-developing/final
values the chart draws from live at different subgraph indices. Added a
probe that reads subgraph indices 0-9 on the same study/chart and logs the
last and scanned value for each, to find the correct index from real
evidence instead of guessing again.

**Fixed after a ninth real test:** even with the eighth test's fix in place,
VAH/VAL/POC still exported as 0 -- confirmed via the diagnostic log line
added in that fix: `VAHArraySize=1800 VAH[last]=0 VAL[last]=0 POC[last]=0`.
The array is real (1800 fully-computed values), but reading exactly one bar
back was still 0.0 -- meaning more than one trailing bar on the Volume
Value Area Lines study's own chart belonged to today's still-open trading
day, not just the last one. Fixed by scanning backward through the array
for the last actually non-zero value instead of assuming it's one or two
bars back.

**Fixed after an eighth real test:** even with the backward-scan fix from
the seventh test in place and a confirmed rebuild, `daily_profile_export.csv`
still produced a garbage row -- `0004-62-75,NQ,0,0,0` -- nearly identical to
the "already fixed" `0004-62-73` garbage from before. Two bugs, both real:

1. **The date was never actually fixed.** `sc.GetTradingDayDate()`'s return
   value was assumed to already be a plain YYYYMMDD int (based on an earlier
   "confirmed by the real compiler" note that chaining `.GetDate()` onto it
   failed to compile). That assumption was wrong: the garbage output both
   times decodes to a small number in the 46,000s -- consistent with a raw
   day-count date serial, not YYYYMMDD digits -- and it barely moved between
   the two tests (73 vs 75), exactly as you'd expect from a day-count
   incrementing by 1 across ~2 days of testing. Whatever this function
   actually returns, its numeric encoding is not reliably decodable as
   YYYYMMDD. Fixed by no longer trying: the value is now used purely as an
   opaque "did the trading day change" comparison token (`==`/`!=`, which
   works regardless of encoding), and the date actually written to the CSV
   is built separately, straight from the bar's own `SCDateTime` via its
   `GetYear()`/`GetMonth()`/`GetDay()` accessors.
2. **VAH/VAL/POC were still 0.** The Volume Value Area Lines study runs on
   its own `Time Period Type = Days` chart with developing lines off. As
   soon as a new day starts, that chart gets a new bar immediately, and that
   bar's subgraph value stays `0.0` until its period actually closes --
   because developing values are switched off. That chart's own day
   boundary (calendar midnight, by default) doesn't necessarily line up
   with the session-based trading-day boundary used elsewhere in this file,
   so its last bar can be "today, still empty" exactly when the export
   fires. Since `0.0` is never a plausible real price level, the read now
   falls back to the array's previous (fully closed) value whenever the
   last one is exactly `0.0`.

A diagnostic log line (`Trading Hypothesis Display: daily export firing.
...`) was also added right at the write, printing the resolved date and the
VAH/VAL/POC array sizes and last values -- check Message Log after the next
export if the row still looks wrong.

**Fixed after a seventh real test:** even with the date bug, the Volume
Value Area Lines Study ID, and the duplicate chart-3 instance all fixed,
`daily_profile_export.csv` still never got a real row across an entire
trading day. Cause: the day-rollover check compared only the chart's last
two bars to detect "the day just changed" -- but this study is non-looping
(`sc.AutoLoop=0`), so a full recalculation (a DLL rebuild, a settings
change on this or a cross-chart study, or Sierra Chart itself being closed
across the rollover) calls it just once with the chart already several
bars or days past the boundary. The two-bar comparison then never fires,
and that day's export is silently, permanently skipped -- with no error,
since nothing actually failed. This session triggered several full
recalculations right around a session boundary while debugging the other
issues, which is almost certainly why no real row ever appeared. Fixed by
scanning backward for the last bar of the most recently closed day
whenever the current day differs from what's already been exported,
instead of assuming the transition happened on the last two bars.

**Fixed after a sixth real test:** the hypothesis text box (`hypothesis.txt`
drawn on the chart) was being written and drawn correctly -- confirmed via
`sc.UseTool()` running with no error -- but was invisible on a real chart
with a light/white background. Cause: its color was hardcoded to
`RGB(255, 255, 255)` (white), which is only visible on a dark chart
background. Added a `Hypothesis Text Color` input (same pattern as the
composite zone colors), defaulted to black instead of white. If your chart
background is dark, change this input back to a light color.

**Fixed after a fifth real test:** the `date` column in a real
`daily_profile_export.csv` came out as garbage like `0004-62-73` instead of
a real calendar date -- which would have crashed the Python side outright
(`date.fromisoformat` rejects a month of 62). Cause: `sc.GetTradingDayDate()`
returns a plain `int` already in YYYYMMDD format (the real compiler already
confirmed this -- chaining `.GetDate()` straight onto its return fails to
compile, since the return type is `int`, not a class with a `GetDate()`
method). The code was instead wrapping that int in an `SCDateTime` first and
calling `.GetDate()` on *that*, which compiles fine but is silently wrong:
`SCDateTime`'s int constructor treats a raw int as its own internal
date-time serial value, not as YYYYMMDD digits, corrupting the date on the
round trip. This had been in the code since the very first build and only
surfaced now because nobody had opened `daily_profile_export.csv` and
checked the date column's actual value until this test. Fixed by using
`sc.GetTradingDayDate()`'s return directly, no `SCDateTime` involved, in
both the daily profile export block and the newer session-open capture.
**If you already have a `daily_profile_export.csv` with rows like this,
delete it before the next session rollover** -- the bad rows will crash
`read_daily_profiles()` on the Python side, and unlike `live_state.csv` this
file is appended to, not overwritten, so the garbage rows won't clear
themselves out on their own.

**Fixed after a fourth real test:** even with all Study IDs resolved and the
file writing successfully, `vwap_monthly` and `vwap_weekly` in `live_state.csv`
came out as `0` while `vwap_intraday` and `cum_delta` were correct. Cause: the
monthly/weekly VWAP studies live on different charts (e.g. a daily chart and a
weekly chart) with far fewer bars than the master chart's intraday bar count,
but the code was indexing every cross-chart array with the master chart's own
last bar index. That index is far past the end of the shorter monthly/weekly
arrays; `SCFloatArray` silently returns `0.0` for an out-of-range index
instead of erroring, so the bug produced no error message at all — just
plausible-looking zeros. Fixed by always reading each cross-chart array's own
last index (`LastArrayValue()`) instead of the master chart's bar index. This
also affected `VAH`/`VAL`/`POC` in `daily_profile_export.csv` whenever the
Volume Value Area Lines study lives on a different chart, and is fixed the
same way.

**Improved after a third real test:** once all Study IDs resolve correctly,
`daily_profile_export.csv` and `live_state.csv` writes can still fail with
`could not open ... for writing.` — this used to be logged with no further
detail. Both messages now include the `errno`/`strerror` reason, same as the
directory-creation error below. In practice this error means the file is
locked by something else, not a code/config problem, since Study ID
resolution and directory creation already succeeded by this point. The two
realistic causes:
- **The file is open in another program** — e.g. you opened `live_state.csv`
  in Excel or Notepad to check its contents. Windows locks it exclusively
  while it's open there; close it and the next refresh will write fine.
- **More than one "Trading Hypothesis Display" instance is still configured
  for the same `Instrument`** — e.g. leftover instances on other charts from
  before you consolidated to a single master instance (see "Cross-chart
  Study IDs" below). Two instances both trying to `ios::trunc`-open the same
  path at the same moment race each other; only one instance per instrument
  should ever have all five Study IDs configured.
Check the errno the Message Log now shows: `errno 13` (permission
denied/sharing violation) points at one of the two causes above; `errno 2`
(no such file or directory) would instead mean `bridgeDir` doesn't actually
exist, which "What live_state.csv is and when it appears" and the
directory-creation fix above should already have ruled out.

**Fixed after a real test run:** the first real test (on a chart with
plenty of history behind it) confirmed `VAHArraySize` was non-zero — the
Volume Value Area Lines connection works — but no `daily_profile_export.csv`
was ever created, and the bridge folder didn't even exist on disk. Two
things were wrong, both now fixed:
- The directory-creation failure was invisible: `_mkdir()`'s return value
  was ignored, so if it failed the code carried on as if the folder
  existed. It now checks the result and logs the exact `errno`/reason to
  the Message Log if creation fails.
- Worse, the "already exported this day" tracker was updated even when the
  write failed — so a single failed attempt permanently skipped that day
  forever, with no retry and no file ever produced. It's now only updated
  after a successful write.
If you rebuild this version and the folder still isn't created, the
Message Log will now say exactly why (e.g. a permissions error) instead of
staying silent.

**Fixed again after a second real test:** even with the fix above, the
folder still never appeared and the Message Log stayed completely silent —
no "could not create directory" message at all. The reason: directory
creation only ran inside the day-close export block, which itself only
runs once ACSIL detects a real trading-day rollover on the chart's bars.
If that rollover hasn't happened yet (e.g. right after adding the study,
or on a chart/replay setup where it takes a while to trigger), the
mkdir code is never reached — no folder, but also no error, since the
line that would log one never executed either. The bridge folder is now
created as soon as the study first calculates, independent of any
day-close detection, so you can check for it on disk immediately after
adding the study instead of waiting for a session rollover.

## What is verified vs. what to check first if it doesn't compile

Verified against real ACSIL documentation and example source (not just
guessed): `sc.Input[]` declaration pattern and setter/getter methods
(`SetString`, `SetStudyID`, `SetInt`, `SetIntLimits`, `SetColor`,
`SetYesNo`, `SetCustomInputStrings`), the `s_UseTool` struct fields used
here (`ChartNumber`, `DrawingType`, `LineNumber`, `AddMethod`,
`BeginDateTime`/`EndDateTime`, `BeginValue`/`EndValue`, `Color`,
`SecondaryColor`, `TransparencyLevel`, `LineWidth`, `Text`, `FontSize`,
`UseRelativeVerticalValues`), `sc.UseTool()`, `sc.GetStudyArrayUsingID()`,
and the `int& X = sc.GetPersistentInt(n);` persistent-variable idiom.

Also added `sc.CalculationPrecedence = LOW_PREC_LEVEL;`, which the ACSIL
docs call out as required when a study reads another study's array, so the
Volume Profile study is guaranteed to have already calculated for the bar.

**Fixed after the first real remote build (build2.sierrachart.com), per its
actual compiler errors:**

- `Input_BridgeFolder.GetString()` returns `const char*`, which can't be
  concatenated with a string literal directly (`const char* + "\\"` isn't
  valid C++). Fixed by wrapping it in `std::string(...)` first.
- `SCDateTime` has no `GetDateString()` member — that call is gone.
  `lastClosedYYYYMMDD` (already obtained from the documented `GetDate()`
  int) is now formatted to `"YYYY-MM-DD"` by a small local
  `FormatISODateFromYYYYMMDD()` helper instead.

Both of these compiled clean conceptually against what the error output
showed; if you rebuild and hit anything else, paste the errors again and
I'll fix those specific lines the same way.

**Not compiled against the real SDK header, so check these first if new
errors show up:**

- `sc.GetPersistentInt()` / `sc.GetPersistentDouble()` and
  `sc.GetTradingDayDate()` are standard, widely-used ACSIL idioms I'm
  confident exist, but I did not independently re-verify their exact
  signatures against your SDK header this session (unlike the items above,
  which I did pull from real docs/example code, and unlike the two bugs
  above, which the real compiler already confirmed and are now fixed). Low
  risk, but worth a second look if the build complains about them
  specifically.
- `TextTool.UseRelativeVerticalValues` for a text drawing — confirmed to
  exist on `s_UseTool` and used for rectangle/marker positioning in
  verified examples, but I have not confirmed it behaves the same way for
  `DRAWING_TEXT` specifically. If the hypothesis box doesn't anchor to a
  fixed corner as expected, this is the first place to look — Sierra
  Chart's own `ACS_Source/studies.cpp` has `scsf_UseToolExample*` functions
  worth comparing against.
- `sc.GetStudyArrayUsingID` assumes the Volume Value Area Lines study is on
  the *same* chart. If you keep it on a different chart in the same
  chartbook, swap it for `sc.GetStudyArrayFromChartUsingID(ChartNumber,
  StudyID, SubgraphIndex, Array)` instead (add a Chart Number input).
- `_mkdir` (from `<direct.h>`) for auto-creating the bridge folder is a
  standard Windows C-runtime call, not ACSIL-specific, and confirmed to
  exist on Windows — low risk, but it's new since the last build so it's
  worth watching the next compile for it specifically.

Please compile this once and send me the exact error list if any of the
above don't match your Sierra Chart version — I'll fix the specific lines
rather than guess further.

## Not implemented yet (later steps)

- The Python side that reads `live_state.csv` and does something with it
  (VWAP bounce/rejection detection, the `hypothesis/` package's A/B day
  classification) — Step 3 only gets the reading pipeline into Sierra
  Chart and the numbers into the bridge file; hypothesis logic itself is
  still to come.
- Any order placement / risk management (`Input_Mode` is declared but not
  wired to anything — Step 4).

## Step 3: VWAP tiers + cumulative delta — same "point at a Study ID" pattern

Same idea as the Volume Value Area Lines study: no VWAP/delta computation
happens in this file — it just reads whatever your own VWAP/delta studies
already calculate via `sc.GetStudyArrayUsingID`, using the confirmed
pattern from Step 2. Not independently re-verified against your SDK header
this session (same caveat as the "not compiled against the real SDK
header" list above), so if the build complains about `sc.Close` (the
current bar's close price, used for `last_price`) or `localtime_s`
specifically, those are the first two things to check.

### Cross-chart Study IDs (each tier can live on its own chart)

A real setup often spreads the VWAP tiers across several charts instead of
stacking every study on one chart (e.g. weekly VWAP on chart 1, monthly VWAP
on chart 4, intraday VWAP + cumulative delta on chart 5). `sc.GetStudyArrayUsingID`
only ever reads from the **current** chart — if you point a Study ID input
at a study that actually lives on a different chart, ACSIL silently
resolves it against whatever has that same ID number on *this* chart
instead (Study IDs are numbered separately per chart, so two studies on two
different charts can easily both be "ID:1"). This is exactly what caused
monthly and weekly VWAP to come out identical in a real test: both inputs
pointed at ID:1, but only one of the two actual VWAP studies lived on the
chart where the Trading Hypothesis Display instance was running.

Fixed by adding a **Chart Number** input next to every Study ID input
(Volume Value Area Lines, VWAP Monthly/Weekly/Intraday, Cumulative Delta).
Each defaults to `0`, meaning "this chart" (same behavior as before). Set
it to the real chart number a tier's study lives on to read it across
charts — the code then uses `sc.GetStudyArrayFromChartUsingID` instead.
Find a chart's number via Sierra Chart's **Window** menu (lists every open
chart with its number) or the chart window's title bar.

Example matching a layout of weekly VWAP=chart 1, volume profile=chart 2,
monthly VWAP=chart 4, intraday VWAP + cumulative delta=chart 5: run **one**
Trading Hypothesis Display instance (e.g. on chart 5, alongside the
intraday VWAP/delta studies it can read as "this chart") and set:
- `VWAP Chart Number: Monthly Tier` = `4`
- `VWAP Chart Number: Weekly Tier` = `1`
- `VWAP Chart Number: Intraday Tier` = `0` (or `5`, same effect)
- `Cumulative Delta Chart Number` = `0` (or `5`)
- `Volume Value Area Lines Chart Number` = whichever chart that study is
  actually on (`0` if it's on chart 5 too)

**The Study ID inputs themselves are plain typed numbers, not a picker.**
Sierra Chart's Study ID picker widget only lists studies on the chart
you're currently editing, so it can't offer a study that lives on a
different chart at all — even with the Chart Number input pointing there
correctly, the picker for e.g. `VWAP Study ID: Monthly Tier` would show
`<Main Price Graph>` with no way to select ID 1 on chart 4. So these five
inputs (Volume Value Area Lines, the three VWAP tiers, Cumulative Delta)
are declared as plain integers instead: open the target study's own
Settings dialog and read the number after "ID:" in its title bar (e.g.
"Study Settings: Main VWAP. ID:1" means type `1`), then type that number
directly into the Study ID input.

**Run only one bridge-writing instance per instrument.** If you keep
multiple Trading Hypothesis Display instances active (one per chart) that
all point at the *same* `Instrument`/`Bridge Folder`, they all write the
same `live_state.csv`/`daily_profile_export.csv` files, and whichever
instance's refresh timer fires last wins — silently overwriting a
correctly-configured write with a partially-configured one. Configure one
instance fully (using the Chart Number inputs above to reach every tier)
and disable or repurpose the others.

## Auto-start run_live.py after a reboot

`run_live_supervisor.bat` (repo root) plus a Task Scheduler "at logon"
entry closes the one real gap found when investigating position/state
recovery after a restart (see ARCHITECTURE.md's Step 4 notes): nothing
previously restarted `run_live.py` itself after the Windows machine
rebooted. Until it's running again, `order_proposal.csv` just goes stale
and the manual trigger's existing `Max Order Proposal Age` check already
refuses to act on it — a safe failure mode even before this, just not a
self-healing one.

**What the `.bat` does:** loops forever, launching
`python -m trading_system.run_live --bridge-dir "C:\SierraChart\TradingHypothesisBridge" --instrument NQ --history-out "C:\SierraChart\TradingHypothesisBridge\NQ\historical_intraday.csv"`
from `C:\LukacinoGit`, and relaunching it 10 seconds after it ever exits
for any reason — a stray Ctrl+C, the console window closing, a crash.
`run_live.py`'s own `while True` loop already never exits on an ordinary
tick error (bad row, missing file — see its `except Exception` clause), so
in practice this supervisor only ever matters for something outside
`run_live.py`'s own control killing the whole process, reboot included.
It deliberately does **not** run `git pull` itself — code updates stay a
manual, reviewed step exactly as before. Since every restart launches a
brand-new Python process that re-reads `trading_system/` from disk, a
manual `git pull` followed by one Ctrl+C on the running window is enough
to pick up a new build; the loop then relaunches it with the new code
automatically. All output (the same lines you'd see in the console today,
plus a start/restart timestamp line from the `.bat` itself) is appended to
`C:\SierraChart\TradingHypothesisBridge\NQ\run_live_supervisor.log`.

**One-time setup — Startup folder shortcut (confirmed working; use this
first).** On a locked-down machine (e.g. a trading VPS), `schtasks /create`
can fail with "Přístup byl odepřen" / "Access denied" for a non-admin user
even with `/rl limited` — confirmed on the user's real deployment. A
shortcut in the per-user Startup folder needs no special privileges at all
and starts at the same point in the login process:
1. `Win+R` → `shell:startup` → Enter — opens your Startup folder.
2. In File Explorer, open `C:\LukacinoGit`, right-click
   `run_live_supervisor.bat` → Send to → Desktop (create shortcut).
3. Drag that new desktop shortcut into the Startup folder from step 1.

To also start it right now instead of waiting for the next logon, just run
`C:\LukacinoGit\run_live_supervisor.bat` directly (double-click it, or run
it from a cmd window already `cd`'d into `C:\LukacinoGit`). If a
`run_live.py` window from before this setup is still open, close it first
(Ctrl+C, possibly more than once since it's a loop, then close the window)
so you don't end up with two instances writing the same bridge files.

**Alternative — Task Scheduler**, on a machine that actually grants
`schtasks` permission to your user:
```
cd C:\LukacinoGit
git pull
schtasks /create /tn "Lukacino run_live" /tr "C:\LukacinoGit\run_live_supervisor.bat" /sc onlogon /rl limited /f
schtasks /run /tn "Lukacino run_live"
```
The `/create` line registers a task that starts the supervisor at your next
logon (it does not start it immediately); `/run` starts it right now too.
To remove it later: `schtasks /delete /tn "Lukacino run_live" /f`.

Either way, a console window titled after the `.bat` opens and stays
open — that's the supervisor loop; leave it running (minimizing it is
fine), same as you'd leave `run_live.py`'s own window running today.

**Checking it's working:** open
`C:\SierraChart\TradingHypothesisBridge\NQ\run_live_supervisor.log` — a
fresh `[<date> <time>] Starting run_live.py` line confirms the supervisor
fired, followed immediately by the `Watching ... (poll every 5s) ...` line
`run_live.py` always prints on startup (the `.bat` launches Python with
`-u`/unbuffered specifically so this line shows up right away instead of
sitting invisible in an output buffer for minutes — confirmed against a
real run where the log briefly looked empty/hung before this fix).

**To stop it for good** (not just for one restart): close the supervisor's
console window, then either delete the Startup-folder shortcut from step 3
above, or (Task Scheduler route) `schtasks /delete /tn "Lukacino run_live" /f`,
so it doesn't come back after your next logon.
