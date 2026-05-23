#pragma once

#include "tourpass/graph.h"
#include "tourpass/llm.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"
#include "tourpass/service_runtime.h"
#include "tourpass/sqlite_store.h"

namespace tourpass {

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port);
int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port, const RuntimeConfig& config);
int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port, const RuntimeConfig& config, SQLiteStore* store);
int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, const std::string& host, int port, const RuntimeConfig& config, SQLiteStore* store);
nlohmann::json errorJson(const std::string& code, const std::string& message, const nlohmann::json& details = nlohmann::json::object());

}  // namespace tourpass
