// Minimal ACSIL stub - ONLY for compile-checking Lukacino_MultiSwing.cpp off-line.
// It is not Sierra Chart and must never be shipped or linked against for real use.
#pragma once
#include <string>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <cctype>
#include <vector>
#include <map>
#include <utility>
#include <cmath>

// the real scstructures.h defines these as macros; reproduce that so std::max / std::min
// misuse fails in the offline build exactly as it does on Sierra's build server
#define max(a,b)            (((a) > (b)) ? (a) : (b))
#define min(a,b)            (((a) < (b)) ? (a) : (b))

#define SCDLLName(x)
#define SCSFExport extern "C" void
#define RGB(r,g,b) (((r)<<16)|((g)<<8)|(b))
#define HMS_TIME(h,m,s) ((h)*3600+(m)*60+(s))
enum { DRAWSTYLE_IGNORE, DRAWSTYLE_LINE, DRAWSTYLE_ARROW_UP };
enum { LOW_PREC_LEVEL };
enum { BHCS_BAR_HAS_CLOSED = 1, BHCS_BAR_HAS_NOT_CLOSED = 0 };
enum { SC_OPEN, SC_HIGH, SC_LOW, SC_LAST, SC_VOLUME, SC_BIDVOL, SC_ASKVOL, SC_NUM_ARRAYS };

struct SCString {
    std::string s;
    SCString() {}
    SCString(const char* p) : s(p ? p : "") {}
    int GetLength() const { return (int)s.size(); }
    char operator[](int i) const { return s[i]; }
    const char* GetChars() const { return s.c_str(); }
    SCString& operator+=(char c) { s += c; return *this; }
    SCString& operator+=(const SCString& o) { s += o.s; return *this; }
    SCString operator+(const SCString& o) const { SCString r; r.s = s + o.s; return r; }
    SCString operator+(const char* o) const { SCString r; r.s = s + o; return r; }
    bool operator==(const SCString& o) const { return s == o.s; }
    bool operator==(const char* o) const { return s == o; }
    int IndexOf(char c) const { size_t p = s.find(c); return p == std::string::npos ? -1 : (int)p; }
    void Format(const char* fmt, ...) { char buf[4096]; va_list a; va_start(a, fmt);
        vsnprintf(buf, sizeof(buf), fmt, a); va_end(a); s = buf; }
    SCString& operator=(const char* p) { s = p ? p : ""; return *this; }
};


// proper civil-date conversion so week/month/quarter keys behave like the real SCDateTime
inline void CivilFromDays(int z, int& y, unsigned& m, unsigned& d)
{
    z += 719468;
    int era = (z >= 0 ? z : z - 146096) / 146097;
    unsigned doe = (unsigned)(z - era * 146097);
    unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int yy = (int)yoe + era * 400;
    unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    unsigned mp = (5 * doy + 2) / 153;
    d = doy - (153 * mp + 2) / 5 + 1;
    m = mp + (mp < 10 ? 3 : -9);
    y = yy + (m <= 2);
}
enum { SCT_ORDERTYPE_MARKET = 1, SCT_ORDERTYPE_LIMIT = 2, SCT_ORDERTYPE_STOP = 3,
       SCT_TIF_DAY = 1, SCT_TIF_GTC = 2,
       SCT_OSC_FILLED = 1, SCT_OSC_CANCELED = 2, SCT_OSC_OPEN = 3 };
enum { DRAWING_TEXT = 1, DRAWING_STATIONARY_TEXT = 2, UTAM_ADD_OR_ADJUST = 1,
       TOOL_DELETE_CHARTDRAWING = 1 };
