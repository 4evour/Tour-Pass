#include "tourpass/env.h"
#include "tourpass/graph.h"

#include <queue>
#include <stdexcept>
#include <utility>
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cmath>

namespace tourpass {

int edgeTravelMinutes(const Edge& edge) {
    if (edge.transitMinutes >= 0) return edge.transitMinutes;
    if (edge.taxiMinutes >= 0) return edge.taxiMinutes;
    return edge.walkMinutes;
}

PoiGraph::PoiGraph(std::vector<Poi> pois, std::vector<Edge> edges)
    : PoiGraph(std::move(pois), std::move(edges), distanceCacheConfigFromEnv()) {}

PoiGraph::PoiGraph(std::vector<Poi> pois, std::vector<Edge> edges, DistanceCacheConfig cacheConfig)
    : pois_(std::move(pois)), edgeCount_(edges.size()) {
    cacheConfig_ = cacheConfig;
    activeCacheMode_ = cacheConfig_.mode;
    if (activeCacheMode_ == DistanceCacheMode::Auto) {
        activeCacheMode_ = pois_.size() <= cacheConfig_.maxAllPairsPois
            ? DistanceCacheMode::AllPairs
            : DistanceCacheMode::OnDemand;
    }
    for (size_t i = 0; i < pois_.size(); ++i) {
        indexById_[pois_[i].id] = i;
        idByName_[pois_[i].name] = pois_[i].id;
    }
    for (const auto& edge : edges) {
        int minutes = edgeTravelMinutes(edge);
        adjacency_[edge.from].push_back({edge.to, minutes});
        adjacency_[edge.to].push_back({edge.from, minutes});
    }
    auto startedAt = std::chrono::steady_clock::now();
    if (activeCacheMode_ == DistanceCacheMode::AllPairs) {
        buildShortestMinuteCache();
    }
    cacheStartupMs_ = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - startedAt).count();
}

const Poi* PoiGraph::findPoi(const std::string& idOrName) const {
    auto idIt = indexById_.find(idOrName);
    if (idIt != indexById_.end()) {
        return &pois_[idIt->second];
    }
    auto nameIt = idByName_.find(idOrName);
    if (nameIt != idByName_.end()) {
        // Iterative lookup: name -> id -> index (no recursion to avoid stack overflow)
        auto idIt2 = indexById_.find(nameIt->second);
        if (idIt2 != indexById_.end()) {
            return &pois_[idIt2->second];
        }
    }
    return nullptr;
}

Poi* PoiGraph::findMutablePoi(const std::string& id) {
    auto it = indexById_.find(id);
    if (it != indexById_.end()) {
        return &pois_[it->second];
    }
    return nullptr;
}

int PoiGraph::shortestMinutes(const std::string& from, const std::string& to) const {
    auto fromIt = indexById_.find(from);
    if (fromIt == indexById_.end()) {
        auto nameIt = idByName_.find(from);
        if (nameIt != idByName_.end()) {
            fromIt = indexById_.find(nameIt->second);
        }
    }
    auto toIt = indexById_.find(to);
    if (toIt == indexById_.end()) {
        auto nameIt = idByName_.find(to);
        if (nameIt != idByName_.end()) {
            toIt = indexById_.find(nameIt->second);
        }
    }
    if (fromIt != indexById_.end() && toIt != indexById_.end()) {
        size_t fromIndex = fromIt->second;
        size_t toIndex = toIt->second;
        if (activeCacheMode_ == DistanceCacheMode::AllPairs &&
            fromIndex < shortestMinuteCache_.size() &&
            toIndex < shortestMinuteCache_[fromIndex].size()) {
            return shortestMinuteCache_[fromIndex][toIndex];
        }
        if (activeCacheMode_ == DistanceCacheMode::OnDemand) {
            int cached = std::numeric_limits<int>::max();
            if (getCachedOnDemand(fromIndex, toIndex, cached)) {
                return cached;
            }
            int computed = computeShortestMinutesByIndex(fromIndex, toIndex);
            putCachedOnDemand(fromIndex, toIndex, computed);
            return computed;
        }
        if (activeCacheMode_ == DistanceCacheMode::Disabled) {
            return computeShortestMinutesByIndex(fromIndex, toIndex);
        }
    }
    return shortestRoute(from, to).travelMinutes;
}

RouteResult PoiGraph::shortestRoute(const std::string& from, const std::string& to) const {
    return findRoute(from, to, false);
}

RouteResult PoiGraph::aStarRoute(const std::string& from, const std::string& to) const {
    return findRoute(from, to, true);
}

double PoiGraph::heuristicMinutes(const Poi& from, const Poi& to) const {
    double latDiff = from.lat - to.lat;
    double lngDiff = from.lng - to.lng;
    double roughKm = std::sqrt(latDiff * latDiff + lngDiff * lngDiff) * 111.0;
    return roughKm / 28.0 * 60.0;
}

