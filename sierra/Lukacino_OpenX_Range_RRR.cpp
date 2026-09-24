// =====================================================================
//  Lukacino Open-X / Range Breakout RRR
//  Sierra Chart ACSIL study (C++)
//
//  Vstupy (entry mode):
//   0 Open +/- X   : RTH open (první bar od Session Start) +/- X.
//                    Logika Breakout: long na open+X, short na open-X.
//                    Logika Fade    : long na open-X, short na open+X.
//   1 Range +/- X  : range = high/low okna Range Start - Range End.
//                    Long na range high + X, short na range low - X.
//
//  Výstupy (exit mode, jediný přepínač, nic se nepřebíjí):
//   0 Fixed TP / SL   : TP a SL z inputů, RRR se ignoruje
//   1 RRR + fixed SL  : SL z inputu, TP = SL x RRR (TP input se ignoruje)
//   2 RRR + ATR SL    : SL = ATR(N dní) x násobek, TP = SL x RRR
//   3 RRR + range SL  : SL = výška range x násobek, TP = SL x RRR
//
//  Jednotky (Ticks / Points) platí pro X, TP a SL. ATR i range jsou
//  vždy v bodech a násobí se násobkem.
//
//  Pravidla, která drží inputy v souladu (viz sierra/README.md):
//   - max. 1 pozice najednou, žádný reversal; Max Trades = vstupy za den
//   - vstup jen po čerstvém protnutí úrovně (ne hned po načtení grafu)
//   - příkazy jen na živém / replay baru, nikdy při přepočtu historie
//   - SL/TP jako GTC bracket; Kill at Session End zavře jen pozici,
//     kterou otevřela tato instance studie
//   - Send Orders To Trade Service platí jen ve Full auto
//   - nevalidní kombinace inputů = obchodování vypnuto + zpráva v logu
// =====================================================================
#include "sierrachart.h"

SCDLLName("Lukacino Open-X Range RRR")

namespace
{
    enum { MODE_SEMI = 0, MODE_FULL = 1 };
    enum { DIR_BOTH = 0, DIR_LONG = 1, DIR_SHORT = 2 };
    enum { ENTRY_OPEN = 0, ENTRY_RANGE = 1 };
    enum { LOGIC_BREAKOUT = 0, LOGIC_FADE = 1 };
    enum { UNITS_TICKS = 0, UNITS_POINTS = 1 };
    enum { EXIT_FIXED = 0, EXIT_RRR_FIXED_SL = 1, EXIT_RRR_ATR = 2, EXIT_RRR_RANGE = 3 };

    const int ATR_MAX_DAYS = 50;
    const int ATR_BUF_BASE = 100;  // persistent float 100..149 = denní rozpětí pro ATR
}

