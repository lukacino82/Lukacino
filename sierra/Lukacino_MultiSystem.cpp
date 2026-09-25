// =====================================================================
//  Lukacino Multi-System  –  Sierra Chart ACSIL study (C++)
//
//  Pět swingových systémů na ES, každý se dá zapnout/vypnout a nastavit:
//    1 RSI(2)          RSI < práh (nad MA200) → long, výstup close > MA(5)
//    2 Lower Closes    N nižších close po sobě → long, výstup 1. vyšší close
//    3 VAL Swing       close pod VAL denního profilu → long, výstup close > POC
//    4 Capitulation    pokles s objemem > k × průměr → long (zkušební)
//    5 Absorption      pokles, ale delta > 0 → short N dní (zkušební)
//
//  Všechna rozhodnutí padají jednou denně v Decision Time (default 15:58),
//  „close“ = close posledního baru, který začal před Decision Time.
//  Studie si vede virtuální pozici každého systému a na účtu drží jejich
//  součet (Sierra má na symbolu jen jednu pozici). Příkaz = rozdíl mezi
//  cílovou a skutečnou pozicí. TP/SL systémů hlídá studie, Emergency Stop je
//  jediný skutečný GTC příkaz u brokera.
//
//  Návod a popis všech inputů: sierra/README_MultiSystem.md
// =====================================================================
#include <vector>
#include <map>
#include <cmath>
#include <cstdlib>
#include "sierrachart.h"

SCDLLName("Lukacino Multi-System")

namespace
{
    // vlastní min/max: sestavení v Sierře (MinGW) nemá makra min/max z windows.h
    template <class T> inline T LMax(T a, T b) { return a > b ? a : b; }
    template <class T> inline T LMin(T a, T b) { return a < b ? a : b; }

    enum { SYS_RSI = 0, SYS_LC, SYS_VAL, SYS_CAP, SYS_ABS, NSYS };
    const char* SYS_NAME[NSYS] = { "RSI(2)", "Lower Closes", "VAL Swing", "Capitulation", "Absorption" };

    enum { EXIT_SIGNAL = 0, EXIT_SIG_FIXED, EXIT_SIG_SL_RRR, EXIT_SIG_ATR_RRR, EXIT_TPSL_ONLY };
    enum { SIZE_FIXED = 0, SIZE_LEVERAGE };
    enum { OPP_BLOCK = 0, OPP_NET };
    enum { LC_EXIT_HIGHER = 0, LC_EXIT_MA, LC_EXIT_PRIOR_HIGH };
    enum { VAL_EXIT_POC = 0, VAL_EXIT_VAH, VAL_EXIT_FIXED };
    enum { CAP_EXIT_PRIOR_HIGH = 0, CAP_EXIT_HIGHER };
    enum { TREND_ANY = 0, TREND_ABOVE, TREND_BELOW };

    struct SysState
    {
        int   Active = 0;      // 1 = v pozici
        int   Dir = 0;         // +1 long, -1 short
        int   Qty = 0;
        int   EntryK = -1;     // index dne vstupu
        int   EntryBar = -1;
        int   LastExitK = -1;
        int   Live = 0;        // 1 = pozice je skutečně na účtu (otevřená na živém baru nebo převzatá)
        float Entry = 0, TP = 0, SL = 0, Ref = 0;   // Ref = POC / VAH dne vstupu (VAL swing)
        double Realized = 0;   // $ uzavřených obchodů
        int   Trades = 0, Wins = 0;
        int   Disabled = 0;    // chybné inputy
    };

    struct State
    {
        // denní historie (jeden záznam = jeden obchodní den s rozhodnutím)
        std::vector<float> C, H, L, V, D, POC, VAH, VAL;
        std::vector<int>   Date;
        // rozpracovaný den
        int   CurDate = 0, DayBars = 0, LastRthTime = 0;
        float DH = 0, DL = 0, DC = 0; double DV = 0, DD = 0;
        std::map<int, double> Prof;
        int   DecidedDate = 0;
        // RSI (Wilder)
        double AU = 0, AD = 0; int RsiInit = 0;
        // systémy a účet
        SysState S[NSYS];
        double Peak = 0;
        int   Paused = 0, PauseUntilK = -1;
        float EmergLevel = 0;
        int   LastIndex = -1;
        // příkazy
        int   StopID = 0, StopQty = 0; float StopPrice = 0;
        int   Pending = 0, PendingCalls = 0, PendingTarget = 0, StopCancelCalls = 0, LastErrTarget = 99999, LastErrActual = 99999;
        int   FirstLiveDone = 0, OrdersBlocked = 0;
        int   LoggedCfg = 0, LoggedDelta = 0, LoggedSize = 0, LoggedStopErr = 0;
        int   StopFailBar = -1, StopFailQty = 0; float StopFailPx = 0;
    };

    // --- pomocné výpočty nad denní historií (k = index dne) --------------
    double SMA(const std::vector<float>& x, int k, int n)
    {
        if (n <= 0 || k + 1 < n) return NAN;
        double s = 0; for (int i = k - n + 1; i <= k; i++) s += x[i];
        return s / n;
    }
    double ATRk(const State& st, int k, int n)   // průměr H-L předchozích n dní (bez dne k)
    {
        if (n <= 0 || k < n) return NAN;
        double s = 0; for (int i = k - n; i < k; i++) s += st.H[i] - st.L[i];
        return s / n;
    }
    double AvgPrev(const std::vector<float>& x, int k, int n)
    {
        if (n <= 0 || k < n) return NAN;
        double s = 0; for (int i = k - n; i < k; i++) s += x[i];
        return s / n;
    }
}

