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
    IN_COUNT = IN_FAMX_SL + 2 * NUM_FAMILIES
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
};

// Enough consecutive rejections to conclude the account is not doing what the study asks.
enum { ORDER_FAILURE_LIMIT = 5 };

// Sierra's own code for "this order was skipped because the chart was doing a full
// recalculation" (scconstants.h). Named here so a rejection can say what it means instead of
// printing a bare number, and because it is the one code that is the study's fault, not the
// account's - see the guard at the top of SyncOrders.
static const int SCT_SKIPPED_FULL_RECALC_CODE = -8998;

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
static const char* OrderRejectHint(int rc)
{
    if (rc == SCT_SKIPPED_FULL_RECALC_CODE)
        return "  Sierra skipped it because the chart was recalculating - this is a study bug, "
               "not an account problem; report it.";
    if (rc == -1)
        return "  -1 is Sierra's generic refusal and carries no reason of its own. Sierra logs the"
               " actual reason separately: look in Window > Message Log at lines WITHOUT the"
               " 'Study: Lukacino Multi-Swing' prefix at this same timestamp, and in"
               " Trade > Trade Activity Log. Usual causes: Trade Simulation Mode off with no"
               " connected trade account, auto trading not enabled, or no trade account selected"
               " for this chart.";
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
    int      trimSentQty = 0;           // an exit already on its way, so it is not sent twice
    int      trimSentAccount = -1;      // the position it was sent against
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
    if (sc.UpdateStartIndex == 0) {
        // Carries the bar count and whether a replay is running, because the one thing this line
        // cannot say on its own is whether the next call will be incremental. If a running replay
        // only ever produces these, with the bar count climbing and no order ever sent, then
        // Sierra is recalculating on every replay bar and the order layer cannot work that way.
        if (logLevel >= LOG_INFO && sc.ArraySize > 0) {
            SCString m;
            m.Format("Multi-Swing: full recalculation at bar %d, replay %s - no orders sent while "
                     "the chart rebuilds (Sierra refuses them, SCT_SKIPPED_FULL_RECALC). The "
                     "account is brought to what the book holds on the first incremental bar.",
                     (int)sc.ArraySize, sc.IsReplayRunning() ? "RUNNING" : "off");
            sc.AddMessageToLog(m, 0);
        }
        return;
    }

    const bool send = (mode == MODE_FULL);
    if (S.legs.size() != S.states.size()) S.legs.assign(S.states.size(), AccountLeg());

    // A rejection means the account no longer holds what the book thinks, so every later order is
    // computed against a wrong position. Rather than repeat that for the rest of the run - the
    // first Sim Replay logged the same rejection thousands of times - trading stops and says so.
    if (S.orderFailures >= ORDER_FAILURE_LIMIT) return;

    // An entry sent in this call is not filled yet, so the position read below still lags it. The
    // trim is skipped for one call rather than selling the entry straight back out.
    bool entrySent = false;

    for (size_t k = 0; k < S.states.size(); ++k) {
        PresetState& st = S.states[k];
        AccountLeg&  lg = S.legs[k];
        const int qty = PresetQty(sc, S, k, cfg);

        // ---- the book is flat here: stop counting this preset, and send nothing yet
        //
        // Sierra's bracket may already have taken these contracts off the account, and this loop
        // has no way to tell. Selling lg.qtyOnAccount blind would then come out of whatever else
        // the net position is carrying - another preset's contracts, still believed open and from
        // that moment silently unprotected. The surplus is trimmed once, below, against the
        // position Sierra actually reports.
        if (st.inPos == 0) {
            lg = AccountLeg();
            continue;
        }

        // ---- already on the account for this trade: Sierra works the bracket, but a trail or a
        // breakeven may have moved where the stop belongs since the entry went out, and an
        // attached order does not move by itself.
        if (lg.entryDay == st.entryDay && lg.qtyOnAccount > 0) {
            MoveAccountStop(sc, S, k, lg, st, send, logLevel);
            continue;
        }

        // ---- a new trade: one entry carrying its own stop and target
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
            entrySent = true;
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
        if (rc > 0) {
            lg.qtyOnAccount = qty;
            lg.parentOrderId = (unsigned int)o.InternalOrderID;   // filled in by Sierra on success
            lg.stopOnAccount = o.Stop1Price;
            entrySent = true;
            S.orderFailures = 0;
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
                     S.orderFailures + 1, (int)ORDER_FAILURE_LIMIT, OrderRejectHint(rc));
            sc.AddMessageToLog(m, 1);
            // The cut-off was only tested once per study call, at the top of this function, while
            // the loop below it runs all forty-eight presets. A day on which every order is
            // refused therefore logged "6 of 5", "7 of 5" and so on, repeated the stopped notice
            // once per preset, and kept firing orders at an account that had refused every one.
            // Break here so the limit means what it says, and say it once.
            if (++S.orderFailures >= ORDER_FAILURE_LIMIT) {
                if (S.orderFailures == ORDER_FAILURE_LIMIT)
                    sc.AddMessageToLog("Multi-Swing: ORDER PLACEMENT STOPPED after too many "
                                       "rejections. The account is not holding what the book "
                                       "thinks and nothing more will be sent. Flatten the position "
                                       "by hand, fix the trade account or Trade Simulation Mode, "
                                       "then toggle the Input 'Reload Presets' to start again.", 1);
                return;
            }
        }
    }

    // ---- bring the total back down to what the book wants
    //
    // Because Sierra works each bracket, it closes a stopped-out preset without telling the study,
    // which makes the reported position - not the ledger - the only honest record of what is held.
    // Everything the book closed for its own reasons (a signal exit, a time stop) is exactly the
    // difference between that position and what the book still wants, and it goes out as one order
    // instead of being guessed at preset by preset.
    int want = 0;
    for (size_t k = 0; k < S.states.size(); ++k)
        if (S.states[k].inPos != 0) want += PresetQty(sc, S, k, cfg);

    int account;
    if (send) {
        s_SCPositionData pos;
        sc.GetTradePosition(pos);
        account = (int)pos.PositionQuantity;
    } else {
        account = S.semiPosition;
    }

    // A market exit is not filled by the time the next study call runs, so the position still reads
    // high. Without this the same surplus would be sold again on every call until the fill landed.
    if (S.trimSentQty > 0) {
        if (account != S.trimSentAccount) {
            S.trimSentQty = 0;
            S.trimSentAccount = -1;
        } else {
            return;
        }
    }
    if (entrySent || account <= want) return;

    const int surplus = account - want;

    if (!send) {
        S.semiPosition -= surplus;
        if (logLevel >= LOG_INFO) {
            SCString m; m.Format("Multi-Swing SEMI: would SELL %d to hold %d contracts.",
                                 surplus, want);
            sc.AddMessageToLog(m, 0);
        }
        return;
    }

    s_SCNewOrder o;
    o.OrderQuantity = surplus;
    o.OrderType     = SCT_ORDERTYPE_MARKET;
    o.TimeInForce   = SCT_TIF_DAY;
    const int rc = (int)sc.SellExit(o);
    if (rc > 0) {
        S.trimSentQty     = surplus;
        S.trimSentAccount = account;
        S.orderFailures   = 0;
        if (logLevel >= LOG_INFO) {
            SCString m; m.Format("Multi-Swing: SELL %d, position %d -> %d (book wants %d).",
                                 surplus, account, want, want);
            sc.AddMessageToLog(m, 0);
        }
    } else {
        SCString m;
        m.Format("Multi-Swing ORDER REJECTED, Sierra returned %d: SELL %d to bring the position "
                 "from %d to %d. (%d of %d before order placement stops.)%s",
                 rc, surplus, account, want, S.orderFailures + 1, (int)ORDER_FAILURE_LIMIT,
                 OrderRejectHint(rc));
        sc.AddMessageToLog(m, 1);
        if (++S.orderFailures >= ORDER_FAILURE_LIMIT)
            sc.AddMessageToLog("Multi-Swing: ORDER PLACEMENT STOPPED after too many rejections. "
                               "The account is not holding what the book thinks and nothing more "
                               "will be sent. Flatten the position by hand, fix the trade account "
                               "or Trade Simulation Mode, then reload the study.", 1);
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
    // A halt stops new entries, so the box must say so before it says anything about the mode -
    // "FULL AUTO - ORDERS LIVE" while a loss limit is blocking every entry would be a lie.
    const bool halted = S.haltedDd || S.haltedDaily;
    const char* modeName = !enabled           ? "OFF (Trading Enabled = No)"
                         : stopped            ? "STOPPED - rejections, nothing is being sent"
                         : S.haltedDd         ? "HALTED - max drawdown stop, no new entries"
                         : S.haltedDaily      ? "HALTED - daily loss limit, no new entries"
                         : mode == MODE_FULL  ? (sending ? "FULL AUTO - ORDERS LIVE"
                                                          : "FULL AUTO - not reaching the account")
                         : mode == MODE_SEMI  ? "SEMI - logging intended orders"
                                              : "SIGNALS ONLY - paper";

    SCString pnl;
    pnl.Format("P&L       %+.0f pts today   %+.0f total   %.0f off peak",
               S.realizedToday, S.realizedTotal, S.equityPeak - S.realizedTotal);
    SCString warn;
    if (S.incompleteDays > 0)
        warn.Format("\nWARNING   %d incomplete session%s - see the Message Log",
                    S.incompleteDays, S.incompleteDays == 1 ? "" : "s");

    SCString text;
    text.Format("LUKACINO MULTI-SWING\n"
                "mode      %s\n"
                "presets   %d in %d families\n"
                "open      %d presets\n"
                "book      %d contracts   position %d\n"
                "days      %d   risk unit %.2f %s\n"
                "%s%s",
                modeName, (int)S.presets.size(), S.familyCount, openPresets,
                target, position, (int)S.daily.size(), cfg.riskUnit,
                sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? "ES" : "MES",
                pnl.GetChars(), warn.GetChars());

    // Red whenever real orders can leave the study, so a live run never looks like a paper one.
    const COLORREF colour = stopped || halted                         ? RGB(255, 200, 0)
                          : (enabled && mode == MODE_FULL && sending)  ? RGB(255, 80, 80)
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
        sc.Input[IN_SCALE_IN].Name = "Scale In By Correction Depth (step 3, not active yet)"; sc.Input[IN_SCALE_IN].SetYesNo(0);
        sc.Input[IN_SCALE_CAP].Name = "Scale In Cap (step 3, not active yet)";               sc.Input[IN_SCALE_CAP].SetFloat(2.0f);

        sc.Input[IN_ENTRY_TYPE].Name = "Entry Type Override";
        sc.Input[IN_ENTRY_TYPE].SetCustomInputStrings("As defined by preset;Force market on close;Force limit");
        sc.Input[IN_ENTRY_TYPE].SetCustomInputIndex(0);
        sc.Input[IN_LIMIT_OFFSET].Name = "Limit / Stop Offset (ticks)"; sc.Input[IN_LIMIT_OFFSET].SetInt(0);
        sc.Input[IN_ENTRY_EXPIRY].Name = "Entry Order Expiry (sessions)"; sc.Input[IN_ENTRY_EXPIRY].SetInt(1);
        sc.Input[IN_MAX_SLIPPAGE].Name = "Max Slippage ticks (step 3, not active yet)";      sc.Input[IN_MAX_SLIPPAGE].SetInt(8);
        sc.Input[IN_FLATTEN_EOD].Name = "Flatten At Session End (step 3, not active yet)";     sc.Input[IN_FLATTEN_EOD].SetYesNo(0);
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
    sc.MaximumPositionAllowed         = sc.Input[IN_MAX_GROSS].GetInt() > 0
                                      ? sc.Input[IN_MAX_GROSS].GetInt() : 1000;
    sc.SupportAttachedOrdersForTrading = 1;      // the stop and target ride with each entry

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
        S->trimSentAccount = -1;
        SCString m;
        if (ok) {
            int valid = 0; for (size_t i = 0; i < S->presets.size(); ++i) if (S->presets[i].valid) ++valid;
            m.Format("Multi-Swing: loaded %d presets (%d valid) in %d families from %s. %s",
                     (int)S->presets.size(), valid, S->familyCount, path.GetChars(), err.GetChars());
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
                      S->trimSentQty = 0; S->trimSentAccount = -1;
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
    // Said once per full recalculation, so it is obvious from the log which of the three the study
    // is actually doing - the difference between a paper run and a live account is one Input.
    if (sc.UpdateStartIndex == 0 && enabled) {
        const int mode = sc.Input[IN_MODE].GetIndex();
        if (mode == MODE_FULL && sc.Input[IN_SEND_LIVE].GetYesNo())
            sc.AddMessageToLog("Multi-Swing: FULL AUTO, orders ARE being sent to the trade service. "
                               "Trade > Trade Simulation Mode decides whether that is the simulator "
                               "or a live account.", 1);
        else if (mode == MODE_FULL)
            // Deliberately says only what is certain. With the flag off the orders do not reach
            // the trade account; whether Sierra still works them in the chart's own simulation is
            // its business, not something this study can assert, and claiming "nothing is sent"
            // would be a guess printed as fact.
            sc.AddMessageToLog("Multi-Swing: FULL AUTO, but 'Send Orders To Trade Service' is No, "
                               "so no order reaches the trade account and nothing appears in "
                               "Trade Orders and Positions. Turn it on to trade the book.", 0);
    }
}
