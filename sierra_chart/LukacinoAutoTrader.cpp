// ============================================================================
//  LukacinoAutoTrader.cpp
//  Primitivni semi / full-auto trading study pro Sierra Chart (ACSIL)
//
//  Vlastnosti:
//    - Trading enabled yes/no, kill switch (manualni + denni loss limit)
//    - Mode: Long only / Short only / Both
//    - Semi-auto (1 obchod na signal) / Full-auto (po uzavreni otevira znovu)
//    - TP: fixni ticky/body  nebo  SL x RRR
//    - SL: fixni ticky/body  nebo  ATR x multiplier
//    - Trailing stop: trigger + odstup + minimalni krok
//      rezim Group (jedna hladina pro celou skupinu) / Per position (kazdy sam)
//    - Max soucasne otevrenych obchodu + max vstupu za den, position size
//    - Vykresleni Entry / TP / SL / Trailing urovni vcetne labelu + status text
//
//  Kompilace: soubor dej do adresare Sierra Chart "Data",
//             pak Analysis >> Build Custom Studies >> vyber tento soubor.
//  Nasazeni:  Chart >> Studies >> Add "Lukacino Auto Trader"
//
//  POZOR: nez poustis naostro, nech chart v Trade Simulation Mode
//         (Trade >> Trade Simulation Mode On) a zkontroluj chovani.
//         Pro realne odesilani prikazu musi byt zaroven zapnuto
//         Trade >> Auto Trading Enabled (globalne i na chartu).
// ============================================================================

#include "sierrachart.h"

SCDLLName("Lukacino Auto Trader")

// ACS Control Bar buttony (Buy / Sell / Flatten). Kdyby si na tom tvoje verze
// Sierra Chart pri kompilaci stezovala, preped na 0 a pouzivej input
// "Manual trigger".
#define LCN_USE_ACS_BUTTONS 1

#define LCN_BUTTON_BUY   1
#define LCN_BUTTON_SELL  2
#define LCN_BUTTON_FLAT  3

namespace
{
  const int MAX_SLOTS   = 20;      // tvrdy strop poctu soucasnych obchodu
  const int LINE_BASE   = 71000;   // bazove cislo pro kreslene urovne
  const int LINE_STATUS = 70999;   // cislo pro statusovy text

  enum { DIR_NONE = 0, DIR_LONG = 1, DIR_SHORT = -1 };

  // ---- jeden obchod ("slot") ---------------------------------------------
  struct TradeSlot
  {
    int   Active;          // slot je obsazeny
    int   Direction;       // DIR_LONG / DIR_SHORT
    int   Quantity;
    int   EntryOrderID;
    int   TargetOrderID;
    int   StopOrderID;
    int   EntryFilled;     // vstup fillnuty -> EntryPrice je platna
    int   EntryBarIndex;
    int   GraceTicks;      // po fillu: pocka nez se brackety objevi v order listu
    float EntryPrice;
    float TargetPrice;
    float StopPrice;       // aktualni stop (i po trailingu)
    float InitialStop;     // puvodni stop -> 1R
    float BestPrice;       // nejlepsi dosazena cena
  };

  // ---- stav celeho systemu (persistent memory) ---------------------------
  struct SystemState
  {
    TradeSlot Slots[MAX_SLOTS];
    int    KillLatched;          // kill switch zaskocil (denni loss limit)
    int    PrevKillInput;        // detekce prepnuti inputu Yes -> No
    int    TradesToday;          // pocet vstupu dnesniho dne
    int    TradingDayDate;
    float  RealizedToday;        // realizovane P/L dne (currency)
    float  GroupTrailLevel;      // spolecna trailing hladina
    int    GroupTrailDir;
    int    PendingReentryDir;    // full-auto: smer k znovuotevreni
    int    LastSignalBarIndex;   // edge detekce externiho signalu
    int    PrevOpenInitialNow;   // edge detekce inputu 29 (No -> Yes)
    int    OpenInitialBlockedLogged; // aby se blokace nelogovala na kazdy tick
    int    ForeignPositionLogged;    // varovani o nesledovane pozici jen jednou
    int    PrevManualTriggerIndex; // edge detekce inputu 06
    int    Initialized;          // prvni volani: nacti stav inputu bez odpalu
    double LastExitTimeDays;     // SCDateTime jako double (dny)
  };

  // 0 = Ticks, 1 = Points
  inline float LcnToPrice(float Value, int UnitsIndex, float TickSize)
  {
    return (UnitsIndex == 0) ? Value * TickSize : Value;
  }

  inline bool LcnIsTerminal(int OrderStatusCode)
  {
    return OrderStatusCode == SCT_OSC_FILLED
        || OrderStatusCode == SCT_OSC_CANCELED
        || OrderStatusCode == SCT_OSC_ERROR;
  }

