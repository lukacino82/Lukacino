#include "sierrachart.h"
#include <cmath>
#include <map>

SCDLLName("ES Order Flow Absorption Detector v3")

static inline float MaxF(float a, float b) { return a > b ? a : b; }
static inline float MinF(float a, float b) { return a < b ? a : b; }
static inline int MaxI(int a, int b) { return a > b ? a : b; }

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
    float priceMaxDelta;    // price of the most positive per-level delta
    float priceMinDelta;    // price of the most negative per-level delta
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
    const int size = (int)sc.VolumeAtPriceForBars->GetSizeAtBarIndex((unsigned int)idx);
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
        if (d > fp.maxLevelDelta)
        {
            fp.maxLevelDelta = d;
            fp.priceMaxDelta = t * sc.TickSize;
        }
        if (d < fp.minLevelDelta)
        {
            fp.minLevelDelta = d;
            fp.priceMinDelta = t * sc.TickSize;
        }
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
        const bool buyImb = below != lv.end() && ask >= imbalanceRatio * MaxF(below->second.first, 1.0f);
        const bool sellImb = above != lv.end() && bid >= imbalanceRatio * MaxF(above->second.second, 1.0f);
        buyRun = buyImb ? buyRun + 1 : 0;
        sellRun = sellImb ? sellRun + 1 : 0;
        fp.stackedBuy = MaxI(fp.stackedBuy, buyRun);
        fp.stackedSell = MaxI(fp.stackedSell, sellRun);
    }
    return true;
}

// Trapped traders: aggressive sellers pushed price down (or buyers pushed it up), no new extreme is made any more,
// and price has come back beyond the levels where most of that aggressive volume was traded. Those traders are
// underwater and may have to exit, which feeds the move against them.
struct TrapResult
{
    int state;          // 0 nothing, 1 setup (push + stall), 2 trapped (price beyond the heavy volume level)
    int swing;          // bar index of the extreme of the push
    float level;        // price with the most aggressive volume of the push
    float trappedVol;   // aggressive volume of the push that is now underwater
    float pushDelta;    // net delta of the push
};

static void AccumulateLevels(SCStudyInterfaceRef sc, int idx, bool sellSide, std::map<int, float>& levels)
{
    const int size = (int)sc.VolumeAtPriceForBars->GetSizeAtBarIndex((unsigned int)idx);
    for (int k = 0; k < size; ++k)
    {
        const s_VolumeAtPriceV2* p = NULL;
        sc.VolumeAtPriceForBars->GetVAPElementAtIndex(idx, k, &p);
        if (p == NULL)
            continue;
        levels[(int)p->PriceInTicks] += sellSide ? (float)p->BidVolume : (float)p->AskVolume;
    }
}