typedef unsigned long COLORREF;
#ifndef RGB
#define RGB(r, g, b) ((COLORREF)(((unsigned char)(r)) | ((unsigned char)(g) << 8) | ((unsigned char)(b) << 16)))
#endif
// Chart drawings have no meaning off-line; the tool is accepted and dropped so the study's
// display code still compiles and runs in the parity harness.
struct s_UseTool {
    int ChartNumber = 0, DrawingType = 0, Region = 0, AddMethod = 0, LineNumber = 0;
    int UseRelativeVerticalValues = 0, FontSize = 0, FontBold = 0, MultiLineLabel = 0;
    int TransparentLabelBackground = 0, BeginIndex = 0;
    double BeginDateTime = 0, BeginValue = 0;
    SCString Text;
    COLORREF Color = 0, SecondaryColor = 0;
    void Clear() { *this = s_UseTool(); }
};
struct s_SCNewOrder {
    int OrderQuantity = 0, OrderType = 0, TimeInForce = 0, InternalOrderID = 0;
    double Price1 = 0, Price2 = 0;
    // Sierra's own bracket: the stop and target ride with the entry and Sierra manages them.
    double Target1Price = 0, Stop1Price = 0;
    int    AttachedOrderTarget1Type = 0, AttachedOrderStop1Type = 0;
};
struct s_SCTradeOrder { int InternalOrderID = 0, OrderStatusCode = 0, OrderQuantity = 0; double Price1 = 0; };
struct s_SCPositionData { double PositionQuantity = 0; double AveragePrice = 0; };

// Sierra counts days from 1899-12-30, a Saturday. The stub used to count from the Unix epoch, a
// Thursday, and that two-day gap hid a real bug: a weekly anchor derived by arithmetic on the day
// number landed on Monday here and on Wednesday in Sierra, so the off-line run was right while
// every live and replayed bar was wrong. The stub now uses Sierra's epoch, so an epoch assumption
// in the study shows up in the parity run instead of waiting for a Replay to expose it.
enum { SC_EPOCH_TO_UNIX_DAYS = 25569 };   // 1899-12-30 -> 1970-01-01

struct SCDateTime {
    int days = 0; int secs = 0;
    int GetDate() const { return days; }
    int GetTimeInSeconds() const { return secs; }
    void SetDate(int d) { days = d; }
    int GetYear() const { int y; unsigned m, d; CivilFromDays(days - SC_EPOCH_TO_UNIX_DAYS, y, m, d); return y; }
    int GetMonth() const { int y; unsigned m, d; CivilFromDays(days - SC_EPOCH_TO_UNIX_DAYS, y, m, d); return (int)m; }
    int GetDay() const { int y; unsigned m, d; CivilFromDays(days - SC_EPOCH_TO_UNIX_DAYS, y, m, d); return (int)d; }
    int GetDayOfWeek() const { return (days + 6) % 7; }   // 0 = Sunday (1899-12-30 was a Saturday)
};

struct SCFloatArray {
    std::vector<float> v;
    float& operator[](int i) { if ((int)v.size() <= i) v.resize(i + 1, 0.f); return v[i]; }
    const float operator[](int i) const { return i < (int)v.size() ? v[i] : 0.f; }
};
struct SCBaseDataArray { SCFloatArray a[SC_NUM_ARRAYS];
    SCFloatArray& operator[](int i) { return a[i]; } };
struct SCDateTimeArray { std::vector<SCDateTime> v;
    SCDateTime& operator[](int i) { if ((int)v.size() <= i) v.resize(i + 1); return v[i]; } };

struct SCSubgraph { SCString Name; int DrawStyle = 0, LineWidth = 0; unsigned PrimaryColor = 0;
    SCFloatArray Data;
    float& operator[](int i) { return Data[i]; } };
typedef SCSubgraph& SCSubgraphRef;

struct SCInput {
    SCString Name; SCString str; int i = 0; float f = 0; int yesno = 0; int idx = 0; int t = 0;
    void SetYesNo(int v) { yesno = v; }   int GetYesNo() const { return yesno; }
    void SetInt(int v) { i = v; }         int GetInt() const { return i; }
    void SetFloat(float v) { f = v; }     float GetFloat() const { return f; }
    void SetString(const char* v) { str = v; } SCString GetString() const { return str; }
    void SetCustomInputStrings(const char*) {}
    void SetCustomInputIndex(int v) { idx = v; } int GetIndex() const { return idx; }
    void SetTime(int v) { t = v; }        int GetTime() const { return t; }
};
typedef SCInput& SCInputRef;

