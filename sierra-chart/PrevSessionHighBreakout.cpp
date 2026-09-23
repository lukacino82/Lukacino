// Previous-session-high breakout – jednoduchy automaticky system pro Sierra Chart (ACSIL)
//
// Logika (Direction: Long only / Short only / Long + Short):
//   Long:   cena prorazi HIGH predchozi session (PSH) ZESPODU -> buy, SL = LOW predchozi session (PSL)
//   Short:  cena prorazi LOW predchozi session (PSL) SHORA    -> sell, SL = HIGH predchozi session (PSH)
//   "Zespodu" = v aktualni obchodni session uz nejaky uzavreny bar zavrel <= PSH (od posledniho
//   vstupu), nebo aktualni bar otevrel <= PSH. Gap nad PSH na otevreni session neni pruraz.
//   Stav se pocita na kazdem baru, takze vstup se neztrati ani pri rychlem replay, kdy
//   Sierra Chart zpracuje vic baru najednou a prikazy posila jen na poslednim baru.
//   Risk/Reward:  TP = vstup +/- RR * riziko (nastavitelne)
//   Exit:         Target / Stop / konec aktualni session (volitelne - input Close At End Of Session)
//   Pozice:       1 kontrakt
//   Limity:       Max Trades Per Session (default 1), Max Trades Per Day (0 = bez limitu).
//                 Dalsi obchod v session jen po novem prurazu (cena se musi vratit pod PSH).
//
// Session Mode (vzdy plati PRAVE JEDEN rezim, rezimy se nemichaji):
//   0 = Custom Time Window  - predchozi session = okno Reference Start-End,
//                             obchoduje se v okne Trading Start-End, exit ve Flatten Time.
//   1 = Daily               - predchozi session = cely predchozi obchodni den (Session Times grafu),
//                             obchoduje se aktualni den, exit ve Flatten Time / na konci dne.
//   2 = Fixed Interval      - predchozi session = predchozi blok N minut (napr. 60 = hodina),
//                             obchoduje se aktualni blok, exit na konci bloku.
// Inputy, ktere do zvoleneho rezimu nepatri, se ignoruji.

#include "sierrachart.h"
#include <cfloat>

SCDLLName("Previous Session High Breakout")

enum { MODE_CUSTOM = 0, MODE_DAILY = 1, MODE_INTERVAL = 2 };

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

static long long IntervalKey(const SCDateTime& dt, int minutes)
{
	const long long len = (minutes > 0 ? minutes : 60) * 60LL;
	const long long secs = (long long)dt.GetDate() * 86400LL + dt.GetTimeInSeconds();
	return secs / len;
}