SCSFExport scsf_Lukacino_MultiSystem(SCStudyInterfaceRef sc)
{
    // ------------------------------------------------------------ inputs
    int n = 0;
    // 0 Hlavní
    SCInputRef In_Enabled     = sc.Input[n++];   // 0
    SCInputRef In_Mode        = sc.Input[n++];   // 1
    SCInputRef In_SendLive    = sc.Input[n++];   // 2
    SCInputRef In_DecTime     = sc.Input[n++];   // 3
    SCInputRef In_RthStart    = sc.Input[n++];   // 4
    SCInputRef In_RthEnd      = sc.Input[n++];   // 5
    SCInputRef In_Units       = sc.Input[n++];   // 6
    // 1 Riziko
    SCInputRef In_SizeMode    = sc.Input[n++];   // 7
    SCInputRef In_Account     = sc.Input[n++];   // 8
    SCInputRef In_MaxTotal    = sc.Input[n++];   // 9
    SCInputRef In_Opposite    = sc.Input[n++];   // 10
    SCInputRef In_DD1         = sc.Input[n++];   // 11
    SCInputRef In_DD1M        = sc.Input[n++];   // 12
    SCInputRef In_DD2         = sc.Input[n++];   // 13
    SCInputRef In_DD2M        = sc.Input[n++];   // 14
    SCInputRef In_Pause       = sc.Input[n++];   // 15
    SCInputRef In_Emerg       = sc.Input[n++];   // 16
    SCInputRef In_AtrLen      = sc.Input[n++];   // 17
    // 2 RSI(2)
    SCInputRef In_R_En = sc.Input[n++], In_R_Size = sc.Input[n++], In_R_Len = sc.Input[n++], In_R_Thr = sc.Input[n++],
               In_R_Trend = sc.Input[n++], In_R_ExitMA = sc.Input[n++];                                    // 18-23
    const int R_EXIT = n; n += 6;                                                                            // 24-29
    // 3 Lower Closes
    SCInputRef In_L_En = sc.Input[n++], In_L_Size = sc.Input[n++], In_L_N = sc.Input[n++], In_L_Rule = sc.Input[n++],
               In_L_ExitMA = sc.Input[n++], In_L_Trend = sc.Input[n++];                                      // 30-35
    const int L_EXIT = n; n += 6;                                                                            // 36-41
    // 4 VAL Swing
    SCInputRef In_V_En = sc.Input[n++], In_V_Size = sc.Input[n++], In_V_VA = sc.Input[n++], In_V_Depth = sc.Input[n++],
               In_V_Rule = sc.Input[n++], In_V_Fixed = sc.Input[n++], In_V_Trend = sc.Input[n++];            // 42-48
    const int V_EXIT = n; n += 6;                                                                            // 49-54
    SCInputRef In_V_Draw = sc.Input[n++];                                                                    // 55
    // 5 Capitulation
    SCInputRef In_C_En = sc.Input[n++], In_C_Size = sc.Input[n++], In_C_Mult = sc.Input[n++], In_C_Len = sc.Input[n++],
               In_C_Down = sc.Input[n++], In_C_Rule = sc.Input[n++];                                         // 56-61
    const int C_EXIT = n; n += 6;                                                                            // 62-67
    // 6 Absorption
    SCInputRef In_A_En = sc.Input[n++], In_A_Size = sc.Input[n++], In_A_Hold = sc.Input[n++], In_A_MinD = sc.Input[n++],
               In_A_Trend = sc.Input[n++], In_A_TrendMA = sc.Input[n++];                                     // 68-73
    const int A_EXIT = n; n += 6;                                                                            // 74-79
    // 7 Zobrazení
    SCInputRef In_Panel = sc.Input[n++], In_PanelPos = sc.Input[n++], In_Font = sc.Input[n++],
               In_AlertNo = sc.Input[n++], In_LogAll = sc.Input[n++];                                        // 80-84
    SCInputRef In_PauseLen = sc.Input[n++];                                                                  // 85

    const int EXIT_BASE[NSYS] = { R_EXIT, L_EXIT, V_EXIT, C_EXIT, A_EXIT };

    SCSubgraphRef SG_POC = sc.Subgraph[0], SG_VAH = sc.Subgraph[1], SG_VAL = sc.Subgraph[2];
    SCSubgraphRef SG_Long = sc.Subgraph[3], SG_Short = sc.Subgraph[4], SG_Exit = sc.Subgraph[5];
    SCSubgraphRef SG_Emerg = sc.Subgraph[6], SG_Net = sc.Subgraph[7];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Lukacino Multi-System";
        sc.StudyDescription = "5 swingovych systemu (RSI(2), Lower Closes, VAL Swing, Capitulation, Absorption) "
                              "s netovanim pozice, TP/SL/RRR, sizingem a Emergency Stopem.";
        sc.AutoLoop = 1; sc.GraphRegion = 0; sc.FreeDLL = 0;

        In_Enabled.Name = "Trading Enabled";                         In_Enabled.SetYesNo(1);
        In_Mode.Name = "Mode";                                       In_Mode.SetCustomInputStrings("Semi-auto (alerts);Full auto (orders)"); In_Mode.SetCustomInputIndex(0);
        In_SendLive.Name = "Send Orders To Trade Service (LIVE!, Full auto only)"; In_SendLive.SetYesNo(0);
        In_DecTime.Name = "Decision Time (daily close for all systems)"; In_DecTime.SetTime(HMS_TIME(15, 58, 0));
        In_RthStart.Name = "RTH Start";                              In_RthStart.SetTime(HMS_TIME(9, 30, 0));
        In_RthEnd.Name = "RTH End";                                  In_RthEnd.SetTime(HMS_TIME(16, 0, 0));
        In_Units.Name = "TP/SL Units (all systems)";                 In_Units.SetCustomInputStrings("Ticks;Points"); In_Units.SetCustomInputIndex(1);

        In_SizeMode.Name = "Sizing Mode";                            In_SizeMode.SetCustomInputStrings("Fixed contracts;Leverage (contract value / account)"); In_SizeMode.SetCustomInputIndex(0);
        In_Account.Name = "Account Size $ (Leverage + DD brakes)";   In_Account.SetFloat(50000); In_Account.SetFloatLimits(100, 1e9);
        In_MaxTotal.Name = "Max Total Contracts (net)";              In_MaxTotal.SetInt(10); In_MaxTotal.SetIntLimits(1, 1000);
        In_Opposite.Name = "Opposite Signals (long vs short systems)"; In_Opposite.SetCustomInputStrings("Block (skip opposite entry);Net (sum positions)"); In_Opposite.SetCustomInputIndex(0);
        In_DD1.Name = "DD Brake 1: drawdown % (0 = off)";            In_DD1.SetFloat(-20); In_DD1.SetFloatLimits(-100, 0);
        In_DD1M.Name = "DD Brake 1: size x";                         In_DD1M.SetFloat(0.5f); In_DD1M.SetFloatLimits(0, 1);
        In_DD2.Name = "DD Brake 2: drawdown % (0 = off)";            In_DD2.SetFloat(-30); In_DD2.SetFloatLimits(-100, 0);
        In_DD2M.Name = "DD Brake 2: size x";                         In_DD2M.SetFloat(0.25f); In_DD2M.SetFloatLimits(0, 1);
        In_Pause.Name = "Pause New Entries at DD % (0 = off)";       In_Pause.SetFloat(0); In_Pause.SetFloatLimits(-100, 0);
        In_Emerg.Name = "Emergency Stop net position (x ATR, 0 = off)"; In_Emerg.SetFloat(5.0f); In_Emerg.SetFloatLimits(0, 50);
        In_AtrLen.Name = "ATR Length (days)";                        In_AtrLen.SetInt(14); In_AtrLen.SetIntLimits(1, 200);

        auto exitBlock = [&](int base, int mode, float tp, float sl, float rrr, float atrm, int maxhold)
        {
            sc.Input[base].Name = "   Exit Mode";
            sc.Input[base].SetCustomInputStrings("Signal only;Signal + Fixed TP/SL;Signal + SL & RRR;Signal + ATR SL & RRR;TP/SL only (no signal exit)");
            sc.Input[base].SetCustomInputIndex(mode);
            sc.Input[base + 1].Name = "   TP (units, Fixed TP/SL)";        sc.Input[base + 1].SetFloat(tp);  sc.Input[base + 1].SetFloatLimits(0, 100000);
            sc.Input[base + 2].Name = "   SL (units, Fixed / SL & RRR)";   sc.Input[base + 2].SetFloat(sl);  sc.Input[base + 2].SetFloatLimits(0, 100000);
            sc.Input[base + 3].Name = "   RRR (TP = SL x RRR)";            sc.Input[base + 3].SetFloat(rrr); sc.Input[base + 3].SetFloatLimits(0, 100);
            sc.Input[base + 4].Name = "   ATR SL Multiplier";              sc.Input[base + 4].SetFloat(atrm); sc.Input[base + 4].SetFloatLimits(0, 50);
            sc.Input[base + 5].Name = "   Max Hold Days (0 = off)";        sc.Input[base + 5].SetInt(maxhold); sc.Input[base + 5].SetIntLimits(0, 1000);
        };

        In_R_En.Name = ">>> RSI(2) - Enabled";                       In_R_En.SetYesNo(1);
        In_R_Size.Name = "   Size (contracts or leverage)";          In_R_Size.SetFloat(1); In_R_Size.SetFloatLimits(0, 1000);
        In_R_Len.Name = "   RSI Length";                             In_R_Len.SetInt(2); In_R_Len.SetIntLimits(1, 100);
        In_R_Thr.Name = "   RSI Entry Below";                        In_R_Thr.SetFloat(10); In_R_Thr.SetFloatLimits(0, 100);
        In_R_Trend.Name = "   Trend Filter MA Length (0 = off)";     In_R_Trend.SetInt(200); In_R_Trend.SetIntLimits(0, 1000);
        In_R_ExitMA.Name = "   Exit: Close Above MA Length";         In_R_ExitMA.SetInt(5); In_R_ExitMA.SetIntLimits(1, 1000);
        exitBlock(R_EXIT, EXIT_SIGNAL, 40, 20, 2, 1.5f, 10);

        In_L_En.Name = ">>> Lower Closes - Enabled";                 In_L_En.SetYesNo(1);
        In_L_Size.Name = "   Size (contracts or leverage)";          In_L_Size.SetFloat(1); In_L_Size.SetFloatLimits(0, 1000);
        In_L_N.Name = "   Number of Lower Closes";                   In_L_N.SetInt(3); In_L_N.SetIntLimits(1, 20);
        In_L_Rule.Name = "   Exit Rule";                             In_L_Rule.SetCustomInputStrings("First higher close;Close > MA;Close > prior day high"); In_L_Rule.SetCustomInputIndex(0);
        In_L_ExitMA.Name = "   Exit MA Length (Exit Rule = Close > MA)"; In_L_ExitMA.SetInt(5); In_L_ExitMA.SetIntLimits(1, 1000);
        In_L_Trend.Name = "   Trend Filter MA Length (0 = off)";     In_L_Trend.SetInt(0); In_L_Trend.SetIntLimits(0, 1000);
        exitBlock(L_EXIT, EXIT_SIGNAL, 40, 20, 2, 1.5f, 10);

        In_V_En.Name = ">>> VAL Swing - Enabled";                    In_V_En.SetYesNo(1);
        In_V_Size.Name = "   Size (contracts or leverage)";          In_V_Size.SetFloat(1); In_V_Size.SetFloatLimits(0, 1000);
        In_V_VA.Name = "   Value Area %";                            In_V_VA.SetFloat(70); In_V_VA.SetFloatLimits(10, 99);
        In_V_Depth.Name = "   Min Depth Below VAL (units, 0 = off)"; In_V_Depth.SetFloat(0); In_V_Depth.SetFloatLimits(0, 100000);
        In_V_Rule.Name = "   Exit Rule";                             In_V_Rule.SetCustomInputStrings("Close > POC of entry day;Close > VAH of entry day;Fixed N days"); In_V_Rule.SetCustomInputIndex(0);
        In_V_Fixed.Name = "   Fixed Hold Days (Exit Rule = Fixed)";  In_V_Fixed.SetInt(3); In_V_Fixed.SetIntLimits(1, 1000);
        In_V_Trend.Name = "   Trend Filter MA Length (0 = off)";     In_V_Trend.SetInt(0); In_V_Trend.SetIntLimits(0, 1000);
        exitBlock(V_EXIT, EXIT_SIGNAL, 40, 20, 2, 1.5f, 10);
        In_V_Draw.Name = "   Draw POC / VAH / VAL";                  In_V_Draw.SetYesNo(1);

        In_C_En.Name = ">>> Capitulation - Enabled (experimental)";  In_C_En.SetYesNo(0);
        In_C_Size.Name = "   Size (contracts or leverage)";          In_C_Size.SetFloat(1); In_C_Size.SetFloatLimits(0, 1000);
        In_C_Mult.Name = "   Volume Multiple (x average)";           In_C_Mult.SetFloat(1.6f); In_C_Mult.SetFloatLimits(0.1f, 100);
        In_C_Len.Name = "   Volume Average Length (days)";           In_C_Len.SetInt(20); In_C_Len.SetIntLimits(1, 500);
        In_C_Down.Name = "   Require Down Day";                      In_C_Down.SetYesNo(1);
        In_C_Rule.Name = "   Exit Rule";                             In_C_Rule.SetCustomInputStrings("Close > prior day high;First higher close"); In_C_Rule.SetCustomInputIndex(0);
        exitBlock(C_EXIT, EXIT_SIGNAL, 40, 20, 2, 1.5f, 5);

        In_A_En.Name = ">>> Absorption Short - Enabled (experimental)"; In_A_En.SetYesNo(0);
        In_A_Size.Name = "   Size (contracts or leverage)";          In_A_Size.SetFloat(1); In_A_Size.SetFloatLimits(0, 1000);
        In_A_Hold.Name = "   Hold Days (signal exit)";               In_A_Hold.SetInt(1); In_A_Hold.SetIntLimits(1, 100);
        In_A_MinD.Name = "   Min Delta (contracts, 0 = off)";        In_A_MinD.SetFloat(0); In_A_MinD.SetFloatLimits(0, 1e9);
        In_A_Trend.Name = "   Trend Filter";                         In_A_Trend.SetCustomInputStrings("Any;Only above MA;Only below MA"); In_A_Trend.SetCustomInputIndex(0);
        In_A_TrendMA.Name = "   Trend Filter MA Length";             In_A_TrendMA.SetInt(200); In_A_TrendMA.SetIntLimits(1, 1000);
        exitBlock(A_EXIT, EXIT_SIGNAL, 40, 20, 2, 1.5f, 0);

        In_Panel.Name = "Show Info Panel";                           In_Panel.SetYesNo(1);
        In_PanelPos.Name = "Panel Position";                         In_PanelPos.SetCustomInputStrings("Top left;Top right;Bottom left;Bottom right"); In_PanelPos.SetCustomInputIndex(0);
        In_Font.Name = "Panel Font Size";                            In_Font.SetInt(10); In_Font.SetIntLimits(6, 30);
        In_AlertNo.Name = "Alert Number (Semi-auto)";                In_AlertNo.SetInt(1); In_AlertNo.SetIntLimits(1, 150);
        In_PauseLen.Name = "Pause Length (days, then DD peak resets)"; In_PauseLen.SetInt(20); In_PauseLen.SetIntLimits(1, 1000);
        In_LogAll.Name = "Log Detail";                               In_LogAll.SetCustomInputStrings("Signals only;Everything (incl. virtual trades)"); In_LogAll.SetCustomInputIndex(0);

        SG_POC.Name = "POC";  SG_POC.DrawStyle = DRAWSTYLE_DASH; SG_POC.PrimaryColor = RGB(255, 200, 0); SG_POC.DrawZeros = false;
        SG_VAH.Name = "VAH";  SG_VAH.DrawStyle = DRAWSTYLE_DASH; SG_VAH.PrimaryColor = RGB(0, 170, 0);   SG_VAH.DrawZeros = false;
        SG_VAL.Name = "VAL";  SG_VAL.DrawStyle = DRAWSTYLE_DASH; SG_VAL.PrimaryColor = RGB(220, 0, 0);   SG_VAL.DrawZeros = false;
        SG_Long.Name = "Long Entry";   SG_Long.DrawStyle = DRAWSTYLE_ARROW_UP;   SG_Long.PrimaryColor = RGB(0, 120, 255); SG_Long.LineWidth = 3; SG_Long.DrawZeros = false;
        SG_Short.Name = "Short Entry"; SG_Short.DrawStyle = DRAWSTYLE_ARROW_DOWN; SG_Short.PrimaryColor = RGB(255, 60, 60); SG_Short.LineWidth = 3; SG_Short.DrawZeros = false;
        SG_Exit.Name = "Exit";         SG_Exit.DrawStyle = DRAWSTYLE_POINT;      SG_Exit.PrimaryColor = RGB(200, 200, 200); SG_Exit.LineWidth = 6; SG_Exit.DrawZeros = false;
        SG_Emerg.Name = "Emergency Stop"; SG_Emerg.DrawStyle = DRAWSTYLE_LINE;   SG_Emerg.PrimaryColor = RGB(255, 0, 255); SG_Emerg.DrawZeros = false;
        SG_Net.Name = "Net Position (target)"; SG_Net.DrawStyle = DRAWSTYLE_HIDDEN; SG_Net.DrawZeros = true;

        sc.AllowMultipleEntriesInSameDirection = true;    // přidávání kontraktů do čisté pozice
        sc.SupportReversals = false;
        sc.SendOrdersToTradeService = false;
        sc.AllowOppositeEntryWithOpposingPositionOrOrders = true;   // Buy/SellOrder pro exit a stop proti pozici
        sc.SupportAttachedOrdersForTrading = false;
        sc.CancelAllOrdersOnEntriesAndReversals = false;  // nesmí zrušit Emergency Stop
        sc.AllowEntryWithWorkingOrders = true;            // Emergency Stop je working order
        sc.CancelAllWorkingOrdersOnExit = false;
        sc.AllowOnlyOneTradePerBar = false;
        sc.MaintainTradeStatisticsAndTradesData = true;
        sc.MaximumPositionAllowed = 10;
        return;
    }

    // ------------------------------------------------------------ stav
    State* st = (State*)sc.GetPersistentPointer(1);
    if (sc.LastCallToFunction)
    {
        if (st) { delete st; sc.SetPersistentPointer(1, NULL); }
        return;
    }
    if (!st) { st = new State; sc.SetPersistentPointer(1, st); }

    const int i = sc.Index;
    if (i == 0)
    {
        // přepočet: stav systémů od začátku (Live příznaky a ID příkazů zůstávají)
        const int stopID = st->StopID, stopQty = st->StopQty; const float stopPx = st->StopPrice;
        *st = State();
        st->StopID = stopID; st->StopQty = stopQty; st->StopPrice = stopPx;
    }

    const bool Enabled  = In_Enabled.GetYesNo() != 0;
    const bool FullAuto = In_Mode.GetIndex() == 1;
    sc.SendOrdersToTradeService = FullAuto && In_SendLive.GetYesNo() != 0;
    const int  MaxTotal = In_MaxTotal.GetInt();
    sc.MaximumPositionAllowed = MaxTotal;
    sc.AllowOppositeEntryWithOpposingPositionOrOrders = true;   // i pro už vložené studie (jinak Sierra ignoruje exit/stop)
    const int  tDec = In_DecTime.GetTime(), tStart = In_RthStart.GetTime(), tEnd = In_RthEnd.GetTime();
    const float Tick = sc.TickSize > 0 ? sc.TickSize : 0.25f;
    const float Unit = In_Units.GetIndex() == 0 ? Tick : 1.0f;
    const double PointValue = sc.TickSize > 0 ? sc.CurrencyValuePerTick / sc.TickSize : 50.0;
    // Realtime = zpracování nových dat (live nebo Replay), i když přijde víc barů najednou.
    const bool Realtime = !sc.IsFullRecalculation;
    const bool LiveBar = Realtime && i == sc.ArraySize - 1;
    const bool LogAll = In_LogAll.GetIndex() == 1;
    const int  AtrLen = In_AtrLen.GetInt();

    const bool SysOn[NSYS] = { In_R_En.GetYesNo() != 0, In_L_En.GetYesNo() != 0, In_V_En.GetYesNo() != 0,
                               In_C_En.GetYesNo() != 0, In_A_En.GetYesNo() != 0 };
    const float SysSize[NSYS] = { In_R_Size.GetFloat(), In_L_Size.GetFloat(), In_V_Size.GetFloat(),
                                  In_C_Size.GetFloat(), In_A_Size.GetFloat() };
    auto exMode = [&](int s) { return sc.Input[EXIT_BASE[s]].GetIndex(); };
    auto exTP   = [&](int s) { return sc.Input[EXIT_BASE[s] + 1].GetFloat() * Unit; };
    auto exSL   = [&](int s) { return sc.Input[EXIT_BASE[s] + 2].GetFloat() * Unit; };
    auto exRRR  = [&](int s) { return sc.Input[EXIT_BASE[s] + 3].GetFloat(); };
    auto exATR  = [&](int s) { return sc.Input[EXIT_BASE[s] + 4].GetFloat(); };
    auto exMax  = [&](int s) { return sc.Input[EXIT_BASE[s] + 5].GetInt(); };

    // ------------------------------------------------------------ kontrola inputů
    SCString GlobalErr;
    if (!(tStart < tDec && tDec <= tEnd)) GlobalErr = "Musi platit RTH Start < Decision Time <= RTH End.";
    for (int s = 0; s < NSYS; s++)
    {
        SCString err;
        const int m = exMode(s);
        if (SysSize[s] <= 0) err = "Size musi byt > 0.";
        else if (m == EXIT_SIG_FIXED && (exTP(s) < Tick || exSL(s) < Tick)) err = "Exit Mode Fixed TP/SL: TP i SL musi byt aspon 1 tick.";
        else if (m == EXIT_SIG_SL_RRR && (exSL(s) < Tick || exRRR(s) <= 0)) err = "Exit Mode SL & RRR: SL aspon 1 tick a RRR > 0.";
        else if (m == EXIT_SIG_ATR_RRR && (exATR(s) <= 0 || exRRR(s) <= 0)) err = "Exit Mode ATR SL & RRR: ATR multiplier a RRR > 0.";
        else if (m == EXIT_TPSL_ONLY && exMax(s) == 0 && exSL(s) < Tick && exTP(s) < Tick)
            err = "Exit Mode TP/SL only potrebuje TP nebo SL, nebo Max Hold Days > 0 (jinak by pozice nikdy neskoncila).";
        else if (m == EXIT_TPSL_ONLY && exMax(s) == 0) err = "Exit Mode TP/SL only: nastav Max Hold Days > 0 (pojistka proti nekonecne pozici).";
        st->S[s].Disabled = err.GetLength() > 0;
        if (SysOn[s] && err.GetLength() > 0 && !st->LoggedCfg && i == sc.ArraySize - 1)
        {
            SCString msg; msg.Format("Lukacino MS: system %s VYPNUT, chybne inputy: %s", SYS_NAME[s], err.GetChars());
            sc.AddMessageToLog(msg, 1);
        }
    }
    if (GlobalErr.GetLength() && !st->LoggedCfg && i == sc.ArraySize - 1)
    {
        SCString msg; msg.Format("Lukacino MS: obchodovani vypnuto: %s", GlobalErr.GetChars()); sc.AddMessageToLog(msg, 1);
    }
    if (i == sc.ArraySize - 1) st->LoggedCfg = 1;
    const bool ConfigOK = GlobalErr.GetLength() == 0;

    // ------------------------------------------------------------ pomocné funkce
    auto logMsg = [&](const SCString& m, bool important)
    {
        if (important || LogAll) sc.AddMessageToLog(m, 0);
    };
    auto netTarget = [&]()
    {
        int net = 0;
        for (int s = 0; s < NSYS; s++) if (st->S[s].Active && st->S[s].Live) net += st->S[s].Dir * st->S[s].Qty;
        return net;
    };
    auto netVirtual = [&]()
    {
        int net = 0;
        for (int s = 0; s < NSYS; s++) if (st->S[s].Active) net += st->S[s].Dir * st->S[s].Qty;
        return net;
    };
    auto openPnL = [&](float px)
    {
        double p = 0;
        for (int s = 0; s < NSYS; s++) if (st->S[s].Active) p += st->S[s].Dir * (px - st->S[s].Entry) * st->S[s].Qty * PointValue;
        return p;
    };
    auto realized = [&]() { double r = 0; for (int s = 0; s < NSYS; s++) r += st->S[s].Realized; return r; };
    auto closeSys = [&](int s, float px, const char* why, int kExit)
    {
        SysState& y = st->S[s];
        const double pnl = y.Dir * (px - y.Entry) * y.Qty * PointValue;
        y.Realized += pnl; y.Trades++; if (pnl > 0) y.Wins++;
        SCString m;
        m.Format("TRADE|%s|%d|%d|%.2f|%.2f|%d|%d|%s", SYS_NAME[s], y.EntryK >= 0 ? st->Date[y.EntryK] : 0,
                 kExit >= 0 ? st->Date[kExit] : sc.BaseDateTimeIn[i].GetDate(), y.Entry, px, y.Dir, y.Qty, why);
        logMsg(m, false);
        if (Realtime && y.Live)
        {
            SCString a; a.Format("Lukacino MS: %s EXIT (%s) %s %d @ %.2f", SYS_NAME[s], why, y.Dir > 0 ? "SELL" : "BUY", y.Qty, px);
            logMsg(a, true);
            if (!FullAuto) sc.SetAlert(In_AlertNo.GetInt(), a);
        }
        y.Active = 0; y.Live = 0; y.LastExitK = kExit >= 0 ? kExit : (int)st->C.size() - 1;
        SG_Exit[i] = px;
    };

    // ------------------------------------------------------------ zpracování uzavřeného baru i-1
    const int t = sc.BaseDateTimeIn[i].GetTimeInSeconds();
    const int date = sc.BaseDateTimeIn[i].GetDate();
    if (i != st->LastIndex && i > 0)
    {
        const int p = i - 1;
        const int pd = sc.BaseDateTimeIn[p].GetDate(), pt = sc.BaseDateTimeIn[p].GetTimeInSeconds();
        if (pd != st->CurDate)
        {
            st->CurDate = pd; st->DayBars = 0; st->Prof.clear(); st->DV = 0; st->DD = 0; st->LastRthTime = 0;
        }
        if (pt >= tStart && pt < tDec)
        {
            if (st->DayBars == 0) { st->DH = sc.High[p]; st->DL = sc.Low[p]; }
            st->DH = LMax(st->DH, sc.High[p]); st->DL = LMin(st->DL, sc.Low[p]); st->DC = sc.Close[p];
            st->DV += sc.Volume[p]; st->DD += sc.AskVolume[p] - sc.BidVolume[p];
            st->DayBars++; st->LastRthTime = pt;
            // profil: objem baru rovnoměrně na ticky mezi low a high (stejně jako v testu)
            const int a = (int)floor(sc.Low[p] / Tick + 1e-6), b = (int)ceil(sc.High[p] / Tick - 1e-6);
            const double v = sc.Volume[p] / (double)(b - a + 1);
            for (int k = a; k <= b; k++) st->Prof[k] += v;
        }
    }
    st->LastIndex = i;

    // ------------------------------------------------------------ denní rozhodnutí
    // Poslední bar před rozhodnutím musí začít nejvýš 15 min před Decision Time, jinak jde o zkrácenou
    // seanci (svátek) a den se přeskočí, stejně jako v testu.
    const bool decisionNow = t >= tDec && st->DecidedDate != date && st->CurDate == date && st->DayBars >= 20
                             && st->LastRthTime >= tDec - 15 * 60 && ConfigOK;
    if (decisionNow)
    {
        st->DecidedDate = date;
        // --- profil dne
        float poc = 0, vah = 0, val = 0;
        if (!st->Prof.empty())
        {
            const int lo = st->Prof.begin()->first, hi = st->Prof.rbegin()->first; const int nb = hi - lo + 1;
            std::vector<double> vp(nb, 0.0); double tot = 0;
            for (auto& kv : st->Prof) { vp[kv.first - lo] = kv.second; tot += kv.second; }
            int pc = 0; for (int k = 1; k < nb; k++) if (vp[k] > vp[pc]) pc = k;
            int a = pc, b = pc; double inc = vp[pc]; const double need = In_V_VA.GetFloat() / 100.0 * tot;
            while (inc < need)
            {
                const double up = b + 1 < nb ? vp[b + 1] : -1, dn = a > 0 ? vp[a - 1] : -1;
                if (up < 0 && dn < 0) break;
                if (up >= dn) { b++; inc += up; } else { a--; inc += dn; }
            }
            poc = (lo + pc) * Tick; vah = (lo + b) * Tick; val = (lo + a) * Tick;
        }
        st->C.push_back(st->DC); st->H.push_back(st->DH); st->L.push_back(st->DL); st->V.push_back((float)st->DV);
        st->D.push_back((float)st->DD); st->POC.push_back(poc); st->VAH.push_back(vah); st->VAL.push_back(val); st->Date.push_back(date);
        const int k = (int)st->C.size() - 1;
        const float c = st->C[k];
        const std::vector<float>& C = st->C;
        // RSI (Wilder, stejně jako pandas ewm(alpha=1/n, adjust=False))
        const int rl = In_R_Len.GetInt();
        if (k >= 1)
        {
            const double d = C[k] - C[k - 1], up = d > 0 ? d : 0, dn = d < 0 ? -d : 0;
            if (!st->RsiInit) { st->AU = up; st->AD = dn; st->RsiInit = 1; }
            else { st->AU += (up - st->AU) / rl; st->AD += (dn - st->AD) / rl; }
        }
        const double rsi = st->RsiInit ? 100.0 - 100.0 / (1.0 + st->AU / (st->AD > 0 ? st->AD : 1e-9)) : NAN;
        const double atr = ATRk(*st, k, AtrLen);

        // --- výstupy (signál, časový stop) otevřených systémů
        for (int s = 0; s < NSYS; s++)
        {
            SysState& y = st->S[s];
            if (!y.Active || y.EntryK >= k) continue;
            const int held = k - y.EntryK; const int m = exMode(s);
            bool sig = false;
            if (m != EXIT_TPSL_ONLY)
            {
                switch (s)
                {
                case SYS_RSI: { const double ma = SMA(C, k, In_R_ExitMA.GetInt()); sig = !std::isnan(ma) && c > ma; } break;
                case SYS_LC:
                    if (In_L_Rule.GetIndex() == LC_EXIT_HIGHER) sig = c > C[k - 1];
                    else if (In_L_Rule.GetIndex() == LC_EXIT_MA) { const double ma = SMA(C, k, In_L_ExitMA.GetInt()); sig = !std::isnan(ma) && c > ma; }
                    else sig = c > st->H[k - 1];
                    break;
                case SYS_VAL:
                    if (In_V_Rule.GetIndex() == VAL_EXIT_FIXED) sig = held >= In_V_Fixed.GetInt();
                    else sig = c > y.Ref;
                    break;
                case SYS_CAP: sig = In_C_Rule.GetIndex() == CAP_EXIT_PRIOR_HIGH ? c > st->H[k - 1] : c > C[k - 1]; break;
                case SYS_ABS: sig = held >= In_A_Hold.GetInt(); break;
                }
            }
            const bool timeUp = exMax(s) > 0 && held >= exMax(s);
            if (sig || timeUp) closeSys(s, c, sig ? "signal" : "max hold", k);
        }

        // --- účet: equity, drawdown, brzdy
        const double equity = In_Account.GetFloat() + realized() + openPnL(c);
        if (st->Peak <= 0) st->Peak = equity;
        st->Peak = LMax(st->Peak, equity);
        const double dd = st->Peak > 0 ? (equity / st->Peak - 1.0) * 100.0 : 0;
        double mult = 1.0;
        if (In_DD1.GetFloat() < 0 && dd <= In_DD1.GetFloat()) mult = In_DD1M.GetFloat();
        if (In_DD2.GetFloat() < 0 && dd <= In_DD2.GetFloat()) mult = In_DD2M.GetFloat();
        // Pauza: po dosažení DD se nové vstupy zastaví na Pause Length dní, pak se maximum equity
        // nastaví na aktuální hodnotu (jinak by bez obchodů equity nikdy nevzrostla a pauza by trvala navždy).
        if (st->Paused && k >= st->PauseUntilK) { st->Paused = 0; st->Peak = equity; }
        if (!st->Paused && In_Pause.GetFloat() < 0 && dd <= In_Pause.GetFloat())
        {
            st->Paused = 1; st->PauseUntilK = k + In_PauseLen.GetInt();
            if (Realtime) { SCString m; m.Format("Lukacino MS: PAUZA novych vstupu na %d dni (DD %.1f %%).", In_PauseLen.GetInt(), dd); sc.AddMessageToLog(m, 1); }
        }

        // --- vstupy
        if (Enabled && !st->Paused)
        {
            for (int s = 0; s < NSYS; s++)
            {
                SysState& y = st->S[s];
                if (!SysOn[s] || y.Disabled || y.Active || y.LastExitK == k) continue;
                bool sig = false; int dir = 1;
                switch (s)
                {
                case SYS_RSI:
                {
                    const int tl = In_R_Trend.GetInt(); const double ma = SMA(C, k, tl);
                    if (k < LMax(tl, rl) + 1 || k < In_R_ExitMA.GetInt()) break;
                    sig = rsi < In_R_Thr.GetFloat() && (tl == 0 || c > ma);
                } break;
                case SYS_LC:
                {
                    const int nn = In_L_N.GetInt(), tl = In_L_Trend.GetInt();
                    if (k < nn || (tl > 0 && k + 1 < tl)) break;
                    sig = true; for (int j = 0; j < nn; j++) if (!(C[k - j] < C[k - j - 1])) { sig = false; break; }
                    if (sig && tl > 0) sig = c > SMA(C, k, tl);
                } break;
                case SYS_VAL:
                {
                    const int tl = In_V_Trend.GetInt();
                    if (val <= 0 || (tl > 0 && k + 1 < tl)) break;
                    sig = c < val - In_V_Depth.GetFloat() * Unit && (tl == 0 || c > SMA(C, k, tl));
                } break;
                case SYS_CAP:
                {
                    const int vl = In_C_Len.GetInt(); if (k < vl) break;
                    const double av = AvgPrev(st->V, k, vl);
                    sig = st->V[k] > In_C_Mult.GetFloat() * av && (!In_C_Down.GetYesNo() || (k >= 1 && c < C[k - 1]));
                } break;
                case SYS_ABS:
                {
                    dir = -1;
                    if (k < 1) break;
                    if (st->V[k] > 0 && st->D[k] == 0)
                    {
                        if (!st->LoggedDelta && Realtime) { sc.AddMessageToLog("Lukacino MS: Absorption potrebuje Bid/Ask Volume v grafu (delta = 0).", 1); st->LoggedDelta = 1; }
                    }
                    const int tr = In_A_Trend.GetIndex(), tl = In_A_TrendMA.GetInt();
                    if (tr != TREND_ANY && k + 1 < tl) break;
                    const double ma = tr != TREND_ANY ? SMA(C, k, tl) : 0;
                    sig = c < C[k - 1] && st->D[k] > LMax(0.0f, In_A_MinD.GetFloat())
                          && (tr == TREND_ANY || (tr == TREND_ABOVE ? c > ma : c < ma));
                } break;
                }
                if (!sig) continue;
                // opačný směr proti otevřeným systémům
                if (In_Opposite.GetIndex() == OPP_BLOCK)
                {
                    bool opp = false;
                    for (int o = 0; o < NSYS; o++) if (st->S[o].Active && st->S[o].Dir != dir) opp = true;
                    if (opp) { SCString m; m.Format("Lukacino MS: %s signal preskocen (Opposite Signals = Block).", SYS_NAME[s]); logMsg(m, Realtime); continue; }
                }
                // velikost
                // Brzda DD zmenší pozici nejvýš na 1 kontrakt (na 0 nikdy: bez obchodů by se equity
                // nemohla zotavit a systém by stál navždy).
                int qty = In_SizeMode.GetIndex() == SIZE_FIXED ? (int)floor(SysSize[s] + 1e-9)
                                                                : (int)floor(equity * SysSize[s] / (c * PointValue));
                if (qty >= 1 && mult < 1.0) qty = LMax(1, (int)floor(qty * mult + 1e-9));
                const int cur = netVirtual();
                const int room = dir > 0 ? MaxTotal - cur : MaxTotal + cur;   // kolik ještě smí přibýt v tomto směru
                qty = LMin(qty, LMax(0, room));
                if (qty < 1)
                {
                    SCString m;
                    if (room <= 0) m.Format("Lukacino MS: %s signal preskocen (strop Max Total Contracts = %d).", SYS_NAME[s], MaxTotal);
                    else m.Format("Lukacino MS: %s signal preskocen: velikost vychazi 0 kontraktu (Leverage %.2f x ucet $%.0f / hodnota kontraktu $%.0f). "
                                  "Zvys Size / Account Size, nebo obchoduj MES.", SYS_NAME[s], SysSize[s], equity, c * PointValue);
                    if (Realtime || !st->LoggedSize) { sc.AddMessageToLog(m, 1); st->LoggedSize = 1; }
                    continue;
                }
                // TP / SL
                const int mo = exMode(s); float slD = 0, tpD = 0;
                if (mo == EXIT_SIG_FIXED || mo == EXIT_TPSL_ONLY) { slD = exSL(s); tpD = exTP(s); }
                else if (mo == EXIT_SIG_SL_RRR) { slD = exSL(s); tpD = slD * exRRR(s); }
                else if (mo == EXIT_SIG_ATR_RRR)
                {
                    if (std::isnan(atr)) { SCString m; m.Format("Lukacino MS: %s signal preskocen (ATR jeste nema data).", SYS_NAME[s]); logMsg(m, Realtime); continue; }
                    slD = (float)(atr * exATR(s)); tpD = slD * exRRR(s);
                }
                y.Active = 1; y.Dir = dir; y.Qty = qty; y.EntryK = k; y.EntryBar = i; y.Entry = c;
                y.SL = slD > 0 ? c - dir * (float)sc.RoundToTickSize(slD, Tick) : 0;
                y.TP = tpD > 0 ? c + dir * (float)sc.RoundToTickSize(tpD, Tick) : 0;
                y.Ref = In_V_Rule.GetIndex() == VAL_EXIT_VAH ? vah : poc;
                y.Live = Realtime ? 1 : 0;
                if (dir > 0) SG_Long[i] = sc.Low[i] - 2 * Tick; else SG_Short[i] = sc.High[i] + 2 * Tick;
                SCString m;
                m.Format("Lukacino MS: %s ENTRY %s %d @ %.2f%s%s", SYS_NAME[s], dir > 0 ? "BUY" : "SELL", qty, c,
                         y.TP > 0 ? " TP set" : "", y.SL > 0 ? " SL set" : "");
                logMsg(m, Realtime);
                if (Realtime && !FullAuto) sc.SetAlert(In_AlertNo.GetInt(), m);
            }
        }
        // Emergency úroveň podle nové čisté pozice
        const int nv = netVirtual();
        if (nv != 0 && In_Emerg.GetFloat() > 0 && !std::isnan(atr)) st->EmergLevel = (float)sc.RoundToTickSize(c - (nv > 0 ? 1 : -1) * (float)(In_Emerg.GetFloat() * atr), Tick);
        else if (nv == 0) st->EmergLevel = 0;
    }

    // ------------------------------------------------------------ intradenní TP / SL / Emergency (virtuálně)
    for (int s = 0; s < NSYS; s++)
    {
        SysState& y = st->S[s];
        if (!y.Active || i <= y.EntryBar) continue;
        const float hiP = sc.High[i], loP = sc.Low[i], op = sc.Open[i];
        const bool slHit = y.SL > 0 && (y.Dir > 0 ? loP <= y.SL : hiP >= y.SL);
        const bool tpHit = y.TP > 0 && (y.Dir > 0 ? hiP >= y.TP : loP <= y.TP);
        if (slHit)
        {
            const float fill = y.Dir > 0 ? LMin(op, y.SL) : LMax(op, y.SL);
            closeSys(s, fill, "SL", -1);
        }
        else if (tpHit)
        {
            const float fill = y.Dir > 0 ? LMax(op, y.TP) : LMin(op, y.TP);
            closeSys(s, fill, "TP", -1);
        }
    }
    {
        const int nv = netVirtual();
        if (nv != 0 && st->EmergLevel > 0)
        {
            bool newer = false;   // pozice musí existovat před tímto barem
            for (int s = 0; s < NSYS; s++) if (st->S[s].Active && st->S[s].EntryBar >= i) newer = true;
            const bool hit = !newer && (nv > 0 ? sc.Low[i] <= st->EmergLevel : sc.High[i] >= st->EmergLevel);
            if (hit)
            {
                const float fill = nv > 0 ? LMin(sc.Open[i], st->EmergLevel) : LMax(sc.Open[i], st->EmergLevel);
                for (int s = 0; s < NSYS; s++) if (st->S[s].Active) closeSys(s, fill, "EMERGENCY", -1);
                st->EmergLevel = 0;
                if (Realtime) { sc.AddMessageToLog("Lukacino MS: EMERGENCY STOP zasazen - vsechny systemy zavreny.", 1); if (!FullAuto) sc.SetAlert(In_AlertNo.GetInt(), "Lukacino MS: EMERGENCY STOP - zavri celou pozici!"); }
            }
        }
        if (netVirtual() == 0) st->EmergLevel = 0;
    }
    if (st->EmergLevel > 0) SG_Emerg[i] = st->EmergLevel;
    SG_Net[i] = (float)netVirtual();
    if (In_V_Draw.GetYesNo() && st->VAL.size() > 0 && st->VAL.back() > 0)
    {
        SG_POC[i] = st->POC.back(); SG_VAH[i] = st->VAH.back(); SG_VAL[i] = st->VAL.back();
    }

    // ------------------------------------------------------------ Full auto: skutečná pozice = cílová
    if (FullAuto && LiveBar && ConfigOK)
    {
        s_SCPositionData Pos; sc.GetTradePosition(Pos);
        const int actual = (int)Pos.PositionQuantity;

        // první živé volání po načtení grafu: převzít, nebo nechat virtuální
        if (!st->FirstLiveDone)
        {
            st->FirstLiveDone = 1;
            const int hist = netVirtual();
            if (actual == hist && actual != 0)
            {
                for (int s = 0; s < NSYS; s++) if (st->S[s].Active) st->S[s].Live = 1;
                sc.AddMessageToLog("Lukacino MS: otevrena pozice na uctu odpovida systemum - prevzata.", 0);
            }
            else if (actual != 0)
            {
                st->OrdersBlocked = 1;
                SCString m; m.Format("Lukacino MS: POZOR, pozice na uctu (%d) neodpovida systemum (%d). Prikazy pozastaveny - "
                                     "srovnej pozici rucne (Flatten) a prepocitej studii.", actual, hist);
                sc.AddMessageToLog(m, 1); sc.SetAlert(In_AlertNo.GetInt(), m);
            }
            // actual == 0 a historie má otevřené pozice: zůstanou jen virtuální (žádný pozdní vstup)
        }

        // Emergency Stop vyplněn u brokera
        if (st->StopID)
        {
            s_SCTradeOrder ord;
            if (sc.GetOrderByOrderID(st->StopID, ord) && ord.OrderStatusCode == SCT_OSC_FILLED)
            {
                for (int s = 0; s < NSYS; s++) if (st->S[s].Active) closeSys(s, (float)ord.AvgFillPrice, "EMERGENCY (broker)", -1);
                st->StopID = 0; st->EmergLevel = 0;
                sc.AddMessageToLog("Lukacino MS: Emergency Stop vyplnen u brokera - systemy vynulovany.", 1);
            }
            else if (sc.GetOrderByOrderID(st->StopID, ord) && (ord.OrderStatusCode == SCT_OSC_CANCELED || ord.OrderStatusCode == SCT_OSC_ERROR))
                st->StopID = 0;
        }

        // Emergency Stop pryč? Pokud ne, pošle zrušení (opakovaně po 50 voláních) a vrátí false.
        // Sierra odmítne exit, když working exit příkazy (stop) už kryjí celou pozici.
        auto stopGone = [&]() -> bool
        {
            if (!st->StopID) return true;
            s_SCTradeOrder ord;
            if (!sc.GetOrderByOrderID(st->StopID, ord) || ord.OrderStatusCode == SCT_OSC_CANCELED
                || ord.OrderStatusCode == SCT_OSC_ERROR || ord.OrderStatusCode == SCT_OSC_FILLED)
            { st->StopID = 0; st->StopCancelCalls = 0; return true; }
            if (st->StopCancelCalls++ % 50 == 0) sc.CancelOrder(st->StopID);
            return false;
        };

        const int target = netTarget();
        if (st->Pending)
        {
            st->PendingCalls++;
            if (actual == st->PendingTarget || st->PendingCalls > 50) st->Pending = 0;
        }
        // zmenšení pozice (exit) jen bez working Emergency Stopu; přidání do pozice hned
        const bool reducing = (actual > 0 && target < actual) || (actual < 0 && target > actual);
        if (!st->Pending && !st->OrdersBlocked && actual != target && (!reducing || stopGone()))
        {
            const int diff = target - actual;
            s_SCNewOrder o; o.OrderType = SCT_ORDERTYPE_MARKET; o.TimeInForce = SCT_TIF_GOOD_TILL_CANCELED; o.TextTag = "LukacinoMS";
            int res = 0, expect = actual;
            // zmenšení pozice přes SellOrder/BuyOrder (bez pravidel Exit funkcí, množství max. do nuly)
            if (actual > 0 && diff < 0)      { o.OrderQuantity = LMin(-diff, actual); res = (int)sc.SellOrder(o); expect = actual - o.OrderQuantity; }
            else if (actual < 0 && diff > 0) { o.OrderQuantity = LMin(diff, -actual); res = (int)sc.BuyOrder(o);  expect = actual + o.OrderQuantity; }
            else if (diff > 0)               { o.OrderQuantity = diff;  res = (int)sc.BuyEntry(o);  expect = actual + diff; }
            else                             { o.OrderQuantity = -diff; res = (int)sc.SellEntry(o); expect = actual + diff; }
            if (res > 0) { st->Pending = 1; st->PendingCalls = 0; st->PendingTarget = expect; st->LastErrTarget = 99999; }
            else
            {
                if (target != st->LastErrTarget || actual != st->LastErrActual)   // do logu jen jednou pro stejný stav
                {
                    SCString m; m.Format("Lukacino MS: prikaz NEODESLAN (%s), cil %d, ucet %d. Zkontroluj Auto Trading Enabled a Trade Service Log.",
                                         sc.GetTradingErrorTextMessage(res), target, actual);
                    sc.AddMessageToLog(m, 1); st->LastErrTarget = target; st->LastErrActual = actual;
                }
                st->Pending = 1; st->PendingCalls = 0; st->PendingTarget = expect;
            }
        }
        // Emergency Stop jako GTC příkaz na celou pozici
        if (!st->Pending && actual == target)
        {
            const bool want = actual != 0 && st->EmergLevel > 0 && In_Emerg.GetFloat() > 0;
            const float px = (float)sc.RoundToTickSize(st->EmergLevel, Tick);
            if (st->StopID && (!want || st->StopQty != abs(actual) || fabs(st->StopPrice - px) > Tick / 2))
                stopGone();                                   // zrušit; nový stop až po potvrzeném zrušení
            else if (!st->StopID && want
                     && (st->StopFailBar != i || st->StopFailQty != abs(actual) || fabs(st->StopFailPx - px) > Tick / 2))
            {
                s_SCNewOrder o; o.OrderType = SCT_ORDERTYPE_STOP; o.Price1 = px; o.OrderQuantity = abs(actual);
                o.TimeInForce = SCT_TIF_GOOD_TILL_CANCELED; o.TextTag = "LukacinoMS Emergency";
                const int res = (int)(actual > 0 ? sc.SellOrder(o) : sc.BuyOrder(o));
                if (res > 0) { st->StopID = o.InternalOrderID; st->StopQty = abs(actual); st->StopPrice = px; st->StopCancelCalls = 0; st->LoggedStopErr = 0; st->StopFailBar = -1; }
                else { st->StopFailBar = i; st->StopFailQty = abs(actual); st->StopFailPx = px; }   // opakovat až na dalším baru / při změně
                if (res <= 0 && !st->LoggedStopErr)
                {
                    SCString m; m.Format("Lukacino MS: Emergency Stop NEODESLAN (%s) @ %.2f. Zkontroluj Trade Service Log.", sc.GetTradingErrorTextMessage(res), px);
                    sc.AddMessageToLog(m, 1); st->LoggedStopErr = 1;
                }
            }
        }
    }

    // ------------------------------------------------------------ panel
    if (i == sc.ArraySize - 1)
    {
        const int LINE = 72641;
        if (!In_Panel.GetYesNo()) sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LINE);
        else
        {
            SCString txt, row;
            const float px = sc.Close[i];
            const double eq = In_Account.GetFloat() + realized() + openPnL(px);
            const double ddp = st->Peak > 0 ? (LMin(eq, st->Peak) / st->Peak - 1) * 100 : 0;
            const int k = (int)st->C.size() - 1;
            const double atr = k >= 0 ? ATRk(*st, k, AtrLen) : NAN;
            txt.Format("Lukacino Multi-System | %s%s | net %d (cil) | DD %.1f %% | ATR %.1f%s\n",
                       FullAuto ? "FULL AUTO" : "SEMI-AUTO", sc.SendOrdersToTradeService ? " LIVE" : "", netVirtual(), ddp,
                       std::isnan(atr) ? 0.0 : atr, st->Paused ? " | PAUZA (DD)" : "");
            for (int s = 0; s < NSYS; s++)
            {
                const SysState& y = st->S[s];
                SCString state;
                if (!SysOn[s]) state = "OFF";
                else if (y.Disabled) state = "CHYBA inputu";
                else if (y.Active) state.Format("%s %d, %d d, vstup %.2f%s", y.Dir > 0 ? "LONG" : "SHORT", y.Qty, k - y.EntryK, y.Entry, y.Live ? "" : " (virt.)");
                else state = "ceka";
                SCString info;
                if (k >= 1)
                {
                    if (s == SYS_RSI) info.Format("RSI %.1f", st->RsiInit ? 100.0 - 100.0 / (1.0 + st->AU / (st->AD > 0 ? st->AD : 1e-9)) : 0.0);
                    else if (s == SYS_LC) { int cnt = 0; for (int j = k; j >= 1 && st->C[j] < st->C[j - 1]; j--) cnt++; info.Format("serie %d/%d", cnt, In_L_N.GetInt()); }
                    else if (s == SYS_VAL) info.Format("close %.2f / VAL %.2f", st->C[k], st->VAL[k]);
                    else if (s == SYS_CAP) { const double av = AvgPrev(st->V, k, In_C_Len.GetInt()); info.Format("objem %.2fx", std::isnan(av) || av <= 0 ? 0.0 : st->V[k] / av); }
                    else info.Format("delta %.0f", st->D[k]);
                }
                row.Format("%-13s %-34s %-24s obch %d, win %d%%, P&L $%.0f\n", SYS_NAME[s], state.GetChars(), info.GetChars(),
                           y.Trades, y.Trades ? y.Wins * 100 / y.Trades : 0, y.Realized);
                txt += row;
            }
            s_UseTool tool; tool.Clear();
            tool.ChartNumber = sc.ChartNumber; tool.DrawingType = DRAWING_TEXT; tool.LineNumber = LINE; tool.AddMethod = UTAM_ADD_OR_ADJUST;
            const int pos = In_PanelPos.GetIndex();
            tool.BeginIndex = (pos == 0 || pos == 2) ? sc.IndexOfFirstVisibleBar : sc.IndexOfLastVisibleBar;
            tool.UseRelativeVerticalValues = 1; tool.BeginValue = (pos <= 1) ? 97.0f : 3.0f;
            tool.Region = sc.GraphRegion; tool.Color = RGB(255, 255, 255); tool.FontBackColor = RGB(20, 20, 30);
            tool.FontSize = In_Font.GetInt(); tool.FontFace = "Courier New"; tool.TransparentLabelBackground = 0;
            tool.TextAlignment = ((pos == 0 || pos == 2) ? DT_LEFT : DT_RIGHT) | ((pos <= 1) ? DT_TOP : DT_BOTTOM);
            tool.Text = txt;
            sc.UseTool(tool);
        }
    }
}
