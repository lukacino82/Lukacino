// ============================================================================================
//  Lukacino_MultiSwing.cpp  -  ACSIL multi-swing correction system for ES / MES
//
//  Research source : swing_lab/ (Python).  Rules are NOT written in this file: they are read
//                    from swing_presets.csv, exported by swing_lab/export_presets.py, so the
//                    backtest and the live study trade the identical rule set.
//
//  CHART REQUIREMENT
//    Apply this study to an INTRADAY chart of ES/MES (1-minute recommended, 5-minute maximum)
//    with the full Globex session loaded.  The study builds its own daily RTH bars.
//    Reason: weekly and monthly VWAP need volume-weighted sigma, which cannot be reconstructed
//    from daily bars at all, and the research engine resolves stops inside the day.
//
//  STEP 1 of the plan in swing_lab/SIERRA_ARCHITECTURE.md
//    Implemented here : preset loading and parsing, daily RTH aggregation, feature engine,
//                       anchored VWAPs with sigma, signal engine, internal paper ledger,
//                       chart drawing, journal CSV.
//    NOT yet here     : live order placement (step 3).  Input "Send Orders To Trade Service"
//                       exists and is validated, but the order layer is a separate step so
//                       that replay parity can be proven first.
//
//  PARITY CONTRACT with swing_lab/engine.py
//    1. a signal is evaluated only on a COMPLETED daily RTH bar
//    2. if stop and target are both touched inside one bar, the STOP counts first
//    3. ATR20 uses the true range of the whole ETH day against the previous RTH close
//    4. MA / RSI / IBS / drawdown use completed RTH daily closes
//    5. the journal CSV has the same columns as lab.trades_df
// ============================================================================================

#include "sierrachart.h"

// scstructures.h defines min() and max() as macros, which makes std::max / std::min fail to
// compile. Undefine them right after the Sierra headers; the standard functions are used below.
#ifdef max
#undef max
#endif
#ifdef min
#undef min
#endif

#include <vector>
#include <string>
#include <fstream>
#include <cmath>
#include <algorithm>

SCDLLName("Lukacino Multi-Swing")

// ------------------------------------------------------------------ input indices (NEVER renumber)
// Bumped by hand whenever the source changes. Sierra compiles on a remote build server and a
// failed or empty compiler response leaves the OLD DLL loaded, which looks identical in the log -
// so the study says which source it is, and a version that did not change means the build did not
// take, however cleanly the build window reported it.
static const char* STUDY_VERSION = "2026-10-01.23";

static const int NUM_FAMILIES = 12;

enum InputIdx {
    IN_TRADING_ENABLED = 0, IN_MODE, IN_SEND_LIVE, IN_DIRECTION, IN_PRESET_FILE, IN_RELOAD,
    IN_RISK_UNIT, IN_INSTRUMENT, IN_EVAL_AT, IN_JOURNAL_FILE,                       // 0-9 global
    IN_FAM1_ON = 10, IN_FAM1_W, IN_FAM2_ON, IN_FAM2_W, IN_FAM3_ON, IN_FAM3_W,
    IN_FAM4_ON, IN_FAM4_W, IN_FAM5_ON, IN_FAM5_W, IN_FAM6_ON, IN_FAM6_W,
    IN_FAM7_ON, IN_FAM7_W, IN_FAM8_ON, IN_FAM8_W, IN_FAM9_ON, IN_FAM9_W,
    IN_FAM10_ON, IN_FAM10_W, IN_FAM11_ON, IN_FAM11_W, IN_FAM12_ON, IN_FAM12_W,     // 10-33 families
    IN_MAX_GROSS = 34, IN_MAX_CONCURRENT, IN_MAX_PER_FAMILY, IN_MAX_PER_ROLE,
    IN_DAILY_LOSS, IN_MAX_DD_STOP, IN_SCALE_IN, IN_SCALE_CAP,                       // 34-41 risk
    IN_ENTRY_TYPE = 42, IN_LIMIT_OFFSET, IN_ENTRY_EXPIRY, IN_MAX_SLIPPAGE,
    IN_FLATTEN_EOD, IN_TIME_STOP,                                                   // 42-47 execution
    IN_RTH_START = 48, IN_RTH_END, IN_LOG_LEVEL, IN_DRAW_SIGNALS,                   // 48-51 session / diag
    IN_EXIT_OVERRIDE = 52, IN_OV_SL_ATR, IN_OV_RRR, IN_OV_SL_TICKS, IN_OV_TP_TICKS,
    IN_OV_BE_R, IN_OV_TRAIL_ATR,                                                    // 52-58 exit override
    IN_SHOW_STATUS = 59, IN_STATUS_CORNER, IN_STATUS_SIZE,
    IN_LABEL_SIGNALS, IN_LABEL_DAYS,                                                // 59-63 on-chart display
    IN_FEATURE_CSV = 64,                                                            // 64 diagnostics
    // Per-family exit override, one pair per family, in the family order of IN_FAM1_ON.
    // Zero means "leave this family's presets on their own validated exit", which is the default,
    // so the book keeps trading exactly what was measured until a number is deliberately typed in.
    // Appended at the end and never renumbered: an existing chart keeps every setting it had.
    IN_FAMX_SL = 65, IN_FAMX_RRR = 66,                                              // 65-88, stride 2
    IN_LIVE_CONFIRM = 89,                                                           // 89 live seatbelt
    IN_COUNT
};

enum ModeKind    { MODE_SIGNALS = 0, MODE_SEMI, MODE_FULL };
enum DirKind     { DIR_LONG_ONLY = 0, DIR_BOTH, DIR_SHORT_ONLY };
enum EvalKind    { EVAL_CLOSE = 0, EVAL_NEXT_OPEN };
enum LogLevel    { LOG_ERRORS = 0, LOG_INFO, LOG_DEBUG };
enum ExitOverride { XO_PRESET = 0, XO_ATR_BRACKET, XO_FIXED_TICKS };
enum EntryOverride { EO_PRESET = 0, EO_FORCE_CLOSE, EO_FORCE_LIMIT };
enum CornerKind  { CORNER_TL = 0, CORNER_TR, CORNER_BL, CORNER_BR };

// Line numbers for the drawings this study manages. Kept well clear of anything drawn by hand so
// redrawing the box never touches a user's own drawing.
enum { DRAW_STATUS_LINE = 7710001, DRAW_LABEL_BASE = 7720001 };

static const int MAX_FAMILIES = 12;
static const int DAILY_HISTORY = 400;          // > 252-day peak window + 200-day MA warm-up

// ------------------------------------------------------------------ preset model
enum SetupKind {
    SK_UNKNOWN = 0,
    SK_LIMIT_RSI_PULLBACK,   // LMT_RSI{len}<{th}_-{k}ATR   limit entry k*ATR below the close
    SK_BELOW_VWAP_SD,        // C<{anchor}vwap-{k}sd
    SK_VWAP_BAND,            // D01_{anchor}vwap-{k}sd[_reclaim]
    SK_RECLAIM_SMA_AFTER_DD, // C06_Reclaim{n}_afterDD
    SK_HIDD_RSI,             // P_Hi{N}DD>{k}&RSI2<{th}
    SK_HIDD_IBS,             // P_Hi{N}DD>{k}&IBS<{th}
    SK_IBS,                  // IBS<{th}
    SK_WILLIAMS_R,           // WR{len}<{th}
    SK_CLOSE_AT_ND_LOW,      // CloseAt{N}dLow
    SK_RSI,                  // RSI{len}<{th}
    SK_CONNORS_RSI           // ConnorsRSI<{th}
};
enum AnchorKind  { ANCH_DAY = 0, ANCH_WEEK, ANCH_MONTH, ANCH_QUARTER };
enum RegimeKind  { RG_ANY = 0, RG_C_GT_SMA, RG_SMA50_GT_SMA200, RG_C_GT_QVWAP,
                   RG_C_GT_PREV_MVWAP, RG_C_GT_SMA200_SHALLOW_DD };
enum ExitSigKind { XS_NONE = 0, XS_C_GT_SMA, XS_C_GT_PREV_HIGH, XS_RSI2_GT, XS_IBS_GT,
                   XS_C_GT_WVWAP, XS_FIRST_UP_CLOSE };
enum EntryKind   { EK_CLOSE = 0, EK_LIMIT, EK_STOP_ABOVE_HIGH };   // EK_CLOSE = fill at the RTH close of the signal day (MOC), as in engine.py emode 0

struct Preset {
    SCString id, family, role, setupStr, regimeStr, exitStr;
    int      familyIdx = -1;

    SetupKind  kind = SK_UNKNOWN;
    AnchorKind anchor = ANCH_DAY;
    double p1 = 0, p2 = 0, p3 = 0;      // meaning depends on kind, see the enum comments
    bool   reclaim = false;

    RegimeKind regime = RG_ANY;
    int        regimeMa = 0;

    EntryKind  entry = EK_CLOSE;
    double     entryOffsetAtr = 0;      // for EK_LIMIT: fill k*ATR below the signal close

    ExitSigKind xsig = XS_NONE;
    int         xsigMa = 0;
    double      xsigParam = 0;
    bool        xsigAtOpen = false;
    double slAtr = 0, tpAtr = 0, beR = 0, trailAtr = 0, trailActR = 0;
    int    timeStop = 0;

    bool   valid = false;
    SCString parseError;
};

// live state of one preset (paper in step 1, real position in step 3)
struct PresetState {
    int    inPos = 0;                   // 0 flat, 1 long
    double entry = 0, stop = 0, target = 0, best = 0, worst = 0;
    double initialStop = 0;
    bool   trailOn = false;
    double trailDist = 1e18, beR = 0;   // resolved at entry, frozen for the life of the trade
    // Where the protective stop belongs in the market from tomorrow on: st.stop moved up by the
    // trail and by breakeven, using the excursion INCLUDING today. It is only read by the order
    // layer - the ledger still decides exits from the pre-bar excursion, so parity is untouched.
    double accountStop = -1e18;
    int    timeStop = 0;
    bool   exitNextOpen = false;        // set by an "@open" signal exit, executed on the next session
    // day references are ABSOLUTE session numbers, never vector indices: the daily history is
    // trimmed to DAILY_HISTORY and every stored vector index would silently shift on each trim
    long   entryDay = -1;
    int    entryDayIdx = -1;            // vector index of the entry day, only for chart drawing
    int    heldDays = 0;
    int    pendingSide = 0;             // order armed at the signal close, to be filled next session
    double pendingLevel = 0;
    long   pendingDay = -1;
    EntryKind pendingKind = EK_CLOSE;
    long   signalDay = -1;
};

// The account side of a preset, deliberately NOT part of PresetState: the exit path resets that
// wholesale on every close, which would drop what is still working in the market and leave it
// there with nothing tracking it.
//
// What this leg records is only that an entry was sent and has not been superseded, so the same
// trade is not bought twice. It deliberately does NOT claim the contracts are still held: Sierra
// works the bracket, and when the stop or the target trades, the account drops without telling the
// study. Only sc.GetTradePosition knows, and the reconciliation at the end of SyncOrders uses it.
struct AccountLeg {
    int  qtyOnAccount = 0;      // what this preset actually put on the account
    long entryDay = -1;         // a re-entry the same session is a new trade, not the old one
    // The entry order Sierra hung this preset's bracket on, and the stop price last working on it.
    // Sierra owns the bracket; these are only what the study needs to move that stop when the
    // trail or breakeven says so, and to not re-send a move that is already in the market.
    unsigned int parentOrderId = 0;
    double stopOnAccount = 0;
    // Retiring a closed preset can fail, and the old code wiped the leg anyway. Those contracts
    // then belonged to nobody: the book no longer counted them, no bracket could be steered
    // because the handle was gone, and the market sell for them was refused because they were
    // still covered. Permanently stuck, on every run. Counted now, so a retry is possible and a
    // dead end is reportable instead of silent.
    int  retireTries = 0;
    // The price this preset's own target was last steered to, when its exit is going out through
    // that target. Non-zero means "an exit is working on the market for these contracts": they are
    // covered, so they must never be offered to a market sell, and if the market walks away from
    // that limit it is moved down again rather than abandoned. Zero means no exit is working.
    double exitPrice = 0.0;
    bool   exitIsStop = false;  // a steered stop needs the market at or below it, a limit at or above
    int    exitCalls = 0;       // calls it has been working; a child that never fills is cancelled
};

// Enough consecutive rejections to conclude the account is not doing what the study asks.
enum { ORDER_FAILURE_LIMIT = 5 };

// Sierra's own code for "this order was skipped because the chart was doing a full
// recalculation" (scconstants.h). Named here so a rejection can say what it means instead of
// printing a bare number, and because it is the one code that is the study's fault, not the
// account's - see the guard at the top of SyncOrders.
static const int SCT_SKIPPED_FULL_RECALC_CODE = -8998;

// Sierra's "skipped" return codes live in a band, not alone: -8998 is the full-recalculation one
// and a replay produced -8995 on the very next run. They are not rejections. Sierra declined to
// act and NOTHING was sent, so blaming the trade account - which the stopped notice did - sends
// you to flatten a position that was never opened. Only the exact meaning differs between them,
// and that is in scconstants.h on the machine running Sierra, not guessable from here.
static bool IsSkipCode(int rc) { return rc <= -8990 && rc >= -8999; }

// Put a price on the instrument's tick grid, rounding away from the market.
//
// The research engine works in continuous prices, so a stop of 1.5 x ATR20 lands wherever the
// arithmetic puts it - 7631.68 on an instrument whose tick is 0.25. An exchange has no such price
// and Sierra refuses the order. Rounding away from the market (a long's stop down, its target up)
// keeps the account's exit no EARLIER than the ledger's: at worst the book closes the trade first
// and the position reconciliation sells at market, which is the path the order layer already
// handles. Rounding the other way would let the account stop out on a tick the research never saw.
static double ToTick(double price, double tick, bool roundDown)
{
    if (tick <= 0 || price <= 0 || price > 1e17) return price;
    const double n = price / tick;
    return (roundDown ? floor(n) : ceil(n)) * tick;
}

// What a Sierra return code means, where the study can say something useful about it.
// Said on both rejection paths, so the two cannot drift apart. "Toggle Reload Presets" was not
// enough of an instruction: the Input already reads Yes on most charts, and setting Yes to Yes is
// not a change, so nothing reloads and the cut-off stays latched. It has to say which way to move
// it.
static const char* STOPPED_NOTICE =
    "Multi-Swing: ORDER PLACEMENT STOPPED after too many rejections. The account is not holding "
    "what the book thinks and nothing more will be sent. Flatten the position by hand, fix the "
    "trade account or Trade Simulation Mode, then change the Input 'Reload Presets' to the OTHER "
    "value (Yes to No, or No to Yes) - it reloads on the change, so setting it to what it already "
    "says does nothing.";

// The same latch, for the case where every refusal was one of Sierra's skip codes. Telling someone
// to flatten a position that was never opened is worse than saying nothing, so this path says what
// actually happened instead.
static const char* STOPPED_NOTICE_SKIPPED =
    "Multi-Swing: ORDER PLACEMENT STOPPED - but every refusal was one of Sierra's SKIPPED codes, "
    "so NOTHING was sent and the account was never touched. There is no position to flatten and "
    "the book is intact. Find out which skip it is (the hint on the lines above says how), fix "
    "that, then change the Input 'Reload Presets' to the OTHER value to lift the latch.";

static const char* OrderRejectHint(int rc)
{
    if (rc == SCT_SKIPPED_FULL_RECALC_CODE)
        return "  Sierra skipped it because the chart was recalculating - this is a study bug, "
               "not an account problem; report it.";
    // Any other code in the skip band. Nothing was sent, so there is no position to reconcile -
    // but which skip it is decides what to do about it, and only Sierra's own header says that.
    if (IsSkipCode(rc))
        return "  This is one of Sierra's SKIPPED codes, not a rejection: nothing was sent and "
               "the account was not touched, so there is no position to flatten. Which skip it is "
               "names the cause, and the name is on this machine. Run this in a command prompt and "
               "send the line it prints: findstr /n \"-8995\" "
               "C:\\SierraChart\\ACS_Source\\scconstants.h    (also try sierrachart.h in the "
               "same folder, and substitute the code above if it differs).";
    // -1 says only "no". The reason lives in Sierra's own log lines, but the study can at least
    // list the switches that have to be on, because every one of them refuses with this same -1
    // and the dialog for this study cannot see or set any of them. Setting 'Send Orders To Trade
    // Service' to Yes is necessary and not sufficient: Sierra gates study orders a second time at
    // the Trade menu, globally and per chart, and a chart with no trade account selected has
    // nowhere to send them.
    if (rc == -1)
        return "  -1 is Sierra's generic refusal and carries no reason of its own. Check, in this"
               " order: (1) Trade > Auto Trading Enabled - Global is ticked; (2) Trade > Auto"
               " Trading Enabled for Chart is ticked for THIS chart; (3) a trade account is"
               " selected for this chart - Trade Window, or Chart Settings > Trading; (4) Trade >"
               " Trade Simulation Mode On, unless you really mean to trade the live account. Then"
               " toggle 'Reload Presets' to lift the cut-off. Sierra logs the real reason"
               " separately: Window > Message Log at lines WITHOUT the 'Study: Lukacino"
               " Multi-Swing' prefix at this same timestamp, and Trade > Trade Activity Log.";
    return "";
}

// one completed daily RTH bar plus the ETH extremes that belong to the same trading day
struct DailyBar {
    SCDateTime date;                    // RTH session date
    double o = 0, h = 0, l = 0, c = 0, v = 0;
    double ethHigh = 0, ethLow = 0;     // overnight + RTH, for true range
    double dvwap = 0, dvwapSd = 0;      // session VWAP and volume-weighted sigma
    double wvwap = 0, wvwapSd = 0;
    double mvwap = 0, mvwapSd = 0;
    double qvwap = 0;
    double prevMvwap = 0;               // final VWAP of the previous completed month
};

// ------------------------------------------------------------------ persistent study state
struct StudyState {
    std::vector<Preset>      presets;
    std::vector<PresetState> states;
    SCString familyNames[MAX_FAMILIES];
    int      familyCount = 0;

    std::vector<DailyBar> daily;        // completed RTH days, oldest first, capped at DAILY_HISTORY
    // in-progress session accumulators
    bool     sessionOpen = false;
    int      curLastRthTod = -1;        // time of day of the last RTH bar seen in the open session
    SCDateTime sessionDate;
    DailyBar cur;
    double   curTpv = 0, curTp2v = 0, curVol = 0;                 // day VWAP accumulators
    double   wTpv = 0, wTp2v = 0, wVol = 0; int  wKey = -1;       // week
    double   mTpv = 0, mTp2v = 0, mVol = 0; int  mKey = -1;       // month
    double   qTpv = 0, qVol = 0;            int  qKey = -1;       // quarter
    double   lastCompletedMvwap = 0;

    long     dayCounter = -1;           // absolute number of completed trading days
    int      incompleteDays = 0;        // sessions finalised without reaching their RTH end
    long     recalcSkips = 0;           // consecutive orders Sierra skipped for a full recalculation
    bool     grossCapWarned = false;    // the "cap is below one preset" notice is said once

