// Funkční mini-emulace ACSIL pro test logiky (ne úplné API)
#pragma once
#include <string>
#include <cstdio>
#include <cstdarg>
#include <vector>
#include <map>
#include <cmath>
#define SCDLLName(x)
#define SCSFExport extern "C" void
#define HMS_TIME(h,m,s) ((h)*3600+(m)*60+(s))
#define RGB(r,g,b) ((r)|((g)<<8)|((b)<<16))
enum {DRAWSTYLE_DASH,DRAWSTYLE_LINE,DRAWSTYLE_ARROW_UP,DRAWSTYLE_ARROW_DOWN};
enum {SCT_ORDERTYPE_MARKET}; enum {SCT_TIF_GOOD_TILL_CANCELED};
struct SCString{std::string s; SCString(){} SCString(const char*c):s(c){} SCString& operator=(const char*c){s=c;return *this;}
 int GetLength()const{return (int)s.size();} const char* GetChars()const{return s.c_str();}
 SCString& Format(const char*f,...){char b[1024];va_list a;va_start(a,f);vsnprintf(b,sizeof b,f,a);va_end(a);s=b;return *this;}
 operator const char*()const{return s.c_str();}};
struct SCInputRef_{const char* Name=""; double v=0; void SetYesNo(int x){v=x;} int GetYesNo(){return (int)v;} void SetCustomInputStrings(const char*){} void SetCustomInputIndex(int x){v=x;} int GetIndex(){return (int)v;}
 void SetInt(int x){v=x;} int GetInt(){return (int)v;} void SetIntLimits(int,int){} void SetFloat(float x){v=x;} float GetFloat(){return (float)v;} void SetFloatLimits(float,float){} void SetTime(int x){v=x;} int GetTime(){return (int)v;}};
typedef SCInputRef_& SCInputRef;
struct SCSubgraph_{const char*Name;int DrawStyle;unsigned PrimaryColor;bool DrawZeros;int LineWidth; std::vector<float> d; float& operator[](int i){if((int)d.size()<=i)d.resize(i+1);return d[i];}};
typedef SCSubgraph_& SCSubgraphRef;
struct SCDateTime{int dt=0,tm=0; int GetDate()const{return dt;} int GetTimeInSeconds()const{return tm;}};
struct Arr{std::vector<float> v; float operator[](int i)const{return v[i];}};
struct DTArr{std::vector<SCDateTime> v; SCDateTime operator[](int i)const{return v[i];}};
struct s_SCPositionData{double PositionQuantity=0; int WorkingOrdersExist=0;};
struct s_SCNewOrder{int OrderQuantity=0;int OrderType=0;int TimeInForce=0;double Stop1Offset=0;double Target1Offset=0;};
struct Trade{int d,t,dir; double e,x; int xd,xt; char why;};
struct SCStudyInterface{SCInputRef_ Input[64]; SCSubgraph_ Subgraph[60]; int SetDefaults=0; const char*GraphName;const char*StudyDescription;int AutoLoop,GraphRegion,FreeDLL;
 bool AllowMultipleEntriesInSameDirection,SupportReversals,SendOrdersToTradeService,AllowOppositeEntryWithOpposingPositionOrOrders,SupportAttachedOrdersForTrading,CancelAllOrdersOnEntriesAndReversals,AllowEntryWithWorkingOrders,CancelAllWorkingOrdersOnExit,AllowOnlyOneTradePerBar,MaintainTradeStatisticsAndTradesData;
 int MaximumPositionAllowed=0; float TickSize=0.25f; int Index=0, ArraySize=0, IsFullRecalculation=0; Arr Open,High,Low,Close; DTArr BaseDateTimeIn;
 std::map<int,float> pf; std::map<int,int> pi; int alerts=0, logs=0, errors=0;
 // simulovaný broker
 int pos=0; double sl=0,tp=0,ent=0; int ed=0,et=0; std::vector<Trade> trades;
 float& GetPersistentFloat(int k){return pf[k];} int& GetPersistentInt(int k){return pi[k];}
 void AddMessageToLog(const char*m,int e){logs++; if(e){errors++; if(errors<20) printf("LOG! %s\n",m);}}
 int SetAlert(int,const char*){alerts++;return 1;}
 float RoundToTickSize(float v,float t){return (float)(std::round(v/t)*t);}
 int GetTradePosition(s_SCPositionData&p){p.PositionQuantity=pos;p.WorkingOrdersExist=pos!=0;return 1;}
 void close(double px,char why){trades.push_back({ed,et,pos>0?1:-1,ent,px,BaseDateTimeIn[Index].dt,BaseDateTimeIn[Index].tm,why});pos=0;}
 double FlattenAndCancelAllOrders(){if(pos)close(Close[Index],'E');return 1;}
 double entry(s_SCNewOrder&o,int dir){if(pos!=0||o.OrderQuantity>MaximumPositionAllowed)return -1;pos=dir*o.OrderQuantity;ent=Close[Index];
   sl=ent-dir*o.Stop1Offset;tp=ent+dir*o.Target1Offset;ed=BaseDateTimeIn[Index].dt;et=BaseDateTimeIn[Index].tm;return 1;}
 double BuyEntry(s_SCNewOrder&o){return entry(o,1);} double SellEntry(s_SCNewOrder&o){return entry(o,-1);}
 const char* GetTradingErrorTextMessage(int){return "sim reject";}
 void bracket(int i){ if(!pos) return; bool L=pos>0; // SL první (pesimisticky)
   if(L? Low[i]<=sl : High[i]>=sl){close(sl,'S');return;} if(L? High[i]>=tp : Low[i]<=tp) close(tp,'T');}
};
typedef SCStudyInterface& SCStudyInterfaceRef;
