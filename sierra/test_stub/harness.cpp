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
       IN_RISK_UNIT, IN_INSTRUMENT, IN_EVAL_AT, IN_JOURNAL_FILE, IN_RTH_START_H = 48, IN_LOG_LEVEL = 50 };

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
        sc.BaseDateTimeIn[n].days = days; sc.BaseDateTimeIn[n].secs = secs;
        sc.BaseData[SC_OPEN][n] = (float)o; sc.BaseData[SC_HIGH][n] = (float)h;
        sc.BaseData[SC_LOW][n] = (float)l;  sc.BaseData[SC_LAST][n] = (float)c;
        sc.BaseData[SC_VOLUME][n] = (float)v;
        ++n;
    }
    sc.ArraySize = n;
    sc.UpdateStartIndex = 0;
    scsf_LukacinoMultiSwing(sc);

    // dump the per-bar published series; the Python side reduces them to one row per RTH day
    std::ofstream out(argv[3]);
    out << "days,secs,daily_close,atr20,wvwap,mvwap,dd_pct,open_presets,rsi2,ibs,connors,wsd,dsd\n";
    for (int i = 0; i < n; ++i)
        out << sc.BaseDateTimeIn[i].days << "," << sc.BaseDateTimeIn[i].secs << ","
            << sc.Subgraph[0][i] << "," << sc.Subgraph[1][i] << "," << sc.Subgraph[2][i] << ","
            << sc.Subgraph[3][i] << "," << sc.Subgraph[4][i] << "," << sc.Subgraph[5][i] << ","
            << sc.Subgraph[7][i] << "," << sc.Subgraph[8][i] << "," << sc.Subgraph[9][i] << ","
            << sc.Subgraph[10][i] << "," << sc.Subgraph[11][i] << "\n";
    std::cerr << "bars " << n << " done\n";
    return 0;
}
