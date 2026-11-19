#pragma once
// Lukacino Flow Intelligence: deterministic price-level research accumulator.
// Pure C++17; no ACSIL dependencies. NOT a trading signal or execution engine.
#include <cstdint>
#include <map>
#include <stdexcept>
#include <vector>
#include <cmath>

namespace lfi {
struct TradePrint {
    std::int64_t timestamp_ms;
    int price_ticks;
    std::uint64_t bid_volume;
    std::uint64_t ask_volume;
};
struct PriceLevel {
    std::uint64_t bid_volume = 0;
    std::uint64_t ask_volume = 0;
    std::uint64_t visits = 0;
    std::int64_t first_ms = -1;
    std::int64_t last_ms = -1;
    std::int64_t delta() const {
        return static_cast<std::int64_t>(ask_volume) - static_cast<std::int64_t>(bid_volume);
    }
    std::uint64_t volume() const { return bid_volume + ask_volume; }
};
class PriceLevelAccumulator {
public:
    explicit PriceLevelAccumulator(int zone_radius_ticks = 0, int reset_distance_ticks = 2)
      : radius_(zone_radius_ticks), reset_(reset_distance_ticks) {
        if (radius_ < 0 || reset_ <= radius_) throw std::invalid_argument("invalid zone settings");
    }
    void resetSession() { levels_.clear(); last_time_ = -1; last_price_ = 0; initialized_ = false; }
    void add(const TradePrint& p) {
        if (p.timestamp_ms < 0 || (initialized_ && p.timestamp_ms < last_time_))
            throw std::invalid_argument("non-monotonic timestamp");
        if (p.bid_volume > UINT64_MAX - p.ask_volume)
            throw std::overflow_error("print volume overflow");
        // Count independent visits to every observed level. A new visit requires
        // leaving its zone by reset_ ticks before coming back.
        for (auto& kv : levels_) {
            if (std::abs(static_cast<long long>(p.price_ticks) - kv.first) >= reset_)
                kv.second.armed = true;
        }
        Internal& v = levels_[p.price_ticks];
        if (!v.seen || v.armed) {
            ++v.data.visits;
            v.armed = false;
        }
        v.seen = true;
        if (v.data.bid_volume > UINT64_MAX - p.bid_volume ||
            v.data.ask_volume > UINT64_MAX - p.ask_volume)
            throw std::overflow_error("level volume overflow");
        v.data.bid_volume += p.bid_volume;
        v.data.ask_volume += p.ask_volume;
        if (v.data.first_ms < 0) v.data.first_ms = p.timestamp_ms;
        v.data.last_ms = p.timestamp_ms;
        initialized_ = true; last_time_ = p.timestamp_ms; last_price_ = p.price_ticks;
    }
    PriceLevel at(int price_ticks) const {
        auto it = levels_.find(price_ticks);
        return it == levels_.end() ? PriceLevel{} : it->second.data;
    }
    PriceLevel zone(int center_ticks) const {
        PriceLevel z;
        for (const auto& kv : levels_) {
            if (std::abs(static_cast<long long>(kv.first) - center_ticks) > radius_) continue;
            const PriceLevel& p = kv.second.data;
            z.bid_volume += p.bid_volume; z.ask_volume += p.ask_volume;
            z.visits += p.visits; // sum of per-level visits, NOT distinct zone visits
            if (z.first_ms < 0 || p.first_ms < z.first_ms) z.first_ms = p.first_ms;
            if (p.last_ms > z.last_ms) z.last_ms = p.last_ms;
        }
        return z;
    }
    std::size_t levelCount() const { return levels_.size(); }
private:
    struct Internal { PriceLevel data; bool armed = false; bool seen = false; };
    std::map<int, Internal> levels_;
    int radius_, reset_, last_price_ = 0;
    std::int64_t last_time_ = -1;
    bool initialized_ = false;
};
} // namespace lfi
