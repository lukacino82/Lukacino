// Trading Hypothesis Study — ACSIL skeleton (Steps 2-3)
//
// Responsibilities of this study, per ARCHITECTURE.md:
//   1. Export this chart's daily volume-profile (VAL/VAH/POC), read from a
//      Volume Value Area Lines study already on this chart, to
//      <BridgeFolder>/<Instrument>/daily_profile_export.csv once per closed
//      trading day.
//   2. Export the current VWAP tiers (monthly/weekly/intraday) and
//      cumulative delta, read from separate VWAP/delta studies on this
//      chart, to <BridgeFolder>/<Instrument>/live_state.csv every refresh
//      interval (overwritten in place — it's a live snapshot, not a log).
//   3. Read back <BridgeFolder>/<Instrument>/composites.csv and
//      hypothesis.txt (written by the Python engine) and draw the composite
//      zones and the hypothesis text box on this chart.
// It does NOT compute composite merge/invalidation logic, VWAP bounce
// detection, or hypothesis text itself — that logic lives (or will live)
// in trading_system/, unit-tested in Python. Duplicating it here in C++
// would risk the two implementations drifting apart.
//
// VERIFICATION STATUS: every sc.Input method, the s_UseTool field names,
// sc.UseTool(), sc.GetStudyArrayUsingID / sc.GetStudyArrayFromChartUsingID,
// SCDateTime::SetDateTimeYMDHMS, and the persistent-variable idiom below
// are confirmed against real ACSIL documentation/example code. The exact
// on-screen anchoring of the hypothesis text box (UseRelativeVerticalValues
// for a fixed corner position) is my best-effort reading of the drawing
// tools doc, NOT compiled/tested against the real Sierra Chart SDK header —
// check that block first if the study fails to compile or the text box
// doesn't land where expected, and adjust the value scale/anchoring calls
// to match what the compiler's sierrachart.h actually declares.

#include "sierrachart.h"
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <ctime>
#include <cstdio>
#include <direct.h> // _mkdir
#include <cerrno>
#include <cstring>

SCDLLName("Trading Hypothesis Study")

namespace {

struct CompositeRow {
    std::string instrument;
    std::string start_date;
    std::string end_date;
    double val = 0.0;
    double vah = 0.0;
    int day_count = 0;
    std::string tier;
    bool active = true;
    std::string invalidated_on;
    std::string remaining_ranges; // "lo:hi;lo:hi"
};

std::vector<std::string> SplitCSVLine(const std::string& line, char delim) {
    std::vector<std::string> fields;
    std::stringstream ss(line);
    std::string field;
    while (std::getline(ss, field, delim))
        fields.push_back(field);
    return fields;
}

std::vector<std::pair<double, double>> ParseRemainingRanges(const std::string& text) {
    std::vector<std::pair<double, double>> ranges;
    if (text.empty())
        return ranges;
    std::stringstream ss(text);
    std::string segment;
    while (std::getline(ss, segment, ';')) {
        auto colon = segment.find(':');
        if (colon == std::string::npos)
            continue;
        double lo = std::stod(segment.substr(0, colon));
        double hi = std::stod(segment.substr(colon + 1));
        ranges.emplace_back(lo, hi);
    }
    return ranges;
}

std::vector<CompositeRow> ReadCompositesCSV(const std::string& path) {
    std::vector<CompositeRow> rows;
    std::ifstream file(path);
    if (!file.is_open())
        return rows;

    std::string line;
    std::getline(file, line); // header
    while (std::getline(file, line)) {
        if (line.empty())
            continue;
        auto f = SplitCSVLine(line, ',');
        if (f.size() < 10)
            continue;
        CompositeRow row;
        row.instrument = f[0];
        row.start_date = f[1];
        row.end_date = f[2];
        row.val = std::stod(f[3]);
        row.vah = std::stod(f[4]);
        row.day_count = std::stoi(f[5]);
        row.tier = f[6];
        row.active = (f[7] == "1");
        row.invalidated_on = f[8];
        row.remaining_ranges = f[9];
        rows.push_back(row);
    }
    return rows;
}

std::string ReadWholeFile(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open())
        return "";
    std::stringstream ss;
    ss << file.rdbuf();
    return ss.str();
}

SCDateTime ParseISODate(const std::string& iso) {
    // Expects "YYYY-MM-DD".
    SCDateTime dt;
    if (iso.size() < 10)
        return dt;
    int year = std::stoi(iso.substr(0, 4));
    int month = std::stoi(iso.substr(5, 2));
    int day = std::stoi(iso.substr(8, 2));
    dt.SetDateTimeYMDHMS(year, month, day, 0, 0, 0);
    return dt;
}

int TierFillTransparency(const std::string& tier, int t23, int t4, int t5) {
    if (tier == "4D") return t4;
    if (tier == "5D+") return t5;
    return t23; // "2-3D"
}

