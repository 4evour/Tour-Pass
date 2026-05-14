#include "tourpass/graph.h"

#include <queue>
#include <stdexcept>
#include <utility>
#include <algorithm>
#include <cmath>

namespace tourpass {

int edgeTravelMinutes(const Edge& edge) {
    if (edge.transitMinutes >= 0) return edge.transitMinutes;
    if (edge.taxiMinutes >= 0) return edge.taxiMinutes;
    return edge.walkMinutes;
}

PoiGraph::PoiGraph(std::vector<Poi> pois, std::vector<Edge> edges)
    : pois_(std::move(pois)) {
    for (size_t i = 0; i < pois_.size(); ++i) {
        indexById_[pois_[i].id] = i;
        idByName_[pois_[i].name] = pois_[i].id;
    }
    for (const auto& edge : edges) {
        int minutes = edgeTravelMinutes(edge);
        adjacency_[edge.from].push_back({edge.to, minutes});
        adjacency_[edge.to].push_back({edge.from, minutes});
    }
}

const Poi* PoiGraph::findPoi(const std::string& idOrName) const {
    auto idIt = indexById_.find(idOrName);
    if (idIt != indexById_.end()) {
        return &pois_[idIt->second];
    }
    auto nameIt = idByName_.find(idOrName);
    if (nameIt != idByName_.end()) {
        return findPoi(nameIt->second);
    }
    return nullptr;
}

int PoiGraph::shortestMinutes(const std::string& from, const std::string& to) const {
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
        std::string id;
    };
    struct QueueCompare {
        bool operator()(const QueueItem& a, const QueueItem& b) const {
            return a.priority > b.priority;
        }
    };
    std::priority_queue<QueueItem, std::vector<QueueItem>, QueueCompare> queue;
    std::unordered_map<std::string, int> dist;
    std::unordered_map<std::string, std::string> previous;
    for (const auto& poi : pois_) {
        dist[poi.id] = std::numeric_limits<int>::max();
    }
    dist[start->id] = 0;
    queue.push({0, 0, start->id});

    while (!queue.empty()) {
        auto item = queue.top();
        queue.pop();
        int cost = item.cost;
        const std::string& id = item.id;
        if (cost != dist[id]) continue;
        if (id == target->id) break;

        auto adjIt = adjacency_.find(id);
        if (adjIt == adjacency_.end()) continue;
        for (const auto& next : adjIt->second) {
            int nextCost = cost + next.minutes;
            if (nextCost < dist[next.to]) {
                dist[next.to] = nextCost;
                previous[next.to] = id;
                int priority = nextCost;
                if (useHeuristic) {
                    const Poi* nextPoi = findPoi(next.to);
                    if (nextPoi) {
                        priority += static_cast<int>(heuristicMinutes(*nextPoi, *target));
                    }
                }
                queue.push({priority, nextCost, next.to});
            }
        }
    }

    if (dist[target->id] == std::numeric_limits<int>::max()) {
        return route;
    }

    route.from = start->id;
    route.to = target->id;
    route.travelMinutes = dist[target->id];
    std::string cursor = target->id;
    while (!cursor.empty()) {
        route.path.push_back(cursor);
        if (cursor == start->id) break;
        auto prevIt = previous.find(cursor);
        if (prevIt == previous.end()) break;
        cursor = prevIt->second;
    }
    std::reverse(route.path.begin(), route.path.end());
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

}  // namespace tourpass
