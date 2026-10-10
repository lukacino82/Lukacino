#include "sierrachart.h"
#include <cstdio>
#include <string>
#include <vector>

std::vector<std::string> g_Log;
extern "C" void scsf_LukacinoAutoTrader(SCStudyInterfaceRef sc);

static s_sc sc;
static int g_Fail = 0;

static void DumpLog(const char* tag){
  for (size_t i=0;i<g_Log.size();i++) printf("      [%s] %s\n", tag, g_Log[i].c_str());
  g_Log.clear();
}
static void Check(const char* what, bool ok){
  printf("   %-58s %s\n", what, ok?"OK":"<<< FAIL");
  if(!ok) g_Fail++;
}

// Inputy podle screenshotu uzivatele
enum { I_ENABLED=0, I_MODE=1, I_AUTO=2, I_UNITS=3, I_SRC=4, I_MANUAL=5, I_SIG=6,
       I_SLMODE=7, I_SLVAL=8, I_ATRP=9, I_ATRM=10, I_TPMODE=11, I_TPVAL=12, I_RRR=13,
       I_SIZE=14, I_MAXCONC=15, I_MAXDAY=16, I_TRAILON=17, I_TRAILMODE=18,
       I_TRTRIG=19, I_TRDIST=20, I_TRSTEP=21, I_KILL=22, I_LOSS=23, I_REDELAY=24,
       I_SEND=25, I_DRAW=26, I_LOG=27, I_OPENNOW=28, I_SHOWTXT=29, I_TXTCOL=30, I_TXTSIZE=31 };

static void FreeStudy(){
  sc.LastCallToFunction = 1; scsf_LukacinoAutoTrader(sc); sc.LastCallToFunction = 0;
  for (int i=0;i<8;i++) sc.Persist[i]=0;
}

static void ResetAll(){
  FreeStudy();
  sc.Orders.clear(); sc.NextOrderID=1; sc.NetQty=0; sc.AvgPrice=0;
  sc.Close.d.clear(); sc.High.d.clear(); sc.Low.d.clear(); sc.BaseDateTimeIn.d.clear();
  sc.ArraySize=0; sc.MenuEventID=0; g_Log.clear();
  sc.SetDefaults=1; scsf_LukacinoAutoTrader(sc); sc.SetDefaults=0;
}

// jeden "tick": prida/aktualizuje bar, zpracuje fily, zavola study
static void Tick(double price, double minutes){
  sc.ProcessFills(price);
  sc.LastTradePrice = price;
  double t = 45000.0 + minutes/1440.0;   // fiktivni datum + cas
  sc.Close.d.push_back((float)price);
  sc.High.d.push_back((float)price);
  sc.Low.d.push_back((float)price);
  sc.BaseDateTimeIn.d.push_back(t);
  sc.ArraySize = (int)sc.Close.d.size();
  sc.UpdateStartIndex = sc.ArraySize-1;
  sc.CurrentSystemDateTime = SCDateTime(t);
  scsf_LukacinoAutoTrader(sc);
}

static int CountFilledEntries(){
  int n=0; for (size_t i=0;i<sc.Orders.size();i++)
    if (sc.Orders[i].IsEntry && sc.Orders[i].Status==SCT_OSC_FILLED) n++;
  return n;
}
static int OpenStopPriceCount(double p){
  int n=0; for (size_t i=0;i<sc.Orders.size();i++)
    if (sc.Orders[i].IsStop && sc.Orders[i].Status==SCT_OSC_OPEN
        && sc.Orders[i].Price1 > p-1e-9 && sc.Orders[i].Price1 < p+1e-9) n++;
  return n;
}
static double OpenStopPrice(){
  for (size_t i=0;i<sc.Orders.size();i++)
    if (sc.Orders[i].IsStop && sc.Orders[i].Status==SCT_OSC_OPEN) return sc.Orders[i].Price1;
  return 0.0;
}

