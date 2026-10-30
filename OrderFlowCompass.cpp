#include "sierrachart.h"
#include <cmath>
#include <map>
#include <string>
#include <vector>

SCDLLName("Order Flow Compass")

static inline float MaxF(float a, float b) { return a > b ? a : b; }
static inline float MinF(float a, float b) { return a < b ? a : b; }
static inline int MaxI(int a, int b) { return a > b ? a : b; }

// Lays text out in a box: lines longer than the width are wrapped at spaces (continuation lines are indented),
// every line is padded to the same width. Width 0 means "as wide as the longest line".
static std::string BoxText(const std::string& raw, size_t width)
{
    if (width > 0 && width < 20)
        width = 20;
    std::vector<std::string> lines;
    size_t start = 0;
    while (start <= raw.size())
    {
        size_t end = raw.find('\n', start);
        if (end == std::string::npos)
            end = raw.size();
        std::string line = raw.substr(start, end - start);
        size_t indent = 0;
        while (indent < line.size() && line[indent] == ' ')
            ++indent;
        if (width > 0)
        {
            while (line.size() > width)
            {
                size_t cut = line.rfind(' ', width);
                if (cut == std::string::npos || cut <= indent + 2)
                    cut = width;
                lines.push_back(line.substr(0, cut));
                size_t next = cut;
                while (next < line.size() && line[next] == ' ')
                    ++next;
                line = std::string(indent + 2, ' ') + line.substr(next);
            }
        }
        lines.push_back(line);
        if (end >= raw.size())
            break;
        start = end + 1;
    }

    if (width == 0)
    {
        for (size_t n = 0; n < lines.size(); ++n)
            width = lines[n].size() > width ? lines[n].size() : width;
    }
    std::string boxed;
    for (size_t n = 0; n < lines.size(); ++n)
    {
        boxed += lines[n];
        if (lines[n].size() < width)
            boxed.append(width - lines[n].size(), ' ');
        if (n + 1 < lines.size())
            boxed += '\n';
    }
    return boxed;
}

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

// Latest value of a subgraph of a study on another chart (e.g. weekly / monthly VWAP). With id 0 the studies of that
// chart are searched for the first one whose subgraph is close to the reference price; the found id is stored in 'id'.
static float ReadHtfValue(SCStudyInterfaceRef sc, int chart, int& id, int sub, float ref, bool mayScan)
{
    if (id > 0)
    {
        SCFloatArray arr;
        sc.GetStudyArrayFromChartUsingID(chart, id, sub, arr);
        const int n = arr.GetArraySize();
        return n > 0 ? arr[n - 1] : 0.0f;
    }
    if (!mayScan)
        return 0.0f;
    for (int candidate = 1; candidate <= 60; ++candidate)
    {
        SCFloatArray arr;
        sc.GetStudyArrayFromChartUsingID(chart, candidate, sub, arr);
        const int n = arr.GetArraySize();
        if (n <= 0)
            continue;
        const float v = arr[n - 1];
        if (v > 0.0f && fabsf(v - ref) <= 0.05f * ref)
        {
            id = candidate;
            return v;
        }
    }
    return 0.0f;
}

// Order clusters: several neighbouring price levels of one bar where one side traded aggressively in bulk
// (sellers hit the bid, or buyers lifted the ask). If price then closes through the cluster against that side,
// the participants are trapped.
struct ClusterResult
{
    float low;
    float high;
    float vol;
};

static ClusterResult FindCluster(SCStudyInterfaceRef sc, int idx, bool sellSide, int levelCount, float minContracts,
                                 float minShare, float dominance)
{
    ClusterResult r = ClusterResult();
    const int size = (int)sc.VolumeAtPriceForBars->GetSizeAtBarIndex((unsigned int)idx);
    if (size <= 0)
        return r;
    std::map<int, std::pair<float, float> > lv;   // price in ticks -> (aggressive volume of the side, volume of the other side)
    float total = 0.0f;
    for (int k = 0; k < size; ++k)
    {
        const s_VolumeAtPriceV2* p = NULL;
        sc.VolumeAtPriceForBars->GetVAPElementAtIndex(idx, k, &p);
        if (p == NULL)
            continue;
        const float bid = (float)p->BidVolume;
        const float ask = (float)p->AskVolume;
        lv[(int)p->PriceInTicks] = sellSide ? std::make_pair(bid, ask) : std::make_pair(ask, bid);
        total += bid + ask;
    }
    if (lv.empty() || total <= 0.0f)
        return r;
    const int lowest = lv.begin()->first;
    const int highest = lv.rbegin()->first;
    float bestSum = 0.0f;
    int bestStart = 0;
    for (int t = lowest; t <= highest; ++t)
    {
        float sum = 0.0f, other = 0.0f;
        for (int q = 0; q < levelCount; ++q)
        {
            std::map<int, std::pair<float, float> >::const_iterator it = lv.find(t + q);
            if (it == lv.end())
                continue;
            sum += it->second.first;
            other += it->second.second;
        }
        if (sum > bestSum && sum >= minContracts && sum >= minShare * total && sum >= dominance * MaxF(other, 1.0f))
        {
            bestSum = sum;
            bestStart = t;
        }
    }
    if (bestSum > 0.0f)
    {
        r.low = bestStart * sc.TickSize;
        r.high = (bestStart + levelCount - 1) * sc.TickSize;
        r.vol = bestSum;
    }
    return r;
}

// Strongest cluster found in the bars [last - age, last] that no later bar up to 'last' has closed through yet.
static bool ActiveCluster(SCStudyInterfaceRef sc, SCSubgraphRef lo, SCSubgraphRef hi, SCSubgraphRef vol, int last, int age,
                          float margin, bool sellSide, float& outLo, float& outHi, float& outVol)
{
    bool found = false;
    for (int j = last; j >= 0 && j >= last - age; --j)
    {
        if (vol[j] <= 0.0f)
            continue;
        bool consumed = false;
        for (int k = j + 1; k <= last; ++k)
        {
            if (sellSide ? sc.Close[k] > hi[j] + margin : sc.Close[k] < lo[j] - margin)
            {
                consumed = true;
                break;
            }
        }
        if (consumed)
            continue;
        if (!found || vol[j] > outVol)
        {
            found = true;
            outLo = lo[j];
            outHi = hi[j];
            outVol = vol[j];
        }
    }
    return found;
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
                               float minFraction, float minContracts, int levelMode, float originFraction,
                               float pushRangeMult, float pushDeltaMult, float maxStallRange)
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
    // Volatility baseline: average bar range of the last 50 bars.
    float avgRange = 0.0f;
    int rangeCount = 0;
    for (int j = MaxI(0, i - 50); j <= i; ++j)
    {
        avgRange += sc.High[j] - sc.Low[j];
        ++rangeCount;
    }
    avgRange = rangeCount > 0 ? avgRange / rangeCount : 0.0f;

    const float pushSize = sellersTrapped ? startVal - sc.Low[ext] : sc.High[ext] - startVal;
    const float minPush = pushRangeMult > 0.0f ? pushRangeMult * avgRange : minPushTicks * sc.TickSize;
    if (pushSize < minPush)
        return r;

    // Sideways phase: the bars after the extreme (before the current bar) must stay in a narrow range.
    if (maxStallRange > 0.0f && i - 1 > ext)
    {
        float hi = sc.High[ext], lo = sc.Low[ext];
        for (int j = ext; j < i; ++j)
        {
            hi = MaxF(hi, sc.High[j]);
            lo = MinF(lo, sc.Low[j]);
        }
        if (hi - lo > maxStallRange * avgRange)
            return r;
    }

    float pushDelta = 0.0f;
    for (int j = start; j <= ext; ++j)
        pushDelta += DeltaSG[j];

    // Significance of the push delta relative to the usual |delta| of a bar, scaled by the length of the push.
    float avgAbsDelta = 0.0f;
    int deltaCount = 0;
    for (int j = MaxI(0, start - 100); j < start; ++j)
    {
        avgAbsDelta += fabsf(DeltaSG[j]);
        ++deltaCount;
    }
    const int pushBars = ext - start + 1;
    const float needDelta = (pushDeltaMult > 0.0f && deltaCount > 0)
        ? pushDeltaMult * (avgAbsDelta / deltaCount) * sqrtf((float)pushBars)
        : minPushDelta;
    if (sellersTrapped ? pushDelta > -needDelta : pushDelta < needDelta)
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
    // Reversal level: where the push started (mode 1, fraction 1.0 = full origin) or where most aggressive volume traded (mode 0).
    float levelPrice = pocTicks * sc.TickSize;
    if (levelMode == 1)
        levelPrice = sellersTrapped ? extVal + originFraction * (startVal - extVal) : extVal - originFraction * (extVal - startVal);
    const int levelTicks = sc.PriceValueToTicks(levelPrice);
    r.level = levelPrice;
    r.trappedVol = trapped;

    const bool beyondLevel = sellersTrapped ? levelTicks <= closeTicks - marginTicks : levelTicks >= closeTicks + marginTicks;
    if (total > 0.0f && trapped / total >= minFraction && trapped >= minContracts && beyondLevel)
        r.state = 2;
    return r;
}

