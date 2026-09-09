# TradingHypothesisStudy.cpp — build notes

## Install

1. Copy `TradingHypothesisStudy.cpp` into your Sierra Chart `ACS_Source`
   folder.
2. In Sierra Chart: Analysis → Build Custom Studies DLL (or add this file to
   your existing custom studies DLL project) and build.
3. Add the study ("Trading Hypothesis Display") to each instrument's chart
   that also carries your Volume Profile study.
4. Set the study's inputs: `Instrument` (must match the subfolder name the
   Python engine writes to), `Bridge Folder`, and the Volume Profile study
   ID + VAH/VAL/POC subgraph indexes (open your Volume Profile study's
   settings to find its Study ID, or use Sierra Chart's "Study Values"
   window to confirm which subgraph is which).

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

**Not compiled against the real SDK header, so check these first:**

- `sc.GetPersistentInt()` / `sc.GetPersistentDouble()` and
  `sc.GetTradingDayDate()` are standard, widely-used ACSIL idioms I'm
  confident exist, but I did not independently re-verify their exact
  signatures against your SDK header this session (unlike the items above,
  which I did pull from real docs/example code). Low risk, but worth a
  second look if the build complains about them specifically.

- `SCDateTime::GetDateString()` — I used it with a `0` format argument by
  analogy with similar ACSIL calls; if this overload doesn't match what
  your `sierrachart.h` declares, replace the daily-profile date export with
  a direct `sprintf`-style format from `lastClosedTradingDay.GetDate()`
  instead (it's documented as returning a `YYYYMMDD` integer, which is
  trivial to split into `Y/100/100`, `Y/100%100`, `Y%100`... or just export
  the raw `YYYYMMDD` int and have the Python side's CSV reader accept
  either format — tell me which one compiles and I'll match the Python
  side to it).
- `TextTool.UseRelativeVerticalValues` for a text drawing — confirmed to
  exist on `s_UseTool` and used for rectangle/marker positioning in
  verified examples, but I have not confirmed it behaves the same way for
  `DRAWING_TEXT` specifically. If the hypothesis box doesn't anchor to a
  fixed corner as expected, this is the first place to look — Sierra
  Chart's own `ACS_Source/studies.cpp` has `scsf_UseToolExample*` functions
  worth comparing against.
- `sc.GetStudyArrayUsingID` assumes the Volume Profile study is on the
  *same* chart. If you keep VAH/VAL/POC on a different chart in the same
  chartbook, swap it for `sc.GetStudyArrayFromChartUsingID(ChartNumber,
  StudyID, SubgraphIndex, Array)` instead (add a Chart Number input).

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
