#include "sierrachart.h"

SCDLLName("Turtle Breakout Strategy 2.0")

/*==========================================================================
  Turtle Breakout Strategy 2.0 — Nasdaq 100 Futures, 60-minute chart

  Entry:
    LONG  - Close > 200 MA AND Close > prior 40-bar high
    SHORT - Close < 200 MA AND Close < prior 40-bar low

  Exit:
    Stop loss   - 2 x ATR(20), fixed price set at entry (attached stop order)
    Take profit - structural: close LONG on a close below the 40-bar low,
                  close SHORT on a close above the 40-bar high
    Trailing    - once price has moved Breakeven Trigger x ATR in favor,
                  the stop is armed at breakeven and then trails as a
                  chandelier ATR stop (highest high since entry minus
                  Chandelier Multiplier x ATR, mirrored for shorts). The
                  fixed 2xATR stop is still a real attached order, so Sierra
                  Chart draws its native working-order line as always; the
                  trailing/chandelier level is not a resting order (this
                  study fires its own market exit once price crosses it),
                  so it is additionally plotted as its own subgraph line
                  ("Trailing Stop Level") to make it visible while in a trade.

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
    SCInputRef Input_MaxContracts     = sc.Input[6];
    SCInputRef Input_AllowLong        = sc.Input[7];
    SCInputRef Input_AllowShort       = sc.Input[8];
    SCInputRef Input_SendOrdersToTradeService = sc.Input[9];
    SCInputRef Input_EnableTrailingStop      = sc.Input[10];
    SCInputRef Input_BreakevenTriggerATR     = sc.Input[11];
    SCInputRef Input_ChandelierATRMultiplier = sc.Input[12];

    SCSubgraphRef Subgraph_MA            = sc.Subgraph[0];
    SCSubgraphRef Subgraph_UpperBreakout = sc.Subgraph[1];
    SCSubgraphRef Subgraph_LowerBreakout = sc.Subgraph[2];
    SCSubgraphRef Subgraph_ATR           = sc.Subgraph[3];
    SCSubgraphRef Subgraph_TrailStopLevel = sc.Subgraph[4];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Turtle Breakout Strategy 2.0";
        sc.StudyDescription = "Turtle-style breakout: 200 MA trend filter + 40-bar Donchian entry, ATR stop, structural exit, breakeven + chandelier ATR trailing, risk-based sizing. NQ futures, 60-minute bars.";

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

        sc.Subgraph[4].Name = "Trailing Stop Level";
        sc.Subgraph[4].DrawStyle = DRAWSTYLE_LINE;
        sc.Subgraph[4].PrimaryColor = RGB(255, 140, 0);
        sc.Subgraph[4].LineWidth = 2;

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

        Input_MaxContracts.Name = "Max Contracts Per Trade";
        Input_MaxContracts.SetInt(50);

        Input_AllowLong.Name = "Allow Long Trades";
        Input_AllowLong.SetYesNo(1);

        Input_AllowShort.Name = "Allow Short Trades";
        Input_AllowShort.SetYesNo(1);

        // Must match the global Trade >> Trade Simulation Mode On setting, or all
        // order actions will be silently ignored (Sierra Chart logs "SendOrdersToTradeService
        // is not consistent with Trade Simulation Mode On setting").
        //   Trade Simulation Mode ON  (checked, e.g. during Replay)  -> set this to No
        //   Trade Simulation Mode OFF (unchecked, e.g. live/Sim1 acct) -> set this to Yes
        // Check Trade >> Trade Simulation Mode On in Sierra Chart before starting Replay,
        // and set this input to match, rather than editing code per session.
        Input_SendOrdersToTradeService.Name = "Send Orders To Trade Service (No = internal Trade Simulation Mode)";
        Input_SendOrdersToTradeService.SetYesNo(0);

        Input_EnableTrailingStop.Name = "Enable Breakeven + Chandelier Trailing";
        Input_EnableTrailingStop.SetYesNo(1);

        Input_BreakevenTriggerATR.Name = "Breakeven Trigger (x ATR)";
        Input_BreakevenTriggerATR.SetFloat(1.0f);

        Input_ChandelierATRMultiplier.Name = "Chandelier Trailing Multiplier (x ATR)";
        Input_ChandelierATRMultiplier.SetFloat(3.0f);

        sc.SupportReversals = 1;
        sc.CancelAllOrdersOnEntriesAndReversals = 1;

        return;
    }

    // Per Sierra Chart docs, sc.SendOrdersToTradeService must be (re)assigned outside of
    // the sc.SetDefaults block for an Input-driven value to take effect.
    sc.SendOrdersToTradeService = Input_SendOrdersToTradeService.GetYesNo();

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
    float CurrentATR = Subgraph_ATR[Index];
    float StopDistance = Input_ATRStopMultiplier.GetFloat() * CurrentATR;

    s_SCPositionData Position;
    sc.GetTradePosition(Position);
    int PositionQty = Position.PositionQuantity;

    bool TrailingEnabled = Input_EnableTrailingStop.GetYesNo() != 0;

    // Persistent trailing-stop state, carried across bars for the open position.
    // (Persistent int slot 1 is already used below for LastEntryBarIndex, so
    // BreakevenArmed uses slot 2 to avoid colliding with it.)
    float& HighestHighSinceEntry = sc.GetPersistentFloat(1);
    float& LowestLowSinceEntry   = sc.GetPersistentFloat(2);
    float& EntryATR              = sc.GetPersistentFloat(3);
    int&   BreakevenArmed        = sc.GetPersistentInt(2);

    // Update trailing extremes/arming and compute the effective stop level for
    // this bar, used both for the trailing-exit check below and for the
    // on-chart "Trailing Stop Level" plot.
    float EffectiveStopLevel = Close; // flat: hug price so the line stays out of the way
    if (PositionQty > 0)
    {
        if (sc.High[Index] > HighestHighSinceEntry)
            HighestHighSinceEntry = sc.High[Index];

        if (!BreakevenArmed && EntryATR > 0 &&
            sc.High[Index] - Position.AveragePrice >= Input_BreakevenTriggerATR.GetFloat() * EntryATR)
        {
            BreakevenArmed = 1;
        }

        if (TrailingEnabled && BreakevenArmed)
        {
            EffectiveStopLevel = HighestHighSinceEntry - Input_ChandelierATRMultiplier.GetFloat() * EntryATR;
            if (EffectiveStopLevel < Position.AveragePrice)
                EffectiveStopLevel = Position.AveragePrice; // once armed, never trail below breakeven
        }
        else if (EntryATR > 0)
        {
            EffectiveStopLevel = Position.AveragePrice - Input_ATRStopMultiplier.GetFloat() * EntryATR;
        }
    }
    else if (PositionQty < 0)
    {
        if (LowestLowSinceEntry == 0 || sc.Low[Index] < LowestLowSinceEntry)
            LowestLowSinceEntry = sc.Low[Index];

        if (!BreakevenArmed && EntryATR > 0 &&
            Position.AveragePrice - sc.Low[Index] >= Input_BreakevenTriggerATR.GetFloat() * EntryATR)
        {
            BreakevenArmed = 1;
        }

        if (TrailingEnabled && BreakevenArmed)
        {
            EffectiveStopLevel = LowestLowSinceEntry + Input_ChandelierATRMultiplier.GetFloat() * EntryATR;
            if (EffectiveStopLevel > Position.AveragePrice)
                EffectiveStopLevel = Position.AveragePrice; // once armed, never trail above breakeven
        }
        else if (EntryATR > 0)
        {
            EffectiveStopLevel = Position.AveragePrice + Input_ATRStopMultiplier.GetFloat() * EntryATR;
        }
    }
    else
    {
        // Flat: reset trailing state so the next entry starts clean.
        HighestHighSinceEntry = 0;
        LowestLowSinceEntry = 0;
        EntryATR = 0;
        BreakevenArmed = 0;
    }
    Subgraph_TrailStopLevel[Index] = EffectiveStopLevel;

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

    // Trailing exit: once armed, flatten if price closes back through the
    // chandelier level computed above (and already plotted for this bar).
    if (PositionQty > 0 && TrailingEnabled && BreakevenArmed && Close < EffectiveStopLevel)
    {
        s_SCNewOrder ExitOrder;
        ExitOrder.OrderQuantity = PositionQty;
        sc.SellExit(ExitOrder);
        return;
    }
    if (PositionQty < 0 && TrailingEnabled && BreakevenArmed && Close > EffectiveStopLevel)
    {
        s_SCNewOrder ExitOrder;
        ExitOrder.OrderQuantity = -PositionQty;
        sc.BuyExit(ExitOrder);
        return;
    }

    if (PositionQty != 0)
        return; // already in a trade, nothing else to do this bar

    // Guard against duplicate entries on the same bar. In Replay/Simulation, ACSIL
    // can call the study function more than once for the same closed bar before
    // sc.GetTradePosition() reflects the fill from the first call. Without this
    // check, two full-size entries can be sent for a single signal.
    int& LastEntryBarIndex = sc.GetPersistentInt(1);
    if (Index == LastEntryBarIndex)
        return;

    // Position sizing: risk a fixed % of equity, sized off the ATR stop distance.
    // sc.CurrencyValuePerTick is the $ value of one tick; divide by TickSize to get $ per full point.
    double PointValue = sc.TickSize > 0 ? sc.CurrencyValuePerTick / sc.TickSize : 0;

    int Contracts = 1;
    if (StopDistance > 0 && PointValue > 0)
    {
        double RiskDollars = Input_AccountEquity.GetDouble() * (Input_RiskPercent.GetFloat() / 100.0);
        Contracts = (int)(RiskDollars / (StopDistance * PointValue));
        if (Contracts < 1)
            Contracts = 1;
    }
    if (Contracts > Input_MaxContracts.GetInt())
        Contracts = Input_MaxContracts.GetInt();

    if (Input_AllowLong.GetYesNo() && Close > MAValue && Close > PriorHigh)
    {
        s_SCNewOrder NewOrder;
        NewOrder.OrderQuantity = Contracts;
        NewOrder.Stop1Offset = StopDistance;
        NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;
        sc.BuyEntry(NewOrder);
        LastEntryBarIndex = Index;
        HighestHighSinceEntry = sc.High[Index];
        EntryATR = CurrentATR;
        BreakevenArmed = 0;
    }
    else if (Input_AllowShort.GetYesNo() && Close < MAValue && Close < PriorLow)
    {
        s_SCNewOrder NewOrder;
        NewOrder.OrderQuantity = Contracts;
        NewOrder.Stop1Offset = StopDistance;
        NewOrder.AttachedOrderStop1Type = SCT_ORDERTYPE_STOP;
        sc.SellEntry(NewOrder);
        LastEntryBarIndex = Index;
        LowestLowSinceEntry = sc.Low[Index];
        EntryATR = CurrentATR;
        BreakevenArmed = 0;
    }
}
