// Previous-session-high breakout – jednoduchy automaticky system pro Sierra Chart (ACSIL)
//
// Logika:
//   Entry:        Long, kdyz cena prorazi high predchozi (referencni) session
//   Stop Loss:    Low predchozi (referencni) session
//   Risk/Reward:  1:1 (nastavitelne)
//   Exit:         Target / Stop / konec dne (Flatten Time)
//   Pozice:       1 kontrakt
//   Max 1 obchod za obchodni session.
//
// Referencni ("predchozi") session lze nastavit jako:
//   0 = Vlastni casove okno (od - do), napr. 18:00-9:30 nebo 9:30-16:00
//   1 = Cely predchozi obchodni den (podle Session Times grafu)
//   2 = Pevny interval v minutach, napr. 60 = predchozi hodina

#include "sierrachart.h"
#include <cfloat>

SCDLLName("Previous Session High Breakout")

// Je cas t (v sekundach od pulnoci) v okne [s, e)? Podporuje okna pres pulnoc.
static bool InWindow(int t, int s, int e)
{
	if (s < e)
		return t >= s && t < e;
	return t >= s || t < e;
}

// Klic instance okna = datum, kdy okno zacalo. -1 = bar neni v okne.
static long long WindowKey(const SCDateTime& dt, int s, int e)
{
	const int t = dt.GetTimeInSeconds();
	if (!InWindow(t, s, e))
		return -1;

	long long d = dt.GetDate();
	if (s > e && t < e)
		d -= 1;  // cast okna po pulnoci patri k predchozimu dni
	return d;
}

enum { REF_CUSTOM = 0, REF_FULL_DAY = 1, REF_INTERVAL = 2 };

// Klic instance referencni session. -1 = bar do zadne referencni session nepatri.
static long long RefKey(SCStudyInterfaceRef sc, const SCDateTime& dt, int mode, int s, int e, int minutes)
{
	switch (mode)
	{
	case REF_FULL_DAY:
		return sc.GetTradingDayDate(dt);
	case REF_INTERVAL:
	{
		const long long len = (minutes > 0 ? minutes : 60) * 60LL;
		const long long secs = (long long)dt.GetDate() * 86400LL + dt.GetTimeInSeconds();
		return secs / len;
	}
	default:
		return WindowKey(dt, s, e);
	}
}