    // Realised P&L in points, from the study's own ledger - not from the account, which the
    // study cannot read here. It is the same number the journal records, so the limits below
    // bite on exactly what the book did, in Replay and on a Sim account alike.
    double   realizedToday = 0, realizedTotal = 0, equityPeak = 0;
    long     realizedDay = -1;
    bool     haltedDaily = false, haltedDd = false;
    bool     loaded = false;
    bool     loadAttempted = false;   // a failed load is reported once, not on every study call
    SCString loadError;
    int      lastProcessedIndex = -1;
    int      journalRows = 0;
    int      semiPosition = 0;          // the position semi-auto pretends to hold
    int      labelsDrawn = 0;           // so the labels can be removed when switched off
    SCString featureCsv;                // empty unless the per-day dump is switched on
    std::vector<AccountLeg> legs;       // parallel to states, but outliving each trade's reset
    int      orderFailures = 0;         // consecutive rejections; trading stops at the limit
    int      lastRejectCode = 0;        // ... and what the last one was, so the latch can tell a
                                        // skip (nothing sent) from a real rejection
    int      trimSentQty = 0;           // an exit already on its way, so it is not sent twice
    int      trimWaited = 0;            // calls it has been waited for, so a sell that never
                                        // lands cannot lock the trim out for ever
    int      bracketsSeen = 0;          // a live stop or target child was found for a leg
    int      bracketsEmpty = 0;         // ... none was: Sierra's bracket had already taken it
    int      modifyOk = 0, modifyFail = 0;   // ModifyOrder verdicts on those children
    int      ordersPlaced = 0;          // accepted orders since the last reload; 0 means this
                                        // study has not touched the account in this run
    bool     orphanHalt = false;        // the account holds contracts this run did not place
    bool     orphanWarned = false;      // said once, not once per call
    bool     chartSimWarned = false;    // ... and for the chart-simulation-has-no-exits note
    bool     capLogged = false;        // ... and for the one-time note naming Sierra's position cap
    bool     confirmWarned = false;    // ... and for the live-trading seatbelt notice
};

// ------------------------------------------------------------------ small parsing helpers
static SCString Trim(const SCString& s)
{
    int a = 0, b = s.GetLength();
    while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r' || s[a] == '\n')) ++a;
    while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r' || s[b - 1] == '\n')) --b;
    SCString out;
    for (int i = a; i < b; ++i) out += s[i];
    return out;
}

static std::vector<SCString> Split(const SCString& s, char sep)
{
    std::vector<SCString> out;
    SCString cur;
    for (int i = 0; i < s.GetLength(); ++i) {
        if (s[i] == sep) { out.push_back(cur); cur = ""; }
        else cur += s[i];
    }
    out.push_back(cur);
    return out;
}

static bool StartsWith(const SCString& s, const char* p)
{
    int n = (int)strlen(p);
    if (s.GetLength() < n) return false;
    for (int i = 0; i < n; ++i) if (s[i] != p[i]) return false;
    return true;
}

static bool Contains(const SCString& s, const char* p) { return s.IndexOf(p[0]) >= 0 && strstr(s.GetChars(), p) != nullptr; }

// read the first number (with optional sign and decimals) starting at or after `from`;
// returns false when there is no digit left
static bool NumberAfter(const SCString& s, int from, double& value, int* endPos = nullptr)
{
    int i = from, n = s.GetLength();
    while (i < n && !(isdigit((unsigned char)s[i]) || ((s[i] == '-' || s[i] == '+') && i + 1 < n && isdigit((unsigned char)s[i + 1])))) ++i;
    if (i >= n) return false;
    int start = i;
    if (s[i] == '-' || s[i] == '+') ++i;
    while (i < n && (isdigit((unsigned char)s[i]) || s[i] == '.')) ++i;
    std::string num;
    for (int k = start; k < i; ++k) num += s[k];
    value = atof(num.c_str());
    if (endPos) *endPos = i;
    return true;
}

// ------------------------------------------------------------------ setup / regime / exit parsing
static bool ParseSetup(Preset& p)
{
    const SCString& s = p.setupStr;
    double a = 0, b = 0, c = 0;
    int pos = 0;

    if (StartsWith(s, "LMT_RSI")) {                 // LMT_RSI2<10_-0.75ATR
        if (!NumberAfter(s, 7, a, &pos)) return false;            // rsi length
        if (!NumberAfter(s, pos, b, &pos)) return false;          // threshold
        if (!NumberAfter(s, pos, c, &pos)) return false;          // ATR offset (written as -0.75)
        p.kind = SK_LIMIT_RSI_PULLBACK; p.p1 = a; p.p2 = b; p.p3 = fabs(c);
        p.entry = EK_LIMIT; p.entryOffsetAtr = fabs(c);
        return true;
    }
    if (StartsWith(s, "C<dvwap") || StartsWith(s, "C<wvwap") || StartsWith(s, "C<mvwap") || StartsWith(s, "C<qvwap")) {
        p.anchor = (s[2] == 'd') ? ANCH_DAY : (s[2] == 'w') ? ANCH_WEEK
                 : (s[2] == 'm') ? ANCH_MONTH : ANCH_QUARTER;
        if (!NumberAfter(s, 7, a, &pos)) return false;            // the k in "-k sd"
        p.kind = SK_BELOW_VWAP_SD; p.p1 = fabs(a);
        return true;
    }
    if (StartsWith(s, "D01_")) {                    // D01_wvwap-2.0sd[_reclaim]
        p.anchor = (s[4] == 'w') ? ANCH_WEEK : (s[4] == 'm') ? ANCH_MONTH : ANCH_DAY;
        if (!NumberAfter(s, 8, a, &pos)) return false;
        p.kind = SK_VWAP_BAND; p.p1 = fabs(a);
        p.reclaim = Contains(s, "reclaim");
        return true;
    }
    if (StartsWith(s, "C06_Reclaim")) {             // C06_Reclaim3_afterDD
        if (!NumberAfter(s, 11, a, &pos)) return false;
        p.kind = SK_RECLAIM_SMA_AFTER_DD; p.p1 = a; p.p2 = 0.03;
        return true;
    }
    if (StartsWith(s, "P_Hi")) {                    // P_Hi20DD>1.0&RSI2<25   /   &IBS<0.25
        if (!NumberAfter(s, 4, a, &pos)) return false;            // 20 or 50
        if (!NumberAfter(s, pos, b, &pos)) return false;          // drawdown in ATR
        bool isIbs = Contains(s, "IBS");
        int lt = -1;                                  // threshold follows the last '<' in the name
        for (int k = pos; k < s.GetLength(); ++k) if (s[k] == '<') lt = k;
        if (lt < 0 || !NumberAfter(s, lt + 1, c, &pos)) return false;
        p.kind = isIbs ? SK_HIDD_IBS : SK_HIDD_RSI; p.p1 = a; p.p2 = b; p.p3 = c;
        return true;
    }
    if (StartsWith(s, "IBS<"))        { if (!NumberAfter(s, 4, a)) return false; p.kind = SK_IBS; p.p1 = a; return true; }
    if (StartsWith(s, "WR"))          { if (!NumberAfter(s, 2, a, &pos)) return false;
                                        if (!NumberAfter(s, pos, b)) return false;
                                        p.kind = SK_WILLIAMS_R; p.p1 = a; p.p2 = b; return true; }
    if (StartsWith(s, "CloseAt"))     { if (!NumberAfter(s, 7, a)) return false; p.kind = SK_CLOSE_AT_ND_LOW; p.p1 = a; return true; }
    if (StartsWith(s, "ConnorsRSI<")) { if (!NumberAfter(s, 11, a)) return false; p.kind = SK_CONNORS_RSI; p.p1 = a; return true; }
    if (StartsWith(s, "RSI"))         { if (!NumberAfter(s, 3, a, &pos)) return false;
                                        if (!NumberAfter(s, pos, b)) return false;
                                        p.kind = SK_RSI; p.p1 = a; p.p2 = b; return true; }
    return false;
}

static bool ParseRegime(Preset& p)
{
    const SCString& r = p.regimeStr;
    double v = 0;
    if (r == "any")                  { p.regime = RG_ANY; return true; }
    if (r == "sma50>sma200")         { p.regime = RG_SMA50_GT_SMA200; return true; }
    if (r == "c>qvwap")              { p.regime = RG_C_GT_QVWAP; return true; }
    if (r == "c>prev_mvwap")         { p.regime = RG_C_GT_PREV_MVWAP; return true; }
    if (StartsWith(r, "c>sma200&dd")) { p.regime = RG_C_GT_SMA200_SHALLOW_DD; p.regimeMa = 200; return true; }
    if (StartsWith(r, "c>sma"))      { if (!NumberAfter(r, 5, v)) return false;
                                       p.regime = RG_C_GT_SMA; p.regimeMa = (int)v; return true; }
    return false;
}

// grammar mirrors swing_lab/systems.py exits(); tokens are separated by '+', sub-parts by '_'
static bool ParseExit(Preset& p)
{
    SCString e = p.exitStr;
    if (StartsWith(e, "x:")) { SCString t; for (int i = 2; i < e.GetLength(); ++i) t += e[i]; e = t; }
    std::vector<SCString> tokens = Split(e, '+');
    for (size_t ti = 0; ti < tokens.size(); ++ti) {
        SCString t = Trim(tokens[ti]);
        if (t.GetLength() == 0) continue;
        double v = 0, v2 = 0, v3 = 0;
        int pos = 0;

        if (StartsWith(t, "Trail")) {                       // Trail1.0ATR_act1.0R[_T20]
            if (!NumberAfter(t, 5, v, &pos)) return false;
            p.trailAtr = v;
            if (NumberAfter(t, pos, v2, &pos)) p.trailActR = v2;
            if (Contains(t, "_T") && NumberAfter(t, pos, v3)) p.timeStop = (int)v3;
            if (p.slAtr <= 0) p.slAtr = (v > 1.0 ? v : 1.0);    // initial protective stop
            continue;
        }
        if (StartsWith(t, "SL") && Contains(t, "RRR")) {     // SL1.5ATR_RRR2.0[_BE1.0R]
            if (!NumberAfter(t, 2, v, &pos)) return false;
            if (!NumberAfter(t, pos, v2, &pos)) return false;
            p.slAtr = v; p.tpAtr = v * v2;
            if (Contains(t, "_BE") && NumberAfter(t, pos, v3)) p.beR = v3;
            if (p.timeStop == 0) p.timeStop = 20;    // implicit in systems.py exits(): bracket -> max_days=20
            continue;
        }
        if (StartsWith(t, "SL")) {                           // catastrophic stop only: SL3.0ATR
            if (!NumberAfter(t, 2, v)) return false;
            p.slAtr = v; continue;
        }
        if (StartsWith(t, "Time")) { if (!NumberAfter(t, 4, v)) return false; p.timeStop = (int)v; continue; }
        if (StartsWith(t, "T") && t.GetLength() <= 4 && isdigit((unsigned char)t[1])) {
            if (!NumberAfter(t, 1, v)) return false; p.timeStop = (int)v; continue;
        }
        // --- signal exits
        if (Contains(t, "@open")) p.xsigAtOpen = true;
        if (StartsWith(t, "C>SMA"))      { if (!NumberAfter(t, 5, v)) return false; p.xsig = XS_C_GT_SMA; p.xsigMa = (int)v; continue; }
        if (StartsWith(t, "C>PrevHigh")) { p.xsig = XS_C_GT_PREV_HIGH; continue; }
        if (StartsWith(t, "C>wvwap"))    { p.xsig = XS_C_GT_WVWAP; continue; }
        if (StartsWith(t, "RSI2>"))      { if (!NumberAfter(t, 5, v)) return false; p.xsig = XS_RSI2_GT; p.xsigParam = v; continue; }
        if (StartsWith(t, "IBS>"))       { if (!NumberAfter(t, 4, v)) return false; p.xsig = XS_IBS_GT; p.xsigParam = v; continue; }
        if (StartsWith(t, "FirstUpClose")) { p.xsig = XS_FIRST_UP_CLOSE; continue; }
        return false;
    }
    return p.xsig != XS_NONE || p.slAtr > 0 || p.timeStop > 0;
}

// Build the full path of a data file. An absolute path in the Input (drive letter, leading slash
// or backslash) is used as given, otherwise the name is taken relative to the Data Files Folder.
static SCString DataPath(SCStudyInterfaceRef sc, const SCString& file)
{
    if (file.GetLength() > 1 && (file[1] == ':' || file[0] == '\\' || file[0] == '/')) return file;
    SCString folder = sc.DataFilesFolder();
    if (folder.GetLength() == 0) return file;
    // sc.DataFilesFolder() already ends with a separator on most builds; do not add a second one.
    const char last = folder[folder.GetLength() - 1];
    if (last == '\\' || last == '/') return folder + file;
    SCString sep; sep += (folder.IndexOf('/') >= 0 && folder.IndexOf('\\') < 0) ? '/' : '\\';
    return folder + sep + file;
}

// ------------------------------------------------------------------ preset file loading
static bool LoadPresets(SCStudyInterfaceRef sc, StudyState& S, const SCString& path, SCString& err)
{
    S.presets.clear(); S.states.clear(); S.familyCount = 0;
    std::ifstream f(path.GetChars());
    if (!f.is_open()) { err.Format("Preset file not found: %s", path.GetChars()); return false; }

    std::string line;
    if (!std::getline(f, line)) { err = "Preset file is empty"; return false; }
    std::vector<SCString> head = Split(SCString(line.c_str()), ',');
    int cId = -1, cFam = -1, cRole = -1, cSetup = -1, cRegime = -1, cExit = -1;
    for (size_t i = 0; i < head.size(); ++i) {
        SCString h = Trim(head[i]);
        if (h == "id") cId = (int)i;           else if (h == "family") cFam = (int)i;
        else if (h == "role") cRole = (int)i;  else if (h == "setup") cSetup = (int)i;
        else if (h == "regime") cRegime = (int)i; else if (h == "exit") cExit = (int)i;
    }
    if (cId < 0 || cFam < 0 || cSetup < 0 || cRegime < 0 || cExit < 0) {
        err = "Preset file header must contain id, family, role, setup, regime, exit"; return false;
    }

    int badRows = 0;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        std::vector<SCString> col = Split(SCString(line.c_str()), ',');
        if ((int)col.size() <= cExit) { ++badRows; continue; }
        Preset p;
        p.id = Trim(col[cId]); p.family = Trim(col[cFam]);
        p.role = (cRole >= 0 && (int)col.size() > cRole) ? Trim(col[cRole]) : SCString("");
        p.setupStr = Trim(col[cSetup]); p.regimeStr = Trim(col[cRegime]); p.exitStr = Trim(col[cExit]);

        p.valid = ParseSetup(p) && ParseRegime(p) && ParseExit(p);
        if (!p.valid) {
            p.parseError.Format("cannot parse setup='%s' regime='%s' exit='%s'",
                                p.setupStr.GetChars(), p.regimeStr.GetChars(), p.exitStr.GetChars());
            ++badRows;
        }
        // map family name -> family input index (order of first appearance, max 12)
        int fi = -1;
        for (int k = 0; k < S.familyCount; ++k) if (S.familyNames[k] == p.family) { fi = k; break; }
        if (fi < 0 && S.familyCount < MAX_FAMILIES) { fi = S.familyCount; S.familyNames[S.familyCount++] = p.family; }
        p.familyIdx = fi;

        S.presets.push_back(p);
        S.states.push_back(PresetState());
    }
    if (S.presets.empty()) { err = "No presets loaded"; return false; }
    if (badRows > 0) err.Format("%d preset row(s) failed to parse - those presets are disabled", badRows);
    return true;
}

// ------------------------------------------------------------------ daily indicator helpers
static double SMA(const std::vector<DailyBar>& d, int endIdx, int n)
{
    if (endIdx + 1 < n) return 0;
    double s = 0; for (int i = endIdx - n + 1; i <= endIdx; ++i) s += d[i].c;
    return s / n;
}
static double HighestHigh(const std::vector<DailyBar>& d, int endIdx, int n)
{
    if (endIdx + 1 < n) return 0;
    double m = -1e18; for (int i = endIdx - n + 1; i <= endIdx; ++i) m = std::max(m, d[i].h);
    return m;
}
static double LowestLow(const std::vector<DailyBar>& d, int endIdx, int n)
{
    if (endIdx + 1 < n) return 0;
    double m = 1e18; for (int i = endIdx - n + 1; i <= endIdx; ++i) m = std::min(m, d[i].l);
    return m;
}
static double LowestClose(const std::vector<DailyBar>& d, int endIdx, int n)
{
    if (endIdx + 1 < n) return 0;
    double m = 1e18; for (int i = endIdx - n + 1; i <= endIdx; ++i) m = std::min(m, d[i].c);
    return m;
}
// Wilder RSI over closes, same recursion as pandas ewm(alpha=1/n, adjust=False) in features.py
static double RSI(const std::vector<DailyBar>& d, int endIdx, int n)
{
    if (endIdx < n) return 50.0;
    double up = 0, dn = 0;
    for (int i = 1; i <= endIdx; ++i) {
        double ch = d[i].c - d[i - 1].c;
        double g = ch > 0 ? ch : 0, l = ch < 0 ? -ch : 0;
        if (i == 1) { up = g; dn = l; }
        else { up += (g - up) / n; dn += (l - dn) / n; }
    }
    if (dn <= 1e-12) return 100.0;
    return 100.0 - 100.0 / (1.0 + up / dn);
}
static double ATR(const std::vector<DailyBar>& d, int endIdx, int n)
{
    if (endIdx + 1 < n + 1) return 0;
    double s = 0;
    for (int i = endIdx - n + 1; i <= endIdx; ++i) {
        double pc = d[i - 1].c;
        double tr = std::max(d[i].ethHigh - d[i].ethLow,
                    std::max(fabs(d[i].ethHigh - pc), fabs(d[i].ethLow - pc)));
        s += tr;
    }
    return s / n;
}
static double IBS(const DailyBar& b)
{
    double r = b.h - b.l;
    return r > 1e-9 ? (b.c - b.l) / r : 0.5;
}
static double WilliamsR(const std::vector<DailyBar>& d, int endIdx, int n)
{
    double hh = HighestHigh(d, endIdx, n), ll = LowestLow(d, endIdx, n);
    if (hh - ll < 1e-9) return -50.0;
    return -100.0 * (hh - d[endIdx].c) / (hh - ll);
}
// ConnorsRSI = (RSI(3) + RSI(2) of the up/down streak + percent rank of the 1-day ROC) / 3
static double ConnorsRSI(const std::vector<DailyBar>& d, int endIdx)
{
    if (endIdx < 101) return 50.0;
    double r3 = RSI(d, endIdx, 3);
    // streak series
    std::vector<double> streak(endIdx + 1, 0.0);
    for (int i = 1; i <= endIdx; ++i) {
        if (d[i].c > d[i - 1].c)      streak[i] = streak[i - 1] > 0 ? streak[i - 1] + 1 : 1;
        else if (d[i].c < d[i - 1].c) streak[i] = streak[i - 1] < 0 ? streak[i - 1] - 1 : -1;
        else                          streak[i] = 0;
    }
    double up = 0, dn = 0;
    for (int i = 1; i <= endIdx; ++i) {
        double ch = streak[i] - streak[i - 1];
        double g = ch > 0 ? ch : 0, l = ch < 0 ? -ch : 0;
        if (i == 1) { up = g; dn = l; } else { up += (g - up) / 2.0; dn += (l - dn) / 2.0; }
    }
    double rStreak = (dn <= 1e-12) ? 100.0 : 100.0 - 100.0 / (1.0 + up / dn);
    double roc = d[endIdx - 1].c > 0 ? (d[endIdx].c / d[endIdx - 1].c - 1.0) : 0.0;
    int below = 0, total = 0;
    for (int i = endIdx - 99; i <= endIdx; ++i) {
        if (i < 1) continue;
        double r = d[i - 1].c > 0 ? (d[i].c / d[i - 1].c - 1.0) : 0.0;
        if (r <= roc) ++below;
        ++total;
    }
    double pr = total > 0 ? 100.0 * below / total : 50.0;
    return (r3 + rStreak + pr) / 3.0;
}
// running 252-session peak of the HIGH and the drawdown of the close from it (correction.py)
static void PeakState(const std::vector<DailyBar>& d, int endIdx, int win, double& peak, double& dd, int& daysFromPeak)
{
    int j0 = std::max(0, endIdx - win + 1);
    peak = -1e18; int pkIdx = j0;
    for (int i = j0; i <= endIdx; ++i) if (d[i].h >= peak) { peak = d[i].h; pkIdx = i; }
    dd = peak > 0 ? d[endIdx].c / peak - 1.0 : 0.0;
    daysFromPeak = endIdx - pkIdx;
}

