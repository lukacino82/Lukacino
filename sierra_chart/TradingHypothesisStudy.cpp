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
#include <cmath>
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

// --- Step 4: order_proposal.csv (see trading_system/bridge/csv_bridge.py's
// OrderProposalSnapshot) -- overwritten in place every tick, like
// live_state.csv, never a growing history. An empty field means "None" on
// the Python side (direction="none" rows leave entry/stop/target_1/
// target_2/runner all empty) -- ParseOptionalDouble mirrors that instead of
// defaulting a missing stop/target to 0.0, which would silently read as a
// real (and catastrophically wrong) price level.
struct OrderProposalRow {
    std::string timestamp;
    std::string instrument;
    std::string direction; // "long", "short", or "none"
    std::string hypothesis_type;
    std::string confluence;
    bool hasEntry = false;
    double entry = 0.0;
    bool hasStop = false;
    double stop = 0.0;
    bool hasTarget1 = false;
    double target1 = 0.0;
    bool hasTarget2 = false;
    double target2 = 0.0;
    bool hasRunner = false;
    double runner = 0.0;
    int contracts = 0;
    // Scale-out split of `contracts` across target_1/target_2/runner,
    // decided by the Python side's confluence-based split (risk/order.py) --
    // always sums to `contracts`. See the ReadOrderProposalCSV column-count
    // fallback below for why these can't just be read unconditionally.
    int contractsTarget1 = 0;
    int contractsTarget2 = 0;
    int contractsRunner = 0;
};

void ParseOptionalDouble(const std::string& field, bool& hasValue, double& value) {
    if (field.empty()) {
        hasValue = false;
        value = 0.0;
        return;
    }
    hasValue = true;
    value = std::stod(field);
}

// Returns false if the file doesn't exist or has no data row yet (header
// only) -- same convention as the Python side's read_order_proposal().
bool ReadOrderProposalCSV(const std::string& path, OrderProposalRow& out) {
    std::ifstream file(path);
    if (!file.is_open())
        return false;
    std::string header, line;
    std::getline(file, header);
    if (!std::getline(file, line) || line.empty())
        return false;
    auto f = SplitCSVLine(line, ',');
    if (f.size() < 11)
        return false;
    out.timestamp = f[0];
    out.instrument = f[1];
    out.direction = f[2];
    out.hypothesis_type = f[3];
    out.confluence = f[4];
    ParseOptionalDouble(f[5], out.hasEntry, out.entry);
    ParseOptionalDouble(f[6], out.hasStop, out.stop);
    ParseOptionalDouble(f[7], out.hasTarget1, out.target1);
    ParseOptionalDouble(f[8], out.hasTarget2, out.target2);
    ParseOptionalDouble(f[9], out.hasRunner, out.runner);
    out.contracts = std::stoi(f[10]);
    // Older order_proposal.csv files (written by a run_live.py from before
    // the scale-out split existed) only have 11 columns -- fall back to a
    // single target_1-only leg, matching this study's pre-scale-out
    // behavior, rather than indexing past the end of `f` or refusing to
    // trade just because the two sides were redeployed a moment apart.
    if (f.size() >= 14)
    {
        out.contractsTarget1 = std::stoi(f[11]);
        out.contractsTarget2 = std::stoi(f[12]);
        out.contractsRunner = std::stoi(f[13]);
    }
    else
    {
        out.contractsTarget1 = out.contracts;
        out.contractsTarget2 = 0;
        out.contractsRunner = 0;
    }
    return true;
}

// Returns the date column of daily_profile_export.csv's last data row (the
// most recently exported trading day), or "" if the file doesn't exist or
// has no data rows yet. Used to guard the day-close export below against
// re-writing a duplicate row for a day it already exported -- see the
// comment at that call site for why the persistent-int bookkeeping alone
// isn't enough.
std::string ReadLastDailyProfileDate(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open())
        return "";
    std::string line, lastDataLine;
    std::getline(file, line); // header
    while (std::getline(file, line))
        if (!line.empty())
            lastDataLine = line;
    if (lastDataLine.empty())
        return "";
    const auto comma = lastDataLine.find(',');
    return comma == std::string::npos ? "" : lastDataLine.substr(0, comma);
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

