// =====================================================================
//  Lukacino ORB RRR – Opening Range Breakout s nastavitelným RRR
//  Sierra Chart ACSIL study (C++)
//
//  Logika (1 obchod denně):
//   1) Opening Range = high/low prvních N minut od začátku seance
//      (default 9:30–9:45 New York čas).
//   2) Vstup LONG, když svíčka ZAVŘE nad OR high.
//      Vstup SHORT, když svíčka ZAVŘE pod OR low.
//      (první signál dne vyhrává, pak už nic)
//   3) Stop loss: opačná strana range (nebo střed range – volitelné).
//   4) Take profit: riziko × RRR.
//   5) Pokud nic nezasáhne, pozice se zavře v čase "Flatten Time".
//
//  Režimy:
//   - Semi-auto  : jen šipky, SL/TP čáry a alert – obchoduješ ručně.
//   - Full auto  : study posílá příkazy (sim / backtest, nebo live
//                  pokud zapneš "Send Orders To Trade Service").
// =====================================================================
#include "sierrachart.h"

SCDLLName("Lukacino ORB RRR")

SCSFExport scsf_Lukacino_ORB_RRR(SCStudyInterfaceRef sc)
{
    // ---- Inputs ------------------------------------------------------
    SCInputRef In_Mode          = sc.Input[0];
    SCInputRef In_Direction     = sc.Input[1];
    SCInputRef In_SessionStart  = sc.Input[2];
    SCInputRef In_ORMinutes     = sc.Input[3];
    SCInputRef In_LastEntryTime = sc.Input[4];
    SCInputRef In_FlattenTime   = sc.Input[5];
    SCInputRef In_RRR           = sc.Input[6];
    SCInputRef In_StopMode      = sc.Input[7];
    SCInputRef In_Qty           = sc.Input[8];
    SCInputRef In_MinRangeTicks = sc.Input[9];
    SCInputRef In_MaxRangeTicks = sc.Input[10];
    SCInputRef In_SendLive      = sc.Input[11];

    // ---- Subgraphs ---------------------------------------------------
    SCSubgraphRef SG_ORHigh = sc.Subgraph[0];
    SCSubgraphRef SG_ORLow  = sc.Subgraph[1];
    SCSubgraphRef SG_Long   = sc.Subgraph[2];
    SCSubgraphRef SG_Short  = sc.Subgraph[3];
    SCSubgraphRef SG_Stop   = sc.Subgraph[4];
    SCSubgraphRef SG_Target = sc.Subgraph[5];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Lukacino ORB RRR";
        sc.StudyDescription =
            "Opening Range Breakout: vstup na zavreni svicky mimo range, "
            "SL na opacne strane range, TP = riziko x RRR, exit na konci dne.";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;

        In_Mode.Name = "Mode";
        In_Mode.SetCustomInputStrings("Semi-auto (signals + alerts only);Full auto (send orders)");
        In_Mode.SetCustomInputIndex(1);

        In_Direction.Name = "Direction";
        In_Direction.SetCustomInputStrings("Both;Long only;Short only");
        In_Direction.SetCustomInputIndex(0);

        In_SessionStart.Name = "Session Start Time (chart time zone)";
        In_SessionStart.SetTime(HMS_TIME(9, 30, 0));

        In_ORMinutes.Name = "Opening Range Length (minutes)";
        In_ORMinutes.SetInt(15);
        In_ORMinutes.SetIntLimits(1, 240);

        In_LastEntryTime.Name = "Last Entry Time";
        In_LastEntryTime.SetTime(HMS_TIME(11, 30, 0));

        In_FlattenTime.Name = "Flatten Time (end of day exit)";
        In_FlattenTime.SetTime(HMS_TIME(15, 55, 0));

        In_RRR.Name = "Risk:Reward (TP = risk x RRR)";
        In_RRR.SetFloat(1.5f);
        In_RRR.SetFloatLimits(0.1f, 20.0f);

        In_StopMode.Name = "Stop Loss Placement";
        In_StopMode.SetCustomInputStrings("Opposite side of range;Range midpoint");
        In_StopMode.SetCustomInputIndex(0);

        In_Qty.Name = "Position Size (contracts)";
        In_Qty.SetInt(1);
        In_Qty.SetIntLimits(1, 100);

        In_MinRangeTicks.Name = "Min Range Size in Ticks (0 = off)";
        In_MinRangeTicks.SetInt(0);

        In_MaxRangeTicks.Name = "Max Range Size in Ticks (0 = off)";
        In_MaxRangeTicks.SetInt(0);

        In_SendLive.Name = "Send Orders To Trade Service (LIVE!)";
        In_SendLive.SetYesNo(0);

        SG_ORHigh.Name = "OR High";
        SG_ORHigh.DrawStyle = DRAWSTYLE_DASH;
        SG_ORHigh.PrimaryColor = RGB(0, 200, 0);
        SG_ORHigh.DrawZeros = false;

        SG_ORLow.Name = "OR Low";
        SG_ORLow.DrawStyle = DRAWSTYLE_DASH;
        SG_ORLow.PrimaryColor = RGB(220, 0, 0);
        SG_ORLow.DrawZeros = false;

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

        // ---- Trading nastavení ----
        sc.AllowMultipleEntriesInSameDirection = false;
        sc.MaximumPositionAllowed = 100;
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

    const bool FullAuto = In_Mode.GetIndex() == 1;
    sc.SendOrdersToTradeService = In_SendLive.GetYesNo() != 0;
    sc.MaximumPositionAllowed = In_Qty.GetInt();

    // ---- Persistent state ---------------------------------------------
    float& RangeHigh   = sc.GetPersistentFloat(1);
    float& RangeLow    = sc.GetPersistentFloat(2);
    float& StopPrice   = sc.GetPersistentFloat(3);
    float& TargetPrice = sc.GetPersistentFloat(4);
    int&   CurDate     = sc.GetPersistentInt(1);
    int&   TradedToday = sc.GetPersistentInt(2);
    int&   TradeDir    = sc.GetPersistentInt(3);   // +1 long, -1 short, 0 flat (virtuální stav pro čáry)

    const int i = sc.Index;
    if (i == 0)
    {
        RangeHigh = RangeLow = StopPrice = TargetPrice = 0;
        CurDate = TradedToday = TradeDir = 0;
    }

    const int BarDate = sc.BaseDateTimeIn[i].GetDate();
    const int BarTime = sc.BaseDateTimeIn[i].GetTime();

    const int tStart   = In_SessionStart.GetTime();
    const int tORend   = tStart + In_ORMinutes.GetInt() * 60;
    const int tLastEnt = In_LastEntryTime.GetTime();
    const int tFlatten = In_FlattenTime.GetTime();

    // ---- Nový den = reset -------------------------------------------
    if (BarDate != CurDate)
    {
        CurDate = BarDate;
        RangeHigh = RangeLow = 0;
        TradedToday = 0;
        TradeDir = 0;
    }

    // ---- Budování Opening Range --------------------------------------
    if (BarTime >= tStart && BarTime < tORend)
    {
        if (RangeHigh == 0 || sc.High[i] > RangeHigh) RangeHigh = sc.High[i];
        if (RangeLow  == 0 || sc.Low[i]  < RangeLow)  RangeLow  = sc.Low[i];
        return; // během range se neobchoduje
    }

    const bool RangeReady = RangeHigh > 0 && RangeLow > 0 && BarTime >= tORend;
    if (RangeReady && BarTime <= tFlatten)
    {
        SG_ORHigh[i] = RangeHigh;
        SG_ORLow[i]  = RangeLow;
    }

    // ---- Sledování otevřeného (virtuálního) obchodu -------------------
    if (TradeDir != 0)
    {
        bool Closed = false;
        if (TradeDir > 0 && (sc.Low[i]  <= StopPrice || sc.High[i] >= TargetPrice)) Closed = true;
        if (TradeDir < 0 && (sc.High[i] >= StopPrice || sc.Low[i]  <= TargetPrice)) Closed = true;
        if (BarTime >= tFlatten) Closed = true;

        SG_Stop[i]   = StopPrice;
        SG_Target[i] = TargetPrice;
        if (Closed) TradeDir = 0;
    }

    // Akce jen na uzavřené svíčce (v real-time nečekáme na tick uprostřed baru)
    if (sc.GetBarHasClosedStatus(i) != BHCS_BAR_HAS_CLOSED)
        return;

    // ---- EOD exit ------------------------------------------------------
    if (BarTime >= tFlatten)
    {
        if (FullAuto)
        {
            s_SCPositionData Pos;
            sc.GetTradePosition(Pos);
            if (Pos.PositionQuantity != 0)
                sc.FlattenAndCancelAllOrders();
        }
        return;
    }

    if (!RangeReady || TradedToday || BarTime > tLastEnt)
        return;

    // ---- Filtr velikosti range -----------------------------------------
    const float RangeTicks = (RangeHigh - RangeLow) / sc.TickSize;
    if (In_MinRangeTicks.GetInt() > 0 && RangeTicks < In_MinRangeTicks.GetInt()) return;
    if (In_MaxRangeTicks.GetInt() > 0 && RangeTicks > In_MaxRangeTicks.GetInt()) return;

    // ---- Signál ---------------------------------------------------------
    const int  Dir     = In_Direction.GetIndex(); // 0 both, 1 long, 2 short
    const float C      = sc.Close[i];
    const float Mid    = (RangeHigh + RangeLow) * 0.5f;
    const bool  StopMid = In_StopMode.GetIndex() == 1;
    const float RRR    = In_RRR.GetFloat();

    int Signal = 0;
    if (Dir != 2 && C > RangeHigh) Signal = +1;
    else if (Dir != 1 && C < RangeLow) Signal = -1;
    if (Signal == 0)
        return;

    const float Stop = Signal > 0 ? (StopMid ? Mid : RangeLow)
                                  : (StopMid ? Mid : RangeHigh);
    const float Risk = Signal > 0 ? C - Stop : Stop - C;
    if (Risk <= 0)
        return;
    const float Reward = sc.RoundToTickSize(Risk * RRR, sc.TickSize);

    TradedToday = 1;
    TradeDir    = Signal;
    StopPrice   = Stop;
    TargetPrice = Signal > 0 ? C + Reward : C - Reward;

    if (Signal > 0) SG_Long[i]  = sc.Low[i]  - 2 * sc.TickSize;
    else            SG_Short[i] = sc.High[i] + 2 * sc.TickSize;

    SCString Msg;
    Msg.Format("ORB %s @ %.2f | SL %.2f | TP %.2f | RRR 1:%.2f",
               Signal > 0 ? "LONG" : "SHORT", C, StopPrice, TargetPrice, RRR);

    if (!FullAuto)
    {
        sc.SetAlert(1, Msg);
        return;
    }

    // ---- Full auto: market + attached SL/TP (offsety od fill ceny) ---
    s_SCNewOrder Order;
    Order.OrderQuantity = In_Qty.GetInt();
    Order.OrderType     = SCT_ORDERTYPE_MARKET;
    Order.TimeInForce   = SCT_TIF_DAY;
    Order.Stop1Offset   = sc.RoundToTickSize(Risk, sc.TickSize);
    Order.Target1Offset = Reward;

    const double Result = Signal > 0 ? sc.BuyEntry(Order) : sc.SellEntry(Order);
    if (Result > 0)
        sc.AddMessageToLog(Msg, 0);
}