// ------------------------------------------------------------------ feature snapshot for one completed day
struct Features {
    double c = 0, h = 0, l = 0, o = 0;
    double atr20 = 0, sma3 = 0, sma5 = 0, sma10 = 0, sma20 = 0, sma50 = 0, sma100 = 0, sma200 = 0;
    double rsi2 = 50, rsi3 = 50, rsi5 = 50, connors = 50, ibs = 0.5, wr10 = -50;
    double dd = 0, peak = 0; int daysFromPeak = 0;
    double hi20DdAtr = 0, hi50DdAtr = 0;
    double dvwap = 0, dvwapSd = 0, wvwap = 0, wvwapSd = 0, mvwap = 0, mvwapSd = 0, qvwap = 0, prevMvwap = 0;
    double prevHigh = 0, prevClose = 0;
    bool   ready = false;
};

static Features ComputeFeatures(const std::vector<DailyBar>& d, int i)
{
    Features f;
    if (i < 210) return f;                      // SMA200 + RSI warm-up
    const DailyBar& b = d[i];
    f.c = b.c; f.h = b.h; f.l = b.l; f.o = b.o;
    f.prevHigh = d[i - 1].h; f.prevClose = d[i - 1].c;
    f.atr20 = ATR(d, i, 20);
    f.sma3 = SMA(d, i, 3);   f.sma5 = SMA(d, i, 5);   f.sma10 = SMA(d, i, 10);
    f.sma20 = SMA(d, i, 20); f.sma50 = SMA(d, i, 50); f.sma100 = SMA(d, i, 100); f.sma200 = SMA(d, i, 200);
    f.rsi2 = RSI(d, i, 2); f.rsi3 = RSI(d, i, 3); f.rsi5 = RSI(d, i, 5);
    f.connors = ConnorsRSI(d, i);
    f.ibs = IBS(b); f.wr10 = WilliamsR(d, i, 10);
    PeakState(d, i, 252, f.peak, f.dd, f.daysFromPeak);
    if (f.atr20 > 1e-9) {
        f.hi20DdAtr = (HighestHigh(d, i, 20) - b.c) / f.atr20;
        f.hi50DdAtr = (HighestHigh(d, i, 50) - b.c) / f.atr20;
    }
    f.dvwap = b.dvwap; f.dvwapSd = b.dvwapSd;
    f.wvwap = b.wvwap; f.wvwapSd = b.wvwapSd;
    f.mvwap = b.mvwap; f.mvwapSd = b.mvwapSd;
    f.qvwap = b.qvwap; f.prevMvwap = b.prevMvwap;
    f.ready = f.atr20 > 1e-9 && f.sma200 > 0;
    return f;
}

static double AnchorVwap(const Features& f, AnchorKind a, double& sd)
{
    switch (a) {
        case ANCH_WEEK:    sd = f.wvwapSd; return f.wvwap;
        case ANCH_MONTH:   sd = f.mvwapSd; return f.mvwap;
        case ANCH_QUARTER: sd = 0;         return f.qvwap;
        default:           sd = f.dvwapSd; return f.dvwap;
    }
}

static bool RegimeOk(const Preset& p, const Features& f)
{
    switch (p.regime) {
        case RG_ANY:                return true;
        case RG_C_GT_SMA:           return p.regimeMa == 50 ? f.c > f.sma50
                                         : p.regimeMa == 100 ? f.c > f.sma100 : f.c > f.sma200;
        case RG_SMA50_GT_SMA200:    return f.sma50 > f.sma200;
        case RG_C_GT_QVWAP:         return f.qvwap > 0 && f.c > f.qvwap;
        case RG_C_GT_PREV_MVWAP:    return f.prevMvwap > 0 && f.c > f.prevMvwap;
        case RG_C_GT_SMA200_SHALLOW_DD: return f.c > f.sma200 && f.dd > -0.10;
    }
    return false;
}

// true when the preset's weakness condition is met on the completed day i
static bool SetupSignal(const Preset& p, const std::vector<DailyBar>& d, int i,
                        const Features& f, const Features& pf)
{
    double sd = 0, vw = 0;
    switch (p.kind) {
        case SK_LIMIT_RSI_PULLBACK: {
            double r = (int)p.p1 == 2 ? f.rsi2 : (int)p.p1 == 3 ? f.rsi3 : f.rsi5;
            return r < p.p2;
        }
        case SK_BELOW_VWAP_SD:
            vw = AnchorVwap(f, p.anchor, sd);
            return vw > 0 && f.c < vw - p.p1 * sd;
        case SK_VWAP_BAND: {
            vw = AnchorVwap(f, p.anchor, sd);
            if (vw <= 0) return false;
            double band = vw - p.p1 * sd;
            if (!p.reclaim) return f.c < band;
            if (!pf.ready) return false;
            double psd = 0, pvw = AnchorVwap(pf, p.anchor, psd);
            return pvw > 0 && pf.c < pvw - p.p1 * psd && f.c > band;   // undercut then reclaim
        }
        case SK_RECLAIM_SMA_AFTER_DD: {
            int n = (int)p.p1;
            double ma = n == 3 ? f.sma3 : n == 5 ? f.sma5 : f.sma10;
            if (ma <= 0 || i < 1) return false;
            double prevMa = n == 3 ? SMA(d, i - 1, 3) : n == 5 ? SMA(d, i - 1, 5) : SMA(d, i - 1, 10);
            return f.c > ma && d[i - 1].c < prevMa && f.dd < -p.p2;
        }
        case SK_HIDD_RSI: {
            double ddAtr = (int)p.p1 == 20 ? f.hi20DdAtr : f.hi50DdAtr;
            return ddAtr > p.p2 && f.rsi2 < p.p3;
        }
        case SK_HIDD_IBS: {
            double ddAtr = (int)p.p1 == 20 ? f.hi20DdAtr : f.hi50DdAtr;
            return ddAtr > p.p2 && f.ibs < p.p3;
        }
        case SK_IBS:              return f.ibs < p.p1;
        case SK_WILLIAMS_R:       return f.wr10 < p.p2;
        case SK_CLOSE_AT_ND_LOW:  return f.c <= LowestClose(d, i, (int)p.p1) + 1e-9;
        case SK_RSI: {
            double r = (int)p.p1 == 2 ? f.rsi2 : (int)p.p1 == 3 ? f.rsi3 : f.rsi5;
            return r < p.p2;
        }
        case SK_CONNORS_RSI:      return f.connors < p.p1;
        default: return false;
    }
}

static bool ExitSignal(const Preset& p, const Features& f)
{
    switch (p.xsig) {
        case XS_C_GT_SMA:
            return p.xsigMa == 3 ? f.c > f.sma3 : p.xsigMa == 5 ? f.c > f.sma5 : f.c > f.sma10;
        case XS_C_GT_PREV_HIGH:  return f.c > f.prevHigh;
        case XS_RSI2_GT:         return f.rsi2 > p.xsigParam;
        case XS_IBS_GT:          return f.ibs > p.xsigParam;
        case XS_C_GT_WVWAP:      return f.wvwap > 0 && f.c > f.wvwap;
        case XS_FIRST_UP_CLOSE:  return f.c > f.prevClose;
        default: return false;
    }
}

// ------------------------------------------------------------------ journal

// Always YYYY-MM-DD. sc.FormatDateTime() follows Sierra's global date/time display setting and
// appends a time, so the ledger it produced was unparseable against the research one on any
// machine not set to ISO - and the off-line harness could never see it, since its stub formats
// dates itself. The ledger has to be comparable regardless of how the user's Sierra displays
// dates, so the format is pinned here.
static SCString DayString(const SCDateTime& t)
{
    SCString r;
    r.Format("%04d-%02d-%02d", t.GetYear(), t.GetMonth(), t.GetDay());
    return r;
}

static const char* JOURNAL_HEADER =
    "preset_id,family,signal_day,entry_day,exit_day,side,entry,exit,pnl_pts,mae,mfe,bars,reason";

// A full recalculation re-simulates every loaded bar, so the ledger is rewritten from scratch
// instead of appended to - otherwise every chart reload would duplicate the whole trade history.
static void ResetJournal(const SCString& path)
{
    std::ofstream f(path.GetChars(), std::ios::trunc);
    if (f.is_open()) f << JOURNAL_HEADER << "\n";
}

// Per-day dump of everything the entry rules read. The journal says which days the study traded;
// when those days differ from the research and the rules are identical, the answer is in the
// numbers the rules were given - above all the day's volume, since the VWAP bands are built from
// it and the price-only families agree while the VWAP ones do not.
static const char* FEATURE_HEADER =
    "day,open,high,low,close,volume,atr20,dvwap,dvwap_sd,wvwap,wvwap_sd,mvwap,mvwap_sd,qvwap,"
    "rsi2,ibs,connors,wr10,dd_pct,sma5,sma10,sma50,sma200";

static void ResetFeatureCsv(const SCString& path)
{
    if (path.GetLength() == 0) return;
    std::ofstream f(path.GetChars(), std::ios::trunc);
    if (f.is_open()) f << FEATURE_HEADER << "\n";
}

static void AppendFeatureCsv(const SCString& path, const SCDateTime& day,
                             const DailyBar& b, const Features& ft)
{
    if (path.GetLength() == 0 || !ft.ready) return;
    std::ofstream f(path.GetChars(), std::ios::app);
    if (!f.is_open()) return;
    SCString row;
    row.Format("%s,%.2f,%.2f,%.2f,%.2f,%.0f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,"
               "%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f",
               DayString(day).GetChars(), b.o, b.h, b.l, b.c, b.v, ft.atr20,
               ft.dvwap, ft.dvwapSd, ft.wvwap, ft.wvwapSd, ft.mvwap, ft.mvwapSd, ft.qvwap,
               ft.rsi2, ft.ibs, ft.connors, ft.wr10, ft.dd * 100.0,
               ft.sma5, ft.sma10, ft.sma50, ft.sma200);
    f << row.GetChars() << "\n";
}

static void AppendJournal(const SCString& path, const SCString& row, StudyState& S)
{
    std::ofstream f(path.GetChars(), std::ios::app);
    if (!f.is_open()) return;
    if (S.journalRows == 0) {
        std::ifstream probe(path.GetChars(), std::ios::ate);
        if (!probe.is_open() || probe.tellg() == 0) f << JOURNAL_HEADER << "\n";
    }
    f << row.GetChars() << "\n";
    ++S.journalRows;
}

static const char* ReasonName(int r)
{
    switch (r) { case 1: return "sl"; case 2: return "tp"; case 3: return "trail";
                 case 4: return "time"; case 5: return "signal"; case 6: return "breakeven"; }
    return "?";
}

// Book a closed trade into the running P&L the loss limits are measured on.
static void BookRealized(StudyState& S, double pnlPts)
{
    S.realizedToday += pnlPts;
    S.realizedTotal += pnlPts;
    if (S.realizedTotal > S.equityPeak) S.equityPeak = S.realizedTotal;
}

// ------------------------------------------------------------------ process one completed daily bar
// Everything the signal engine needs from the Inputs, resolved once per bar.
struct RunCfg {
    double riskUnit = 1.0;
    int    direction = DIR_LONG_ONLY;
    int    logLevel = LOG_INFO;
    // exit override
    int    exitOverride = XO_PRESET;
    double ovSlAtr = 1.0, ovRrr = 2.0, ovBeR = 0.0, ovTrailAtr = 0.0;
    double ovSlPts = 0.0, ovTpPts = 0.0;
    int    globalTimeStop = 0;
    // entry override
    int    entryOverride = EO_PRESET;
    double limitOffsetPts = 0.0;
    int    entryExpiry = 1;
    bool   entryNextOpen = false;
    // per-family exit override, 0 = leave the family on its preset exits
    double famSlAtr[NUM_FAMILIES] = {0};
    double famRrr[NUM_FAMILIES]   = {0};
    // risk caps
    int    maxConcurrent = 0, maxPerFamily = 0, maxPerRole = 0;
    double maxGross = 0;        // in MES equivalents
    double contractMult = 1.0;  // 1 for MES, 10 for ES
    // loss limits, in account currency; 0 disables. usdPerPoint is per single contract.
    double dailyLossUsd = 0, maxDdUsd = 0, usdPerPoint = 5.0;
    // session completeness
    int    rthEndSec = 16 * 3600;
    int    sessionSlackSec = 300;        // tolerance on the last RTH bar before a day counts as short
    int    earlyCloseSec = 13 * 3600 + 30 * 60;  // 13:30 - the latest a SCHEDULED early close lands
};

// Resolve the exit distances for one entry: preset values, or the global override when armed.
// The override deliberately breaks parity with the research, which is why it is off by default.
static void ResolveExit(const Preset& p, const RunCfg& cfg, double atr,
                        double& slDist, double& tpDist, double& trailDist, double& beR, int& timeStop)
{
    if (cfg.exitOverride == XO_ATR_BRACKET) {
        slDist = cfg.ovSlAtr * atr;
        tpDist = cfg.ovRrr > 0 ? slDist * cfg.ovRrr : 1e18;
    } else if (cfg.exitOverride == XO_FIXED_TICKS) {
        slDist = cfg.ovSlPts > 0 ? cfg.ovSlPts : 1e18;
        tpDist = cfg.ovTpPts > 0 ? cfg.ovTpPts : 1e18;
    } else {
        slDist = p.slAtr > 0 ? p.slAtr * atr : 1e18;
        tpDist = p.tpAtr > 0 ? p.tpAtr * atr : 1e18;
    }
    // A family override sits between the preset and the global one: the global override says
    // "ALL presets" and means it, so it wins; otherwise a family's own numbers replace the
    // preset's, and a zero leaves the preset alone. SL alone is enough - the target then keeps
    // the preset's own risk-reward, which is usually what you want when widening a stop.
    if (cfg.exitOverride == XO_PRESET && p.familyIdx >= 0 && p.familyIdx < NUM_FAMILIES) {
        const double fsl = cfg.famSlAtr[p.familyIdx], frrr = cfg.famRrr[p.familyIdx];
        if (fsl > 0 || frrr > 0) {
            const double presetRrr = (p.slAtr > 0 && p.tpAtr > 0) ? p.tpAtr / p.slAtr : 0.0;
            const double useSl  = fsl  > 0 ? fsl  : p.slAtr;
            const double useRrr = frrr > 0 ? frrr : presetRrr;
            if (useSl > 0) {
                slDist = useSl * atr;
                tpDist = useRrr > 0 ? slDist * useRrr : tpDist;
            }
        }
    }
    if (cfg.exitOverride == XO_PRESET) {
        trailDist = p.trailAtr > 0 ? p.trailAtr * atr : 1e18;
        beR = p.beR;
        timeStop = p.timeStop;
    } else {
        trailDist = cfg.ovTrailAtr > 0 ? cfg.ovTrailAtr * atr : 1e18;
        beR = cfg.ovBeR;
        timeStop = p.timeStop;
    }
    if (cfg.globalTimeStop > 0) timeStop = cfg.globalTimeStop;
}

static void OpenPosition(PresetState& st, const Preset& p, const RunCfg& cfg, double atr,
                         double fill, long absDay, int i)
{
    double slDist, tpDist, trailDist, beR;
    int timeStop;
    ResolveExit(p, cfg, atr, slDist, tpDist, trailDist, beR, timeStop);
    st.inPos = 1; st.entry = fill; st.entryDay = absDay; st.entryDayIdx = i; st.heldDays = 0;
    st.best = fill; st.worst = fill;
    st.trailOn = (p.trailActR <= 0);
    st.initialStop = slDist < 1e17 ? slDist : 0;
    st.stop   = slDist < 1e17 ? fill - slDist : -1e18;
    st.target = tpDist < 1e17 ? fill + tpDist : 1e18;
    st.trailDist = trailDist; st.beR = beR; st.timeStop = timeStop;
}

// Would opening this preset breach one of the exposure caps? Zero means the cap is off.
static bool CapsAllow(const StudyState& S, size_t k, const RunCfg& cfg)
{
    const Preset& p = S.presets[k];
    int total = 0, sameFamily = 0, sameRole = 0;
    double gross = 0;
    for (size_t j = 0; j < S.states.size(); ++j) {
        if (S.states[j].inPos == 0) continue;
        ++total;
        gross += cfg.riskUnit * cfg.contractMult;
        if (S.presets[j].familyIdx == p.familyIdx) ++sameFamily;
        if (S.presets[j].role == p.role) ++sameRole;
    }
    if (cfg.maxConcurrent > 0 && total >= cfg.maxConcurrent) return false;
    if (cfg.maxPerFamily > 0 && sameFamily >= cfg.maxPerFamily) return false;
    if (cfg.maxPerRole > 0 && sameRole >= cfg.maxPerRole) return false;
    if (cfg.maxGross > 0 && gross + cfg.riskUnit * cfg.contractMult > cfg.maxGross) return false;
    return true;
}