// nastaveni presne podle screenshotu uzivatele (NQ, Points, SL 20, RRR 2)
static void ApplyUserSettings(){
  sc.Input[I_ENABLED].SetYesNo(1);
  sc.Input[I_MODE].SetCustomInputIndex(0);     // Long only
  sc.Input[I_AUTO].SetCustomInputIndex(1);     // Full auto
  sc.Input[I_UNITS].SetCustomInputIndex(1);    // Points
  sc.Input[I_SRC].SetCustomInputIndex(0);      // Manual only
  sc.Input[I_MANUAL].SetCustomInputIndex(0);   // Off
  sc.Input[I_SLMODE].SetCustomInputIndex(0);   // Fixed
  sc.Input[I_SLVAL].SetFloat(20.0f);
  sc.Input[I_TPMODE].SetCustomInputIndex(1);   // RRR
  sc.Input[I_RRR].SetFloat(2.0f);
  sc.Input[I_SIZE].SetInt(1);
  sc.Input[I_MAXCONC].SetInt(1);
  sc.Input[I_MAXDAY].SetInt(10);
  sc.Input[I_TRAILON].SetYesNo(0);             // trailing OFF
  sc.Input[I_TRAILMODE].SetCustomInputIndex(1);
  sc.Input[I_TRTRIG].SetFloat(12.0f);
  sc.Input[I_TRDIST].SetFloat(8.0f);
  sc.Input[I_TRSTEP].SetFloat(2.0f);
  sc.Input[I_KILL].SetYesNo(0);
  sc.Input[I_LOSS].SetFloat(0.0f);
  sc.Input[I_REDELAY].SetInt(5);
  sc.Input[I_SEND].SetYesNo(1);
  sc.Input[I_DRAW].SetYesNo(1);
  sc.Input[I_LOG].SetYesNo(1);
  sc.Input[I_OPENNOW].SetYesNo(0);
  sc.Input[I_SHOWTXT].SetYesNo(1);
}

