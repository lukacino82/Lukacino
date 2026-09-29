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
struct SCDateTime {
    int days = 0; int secs = 0;
    int GetDate() const { return days; }
    int GetTimeInSeconds() const { return secs; }
    void SetDate(int d) { days = d; }
    int GetYear() const { int y; unsigned m, d; CivilFromDays(days, y, m, d); return y; }
    int GetMonth() const { int y; unsigned m, d; CivilFromDays(days, y, m, d); return (int)m; }
    int GetDay() const { int y; unsigned m, d; CivilFromDays(days, y, m, d); return (int)d; }
    int GetDayOfWeek() const { return (days + 4) % 7; }   // 0 = Sunday (1970-01-01 was Thursday)
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
    void AddMessageToLog(const SCString& m, int) { fprintf(stderr, "LOG: %s\n", m.GetChars()); }
    SCString DataFilesFolder() { return SCString("."); }
    int GetBarHasClosedStatus(int) { return BHCS_BAR_HAS_CLOSED; }
};
typedef SCStudyInterface& SCStudyInterfaceRef;