static void ProcessDay(SCStudyInterfaceRef sc, StudyState& S, const std::vector<Features>& F, int i,
                       long absDay, const RunCfg& cfg, const SCString& journalPath)
{
    const double riskUnit = cfg.riskUnit;
    const int direction = cfg.direction, logLevel = cfg.logLevel;
    const std::vector<DailyBar>& d = S.daily;
    const Features& f = F[i];
    if (!f.ready) return;
    const Features& pf = (i >= 1 && F[i - 1].ready) ? F[i - 1] : f;

    // ---- loss limits
    //
    // A new trading day clears the daily limit; the drawdown limit does not clear by itself,
    // because a book that has given back that much is not a book to keep starting fresh every
    // morning. Both only block NEW entries: positions already in the market keep their stop and
    // target and are managed to the end, which is the opposite of a flatten-everything switch
    // and is deliberate - swings are held overnight and a forced exit at a limit breach would
    // realise the worst price of the move.
    const double usdPerPt = cfg.usdPerPoint;
    if (absDay != S.realizedDay) {
        // The book decides once a session, at the close, so every entry and every exit of a day
        // happen at the same instant: a limit that stopped trading "for the rest of the day"
        // would have nothing left to stop. What it can do is stand the book down for the session
        // after a day that lost more than the limit, and that is what this does.
        const bool breach = cfg.dailyLossUsd > 0 && S.realizedDay >= 0 &&
                            S.realizedToday * usdPerPt <= -cfg.dailyLossUsd;
        if (breach) {
            SCString m; m.Format("Multi-Swing: DAILY LOSS LIMIT - the last session realised "
                                 "%.0f USD (%.2f pts), past the %.0f USD limit. No new entries "
                                 "this session; open positions keep their stop and target.",
                                 -S.realizedToday * usdPerPt, S.realizedToday, cfg.dailyLossUsd);
            sc.AddMessageToLog(m, 1);
        }
        S.haltedDaily = breach;
        S.realizedDay = absDay;
        S.realizedToday = 0;
    }
    if (cfg.maxDdUsd > 0 && !S.haltedDd &&
        (S.equityPeak - S.realizedTotal) * usdPerPt >= cfg.maxDdUsd) {
        S.haltedDd = true;
        SCString m; m.Format("Multi-Swing: MAX DRAWDOWN STOP hit - %.0f USD off the peak "
                             "(%.2f pts). No new entries at all until the study is reloaded; "
                             "open positions keep their stop and target.",
                             (S.equityPeak - S.realizedTotal) * usdPerPt, S.equityPeak - S.realizedTotal);
        sc.AddMessageToLog(m, 1);
    }
    const bool halted = S.haltedDaily || S.haltedDd;

    // Max Gross Exposure is in MES equivalents, so one preset costs riskUnit x 1 on MES and
    // riskUnit x 10 on ES. Set the cap below that and CapsAllow refuses the very first entry of
    // every session forever - and the symptom, an empty book, looks exactly like a quiet market.
    // Nothing else in the study can distinguish those two, so it says which one it is.
    const double onePreset = cfg.riskUnit * cfg.contractMult;
    if (!S.grossCapWarned && cfg.maxGross > 0 && onePreset > cfg.maxGross) {
        S.grossCapWarned = true;
        SCString m;
        m.Format("Multi-Swing: MAX GROSS EXPOSURE (%.0f) IS SMALLER THAN ONE PRESET (%.0f = risk "
                 "unit %.2f x %.0f for %s). No preset can ever enter and the book will stay empty. "
                 "The cap counts MES equivalents, so on ES one preset costs ten of them.",
                 cfg.maxGross, onePreset, cfg.riskUnit, cfg.contractMult,
                 cfg.contractMult > 1.5 ? "ES" : "MES");
        sc.AddMessageToLog(m, 1);
    }

    for (size_t k = 0; k < S.presets.size(); ++k) {
        Preset& p = S.presets[k];
        PresetState& st = S.states[k];
        if (!p.valid) continue;
        // family switch and weight from the Inputs
        double weight = 1.0;
        if (p.familyIdx >= 0) {
            if (sc.Input[IN_FAM1_ON + 2 * p.familyIdx].GetYesNo() == 0) { st = PresetState(); continue; }
            weight = sc.Input[IN_FAM1_W + 2 * p.familyIdx].GetFloat();
        }
        if (direction == DIR_SHORT_ONLY) { st = PresetState(); continue; }   // every preset here is long

        // ---- 1. a resting order armed yesterday may fill today (limit / stop, ON + RTH)
        if (st.inPos == 0 && st.pendingSide != 0 && !halted &&
            absDay - st.pendingDay >= 1 && absDay - st.pendingDay <= cfg.entryExpiry) {
            bool filled = false; double fill = 0;
            if (st.pendingLevel > 1e17) { filled = true; fill = d[i].o; }          // "next open" entry
            else if (st.pendingKind == EK_LIMIT) {
                if (d[i].ethLow <= st.pendingLevel) { filled = true; fill = std::min(st.pendingLevel, d[i].o); }
            } else if (st.pendingKind == EK_STOP_ABOVE_HIGH) {
                if (d[i].ethHigh >= st.pendingLevel) { filled = true; fill = std::max(st.pendingLevel, d[i].o); }
            }
            if (filled || absDay - st.pendingDay >= cfg.entryExpiry) st.pendingSide = 0;
            if (filled) OpenPosition(st, p, cfg, f.atr20, fill, absDay, i);
        }

        // ---- 2. an "@open" exit armed yesterday is executed on today's open, before anything else
        if (st.inPos == 1 && st.exitNextOpen) {
            double px = d[i].o;
            double pnl = px - st.entry;
            SCString row;
            int sdIdx = i - (int)(absDay - st.signalDay), edIdx = i - (int)(absDay - st.entryDay);
            row.Format("%s,%s,%s,%s,%s,1,%.2f,%.2f,%.2f,%.2f,%.2f,%d,%s",
                       p.id.GetChars(), p.family.GetChars(),
                       DayString(d[std::max(sdIdx, 0)].date).GetChars(),
                       DayString(d[std::max(edIdx, 0)].date).GetChars(),
                       DayString(d[i].date).GetChars(),
                       st.entry, px, pnl * riskUnit * weight,
                       st.worst - st.entry, st.best - st.entry,
                       (int)(absDay - st.entryDay) + 1, "signal");
            AppendJournal(journalPath, row, S);
            BookRealized(S, pnl * riskUnit * weight);
            st = PresetState();
        }

        // ---- 3. manage an open position against today's range; stop first when both are touched
        if (st.inPos == 1) {
            // the protective level is derived from the excursion BEFORE this bar, so that today's
            // own high can never arm a trail or breakeven that today's low then triggers
            double eff = st.stop; int reason = 1;
            if (st.trailOn && st.trailDist < 1e17) {
                double ts = st.best - st.trailDist;
                if (ts > eff) { eff = ts; reason = 3; }
            }
            if (st.beR > 0 && st.initialStop > 0 && (st.best - st.entry) >= st.beR * st.initialStop) {
                double be = st.entry;
                if (be > eff) { eff = be; reason = 6; }
            }
            st.best  = std::max(st.best, d[i].ethHigh);
            st.worst = std::min(st.worst, d[i].ethLow);
            bool hitStop   = (eff > -1e17) && d[i].ethLow  <= eff;
            bool hitTarget = (st.target < 1e17) && d[i].ethHigh >= st.target;
            int  code = 0; double px = 0;
            if (hitStop)        { code = reason; px = std::min(d[i].o, eff); }   // gap through fills at the open
            else if (hitTarget) { code = 2;      px = std::max(d[i].o, st.target); }

            if (code == 0) {
                ++st.heldDays;
                if (st.timeStop > 0 && st.heldDays >= st.timeStop) { code = 4; px = d[i].c; }
                else if (ExitSignal(p, f)) {
                    if (p.xsigAtOpen) st.exitNextOpen = true;    // executed on the next open
                    else { code = 5; px = d[i].c; }
                }
                if (!st.trailOn && p.trailActR > 0 && st.initialStop > 0 &&
                    (st.best - st.entry) >= p.trailActR * st.initialStop) st.trailOn = true;

                // Re-derive where the account's stop should sit now that today's excursion counts.
                double acc = st.stop;
                if (st.trailOn && st.trailDist < 1e17)
                    acc = std::max(acc, st.best - st.trailDist);
                if (st.beR > 0 && st.initialStop > 0 && (st.best - st.entry) >= st.beR * st.initialStop)
                    acc = std::max(acc, st.entry);
                st.accountStop = acc;
            }
            if (code != 0) {
                double pnl = px - st.entry;
                SCString row;
                int sdIdx = i - (int)(absDay - st.signalDay), edIdx = i - (int)(absDay - st.entryDay);
                SCDateTime sd = d[std::max(sdIdx, 0)].date, ed = d[std::max(edIdx, 0)].date, xd = d[i].date;
                row.Format("%s,%s,%s,%s,%s,1,%.2f,%.2f,%.2f,%.2f,%.2f,%d,%s",
                           p.id.GetChars(), p.family.GetChars(),
                           DayString(sd).GetChars(), DayString(ed).GetChars(),
                           DayString(xd).GetChars(),
                           st.entry, px, pnl * riskUnit * weight,
                           st.worst - st.entry, st.best - st.entry,
                           (int)(absDay - st.entryDay) + 1, ReasonName(code));
                AppendJournal(journalPath, row, S);
                BookRealized(S, pnl * riskUnit * weight);
                if (logLevel >= LOG_INFO) {
                    SCString m; m.Format("EXIT %s %s @ %.2f  (%.2f pts, %s)",
                                         p.id.GetChars(), DayString(xd).GetChars(), px, pnl, ReasonName(code));
                    sc.AddMessageToLog(m, 0);
                }
                st = PresetState();
            }
        }

        // ---- 4. a new signal on today's close
        if (st.inPos == 0 && st.pendingSide == 0 && !st.exitNextOpen && !halted) {
            if (RegimeOk(p, f) && SetupSignal(p, d, i, f, pf) && CapsAllow(S, k, cfg)) {
                st.signalDay = absDay;
                EntryKind entry = p.entry;
                if (cfg.entryOverride == EO_FORCE_CLOSE) entry = EK_CLOSE;
                else if (cfg.entryOverride == EO_FORCE_LIMIT) entry = EK_LIMIT;
                if (cfg.entryNextOpen && entry == EK_CLOSE) { entry = EK_LIMIT; }   // filled at the next open
                if (entry == EK_CLOSE) {
                    OpenPosition(st, p, cfg, f.atr20, f.c, absDay, i);
                } else {
                    st.pendingSide = 1;
                    st.pendingDay  = absDay;
                    st.pendingKind = entry;
                    if (cfg.entryNextOpen && p.entry == EK_CLOSE) st.pendingLevel = 1e18;  // any price: next open
                    else st.pendingLevel = (entry == EK_LIMIT)
                                         ? f.c - p.entryOffsetAtr * f.atr20 - cfg.limitOffsetPts
                                         : f.h + cfg.limitOffsetPts;
                }
                if (logLevel >= LOG_INFO) {
                    SCString m; m.Format("SIGNAL %s %s  close %.2f  ATR %.2f  %s",
                                         p.id.GetChars(), DayString(d[i].date).GetChars(),
                                         f.c, f.atr20, p.entry == EK_CLOSE ? "filled at close" : "order armed");
                    sc.AddMessageToLog(m, 0);
                }
            }
        }
    }
}

// ------------------------------------------------------------------ calendar helpers
// The trading day of a bar: bars at or after the RTH end belong to the NEXT trading day,
// exactly like the ON -> next RTH session mapping in swing_lab/features.py.
static int TradingDateDays(const SCDateTime& dt, int rthEndSeconds)
{
    int days = dt.GetDate();
    if (dt.GetTimeInSeconds() >= rthEndSeconds) {
        ++days;
        SCDateTime probe; probe.SetDate(days);
        int dow = probe.GetDayOfWeek();                 // 0 = Sunday
        if (dow == 6) days += 2; else if (dow == 0) days += 1;
    }
    return days;
}
// The Monday that owns this date, used as the weekly anchor's key.
//
// This used to be (days + 3) / 7, which lands on a Monday only if day zero is a Thursday - true of
// the Unix epoch, and of the harness stub, but not of Sierra: SCDateTime counts from 1899-12-30, a
// Saturday, so in Sierra the week turned over on a WEDNESDAY. The weekly VWAP and its sigma bands
// were anchored two days late for every live and replayed bar, while the off-line run was correct,
// which is why no parity test caught it. Asking the date for its own weekday is epoch-independent.
static int WeekKey(const SCDateTime& t)
{
    const int dow = t.GetDayOfWeek();        // 0 = Sunday
    return t.GetDate() - (dow + 6) % 7;      // days back to Monday
}
static int MonthKey(const SCDateTime& d) { return d.GetYear() * 12 + d.GetMonth(); }
static int QuarterKey(const SCDateTime& d) { return d.GetYear() * 4 + (d.GetMonth() - 1) / 3; }

static void ResetDayAccumulators(StudyState& S)
{
    S.cur = DailyBar();
    S.curTpv = S.curTp2v = S.curVol = 0;
    S.sessionOpen = false;
    S.curLastRthTod = -1;
}


// Close the in-progress trading day: finish the VWAP accumulators, append the daily bar,
// compute its features and run the signal engine on it. Called when the next trading day's
// first bar arrives, and - for live trading - once the session end has passed in real time,
// so a half-day session is not left open until the next Globex open.
static void FinalizeDay(SCStudyInterfaceRef sc, StudyState& S, std::vector<Features>& feats,
                        const RunCfg& cfg, const SCString& journal, bool enabled)
{
    DailyBar& b = S.cur;

    // A session that never reached its RTH end was not fully delivered: a replay stopped and
    // restarted mid-session, or a hole in the feed. The day still has to be appended, because
    // dropping it would shift every session index the open positions count against - but its
    // close is whatever price arrived last, and that close then feeds ATR20 and every moving
    // average for the next twenty sessions. Measured once on the 2023-08-09 replay: one session
    // truncated at 15:35 moved 26 entries across five days. Silence is what made that expensive
    // to find, so it is logged loudly and counted in the status box.
    if (S.curLastRthTod >= 0 && S.curLastRthTod < cfg.rthEndSec - cfg.sessionSlackSec) {
        // A scheduled half day and a hole in the feed both leave the session short, and no bar
        // says which one happened - the study does not know the exchange calendar. The clock
        // does separate them in practice: every US early close lands at 13:00 or 13:15, and
        // nothing is scheduled to close later than that but before the bell. Measured over
        // 2015-2026 of clean research data: 99 short sessions, all of them at 12:59, 13:00 or
        // 13:14, and not one in between - while the 2023-08-09 replay was cut at 15:35. So a
        // session ending after earlyCloseSec is a gap, and one ending before it is a half day
        // that both this study and the research engine see the same way.
        const int hh = S.curLastRthTod / 3600, mm = (S.curLastRthTod % 3600) / 60;
        if (S.curLastRthTod >= cfg.earlyCloseSec) {
            ++S.incompleteDays;
            SCString m;
            m.Format("Multi-Swing: INCOMPLETE SESSION %s - last RTH bar at %02d:%02d, RTH ends at "
                     "%02d:%02d, and no exchange half day closes then. The close used is %.2f, "
                     "which is not the session's close. This day's signals and the next ~20 "
                     "sessions of ATR are computed from it. Re-run the replay without stopping "
                     "mid-session, or fill the gap in the chart's data.",
                     DayString(b.date).GetChars(), hh, mm,
                     cfg.rthEndSec / 3600, (cfg.rthEndSec % 3600) / 60, b.c);
            sc.AddMessageToLog(m, 1);
        } else if (cfg.logLevel >= LOG_DEBUG) {
            SCString m;
            m.Format("Multi-Swing: shortened session %s - last RTH bar at %02d:%02d, consistent "
                     "with a scheduled early close.", DayString(b.date).GetChars(), hh, mm);
            sc.AddMessageToLog(m, 0);
        }
    }

    if (S.curVol > 0) {
        b.dvwap = S.curTpv / S.curVol;
        b.dvwapSd = sqrt(std::max(S.curTp2v / S.curVol - b.dvwap * b.dvwap, 0.0));
    }
    if (S.wVol > 0) { b.wvwap = S.wTpv / S.wVol;
                      b.wvwapSd = sqrt(std::max(S.wTp2v / S.wVol - b.wvwap * b.wvwap, 0.0)); }
    if (S.mVol > 0) { b.mvwap = S.mTpv / S.mVol;
                      b.mvwapSd = sqrt(std::max(S.mTp2v / S.mVol - b.mvwap * b.mvwap, 0.0)); }
    if (S.qVol > 0) b.qvwap = S.qTpv / S.qVol;
    b.prevMvwap = S.lastCompletedMvwap;

    S.daily.push_back(b);
    if ((int)S.daily.size() > DAILY_HISTORY) { S.daily.erase(S.daily.begin()); feats.erase(feats.begin()); }
    int di = (int)S.daily.size() - 1;
    feats.resize(S.daily.size());
    feats[di] = ComputeFeatures(S.daily, di);
    AppendFeatureCsv(S.featureCsv, b.date, S.daily[di], feats[di]);
    ++S.dayCounter;
    if (enabled) ProcessDay(sc, S, feats, di, S.dayCounter, cfg, journal);
    ResetDayAccumulators(S);
}

// ------------------------------------------------------------------ order layer
//
// The book is 48 presets, each with its own stop and target; a Sierra chart holds one position.
// Every entry is therefore sent as its own order carrying Sierra's own bracket - the stop and the
// target attached to it - and Sierra works and cancels them. The study does not manage protective
// orders itself. It tried, and the first Replay through a simulator showed why not: a hand-built
// ladder of sell-stops has to agree with Sierra about how much of the position is already spoken
// for, it never did, and every call ended in a rejected order and presets left unprotected.
//
// Netting the book into one market order a session was the other thing tried, and measured: it
// drops 39 % of the book's exits, the ones that happen at a stop, a target or a trail, so the
// account would trade a book without stops rather than the validated one. See check_netting.py.
//
// Quantity per preset is Risk Unit x family weight, the figure the ledger books P&L on.
static int PresetQty(SCStudyInterfaceRef sc, const StudyState& S, size_t k, const RunCfg& cfg)
{
    if (k >= S.presets.size()) return 0;
    const int fi = S.presets[k].familyIdx;
    if (fi < 0 || sc.Input[IN_FAM1_ON + 2 * fi].GetYesNo() == 0) return 0;
    const double q = cfg.riskUnit * sc.Input[IN_FAM1_W + 2 * fi].GetFloat();
    return (int)(q + 0.5);
}

// The book stores "no stop" as -1e18 and "no target" as +1e18, so a price is only real when it is
// anywhere near the market. Testing price > 0 let the +1e18 through, and the study spent a Replay
// asking the simulator for limit orders at a billion billion.
// What the book wants the account to be holding, for the status box.
static int TargetContracts(SCStudyInterfaceRef sc, const StudyState& S, const RunCfg& cfg)
{
    int q = 0;
    for (size_t k = 0; k < S.states.size(); ++k)
        if (S.states[k].inPos != 0) q += PresetQty(sc, S, k, cfg);
    return q;
}

static bool RealPrice(double p, double ref)
{
    return p > 0 && ref > 0 && p > ref * 0.5 && p < ref * 2.0;
}

// Sierra refused because the chart is recalculating. That is its call to make, not something to
// predict: a chart replay turned out to recalculate on EVERY bar, so a guard that skipped sending
// whenever sc.UpdateStartIndex was 0 silenced the order layer for the whole replay. The study
// therefore always offers the order and lets Sierra decide, and handles this one code separately:
// it does not count toward the rejection cut-off - an account that never saw the order cannot be
// out of step with the book - and the rest of the call is abandoned, so one refused order costs
// one log line instead of forty-eight. Logged on the first and then every 500th, because at one
// per replay bar it would otherwise be the only thing in the Message Log.
static bool SkippedForRecalc(SCStudyInterfaceRef sc, StudyState& S, int rc, int logLevel)
{
    if (rc != SCT_SKIPPED_FULL_RECALC_CODE) return false;
    ++S.recalcSkips;
    if (logLevel >= LOG_INFO && (S.recalcSkips == 1 || S.recalcSkips % 500 == 0)) {
        SCString m;
        m.Format("Multi-Swing: Sierra is recalculating the chart and skipped the order "
                 "(SCT_SKIPPED_FULL_RECALC, %ld so far, bar %d, replay %s). Nothing reached the "
                 "account, so nothing is out of step; the book is offered again on the next call. "
                 "If this never stops during a replay, the Chart Replay dialog's Replay Mode is "
                 "the setting that decides whether a replay recalculates every bar.",
                 S.recalcSkips, (int)sc.ArraySize, sc.IsReplayRunning() ? "RUNNING" : "off");
        sc.AddMessageToLog(m, 0);
    }
    return true;
}