RouteResult PoiGraph::findRoute(const std::string& from, const std::string& to, bool useHeuristic) const {
    RouteResult route;
    route.from = from;
    route.to = to;
    route.travelMinutes = std::numeric_limits<int>::max();
    route.algorithm = useHeuristic ? "astar" : "dijkstra";

    const Poi* start = findPoi(from);
    const Poi* target = findPoi(to);
    if (!start || !target) {
        return route;
    }
    if (start->id == target->id) {
        route.from = start->id;
        route.to = target->id;
        route.travelMinutes = 0;
        route.path = {start->id};
        return route;
    }

    struct QueueItem {
        int priority = 0;
        int cost = 0;
        size_t idx = 0;
    };
    struct QueueCompare {
        bool operator()(const QueueItem& a, const QueueItem& b) const {
            return a.priority > b.priority;
        }
    };
    std::priority_queue<QueueItem, std::vector<QueueItem>, QueueCompare> queue;
    const size_t n = pois_.size();
    std::vector<int> dist(n, std::numeric_limits<int>::max());
    std::vector<size_t> previous(n, n); // n = sentinel for "no previous"
    size_t startIdx = indexById_.at(start->id);
    size_t targetIdx = indexById_.at(target->id);
    dist[startIdx] = 0;
    queue.push({0, 0, startIdx});

    while (!queue.empty()) {
        auto item = queue.top();
        queue.pop();
        int cost = item.cost;
        size_t curIdx = item.idx;
        if (cost != dist[curIdx]) continue;
        if (curIdx == targetIdx) break;

        const std::string& curId = pois_[curIdx].id;
        auto adjIt = adjacency_.find(curId);
        if (adjIt == adjacency_.end()) continue;
        for (const auto& next : adjIt->second) {
            auto nextIt = indexById_.find(next.to);
            if (nextIt == indexById_.end()) continue;
            size_t nextIdx = nextIt->second;
            int nextCost = cost + next.minutes;
            if (nextCost < dist[nextIdx]) {
                dist[nextIdx] = nextCost;
                previous[nextIdx] = curIdx;
                int priority = nextCost;
                if (useHeuristic) {
                    priority += static_cast<int>(heuristicMinutes(pois_[nextIdx], *target));
                }
                queue.push({priority, nextCost, nextIdx});
            }
        }
    }

    if (dist[targetIdx] == std::numeric_limits<int>::max()) {
        return route;
    }

    route.from = start->id;
    route.to = target->id;
    route.travelMinutes = dist[targetIdx];
    size_t cursor = targetIdx;
    while (cursor < n) {
        route.path.push_back(pois_[cursor].id);
        if (cursor == startIdx) break;
        cursor = previous[cursor];
    }
    std::reverse(route.path.begin(), route.path.end());
    for (const auto& pid : route.path) {
        const Poi* p = findPoi(pid);
        if (p) {
            route.pathCoords.push_back({p->lat, p->lng});
        } else {
            route.pathCoords.push_back({0.0, 0.0});
        }
    }
    return route;
}

std::vector<const Poi*> PoiGraph::reachableFrom(const std::string& from) const {
    std::vector<const Poi*> result;
    const Poi* start = findPoi(from);
    if (!start) return result;

    auto adjIt = adjacency_.find(start->id);
    if (adjIt == adjacency_.end()) return result;
    for (const auto& adjacent : adjIt->second) {
        const Poi* poi = findPoi(adjacent.to);
        if (poi) result.push_back(poi);
    }
    return result;
}

DistanceCacheStats PoiGraph::distanceCacheStats() const {
    size_t entries = 0;
    for (const auto& row : shortestMinuteCache_) {
        entries += row.size();
    }
    uint64_t hits = 0;
    uint64_t misses = 0;
    uint64_t evictions = 0;
    if (activeCacheMode_ == DistanceCacheMode::OnDemand) {
        std::lock_guard<std::mutex> lock(onDemandMutex_);
        entries = onDemandEntries_.size();
        hits = onDemandHits_;
        misses = onDemandMisses_;
        evictions = onDemandEvictions_;
    }
    return DistanceCacheStats{
        activeCacheMode_ != DistanceCacheMode::Disabled,
        distanceCacheModeToString(activeCacheMode_),
        pois_.size(),
        entries,
        activeCacheMode_ == DistanceCacheMode::OnDemand ? cacheConfig_.onDemandEntries : entries,
        hits,
        misses,
        evictions,
        cacheStartupMs_
    };
}

