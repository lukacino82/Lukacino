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
       SCT_TIF_DAY = 1, SCT_TIF_GTC = 2, SCT_TIF_GOOD_TILL_CANCELED = 2,
       SCT_OSC_FILLED = 1, SCT_OSC_CANCELED = 2, SCT_OSC_OPEN = 3, SCT_OSC_ERROR = 4 };
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
    // Sierra's own bracket, in the two forms scstructures.h actually offers: an absolute price or
    // an offset from the fill. Confirmed by findstr against the real header, lines 1190-1198.
    double Target1Price = 0, Stop1Price = 0;
    double Target1Offset = 0, Stop1Offset = 0;
    // The label Sierra shows next to the order in Trade Activity. Costs nothing and is the only
    // way to tell this study's orders from anything else on the same account.
    SCString TextTag;
};
// There is NO attached-order "type" field and no SCAttachedOrderTypeEnum. findstr for
// ATTACHEDORDER across scstructures.h and scconstants.h matched nothing at all, and
// scstructures.h:1353-1356 shows how Sierra decides an order has attached orders:
//
//     return Target1Offset != 0.0 || Stop1Offset != 0.0
//         || Target1Price  != 0.0 || Stop1Price  != 0.0;
//
// Setting Stop1Price alone is therefore the correct and complete way to ask for a protective
// stop. The earlier theory that a missing type was behind the refusals is dead, and the fields
// this stub briefly carried for it never existed in Sierra - they are gone, because a stub that
// invents members hides exactly the mistake that made them up.
struct s_SCTradeOrder { int InternalOrderID = 0, OrderStatusCode = 0, OrderQuantity = 0; double Price1 = 0, AvgFillPrice = 0; };
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
    // Real ACSIL clamps the dialog to these; nothing here needs the clamp, but a study that sets
    // limits must compile against the stub too.
    void SetFloatLimits(float, float) {}
    void SetIntLimits(int, int) {}
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

    // Sierra's trade-service gate, which this stub did not have and which is why a replay that
    // produced 805 refusals produced none here. Sierra requires SendOrdersToTradeService to AGREE
    // with Trade > Trade Simulation Mode: with simulation mode on and the flag set, it throws the
    // order away before reading it and answers the generic -1, writing the reason to the Trade
    // Service Log alone:
    //
    //     SendOrdersToTradeService is not consistent with 'Trade >> Trade Simulation Mode On'
    //     setting.  Order action ignored.  SendOrdersToTradeService=1,  TradeSimulationModeOn=1
    //
    // STUB_SIM_MODE_ON=1 turns the global simulation mode on in this stub, so the study's recovery
    // from that collision can be measured here instead of in a replay. It is checked before every
    // other reason an order can be refused, because Sierra checks it before anything else - that
    // ordering is the whole point: with the flag set, no property of the order matters.
    bool stubSimModeOn = getenv("STUB_SIM_MODE_ON") && atoi(getenv("STUB_SIM_MODE_ON")) == 1;
    int  tradeServiceIgnored = 0;        // orders discarded at that gate
    bool TradeServiceInconsistent()
    {
        if (!stubSimModeOn || SendOrdersToTradeService == 0) return false;
        ++tradeServiceIgnored;
        return true;
    }
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
    // STUB_ORDERS=sim_nomodify is the chart's own simulation as his Message Log showed it:
    // entries accepted with their brackets, but ModifyOrder and CancelOrder both refused, so a
    // bracket can be neither steered nor cancelled and the contracts can only leave when Sierra
    // itself fills a child. It is the state in which a study that retries every call buries the
    // log - thousands of identical lines a second at replay speed.
    bool   stubRefuseModify = getenv("STUB_ORDERS")
                            && strcmp(getenv("STUB_ORDERS"), "sim_nomodify") == 0;
    // on by default in sim: it is what Sierra does. STUB_COVERAGE=0 turns it off to show the
    // difference a design makes.
    bool   enforceCoverage = !(getenv("STUB_COVERAGE") && atoi(getenv("STUB_COVERAGE")) == 0);
    int    nextOrderId = 1;
    // STUB_START_POS=<n> starts the account already holding contracts nobody in this run placed,
    // which is exactly the state a reload or a Sierra restart leaves behind.
    double stubPosition = getenv("STUB_START_POS") ? atof(getenv("STUB_START_POS")) : 0;
    std::map<int, StubOrder> working;          // attached stops and targets still live
    std::map<int, std::pair<int,int> > bracket; // parent -> (targetId, stopId)
    // counters the harness prints; every one of them was a question I could not answer before
    int    entriesOk = 0, entriesRefused = 0, refusedByWorkingOrders = 0, refusedByMaxPosition = 0;
    int    bracketedRefused = 0, bareOk = 0;
    int    trimsOk = 0, trimQtyTotal = 0, trimOverSurplus = 0;
    int    stopMovesOk = 0, stopMovesOnDeadOrder = 0, cancelledByTrim = 0;
    double stubPeakPosition = 0;

    // STUB_BRACKETS_FILL_AFTER=<n> models the one failure his chart hit and nothing else could
    // reproduce: after n study calls every bracket has filled on its own, so the account is FLAT
    // and every bracket child is gone - while the study still holds legs it was refused
    // permission to steer. That is the state behind "book 9 contracts position 0".
    long stubFillAfter = getenv("STUB_BRACKETS_FILL_AFTER")
                       ? atol(getenv("STUB_BRACKETS_FILL_AFTER")) : -1;
    long stubCalls = 0;
    bool BracketsAllGone() const { return stubFillAfter >= 0 && stubCalls > stubFillAfter; }

    // STUB_POS_ZERO_AFTER=<n> is the nastier half, and the one that matches his log exactly: the
    // position goes to zero while Sierra still reports the bracket children as live. The study
    // then cannot resolve the leg through RETIRE_ALREADY, its steer is refused, and it ends up
    // claiming contracts the account does not have - "book 9 contracts position 0" - forever.
    long stubZeroAfter = getenv("STUB_POS_ZERO_AFTER")
                       ? atol(getenv("STUB_POS_ZERO_AFTER")) : -1;
    bool PositionZeroed() const { return stubZeroAfter >= 0 && stubCalls > stubZeroAfter; }

    void GetTradePosition(s_SCPositionData& p)
    {
        p = s_SCPositionData();
        p.PositionQuantity = (stubSim && !BracketsAllGone() && !PositionZeroed())
                           ? stubPosition : 0;
    }
    int  ChartNumber = 1;
    double TickSize = 0.25;
    void UseTool(const s_UseTool&) {}
    void DeleteACSChartDrawing(int, int, int) {}

    // STUB_REFUSE_ENTRY_AFTER=<n> accepts n entries and then refuses every later one with -1,
    // leaving the account FLAT while the study's book believes it holds contracts. That is the
    // exact state his chart reached - "book 10 contracts position 0" under STOPPED - and the only
    // way to measure whether the latch heals itself out of it.
    long stubEntryBudget = getenv("STUB_REFUSE_ENTRY_AFTER")
                         ? atol(getenv("STUB_REFUSE_ENTRY_AFTER")) : -1;
    long stubEntriesTaken = 0;

    int  BuyEntry(s_SCNewOrder& o)
    {
        ++ordersAttempted;
        if (TradeServiceInconsistent()) return -1;
        if (!stubSim) return -1;
        if (stubEntryBudget >= 0 && stubEntriesTaken >= stubEntryBudget) {
            ++entriesRefused; return -1;
        }
        ++stubEntriesTaken;
        if (!AllowEntryWithWorkingOrders && !working.empty()) {
            ++entriesRefused; ++refusedByWorkingOrders; return -1;
        }
        if (MaximumPositionAllowed > 0 && stubPosition + o.OrderQuantity > MaximumPositionAllowed) {
            ++entriesRefused; ++refusedByMaxPosition; return -1;
        }
        // STUB_REFUSE_PRICE_BRACKET=1 refuses an entry whose bracket is given as absolute prices
        // and accepts the same entry given as offsets. It models the one thing his chart might be
        // doing - every price-form entry refused with a bare -1 - so the retry path can be
        // measured rather than hoped for.
        static const bool refusePriceBracket =
            getenv("STUB_REFUSE_PRICE_BRACKET") && atoi(getenv("STUB_REFUSE_PRICE_BRACKET")) == 1;
        if (refusePriceBracket && (o.Stop1Price != 0 || o.Target1Price != 0)) {
            ++entriesRefused; return -1;
        }
        // STUB_REFUSE_ANY_BRACKET=1 refuses an entry carrying a bracket in EITHER form and accepts
        // the same entry bare. It models what his replay actually did: 805 refusals, both
        // bracketed forms, Sierra's own words saying only "General order error", and not one
        // trade. Without it the bare fallback cannot be measured at all, because this stub takes
        // every bracket it is offered.
        static const bool refuseAnyBracket =
            getenv("STUB_REFUSE_ANY_BRACKET") && atoi(getenv("STUB_REFUSE_ANY_BRACKET")) == 1;
        if (refuseAnyBracket && (o.Stop1Price != 0 || o.Target1Price != 0
                              || o.Stop1Offset != 0 || o.Target1Offset != 0)) {
            ++entriesRefused; ++bracketedRefused; return -1;
        }

        const int id = nextOrderId++;
        o.InternalOrderID = id;
        // A market entry is filled the moment it is accepted, so it is recorded as finished at
        // the price the study last saw. Without this the parent order is in neither `working` nor
        // `finished` and GetOrderByOrderID answers "no such order" for an order that certainly
        // exists - which is how a study asking for its own fill price gets nothing back.
        stubPosition += o.OrderQuantity;
        if (stubPosition > stubPeakPosition) stubPeakPosition = stubPosition;

        // An offset bracket is the same bracket measured from the fill. The stub fills a market
        // order at the price the study last saw, which is what stubLast carries.
        const double fill = (ArraySize > 0) ? (double)BaseData[SC_LAST][ArraySize - 1] : 0.0;
        if (o.Target1Price == 0 && o.Target1Offset != 0) o.Target1Price = fill + o.Target1Offset;
        if (o.Stop1Price   == 0 && o.Stop1Offset   != 0) o.Stop1Price   = fill - o.Stop1Offset;

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
        finished[id] = SCT_OSC_FILLED;
        lastFillPrice = fill;
        if (targetId == 0 && stopId == 0) ++bareOk;   // nothing attached: a naked long
        ++entriesOk;
        return id;
    }

    // STUB_FILL_DELAY=<calls> accepts the exit but only reduces the position that many calls
    // later, which is what a Replay running faster than fills settle looks like. Without it every
    // fill is instant and the "sold the same surplus twice" bug cannot be reproduced offline.
    int    stubFillDelay = getenv("STUB_FILL_DELAY") ? atoi(getenv("STUB_FILL_DELAY")) : 0;
    // One entry per sell still in flight, each with its own countdown. Lumping them into a single
    // quantity and a single countdown was wrong in the one case the delay exists to model: a second
    // sell restarted the clock, so a chart that sold on every call never settled at all and the
    // position ran to the cap no matter what the study did. That was the stub, not the study.
    std::vector<std::pair<int,int> > pendingSells;   // qty, calls remaining
    int    pendingSellQty = 0;
    int    oversoldEvents = 0;
    double minPositionSeen = 1e9;
    void StubTick(int want)
    {
        ++stubCalls;
        if (!stubSim) return;
        for (size_t i = 0; i < pendingSells.size(); ) {
            if (--pendingSells[i].second <= 0) {
                stubPosition -= pendingSells[i].first;
                if (stubPosition < 0) stubPosition = 0;
                pendingSellQty -= pendingSells[i].first;
                pendingSells.erase(pendingSells.begin() + i);
            } else ++i;
        }
        if (pendingSellQty < 0) pendingSellQty = 0;
        // A resting protective stop (parent 0) fills when the market trades down to it. Every
        // contract it holds leaves the account at once - which is the point of it - and the
        // bracket children it was sitting underneath are left alone here deliberately: whether
        // they then fire too, and take the account short, is the real risk of running one of
        // these under forty-eight brackets, and a stub that quietly tidied them away would hide
        // exactly that.
        for (std::map<int, StubOrder>::iterator it = working.begin(); it != working.end(); ) {
            if (it->second.parent != 0 || !it->second.isStop) { ++it; continue; }
            if (stubLast <= 0 || stubLast > it->second.price) { ++it; continue; }
            stubPosition -= it->second.qty;
            if (stubPosition < 0) stubPosition = 0;
            finished[it->first] = SCT_OSC_FILLED;
            lastFillPrice = it->second.price;
            ++emergFills;
            std::map<int, StubOrder>::iterator dead = it++;
            working.erase(dead);
        }
        if (stubPosition < minPositionSeen) minPositionSeen = stubPosition;
        if (stubPosition < want) ++oversoldEvents;   // the book wanted more than is held
    }

    // Sierra's actual rule, quoted from a Trade Activity Log: "SellExit signal is ignored ... there
    // are already working exit orders that will flatten the position. Current Position with working
    // exit orders: 0." A market sell is refused for any contract already covered by a working stop
    // or target. The stub enforces exactly that, so the offline run can no longer pass a design
    // that only works because the stub was more permissive than Sierra.
    int  exitsRefusedAsCovered = 0;
    int  SellExit(s_SCNewOrder& o)
    {
        ++ordersAttempted;
        if (TradeServiceInconsistent()) return -1;
        if (!stubSim) return -1;
        if (stubRefuseExits) return -1;
        if (enforceCoverage) {
            // Coverage is counted per bracket, not per child. An OCO pair covers its parent's
            // quantity once, and a bracket with only one live child - a preset whose exit carries
            // no target has no target order - covers it just the same. Halving the child total
            // was wrong for exactly those, and integer division then threw the remainder away,
            // which understated coverage and made this stub refuse sells Sierra would accept.
            int covered = 0;
            for (std::map<int, std::pair<int,int> >::iterator b = bracket.begin();
                 b != bracket.end(); ++b) {
                std::map<int, StubOrder>::iterator t = working.find(b->second.first);
                std::map<int, StubOrder>::iterator p = working.find(b->second.second);
                if (t != working.end())      covered += t->second.qty;
                else if (p != working.end()) covered += p->second.qty;
            }
            int uncovered = (int)stubPosition - covered;
            if (uncovered < 0) uncovered = 0;
            if (o.OrderQuantity > uncovered) { ++exitsRefusedAsCovered; return -1; }
        }
        if (o.OrderQuantity > stubPosition - pendingSellQty) ++trimOverSurplus;
        if (stubFillDelay > 0) {
            pendingSells.push_back(std::make_pair((int)o.OrderQuantity, stubFillDelay));
            pendingSellQty += o.OrderQuantity;
            ++trimsOk; trimQtyTotal += o.OrderQuantity;
            o.InternalOrderID = nextOrderId++;
            return o.InternalOrderID;
        }
        stubPosition -= o.OrderQuantity;
        if (stubPosition < 0) stubPosition = 0;
        // Attached orders belong to a position, so closing contracts retires their brackets - but
        // only the brackets of the contracts actually closed. Under coverage enforcement above,
        // a market sell can only ever take contracts that NOTHING covers, so there is no bracket
        // to retire and retiring one anyway destroys the caller's own record of a live trade: the
        // study then saw an empty bracket for a preset whose contracts were still held, let the leg
        // go, and those contracts became a surplus it sold - which retired another live bracket,
        // and so on. 3,216 contracts of the offline run's market sells were this stub eating its
        // own state. With coverage off (STUB_COVERAGE=0) the sell does reach covered contracts, and
        // then their brackets do have to go.
        for (int left = enforceCoverage ? 0 : o.OrderQuantity; left > 0; ) {
            std::map<int, std::pair<int,int> >::iterator b = bracket.begin();
            bool retired = false;
            for (; b != bracket.end(); ++b) {
                std::map<int, StubOrder>::iterator t = working.find(b->second.first);
                std::map<int, StubOrder>::iterator p = working.find(b->second.second);
                if (t == working.end() && p == working.end()) continue;
                const int q = t != working.end() ? t->second.qty : p->second.qty;
                if (t != working.end()) working.erase(t);
                if (p != working.end()) working.erase(p);
                bracket.erase(b);
                left -= q;
                retired = true;
                break;
            }
            if (!retired) break;
        }
        if (CancelAllOrdersOnEntriesAndReversals) {
            cancelledByTrim += (int)working.size();
            working.clear();
            bracket.clear();
        }
        ++trimsOk; trimQtyTotal += o.OrderQuantity;
        o.InternalOrderID = nextOrderId++;
        return o.InternalOrderID;
    }

    double stubLast = 0;          // the harness sets this to the bar close before each call
    int    bracketExits = 0;      // children steered to the market and filled
    int  ModifyOrder(s_SCNewOrder& o)
    {
        if (!stubSim) return -1;
        if (stubRefuseModify) return -1;
        std::map<int, StubOrder>::iterator it = working.find(o.InternalOrderID);
        if (it == working.end()) { ++stopMovesOnDeadOrder; return -1; }
        it->second.price = o.Price1;
        ++stopMovesOk;
        // A sell LIMIT at or below the market fills at once - that is how a preset the book has
        // closed leaves the account. A sell STOP below the market does NOT: it waits for price to
        // fall to it. Filling both was a bug in this stub, and an expensive one: every trailing
        // stop move was treated as an exit, so the stub's position ran away from the study's
        // ledger and produced phantom surpluses that looked exactly like a fault in the study.
        const bool fillsNow = it->second.isStop ? (o.Price1 >= stubLast) : (o.Price1 <= stubLast);
        if (stubLast > 0 && fillsNow) {
            const int parent = it->second.parent;
            const int qty    = it->second.qty;
            std::map<int, std::pair<int,int> >::iterator b = bracket.find(parent);
            if (b != bracket.end()) {
                working.erase(b->second.first);
                working.erase(b->second.second);
                bracket.erase(b);
            } else {
                working.erase(it);
            }
            stubPosition -= qty;
            if (stubPosition < 0) stubPosition = 0;
            finished[o.InternalOrderID] = SCT_OSC_FILLED;
            lastFillPrice = o.Price1;
            ++bracketExits;
        }
        return 1;
    }

    int  cancelsOk = 0, cancelsOnDeadOrder = 0;
    int  CancelOrder(int id)
    {
        if (!stubSim) return -1;
        if (stubRefuseModify) return -1;
        std::map<int, StubOrder>::iterator it = working.find(id);
        if (it == working.end()) { ++cancelsOnDeadOrder; return -1; }
        working.erase(it);
        finished[id] = SCT_OSC_CANCELED;
        ++cancelsOk;
        return 1;
    }
    // The final state of every order this stub has finished with: an order that filled or was
    // cancelled is no longer in `working`, and a study that only ever got "no such order" back
    // could not tell a filled protective stop from one that never existed. That distinction is the
    // whole point of asking, so it is recorded.
    std::map<int, int> finished;          // id -> SCT_OSC_*
    double lastFillPrice = 0;
    int  GetOrderByOrderID(int id, s_SCTradeOrder& r)
    {
        r = s_SCTradeOrder();
        r.InternalOrderID = id;
        std::map<int, StubOrder>::iterator it = working.find(id);
        if (it != working.end()) {
            r.OrderStatusCode = SCT_OSC_OPEN;
            r.OrderQuantity   = it->second.qty;
            r.Price1          = it->second.price;
            return 1;
        }
        std::map<int, int>::iterator f = finished.find(id);
        if (f == finished.end()) return 0;          // 0 = no such order
        r.OrderStatusCode = f->second;
        r.AvgFillPrice    = lastFillPrice;
        return 1;
    }

    // STUB_REFUSE_EMERG=1 refuses the standalone protective stop and accepts everything else. It
    // models the one thing Sierra might legitimately do to it: the contracts are already covered by
    // forty-eight bracket stops, so a further sell order over the same position can be read as
    // over-coverage. Whether Sierra actually refuses it is NOT known, which is exactly why the
    // refusal has to be measurable rather than assumed either way.
    bool  stubRefuseEmerg = getenv("STUB_REFUSE_EMERG")
                         && atoi(getenv("STUB_REFUSE_EMERG")) == 1;
    int   emergPlaced = 0, emergRefused = 0, emergFills = 0;

    // A plain sell order, not an exit: Sierra's SellOrder. A STOP rests in the book until the
    // market reaches it; a MARKET one reduces the position at once. Coverage is deliberately NOT
    // enforced here - that rule is Sierra's answer to SellExit, and whether it also applies to
    // this call is what STUB_REFUSE_EMERG exists to test.
    int  SellOrder(s_SCNewOrder& o)
    {
        ++ordersAttempted;
        if (TradeServiceInconsistent()) return -1;
        if (!stubSim) return -1;
        if (o.OrderType == SCT_ORDERTYPE_STOP) {
            if (stubRefuseEmerg) { ++emergRefused; return -1; }
            const int id = nextOrderId++;
            o.InternalOrderID = id;
            StubOrder t; t.id = id; t.parent = 0; t.qty = o.OrderQuantity;
            t.price = o.Price1; t.isStop = true;
            working[id] = t;                  // parent 0: belongs to no bracket
            ++emergPlaced;
            return id;
        }
        stubPosition -= o.OrderQuantity;
        if (stubPosition < 0) stubPosition = 0;
        o.InternalOrderID = nextOrderId++;
        return o.InternalOrderID;
    }
    // Signature copied from the real sierrachart.h (void, int parent, two int out-params).
    void GetAttachedOrderIDsForParentOrder(int parent, int& r_TargetInternalOrderID, int& r_StopInternalOrderID)
    {
        r_TargetInternalOrderID = 0; r_StopInternalOrderID = 0;
        if (!stubSim || BracketsAllGone()) return;
        std::map<int, std::pair<int,int> >::iterator it = bracket.find(parent);
        if (it == bracket.end()) return;
        if (working.count(it->second.first))  r_TargetInternalOrderID = it->second.first;
        if (working.count(it->second.second)) r_StopInternalOrderID  = it->second.second;
    }
    void AddMessageToLog(const SCString& m, int) { fprintf(stderr, "LOG: %s\n", m.GetChars()); }

    // Sierra's own words behind a trading error code. The real ACSIL call is what finally makes a
    // bare "-1" readable; the stub only has to return something, because what matters here is
    // that the study compiles and prints it. The study assigns the result into an SCString before
    // using it, so it does not matter whether the real build returns const char* or SCString.
    const char* GetTradingErrorTextMessage(int code)
    {
        if (code == -1) return "stub: generic refusal, no reason recorded";
        if (code <= -8990 && code >= -8999) return "stub: skipped, nothing was sent";
        return "";
    }
    // Ends with a separator, like Sierra's own. Without it DataPath picks a Windows backslash on
    // this platform and writes a file literally named ".\\name.csv" - which is right on Windows and
    // invisible here, so the one test that reads the file back could not find it.
    SCString DataFilesFolder() { return SCString("./"); }
    int GetBarHasClosedStatus(int) { return BHCS_BAR_HAS_CLOSED; }
};
typedef SCStudyInterface& SCStudyInterfaceRef;
