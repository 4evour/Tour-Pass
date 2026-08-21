#pragma once

#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "tourpass/graph.h"

namespace tourpass {

struct SearchResult {
    std::string id;
    std::string name;
    std::string type;
    std::string area;
    double score = 0.0;
    double popularity = 0.0;
    std::string description;
    std::vector<std::string> matchedTerms;
    std::string scoreExplanation;
    std::vector<ScoreComponent> scoreContributions;
    double lat = 0.0;
    double lng = 0.0;
    int priceLevel = 1;
    std::string mealType;
    int visitDurationMinutes = 60;
    int openMinutes = 0;
    int closeMinutes = 24 * 60;
    std::string recommendation;
    std::string imageUrl;
    std::string guideText;
    std::vector<PoiImage> images;
};

struct PoiSearchIndex {
    const Poi* poi;
    std::string nameLc;
    std::string areaLc;
    std::string descriptionLc;
    std::string tagsTextLc;
    double docLength;
};

class SearchEngine {
public:
    explicit SearchEngine(const PoiGraph& graph);
    void rebuild();
    std::vector<SearchResult> search(const std::string& query, const std::string& type, int limit) const;

private:
    const PoiGraph& graph_;
    std::vector<PoiSearchIndex> index_;
    double averageLength_;
    std::unordered_map<std::string, std::unordered_set<size_t>> invertedIndex_;
};

nlohmann::json searchResultToJson(const SearchResult& result);

}  // namespace tourpass
