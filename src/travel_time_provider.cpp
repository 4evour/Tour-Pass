#include "tourpass/travel_time_provider.h"

#include <cstdlib>
#include <iostream>
#include <sstream>

#include "httplib.h"
#include "json.hpp"

namespace tourpass {

// --- LocalDataProvider ---

LocalDataProvider::LocalDataProvider(const PoiGraph& graph) : graph_(graph) {}

TravelTimeResult LocalDataProvider::getTravelTime(const std::string& fromId, const std::string& toId) {
    int minutes = graph_.shortestMinutes(fromId, toId);
    if (minutes == std::numeric_limits<int>::max()) {
        return {-1, "local", false};
    }
    return {minutes, "local", false};
}

// --- AmapLiveProvider ---

namespace {

std::string getenvStr(const char* key) {
    const char* v = std::getenv(key);
    return v ? std::string(v) : std::string();
}

int parseDrivingDuration(const std::string& responseBody) {
    try {
        auto json = nlohmann::json::parse(responseBody);
        if (json.value("status", "") != "1") return -1;
        auto& route = json["route"];
        auto& paths = route["paths"];
        if (!paths.is_array() || paths.empty()) return -1;
        int seconds = paths[0].value("duration", 0);
        return (seconds + 59) / 60;  // round up to minutes
    } catch (...) {
        return -1;
    }
}

}  // namespace

AmapLiveProvider::AmapLiveProvider(const std::string& apiKey, const PoiGraph& graph, size_t cacheCapacity)
    : apiKey_(apiKey), graph_(graph), cacheCapacity_(cacheCapacity) {}

std::string AmapLiveProvider::cacheKey(const std::string& from, const std::string& to) const {
    if (from < to) return from + "|" + to;
    return to + "|" + from;
}

bool AmapLiveProvider::getCached(const std::string& key, int& minutes) const {
    std::lock_guard<std::mutex> lock(cacheMutex_);
    auto found = cacheIndex_.find(key);
    if (found == cacheIndex_.end()) {
        ++cacheMisses_;
        return false;
    }
    auto& entry = found->second->second;
    if (std::chrono::steady_clock::now() - entry.cachedAt > cacheTtl_) {
        cacheOrder_.erase(found->second);
        cacheIndex_.erase(found);
        ++cacheMisses_;
        return false;
    }
    cacheOrder_.splice(cacheOrder_.begin(), cacheOrder_, found->second);
    minutes = entry.minutes;
    ++cacheHits_;
    return true;
}

void AmapLiveProvider::putCache(const std::string& key, int minutes) {
    std::lock_guard<std::mutex> lock(cacheMutex_);
    auto found = cacheIndex_.find(key);
    if (found != cacheIndex_.end()) {
        found->second->second.minutes = minutes;
        found->second->second.cachedAt = std::chrono::steady_clock::now();
        cacheOrder_.splice(cacheOrder_.begin(), cacheOrder_, found->second);
        return;
    }
    cacheOrder_.push_front({key, {minutes, std::chrono::steady_clock::now()}});
    cacheIndex_[key] = cacheOrder_.begin();
    while (cacheOrder_.size() > cacheCapacity_) {
        cacheIndex_.erase(cacheOrder_.back().first);
        cacheOrder_.pop_back();
    }
}

int AmapLiveProvider::fetchFromAmap(const Poi& from, const Poi& to) const {
    std::ostringstream path;
    path << "/v3/direction/driving?origin=" << std::fixed << from.lng << "," << from.lat
         << "&destination=" << std::fixed << to.lng << "," << to.lat
         << "&key=" << apiKey_;

    try {
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
        httplib::SSLClient client("restapi.amap.com");
#else
        httplib::Client client("https://restapi.amap.com");
#endif
        if (!client.is_valid()) return -1;
        client.set_connection_timeout(3);
        client.set_read_timeout(5);

        auto result = client.Get(path.str());
        if (!result || result->status != 200) return -1;
        return parseDrivingDuration(result->body);
    } catch (...) {
        return -1;
    }
}

TravelTimeResult AmapLiveProvider::getTravelTime(const std::string& fromId, const std::string& toId) {
    std::string key = cacheKey(fromId, toId);
    int cached = -1;
    if (getCached(key, cached)) {
        if (cached >= 0) return {cached, "amap", true};
    }

    const Poi* from = graph_.findPoi(fromId);
    const Poi* to = graph_.findPoi(toId);
    if (!from || !to) return {-1, "amap", false};

    int minutes = fetchFromAmap(*from, *to);
    if (minutes >= 0) {
        putCache(key, minutes);
        return {minutes, "amap", false};
    }

    // Fallback to local data
    int localMinutes = graph_.shortestMinutes(fromId, toId);
    if (localMinutes != std::numeric_limits<int>::max()) {
        return {localMinutes, "local_fallback", false};
    }
    return {-1, "amap_failed", false};
}

// --- Factory ---

std::unique_ptr<TravelTimeProvider> createTravelTimeProvider(const PoiGraph& graph) {
    std::string mode = getenvStr("TOURPASS_TRAVEL_TIME_PROVIDER");
    if (mode == "amap") {
        std::string apiKey = getenvStr("TOURPASS_AMAP_API_KEY");
        if (apiKey.empty()) {
            apiKey = getenvStr("AMAP_API_KEY");
        }
        if (!apiKey.empty()) {
            std::cout << "TravelTimeProvider: using AmapLiveProvider (real-time routing)" << std::endl;
            return std::make_unique<AmapLiveProvider>(apiKey, graph);
        }
        std::cerr << "TravelTimeProvider: amap mode requires TOURPASS_AMAP_API_KEY, falling back to local" << std::endl;
    }
    return std::make_unique<LocalDataProvider>(graph);
}

}  // namespace tourpass