static TrapResult EvaluateTrap(SCStudyInterfaceRef sc, SCSubgraphRef DeltaSG, int i, bool sellersTrapped, int lookback,
                               int minPushTicks, float minPushDelta, int stallBars, int marginTicks,
                               float minFraction, float minContracts)
{
    TrapResult r = TrapResult();
    const int from = MaxI(0, i - lookback);

    // Extreme of the push: lowest low for trapped sellers, highest high for trapped buyers.
    int ext = i;
    float extVal = sellersTrapped ? sc.Low[i] : sc.High[i];
    for (int j = i; j >= from; --j)
    {
        const float v = sellersTrapped ? sc.Low[j] : sc.High[j];
        if (sellersTrapped ? v < extVal : v > extVal)
        {
            extVal = v;
            ext = j;
        }
    }
    r.swing = ext;
    if (i - ext < stallBars)
        return r;   // still making new extremes, or the extreme is too fresh

    // Start of the push: the opposite extreme before it.
    int start = ext;
    float startVal = sellersTrapped ? sc.High[ext] : sc.Low[ext];
    for (int j = ext; j >= from; --j)
    {
        const float v = sellersTrapped ? sc.High[j] : sc.Low[j];
        if (sellersTrapped ? v > startVal : v < startVal)
        {
            startVal = v;
            start = j;
        }
    }
    const float pushSize = sellersTrapped ? startVal - sc.Low[ext] : sc.High[ext] - startVal;
    if (pushSize < minPushTicks * sc.TickSize)
        return r;

    float pushDelta = 0.0f;
    for (int j = start; j <= ext; ++j)
        pushDelta += DeltaSG[j];
    if (sellersTrapped ? pushDelta > -minPushDelta : pushDelta < minPushDelta)
        return r;   // the push was not one-sided enough

    r.state = 1;
    r.pushDelta = pushDelta;

    std::map<int, float> lv;   // price in ticks -> aggressive volume of the pushing side
    for (int j = start; j <= ext; ++j)
        AccumulateLevels(sc, j, sellersTrapped, lv);
    if (lv.empty())
        return r;

    typedef std::map<int, float>::const_iterator Iter;
    float total = 0.0f, maxVol = 0.0f;
    int pocTicks = 0;
    for (Iter it = lv.begin(); it != lv.end(); ++it)
    {
        total += it->second;
        if (it->second > maxVol)
        {
            maxVol = it->second;
            pocTicks = it->first;
        }
    }
    const int closeTicks = sc.PriceValueToTicks(sc.Close[i]);
    float trapped = 0.0f;
    for (Iter it = lv.begin(); it != lv.end(); ++it)
    {
        if (sellersTrapped ? it->first <= closeTicks - marginTicks : it->first >= closeTicks + marginTicks)
            trapped += it->second;
    }
    r.level = pocTicks * sc.TickSize;
    r.trappedVol = trapped;

    const bool beyondLevel = sellersTrapped ? pocTicks <= closeTicks - marginTicks : pocTicks >= closeTicks + marginTicks;
    if (total > 0.0f && trapped / total >= minFraction && trapped >= minContracts && beyondLevel)
        r.state = 2;
    return r;
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
    SCSubgraphRef ReasonSG = sc.Subgraph[22];     // bitmask of the watch: 1 divergence, 2 thin extreme, 4 big volume at extreme, 8 delta shock
    SCSubgraphRef ShockSG = sc.Subgraph[23];      // delta change of the bar / average |delta change| of previous bars
    SCSubgraphRef FlipSG = sc.Subgraph[24];       // +1 buyers take over (delta flips up with a shock), -1 sellers take over
    SCSubgraphRef PressureSG = sc.Subgraph[25];   // sum of delta / sum of volume over the lookback, in percent
    SCSubgraphRef EventLevelDeltaSG = sc.Subgraph[26]; // signed delta of a big single price level (0 = none)
    SCSubgraphRef EventLevelPriceSG = sc.Subgraph[27]; // price of that level
    SCSubgraphRef TrapStateSG = sc.Subgraph[28];  // +1 sellers setup, +2 sellers trapped, -1 buyers setup, -2 buyers trapped
    SCSubgraphRef TrapLevelSG = sc.Subgraph[29];  // price with the most aggressive volume of the push
    SCSubgraphRef TrapVolSG = sc.Subgraph[30];    // aggressive volume of the push that is now underwater
    SCSubgraphRef TrapPushSG = sc.Subgraph[31];   // net delta of the push

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
    SCInputRef UseDeltaShock = sc.Input[20];
    SCInputRef DeltaShockMult = sc.Input[21];
    SCInputRef FlipFraction = sc.Input[22];
    SCInputRef AlertOnWatch = sc.Input[23];
    SCInputRef CooldownBars = sc.Input[24];
    SCInputRef OppositeLockBars = sc.Input[25];
    SCInputRef MinRoomTicks = sc.Input[26];
    SCInputRef RoomLookback = sc.Input[27];
    SCInputRef MinWickTicks = sc.Input[28];
    SCInputRef ShowPanel = sc.Input[29];
    SCInputRef ShowIntervals = sc.Input[30];
    SCInputRef SessionStartHour = sc.Input[31];
    SCInputRef BigLevelDelta = sc.Input[32];
    SCInputRef BigBarDelta = sc.Input[33];
    SCInputRef SpikeMult = sc.Input[34];
    SCInputRef SqueezeMinDelta = sc.Input[35];
    SCInputRef EventWindowMin = sc.Input[36];
    SCInputRef ChaseTicks = sc.Input[37];
    SCInputRef ArrowMode = sc.Input[38];
    SCInputRef TrapLookback = sc.Input[39];
    SCInputRef TrapMinPushTicks = sc.Input[40];
    SCInputRef TrapMinPushDelta = sc.Input[41];
    SCInputRef TrapStallBars = sc.Input[42];
    SCInputRef TrapMarginTicks = sc.Input[43];
    SCInputRef TrapMinFraction = sc.Input[44];
    SCInputRef TrapMinContracts = sc.Input[45];

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
        ShockSG.Name = "Delta shock (delta change / average |delta change|)";
        FlipSG.Name = "Delta flip (+1 buyers take over, -1 sellers take over)";
        PressureSG.Name = "Pressure % (sum delta / sum volume over lookback)";
        EventLevelDeltaSG.Name = "Big level delta (single price level)";
        EventLevelPriceSG.Name = "Big level price";
        TrapStateSG.Name = "Trap state (+1/+2 sellers setup/trapped, -1/-2 buyers)";
        TrapLevelSG.Name = "Trap level (price with most aggressive volume)";
        TrapVolSG.Name = "Trapped volume (contracts underwater)";
        TrapPushSG.Name = "Trap push delta";
        // Metrics are not drawn but stay visible in the Chart Values Window and the region data line.
        for (int s = 4; s <= 31; ++s)
            sc.Subgraph[s].DrawStyle = DRAWSTYLE_HIDDEN;
        State.DrawStyle = DRAWSTYLE_IGNORE;
        Resolve.DrawStyle = DRAWSTYLE_IGNORE;

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
        AlertsOn.Name = "Alert on confirmed LONG/SHORT trigger";
        AlertsOn.SetYesNo(1);
        ZoneDeltaFraction.Name = "Big volume pattern: minimum |zone delta| / zone volume";
        ZoneDeltaFraction.SetFloat(0.20f);
        ZoneDeltaFraction.SetFloatLimits(0.01f, 1.0f);
        UseDeltaShock.Name = "Pattern 4: delta shock / flip (pressure changes sides)";
        UseDeltaShock.SetYesNo(1);
        DeltaShockMult.Name = "Delta shock: |delta change| / average |delta change| minimum";
        DeltaShockMult.SetFloat(2.5f);
        DeltaShockMult.SetFloatLimits(1.0f, 20.0f);
        FlipFraction.Name = "Delta flip: minimum |delta| / volume of the bar";
        FlipFraction.SetFloat(0.10f);
        FlipFraction.SetFloatLimits(0.01f, 1.0f);
        AlertOnWatch.Name = "Alert also on yellow dot (watch)";
        AlertOnWatch.SetYesNo(0);
        CooldownBars.Name = "Anti-whipsaw: bars before the next trigger in the same direction";
        CooldownBars.SetInt(5);
        CooldownBars.SetIntLimits(0, 500);
        OppositeLockBars.Name = "Anti-whipsaw: bars before a trigger in the opposite direction";
        OppositeLockBars.SetInt(10);
        OppositeLockBars.SetIntLimits(0, 500);
        MinRoomTicks.Name = "Room to run: minimum distance to the recent extreme (ticks, 0 = off)";
        MinRoomTicks.SetInt(0);
        MinRoomTicks.SetIntLimits(0, 5000);
        RoomLookback.Name = "Room to run: lookback for the recent extreme (bars)";
        RoomLookback.SetInt(40);
        RoomLookback.SetIntLimits(2, 1000);
        MinWickTicks.Name = "Failed auction: minimum wick beyond the bar body (ticks)";
        MinWickTicks.SetInt(2);
        MinWickTicks.SetIntLimits(1, 100);
        ShowPanel.Name = "Show info panel in the chart (metrics of the last closed bar)";
        ShowPanel.SetYesNo(1);
        ShowIntervals.Name = "Show interval panel (1h / 2h / 3h / session pressure, price band, big prints)";
        ShowIntervals.SetYesNo(1);
        SessionStartHour.Name = "Session start (hour of the chart time, e.g. 15.5 = 15:30)";
        SessionStartHour.SetFloat(0.0f);
        SessionStartHour.SetFloatLimits(0.0f, 23.99f);
        BigLevelDelta.Name = "Big print: net delta at one price level (contracts)";
        BigLevelDelta.SetInt(500);
        BigLevelDelta.SetIntLimits(10, 100000);
        BigBarDelta.Name = "Big print: net delta of one bar (contracts)";
        BigBarDelta.SetInt(1500);
        BigBarDelta.SetIntLimits(10, 1000000);
        SpikeMult.Name = "Volume spike: bar volume / average minimum";
        SpikeMult.SetFloat(3.0f);
        SqueezeMinDelta.Name = "Interval absorption flag: minimum |net delta| (contracts)";
        SqueezeMinDelta.SetInt(2000);
        SqueezeMinDelta.SetIntLimits(10, 10000000);
        EventWindowMin.Name = "Big print list: look back (minutes)";
        EventWindowMin.SetInt(60);
        EventWindowMin.SetIntLimits(5, 1440);
        ChaseTicks.Name = "Anti-chase: block a trigger when price already ran this many ticks from the recent extreme (0 = off)";
        ChaseTicks.SetInt(0);
        ChaseTicks.SetIntLimits(0, 5000);
        ArrowMode.Name = "Arrow source (0 absorption confirmation, 1 trapped traders, 2 both)";
        ArrowMode.SetInt(1);
        ArrowMode.SetIntLimits(0, 2);
        TrapLookback.Name = "Trapped traders: lookback for the push (bars)";
        TrapLookback.SetInt(40);
        TrapLookback.SetIntLimits(10, 500);
        TrapMinPushTicks.Name = "Trapped traders: minimum size of the push (ticks)";
        TrapMinPushTicks.SetInt(24);
        TrapMinPushTicks.SetIntLimits(2, 5000);
        TrapMinPushDelta.Name = "Trapped traders: minimum net delta of the push (contracts)";
        TrapMinPushDelta.SetInt(1000);
        TrapMinPushDelta.SetIntLimits(10, 1000000);
        TrapStallBars.Name = "Trapped traders: bars without a new extreme before the reversal";
        TrapStallBars.SetInt(3);
        TrapStallBars.SetIntLimits(1, 100);
        TrapMarginTicks.Name = "Trapped traders: price must be this many ticks beyond the heavy level";
        TrapMarginTicks.SetInt(2);
        TrapMarginTicks.SetIntLimits(0, 100);
        TrapMinFraction.Name = "Trapped traders: minimum share of the push volume that is underwater";
        TrapMinFraction.SetFloat(0.6f);
        TrapMinFraction.SetFloatLimits(0.05f, 1.0f);
        TrapMinContracts.Name = "Trapped traders: minimum underwater volume (contracts)";
        TrapMinContracts.SetFloat(1500.0f);
        TrapMinContracts.SetFloatLimits(10.0f, 10000000.0f);
        return;
    }

    const int i = sc.Index;
    LongWatch[i] = ShortWatch[i] = LongTrigger[i] = ShortTrigger[i] = 0.0f;
    ReasonSG[i] = 0.0f;
    EventLevelDeltaSG[i] = 0.0f;
    EventLevelPriceSG[i] = 0.0f;
    TrapStateSG[i] = 0.0f;
    TrapLevelSG[i] = 0.0f;
    TrapVolSG[i] = 0.0f;
    TrapPushSG[i] = 0.0f;
    State.Arrays[3][i] = 0.0f;
    State.Arrays[0][i] = 0.0f;
    State.Arrays[1][i] = 0.0f;
    State.Arrays[2][i] = 0.0f;
    Resolve.Arrays[0][i] = 0.0f;
    Wins[i] = i > 0 ? Wins[i - 1] : 0.0f;
    Losses[i] = i > 0 ? Losses[i - 1] : 0.0f;
    Timeouts[i] = i > 0 ? Timeouts[i - 1] : 0.0f;

    // Delta metrics are available for every bar, including the one in progress.
    const int n = Lookback.GetInt();
    const float volume = sc.Volume[i];
    const float delta = sc.AskVolume[i] - sc.BidVolume[i];
    DeltaSG[i] = delta;
    DeltaPctSG[i] = volume > 0.0f ? 100.0f * delta / volume : 0.0f;
    DeltaChgSG[i] = i > 0 ? delta - DeltaSG[i - 1] : delta;
    CumDeltaSG[i] = (i > 0 ? CumDeltaSG[i - 1] : 0.0f) + delta;
    VolJumpSG[i] = (i > 0 && sc.Volume[i - 1] > 0.0f) ? volume / sc.Volume[i - 1] : 0.0f;
    VolRatioSG[i] = 0.0f;

    // Pressure: who dominated the last n bars. Shock / flip: the delta of this bar against its own recent behaviour.
    PressureSG[i] = 0.0f;
    ShockSG[i] = 0.0f;
    FlipSG[i] = 0.0f;
    if (i >= n)
    {
        float sumDelta = 0.0f, sumVolume = 0.0f, avgAbsChg = 0.0f;
        for (int j = i - n + 1; j <= i; ++j)
        {
            sumDelta += DeltaSG[j];
            sumVolume += sc.Volume[j];
        }
        for (int j = i - n; j < i; ++j)
            avgAbsChg += fabsf(DeltaChgSG[j]);
        avgAbsChg /= n;
        if (sumVolume > 0.0f)
            PressureSG[i] = 100.0f * sumDelta / sumVolume;
        if (avgAbsChg > 0.0f)
        {
            ShockSG[i] = DeltaChgSG[i] / avgAbsChg;
            const float prevDelta = DeltaSG[i - 1];
            const bool flipped = delta * prevDelta < 0.0f;
            if (flipped && fabsf(ShockSG[i]) >= DeltaShockMult.GetFloat() && volume > 0.0f
                && fabsf(delta) / volume >= FlipFraction.GetFloat())
                FlipSG[i] = delta > 0.0f ? 1.0f : -1.0f;
        }
    }
    MaxLevelSG[i] = PocDeltaSG[i] = BigLevelsSG[i] = StackBuySG[i] = StackSellSG[i] = AvgLevelSG[i] = 0.0f;

    const bool barClosed = sc.GetBarHasClosedStatus(i) == BHCS_BAR_HAS_CLOSED;

    // Resolve earlier triggers against this bar. Re-running the same closed bar gives the same counts.
    if (barClosed)
    {
        const float target = TargetTicks.GetInt() * sc.TickSize;
        const float stop = StopTicks.GetInt() * sc.TickSize;
        const int horizon = HorizonBars.GetInt();

        for (int j = MaxI(0, i - horizon); j < i; ++j)
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

    // Info panel: metrics of the last closed bar, drawn in the chart so they do not depend on hover or on the data line width.
    if (ShowPanel.GetYesNo() && i == sc.ArraySize - 1 && i > 0)
    {
        const int k = i - 1;
        SCString txt;
        txt.Format("ABSORPTION v3  (last closed bar)\nDelta %d  (%.1f%%)   Delta chg %d\nShock %.1fx   Flip %d   Pressure %.1f%%\n"
                   "Volume/avg %.1fx   Max level %d   Delta at max level %d\nBig levels %d   Stacked buy/sell %d / %d\n"
                   "Watch reason %d   (1 div, 2 thin, 4 big, 8 shock)\nWins %d   Losses %d   Timeouts %d   Win rate %.0f%%",
                   (int)DeltaSG[k], DeltaPctSG[k], (int)DeltaChgSG[k], ShockSG[k], (int)FlipSG[k], PressureSG[k],
                   VolRatioSG[k], (int)MaxLevelSG[k], (int)PocDeltaSG[k], (int)BigLevelsSG[k], (int)StackBuySG[k],
                   (int)StackSellSG[k], (int)ReasonSG[k], (int)Wins[k], (int)Losses[k], (int)Timeouts[k], WinRate[k]);

        s_UseTool Tool;
        Tool.Clear();
        Tool.ChartNumber = sc.ChartNumber;
        Tool.DrawingType = DRAWING_TEXT;
        Tool.LineNumber = 91827;
        Tool.AddMethod = UTAM_ADD_OR_ADJUST;
        Tool.Region = sc.GraphRegion;
        Tool.UseRelativeVerticalValues = 1;
        Tool.BeginDateTime = 3;
        Tool.BeginValue = 96;
        Tool.FontSize = 9;
        Tool.Color = RGB(255, 255, 255);
        Tool.FontBackColor = RGB(30, 30, 30);
        Tool.TransparentLabelBackground = 0;
        Tool.Text = txt;
        sc.UseTool(Tool);
    }

    // Interval panel: who dominated the last 1 / 2 / 3 hours and the session, in which price band, plus recent big prints.
    if (ShowIntervals.GetYesNo() && i == sc.ArraySize - 1 && i > 0)
    {
        const double lastT = sc.BaseDateTimeIn[i].GetAsDouble();
        double sessionStart = floor(lastT) + SessionStartHour.GetFloat() / 24.0;
        if (sessionStart > lastT)
            sessionStart -= 1.0;
        const double starts[4] = { lastT - 1.0 / 24.0, lastT - 2.0 / 24.0, lastT - 3.0 / 24.0, sessionStart };
        const char* labels[4] = { "1h", "2h", "3h", "Seance" };

        SCString txtB;
        txtB.Format("TLAK A CENOVE PASMO (aktualni bar vcetne)\n");
        for (int w = 0; w < 4; ++w)
        {
            float sumAsk = 0.0f, sumBid = 0.0f;
            float hi = sc.High[i], lo = sc.Low[i];
            int first = i;
            for (int j = i; j >= 0 && sc.BaseDateTimeIn[j].GetAsDouble() >= starts[w]; --j)
            {
                sumAsk += sc.AskVolume[j];
                sumBid += sc.BidVolume[j];
                hi = MaxF(hi, sc.High[j]);
                lo = MinF(lo, sc.Low[j]);
                first = j;
            }
            const float vol = sumAsk + sumBid;
            const float d = sumAsk - sumBid;
            const float buyPct = vol > 0.0f ? 100.0f * sumAsk / vol : 0.0f;
            const float change = sc.Close[i] - sc.Open[first];
            const float range = hi - lo;
            const float efficiency = range > 0.0f ? fabsf(change) / range : 0.0f;
            const char* who = buyPct >= 52.0f ? "KUPUJICI" : (buyPct <= 48.0f ? "PRODAVAJICI" : "VYROVNANO");

            // Absorption of a large net delta: price moved against it or hardly moved at all.
            const char* flag = "";
            if (fabsf(d) >= (float)SqueezeMinDelta.GetInt())
            {
                if (d < 0.0f && change > 0.0f) flag = "ABSORPCE prodeju, cena roste (mozny short squeeze)";
                else if (d > 0.0f && change < 0.0f) flag = "ABSORPCE nakupu, cena klesa (mozny long squeeze)";
                else if (d < 0.0f && efficiency < 0.25f) flag = "ABSORPCE prodeju, cena stoji";
                else if (d > 0.0f && efficiency < 0.25f) flag = "ABSORPCE nakupu, cena stoji";
            }

            SCString line;
            line.Format("%-6s %-11s delta %+d  (%.0f%% BUY)  objem %d | cena %+.2f  pasmo %.2f-%.2f  %s\n",
                        labels[w], who, (int)d, buyPct, (int)vol, change, lo, hi, flag);
            txtB.Append(line.GetChars());
        }

        SCString head;
        head.Format("\nVELKE OBJEMY (poslednich %d min, uzavrene bary)\n", EventWindowMin.GetInt());
        txtB.Append(head.GetChars());
        const double evStart = lastT - EventWindowMin.GetInt() / 1440.0;
        int shown = 0;
        for (int j = i - 1; j >= 0 && shown < 5; --j)
        {
            if (sc.BaseDateTimeIn[j].GetAsDouble() < evStart)
                break;
            const bool lvl = EventLevelDeltaSG[j] != 0.0f;
            const bool bigBar = fabsf(DeltaSG[j]) >= (float)BigBarDelta.GetInt();
            const bool spike = VolRatioSG[j] >= SpikeMult.GetFloat();
            if (!lvl && !bigBar && !spike)
                continue;

            SCString line;
            line.Format("%02d:%02d  ", sc.BaseDateTimeIn[j].GetHour(), sc.BaseDateTimeIn[j].GetMinute());
            if (lvl)
            {
                SCString part;
                part.Format("%s %+d @ %.2f   ", EventLevelDeltaSG[j] > 0.0f ? "NAKUP" : "PRODEJ", (int)EventLevelDeltaSG[j], EventLevelPriceSG[j]);
                line.Append(part.GetChars());
            }
            if (bigBar)
            {
                SCString part;
                part.Format("delta baru %+d   ", (int)DeltaSG[j]);
                line.Append(part.GetChars());
            }
            if (spike)
            {
                SCString part;
                part.Format("objem %.1fx prumer   ", VolRatioSG[j]);
                line.Append(part.GetChars());
            }
            line.Append("\n");
            txtB.Append(line.GetChars());
            ++shown;
        }
        if (shown == 0)
            txtB.Append("zadne\n");

        // Trapped traders: current state of the last closed bar and the last trapped-trader signal.
        txtB.Append("\nTRAPPED TRADERS\n");
        const int k = i - 1;
        const float st = TrapStateSG[k];
        SCString trapLine;
        if (st == 0.0f)
        {
            trapLine.Format("zadny setup\n");
        }
        else
        {
            const bool sellers = st > 0.0f;
            if (fabsf(st) == 1.0f)
                trapLine.Format("SETUP %s: %s tlaci (delta %+d), nove %s se nedela; past nad/pod %.2f\n",
                                sellers ? "LONG" : "SHORT", sellers ? "prodavajici" : "kupujici", (int)TrapPushSG[k],
                                sellers ? "low" : "high", TrapLevelSG[k]);
            else
                trapLine.Format("PAST AKTIVNI: %s v pasti %d kontraktu, nejvetsi objem @ %.2f, cena uz je za nim\n",
                                sellers ? "prodavajici" : "kupujici", (int)TrapVolSG[k], TrapLevelSG[k]);
        }
        txtB.Append(trapLine.GetChars());
        for (int j = k; j >= 0 && j >= i - 400; --j)
        {
            if (State.Arrays[3][j] == 0.0f)
                continue;
            SCString sig;
            sig.Format("posledni signal %02d:%02d  %s  (%s v pasti %d kontraktu, objem @ %.2f)\n",
                       sc.BaseDateTimeIn[j].GetHour(), sc.BaseDateTimeIn[j].GetMinute(),
                       State.Arrays[3][j] > 0.0f ? "LONG" : "SHORT", State.Arrays[3][j] > 0.0f ? "prodavajici" : "kupujici",
                       (int)TrapVolSG[j], TrapLevelSG[j]);
            txtB.Append(sig.GetChars());
            break;
        }

        s_UseTool ToolB;
        ToolB.Clear();
        ToolB.ChartNumber = sc.ChartNumber;
        ToolB.DrawingType = DRAWING_TEXT;
        ToolB.LineNumber = 91828;
        ToolB.AddMethod = UTAM_ADD_OR_ADJUST;
        ToolB.Region = sc.GraphRegion;
        ToolB.UseRelativeVerticalValues = 1;
        ToolB.BeginDateTime = 3;
        ToolB.BeginValue = 76;
        ToolB.FontSize = 9;
        ToolB.Color = RGB(255, 255, 255);
        ToolB.FontBackColor = RGB(30, 30, 30);
        ToolB.TransparentLabelBackground = 0;
        ToolB.Text = txtB;
        sc.UseTool(ToolB);
    }

    if (!barClosed || volume <= 0.0f)
        return;

    // Baselines from the previous bars only.
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

        // Big print: one price level where aggressive flow was one-sided and large.
        const float bigLevel = (float)BigLevelDelta.GetInt();
        if (fp.maxLevelDelta >= bigLevel && fp.maxLevelDelta >= -fp.minLevelDelta)
        {
            EventLevelDeltaSG[i] = fp.maxLevelDelta;
            EventLevelPriceSG[i] = fp.priceMaxDelta;
        }
        else if (-fp.minLevelDelta >= bigLevel)
        {
            EventLevelDeltaSG[i] = fp.minLevelDelta;
            EventLevelPriceSG[i] = fp.priceMinDelta;
        }
    }

    if (i < n + 1 || avgVolume <= 0.0f)
        return;

    // Trapped traders: evaluated for both sides, the stronger state is kept.
    TrapResult trapSell = TrapResult(), trapBuy = TrapResult();
    if (haveFootprint)
    {
        trapSell = EvaluateTrap(sc, DeltaSG, i, true, TrapLookback.GetInt(), TrapMinPushTicks.GetInt(),
                                (float)TrapMinPushDelta.GetInt(), TrapStallBars.GetInt(), TrapMarginTicks.GetInt(),
                                TrapMinFraction.GetFloat(), TrapMinContracts.GetFloat());
        trapBuy = EvaluateTrap(sc, DeltaSG, i, false, TrapLookback.GetInt(), TrapMinPushTicks.GetInt(),
                               (float)TrapMinPushDelta.GetInt(), TrapStallBars.GetInt(), TrapMarginTicks.GetInt(),
                               TrapMinFraction.GetFloat(), TrapMinContracts.GetFloat());
    }
    const bool pickSellers = trapSell.state > trapBuy.state
        || (trapSell.state == trapBuy.state && fabsf(trapSell.pushDelta) >= fabsf(trapBuy.pushDelta));
    const TrapResult& trap = pickSellers ? trapSell : trapBuy;
    if (trap.state > 0)
    {
        TrapStateSG[i] = (pickSellers ? 1.0f : -1.0f) * (float)trap.state;
        TrapLevelSG[i] = trap.level;
        TrapVolSG[i] = trap.trappedVol;
        TrapPushSG[i] = trap.pushDelta;
    }

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
            // The thin extreme must be a rejected probe (a wick beyond the body), not the edge where a Renko brick
            // simply completes: that edge is always thin and would produce a signal on every brick.
            const float bodyTop = sc.Open[i] > sc.Close[i] ? sc.Open[i] : sc.Close[i];
            const float bodyBottom = sc.Open[i] < sc.Close[i] ? sc.Open[i] : sc.Close[i];
            const float minWick = MinWickTicks.GetInt() * sc.TickSize;
            failedHigh = brickDown && !brickUp && sc.High[i] - bodyTop >= minWick && fp.highZoneVol <= limit
                && (VAH.GetFloat() <= 0.0f || sc.High[i] > VAH.GetFloat());
            failedLow = brickUp && !brickDown && bodyBottom - sc.Low[i] >= minWick && fp.lowZoneVol <= limit
                && (VAL.GetFloat() <= 0.0f || sc.Low[i] < VAL.GetFloat());
        }

        // Pattern 3: heavy volume at the extreme with aggressive flow against the rejection.
        if (UseBigVolume.GetYesNo())
        {
            const float big = BigZoneMult.GetFloat() * expectedZone;
            bigAtLow = brickUp && fp.lowZoneVol >= big && fp.lowZoneDelta <= -ZoneDeltaFraction.GetFloat() * fp.lowZoneVol;
            bigAtHigh = brickDown && fp.highZoneVol >= big && fp.highZoneDelta >= ZoneDeltaFraction.GetFloat() * fp.highZoneVol;
        }
    }

    // Pattern 4: delta flips sign with a shock after the opposite brick, so pressure changes sides.
    const bool buyersTakeOver = UseDeltaShock.GetYesNo() && FlipSG[i] > 0.0f && sc.Close[i - 1] < sc.Open[i - 1];
    const bool sellersTakeOver = UseDeltaShock.GetYesNo() && FlipSG[i] < 0.0f && sc.Close[i - 1] > sc.Open[i - 1];

    const bool longCandidate = sellerDivergence || failedLow || bigAtLow || buyersTakeOver;
    const bool shortCandidate = buyerDivergence || failedHigh || bigAtHigh || sellersTakeOver;

    float reason = 0.0f;
    if (longCandidate && !shortCandidate)
    {
        LongWatch[i] = sc.Low[i] - sc.TickSize;
        reason = (sellerDivergence ? 1.0f : 0.0f) + (failedLow ? 2.0f : 0.0f) + (bigAtLow ? 4.0f : 0.0f) + (buyersTakeOver ? 8.0f : 0.0f);
    }
    else if (shortCandidate && !longCandidate)
    {
        ShortWatch[i] = sc.High[i] + sc.TickSize;
        reason = (buyerDivergence ? 1.0f : 0.0f) + (failedHigh ? 2.0f : 0.0f) + (bigAtHigh ? 4.0f : 0.0f) + (sellersTakeOver ? 8.0f : 0.0f);
    }
    ReasonSG[i] = reason;

    // Confirmation: next closed bar exceeds the candidate bar extreme with delta in the trade direction.
    const int p = i - 1;
    const bool stackedOkLong = !RequireStacked.GetYesNo() || (haveFootprint && fp.stackedBuy >= StackCount.GetInt());
    const bool stackedOkShort = !RequireStacked.GetYesNo() || (haveFootprint && fp.stackedSell >= StackCount.GetInt());

    // Anti-whipsaw: the most recent trigger blocks same-direction triggers for CooldownBars and
    // opposite-direction triggers for OppositeLockBars. Room to run: the recent extreme in the trade direction
    // must be at least MinRoomTicks away, so the price has space to reach the target.
    float lastDir = 0.0f;
    int lastAge = 1000000;
    for (int j = i - 1; j >= MaxI(0, i - MaxI(CooldownBars.GetInt(), OppositeLockBars.GetInt())); --j)
    {
        if (State.Arrays[0][j] != 0.0f)
        {
            lastDir = State.Arrays[0][j];
            lastAge = i - j;
            break;
        }
    }
    const bool blockedLong = (lastDir > 0.0f && lastAge < CooldownBars.GetInt()) || (lastDir < 0.0f && lastAge < OppositeLockBars.GetInt());
    const bool blockedShort = (lastDir < 0.0f && lastAge < CooldownBars.GetInt()) || (lastDir > 0.0f && lastAge < OppositeLockBars.GetInt());

    float recentHigh = sc.High[i], recentLow = sc.Low[i];
    for (int j = MaxI(0, i - RoomLookback.GetInt()); j < i; ++j)
    {
        recentHigh = MaxF(recentHigh, sc.High[j]);
        recentLow = MinF(recentLow, sc.Low[j]);
    }
    const float minRoom = MinRoomTicks.GetInt() * sc.TickSize;
    const bool roomLong = MinRoomTicks.GetInt() == 0 || recentHigh - sc.Close[i] >= minRoom;
    const bool roomShort = MinRoomTicks.GetInt() == 0 || sc.Close[i] - recentLow >= minRoom;
    // Anti-chase: do not buy after price already ran far up from the recent low (or sell far below the recent high).
    const float chase = ChaseTicks.GetInt() * sc.TickSize;
    const bool notChasedLong = ChaseTicks.GetInt() == 0 || sc.Close[i] - recentLow <= chase;
    const bool notChasedShort = ChaseTicks.GetInt() == 0 || recentHigh - sc.Close[i] <= chase;

    // Arrow sources: confirmation of an absorption watch (mode 0 or 2) and/or trapped traders (mode 1 or 2).
    const int arrowMode = ArrowMode.GetInt();
    const bool longFromAbsorption = arrowMode != 1 && LongWatch[p] != 0.0f && sc.Close[i] > sc.High[p] && delta > 0.0f && stackedOkLong;
    const bool shortFromAbsorption = arrowMode != 1 && ShortWatch[p] != 0.0f && sc.Close[i] < sc.Low[p] && delta < 0.0f && stackedOkShort;

    // Trapped traders fire once per push: the bar must reverse with the flow (up brick with buying, or down brick with selling).
    bool longFromTrap = arrowMode != 0 && TrapStateSG[i] == 2.0f && sc.Close[i] > sc.Open[i] && delta > 0.0f;
    bool shortFromTrap = arrowMode != 0 && TrapStateSG[i] == -2.0f && sc.Close[i] < sc.Open[i] && delta < 0.0f;
    if (longFromTrap || shortFromTrap)
    {
        const float key = (longFromTrap ? 1.0f : -1.0f) * (float)(trap.swing + 1);
        for (int j = i - 1; j >= MaxI(0, i - TrapLookback.GetInt()); --j)
        {
            if (State.Arrays[3][j] == key)
            {
                longFromTrap = false;
                shortFromTrap = false;
                break;
            }
        }
    }

    bool newTrigger = false;
    if ((longFromAbsorption || longFromTrap) && !blockedLong && roomLong && notChasedLong)
    {
        LongTrigger[i] = sc.Low[i] - 2.0f * sc.TickSize;
        State.Arrays[0][i] = 1.0f;
        State.Arrays[1][i] = sc.Close[i];
        if (longFromTrap)
            State.Arrays[3][i] = (float)(trap.swing + 1);
        newTrigger = true;
    }
    else if ((shortFromAbsorption || shortFromTrap) && !blockedShort && roomShort && notChasedShort)
    {
        ShortTrigger[i] = sc.High[i] + 2.0f * sc.TickSize;
        State.Arrays[0][i] = -1.0f;
        State.Arrays[1][i] = sc.Close[i];
        if (shortFromTrap)
            State.Arrays[3][i] = -(float)(trap.swing + 1);
        newTrigger = true;
    }

    // Alerts only for the bar that has just closed, never during historical recalculation.
    int& LastAlertBar = sc.GetPersistentInt(2);
    const bool watchNow = LongWatch[i] != 0.0f || ShortWatch[i] != 0.0f;
    if (!sc.IsFullRecalculation && i == sc.ArraySize - 2 && LastAlertBar != i
        && ((newTrigger && AlertsOn.GetYesNo()) || (!newTrigger && watchNow && AlertOnWatch.GetYesNo())))
    {
        LastAlertBar = i;
        SCString msg;
        if (newTrigger)
            msg.Format("%s confirmed at %.2f", State.Arrays[0][i] > 0.0f ? "LONG" : "SHORT", sc.Close[i]);
        else
            msg.Format("%s absorption watch (reason %d, delta %d, volume %d)",
                       LongWatch[i] != 0.0f ? "Seller" : "Buyer", (int)reason, (int)delta, (int)volume);
        sc.SetAlert(newTrigger ? 2 : 1, msg);
    }
}