std::vector<int> PoiGraph::computeSingleSourceShortestMinutes(const std::string& from) const {
    std::vector<int> dist(pois_.size(), std::numeric_limits<int>::max());
    auto startIt = indexById_.find(from);
    if (startIt == indexById_.end()) {
        return dist;
    }

    struct QueueItem {
        int cost = 0;
        std::string id;
    };
    struct QueueCompare {
        bool operator()(const QueueItem& a, const QueueItem& b) const {
            return a.cost > b.cost;
        }
    };

    std::priority_queue<QueueItem, std::vector<QueueItem>, QueueCompare> queue;
    dist[startIt->second] = 0;
    queue.push({0, from});

    while (!queue.empty()) {
        auto item = queue.top();
        queue.pop();
        auto idIt = indexById_.find(item.id);
        if (idIt == indexById_.end() || item.cost != dist[idIt->second]) {
            continue;
        }

        auto adjIt = adjacency_.find(item.id);
        if (adjIt == adjacency_.end()) continue;
        for (const auto& next : adjIt->second) {
            auto nextIndex = indexById_.find(next.to);
            if (nextIndex == indexById_.end()) continue;
            int nextCost = item.cost + next.minutes;
            if (nextCost < dist[nextIndex->second]) {
                dist[nextIndex->second] = nextCost;
                queue.push({nextCost, next.to});
            }
        }
    }
    return dist;
}

void PoiGraph::buildShortestMinuteCache() {
    shortestMinuteCache_.clear();
    shortestMinuteCache_.reserve(pois_.size());
    for (const auto& poi : pois_) {
        shortestMinuteCache_.push_back(computeSingleSourceShortestMinutes(poi.id));
    }
}

int PoiGraph::computeShortestMinutesByIndex(size_t from, size_t to) const {
    if (from >= pois_.size() || to >= pois_.size()) {
        return std::numeric_limits<int>::max();
    }
    if (from == to) {
        return 0;
    }
    auto dist = computeSingleSourceShortestMinutes(pois_[from].id);
    return to < dist.size() ? dist[to] : std::numeric_limits<int>::max();
}

bool PoiGraph::getCachedOnDemand(size_t from, size_t to, int& minutes) const {
    if (from > to) std::swap(from, to);
    uint64_t key = (static_cast<uint64_t>(from) << 32) | static_cast<uint64_t>(to);
    std::lock_guard<std::mutex> lock(onDemandMutex_);
    auto found = onDemandIndex_.find(key);
    if (found == onDemandIndex_.end()) {
        ++onDemandMisses_;
        return false;
    }
    onDemandEntries_.splice(onDemandEntries_.begin(), onDemandEntries_, found->second);
    minutes = onDemandEntries_.front().minutes;
    ++onDemandHits_;
    return true;
}

void PoiGraph::putCachedOnDemand(size_t from, size_t to, int minutes) const {
    if (cacheConfig_.onDemandEntries == 0) return;
    if (from > to) std::swap(from, to);
    uint64_t key = (static_cast<uint64_t>(from) << 32) | static_cast<uint64_t>(to);
    std::lock_guard<std::mutex> lock(onDemandMutex_);
    auto found = onDemandIndex_.find(key);
    if (found != onDemandIndex_.end()) {
        found->second->minutes = minutes;
        onDemandEntries_.splice(onDemandEntries_.begin(), onDemandEntries_, found->second);
        return;
    }
    onDemandEntries_.push_front(OnDemandEntry{key, minutes});
    onDemandIndex_[key] = onDemandEntries_.begin();
    while (onDemandEntries_.size() > cacheConfig_.onDemandEntries) {
        onDemandIndex_.erase(onDemandEntries_.back().key);
        onDemandEntries_.pop_back();
        ++onDemandEvictions_;
    }
}

namespace {

// envSize is provided by tourpass/env.h (included above)

DistanceCacheMode parseDistanceCacheMode(const char* value) {
    if (!value || !*value) return DistanceCacheMode::Auto;
    std::string mode = value;
    if (mode == "all_pairs") return DistanceCacheMode::AllPairs;
    if (mode == "on_demand") return DistanceCacheMode::OnDemand;
    if (mode == "disabled") return DistanceCacheMode::Disabled;
    return DistanceCacheMode::Auto;
}

}  // namespace

DistanceCacheConfig distanceCacheConfigFromEnv() {
    DistanceCacheConfig config;
    config.mode = parseDistanceCacheMode(std::getenv("TOURPASS_DISTANCE_CACHE_MODE"));
    config.maxAllPairsPois = envSize("TOURPASS_DISTANCE_CACHE_MAX_POIS", 500, 1, 100000);
    config.onDemandEntries = envSize("TOURPASS_DISTANCE_CACHE_ENTRIES", 10000, 1, 1000000);
    return config;
}

std::string distanceCacheModeToString(DistanceCacheMode mode) {
    switch (mode) {
        case DistanceCacheMode::Auto:
            return "auto";
        case DistanceCacheMode::AllPairs:
            return "all_pairs";
        case DistanceCacheMode::OnDemand:
            return "on_demand";
        case DistanceCacheMode::Disabled:
            return "disabled";
    }
    return "auto";
}

}  // namespace tourpass
