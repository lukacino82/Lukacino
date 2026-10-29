#include "sierrachart.h"
#include <cmath>
#include <map>

SCDLLName("ES Market Activity Monitor")

static inline float MaxF(float a, float b) { return a > b ? a : b; }
static inline float MinF(float a, float b) { return a < b ? a : b; }

// Market Activity Monitor: for 30 min, 1-5 hours and the session shows the price range, traded volume,
// aggressive buying (ask volume), aggressive selling (bid volume), cumulative delta, who dominated and in which
// price bands most of the volume was traded. A large delta without a matching price move is flagged.
SCSFExport scsf_ESMarketActivityMonitor(SCStudyInterfaceRef sc)
{
    SCInputRef SessionStartHour = sc.Input[0];
    SCInputRef DominancePct = sc.Input[1];
    SCInputRef BandPoints = sc.Input[2];
    SCInputRef ShowBands = sc.Input[3];
    SCInputRef MismatchDelta = sc.Input[4];
    SCInputRef PosX = sc.Input[5];
    SCInputRef PosY = sc.Input[6];
    SCInputRef FontSize = sc.Input[7];

    const int kLineNumber = 91830;

    if (sc.SetDefaults)
    {
        sc.GraphName = "ES Market Activity Monitor (unverified)";
        sc.StudyDescription = "Price range, volume, aggressive buying/selling, delta, dominance and price bands for 30 min, 1-5 h and the session.";
        sc.AutoLoop = 0;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.MaintainVolumeAtPriceData = 1;

        SessionStartHour.Name = "Session start (hour of the chart time, e.g. 15.5 = 15:30)";
        SessionStartHour.SetFloat(0.0f);
        SessionStartHour.SetFloatLimits(0.0f, 23.99f);
        DominancePct.Name = "Dominance: share of aggressive buying (%) from which BUYERS dominate (SELLERS below 100 - this)";
        DominancePct.SetFloat(52.0f);
        DominancePct.SetFloatLimits(50.0f, 90.0f);
        BandPoints.Name = "Price band size (points)";
        BandPoints.SetFloat(5.0f);
        BandPoints.SetFloatLimits(0.25f, 500.0f);
        ShowBands.Name = "Show price bands with most volume";
        ShowBands.SetYesNo(1);
        MismatchDelta.Name = "Flag delta without price move: minimum |net delta| (contracts)";
        MismatchDelta.SetInt(2000);
        MismatchDelta.SetIntLimits(10, 10000000);
        PosX.Name = "Panel position: horizontal (% of chart width)";
        PosX.SetInt(3);
        PosX.SetIntLimits(0, 95);
        PosY.Name = "Panel position: vertical (% of chart height, 100 = top)";
        PosY.SetInt(76);
        PosY.SetIntLimits(5, 100);
        FontSize.Name = "Font size";
        FontSize.SetInt(9);
        FontSize.SetIntLimits(6, 24);
        return;
    }

    if (sc.LastCallToFunction)
    {
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, kLineNumber);
        return;
    }

    if (sc.ArraySize < 2)
        return;

    const int last = sc.ArraySize - 1;
    const double lastT = sc.BaseDateTimeIn[last].GetAsDouble();
    double sessionStart = floor(lastT) + SessionStartHour.GetFloat() / 24.0;
    if (sessionStart > lastT)
        sessionStart -= 1.0;

    const int W = 7;
    const char* labels[7] = { "30 min", "1 h", "2 h", "3 h", "4 h", "5 h", "Seance" };
    const double starts[7] = { lastT - 0.5 / 24.0, lastT - 1.0 / 24.0, lastT - 2.0 / 24.0, lastT - 3.0 / 24.0,
                               lastT - 4.0 / 24.0, lastT - 5.0 / 24.0, sessionStart };

    // Price bands are rebuilt once per new bar because they read Volume at Price of every bar in the windows.
    int& lastBandBar = sc.GetPersistentInt(1);
    if (ShowBands.GetYesNo() && lastBandBar != last)
    {
        lastBandBar = last;
        double earliest = starts[0];
        for (int w = 1; w < W; ++w)
            earliest = starts[w] < earliest ? starts[w] : earliest;

        std::map<int, float> bands[7];
        const float bandSize = BandPoints.GetFloat();
        for (int j = last; j >= 0; --j)
        {
            const double t = sc.BaseDateTimeIn[j].GetAsDouble();
            if (t < earliest)
                break;
            const int size = (int)sc.VolumeAtPriceForBars->GetSizeAtBarIndex((unsigned int)j);
            for (int k = 0; k < size; ++k)
            {
                const s_VolumeAtPriceV2* p = NULL;
                sc.VolumeAtPriceForBars->GetVAPElementAtIndex(j, k, &p);
                if (p == NULL)
                    continue;
                const float vol = (float)p->BidVolume + (float)p->AskVolume;
                const int band = (int)floor((p->PriceInTicks * sc.TickSize) / bandSize);
                for (int w = 0; w < W; ++w)
                {
                    if (t >= starts[w])
                        bands[w][band] += vol;
                }
            }
        }

        typedef std::map<int, float>::const_iterator Iter;
        for (int w = 0; w < W; ++w)
        {
            SCString& cache = sc.GetPersistentSCString(w + 1);
            cache.Format("%s", "");
            float total = 0.0f;
            for (Iter it = bands[w].begin(); it != bands[w].end(); ++it)
                total += it->second;
            int picked[3] = { 0, 0, 0 };
            for (int rank = 0; rank < 3; ++rank)
            {
                float best = 0.0f;
                int bestBand = 0;
                bool found = false;
                for (Iter it = bands[w].begin(); it != bands[w].end(); ++it)
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
                SCString part;
                part.Format("%s%.0f-%.0f %.0f%%", rank == 0 ? "" : "   ", bestBand * bandSize, (bestBand + 1) * bandSize, 100.0f * best / total);
                cache.Append(part.GetChars());
            }
        }
    }

    SCString txt;
    txt.Format("MARKET ACTIVITY MONITOR   cena %.2f\n", sc.Close[last]);
    for (int w = 0; w < W; ++w)
    {
        float sumAsk = 0.0f, sumBid = 0.0f;
        float hi = sc.High[last], lo = sc.Low[last];
        int first = last;
        for (int j = last; j >= 0 && sc.BaseDateTimeIn[j].GetAsDouble() >= starts[w]; --j)
        {
            sumAsk += sc.AskVolume[j];
            sumBid += sc.BidVolume[j];
            hi = MaxF(hi, sc.High[j]);
            lo = MinF(lo, sc.Low[j]);
            first = j;
        }
        const float vol = sumAsk + sumBid;
        const float delta = sumAsk - sumBid;
        const float buyPct = vol > 0.0f ? 100.0f * sumAsk / vol : 0.0f;
        const float change = sc.Close[last] - sc.Open[first];
        const float range = hi - lo;
        const float efficiency = range > 0.0f ? fabsf(change) / range : 0.0f;
        const float limit = DominancePct.GetFloat();
        const char* who = buyPct >= limit ? "KUPUJICI" : (buyPct <= 100.0f - limit ? "PRODAVAJICI" : "VYROVNANO");

        // A large delta without the matching price move: price went against it or hardly moved.
        const char* flag = "";
        if (fabsf(delta) >= (float)MismatchDelta.GetInt())
        {
            if (delta > 0.0f && change < 0.0f) flag = "NESOULAD: kupuje se, cena klesa";
            else if (delta < 0.0f && change > 0.0f) flag = "NESOULAD: prodava se, cena roste";
            else if (delta > 0.0f && efficiency < 0.25f) flag = "NESOULAD: kupuje se, cena stoji";
            else if (delta < 0.0f && efficiency < 0.25f) flag = "NESOULAD: prodava se, cena stoji";
        }

        SCString line;
        line.Format("%-6s %.2f-%.2f | obj %d | ASK %d / BID %d | delta %+d | %s %.0f%% | zmena %+.2f  %s\n",
                    labels[w], lo, hi, (int)vol, (int)sumAsk, (int)sumBid, (int)delta, who, buyPct, change, flag);
        txt.Append(line.GetChars());

        if (ShowBands.GetYesNo())
        {
            SCString& cache = sc.GetPersistentSCString(w + 1);
            if (cache.GetLength() > 0)
            {
                SCString bandLine;
                bandLine.Format("       pasma: %s\n", cache.GetChars());
                txt.Append(bandLine.GetChars());
            }
        }
    }

    s_UseTool Tool;
    Tool.Clear();
    Tool.ChartNumber = sc.ChartNumber;
    Tool.DrawingType = DRAWING_TEXT;
    Tool.LineNumber = kLineNumber;
    Tool.AddMethod = UTAM_ADD_OR_ADJUST;
    Tool.Region = sc.GraphRegion;
    Tool.UseRelativeVerticalValues = 1;
    Tool.BeginDateTime = PosX.GetInt();
    Tool.BeginValue = (float)PosY.GetInt();
    Tool.FontSize = FontSize.GetInt();
    Tool.Color = RGB(255, 255, 255);
    Tool.FontBackColor = RGB(30, 30, 30);
    Tool.TransparentLabelBackground = 0;
    Tool.Text = txt;
    sc.UseTool(Tool);
}
