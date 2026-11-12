// Standalone smoke tests: g++ -std=c++17 -Wall -Wextra -pedantic LFI_PriceLevelAccumulator_test.cpp -o lfi_test && ./lfi_test
#include "LFI_PriceLevelAccumulator.hpp"
#include <cassert>
#include <stdexcept>
int main() {
    lfi::PriceLevelAccumulator a(0, 2);
    a.add({1000, 100, 30, 10});
    a.add({1001, 100, 20, 5});
    assert(a.at(100).visits == 1);
    assert(a.at(100).bid_volume == 50 && a.at(100).ask_volume == 15);
    assert(a.at(100).delta() == -35);
    a.add({1002, 101, 1, 1}); // 1 tick away does not rearm
    a.add({1003, 100, 1, 1});
    assert(a.at(100).visits == 1);
    a.add({1004, 102, 5, 5}); // 2 ticks away rearms
    a.add({1005, 100, 10, 20});
    assert(a.at(100).visits == 2);
    assert(a.at(100).volume() == 97);
    bool threw = false;
    try { a.add({999, 100, 1, 1}); }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    a.resetSession();
    assert(a.levelCount() == 0);
    a.add({2000, 100, 1, 2});
    assert(a.at(100).visits == 1 && a.at(100).delta() == 1);
}