// =====================================================================
int main(){
  printf("\n=== TEST 1: presne nastaveni uzivatele, input 29 No -> Yes ===\n");
  {
    ResetAll(); ApplyUserSettings();
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);          // rozbeh
    g_Log.clear();
    sc.Input[I_OPENNOW].SetYesNo(1);           // uzivatel prepne na Yes
    Tick(p, 5);
    Tick(p, 6);
    DumpLog("T1");
    Check("vstup se otevrel", CountFilledEntries() >= 1);
    Check("netto pozice = 1", sc.NetQty == 1.0);
  }

  printf("\n=== TEST 2: Both mode blokuje, pak prepnuti na Long only ===\n");
  {
    ResetAll(); ApplyUserSettings();
    sc.Input[I_MODE].SetCustomInputIndex(2);   // Both
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    g_Log.clear();
    sc.Input[I_OPENNOW].SetYesNo(1);
    Tick(p, 5); Tick(p, 6);
    Check("v Both modu se nic neotevrelo", CountFilledEntries()==0);
    sc.Input[I_MODE].SetCustomInputIndex(0);   // prepnuti na Long only
    Tick(p, 7); Tick(p, 8);
    DumpLog("T2");
    Check("po prepnuti na Long se vstup odpalil", CountFilledEntries()>=1);
  }

  printf("\n=== TEST 3: manualni trigger Off -> Buy (semi auto) ===\n");
  {
    ResetAll(); ApplyUserSettings();
    sc.Input[I_AUTO].SetCustomInputIndex(0);   // semi auto
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    g_Log.clear();
    sc.Input[I_MANUAL].SetCustomInputIndex(1); // Buy
    Tick(p, 5); Tick(p, 6);
    DumpLog("T3");
    Check("manualni Buy otevrel obchod", CountFilledEntries()>=1);
  }

  printf("\n=== TEST 4: TP zasah, detekce uzavreni, full auto re-entry ===\n");
  {
    ResetAll(); ApplyUserSettings();
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    sc.Input[I_OPENNOW].SetYesNo(1);
    Tick(p, 5); Tick(p, 6);
    int entriesAfterFirst = CountFilledEntries();
    g_Log.clear();
    // TP = 20 points * RRR 2 = 40 points -> 29840
    for (int i=0;i<4;i++) Tick(29845.0, 7+i);
    DumpLog("T4");
    Check("prvni obchod se uzavrel na TP", sc.NetQty==0.0 || CountFilledEntries()>entriesAfterFirst);
    // full auto: po 5 s prodlevy (cas chartu) ma otevrit znovu
    for (int i=0;i<4;i++) Tick(29845.0, 11+i);
    DumpLog("T4b");
    Check("full auto znovu otevrel obchod", CountFilledEntries() > entriesAfterFirst);
  }

  printf("\n=== TEST 5: SL zasah a zaporne realizovane P/L ===\n");
  {
    ResetAll(); ApplyUserSettings();
    sc.Input[I_AUTO].SetCustomInputIndex(0);   // semi auto, at nereentruje
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    sc.Input[I_OPENNOW].SetYesNo(1);
    Tick(p, 5); Tick(p, 6);
    g_Log.clear();
    for (int i=0;i<4;i++) Tick(29775.0, 7+i);  // SL = 29780
    DumpLog("T5");
    Check("obchod uzavren na SL, pozice flat", sc.NetQty==0.0);
  }

  printf("\n=== TEST 6: trailing per position posouva stop ===\n");
  {
    ResetAll(); ApplyUserSettings();
    sc.Input[I_AUTO].SetCustomInputIndex(0);
    sc.Input[I_TRAILON].SetYesNo(1);
    sc.Input[I_TRTRIG].SetFloat(10.0f);        // 10 points
    sc.Input[I_TRDIST].SetFloat(6.0f);
    sc.Input[I_TRSTEP].SetFloat(1.0f);
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    sc.Input[I_OPENNOW].SetYesNo(1);
    Tick(p, 5); Tick(p, 6);
    double stopBefore = OpenStopPrice();
    g_Log.clear();
    Tick(29815.0, 7); Tick(29820.0, 8);
    DumpLog("T6");
    double stopAfter = OpenStopPrice();
    printf("      stop pred: %.2f  po: %.2f\n", stopBefore, stopAfter);
    Check("stop se posunul nahoru", stopAfter > stopBefore + 1e-9);
    Check("stop = cena - 6 bodu", stopAfter > 29813.9 && stopAfter < 29814.1);
  }

  printf("\n=== TEST 7: kill switch flattne a zablokuje vstupy ===\n");
  {
    ResetAll(); ApplyUserSettings();
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    sc.Input[I_OPENNOW].SetYesNo(1);
    Tick(p, 5); Tick(p, 6);
    g_Log.clear();
    sc.Input[I_KILL].SetYesNo(1);
    Tick(p, 7); Tick(p, 8);
    DumpLog("T7");
    Check("kill switch vyflattoval pozici", sc.NetQty==0.0);
  }

  printf("\n=== TEST 8: cizi pozice v DOM blokuje vstup (MaximumPositionAllowed) ===\n");
  {
    ResetAll(); ApplyUserSettings();
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    sc.NetQty = 1.0; sc.AvgPrice = 30836.25;   // cizi pozice z jine study
    g_Log.clear();
    sc.Input[I_OPENNOW].SetYesNo(1);
    Tick(p, 5); Tick(p, 6);
    DumpLog("T8");
    printf("      entries: %d\n", CountFilledEntries());
  }

  printf("\n=== TEST 9: Sierra uklizi fillnute ordery ze seznamu ===\n");
  {
    ResetAll(); ApplyUserSettings();
    sc.PurgeTerminalOrders = true;           // chovani skutecne Sierry
    sc.Input[I_AUTO].SetCustomInputIndex(0); // semi auto
    sc.EntrySubmitCount = 0;
    double p = 29800.0;
    for (int i=0;i<5;i++) Tick(p, i);
    sc.Input[I_OPENNOW].SetYesNo(1);
    for (int i=0;i<8;i++) Tick(p, 5+i);      // entry order mezitim zmizi ze seznamu

    bool lostTrack=false;
    for (size_t i=0;i<g_Log.size();i++)
      if (g_Log[i].find("POZOR")!=std::string::npos) lostTrack=true;
    DumpLog("T9");
    Check("study neztratila stopu po vlastni pozici", !lostTrack);
    Check("odeslan prave jeden vstup", sc.EntrySubmitCount==1);
    Check("pozice je otevrena", sc.NetQty==1.0);

    g_Log.clear();
    for (int i=0;i<4;i++) Tick(29845.0, 20+i);   // TP 29840
    bool sawExit=false;
    for (size_t i=0;i<g_Log.size();i++)
      if (g_Log[i].find("EXIT")!=std::string::npos) sawExit=true;
    DumpLog("T9b");
    Check("uzavreni na TP bylo detekovano", sawExit);
    Check("pozice je flat", sc.NetQty==0.0);
    sc.PurgeTerminalOrders = false;
  }

  printf("\n=========== %s ===========\n\n", g_Fail==0 ? "VSE PROSLO" : "NEKTERE TESTY SELHALY");
  return g_Fail;
}