  void LcnClearSlotDrawings(SCStudyInterfaceRef sc, int SlotIndex)
  {
    for (int k = 0; k < 3; k++)
      sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING,
                               LINE_BASE + SlotIndex * 10 + k);
  }

  void LcnResetSlot(SCStudyInterfaceRef sc, TradeSlot& Slot, int SlotIndex)
  {
    memset(&Slot, 0, sizeof(TradeSlot));
    LcnClearSlotDrawings(sc, SlotIndex);
  }

  // Dohledani attached (OCO) orderu podle parent ID. Target vs Stop
  // rozlisujeme podle ceny vuci entry - nezavisle na enum nazvech typu.
  void LcnResolveAttachedOrders(SCStudyInterfaceRef sc, TradeSlot& Slot)
  {
    if (Slot.EntryOrderID == 0 || Slot.EntryFilled == 0)
      return;
    if (Slot.TargetOrderID != 0 && Slot.StopOrderID != 0)
      return;

    s_SCTradeOrder Order;
    int Index = 0;
    while (sc.GetOrderByIndex(Index, Order) != SCTRADING_ORDER_ERROR)
    {
      if (Order.ParentInternalOrderID == Slot.EntryOrderID)
      {
        const float OrderPrice = (float)Order.Price1;
        const bool IsAbove  = (OrderPrice > Slot.EntryPrice);
        const bool IsTarget = (Slot.Direction == DIR_LONG) ? IsAbove : !IsAbove;

        if (IsTarget)
        {
          Slot.TargetOrderID = Order.InternalOrderID;
          Slot.TargetPrice   = OrderPrice;
        }
        else
        {
          Slot.StopOrderID = Order.InternalOrderID;
          Slot.StopPrice   = OrderPrice;
          if (Slot.InitialStop == 0.0f)
            Slot.InitialStop = OrderPrice;
        }
      }
      Index++;
    }
  }

  void LcnDrawLevel(SCStudyInterfaceRef sc, int LineNumber, int BeginIndex,
                    float LevelPrice, COLORREF LineColor, int Width,
                    int LineStyleValue, const SCString& Label)
  {
    if (LevelPrice <= 0.0f)
      return;

    s_UseTool Tool;
    Tool.Clear();
    Tool.ChartNumber = sc.ChartNumber;
    Tool.DrawingType = DRAWING_LINE;
    Tool.LineNumber  = LineNumber;
    Tool.BeginIndex  = BeginIndex;
    Tool.EndIndex    = sc.ArraySize - 1;
    Tool.BeginValue  = LevelPrice;
    Tool.EndValue    = LevelPrice;
    Tool.Color       = LineColor;
    Tool.LineWidth   = Width;
    Tool.LineStyle   = (SubgraphLineStyles)LineStyleValue;
    Tool.Text        = Label;
    Tool.TextColor   = LineColor;
    Tool.FontSize    = 8;
    Tool.AddMethod   = UTAM_ADD_OR_ADJUST;
    Tool.AddAsUserDrawnDrawing = 0;
    sc.UseTool(Tool);
  }
}

