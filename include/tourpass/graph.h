#pragma once

#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

#include "tourpass/models.h"

namespace tourpass {

class PoiGraph {
public:
    PoiGraph() = default;
    PoiGraph(std::vector<Poi> pois, std::vector<Edge> edges);

    const Poi* findPoi(const std::string& idOrName) const;
    const std::vector<Poi>& pois() const { return pois_; }
    int shortestMinutes(const std::string& from, const std::string& to) const;
    RouteResult shortestRoute(const std::string& from, const std::string& to) const;
    RouteResult aStarRoute(const std::string& from, const std::string& to) const;
    std::vector<const Poi*> reachableFrom(const std::string& from) const;
    bool empty() const { return pois_.empty(); }

private:
    struct Adjacent {
        std::string to;
        int minutes = 0;
    };

    std::vector<Poi> pois_;
    std::unordered_map<std::string, size_t> indexById_;
    std::unordered_map<std::string, std::string> idByName_;
    std::unordered_map<std::string, std::vector<Adjacent>> adjacency_;

    RouteResult findRoute(const std::string& from, const std::string& to, bool useHeuristic) const;
    double heuristicMinutes(const Poi& from, const Poi& to) const;
};

int edgeTravelMinutes(const Edge& edge);

}  // namespace tourpass
