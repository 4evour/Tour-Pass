#pragma once

#include "tourpass/graph.h"
#include "tourpass/llm.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"

namespace tourpass {

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port);
nlohmann::json errorJson(const std::string& code, const std::string& message, const nlohmann::json& details = nlohmann::json::object());

}  // namespace tourpass
