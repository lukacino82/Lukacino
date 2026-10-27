#include "sierrachart.h"
#include <cmath>
#include <algorithm>

SCDLLName("ES Order Flow Absorption Detector v2")

// Bar-level volume statistics from Volume at Price data: volume traded within
// zoneTicks of the bar high and of the bar low, plus the number of price levels.
static bool GetBarLevelStats(SCStudyInterfaceRef sc, int barIndex, int zoneTicks,
                             float& highZoneVol, float& lowZoneVol, int& levels)
{
    int size = 0;
    sc.VolumeAtPriceForBars->GetSizeAtBarIndex(barIndex, size);
    if (size <= 0)
        return false;

    const int highTicks = sc.PriceValueToTicks(sc.High[barIndex]);
    const int lowTicks = sc.PriceValueToTicks(sc.Low[barIndex]);
    highZoneVol = 0.0f;
    lowZoneVol = 0.0f;
    levels = size;

    for (int k = 0; k < size; ++k)
    {
        const s_VolumeAtPriceV2* p = NULL;
        sc.VolumeAtPriceForBars->GetVAPElementAtIndex(barIndex, k, &p);
        if (p == NULL)
            continue;
        const float v = (float)p->Volume;
        if (p->PriceInTicks >= highTicks - zoneTicks)
            highZoneVol += v;
        if (p->PriceInTicks <= lowTicks + zoneTicks)
            lowZoneVol += v;
    }
    return true;
}

