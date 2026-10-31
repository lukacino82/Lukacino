// Research Export - Sierra Chart ACSIL study (module 8 of the research brief).
// Exports closed bars and the footprint (bid / ask volume at every price of every bar) to CSV files so that
// the hypotheses about absorption, imbalance and repeated tests of a level can be tested offline on real ticks.
//
// NOT compiled or tested by the author of this file (no Sierra Chart in the build environment): the first build in
// Sierra Chart may need a small fix. See README_ResearchExport.md.
#include "sierrachart.h"

SCDLLName("Research Export")

SCSFExport scsf_ResearchExport(SCStudyInterfaceRef sc)
{
    SCInputRef Input_ExportFootprint = sc.Input[0];
    SCInputRef Input_FilePrefix      = sc.Input[1];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Research Export (bars + footprint CSV)";
        sc.StudyDescription = "Writes closed bars and volume at price (bid/ask) to CSV files in the Sierra Chart Data folder.";
        sc.AutoLoop = 0;                       // loop over the bars ourselves
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.MaintainVolumeAtPriceData = 1;      // keep bid/ask volume at every price for every bar

        Input_ExportFootprint.Name = "Export footprint (volume at price)";
        Input_ExportFootprint.SetYesNo(1);

        Input_FilePrefix.Name = "File name prefix";
        Input_FilePrefix.SetString("ResearchExport");
        return;
    }

    int& LastExported = sc.GetPersistentInt(1);   // index of the last bar that has been written

    if (sc.LastCallToFunction)
        return;

    SCString Prefix = Input_FilePrefix.GetString();
    SCString Folder = sc.DataFilesFolder();
    SCString BarsFile = Folder + "\\" + Prefix + "_" + sc.Symbol + "_bars.csv";
    SCString VapFile  = Folder + "\\" + Prefix + "_" + sc.Symbol + "_footprint.csv";

    bool Truncate = false;
    if (sc.IsFullRecalculation && sc.UpdateStartIndex == 0)
    {
        LastExported = -1;
        Truncate = true;
    }

    // the last bar is still forming, export only closed bars
    const int LastClosed = sc.ArraySize - 2;
    if (LastClosed <= LastExported)
        return;

    FILE* fb = fopen(BarsFile.GetChars(), Truncate ? "w" : "a");
    FILE* fv = Input_ExportFootprint.GetYesNo() ? fopen(VapFile.GetChars(), Truncate ? "w" : "a") : NULL;
    if (fb == NULL)
        return;

    if (Truncate)
    {
        fprintf(fb, "DateTime,Open,High,Low,Close,Volume,BidVolume,AskVolume,Trades\n");
        if (fv != NULL)
            fprintf(fv, "DateTime,Price,BidVolume,AskVolume\n");
    }

    for (int i = LastExported + 1; i <= LastClosed; ++i)
    {
        // set the chart time zone in Sierra Chart to America/New_York so that the times are in ET
        int Y, M, D, h, m, s;
        sc.BaseDateTimeIn[i].GetDateTimeYMDHMS(Y, M, D, h, m, s);
        char Stamp[32];
        sprintf(Stamp, "%04d-%02d-%02d %02d:%02d:%02d", Y, M, D, h, m, s);

        fprintf(fb, "%s,%.2f,%.2f,%.2f,%.2f,%.0f,%.0f,%.0f,%.0f\n", Stamp,
                sc.BaseData[SC_OPEN][i], sc.BaseData[SC_HIGH][i], sc.BaseData[SC_LOW][i], sc.BaseData[SC_LAST][i],
                sc.BaseData[SC_VOLUME][i], sc.BaseData[SC_BIDVOL][i], sc.BaseData[SC_ASKVOL][i],
                sc.BaseData[SC_NUM_TRADES][i]);

        if (fv != NULL && sc.VolumeAtPriceForBars != NULL)
        {
            const int Count = sc.VolumeAtPriceForBars->GetSizeAtBarIndex(i);
            for (int k = 0; k < Count; ++k)
            {
                const s_VolumeAtPriceV2* p = NULL;
                sc.VolumeAtPriceForBars->GetVAPElementAtIndex(i, k, &p);
                if (p == NULL)
                    continue;
                fprintf(fv, "%s,%.2f,%u,%u\n", Stamp, p->PriceInTicks * sc.TickSize, p->BidVolume, p->AskVolume);
            }
        }
    }
    LastExported = LastClosed;

    fclose(fb);
    if (fv != NULL)
        fclose(fv);
}
