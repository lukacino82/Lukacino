// Offline parity harness: feeds real ES 1-minute bars through the study and dumps what its
// feature engine computed, so it can be diffed against swing_lab/features.py.
// Build:  g++ -O2 -std=c++17 -Itest_stub test_stub/harness.cpp Lukacino_MultiSwing.cpp -o /tmp/harness
#include "sierrachart.h"

// same guard the study uses: the Sierra headers define min/max as macros
#ifdef max
#undef max
#endif
#ifdef min
#undef min
#endif

#include <fstream>
#include <sstream>
#include <iostream>

SCSFExport scsf_LukacinoMultiSwing(SCStudyInterfaceRef sc);
// input indices duplicated here on purpose: the harness must use the same numbers a Sierra user
// sees, so a renumbering in the study shows up as a test failure instead of silently passing
enum { IN_TRADING_ENABLED = 0, IN_MODE, IN_SEND_LIVE, IN_DIRECTION, IN_PRESET_FILE, IN_RELOAD,
       IN_RISK_UNIT, IN_INSTRUMENT, IN_EVAL_AT, IN_JOURNAL_FILE,
       IN_MAX_GROSS = 34, IN_MAX_CONCURRENT, IN_MAX_PER_FAMILY, IN_MAX_PER_ROLE,
       IN_ENTRY_EXPIRY = 44, IN_TIME_STOP = 47, IN_LOG_LEVEL = 50,
       IN_EXIT_OVERRIDE = 52, IN_OV_SL_ATR = 53, IN_OV_RRR = 54,
       IN_DAILY_LOSS = 38, IN_MAX_DD_STOP = 39, IN_FAMX_SL = 65, IN_FAMX_RRR = 66 };

