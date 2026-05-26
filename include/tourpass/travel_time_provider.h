#pragma once

#include <chrono>
#include <list>
#include <mutex>
#include <string>
#include <unordered_map>

#include "tourpass/graph.h"

namespace tourpass {

struct TravelTimeResult {
    int minutes = -1;
    std::string source;
    bool cached = false;
};

class TravelTimeProvider {
public:
    virtual ~TravelTimeProvider() = default;
    virtual TravelTimeResult getTravelTime(const std::string& fromId, const std::string& toId) = 0;
    virtual std::string name() const = 0;
};

class LocalDataProvider : public TravelTimeProvider {
public:
    explicit LocalDataProvider(const PoiGraph& graph);
    TravelTimeResult getTravelTime(const std::string& fromId, const std::string& toId) override;
    std::string name() const override { return "local"; }

private:
    const PoiGraph& graph_;
};

class AmapLiveProvider : public TravelTimeProvider {
public:
    AmapLiveProvider(const std::string& apiKey, const PoiGraph& graph, size_t cacheCapacity = 10000);
    TravelTimeResult getTravelTime(const std::string& fromId, const std::string& toId) override;
    std::string name() const override { return "amap"; }

private:
    struct CacheEntry {
        int minutes = -1;
        std::chrono::steady_clock::time_point cachedAt;
    };

    std::string apiKey_;
    const PoiGraph& graph_;
    std::chrono::seconds cacheTtl_{3600};
    size_t cacheCapacity_;

    mutable std::mutex cacheMutex_;
    mutable std::list<std::pair<std::string, CacheEntry>> cacheOrder_;
    mutable std::unordered_map<std::string, std::list<std::pair<std::string, CacheEntry>>::iterator> cacheIndex_;
    mutable uint64_t cacheHits_ = 0;
    mutable uint64_t cacheMisses_ = 0;

    std::string cacheKey(const std::string& from, const std::string& to) const;
    bool getCached(const std::string& key, int& minutes) const;
    void putCache(const std::string& key, int minutes);
    int fetchFromAmap(const Poi& from, const Poi& to) const;
};

std::unique_ptr<TravelTimeProvider> createTravelTimeProvider(const PoiGraph& graph);

}  // namespace tourpass
