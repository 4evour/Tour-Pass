#pragma once

#include <string>
#include <shared_mutex>
#include <unordered_map>

#include "tourpass/data_store.h"
#include "tourpass/graph.h"
#include "tourpass/llm.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"
#include "tourpass/service_runtime.h"

namespace tourpass {

struct CityBundle {
    PoiGraph graph;
    TripPlanner planner;
    SearchEngine search;
    std::string poisPath;
    mutable std::shared_mutex dataMutex;
    CityBundle(std::vector<Poi> pois, std::vector<Edge> edges)
        : graph(std::move(pois), std::move(edges)), planner(graph), search(graph) {}
    CityBundle(const CityBundle&) = delete;
    CityBundle& operator=(const CityBundle&) = delete;
};

// Multi-city API
int runServer(std::unordered_map<std::string, std::unique_ptr<CityBundle>> cities, const std::string& defaultCity,
              LlmClient& llm, const std::string& host, int port, const RuntimeConfig& config, DataStore* store);

nlohmann::json errorJson(const std::string& code, const std::string& message, const nlohmann::json& details = nlohmann::json::object());
std::string contentSecurityPolicy(
    const std::string& scriptSrc = "'self'",
    const std::string& connectSrc = "'self' https://api.open-meteo.com https://*.tile.openstreetmap.org https://*.is.autonavi.com");

}  // namespace tourpass