SCSFExport scsf_Lukacino_OpenX_Range_RRR(SCStudyInterfaceRef sc)
{
    // ---- Inputs ------------------------------------------------------
    SCInputRef In_Enabled      = sc.Input[0];
    SCInputRef In_Mode         = sc.Input[1];
    SCInputRef In_SendLive     = sc.Input[2];
    SCInputRef In_Direction    = sc.Input[3];
    SCInputRef In_MaxTrades    = sc.Input[4];
    SCInputRef In_Qty          = sc.Input[5];
    SCInputRef In_KillEOD      = sc.Input[6];
    SCInputRef In_SessionStart = sc.Input[7];
    SCInputRef In_LastEntry    = sc.Input[8];
    SCInputRef In_Flatten      = sc.Input[9];
    SCInputRef In_EntryMode    = sc.Input[10];
    SCInputRef In_OpenLogic    = sc.Input[11];
    SCInputRef In_EntryX       = sc.Input[12];
    SCInputRef In_RangeStart   = sc.Input[13];
    SCInputRef In_RangeEnd     = sc.Input[14];
    SCInputRef In_Units        = sc.Input[15];
    SCInputRef In_ExitMode     = sc.Input[16];
    SCInputRef In_TP           = sc.Input[17];
    SCInputRef In_SL           = sc.Input[18];
    SCInputRef In_RRR          = sc.Input[19];
    SCInputRef In_ATRDays      = sc.Input[20];
    SCInputRef In_ATRMult      = sc.Input[21];
    SCInputRef In_RangeMult    = sc.Input[22];

    // ---- Subgraphs ---------------------------------------------------
    SCSubgraphRef SG_Open       = sc.Subgraph[0];
    SCSubgraphRef SG_LongLevel  = sc.Subgraph[1];
    SCSubgraphRef SG_ShortLevel = sc.Subgraph[2];
    SCSubgraphRef SG_RangeHigh  = sc.Subgraph[3];
    SCSubgraphRef SG_RangeLow   = sc.Subgraph[4];
    SCSubgraphRef SG_Long       = sc.Subgraph[5];
    SCSubgraphRef SG_Short      = sc.Subgraph[6];
    SCSubgraphRef SG_Stop       = sc.Subgraph[7];
    SCSubgraphRef SG_Target     = sc.Subgraph[8];
    SCSubgraphRef SG_ATR        = sc.Subgraph[9];   // jen hodnota (název grafu, Chart Values)
    SCSubgraphRef SG_SLDist     = sc.Subgraph[10];
    SCSubgraphRef SG_TPDist     = sc.Subgraph[11];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Lukacino Open-X Range RRR";
        sc.StudyDescription =
            "Vstup na open +/- X nebo na pruraz range +/- X. SL/TP: fixni, RRR + fixni SL, "
            "RRR + ATR SL, RRR + range SL. Semi-auto (alerty) nebo Full auto (prikazy).";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;

        In_Enabled.Name = "Trading Enabled";
        In_Enabled.SetYesNo(1);

        In_Mode.Name = "Mode";
        In_Mode.SetCustomInputStrings("Semi-auto (signals + alerts);Full auto (send orders)");
        In_Mode.SetCustomInputIndex(MODE_SEMI);

        In_SendLive.Name = "Send Orders To Trade Service (LIVE!, Full auto only)";
        In_SendLive.SetYesNo(0);

        In_Direction.Name = "Direction";
        In_Direction.SetCustomInputStrings("Both;Long only;Short only");
        In_Direction.SetCustomInputIndex(DIR_LONG);

        In_MaxTrades.Name = "Max Trades Per Day (entries)";
        In_MaxTrades.SetInt(1);
        In_MaxTrades.SetIntLimits(1, 50);

        In_Qty.Name = "Position Size (contracts)";
        In_Qty.SetInt(1);
        In_Qty.SetIntLimits(1, 100);

        In_KillEOD.Name = "Kill Position At Session End (Flatten Time)";
        In_KillEOD.SetYesNo(1);

        In_SessionStart.Name = "Session Start / Open Time (chart time zone)";
        In_SessionStart.SetTime(HMS_TIME(9, 30, 0));

        In_LastEntry.Name = "Last Entry Time";
        In_LastEntry.SetTime(HMS_TIME(15, 0, 0));

        In_Flatten.Name = "Flatten Time (session end)";
        In_Flatten.SetTime(HMS_TIME(15, 55, 0));

        In_EntryMode.Name = "Entry Mode";
        In_EntryMode.SetCustomInputStrings("Open +/- X;Range breakout +/- X");
        In_EntryMode.SetCustomInputIndex(ENTRY_OPEN);

        In_OpenLogic.Name = "Open +/- X Logic (Entry Mode Open only)";
        In_OpenLogic.SetCustomInputStrings(
            "Breakout (long open+X, short open-X);Fade (long open-X, short open+X)");
        In_OpenLogic.SetCustomInputIndex(LOGIC_BREAKOUT);

        In_EntryX.Name = "Entry Distance X (units)";
        In_EntryX.SetFloat(15.0f);
        In_EntryX.SetFloatLimits(0.0f, 100000.0f);

        In_RangeStart.Name = "Range Start Time (range entry / range SL)";
        In_RangeStart.SetTime(HMS_TIME(9, 30, 0));

        In_RangeEnd.Name = "Range End Time";
        In_RangeEnd.SetTime(HMS_TIME(9, 45, 0));

        In_Units.Name = "Units for X / TP / SL";
        In_Units.SetCustomInputStrings("Ticks;Points");
        In_Units.SetCustomInputIndex(UNITS_POINTS);

        In_ExitMode.Name = "Exit Mode";
        In_ExitMode.SetCustomInputStrings(
            "Fixed TP / SL;RRR + fixed SL;RRR + ATR SL;RRR + range SL");
        In_ExitMode.SetCustomInputIndex(EXIT_RRR_FIXED_SL);

        In_TP.Name = "TP (units, Exit Mode Fixed only)";
        In_TP.SetFloat(40.0f);
        In_TP.SetFloatLimits(0.0f, 100000.0f);

        In_SL.Name = "SL (units, Exit Mode Fixed / RRR + fixed SL)";
        In_SL.SetFloat(20.0f);
        In_SL.SetFloatLimits(0.0f, 100000.0f);

        In_RRR.Name = "RRR = TP / SL (RRR modes)";
        In_RRR.SetFloat(2.0f);
        In_RRR.SetFloatLimits(0.1f, 20.0f);

        In_ATRDays.Name = "ATR Length (days, RRR + ATR SL)";
        In_ATRDays.SetInt(14);
        In_ATRDays.SetIntLimits(1, ATR_MAX_DAYS);

        In_ATRMult.Name = "ATR SL Multiplier (SL = ATR x mult)";
        In_ATRMult.SetFloat(0.25f);
        In_ATRMult.SetFloatLimits(0.01f, 10.0f);

        In_RangeMult.Name = "Range SL Multiplier (SL = range height x mult)";
        In_RangeMult.SetFloat(1.0f);
        In_RangeMult.SetFloatLimits(0.01f, 10.0f);

        SG_Open.Name = "Session Open";
        SG_Open.DrawStyle = DRAWSTYLE_DASH;
        SG_Open.PrimaryColor = RGB(160, 160, 160);
        SG_Open.DrawZeros = false;

        SG_LongLevel.Name = "Long Entry Level";
        SG_LongLevel.DrawStyle = DRAWSTYLE_DASH;
        SG_LongLevel.PrimaryColor = RGB(0, 120, 255);
        SG_LongLevel.DrawZeros = false;

        SG_ShortLevel.Name = "Short Entry Level";
        SG_ShortLevel.DrawStyle = DRAWSTYLE_DASH;
        SG_ShortLevel.PrimaryColor = RGB(255, 120, 0);
        SG_ShortLevel.DrawZeros = false;

        SG_RangeHigh.Name = "Range High";
        SG_RangeHigh.DrawStyle = DRAWSTYLE_LINE;
        SG_RangeHigh.PrimaryColor = RGB(0, 200, 0);
        SG_RangeHigh.DrawZeros = false;

        SG_RangeLow.Name = "Range Low";
        SG_RangeLow.DrawStyle = DRAWSTYLE_LINE;
        SG_RangeLow.PrimaryColor = RGB(220, 0, 0);
        SG_RangeLow.DrawZeros = false;

        SG_Long.Name = "Long Signal";
        SG_Long.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_Long.PrimaryColor = RGB(0, 120, 255);
        SG_Long.LineWidth = 3;
        SG_Long.DrawZeros = false;

        SG_Short.Name = "Short Signal";
        SG_Short.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_Short.PrimaryColor = RGB(255, 60, 60);
        SG_Short.LineWidth = 3;
        SG_Short.DrawZeros = false;

        SG_Stop.Name = "Stop Loss";
        SG_Stop.DrawStyle = DRAWSTYLE_LINE;
        SG_Stop.PrimaryColor = RGB(255, 0, 0);
        SG_Stop.DrawZeros = false;

        SG_Target.Name = "Take Profit";
        SG_Target.DrawStyle = DRAWSTYLE_LINE;
        SG_Target.PrimaryColor = RGB(0, 255, 0);
        SG_Target.DrawZeros = false;

        // Nekreslí se, jen ukazují aktuální ATR a vzdálenost SL/TP v bodech
        SG_ATR.Name = "ATR (points)";
        SG_ATR.DrawStyle = DRAWSTYLE_HIDDEN;
        SG_ATR.DrawZeros = false;

        SG_SLDist.Name = "SL distance (points)";
        SG_SLDist.DrawStyle = DRAWSTYLE_HIDDEN;
        SG_SLDist.DrawZeros = false;

        SG_TPDist.Name = "TP distance (points)";
        SG_TPDist.DrawStyle = DRAWSTYLE_HIDDEN;
        SG_TPDist.DrawZeros = false;

        // ---- Trading nastavení ----
        sc.AllowMultipleEntriesInSameDirection = false;
        sc.MaximumPositionAllowed = 1;
        sc.SupportReversals = false;
        sc.SendOrdersToTradeService = false;
        sc.AllowOppositeEntryWithOpposingPositionOrOrders = false;
        sc.SupportAttachedOrdersForTrading = false;
        sc.CancelAllOrdersOnEntriesAndReversals = true;
        sc.AllowEntryWithWorkingOrders = false;
        sc.CancelAllWorkingOrdersOnExit = true;
        sc.AllowOnlyOneTradePerBar = true;
        sc.MaintainTradeStatisticsAndTradesData = true;
        return;
    }

    // ---- Nastavení z inputů --------------------------------------------
    const bool Enabled   = In_Enabled.GetYesNo() != 0;
    const bool FullAuto  = In_Mode.GetIndex() == MODE_FULL;
    const bool SendLive  = In_SendLive.GetYesNo() != 0;
    const int  Dir       = In_Direction.GetIndex();
    const int  MaxTrades = In_MaxTrades.GetInt();
    const int  Qty       = In_Qty.GetInt();
    const bool KillEOD   = In_KillEOD.GetYesNo() != 0;
    const int  tStart    = In_SessionStart.GetTime();
    const int  tLastEnt  = In_LastEntry.GetTime();
    const int  tFlatten  = In_Flatten.GetTime();
    const int  EntryMode = In_EntryMode.GetIndex();
    const bool Fade      = In_OpenLogic.GetIndex() == LOGIC_FADE;
    const int  tRStart   = In_RangeStart.GetTime();
    const int  tREnd     = In_RangeEnd.GetTime();
    const int  ExitMode  = In_ExitMode.GetIndex();
    const float RRR      = In_RRR.GetFloat();
    const int  ATRDays   = In_ATRDays.GetInt();
    const float Tick     = sc.TickSize;

    // Live flag má smysl jen ve Full auto. V Semi-auto se nikdy nic neposílá.
    sc.SendOrdersToTradeService = FullAuto && SendLive;
    sc.MaximumPositionAllowed = Qty;

    // Jednotky: X, TP, SL jsou v tickách nebo bodech podle přepínače
    const float UnitPts = In_Units.GetIndex() == UNITS_TICKS ? Tick : 1.0f;
    const float X       = In_EntryX.GetFloat() * UnitPts;
    const float TPpts   = In_TP.GetFloat() * UnitPts;
    const float SLpts   = In_SL.GetFloat() * UnitPts;

    // Range je potřeba pro vstup "Range breakout" i pro exit "RRR + range SL"
    const bool UseRange = EntryMode == ENTRY_RANGE || ExitMode == EXIT_RRR_RANGE;

    // ---- Kontrola konzistence inputů -----------------------------------
    SCString CfgErr;
    if (Tick <= 0)
        CfgErr = "Tick Size grafu je 0.";
    else if (!(tStart < tLastEnt && tLastEnt <= tFlatten))
        CfgErr = "Musi platit Session Start < Last Entry Time <= Flatten Time.";
    else if (UseRange && !(tStart <= tRStart && tRStart < tREnd && tREnd <= tLastEnt))
        CfgErr = "Musi platit Session Start <= Range Start < Range End <= Last Entry Time.";
    else if (EntryMode == ENTRY_OPEN && X < Tick)
        CfgErr = "Open +/- X potrebuje X aspon 1 tick (pri X = 0 by long i short vstoupily hned na open).";
    else if (ExitMode == EXIT_FIXED && (TPpts < Tick || SLpts < Tick))
        CfgErr = "Exit Mode Fixed TP / SL: TP i SL musi byt aspon 1 tick.";
    else if (ExitMode == EXIT_RRR_FIXED_SL && SLpts < Tick)
        CfgErr = "Exit Mode RRR + fixed SL: SL musi byt aspon 1 tick.";
    else if (ExitMode != EXIT_FIXED && RRR <= 0)
        CfgErr = "RRR musi byt vetsi nez 0.";
    const bool ConfigOK = CfgErr.GetLength() == 0;

    // ---- Persistent state ---------------------------------------------
    float& DayOpen     = sc.GetPersistentFloat(1);
    float& RangeHigh   = sc.GetPersistentFloat(2);
    float& RangeLow    = sc.GetPersistentFloat(3);
    float& SessHigh    = sc.GetPersistentFloat(4);
    float& SessLow     = sc.GetPersistentFloat(5);
    float& StopPrice   = sc.GetPersistentFloat(6);
    float& TargetPrice = sc.GetPersistentFloat(7);
    float& EntryPrice  = sc.GetPersistentFloat(8);

    int& CurDate      = sc.GetPersistentInt(1);
    int& OpenValid    = sc.GetPersistentInt(2);
    int& RangeHasBars = sc.GetPersistentInt(3);
    int& TradesToday  = sc.GetPersistentInt(4);
    int& TradeDir     = sc.GetPersistentInt(5);   // +1 long, -1 short, 0 flat (stav studie)
    int& OwnPosition  = sc.GetPersistentInt(6);   // 1 = reálnou pozici otevřela tato instance
    int& ArmLong      = sc.GetPersistentInt(7);   // cena byla na "správné" straně long úrovně
    int& ArmShort     = sc.GetPersistentInt(8);
    int& LastIndex    = sc.GetPersistentInt(9);
    int& AtrCount     = sc.GetPersistentInt(10);
    int& AtrPos       = sc.GetPersistentInt(11);
    int& SessValid    = sc.GetPersistentInt(12);
    int& DayPartial   = sc.GetPersistentInt(13);  // data začínají uprostřed seance
    int& EntryIndex   = sc.GetPersistentInt(14);
    int& EntryDate    = sc.GetPersistentInt(15);
    int& LoggedCfg    = sc.GetPersistentInt(16);
    int& LoggedLive   = sc.GetPersistentInt(17);
    int& LoggedDay    = sc.GetPersistentInt(18);  // datum posledního denního výpisu ATR/SL/TP
    int& LoggedWrongDir = sc.GetPersistentInt(19);  // datum varování o pozici proti Direction

    const int i = sc.Index;
    const int BarDate = sc.BaseDateTimeIn[i].GetDate();
    const int t       = sc.BaseDateTimeIn[i].GetTimeInSeconds();

    if (i == 0)
    {
        DayOpen = RangeHigh = RangeLow = SessHigh = SessLow = 0;
        StopPrice = TargetPrice = EntryPrice = 0;
        CurDate = OpenValid = RangeHasBars = TradesToday = TradeDir = 0;
        ArmLong = ArmShort = AtrCount = AtrPos = SessValid = 0;
        EntryIndex = 0;
        LastIndex = -1;
        LoggedCfg = LoggedLive = LoggedDay = LoggedWrongDir = 0;
        DayPartial = t > tStart ? 1 : 0;
        CurDate = BarDate;
        // OwnPosition a EntryDate se při přepočtu nemažou: reálná pozice mohla
        // zůstat otevřená a Kill musí vědět, ze kterého dne je
    }

    // Příkazy a alerty jen na živém baru (real-time nebo Replay), nikdy při přepočtu historie
    const bool LiveBar = i == sc.ArraySize - 1 && !sc.IsFullRecalculation;

    if (i == sc.ArraySize - 1)
    {
        if (!ConfigOK && !LoggedCfg)
        {
            SCString Msg;
            Msg.Format("Lukacino Open-X Range RRR: obchodovani vypnuto, chybne inputy: %s", CfgErr.GetChars());
            sc.AddMessageToLog(Msg, 1);
            LoggedCfg = 1;
        }
        if (!FullAuto && SendLive && !LoggedLive)
        {
            sc.AddMessageToLog("Lukacino Open-X Range RRR: Send Orders To Trade Service se v Semi-auto ignoruje (neposila se nic).", 0);
            LoggedLive = 1;
        }
    }

    // ---- Nový den: ATR z uzavřené seance + reset denního stavu --------
    if (BarDate != CurDate)
    {
        if (SessValid && !DayPartial && SessHigh > SessLow)
        {
            sc.GetPersistentFloat(ATR_BUF_BASE + AtrPos) = SessHigh - SessLow;
            AtrPos = (AtrPos + 1) % ATRDays;
            if (AtrCount < ATRDays) AtrCount++;
        }
        CurDate = BarDate;
        DayOpen = RangeHigh = RangeLow = SessHigh = SessLow = 0;
        OpenValid = RangeHasBars = SessValid = DayPartial = 0;
        TradesToday = 0;
        ArmLong = ArmShort = 0;
    }

    const bool InSession = t >= tStart && t < tFlatten;

    // ---- Open, rozpětí seance (pro ATR) a range ------------------------
    if (InSession && !DayPartial)
    {
        if (!OpenValid)
        {
            DayOpen = sc.Open[i];
            OpenValid = 1;
        }
        if (!SessValid || sc.High[i] > SessHigh) SessHigh = sc.High[i];
        if (!SessValid || sc.Low[i]  < SessLow)  SessLow  = sc.Low[i];
        SessValid = 1;
    }

    if (UseRange && !DayPartial && t >= tRStart && t < tREnd)
    {
        if (!RangeHasBars || sc.High[i] > RangeHigh) RangeHigh = sc.High[i];
        if (!RangeHasBars || sc.Low[i]  < RangeLow)  RangeLow  = sc.Low[i];
        RangeHasBars = 1;
    }
    const bool RangeReady = UseRange && RangeHasBars && t >= tREnd;

    float ATR = 0;
    if (AtrCount >= ATRDays)
    {
        for (int k = 0; k < ATRDays; k++)
            ATR += sc.GetPersistentFloat(ATR_BUF_BASE + k);
        ATR /= ATRDays;
    }

    // Vzdálenost SL/TP podle Exit Mode (0 = zatím neznámá: ATR bez dost dní, range před koncem okna)
    float Risk = 0;
    switch (ExitMode)
    {
    case EXIT_FIXED:
    case EXIT_RRR_FIXED_SL: Risk = SLpts; break;
    case EXIT_RRR_ATR:      Risk = AtrCount >= ATRDays ? ATR * In_ATRMult.GetFloat() : 0; break;
    case EXIT_RRR_RANGE:    Risk = RangeReady ? (RangeHigh - RangeLow) * In_RangeMult.GetFloat() : 0; break;
    }
    Risk = (float)sc.RoundToTickSize(Risk, Tick);
    const float Reward = Risk > 0
        ? (float)sc.RoundToTickSize(ExitMode == EXIT_FIXED ? TPpts : Risk * RRR, Tick) : 0;

    if (ATR > 0)    SG_ATR[i]    = ATR;
    if (Risk > 0)   SG_SLDist[i] = Risk;
    if (Reward > 0) SG_TPDist[i] = Reward;

    // Jednou denně (po otevření seance, a u range SL po konci range) vypiš do logu aktuální hodnoty
    if (LiveBar && InSession && OpenValid && LoggedDay != BarDate
        && (ExitMode != EXIT_RRR_RANGE || RangeReady))
    {
        SCString Msg;
        if (AtrCount >= ATRDays)
            Msg.Format("Lukacino: ATR(%d) = %.2f b. | SL = %.2f b. | TP = %.2f b.", ATRDays, ATR, Risk, Reward);
        else
            Msg.Format("Lukacino: ATR(%d) zatim nema dost dni (%d/%d) | SL = %.2f b. | TP = %.2f b.",
                       ATRDays, AtrCount, ATRDays, Risk, Reward);
        sc.AddMessageToLog(Msg, 0);
        LoggedDay = BarDate;
    }

    // ---- Vstupní úrovně ----------------------------------------------
    // LongUp/ShortUp: úroveň se protíná zespodu (stop vstup) nebo shora (limit vstup)
    float LongLevel = 0, ShortLevel = 0;
    bool LevelsReady = false;
    bool LongUp = true, ShortUp = false;
    if (EntryMode == ENTRY_OPEN)
    {
        LevelsReady = OpenValid != 0;
        LongLevel   = Fade ? DayOpen - X : DayOpen + X;
        ShortLevel  = Fade ? DayOpen + X : DayOpen - X;
        LongUp  = !Fade;
        ShortUp = Fade;
    }
    else
    {
        LevelsReady = RangeReady;
        LongLevel   = RangeHigh + X;
        ShortLevel  = RangeLow - X;
    }

    if (InSession)
    {
        if (OpenValid) SG_Open[i] = DayOpen;
        if (RangeReady)
        {
            SG_RangeHigh[i] = RangeHigh;
            SG_RangeLow[i]  = RangeLow;
        }
        if (LevelsReady && t <= tLastEnt)
        {
            if (Dir != DIR_SHORT) SG_LongLevel[i]  = LongLevel;
            if (Dir != DIR_LONG)  SG_ShortLevel[i] = ShortLevel;
        }
    }

    // ---- Reálná pozice (Full auto, nebo zbylá vlastní pozice) na živém baru
    s_SCPositionData Pos;
    bool RealFlat = true;
    if (LiveBar && (FullAuto || OwnPosition))
    {
        sc.GetTradePosition(Pos);
        RealFlat = Pos.PositionQuantity == 0;
        // Bracket zavřel pozici: studie je znovu volná
        if (OwnPosition && RealFlat && !Pos.WorkingOrdersExist)
        {
            OwnPosition = 0;
            TradeDir = 0;
        }
        // Pozice zmizela jinak než přes bracket (ruční zavření, reset Replay...), ale SL/TP
        // zůstaly viset. Takový osiřelý GTC příkaz by po zásahu otevřel pozici opačným směrem.
        // (i > EntryIndex + 1: market vstup z tohoto nebo minulého baru se ještě může plnit)
        else if (OwnPosition && RealFlat && Pos.WorkingOrdersExist && i > EntryIndex + 1)
        {
            sc.CancelAllOrders();
            sc.AddMessageToLog("Lukacino: pozice je zavrena, ale SL/TP prikazy zustaly - zruseny.", 1);
            OwnPosition = 0;
            TradeDir = 0;
        }

        // Pozice proti nastavenému směru (short při Long only a naopak) nikdy nevznikne ze studie.
        // Nezavírá se automaticky (může být ruční), jen jednou denně varování.
        const bool WrongDir = (Dir == DIR_LONG && Pos.PositionQuantity < 0)
                           || (Dir == DIR_SHORT && Pos.PositionQuantity > 0);
        if (WrongDir && LoggedWrongDir != BarDate)
        {
            SCString Msg;
            Msg.Format("Lukacino: POZOR, na uctu je %s pozice %.0f, ale Direction = %s. Studie ji neotevrela "
                       "(zbyly prikaz / rucni obchod). Zkontroluj Trade >> Trade Activity Log.",
                       Pos.PositionQuantity < 0 ? "SHORT" : "LONG", Pos.PositionQuantity,
                       Dir == DIR_LONG ? "Long only" : "Short only");
            sc.AddMessageToLog(Msg, 1);
            sc.SetAlert(1, Msg);
            LoggedWrongDir = BarDate;
        }
    }

    // ---- Sledování obchodu (čáry SL/TP, stav pro Semi-auto) ------------
    if (TradeDir != 0)
    {
        SG_Stop[i]   = StopPrice;
        SG_Target[i] = TargetPrice;
        if (i > EntryIndex)
        {
            const bool HitSL = TradeDir > 0 ? sc.Low[i]  <= StopPrice   : sc.High[i] >= StopPrice;
            const bool HitTP = TradeDir > 0 ? sc.High[i] >= TargetPrice : sc.Low[i]  <= TargetPrice;
            if (HitSL || HitTP)
            {
                if (LiveBar)
                {
                    SCString Msg;
                    Msg.Format("Lukacino: %s %s zasazen (%.2f)", TradeDir > 0 ? "LONG" : "SHORT",
                               HitSL ? "SL" : "TP", HitSL ? StopPrice : TargetPrice);
                    sc.AddMessageToLog(Msg, 0);
                }
                TradeDir = 0;
            }
        }
    }

    // ---- Kill na konci seance ------------------------------------------
    // Platí i při Trading Enabled = No, aby vypnutí nenechalo pozici přes noc.
    if (KillEOD && (TradeDir != 0 || OwnPosition) && (t >= tFlatten || BarDate != EntryDate))
    {
        if (LiveBar)
        {
            if (OwnPosition)  // i po přepnutí na Semi-auto: pozici otevřela tato studie
            {
                if (!RealFlat)
                {
                    const int Result = (int)sc.FlattenAndCancelAllOrders();
                    sc.AddMessageToLog(Result > 0
                        ? "Lukacino: Flatten Time, pozice zavrena."
                        : "Lukacino: Flatten Time, zavreni pozice SELHALO - zkontroluj Trade Service Log!", Result > 0 ? 0 : 1);
                }
                OwnPosition = 0;
            }
            else if (!FullAuto && TradeDir != 0)
                sc.SetAlert(1, "Lukacino: Flatten Time - zavri pozici rucne!");
        }
        TradeDir = 0;
    }

    // ---- Čerstvé protnutí: jednou za bar podle close předchozího baru --
    if (i != LastIndex)
    {
        if (i > 0 && LevelsReady && TradeDir == 0 && !OwnPosition
            && sc.BaseDateTimeIn[i - 1].GetDate() == BarDate
            && (EntryMode == ENTRY_OPEN || sc.BaseDateTimeIn[i - 1].GetTimeInSeconds() >= tREnd))
        {
            const float PC = sc.Close[i - 1];
            if (LongUp ? PC < LongLevel : PC > LongLevel)    ArmLong = 1;
            if (ShortUp ? PC < ShortLevel : PC > ShortLevel) ArmShort = 1;
        }
        LastIndex = i;
    }

    // ---- Vstup -------------------------------------------------------
    if (!Enabled || !ConfigOK || !LevelsReady || DayPartial)
        return;
    if (t < tStart || t > tLastEnt || t >= tFlatten)
        return;
    if (TradesToday >= MaxTrades || TradeDir != 0 || OwnPosition || !RealFlat)
        return;
    if (ExitMode == EXIT_RRR_ATR && AtrCount < ATRDays)
        return;  // ATR ještě nemá dost uzavřených dní
    if (ExitMode == EXIT_RRR_RANGE && !RangeReady)
        return;  // Open +/- X s range SL: vstup až po konci range okna

    const float O = sc.Open[i];
    const float C = sc.Close[i];
    const bool LongSig = Dir != DIR_SHORT
        && (LongUp ? (ArmLong || O < LongLevel) && C >= LongLevel
                   : (ArmLong || O > LongLevel) && C <= LongLevel);
    const bool ShortSig = Dir != DIR_LONG
        && (ShortUp ? (ArmShort || O < ShortLevel) && C >= ShortLevel
                    : (ArmShort || O > ShortLevel) && C <= ShortLevel);
    if (!LongSig && !ShortSig)
        return;
    const int Signal = LongSig ? +1 : -1;

    // ---- SL / TP (spočítané výše podle Exit Mode) ----------------------
    if (Risk < Tick || Reward < Tick)
    {
        ArmLong = ArmShort = 0;
        if (LiveBar)
            sc.AddMessageToLog("Lukacino: signal preskocen, SL nebo TP vychazi pod 1 tick.", 1);
        return;
    }

    TradesToday++;
    TradeDir    = Signal;
    EntryPrice  = C;
    StopPrice   = Signal > 0 ? C - Risk   : C + Risk;
    TargetPrice = Signal > 0 ? C + Reward : C - Reward;
    EntryIndex  = i;
    EntryDate   = BarDate;
    ArmLong = ArmShort = 0;  // další obchod až po novém protnutí

    if (Signal > 0) SG_Long[i]  = sc.Low[i]  - 2 * Tick;
    else            SG_Short[i] = sc.High[i] + 2 * Tick;
    SG_Stop[i]   = StopPrice;
    SG_Target[i] = TargetPrice;

    if (!LiveBar)
        return;  // historie: jen šipky a čáry

    SCString Msg;
    Msg.Format("Lukacino %s @ %.2f | SL %.2f | TP %.2f | RR %.2f | obchod %d/%d",
               Signal > 0 ? "LONG" : "SHORT", C, StopPrice, TargetPrice, Reward / Risk,
               TradesToday, MaxTrades);
    sc.AddMessageToLog(Msg, 0);

    if (!FullAuto)
    {
        sc.SetAlert(1, Msg);
        return;
    }

    // ---- Full auto: market + attached SL/TP (offsety od fill ceny) ---
    // GTC vždy: bracket nesmí vypršet, když je Kill = No a pozice drží přes noc.
    s_SCNewOrder Order;
    Order.OrderQuantity = Qty;
    Order.OrderType     = SCT_ORDERTYPE_MARKET;
    Order.TimeInForce   = SCT_TIF_GOOD_TILL_CANCELED;
    Order.Stop1Offset   = Risk;
    Order.Target1Offset = Reward;

    const int Result = (int)(Signal > 0 ? sc.BuyEntry(Order) : sc.SellEntry(Order));
    if (Result > 0)
        OwnPosition = 1;
    else
    {
        // Signál je spotřebovaný (ArmLong/ArmShort = 0), takže se neopakuje každý tick
        TradeDir = 0;
        TradesToday--;
        SCString Err;
        Err.Format("Lukacino: prikaz NEODESLAN: %s (zkontroluj Trade >> Auto Trading Enabled, "
                   "Trade Simulation Mode a Trade Service Log)", sc.GetTradingErrorTextMessage(Result));
        sc.AddMessageToLog(Err, 1);
    }
}