SCSFExport scsf_OrderFlowCompass(SCStudyInterfaceRef sc)
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
    SCSubgraphRef ClSellLo = sc.Subgraph[32];     // cluster of aggressive sells in the bar: lowest price
    SCSubgraphRef ClSellHi = sc.Subgraph[33];     // highest price
    SCSubgraphRef ClSellVol = sc.Subgraph[34];    // contracts in the cluster
    SCSubgraphRef ClBuyLo = sc.Subgraph[35];      // cluster of aggressive buys in the bar
    SCSubgraphRef ClBuyHi = sc.Subgraph[36];
    SCSubgraphRef ClBuyVol = sc.Subgraph[37];

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
    SCInputRef TrapLevelMode = sc.Input[46];
    SCInputRef TrapOriginFraction = sc.Input[47];
    SCInputRef TrapPushRangeMult = sc.Input[48];
    SCInputRef TrapPushDeltaMult = sc.Input[49];
    SCInputRef TrapReactionMult = sc.Input[50];
    SCInputRef TrapMaxStallRange = sc.Input[51];
    SCInputRef DominancePct = sc.Input[52];
    SCInputRef BandPoints = sc.Input[53];
    SCInputRef ShowBands = sc.Input[54];
    SCInputRef FontName = sc.Input[55];
    SCInputRef BoldText = sc.Input[56];
    SCInputRef BoxX = sc.Input[57];
    SCInputRef BoxY = sc.Input[58];
    SCInputRef BoxFont = sc.Input[59];
    SCInputRef BoxColor = sc.Input[60];
    SCInputRef BoxBack = sc.Input[61];
    SCInputRef BoxTransparent = sc.Input[62];
    SCInputRef ShowPanelB = sc.Input[63];
    SCInputRef Show30m = sc.Input[64];
    SCInputRef Show1h = sc.Input[65];
    SCInputRef Show2h = sc.Input[66];
    SCInputRef Show3h = sc.Input[67];
    SCInputRef Show4h = sc.Input[68];
    SCInputRef Show5h = sc.Input[69];
    SCInputRef ShowSession = sc.Input[70];
    SCInputRef MaxEvents = sc.Input[71];
    SCInputRef ShowComments = sc.Input[72];
    SCInputRef ShowLegend = sc.Input[73];
    SCInputRef TrapLocationHours = sc.Input[74];
    SCInputRef TrapLocationPct = sc.Input[75];
    SCInputRef ShowTraps = sc.Input[76];
    SCInputRef ShowHeader = sc.Input[77];
    SCInputRef ShowStats = sc.Input[78];
    SCInputRef BoxWidth = sc.Input[79];
    SCInputRef ShowSlices = sc.Input[80];
    SCInputRef ShowDomStrip = sc.Input[81];
    SCInputRef DomStripX = sc.Input[82];
    SCInputRef DomStripY = sc.Input[83];
    SCInputRef DomStripSpacing = sc.Input[84];
    SCInputRef BuyColor = sc.Input[85];
    SCInputRef SellColor = sc.Input[86];
    SCInputRef DisplayMode = sc.Input[87];
    SCInputRef TargetChart = sc.Input[88];
    SCInputRef MarkerHistoryBars = sc.Input[89];
    SCInputRef MirrorDots = sc.Input[90];
    SCInputRef MirrorArrows = sc.Input[91];
    SCInputRef DotSize = sc.Input[92];
    SCInputRef ArrowSize = sc.Input[93];
    SCInputRef DomStripFont = sc.Input[94];
    SCInputRef DomStripDetail = sc.Input[95];
    SCInputRef DomStripPad = sc.Input[96];
    SCInputRef ClusterArrows = sc.Input[97];
    SCInputRef ClusterLevels = sc.Input[98];
    SCInputRef ClusterMinContracts = sc.Input[99];
    SCInputRef ClusterMinShare = sc.Input[100];
    SCInputRef ClusterDominance = sc.Input[101];
    SCInputRef ClusterMaxAge = sc.Input[102];
    SCInputRef ClusterMarginTicks = sc.Input[103];
    SCInputRef ClusterNeedDelta = sc.Input[104];
    SCInputRef MarkArrowStyle = sc.Input[105];
    SCInputRef MarkDotColor = sc.Input[106];
    SCInputRef MarkLongColor = sc.Input[107];
    SCInputRef MarkShortColor = sc.Input[108];
    SCInputRef MarkDotShortColor = sc.Input[109];
    SCInputRef HtfOn = sc.Input[110];
    SCInputRef DailyChart = sc.Input[111];
    SCInputRef DailyID = sc.Input[112];
    SCInputRef DailySub = sc.Input[113];
    SCInputRef WeeklyChart = sc.Input[114];
    SCInputRef WeeklyID = sc.Input[115];
    SCInputRef WeeklySub = sc.Input[116];
    SCInputRef MonthlyChart = sc.Input[117];
    SCInputRef MonthlyID = sc.Input[118];
    SCInputRef MonthlySub = sc.Input[119];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Order Flow Compass (footprint + delta + market monitor, unverified)";
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
        ClSellLo.Name = "Sell cluster low";
        ClSellHi.Name = "Sell cluster high";
        ClSellVol.Name = "Sell cluster contracts";
        ClBuyLo.Name = "Buy cluster low";
        ClBuyHi.Name = "Buy cluster high";
        ClBuyVol.Name = "Buy cluster contracts";
        // Metrics are not drawn but stay visible in the Chart Values Window and the region data line.
        for (int s = 4; s <= 37; ++s)
            sc.Subgraph[s].DrawStyle = DRAWSTYLE_HIDDEN;
        State.DrawStyle = DRAWSTYLE_IGNORE;
        Resolve.DrawStyle = DRAWSTYLE_IGNORE;

        Lookback.Name = "Average lookback (bars)";
        Lookback.SetInt(30);
        Lookback.SetIntLimits(5, 500);
        DeltaThreshold.Name = "Minimum absolute delta fraction of bar volume";
        DeltaThreshold.SetFloat(0.25f);
        DeltaThreshold.SetFloatLimits(0.01f, 1.0f);
        MinVolumeRatio.Name = "Bar volume / previous average minimum (divergence)";
        MinVolumeRatio.SetFloat(2.0f);
        ZoneTicks.Name = "Extreme zone size (ticks below high / above low)";
        ZoneTicks.SetInt(2);
        ZoneTicks.SetIntLimits(0, 20);
        ThinRatio.Name = "Thin extreme: zone volume / expected zone volume maximum";
        ThinRatio.SetFloat(0.30f);
        ThinRatio.SetFloatLimits(0.01f, 1.0f);
        BigZoneMult.Name = "Big volume at extreme: zone volume / expected zone volume minimum";
        BigZoneMult.SetFloat(3.0f);
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
        TargetTicks.SetInt(32);
        TargetTicks.SetIntLimits(1, 2000);
        StopTicks.Name = "Stop after entry (ticks)";
        StopTicks.SetInt(16);
        StopTicks.SetIntLimits(1, 2000);
        HorizonBars.Name = "Bars to resolve a trigger before timeout";
        HorizonBars.SetInt(15);
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
        ZoneDeltaFraction.SetFloat(0.25f);
        ZoneDeltaFraction.SetFloatLimits(0.01f, 1.0f);
        UseDeltaShock.Name = "Pattern 4: delta shock / flip (pressure changes sides)";
        UseDeltaShock.SetYesNo(1);
        DeltaShockMult.Name = "Delta shock: |delta change| / average |delta change| minimum";
        DeltaShockMult.SetFloat(3.0f);
        DeltaShockMult.SetFloatLimits(1.0f, 20.0f);
        FlipFraction.Name = "Delta flip: minimum |delta| / volume of the bar";
        FlipFraction.SetFloat(0.15f);
        FlipFraction.SetFloatLimits(0.01f, 1.0f);
        AlertOnWatch.Name = "Alert also on yellow dot (watch)";
        AlertOnWatch.SetYesNo(0);
        CooldownBars.Name = "Anti-whipsaw: bars before the next trigger in the same direction";
        CooldownBars.SetInt(6);
        CooldownBars.SetIntLimits(0, 500);
        OppositeLockBars.Name = "Anti-whipsaw: bars before a trigger in the opposite direction";
        OppositeLockBars.SetInt(12);
        OppositeLockBars.SetIntLimits(0, 500);
        MinRoomTicks.Name = "Room to run: minimum distance to the recent extreme (ticks, 0 = off)";
        MinRoomTicks.SetInt(12);
        MinRoomTicks.SetIntLimits(0, 5000);
        RoomLookback.Name = "Room to run: lookback for the recent extreme (bars)";
        RoomLookback.SetInt(50);
        RoomLookback.SetIntLimits(2, 1000);
        MinWickTicks.Name = "Failed auction: minimum wick beyond the bar body (ticks)";
        MinWickTicks.SetInt(2);
        MinWickTicks.SetIntLimits(1, 100);
        ShowPanel.Name = "Section: metrics of the last closed bar";
        ShowPanel.SetYesNo(1);
        ShowIntervals.Name = "Section: Market Activity Monitor (30 min - 5 h, session)";
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
        SqueezeMinDelta.Name = "Monitor: flag delta without price move, minimum |net delta| (contracts)";
        SqueezeMinDelta.SetInt(3000);
        SqueezeMinDelta.SetIntLimits(10, 10000000);
        EventWindowMin.Name = "Big print list: look back (minutes)";
        EventWindowMin.SetInt(60);
        EventWindowMin.SetIntLimits(5, 1440);
        ChaseTicks.Name = "Anti-chase: block a trigger when price already ran this many ticks from the recent extreme (0 = off)";
        ChaseTicks.SetInt(0);
        ChaseTicks.SetIntLimits(0, 5000);
        ArrowMode.Name = "Arrow source (0 absorption confirmation, 1 trapped traders, 2 both)";
        ArrowMode.SetInt(2);
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
        TrapMinContracts.SetFloat(800.0f);
        TrapMinContracts.SetFloatLimits(10.0f, 10000000.0f);
        TrapLevelMode.Name = "Reversal level (0 = price with most aggressive volume, 1 = where the push started)";
        TrapLevelMode.SetInt(1);
        TrapLevelMode.SetIntLimits(0, 1);
        TrapOriginFraction.Name = "Reversal level mode 1: share of the push price must retrace (1.0 = full origin, 0.5 = half)";
        TrapOriginFraction.SetFloat(0.5f);
        TrapOriginFraction.SetFloatLimits(0.1f, 1.0f);
        TrapPushRangeMult.Name = "Push size relative to volatility: x average bar range (0 = use ticks)";
        TrapPushRangeMult.SetFloat(2.0f);
        TrapPushRangeMult.SetFloatLimits(0.0f, 50.0f);
        TrapPushDeltaMult.Name = "Push delta relative: x average |bar delta| x sqrt(bars) (0 = use contracts)";
        TrapPushDeltaMult.SetFloat(1.5f);
        TrapPushDeltaMult.SetFloatLimits(0.0f, 50.0f);
        TrapReactionMult.Name = "Reaction bar: minimum |delta| as multiple of the average |bar delta|";
        TrapReactionMult.SetFloat(1.0f);
        TrapReactionMult.SetFloatLimits(0.0f, 50.0f);
        TrapMaxStallRange.Name = "Sideways phase: max range x average bar range (0 = off)";
        TrapMaxStallRange.SetFloat(0.0f);
        TrapMaxStallRange.SetFloatLimits(0.0f, 50.0f);
        DominancePct.Name = "Monitor: share of aggressive buying (%) from which BUYERS dominate (SELLERS below 100 - this)";
        DominancePct.SetFloat(50.5f);
        DominancePct.SetFloatLimits(50.0f, 90.0f);
        BandPoints.Name = "Monitor: price band size (points)";
        BandPoints.SetFloat(5.0f);
        BandPoints.SetFloatLimits(0.25f, 500.0f);
        ShowBands.Name = "Monitor: show price bands with most volume";
        ShowBands.SetYesNo(1);

        // Look and position of the text panels. Positions are percentages of the chart (100 = top / right edge).
        FontName.Name = "Text: font name (a fixed-width font such as Consolas keeps the columns aligned)";
        FontName.SetString("Consolas");
        BoldText.Name = "Text: bold";
        BoldText.SetYesNo(0);
        BoxX.Name = "Text box: position horizontal (% of chart width)";
        BoxX.SetInt(3);
        BoxX.SetIntLimits(0, 95);
        BoxY.Name = "Text box: position vertical (% of chart height, 100 = top)";
        BoxY.SetInt(96);
        BoxY.SetIntLimits(2, 100);
        BoxFont.Name = "Text box: font size";
        BoxFont.SetInt(9);
        BoxFont.SetIntLimits(5, 36);
        BoxColor.Name = "Text box: text color";
        BoxColor.SetColor(RGB(0, 0, 0));
        BoxBack.Name = "Text box: background color";
        BoxBack.SetColor(RGB(255, 255, 128));
        BoxTransparent.Name = "Text box: transparent background";
        BoxTransparent.SetYesNo(0);

        ShowPanelB.Name = "Section: list of big prints";
        ShowPanelB.SetYesNo(1);

        Show30m.Name = "Monitor: show 30 min";
        Show30m.SetYesNo(1);
        Show1h.Name = "Monitor: show 1 h";
        Show1h.SetYesNo(1);
        Show2h.Name = "Monitor: show 2 h";
        Show2h.SetYesNo(1);
        Show3h.Name = "Monitor: show 3 h";
        Show3h.SetYesNo(0);
        Show4h.Name = "Monitor: show 4 h";
        Show4h.SetYesNo(0);
        Show5h.Name = "Monitor: show 5 h";
        Show5h.SetYesNo(1);
        ShowSession.Name = "Monitor: show session";
        ShowSession.SetYesNo(1);
        MaxEvents.Name = "Big prints: number of prints listed";
        MaxEvents.SetInt(2);
        MaxEvents.SetIntLimits(1, 30);
        ShowComments.Name = "Monitor: comment line per interval (trend/sideways, price at high/low, volume vs previous, delta shift)";
        ShowComments.SetYesNo(1);
        ShowLegend.Name = "Section: legend of the monitor labels";
        ShowLegend.SetYesNo(0);
        ShowTraps.Name = "Section: trapped traders (state and last signal)";
        ShowTraps.SetYesNo(1);
        ShowHeader.Name = "Section: header (price and time)";
        ShowHeader.SetYesNo(1);
        ShowStats.Name = "Section: statistics of the signals (wins, losses)";
        ShowStats.SetYesNo(0);
        BoxWidth.Name = "Text box width in characters (0 = as wide as the longest line; longer lines are wrapped)";
        BoxWidth.SetInt(62);
        BoxWidth.SetIntLimits(0, 400);
        ShowSlices.Name = "Monitor: development by time slices (0-30 min, 30-60 min, 1-2 h ... 4-5 h, delta and price change)";
        ShowSlices.SetYesNo(1);
        ShowDomStrip.Name = "Dominance strip: show dominance of every interval in its own colored text (buyers green, sellers red)";
        ShowDomStrip.SetYesNo(1);
        DomStripX.Name = "Dominance strip: position horizontal of the first item (% of chart width)";
        DomStripX.SetInt(3);
        DomStripX.SetIntLimits(0, 95);
        DomStripY.Name = "Dominance strip: position vertical (% of chart height, 100 = top)";
        DomStripY.SetInt(99);
        DomStripY.SetIntLimits(2, 100);
        DomStripSpacing.Name = "Dominance strip: horizontal distance between items (% of chart width)";
        DomStripSpacing.SetInt(6);
        DomStripSpacing.SetIntLimits(2, 40);
        DomStripFont.Name = "Dominance strip: font size (0 = same as the box)";
        DomStripFont.SetInt(0);
        DomStripFont.SetIntLimits(0, 40);
        DomStripDetail.Name = "Dominance strip: 0 = short (1h -1.2% DN), 1 = wide (adds who dominates: KUPUJICI / PRODAVAJICI / VYROVNANO)";
        DomStripDetail.SetInt(0);
        DomStripDetail.SetIntLimits(0, 1);
        DomStripPad.Name = "Dominance strip: extra spaces around each item (widens the colored field)";
        DomStripPad.SetInt(0);
        DomStripPad.SetIntLimits(0, 10);
        ClusterArrows.Name = "Cluster arrows: sells (buys) piled up on a few levels and price closes through them = LONG (SHORT) arrow";
        ClusterArrows.SetYesNo(1);
        ClusterLevels.Name = "Cluster: number of neighbouring price levels (ticks) that form a cluster";
        ClusterLevels.SetInt(3);
        ClusterLevels.SetIntLimits(2, 8);
        ClusterMinContracts.Name = "Cluster: minimum aggressive contracts in the cluster";
        ClusterMinContracts.SetInt(200);
        ClusterMinContracts.SetIntLimits(10, 1000000);
        ClusterMinShare.Name = "Cluster: minimum share of the bar volume in the cluster (%)";
        ClusterMinShare.SetFloat(30.0f);
        ClusterMinShare.SetFloatLimits(5.0f, 100.0f);
        ClusterDominance.Name = "Cluster: aggressive side must trade at least this many times more than the other side on those levels";
        ClusterDominance.SetFloat(1.5f);
        ClusterDominance.SetFloatLimits(1.0f, 20.0f);
        ClusterMaxAge.Name = "Cluster: how many bars back a cluster stays valid (waiting for price to close through it)";
        ClusterMaxAge.SetInt(6);
        ClusterMaxAge.SetIntLimits(0, 100);
        ClusterMarginTicks.Name = "Cluster: the close must be this many ticks beyond the cluster";
        ClusterMarginTicks.SetInt(1);
        ClusterMarginTicks.SetIntLimits(0, 50);
        ClusterNeedDelta.Name = "Cluster: the closing bar must also have delta in the trade direction (when the cluster is from an earlier bar)";
        ClusterNeedDelta.SetYesNo(1);
        MarkArrowStyle.Name = "Markers: LONG/SHORT symbol (0 arrow, 1 triangle, 2 diamond, 3 square); sizes are the dot size and arrow size inputs";
        MarkArrowStyle.SetInt(1);
        MarkArrowStyle.SetIntLimits(0, 3);
        MarkDotColor.Name = "Markers: color of the dot below the bar = sellers absorbed, potential growth (light green)";
        MarkDotColor.SetColor(RGB(120, 220, 120));
        HtfOn.Name = "Regime: show daily / weekly / monthly VWAP position (VWAP studies on other charts)";
        HtfOn.SetYesNo(1);
        DailyChart.Name = "Regime: chart number with the daily VWAP";
        DailyChart.SetInt(3);
        DailyChart.SetIntLimits(0, 200);
        DailyID.Name = "Regime: ID of the daily VWAP study on that chart (0 = search automatically)";
        DailyID.SetInt(0);
        DailyID.SetIntLimits(0, 10000);
        DailySub.Name = "Regime: subgraph index of the daily VWAP line (0 = first)";
        DailySub.SetInt(0);
        DailySub.SetIntLimits(0, 59);
        WeeklyChart.Name = "Regime: chart number with the weekly VWAP";
        WeeklyChart.SetInt(1);
        WeeklyChart.SetIntLimits(0, 200);
        WeeklyID.Name = "Regime: ID of the weekly VWAP study on that chart (0 = search automatically)";
        WeeklyID.SetInt(0);
        WeeklyID.SetIntLimits(0, 10000);
        WeeklySub.Name = "Regime: subgraph index of the weekly VWAP line (0 = first)";
        WeeklySub.SetInt(0);
        WeeklySub.SetIntLimits(0, 59);
        MonthlyChart.Name = "Regime: chart number with the monthly VWAP";
        MonthlyChart.SetInt(4);
        MonthlyChart.SetIntLimits(0, 200);
        MonthlyID.Name = "Regime: ID of the monthly VWAP study on that chart (0 = search automatically)";
        MonthlyID.SetInt(0);
        MonthlyID.SetIntLimits(0, 10000);
        MonthlySub.Name = "Regime: subgraph index of the monthly VWAP line (0 = first)";
        MonthlySub.SetInt(0);
        MonthlySub.SetIntLimits(0, 59);
        MarkDotShortColor.Name = "Markers: color of the dot above the bar = buyers absorbed, potential fall (light red)";
        MarkDotShortColor.SetColor(RGB(255, 130, 130));
        MarkLongColor.Name = "Markers: color of the LONG symbol";
        MarkLongColor.SetColor(RGB(0, 170, 0));
        MarkShortColor.Name = "Markers: color of the SHORT symbol";
        MarkShortColor.SetColor(RGB(210, 0, 0));
        BuyColor.Name = "Dominance strip: color when buyers dominate";
        BuyColor.SetColor(RGB(0, 150, 0));
        SellColor.Name = "Dominance strip: color when sellers dominate";
        SellColor.SetColor(RGB(210, 0, 0));
        DisplayMode.Name = "Display: 0 = compact (few lines: signal, bar, position, big prints), 1 = detailed (all sections)";
        DisplayMode.SetInt(0);
        DisplayMode.SetIntLimits(0, 1);
        TargetChart.Name = "Mirror to chart number (the # in the chart title, e.g. the VWAP / composite chart; 0 = off)";
        TargetChart.SetInt(11);
        TargetChart.SetIntLimits(0, 200);
        MarkerHistoryBars.Name = "Mirror: how many of the latest bars of this chart get markers on the other chart";
        MarkerHistoryBars.SetInt(1000);
        MarkerHistoryBars.SetIntLimits(10, 20000);
        MirrorDots.Name = "Mirror: yellow dots (absorption watch)";
        MirrorDots.SetYesNo(1);
        MirrorArrows.Name = "Mirror: LONG / SHORT arrows";
        MirrorArrows.SetYesNo(1);
        DotSize.Name = "Mirror: dot size";
        DotSize.SetInt(5);
        DotSize.SetIntLimits(1, 40);
        ArrowSize.Name = "Mirror: arrow size";
        ArrowSize.SetInt(7);
        ArrowSize.SetIntLimits(1, 40);
        TrapLocationHours.Name = "Trapped traders: the extreme of the push must lie at the edge of the range of the last N hours (0 = off)";
        TrapLocationHours.SetFloat(2.0f);
        TrapLocationHours.SetFloatLimits(0.0f, 24.0f);
        TrapLocationPct.Name = "Trapped traders: edge of the range in percent (e.g. 35 = outer 35% of the range)";
        TrapLocationPct.SetFloat(50.0f);
        TrapLocationPct.SetFloatLimits(5.0f, 100.0f);
        return;
    }

    if (sc.LastCallToFunction)
    {
        // Remove the text panels when the study is removed from the chart.
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91827);
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91828);
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91830);
        for (int w = 0; w < 7; ++w)
            sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91840 + w);
        if (TargetChart.GetInt() > 0)
        {
            // Remove the mirrored markers from the other chart.
            for (int idx = MaxI(0, sc.ArraySize - MarkerHistoryBars.GetInt()); idx < sc.ArraySize; ++idx)
            {
                for (int t = 0; t < 4; ++t)
                    sc.DeleteACSChartDrawing(TargetChart.GetInt(), TOOL_DELETE_CHARTDRAWING, 700000 + (idx % 200000) * 4 + t);
            }
        }
        return;
    }

    // Look of the dots and arrows follows the inputs (the Subgraphs tab is overridden for these four).
    {
        const int styleUp[4] = { DRAWSTYLE_ARROW_UP, DRAWSTYLE_TRIANGLE_UP, DRAWSTYLE_DIAMOND, DRAWSTYLE_SQUARE };
        const int styleDown[4] = { DRAWSTYLE_ARROW_DOWN, DRAWSTYLE_TRIANGLE_DOWN, DRAWSTYLE_DIAMOND, DRAWSTYLE_SQUARE };
        LongTrigger.DrawStyle = styleUp[MarkArrowStyle.GetInt()];
        ShortTrigger.DrawStyle = styleDown[MarkArrowStyle.GetInt()];
        LongWatch.LineWidth = ShortWatch.LineWidth = DotSize.GetInt();
        LongTrigger.LineWidth = ShortTrigger.LineWidth = ArrowSize.GetInt();
        LongWatch.PrimaryColor = MarkDotColor.GetColor();
        ShortWatch.PrimaryColor = MarkDotShortColor.GetColor();
        LongTrigger.PrimaryColor = MarkLongColor.GetColor();
        ShortTrigger.PrimaryColor = MarkShortColor.GetColor();
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
    ClSellLo[i] = ClSellHi[i] = ClSellVol[i] = ClBuyLo[i] = ClBuyHi[i] = ClBuyVol[i] = 0.0f;
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
        msg.Format("Absorption Reversal Monitor: wins %d, losses %d, timeouts %d, win rate %.1f%%",
                   (int)Wins[i], (int)Losses[i], (int)Timeouts[i], WinRate[i]);
        sc.AddMessageToLog(msg, 0);
    }

    // The text box is assembled from sections that can be switched on and off. The sections are built here and below.
    SCString secHeader, secLastBar, secStats, secMonitor, secBig, secTraps;
    if (i == sc.ArraySize - 1 && i > 0)
    {
        const int k = i - 1;
        secHeader.Format("ABSORPTION REVERSAL MONITOR\ncena %.2f   cas %02d:%02d\n", sc.Close[i],
                         sc.BaseDateTimeIn[i].GetHour(), sc.BaseDateTimeIn[i].GetMinute());
        secLastBar.Format("POSLEDNI UZAVRENY BAR\nDelta %d  (%.1f%%)   Delta chg %d\nShock %.1fx   Flip %d   Pressure %.1f%%\n"
                          "Volume/avg %.1fx   Max level %d   Delta at max level %d\nBig levels %d   Stacked buy/sell %d / %d\n"
                          "Watch reason %d   (1 div, 2 thin, 4 big, 8 shock)\n",
                          (int)DeltaSG[k], DeltaPctSG[k], (int)DeltaChgSG[k], ShockSG[k], (int)FlipSG[k], PressureSG[k],
                          VolRatioSG[k], (int)MaxLevelSG[k], (int)PocDeltaSG[k], (int)BigLevelsSG[k], (int)StackBuySG[k],
                          (int)StackSellSG[k], (int)ReasonSG[k]);
        secStats.Format("STATISTIKA  W %d / L %d / T %d   uspesnost %.0f%%",
                        (int)Wins[k], (int)Losses[k], (int)Timeouts[k], WinRate[k]);
        if ((int)(Wins[k] + Losses[k]) < 30)
            secStats.Append("\n(mene nez 30 signalu: zatim neprukazne)");
        secStats.Append("\n");
    }

    // Panels: Market Activity Monitor (30 min ... 5 h and the session) plus big prints and trapped traders.
    if ((ShowIntervals.GetYesNo() || ShowPanelB.GetYesNo() || ShowTraps.GetYesNo()) && i == sc.ArraySize - 1 && i > 0)
    {
        const double lastT = sc.BaseDateTimeIn[i].GetAsDouble();
        double sessionStart = floor(lastT) + SessionStartHour.GetFloat() / 24.0;
        if (sessionStart > lastT)
            sessionStart -= 1.0;
        const int W = 7;
        const char* labels[7] = { "30 min", "1 h", "2 h", "3 h", "4 h", "5 h", "Seance" };
        const double starts[7] = { lastT - 0.5 / 24.0, lastT - 1.0 / 24.0, lastT - 2.0 / 24.0, lastT - 3.0 / 24.0,
                                   lastT - 4.0 / 24.0, lastT - 5.0 / 24.0, sessionStart };

        const bool showW[7] = { Show30m.GetYesNo() != 0, Show1h.GetYesNo() != 0, Show2h.GetYesNo() != 0, Show3h.GetYesNo() != 0,
                                Show4h.GetYesNo() != 0, Show5h.GetYesNo() != 0, ShowSession.GetYesNo() != 0 };
        if (ShowIntervals.GetYesNo())
        {
        // Price bands are rebuilt once per new bar because they read Volume at Price of every bar in the windows.
        int& lastBandBar = sc.GetPersistentInt(3);
        if (ShowBands.GetYesNo() && lastBandBar != i)
        {
            lastBandBar = i;
            double earliest = starts[0];
            for (int w = 1; w < W; ++w)
                earliest = starts[w] < earliest ? starts[w] : earliest;

            std::map<int, float> bands[7];
            const float bandSize = BandPoints.GetFloat();
            for (int j = i; j >= 0; --j)
            {
                const double t = sc.BaseDateTimeIn[j].GetAsDouble();
                if (t < earliest)
                    break;
                const int size = (int)sc.VolumeAtPriceForBars->GetSizeAtBarIndex((unsigned int)j);
                for (int e = 0; e < size; ++e)
                {
                    const s_VolumeAtPriceV2* p = NULL;
                    sc.VolumeAtPriceForBars->GetVAPElementAtIndex(j, e, &p);
                    if (p == NULL)
                        continue;
                    const float levelVol = (float)p->BidVolume + (float)p->AskVolume;
                    const int band = (int)floor((p->PriceInTicks * sc.TickSize) / bandSize);
                    for (int w = 0; w < W; ++w)
                    {
                        if (t >= starts[w])
                            bands[w][band] += levelVol;
                    }
                }
            }

            typedef std::map<int, float>::const_iterator BandIter;
            for (int w = 0; w < W; ++w)
            {
                SCString& cache = sc.GetPersistentSCString(w + 1);
                cache.Format("%s", "");
                sc.GetPersistentInt(10 + w) = 0;
                float total = 0.0f;
                for (BandIter it = bands[w].begin(); it != bands[w].end(); ++it)
                    total += it->second;
                int picked[3] = { 0, 0, 0 };
                for (int rank = 0; rank < 3; ++rank)
                {
                    float best = 0.0f;
                    int bestBand = 0;
                    bool found = false;
                    for (BandIter it = bands[w].begin(); it != bands[w].end(); ++it)
                    {
                        bool used = false;
                        for (int q = 0; q < rank; ++q)
                            used = used || picked[q] == it->first;
                        if (!used && it->second > best)
                        {
                            best = it->second;
                            bestBand = it->first;
                            found = true;
                        }
                    }
                    if (!found || total <= 0.0f)
                        break;
                    picked[rank] = bestBand;
                    if (rank == 0)
                        sc.GetPersistentInt(10 + w) = bestBand + 1;
                    SCString part;
                    part.Format("%s%.0f-%.0f %.0f%%", rank == 0 ? "" : "   ", bestBand * bandSize, (bestBand + 1) * bandSize,
                                100.0f * best / total);
                    cache.Append(part.GetChars());
                }
            }
        }

        int domKind[7] = { 2, 2, 2, 2, 2, 2, 2 };   // 1 buyers, -1 sellers, 0 balanced, 2 not shown
        float domDeltaPct[7] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
        const char* domTrend[7] = { "--", "--", "--", "--", "--", "--", "--" };
        bool domFlag[7] = { false, false, false, false, false, false, false };
        const char* shortLabels[7] = { "30m", "1h", "2h", "3h", "4h", "5h", "Ses" };
        SCString txtM;
        txtM.Format("MARKET ACTIVITY MONITOR\n%s\n", "INT    CENOVE PASMO     DELTA  DELTA%  DOMIN.  TREND      ZMENA");
        for (int w = 0; w < W; ++w)
        {
            if (!showW[w])
                continue;
            float sumAsk = 0.0f, sumBid = 0.0f;
            float hi = sc.High[i], lo = sc.Low[i];
            float deltaOld = 0.0f, deltaNew = 0.0f;   // delta of the first and of the second half of the interval
            const double mid = 0.5 * (starts[w] + lastT);
            int first = i;
            for (int j = i; j >= 0 && sc.BaseDateTimeIn[j].GetAsDouble() >= starts[w]; --j)
            {
                sumAsk += sc.AskVolume[j];
                sumBid += sc.BidVolume[j];
                if (sc.BaseDateTimeIn[j].GetAsDouble() >= mid)
                    deltaNew += sc.AskVolume[j] - sc.BidVolume[j];
                else
                    deltaOld += sc.AskVolume[j] - sc.BidVolume[j];
                hi = MaxF(hi, sc.High[j]);
                lo = MinF(lo, sc.Low[j]);
                first = j;
            }
            // Volume of the interval of the same length right before this one (not for the session).
            float prevVol = 0.0f;
            if (w < 6)
            {
                const double prevStart = starts[w] - (lastT - starts[w]);
                for (int j = first - 1; j >= 0 && sc.BaseDateTimeIn[j].GetAsDouble() >= prevStart; --j)
                    prevVol += sc.AskVolume[j] + sc.BidVolume[j];
            }
            const float vol = sumAsk + sumBid;
            const float d = sumAsk - sumBid;
            const float buyPct = vol > 0.0f ? 100.0f * sumAsk / vol : 0.0f;
            const float change = sc.Close[i] - sc.Open[first];
            const float range = hi - lo;
            const float efficiency = range > 0.0f ? fabsf(change) / range : 0.0f;
            const float domLimit = DominancePct.GetFloat();
            const char* who = buyPct >= domLimit ? "KUPUJI" : (buyPct <= 100.0f - domLimit ? "PRODAVA" : "VYROVN");
            domKind[w] = buyPct >= domLimit ? 1 : (buyPct <= 100.0f - domLimit ? -1 : 0);
            domDeltaPct[w] = vol > 0.0f ? 100.0f * d / vol : 0.0f;

            // A large delta without the matching price move: price went against it or hardly moved.
            const char* flag = "";
            if (fabsf(d) >= (float)SqueezeMinDelta.GetInt())
            {
                if (d > 0.0f && change < 0.0f) flag = "NESOULAD: kupuje se, cena klesa";
                else if (d < 0.0f && change > 0.0f) flag = "NESOULAD: prodava se, cena roste";
                else if (d > 0.0f && efficiency < 0.15f) flag = "NESOULAD: kupuje se, cena stoji";
                else if (d < 0.0f && efficiency < 0.15f) flag = "NESOULAD: prodava se, cena stoji";
            }

            domFlag[w] = flag[0] != '\0';
            domTrend[w] = efficiency < 0.30f ? "--" : (change > 0.0f ? "UP" : "DN");
            SCString rangeText;
            rangeText.Format("%.2f-%.2f", lo, hi);
            // Trend: direction of the price change in the interval and the share of its range the price covered.
            SCString trendText;
            if (efficiency < 0.30f) trendText.Format("BOCNI %.0f%%", 100.0f * efficiency);
            else trendText.Format("%s %.0f%%", change > 0.0f ? "NAHORU" : "DOLU", 100.0f * efficiency);
            SCString line;
            line.Format("%-6s %-15s %+6d %+6.2f%%  %-7s %-9s %+6.2f\n", labels[w], rangeText.GetChars(), (int)d,
                        vol > 0.0f ? 100.0f * d / vol : 0.0f, who, trendText.GetChars(), change);
            txtM.Append(line.GetChars());
            SCString detail;
            detail.Format("       obj %d   ASK %d / BID %d   kupujici %.1f%%\n", (int)vol, (int)sumAsk, (int)sumBid, buyPct);
            txtM.Append(detail.GetChars());
            if (flag[0] != '\0')
            {
                SCString flagLine;
                flagLine.Format("       ! %s\n", flag);
                txtM.Append(flagLine.GetChars());
            }

            if (ShowComments.GetYesNo())
            {
                SCString comment;
                const float pricePos = range > 0.0f ? (sc.Close[i] - lo) / range : 0.5f;
                const int topBandId = sc.GetPersistentInt(10 + w);
                if (ShowBands.GetYesNo() && topBandId > 0)
                {
                    const float bandLow = (topBandId - 1) * BandPoints.GetFloat();
                    const float bandHigh = bandLow + BandPoints.GetFloat();
                    SCString bandPart;
                    if (sc.Close[i] < bandLow) bandPart.Format("cena POD hlavnim pasmem %.0f-%.0f  ", bandLow, bandHigh);
                    else if (sc.Close[i] > bandHigh) bandPart.Format("cena NAD hlavnim pasmem %.0f-%.0f  ", bandLow, bandHigh);
                    else bandPart.Format("cena V hlavnim pasmu %.0f-%.0f  ", bandLow, bandHigh);
                    comment.Append(bandPart.GetChars());
                }
                if (pricePos >= 0.8f) comment.Append("cena u HIGH intervalu  ");
                else if (pricePos <= 0.2f) comment.Append("cena u LOW intervalu  ");
                if (prevVol > 0.0f)
                {
                    const float volRatio = vol / prevVol;
                    SCString part;
                    if (volRatio >= 1.5f) { part.Format("objem %.1fx vyssi nez predchozi  ", volRatio); comment.Append(part.GetChars()); }
                    else if (volRatio <= 0.6f) { part.Format("objem klesa (%.1fx predchozi)  ", volRatio); comment.Append(part.GetChars()); }
                }
                const float shiftLimit = 0.03f * vol;
                if (deltaOld * deltaNew < 0.0f && fabsf(deltaOld) >= shiftLimit && fabsf(deltaNew) >= shiftLimit)
                    comment.Append(deltaNew > 0.0f ? "DELTA SE OBRATILA: drive prodej, ted nakup  " : "DELTA SE OBRATILA: drive nakup, ted prodej  ");
                else if (deltaOld * deltaNew > 0.0f && fabsf(deltaNew) > 1.5f * fabsf(deltaOld))
                    comment.Append("tlak zrychluje  ");
                else if (deltaOld * deltaNew > 0.0f && fabsf(deltaNew) < 0.5f * fabsf(deltaOld))
                    comment.Append("tlak slabne  ");
                if (comment.GetLength() > 0)
                {
                    SCString commentLine;
                    commentLine.Format("       > %s\n", comment.GetChars());
                    txtM.Append(commentLine.GetChars());
                }
            }

            if (ShowBands.GetYesNo())
            {
                SCString& cache = sc.GetPersistentSCString(w + 1);
                if (cache.GetLength() > 0)
                {
                    SCString bandLine;
                    bandLine.Format("       pasma: %s\n", cache.GetChars());
                    txtM.Append(bandLine.GetChars());
                }
            }
        }

        // Dominance strip: every interval is its own small text, so each one can have its own color.
        {
            int slot = 0;
            for (int w = 0; w < W; ++w)
            {
                if (!ShowDomStrip.GetYesNo() || !showW[w])
                {
                    sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91840 + w);
                    continue;
                }
                SCString stripText;
                stripText.Format(" %s %+.1f%% %s%s", shortLabels[w], domDeltaPct[w], domTrend[w], domFlag[w] ? " !" : "");
                if (DomStripDetail.GetInt() == 1)
                {
                    stripText.Append(domKind[w] == 1 ? " KUPUJICI" : (domKind[w] == -1 ? " PRODAVAJICI" : " VYROVNANO"));
                }
                stripText.Append(" ");
                std::string padding((size_t)DomStripPad.GetInt(), ' ');
                std::string stripFull = padding + stripText.GetChars() + padding;
                stripText = stripFull.c_str();

                s_UseTool ToolD;
                ToolD.Clear();
                ToolD.ChartNumber = sc.ChartNumber;
                ToolD.DrawingType = DRAWING_TEXT;
                ToolD.LineNumber = 91840 + w;
                ToolD.AddMethod = UTAM_ADD_OR_ADJUST;
                ToolD.Region = sc.GraphRegion;
                ToolD.UseRelativeVerticalValues = 1;
                ToolD.BeginDateTime = DomStripX.GetInt() + slot * DomStripSpacing.GetInt();
                ToolD.BeginValue = (float)DomStripY.GetInt();
                ToolD.FontFace = FontName.GetString();
                ToolD.FontBold = 1;
                ToolD.FontSize = DomStripFont.GetInt() > 0 ? DomStripFont.GetInt() : BoxFont.GetInt();
                ToolD.Color = domKind[w] == 1 ? BuyColor.GetColor() : (domKind[w] == -1 ? SellColor.GetColor() : BoxColor.GetColor());
                ToolD.FontBackColor = BoxBack.GetColor();
                ToolD.TransparentLabelBackground = BoxTransparent.GetYesNo();
                ToolD.Text = stripText;
                sc.UseTool(ToolD);
                ++slot;
            }
        }

        if (ShowSlices.GetYesNo())
        {
            // Non-overlapping time slices make the development visible: where the buying or selling happened.
            const double bounds[6] = { 0.5, 1.0, 2.0, 3.0, 4.0, 5.0 };   // upper limits of the slices in hours back
            const char* sliceLabels[6] = { "0-30m", "30-60m", "1-2h", "2-3h", "3-4h", "4-5h" };
            float sliceDelta[6] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
            float sliceOpen[6] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
            float sliceClose[6] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
            bool sliceUsed[6] = { false, false, false, false, false, false };
            for (int j = i; j >= 0; --j)
            {
                const double hoursBack = (lastT - sc.BaseDateTimeIn[j].GetAsDouble()) * 24.0;
                if (hoursBack >= 5.0)
                    break;
                int sl = 0;
                while (sl < 5 && hoursBack >= bounds[sl])
                    ++sl;
                if (!sliceUsed[sl])
                {
                    sliceUsed[sl] = true;
                    sliceClose[sl] = sc.Close[j];
                }
                sliceOpen[sl] = sc.Open[j];
                sliceDelta[sl] += sc.AskVolume[j] - sc.BidVolume[j];
            }
            txtM.Append("\nVYVOJ PO VRSTVACH (nejstarsi -> nejnovejsi, delta / zmena ceny)\n");
            for (int sl = 5; sl >= 0; --sl)
            {
                if (!sliceUsed[sl])
                    continue;
                SCString part;
                part.Format("%s: %+d / %+.2f%s", sliceLabels[sl], (int)sliceDelta[sl], sliceClose[sl] - sliceOpen[sl], sl > 0 ? "  |  " : "");
                txtM.Append(part.GetChars());
            }
            txtM.Append("\n");
        }

        if (ShowLegend.GetYesNo())
        {
            SCString legend;
            legend.Format("Legenda: DOMIN. KUPUJI/PRODAVA = aspon %.1f%% agresivniho objemu na jedne strane, VYROVN = %.1f-%.1f%% (zadna strana nedominuje)\n"
                          "TREND = smer zmeny ceny v intervalu + podil jeho rozsahu, ktery cena urazila (pod 30%% = BOCNI)\n"
                          "NESOULAD = velka delta, ale cena sla proti ni nebo stoji (mozna absorpce)\n",
                          DominancePct.GetFloat(), 100.0f - DominancePct.GetFloat(), DominancePct.GetFloat());
            txtM.Append(legend.GetChars());
        }

        secMonitor = txtM;
        }
        else
        {
            for (int w = 0; w < W; ++w)
                sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91840 + w);
        }

        if (ShowPanelB.GetYesNo() || ShowTraps.GetYesNo())
        {
        SCString& txtB = secBig;
        SCString head;
        head.Format("VELKE OBJEMY (poslednich %d min, uzavrene bary)\n", EventWindowMin.GetInt());
        txtB.Append(head.GetChars());
        const double evStart = lastT - EventWindowMin.GetInt() / 1440.0;
        int shown = 0;
        for (int j = i - 1; j >= 0 && shown < MaxEvents.GetInt(); --j)
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
                part.Format("objem %.1fx prumer (delta %+d, cena %s)   ", VolRatioSG[j], (int)DeltaSG[j],
                            sc.Close[j] > sc.Open[j] ? "nahoru" : (sc.Close[j] < sc.Open[j] ? "dolu" : "stoji"));
                line.Append(part.GetChars());
            }
            line.Append("\n");
            txtB.Append(line.GetChars());
            ++shown;
        }
        if (shown == 0)
            txtB.Append("zadne\n");

        // Trapped traders: current state of the last closed bar and the last trapped-trader signal.
        secTraps.Append("TRAPPED TRADERS\n");
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
                trapLine.Format("SETUP %s: %s tlaci (delta %+d), nove %s se nedela; signal po prekonani %.2f\n",
                                sellers ? "LONG" : "SHORT", sellers ? "prodavajici" : "kupujici", (int)TrapPushSG[k],
                                sellers ? "low" : "high", TrapLevelSG[k]);
            else
                trapLine.Format("PAST AKTIVNI: %s v pasti, agresivni objem %d kontraktu je ted v ztrate (hruby odhad), uroven obratu %.2f\n",
                                sellers ? "prodavajici" : "kupujici", (int)TrapVolSG[k], TrapLevelSG[k]);
        }
        secTraps.Append(trapLine.GetChars());
        for (int j = k; j >= 0 && j >= i - 400; --j)
        {
            if (State.Arrays[3][j] == 0.0f)
                continue;
            SCString sig;
            const int ageMin = (int)((lastT - sc.BaseDateTimeIn[j].GetAsDouble()) * 1440.0 + 0.5);
            sig.Format("posledni signal %02d:%02d (pred %d h %02d min)  %s  (%s v pasti, hruby odhad %d kontraktu, uroven obratu %.2f)\n",
                       sc.BaseDateTimeIn[j].GetHour(), sc.BaseDateTimeIn[j].GetMinute(), ageMin / 60, ageMin % 60,
                       State.Arrays[3][j] > 0.0f ? "LONG" : "SHORT", State.Arrays[3][j] > 0.0f ? "prodavajici" : "kupujici",
                       (int)TrapVolSG[j], TrapLevelSG[j]);
            secTraps.Append(sig.GetChars());
            break;
        }

        }
    }

    // One text box assembled from the sections that are switched on, with a configurable width.
    if (i == sc.ArraySize - 1 && i > 0)
    {
        int& oldPanelsRemoved = sc.GetPersistentInt(4);
        if (!oldPanelsRemoved)
        {
            oldPanelsRemoved = 1;
            sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91828);
            sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91830);
        }

        SCString secCompact;
        if (DisplayMode.GetInt() == 0)
        {
            // Compact mode: only what is needed for a decision, a few short lines.
            const int k = i - 1;
            const double nowT = sc.BaseDateTimeIn[i].GetAsDouble();
            SCString part;
            if (ShowHeader.GetYesNo())
            {
                part.Format("cena %.2f   %02d:%02d\n", sc.Close[i], sc.BaseDateTimeIn[i].GetHour(), sc.BaseDateTimeIn[i].GetMinute());
                secCompact.Append(part.GetChars());
            }
            if (ShowTraps.GetYesNo())
            {
                const float st = TrapStateSG[k];
                const bool sellersSide = st > 0.0f;
                if (st == 0.0f)
                    part.Format("SIGNAL  bez setupu");
                else if (fabsf(st) == 1.0f)
                    part.Format("SETUP %s  %s tlaci\n       signal po prekonani %.2f", sellersSide ? "LONG" : "SHORT",
                                sellersSide ? "prodavajici" : "kupujici", TrapLevelSG[k]);
                else
                    part.Format("PAST %s  %s v pasti\n       uroven %.2f", sellersSide ? "LONG" : "SHORT",
                                sellersSide ? "prodavajici" : "kupujici", TrapLevelSG[k]);
                secCompact.Append(part.GetChars());
                for (int j = k; j >= 0 && j >= i - 400; --j)
                {
                    if (State.Arrays[3][j] == 0.0f)
                        continue;
                    const int ageMin = (int)((nowT - sc.BaseDateTimeIn[j].GetAsDouble()) * 1440.0 + 0.5);
                    part.Format("\nPOSLEDNI  %02d:%02d %s (pred %dh%02dm)", sc.BaseDateTimeIn[j].GetHour(),
                                sc.BaseDateTimeIn[j].GetMinute(), State.Arrays[3][j] > 0.0f ? "LONG" : "SHORT", ageMin / 60, ageMin % 60);
                    secCompact.Append(part.GetChars());
                    break;
                }
                secCompact.Append("\n");
            }
            if (ShowTraps.GetYesNo() && ClusterArrows.GetYesNo())
            {
                const float cMargin = ClusterMarginTicks.GetInt() * sc.TickSize;
                float cLo = 0.0f, cHi = 0.0f, cVol = 0.0f;
                if (ActiveCluster(sc, ClSellLo, ClSellHi, ClSellVol, k, ClusterMaxAge.GetInt(), cMargin, true, cLo, cHi, cVol))
                {
                    part.Format("KLASTR  PRODEJ %.2f-%.2f (%d)\n        LONG po close nad %.2f\n", cLo, cHi, (int)cVol, cHi + cMargin);
                    secCompact.Append(part.GetChars());
                }
                if (ActiveCluster(sc, ClBuyLo, ClBuyHi, ClBuyVol, k, ClusterMaxAge.GetInt(), cMargin, false, cLo, cHi, cVol))
                {
                    part.Format("KLASTR  NAKUP %.2f-%.2f (%d)\n        SHORT po close pod %.2f\n", cLo, cHi, (int)cVol, cLo - cMargin);
                    secCompact.Append(part.GetChars());
                }
            }
            if (HtfOn.GetYesNo())
            {
                // Position of the price against the daily, weekly and monthly VWAP of the other charts.
                const double nowSys = sc.CurrentSystemDateTime.GetAsDouble();
                double& lastScan = sc.GetPersistentDouble(2);
                const bool mayScan = nowSys - lastScan > 30.0 / 86400.0;
                bool scanned = false;
                const int htfChart[3] = { DailyChart.GetInt(), WeeklyChart.GetInt(), MonthlyChart.GetInt() };
                const int htfInput[3] = { DailyID.GetInt(), WeeklyID.GetInt(), MonthlyID.GetInt() };
                const int htfSub[3] = { DailySub.GetInt(), WeeklySub.GetInt(), MonthlySub.GetInt() };
                const char* htfName[3] = { "den", "tyd", "mes" };
                SCString vwapLine;
                int below = 0, above = 0, known = 0;
                for (int h = 0; h < 3; ++h)
                {
                    if (htfChart[h] <= 0)
                        continue;
                    int& found = sc.GetPersistentInt(21 + h);
                    int use = htfInput[h] > 0 ? htfInput[h] : found;
                    const bool wasUnknown = use == 0;
                    if (wasUnknown && mayScan)
                        scanned = true;
                    const float v = ReadHtfValue(sc, htfChart[h], use, htfSub[h], sc.Close[i], mayScan);
                    if (htfInput[h] == 0 && use > 0 && found != use)
                    {
                        found = use;
                        SCString logMsg;
                        logMsg.Format("Regime: %s VWAP found on chart %d, study ID %d (set it in the inputs if this is not the VWAP)", htfName[h], htfChart[h], use);
                        sc.AddMessageToLog(logMsg, 0);
                    }
                    if (v > 0.0f)
                    {
                        ++known;
                        if (sc.Close[i] < v)
                            ++below;
                        else
                            ++above;
                        part.Format("%s%s %+d", vwapLine.GetLength() > 0 ? " | " : "", htfName[h], (int)(sc.Close[i] - v));
                    }
                    else
                    {
                        part.Format("%s%s n/a", vwapLine.GetLength() > 0 ? " | " : "", htfName[h]);
                    }
                    vwapLine.Append(part.GetChars());
                }
                if (scanned)
                    lastScan = nowSys;
                if (vwapLine.GetLength() > 0)
                {
                    secCompact.Append("VWAP  cena vs ");
                    secCompact.Append(vwapLine.GetChars());
                    secCompact.Append("\n");
                    if (known > 0 && below == known)
                        secCompact.Append("REZIM pod vsemi = klesajici\n      LONG proti trendu, SHORT po trendu\n");
                    else if (known > 0 && above == known)
                        secCompact.Append("REZIM nad vsemi = rostouci\n      SHORT proti trendu, LONG po trendu\n");
                    else if (known > 0)
                        secCompact.Append("REZIM smisene = rotace, okraje oblasti\n");
                }
            }
            if (ShowPanel.GetYesNo())
            {
                SCString why;
                const int reason = (int)ReasonSG[k];
                if (reason & 1) why.Append("delta/cena ");
                if (reason & 2) why.Append("vyschly-extrem ");
                if (reason & 4) why.Append("velky-objem ");
                if (reason & 8) why.Append("shock ");
                if (why.GetLength() == 0) why.Append("-");
                part.Format("BAR  delta %+d (%+.1f%%)  vol %.1fx\n     watch: %s%s%s\n", (int)DeltaSG[k], DeltaPctSG[k], VolRatioSG[k],
                            why.GetChars(), StackBuySG[k] >= (float)StackCount.GetInt() ? " STACK+" : "",
                            StackSellSG[k] >= (float)StackCount.GetInt() ? " STACK-" : "");
                secCompact.Append(part.GetChars());
            }
            if (ShowIntervals.GetYesNo() && ShowBands.GetYesNo())
            {
                const int bandIds[2] = { sc.GetPersistentInt(11), sc.GetPersistentInt(16) };
                const char* bandLabels[2] = { "1h", "ses" };
                SCString positions;
                for (int q = 0; q < 2; ++q)
                {
                    if (bandIds[q] <= 0)
                        continue;
                    const float bandLow = (bandIds[q] - 1) * BandPoints.GetFloat();
                    const float bandHigh = bandLow + BandPoints.GetFloat();
                    part.Format("%s%s %.0f-%.0f %s", positions.GetLength() > 0 ? "  |  " : "PASMO  ", bandLabels[q], bandLow, bandHigh,
                                sc.Close[i] < bandLow ? "POD" : (sc.Close[i] > bandHigh ? "NAD" : "V"));
                    positions.Append(part.GetChars());
                }
                if (positions.GetLength() > 0)
                {
                    secCompact.Append(positions.GetChars());
                    secCompact.Append("\n");
                }
            }
            if (ShowSlices.GetYesNo())
            {
                // What happened in separate periods, newest first: delta in thousands of contracts / price change in points.
                const double sliceBounds[3] = { 0.5, 1.0, 2.0 };
                const char* sliceNames[4] = { "0-30m", "30-60m", "1-2h", "2-3h" };
                float sDelta[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
                float sOpen[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
                float sClose[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
                bool sUsed[4] = { false, false, false, false };
                for (int j = i; j >= 0; --j)
                {
                    const double hoursBack = (nowT - sc.BaseDateTimeIn[j].GetAsDouble()) * 24.0;
                    if (hoursBack >= 3.0)
                        break;
                    int sl = 0;
                    while (sl < 3 && hoursBack >= sliceBounds[sl])
                        ++sl;
                    if (!sUsed[sl])
                    {
                        sUsed[sl] = true;
                        sClose[sl] = sc.Close[j];
                    }
                    sOpen[sl] = sc.Open[j];
                    sDelta[sl] += sc.AskVolume[j] - sc.BidVolume[j];
                }
                SCString slicesLine;
                for (int sl = 0; sl < 4; ++sl)
                {
                    if (!sUsed[sl])
                        continue;
                    part.Format("%s%-6s %+.1fk/%+.1f", slicesLine.GetLength() > 0 ? (sl % 2 == 0 ? "\n       " : "  |  ") : "", sliceNames[sl],
                                sDelta[sl] / 1000.0f, sClose[sl] - sOpen[sl]);
                    slicesLine.Append(part.GetChars());
                }
                if (slicesLine.GetLength() > 0)
                {
                    secCompact.Append("VYVOJ  ");
                    secCompact.Append(slicesLine.GetChars());
                    secCompact.Append("\n");
                }
            }
            if (ShowPanelB.GetYesNo())
            {
                SCString prints;
                int shownPrints = 0;
                const double printStart = nowT - EventWindowMin.GetInt() / 1440.0;
                for (int j = i - 1; j >= 0 && shownPrints < MaxEvents.GetInt(); --j)
                {
                    if (sc.BaseDateTimeIn[j].GetAsDouble() < printStart)
                        break;
                    const bool lvl = EventLevelDeltaSG[j] != 0.0f;
                    const bool bigBar = fabsf(DeltaSG[j]) >= (float)BigBarDelta.GetInt();
                    const bool spike = VolRatioSG[j] >= SpikeMult.GetFloat();
                    if (!lvl && !bigBar && !spike)
                        continue;
                    part.Format("%s%02d:%02d", shownPrints > 0 ? "\n       " : "", sc.BaseDateTimeIn[j].GetHour(), sc.BaseDateTimeIn[j].GetMinute());
                    prints.Append(part.GetChars());
                    if (lvl)
                    {
                        part.Format(" %s %+d@%.2f", EventLevelDeltaSG[j] > 0.0f ? "NAKUP" : "PRODEJ", (int)EventLevelDeltaSG[j], EventLevelPriceSG[j]);
                        prints.Append(part.GetChars());
                    }
                    if (bigBar)
                    {
                        part.Format(" delta %+d", (int)DeltaSG[j]);
                        prints.Append(part.GetChars());
                    }
                    if (spike)
                    {
                        part.Format(" %.1fx obj. (d %+d, cena %s)", VolRatioSG[j], (int)DeltaSG[j],
                                    sc.Close[j] > sc.Open[j] ? "nahoru" : (sc.Close[j] < sc.Open[j] ? "dolu" : "stoji"));
                        prints.Append(part.GetChars());
                    }
                    ++shownPrints;
                }
                if (shownPrints > 0)
                {
                    secCompact.Append("VELKE  ");
                    secCompact.Append(prints.GetChars());
                    secCompact.Append("\n");
                }
            }
            if (ShowStats.GetYesNo())
            {
                part.Format("STAT  W %d / L %d  (%.0f%%)%s\n", (int)Wins[k], (int)Losses[k], WinRate[k],
                            (int)(Wins[k] + Losses[k]) < 30 ? "  neprukazne (<30)" : "");
                secCompact.Append(part.GetChars());
            }
        }

        const char* texts[6] = { secHeader.GetChars(), secLastBar.GetChars(), secStats.GetChars(),
                                 secMonitor.GetChars(), secBig.GetChars(), secTraps.GetChars() };
        bool on[6] = { ShowHeader.GetYesNo() != 0, ShowPanel.GetYesNo() != 0, ShowStats.GetYesNo() != 0,
                             ShowIntervals.GetYesNo() != 0, ShowPanelB.GetYesNo() != 0, ShowTraps.GetYesNo() != 0 };

        if (DisplayMode.GetInt() == 0)
        {
            texts[0] = secCompact.GetChars();
            on[0] = true;
            for (int q = 1; q < 6; ++q)
                on[q] = false;
        }

        std::string raw;
        for (int q = 0; q < 6; ++q)
        {
            std::string part = texts[q];
            while (!part.empty() && part[part.size() - 1] == '\n')
                part.erase(part.size() - 1);
            if (!on[q] || part.empty())
                continue;
            if (!raw.empty())
                raw += "\n\n";
            raw += part;
        }

        if (raw.empty())
        {
            sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, 91827);
        }
        else
        {
            const std::string boxed = BoxText(raw, BoxWidth.GetInt() > 0 ? (size_t)BoxWidth.GetInt() : 0);

            s_UseTool Tool;
            Tool.Clear();
            Tool.ChartNumber = sc.ChartNumber;
            Tool.DrawingType = DRAWING_TEXT;
            Tool.LineNumber = 91827;
            Tool.AddMethod = UTAM_ADD_OR_ADJUST;
            Tool.Region = sc.GraphRegion;
            Tool.UseRelativeVerticalValues = 1;
            Tool.BeginDateTime = BoxX.GetInt();
            Tool.BeginValue = (float)BoxY.GetInt();
            Tool.FontFace = FontName.GetString();
            Tool.FontBold = BoldText.GetYesNo();
            Tool.FontSize = BoxFont.GetInt();
            Tool.Color = BoxColor.GetColor();
            Tool.FontBackColor = BoxBack.GetColor();
            Tool.TransparentLabelBackground = BoxTransparent.GetYesNo();
            Tool.Text = boxed.c_str();
            sc.UseTool(Tool);
        }
    }

    // Re-send the history of markers every ~20 s from the last bar (placed before the early return, because the last bar is usually still open): if the other chart was not ready during the
    // full recalculation (or was reloaded), the markers drawn then are lost and would never come back otherwise.
    if (TargetChart.GetInt() > 0 && i == sc.ArraySize - 1)
    {
        const double nowTime = sc.CurrentSystemDateTime.GetAsDouble();
        double& lastResync = sc.GetPersistentDouble(1);
        if (nowTime - lastResync > 20.0 / 86400.0)
        {
            lastResync = nowTime;
            int sent = 0, failed = 0;
            const bool wantedAll[4] = { MirrorDots.GetYesNo() != 0, MirrorDots.GetYesNo() != 0,
                                        MirrorArrows.GetYesNo() != 0, MirrorArrows.GetYesNo() != 0 };
            const int markerTypesAll[4] = { MARKER_POINT, MARKER_POINT, MARKER_ARROWUP, MARKER_ARROWDOWN };
            const unsigned int colorsAll[4] = { (unsigned int)LongWatch.PrimaryColor, (unsigned int)ShortWatch.PrimaryColor,
                                                (unsigned int)LongTrigger.PrimaryColor, (unsigned int)ShortTrigger.PrimaryColor };
            for (int idx = MaxI(0, sc.ArraySize - MarkerHistoryBars.GetInt()); idx < sc.ArraySize - 1; ++idx)
            {
                const float pricesAll[4] = { LongWatch[idx], ShortWatch[idx], LongTrigger[idx], ShortTrigger[idx] };
                for (int t = 0; t < 4; ++t)
                {
                    if (!wantedAll[t] || pricesAll[t] == 0.0f)
                        continue;
                    s_UseTool Marker;
                    Marker.Clear();
                    Marker.ChartNumber = TargetChart.GetInt();
                    Marker.DrawingType = DRAWING_MARKER;
                    Marker.LineNumber = 700000 + (idx % 200000) * 4 + t;
                    Marker.AddMethod = UTAM_ADD_OR_ADJUST;
                    Marker.Region = 0;
                    Marker.BeginDateTime = sc.BaseDateTimeIn[idx];
                    Marker.BeginValue = pricesAll[t];
                    Marker.MarkerType = markerTypesAll[t];
                    Marker.MarkerSize = t < 2 ? DotSize.GetInt() : ArrowSize.GetInt();
                    Marker.Color = colorsAll[t];
                    if (sc.UseTool(Marker))
                        ++sent;
                    else
                        ++failed;
                }
            }
            int& lastLoggedSent = sc.GetPersistentInt(6);
            if (sent + failed != lastLoggedSent)
            {
                lastLoggedSent = sent + failed;
                SCString mirrorMsg;
                mirrorMsg.Format("Mirror to chart %d: %d markers sent, %d refused by UseTool", TargetChart.GetInt(), sent, failed);
                sc.AddMessageToLog(mirrorMsg, 0);
            }
        }
    }

    if (!barClosed || volume <= 0.0f)
        return;

    // Baselines from the previous bars only.
    float avgVolume = 0.0f, avgLevelVol = 0.0f, avgAbsDelta = 0.0f;
    int levelSamples = 0;
    if (i >= n)
    {
        for (int j = i - n; j < i; ++j)
        {
            avgVolume += sc.Volume[j];
            avgAbsDelta += fabsf(DeltaSG[j]);
            if (AvgLevelSG[j] > 0.0f)
            {
                avgLevelVol += AvgLevelSG[j];
                ++levelSamples;
            }
        }
        avgVolume /= n;
        avgAbsDelta /= n;
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

    if (haveFootprint && ClusterArrows.GetYesNo())
    {
        const ClusterResult cs = FindCluster(sc, i, true, ClusterLevels.GetInt(), (float)ClusterMinContracts.GetInt(),
                                             ClusterMinShare.GetFloat() / 100.0f, ClusterDominance.GetFloat());
        const ClusterResult cb = FindCluster(sc, i, false, ClusterLevels.GetInt(), (float)ClusterMinContracts.GetInt(),
                                             ClusterMinShare.GetFloat() / 100.0f, ClusterDominance.GetFloat());
        ClSellLo[i] = cs.low;
        ClSellHi[i] = cs.high;
        ClSellVol[i] = cs.vol;
        ClBuyLo[i] = cb.low;
        ClBuyHi[i] = cb.high;
        ClBuyVol[i] = cb.vol;
    }

    if (i < n + 1 || avgVolume <= 0.0f)
        return;

    // Trapped traders: evaluated for both sides, the stronger state is kept.
    TrapResult trapSell = TrapResult(), trapBuy = TrapResult();
    if (haveFootprint)
    {
        trapSell = EvaluateTrap(sc, DeltaSG, i, true, TrapLookback.GetInt(), TrapMinPushTicks.GetInt(),
                                (float)TrapMinPushDelta.GetInt(), TrapStallBars.GetInt(), TrapMarginTicks.GetInt(),
                                TrapMinFraction.GetFloat(), TrapMinContracts.GetFloat(), TrapLevelMode.GetInt(),
                                TrapOriginFraction.GetFloat(), TrapPushRangeMult.GetFloat(), TrapPushDeltaMult.GetFloat(),
                                TrapMaxStallRange.GetFloat());
        trapBuy = EvaluateTrap(sc, DeltaSG, i, false, TrapLookback.GetInt(), TrapMinPushTicks.GetInt(),
                               (float)TrapMinPushDelta.GetInt(), TrapStallBars.GetInt(), TrapMarginTicks.GetInt(),
                               TrapMinFraction.GetFloat(), TrapMinContracts.GetFloat(), TrapLevelMode.GetInt(),
                               TrapOriginFraction.GetFloat(), TrapPushRangeMult.GetFloat(), TrapPushDeltaMult.GetFloat(),
                               TrapMaxStallRange.GetFloat());
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
    bool longFromTrap = arrowMode != 0 && TrapStateSG[i] == 2.0f && sc.Close[i] > sc.Open[i] && delta > 0.0f
        && delta >= TrapReactionMult.GetFloat() * avgAbsDelta;
    bool shortFromTrap = arrowMode != 0 && TrapStateSG[i] == -2.0f && sc.Close[i] < sc.Open[i] && delta < 0.0f
        && -delta >= TrapReactionMult.GetFloat() * avgAbsDelta;
    if ((longFromTrap || shortFromTrap) && TrapLocationHours.GetFloat() > 0.0f)
    {
        // A reversal means more at the edge of a larger range than in the middle of it.
        const double rangeStart = sc.BaseDateTimeIn[i].GetAsDouble() - TrapLocationHours.GetFloat() / 24.0;
        float rangeHigh = sc.High[i], rangeLow = sc.Low[i];
        for (int j = i; j >= 0 && sc.BaseDateTimeIn[j].GetAsDouble() >= rangeStart; --j)
        {
            rangeHigh = MaxF(rangeHigh, sc.High[j]);
            rangeLow = MinF(rangeLow, sc.Low[j]);
        }
        const float edge = (rangeHigh - rangeLow) * TrapLocationPct.GetFloat() / 100.0f;
        if (longFromTrap && sc.Low[trap.swing] > rangeLow + edge)
            longFromTrap = false;
        if (shortFromTrap && sc.High[trap.swing] < rangeHigh - edge)
            shortFromTrap = false;
    }
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

    // Cluster arrows: aggressive sells (buys) piled up on a few levels, price closes through them against that side.
    // The cluster may come from this bar (then the bar itself must close beyond it in its own direction) or from
    // one of the last ClusterMaxAge bars that price has not closed through yet. Room to run is not required here,
    // because price is by definition already beyond the cluster.
    bool longFromCluster = false, shortFromCluster = false;
    if (ClusterArrows.GetYesNo() && haveFootprint)
    {
        const float cMargin = ClusterMarginTicks.GetInt() * sc.TickSize;
        float cLo = 0.0f, cHi = 0.0f, cVol = 0.0f;
        if (ActiveCluster(sc, ClSellLo, ClSellHi, ClSellVol, i - 1, ClusterMaxAge.GetInt(), cMargin, true, cLo, cHi, cVol)
            && sc.Close[i] > cHi + cMargin && (!ClusterNeedDelta.GetYesNo() || delta > 0.0f))
            longFromCluster = true;
        else if (ClSellVol[i] > 0.0f && sc.Close[i] > ClSellHi[i] + cMargin && sc.Close[i] > sc.Open[i])
            longFromCluster = true;
        if (ActiveCluster(sc, ClBuyLo, ClBuyHi, ClBuyVol, i - 1, ClusterMaxAge.GetInt(), cMargin, false, cLo, cHi, cVol)
            && sc.Close[i] < cLo - cMargin && (!ClusterNeedDelta.GetYesNo() || delta < 0.0f))
            shortFromCluster = true;
        else if (ClBuyVol[i] > 0.0f && sc.Close[i] < ClBuyLo[i] - cMargin && sc.Close[i] < sc.Open[i])
            shortFromCluster = true;
        if (longFromCluster && shortFromCluster)
            longFromCluster = shortFromCluster = false;   // conflicting clusters: no arrow
    }

    bool newTrigger = false;
    if (longFromCluster && !blockedLong && notChasedLong)
    {
        LongTrigger[i] = sc.Low[i] - 2.0f * sc.TickSize;
        State.Arrays[0][i] = 1.0f;
        State.Arrays[1][i] = sc.Close[i];
        newTrigger = true;
    }
    else if (shortFromCluster && !blockedShort && notChasedShort)
    {
        ShortTrigger[i] = sc.High[i] + 2.0f * sc.TickSize;
        State.Arrays[0][i] = -1.0f;
        State.Arrays[1][i] = sc.Close[i];
        newTrigger = true;
    }
    else if ((longFromAbsorption || longFromTrap) && !blockedLong && roomLong && notChasedLong)
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

    // Mirror the dots and arrows to another chart (e.g. the VWAP / composite chart) as drawings at the same time and price.
    // The signals are still computed from the footprint and delta of this chart.
    if (TargetChart.GetInt() > 0 && i >= sc.ArraySize - MarkerHistoryBars.GetInt())
    {
        const float prices[4] = { LongWatch[i], ShortWatch[i], LongTrigger[i], ShortTrigger[i] };
        const bool wanted[4] = { MirrorDots.GetYesNo() != 0, MirrorDots.GetYesNo() != 0,
                                 MirrorArrows.GetYesNo() != 0, MirrorArrows.GetYesNo() != 0 };
        const int markerTypes[4] = { MARKER_POINT, MARKER_POINT, MARKER_ARROWUP, MARKER_ARROWDOWN };
        const unsigned int colors[4] = { (unsigned int)LongWatch.PrimaryColor, (unsigned int)ShortWatch.PrimaryColor,
                                         (unsigned int)LongTrigger.PrimaryColor, (unsigned int)ShortTrigger.PrimaryColor };
        for (int t = 0; t < 4; ++t)
        {
            const int lineNumber = 700000 + (i % 200000) * 4 + t;
            if (wanted[t] && prices[t] != 0.0f)
            {
                s_UseTool Marker;
                Marker.Clear();
                Marker.ChartNumber = TargetChart.GetInt();
                Marker.DrawingType = DRAWING_MARKER;
                Marker.LineNumber = lineNumber;
                Marker.AddMethod = UTAM_ADD_OR_ADJUST;
                Marker.Region = 0;
                Marker.BeginDateTime = sc.BaseDateTimeIn[i];
                Marker.BeginValue = prices[t];
                Marker.MarkerType = markerTypes[t];
                Marker.MarkerSize = t < 2 ? DotSize.GetInt() : ArrowSize.GetInt();
                Marker.Color = colors[t];
                sc.UseTool(Marker);
            }
            else
            {
                sc.DeleteACSChartDrawing(TargetChart.GetInt(), TOOL_DELETE_CHARTDRAWING, lineNumber);
            }
        }
    }
}
