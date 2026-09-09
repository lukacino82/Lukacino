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
    SCInputRef Input_VP_VAHSubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VP_VALSubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VP_POCSubgraph = sc.Input[++InputIdx];

    // Sierra Chart's native VWAP study only computes one time-period type
    // per instance, so the monthly/weekly/intraday tiers need three
    // separate VWAP study instances on this chart, each pointed to here.
    SCInputRef Input_VWAP_MonthlyStudyID = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_MonthlySubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_WeeklyStudyID = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_WeeklySubgraph = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_IntradayStudyID = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_IntradaySubgraph = sc.Input[++InputIdx];

    SCInputRef Input_Delta_StudyID = sc.Input[++InputIdx];
    SCInputRef Input_Delta_Subgraph = sc.Input[++InputIdx];

    SCInputRef Input_ShowCompositeZones = sc.Input[++InputIdx];
    SCInputRef Input_ShowHypothesisText = sc.Input[++InputIdx];
    SCInputRef Input_RefreshIntervalSeconds = sc.Input[++InputIdx];
    SCInputRef Input_HypothesisFontSize = sc.Input[++InputIdx];
    SCInputRef Input_HypothesisVerticalPosition = sc.Input[++InputIdx]; // 0-100, 100=top

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
        Input_VP_StudyID.Name = "Volume Value Area Lines Study ID (this chart)";
        Input_VP_StudyID.SetStudyID(0);

        Input_VP_VAHSubgraph.Name = "Vol Value Area High Subgraph Index (SG2 = 1)";
        Input_VP_VAHSubgraph.SetInt(1);

        Input_VP_VALSubgraph.Name = "Vol Value Area Low Subgraph Index (SG3 = 2)";
        Input_VP_VALSubgraph.SetInt(2);

        Input_VP_POCSubgraph.Name = "Vol POC Subgraph Index (SG1 = 0)";
        Input_VP_POCSubgraph.SetInt(0);

        // Point each at a separate "VWAP" study instance on this chart, one
        // per Time Period Type (Sierra Chart's VWAP study only computes a
        // single tier per instance). Subgraph 0 is the VWAP line itself on
        // a default VWAP study; check your chart's Subgraphs tab and adjust
        // if you've customized it (e.g. added standard-deviation bands
        // ahead of it).
        Input_VWAP_MonthlyStudyID.Name = "VWAP Study ID: Monthly Tier (this chart)";
        Input_VWAP_MonthlyStudyID.SetStudyID(0);
        Input_VWAP_MonthlySubgraph.Name = "VWAP Monthly Subgraph Index";
        Input_VWAP_MonthlySubgraph.SetInt(0);

        Input_VWAP_WeeklyStudyID.Name = "VWAP Study ID: Weekly Tier (this chart)";
        Input_VWAP_WeeklyStudyID.SetStudyID(0);
        Input_VWAP_WeeklySubgraph.Name = "VWAP Weekly Subgraph Index";
        Input_VWAP_WeeklySubgraph.SetInt(0);

        Input_VWAP_IntradayStudyID.Name = "VWAP Study ID: Intraday Tier (this chart)";
        Input_VWAP_IntradayStudyID.SetStudyID(0);
        Input_VWAP_IntradaySubgraph.Name = "VWAP Intraday Subgraph Index";
        Input_VWAP_IntradaySubgraph.SetInt(0);

        // Point this at whichever cumulative-delta study you use (e.g. a
        // "Numbers Bars - Bid vs Ask Volume Difference" or a Cumulative
        // Delta Bars study). Subgraph index depends on which one — check
        // its Subgraphs tab.
        Input_Delta_StudyID.Name = "Cumulative Delta Study ID (this chart)";
        Input_Delta_StudyID.SetStudyID(0);
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
    sc.GetStudyArrayUsingID(Input_VP_StudyID.GetStudyID(), Input_VP_VAHSubgraph.GetInt(), VAHArray);
    sc.GetStudyArrayUsingID(Input_VP_StudyID.GetStudyID(), Input_VP_VALSubgraph.GetInt(), VALArray);
    sc.GetStudyArrayUsingID(Input_VP_StudyID.GetStudyID(), Input_VP_POCSubgraph.GetInt(), POCArray);

    SCFloatArray VWAPMonthlyArray, VWAPWeeklyArray, VWAPIntradayArray, DeltaArray;
    sc.GetStudyArrayUsingID(Input_VWAP_MonthlyStudyID.GetStudyID(), Input_VWAP_MonthlySubgraph.GetInt(), VWAPMonthlyArray);
    sc.GetStudyArrayUsingID(Input_VWAP_WeeklyStudyID.GetStudyID(), Input_VWAP_WeeklySubgraph.GetInt(), VWAPWeeklyArray);
    sc.GetStudyArrayUsingID(Input_VWAP_IntradayStudyID.GetStudyID(), Input_VWAP_IntradaySubgraph.GetInt(), VWAPIntradayArray);
    sc.GetStudyArrayUsingID(Input_Delta_StudyID.GetStudyID(), Input_Delta_Subgraph.GetInt(), DeltaArray);

    // Log the resolved config once so you can verify it immediately instead
    // of waiting for end-of-day rollover to find out something's wrong.
    // A VAH array size of 0 here means Input_VP_StudyID isn't pointing at a
    // real, already-calculated study — check the "Volume Value Area Lines
    // Study ID" input first if you see that.
    int& HasLoggedStartupConfig = sc.GetPersistentInt(2);
    if (!HasLoggedStartupConfig)
    {
        std::stringstream cfg;
        cfg << "Trading Hypothesis Display config: dailyProfilePath=" << dailyProfilePath
            << " compositesPath=" << compositesPath << " hypothesisPath=" << hypothesisPath
            << " liveStatePath=" << liveStatePath
            << " VolumeValueAreaLinesStudyID=" << Input_VP_StudyID.GetStudyID()
            << " VAHArraySize=" << VAHArray.GetArraySize()
            << " VWAPMonthlyStudyID=" << Input_VWAP_MonthlyStudyID.GetStudyID()
            << " VWAPMonthlyArraySize=" << VWAPMonthlyArray.GetArraySize()
            << " VWAPWeeklyStudyID=" << Input_VWAP_WeeklyStudyID.GetStudyID()
            << " VWAPWeeklyArraySize=" << VWAPWeeklyArray.GetArraySize()
            << " VWAPIntradayStudyID=" << Input_VWAP_IntradayStudyID.GetStudyID()
            << " VWAPIntradayArraySize=" << VWAPIntradayArray.GetArraySize()
            << " DeltaStudyID=" << Input_Delta_StudyID.GetStudyID()
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

    if (sc.ArraySize > 1 && VAHArray.GetArraySize() > 1)
    {
        const int lastClosedBar = sc.ArraySize - 2; // last fully closed bar
        SCDateTime lastClosedTradingDay = sc.GetTradingDayDate(sc.BaseDateTimeIn[lastClosedBar]);
        SCDateTime currentTradingDay = sc.GetTradingDayDate(sc.BaseDateTimeIn[sc.ArraySize - 1]);

        int lastClosedYYYYMMDD = lastClosedTradingDay.GetDate();
        if (currentTradingDay.GetDate() != lastClosedYYYYMMDD
            && lastClosedYYYYMMDD != LastExportedDateYYYYMMDD)
        {
            std::ofstream out(dailyProfilePath, std::ios::app);
            if (out.is_open())
            {
                out << FormatISODateFromYYYYMMDD(lastClosedYYYYMMDD) << "," << instrument << ","
                    << VALArray[lastClosedBar] << "," << VAHArray[lastClosedBar] << ","
                    << POCArray[lastClosedBar] << "\n";
                // Only remember this day as exported once the write actually
                // succeeded — otherwise a transient failure (e.g. the
                // directory not existing yet) would silently and permanently
                // skip this day, with no file ever produced and no retry.
                LastExportedDateYYYYMMDD = lastClosedYYYYMMDD;
            }
            else
            {
                std::string msg = "Trading Hypothesis Display: could not open "
                                 + dailyProfilePath + " for writing.";
                sc.AddMessageToLog(msg.c_str(), 1);
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
    if (sc.ArraySize > 0 && VWAPMonthlyArray.GetArraySize() > 0
        && VWAPWeeklyArray.GetArraySize() > 0 && VWAPIntradayArray.GetArraySize() > 0
        && DeltaArray.GetArraySize() > 0)
    {
        const int lastBar = sc.ArraySize - 1;
        std::ofstream liveOut(liveStatePath, std::ios::trunc);
        if (liveOut.is_open())
        {
            liveOut << "timestamp,instrument,last_price,vwap_monthly,vwap_weekly,vwap_intraday,cum_delta\n";
            liveOut << FormatISODateTime(nowTimeT) << "," << instrument << ","
                    << sc.Close[lastBar] << "," << VWAPMonthlyArray[lastBar] << ","
                    << VWAPWeeklyArray[lastBar] << "," << VWAPIntradayArray[lastBar] << ","
                    << DeltaArray[lastBar] << "\n";
        }
        else
        {
            std::string msg = "Trading Hypothesis Display: could not open "
                             + liveStatePath + " for writing.";
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
            TextTool.Color = RGB(255, 255, 255);
            TextTool.Text.Format("%s", fullText.c_str()); // "%s" as the format string keeps any literal '%' in fullText harmless
            TextTool.AddAsUserDrawnDrawing = 0;
            sc.UseTool(TextTool);
        }
    }
}