// Move a preset's protective stop to where the trail or breakeven now puts it.
//
// Sierra owns the attached bracket and never moves it on its own, so eight of the forty-eight
// presets - the trailing and breakeven ones, 304 of 6,504 trades in the reference ledger - used to
// end on a market exit at whatever price the book happened to close them at, instead of on the
// stop the research measured. The position was never unprotected, the original wider stop stayed
// in the market, but the exit price was systematically worse.
//
// The stop is only ever raised. These presets are long-only, and lowering a protective stop on a
// live position to match a number the study recomputed is the one mistake here that could actually
// cost money rather than basis points.
// How a preset the book has closed actually comes off the account.
//
// Every entry goes out with a stop and a target attached, so every contract held is already
// covered by a working sell order. Sierra will not accept a market sell on top of that, and it
// says so in the Trade Activity Log in as many words:
//
//   SellExit signal is ignored. ... there are already working exit orders that will flatten the
//   position. Current Position with working exit orders: 0. Current Position: 21.
//
// "Position with working exit orders: 0" is the whole answer - nothing is uncovered, so there is
// nothing a further sell could legitimately close. That is why every BUY was accepted and every
// SELL refused: an exit that could not exist by construction, not a misconfigured account.
//
// So the exit goes THROUGH the bracket. The preset's own target is a working sell limit above the
// market; moved to just under the market it fills at once and takes exactly that preset's
// contracts off. The thirteen presets whose exit carries no price have no target, only a stop, and
// that stop is moved just above the market instead, where a sell stop triggers immediately. Some
// routes refuse that price; the refusal is handled rather than assumed, because the alternative -
// cancelling the stop and waiting for a market sell - leaves those contracts unprotected in the
// meantime, and that is a real risk where a rejected modification costs only a call.
//
// A steered child is a working order like any other: it is not filled by the time the next study
// call runs, and in a fast replay it may take many calls, or the market may walk away from the
// price it was moved to. So the leg is NOT forgotten when the exit goes out. It is kept, its
// contracts keep counting as held, and every later call either leaves the order where it is - the
// market can still fill it - or moves it to follow the market. The leg is only let go once the
// bracket reports no live children, which is Sierra's own way of saying the contracts have left
// the account.
//
// Forgetting the leg after one call is what produced the last refusal on the chart: the exit was
// steered, the leg was wiped, the fill had not landed, and on the next call those contracts looked
// like a surplus nobody owned - so they went out as a market sell, which Sierra refused because the
// moved target was still covering them. Five of those latch the whole order layer.
enum RetireVerdict {
    RETIRE_SENT,        // a child was just steered to the market
    RETIRE_WORKING,     // a steered child is already sitting at a price the market can fill
    RETIRE_ALREADY,     // no live child: the bracket is done, so the contracts are off
    RETIRE_UNCOVERED,   // the bracket was cancelled - sellable, but not in this same call
    RETIRE_STUCK        // no handle on the bracket at all; nothing this study can do
};

static RetireVerdict RetireLegNow(SCStudyInterfaceRef sc, StudyState& S, AccountLeg& lg,
                                  size_t k, double last, int logLevel)
{
    // A steered child that has not filled after this many calls is not going to: cancel the
    // bracket and let the market sell take the contracts instead. It is a long way past any
    // plausible fill, and the alternative - waiting for ever on an order the route is holding
    // rather than working - hides contracts the book has already written off.
    enum { EXIT_PATIENCE = 8 };

    if (lg.parentOrderId == 0) return RETIRE_STUCK;
    int targetId = 0, stopId = 0;
    sc.GetAttachedOrderIDsForParentOrder((int)lg.parentOrderId, targetId, stopId);
    if (targetId == 0 && stopId == 0) {
        ++S.bracketsEmpty;                 // the bracket is done, so the contracts are off
        lg.exitPrice = 0.0; lg.exitCalls = 0;
        return RETIRE_ALREADY;
    }
    ++S.bracketsSeen;

    const double tick = sc.TickSize > 0 ? sc.TickSize : 0.25;

    // Which child is steered, and where to.
    //
    // A target is a sell limit above the market: moved just under the market it is fillable at
    // once, at a price every route accepts. A stop is a sell stop below the market: moved just
    // above the market it triggers at once, which is a price some routes reject - so it is tried
    // and the refusal is handled, rather than assumed either way. The thirteen presets whose exit
    // carries no price at all have only a stop, and this is the whole reason to try: cancelling it
    // leaves their contracts unprotected until a market sell takes them, and steering it does not.
    const bool   useStop = (targetId == 0);
    const int    childId = useStop ? stopId : targetId;
    const double price   = useStop ? ToTick(last + tick, tick, false) : ToTick(last - tick, tick, true);

    if (lg.exitPrice > 0.0) {
        // An exit already at a price the market can fill is left alone: re-sending the same price
        // on every call would be thousands of pointless modifications in one replay. It is moved
        // only when the market has walked past it, which is the one case where leaving it means it
        // never fills - a sell limit needs the market at or above it, a triggered sell stop at or
        // below.
        const bool fillable = lg.exitIsStop ? (last <= lg.exitPrice) : (last >= lg.exitPrice);
        if (fillable && ++lg.exitCalls <= EXIT_PATIENCE) return RETIRE_WORKING;
        if (lg.exitCalls > EXIT_PATIENCE) {
            if (targetId != 0) sc.CancelOrder(targetId);
            if (stopId   != 0) sc.CancelOrder(stopId);
            if (logLevel >= LOG_INFO) {
                SCString m;
                m.Format("Multi-Swing: EXIT %s did not fill in %d calls at %.2f; its bracket was "
                         "cancelled and its %d contract(s) go out at market instead.",
                         S.presets[k].id.GetChars(), (int)EXIT_PATIENCE, lg.exitPrice,
                         lg.qtyOnAccount);
                sc.AddMessageToLog(m, 0);
            }
            lg.exitPrice = 0.0; lg.exitCalls = 0;
            return RETIRE_UNCOVERED;
        }
    }

    s_SCNewOrder mod;
    mod.InternalOrderID = childId;
    mod.Price1 = price;
    const int rc = (int)sc.ModifyOrder(mod);
    if (SkippedForRecalc(sc, S, rc, logLevel)) return RETIRE_STUCK;   // retried next call
    if (rc > 0) {
        ++S.modifyOk;
        const bool again = lg.exitPrice > 0.0;
        if (logLevel >= (again ? LOG_DEBUG : LOG_INFO)) {
            SCString m;
            if (again)
                m.Format("Multi-Swing: EXIT %s still working - the market left it behind, so its "
                         "%s order %d follows from %.2f to %.2f.",
                         S.presets[k].id.GetChars(), useStop ? "stop" : "target", childId,
                         lg.exitPrice, price);
            else
                m.Format("Multi-Swing: EXIT %s through its own bracket - %s order %d moved to "
                         "%.2f for %d contract(s).",
                         S.presets[k].id.GetChars(), useStop ? "stop" : "target", childId, price,
                         lg.qtyOnAccount);
            sc.AddMessageToLog(m, 0);
        }
        lg.exitPrice  = price;
        lg.exitIsStop = useStop;
        lg.exitCalls  = 0;
        return RETIRE_SENT;
    }

    ++S.modifyFail;
    // The route would not take the price. Cancel the bracket so the contracts stop counting as
    // covered; a market sell for them is then something Sierra will accept - a call later, once
    // the cancel has actually taken.
    if (targetId != 0) sc.CancelOrder(targetId);
    if (stopId   != 0) sc.CancelOrder(stopId);
    lg.exitPrice = 0.0; lg.exitCalls = 0;
    if (logLevel >= LOG_INFO && lg.retireTries == 0) {
        SCString m;
        m.Format("Multi-Swing: could not steer %s's %s (order %d to %.2f, Sierra returned %d); "
                 "cancelled the bracket, so those %d contract(s) go out at market once the cancel "
                 "has taken.",
                 S.presets[k].id.GetChars(), useStop ? "stop" : "target", childId, price, rc,
                 lg.qtyOnAccount);
        sc.AddMessageToLog(m, 0);
    }
    return RETIRE_UNCOVERED;
}

static void MoveAccountStop(SCStudyInterfaceRef sc, StudyState& S, size_t k, AccountLeg& lg,
                            const PresetState& st, bool send, int logLevel)
{
    const double want = st.accountStop;
    if (want < -1e17) return;                                  // this preset has no stop at all
    const double tick = sc.TickSize > 0 ? sc.TickSize : 0.25;

    // Decide on the price that would actually be sent, not on the unrounded wish. Rounding the
    // stop down can leave it up to a tick below what the trail asked for, so comparing the wish
    // against what is working made the same tick look like a move still owed on every call: 643
    // real moves became 6,573 re-sends of prices already in the market.
    const double onTick = ToTick(want, tick, true);
    if (onTick <= lg.stopOnAccount + tick / 2.0) return;       // already there, or a step down
    if (!send) {
        if (logLevel >= LOG_INFO) {
            SCString m; m.Format("Multi-Swing SEMI: would MOVE STOP for %s from %.2f to %.2f",
                                 S.presets[k].id.GetChars(), lg.stopOnAccount, onTick);
            sc.AddMessageToLog(m, 0);
        }
        lg.stopOnAccount = onTick;
        return;
    }

    if (lg.parentOrderId == 0) return;                         // nothing to hang the lookup on
    int targetId = 0, stopId = 0;
    sc.GetAttachedOrderIDsForParentOrder((int)lg.parentOrderId, targetId, stopId);
    if (stopId == 0) return;   // no working stop child: already filled, or the bracket is gone

    s_SCNewOrder mod;
    mod.InternalOrderID = stopId;
    mod.Price1 = onTick;
    const int rc = (int)sc.ModifyOrder(mod);
    if (SkippedForRecalc(sc, S, rc, logLevel)) return;
    if (rc > 0) {
        if (logLevel >= LOG_INFO) {
            SCString m; m.Format("Multi-Swing: STOP MOVED for %s from %.2f to %.2f (order %d)",
                                 S.presets[k].id.GetChars(), lg.stopOnAccount, mod.Price1, stopId);
            sc.AddMessageToLog(m, 0);
        }
        // Record what is actually working in the market, not the unrounded wish, or every later
        // call would see the tick of difference as a move still owed and keep re-sending it.
        lg.stopOnAccount = mod.Price1;
    } else {
        // Not counted against orderFailures: a refused stop move leaves the previous, wider stop
        // working, so the position stays protected and the book stays consistent with the account.
        // Cutting off entries over it would be a bigger problem than the one being reported.
        SCString m;
        m.Format("Multi-Swing: STOP MOVE REFUSED, Sierra returned %d: %s from %.2f to %.2f "
                 "(stop order %d, parent %u). The earlier, wider stop is still working.",
                 rc, S.presets[k].id.GetChars(), lg.stopOnAccount, want, stopId, lg.parentOrderId);
        sc.AddMessageToLog(m, 1);
    }
}

// The rejection cut-off used to be cleared by any single accepted order. A configuration that
// refused nine orders in ten therefore never latched: the tenth reset the counter, the next call
// started from zero, and the account drifted further from the book on every bar while the status
// box stayed green. Counted per call instead - a call that got everything it asked for clears the
// pressure, a call with refusals adds its refusals to it - and committed from a destructor so
// that every path out of SyncOrders, including the early returns, records the same thing.
struct FailureTally {
    StudyState& S;
    int  fails = 0;
    bool anyOk = false;
    explicit FailureTally(StudyState& s) : S(s) {}
    ~FailureTally() { if (fails > 0) S.orderFailures += fails; else if (anyOk) S.orderFailures = 0; }
    FailureTally(const FailureTally&) = delete;
    FailureTally& operator=(const FailureTally&) = delete;
};

// ---- bring the total back down to what the book wants
//
// Because Sierra works each bracket, it closes a stopped-out preset without telling the study,
// which makes the reported position - not the ledger - the only honest record of what is held.
// Everything the book closed for its own reasons (a signal exit, a time stop) is exactly the
// difference between that position and what the book still wants, and it goes out as one order
// instead of being guessed at preset by preset.
//
// What reaches this order is now only what nothing else covers: contracts whose bracket was
// cancelled on an earlier call, and contracts the account still reports after their bracket has
// gone. Every preset the book has closed leaves through its own target instead (RetireLegNow),
// and its contracts count as wanted here until they are genuinely off. That distinction is the
// whole fix: a market sell for a contract that still has a working stop or target on it is
// over-selling by construction, Sierra refuses it, and five refusals latch the order layer.
//
// This runs BEFORE the entries now, and that ordering is the point. It used to run after them,
// and a chart where the entries were accepted while the trims were refused then ratcheted: every
// session added contracts and nothing ever came off, so the account walked from ten to nineteen
// while the book still wanted ten, and only the five-rejection cut-off eventually stopped it -
// after the drift, not before. Squaring the position first means the account can never grow while
// its exits are being refused.
enum TrimResult { TRIM_NOTHING, TRIM_SENT, TRIM_WAITING, TRIM_REFUSED };

static TrimResult TrimSurplus(SCStudyInterfaceRef sc, StudyState& S, const RunCfg& cfg,
                              bool send, int logLevel, FailureTally& tally, int want, int account)
{
    // What this order may take, and when.
    //
    // WHAT: only contracts no preset claims. Every contract the study puts on the account is
    // recorded on the preset that bought it and carries that preset's bracket; Sierra refuses a
    // market sell for anything a bracket covers, and a preset's contracts leave through its own
    // target instead (RetireLegNow). So the quantity here is the position minus everything the
    // legs account for: contracts left behind by a bracket that was cancelled, and contracts the
    // book cannot place with anybody. Deriving it from the legs rather than remembering what was
    // sent is what makes it self-correcting - as the fills land, the position falls and this
    // number falls with it, with nothing to decay, expire or get out of step.
    //
    // WHEN: once, then not again for a few calls. A market order is not reported filled by the
    // time the next study call runs - above real-time replay speeds it can take several - and the
    // calls in between still see those contracts. Offering them again is the refusal that latches
    // the whole order layer, and offline, against a two-call fill, it sold 193,679 contracts where
    // the book wanted 8,800. The wait is a plain countdown rather than a test on the position,
    // because the position also moves for reasons that have nothing to do with this order - any
    // bracket filling in the meantime made a "has it landed yet" test read yes and resend.
    enum { TRIM_COOLDOWN = 8 };
    if (S.trimWaited > 0) { --S.trimWaited; return TRIM_NOTHING; }

    int ownedByLegs = 0;
    for (size_t k = 0; k < S.legs.size(); ++k) ownedByLegs += S.legs[k].qtyOnAccount;
    int surplus = account - ownedByLegs;
    // The book's own view is the second opinion: it can only make this smaller, never larger.
    if (surplus > account - want) surplus = account - want;
    if (surplus <= 0) return TRIM_NOTHING;

    if (!send) {
        S.semiPosition -= surplus;
        if (logLevel >= LOG_INFO) {
            SCString m; m.Format("Multi-Swing SEMI: would SELL %d to hold %d contracts.",
                                 surplus, want);
            sc.AddMessageToLog(m, 0);
        }
        return TRIM_SENT;
    }

    s_SCNewOrder o;
    o.OrderQuantity = surplus;
    o.OrderType     = SCT_ORDERTYPE_MARKET;
    o.TimeInForce   = SCT_TIF_DAY;
    const int rc = (int)sc.SellExit(o);
    if (SkippedForRecalc(sc, S, rc, logLevel)) return TRIM_WAITING;
    if (rc > 0) {
        S.trimSentQty     = surplus;          // what is on its way, for the diagnostics
        S.trimWaited      = TRIM_COOLDOWN;    // nothing further offered until the fill can land
        ++S.ordersPlaced;
        tally.anyOk       = true;
        if (logLevel >= LOG_INFO) {
            SCString m; m.Format("Multi-Swing: SELL %d - %d contract(s) on the account that no "
                                 "preset claims, position %d -> %d (book wants %d).",
                                 surplus, surplus, account, account - surplus, want);
            sc.AddMessageToLog(m, 0);
        }
        return TRIM_SENT;
    }

    SCString m;
    m.Format("Multi-Swing ORDER REJECTED, Sierra returned %d: SELL %d unclaimed contract(s) to "
             "bring the position from %d to %d. (%d of %d before order placement stops.)%s",
             rc, surplus, account, account - surplus, S.orderFailures + tally.fails + 1,
             (int)ORDER_FAILURE_LIMIT, OrderRejectHint(rc));
    sc.AddMessageToLog(m, 1);
    S.lastRejectCode = rc;
    if (S.orderFailures + ++tally.fails >= ORDER_FAILURE_LIMIT)
        sc.AddMessageToLog(IsSkipCode(rc) ? STOPPED_NOTICE_SKIPPED : STOPPED_NOTICE, 1);
    return TRIM_REFUSED;
}

