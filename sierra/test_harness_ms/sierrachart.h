// Funkční mini-emulace ACSIL pro test studie Lukacino Multi-System (ne úplné API).
// Broker: market příkaz = fill na Open aktuálního baru (první tick po odeslání),
// stop příkaz = čeká, vyplní se na dalším baru, kde low/high protne cenu (gap = Open).
#pragma once
#include <cstdlib>
#include <string>
#include <cstdio>
#include <cstdarg>
#include <vector>
#include <map>
#include <cmath>
#include <algorithm>
#define SCDLLName(x)
#define SCSFExport extern "C" void
#define HMS_TIME(h,m,s) ((h)*3600+(m)*60+(s))
#define RGB(r,g,b) ((r)|((g)<<8)|((b)<<16))
enum {DRAWSTYLE_DASH,DRAWSTYLE_LINE,DRAWSTYLE_ARROW_UP,DRAWSTYLE_ARROW_DOWN,DRAWSTYLE_POINT,DRAWSTYLE_HIDDEN};
enum {SCT_ORDERTYPE_MARKET=0, SCT_ORDERTYPE_STOP=2}; enum {SCT_TIF_GOOD_TILL_CANCELED=2};
enum {SCT_OSC_OPEN=1, SCT_OSC_FILLED=2, SCT_OSC_CANCELED=3, SCT_OSC_ERROR=4};
enum {DRAWING_TEXT=10, UTAM_ADD_OR_ADJUST=1, TOOL_DELETE_CHARTDRAWING=1};
enum {DT_LEFT=0, DT_TOP=0, DT_RIGHT=2, DT_BOTTOM=8};
struct SCString{std::string s; SCString(){} SCString(const char*c):s(c){} SCString& operator=(const char*c){s=c;return *this;}
 int GetLength()const{return (int)s.size();} const char* GetChars()const{return s.c_str();}
 SCString& Format(const char*f,...){char b[4096];va_list a;va_start(a,f);vsnprintf(b,sizeof b,f,a);va_end(a);s=b;return *this;}
 SCString& operator+=(const SCString&o){s+=o.s;return *this;} operator const char*()const{return s.c_str();}};
struct SCInputRef_{const char* Name=""; double v=0; void SetYesNo(int x){v=x;} int GetYesNo(){return (int)v;} void SetCustomInputStrings(const char*){} void SetCustomInputIndex(int x){v=x;} int GetIndex(){return (int)v;}
 void SetInt(int x){v=x;} int GetInt(){return (int)v;} void SetIntLimits(int,int){} void SetFloat(float x){v=x;} float GetFloat(){return (float)v;} void SetFloatLimits(float,float){} void SetTime(int x){v=x;} int GetTime(){return (int)v;}};