// sc.GetTradingDayDate()'s return value is only ever used as an opaque
// comparison key here (does this bar belong to the same trading day as that
// one?) -- equality/inequality works no matter what numeric encoding it
// actually uses internally. Formatting it as if it were YYYYMMDD digits
// assumed a specific encoding that a real daily_profile_export.csv proved
// wrong twice now: both the SCDateTime-wrapped attempt and the later "use
// the int directly" attempt produced the same style of garbage
// ("0004-62-73", then "0004-62-75", two days apart matching two days of
// real testing) -- a low, slowly incrementing number consistent with a raw
// day-count serial, not YYYYMMDD. Sidestep the ambiguity entirely for the
// actual printed date: read the real calendar Y/M/D straight off the bar's
// own SCDateTime via its documented accessors instead of decoding any
// function's return value.
std::string FormatISODateFromSCDateTime(const SCDateTime& dt) {
    char buf[11];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d", dt.GetYear(), dt.GetMonth(), dt.GetDay());
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

// Calendar-date portion ("YYYY-MM-DD") of a naive local timestamp, used as
// the day boundary for the Max Trades Per Day safety cap below. Deliberately
// NOT sc.GetTradingDayDate()'s opaque comparison value (see
// FormatISODateFromSCDateTime's comment on why that can't be trusted as a
// real calendar date) -- a plain wall-clock date is trivial to persist to
// disk and compare across restarts/recalculations, which is exactly what a
// trade-count cap needs to survive.
std::string TodayDateString(time_t now) {
    return FormatISODateTime(now).substr(0, 10);
}

// Counts how many rows of trigger_log.csv (this study's own append-only
// record of every order it has actually placed) already belong to
// `dateStr`. Matches by a plain "dateStr," line prefix rather than a
// header-aware CSV parse -- deliberately robust to the file starting with or
// without a header line, since a header row never matches a date prefix.
// Reading the log itself (not a persistent int) is what makes this cap
// survive a Sierra Chart restart or the full-recalculation persistent-
// storage reset documented above for the daily profile export -- a persistent
// int alone would silently reset the count to 0 and defeat the cap exactly
// the way it caused duplicate profile rows.
int CountTriggersForDate(const std::string& path, const std::string& dateStr) {
    std::ifstream file(path);
    if (!file.is_open())
        return 0;
    const std::string prefix = dateStr + ",";
    int count = 0;
    std::string line;
    while (std::getline(file, line))
        if (line.rfind(prefix, 0) == 0)
            ++count;
    return count;
}

// Inverse of FormatISODateTime -- parses the same naive local
// "YYYY-MM-DDTHH:MM:SS" string order_proposal.csv/live_state.csv carry,
// so a manual order trigger can check the proposal's freshness against
// "now" using the same local-time convention ACSIL itself writes with.
// Returns 0 (treated as infinitely stale, never as "now") if the string is
// too short to parse.
time_t ParseISODateTimeToUnix(const std::string& iso) {
    if (iso.size() < 19)
        return 0;
    struct tm tmVal = {};
    tmVal.tm_year = std::stoi(iso.substr(0, 4)) - 1900;
    tmVal.tm_mon = std::stoi(iso.substr(5, 2)) - 1;
    tmVal.tm_mday = std::stoi(iso.substr(8, 2));
    tmVal.tm_hour = std::stoi(iso.substr(11, 2));
    tmVal.tm_min = std::stoi(iso.substr(14, 2));
    tmVal.tm_sec = std::stoi(iso.substr(17, 2));
    tmVal.tm_isdst = -1;
    return mktime(&tmVal);
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

// The Volume Value Area Lines study's own chart doesn't necessarily have
// "1 bar = 1 day": with developing lines off, every bar belonging to
// today's still-open trading day reads 0.0 until the day actually closes,
// and today's forming day can already span more than one trailing bar by
// the time this fires (confirmed against a real chart: a single
// fall-back-one-bar attempt still read 0.0 -- VAHArraySize=1800,
// VAH[last]=0 -- because more than one trailing bar belonged to the still-
// open day). 0.0 is never a plausible real price level, so scan backward
// for the last actually-computed (non-zero) value instead of assuming it's
// exactly one or two bars back.
float LastClosedProfileValue(SCFloatArray& array) {
    for (int i = array.GetArraySize() - 1; i >= 0; --i)
        if (array[i] != 0.0f)
            return array[i];
    return 0.0f;
}

// Every way this can end, in the exact order they're checked -- first
// failure wins, nothing after it is evaluated. Success means at least one
// scale-out leg was actually submitted (sc.BuyEntry/sc.SellEntry returned
// > 0); a proposal that fails every leg's submission is NOT Success (see
// TryFireOrderFromProposal's return at the very end).
enum class TriggerOutcome {
    Success,
    KillSwitchOff,
    NoProposalData,
    NoSignal,
    InstrumentMismatch,
    StaleProposal,
    BadContractCount,
    MissingRiskLevel,
    LegSumMismatch,
    LegPriceMissing,
    BackwardsStop,
    PositionAlreadyOpen,
    WorkingOrderExists,
    TradeCapReached,
    AllLegsFailed,
};

struct TriggerAttempt {
    TriggerOutcome outcome;
    // Empty when outcome == Success (the per-leg submission lines are
    // logged directly inside TryFireOrderFromProposal instead, since
    // there's one line per leg, not one summary line). Callers decide
    // whether/when to actually log this -- see the Semi Auto vs. Fully
    // Auto call sites below for why that differs between the two.
    std::string refusalMessage;
};

// The shared core of Step 4's order placement, used by both the Semi Auto
// manual trigger (one-shot, always logs) and Fully Auto (polled on a timer,
// logs are deduplicated by the caller) -- extracted so Fully Auto reuses
// the exact same, already real-hardware-verified checks and order-placement
// code instead of a second, divergent copy. `triggerLabel` becomes the
// leading phrase of every message this produces (e.g. "Trading Hypothesis
// Display: manual trigger" or "Trading Hypothesis Display: Fully Auto"), so
// the Message Log always shows which path actually fired.
//
// VERIFICATION STATUS: unchanged from before this was extracted into its
// own function -- see the comment that used to sit directly above this
// block (now above its two call sites) for exactly which parts are
// confirmed against real ACSIL docs vs. only the local g++ stub.
TriggerAttempt TryFireOrderFromProposal(
    SCStudyInterfaceRef sc,
    const std::string& orderProposalPath,
    const std::string& triggerLogPath,
    const std::string& instrument,
    bool tradingEnabled,
    int maxProposalAgeSeconds,
    int maxContractsSafetyCap,
    int maxTradesPerDay,
    time_t nowTimeT,
    double now,
    const std::string& triggerLabel)
{
    OrderProposalRow proposal;
    if (!tradingEnabled)
        return { TriggerOutcome::KillSwitchOff, triggerLabel
            + " fired but Trading Enabled is No (kill switch) -- refusing to act. Flip it back to Yes to resume." };
    if (!ReadOrderProposalCSV(orderProposalPath, proposal))
        return { TriggerOutcome::NoProposalData, triggerLabel
            + " fired but order_proposal.csv has no data row yet -- nothing to act on." };
    if (proposal.direction != "long" && proposal.direction != "short")
        return { TriggerOutcome::NoSignal, triggerLabel
            + " fired but the current proposal direction is '" + proposal.direction + "' -- nothing tradeable right now." };
    if (proposal.instrument != instrument)
        return { TriggerOutcome::InstrumentMismatch, triggerLabel
            + " fired but order_proposal.csv's instrument ('" + proposal.instrument
            + "') does not match this study's Instrument input ('" + instrument + "') -- refusing to act on a mismatched file." };
    if ((now - static_cast<double>(ParseISODateTimeToUnix(proposal.timestamp))) > maxProposalAgeSeconds)
        return { TriggerOutcome::StaleProposal, triggerLabel
            + " fired but order_proposal.csv is stale (older than Max Order Proposal Age) -- refusing to act on it. "
              "Check that run_live.py is still running." };
    if (proposal.contracts <= 0 || proposal.contracts > maxContractsSafetyCap)
        return { TriggerOutcome::BadContractCount, triggerLabel
            + " fired but proposed contracts (" + std::to_string(proposal.contracts)
            + ") is 0 or exceeds the Max Contracts Safety Cap -- refusing to act." };
    if (!proposal.hasStop || !proposal.hasTarget1)
        return { TriggerOutcome::MissingRiskLevel, triggerLabel
            + " fired but the proposal is missing a stop or target_1 -- refusing to place an order with no risk level." };
    if (proposal.contractsTarget1 + proposal.contractsTarget2 + proposal.contractsRunner != proposal.contracts)
        return { TriggerOutcome::LegSumMismatch, triggerLabel
            + " fired but the scale-out leg quantities in order_proposal.csv don't sum to the total contracts -- "
              "refusing to act on an inconsistent proposal." };
    if ((proposal.contractsTarget2 > 0 && !proposal.hasTarget2)
        || (proposal.contractsRunner > 0 && !proposal.hasRunner))
        return { TriggerOutcome::LegPriceMissing, triggerLabel
            + " fired but the scale-out split calls for a target_2 or runner leg with no corresponding price in "
              "order_proposal.csv -- refusing to act on an inconsistent proposal." };
    if ((proposal.direction == "long" && proposal.stop >= proposal.target1)
        || (proposal.direction == "short" && proposal.stop <= proposal.target1)
        || (proposal.contractsTarget2 > 0
            && ((proposal.direction == "long" && proposal.stop >= proposal.target2)
             || (proposal.direction == "short" && proposal.stop <= proposal.target2)))
        || (proposal.contractsRunner > 0
            && ((proposal.direction == "long" && proposal.stop >= proposal.runner)
             || (proposal.direction == "short" && proposal.stop <= proposal.runner))))
        return { TriggerOutcome::BackwardsStop, triggerLabel
            + " fired but stop is on the wrong side of target_1 (or an active target_2/runner leg) for this "
              "direction -- refusing to place a backwards bracket order." };

    s_SCPositionData PositionData;
    sc.GetTradePosition(PositionData);
    if (PositionData.PositionQuantity != 0)
        return { TriggerOutcome::PositionAlreadyOpen, triggerLabel
            + " fired but a position is already open (" + std::to_string(PositionData.PositionQuantity)
            + " contracts) -- refusing to open a second one. Flatten first if this is intentional." };
    if (PositionData.WorkingOrdersExist != 0)
        return { TriggerOutcome::WorkingOrderExists, triggerLabel
            + " fired but a working (not yet filled) order already exists for this account/symbol -- refusing to "
              "place a second one. Cancel it first if this is intentional." };
    if (CountTriggersForDate(triggerLogPath, TodayDateString(nowTimeT)) >= maxTradesPerDay)
        return { TriggerOutcome::TradeCapReached, triggerLabel
            + " fired but Max Trades Per Day (" + std::to_string(maxTradesPerDay)
            + ") is already reached for today (see trigger_log.csv) -- refusing to place another. Raise the input "
              "if this is intentional." };

    // Up to three separate bracket orders, one per nonzero scale-out leg --
    // s_SCNewOrder only carries a single Target1Price, so a real multi-target
    // scale-out needs one order submission per target, not one order with
    // several targets. All legs share proposal.stop; there is deliberately
    // no per-leg stop management (breakeven-on-fill, trailing the runner)
    // yet -- that needs fill-event tracking this bridge doesn't have, so
    // it's deferred the same way pyramiding/trailing already are (see
    // ARCHITECTURE.md's Step 4 notes). Each leg's own attached stop/target
    // still exits it independently once submitted, which is what lets
    // Fully Auto both enter AND exit purely from Sierra Chart's own order
    // management -- no extra exit logic needed here.
    struct Leg { const char* name; int quantity; double targetPrice; };
    const Leg legs[] = {
        {"target_1", proposal.contractsTarget1, proposal.target1},
        {"target_2", proposal.contractsTarget2, proposal.target2},
        {"runner",   proposal.contractsRunner,  proposal.runner},
    };

    int totalSubmitted = 0;
    for (const Leg& leg : legs)
    {
        if (leg.quantity <= 0)
            continue;

        s_SCNewOrder NewOrder;
        NewOrder.OrderQuantity = leg.quantity;
        NewOrder.OrderType = SCT_ORDERTYPE_MARKET;
        NewOrder.TimeInForce = SCT_TIF_DAY;
        NewOrder.Target1Price = leg.targetPrice;
        NewOrder.Stop1Price = proposal.stop;
        NewOrder.AttachedOrderTarget1Type = SCT_ORDERTYPE_LIMIT;
        NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;

        const int result = (proposal.direction == "long") ? sc.BuyEntry(NewOrder) : sc.SellEntry(NewOrder);
        std::stringstream msg;
        msg << triggerLabel << " -> " << proposal.direction << " "
            << leg.quantity << " contract(s) [" << leg.name << " leg] (" << proposal.hypothesis_type
            << ", " << proposal.confluence << "), stop=" << proposal.stop << " target=" << leg.targetPrice
            << " -- sc." << (proposal.direction == "long" ? "BuyEntry" : "SellEntry")
            << " returned " << result
            << (result > 0 ? " (submitted)" : " (FAILED -- check Sierra Chart's own Trade Service log for the reason)");
        sc.AddMessageToLog(msg.str().c_str(), result > 0 ? 0 : 1);

        if (result > 0)
            totalSubmitted += leg.quantity;
    }

    // Only log this trigger toward the daily cap once at least one leg
    // actually went out -- a fully-failed submission shouldn't burn a slot
    // the trader (or Fully Auto) could otherwise retry after fixing
    // whatever caused the failure. Counts as one trade regardless of how
    // many legs succeeded -- the cap is about how many times this fired
    // today, not how many individual bracket orders exist on the account.
    if (totalSubmitted > 0)
    {
        const std::string todayStr = TodayDateString(nowTimeT);
        const bool needsHeader = !std::ifstream(triggerLogPath).good();
        std::ofstream logOut(triggerLogPath, std::ios::app);
        if (logOut.is_open())
        {
            if (needsHeader)
                logOut << "date,timestamp,direction,contracts\n";
            logOut << todayStr << "," << FormatISODateTime(nowTimeT) << ","
                   << proposal.direction << "," << totalSubmitted << "\n";
        }
        else
        {
            sc.AddMessageToLog(
                (triggerLabel + ": order placed but could not open " + triggerLogPath + " for writing: "
                 + std::strerror(errno) + " (errno " + std::to_string(errno) + "). Max Trades Per Day will "
                 "under-count today.").c_str(), 1);
        }
    }

    // A proposal that passed every check but whose every leg's
    // sc.BuyEntry/sc.SellEntry call still failed (e.g. Sierra Chart's own
    // Trade Service rejected it) is not a success -- Fully Auto's dedup
    // below should keep retrying/logging it, not go quiet as if it had
    // actually opened a trade. Each individual failure was already logged
    // above per leg; this is just the summary outcome code for that dedup.
    if (totalSubmitted > 0)
        return { TriggerOutcome::Success, "" };
    return { TriggerOutcome::AllLegsFailed, triggerLabel
        + " fired but every scale-out leg's order submission failed -- see the per-leg lines above for the "
          "reason Sierra Chart's own Trade Service gave." };
}

const int LINE_NUMBER_BASE_COMPOSITE = 500000;
const int LINE_NUMBER_HYPOTHESIS_TEXT = 999001;

} // namespace

SCSFExport scsf_TradingHypothesisDisplay(SCStudyInterfaceRef sc)
{
    int InputIdx = -1;

    SCInputRef Input_Instrument = sc.Input[++InputIdx];
    SCInputRef Input_BridgeFolder = sc.Input[++InputIdx];

    SCInputRef Input_Mode = sc.Input[++InputIdx];
    // Step 4, staged rollout: manual one-click trigger first (compiled and
    // run against a live chart on the user's real Sierra Chart), then
    // "Fully Auto" reusing that exact same, tested order-placement code
    // (TryFireOrderFromProposal) on a timer instead of a click -- the user's
    // explicit choice over jumping straight to full automation. There is no
    // native clickable-button Input type in ACSIL, so a self-resetting
    // Yes/No toggle (flip to Yes, ACSIL acts once and flips it back to No)
    // is the standard idiom for Semi Auto's one-shot manual action.
    SCInputRef Input_ManualTriggerOrder = sc.Input[++InputIdx];
    SCInputRef Input_MaxProposalAgeSeconds = sc.Input[++InputIdx];
    SCInputRef Input_MaxContractsSafetyCap = sc.Input[++InputIdx];
    // Risk limits (Step 4 hardening, decided before the first real order
    // ever went out): a manual kill switch and a hard per-day trade count
    // cap. A real dollar-based daily loss limit is deliberately NOT
    // implemented yet -- it would need either a confirmed ACSIL realized-P&L
    // field or a fills bridge neither of which exists today, and guessing
    // either risks another failed build the way sc.GetOrders did. Until
    // that's designed, the trader's own Sierra Chart Trade Activity /
    // Account Balance window is the real daily-loss backstop; flipping
    // Trading Enabled to No here is the one-click way to act on it.
    SCInputRef Input_TradingEnabled = sc.Input[++InputIdx];
    SCInputRef Input_MaxTradesPerDay = sc.Input[++InputIdx];

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

    // Deliberately appended at the very END of the input list, not grouped
    // with the other Intraday VWAP inputs above -- every input's index
    // here is a position in Sierra Chart's per-chart saved settings, so
    // inserting a new one in the *middle* would shift every input after it
    // and silently scramble everyone's already-configured Delta/display/
    // color settings on the next recompile. Appending here means only this
    // one new input needs to be set after rebuilding; everything else
    // keeps its saved value. Same Study ID/Chart Number as the Intraday
    // VWAP inputs above (Input_VWAP_IntradayStudyID/ChartNumber), just a
    // different subgraph -- that study's own +1 standard deviation band,
    // for a live, per-tick stop-loss distance (see Python side:
    // LiveMarketState.vwap_intraday_sd1 / run_live.py's use_vwap_sd1_as_
    // risk_distance). On Sierra Chart's stock "Volume Weighted Average
    // Price" study this is normally one of "Top/Bottom Band N" -- check
    // that study's own "Band N Std Deviation Multiplier/Fixed Offset"
    // input (Band 1 defaults to 0.5, so it's usually Band 2 that's the
    // *actual* +1 SD, not Band 1) before trusting the default below on a
    // chart configured differently.
    SCInputRef Input_VWAP_IntradaySD1Subgraph = sc.Input[++InputIdx];

    // Same mechanism as Input_VWAP_IntradaySD1Subgraph immediately above --
    // and appended right after it for the exact same reason (Sierra
    // Chart's per-chart saved settings are positional; inserting these two
    // anywhere but the very end would shift every input after them). Feeds
    // Python's hypothesis/synthesis.py multi-timeframe weighted model
    // (ARCHITECTURE.md item 8): reading "MM bullish but cooling" (price
    // retreated from outside 2SD to inside 1SD, still above the monthly
    // VWAP line) as a number needs the monthly VWAP study's own +-1SD band,
    // not just the bare above/below Position tiers.py already gives from
    // the plain VWAP centerline. Same Study ID/Chart Number as the
    // existing Monthly/Weekly VWAP inputs above, just a different
    // subgraph -- check that VWAP study's own "Band N Std Deviation
    // Multiplier/Fixed Offset" input before trusting the default below
    // (Band 1 is usually 0.5, not the real +1 SD -- see the comment on
    // Input_VWAP_IntradaySD1Subgraph above for how this was confirmed on
    // the user's own chart).
    SCInputRef Input_VWAP_MonthlySD1Subgraph = sc.Input[++InputIdx];
    SCInputRef Input_VWAP_WeeklySD1Subgraph = sc.Input[++InputIdx];

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

        // Needed to submit an entry order with an attached stop and target
        // in one call (Target1Price/Stop1Price below) rather than three
        // separate order submissions. AllowMultipleEntriesInSameDirection=0
        // is a first line of defense against a double-fire; the explicit
        // sc.GetTradePosition check in the manual-trigger block below is
        // the real, verified one-trade-at-a-time guard this code controls
        // directly -- sc.MaximumPositionAllowed is deliberately left at its
        // default rather than set here, since its exact interaction with
        // attached-order brackets isn't verified against the real SDK.
        sc.SupportAttachedOrdersForTrading = 1;
        sc.AllowMultipleEntriesInSameDirection = 0;

        Input_Instrument.Name = "Instrument (bridge subfolder name, e.g. ES)";
        Input_Instrument.SetString("ES");

        Input_BridgeFolder.Name = "Bridge Folder (shared with Python engine)";
        Input_BridgeFolder.SetString("C:\\SierraChart\\TradingHypothesisBridge");

        // "Semi Auto" wires up the manual one-click trigger below.
        // "Fully Auto" fires the exact same checks/order-placement
        // automatically on a timer (Input_RefreshIntervalSeconds cadence) --
        // no manual click needed, but every safety check (Trading Enabled,
        // Max Trades Per Day, position/working-order guard, etc.) still
        // applies identically. See "Fully Auto mode" in sierra_chart/
        // README.md before switching to it, even on a Replay/SIM session.
        Input_Mode.Name = "Mode (Hypothesis Only / Semi Auto = manual trigger / Fully Auto = automatic)";
        Input_Mode.SetCustomInputStrings("Hypothesis Only;Semi Auto;Fully Auto");
        Input_Mode.SetCustomInputIndex(0);

        Input_ManualTriggerOrder.Name = "Trigger Order Now (flip to Yes to act on the current order_proposal.csv -- auto-resets to No)";
        Input_ManualTriggerOrder.SetYesNo(0);

        Input_MaxProposalAgeSeconds.Name = "Max Order Proposal Age (seconds) -- refuse to trigger on a stale file";
        Input_MaxProposalAgeSeconds.SetInt(30);
        Input_MaxProposalAgeSeconds.SetIntLimits(1, 3600);

        Input_MaxContractsSafetyCap.Name = "Max Contracts Safety Cap (independent of Python sizing -- refuses to trigger above this)";
        Input_MaxContractsSafetyCap.SetInt(5);
        Input_MaxContractsSafetyCap.SetIntLimits(1, 100);

        Input_TradingEnabled.Name = "Trading Enabled (kill switch -- flip to No to block every trigger immediately)";
        Input_TradingEnabled.SetYesNo(1);

        Input_MaxTradesPerDay.Name = "Max Trades Per Day (hard cap, counted from this study's own trigger_log.csv)";
        Input_MaxTradesPerDay.SetInt(3);
        Input_MaxTradesPerDay.SetIntLimits(1, 50);

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

        Input_VWAP_IntradaySD1Subgraph.Name = "VWAP Intraday +1 SD Band Subgraph Index "
            "(check the VWAP study's own Band N multiplier -- the band whose multiplier is 1.0 is the real +1 SD)";
        Input_VWAP_IntradaySD1Subgraph.SetInt(3);  // user's own chart: DAY-VWAP ID:5, Top Band 2 (SG4) = index 3

        Input_VWAP_MonthlySD1Subgraph.Name = "VWAP Monthly +1 SD Band Subgraph Index "
            "(check that VWAP study's own Band N multiplier -- the band whose multiplier is 1.0 is the real +1 SD)";
        Input_VWAP_MonthlySD1Subgraph.SetInt(3);  // same convention as the intraday input above -- verify against your own chart

        Input_VWAP_WeeklySD1Subgraph.Name = "VWAP Weekly +1 SD Band Subgraph Index "
            "(check that VWAP study's own Band N multiplier -- the band whose multiplier is 1.0 is the real +1 SD)";
        Input_VWAP_WeeklySD1Subgraph.SetInt(3);  // same convention as the intraday input above -- verify against your own chart

        return;
    }

    const std::string instrument = Input_Instrument.GetString();
    const std::string bridgeDir = std::string(Input_BridgeFolder.GetString()) + "\\" + instrument;
    const std::string dailyProfilePath = bridgeDir + "\\daily_profile_export.csv";
    const std::string compositesPath = bridgeDir + "\\composites.csv";
    const std::string hypothesisPath = bridgeDir + "\\hypothesis.txt";
    const std::string liveStatePath = bridgeDir + "\\live_state.csv";
    const std::string orderProposalPath = bridgeDir + "\\order_proposal.csv";
    const std::string triggerLogPath = bridgeDir + "\\trigger_log.csv";

    SCFloatArray VAHArray, VALArray, POCArray;
    GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), Input_VP_VAHSubgraph.GetInt(), VAHArray);
    GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), Input_VP_VALSubgraph.GetInt(), VALArray);
    GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), Input_VP_POCSubgraph.GetInt(), POCArray);

    SCFloatArray VWAPMonthlyArray, VWAPWeeklyArray, VWAPIntradayArray, VWAPIntradaySD1Array, DeltaArray;
    SCFloatArray VWAPMonthlySD1Array, VWAPWeeklySD1Array;
    GetStudyArrayAnyChart(sc, Input_VWAP_MonthlyChartNumber.GetInt(), Input_VWAP_MonthlyStudyID.GetInt(), Input_VWAP_MonthlySubgraph.GetInt(), VWAPMonthlyArray);
    GetStudyArrayAnyChart(sc, Input_VWAP_WeeklyChartNumber.GetInt(), Input_VWAP_WeeklyStudyID.GetInt(), Input_VWAP_WeeklySubgraph.GetInt(), VWAPWeeklyArray);
    GetStudyArrayAnyChart(sc, Input_VWAP_IntradayChartNumber.GetInt(), Input_VWAP_IntradayStudyID.GetInt(), Input_VWAP_IntradaySubgraph.GetInt(), VWAPIntradayArray);
    GetStudyArrayAnyChart(sc, Input_VWAP_IntradayChartNumber.GetInt(), Input_VWAP_IntradayStudyID.GetInt(), Input_VWAP_IntradaySD1Subgraph.GetInt(), VWAPIntradaySD1Array);
    GetStudyArrayAnyChart(sc, Input_VWAP_MonthlyChartNumber.GetInt(), Input_VWAP_MonthlyStudyID.GetInt(), Input_VWAP_MonthlySD1Subgraph.GetInt(), VWAPMonthlySD1Array);
    GetStudyArrayAnyChart(sc, Input_VWAP_WeeklyChartNumber.GetInt(), Input_VWAP_WeeklyStudyID.GetInt(), Input_VWAP_WeeklySD1Subgraph.GetInt(), VWAPWeeklySD1Array);
    GetStudyArrayAnyChart(sc, Input_Delta_ChartNumber.GetInt(), Input_Delta_StudyID.GetInt(), Input_Delta_Subgraph.GetInt(), DeltaArray);

    // 0.0 ("not available", same convention live_state.csv's other optional
    // fields use) unless the SD1 array actually resolved to real data --
    // an unconfigured/wrong subgraph index would otherwise make
    // LastArrayValue's 0.0-for-empty-array fallback silently subtract
    // against a real VWAP value and produce a bogus non-zero "distance".
    const float vwapIntradaySD1Distance = VWAPIntradaySD1Array.GetArraySize() > 0
        ? static_cast<float>(std::fabs(LastArrayValue(VWAPIntradaySD1Array) - LastArrayValue(VWAPIntradayArray)))
        : 0.0f;
    const float vwapMonthlySD1Distance = VWAPMonthlySD1Array.GetArraySize() > 0
        ? static_cast<float>(std::fabs(LastArrayValue(VWAPMonthlySD1Array) - LastArrayValue(VWAPMonthlyArray)))
        : 0.0f;
    const float vwapWeeklySD1Distance = VWAPWeeklySD1Array.GetArraySize() > 0
        ? static_cast<float>(std::fabs(LastArrayValue(VWAPWeeklySD1Array) - LastArrayValue(VWAPWeeklyArray)))
        : 0.0f;

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
            << " orderProposalPath=" << orderProposalPath
            << " Mode=" << Input_Mode.GetIndex()
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
            << " VWAPIntradaySD1Subgraph=" << Input_VWAP_IntradaySD1Subgraph.GetInt()
            << " VWAPIntradaySD1ArraySize=" << VWAPIntradaySD1Array.GetArraySize()
            << " VWAPMonthlySD1Subgraph=" << Input_VWAP_MonthlySD1Subgraph.GetInt()
            << " VWAPMonthlySD1ArraySize=" << VWAPMonthlySD1Array.GetArraySize()
            << " VWAPWeeklySD1Subgraph=" << Input_VWAP_WeeklySD1Subgraph.GetInt()
            << " VWAPWeeklySD1ArraySize=" << VWAPWeeklySD1Array.GetArraySize()
            << " DeltaStudyID=" << Input_Delta_StudyID.GetInt()
            << " DeltaChart=" << Input_Delta_ChartNumber.GetInt()
            << " DeltaArraySize=" << DeltaArray.GetArraySize()
            << " TradingEnabled=" << Input_TradingEnabled.GetYesNo()
            << " MaxTradesPerDay=" << Input_MaxTradesPerDay.GetInt();
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
    // first export attempt.
    //
    // Attempted every single recalculation, NOT gated by an all-time
    // "already created" flag -- a real test found that gate was wrong:
    // EnsureDirectoryExists's own _mkdir+EEXIST check already makes this
    // idempotent and cheap on an existing directory, but the old code only
    // ever called it once per chart instance, ever. That meant changing the
    // `Bridge Folder` input after this instance had already succeeded once
    // for its OLD value (e.g. pointing a backtest chart at an isolated
    // bridge dir after it had been running against the shared live one)
    // never created the new path at all -- confirmed directly: the parent
    // folder existed (created by hand while diagnosing) but its `<Instrument>`
    // subfolder never appeared, and nothing was ever written there, with no
    // error logged either, since the gate skipped the whole block silently.
    // `BridgeDirErrorLogged` now only dedupes the LOG line (so a persistent
    // real failure, e.g. bad permissions, still reports once and goes quiet
    // rather than spamming every recalculation) -- it no longer gates
    // whether creation is attempted.
    int& BridgeDirErrorLogged = sc.GetPersistentInt(3);
    {
        std::string dirErr = EnsureDirectoryExists(Input_BridgeFolder.GetString());
        if (dirErr.empty())
            dirErr = EnsureDirectoryExists(bridgeDir);
        if (dirErr.empty())
        {
            BridgeDirErrorLogged = 0; // clears so a later, different failure gets its own fresh log line
        }
        else if (!BridgeDirErrorLogged)
        {
            sc.AddMessageToLog(("Trading Hypothesis Display: " + dirErr).c_str(), 1);
            BridgeDirErrorLogged = 1;
        }
    }

    // --- 1. Export the just-closed trading day's volume profile ---------
    // Persistent storage across recalculations: index 1 = last exported
    // trading day, as whatever opaque comparison value sc.GetTradingDayDate()
    // returns (see the comment on FormatISODateFromSCDateTime -- it is NOT
    // reliably YYYYMMDD, just a value that changes exactly when the trading
    // day changes), reused via sc.GetPersistentInt (a standard ACSIL idiom
    // for state that must survive across calls).
    int& LastExportedDateYYYYMMDD = sc.GetPersistentInt(1);

    // Gated on Input_VP_StudyID itself (> 0), not on VAHArray.GetArraySize():
    // see the vwapDeltaConfigured comment below for why array size alone
    // doesn't reliably indicate a real, resolved study.
    if (sc.ArraySize > 1 && Input_VP_StudyID.GetInt() > 0)
    {
        const int lastBar = sc.ArraySize - 1;
        // sc.GetTradingDayDate()'s return value is used purely as an opaque
        // token here to detect a day change (==/!=) -- never decoded as
        // YYYYMMDD. Two different assumptions about its numeric encoding
        // (SCDateTime-wrapped-then-.GetDate(), and "it's already a plain
        // YYYYMMDD int") both produced the same style of garbage against a
        // real daily_profile_export.csv ("0004-62-73", then "0004-62-75"),
        // consistent with it actually being a raw day-count serial. The
        // actual printed date is now built separately, straight from the
        // bar's own SCDateTime (see FormatISODateFromSCDateTime), so this
        // value's real encoding no longer matters -- only that it changes
        // exactly when the trading day does.
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
                // A real chart confirmed this actually happens: Sierra Chart
                // periodically tags this chart for a full recalculation on
                // its own (cross-chart dependencies from other studies/
                // charts in the same chartbook), and a full recalculation
                // resets persistent storage -- including
                // LastExportedDateYYYYMMDD back to 0 -- even though nothing
                // about the trading day actually changed. Without this
                // check, every such recalculation looks exactly like a
                // fresh, never-exported day rollover and appends another
                // duplicate row for the same date (confirmed: the file
                // gained a second real row for a date already present,
                // immediately after a logged "Performing a full
                // recalculation" message). The persistent int alone can't
                // survive that reset, so check the file's own last row
                // instead -- the one piece of state that's actually durable
                // across a recalculation.
                const std::string lastClosedDateStr = FormatISODateFromSCDateTime(sc.BaseDateTimeIn[lastClosedBar]);
                if (ReadLastDailyProfileDate(dailyProfilePath) == lastClosedDateStr)
                {
                    LastExportedDateYYYYMMDD = lastClosedYYYYMMDD; // resync so we don't re-check the file every tick
                }
                else
                {
                std::stringstream diag;
                diag << "Trading Hypothesis Display: daily export firing. lastClosedBar=" << lastClosedBar
                     << " date=" << FormatISODateFromSCDateTime(sc.BaseDateTimeIn[lastClosedBar])
                     << " VAHArraySize=" << VAHArray.GetArraySize()
                     << " VAH[last]=" << LastArrayValue(VAHArray)
                     << " VAL[last]=" << LastArrayValue(VALArray)
                     << " POC[last]=" << LastArrayValue(POCArray)
                     // The values actually written below -- logged separately
                     // from VAH/VAL/POC[last] above so a stale build (still
                     // running the old one-bar-back fallback instead of this
                     // backward scan) is immediately visible in the log
                     // instead of only showing up as a wrong CSV row.
                     << " VAH[scanned]=" << LastClosedProfileValue(VAHArray)
                     << " VAL[scanned]=" << LastClosedProfileValue(VALArray)
                     << " POC[scanned]=" << LastClosedProfileValue(POCArray);
                sc.AddMessageToLog(diag.str().c_str(), 0);

                // Confirmed by a real raw dump: subgraph index 1 (the one
                // configured as "Vol Value Area High") is 0.0 at EVERY
                // sampled index, including index 0 -- the oldest bar in the
                // whole 1800-bar history. That rules out a scan bug; this
                // subgraph is simply never populated with this study's
                // current settings (Draw Developing Value Area Lines=No
                // likely disables the developing subgraphs 0-2 entirely and
                // moves the actual non-developing/final values other
                // studies draw from to different subgraph indices). Rather
                // than guess which index, probe every subgraph 0-9 on the
                // same study/chart and print the last value AND a backward-
                // scanned non-zero value for each, so the correct index can
                // be read directly out of the log.
                {
                    std::stringstream dump;
                    dump << "Trading Hypothesis Display: Volume Value Area Lines subgraph probe (StudyID="
                         << Input_VP_StudyID.GetInt() << " Chart=" << Input_VP_ChartNumber.GetInt() << "):";
                    for (int sg = 0; sg <= 9; ++sg)
                    {
                        SCFloatArray probeArray;
                        GetStudyArrayAnyChart(sc, Input_VP_ChartNumber.GetInt(), Input_VP_StudyID.GetInt(), sg, probeArray);
                        const int size = probeArray.GetArraySize();
                        dump << " SG[" << sg << "](size=" << size << ")";
                        if (size > 0)
                            dump << ":last=" << probeArray[size - 1] << ",scanned=" << LastClosedProfileValue(probeArray);
                    }
                    sc.AddMessageToLog(dump.str().c_str(), 0);
                }

                // A real Replay-mode test on a brand-new bridge folder (never
                // touched by hand) surfaced this file NEVER writing a header
                // row -- unlike trigger_log.csv, which already gets this
                // right below. That went unnoticed on the live deployment
                // because its file had a header line from early manual
                // debugging, but a genuinely fresh file has none, and
                // Python's csv.DictReader then silently treats the FIRST
                // DATA ROW as the column names -- every later row then fails
                // to parse with a bare `KeyError: 'instrument'`, caught by
                // run_live.py's per-tick exception handler and printed as
                // `tick failed: 'instrument'` with no further detail. Fixed
                // the same way trigger_log.csv already handles it: write the
                // header once, before the first data row ever goes in.
                const bool dailyProfileNeedsHeader = !std::ifstream(dailyProfilePath).good();
                std::ofstream out(dailyProfilePath, std::ios::app);
                if (out.is_open())
                {
                    if (dailyProfileNeedsHeader)
                        out << "date,instrument,val,vah,poc\n";
                    out << FormatISODateFromSCDateTime(sc.BaseDateTimeIn[lastClosedBar]) << "," << instrument << ","
                        << LastClosedProfileValue(VALArray) << "," << LastClosedProfileValue(VAHArray) << ","
                        << LastClosedProfileValue(POCArray) << "\n";
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
                } // end of "else" -- the file didn't already have this date
            }
        }
    }

    // Confirmed by the subgraph probe: subgraphs 0-2 on the Volume Value
    // Area Lines study exist (size=1800, matching this chart's bar count)
    // but scan as 0.0 across the ENTIRE array, and subgraphs 3-9 don't
    // exist at all (size=0) -- so there's no separate "non-developing"
    // subgraph hiding the real data either. Working theory: with "Draw
    // Developing Value Area Lines=No", this study may never write these
    // subgraphs at all (drawing the visible lines through some other,
    // non-subgraph mechanism), rather than writing them only for closed
    // days. Log the LIVE last-bar value every time it actually changes
    // (not gated on a day rollover) so toggling "Draw Developing Value
    // Area Lines" to Yes on that study (chart 2) and watching this log can
    // confirm or rule that out without waiting for the next real day
    // change.
    {
        // Comparing only against the persistent double's own previous value
        // was a bug: that persistent double *starts* at 0.0 by default, the
        // same as the value being watched, so "did it change" was always
        // false on the very first real value too -- no log line could ever
        // appear even if this ran every single tick, silently making the
        // whole diagnostic useless. HasLoggedLiveVAH forces at least one
        // unconditional log line so there's positive proof this code path
        // actually runs and what it currently sees, not just silence that's
        // ambiguous between "never ran" and "value never changed".
        int& HasLoggedLiveVAH = sc.GetPersistentInt(5);
        double& LastLoggedLiveVAH = sc.GetPersistentDouble(3);
        const float currentVAH = LastArrayValue(VAHArray);
        if (!HasLoggedLiveVAH || currentVAH != static_cast<float>(LastLoggedLiveVAH))
        {
            std::stringstream live;
            live << "Trading Hypothesis Display: live VAH subgraph value is " << currentVAH
                 << " (VAHArraySize=" << VAHArray.GetArraySize() << ")";
            sc.AddMessageToLog(live.str().c_str(), 0);
            LastLoggedLiveVAH = currentVAH;
            HasLoggedLiveVAH = 1;
        }
    }

    // "now"/"nowTimeT" are needed by both section 1b (proposal-freshness
    // check) and section 2b (live_state.csv's timestamp column) below --
    // computed once here, ahead of both, rather than duplicated.
    const time_t nowTimeT = time(nullptr);
    const double now = static_cast<double>(nowTimeT);

    // --- 1b. Order trigger (Step 4: Semi Auto manual click, or Fully Auto's
    // automatic timer) -- both share TryFireOrderFromProposal (defined near
    // the top of this file) so Fully Auto reuses exactly the same,
    // already-verified checks and order-placement code rather than a
    // second, divergent copy. Placed before the refresh-interval throttle
    // below (section 2) so a manual trigger flip is honored immediately on
    // the next recalculation rather than waiting up to
    // Input_RefreshIntervalSeconds; Fully Auto applies its own, separate
    // throttle (see below) so it doesn't spam the Message Log or the CSV
    // reads every recalculation.
    //
    // VERIFICATION STATUS: TryFireOrderFromProposal's use of s_SCNewOrder's
    // field names (Target1Price/Stop1Price/AttachedOrderTarget1Type/
    // AttachedOrderStop1Type), sc.BuyEntry/sc.SellEntry's return-value
    // convention (>0 = submitted), and Input_Mode.GetIndex() are my
    // best-effort reading of ACSIL documentation and example code, NOT yet
    // compiled against the real Sierra Chart SDK header -- check that
    // function first if this fails to compile, and confirm the exact
    // field/return-value semantics against sierrachart.h before ever
    // flipping the trigger (or switching to Fully Auto) on a real SIM
    // account. s_SCPositionData's PositionQuantity and WorkingOrdersExist
    // fields, by contrast, ARE confirmed against Sierra Chart's own
    // ACSILTrading.html documentation (pasted in by the user after an
    // earlier sc.GetOrders() guess failed a real build -- see
    // ARCHITECTURE.md's Step 4 notes).
    const int modeIndex = Input_Mode.GetIndex(); // 0=Hypothesis Only, 1=Semi Auto, 2=Fully Auto
    if (modeIndex == 1 && Input_ManualTriggerOrder.GetYesNo())
    {
        // Reset the trigger immediately, before doing anything else -- so
        // this is always a one-shot action per click, never a standing
        // condition that could re-fire on a later recalculation if
        // something below returns early in some future edit.
        Input_ManualTriggerOrder.SetYesNo(0);

        TriggerAttempt attempt = TryFireOrderFromProposal(
            sc, orderProposalPath, triggerLogPath, instrument,
            Input_TradingEnabled.GetYesNo() != 0,
            Input_MaxProposalAgeSeconds.GetInt(),
            Input_MaxContractsSafetyCap.GetInt(),
            Input_MaxTradesPerDay.GetInt(),
            nowTimeT, now,
            std::string("Trading Hypothesis Display: manual trigger"));
        // Always logged, exactly like before this was extracted into a
        // shared function -- a manual click is a one-shot, deliberate
        // action, so the trader should see the outcome (or refusal reason)
        // every single time, not have it deduplicated away.
        if (attempt.outcome != TriggerOutcome::Success)
            sc.AddMessageToLog(attempt.refusalMessage.c_str(), 1);
    }
    else if (modeIndex == 2)
    {
        // Fully Auto: the same tested order-placement path as Semi Auto's
        // manual trigger, fired automatically on a timer instead of waiting
        // for a click -- the second, later stage of the staged rollout the
        // user chose, reached now that manual triggering has compiled and
        // run successfully on real hardware (see ARCHITECTURE.md's Step 4
        // notes). Throttled to Input_RefreshIntervalSeconds -- the same
        // cadence order_proposal.csv actually changes on (run_live.py's own
        // poll interval) -- rather than every recalculation, which can fire
        // many times a second via sc.UpdateAlways. Entries AND exits both
        // come from this: entry via sc.BuyEntry/sc.SellEntry below, exit via
        // each leg's own attached stop/target order that Sierra Chart's own
        // Trade Service manages once submitted (including during a Replay
        // session) -- no separate exit logic is needed here.
        double& LastAutoFireAttempt = sc.GetPersistentDouble(4);
        if (now - LastAutoFireAttempt >= Input_RefreshIntervalSeconds.GetInt())
        {
            LastAutoFireAttempt = now;
            TriggerAttempt attempt = TryFireOrderFromProposal(
                sc, orderProposalPath, triggerLogPath, instrument,
                Input_TradingEnabled.GetYesNo() != 0,
                Input_MaxProposalAgeSeconds.GetInt(),
                Input_MaxContractsSafetyCap.GetInt(),
                Input_MaxTradesPerDay.GetInt(),
                nowTimeT, now,
                std::string("Trading Hypothesis Display: Fully Auto"));

            // Dedup against the previous attempt's outcome so a routine,
            // long-lived state (no signal right now, already in a trade,
            // today's cap already reached) logs once on the transition into
            // it instead of spamming the Message Log every
            // Input_RefreshIntervalSeconds for as long as it holds. A real
            // order placement (Success) is never deduplicated -- each one
            // is always logged (via the per-leg lines inside
            // TryFireOrderFromProposal itself), and is also what resets this
            // so the *next* new refusal reason (e.g. the position this just
            // opened) gets its own fresh log line.
            int& LastAutoOutcome = sc.GetPersistentInt(7);
            const int outcomeCode = static_cast<int>(attempt.outcome);
            if (attempt.outcome != TriggerOutcome::Success && outcomeCode != LastAutoOutcome)
                sc.AddMessageToLog(attempt.refusalMessage.c_str(), 1);
            LastAutoOutcome = outcomeCode;
        }
    }

    // --- 2. Throttle bridge-file reads/writes to Input_RefreshIntervalSeconds --
    double& LastRefreshUnixTime = sc.GetPersistentDouble(1);
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
        // sc.GetTradingDayDate()'s return value is only ever used as an
        // opaque day-change token here (==/!=), never formatted -- see the
        // comment on the daily profile export block above for why decoding
        // its actual numeric encoding turned out to be unreliable.
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
            liveOut << "timestamp,instrument,last_price,session_open,vwap_monthly,vwap_weekly,vwap_intraday,cum_delta,vwap_intraday_sd1,vwap_monthly_sd1,vwap_weekly_sd1\n";
            liveOut << FormatISODateTime(nowTimeT) << "," << instrument << ","
                    << sc.Close[lastBar] << "," << SessionOpenPrice << ","
                    << LastArrayValue(VWAPMonthlyArray) << ","
                    << LastArrayValue(VWAPWeeklyArray) << "," << LastArrayValue(VWAPIntradayArray) << ","
                    << LastArrayValue(DeltaArray) << "," << vwapIntradaySD1Distance << ","
                    << vwapMonthlySD1Distance << "," << vwapWeeklySD1Distance << "\n";
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