static void SyncOrders(SCStudyInterfaceRef sc, StudyState& S, const RunCfg& cfg,
                       int mode, bool enabled, int logLevel, double last)
{
    if (!enabled || mode == MODE_SIGNALS) return;

    // Sierra refuses every ACSIL order placed during a full recalculation and returns
    // SCT_SKIPPED_FULL_RECALC (-8998) for each one. That is deliberate on its side: a study
    // recalculating years of history must not fire that history at an account. This function is
    // called at the end of every study call, including the recalculating ones, so a fresh chart
    // or a reload used to burn straight through the rejection cut-off and stop the order layer
    // before the first live bar - which is exactly what a Sim replay did, ten refusals in one
    // call, all of them -8998.
    //
    // Nothing is lost by waiting: the book's state survives the recalculation, and the first
    // incremental call reconciles the account to it through the same path as any other day.
    // The seatbelt. 'Send Orders To Trade Service' = Yes means only "send"; whether that lands in
    // Sim1 or in a real account is decided by Trade > Trade Simulation Mode, which this study can
    // neither read nor set. So nothing in here can tell a replay from live money, and the status
    // box reads identically for both. One deliberate Input stands in for that missing distinction:
    // until it is set, Full auto computes and logs the whole book but sends nothing.
    const bool confirmed = sc.Input[IN_LIVE_CONFIRM].GetYesNo() != 0;
    const bool send = (mode == MODE_FULL) && confirmed;
    if (mode == MODE_FULL && !confirmed) {
        if (!S.confirmWarned) {
            S.confirmWarned = true;
            sc.AddMessageToLog(
                "Multi-Swing: FULL AUTO, but 'LIVE TRADING CONFIRMED' is No - nothing is being "
                "sent. The book runs and logs as usual so you can read it first. Set that Input to "
                "Yes when you mean orders to leave, and check Trade > Trade Simulation Mode before "
                "you do: this study cannot tell the simulator from a real account.", 1);
        }
        return;
    }
    if (S.legs.size() != S.states.size()) S.legs.assign(S.states.size(), AccountLeg());

    // Retracted. This used to warn that the chart's own simulation refuses ModifyOrder and
    // CancelOrder, so a bracket could be neither moved nor removed. That was wrong, and wrong for
    // the same reason everything else was: sc.SupportAttachedOrdersForTrading was being assigned
    // outside the SetDefaults block, so Sierra never had attached orders on and there were no
    // bracket children to modify. With the flag set where Sierra reads it, a replay into the
    // chart's own simulation logs "STOP MOVED for IBS<x_1 from 3703.00 to 3735.00 (order 162856)".
    // It steers brackets. The note about which mode touches which account is further down, said
    // once per load, and that is the only thing worth saying here.

    // A rejection means the account no longer holds what the book thinks, so every later order is
    // computed against a wrong position. Rather than repeat that for the rest of the run - the
    // first Sim Replay logged the same rejection thousands of times - trading stops and says so.
    if (S.orderFailures >= ORDER_FAILURE_LIMIT) return;
    FailureTally tally(S);

    // Take the presets the book has closed off the account, before anything is counted or sent.
    // Each goes out through its own bracket. A leg is only forgotten once it is genuinely gone -
    // wiping one whose exit failed is what left contracts belonging to nobody, uncloseable by any
    // route, on every run so far.
    const int RETIRE_TRIES = 3;
    int stillCovered = 0;          // held, closed by the book, but not yet sellable
    for (size_t k = 0; k < S.states.size(); ++k) {
        PresetState& st = S.states[k];
        AccountLeg&  lg = S.legs[k];
        if (lg.qtyOnAccount <= 0) continue;
        // Everything this preset has on the account that the book no longer wants: the trade it
        // has closed, and also the trade it closed and re-entered between two calls, which the
        // entry loop used to overwrite. Both are retired here and nowhere else.
        if (st.inPos != 0 && lg.entryDay == st.entryDay) continue;
        if (!send) { lg = AccountLeg(); continue; }

        // A leg that has already been given up on is left completely alone. Retrying it on every
        // call is what turned one unsteerable bracket into thousands of identical log lines a
        // second on a fast replay: the same two orders, the same refusal, the same cancel, for as
        // long as the run lasted. It changed nothing on the account and buried every other line.
        // Its contracts still count as held, and the report below has already said so once.
        if (lg.retireTries >= RETIRE_TRIES) { stillCovered += lg.qtyOnAccount; continue; }

        const RetireVerdict v = RetireLegNow(sc, S, lg, k, last, logLevel);
        if (v == RETIRE_ALREADY) {
            // The bracket has no live children, so these contracts are off the account. If they
            // somehow are not, the position read below still sees them and, with no order left
            // covering them, the market sell can legitimately take them.
            lg = AccountLeg();
            continue;
        }
        // Everything else is still held and still covered - by a working exit, or by a bracket
        // whose cancel has not taken yet. Offering any of it to a market sell earns the refusal
        // that latches the order layer, so it counts as wanted until it is genuinely gone.
        stillCovered += lg.qtyOnAccount;
        if (v == RETIRE_SENT || v == RETIRE_WORKING) { lg.retireTries = 0; continue; }

        // No reachable bracket, or a cancel that keeps not taking. Saying so once is the only
        // honest move: the study cannot close these, and latching silently would hide it.
        if (++lg.retireTries >= RETIRE_TRIES) {
            SCString m;
            m.Format("Multi-Swing: CANNOT CLOSE %s - %d contract(s) on the account whose bracket "
                     "will not be steered or cancelled after %d attempts. Nothing further will be "
                     "tried for them and they keep counting as held, so the book stays honest. "
                     "Close them by hand in Trade > Trade Orders and Positions. If every preset "
                     "says this, 'Send Orders To Trade Service' is No: the chart's own simulation "
                     "refuses ModifyOrder, so set that Input to Yes for Full auto.",
                     S.presets[k].id.GetChars(), lg.qtyOnAccount, RETIRE_TRIES);
            sc.AddMessageToLog(m, 1);
        }
    }

    // What the book wants to be holding, and what is actually held. Contracts whose exit is still
    // pending count as wanted: they are covered, so offering them to a market sell only earns a
    // refusal, and five of those latch the whole order layer.
    int want = stillCovered;
    for (size_t k = 0; k < S.states.size(); ++k) {
        const PresetState& st = S.states[k];
        if (st.inPos == 0) continue;
        // A preset whose previous trade is still coming off the account does not enter in this
        // call - the entry loop below holds it back - so what it is about to hold is not counted
        // yet. What it still holds is already in stillCovered.
        if (S.legs[k].qtyOnAccount > 0 && S.legs[k].entryDay != st.entryDay) continue;
        want += PresetQty(sc, S, k, cfg);
    }

    int account;
    if (send) {
        s_SCPositionData pos;
        sc.GetTradePosition(pos);
        account = (int)pos.PositionQuantity;
    } else {
        account = S.semiPosition;
    }

    // A position this run did not open cannot be managed by this run, and must not be traded
    // around. Reloading the presets or restarting Sierra rebuilds the book from bar zero and
    // throws away every order ID the study held, so the brackets left behind by the previous run
    // become unreachable: they keep working, their quantity keeps covering the position, and the
    // market sell that would square it comes back refused. That is how one chart went from ten
    // contracts to nineteen and then to twenty-seven across three runs, each one adding what the
    // last could no longer take off.
    //
    // No amount of code fixes it after the fact - the IDs are gone. So the study refuses to trade
    // at all until the account is flat, and says so instead of quietly making it worse.
    if (send && S.ordersPlaced == 0 && account > 0) {
        S.orphanHalt = true;
        if (!S.orphanWarned) {
            S.orphanWarned = true;
            SCString m;
            m.Format("Multi-Swing: NOT TRADING. The account holds %d contracts that this run did "
                     "not place - a reload or a restart loses the order IDs, so their stops and "
                     "targets cannot be reached or cancelled from here, and an exit sent around "
                     "them is refused. Trade > Flatten and Cancel All, then change the Input "
                     "'Reload Presets' to the other value. Nothing will be sent until the account "
                     "is flat.", account);
            sc.AddMessageToLog(m, 1);
        }
        return;
    }
    S.orphanHalt = false;

    // Square the position before adding to it. An account that is above the book is the one state
    // in which sending an entry is indefensible: it makes the gap worse, and if the exits are the
    // orders being refused - which is what a chart did, entries accepted and every SELL refused -
    // the position ratchets up session after session with nothing ever coming off. Ten became
    // nineteen that way. So the trim goes first, and while the account is still above the book
    // nothing new is offered.
    const TrimResult trim = TrimSurplus(sc, S, cfg, send, logLevel, tally, want, account);
    // A refused exit is the one state in which adding is indefensible: the way down is shut, so
    // anything sent now can only widen the gap. A trim already in flight means the position has
    // not settled and the numbers below would be guesses.
    if (trim == TRIM_REFUSED || trim == TRIM_WAITING) return;
    // A trim that went out is different, and blocking entries on it was too blunt: measured
    // offline, returning here cost 796 entries out of 9821, because a session that had anything
    // to sell sent nothing at all. The surplus belongs to presets the book has already closed and
    // the new entries belong to presets it has just opened - independent decisions. So the
    // entries go out, counted against where the trim is taking the position rather than where it
    // started, which is also the number the exposure cap should be measured against.
    if (trim == TRIM_SENT) account = send ? want : S.semiPosition;

    // The book's own gross cap is enforced on the ledger, and the ledger can legitimately sit
    // above the account for a call or two. An entry decided in that window asked Sierra for one
    // contract past sc.MaximumPositionAllowed and was refused - six times over eighteen years in
    // the offline order simulation. Those refusals are not an account problem, but the rejection
    // cut-off cannot tell them apart, and five in one call latch the whole order layer STOPPED. So
    // the study declines them itself instead of offering them, projecting the position forward
    // across the entries this call sends.
    int projected = account;
    const int accountCap = sc.MaximumPositionAllowed;

    for (size_t k = 0; k < S.states.size(); ++k) {
        PresetState& st = S.states[k];
        AccountLeg&  lg = S.legs[k];
        const int qty = PresetQty(sc, S, k, cfg);

        // ---- the book is flat here: nothing to send, and nothing left to record
        //
        // The pre-pass above has already dealt with this preset: its exit went out through its own
        // bracket, or Sierra's bracket had already taken it, or it was uncovered for the market
        // sell, or it is being retried and its quantity is counted in `want`. Whichever it was,
        // this loop must not wipe the leg - doing so was the third place where contracts stopped
        // belonging to anybody and became impossible to close.
        if (st.inPos == 0) continue;

        // ---- already on the account for this trade: Sierra works the bracket, but a trail or a
        // breakeven may have moved where the stop belongs since the entry went out, and an
        // attached order does not move by itself.
        if (lg.entryDay == st.entryDay && lg.qtyOnAccount > 0) {
            MoveAccountStop(sc, S, k, lg, st, send, logLevel);
            continue;
        }

        // ---- a new trade: one entry carrying its own stop and target
        //
        // A preset can close and re-enter in the same session, and this used to reach that case by
        // overwriting the leg - throwing away the record of contracts the previous trade may still
        // have on the account, with their bracket still working. Those contracts then belonged to
        // nobody: not to the book, not to any leg, and a market sell for them was refused because
        // they were covered.
        //
        // One leg cannot hold two trades, so the new one waits instead. The pre-pass above is
        // already working the old contracts off through their own bracket; the entry goes out on
        // the call after they are gone, which costs a call and keeps the account and the ledger
        // describing the same contracts.
        if (lg.qtyOnAccount > 0) continue;
        lg = AccountLeg();
        lg.entryDay = st.entryDay;
        if (qty <= 0) continue;

        if (!send) {
            S.semiPosition += qty;
            if (logLevel >= LOG_INFO) {
                const double tk = sc.TickSize > 0 ? sc.TickSize : 0.25;
                SCString m; m.Format("Multi-Swing SEMI: would BUY %d for %s, stop %.2f target %.2f",
                                     qty, S.presets[k].id.GetChars(),
                                     RealPrice(st.stop, last) ? ToTick(st.stop, tk, true) : 0.0,
                                     RealPrice(st.target, last) ? ToTick(st.target, tk, false) : 0.0);
                sc.AddMessageToLog(m, 0);
            }
            lg.qtyOnAccount = qty;
            lg.stopOnAccount = RealPrice(st.stop, last)
                             ? ToTick(st.stop, sc.TickSize > 0 ? sc.TickSize : 0.25, true) : 0.0;
            continue;
        }

        if (accountCap > 0 && projected + qty > accountCap) {
            if (logLevel >= LOG_DEBUG) {
                SCString m;
                m.Format("Multi-Swing: holding back %s - the account is at %d and %d is the "
                         "maximum position allowed. Usually a trim that has not filled yet.",
                         S.presets[k].id.GetChars(), projected, accountCap);
                sc.AddMessageToLog(m, 0);
            }
            lg = AccountLeg();
            continue;
        }

        s_SCNewOrder o;
        o.OrderQuantity = qty;
        o.OrderType     = SCT_ORDERTYPE_MARKET;
        o.TimeInForce   = SCT_TIF_DAY;
        const double tick = sc.TickSize > 0 ? sc.TickSize : 0.25;
        if (RealPrice(st.stop, last))   o.Stop1Price   = ToTick(st.stop, tick, true);
        if (RealPrice(st.target, last)) o.Target1Price = ToTick(st.target, tick, false);

        // Sierra's return code is the whole diagnosis of a refused order, so it is captured and
        // logged. An earlier version tested the call inline and printed a hardcoded 0, throwing
        // away the one number that says why - and then the failure cut-off silenced the rest.
        const int rc = (int)sc.BuyEntry(o);
        if (SkippedForRecalc(sc, S, rc, logLevel)) { lg = AccountLeg(); return; }
        if (rc > 0) {
            S.recalcSkips = 0;
            lg.qtyOnAccount = qty;
            lg.parentOrderId = (unsigned int)o.InternalOrderID;   // filled in by Sierra on success
            lg.stopOnAccount = o.Stop1Price;
            projected += qty;
            ++S.ordersPlaced;
            tally.anyOk = true;
            if (logLevel >= LOG_INFO) {
                SCString m; m.Format("Multi-Swing: BUY %d %s  stop %.2f  target %.2f",
                                     qty, S.presets[k].id.GetChars(), o.Stop1Price, o.Target1Price);
                sc.AddMessageToLog(m, 0);
            }
        } else {
            SCString m;
            m.Format("Multi-Swing ORDER REJECTED, Sierra returned %d: BUY %d %s at market, "
                     "stop %.2f target %.2f. (%d of %d before order placement stops.)%s",
                     rc, qty, S.presets[k].id.GetChars(), o.Stop1Price, o.Target1Price,
                     S.orderFailures + tally.fails + 1, (int)ORDER_FAILURE_LIMIT,
                     OrderRejectHint(rc));
            sc.AddMessageToLog(m, 1);
            // The cut-off was only tested once per study call, at the top of this function, while
            // the loop below it runs all forty-eight presets. A day on which every order is
            // refused therefore logged "6 of 5", "7 of 5" and so on, repeated the stopped notice
            // once per preset, and kept firing orders at an account that had refused every one.
            // Return here so the limit means what it says, and say it once.
            S.lastRejectCode = rc;
            if (S.orderFailures + ++tally.fails >= ORDER_FAILURE_LIMIT) {
                sc.AddMessageToLog(IsSkipCode(rc) ? STOPPED_NOTICE_SKIPPED : STOPPED_NOTICE, 1);
                return;
            }
        }
    }
}


// ------------------------------------------------------------------ on-chart status box
//
// ACSIL has no status-text call (sc.SetStudyStatusText does not exist), so the box is a stationary
// text drawing the study keeps up to date. It is the only place the mode is visible without opening
// the Message Log, and telling a paper run from a live one at a glance is worth a drawing.
static void DrawStatusBox(SCStudyInterfaceRef sc, const StudyState& S, const RunCfg& cfg,
                          bool enabled, int openPresets, int target, int position)
{
    if (sc.Input[IN_SHOW_STATUS].GetYesNo() == 0) {
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, DRAW_STATUS_LINE);
        return;
    }

    const int  mode   = sc.Input[IN_MODE].GetIndex();
    const bool sending = sc.Input[IN_SEND_LIVE].GetYesNo() != 0;
    // Once placement has stopped the box must say so: it was still reading "ORDERS LIVE" while
    // nothing was being sent, which is the one thing a status box must never get wrong.
    const bool stopped = S.orderFailures >= ORDER_FAILURE_LIMIT;
    const bool confirmed = sc.Input[IN_LIVE_CONFIRM].GetYesNo() != 0;
    // A halt stops new entries, so the box must say so before it says anything about the mode -
    // "FULL AUTO - ORDERS LIVE" while a loss limit is blocking every entry would be a lie.
    const bool halted = S.haltedDd || S.haltedDaily;
    const char* modeName = !enabled           ? "OFF (Trading Enabled = No)"
                         : S.orphanHalt       ? "NOT TRADING - flatten the account first"
                         : stopped            ? (IsSkipCode(S.lastRejectCode)
                                                  ? "STOPPED - Sierra SKIPPED every order; nothing was sent"
                                                  : "STOPPED - rejections, nothing is being sent")
                         : S.haltedDd         ? "HALTED - max drawdown stop, no new entries"
                         : S.haltedDaily      ? "HALTED - daily loss limit, no new entries"
                         // Full auto without the trade service cannot work a bracket, so the box
                         // says which switch to move rather than reading like a healthy run.
                         : mode == MODE_FULL && !confirmed
                                              ? "FULL AUTO - ARMED, not sending: Live Trading Confirmed = No"
                         : mode == MODE_FULL  ? (sending ? "FULL AUTO - ORDERS LIVE"
                                                         : "FULL AUTO - no exits: set Input 3 to Yes")
                         : mode == MODE_SEMI  ? "SEMI - logging intended orders"
                                              : "SIGNALS ONLY - paper";

    SCString pnl;
    pnl.Format("P&L       %+.0f pts today   %+.0f total   %.0f off peak",
               S.realizedToday, S.realizedTotal, S.equityPeak - S.realizedTotal);
    SCString warn;
    // Before SMA200 exists no preset can signal, so an empty book during the first two hundred
    // sessions is the study working, not the study broken. Said outright because the only other
    // way to know was to count the 'days' line yourself and know what it had to reach.
    const int WARMUP_SESSIONS = 200;
    const double onePreset = cfg.riskUnit * cfg.contractMult;
    if (cfg.maxGross > 0 && onePreset > cfg.maxGross)
        warn.Format("\nBLOCKED    Max Gross %.0f < one preset (%.0f) - no preset can ever enter",
                    cfg.maxGross, onePreset);
    else if ((int)S.daily.size() < WARMUP_SESSIONS)
        warn.Format("\nWARMING UP %d of %d sessions - no preset can signal until SMA200 exists",
                    (int)S.daily.size(), WARMUP_SESSIONS);
    if (S.orphanHalt) {
        SCString orp;
        orp.Format("\nFLATTEN    the account holds contracts this run did not place - "
                   "Trade > Flatten and Cancel All");
        warn += orp;
    }
    if (S.incompleteDays > 0) {
        SCString inc;
        inc.Format("\nWARNING   %d incomplete session%s - see the Message Log",
                   S.incompleteDays, S.incompleteDays == 1 ? "" : "s");
        warn += inc;
    }

    SCString text;
    text.Format("LUKACINO MULTI-SWING\n"
                "mode      %s\n"
                "presets   %d in %d families\n"
                "open      %d presets\n"
                "book      %d contracts   position %d\n"
                "days      %d   risk unit %.2f %s\n"
                "cap       %d %s contracts   (Max Gross %.0f MES)\n"
                "%s%s",
                modeName, (int)S.presets.size(), S.familyCount, openPresets,
                target, position, (int)S.daily.size(), cfg.riskUnit,
                sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? "ES" : "MES",
                cfg.contractMult > 0 ? (int)(cfg.maxGross / cfg.contractMult) : 0,
                sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? "ES" : "MES",
                cfg.maxGross,
                pnl.GetChars(), warn.GetChars());

    // Red whenever real orders can leave the study, so a live run never looks like a paper one.
    const COLORREF colour = stopped || halted                         ? RGB(255, 200, 0)
                          : (enabled && mode == MODE_FULL && sending && confirmed)
                                                                        ? RGB(255, 80, 80)
                          : !enabled                                   ? RGB(150, 150, 150)
                                                                       : RGB(0, 220, 120);
    const int corner = sc.Input[IN_STATUS_CORNER].GetIndex();
    s_UseTool t;
    t.Clear();
    t.ChartNumber   = sc.ChartNumber;
    t.DrawingType   = DRAWING_STATIONARY_TEXT;
    t.Region        = 0;
    t.AddMethod     = UTAM_ADD_OR_ADJUST;
    t.LineNumber    = DRAW_STATUS_LINE;
    t.UseRelativeVerticalValues = 1;                       // both coordinates are then percentages
    t.BeginDateTime = (corner == CORNER_TR || corner == CORNER_BR) ? 70 : 2;
    t.BeginValue    = (corner == CORNER_BL || corner == CORNER_BR) ?  2 : 97;
    t.Text          = text;
    t.Color         = colour;
    t.FontSize      = sc.Input[IN_STATUS_SIZE].GetInt();
    t.FontBold      = 1;
    t.MultiLineLabel = 1;
    t.TransparentLabelBackground = 0;
    t.SecondaryColor = RGB(0, 0, 0);
    sc.UseTool(t);
}