typedef SCInputRef_& SCInputRef;
struct SCSubgraph_{const char*Name;int DrawStyle;unsigned PrimaryColor;bool DrawZeros;int LineWidth; std::vector<float> d; float& operator[](int i){if((int)d.size()<=i)d.resize(i+1,0);return d[i];}};
typedef SCSubgraph_& SCSubgraphRef;
struct SCDateTime{int dt=0,tm=0; int GetDate()const{return dt;} int GetTimeInSeconds()const{return tm;}};
struct Arr{std::vector<float> v; float operator[](int i)const{return v[i];}};
struct DTArr{std::vector<SCDateTime> v; SCDateTime operator[](int i)const{return v[i];}};
struct s_SCPositionData{double PositionQuantity=0; int WorkingOrdersExist=0;};
struct s_SCNewOrder{int OrderQuantity=0;int OrderType=0;int TimeInForce=0;double Price1=0;SCString TextTag;int InternalOrderID=0;};
struct s_SCTradeOrder{int InternalOrderID=0;int OrderStatusCode=0;double AvgFillPrice=0;double Price1=0;int OrderQuantity=0;};
struct s_UseTool{int ChartNumber,DrawingType,LineNumber,AddMethod,BeginIndex,UseRelativeVerticalValues,Region,FontSize,TransparentLabelBackground; float BeginValue; unsigned Color,FontBackColor,TextAlignment; SCString FontFace,Text; void Clear(){}};
struct Fill{int d,t,side,qty; double px; std::string tag;};
struct SCStudyInterface{
 SCInputRef_ Input[128]; SCSubgraph_ Subgraph[60]; int SetDefaults=0,LastCallToFunction=0; const char*GraphName;const char*StudyDescription;int AutoLoop,GraphRegion=0,FreeDLL,ChartNumber=1;
 bool AllowMultipleEntriesInSameDirection,SupportReversals,SendOrdersToTradeService,AllowOppositeEntryWithOpposingPositionOrOrders,SupportAttachedOrdersForTrading,CancelAllOrdersOnEntriesAndReversals,AllowEntryWithWorkingOrders,CancelAllWorkingOrdersOnExit,AllowOnlyOneTradePerBar,MaintainTradeStatisticsAndTradesData;
 int MaximumPositionAllowed=0; float TickSize=0.25f; double CurrencyValuePerTick=12.5; int Index=0, ArraySize=0, IsFullRecalculation=0, IndexOfFirstVisibleBar=0, IndexOfLastVisibleBar=0;
 Arr Open,High,Low,Close,Volume,AskVolume,BidVolume; DTArr BaseDateTimeIn;
 void* pp[10]={0}; void* GetPersistentPointer(int k){return pp[k];} void SetPersistentPointer(int k,void*p){pp[k]=p;}
 std::vector<std::string> trades; int alerts=0, logs=0, errors=0; std::string lastPanel;
 void AddMessageToLog(const char*m,int e){logs++; std::string s(m); if(s.rfind("TRADE|",0)==0){trades.push_back(s);return;} if(e){errors++; if(errors<30) printf("LOG! %s\n",m);} else if(getenv("VERBOSE")) printf("log %s\n",m);}
 int SetAlert(int,const char*){alerts++;return 1;}
 float RoundToTickSize(float v,float t){return (float)(std::round(v/t)*t);}
 int UseTool(s_UseTool&t){lastPanel=t.Text.s;return 1;} int DeleteACSChartDrawing(int,int,int){lastPanel="";return 1;}
 // ---- broker
 int pos=getenv("START_POS")?atoi(getenv("START_POS")):0; double avg=0, realized=0; std::vector<Fill> fills; std::map<int,s_SCTradeOrder> orders; std::map<int,int> stopSide; int nextId=1, rejects=0;
 void fill(int side,int q,double px,const char*tag){ // side +1 buy, -1 sell
   int np=pos+side*q;
   if(pos==0||(pos>0)==(side>0)){ avg=(avg*std::abs(pos)+px*q)/std::abs(np); }
   else { int closed=std::min(q,std::abs(pos)); realized+=closed*(px-avg)*(pos>0?1:-1)*50.0/50.0; if(std::abs(np)>0&&(np>0)!=(pos>0)) avg=px; }
   pos=np; if(pos==0) avg=0; fills.push_back({BaseDateTimeIn[Index].dt,BaseDateTimeIn[Index].tm,side,q,px,tag}); }
 int market(s_SCNewOrder&o,int side,bool exit){ if(o.OrderQuantity<=0) {rejects++;return -1;}
   if(exit && (pos==0 || (pos>0)==(side>0) || o.OrderQuantity>std::abs(pos))) {rejects++;return -2;}
   if(exit && getenv("STRICT_EXIT")){ int w=0; for(auto&kv:orders) if(kv.second.OrderStatusCode==SCT_OSC_OPEN && stopSide[kv.first]==side) w+=kv.second.OrderQuantity;
     if(w+o.OrderQuantity>std::abs(pos)) {rejects++;return -4;} } // Sierra: exit + working exit orders nesmí překročit pozici
   if(!exit && std::abs(pos+side*o.OrderQuantity)>MaximumPositionAllowed) {rejects++;return -3;}
   int id=nextId++; o.InternalOrderID=id;
   if(o.OrderType==SCT_ORDERTYPE_STOP){ s_SCTradeOrder t; t.InternalOrderID=id; t.OrderStatusCode=SCT_OSC_OPEN; t.Price1=o.Price1; t.OrderQuantity=o.OrderQuantity; orders[id]=t; stopSide[id]=side; return 1;}
   fill(side,o.OrderQuantity,Open[Index],"mkt"); s_SCTradeOrder t; t.InternalOrderID=id; t.OrderStatusCode=SCT_OSC_FILLED; t.AvgFillPrice=Open[Index]; orders[id]=t; return 1;}
 double BuyEntry(s_SCNewOrder&o){return market(o,1,false);} double SellEntry(s_SCNewOrder&o){return market(o,-1,false);}
 double BuyExit(s_SCNewOrder&o){return market(o,1,true);} double SellExit(s_SCNewOrder&o){return market(o,-1,true);}
 double BuyOrder(s_SCNewOrder&o){ if(getenv("NO_EXIT")) return 0; return market(o,1,false);} double SellOrder(s_SCNewOrder&o){ if(getenv("NO_EXIT")) return 0; return market(o,-1,false);}
 int CancelOrder(int id){ if(orders.count(id)&&orders[id].OrderStatusCode==SCT_OSC_OPEN) orders[id].OrderStatusCode=SCT_OSC_CANCELED; return 1;}
 int GetOrderByOrderID(int id,s_SCTradeOrder&o){ if(!orders.count(id)) return 0; o=orders[id]; return 1;}
 int GetTradePosition(s_SCPositionData&p){p.PositionQuantity=pos; p.WorkingOrdersExist=0; for(auto&kv:orders) if(kv.second.OrderStatusCode==SCT_OSC_OPEN) p.WorkingOrdersExist=1; return 1;}
 const char* GetTradingErrorTextMessage(int){return "sim reject";}
 void checkStops(int i){ for(auto&kv:orders){ s_SCTradeOrder&t=kv.second; if(t.OrderStatusCode!=SCT_OSC_OPEN) continue; int side=stopSide[kv.first];
     bool hit= side<0 ? Low[i]<=t.Price1 : High[i]>=t.Price1; if(!hit) continue;
     double px= side<0 ? std::min((double)Open[i],t.Price1) : std::max((double)Open[i],t.Price1);
     int q=std::min(t.OrderQuantity,std::abs(pos)); if(q<=0||(pos>0)==(side>0)){t.OrderStatusCode=SCT_OSC_CANCELED;continue;}
     int save=Index; Index=i; fill(side,q,px,"stop"); Index=save; t.OrderStatusCode=SCT_OSC_FILLED; t.AvgFillPrice=px; } }
};
typedef SCStudyInterface& SCStudyInterfaceRef;
