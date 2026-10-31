# Research Export (Sierra Chart ACSIL)

Study that writes closed bars and the footprint (bid / ask volume at each price of each bar) to CSV. The files make it
possible to test absorption, imbalance and repeated tests of a level on real tick data (not possible on 1-minute data).

**Status:** the code was written without access to Sierra Chart and has **not been compiled or tested**. The first build
may need a small fix (names of members of `s_VolumeAtPriceV2`, `GetDateTimeYMDHMS`). Send me the compiler message and I
will correct it.

## Installation
1. Copy `ResearchExport.cpp` to `C:\SierraChart\ACS_Source\`.
2. Sierra Chart: Analysis > Build Custom Studies DLL > select the file > Build (Remote Build for the 64-bit version).
3. Analysis > Studies > Add Custom Study > "Research Export (bars + footprint CSV)".

## Chart settings
- **Time zone:** Global Settings > Time Zone (or Chart > Chart Settings) = `America/New_York`, so that times are in ET,
  consistent with the research data.
- **Bars:** 1 minute (or the bars you test on), contract `ESZ26_FUT_CME` or the continuous contract.
- **Intraday data storage time unit: 1 Tick** (Chart > Chart Settings > Intraday Data Storage Time Unit), otherwise the
  volume at price is not exact. Tick history depends on the data service (CME feed with the Sierra Chart service has the
  tick data stored; older history has to be downloaded or comes from the .scid files you already have).
- **Number of days to load:** as many as needed (365+). Bid/ask volume exists only for periods recorded with it.

## Output
Files in the `Data` folder of Sierra Chart:
- `ResearchExport_<symbol>_bars.csv`: `DateTime,Open,High,Low,Close,Volume,BidVolume,AskVolume,Trades`
- `ResearchExport_<symbol>_footprint.csv`: `DateTime,Price,BidVolume,AskVolume` (one row per price and bar)

A full recalculation (Analysis > Recalculate) rewrites the files. Send the files (a zip; large) through Google Drive
folder "30 Screeny VWAP HA delta" or GitHub.