// SCDateTime has no GetDateString() member (confirmed by the real compiler,
// not just the docs) — build "YYYY-MM-DD" ourselves from the YYYYMMDD int
// that GetDate() does provide.
// _mkdir only creates one missing level at a time, so call it on each path
// level you need to guarantee, not just the deepest one. Returns an empty
// string on success (including "already exists"), or a description of the
// failure (with errno) otherwise, so a caller can surface it instead of
// silently doing nothing when the directory truly couldn't be created.
std::string EnsureDirectoryExists(const std::string& path) {
    if (_mkdir(path.c_str()) == 0)
        return "";
    if (errno == EEXIST)
        return "";
    return "could not create directory " + path + ": " + std::strerror(errno)
         + " (errno " + std::to_string(errno) + ")";
}

std::string FormatISODateFromYYYYMMDD(int yyyymmdd) {
    int year = yyyymmdd / 10000;
    int month = (yyyymmdd / 100) % 100;
    int day = yyyymmdd % 100;
    char buf[11];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d", year, month, day);
    return std::string(buf);
}

// Naive local "YYYY-MM-DDTHH:MM:SS", matching what Python's
// datetime.fromisoformat() expects on the live_state.csv bridge file.
std::string FormatISODateTime(time_t t) {
    struct tm tmVal;
    localtime_s(&tmVal, &t);
    char buf[32];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
        tmVal.tm_year + 1900, tmVal.tm_mon + 1, tmVal.tm_mday,
        tmVal.tm_hour, tmVal.tm_min, tmVal.tm_sec);
    return std::string(buf);
}

// sc.GetStudyArrayUsingID only ever looks at the current chart. A real setup
// often spreads the VWAP tiers (and the delta/volume-profile studies) across
// several charts in the same chartbook -- e.g. one chart per tier -- rather
// than stacking every study onto one chart, so this falls back to
// sc.GetStudyArrayFromChartUsingID whenever chartNumber points elsewhere.
// chartNumber <= 0, or equal to this study's own chart, means "this chart".
void GetStudyArrayAnyChart(SCStudyInterfaceRef sc, int chartNumber, int studyID, int subgraphIndex, SCFloatArray& array) {
    if (chartNumber > 0 && chartNumber != sc.ChartNumber)
        sc.GetStudyArrayFromChartUsingID(chartNumber, studyID, subgraphIndex, array);
    else
        sc.GetStudyArrayUsingID(studyID, subgraphIndex, array);
}

// A cross-chart array is indexed by *its own* chart's bar count, which does
// not match this chart's sc.ArraySize -- e.g. a monthly VWAP chart with far
// fewer bars than this chart's 500-volume bars. Indexing it with this
// chart's bar index reads past the end; SCFloatArray silently returns 0.0f
// for an out-of-range index rather than crashing, which is exactly the
// "vwap_monthly/vwap_weekly always 0" symptom this was causing. Always read
// the array's own last index to get its latest value.
float LastArrayValue(SCFloatArray& array) {
    return array.GetArraySize() > 0 ? array[array.GetArraySize() - 1] : 0.0f;
}

const int LINE_NUMBER_BASE_COMPOSITE = 500000;
const int LINE_NUMBER_HYPOTHESIS_TEXT = 999001;

} // namespace

