#include "sierrachart.h"

SCDLLName("ES Absorption Mirror")

// Companion study for the chart with the VWAP / composites. It reads the dots and arrows that
// "ES Absorption Reversal Monitor" computes on another chart (the Renko footprint chart) and draws them here
// as ordinary study subgraphs, matched by time. Add it to the VWAP chart, set the source chart number and the
// ID of the monitor study on that chart (shown in its settings window as "ID:").

SCSFExport scsf_ESAbsorptionMirror(SCStudyInterfaceRef sc)
{
    SCSubgraphRef LongWatch = sc.Subgraph[0];
    SCSubgraphRef ShortWatch = sc.Subgraph[1];
    SCSubgraphRef LongTrigger = sc.Subgraph[2];
    SCSubgraphRef ShortTrigger = sc.Subgraph[3];

    SCInputRef SourceChart = sc.Input[0];
    SCInputRef SourceStudyID = sc.Input[1];
    SCInputRef History = sc.Input[2];

    if (sc.SetDefaults)
    {
        sc.GraphName = "ES Absorption Mirror (dots and arrows from the Renko chart)";
        sc.StudyDescription = "Shows the yellow dots and LONG/SHORT arrows of ES Absorption Reversal Monitor from another chart.";
        sc.AutoLoop = 0;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.UpdateAlways = 1;

        LongWatch.Name = "Seller absorption watch (dot below bar)";
        LongWatch.DrawStyle = DRAWSTYLE_POINT_ON_LOW;
        LongWatch.PrimaryColor = RGB(255, 190, 0);
        LongWatch.LineWidth = 6;
        ShortWatch.Name = "Buyer absorption watch (dot above bar)";
        ShortWatch.DrawStyle = DRAWSTYLE_POINT_ON_HIGH;
        ShortWatch.PrimaryColor = RGB(255, 190, 0);
        ShortWatch.LineWidth = 6;
        LongTrigger.Name = "LONG";
        LongTrigger.DrawStyle = DRAWSTYLE_ARROW_UP;
        LongTrigger.PrimaryColor = RGB(0, 180, 0);
        LongTrigger.LineWidth = 9;
        ShortTrigger.Name = "SHORT";
        ShortTrigger.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        ShortTrigger.PrimaryColor = RGB(220, 0, 0);
        ShortTrigger.LineWidth = 9;

        SourceChart.Name = "Source chart number (the # of the Renko chart)";
        SourceChart.SetInt(7);
        SourceChart.SetIntLimits(1, 200);
        SourceStudyID.Name = "ID of the ES Absorption Reversal Monitor study on the source chart";
        SourceStudyID.SetInt(4);
        SourceStudyID.SetIntLimits(1, 10000);
        History.Name = "Number of latest bars of this chart to fill";
        History.SetInt(3000);
        History.SetIntLimits(10, 100000);
        return;
    }

    SCDateTimeArray sourceTime;
    sc.GetChartDateTimeArray(SourceChart.GetInt(), sourceTime);
    const int sourceCount = sourceTime.GetArraySize();
    if (sourceCount <= 0)
        return;

    SCFloatArray srcLongWatch, srcShortWatch, srcLongTrigger, srcShortTrigger;
    sc.GetStudyArrayFromChartUsingID(SourceChart.GetInt(), SourceStudyID.GetInt(), 0, srcLongWatch);
    sc.GetStudyArrayFromChartUsingID(SourceChart.GetInt(), SourceStudyID.GetInt(), 1, srcShortWatch);
    sc.GetStudyArrayFromChartUsingID(SourceChart.GetInt(), SourceStudyID.GetInt(), 2, srcLongTrigger);
    sc.GetStudyArrayFromChartUsingID(SourceChart.GetInt(), SourceStudyID.GetInt(), 3, srcShortTrigger);
    if (srcLongWatch.GetArraySize() <= 0)
    {
        int& warned = sc.GetPersistentInt(1);
        if (!warned)
        {
            warned = 1;
            SCString msg;
            msg.Format("ES Absorption Mirror: no data from chart %d study ID %d - check the chart number and the ID in the study settings",
                       SourceChart.GetInt(), SourceStudyID.GetInt());
            sc.AddMessageToLog(msg, 1);
        }
        return;   // wrong chart number or study ID
    }

    const int first = sc.ArraySize - History.GetInt() > 0 ? sc.ArraySize - History.GetInt() : 0;
    int s = 0;   // source bars and bars of this chart are both sorted by time
    for (int j = first; j < sc.ArraySize; ++j)
    {
        LongWatch[j] = 0.0f;
        ShortWatch[j] = 0.0f;
        LongTrigger[j] = 0.0f;
        ShortTrigger[j] = 0.0f;

        const double from = sc.BaseDateTimeIn[j].GetAsDouble();
        const double to = j + 1 < sc.ArraySize ? sc.BaseDateTimeIn[j + 1].GetAsDouble() : 1.0e9;
        while (s < sourceCount && sourceTime[s].GetAsDouble() < from)
            ++s;
        for (int k = s; k < sourceCount && sourceTime[k].GetAsDouble() < to; ++k)
        {
            if (srcLongWatch[k] != 0.0f)
                LongWatch[j] = srcLongWatch[k];
            if (srcShortWatch[k] != 0.0f)
                ShortWatch[j] = srcShortWatch[k];
            if (srcLongTrigger[k] != 0.0f)
                LongTrigger[j] = srcLongTrigger[k];
            if (srcShortTrigger[k] != 0.0f)
                ShortTrigger[j] = srcShortTrigger[k];
        }
    }
}
