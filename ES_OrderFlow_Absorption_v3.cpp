#include "sierrachart.h"
#include <cmath>
#include <algorithm>
#include <map>

SCDLLName("ES Order Flow Absorption Detector v3")

// Everything read from the Volume at Price data of one closed bar.
struct BarFootprint
{
    int levels;
    float totalVolume;
    float maxLevelVolume;   // volume of the busiest price level (bar POC)
    float pocPrice;
    float pocDelta;
    float maxLevelDelta;    // most positive per-level delta (ask - bid)
    float minLevelDelta;    // most negative per-level delta
    float highZoneVol;      // volume within zoneTicks of the bar high
    float highZoneDelta;
    float lowZoneVol;       // volume within zoneTicks of the bar low
    float lowZoneDelta;
    int bigLevels;          // levels with volume >= bigLevelVol
    int stackedBuy;         // longest run of consecutive diagonal buy imbalances
    int stackedSell;        // longest run of consecutive diagonal sell imbalances
};

static bool ReadFootprint(SCStudyInterfaceRef sc, int idx, int zoneTicks, float imbalanceRatio,
                          float bigLevelVol, BarFootprint& fp)
{
    int size = 0;
    sc.VolumeAtPriceForBars->GetSizeAtBarIndex(idx, size);
    if (size <= 0)
        return false;

    std::map<int, std::pair<float, float> > lv; // price in ticks -> (bid volume, ask volume)
    for (int k = 0; k < size; ++k)
    {
        const s_VolumeAtPriceV2* p = NULL;
        sc.VolumeAtPriceForBars->GetVAPElementAtIndex(idx, k, &p);
        if (p == NULL)
            continue;
        lv[(int)p->PriceInTicks] = std::make_pair((float)p->BidVolume, (float)p->AskVolume);
    }
    if (lv.empty())
        return false;

    fp = BarFootprint();
    fp.levels = (int)lv.size();
    const int highTicks = sc.PriceValueToTicks(sc.High[idx]);
    const int lowTicks = sc.PriceValueToTicks(sc.Low[idx]);

    typedef std::map<int, std::pair<float, float> >::const_iterator Iter;
    for (Iter it = lv.begin(); it != lv.end(); ++it)
    {
        const int t = it->first;
        const float bid = it->second.first;
        const float ask = it->second.second;
        const float vol = bid + ask;
        const float d = ask - bid;

        fp.totalVolume += vol;
        if (vol > fp.maxLevelVolume)
        {
            fp.maxLevelVolume = vol;
            fp.pocPrice = t * sc.TickSize;
            fp.pocDelta = d;
        }
        fp.maxLevelDelta = std::max(fp.maxLevelDelta, d);
        fp.minLevelDelta = std::min(fp.minLevelDelta, d);
        if (bigLevelVol > 0.0f && vol >= bigLevelVol)
            ++fp.bigLevels;
        if (t >= highTicks - zoneTicks)
        {
            fp.highZoneVol += vol;
            fp.highZoneDelta += d;
        }
        if (t <= lowTicks + zoneTicks)
        {
            fp.lowZoneVol += vol;
            fp.lowZoneDelta += d;
        }
    }

    // Diagonal imbalances: ask at P against bid one tick below, bid at P against ask one tick above.
    int buyRun = 0, sellRun = 0;
    for (Iter it = lv.begin(); it != lv.end(); ++it)
    {
        const int t = it->first;
        const float bid = it->second.first;
        const float ask = it->second.second;
        Iter below = lv.find(t - 1);
        Iter above = lv.find(t + 1);
        const bool buyImb = below != lv.end() && ask >= imbalanceRatio * std::max(below->second.first, 1.0f);
        const bool sellImb = above != lv.end() && bid >= imbalanceRatio * std::max(above->second.second, 1.0f);
        buyRun = buyImb ? buyRun + 1 : 0;
        sellRun = sellImb ? sellRun + 1 : 0;
        fp.stackedBuy = std::max(fp.stackedBuy, buyRun);
        fp.stackedSell = std::max(fp.stackedSell, sellRun);
    }
    return true;
}

