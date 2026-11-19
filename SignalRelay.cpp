#include "sierrachart.h"

SCDLLName("Signal Relay")

// Companion study for the chart with the VWAP / composites. It reads the dots and arrows that
// "Order Flow Compass" computes on another chart (the Renko footprint chart) and draws them here
// as ordinary study subgraphs, matched by time. Add it to the VWAP chart, set the source chart number and the
// ID of the monitor study on that chart (shown in its settings window as "ID:").

SCSFExport scsf_SignalRelay(SCStudyInterfaceRef sc)
{
    SCSubgraphRef LongWatch = sc.Subgraph[0];
    SCSubgraphRef ShortWatch = sc.Subgraph[1];
    SCSubgraphRef LongTrigger = sc.Subgraph[2];
    SCSubgraphRef ShortTrigger = sc.Subgraph[3];

    SCInputRef SourceChart = sc.Input[0];
    SCInputRef SourceStudyID = sc.Input[1];
    SCInputRef History = sc.Input[2];
    SCInputRef DotSize = sc.Input[3];
    SCInputRef ArrowSize = sc.Input[4];
    SCInputRef ArrowStyle = sc.Input[5];
    SCInputRef DotColor = sc.Input[6];
    SCInputRef LongColor = sc.Input[7];
    SCInputRef ShortColor = sc.Input[8];
    SCInputRef DotShortColor = sc.Input[9];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Signal Relay (dots and arrows from another chart)";
        sc.StudyDescription = "Shows the yellow dots and LONG/SHORT arrows of Order Flow Compass from another chart.";
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
        SourceStudyID.Name = "ID of the Order Flow Compass study on the source chart";
        SourceStudyID.SetInt(4);
        SourceStudyID.SetIntLimits(1, 10000);
        History.Name = "Number of latest bars of this chart to fill";
        History.SetInt(3000);
        History.SetIntLimits(10, 100000);
        DotSize.Name = "Dot size";
        DotSize.SetInt(5);
        DotSize.SetIntLimits(1, 30);
        ArrowSize.Name = "LONG / SHORT symbol size";
        ArrowSize.SetInt(7);
        ArrowSize.SetIntLimits(1, 30);
        ArrowStyle.Name = "LONG / SHORT symbol (0 arrow, 1 triangle, 2 diamond, 3 square)";
        ArrowStyle.SetInt(1);
        ArrowStyle.SetIntLimits(0, 3);
        DotColor.Name = "Dot color below the bar = sellers absorbed, potential growth (light green)";
        DotColor.SetColor(RGB(120, 220, 120));
        DotShortColor.Name = "Dot color above the bar = buyers absorbed, potential fall (light red)";
        DotShortColor.SetColor(RGB(255, 130, 130));
        LongColor.Name = "LONG color";
        LongColor.SetColor(RGB(0, 170, 0));
        ShortColor.Name = "SHORT color";
        ShortColor.SetColor(RGB(210, 0, 0));
        return;
    }

    {
        const int styleUp[4] = { DRAWSTYLE_ARROW_UP, DRAWSTYLE_TRIANGLE_UP, DRAWSTYLE_DIAMOND, DRAWSTYLE_SQUARE };
        const int styleDown[4] = { DRAWSTYLE_ARROW_DOWN, DRAWSTYLE_TRIANGLE_DOWN, DRAWSTYLE_DIAMOND, DRAWSTYLE_SQUARE };
        LongTrigger.DrawStyle = styleUp[ArrowStyle.GetInt()];
        ShortTrigger.DrawStyle = styleDown[ArrowStyle.GetInt()];
        LongWatch.LineWidth = ShortWatch.LineWidth = DotSize.GetInt();
        LongTrigger.LineWidth = ShortTrigger.LineWidth = ArrowSize.GetInt();
        LongWatch.PrimaryColor = DotColor.GetColor();
        ShortWatch.PrimaryColor = DotShortColor.GetColor();
        LongTrigger.PrimaryColor = LongColor.GetColor();
        ShortTrigger.PrimaryColor = ShortColor.GetColor();
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
            msg.Format("Signal Relay: no data from chart %d study ID %d - check the chart number and the ID in the study settings",
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
