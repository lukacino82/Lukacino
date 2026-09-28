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
#include <vector>
#include <string>
#include <fstream>
#include <cmath>
#include <algorithm>

SCDLLName("Lukacino Multi-Swing")

// ------------------------------------------------------------------ input indices (NEVER renumber)
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
    IN_COUNT
};

enum ModeKind    { MODE_SIGNALS = 0, MODE_SEMI, MODE_FULL };
enum DirKind     { DIR_LONG_ONLY = 0, DIR_BOTH, DIR_SHORT_ONLY };
enum EvalKind    { EVAL_CLOSE_MINUS_1 = 0, EVAL_CLOSE, EVAL_NEXT_OPEN };
enum LogLevel    { LOG_ERRORS = 0, LOG_INFO, LOG_DEBUG };

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
    bool   exitNextOpen = false;        // set by an "@open" signal exit, executed on the next session
    // day references are ABSOLUTE session numbers, never vector indices: the daily history is
    // trimmed to DAILY_HISTORY and every stored vector index would silently shift on each trim
    long   entryDay = -1;
    int    entryDayIdx = -1;            // vector index of the entry day, only for chart drawing
    int    heldDays = 0;
    int    pendingSide = 0;             // order armed at the signal close, to be filled next session
    double pendingLevel = 0;
    long   pendingDay = -1;
    long   signalDay = -1;
};

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
    SCDateTime sessionDate;
    DailyBar cur;
    double   curTpv = 0, curTp2v = 0, curVol = 0;                 // day VWAP accumulators
    double   wTpv = 0, wTp2v = 0, wVol = 0; int  wKey = -1;       // week
    double   mTpv = 0, mTp2v = 0, mVol = 0; int  mKey = -1;       // month
    double   qTpv = 0, qVol = 0;            int  qKey = -1;       // quarter
    double   lastCompletedMvwap = 0;

    long     dayCounter = -1;           // absolute number of completed trading days
    bool     loaded = false;
    SCString loadError;
    int      lastProcessedIndex = -1;
    int      journalRows = 0;
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
static void AppendJournal(const SCString& path, const SCString& row, StudyState& S)
{
    std::ofstream f(path.GetChars(), std::ios::app);
    if (!f.is_open()) return;
    if (S.journalRows == 0) {
        std::ifstream probe(path.GetChars(), std::ios::ate);
        if (!probe.is_open() || probe.tellg() == 0)
            f << "preset_id,family,signal_day,entry_day,exit_day,side,entry,exit,pnl_pts,mae,mfe,bars,reason\n";
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

// ------------------------------------------------------------------ process one completed daily bar
static void ProcessDay(SCStudyInterfaceRef sc, StudyState& S, const std::vector<Features>& F, int i,
                       long absDay, double riskUnit, int direction, const SCString& journalPath, int logLevel)
{
    const std::vector<DailyBar>& d = S.daily;
    const Features& f = F[i];
    if (!f.ready) return;
    const Features& pf = (i >= 1 && F[i - 1].ready) ? F[i - 1] : f;

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
        if (st.inPos == 0 && st.pendingSide != 0 && st.pendingDay == absDay - 1) {
            bool filled = false; double fill = 0;
            if (p.entry == EK_LIMIT) {
                if (d[i].ethLow <= st.pendingLevel) { filled = true; fill = std::min(st.pendingLevel, d[i].o); }
            } else if (p.entry == EK_STOP_ABOVE_HIGH) {
                if (d[i].ethHigh >= st.pendingLevel) { filled = true; fill = std::max(st.pendingLevel, d[i].o); }
            }
            st.pendingSide = 0;
            if (filled) {
                st.inPos = 1; st.entry = fill; st.entryDay = absDay; st.entryDayIdx = i; st.heldDays = 0;
                st.best = fill; st.worst = fill; st.trailOn = (p.trailActR <= 0);
                st.initialStop = p.slAtr > 0 ? p.slAtr * f.atr20 : 0;
                st.stop   = st.initialStop > 0 ? fill - st.initialStop : -1e18;
                st.target = p.tpAtr > 0 ? fill + p.tpAtr * f.atr20 : 1e18;
            }
        }

        // ---- 2. an "@open" exit armed yesterday is executed on today's open, before anything else
        if (st.inPos == 1 && st.exitNextOpen) {
            double px = d[i].o;
            double pnl = px - st.entry;
            SCString row;
            int sdIdx = i - (int)(absDay - st.signalDay), edIdx = i - (int)(absDay - st.entryDay);
            row.Format("%s,%s,%s,%s,%s,1,%.2f,%.2f,%.2f,%.2f,%.2f,%d,%s",
                       p.id.GetChars(), p.family.GetChars(),
                       sc.FormatDateTime(d[std::max(sdIdx, 0)].date).GetChars(),
                       sc.FormatDateTime(d[std::max(edIdx, 0)].date).GetChars(),
                       sc.FormatDateTime(d[i].date).GetChars(),
                       st.entry, px, pnl * riskUnit * weight,
                       st.worst - st.entry, st.best - st.entry,
                       (int)(absDay - st.entryDay) + 1, "signal");
            AppendJournal(journalPath, row, S);
            st = PresetState();
        }

        // ---- 3. manage an open position against today's range; stop first when both are touched
        if (st.inPos == 1) {
            // the protective level is derived from the excursion BEFORE this bar, so that today's
            // own high can never arm a trail or breakeven that today's low then triggers
            double eff = st.stop; int reason = 1;
            if (st.trailOn && p.trailAtr > 0) {
                double ts = st.best - p.trailAtr * f.atr20;
                if (ts > eff) { eff = ts; reason = 3; }
            }
            if (p.beR > 0 && st.initialStop > 0 && (st.best - st.entry) >= p.beR * st.initialStop) {
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
                if (p.timeStop > 0 && st.heldDays >= p.timeStop) { code = 4; px = d[i].c; }
                else if (ExitSignal(p, f)) {
                    if (p.xsigAtOpen) st.exitNextOpen = true;    // executed on the next open
                    else { code = 5; px = d[i].c; }
                }
                if (!st.trailOn && p.trailActR > 0 && st.initialStop > 0 &&
                    (st.best - st.entry) >= p.trailActR * st.initialStop) st.trailOn = true;
            }
            if (code != 0) {
                double pnl = px - st.entry;
                SCString row;
                int sdIdx = i - (int)(absDay - st.signalDay), edIdx = i - (int)(absDay - st.entryDay);
                SCDateTime sd = d[std::max(sdIdx, 0)].date, ed = d[std::max(edIdx, 0)].date, xd = d[i].date;
                row.Format("%s,%s,%s,%s,%s,1,%.2f,%.2f,%.2f,%.2f,%.2f,%d,%s",
                           p.id.GetChars(), p.family.GetChars(),
                           sc.FormatDateTime(sd).GetChars(), sc.FormatDateTime(ed).GetChars(),
                           sc.FormatDateTime(xd).GetChars(),
                           st.entry, px, pnl * riskUnit * weight,
                           st.worst - st.entry, st.best - st.entry,
                           (int)(absDay - st.entryDay) + 1, ReasonName(code));
                AppendJournal(journalPath, row, S);
                if (logLevel >= LOG_INFO) {
                    SCString m; m.Format("EXIT %s %s @ %.2f  (%.2f pts, %s)",
                                         p.id.GetChars(), sc.FormatDateTime(xd).GetChars(), px, pnl, ReasonName(code));
                    sc.AddMessageToLog(m, 0);
                }
                st = PresetState();
            }
        }

        // ---- 4. a new signal on today's close
        if (st.inPos == 0 && st.pendingSide == 0 && !st.exitNextOpen) {
            if (RegimeOk(p, f) && SetupSignal(p, d, i, f, pf)) {
                st.signalDay = absDay;
                if (p.entry == EK_CLOSE) {
                    st.inPos = 1; st.entry = f.c; st.entryDay = absDay; st.entryDayIdx = i; st.heldDays = 0;
                    st.best = f.c; st.worst = f.c; st.trailOn = (p.trailActR <= 0);
                    st.initialStop = p.slAtr > 0 ? p.slAtr * f.atr20 : 0;
                    st.stop   = st.initialStop > 0 ? f.c - st.initialStop : -1e18;
                    st.target = p.tpAtr > 0 ? f.c + p.tpAtr * f.atr20 : 1e18;
                } else {
                    st.pendingSide = 1;
                    st.pendingDay  = absDay;
                    st.pendingLevel = (p.entry == EK_LIMIT) ? f.c - p.entryOffsetAtr * f.atr20 : f.h;
                }
                if (logLevel >= LOG_INFO) {
                    SCString m; m.Format("SIGNAL %s %s  close %.2f  ATR %.2f  %s",
                                         p.id.GetChars(), sc.FormatDateTime(d[i].date).GetChars(),
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
static int WeekKey(int days)  { return (days + 3) / 7; }          // weeks start on Monday
static int MonthKey(const SCDateTime& d) { return d.GetYear() * 12 + d.GetMonth(); }
static int QuarterKey(const SCDateTime& d) { return d.GetYear() * 4 + (d.GetMonth() - 1) / 3; }

static void ResetDayAccumulators(StudyState& S)
{
    S.cur = DailyBar();
    S.curTpv = S.curTp2v = S.curVol = 0;
    S.sessionOpen = false;
}


// Close the in-progress trading day: finish the VWAP accumulators, append the daily bar,
// compute its features and run the signal engine on it. Called when the next trading day's
// first bar arrives, and - for live trading - once the session end has passed in real time,
// so a half-day session is not left open until the next Globex open.
static void FinalizeDay(SCStudyInterfaceRef sc, StudyState& S, std::vector<Features>& feats,
                        double riskUnit, int direction, const SCString& journal, int logLevel, bool enabled)
{
    DailyBar& b = S.cur;
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
    ++S.dayCounter;
    if (enabled) ProcessDay(sc, S, feats, di, S.dayCounter, riskUnit, direction, journal, logLevel);
    ResetDayAccumulators(S);
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
        sc.Input[IN_EVAL_AT].Name = "Evaluate Signals At";
        sc.Input[IN_EVAL_AT].SetCustomInputStrings("RTH close;RTH close -1 min;Next RTH open");
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

        sc.Input[IN_MAX_GROSS].Name = "Max Gross Contracts";        sc.Input[IN_MAX_GROSS].SetInt(60);
        sc.Input[IN_MAX_CONCURRENT].Name = "Max Concurrent Presets"; sc.Input[IN_MAX_CONCURRENT].SetInt(24);
        sc.Input[IN_MAX_PER_FAMILY].Name = "Max Presets Per Family"; sc.Input[IN_MAX_PER_FAMILY].SetInt(4);
        sc.Input[IN_MAX_PER_ROLE].Name = "Max Presets Per Role";     sc.Input[IN_MAX_PER_ROLE].SetInt(12);
        sc.Input[IN_DAILY_LOSS].Name = "Daily Loss Limit (USD, 0=off)"; sc.Input[IN_DAILY_LOSS].SetFloat(0);
        sc.Input[IN_MAX_DD_STOP].Name = "Max Drawdown Stop (USD, 0=off)"; sc.Input[IN_MAX_DD_STOP].SetFloat(0);
        sc.Input[IN_SCALE_IN].Name = "Scale In By Correction Depth"; sc.Input[IN_SCALE_IN].SetYesNo(0);
        sc.Input[IN_SCALE_CAP].Name = "Scale In Cap";               sc.Input[IN_SCALE_CAP].SetFloat(2.0f);

        sc.Input[IN_ENTRY_TYPE].Name = "Entry Order Type";
        sc.Input[IN_ENTRY_TYPE].SetCustomInputStrings("As defined by preset;Force market on close;Force limit");
        sc.Input[IN_ENTRY_TYPE].SetCustomInputIndex(0);
        sc.Input[IN_LIMIT_OFFSET].Name = "Extra Limit Offset (ticks)"; sc.Input[IN_LIMIT_OFFSET].SetInt(0);
        sc.Input[IN_ENTRY_EXPIRY].Name = "Entry Order Expiry (sessions)"; sc.Input[IN_ENTRY_EXPIRY].SetInt(1);
        sc.Input[IN_MAX_SLIPPAGE].Name = "Max Slippage (ticks)";      sc.Input[IN_MAX_SLIPPAGE].SetInt(8);
        sc.Input[IN_FLATTEN_EOD].Name = "Flatten At Session End";     sc.Input[IN_FLATTEN_EOD].SetYesNo(0);
        sc.Input[IN_TIME_STOP].Name = "Global Time Stop (sessions, 0=preset)"; sc.Input[IN_TIME_STOP].SetInt(0);

        sc.Input[IN_RTH_START].Name = "RTH Start (chart time zone)";  sc.Input[IN_RTH_START].SetTime(HMS_TIME(9, 30, 0));
        sc.Input[IN_RTH_END].Name = "RTH End (chart time zone)";      sc.Input[IN_RTH_END].SetTime(HMS_TIME(16, 0, 0));
        sc.Input[IN_LOG_LEVEL].Name = "Log Level";
        sc.Input[IN_LOG_LEVEL].SetCustomInputStrings("Errors;Info;Debug trace per preset");
        sc.Input[IN_LOG_LEVEL].SetCustomInputIndex(LOG_INFO);
        sc.Input[IN_DRAW_SIGNALS].Name = "Draw Signals On Chart";     sc.Input[IN_DRAW_SIGNALS].SetYesNo(1);
        return;
    }

    // ---------------- persistent state ----------------
    StudyState* S = (StudyState*)sc.GetPersistentPointer(0);
    if (sc.LastCallToFunction) { if (S) { delete S; sc.SetPersistentPointer(0, nullptr); } return; }
    if (S == nullptr) { S = new StudyState(); sc.SetPersistentPointer(0, S); }

    const int logLevel = sc.Input[IN_LOG_LEVEL].GetIndex();

    // ---------------- preset (re)load ----------------
    int reloadFlag = sc.Input[IN_RELOAD].GetYesNo();
    if (!S->loaded || reloadFlag != sc.GetPersistentInt(1)) {
        sc.SetPersistentInt(1, reloadFlag);
        SCString path = DataPath(sc, sc.Input[IN_PRESET_FILE].GetString());
        SCString err;
        bool ok = LoadPresets(sc, *S, path, err);
        S->loaded = ok;
        S->loadError = err;
        S->lastProcessedIndex = -1;
        S->daily.clear();
        ResetDayAccumulators(*S);
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
            m.Format("Multi-Swing ERROR: %s", err.GetChars());
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

    // ---------------- main loop over intraday bars ----------------
    const int rthStart = sc.Input[IN_RTH_START].GetTime();
    const int rthEnd   = sc.Input[IN_RTH_END].GetTime();
    const double riskUnit = sc.Input[IN_RISK_UNIT].GetFloat();
    const int direction   = sc.Input[IN_DIRECTION].GetIndex();
    const SCString journal = DataPath(sc, sc.Input[IN_JOURNAL_FILE].GetString());
    const bool enabled = sc.Input[IN_TRADING_ENABLED].GetYesNo() != 0;

    // a full recalculation restarts the aggregation from scratch
    int start = sc.UpdateStartIndex;
    if (start == 0) { S->daily.clear(); ResetDayAccumulators(*S); S->lastProcessedIndex = -1; S->dayCounter = -1;
                      S->wKey = S->mKey = S->qKey = -1; S->lastCompletedMvwap = 0;
                      for (size_t k = 0; k < S->states.size(); ++k) S->states[k] = PresetState(); }

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
            FinalizeDay(sc, *S, feats, riskUnit, direction, journal, logLevel, enabled);

        // ---- period rollovers, keyed on the trading date exactly like features.py
        int wk = WeekKey(tDays), mk = MonthKey(tDate), qk = QuarterKey(tDate);
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
        }
        S->lastProcessedIndex = i;
    }

    // ---------------- live guard: close a half-day session once its RTH end has passed ----------------
    // In a historical recalculation this never fires, because it only looks at the very last bar.
    if (S->sessionOpen && S->cur.v > 0 && S->cur.c > 0 && sc.ArraySize > 0) {
        const SCDateTime now = sc.CurrentSystemDateTime;
        const int curDayDays = S->cur.date.GetDate();
        const bool sessionEndPassed = now.GetDate() > curDayDays ||
                                      (now.GetDate() == curDayDays && now.GetTimeInSeconds() >= rthEnd);
        const SCDateTime lastBar = sc.BaseDateTimeIn[sc.ArraySize - 1];
        const bool noBarsSinceEnd = lastBar.GetTimeInSeconds() < rthEnd || lastBar.GetDate() < curDayDays;
        if (enabled && sessionEndPassed && noBarsSinceEnd) {
            if (logLevel >= LOG_INFO)
                sc.AddMessageToLog("Multi-Swing: session end passed with no further bars "
                                   "(shortened session) - closing the trading day now.", 0);
            FinalizeDay(sc, *S, feats, riskUnit, direction, journal, logLevel, enabled);
        }
    }

    // ---------------- status line ----------------
    if (logLevel >= LOG_INFO && sc.UpdateStartIndex > 0 && !S->daily.empty()) {
        int openPresets = 0;
        for (size_t k = 0; k < S->states.size(); ++k) if (S->states[k].inPos != 0) ++openPresets;
        SCString st;
        st.Format("Multi-Swing | days %d | presets %d | open %d | mode %s | live orders %s",
                  (int)S->daily.size(), (int)S->presets.size(), openPresets,
                  sc.Input[IN_MODE].GetIndex() == MODE_FULL ? "FULL AUTO" :
                  sc.Input[IN_MODE].GetIndex() == MODE_SEMI ? "SEMI" : "SIGNALS",
                  sc.Input[IN_SEND_LIVE].GetYesNo() ? "ENABLED" : "off");
        sc.SetStudyStatusText(st);
    }
    // step 1 never sends orders; the guard stays until the order layer is implemented
    if (sc.Input[IN_MODE].GetIndex() == MODE_FULL && sc.Input[IN_SEND_LIVE].GetYesNo() && sc.UpdateStartIndex == 0)
        sc.AddMessageToLog("Multi-Swing: order placement is not implemented in this build "
                           "(step 1 = signals + journal only). No orders will be sent.", 1);
}
