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

double bm25Contribution(double tf, double documentCount, double documentFrequency, double docLength, double averageLength) {
    if (tf <= 0.0) {
        return 0.0;
    }
    const double k1 = 1.35;
    const double b = 0.72;
    double idf = std::log(1.0 + (documentCount - documentFrequency + 0.5) / (documentFrequency + 0.5));
    double normalized = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * docLength / averageLength));
    return idf * normalized * 10.0;
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
        std::vector<ScoreComponent> contributions;

        for (const auto& token : tokens) {
            double nameTf = fieldTermFrequency(name, token, 3.0);
            double tagsTf = fieldTermFrequency(tagsText, token, 2.4);
            double areaTf = fieldTermFrequency(area, token, 1.5);
            double descriptionTf = fieldTermFrequency(description, token, 1.0);
            double tf = nameTf + tagsTf + areaTf + descriptionTf;
            if (tf > 0.0) {
                matchedTerms.push_back(token);
                double documentCount = static_cast<double>(pois.size());
                double df = static_cast<double>(documentFrequency[token]);
                double tokenScore = bm25Contribution(tf, documentCount, df, docLength, averageLength);
                score += tokenScore;

                if (nameTf > 0.0) {
                    contributions.push_back({"名称BM25", std::round(bm25Contribution(nameTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "查询词「" + token + "」命中名称字段。"});
                }
                if (tagsTf > 0.0) {
                    contributions.push_back({"标签BM25", std::round(bm25Contribution(tagsTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "查询词「" + token + "」命中标签字段。"});
                }
                if (areaTf > 0.0) {
                    contributions.push_back({"区域BM25", std::round(bm25Contribution(areaTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "查询词「" + token + "」命中区域字段。"});
                }
                if (descriptionTf > 0.0) {
                    contributions.push_back({"描述BM25", std::round(bm25Contribution(descriptionTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "查询词「" + token + "」命中描述字段。"});
                }
            }
        }
        if (tokens.empty()) {
            score = poi.popularity;
            matchedTerms.push_back("热度");
            contributions.push_back({"热度", poi.popularity, "空查询按 POI 热度排序。"});
        }
        score += poi.popularity;
        contributions.push_back({"热度加权", poi.popularity, "检索排序叠加 POI 热度，避免低质量文本匹配靠前。"});

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
            result.scoreContributions = contributions;
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
    nlohmann::json contributions = nlohmann::json::array();
    for (const auto& component : result.scoreContributions) {
        contributions.push_back(scoreComponentToJson(component));
    }
    return {
        {"id", result.id},
        {"name", result.name},
        {"type", result.type},
        {"area", result.area},
        {"score", result.score},
        {"description", result.description},
        {"matched_terms", result.matchedTerms},
        {"score_explanation", result.scoreExplanation},
        {"score_contributions", contributions}
    };
}

}  // namespace tourpass