SCSFExport scsf_PrevSessionHighBreakout(SCStudyInterfaceRef sc)
{
	SCSubgraphRef SG_PrevHigh = sc.Subgraph[0];
	SCSubgraphRef SG_PrevLow  = sc.Subgraph[1];
	SCSubgraphRef SG_Target   = sc.Subgraph[2];

	SCInputRef In_Enabled    = sc.Input[0];
	SCInputRef In_Mode       = sc.Input[1];
	SCInputRef In_RefStart   = sc.Input[2];
	SCInputRef In_RefEnd     = sc.Input[3];
	SCInputRef In_TradeStart = sc.Input[4];
	SCInputRef In_TradeEnd   = sc.Input[5];
	SCInputRef In_Flatten    = sc.Input[6];
	SCInputRef In_Minutes    = sc.Input[7];
	SCInputRef In_RR         = sc.Input[8];
	SCInputRef In_Qty        = sc.Input[9];
	SCInputRef In_MaxSess    = sc.Input[10];
	SCInputRef In_MaxDay     = sc.Input[11];
	SCInputRef In_CloseEOS   = sc.Input[12];
	SCInputRef In_Direction  = sc.Input[13];

	if (sc.SetDefaults)
	{
		sc.GraphName = "Previous Session High Breakout";
		sc.StudyDescription = "Long pri prurazu high / short pri prurazu low predchozi session, SL na opacne strane predchozi session, TP = RR x riziko, exit na konci session.";
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

		In_Mode.Name = "Session Mode";
		In_Mode.SetCustomInputStrings("Custom Time Window;Daily (Previous Day);Fixed Interval (minutes)");
		In_Mode.SetCustomInputIndex(MODE_CUSTOM);

		In_RefStart.Name = "[Custom] Previous Session Start";
		In_RefStart.SetTime(HMS_TIME(9, 30, 0));
		In_RefEnd.Name = "[Custom] Previous Session End";
		In_RefEnd.SetTime(HMS_TIME(16, 0, 0));
		In_TradeStart.Name = "[Custom] Trading Session Start";
		In_TradeStart.SetTime(HMS_TIME(9, 30, 0));
		In_TradeEnd.Name = "[Custom] Trading Session End";
		In_TradeEnd.SetTime(HMS_TIME(16, 0, 0));

		In_Flatten.Name = "[Custom + Daily] Flatten Time (End of Day Exit)";
		In_Flatten.SetTime(HMS_TIME(15, 55, 0));

		In_Minutes.Name = "[Interval] Interval Length (minutes)";
		In_Minutes.SetInt(60);
		In_Minutes.SetIntLimits(1, 1440);

		In_RR.Name = "Reward : Risk";
		In_RR.SetFloat(1.0f);
		In_Qty.Name = "Position Size (contracts)";
		In_Qty.SetInt(1);

		In_MaxSess.Name = "Max Trades Per Session";
		In_MaxSess.SetInt(1);
		In_MaxSess.SetIntLimits(1, 1000);
		In_MaxDay.Name = "Max Trades Per Day (0 = no limit)";
		In_MaxDay.SetInt(0);
		In_MaxDay.SetIntLimits(0, 1000);

		In_CloseEOS.Name = "Close Position At End Of Session/Day";
		In_CloseEOS.SetYesNo(1);

		In_Direction.Name = "Direction";
		In_Direction.SetCustomInputStrings("Long only;Short only;Long + Short");
		In_Direction.SetCustomInputIndex(0);

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

	float& RefHigh       = sc.GetPersistentFloat(1);  // high predchozi (dokoncene) session
	float& RefHighBuild  = sc.GetPersistentFloat(2);  // high rozpracovane session
	float& RefLow        = sc.GetPersistentFloat(3);  // low predchozi (dokoncene) session
	float& RefLowBuild   = sc.GetPersistentFloat(4);  // low rozpracovane session
	float& TargetPrice   = sc.GetPersistentFloat(5);
	double& EntryKey     = sc.GetPersistentDouble(1); // session, ve ktere byla otevrena pozice
	int& RefValid        = sc.GetPersistentInt(1);
	int& TradesSession   = sc.GetPersistentInt(2);    // pocet obchodu v aktualni session
	int& RefPartial      = sc.GetPersistentInt(3);    // prvni referencni session na grafu neni kompletni
	int& LastIndex       = sc.GetPersistentInt(4);
	int& TradesDay       = sc.GetPersistentInt(5);    // pocet obchodu v aktualnim obchodnim dni
	int& DayKey          = sc.GetPersistentInt(6);
	int& BeenBelow       = sc.GetPersistentInt(7);    // v session byl close <= PSH -> long pruraz mozny
	int& BeenAbove       = sc.GetPersistentInt(8);    // v session byl close >= PSL -> short pruraz mozny

	const int i = sc.Index;
	const int mode    = In_Mode.GetIndex();
	const int refS    = In_RefStart.GetTime(), refE = In_RefEnd.GetTime();
	const int trS     = In_TradeStart.GetTime(), trE = In_TradeEnd.GetTime();
	const int minutes = In_Minutes.GetInt();

	// Klic predchozi/referencni session a klic obchodni session podle JEDNOHO zvoleneho rezimu
	auto RefKey = [&](const SCDateTime& dt) -> long long
	{
		switch (mode)
		{
		case MODE_DAILY:    return sc.GetTradingDayDate(dt);
		case MODE_INTERVAL: return IntervalKey(dt, minutes);
		default:            return WindowKey(dt, refS, refE);
		}
	};
	auto TradeKey = [&](const SCDateTime& dt) -> long long
	{
		switch (mode)
		{
		case MODE_DAILY:    return sc.GetTradingDayDate(dt);
		case MODE_INTERVAL: return IntervalKey(dt, minutes);
		default:            return WindowKey(dt, trS, trE);
		}
	};

	if (i == 0)
	{
		RefHigh = 0; RefHighBuild = -FLT_MAX;
		RefLow = 0; RefLowBuild = FLT_MAX;
		TargetPrice = 0; EntryKey = -1;
		RefValid = 0; TradesSession = 0;
		RefPartial = RefKey(sc.BaseDateTimeIn[0]) != -1 ? 1 : 0;  // data zacinaji uprostred session
		LastIndex = -1; TradesDay = 0; DayKey = -1;
		BeenBelow = 0; BeenAbove = 0;
	}

	const long long kTrCur  = TradeKey(sc.BaseDateTimeIn[i]);
	const long long kTrPrev = i > 0 ? TradeKey(sc.BaseDateTimeIn[i - 1]) : -1;

	s_SCPositionData Pos;
	sc.GetTradePosition(Pos);
	const bool flat = Pos.PositionQuantity == 0;

	// --- Zpracovani uzavreneho baru a prechodu mezi sessions (jednou za bar) ---
	if (i != LastIndex)
	{
		const long long kRefCur = RefKey(sc.BaseDateTimeIn[i]);
		long long kRefPrev = -1;
		bool refChanged = false;

		if (i > 0)
		{
			const int p = i - 1;
			kRefPrev = RefKey(sc.BaseDateTimeIn[p]);

			if (kRefPrev != -1)
			{
				RefHighBuild = max(RefHighBuild, sc.High[p]);
				RefLowBuild  = min(RefLowBuild, sc.Low[p]);
			}

			// Predchozi session skoncila -> zafixuj jeji high a low
			if (kRefPrev != -1 && kRefCur != kRefPrev)
			{
				if (RefPartial)
					RefPartial = 0;  // neuplnou session nepouzivej
				else
				{
					RefHigh = RefHighBuild;
					RefLow = RefLowBuild;
					RefValid = 1;
					refChanged = true;
				}
			}
		}

		if (kRefCur != -1 && kRefCur != kRefPrev)
		{
			RefHighBuild = -FLT_MAX;  // zacina nova session
			RefLowBuild = FLT_MAX;
		}

		if (kTrCur != -1 && kTrCur != kTrPrev)
		{
			TradesSession = 0;  // nova obchodni session -> vynuluj pocitadlo
		}

		// Stav pro pruraz: novy level nebo nova session -> zacina se znovu.
		// Jinak uzavreny bar teze session (bez otevrene pozice) zapise, ze cena byla pod PSH / nad PSL.
		if (refChanged || kTrCur != kTrPrev)
		{
			BeenBelow = 0;
			BeenAbove = 0;
		}
		else if (i > 0 && kTrCur != -1 && RefValid && flat)
		{
			if (sc.Close[i - 1] <= RefHigh) BeenBelow = 1;
			if (sc.Close[i - 1] >= RefLow)  BeenAbove = 1;
		}

		const int dayCur = sc.GetTradingDayDate(sc.BaseDateTimeIn[i]);
		if (dayCur != DayKey)
		{
			TradesDay = 0;  // novy obchodni den
			DayKey = dayCur;
		}

		LastIndex = i;
	}

	// --- Aktualni bar ---
	const int t = sc.BaseDateTimeIn[i].GetTimeInSeconds();

	// Okno pred koncem dne, kdy se pozice zavira a nevstupuje se.
	// Flatten Time mimo obchodni session se ignoruje (jinak by blokoval vstupy skoro cely den).
	const int flatT = In_Flatten.GetTime();
	bool inFlatten = false;
	if (mode == MODE_CUSTOM && InWindow(flatT, trS, trE))
		inFlatten = InWindow(t, flatT, trE);
	else if (mode == MODE_DAILY && InWindow(flatT, sc.StartTime1, sc.EndTime1 + 1))
		inFlatten = InWindow(t, flatT, sc.EndTime1 + 1);

	// Custom: okna se nesmi castecne prekryvat (obchodovalo by se podle stareho levelu,
	// zatimco nova predchozi session jeste bezi). Povoleno: totozna okna nebo oddelena okna.
	bool configOK = true;
	if (mode == MODE_CUSTOM)
	{
		const bool same = refS == trS && refE == trE;
		const bool overlap = InWindow(trS, refS, refE) || InWindow(refS, trS, trE);
		configOK = same || !overlap;
		if (!configOK && i == sc.ArraySize - 1 && sc.IsFullRecalculation)
			sc.AddMessageToLog("Previous Session High Breakout: [Custom] Previous a Trading okno se castecne prekryvaji - obchodovani vypnuto.", 1);
	}

	if (RefValid)
	{
		SG_PrevHigh[i] = RefHigh;
		SG_PrevLow[i] = RefLow;
	}

	const bool closeEOS = In_CloseEOS.GetYesNo() != 0;

	// Exit: konec session, ve ktere byl obchod otevren / Flatten Time
	// (pri Close At End Of Session = No se pozice drzi jen do Stop / Target)
	if (!flat)
	{
		if (EntryKey < 0)
			EntryKey = (double)kTrCur;  // pozice existovala uz pred prepocitanim studie

		if (closeEOS && (kTrCur == -1 || (double)kTrCur != EntryKey || inFlatten))
		{
			sc.FlattenAndCancelAllOrders();
			return;
		}
		SG_Target[i] = TargetPrice;
		return;
	}

	// Entry
	if (!In_Enabled.GetYesNo() || !configOK || !RefValid || kTrCur == -1 || inFlatten)
		return;

	// Limity poctu obchodu
	const int maxSess = In_MaxSess.GetInt() > 0 ? In_MaxSess.GetInt() : 1;
	if (TradesSession >= maxSess)
		return;
	if (In_MaxDay.GetInt() > 0 && TradesDay >= In_MaxDay.GetInt())
		return;

	// Pruraz v ramci TETO session (stav BeenBelow/BeenAbove + open aktualniho baru).
	// Gap za level ani pokracovani za levelem bez navratu neni vstup.
	const int dir = In_Direction.GetIndex();  // 0 = long, 1 = short, 2 = oboje
	const bool longOK  = dir != 1 && (BeenBelow || sc.Open[i] <= RefHigh) && sc.Close[i] > RefHigh;
	const bool shortOK = dir != 0 && (BeenAbove || sc.Open[i] >= RefLow)  && sc.Close[i] < RefLow;
	if (!longOK && !shortOK)
		return;

	const bool isLong = longOK;
	const float entry = sc.Close[i];
	const float stop  = isLong ? RefLow : RefHigh;  // SL = opacna strana predchozi session
	const float risk  = isLong ? entry - stop : stop - entry;
	if (risk <= 0)
		return;

	s_SCNewOrder Order;
	Order.OrderQuantity = In_Qty.GetInt();
	Order.OrderType = SCT_ORDERTYPE_MARKET;
	// GTC vzdy: Stop/Target nesmi vyprset, ani kdyz se Close At End Of Session
	// prepne na No pri otevrene pozici. Pri Yes je zrusi FlattenAndCancelAllOrders.
	Order.TimeInForce = SCT_TIF_GOOD_TILL_CANCELED;
	Order.Stop1Price = stop;
	Order.Target1Price = isLong ? entry + risk * In_RR.GetFloat() : entry - risk * In_RR.GetFloat();

	const int result = (int)(isLong ? sc.BuyEntry(Order) : sc.SellEntry(Order));

	// Diagnostika: na poslednim (zivem) baru zapis do Message Logu, proc prikaz neprosel
	if (result <= 0 && i == sc.ArraySize - 1)
	{
		SCString msg;
		msg.Format("Previous Session High Breakout: %s signal na %.2f, ale prikaz vratil chybu %d "
			"(zkontroluj Trade >> Auto Trading Enabled Global/Chart, Trade Simulation Mode a Trade Service Log).",
			isLong ? "LONG" : "SHORT", entry, result);
		sc.AddMessageToLog(msg, 1);
	}

	// Signal na historii pri nacteni/prepoctu grafu (prikazy se tam neposilaji) ber jako spotrebovany,
	// aby se po nacteni grafu nevstupovalo pozde za cenou, ktera uz level davno prorazila.
	if (result <= 0 && sc.IsFullRecalculation)
	{
		BeenBelow = 0;
		BeenAbove = 0;
	}

	if (result > 0)
	{
		TradesSession++;
		TradesDay++;
		BeenBelow = 0;  // dalsi obchod az po novem navratu za level
		BeenAbove = 0;
		EntryKey = (double)kTrCur;
		TargetPrice = Order.Target1Price;
		SG_Target[i] = TargetPrice;
	}
}