SCSFExport scsf_TradingHypothesisDisplay(SCStudyInterfaceRef sc)
{
    int InputIdx = -1;

    SCInputRef Input_Instrument = sc.Input[++InputIdx];
    SCInputRef Input_BridgeFolder = sc.Input[++InputIdx];

    SCInputRef Input_Mode = sc.Input[++InputIdx]; // reserved for Step 4, not wired yet

    SCInputRef Input_VP_StudyID = sc.Input[++InputIdx];
    SCInputRef Input_VP_ChartNumber = sc.Input[++InputIdx];
    SCInputRef Input_VP_VAHSubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VP_VALSubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VP_POCSubgraph = sc.Input[++InputIdx];

    // Sierra Chart's native VWAP study only computes one time-period type
    // per instance, so the monthly/weekly/intraday tiers need three
    // separate VWAP study instances -- on this chart, or spread across
    // several charts in the same chartbook via the Chart Number inputs
    // below (0 = this chart).
    SCInputRef Input_VWAP_MonthlyStudyID = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_MonthlyChartNumber = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_MonthlySubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_WeeklyStudyID = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_WeeklyChartNumber = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_WeeklySubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_IntradayStudyID = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_IntradayChartNumber = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_IntradaySubgraph = sc.Input[++InputIdx];

    SCInputRef Input_Delta_StudyID = sc.Input[++InputIdx];
    SCInputRef Input_Delta_ChartNumber = sc.Input[++InputIdx];
    SCInputRef Input_Delta_Subgraph = sc.Input[++InputIdx];

    SCInputRef Input_ShowCompositeZones = sc.Input[++InputIdx];
    SCInputRef Input_ShowHypothesisText = sc.Input[++InputIdx];
    SCInputRef Input_RefreshIntervalSeconds = sc.Input[++InputIdx];
    SCInputRef Input_HypothesisFontSize = sc.Input[++InputIdx];
    SCInputRef Input_HypothesisVerticalPosition = sc.Input[++InputIdx]; // 0-100, 100=top
    SCInputRef Input_HypothesisTextColor = sc.Input[++InputIdx];

    SCInputRef Input_Color_Tier_2_3 = sc.Input[++InputIdx];
    SCInputRef Input_Color_Tier_4 = sc.Input[++InputIdx];
    SCInputRef Input_Color_Tier_5Plus = sc.Input[++InputIdx];
    SCInputRef Input_Color_Invalidated = sc.Input[++InputIdx];

    SCInputRef Input_Transparency_Tier_2_3 = sc.Input[++InputIdx];
    SCInputRef Input_Transparency_Tier_4 = sc.Input[++InputIdx];
    SCInputRef Input_Transparency_Tier_5Plus = sc.Input[++InputIdx];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Trading Hypothesis Display";
        sc.StudyDescription =
            "Reads composite zones and a hypothesis text box written by the "
            "Python trading engine and draws them on this chart; exports "
            "this chart's daily volume profile for the engine to consume. "
            "See ARCHITECTURE.md in the trading_system repo.";
        sc.AutoLoop = 0; // we manage our own once-per-recalc / once-per-day logic
        sc.UpdateAlways = 1; // so the refresh-interval timer keeps ticking with no new bars
        sc.CalculationPrecedence = LOW_PREC_LEVEL; // ensure the Volume Profile study has already calculated

        Input_Instrument.Name = "Instrument (bridge subfolder name, e.g. ES)";
        Input_Instrument.SetString("ES");

        Input_BridgeFolder.Name = "Bridge Folder (shared with Python engine)";
        Input_BridgeFolder.SetString("C:\\SierraChart\\TradingHypothesisBridge");

        Input_Mode.Name = "Mode (reserved, not wired to order logic yet)";
        Input_Mode.SetCustomInputStrings("Hypothesis Only;Semi Auto;Fully Auto");
        Input_Mode.SetCustomInputIndex(0);

        // Point this at a "Volume Value Area Lines" study (Time Period Type
        // = Days, Length = 1, Draw Developing Value Area Lines = No), NOT
        // at a "Volume Profile" study drawn as a TPO Profile — that draw
        // type only exposes Color subgraphs, not the numeric POC/VAH/VAL
        // arrays this study needs. Confirmed against a real chart's
        // Subgraphs tab: Vol POC = SG1 (index 0), Vol Value Area High =
        // SG2 (index 1), Vol Value Area Low = SG3 (index 2).
        //
        // Plain number, not a "pick a study" dropdown: Sierra Chart's
        // Study ID picker only lists studies on THIS chart, so it can't
        // select a study living on another chart even though the Chart
        // Number input below lets this study read one. Type in the number
        // shown after "ID:" in the target study's own Settings dialog
        // title bar (e.g. "Study Settings: Main VWAP. ID:1").
        Input_VP_StudyID.Name = "Volume Value Area Lines Study ID (type the number, see ID: in that study's own title bar)";
        Input_VP_StudyID.SetInt(0);
        Input_VP_StudyID.SetIntLimits(0, 9999);

        Input_VP_ChartNumber.Name = "Volume Value Area Lines Chart Number (0 = this chart)";
        Input_VP_ChartNumber.SetInt(0);

        Input_VP_VAHSubgraph.Name = "Vol Value Area High Subgraph Index (SG2 = 1)";
        Input_VP_VAHSubgraph.SetInt(1);

        Input_VP_VALSubgraph.Name = "Vol Value Area Low Subgraph Index (SG3 = 2)";
        Input_VP_VALSubgraph.SetInt(2);

        Input_VP_POCSubgraph.Name = "Vol POC Subgraph Index (SG1 = 0)";
        Input_VP_POCSubgraph.SetInt(0);

        // Point each at a separate "VWAP" study instance, one per Time
        // Period Type (Sierra Chart's VWAP study only computes a single
        // tier per instance). The Chart Number input lets each tier live on
        // a different chart in the same chartbook (0 = this chart) --
        // sc.GetStudyArrayUsingID only ever sees the current chart, so a
        // tier's VWAP study on another chart needs its real chart number
        // here, not just its Study ID. Subgraph 0 is the VWAP line itself
        // on a default VWAP study; check that chart's Subgraphs tab and
        // adjust if it's been customized (e.g. standard-deviation bands
        // ahead of it).
        Input_VWAP_MonthlyStudyID.Name = "VWAP Study ID: Monthly Tier (type the number, see ID: in that study's own title bar)";
        Input_VWAP_MonthlyStudyID.SetInt(0);
        Input_VWAP_MonthlyStudyID.SetIntLimits(0, 9999);
        Input_VWAP_MonthlyChartNumber.Name = "VWAP Chart Number: Monthly Tier (0 = this chart)";
        Input_VWAP_MonthlyChartNumber.SetInt(0);
        Input_VWAP_MonthlySubgraph.Name = "VWAP Monthly Subgraph Index";
        Input_VWAP_MonthlySubgraph.SetInt(0);

        Input_VWAP_WeeklyStudyID.Name = "VWAP Study ID: Weekly Tier (type the number, see ID: in that study's own title bar)";
        Input_VWAP_WeeklyStudyID.SetInt(0);
        Input_VWAP_WeeklyStudyID.SetIntLimits(0, 9999);
        Input_VWAP_WeeklyChartNumber.Name = "VWAP Chart Number: Weekly Tier (0 = this chart)";
        Input_VWAP_WeeklyChartNumber.SetInt(0);
        Input_VWAP_WeeklySubgraph.Name = "VWAP Weekly Subgraph Index";
        Input_VWAP_WeeklySubgraph.SetInt(0);

        Input_VWAP_IntradayStudyID.Name = "VWAP Study ID: Intraday Tier (type the number, see ID: in that study's own title bar)";
        Input_VWAP_IntradayStudyID.SetInt(0);
        Input_VWAP_IntradayStudyID.SetIntLimits(0, 9999);
        Input_VWAP_IntradayChartNumber.Name = "VWAP Chart Number: Intraday Tier (0 = this chart)";
        Input_VWAP_IntradayChartNumber.SetInt(0);
        Input_VWAP_IntradaySubgraph.Name = "VWAP Intraday Subgraph Index";
        Input_VWAP_IntradaySubgraph.SetInt(0);

        // Point this at whichever cumulative-delta study you use (e.g. a
        // "Numbers Bars - Bid vs Ask Volume Difference" or a Cumulative
        // Delta Bars study). Subgraph index depends on which one — check
        // its Subgraphs tab.
        Input_Delta_StudyID.Name = "Cumulative Delta Study ID (type the number, see ID: in that study's own title bar)";
        Input_Delta_StudyID.SetInt(0);
        Input_Delta_StudyID.SetIntLimits(0, 9999);
        Input_Delta_ChartNumber.Name = "Cumulative Delta Chart Number (0 = this chart)";
        Input_Delta_ChartNumber.SetInt(0);
        Input_Delta_Subgraph.Name = "Cumulative Delta Subgraph Index";
        Input_Delta_Subgraph.SetInt(0);

        Input_ShowCompositeZones.Name = "Show Composite Zones";
        Input_ShowCompositeZones.SetYesNo(1);

        Input_ShowHypothesisText.Name = "Show Hypothesis Text Box";
        Input_ShowHypothesisText.SetYesNo(1);

        Input_RefreshIntervalSeconds.Name = "Bridge File Refresh Interval (seconds)";
        Input_RefreshIntervalSeconds.SetInt(5);
        Input_RefreshIntervalSeconds.SetIntLimits(1, 3600);

        Input_HypothesisFontSize.Name = "Hypothesis Text Font Size";
        Input_HypothesisFontSize.SetInt(10);

        Input_HypothesisVerticalPosition.Name = "Hypothesis Text Vertical Position (0=bottom,100=top)";
        Input_HypothesisVerticalPosition.SetInt(92);
        Input_HypothesisVerticalPosition.SetIntLimits(0, 100);

        // Was hardcoded white, which is invisible on a light/white chart
        // background -- confirmed on a real chart (text was being drawn,
        // just unreadable). Defaulting to black instead; change this if
        // your chart background is dark.
        Input_HypothesisTextColor.Name = "Hypothesis Text Color";
        Input_HypothesisTextColor.SetColor(RGB(0, 0, 0));

        Input_Color_Tier_2_3.Name = "Composite Color: 2-3 Day Tier";
        Input_Color_Tier_2_3.SetColor(RGB(255, 192, 203)); // light pink

        Input_Color_Tier_4.Name = "Composite Color: 4 Day Tier";
        Input_Color_Tier_4.SetColor(RGB(255, 105, 180)); // darker pink

        Input_Color_Tier_5Plus.Name = "Composite Color: 5+ Day Tier";
        Input_Color_Tier_5Plus.SetColor(RGB(199, 21, 133)); // darkest pink

        Input_Color_Invalidated.Name = "Composite Color: Invalidated Remainder";
        Input_Color_Invalidated.SetColor(RGB(128, 128, 128)); // grey

        Input_Transparency_Tier_2_3.Name = "Fill Transparency: 2-3 Day Tier";
        Input_Transparency_Tier_2_3.SetInt(75);
        Input_Transparency_Tier_2_3.SetIntLimits(0, 100);

        Input_Transparency_Tier_4.Name = "Fill Transparency: 4 Day Tier";
        Input_Transparency_Tier_4.SetInt(45);
        Input_Transparency_Tier_4.SetIntLimits(0, 100);

        Input_Transparency_Tier_5Plus.Name = "Fill Transparency: 5+ Day Tier";
        Input_Transparency_Tier_5Plus.SetInt(20);
        Input_Transparency_Tier_5Plus.SetIntLimits(0, 100);

        return;
    }

    const std::string instrument = Input_Instrument.GetString();
    const std::string bridgeDir = std::string(Input_BridgeFolder.GetString()) + "\\" + instrument;
    const std::string dailyProfilePath = bridgeDir + "\\daily_profile_export.csv";
    const std::string compositesPath = bridgeDir + "\\composites.csv";
    const std::string hypothesisPath = bridgeDir + "\\hypothesis.txt";
    const std::string liveStatePath = bridgeDir + "\\live_state.csv";

    SCFloatArray VAHArray, VALArray, POCArray;
    GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), Input_VP_VAHSubgraph.GetInt(), VAHArray);
    GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), Input_VP_VALSubgraph.GetInt(), VALArray);
    GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), Input_VP_POCSubgraph.GetInt(), POCArray);

    SCFloatArray VWAPMonthlyArray, VWAPWeeklyArray, VWAPIntradayArray, DeltaArray;
    GetStudyArrayAnyChart(sc, Input_VWAP_MonthlyChartNumber.GetInt(), Input_VWAP_MonthlyStudyID.GetInt(), Input_VWAP_MonthlySubgraph.GetInt(), VWAPMonthlyArray);
    GetStudyArrayAnyChart(sc, Input_VWAP_WeeklyChartNumber.GetInt(), Input_VWAP_WeeklyStudyID.GetInt(), Input_VWAP_WeeklySubgraph.GetInt(), VWAPWeeklyArray);
    GetStudyArrayAnyChart(sc, Input_VWAP_IntradayChartNumber.GetInt(), Input_VWAP_IntradayStudyID.GetInt(), Input_VWAP_IntradaySubgraph.GetInt(), VWAPIntradayArray);
    GetStudyArrayAnyChart(sc, Input_Delta_ChartNumber.GetInt(), Input_Delta_StudyID.GetInt(), Input_Delta_Subgraph.GetInt(), DeltaArray);

    // Log the resolved config once so you can verify it immediately instead
    // of waiting for end-of-day rollover to find out something's wrong.
    // A VAH array size of 0 here means Input_VP_StudyID isn't pointing at a
    // real, already-calculated study — check the "Volume Value Area Lines
    // Study ID" input first if you see that.
    int& HasLoggedStartupConfig = sc.GetPersistentInt(2);
    if (!HasLoggedStartupConfig)
    {
        std::stringstream cfg;
        cfg << "Trading Hypothesis Display config: thisChart=" << sc.ChartNumber
            << " dailyProfilePath=" << dailyProfilePath
            << " compositesPath=" << compositesPath << " hypothesisPath=" << hypothesisPath
            << " liveStatePath=" << liveStatePath
            << " VolumeValueAreaLinesStudyID=" << Input_VP_StudyID.GetInt()
            << " VolumeValueAreaLinesChart=" << Input_VP_ChartNumber.GetInt()
            << " VAHArraySize=" << VAHArray.GetArraySize()
            << " VWAPMonthlyStudyID=" << Input_VWAP_MonthlyStudyID.GetInt()
            << " VWAPMonthlyChart=" << Input_VWAP_MonthlyChartNumber.GetInt()
            << " VWAPMonthlyArraySize=" << VWAPMonthlyArray.GetArraySize()
            << " VWAPWeeklyStudyID=" << Input_VWAP_WeeklyStudyID.GetInt()
            << " VWAPWeeklyChart=" << Input_VWAP_WeeklyChartNumber.GetInt()
            << " VWAPWeeklyArraySize=" << VWAPWeeklyArray.GetArraySize()
            << " VWAPIntradayStudyID=" << Input_VWAP_IntradayStudyID.GetInt()
            << " VWAPIntradayChart=" << Input_VWAP_IntradayChartNumber.GetInt()
            << " VWAPIntradayArraySize=" << VWAPIntradayArray.GetArraySize()
            << " DeltaStudyID=" << Input_Delta_StudyID.GetInt()
            << " DeltaChart=" << Input_Delta_ChartNumber.GetInt()
            << " DeltaArraySize=" << DeltaArray.GetArraySize();
        sc.AddMessageToLog(cfg.str().c_str(), 0);
        HasLoggedStartupConfig = 1;
    }

    // Create the bridge folder as soon as the study runs, not only when a
    // trading day first closes: the day-close export block below only
    // executes after a real session rollover is detected on this chart's
    // bars, which can be a long wait (or may never trigger, e.g. on a chart
    // whose bar data doesn't span a rollover yet). Creating the directory
    // here means it's verifiable on disk immediately, and any permission
    // problem is surfaced right away instead of silently waiting for the
    // first export attempt. Only marked done once creation actually
    // succeeds, so a transient failure (e.g. a locked drive) retries on the
    // next recalculation instead of being permanently skipped.
    int& HasCreatedBridgeDir = sc.GetPersistentInt(3);
    if (!HasCreatedBridgeDir)
    {
        std::string dirErr = EnsureDirectoryExists(Input_BridgeFolder.GetString());
        if (dirErr.empty())
            dirErr = EnsureDirectoryExists(bridgeDir);
        if (dirErr.empty())
            HasCreatedBridgeDir = 1;
        else
            sc.AddMessageToLog(("Trading Hypothesis Display: " + dirErr).c_str(), 1);
    }

    // --- 1. Export the just-closed trading day's volume profile ---------
    // Persistent storage across recalculations: index 1 = last exported
    // trading day as YYYYMMDD, reused via sc.GetPersistentInt (a standard
    // ACSIL idiom for state that must survive across calls).
    int& LastExportedDateYYYYMMDD = sc.GetPersistentInt(1);

    // Gated on Input_VP_StudyID itself (> 0), not on VAHArray.GetArraySize():
    // see the vwapDeltaConfigured comment below for why array size alone
    // doesn't reliably indicate a real, resolved study.
    if (sc.ArraySize > 1 && Input_VP_StudyID.GetInt() > 0)
    {
        const int lastBar = sc.ArraySize - 1;
        // sc.GetTradingDayDate() returns a plain int already in YYYYMMDD
        // format (confirmed by the real compiler: chaining .GetDate()
        // straight onto its return fails to compile because the return
        // type is 'int', not a class with a GetDate() method). Wrapping it
        // in SCDateTime first and calling .GetDate() on THAT compiles fine
        // but is silently wrong -- SCDateTime's constructor treats a raw
        // int as its own internal date-time serial value, not as YYYYMMDD
        // digits, so the round trip corrupts the date. Confirmed against a
        // real daily_profile_export.csv: this previously produced garbage
        // like "0004-62-73" instead of a real calendar date. Use the int
        // directly, no SCDateTime involved.
        const int currentTradingDayYYYYMMDD = sc.GetTradingDayDate(sc.BaseDateTimeIn[lastBar]);

        // Don't rely on catching the exact bar where the day changes (the
        // previous version compared only the last two bars): a full
        // recalculation -- triggered by a DLL rebuild, a settings change on
        // this or a cross-chart study, or Sierra Chart itself being closed
        // across the rollover -- calls this non-looping (sc.AutoLoop=0)
        // function just once with the chart already several bars (or days)
        // past the boundary. The last-two-bars comparison then never fires,
        // and the whole day silently, permanently goes unexported.
        // Confirmed against a real chart: multiple full recalculations
        // during a session boundary meant daily_profile_export.csv never
        // got a real row at all. Instead, whenever the last bar's day
        // differs from what's already been exported, scan backward for the
        // last bar that still belongs to the most recently closed day.
        if (currentTradingDayYYYYMMDD != LastExportedDateYYYYMMDD)
        {
            int lastClosedBar = lastBar;
            while (lastClosedBar > 0
                && sc.GetTradingDayDate(sc.BaseDateTimeIn[lastClosedBar]) == currentTradingDayYYYYMMDD)
                --lastClosedBar;
            const int lastClosedYYYYMMDD = sc.GetTradingDayDate(sc.BaseDateTimeIn[lastClosedBar]);

            // lastClosedYYYYMMDD == currentTradingDayYYYYMMDD here means the
            // whole chart is a single, still-open day -- nothing has closed
            // yet to export.
            if (lastClosedYYYYMMDD != currentTradingDayYYYYMMDD
                && lastClosedYYYYMMDD != LastExportedDateYYYYMMDD)
            {
                std::ofstream out(dailyProfilePath, std::ios::app);
                if (out.is_open())
                {
                    out << FormatISODateFromYYYYMMDD(lastClosedYYYYMMDD) << "," << instrument << ","
                        << LastArrayValue(VALArray) << "," << LastArrayValue(VAHArray) << ","
                        << LastArrayValue(POCArray) << "\n";
                    // Only remember this day as exported once the write actually
                    // succeeded — otherwise a transient failure (e.g. the
                    // directory not existing yet) would silently and permanently
                    // skip this day, with no file ever produced and no retry.
                    LastExportedDateYYYYMMDD = lastClosedYYYYMMDD;
                }
                else
                {
                    // errno alone won't say "another process has this file open"
                    // on Windows (that's a sharing violation, not something
                    // fstream/errno models) but it does distinguish that from a
                    // real permissions/path problem, which "could not open" alone
                    // never did -- see the same reasoning on the live_state.csv
                    // write below.
                    std::string msg = "Trading Hypothesis Display: could not open "
                                     + dailyProfilePath + " for writing: "
                                     + std::strerror(errno) + " (errno " + std::to_string(errno) + ").";
                    sc.AddMessageToLog(msg.c_str(), 1);
                }
            }
        }
    }

    // --- 2. Throttle bridge-file reads/writes to Input_RefreshIntervalSeconds --
    double& LastRefreshUnixTime = sc.GetPersistentDouble(1);
    const time_t nowTimeT = time(nullptr);
    const double now = static_cast<double>(nowTimeT);
    if (now - LastRefreshUnixTime < Input_RefreshIntervalSeconds.GetInt())
        return;
    LastRefreshUnixTime = now;

    // --- 2b. Write the current VWAP tiers / cumulative delta snapshot ----
    // Unlike daily_profile_export.csv (one row per closed session), this
    // file is overwritten every refresh with the latest values for the
    // still-open session, so the Python engine always reads the most
    // recent snapshot rather than a growing history.
    //
    // Gate this on the Study ID inputs themselves (> 0), not on
    // GetArraySize(): a real test run showed sc.GetStudyArrayUsingID still
    // returns a *non-empty* array even when the Study ID input is left at
    // its default 0 (unconfigured) -- its size doesn't reliably signal a
    // real, resolved study the way the comments here previously assumed.
    // Checking the input directly is the only unambiguous way to know the
    // four VWAP/delta studies have actually been pointed at something.
    const bool vwapDeltaConfigured = Input_VWAP_MonthlyStudyID.GetInt() > 0
        && Input_VWAP_WeeklyStudyID.GetInt() > 0
        && Input_VWAP_IntradayStudyID.GetInt() > 0
        && Input_Delta_StudyID.GetInt() > 0;
    if (sc.ArraySize > 0 && vwapDeltaConfigured)
    {
        const int lastBar = sc.ArraySize - 1;

        // Track today's session open price: needed by the Python side's
        // A-day/B-day regime read (gap vs. yesterday's value area). Only
        // rescans for the first bar of the day when the trading day itself
        // changes, not on every refresh -- sc.GetTradingDayDate per bar
        // isn't free, and this only needs to run once per session.
        int& SessionOpenTradingDayYYYYMMDD = sc.GetPersistentInt(4);
        double& SessionOpenPrice = sc.GetPersistentDouble(2);
        // sc.GetTradingDayDate() returns a plain int already in YYYYMMDD
        // format -- see the fix/comment on the daily profile export block
        // above. Wrapping it in SCDateTime and calling .GetDate() on that
        // (what this block originally did) compiled fine but was confirmed
        // wrong against a real daily_profile_export.csv (garbage dates).
        // Use the int directly.
        const int currentTradingDayYYYYMMDD = sc.GetTradingDayDate(sc.BaseDateTimeIn[lastBar]);
        if (currentTradingDayYYYYMMDD != SessionOpenTradingDayYYYYMMDD)
        {
            int firstBarOfSession = lastBar;
            while (firstBarOfSession > 0
                && sc.GetTradingDayDate(sc.BaseDateTimeIn[firstBarOfSession - 1]) == currentTradingDayYYYYMMDD)
                --firstBarOfSession;
            SessionOpenPrice = sc.Open[firstBarOfSession];
            SessionOpenTradingDayYYYYMMDD = currentTradingDayYYYYMMDD;
        }

        std::ofstream liveOut(liveStatePath, std::ios::trunc);
        if (liveOut.is_open())
        {
            liveOut << "timestamp,instrument,last_price,session_open,vwap_monthly,vwap_weekly,vwap_intraday,cum_delta\n";
            liveOut << FormatISODateTime(nowTimeT) << "," << instrument << ","
                    << sc.Close[lastBar] << "," << SessionOpenPrice << ","
                    << LastArrayValue(VWAPMonthlyArray) << ","
                    << LastArrayValue(VWAPWeeklyArray) << "," << LastArrayValue(VWAPIntradayArray) << ","
                    << LastArrayValue(DeltaArray) << "\n";
        }
        else
        {
            // errno=13 (EACCES) here almost always means something else has
            // the file open exclusively right now -- e.g. it's open in
            // Excel/Notepad for inspection, or (if this ever regresses) a
            // second Trading Hypothesis Display instance for the same
            // Instrument still racing this one for the same path. errno=2
            // (ENOENT) instead would point at bridgeDir not actually
            // existing. Either way this is strictly more diagnosable than
            // the old bare "could not open" message.
            std::string msg = "Trading Hypothesis Display: could not open "
                             + liveStatePath + " for writing: "
                             + std::strerror(errno) + " (errno " + std::to_string(errno) + ").";
            sc.AddMessageToLog(msg.c_str(), 1);
        }
    }

    // --- 3. Draw composite zones ------------------------------------------
    if (Input_ShowCompositeZones.GetYesNo())
    {
        std::vector<CompositeRow> composites = ReadCompositesCSV(compositesPath);
        SCDateTime chartEnd = sc.BaseDateTimeIn[sc.ArraySize - 1];

        for (size_t i = 0; i < composites.size(); ++i)
        {
            const CompositeRow& row = composites[i];

            s_UseTool Tool;
            Tool.Clear();
            Tool.ChartNumber = sc.ChartNumber;
            Tool.DrawingType = DRAWING_RECTANGLEHIGHLIGHT;
            Tool.LineNumber = LINE_NUMBER_BASE_COMPOSITE + static_cast<int>(i);
            Tool.AddMethod = UTAM_ADD_OR_ADJUST;
            Tool.BeginDateTime = ParseISODate(row.start_date);
            Tool.EndDateTime = row.active ? chartEnd : ParseISODate(row.end_date);

            if (row.active)
            {
                Tool.BeginValue = row.val;
                Tool.EndValue = row.vah;
                Tool.Color = row.tier == "5D+" ? Input_Color_Tier_5Plus.GetColor()
                            : row.tier == "4D" ? Input_Color_Tier_4.GetColor()
                                                : Input_Color_Tier_2_3.GetColor();
                Tool.SecondaryColor = Tool.Color;
                Tool.TransparencyLevel = TierFillTransparency(
                    row.tier,
                    Input_Transparency_Tier_2_3.GetInt(),
                    Input_Transparency_Tier_4.GetInt(),
                    Input_Transparency_Tier_5Plus.GetInt());
                Tool.LineWidth = 1;
                sc.UseTool(Tool);
            }
            else
            {
                // Invalidated: draw only the non-overlapped remainder,
                // as a thin reference rectangle rather than a full magnet
                // zone, per the invalidation rule in the composite engine.
                auto remaining = ParseRemainingRanges(row.remaining_ranges);
                for (size_t r = 0; r < remaining.size(); ++r)
                {
                    s_UseTool RemTool;
                    RemTool.Clear();
                    RemTool.ChartNumber = sc.ChartNumber;
                    RemTool.DrawingType = DRAWING_RECTANGLEHIGHLIGHT;
                    RemTool.LineNumber = LINE_NUMBER_BASE_COMPOSITE + 100000
                                        + static_cast<int>(i) * 10 + static_cast<int>(r);
                    RemTool.AddMethod = UTAM_ADD_OR_ADJUST;
                    RemTool.BeginDateTime = ParseISODate(row.start_date);
                    RemTool.EndDateTime = ParseISODate(row.end_date);
                    RemTool.BeginValue = remaining[r].first;
                    RemTool.EndValue = remaining[r].second;
                    RemTool.Color = Input_Color_Invalidated.GetColor();
                    RemTool.SecondaryColor = RemTool.Color;
                    RemTool.TransparencyLevel = 80;
                    RemTool.LineWidth = 1;
                    sc.UseTool(RemTool);
                }
            }
        }
    }

    // --- 4. Draw the hypothesis text box ---------------------------------
    if (Input_ShowHypothesisText.GetYesNo())
    {
        std::string fullText = ReadWholeFile(hypothesisPath);
        if (!fullText.empty())
        {
            s_UseTool TextTool;
            TextTool.Clear();
            TextTool.ChartNumber = sc.ChartNumber;
            TextTool.DrawingType = DRAWING_TEXT;
            TextTool.LineNumber = LINE_NUMBER_HYPOTHESIS_TEXT;
            TextTool.AddMethod = UTAM_ADD_OR_ADJUST;
            TextTool.BeginDateTime = sc.BaseDateTimeIn[sc.ArraySize - 1];
            TextTool.UseRelativeVerticalValues = 1;
            TextTool.BeginValue = static_cast<float>(Input_HypothesisVerticalPosition.GetInt());
            TextTool.FontSize = Input_HypothesisFontSize.GetInt();
            TextTool.Color = Input_HypothesisTextColor.GetColor();
            TextTool.Text.Format("%s", fullText.c_str()); // "%s" as the format string keeps any literal '%' in fullText harmless
            TextTool.AddAsUserDrawnDrawing = 0;
            sc.UseTool(TextTool);
        }
    }
}