struct SCStudyInterface {
    int SetDefaults = 0, AutoLoop = 0, GraphRegion = 0, FreeDLL = 0, CalculationPrecedence = 0;
    int MaintainAdditionalChartDataArrays = 0, LastCallToFunction = 0;
    int UpdateStartIndex = 0, ArraySize = 0, SecondsPerBar = 60;
    SCString GraphName, StudyDescription;
    SCSubgraph Subgraph[64];
    SCInput Input[128];
    SCBaseDataArray BaseData;
    SCDateTimeArray BaseDateTimeIn;
    void* persistentPtr = nullptr; int persistentInt[8] = {0};
    void* GetPersistentPointer(int) { return persistentPtr; }
    void SetPersistentPointer(int, void* p) { persistentPtr = p; }
    int GetPersistentInt(int k) { return persistentInt[k]; }
    void SetPersistentInt(int k, int v) { persistentInt[k] = v; }
    SCDateTime CurrentSystemDateTime;
    // the off-line harness is never a replay; the study must still not depend on the wall clock
    int IsReplayRunning() { return 0; }

    // Trading API. Two behaviours, chosen by the STUB_ORDERS environment variable:
    //
    //   refuse (default) - every order comes back -1, which is what the parity run wants: the
    //                      back-test must stay a paper run, and the rejection paths get exercised.
    //   sim              - a small order book that enforces the same three rules Sierra documents
    //                      for a study's orders: MaximumPositionAllowed, AllowEntryWithWorkingOrders
    //                      and CancelAllOrdersOnEntriesAndReversals, and that keeps each entry's
    //                      attached stop and target so GetAttachedOrderIDsForParentOrder and
    //                      ModifyOrder mean something.
    //
    // 'sim' tests THIS study against Sierra's contract, not Sierra itself. It cannot prove what
    // Sierra does; it can prove that the study never asks for something the contract forbids -
    // that it does not trim more than the surplus, does not leave a preset's stop unmoved, and
    // does not depend on orders being cancelled behind its back. Those were all unanswerable from
    // the code before, and every one of them is a way to end up holding an unprotected book.
    int  SendOrdersToTradeService = 0;
    int  AllowMultipleEntriesInSameDirection = 0;
    int  SupportReversals = 0;
    int  AllowOnlyOneTradePerBar = 0;
    int  MaximumPositionAllowed = 0;
    int  SupportAttachedOrdersForTrading = 0;
    int  AllowEntryWithWorkingOrders = 0;
    int  CancelAllOrdersOnEntriesAndReversals = 0;
    int  ordersAttempted = 0;

    struct StubOrder { int id = 0, parent = 0, qty = 0; double price = 0; bool isStop = false; };
    bool   stubSim = getenv("STUB_ORDERS") && strncmp(getenv("STUB_ORDERS"), "sim", 3) == 0;
    // STUB_ORDERS=sim_noexit reproduces the one asymmetry that actually happened on a chart:
    // entries accepted, every exit refused. It is the state in which a book that squares its
    // position after adding to it ratchets upward and never comes back down.
    bool   stubRefuseExits = getenv("STUB_ORDERS")
                           && strcmp(getenv("STUB_ORDERS"), "sim_noexit") == 0;
    int    nextOrderId = 1;
    double stubPosition = 0;
    std::map<int, StubOrder> working;          // attached stops and targets still live
    std::map<int, std::pair<int,int> > bracket; // parent -> (targetId, stopId)
    // counters the harness prints; every one of them was a question I could not answer before
    int    entriesOk = 0, entriesRefused = 0, refusedByWorkingOrders = 0, refusedByMaxPosition = 0;
    int    trimsOk = 0, trimQtyTotal = 0, trimOverSurplus = 0;
    int    stopMovesOk = 0, stopMovesOnDeadOrder = 0, cancelledByTrim = 0;
    double stubPeakPosition = 0;

