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