// the study keeps its daily bars inside a private struct; for the harness we re-read the
// subgraphs it publishes, which is exactly what a Sierra user can see on the chart
int main(int argc, char** argv)
{
    if (argc < 4) { std::cerr << "usage: harness <bars.csv> <presets.csv> <out.csv>\n"; return 2; }
    static SCStudyInterface sc;
    sc.SetDefaults = 1; scsf_LukacinoMultiSwing(sc); sc.SetDefaults = 0;
    sc.Input[IN_PRESET_FILE].SetString(argv[2]);
    sc.Input[IN_JOURNAL_FILE].SetString(argc > 4 ? argv[4] : "harness_journal.csv");
    sc.Input[IN_TRADING_ENABLED].SetYesNo(1);
    sc.Input[IN_LOG_LEVEL].SetCustomInputIndex(0);
    // the research book has no exposure caps, so the parity run must not apply any either
    sc.Input[IN_MAX_CONCURRENT].SetInt(0); sc.Input[IN_MAX_PER_FAMILY].SetInt(0);
    sc.Input[IN_MAX_PER_ROLE].SetInt(0);   sc.Input[IN_MAX_GROSS].SetInt(0);
    sc.Input[IN_ENTRY_EXPIRY].SetInt(1);   sc.Input[IN_RISK_UNIT].SetFloat(1.0f);
    // optional switches so the new risk caps and exit overrides can be exercised from the test
    if (const char* v = getenv("MAX_CONCURRENT")) sc.Input[IN_MAX_CONCURRENT].SetInt(atoi(v));
    if (const char* v = getenv("EXIT_OVERRIDE"))  sc.Input[IN_EXIT_OVERRIDE].SetCustomInputIndex(atoi(v));
    if (const char* v = getenv("OV_SL_ATR"))      sc.Input[IN_OV_SL_ATR].SetFloat((float)atof(v));
    if (const char* v = getenv("OV_RRR"))         sc.Input[IN_OV_RRR].SetFloat((float)atof(v));
    if (const char* v = getenv("TIME_STOP"))      sc.Input[IN_TIME_STOP].SetInt(atoi(v));
    // MODE=1 is semi-auto: nothing is sent, but the order layer runs and logs what it would do,
    // which is the only way to exercise it offline - the stub's BuyEntry always refuses.
    if (const char* v = getenv("MODE"))           sc.Input[IN_MODE].SetCustomInputIndex(atoi(v));
    if (const char* v = getenv("LOG_LEVEL"))      sc.Input[IN_LOG_LEVEL].SetCustomInputIndex(atoi(v));
    if (const char* v = getenv("DAILY_LOSS"))     sc.Input[IN_DAILY_LOSS].SetFloat((float)atof(v));
    if (const char* v = getenv("MAX_DD"))         sc.Input[IN_MAX_DD_STOP].SetFloat((float)atof(v));
    // FAM_SL / FAM_RRR take "family:value" pairs, 1-based, e.g. FAM_SL="1:2.0,3:1.5"
    for (int which = 0; which < 2; ++which) {
        const char* v = getenv(which == 0 ? "FAM_SL" : "FAM_RRR");
        if (!v) continue;
        const int base = which == 0 ? IN_FAMX_SL : IN_FAMX_RRR;
        std::stringstream ps(v); std::string tok;
        while (std::getline(ps, tok, ',')) {
            size_t colon = tok.find(':');
            if (colon == std::string::npos) continue;
            int fam = atoi(tok.substr(0, colon).c_str());
            if (fam < 1 || fam > 12) continue;
            sc.Input[base + 2 * (fam - 1)].SetFloat((float)atof(tok.substr(colon + 1).c_str()));
        }
    }
    sc.SecondsPerBar = 60;

    std::ifstream f(argv[1]);
    if (!f.is_open()) { std::cerr << "cannot open " << argv[1] << "\n"; return 2; }
    std::string line; std::getline(f, line);            // header: days,secs,o,h,l,c,v
    int n = 0;
    while (std::getline(f, line)) {
        std::stringstream ss(line); std::string t;
        int days, secs; double o, h, l, c, v;
        std::getline(ss, t, ','); days = atoi(t.c_str());
        std::getline(ss, t, ','); secs = atoi(t.c_str());
        std::getline(ss, t, ','); o = atof(t.c_str());
        std::getline(ss, t, ','); h = atof(t.c_str());
        std::getline(ss, t, ','); l = atof(t.c_str());
        std::getline(ss, t, ','); c = atof(t.c_str());
        std::getline(ss, t, ','); v = atof(t.c_str());
        // the bar file counts from the Unix epoch, SCDateTime from Sierra's
        sc.BaseDateTimeIn[n].days = days + SC_EPOCH_TO_UNIX_DAYS; sc.BaseDateTimeIn[n].secs = secs;
        sc.BaseData[SC_OPEN][n] = (float)o; sc.BaseData[SC_HIGH][n] = (float)h;
        sc.BaseData[SC_LOW][n] = (float)l;  sc.BaseData[SC_LAST][n] = (float)c;
        sc.BaseData[SC_VOLUME][n] = (float)v;
        ++n;
    }
    // One call with everything is how a chart recalculates; CHUNK=<bars> instead delivers the
    // history in slices, which is how Sierra actually calls a study as bars arrive and the only
    // way the order layer runs offline at all - it is invoked once per study call, so a single
    // call only ever sees the final state. It is also a parity test in its own right: incremental
    // and batch must produce the same ledger, and a session delivered short is exactly the class
    // of bug that does not show up in one batch call.
    const int chunk = getenv("CHUNK") ? atoi(getenv("CHUNK")) : 0;
    if (chunk <= 0) {
        sc.ArraySize = n;
        sc.UpdateStartIndex = 0;
        scsf_LukacinoMultiSwing(sc);
    } else {
        int done = 0;
        while (done < n) {
            const int end = (done + chunk < n) ? done + chunk : n;
            sc.ArraySize = end;
            sc.UpdateStartIndex = done;
            scsf_LukacinoMultiSwing(sc);
            done = end;
        }
    }

    // dump the per-bar published series; the Python side reduces them to one row per RTH day
    std::ofstream out(argv[3]);
    out << "days,secs,daily_close,atr20,wvwap,mvwap,dd_pct,open_presets,rsi2,ibs,connors,wsd,dsd\n";
    for (int i = 0; i < n; ++i)
        out << sc.BaseDateTimeIn[i].days - SC_EPOCH_TO_UNIX_DAYS << "," << sc.BaseDateTimeIn[i].secs << ","
            << sc.Subgraph[0][i] << "," << sc.Subgraph[1][i] << "," << sc.Subgraph[2][i] << ","
            << sc.Subgraph[3][i] << "," << sc.Subgraph[4][i] << "," << sc.Subgraph[5][i] << ","
            << sc.Subgraph[7][i] << "," << sc.Subgraph[8][i] << "," << sc.Subgraph[9][i] << ","
            << sc.Subgraph[10][i] << "," << sc.Subgraph[11][i] << "\n";
    std::cerr << "bars " << n << " done\n";
    return 0;
}
