#include "sierrachart.h"

SCDLLName("Turtle Breakout Strategy")

/*==========================================================================
  Turtle Breakout Strategy
  --------------------------------------------------------------------------
  Simplified Turtle-style breakout system, intended for the 60-minute
  timeframe on Nasdaq 100 Futures (set the chart's bar period accordingly).

  Entry:
    LONG  - Close > 200-period MA AND Close > prior N-bar high
    SHORT - Close < 200-period MA AND Close < prior N-bar low

  Exit:
    Stop loss  - 2 x ATR(20), set as a fixed-price stop at entry
    Take profit - structural: close LONG on a close below the recent
                  N-bar low, close SHORT on a close above the recent
                  N-bar high (no fixed profit target)

  Position sizing:
    Contracts = floor( (Equity x Risk%) / (StopDistancePoints x PointValue) )
    capped at Max Contracts Per Trade.
==========================================================================*/

SCSFExport scsf_TurtleBreakoutStrategy(SCStudyInterfaceRef sc)
{
    SCInputRef Input_MALength           = sc.Input[0];
    SCInputRef Input_BreakoutLength      = sc.Input[1];
    SCInputRef Input_ATRLength           = sc.Input[2];
    SCInputRef Input_ATRStopMultiplier   = sc.Input[3];
    SCInputRef Input_AccountEquity       = sc.Input[4];
    SCInputRef Input_RiskPercent         = sc.Input[5];
    SCInputRef Input_MaxContracts        = sc.Input[6];
    SCInputRef Input_AllowLong           = sc.Input[7];
    SCInputRef Input_AllowShort          = sc.Input[8];
    SCInputRef Input_Enabled             = sc.Input[9];

    SCSubgraphRef Subgraph_MA            = sc.Subgraph[0];
    SCSubgraphRef Subgraph_UpperBreakout = sc.Subgraph[1];
    SCSubgraphRef Subgraph_LowerBreakout = sc.Subgraph[2];
    SCSubgraphRef Subgraph_ATR           = sc.Subgraph[3];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Turtle Breakout Strategy";
        sc.StudyDescription =
            "Simplified Turtle-style breakout strategy. Long above the 200 MA "
            "on a close above the prior N-bar high, short below the 200 MA on "
            "a close below the prior N-bar low. Stop = ATR multiple. Exit on "
            "opposite channel break. Position sized to risk a fixed % of "
            "account equity per trade. Intended for NQ futures, 60-minute bars.";

        sc.AutoLoop = 1;
        sc.GraphRegion = 0;

        sc.Subgraph[0].Name = "Trend MA";
        sc.Subgraph[0].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[0].PrimaryColor = RGB(255, 255, 0);

        sc.Subgraph[1].Name = "N-Bar High";
        sc.Subgraph[1].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[1].PrimaryColor = RGB(0, 255, 0);

        sc.Subgraph[2].Name = "N-Bar Low";
        sc.Subgraph[2].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[2].PrimaryColor = RGB(255, 0, 0);

        sc.Subgraph[3].Name = "ATR";
        sc.Subgraph[3].DrawStyle = DRAWSTYLE_IGNORE;

        Input_MALength.Name = "Trend MA Length";
        Input_MALength.SetInt(200);
        Input_MALength.SetIntLimits(1, 2000);

        Input_BreakoutLength.Name = "Breakout Lookback (bars)";
        Input_BreakoutLength.SetInt(40);
        Input_BreakoutLength.SetIntLimits(2, 500);

        Input_ATRLength.Name = "ATR Length";
        Input_ATRLength.SetInt(20);
        Input_ATRLength.SetIntLimits(1, 500);

        Input_ATRStopMultiplier.Name = "ATR Stop Multiplier";
        Input_ATRStopMultiplier.SetFloat(2.0f);
        Input_ATRStopMultiplier.SetFloatLimits(0.1f, 20.0f);

        Input_AccountEquity.Name = "Account Equity ($)";
        Input_AccountEquity.SetDouble(100000.0);
        Input_AccountEquity.SetDoubleLimits(0.0, 1000000000.0);

        Input_RiskPercent.Name = "Risk Per Trade (% of Equity)";
        Input_RiskPercent.SetFloat(2.0f);
        Input_RiskPercent.SetFloatLimits(0.01f, 100.0f);

        Input_MaxContracts.Name = "Max Contracts Per Trade";
        Input_MaxContracts.SetInt(50);
        Input_MaxContracts.SetIntLimits(1, 10000);

        Input_AllowLong.Name = "Allow Long Trades";
        Input_AllowLong.SetYesNo(1);

        Input_AllowShort.Name = "Allow Short Trades";
        Input_AllowShort.SetYesNo(1);

        Input_Enabled.Name = "Strategy Enabled (Auto Trading)";
        Input_Enabled.SetYesNo(0);

        sc.AllowMultipleEntriesInSameDirection = 0;
        sc.MaximumPositionAllowed = 100000;
        sc.SupportReversals = 1;
        sc.SendOrdersToTradeService = 1;
        sc.AllowOppositeEntryWithOpposingPositionOrOrders = 1;
        sc.CancelAllOrdersOnEntriesAndReversals = 1;

        return;
    }

    int MALength         = Input_MALength.GetInt();
    int BreakoutLength    = Input_BreakoutLength.GetInt();
    int ATRLength         = Input_ATRLength.GetInt();
    float ATRMultiplier   = Input_ATRStopMultiplier.GetFloat();

    sc.SimpleMovAvg(sc.Close, Subgraph_MA, MALength);
    sc.Highest(sc.High, Subgraph_UpperBreakout, BreakoutLength);
    sc.Lowest(sc.Low, Subgraph_LowerBreakout, BreakoutLength);
    sc.ATR(sc.BaseDataIn, Subgraph_ATR, ATRLength, MOVAVGTYPE_SIMPLE);

    int Index = sc.Index;

    // Need enough history for the longest lookback plus one prior bar for
    // the breakout reference level.
    if (Index < MALength || Index <= BreakoutLength || Index < ATRLength)
        return;

    // Only act once a bar has fully closed (avoid acting on an in-progress bar).
    if (sc.GetBarHasClosedStatus(Index) != BHCS_BAR_HAS_CLOSED)
        return;

    if (Input_Enabled.GetYesNo() == 0)
        return;

    float Close = sc.Close[Index];
    float MAValue = Subgraph_MA[Index];
    // Prior N-bar high/low, excluding the just-closed bar itself.
    float PriorUpperBreakout = Subgraph_UpperBreakout[Index - 1];
    float PriorLowerBreakout = Subgraph_LowerBreakout[Index - 1];
    float ATRValue = Subgraph_ATR[Index];

    s_SCPositionData PositionData;
    sc.GetTradePosition(PositionData);
    int CurrentPosition = PositionData.PositionQuantity; // >0 long, <0 short

    bool LongSignal  = Input_AllowLong.GetYesNo()  != 0 && Close > MAValue && Close > PriorUpperBreakout;
    bool ShortSignal = Input_AllowShort.GetYesNo() != 0 && Close < MAValue && Close < PriorLowerBreakout;

    bool ExitLongStructural  = Close < PriorLowerBreakout;
    bool ExitShortStructural = Close > PriorUpperBreakout;

    double StopDistancePoints = (double)ATRMultiplier * (double)ATRValue;

    int Contracts = 1;
    if (StopDistancePoints > 0.0 && sc.PointValue > 0.0)
    {
        double RiskDollars = Input_AccountEquity.GetDouble() * ((double)Input_RiskPercent.GetFloat() / 100.0);
        double DollarRiskPerContract = StopDistancePoints * sc.PointValue;
        if (DollarRiskPerContract > 0.0)
            Contracts = (int)(RiskDollars / DollarRiskPerContract);
    }
    if (Contracts < 1)
        Contracts = 1;
    if (Contracts > Input_MaxContracts.GetInt())
        Contracts = Input_MaxContracts.GetInt();

    bool JustExited = false;

    // Manage structural exit of an existing position first.
    if (CurrentPosition > 0 && ExitLongStructural)
    {
        s_SCNewOrder ExitOrder;
        ExitOrder.OrderQuantity = CurrentPosition;
        ExitOrder.OrderType = SCT_ORDERTYPE_MARKET;
        sc.SellExit(ExitOrder);
        JustExited = true;
    }
    else if (CurrentPosition < 0 && ExitShortStructural)
    {
        s_SCNewOrder ExitOrder;
        ExitOrder.OrderQuantity = -CurrentPosition;
        ExitOrder.OrderType = SCT_ORDERTYPE_MARKET;
        sc.BuyExit(ExitOrder);
        JustExited = true;
    }

    // Only look for a new entry when flat and we didn't just exit this bar.
    if (CurrentPosition == 0 && !JustExited)
    {
        if (LongSignal)
        {
            s_SCNewOrder NewOrder;
            NewOrder.OrderQuantity = Contracts;
            NewOrder.OrderType = SCT_ORDERTYPE_MARKET;
            NewOrder.Stop1Offset = (float)StopDistancePoints;
            NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;
            sc.BuyEntry(NewOrder);
        }
        else if (ShortSignal)
        {
            s_SCNewOrder NewOrder;
            NewOrder.OrderQuantity = Contracts;
            NewOrder.OrderType = SCT_ORDERTYPE_MARKET;
            NewOrder.Stop1Offset = (float)StopDistancePoints;
            NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;
            sc.SellEntry(NewOrder);
        }
    }
}