SCSFExport scsf_ESAbsorptionDetectorV2(SCStudyInterfaceRef sc)
{
    SCSubgraphRef LongWatch = sc.Subgraph[0];
    SCSubgraphRef ShortWatch = sc.Subgraph[1];
    SCSubgraphRef LongTrigger = sc.Subgraph[2];
    SCSubgraphRef ShortTrigger = sc.Subgraph[3];
    SCSubgraphRef Wins = sc.Subgraph[4];
    SCSubgraphRef Losses = sc.Subgraph[5];
    SCSubgraphRef Timeouts = sc.Subgraph[6];
    SCSubgraphRef WinRate = sc.Subgraph[7];
    SCSubgraphRef State = sc.Subgraph[8];   // Arrays: 0 direction, 1 entry, 2 result (1 win, -1 loss, 2 timeout)
    SCSubgraphRef Resolve = sc.Subgraph[9]; // Arrays: 0 bar index at which the trigger was resolved

    SCInputRef Mode = sc.Input[0];
    SCInputRef Lookback = sc.Input[1];
    SCInputRef DeltaThreshold = sc.Input[2];
    SCInputRef MinVolumeRatio = sc.Input[3];
    SCInputRef ZoneTicks = sc.Input[4];
    SCInputRef ThinRatio = sc.Input[5];
    SCInputRef VAH = sc.Input[6];
    SCInputRef VAL = sc.Input[7];
    SCInputRef TargetTicks = sc.Input[8];
    SCInputRef StopTicks = sc.Input[9];
    SCInputRef HorizonBars = sc.Input[10];

    if (sc.SetDefaults)
    {
        sc.GraphName = "ES Absorption + Failed Auction + Delta Reversal v2 (unverified)";
        sc.StudyDescription = "Closed-bar detector: delta/price divergence (absorption) and thin-extreme failed auction using Volume at Price, "
                              "next-bar confirmation and forward win/loss statistics. Not compiled or backtested by the author.";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.MaintainAdditionalChartDataArrays = 0;
        sc.MaintainVolumeAtPriceData = 1;

        LongWatch.Name = "Seller Absorption / Failed Low Watch";
        LongWatch.DrawStyle = DRAWSTYLE_POINT_ON_LOW;
        LongWatch.PrimaryColor = RGB(255, 190, 0);
        LongWatch.LineWidth = 5;
        ShortWatch.Name = "Buyer Absorption / Failed High Watch";
        ShortWatch.DrawStyle = DRAWSTYLE_POINT_ON_HIGH;
        ShortWatch.PrimaryColor = RGB(255, 190, 0);
        ShortWatch.LineWidth = 5;
        LongTrigger.Name = "LONG Confirmation";
        LongTrigger.DrawStyle = DRAWSTYLE_ARROW_UP;
        LongTrigger.PrimaryColor = RGB(0, 180, 0);
        LongTrigger.LineWidth = 4;
        ShortTrigger.Name = "SHORT Confirmation";
        ShortTrigger.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        ShortTrigger.PrimaryColor = RGB(220, 0, 0);
        ShortTrigger.LineWidth = 4;

        Wins.Name = "Cumulative wins";
        Wins.DrawStyle = DRAWSTYLE_IGNORE;
        Losses.Name = "Cumulative losses";
        Losses.DrawStyle = DRAWSTYLE_IGNORE;
        Timeouts.Name = "Cumulative timeouts";
        Timeouts.DrawStyle = DRAWSTYLE_IGNORE;
        WinRate.Name = "Win rate % (wins / (wins + losses))";
        WinRate.DrawStyle = DRAWSTYLE_IGNORE;
        State.Name = "State (internal)";
        State.DrawStyle = DRAWSTYLE_IGNORE;
        Resolve.Name = "Resolve (internal)";
        Resolve.DrawStyle = DRAWSTYLE_IGNORE;

        Mode.Name = "Pattern mode (0 both, 1 absorption only, 2 failed auction only)";
        Mode.SetInt(0);
        Mode.SetIntLimits(0, 2);
        Lookback.Name = "Average volume lookback";
        Lookback.SetInt(20);
        Lookback.SetIntLimits(5, 500);
        DeltaThreshold.Name = "Minimum absolute delta fraction of bar volume";
        DeltaThreshold.SetFloat(0.15f);
        DeltaThreshold.SetFloatLimits(0.01f, 1.0f);
        MinVolumeRatio.Name = "Bar volume / previous average minimum";
        MinVolumeRatio.SetFloat(1.5f);
        ZoneTicks.Name = "Extreme zone size (ticks below high / above low)";
        ZoneTicks.SetInt(2);
        ZoneTicks.SetIntLimits(0, 20);
        ThinRatio.Name = "Thin extreme: zone volume / expected zone volume maximum";
        ThinRatio.SetFloat(0.35f);
        ThinRatio.SetFloatLimits(0.01f, 1.0f);
        VAH.Name = "Composite VAH (0 = not required)";
        VAH.SetFloat(0.0f);
        VAL.Name = "Composite VAL (0 = not required)";
        VAL.SetFloat(0.0f);
        TargetTicks.Name = "Target after entry (ticks)";
        TargetTicks.SetInt(16);
        TargetTicks.SetIntLimits(1, 2000);
        StopTicks.Name = "Stop after entry (ticks)";
        StopTicks.SetInt(8);
        StopTicks.SetIntLimits(1, 2000);
        HorizonBars.Name = "Bars to resolve a trigger before timeout";
        HorizonBars.SetInt(10);
        HorizonBars.SetIntLimits(1, 500);
        return;
    }

    const int i = sc.Index;
    LongWatch[i] = ShortWatch[i] = LongTrigger[i] = ShortTrigger[i] = 0.0f;
    State.Arrays[0][i] = 0.0f;
    State.Arrays[1][i] = 0.0f;
    State.Arrays[2][i] = 0.0f;
    Resolve.Arrays[0][i] = 0.0f;
    Wins[i] = i > 0 ? Wins[i - 1] : 0.0f;
    Losses[i] = i > 0 ? Losses[i - 1] : 0.0f;
    Timeouts[i] = i > 0 ? Timeouts[i - 1] : 0.0f;

    const bool barClosed = sc.GetBarHasClosedStatus(i) == BHCS_BAR_HAS_CLOSED;

    // Resolve earlier triggers against this bar. Re-running the same closed bar gives the same counts.
    if (barClosed)
    {
        const float target = TargetTicks.GetInt() * sc.TickSize;
        const float stop = StopTicks.GetInt() * sc.TickSize;
        const int horizon = HorizonBars.GetInt();

        for (int j = std::max(0, i - horizon); j < i; ++j)
        {
            const float dir = State.Arrays[0][j];
            if (dir == 0.0f)
                continue;
            const bool pending = State.Arrays[2][j] == 0.0f;
            if (!pending && Resolve.Arrays[0][j] != (float)i)
                continue;

            const float entry = State.Arrays[1][j];
            float outcome = 0.0f;
            if (dir > 0.0f)
            {
                if (sc.Low[i] <= entry - stop) outcome = -1.0f;        // stop is checked first
                else if (sc.High[i] >= entry + target) outcome = 1.0f;
            }
            else
            {
                if (sc.High[i] >= entry + stop) outcome = -1.0f;
                else if (sc.Low[i] <= entry - target) outcome = 1.0f;
            }
            if (outcome == 0.0f && i - j >= horizon)
                outcome = 2.0f;
            if (outcome == 0.0f)
                continue;

            State.Arrays[2][j] = outcome;
            Resolve.Arrays[0][j] = (float)i;
            if (outcome == 1.0f) Wins[i] += 1.0f;
            else if (outcome == -1.0f) Losses[i] += 1.0f;
            else Timeouts[i] += 1.0f;
        }
    }

    const float decided = Wins[i] + Losses[i];
    WinRate[i] = decided > 0.0f ? 100.0f * Wins[i] / decided : 0.0f;

    int& LastLogged = sc.GetPersistentInt(1);
    if (i == sc.ArraySize - 1 && LastLogged != i)
    {
        LastLogged = i;
        SCString msg;
        msg.Format("Absorption v2: wins %d, losses %d, timeouts %d, win rate %.1f%%",
                   (int)Wins[i], (int)Losses[i], (int)Timeouts[i], WinRate[i]);
        sc.AddMessageToLog(msg, 0);
    }

    if (!barClosed || i < Lookback.GetInt() + 1)
        return;

    float avgVolume = 0.0f;
    for (int j = i - Lookback.GetInt(); j < i; ++j)
        avgVolume += sc.Volume[j];
    avgVolume /= Lookback.GetInt();

    const float volume = sc.Volume[i];
    if (volume <= 0.0f || avgVolume <= 0.0f)
        return;

    const float delta = sc.AskVolume[i] - sc.BidVolume[i];
    const float deltaFraction = delta / volume;
    const bool elevated = volume >= avgVolume * MinVolumeRatio.GetFloat();
    const bool brickUp = sc.Close[i] >= sc.Open[i];
    const bool brickDown = sc.Close[i] <= sc.Open[i];
    const int mode = Mode.GetInt();

    // Pattern 1: delta against price. Heavy selling but the bar did not close lower (and the reverse).
    const bool sellerAbsorption = elevated && deltaFraction <= -DeltaThreshold.GetFloat() && brickUp;
    const bool buyerAbsorption = elevated && deltaFraction >= DeltaThreshold.GetFloat() && brickDown;

    // Pattern 2: failed auction. Thin volume at the extreme of the bar, optionally outside the composite value area.
    bool failedHigh = false;
    bool failedLow = false;
    if (mode != 1)
    {
        float highZoneVol = 0.0f, lowZoneVol = 0.0f;
        int levels = 0;
        if (GetBarLevelStats(sc, i, ZoneTicks.GetInt(), highZoneVol, lowZoneVol, levels) && levels > 0)
        {
            const float expectedZone = (volume / levels) * (ZoneTicks.GetInt() + 1);
            const float limit = ThinRatio.GetFloat() * expectedZone;
            failedHigh = brickUp && !brickDown && highZoneVol <= limit && (VAH.GetFloat() <= 0.0f || sc.High[i] > VAH.GetFloat());
            failedLow = brickDown && !brickUp && lowZoneVol <= limit && (VAL.GetFloat() <= 0.0f || sc.Low[i] < VAL.GetFloat());
        }
    }

    const bool longCandidate = (mode != 2 && sellerAbsorption) || failedLow;
    const bool shortCandidate = (mode != 2 && buyerAbsorption) || failedHigh;

    if (longCandidate && !shortCandidate) LongWatch[i] = sc.Low[i] - sc.TickSize;
    if (shortCandidate && !longCandidate) ShortWatch[i] = sc.High[i] + sc.TickSize;

    // Confirmation: next closed bar exceeds the candidate bar extreme with delta in the trade direction.
    const int p = i - 1;
    if (LongWatch[p] != 0.0f && sc.Close[i] > sc.High[p] && delta > 0.0f)
    {
        LongTrigger[i] = sc.Low[i] - 2.0f * sc.TickSize;
        State.Arrays[0][i] = 1.0f;
        State.Arrays[1][i] = sc.Close[i];
    }
    else if (ShortWatch[p] != 0.0f && sc.Close[i] < sc.Low[p] && delta < 0.0f)
    {
        ShortTrigger[i] = sc.High[i] + 2.0f * sc.TickSize;
        State.Arrays[0][i] = -1.0f;
        State.Arrays[1][i] = sc.Close[i];
    }
}
