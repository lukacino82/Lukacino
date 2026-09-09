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
   docs/support board and from a real chart's Subgraphs tab). Configure it:
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
6. Add the study ("Trading Hypothesis Display") to the same chart.
7. Set its inputs: `Instrument` (must match the subfolder name the Python
   engine writes to), `Bridge Folder`, and point `Volume Value Area Lines
   Study ID (this chart)` at the study from step 3 (click that input row to
   pick it from the chart's study list). The VAH/VAL/POC subgraph index
   inputs already default to the confirmed values (VAH=1, VAL=2, POC=0 —
   i.e. SG2/SG3/SG1), so leave them unless your Subgraphs tab shows a
   different order. Likewise point the three `VWAP Study ID: ... Tier`
   inputs at the studies from step 4 and `Cumulative Delta Study ID` at the
   study from step 5.

`Bridge Folder` is just a path typed into that Input — the study now
creates it (and the `<Instrument>` subfolder under it) on disk itself the
first time it needs to write, so you don't need to create it by hand
first. If it still can't write there (e.g. permissions), you'll now see a
message in Sierra Chart's **Message Log** (Window → Message Log) saying
exactly which path it failed to open, instead of silently doing nothing.

The study also logs its resolved config once right after you add it (no
need to wait for end-of-day rollover to check it): the bridge file paths,
every Study ID it resolved to, and each one's array size. If any
`...ArraySize` shows `0`, that Study ID input isn't pointing at a real,
already-calculated study yet — that's the first thing to fix for that
particular reading (Volume Value Area Lines, one of the three VWAP tiers,
or the delta study).

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
