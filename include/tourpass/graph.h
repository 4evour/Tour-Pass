#pragma once

#include <limits>
#include <list>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include "tourpass/models.h"

namespace tourpass {

struct DistanceCacheStats {
    bool enabled = false;
    std::string mode = "all_pairs";
    size_t poiCount = 0;
    size_t entries = 0;
    size_t maxEntries = 0;
    uint64_t hits = 0;
    uint64_t misses = 0;
    uint64_t evictions = 0;
    int64_t startupMs = 0;
};

enum class DistanceCacheMode {
    Auto,
    AllPairs,
    OnDemand,
    Disabled
};

struct DistanceCacheConfig {
    DistanceCacheMode mode = DistanceCacheMode::Auto;
    size_t maxAllPairsPois = 500;
    size_t onDemandEntries = 10000;
};

class PoiGraph {
public:
    PoiGraph() = default;
    PoiGraph(std::vector<Poi> pois, std::vector<Edge> edges);
    PoiGraph(std::vector<Poi> pois, std::vector<Edge> edges, DistanceCacheConfig cacheConfig);

    PoiGraph(const PoiGraph&) = delete;
    PoiGraph& operator=(const PoiGraph&) = delete;
    PoiGraph(PoiGraph&&) = delete;
    PoiGraph& operator=(PoiGraph&&) = delete;

    const Poi* findPoi(const std::string& idOrName) const;
    const std::vector<Poi>& pois() const { return pois_; }
    size_t edgeCount() const { return edgeCount_; }
    int shortestMinutes(const std::string& from, const std::string& to) const;
    RouteResult shortestRoute(const std::string& from, const std::string& to) const;
    RouteResult aStarRoute(const std::string& from, const std::string& to) const;
    std::vector<const Poi*> reachableFrom(const std::string& from) const;
    DistanceCacheStats distanceCacheStats() const;
    bool empty() const { return pois_.empty(); }

private:
    struct Adjacent {
        std::string to;
        int minutes = 0;
    };

    std::vector<Poi> pois_;
    size_t edgeCount_ = 0;
    std::unordered_map<std::string, size_t> indexById_;
    std::unordered_map<std::string, std::string> idByName_;
    std::unordered_map<std::string, std::vector<Adjacent>> adjacency_;
    std::vector<std::vector<int>> shortestMinuteCache_;
    DistanceCacheConfig cacheConfig_;
    DistanceCacheMode activeCacheMode_ = DistanceCacheMode::AllPairs;
    int64_t cacheStartupMs_ = 0;

    struct OnDemandEntry {
        uint64_t key = 0;
        int minutes = std::numeric_limits<int>::max();
    };
    mutable std::mutex onDemandMutex_;
    mutable std::list<OnDemandEntry> onDemandEntries_;
    mutable std::unordered_map<uint64_t, std::list<OnDemandEntry>::iterator> onDemandIndex_;
    mutable uint64_t onDemandHits_ = 0;
    mutable uint64_t onDemandMisses_ = 0;
    mutable uint64_t onDemandEvictions_ = 0;

    RouteResult findRoute(const std::string& from, const std::string& to, bool useHeuristic) const;
    double heuristicMinutes(const Poi& from, const Poi& to) const;
    std::vector<int> computeSingleSourceShortestMinutes(const std::string& from) const;
    int computeShortestMinutesByIndex(size_t from, size_t to) const;
    void buildShortestMinuteCache();
    bool getCachedOnDemand(size_t from, size_t to, int& minutes) const;
    void putCachedOnDemand(size_t from, size_t to, int minutes) const;
};

int edgeTravelMinutes(const Edge& edge);
DistanceCacheConfig distanceCacheConfigFromEnv();
std::string distanceCacheModeToString(DistanceCacheMode mode);

}  // namespace tourpass
