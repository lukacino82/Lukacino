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
4. Add the study ("Trading Hypothesis Display") to the same chart.
5. Set its inputs: `Instrument` (must match the subfolder name the Python
   engine writes to), `Bridge Folder`, and point `Volume Value Area Lines
   Study ID (this chart)` at the study from step 3 (click that input row to
   pick it from the chart's study list). The VAH/VAL/POC subgraph index
   inputs already default to the confirmed values (VAH=1, VAL=2, POC=0 —
   i.e. SG2/SG3/SG1), so leave them unless your Subgraphs tab shows a
   different order.

`Bridge Folder` is just a path typed into that Input — the study now
creates it (and the `<Instrument>` subfolder under it) on disk itself the
first time it needs to write, so you don't need to create it by hand
first. If it still can't write there (e.g. permissions), you'll now see a
message in Sierra Chart's **Message Log** (Window → Message Log) saying
exactly which path it failed to open, instead of silently doing nothing.

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

- Reading the monthly/weekly/intraday VWAP tiers and cumulative delta
  (Step 2 focused on the composite zones + hypothesis box first, since
  those are the newest/most custom part; VWAP/delta reading is the same
  `GetStudyArrayUsingID` pattern applied to your existing VWAP/Delta
  studies — tell me their Study IDs and subgraph layout and I'll wire them
  in the same way).
- Any order placement / risk management (`Input_Mode` is declared but not
  wired to anything — Step 4).
