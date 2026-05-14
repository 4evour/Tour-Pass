#include "tourpass/search.h"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <unordered_map>

namespace tourpass {

namespace {

std::string lowerAscii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

std::vector<std::string> splitQuery(const std::string& query) {
    std::vector<std::string> tokens;
    std::stringstream ss(query);
    std::string token;
    while (ss >> token) {
        tokens.push_back(lowerAscii(token));
    }
    if (tokens.empty() && !query.empty()) {
        tokens.push_back(lowerAscii(query));
    }
    return tokens;
}

}  // namespace

SearchEngine::SearchEngine(const PoiGraph& graph) : graph_(graph) {}

std::vector<SearchResult> SearchEngine::search(const std::string& query, const std::string& type, int limit) const {
    std::vector<SearchResult> results;
    if (limit <= 0) limit = 10;
    const auto tokens = splitQuery(query);

    for (const auto& poi : graph_.pois()) {
        if (!type.empty() && poiTypeToString(poi.type) != type) {
            continue;
        }
        std::string text = lowerAscii(poi.name + " " + poi.area + " " + poi.description);
        for (const auto& tag : poi.tags) {
            text += " " + lowerAscii(tag);
        }

        double score = 0.0;
        for (const auto& token : tokens) {
            if (text.find(token) != std::string::npos) {
                score += 10.0;
            }
            for (const auto& tag : poi.tags) {
                if (lowerAscii(tag).find(token) != std::string::npos) {
                    score += 8.0;
                }
            }
        }
        if (tokens.empty()) {
            score = poi.popularity;
        }
        score += poi.popularity;

        if (score > 0.0) {
            results.push_back({poi.id, poi.name, poiTypeToString(poi.type), poi.area, score, poi.description});
        }
    }

    std::sort(results.begin(), results.end(), [](const SearchResult& a, const SearchResult& b) {
        return a.score > b.score;
    });
    if (static_cast<int>(results.size()) > limit) {
        results.resize(static_cast<size_t>(limit));
    }
    return results;
}

nlohmann::json searchResultToJson(const SearchResult& result) {
    return {
        {"id", result.id},
        {"name", result.name},
        {"type", result.type},
        {"area", result.area},
        {"score", result.score},
        {"description", result.description}
    };
}

}  // namespace tourpass
