#include "tourpass/search.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <set>
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

double fieldTermFrequency(const std::string& field, const std::string& token, double weight) {
    if (field.empty() || token.empty()) {
        return 0.0;
    }
    double frequency = 0.0;
    size_t pos = field.find(token);
    while (pos != std::string::npos) {
        frequency += weight;
        pos = field.find(token, pos + token.size());
    }
    return frequency;
}

std::string joinTerms(const std::vector<std::string>& terms) {
    std::ostringstream out;
    for (size_t i = 0; i < terms.size(); ++i) {
        if (i > 0) out << "、";
        out << terms[i];
    }
    return out.str();
}

}  // namespace

SearchEngine::SearchEngine(const PoiGraph& graph) : graph_(graph) {}

std::vector<SearchResult> SearchEngine::search(const std::string& query, const std::string& type, int limit) const {
    std::vector<SearchResult> results;
    if (limit <= 0) limit = 10;
    const auto tokens = splitQuery(query);
    const auto& pois = graph_.pois();

    std::unordered_map<std::string, int> documentFrequency;
    for (const auto& token : tokens) {
        int count = 0;
        for (const auto& poi : pois) {
            std::string text = lowerAscii(poi.name + " " + poi.area + " " + poi.description);
            for (const auto& tag : poi.tags) {
                text += " " + lowerAscii(tag);
            }
            if (text.find(token) != std::string::npos) {
                ++count;
            }
        }
        documentFrequency[token] = std::max(1, count);
    }

    double totalLength = 0.0;
    for (const auto& poi : pois) {
        totalLength += 2.0 + poi.tags.size() + std::max<size_t>(1, poi.description.size() / 6);
    }
    const double averageLength = pois.empty() ? 1.0 : totalLength / static_cast<double>(pois.size());

    for (const auto& poi : pois) {
        if (!type.empty() && poiTypeToString(poi.type) != type) {
            continue;
        }

        double score = 0.0;
        std::vector<std::string> matchedTerms;
        std::string tagsText;
        for (const auto& tag : poi.tags) {
            tagsText += lowerAscii(tag) + " ";
        }
        const std::string name = lowerAscii(poi.name);
        const std::string area = lowerAscii(poi.area);
        const std::string description = lowerAscii(poi.description);
        const double docLength = 2.0 + poi.tags.size() + std::max<size_t>(1, poi.description.size() / 6);
        const double k1 = 1.35;
        const double b = 0.72;

        for (const auto& token : tokens) {
            double tf = 0.0;
            tf += fieldTermFrequency(name, token, 3.0);
            tf += fieldTermFrequency(tagsText, token, 2.4);
            tf += fieldTermFrequency(area, token, 1.5);
            tf += fieldTermFrequency(description, token, 1.0);
            if (tf > 0.0) {
                matchedTerms.push_back(token);
                double idf = std::log(1.0 + (static_cast<double>(pois.size()) - documentFrequency[token] + 0.5) / (documentFrequency[token] + 0.5));
                double normalized = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * docLength / averageLength));
                score += idf * normalized * 10.0;
            }
        }
        if (tokens.empty()) {
            score = poi.popularity;
            matchedTerms.push_back("热度");
        }
        score += poi.popularity;

        if (score > 0.0) {
            SearchResult result;
            result.id = poi.id;
            result.name = poi.name;
            result.type = poiTypeToString(poi.type);
            result.area = poi.area;
            result.score = std::round(score * 10.0) / 10.0;
            result.description = poi.description;
            result.matchedTerms = matchedTerms;
            result.scoreExplanation = tokens.empty()
                ? "空查询按 POI 热度排序。"
                : "BM25 + 字段权重：名称、标签、区域和描述共同贡献，匹配词为「" + joinTerms(matchedTerms) + "」。";
            results.push_back(result);
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
        {"description", result.description},
        {"matched_terms", result.matchedTerms},
        {"score_explanation", result.scoreExplanation}
    };
}

}  // namespace tourpass