// ------------------------------------------------------------------ the study
SCSFExport scsf_LukacinoMultiSwing(SCStudyInterfaceRef sc)
{
    SCSubgraphRef SG_Close   = sc.Subgraph[0];
    SCSubgraphRef SG_ATR     = sc.Subgraph[1];
    SCSubgraphRef SG_WVWAP   = sc.Subgraph[2];
    SCSubgraphRef SG_MVWAP   = sc.Subgraph[3];
    SCSubgraphRef SG_DD      = sc.Subgraph[4];
    SCSubgraphRef SG_OpenPos = sc.Subgraph[5];
    SCSubgraphRef SG_Signal  = sc.Subgraph[6];
    SCSubgraphRef SG_RSI2    = sc.Subgraph[7];
    SCSubgraphRef SG_IBS     = sc.Subgraph[8];
    SCSubgraphRef SG_Connors = sc.Subgraph[9];
    SCSubgraphRef SG_WSD     = sc.Subgraph[10];
    SCSubgraphRef SG_DSD     = sc.Subgraph[11];
    SCSubgraphRef SG_Entries = sc.Subgraph[12];

    if (sc.SetDefaults) {
        sc.GraphName = "Lukacino Multi-Swing";
        sc.StudyDescription =
            "Multi-swing correction system. Rules are read from swing_presets.csv exported by "
            "swing_lab. Apply to an INTRADAY chart (1-min recommended) with the full Globex session: "
            "the study builds its own daily RTH bars and anchored weekly/monthly VWAP with "
            "volume-weighted sigma, which daily bars cannot provide.";
        sc.AutoLoop = 0;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.CalculationPrecedence = LOW_PREC_LEVEL;
        sc.MaintainAdditionalChartDataArrays = 1;

        SG_Close.Name = "Daily RTH Close";      SG_Close.DrawStyle = DRAWSTYLE_IGNORE;
        SG_ATR.Name = "ATR20 (daily ETH)";      SG_ATR.DrawStyle = DRAWSTYLE_IGNORE;
        SG_WVWAP.Name = "Weekly VWAP";          SG_WVWAP.DrawStyle = DRAWSTYLE_LINE;
        SG_WVWAP.PrimaryColor = RGB(0, 160, 255); SG_WVWAP.LineWidth = 2;
        SG_MVWAP.Name = "Monthly VWAP";         SG_MVWAP.DrawStyle = DRAWSTYLE_LINE;
        SG_MVWAP.PrimaryColor = RGB(255, 140, 0); SG_MVWAP.LineWidth = 2;
        SG_DD.Name = "Drawdown from 252d high %"; SG_DD.DrawStyle = DRAWSTYLE_IGNORE;
        SG_OpenPos.Name = "Open presets";       SG_OpenPos.DrawStyle = DRAWSTYLE_IGNORE;
        SG_Signal.Name = "Signal";              SG_Signal.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_Signal.PrimaryColor = RGB(0, 200, 0); SG_Signal.LineWidth = 3;
        SG_RSI2.Name = "RSI2 (daily)";          SG_RSI2.DrawStyle = DRAWSTYLE_IGNORE;
        SG_IBS.Name = "IBS (daily)";            SG_IBS.DrawStyle = DRAWSTYLE_IGNORE;
        SG_Connors.Name = "Connors RSI";        SG_Connors.DrawStyle = DRAWSTYLE_IGNORE;
        SG_WSD.Name = "Weekly VWAP sigma";      SG_WSD.DrawStyle = DRAWSTYLE_IGNORE;
        SG_DSD.Name = "Daily VWAP sigma";       SG_DSD.DrawStyle = DRAWSTYLE_IGNORE;
        SG_Entries.Name = "Presets entering";   SG_Entries.DrawStyle = DRAWSTYLE_IGNORE;

        sc.Input[IN_TRADING_ENABLED].Name = "Trading Enabled";
        sc.Input[IN_TRADING_ENABLED].SetYesNo(0);
        sc.Input[IN_MODE].Name = "Mode";
        sc.Input[IN_MODE].SetCustomInputStrings("Signals only;Semi-auto (alerts + prepared order);Full auto");
        sc.Input[IN_MODE].SetCustomInputIndex(MODE_SIGNALS);
        sc.Input[IN_SEND_LIVE].Name = "Send Orders To Trade Service (LIVE!)";
        sc.Input[IN_SEND_LIVE].SetYesNo(0);
        sc.Input[IN_DIRECTION].Name = "Direction Filter";
        sc.Input[IN_DIRECTION].SetCustomInputStrings("Long only;Both;Short only");
        sc.Input[IN_DIRECTION].SetCustomInputIndex(DIR_LONG_ONLY);
        sc.Input[IN_PRESET_FILE].Name = "Preset File (in Data Files Folder)";
        sc.Input[IN_PRESET_FILE].SetString("swing_presets.csv");
        sc.Input[IN_RELOAD].Name = "Reload Presets (toggle)";
        sc.Input[IN_RELOAD].SetYesNo(0);
        sc.Input[IN_RISK_UNIT].Name = "Risk Unit (contracts per preset)";
        sc.Input[IN_RISK_UNIT].SetFloat(1.0f);
        sc.Input[IN_INSTRUMENT].Name = "Instrument";
        sc.Input[IN_INSTRUMENT].SetCustomInputStrings("MES;ES");
        sc.Input[IN_INSTRUMENT].SetCustomInputIndex(0);
        sc.Input[IN_EVAL_AT].Name = "Entry Timing";
        sc.Input[IN_EVAL_AT].SetCustomInputStrings("Fill at RTH close (as research);Fill at next RTH open");
        sc.Input[IN_EVAL_AT].SetCustomInputIndex(EVAL_CLOSE);
        sc.Input[IN_JOURNAL_FILE].Name = "Journal CSV";
        sc.Input[IN_JOURNAL_FILE].SetString("swing_journal.csv");

        const char* famDefault[MAX_FAMILIES] = {
            "Family 1 (limit RSI pullback)", "Family 2 (below daily VWAP)", "Family 3 (below weekly VWAP)",
            "Family 4 (reclaim short MA)",   "Family 5 (drawdown + RSI)",   "Family 6 (IBS)",
            "Family 7 (Williams %R)",        "Family 8 (VWAP band)",        "Family 9 (N-day low close)",
            "Family 10 (RSI oversold)",      "Family 11 (drawdown + IBS)",  "Family 12 (Connors RSI)" };
        for (int k = 0; k < MAX_FAMILIES; ++k) {
            SCString n; n.Format("%s - Enabled", famDefault[k]);
            sc.Input[IN_FAM1_ON + 2 * k].Name = n;
            sc.Input[IN_FAM1_ON + 2 * k].SetYesNo(1);
            SCString w; w.Format("%s - Weight", famDefault[k]);
            sc.Input[IN_FAM1_W + 2 * k].Name = w;
            sc.Input[IN_FAM1_W + 2 * k].SetFloat(1.0f);
        }

        sc.Input[IN_MAX_GROSS].Name = "Max Gross Exposure (MES equivalents)";        sc.Input[IN_MAX_GROSS].SetInt(60);   // MES equivalents
        sc.Input[IN_MAX_CONCURRENT].Name = "Max Concurrent Presets"; sc.Input[IN_MAX_CONCURRENT].SetInt(48);
        sc.Input[IN_MAX_PER_FAMILY].Name = "Max Presets Per Family"; sc.Input[IN_MAX_PER_FAMILY].SetInt(4);
        sc.Input[IN_MAX_PER_ROLE].Name = "Max Presets Per Role";     sc.Input[IN_MAX_PER_ROLE].SetInt(12);
        sc.Input[IN_DAILY_LOSS].Name = "Daily Loss Limit USD (0 = off, stands down next session)";  sc.Input[IN_DAILY_LOSS].SetFloat(0);
        sc.Input[IN_MAX_DD_STOP].Name = "Max Drawdown Stop USD (0 = off, halts until reload)"; sc.Input[IN_MAX_DD_STOP].SetFloat(0);
        sc.Input[IN_SCALE_IN].Name = "(unused) Scale In By Correction Depth"; sc.Input[IN_SCALE_IN].SetYesNo(0);
        sc.Input[IN_SCALE_CAP].Name = "(unused) Scale In Cap";               sc.Input[IN_SCALE_CAP].SetFloat(2.0f);

        sc.Input[IN_ENTRY_TYPE].Name = "Entry Type Override";
        sc.Input[IN_ENTRY_TYPE].SetCustomInputStrings("As defined by preset;Force market on close;Force limit");
        sc.Input[IN_ENTRY_TYPE].SetCustomInputIndex(0);
        sc.Input[IN_LIMIT_OFFSET].Name = "Limit / Stop Offset (ticks)"; sc.Input[IN_LIMIT_OFFSET].SetInt(0);
        sc.Input[IN_ENTRY_EXPIRY].Name = "Entry Order Expiry (sessions)"; sc.Input[IN_ENTRY_EXPIRY].SetInt(1);
        sc.Input[IN_MAX_SLIPPAGE].Name = "(unused) Max Slippage ticks";      sc.Input[IN_MAX_SLIPPAGE].SetInt(8);
        sc.Input[IN_FLATTEN_EOD].Name = "(unused) Flatten At Session End";     sc.Input[IN_FLATTEN_EOD].SetYesNo(0);
        sc.Input[IN_TIME_STOP].Name = "Time Stop Override (sessions, 0 = use preset)"; sc.Input[IN_TIME_STOP].SetInt(0);

        sc.Input[IN_RTH_START].Name = "RTH Start (chart time zone)";  sc.Input[IN_RTH_START].SetTime(HMS_TIME(9, 30, 0));
        sc.Input[IN_RTH_END].Name = "RTH End (chart time zone)";      sc.Input[IN_RTH_END].SetTime(HMS_TIME(16, 0, 0));
        sc.Input[IN_LOG_LEVEL].Name = "Log Level";
        sc.Input[IN_LOG_LEVEL].SetCustomInputStrings("Errors;Info;Debug trace per preset");
        sc.Input[IN_LOG_LEVEL].SetCustomInputIndex(LOG_INFO);
        sc.Input[IN_DRAW_SIGNALS].Name = "Draw Signals On Chart";     sc.Input[IN_DRAW_SIGNALS].SetYesNo(1);

        // Global TP / SL / RRR override. Default OFF: each preset carries the exit model that was
        // validated for it, and forcing one exit on all 48 invalidates the research numbers.
        sc.Input[IN_EXIT_OVERRIDE].Name = "Exit Override (overrides ALL presets)";
        sc.Input[IN_EXIT_OVERRIDE].SetCustomInputStrings(
            "Use preset exits (validated);Override: ATR bracket;Override: fixed ticks");
        sc.Input[IN_EXIT_OVERRIDE].SetCustomInputIndex(XO_PRESET);
        sc.Input[IN_OV_SL_ATR].Name = "  Override SL (x ATR20)";     sc.Input[IN_OV_SL_ATR].SetFloat(1.0f);
        sc.Input[IN_OV_RRR].Name = "  Override RRR (TP = SL x RRR)"; sc.Input[IN_OV_RRR].SetFloat(2.0f);
        sc.Input[IN_OV_SL_TICKS].Name = "  Override SL (ticks)";     sc.Input[IN_OV_SL_TICKS].SetInt(80);
        sc.Input[IN_OV_TP_TICKS].Name = "  Override TP (ticks)";     sc.Input[IN_OV_TP_TICKS].SetInt(160);
        sc.Input[IN_OV_BE_R].Name = "  Override Breakeven (R, 0=off)"; sc.Input[IN_OV_BE_R].SetFloat(0);
        sc.Input[IN_OV_TRAIL_ATR].Name = "  Override Trailing (x ATR20, 0=off)";
        sc.Input[IN_OV_TRAIL_ATR].SetFloat(0);

        // On-chart display. The status box is on by default: the mode, and whether orders can
        // actually leave, should not be something you have to open a log to find out.
        sc.Input[IN_SHOW_STATUS].Name = "Show Status Box On Chart";
        sc.Input[IN_SHOW_STATUS].SetYesNo(1);
        sc.Input[IN_STATUS_CORNER].Name = "  Status Box Corner";
        sc.Input[IN_STATUS_CORNER].SetCustomInputStrings("Top left;Top right;Bottom left;Bottom right");
        sc.Input[IN_STATUS_CORNER].SetCustomInputIndex(CORNER_TL);
        sc.Input[IN_STATUS_SIZE].Name = "  Status Box Font Size";
        sc.Input[IN_STATUS_SIZE].SetInt(10);
        sc.Input[IN_LABEL_SIGNALS].Name = "Label Signals With Preset Count";
        sc.Input[IN_LABEL_SIGNALS].SetYesNo(0);
        sc.Input[IN_LABEL_DAYS].Name = "  Label Only The Last N Sessions (0 = all)";
        sc.Input[IN_LABEL_DAYS].SetInt(60);

        // Per-family exit override. Zero keeps the family on the exits its presets were validated
        // with, so the defaults change nothing.
        for (int k = 0; k < NUM_FAMILIES; ++k) {
            SCString a, b;
            a.Format("  Fam%d Override SL (x ATR20, 0 = preset)", k + 1);
            b.Format("  Fam%d Override RRR (0 = preset)", k + 1);
            sc.Input[IN_FAMX_SL  + 2 * k].Name = a; sc.Input[IN_FAMX_SL  + 2 * k].SetFloat(0);
            sc.Input[IN_FAMX_RRR + 2 * k].Name = b; sc.Input[IN_FAMX_RRR + 2 * k].SetFloat(0);
        }
        sc.Input[IN_FEATURE_CSV].Name = "Feature Dump CSV (blank = off)";
        sc.Input[IN_FEATURE_CSV].SetString("");

        sc.Input[IN_LIVE_CONFIRM].Name = "LIVE TRADING CONFIRMED (seatbelt)";
        sc.Input[IN_LIVE_CONFIRM].SetYesNo(0);

        // These six are study CONFIGURATION, not runtime state: Sierra reads them when the study
        // is configured, and assigning them later in the call - which is what this study did until
        // now - leaves them at Sierra's own defaults. SupportAttachedOrdersForTrading defaults to
        // FALSE, so every entry carrying Stop1Price and Target1Price was an order Sierra would not
        // accept, and it refused each one with a bare -1 that named no reason. That is the whole
        // story of the rejections: not the account, not auto trading, not the position cap, not
        // the prices. Set here, where they are read. The assignments further down stay as they
        // were, so a Sierra build that does re-read them per call still sees the same values.
        sc.AllowMultipleEntriesInSameDirection = 1;
        sc.SupportReversals                    = 0;
        sc.AllowOnlyOneTradePerBar             = 0;
        sc.SupportAttachedOrdersForTrading     = 1;
        sc.AllowEntryWithWorkingOrders         = 1;
        sc.CancelAllOrdersOnEntriesAndReversals = 0;

        // Same class of mistake, and the one that was actually blocking everything: the status box
        // printed "cap 0 ES contracts" on his chart with Max Gross at 600, so the runtime
        // assignment below never took and Sierra was holding ZERO. A cap of zero refuses every
        // entry, which is exactly what we spent days chasing.
        //
        // Set high here, where Sierra reads it, and let the study's own Max Gross Exposure be the
        // limit that matters - it is enforced in CapsAllow and in the projection in SyncOrders,
        // in MES equivalents, which is the unit the book is written in. Sierra's cap is a backstop
        // against a runaway, not the working limit, and the two can no longer disagree on units.
        sc.MaximumPositionAllowed = 1000;
        return;
    }

    // ---------------- persistent state ----------------
    StudyState* S = (StudyState*)sc.GetPersistentPointer(0);
    if (sc.LastCallToFunction) { if (S) { delete S; sc.SetPersistentPointer(0, nullptr); } return; }
    if (S == nullptr) { S = new StudyState(); sc.SetPersistentPointer(0, S); }

    const int logLevel = sc.Input[IN_LOG_LEVEL].GetIndex();

    S->featureCsv = sc.Input[IN_FEATURE_CSV].GetString()[0] == 0
                  ? SCString() : DataPath(sc, sc.Input[IN_FEATURE_CSV].GetString());

    // ---------------- trading flags ----------------
    // The book adds to and trims one net position, so successive entries in the same direction must
    // be allowed and reversals must not be: a SellExit here means "hold less", never "go short".
    // Whether these orders reach a broker or Sierra's simulator is the Trade menu's business, not
    // this study's - with Trade Simulation on, a Replay fills them against the replayed bars.
    sc.SendOrdersToTradeService       = sc.Input[IN_SEND_LIVE].GetYesNo() != 0;
    sc.AllowMultipleEntriesInSameDirection = 1;
    sc.SupportReversals               = 0;
    sc.AllowOnlyOneTradePerBar        = 0;
    sc.SupportAttachedOrdersForTrading = 1;      // the stop and target ride with each entry

    // Every preset after the first is submitted while the earlier presets' stops and targets are
    // still working orders, because that is what this book IS: many brackets riding one net
    // position. Sierra's default for this is false, which refuses exactly that - the first entry
    // of a session fills and every later one is rejected, leaving the account holding one contract
    // while the book believes it holds ten. Nothing in the study could have told you that apart
    // from the rejection code, and the count in the status box.
    sc.AllowEntryWithWorkingOrders    = 1;

    // The other half of the same requirement, and the more dangerous one. Sierra's own guidance is
    // to turn this ON when using attached orders, so that reducing a position cancels the attached
    // orders that no longer match it. That guidance is written for a system holding ONE bracket.
    // Here a trim closes one preset out of ten, and cancelling "all orders" would strip the stop
    // off the nine presets that are still open - the book would keep reporting them as protected
    // while nothing stood behind them. Set to false explicitly, never left to the default, because
    // the cost of the default changing under us is an unprotected book.
    sc.CancelAllOrdersOnEntriesAndReversals = 0;

    // Max Gross Exposure is counted in MES equivalents, so on ES one preset at risk unit 1 costs
    // ten of them. sc.MaximumPositionAllowed is counted in contracts of the instrument actually
    // being traded. Passing the MES-equivalent number straight through therefore made Sierra's
    // hard cap ten times looser than the book's own on ES - 600 contracts allowed where the book
    // would never ask for more than 60. Converted, so the two agree.
    const int grossInput = sc.Input[IN_MAX_GROSS].GetInt();
    const double mult    = sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? 10.0 : 1.0;
    // Re-asserted every call in case this Sierra build does read it here, but never below the
    // book's own worst case: a cap under what the book can legitimately hold would refuse entries
    // the study had already decided were inside every limit it knows about.
    const int wantCap = grossInput > 0
                      ? (int)std::max(1.0, std::floor(grossInput / mult))
                      : 1000;
    if (sc.MaximumPositionAllowed < wantCap) sc.MaximumPositionAllowed = wantCap;

    // This number is the hardest limit in the whole study and it was the only one nobody could
    // see. On ES the default Max Gross Exposure of 60 MES equivalents makes it SIX contracts, and
    // Sierra refuses everything past it with a bare -1 that names no reason - which reads exactly
    // like an account or auto-trading problem and sent us looking in the wrong place for an hour.
    // Logged once per load, so the cap is on the record next to the rejections it causes.
    if (!S->capLogged) {
        S->capLogged = true;
        SCString m;
        // sc.MaximumPositionAllowed reads back 0 no matter what was written to it - it is
        // write-only from a study's side. The previous version printed that readback and called a
        // zero "a study bug", which was alarming and wrong: orders were going through at the same
        // time it read 0. Only the book's own figure is reportable, so only that is reported.
        m.Format("Multi-Swing: the book may hold %d %s contract(s) (Max Gross Exposure %d MES "
                 "equivalents / %.0f). That is the limit that bites - raise Max Gross Exposure if "
                 "the book needs more.",
                 mult > 0 ? (int)std::floor(grossInput / mult) : 0,
                 sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? "ES" : "MES",
                 grossInput, mult);
        sc.AddMessageToLog(m, 0);
    }

    // ---------------- preset (re)load ----------------
    int reloadFlag = sc.Input[IN_RELOAD].GetYesNo();
    if ((!S->loaded && !S->loadAttempted) || reloadFlag != sc.GetPersistentInt(1)) {
        sc.SetPersistentInt(1, reloadFlag);
        SCString path = DataPath(sc, sc.Input[IN_PRESET_FILE].GetString());
        SCString err;
        bool ok = LoadPresets(sc, *S, path, err);
        S->loaded = ok;
        S->loadAttempted = true;
        S->loadError = err;
        S->lastProcessedIndex = -1;
        S->daily.clear();
        ResetDayAccumulators(*S);
        // A reload rebuilds the whole book from the first bar, so the order layer's view of the
        // account has to go with it: legs left behind would describe entries of a book that no
        // longer exists. It also clears the rejection cut-off, which is the only way to lift it
        // from the Inputs - otherwise a run that hit five rejections stays STOPPED until the
        // study is removed and added again, with no control on the dialog that says so.
        S->orderFailures = 0;
        S->legs.clear();
        S->trimSentQty = 0;
        S->trimWaited = 0;
        S->ordersPlaced = 0;
        S->orphanHalt = false;
        S->orphanWarned = false;
        S->chartSimWarned = false;
        S->bracketsSeen = S->bracketsEmpty = 0;
        S->modifyOk = S->modifyFail = 0;
        SCString m;
        if (ok) {
            int valid = 0; for (size_t i = 0; i < S->presets.size(); ++i) if (S->presets[i].valid) ++valid;
            m.Format("Multi-Swing %s: loaded %d presets (%d valid) in %d families from %s. %s",
                     STUDY_VERSION, (int)S->presets.size(), valid, S->familyCount,
                     path.GetChars(), err.GetChars());
            sc.AddMessageToLog(m, 0);
            for (size_t i = 0; i < S->presets.size(); ++i)
                if (!S->presets[i].valid) { SCString e; e.Format("  preset %s: %s",
                     S->presets[i].id.GetChars(), S->presets[i].parseError.GetChars()); sc.AddMessageToLog(e, 1); }
        } else {
            m.Format("Multi-Swing ERROR: %s  -- copy swing_presets.csv into the Data Files Folder, "
                     "then toggle the Input 'Reload Presets' to retry. This message is logged once.",
                     err.GetChars());
            sc.AddMessageToLog(m, 1);
            return;
        }
    }
    if (!S->loaded) return;

    // chart sanity: this must be an intraday chart, otherwise VWAP sigma is not computable
    if (sc.SecondsPerBar <= 0 || sc.SecondsPerBar > 3600) {
        if (sc.UpdateStartIndex == 0)
            sc.AddMessageToLog("Multi-Swing ERROR: apply to an INTRADAY chart of 60 minutes or less "
                               "(1-minute recommended). Weekly/monthly VWAP sigma needs intraday volume.", 1);
        return;
    }
    // Parity with the research engine was measured on 1-minute bars. Coarser bars still work, but
    // the daily OHLC and the volume-weighted VWAP sigma drift, so say so once per chart.
    if (sc.SecondsPerBar != 60 && sc.GetPersistentInt(2) == 0) {
        sc.SetPersistentInt(2, 1);
        SCString w; w.Format("Multi-Swing WARNING: chart bar size is %d seconds. The backtest parity "
                             "(32/48 presets identical) was verified on 1-MINUTE bars; on coarser bars "
                             "the VWAP sigma and daily range differ slightly. Use a 1 Min chart.",
                             sc.SecondsPerBar);
        sc.AddMessageToLog(w, 1);
    }

    // ---------------- main loop over intraday bars ----------------
    const int rthStart = sc.Input[IN_RTH_START].GetTime();
    const int rthEnd   = sc.Input[IN_RTH_END].GetTime();
    const SCString journal = DataPath(sc, sc.Input[IN_JOURNAL_FILE].GetString());
    const double tickSize = 0.25;                       // ES and MES share the same tick

    RunCfg cfg;
    cfg.riskUnit      = sc.Input[IN_RISK_UNIT].GetFloat();
    cfg.direction     = sc.Input[IN_DIRECTION].GetIndex();
    cfg.logLevel      = logLevel;
    cfg.exitOverride  = sc.Input[IN_EXIT_OVERRIDE].GetIndex();
    cfg.ovSlAtr       = sc.Input[IN_OV_SL_ATR].GetFloat();
    cfg.ovRrr         = sc.Input[IN_OV_RRR].GetFloat();
    cfg.ovSlPts       = sc.Input[IN_OV_SL_TICKS].GetInt() * tickSize;
    cfg.ovTpPts       = sc.Input[IN_OV_TP_TICKS].GetInt() * tickSize;
    cfg.ovBeR         = sc.Input[IN_OV_BE_R].GetFloat();
    cfg.ovTrailAtr    = sc.Input[IN_OV_TRAIL_ATR].GetFloat();
    for (int k = 0; k < NUM_FAMILIES; ++k) {
        cfg.famSlAtr[k] = sc.Input[IN_FAMX_SL  + 2 * k].GetFloat();
        cfg.famRrr[k]   = sc.Input[IN_FAMX_RRR + 2 * k].GetFloat();
    }
    cfg.dailyLossUsd  = sc.Input[IN_DAILY_LOSS].GetFloat();
    cfg.maxDdUsd      = sc.Input[IN_MAX_DD_STOP].GetFloat();
    cfg.rthEndSec     = rthEnd;
    cfg.globalTimeStop = sc.Input[IN_TIME_STOP].GetInt();
    cfg.entryOverride = sc.Input[IN_ENTRY_TYPE].GetIndex();
    cfg.limitOffsetPts = sc.Input[IN_LIMIT_OFFSET].GetInt() * tickSize;
    cfg.entryExpiry   = std::max(1, sc.Input[IN_ENTRY_EXPIRY].GetInt());
    cfg.entryNextOpen = sc.Input[IN_EVAL_AT].GetIndex() == EVAL_NEXT_OPEN;
    cfg.maxConcurrent = sc.Input[IN_MAX_CONCURRENT].GetInt();
    cfg.maxPerFamily  = sc.Input[IN_MAX_PER_FAMILY].GetInt();
    cfg.maxPerRole    = sc.Input[IN_MAX_PER_ROLE].GetInt();
    cfg.maxGross      = sc.Input[IN_MAX_GROSS].GetInt();
    cfg.contractMult  = sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? 10.0 : 1.0;   // ES = 10 x MES
    cfg.usdPerPoint   = 5.0 * cfg.contractMult;                                 // MES 5, ES 50
    const bool enabled = sc.Input[IN_TRADING_ENABLED].GetYesNo() != 0;

    // a full recalculation restarts the aggregation from scratch
    int start = sc.UpdateStartIndex;
    if (start == 0) { S->daily.clear(); ResetDayAccumulators(*S); S->lastProcessedIndex = -1; S->dayCounter = -1;
                      S->wKey = S->mKey = S->qKey = -1; S->lastCompletedMvwap = 0;
                      for (size_t k = 0; k < S->states.size(); ++k) S->states[k] = PresetState();
                      S->journalRows = 0; S->semiPosition = 0;
                      S->orderFailures = 0; S->legs.clear();
                      S->trimSentQty = 0; S->trimWaited = 0;
                      S->ordersPlaced = 0; S->orphanHalt = false; S->orphanWarned = false;
                      S->chartSimWarned = false;
                      S->bracketsSeen = S->bracketsEmpty = 0; S->modifyOk = S->modifyFail = 0;
                      S->incompleteDays = 0;
                      S->realizedToday = S->realizedTotal = S->equityPeak = 0;
                      S->realizedDay = -1; S->haltedDaily = S->haltedDd = false;
                      ResetJournal(DataPath(sc, sc.Input[IN_JOURNAL_FILE].GetString()));
                      ResetFeatureCsv(S->featureCsv); }

    static std::vector<Features> feats;                 // parallel to S->daily, rebuilt on demand
    if (start == 0) feats.clear();

    for (int i = start; i < sc.ArraySize; ++i) {
        // only completed bars take part in the aggregation
        if (i == sc.ArraySize - 1 && sc.GetBarHasClosedStatus(i) != BHCS_BAR_HAS_CLOSED) {
            // still carry the last known values forward so the plots do not gap
            if (!S->daily.empty()) {
                const DailyBar& lb = S->daily.back();
                SG_Close[i] = (float)lb.c; SG_WVWAP[i] = (float)lb.wvwap; SG_MVWAP[i] = (float)lb.mvwap;
            }
            break;
        }
        const SCDateTime bt = sc.BaseDateTimeIn[i];
        const int tod  = bt.GetTimeInSeconds();
        const int tDays = TradingDateDays(bt, rthEnd);
        SCDateTime tDate; tDate.SetDate(tDays);

        // ---- a completed RTH session closes the trading day
        if (S->sessionOpen && S->cur.v > 0 && S->cur.c > 0 && tDays != S->cur.date.GetDate())
            FinalizeDay(sc, *S, feats, cfg, journal, enabled);

        // ---- period rollovers, keyed on the trading date exactly like features.py
        int wk = WeekKey(tDate), mk = MonthKey(tDate), qk = QuarterKey(tDate);
        if (mk != S->mKey) {
            if (S->mKey >= 0 && S->mVol > 0) S->lastCompletedMvwap = S->mTpv / S->mVol;
            S->mKey = mk; S->mTpv = S->mTp2v = S->mVol = 0;
        }
        if (wk != S->wKey) { S->wKey = wk; S->wTpv = S->wTp2v = S->wVol = 0; }
        if (qk != S->qKey) { S->qKey = qk; S->qTpv = S->qVol = 0; }

        // ---- accumulate this bar
        const double hi = sc.BaseData[SC_HIGH][i], lo = sc.BaseData[SC_LOW][i];
        const double cl = sc.BaseData[SC_LAST][i],  op = sc.BaseData[SC_OPEN][i];
        const double vol = sc.BaseData[SC_VOLUME][i];
        const double tp = (hi + lo + cl) / 3.0;

        if (!S->sessionOpen) {
            S->cur = DailyBar();
            S->cur.date = tDate;
            S->cur.ethHigh = hi; S->cur.ethLow = lo;
            S->sessionOpen = true;
        } else {
            S->cur.ethHigh = std::max(S->cur.ethHigh, hi);
            S->cur.ethLow  = std::min(S->cur.ethLow, lo);
        }
        S->cur.date = tDate;
        S->cur.v += vol;
        S->curTpv += tp * vol; S->curTp2v += tp * tp * vol; S->curVol += vol;
        S->wTpv  += tp * vol;  S->wTp2v  += tp * tp * vol;  S->wVol  += vol;
        S->mTpv  += tp * vol;  S->mTp2v  += tp * tp * vol;  S->mVol  += vol;
        S->qTpv  += tp * vol;  S->qVol   += vol;

        const bool inRth = (tod >= rthStart && tod < rthEnd);
        if (inRth) {
            if (S->cur.o == 0) { S->cur.o = op; S->cur.h = hi; S->cur.l = lo; }
            else { S->cur.h = std::max(S->cur.h, hi); S->cur.l = std::min(S->cur.l, lo); }
            S->cur.c = cl;
            S->curLastRthTod = tod;
        }

        // ---- plots and diagnostics on the intraday chart
        if (!S->daily.empty()) {
            const DailyBar& lb = S->daily.back();
            int di = (int)S->daily.size() - 1;
            SG_Close[i] = (float)lb.c;
            SG_WVWAP[i] = (float)lb.wvwap;
            SG_MVWAP[i] = (float)lb.mvwap;
            if (di < (int)feats.size() && feats[di].ready) {
                const Features& ff = feats[di];
                SG_ATR[i] = (float)ff.atr20;
                SG_DD[i]  = (float)(ff.dd * 100.0);
                SG_RSI2[i] = (float)ff.rsi2;  SG_IBS[i] = (float)ff.ibs;
                SG_Connors[i] = (float)ff.connors;
                SG_WSD[i] = (float)ff.wvwapSd; SG_DSD[i] = (float)ff.dvwapSd;
            }
        }
        int openPresets = 0;
        for (size_t k = 0; k < S->states.size(); ++k) if (S->states[k].inPos != 0) ++openPresets;
        SG_OpenPos[i] = (float)openPresets;
        if (sc.Input[IN_DRAW_SIGNALS].GetYesNo() && !S->daily.empty()) {
            int justEntered = 0;
            for (size_t k = 0; k < S->states.size(); ++k)
                if (S->states[k].inPos != 0 && S->states[k].entryDay == S->dayCounter) ++justEntered;
            SG_Signal[i] = justEntered > 0 ? (float)lo : 0.0f;
            SG_Entries[i] = (float)justEntered;
        }
        S->lastProcessedIndex = i;
    }

    // ---------------- live guard: close a half-day session once its RTH end has passed ----------------
    // On a shortened session RTH ends early and no further bar arrives, so without this the day
    // would not close until the next session's first bar and its signal would be a session late.
    //
    // It must fire only at the live edge of the chart. sc.CurrentSystemDateTime is the wall clock,
    // which during a Replay of history sits years past every bar - so the original test (system
    // date later than the bar's) was true on every call, and the guard closed the same trading day
    // over and over. A Replay from 2018 produced about twice the trades from its start date on,
    // while the years before it, replayed as ordinary chart history, matched. Requiring the wall
    // clock to be on the very day being closed confines it to live trading, where it belongs.
    if (S->sessionOpen && S->cur.v > 0 && S->cur.c > 0 && sc.ArraySize > 0) {
        const SCDateTime now = sc.CurrentSystemDateTime;
        const int curDayDays = S->cur.date.GetDate();
        const bool sessionEndPassed = sc.IsReplayRunning() == 0 &&
                                      now.GetDate() == curDayDays &&
                                      now.GetTimeInSeconds() >= rthEnd;
        const SCDateTime lastBar = sc.BaseDateTimeIn[sc.ArraySize - 1];
        const bool noBarsSinceEnd = lastBar.GetTimeInSeconds() < rthEnd || lastBar.GetDate() < curDayDays;
        if (enabled && sessionEndPassed && noBarsSinceEnd) {
            if (logLevel >= LOG_INFO)
                sc.AddMessageToLog("Multi-Swing: session end passed with no further bars "
                                   "(shortened session) - closing the trading day now.", 0);
            FinalizeDay(sc, *S, feats, cfg, journal, enabled);
        }
    }

    // ---------------- bring the account to what the book holds ----------------
    // Once per study call, after every entry and exit for these bars has been booked, so a preset
    // entering and another exiting on the same day nets out instead of sending two orders.
    SyncOrders(sc, *S, cfg, sc.Input[IN_MODE].GetIndex(), enabled, logLevel,
               S->daily.empty() ? 0.0 : S->daily.back().c);

    // ---------------- signal labels ----------------
    // Walked backwards from the newest bar so "the last N sessions" is knowable: during the bar
    // loop the chart's final session is still ahead. A full replay would otherwise bury the chart
    // under thousands of drawings, which is why the cap is the default rather than the exception.
    if (sc.Input[IN_LABEL_SIGNALS].GetYesNo() && sc.ArraySize > 0) {
        const int keep = sc.Input[IN_LABEL_DAYS].GetInt();
        int drawn = 0;
        for (int i = sc.ArraySize - 1; i >= 0 && (keep <= 0 || drawn < keep); --i) {
            if (SG_Entries[i] <= 0) continue;
            s_UseTool t;
            t.Clear();
            t.ChartNumber = sc.ChartNumber;
            t.DrawingType = DRAWING_TEXT;
            t.Region      = 0;
            t.AddMethod   = UTAM_ADD_OR_ADJUST;
            t.LineNumber  = DRAW_LABEL_BASE + drawn;
            t.BeginIndex  = i;
            t.BeginValue  = sc.BaseData[SC_LOW][i] - 8 * sc.TickSize;
            SCString lab; lab.Format("%dx", (int)SG_Entries[i]);
            t.Text        = lab;
            t.Color       = RGB(0, 200, 0);
            t.FontSize    = 8;
            sc.UseTool(t);
            ++drawn;
        }
        S->labelsDrawn = drawn;
    } else if (S->labelsDrawn > 0) {
        for (int k = 0; k < S->labelsDrawn; ++k)
            sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, DRAW_LABEL_BASE + k);
        S->labelsDrawn = 0;
    }

    // ---------------- on-chart status box ----------------
    {
        int openPresets = 0;
        for (size_t k = 0; k < S->states.size(); ++k) if (S->states[k].inPos != 0) ++openPresets;
        s_SCPositionData pos; sc.GetTradePosition(pos);
        DrawStatusBox(sc, *S, cfg, enabled, openPresets, TargetContracts(sc, *S, cfg),
                      (int)pos.PositionQuantity);
    }

    // ---------------- status line: logged only when the open-position count changes ----------------
    if (logLevel >= LOG_INFO && !S->daily.empty()) {
        int openPresets = 0;
        for (size_t k = 0; k < S->states.size(); ++k) if (S->states[k].inPos != 0) ++openPresets;
        if (openPresets != sc.GetPersistentInt(2)) {
            sc.SetPersistentInt(2, openPresets);
            SCString st;
            st.Format("Multi-Swing | days %d | presets %d | open %d | mode %s | live orders %s",
                      (int)S->daily.size(), (int)S->presets.size(), openPresets,
                      sc.Input[IN_MODE].GetIndex() == MODE_FULL ? "FULL AUTO" :
                      sc.Input[IN_MODE].GetIndex() == MODE_SEMI ? "SEMI" : "SIGNALS",
                      sc.Input[IN_SEND_LIVE].GetYesNo() ? "ENABLED" : "off");
            sc.AddMessageToLog(st, 0);
        }
    }
    // Said once per LOAD, not once per full recalculation. A replay full-recalculates constantly
    // and every preset reload is another one, so the per-recalc version printed this paragraph
    // four times in thirty seconds of his log. The mode does not change between recalculations;
    // it changes when the Input changes, and that reloads.
    if (sc.UpdateStartIndex == 0 && enabled && !S->chartSimWarned) {
        S->chartSimWarned = true;
        const int mode = sc.Input[IN_MODE].GetIndex();
        if (mode == MODE_FULL && sc.Input[IN_SEND_LIVE].GetYesNo())
            sc.AddMessageToLog("Multi-Swing: FULL AUTO, orders ARE being sent to the trade service. "
                               "Trade > Trade Simulation Mode decides whether that is the simulator "
                               "or a live account.", 1);
        else if (mode == MODE_FULL)
            // This used to hedge, because the study cannot see where Sierra routed the order. A
            // chart settled it: with the flag off the orders are still placed and still fill, in
            // the chart's own simulation, against the chart's own bars - the position appears on
            // the chart and sc.GetTradePosition reports it. It is a real third mode, and the right
            // one for a Replay: deterministic fills, nothing routed anywhere, no account to
            // misconfigure. What it is NOT is the Sim account, so Trade Orders and Positions
            // stays empty and no broker ever sees it.
            sc.AddMessageToLog("Multi-Swing: FULL AUTO with 'Send Orders To Trade Service' = No. "
                               "Orders ARE placed and filled in the CHART'S OWN simulation - they "
                               "draw on the chart and count in the status box - but no trade "
                               "account is touched and Trade Orders and Positions stays empty. "
                               "This is the safe way to test a Replay. Set it to Yes only when you "
                               "want the orders on the Sim or live account.", 0);
    }
}