// ============================================================================
SCSFExport scsf_LukacinoAutoTrader(SCStudyInterfaceRef sc)
{
  // ---- inputy ------------------------------------------------------------
  SCInputRef Input_TradingEnabled  = sc.Input[0];
  SCInputRef Input_Mode            = sc.Input[1];
  SCInputRef Input_AutoMode        = sc.Input[2];
  SCInputRef Input_Units           = sc.Input[3];

  SCInputRef Input_EntrySource     = sc.Input[4];
  SCInputRef Input_ManualTrigger   = sc.Input[5];
  SCInputRef Input_SignalStudy     = sc.Input[6];

  SCInputRef Input_SLMode          = sc.Input[7];
  SCInputRef Input_SLValue         = sc.Input[8];
  SCInputRef Input_ATRPeriod       = sc.Input[9];
  SCInputRef Input_ATRMultiplier   = sc.Input[10];

  SCInputRef Input_TPMode          = sc.Input[11];
  SCInputRef Input_TPValue         = sc.Input[12];
  SCInputRef Input_RRR             = sc.Input[13];

  SCInputRef Input_PositionSize    = sc.Input[14];
  SCInputRef Input_MaxConcurrent   = sc.Input[15];
  SCInputRef Input_MaxTradesPerDay = sc.Input[16];

  SCInputRef Input_TrailEnabled    = sc.Input[17];
  SCInputRef Input_TrailMode       = sc.Input[18];
  SCInputRef Input_TrailTrigger    = sc.Input[19];
  SCInputRef Input_TrailDistance   = sc.Input[20];
  SCInputRef Input_TrailStep       = sc.Input[21];

  SCInputRef Input_KillSwitch      = sc.Input[22];
  SCInputRef Input_DailyLossLimit  = sc.Input[23];

  SCInputRef Input_ReentryDelaySec = sc.Input[24];
  SCInputRef Input_SendToService   = sc.Input[25];
  SCInputRef Input_ShowLevels      = sc.Input[26];
  SCInputRef Input_DoLog           = sc.Input[27];
  SCInputRef Input_OpenInitialNow  = sc.Input[28];
  SCInputRef Input_ShowStatusText  = sc.Input[29];
  SCInputRef Input_StatusTextColor = sc.Input[30];
  SCInputRef Input_StatusFontSize  = sc.Input[31];

  SCSubgraphRef Subgraph_ATR       = sc.Subgraph[0];

  if (sc.SetDefaults)
  {
    sc.GraphName = "Lukacino Auto Trader";
    sc.GraphRegion = 0;
    sc.AutoLoop = 0;            // rucni smycka, obchodujeme na poslednim baru
    sc.UpdateAlways = 1;        // tick-by-tick
    sc.CalculationPrecedence = LOW_PREC_LEVEL;

    // --- trading nastaveni study
    sc.SupportAttachedOrdersForTrading = 1;
    sc.AllowMultipleEntriesInSameDirection = 1;
    sc.AllowOnlyOneTradePerBar = 0;
    sc.MaintainTradeStatisticsAndTradesData = 1;
    sc.CancelAllOrdersOnEntriesAndReversals = 0;
    sc.AllowEntryWithWorkingOrders = 1;
    sc.SupportReversals = 0;
    sc.AllowOppositeEntryWithOpposingPositionOrOrders = 0;
    sc.MaximumPositionAllowed = 100;

    Subgraph_ATR.Name = "ATR (internal)";
    Subgraph_ATR.DrawStyle = DRAWSTYLE_IGNORE;

    Input_TradingEnabled.Name = "01. Trading enabled";
    Input_TradingEnabled.SetYesNo(0);

    Input_Mode.Name = "02. Mode";
    Input_Mode.SetCustomInputStrings("Long only;Short only;Both");
    Input_Mode.SetCustomInputIndex(2);

    Input_AutoMode.Name = "03. Auto mode";
    Input_AutoMode.SetCustomInputStrings("Semi auto;Full auto");
    Input_AutoMode.SetCustomInputIndex(0);

    Input_Units.Name = "04. Units for TP / SL / Trail";
    Input_Units.SetCustomInputStrings("Ticks;Points");
    Input_Units.SetCustomInputIndex(0);

    Input_EntrySource.Name = "05. Entry source";
    Input_EntrySource.SetCustomInputStrings("Manual only;Study signal only;Manual + study signal");
    Input_EntrySource.SetCustomInputIndex(0);

    Input_ManualTrigger.Name = "06. Manual trigger (edge Off -> Buy/Sell)";
    Input_ManualTrigger.SetCustomInputStrings("Off;Buy;Sell");
    Input_ManualTrigger.SetCustomInputIndex(0);

    Input_SignalStudy.Name = "07. Signal study subgraph (>0 long, <0 short)";
    Input_SignalStudy.SetStudySubgraphValues(0, 0);

    Input_SLMode.Name = "08. SL mode";
    Input_SLMode.SetCustomInputStrings("Fixed;ATR");
    Input_SLMode.SetCustomInputIndex(0);

    Input_SLValue.Name = "09. SL fixed (ticks / points)";
    Input_SLValue.SetFloat(20.0f);

    Input_ATRPeriod.Name = "10. ATR period";
    Input_ATRPeriod.SetInt(14);

    Input_ATRMultiplier.Name = "11. ATR multiplier (for SL)";
    Input_ATRMultiplier.SetFloat(1.5f);

    Input_TPMode.Name = "12. TP mode";
    Input_TPMode.SetCustomInputStrings("Fixed;RRR x SL");
    Input_TPMode.SetCustomInputIndex(1);

    Input_TPValue.Name = "13. TP fixed (ticks / points)";
    Input_TPValue.SetFloat(40.0f);

    Input_RRR.Name = "14. RRR";
    Input_RRR.SetFloat(2.0f);

    Input_PositionSize.Name = "15. Position size (per trade)";
    Input_PositionSize.SetInt(1);

    Input_MaxConcurrent.Name = "16. Max concurrent trades";
    Input_MaxConcurrent.SetInt(1);
    Input_MaxConcurrent.SetIntLimits(1, MAX_SLOTS);

    Input_MaxTradesPerDay.Name = "17. Max trades per day (0 = unlimited)";
    Input_MaxTradesPerDay.SetInt(10);

    Input_TrailEnabled.Name = "18. Trailing stop enabled";
    Input_TrailEnabled.SetYesNo(1);

    Input_TrailMode.Name = "19. Trailing mode";
    Input_TrailMode.SetCustomInputStrings("Group;Per position");
    Input_TrailMode.SetCustomInputIndex(1);

    Input_TrailTrigger.Name = "20. Trail trigger (profit, ticks / points)";
    Input_TrailTrigger.SetFloat(12.0f);

    Input_TrailDistance.Name = "21. Trail distance (ticks / points)";
    Input_TrailDistance.SetFloat(8.0f);

    Input_TrailStep.Name = "22. Trail min step (ticks / points)";
    Input_TrailStep.SetFloat(2.0f);

    Input_KillSwitch.Name = "23. KILL SWITCH (flatten + block entries)";
    Input_KillSwitch.SetYesNo(0);

    Input_DailyLossLimit.Name = "24. Daily loss limit (currency, 0 = off)";
    Input_DailyLossLimit.SetFloat(0.0f);

    Input_ReentryDelaySec.Name = "25. Full auto re-entry delay (seconds)";
    Input_ReentryDelaySec.SetInt(5);

    Input_SendToService.Name = "26. Send orders to trade service";
    Input_SendToService.SetYesNo(1);

    Input_ShowLevels.Name = "27. Draw entry / TP / SL / trail levels";
    Input_ShowLevels.SetYesNo(1);

    Input_DoLog.Name = "28. Log events to Message Log";
    Input_DoLog.SetYesNo(1);

    Input_OpenInitialNow.Name = "29. Open initial position now";
    Input_OpenInitialNow.SetYesNo(0);

    Input_ShowStatusText.Name = "30. Show status text";
    Input_ShowStatusText.SetYesNo(1);

    Input_StatusTextColor.Name = "31. Status text color";
    Input_StatusTextColor.SetColor(240, 240, 240);

    Input_StatusFontSize.Name = "32. Status text font size";
    Input_StatusFontSize.SetInt(10);
    Input_StatusFontSize.SetIntLimits(5, 40);

#if LCN_USE_ACS_BUTTONS
    sc.SetCustomStudyControlBarButtonText(LCN_BUTTON_BUY,  "LCN Buy");
    sc.SetCustomStudyControlBarButtonText(LCN_BUTTON_SELL, "LCN Sell");
    sc.SetCustomStudyControlBarButtonText(LCN_BUTTON_FLAT, "LCN Flat");
#endif

    return;
  }

  // ---- persistent stav ---------------------------------------------------
  SystemState* pState = (SystemState*)sc.GetPersistentPointer(0);

  if (sc.LastCallToFunction)
  {
    if (pState != NULL)
    {
      delete pState;
      sc.SetPersistentPointer(0, NULL);
    }
    return;
  }

  if (pState == NULL)
  {
    pState = new SystemState();
    memset(pState, 0, sizeof(SystemState));
    sc.SetPersistentPointer(0, pState);
  }
  SystemState& St = *pState;

  if (sc.ArraySize < 2)
    return;

  const int   LastIndex = sc.ArraySize - 1;
  const float TickSize  = (float)sc.TickSize;

  // ---- ATR (pocita se i pri full recalculation) --------------------------
  int ATRPeriod = Input_ATRPeriod.GetInt();
  if (ATRPeriod < 1)
    ATRPeriod = 1;

  for (int i = sc.UpdateStartIndex; i <= LastIndex; i++)
    sc.ATR(sc.BaseDataIn, Subgraph_ATR, i, ATRPeriod, MOVAVGTYPE_WILDERS);

  // behem prepocitavani historie se neobchoduje
  if (sc.IsFullRecalculation)
    return;

  sc.SendOrdersToTradeService = (Input_SendToService.GetYesNo() != 0);

  // ---- precteni inputu ---------------------------------------------------
  const int  Units       = Input_Units.GetIndex();
  const int  ModeIndex   = Input_Mode.GetIndex();          // 0 L, 1 S, 2 both
  const bool FullAuto    = (Input_AutoMode.GetIndex() == 1);
  const int  EntrySource = Input_EntrySource.GetIndex();
  const bool UseManual   = (EntrySource == 0 || EntrySource == 2);
  const bool UseStudy    = (EntrySource == 1 || EntrySource == 2);

  int Qty = Input_PositionSize.GetInt();
  if (Qty < 1)
    Qty = 1;

  int MaxConcurrent = Input_MaxConcurrent.GetInt();
  if (MaxConcurrent < 1)          MaxConcurrent = 1;
  if (MaxConcurrent > MAX_SLOTS)  MaxConcurrent = MAX_SLOTS;

  int MaxPerDay = Input_MaxTradesPerDay.GetInt();
  if (MaxPerDay < 0)
    MaxPerDay = 0;

  const bool  TrailEnabled   = (Input_TrailEnabled.GetYesNo() != 0);
  const bool  TrailPerPos    = (Input_TrailMode.GetIndex() == 1);
  const float TrailTrigger   = LcnToPrice(Input_TrailTrigger.GetFloat(), Units, TickSize);
  const float TrailDistance  = LcnToPrice(Input_TrailDistance.GetFloat(), Units, TickSize);
  const float TrailStep      = LcnToPrice(Input_TrailStep.GetFloat(), Units, TickSize);
  const float DailyLossLimit = Input_DailyLossLimit.GetFloat();
  const bool  ShowLevels     = (Input_ShowLevels.GetYesNo() != 0);
  const bool  ShowStatusText = (Input_ShowStatusText.GetYesNo() != 0);
  const bool  DoLog          = (Input_DoLog.GetYesNo() != 0);

  int ReentryDelay = Input_ReentryDelaySec.GetInt();
  if (ReentryDelay < 0)
    ReentryDelay = 0;

  sc.MaximumPositionAllowed = MaxConcurrent * Qty;

  const float Price = (sc.LastTradePrice > 0.0)
                    ? (float)sc.LastTradePrice
                    : sc.Close[LastIndex];
  const float ValuePerTick = (float)sc.CurrencyValuePerTick;

  // ---- novy obchodni den -------------------------------------------------
  const int TradingDay = sc.GetTradingDayDate(sc.BaseDateTimeIn[LastIndex]);
  if (St.TradingDayDate != TradingDay)
  {
    St.TradingDayDate    = TradingDay;
    St.TradesToday       = 0;
    St.RealizedToday     = 0.0f;
    St.KillLatched       = 0;
    St.PendingReentryDir = DIR_NONE;
    St.GroupTrailLevel   = 0.0f;
    St.GroupTrailDir     = DIR_NONE;
  }

  s_SCPositionData PositionData;
  sc.GetTradePosition(PositionData);
  const double NetQuantity = PositionData.PositionQuantity;

  // ==========================================================================
  //  1) SYNC SLOTU - fill vstupu, detekce uzavreni obchodu
  // ==========================================================================
  int OpenSlots = 0;

  for (int s = 0; s < MAX_SLOTS; s++)
  {
    TradeSlot& Slot = St.Slots[s];
    if (Slot.Active == 0)
      continue;

    s_SCTradeOrder Order;

    // --- entry order jeste neni fillnuty
    if (Slot.EntryFilled == 0)
    {
      if (sc.GetOrderByOrderID(Slot.EntryOrderID, Order) == SCTRADING_ORDER_ERROR)
      {
        LcnResetSlot(sc, Slot, s);           // order zmizel -> slot volny
        continue;
      }

      if (Order.OrderStatusCode == SCT_OSC_FILLED)
      {
        Slot.EntryFilled   = 1;
        Slot.EntryPrice    = (float)Order.AvgFillPrice;
        Slot.BestPrice     = Slot.EntryPrice;
        Slot.EntryBarIndex = LastIndex;
        Slot.GraceTicks    = 10;

        if (DoLog)
        {
          SCString Message;
          Message.Format("LCN slot %d: ENTRY %s qty %d @ %.5f",
                         s, Slot.Direction == DIR_LONG ? "LONG" : "SHORT",
                         Slot.Quantity, Slot.EntryPrice);
          sc.AddMessageToLog(Message, 0);
        }
      }
      else if (LcnIsTerminal(Order.OrderStatusCode))
      {
        LcnResetSlot(sc, Slot, s);           // cancel / error pred fillem
        continue;
      }
      else
      {
        OpenSlots++;                         // pending vstup drzi slot
        continue;
      }
    }

    if (Slot.GraceTicks > 0)
      --Slot.GraceTicks;

    LcnResolveAttachedOrders(sc, Slot);

    // attached ordery jeste nejsou zname
    if (Slot.StopOrderID == 0 || Slot.TargetOrderID == 0)
    {
      // bezpecnostni ventil: pozice je flat a brackety se nenasly ani po grace
      if (NetQuantity == 0.0 && Slot.GraceTicks == 0
          && Slot.StopOrderID == 0 && Slot.TargetOrderID == 0)
      {
        LcnResetSlot(sc, Slot, s);
        continue;
      }
      OpenSlots++;
      continue;
    }

    // --- exit ordery (TP / SL)
    bool  StopLive = false, TargetLive = false;
    float ExitPrice = 0.0f;
    const char* ExitReason = "CLOSE";

    if (sc.GetOrderByOrderID(Slot.StopOrderID, Order) != SCTRADING_ORDER_ERROR)
    {
      Slot.StopPrice = (float)Order.Price1;
      if (Order.OrderStatusCode == SCT_OSC_FILLED)
      {
        ExitPrice  = (float)Order.AvgFillPrice;
        ExitReason = "STOP";
      }
      else if (!LcnIsTerminal(Order.OrderStatusCode))
        StopLive = true;
    }

    if (sc.GetOrderByOrderID(Slot.TargetOrderID, Order) != SCTRADING_ORDER_ERROR)
    {
      Slot.TargetPrice = (float)Order.Price1;
      if (Order.OrderStatusCode == SCT_OSC_FILLED)
      {
        ExitPrice  = (float)Order.AvgFillPrice;
        ExitReason = "TARGET";
      }
      else if (!LcnIsTerminal(Order.OrderStatusCode))
        TargetLive = true;
    }

    if (!StopLive && !TargetLive)
    {
      // obchod je uzavreny
      if (ExitPrice <= 0.0f)
        ExitPrice = Price;                   // rucni flatten apod.

      const float PnL = Slot.Direction * (ExitPrice - Slot.EntryPrice)
                      / TickSize * ValuePerTick * Slot.Quantity;
      St.RealizedToday += PnL;

      if (DoLog)
      {
        SCString Message;
        Message.Format("LCN slot %d: EXIT %s @ %.5f | P/L %.2f | realized today %.2f",
                       s, ExitReason, ExitPrice, PnL, St.RealizedToday);
        sc.AddMessageToLog(Message, 0);
      }

      const int ClosedDir = Slot.Direction;
      LcnResetSlot(sc, Slot, s);

      if (FullAuto)
      {
        St.PendingReentryDir = ClosedDir;
        // cas chartu, ne systemovy - jinak pri Replay 240X odpovida
        // 5 sekund prodlevy zhruba 20 minutam trhu
        St.LastExitTimeDays  = sc.BaseDateTimeIn[LastIndex].GetAsDouble();
      }
      continue;
    }

    OpenSlots++;
  }

  // ==========================================================================
  //  1b) CIZI POZICE
  // ==========================================================================
  // Pozice, kterou tato study neotevrela (zbytek z jine study, rucni vstup
  // z Trade DOM, pozustatek po Replay). Study ji neadoptuje - a protoze
  // sc.MaximumPositionAllowed = Max concurrent x Position size, Sierra pak
  // odmitne KAZDY dalsi vstup. Bez tohohle hlaseni to vypada, ze script nedela
  // vubec nic.
  {
    double TrackedQty = 0.0;
    for (int s = 0; s < MAX_SLOTS; s++)
      if (St.Slots[s].Active != 0 && St.Slots[s].EntryFilled != 0)
        TrackedQty += St.Slots[s].Direction * St.Slots[s].Quantity;

    const double NetAbs     = (NetQuantity < 0.0) ? -NetQuantity : NetQuantity;
    const double TrackedAbs = (TrackedQty  < 0.0) ? -TrackedQty  : TrackedQty;

    if (NetAbs > TrackedAbs + 0.0001)
    {
      if (St.ForeignPositionLogged == 0)
      {
        if (DoLog)
        {
          SCString Message;
          Message.Format("LCN POZOR: v Trade DOM je pozice %.0f kontraktu, ale tato "
                         "study sleduje jen %.0f. Cizi pozici neadoptuje a vsechny "
                         "vstupy budou odmitany, protoze Maximum Position Allowed = "
                         "%d. Udelej Flatten v Trade DOM (pripadne Trade >> Reset "
                         "Trade Simulation) a zkus to znovu.",
                         NetAbs, TrackedAbs, sc.MaximumPositionAllowed);
          sc.AddMessageToLog(Message, 1);
        }
        St.ForeignPositionLogged = 1;
      }
    }
    else
    {
      St.ForeignPositionLogged = 0;
    }
  }

  // ==========================================================================
  //  2) KILL SWITCH
  // ==========================================================================
  float OpenPnL = 0.0f;
  for (int s = 0; s < MAX_SLOTS; s++)
  {
    const TradeSlot& Slot = St.Slots[s];
    if (Slot.Active != 0 && Slot.EntryFilled != 0)
      OpenPnL += Slot.Direction * (Price - Slot.EntryPrice)
               / TickSize * ValuePerTick * Slot.Quantity;
  }

  const float TotalPnLToday = St.RealizedToday + OpenPnL;

  if (DailyLossLimit > 0.0f && TotalPnLToday <= -DailyLossLimit && St.KillLatched == 0)
  {
    St.KillLatched = 1;
    if (DoLog)
    {
      SCString Message;
      Message.Format("LCN KILL SWITCH: denni loss limit %.2f dosazen (P/L %.2f)",
                     DailyLossLimit, TotalPnLToday);
      sc.AddMessageToLog(Message, 1);
    }
  }

  const int KillInput = Input_KillSwitch.GetYesNo();

  // prepnuti inputu Yes -> No resetuje zaskoceny latch
  if (St.PrevKillInput == 1 && KillInput == 0)
    St.KillLatched = 0;
  St.PrevKillInput = KillInput;

  const bool KillActive = (KillInput != 0) || (St.KillLatched != 0);

  if (KillActive)
  {
    if (NetQuantity != 0.0 || OpenSlots > 0)
    {
      sc.FlattenAndCancelAllOrders();
      if (DoLog)
        sc.AddMessageToLog("LCN KILL SWITCH aktivni: flatten + cancel all orders", 1);
    }

    for (int s = 0; s < MAX_SLOTS; s++)
      if (St.Slots[s].Active != 0)
        LcnResetSlot(sc, St.Slots[s], s);

    St.PendingReentryDir = DIR_NONE;
    OpenSlots = 0;
  }

#if LCN_USE_ACS_BUTTONS
  if (!KillActive && sc.MenuEventID == LCN_BUTTON_FLAT)
  {
    sc.FlattenAndCancelAllOrders();
    for (int s = 0; s < MAX_SLOTS; s++)
      if (St.Slots[s].Active != 0)
        LcnResetSlot(sc, St.Slots[s], s);
    St.PendingReentryDir = DIR_NONE;
    OpenSlots = 0;
    if (DoLog)
      sc.AddMessageToLog("LCN: manualni FLATTEN", 0);
  }
#endif

  // ==========================================================================
  //  3) TRAILING STOP
  // ==========================================================================
  if (TrailEnabled && !KillActive)
  {
    if (TrailPerPos)
    {
      // --- kazdy obchod trailuje sam od sveho entry
      for (int s = 0; s < MAX_SLOTS; s++)
      {
        TradeSlot& Slot = St.Slots[s];
        if (Slot.Active == 0 || Slot.EntryFilled == 0 || Slot.StopOrderID == 0)
          continue;

        if (Slot.Direction == DIR_LONG && Price > Slot.BestPrice)
          Slot.BestPrice = Price;
        if (Slot.Direction == DIR_SHORT && (Price < Slot.BestPrice || Slot.BestPrice == 0.0f))
          Slot.BestPrice = Price;

        if (Slot.Direction * (Price - Slot.EntryPrice) < TrailTrigger)
          continue;

        float Desired = Price - Slot.Direction * TrailDistance;
        Desired = (float)sc.RoundToTickSize(Desired, sc.TickSize);

        const bool Improves = (Slot.Direction == DIR_LONG)
                            ? (Desired >= Slot.StopPrice + TrailStep)
                            : (Desired <= Slot.StopPrice - TrailStep);
        if (!Improves)
          continue;

        s_SCNewOrder ModifyOrder;
        ModifyOrder.InternalOrderID = Slot.StopOrderID;
        ModifyOrder.Price1 = Desired;
        if (sc.ModifyOrder(ModifyOrder) > 0)
        {
          Slot.StopPrice = Desired;
          if (DoLog)
          {
            SCString Message;
            Message.Format("LCN slot %d: trail stop -> %.5f", s, Desired);
            sc.AddMessageToLog(Message, 0);
          }
        }
      }
    }
    else
    {
      // --- GROUP: jedna hladina pro celou netto pozici
      const int NetDir = (NetQuantity > 0.0) ? DIR_LONG
                       : ((NetQuantity < 0.0) ? DIR_SHORT : DIR_NONE);

      if (NetDir == DIR_NONE)
      {
        St.GroupTrailLevel = 0.0f;
        St.GroupTrailDir   = DIR_NONE;
      }
      else
      {
        if (St.GroupTrailDir != NetDir)
        {
          St.GroupTrailDir   = NetDir;
          St.GroupTrailLevel = 0.0f;
        }

        const float AvgPrice = (float)PositionData.AveragePrice;

        if (NetDir * (Price - AvgPrice) >= TrailTrigger)
        {
          float Desired = Price - NetDir * TrailDistance;
          Desired = (float)sc.RoundToTickSize(Desired, sc.TickSize);

          const bool First = (St.GroupTrailLevel == 0.0f);
          const bool Improves = First
                              || ((NetDir == DIR_LONG)
                                  ? (Desired >= St.GroupTrailLevel + TrailStep)
                                  : (Desired <= St.GroupTrailLevel - TrailStep));

          if (Improves)
          {
            St.GroupTrailLevel = Desired;

            for (int s = 0; s < MAX_SLOTS; s++)
            {
              TradeSlot& Slot = St.Slots[s];
              if (Slot.Active == 0 || Slot.EntryFilled == 0 || Slot.StopOrderID == 0)
                continue;
              if (Slot.Direction != NetDir)
                continue;

              s_SCNewOrder ModifyOrder;
              ModifyOrder.InternalOrderID = Slot.StopOrderID;
              ModifyOrder.Price1 = Desired;
              if (sc.ModifyOrder(ModifyOrder) > 0)
                Slot.StopPrice = Desired;
            }

            if (DoLog)
            {
              SCString Message;
              Message.Format("LCN GROUP trail stop -> %.5f", Desired);
              sc.AddMessageToLog(Message, 0);
            }
          }
        }
      }
    }
  }

  // ==========================================================================
  //  4) VSTUPNI SIGNAL
  // ==========================================================================
  int Signal = DIR_NONE;

  // Prvni volani po nacteni study: jen si zapamatuj stav prepinacu, neodpaluj.
  // (Jinak by chart s inputem 29 nechanym na Yes otevrel obchod hned po loadu.)
  if (St.Initialized == 0)
  {
    St.PrevOpenInitialNow     = Input_OpenInitialNow.GetYesNo();
    St.PrevManualTriggerIndex = Input_ManualTrigger.GetIndex();
    St.Initialized            = 1;
  }

  // --- "Open initial position now" (input 29)
  // Stejny pattern jako Pyramiding Pro System: edge detekce prepnuti No -> Yes
  // proti ulozene predchozi hodnote. Input se NERESETUJE sam - prepnes ho
  // zpatky na No rucne, stejne jako u Pyramiding Pro.
  // Odpali jen kdyz neni nic otevreneho; v rezimu Both je blokovan, protoze
  // neni jednoznacne, kterym smerem (Pyramiding Pro to resi stejne).
  {
    const int OpenInitialNow = Input_OpenInitialNow.GetYesNo();

    if (OpenInitialNow == 0)
    {
      // prepinac zpatky na No -> znovu nabito
      St.PrevOpenInitialNow         = 0;
      St.OpenInitialBlockedLogged   = 0;
    }
    else if (St.PrevOpenInitialNow == 0)
    {
      if (ModeIndex == 2)
      {
        // Rezim Both: konfiguracni problem, ktery uzivatel za chvili opravi.
        // Hranu NESPOTREBOVAVAME - jakmile prepne Mode na Long/Short only,
        // vstup se odpali sam, bez nutnosti preklikavat input 29.
        if (DoLog && St.OpenInitialBlockedLogged == 0)
        {
          sc.AddMessageToLog("LCN: 'Open initial position now' je v rezimu Both "
                             "blokovan. Prepni Mode na Long only / Short only a "
                             "vstup se odpali sam (input 29 muze zustat na Yes).", 1);
          St.OpenInitialBlockedLogged = 1;
        }
      }
      else if (OpenSlots > 0)
      {
        // Tady hranu spotrebujeme zamerne: jinak by input 29 nechany na Yes
        // fungoval jako opakovac a otevrel novy obchod hned po kazdem uzavreni.
        if (DoLog)
          sc.AddMessageToLog("LCN: 'Open initial position now' ignorovan - obchod "
                             "uz je otevreny. Pro dalsi vstup prepni input 29 na "
                             "No a zpatky na Yes.", 0);
        St.PrevOpenInitialNow = 1;
      }
      else
      {
        Signal = (ModeIndex == 1) ? DIR_SHORT : DIR_LONG;
        St.PrevOpenInitialNow       = 1;
        St.OpenInitialBlockedLogged = 0;
      }
    }
  }

  // --- manualni trigger (input 06), stejna edge detekce
  {
    const int ManualIndex = Input_ManualTrigger.GetIndex();   // 0 off, 1 buy, 2 sell

    if (Signal == DIR_NONE && UseManual && ManualIndex != St.PrevManualTriggerIndex)
    {
      if (ManualIndex == 1)
        Signal = DIR_LONG;
      else if (ManualIndex == 2)
        Signal = DIR_SHORT;
    }

    St.PrevManualTriggerIndex = ManualIndex;
  }

#if LCN_USE_ACS_BUTTONS
  if (Signal == DIR_NONE && UseManual)
  {
    if (sc.MenuEventID == LCN_BUTTON_BUY)
      Signal = DIR_LONG;
    else if (sc.MenuEventID == LCN_BUTTON_SELL)
      Signal = DIR_SHORT;
  }
#endif

  if (Signal == DIR_NONE && UseStudy)
  {
    SCFloatArray SignalArray;
    sc.GetStudyArrayUsingID(Input_SignalStudy.GetStudyID(),
                            Input_SignalStudy.GetSubgraphIndex(),
                            SignalArray);

    if (SignalArray.GetArraySize() > LastIndex)
    {
      const float SignalNow  = SignalArray[LastIndex];
      const float SignalPrev = SignalArray[LastIndex - 1];

      // edge: z nuly na nenulu, max jeden vstup na bar
      if (SignalNow != 0.0f && SignalPrev == 0.0f && St.LastSignalBarIndex != LastIndex)
      {
        Signal = (SignalNow > 0.0f) ? DIR_LONG : DIR_SHORT;
        St.LastSignalBarIndex = LastIndex;
      }
    }
  }

  // full auto: znovuotevreni po uzavreni predchoziho obchodu
  if (Signal == DIR_NONE && FullAuto && St.PendingReentryDir != DIR_NONE)
  {
    const double ElapsedSeconds =
      (sc.BaseDateTimeIn[LastIndex].GetAsDouble() - St.LastExitTimeDays) * 86400.0;

    if (ElapsedSeconds >= (double)ReentryDelay)
    {
      Signal = St.PendingReentryDir;
      St.PendingReentryDir = DIR_NONE;
    }
  }

  // ---- filtry ------------------------------------------------------------
  // Kazde zahozeni signalu se loguje i s duvodem - jinak script jen tise mlci
  // a neni poznat, proc se obchod neotevrel.
  if (Signal != DIR_NONE)
  {
    const char* BlockReason = NULL;

    if (KillActive)
      BlockReason = "kill switch je aktivni";
    else if (Input_TradingEnabled.GetYesNo() == 0)
      BlockReason = "input 01 Trading enabled = No";
    else if (ModeIndex == 0 && Signal != DIR_LONG)
      BlockReason = "input 02 Mode = Long only, signal byl SHORT";
    else if (ModeIndex == 1 && Signal != DIR_SHORT)
      BlockReason = "input 02 Mode = Short only, signal byl LONG";
    else if (OpenSlots >= MaxConcurrent)
      BlockReason = "dosazen input 16 Max concurrent trades";
    else if (MaxPerDay > 0 && St.TradesToday >= MaxPerDay)
      BlockReason = "dosazen input 17 Max trades per day";

    // smer proti otevrenym obchodum nedovolime (zadne reversals)
    if (BlockReason == NULL)
    {
      for (int s = 0; s < MAX_SLOTS; s++)
      {
        if (St.Slots[s].Active != 0 && St.Slots[s].Direction != Signal)
        {
          BlockReason = "uz je otevreny obchod v opacnem smeru";
          break;
        }
      }
    }

    if (BlockReason != NULL)
    {
      Signal = DIR_NONE;
      if (DoLog)
      {
        SCString Message;
        Message.Format("LCN: vstup zablokovan - %s", BlockReason);
        sc.AddMessageToLog(Message, 1);
      }
    }
  }

  // ==========================================================================
  //  5) ZADANI OBCHODU
  // ==========================================================================
  if (Signal != DIR_NONE)
  {
    int FreeSlot = -1;
    for (int s = 0; s < MAX_SLOTS; s++)
    {
      if (St.Slots[s].Active == 0)
      {
        FreeSlot = s;
        break;
      }
    }

    if (FreeSlot >= 0)
    {
      // --- SL offset
      float StopOffset;
      if (Input_SLMode.GetIndex() == 0)
        StopOffset = LcnToPrice(Input_SLValue.GetFloat(), Units, TickSize);
      else
        StopOffset = Subgraph_ATR[LastIndex] * Input_ATRMultiplier.GetFloat();

      StopOffset = (float)sc.RoundToTickSize(StopOffset, sc.TickSize);
      if (StopOffset < TickSize)
        StopOffset = TickSize;

      // --- TP offset
      float TargetOffset;
      if (Input_TPMode.GetIndex() == 0)
        TargetOffset = LcnToPrice(Input_TPValue.GetFloat(), Units, TickSize);
      else
        TargetOffset = StopOffset * Input_RRR.GetFloat();

      TargetOffset = (float)sc.RoundToTickSize(TargetOffset, sc.TickSize);
      if (TargetOffset < TickSize)
        TargetOffset = TickSize;

      s_SCNewOrder NewOrder;
      NewOrder.OrderQuantity = Qty;
      NewOrder.OrderType     = SCT_ORDERTYPE_MARKET;
      NewOrder.TimeInForce   = SCT_TIF_DAY;
      NewOrder.Stop1Offset   = StopOffset;
      NewOrder.Target1Offset = TargetOffset;
      NewOrder.AttachedOrderStop1Type   = SCT_ORDERTYPE_STOP;
      NewOrder.AttachedOrderTarget1Type = SCT_ORDERTYPE_LIMIT;
      NewOrder.OCOGroup1Quantity = Qty;

      const int Result = (Signal == DIR_LONG) ? sc.BuyEntry(NewOrder)
                                              : sc.SellEntry(NewOrder);

      if (Result > 0)
      {
        TradeSlot& Slot = St.Slots[FreeSlot];
        memset(&Slot, 0, sizeof(TradeSlot));
        Slot.Active        = 1;
        Slot.Direction     = Signal;
        Slot.Quantity      = Qty;
        Slot.EntryOrderID  = NewOrder.InternalOrderID;
        Slot.EntryBarIndex = LastIndex;

        St.TradesToday++;
        OpenSlots++;

        if (DoLog)
        {
          SCString Message;
          Message.Format(
            "LCN slot %d: submit %s qty %d | SL %.1f ticks | TP %.1f ticks | trades today %d",
            FreeSlot, Signal == DIR_LONG ? "BUY" : "SELL", Qty,
            StopOffset / TickSize, TargetOffset / TickSize, St.TradesToday);
          sc.AddMessageToLog(Message, 0);
        }
      }
      else if (DoLog)
      {
        SCString Message;
        Message.Format("LCN: order odmitnut Sierra Chartem, kod %d. Nejcastejsi "
                       "priciny: v DOM uz visi pozice, kterou study nesleduje; "
                       "neni zapnuto Trade >> Auto Trading Enabled; nebo "
                       "Max concurrent x Position size (= %d) je prilis nizke.",
                       Result, sc.MaximumPositionAllowed);
        sc.AddMessageToLog(Message, 1);
      }
    }
  }

  // ==========================================================================
  //  6) VYKRESLENI UROVNI + STATUS
  // ==========================================================================
  if (!ShowLevels)
  {
    for (int s = 0; s < MAX_SLOTS; s++)
      LcnClearSlotDrawings(sc, s);
  }
  else
  {
    for (int s = 0; s < MAX_SLOTS; s++)
    {
      const TradeSlot& Slot = St.Slots[s];

      if (Slot.Active == 0 || Slot.EntryFilled == 0)
      {
        LcnClearSlotDrawings(sc, s);
        continue;
      }

      int BeginIndex = Slot.EntryBarIndex;
      if (BeginIndex < 0)
        BeginIndex = 0;

      SCString Label;

      Label.Format("ENTRY #%d %s", s, Slot.Direction == DIR_LONG ? "L" : "S");
      LcnDrawLevel(sc, LINE_BASE + s * 10 + 0, BeginIndex, Slot.EntryPrice,
                   RGB(170, 170, 170), 1, LINESTYLE_DOT, Label);

      Label.Format("TP #%d", s);
      LcnDrawLevel(sc, LINE_BASE + s * 10 + 1, BeginIndex, Slot.TargetPrice,
                   RGB(0, 190, 0), 2, LINESTYLE_SOLID, Label);

      const bool IsTrailing = (Slot.InitialStop != 0.0f)
                           && (Slot.StopPrice != Slot.InitialStop);

      Label.Format("%s #%d", IsTrailing ? "TRAIL" : "SL", s);
      LcnDrawLevel(sc, LINE_BASE + s * 10 + 2, BeginIndex, Slot.StopPrice,
                   IsTrailing ? RGB(255, 170, 0) : RGB(220, 0, 0), 2, LINESTYLE_SOLID,
                   Label);
    }
  }

  // --- statusovy text nad poslednim barem (input 30 / 31 / 32)
  if (!ShowStatusText)
  {
    sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LINE_STATUS);
  }
  else
  {
    SCString DayLimitText;
    if (MaxPerDay > 0)
      DayLimitText.Format("/%d", MaxPerDay);

    SCString Status;
    Status.Format(
      "LCN | %s | %s | %s | open %d/%d | today %d%s | P/L %.2f | trail: %s%s",
      Input_TradingEnabled.GetYesNo() != 0 ? "ON" : "OFF",
      FullAuto ? "FULL AUTO" : "SEMI AUTO",
      ModeIndex == 0 ? "LONG" : (ModeIndex == 1 ? "SHORT" : "BOTH"),
      OpenSlots, MaxConcurrent,
      St.TradesToday, DayLimitText.GetChars(),
      TotalPnLToday,
      TrailEnabled ? (TrailPerPos ? "PER-POSITION" : "GROUP") : "OFF",
      KillActive ? "  *** KILL SWITCH ***" : "");

    s_UseTool Tool;
    Tool.Clear();
    Tool.ChartNumber = sc.ChartNumber;
    Tool.DrawingType = DRAWING_TEXT;
    Tool.LineNumber  = LINE_STATUS;
    Tool.BeginIndex  = LastIndex;
    Tool.BeginValue  = sc.High[LastIndex] + 10.0f * TickSize;
    // pri aktivnim kill switchi vzdy cervene, jinak barva z inputu 31
    Tool.Color       = KillActive ? RGB(255, 60, 60)
                                  : Input_StatusTextColor.GetColor();
    Tool.FontSize    = Input_StatusFontSize.GetInt();
    Tool.FontBold    = 1;
    Tool.Text        = Status;
    Tool.TextAlignment = DT_RIGHT | DT_BOTTOM;
    Tool.AddMethod   = UTAM_ADD_OR_ADJUST;
    Tool.AddAsUserDrawnDrawing = 0;
    sc.UseTool(Tool);
  }
}
