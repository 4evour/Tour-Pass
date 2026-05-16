#pragma once

#include <string>
#include <vector>

#include "tourpass/graph.h"

namespace tourpass {

struct SearchResult {
    std::string id;
    std::string name;
    std::string type;
    std::string area;
    double score = 0.0;
    std::string description;
    std::vector<std::string> matchedTerms;
    std::string scoreExplanation;
    std::vector<ScoreComponent> scoreContributions;
};

class SearchEngine {
public:
    explicit SearchEngine(const PoiGraph& graph);
    std::vector<SearchResult> search(const std::string& query, const std::string& type, int limit) const;

private:
    const PoiGraph& graph_;
};

nlohmann::json searchResultToJson(const SearchResult& result);

}  // namespace tourpass
