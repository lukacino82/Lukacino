#include "sierrachart.h"

SCDLLName("Turtle Breakout Strategy")

/*==========================================================================
  Turtle Breakout Strategy — Nasdaq 100 Futures, 60-minute chart

  Entry:
    LONG  - Close > 200 MA AND Close > prior 40-bar high
    SHORT - Close < 200 MA AND Close < prior 40-bar low

  Exit:
    Stop loss   - 2 x ATR(20), fixed price set at entry
    Take profit - structural: close LONG on a close below the 40-bar low,
                  close SHORT on a close above the 40-bar high

  Position sizing:
    Contracts = (Equity x Risk%) / (StopDistancePoints x PointValue)
==========================================================================*/

SCSFExport scsf_TurtleBreakoutStrategy(SCStudyInterfaceRef sc)
{
    SCInputRef Input_MALength         = sc.Input[0];
    SCInputRef Input_BreakoutLength   = sc.Input[1];
    SCInputRef Input_ATRLength        = sc.Input[2];
    SCInputRef Input_ATRStopMultiplier = sc.Input[3];
    SCInputRef Input_AccountEquity    = sc.Input[4];
    SCInputRef Input_RiskPercent      = sc.Input[5];

    SCSubgraphRef Subgraph_MA            = sc.Subgraph[0];
    SCSubgraphRef Subgraph_UpperBreakout = sc.Subgraph[1];
    SCSubgraphRef Subgraph_LowerBreakout = sc.Subgraph[2];
    SCSubgraphRef Subgraph_ATR           = sc.Subgraph[3];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Turtle Breakout Strategy";
        sc.StudyDescription = "Turtle-style breakout: 200 MA trend filter + 40-bar Donchian entry, ATR stop, structural exit, risk-based sizing. NQ futures, 60-minute bars.";

        sc.AutoLoop = 1;
        sc.GraphRegion = 0;

        sc.Subgraph[0].Name = "200 MA";
        sc.Subgraph[0].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[0].PrimaryColor = RGB(255, 255, 0);

        sc.Subgraph[1].Name = "40-Bar High";
        sc.Subgraph[1].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[1].PrimaryColor = RGB(0, 255, 0);

        sc.Subgraph[2].Name = "40-Bar Low";
        sc.Subgraph[2].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[2].PrimaryColor = RGB(255, 0, 0);

        sc.Subgraph[3].Name = "ATR";
        sc.Subgraph[3].DrawStyle = DRAWSTYLE_IGNORE;

        Input_MALength.Name = "Trend MA Length";
        Input_MALength.SetInt(200);

        Input_BreakoutLength.Name = "Breakout Lookback (bars)";
        Input_BreakoutLength.SetInt(40);

        Input_ATRLength.Name = "ATR Length";
        Input_ATRLength.SetInt(20);

        Input_ATRStopMultiplier.Name = "ATR Stop Multiplier";
        Input_ATRStopMultiplier.SetFloat(2.0f);

        Input_AccountEquity.Name = "Account Equity ($)";
        Input_AccountEquity.SetDouble(100000.0);

        Input_RiskPercent.Name = "Risk Per Trade (% of Equity)";
        Input_RiskPercent.SetFloat(2.0f);

        sc.SendOrdersToTradeService = 1;
        sc.SupportReversals = 1;
        sc.CancelAllOrdersOnEntriesAndReversals = 1;

        return;
    }

    int MALength       = Input_MALength.GetInt();
    int BreakoutLength = Input_BreakoutLength.GetInt();
    int ATRLength      = Input_ATRLength.GetInt();

    sc.SimpleMovAvg(sc.Close, Subgraph_MA, MALength);
    sc.Highest(sc.High, Subgraph_UpperBreakout, BreakoutLength);
    sc.Lowest(sc.Low, Subgraph_LowerBreakout, BreakoutLength);
    sc.ATR(sc.BaseDataIn, Subgraph_ATR, ATRLength, MOVAVGTYPE_SIMPLE);

    int Index = sc.Index;
    if (Index <= BreakoutLength || Index < MALength || Index < ATRLength)
        return;

    if (sc.GetBarHasClosedStatus(Index) != BHCS_BAR_HAS_CLOSED)
        return;

    float Close = sc.Close[Index];
    float MAValue = Subgraph_MA[Index];
    float PriorHigh = Subgraph_UpperBreakout[Index - 1]; // prior 40-bar high, excludes current bar
    float PriorLow  = Subgraph_LowerBreakout[Index - 1]; // prior 40-bar low, excludes current bar
    float StopDistance = Input_ATRStopMultiplier.GetFloat() * Subgraph_ATR[Index];

    s_SCPositionData Position;
    sc.GetTradePosition(Position);
    int PositionQty = Position.PositionQuantity;

    // Structural exit: close the position when price breaks the opposite side of the channel.
    if (PositionQty > 0 && Close < PriorLow)
    {
        s_SCNewOrder ExitOrder;
        ExitOrder.OrderQuantity = PositionQty;
        sc.SellExit(ExitOrder);
        return;
    }
    if (PositionQty < 0 && Close > PriorHigh)
    {
        s_SCNewOrder ExitOrder;
        ExitOrder.OrderQuantity = -PositionQty;
        sc.BuyExit(ExitOrder);
        return;
    }

    if (PositionQty != 0)
        return; // already in a trade, nothing else to do this bar

    // Position sizing: risk a fixed % of equity, sized off the ATR stop distance.
    int Contracts = 1;
    if (StopDistance > 0 && sc.PointValue > 0)
    {
        double RiskDollars = Input_AccountEquity.GetDouble() * (Input_RiskPercent.GetFloat() / 100.0);
        Contracts = (int)(RiskDollars / (StopDistance * sc.PointValue));
        if (Contracts < 1)
            Contracts = 1;
    }

    if (Close > MAValue && Close > PriorHigh)
    {
        s_SCNewOrder NewOrder;
        NewOrder.OrderQuantity = Contracts;
        NewOrder.Stop1Offset = StopDistance;
        NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;
        sc.BuyEntry(NewOrder);
    }
    else if (Close < MAValue && Close < PriorLow)
    {
        s_SCNewOrder NewOrder;
        NewOrder.OrderQuantity = Contracts;
        NewOrder.Stop1Offset = StopDistance;
        NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;
        sc.SellEntry(NewOrder);
    }
}