SCSFExport scsf_PrevSessionHighBreakout(SCStudyInterfaceRef sc)
{
	SCSubgraphRef SG_PrevHigh = sc.Subgraph[0];
	SCSubgraphRef SG_PrevLow  = sc.Subgraph[1];
	SCSubgraphRef SG_Target   = sc.Subgraph[2];

	SCInputRef In_Enabled    = sc.Input[0];
	SCInputRef In_RefStart   = sc.Input[1];
	SCInputRef In_RefEnd     = sc.Input[2];
	SCInputRef In_TradeStart = sc.Input[3];
	SCInputRef In_TradeEnd   = sc.Input[4];
	SCInputRef In_Flatten    = sc.Input[5];
	SCInputRef In_RR         = sc.Input[6];
	SCInputRef In_Qty        = sc.Input[7];
	SCInputRef In_RefMode    = sc.Input[8];
	SCInputRef In_RefMinutes = sc.Input[9];

	if (sc.SetDefaults)
	{
		sc.GraphName = "Previous Session High Breakout";
		sc.StudyDescription = "Long pri prurazu high predchozi session, SL = low predchozi session, RR 1:1, exit na konci dne.";
		sc.GraphRegion = 0;
		sc.AutoLoop = 1;

		SG_PrevHigh.Name = "Previous Session High";
		SG_PrevHigh.DrawStyle = DRAWSTYLE_DASH;
		SG_PrevHigh.PrimaryColor = RGB(255, 80, 80);
		SG_PrevHigh.LineWidth = 2;
		SG_PrevHigh.DrawZeros = false;

		SG_PrevLow.Name = "Previous Session Low (Stop)";
		SG_PrevLow.DrawStyle = DRAWSTYLE_DASH;
		SG_PrevLow.PrimaryColor = RGB(200, 0, 0);
		SG_PrevLow.LineWidth = 2;
		SG_PrevLow.DrawZeros = false;

		SG_Target.Name = "Target";
		SG_Target.DrawStyle = DRAWSTYLE_DASH;
		SG_Target.PrimaryColor = RGB(0, 200, 120);
		SG_Target.LineWidth = 1;
		SG_Target.DrawZeros = false;

		In_Enabled.Name = "Trading Enabled";
		In_Enabled.SetYesNo(1);

		In_RefMode.Name = "Reference (Previous) Session Type";
		In_RefMode.SetCustomInputStrings("Custom Time Window;Full Previous Day;Fixed Interval (minutes)");
		In_RefMode.SetCustomInputIndex(REF_CUSTOM);
		In_RefMinutes.Name = "Fixed Interval Length (minutes)";
		In_RefMinutes.SetInt(60);
		In_RefMinutes.SetIntLimits(1, 1440);

		In_RefStart.Name = "Reference (Previous) Session Start";
		In_RefStart.SetTime(HMS_TIME(9, 30, 0));
		In_RefEnd.Name = "Reference (Previous) Session End";
		In_RefEnd.SetTime(HMS_TIME(16, 0, 0));

		In_TradeStart.Name = "Trading Session Start";
		In_TradeStart.SetTime(HMS_TIME(9, 30, 0));
		In_TradeEnd.Name = "Trading Session End";
		In_TradeEnd.SetTime(HMS_TIME(16, 0, 0));
		In_Flatten.Name = "Flatten Time (End of Day Exit)";
		In_Flatten.SetTime(HMS_TIME(15, 55, 0));

		In_RR.Name = "Reward : Risk";
		In_RR.SetFloat(1.0f);
		In_Qty.Name = "Position Size (contracts)";
		In_Qty.SetInt(1);

		// Nastaveni obchodovani
		sc.AllowMultipleEntriesInSameDirection = false;
		sc.MaximumPositionAllowed = 1;
		sc.SupportReversals = false;
		sc.SendOrdersToTradeService = false;  // simulace; pro live nastav true
		sc.AllowOppositeEntryWithOpposingPositionOrOrders = false;
		sc.SupportAttachedOrdersForTrading = false;
		sc.CancelAllOrdersOnEntriesAndReversals = true;
		sc.AllowEntryWithWorkingOrders = false;
		sc.CancelAllWorkingOrdersOnExit = true;
		sc.AllowOnlyOneTradePerBar = true;
		sc.MaintainTradeStatisticsAndTradesData = true;
		return;
	}

	sc.MaximumPositionAllowed = In_Qty.GetInt();

	float& RefHigh      = sc.GetPersistentFloat(1);  // high posledni dokoncene referencni session
	float& RefHighBuild = sc.GetPersistentFloat(2);  // high rozpracovane referencni session
	float& RefLow       = sc.GetPersistentFloat(3);  // low posledni dokoncene referencni session
	float& RefLowBuild  = sc.GetPersistentFloat(4);  // low rozpracovane referencni session
	float& TargetPrice  = sc.GetPersistentFloat(5);
	int& RefHighValid   = sc.GetPersistentInt(1);
	int& TradedSession  = sc.GetPersistentInt(2);
	int& BeenBelow      = sc.GetPersistentInt(3);  // cena byla v session pod PSH -> skutecny pruraz
	int& LastIndex      = sc.GetPersistentInt(4);

	const int i = sc.Index;
	const int refS = In_RefStart.GetTime(), refE = In_RefEnd.GetTime();
	const int trS  = In_TradeStart.GetTime(), trE = In_TradeEnd.GetTime();
	const int refMode = In_RefMode.GetIndex();
	const int refMin  = In_RefMinutes.GetInt();

	if (i == 0)
	{
		RefHigh = 0; RefHighBuild = -FLT_MAX;
		RefLow = 0; RefLowBuild = FLT_MAX;
		TargetPrice = 0;
		RefHighValid = 0; TradedSession = 0; BeenBelow = 0;
		LastIndex = -1;
	}

	// --- Zpracovani uzavreneho baru a prechodu mezi sessions (jednou za bar) ---
	if (i != LastIndex)
	{
		const long long kRefCur = RefKey(sc, sc.BaseDateTimeIn[i], refMode, refS, refE, refMin);
		const long long kTrCur  = WindowKey(sc.BaseDateTimeIn[i], trS, trE);
		long long kRefPrev = -1, kTrPrev = -1;

		if (i > 0)
		{
			const int p = i - 1;
			kRefPrev = RefKey(sc, sc.BaseDateTimeIn[p], refMode, refS, refE, refMin);
			kTrPrev  = WindowKey(sc.BaseDateTimeIn[p], trS, trE);

			if (kRefPrev != -1)
			{
				RefHighBuild = max(RefHighBuild, sc.High[p]);
				RefLowBuild  = min(RefLowBuild, sc.Low[p]);
			}

			if (kTrPrev != -1 && RefHighValid && sc.Close[p] <= RefHigh)
				BeenBelow = 1;

			// Referencni session skoncila -> zafixuj jeji high a low
			if (kRefPrev != -1 && kRefCur != kRefPrev)
			{
				RefHigh = RefHighBuild;
				RefLow = RefLowBuild;
				RefHighValid = 1;
				BeenBelow = 0;  // novy level -> cekame na novy pruraz zespodu
			}
		}

		if (kRefCur != -1 && kRefCur != kRefPrev)
		{
			RefHighBuild = -FLT_MAX;  // zacina nova referencni session
			RefLowBuild = FLT_MAX;
		}

		if (kTrCur != -1 && kTrCur != kTrPrev)
		{
			TradedSession = 0;  // zacina nova obchodni session
			BeenBelow = 0;
		}

		LastIndex = i;
	}

	// --- Aktualni bar ---
	const int t = sc.BaseDateTimeIn[i].GetTimeInSeconds();
	const bool inTrade   = InWindow(t, trS, trE);
	const bool inFlatten = InWindow(t, In_Flatten.GetTime(), trE);

	if (RefHighValid)
	{
		SG_PrevHigh[i] = RefHigh;
		SG_PrevLow[i] = RefLow;
	}

	s_SCPositionData Pos;
	sc.GetTradePosition(Pos);
	const bool flat = Pos.PositionQuantity == 0;

	// Exit: konec dne / mimo obchodni session
	if (!flat && (!inTrade || inFlatten))
	{
		sc.FlattenAndCancelAllOrders();
		return;
	}

	if (!flat)
	{
		SG_Target[i] = TargetPrice;
		return;
	}

	// Entry
	if (!In_Enabled.GetYesNo() || !RefHighValid || !inTrade || inFlatten || TradedSession)
		return;

	const bool breakout = (BeenBelow || sc.Open[i] <= RefHigh) && sc.Close[i] > RefHigh;
	if (!breakout)
		return;

	const float entry = sc.Close[i];
	const float stop  = RefLow;  // SL = low predchozi session
	const float risk  = entry - stop;
	if (risk <= 0)
		return;

	s_SCNewOrder Order;
	Order.OrderQuantity = In_Qty.GetInt();
	Order.OrderType = SCT_ORDERTYPE_MARKET;
	Order.TimeInForce = SCT_TIF_DAY;
	Order.Stop1Price = stop;
	Order.Target1Price = entry + risk * In_RR.GetFloat();

	if (sc.BuyEntry(Order) > 0)
	{
		TradedSession = 1;
		TargetPrice = Order.Target1Price;
		SG_Target[i] = TargetPrice;
	}
}
