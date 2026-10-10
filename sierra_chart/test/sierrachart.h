// Simulator ACSIL rozhrani pro testovani LukacinoAutoTrader.cpp mimo Sierra Chart.
#pragma once
#include <cstring>
#include <cstdio>
#include <cstdarg>
#include <vector>
#include <string>

typedef unsigned int COLORREF;
inline COLORREF RGB(int r,int g,int b){return (COLORREF)(r|(g<<8)|(b<<16));}

#define SCDLLName(x)
#define SCSFExport extern "C" void
#define DT_RIGHT 1
#define DT_BOTTOM 2

enum SubgraphLineStyles { LINESTYLE_SOLID = 0, LINESTYLE_DOT = 1 };
enum { DRAWSTYLE_IGNORE = 0, LOW_PREC_LEVEL = 0 };
enum { DRAWING_LINE = 1, DRAWING_TEXT = 2 };
enum { UTAM_ADD_OR_ADJUST = 1, TOOL_DELETE_CHARTDRAWING = 2 };
enum { MOVAVGTYPE_WILDERS = 3 };
enum { SCT_ORDERTYPE_MARKET = 1, SCT_ORDERTYPE_STOP = 2, SCT_ORDERTYPE_LIMIT = 3 };
enum { SCT_TIF_DAY = 1 };
enum { SCT_OSC_OPEN = 1, SCT_OSC_FILLED = 2, SCT_OSC_CANCELED = 3, SCT_OSC_ERROR = 4 };
enum { SCTRADING_ORDER_ERROR = -1 };

extern std::vector<std::string> g_Log;

struct SCString {
  char Buf[1024];
  SCString(){Buf[0]=0;}
  SCString(const char* s){ std::snprintf(Buf,sizeof(Buf),"%s", s?s:""); }
  const char* GetChars() const { return Buf; }
  void Format(const char* f, ...) {
    va_list ap; va_start(ap,f); std::vsnprintf(Buf,sizeof(Buf),f,ap); va_end(ap);
  }
  SCString& operator=(const char* s){ std::snprintf(Buf,sizeof(Buf),"%s",s?s:""); return *this; }
};

struct SCDateTime {
  double v;
  SCDateTime():v(0){}
  SCDateTime(double d):v(d){}
  double GetAsDouble() const { return v; }
};

struct SCFloatArray {
  std::vector<float> d;
  float operator[](int i) const { return (i>=0 && i<(int)d.size()) ? d[i] : 0.0f; }
  float& operator[](int i) { static float dummy=0.0f;
    if (i<0) return dummy;
    if (i>=(int)d.size()) d.resize(i+1, 0.0f);
    return d[i]; }
  int GetArraySize() const { return (int)d.size(); }
};
typedef SCFloatArray& SCFloatArrayRef;

struct SCDateTimeArray {
  std::vector<double> d;
  SCDateTime operator[](int i) const {
    return SCDateTime((i>=0 && i<(int)d.size()) ? d[i] : 0.0); }
};

struct SCSubgraph {
  SCString Name;
  int DrawStyle;
  SCFloatArray Arr;
  float operator[](int i) const { return Arr[i]; }
  float& operator[](int i) { return Arr[i]; }
};
typedef SCSubgraph& SCSubgraphRef;

struct SCInput {
  SCString Name;
  int IntVal = 0; float FloatVal = 0.0f; int Index = 0; int YesNo = 0;
  COLORREF Color = 0;
  void SetYesNo(int v){ YesNo=v; }           int GetYesNo() const {return YesNo;}
  void SetInt(int v){ IntVal=v; }            int GetInt() const {return IntVal;}
  void SetFloat(float v){ FloatVal=v; }      float GetFloat() const {return FloatVal;}
  void SetIntLimits(int,int){}
  void SetCustomInputStrings(const char*){}
  void SetCustomInputIndex(int v){ Index=v; }
  int GetIndex() const {return Index;}
  void SetStudySubgraphValues(int,int){}
  int GetStudyID() const {return 0;}
  int GetSubgraphIndex() const {return 0;}
  void SetColor(int r,int g,int b){ Color=RGB(r,g,b); }
  COLORREF GetColor() const {return Color;}
};
typedef SCInput& SCInputRef;

struct SCBaseData { SCFloatArray a; };
typedef SCBaseData& SCBaseDataRef;

struct s_SCNewOrder {
  int OrderQuantity, OrderType, TimeInForce, InternalOrderID, OCOGroup1Quantity;
  int AttachedOrderStop1Type, AttachedOrderTarget1Type;
  double Stop1Offset, Target1Offset, Price1;
  s_SCNewOrder(){ std::memset(this,0,sizeof(*this)); }
};

