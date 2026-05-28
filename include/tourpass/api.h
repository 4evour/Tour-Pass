#pragma once

#include <string>
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
    CityBundle(std::vector<Poi> pois, std::vector<Edge> edges)
        : graph(std::move(pois), std::move(edges)), planner(graph), search(graph) {}
    CityBundle(const CityBundle&) = delete;
    CityBundle& operator=(const CityBundle&) = delete;
};

// Multi-city API
int runServer(std::unordered_map<std::string, std::unique_ptr<CityBundle>> cities, const std::string& defaultCity,
              LlmClient& llm, const std::string& host, int port, const RuntimeConfig& config, DataStore* store);

nlohmann::json errorJson(const std::string& code, const std::string& message, const nlohmann::json& details = nlohmann::json::object());

}  // namespace tourpass