SCSFExport scsf_ESAbsorptionDetectorV3(SCStudyInterfaceRef sc)
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
    SCSubgraphRef DeltaSG = sc.Subgraph[10];
    SCSubgraphRef DeltaPctSG = sc.Subgraph[11];
    SCSubgraphRef DeltaChgSG = sc.Subgraph[12];
    SCSubgraphRef CumDeltaSG = sc.Subgraph[13];
    SCSubgraphRef VolRatioSG = sc.Subgraph[14];   // bar volume / average of previous bars
    SCSubgraphRef VolJumpSG = sc.Subgraph[15];    // bar volume / previous bar volume
    SCSubgraphRef MaxLevelSG = sc.Subgraph[16];   // busiest level volume
    SCSubgraphRef PocDeltaSG = sc.Subgraph[17];   // delta at the busiest level
    SCSubgraphRef BigLevelsSG = sc.Subgraph[18];  // number of big-volume levels
    SCSubgraphRef StackBuySG = sc.Subgraph[19];
    SCSubgraphRef StackSellSG = sc.Subgraph[20];
    SCSubgraphRef AvgLevelSG = sc.Subgraph[21];   // bar volume per price level (basis for "big level")
    SCSubgraphRef ReasonSG = sc.Subgraph[22];     // bitmask of the watch: 1 divergence, 2 thin extreme, 4 big volume at extreme

    SCInputRef Lookback = sc.Input[0];
    SCInputRef DeltaThreshold = sc.Input[1];
    SCInputRef MinVolumeRatio = sc.Input[2];
    SCInputRef ZoneTicks = sc.Input[3];
    SCInputRef ThinRatio = sc.Input[4];
    SCInputRef BigZoneMult = sc.Input[5];
    SCInputRef BigLevelMult = sc.Input[6];
    SCInputRef ImbalanceRatio = sc.Input[7];
    SCInputRef StackCount = sc.Input[8];
    SCInputRef VAH = sc.Input[9];
    SCInputRef VAL = sc.Input[10];
    SCInputRef TargetTicks = sc.Input[11];
    SCInputRef StopTicks = sc.Input[12];
    SCInputRef HorizonBars = sc.Input[13];
    SCInputRef UseDivergence = sc.Input[14];
    SCInputRef UseThinExtreme = sc.Input[15];
    SCInputRef UseBigVolume = sc.Input[16];
    SCInputRef RequireStacked = sc.Input[17];
    SCInputRef AlertsOn = sc.Input[18];
    SCInputRef ZoneDeltaFraction = sc.Input[19];

    if (sc.SetDefaults)
    {
        sc.GraphName = "ES Order Flow Absorption v3 (footprint + delta, unverified)";
        sc.StudyDescription = "Reads delta metrics and Volume at Price per closed bar, flags absorption (yellow dots) and confirmed reversals "
                              "(arrows), and keeps forward win/loss statistics. Not compiled or backtested by the author.";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.MaintainAdditionalChartDataArrays = 0;
        sc.MaintainVolumeAtPriceData = 1;

        LongWatch.Name = "Seller Absorption Watch (yellow dot below bar)";
        LongWatch.DrawStyle = DRAWSTYLE_POINT_ON_LOW;
        LongWatch.PrimaryColor = RGB(255, 190, 0);
        LongWatch.LineWidth = 5;
        ShortWatch.Name = "Buyer Absorption Watch (yellow dot above bar)";
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
        Losses.Name = "Cumulative losses";
        Timeouts.Name = "Cumulative timeouts";
        WinRate.Name = "Win rate % (wins / (wins + losses))";
        State.Name = "State (internal)";
        Resolve.Name = "Resolve (internal)";
        DeltaSG.Name = "Delta";
        DeltaPctSG.Name = "Delta % of volume";
        DeltaChgSG.Name = "Delta change vs previous bar";
        CumDeltaSG.Name = "Cumulative delta";
        VolRatioSG.Name = "Volume / average";
        VolJumpSG.Name = "Volume / previous bar";
        MaxLevelSG.Name = "Max level volume";
        PocDeltaSG.Name = "Delta at max level";
        BigLevelsSG.Name = "Big-volume levels";
        StackBuySG.Name = "Stacked buy imbalances";
        StackSellSG.Name = "Stacked sell imbalances";
        AvgLevelSG.Name = "Volume per level";
        ReasonSG.Name = "Watch reason bitmask";
        for (int s = 4; s <= 22; ++s)
            sc.Subgraph[s].DrawStyle = DRAWSTYLE_IGNORE;

        Lookback.Name = "Average lookback (bars)";
        Lookback.SetInt(20);
        Lookback.SetIntLimits(5, 500);
        DeltaThreshold.Name = "Minimum absolute delta fraction of bar volume";
        DeltaThreshold.SetFloat(0.15f);
        DeltaThreshold.SetFloatLimits(0.01f, 1.0f);
        MinVolumeRatio.Name = "Bar volume / previous average minimum (divergence)";
        MinVolumeRatio.SetFloat(1.5f);
        ZoneTicks.Name = "Extreme zone size (ticks below high / above low)";
        ZoneTicks.SetInt(2);
        ZoneTicks.SetIntLimits(0, 20);
        ThinRatio.Name = "Thin extreme: zone volume / expected zone volume maximum";
        ThinRatio.SetFloat(0.35f);
        ThinRatio.SetFloatLimits(0.01f, 1.0f);
        BigZoneMult.Name = "Big volume at extreme: zone volume / expected zone volume minimum";
        BigZoneMult.SetFloat(2.5f);
        BigLevelMult.Name = "Big level: level volume / average level volume minimum";
        BigLevelMult.SetFloat(3.0f);
        ImbalanceRatio.Name = "Diagonal imbalance ratio";
        ImbalanceRatio.SetFloat(3.0f);
        StackCount.Name = "Stacked imbalances required";
        StackCount.SetInt(3);
        StackCount.SetIntLimits(1, 20);
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
        UseDivergence.Name = "Pattern 1: delta against price";
        UseDivergence.SetYesNo(1);
        UseThinExtreme.Name = "Pattern 2: thin extreme (failed auction)";
        UseThinExtreme.SetYesNo(1);
        UseBigVolume.Name = "Pattern 3: big volume with opposite delta at extreme";
        UseBigVolume.SetYesNo(1);
        RequireStacked.Name = "Require stacked imbalances on the confirmation bar";
        RequireStacked.SetYesNo(0);
        AlertsOn.Name = "Alerts on watch and trigger";
        AlertsOn.SetYesNo(1);
        ZoneDeltaFraction.Name = "Big volume pattern: minimum |zone delta| / zone volume";
        ZoneDeltaFraction.SetFloat(0.20f);
        ZoneDeltaFraction.SetFloatLimits(0.01f, 1.0f);
        return;
    }

    const int i = sc.Index;
    LongWatch[i] = ShortWatch[i] = LongTrigger[i] = ShortTrigger[i] = 0.0f;
    ReasonSG[i] = 0.0f;
    State.Arrays[0][i] = 0.0f;
    State.Arrays[1][i] = 0.0f;
    State.Arrays[2][i] = 0.0f;
    Resolve.Arrays[0][i] = 0.0f;
    Wins[i] = i > 0 ? Wins[i - 1] : 0.0f;
    Losses[i] = i > 0 ? Losses[i - 1] : 0.0f;
    Timeouts[i] = i > 0 ? Timeouts[i - 1] : 0.0f;

    // Delta metrics are available for every bar, including the one in progress.
    const float volume = sc.Volume[i];
    const float delta = sc.AskVolume[i] - sc.BidVolume[i];
    DeltaSG[i] = delta;
    DeltaPctSG[i] = volume > 0.0f ? 100.0f * delta / volume : 0.0f;
    DeltaChgSG[i] = i > 0 ? delta - DeltaSG[i - 1] : delta;
    CumDeltaSG[i] = (i > 0 ? CumDeltaSG[i - 1] : 0.0f) + delta;
    VolJumpSG[i] = (i > 0 && sc.Volume[i - 1] > 0.0f) ? volume / sc.Volume[i - 1] : 0.0f;
    VolRatioSG[i] = 0.0f;
    MaxLevelSG[i] = PocDeltaSG[i] = BigLevelsSG[i] = StackBuySG[i] = StackSellSG[i] = AvgLevelSG[i] = 0.0f;

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
        msg.Format("Absorption v3: wins %d, losses %d, timeouts %d, win rate %.1f%%",
                   (int)Wins[i], (int)Losses[i], (int)Timeouts[i], WinRate[i]);
        sc.AddMessageToLog(msg, 0);
    }

    if (!barClosed || volume <= 0.0f)
        return;

    // Baselines from the previous bars only.
    const int n = Lookback.GetInt();
    float avgVolume = 0.0f, avgLevelVol = 0.0f;
    int levelSamples = 0;
    if (i >= n)
    {
        for (int j = i - n; j < i; ++j)
        {
            avgVolume += sc.Volume[j];
            if (AvgLevelSG[j] > 0.0f)
            {
                avgLevelVol += AvgLevelSG[j];
                ++levelSamples;
            }
        }
        avgVolume /= n;
        avgLevelVol = levelSamples > 0 ? avgLevelVol / levelSamples : 0.0f;
    }
    if (avgVolume > 0.0f)
        VolRatioSG[i] = volume / avgVolume;

    BarFootprint fp = BarFootprint();
    const bool haveFootprint = ReadFootprint(sc, i, ZoneTicks.GetInt(), ImbalanceRatio.GetFloat(),
                                             BigLevelMult.GetFloat() * avgLevelVol, fp);
    if (haveFootprint)
    {
        AvgLevelSG[i] = fp.totalVolume / fp.levels;
        MaxLevelSG[i] = fp.maxLevelVolume;
        PocDeltaSG[i] = fp.pocDelta;
        BigLevelsSG[i] = (float)fp.bigLevels;
        StackBuySG[i] = (float)fp.stackedBuy;
        StackSellSG[i] = (float)fp.stackedSell;
    }

    if (i < n + 1 || avgVolume <= 0.0f)
        return;

    const float deltaFraction = delta / volume;
    const bool elevated = volume >= avgVolume * MinVolumeRatio.GetFloat();
    const bool brickUp = sc.Close[i] >= sc.Open[i];
    const bool brickDown = sc.Close[i] <= sc.Open[i];

    // Pattern 1: delta against price. Heavy selling but the bar did not close lower (and the reverse).
    const bool sellerDivergence = UseDivergence.GetYesNo() && elevated && deltaFraction <= -DeltaThreshold.GetFloat() && brickUp;
    const bool buyerDivergence = UseDivergence.GetYesNo() && elevated && deltaFraction >= DeltaThreshold.GetFloat() && brickDown;

    bool failedHigh = false, failedLow = false, bigAtLow = false, bigAtHigh = false;
    if (haveFootprint)
    {
        const float expectedZone = (volume / fp.levels) * (ZoneTicks.GetInt() + 1);

        // Pattern 2: thin volume at the extreme, optionally outside the composite value area.
        if (UseThinExtreme.GetYesNo())
        {
            const float limit = ThinRatio.GetFloat() * expectedZone;
            failedHigh = brickUp && !brickDown && fp.highZoneVol <= limit && (VAH.GetFloat() <= 0.0f || sc.High[i] > VAH.GetFloat());
            failedLow = brickDown && !brickUp && fp.lowZoneVol <= limit && (VAL.GetFloat() <= 0.0f || sc.Low[i] < VAL.GetFloat());
        }

        // Pattern 3: heavy volume at the extreme with aggressive flow against the rejection.
        if (UseBigVolume.GetYesNo())
        {
            const float big = BigZoneMult.GetFloat() * expectedZone;
            bigAtLow = brickUp && fp.lowZoneVol >= big && fp.lowZoneDelta <= -ZoneDeltaFraction.GetFloat() * fp.lowZoneVol;
            bigAtHigh = brickDown && fp.highZoneVol >= big && fp.highZoneDelta >= ZoneDeltaFraction.GetFloat() * fp.highZoneVol;
        }
    }

    const bool longCandidate = sellerDivergence || failedLow || bigAtLow;
    const bool shortCandidate = buyerDivergence || failedHigh || bigAtHigh;

    float reason = 0.0f;
    if (longCandidate && !shortCandidate)
    {
        LongWatch[i] = sc.Low[i] - sc.TickSize;
        reason = (sellerDivergence ? 1.0f : 0.0f) + (failedLow ? 2.0f : 0.0f) + (bigAtLow ? 4.0f : 0.0f);
    }
    else if (shortCandidate && !longCandidate)
    {
        ShortWatch[i] = sc.High[i] + sc.TickSize;
        reason = (buyerDivergence ? 1.0f : 0.0f) + (failedHigh ? 2.0f : 0.0f) + (bigAtHigh ? 4.0f : 0.0f);
    }
    ReasonSG[i] = reason;

    // Confirmation: next closed bar exceeds the candidate bar extreme with delta in the trade direction.
    const int p = i - 1;
    const bool stackedOkLong = !RequireStacked.GetYesNo() || (haveFootprint && fp.stackedBuy >= StackCount.GetInt());
    const bool stackedOkShort = !RequireStacked.GetYesNo() || (haveFootprint && fp.stackedSell >= StackCount.GetInt());
    bool newTrigger = false;
    if (LongWatch[p] != 0.0f && sc.Close[i] > sc.High[p] && delta > 0.0f && stackedOkLong)
    {
        LongTrigger[i] = sc.Low[i] - 2.0f * sc.TickSize;
        State.Arrays[0][i] = 1.0f;
        State.Arrays[1][i] = sc.Close[i];
        newTrigger = true;
    }
    else if (ShortWatch[p] != 0.0f && sc.Close[i] < sc.Low[p] && delta < 0.0f && stackedOkShort)
    {
        ShortTrigger[i] = sc.High[i] + 2.0f * sc.TickSize;
        State.Arrays[0][i] = -1.0f;
        State.Arrays[1][i] = sc.Close[i];
        newTrigger = true;
    }

    // Alerts only for the bar that has just closed, never during historical recalculation.
    int& LastAlertBar = sc.GetPersistentInt(2);
    if (AlertsOn.GetYesNo() && !sc.IsFullRecalculation && i == sc.ArraySize - 2 && LastAlertBar != i
        && (newTrigger || LongWatch[i] != 0.0f || ShortWatch[i] != 0.0f))
    {
        LastAlertBar = i;
        SCString msg;
        if (newTrigger)
            msg.Format("%s confirmed at %.2f", State.Arrays[0][i] > 0.0f ? "LONG" : "SHORT", sc.Close[i]);
        else
            msg.Format("%s absorption watch (reason %d, delta %d, volume %d)",
                       LongWatch[i] != 0.0f ? "Seller" : "Buyer", (int)reason, (int)delta, (int)volume);
        sc.SetAlert(1, msg);
    }
}