struct s_SCTradeOrder {
  int InternalOrderID, ParentInternalOrderID, OrderStatusCode;
  double Price1, AvgFillPrice;
  s_SCTradeOrder(){ std::memset(this,0,sizeof(*this)); }
};

struct s_SCPositionData {
  double PositionQuantity, AveragePrice;
  s_SCPositionData(){ std::memset(this,0,sizeof(*this)); }
};

struct s_UseTool {
  int ChartNumber, DrawingType, LineNumber, BeginIndex, EndIndex, LineWidth;
  int FontSize, FontBold, AddMethod, AddAsUserDrawnDrawing, TextAlignment;
  float BeginValue, EndValue;
  COLORREF Color, TextColor;
  SubgraphLineStyles LineStyle;
  SCString Text;
  void Clear(){ ChartNumber=DrawingType=LineNumber=BeginIndex=EndIndex=LineWidth=0;
                FontSize=FontBold=AddMethod=AddAsUserDrawnDrawing=TextAlignment=0;
                BeginValue=EndValue=0.0f; Color=TextColor=0;
                LineStyle=LINESTYLE_SOLID; Text=""; }
};

// --------------------------------------------------------------------------
// Simulovana evidence orderu
// --------------------------------------------------------------------------
struct SimOrder {
  int ID = 0, ParentID = 0, Status = SCT_OSC_OPEN;
  double Price1 = 0.0, AvgFillPrice = 0.0;
  int Qty = 0;
  int Action = 0;      // +1 buy, -1 sell
  int IsEntry = 0, IsStop = 0;
  int TerminalAge = 0;
  int SiblingID = 0;   // OCO
};

struct s_sc {
  int SetDefaults=0, GraphRegion=0, AutoLoop=0, UpdateAlways=0, CalculationPrecedence=0;
  int SupportAttachedOrdersForTrading=0, AllowMultipleEntriesInSameDirection=0;
  int AllowOnlyOneTradePerBar=0, MaintainTradeStatisticsAndTradesData=0;
  int CancelAllOrdersOnEntriesAndReversals=0, AllowEntryWithWorkingOrders=0;
  int SupportReversals=0, AllowOppositeEntryWithOpposingPositionOrOrders=0;
  int MaximumPositionAllowed=0, LastCallToFunction=0, ArraySize=0, UpdateStartIndex=0;
  int IsFullRecalculation=0, SendOrdersToTradeService=0, MenuEventID=0, ChartNumber=1;
  int BaseGraphValueFormat=2;
  double TickSize=0.25, LastTradePrice=0.0, CurrencyValuePerTick=5.0;
  SCString GraphName;
  SCInput Input[128];
  SCSubgraph Subgraph[64];
  SCFloatArray Close, High, Low, Open;
  SCDateTimeArray BaseDateTimeIn;
  SCBaseData BaseDataIn;
  SCDateTime CurrentSystemDateTime;

  // --- simulator state
  std::vector<SimOrder> Orders;
  int NextOrderID = 1;
  double NetQty = 0.0, AvgPrice = 0.0;
  void* Persist[8] = {0};
  float SimATR = 10.0f;
  bool PurgeTerminalOrders = false;
  int EntrySubmitCount = 0;

  void SetCustomStudyControlBarButtonText(int, const char*){}
  void* GetPersistentPointer(int i){ return Persist[i]; }
  void SetPersistentPointer(int i, void* p){ Persist[i]=p; }

  void ATR(SCBaseDataRef, SCSubgraphRef sg, int idx, int, unsigned int){ sg[idx]=SimATR; }
  int GetTradingDayDate(SCDateTime dt){ return (int)dt.GetAsDouble(); }

  void GetTradePosition(s_SCPositionData& p){ p.PositionQuantity=NetQty; p.AveragePrice=AvgPrice; }

  int GetOrderByOrderID(int id, s_SCTradeOrder& o){
    for (size_t i=0;i<Orders.size();i++) if (Orders[i].ID==id){
      o.InternalOrderID=Orders[i].ID; o.ParentInternalOrderID=Orders[i].ParentID;
      o.OrderStatusCode=Orders[i].Status; o.Price1=Orders[i].Price1;
      o.AvgFillPrice=Orders[i].AvgFillPrice; return 1; }
    return SCTRADING_ORDER_ERROR;
  }
  int GetOrderByIndex(int idx, s_SCTradeOrder& o){
    if (idx<0 || idx>=(int)Orders.size()) return SCTRADING_ORDER_ERROR;
    o.InternalOrderID=Orders[idx].ID; o.ParentInternalOrderID=Orders[idx].ParentID;
    o.OrderStatusCode=Orders[idx].Status; o.Price1=Orders[idx].Price1;
    o.AvgFillPrice=Orders[idx].AvgFillPrice; return 1;
  }