    void GetTradePosition(s_SCPositionData& p)
    { p = s_SCPositionData(); p.PositionQuantity = stubSim ? stubPosition : 0; }
    int  ChartNumber = 1;
    double TickSize = 0.25;
    void UseTool(const s_UseTool&) {}
    void DeleteACSChartDrawing(int, int, int) {}

    int  BuyEntry(s_SCNewOrder& o)
    {
        ++ordersAttempted;
        if (!stubSim) return -1;
        if (!AllowEntryWithWorkingOrders && !working.empty()) {
            ++entriesRefused; ++refusedByWorkingOrders; return -1;
        }
        if (MaximumPositionAllowed > 0 && stubPosition + o.OrderQuantity > MaximumPositionAllowed) {
            ++entriesRefused; ++refusedByMaxPosition; return -1;
        }
        const int id = nextOrderId++;
        o.InternalOrderID = id;
        stubPosition += o.OrderQuantity;
        if (stubPosition > stubPeakPosition) stubPeakPosition = stubPosition;
        int targetId = 0, stopId = 0;
        if (o.Target1Price != 0) {
            targetId = nextOrderId++;
            StubOrder t; t.id = targetId; t.parent = id; t.qty = o.OrderQuantity;
            t.price = o.Target1Price; t.isStop = false; working[targetId] = t;
        }
        if (o.Stop1Price != 0) {
            stopId = nextOrderId++;
            StubOrder t; t.id = stopId; t.parent = id; t.qty = o.OrderQuantity;
            t.price = o.Stop1Price; t.isStop = true; working[stopId] = t;
        }
        bracket[id] = std::make_pair(targetId, stopId);
        ++entriesOk;
        return id;
    }

    int  SellExit(s_SCNewOrder& o)
    {
        ++ordersAttempted;
        if (!stubSim) return -1;
        if (stubRefuseExits) return -1;
        if (o.OrderQuantity > stubPosition) ++trimOverSurplus;   // would sell what is not held
        stubPosition -= o.OrderQuantity;
        if (stubPosition < 0) stubPosition = 0;
        if (CancelAllOrdersOnEntriesAndReversals) {
            cancelledByTrim += (int)working.size();
            working.clear();
            bracket.clear();
        }
        ++trimsOk; trimQtyTotal += o.OrderQuantity;
        o.InternalOrderID = nextOrderId++;
        return o.InternalOrderID;
    }

    int  ModifyOrder(s_SCNewOrder& o)
    {
        if (!stubSim) return -1;
        std::map<int, StubOrder>::iterator it = working.find(o.InternalOrderID);
        if (it == working.end()) { ++stopMovesOnDeadOrder; return -1; }
        it->second.price = o.Price1;
        ++stopMovesOk;
        return 1;
    }

    int  cancelsOk = 0, cancelsOnDeadOrder = 0;
    int  CancelOrder(int id)
    {
        if (!stubSim) return -1;
        std::map<int, StubOrder>::iterator it = working.find(id);
        if (it == working.end()) { ++cancelsOnDeadOrder; return -1; }
        working.erase(it);
        ++cancelsOk;
        return 1;
    }
    int  GetOrderByOrderID(int, s_SCTradeOrder&) { return 0; }   // 0 = no such order
    // Signature copied from the real sierrachart.h (void, int parent, two int out-params).
    void GetAttachedOrderIDsForParentOrder(int parent, int& r_TargetInternalOrderID, int& r_StopInternalOrderID)
    {
        r_TargetInternalOrderID = 0; r_StopInternalOrderID = 0;
        if (!stubSim) return;
        std::map<int, std::pair<int,int> >::iterator it = bracket.find(parent);
        if (it == bracket.end()) return;
        if (working.count(it->second.first))  r_TargetInternalOrderID = it->second.first;
        if (working.count(it->second.second)) r_StopInternalOrderID  = it->second.second;
    }
    void AddMessageToLog(const SCString& m, int) { fprintf(stderr, "LOG: %s\n", m.GetChars()); }
    SCString DataFilesFolder() { return SCString("."); }
    int GetBarHasClosedStatus(int) { return BHCS_BAR_HAS_CLOSED; }
};
typedef SCStudyInterface& SCStudyInterfaceRef;