  void AddMessageToLog(const char* m, int){ g_Log.push_back(m?m:""); }
  void AddMessageToLog(SCString& m, int){ g_Log.push_back(m.GetChars()); }

  double RoundToTickSize(double v, double ts){ if(ts<=0) return v;
    double n = (v>=0) ? (long long)(v/ts+0.5) : -(long long)(-v/ts+0.5); return n*ts; }

  int ModifyOrder(s_SCNewOrder& mo){
    for (size_t i=0;i<Orders.size();i++)
      if (Orders[i].ID==mo.InternalOrderID && Orders[i].Status==SCT_OSC_OPEN){
        Orders[i].Price1 = mo.Price1; return 1; }
    return -1;
  }

  int FlattenAndCancelAllOrders(){
    for (size_t i=0;i<Orders.size();i++)
      if (Orders[i].Status==SCT_OSC_OPEN) Orders[i].Status=SCT_OSC_CANCELED;
    NetQty=0.0; AvgPrice=0.0; return 1;
  }

  void GetStudyArrayUsingID(int,int,SCFloatArrayRef){}

  int SubmitEntry(s_SCNewOrder& no, int action){
    // Sierra odmitne order, ktery by prekrocil MaximumPositionAllowed
    double projected = NetQty + action*no.OrderQuantity;
    double absProj = projected<0?-projected:projected;
    if (MaximumPositionAllowed>0 && absProj > MaximumPositionAllowed + 1e-9) return -1;

    SimOrder e; e.ID=NextOrderID++; e.Status=SCT_OSC_FILLED;
    e.AvgFillPrice=LastTradePrice; e.Price1=LastTradePrice;
    e.Qty=no.OrderQuantity; e.Action=action; e.IsEntry=1;
    Orders.push_back(e);

    AvgPrice = (NetQty==0.0) ? LastTradePrice : AvgPrice;
    NetQty = projected;

    SimOrder tgt; tgt.ID=NextOrderID++; tgt.ParentID=e.ID; tgt.Status=SCT_OSC_OPEN;
    tgt.Price1 = e.AvgFillPrice + action*no.Target1Offset;
    tgt.Qty=no.OrderQuantity; tgt.Action=-action;
    SimOrder stp; stp.ID=NextOrderID++; stp.ParentID=e.ID; stp.Status=SCT_OSC_OPEN;
    stp.Price1 = e.AvgFillPrice - action*no.Stop1Offset;
    stp.Qty=no.OrderQuantity; stp.Action=-action; stp.IsStop=1;
    tgt.SiblingID=stp.ID; stp.SiblingID=tgt.ID;
    Orders.push_back(tgt); Orders.push_back(stp);

    no.InternalOrderID = e.ID;
    EntrySubmitCount++;
    return 1;
  }
  int BuyEntry(s_SCNewOrder& no){ return SubmitEntry(no, +1); }
  int SellEntry(s_SCNewOrder& no){ return SubmitEntry(no, -1); }

  void DeleteACSChartDrawing(int,int,int){}
  void UseTool(s_UseTool&){}

  // --- zpracovani fillu exit orderu podle ceny
  void ProcessFills(double price){
    for (size_t i=0;i<Orders.size();i++){
      SimOrder& o = Orders[i];
      if (o.Status!=SCT_OSC_OPEN || o.IsEntry) continue;
      bool hit = (o.Action<0) ? (o.IsStop ? price<=o.Price1 : price>=o.Price1)
                              : (o.IsStop ? price>=o.Price1 : price<=o.Price1);
      if (!hit) continue;
      o.Status=SCT_OSC_FILLED; o.AvgFillPrice=o.Price1;
      NetQty += o.Action*o.Qty;
      if (NetQty==0.0) AvgPrice=0.0;
      for (size_t j=0;j<Orders.size();j++)
        if (Orders[j].ID==o.SiblingID && Orders[j].Status==SCT_OSC_OPEN)
          Orders[j].Status=SCT_OSC_CANCELED;
    }
    // Sierra Chart dokoncene ordery ze seznamu odklizi
    if (PurgeTerminalOrders){
      for (size_t i=0;i<Orders.size();i++)
        if (Orders[i].Status!=SCT_OSC_OPEN) Orders[i].TerminalAge++;
      std::vector<SimOrder> keep;
      for (size_t i=0;i<Orders.size();i++)
        if (Orders[i].Status==SCT_OSC_OPEN || Orders[i].TerminalAge<1) keep.push_back(Orders[i]);
      Orders.swap(keep);
    }
  }
};
typedef s_sc& SCStudyInterfaceRef;
