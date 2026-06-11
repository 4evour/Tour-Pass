#include "tourpass/search.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <set>
#include <sstream>
#include <unordered_map>
#include <unordered_set>

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

SearchEngine::SearchEngine(const PoiGraph& graph) : graph_(graph), averageLength_(1.0) {
    const auto& pois = graph_.pois();
    index_.reserve(pois.size());
    double totalLength = 0.0;
    for (const auto& poi : pois) {
        PoiSearchIndex entry;
        entry.poi = &poi;
        entry.nameLc = lowerAscii(poi.name);
        entry.areaLc = lowerAscii(poi.area);
        entry.descriptionLc = lowerAscii(poi.description);
        std::string tags;
        for (const auto& tag : poi.tags) {
            tags += lowerAscii(tag) + " ";
        }
        entry.tagsTextLc = std::move(tags);
        entry.docLength = 2.0 + poi.tags.size() + std::max<size_t>(1, poi.description.size() / 6);
        totalLength += entry.docLength;
        index_.push_back(std::move(entry));
    }
    averageLength_ = pois.empty() ? 1.0 : totalLength / static_cast<double>(pois.size());

    // Build inverted index for fast document frequency lookups
    for (size_t i = 0; i < index_.size(); ++i) {
        const auto& entry = index_[i];
        auto addWords = [&](const std::string& text) {
            std::istringstream iss(text);
            std::string word;
            while (iss >> word) {
                invertedIndex_[word].insert(i);
            }
        };
        addWords(entry.nameLc);
        addWords(entry.areaLc);
        addWords(entry.tagsTextLc);
        addWords(entry.descriptionLc);
    }
}

std::vector<SearchResult> SearchEngine::search(const std::string& query, const std::string& type, int limit) const {
    std::vector<SearchResult> results;
    if (limit <= 0) limit = 10;
    const auto tokens = splitQuery(query);

    std::unordered_map<std::string, int> documentFrequency;
    for (const auto& token : tokens) {
        // Use pre-built inverted index for O(1) DF lookup instead of O(N) scan
        auto invIt = invertedIndex_.find(token);
        int count = (invIt != invertedIndex_.end()) ? static_cast<int>(invIt->second.size()) : 0;
        documentFrequency[token] = std::max(1, count);
    }

    const double averageLength = averageLength_;

    for (const auto& entry : index_) {
        const auto& poi = *entry.poi;
        if (!type.empty() && poiTypeToString(poi.type) != type) {
            continue;
        }

        // Skip non-tourist POIs (schools, companies, factories, etc.)
        static const std::unordered_set<std::string> blacklistTags = {
            "学校", "职业技术学校", "职业技术学院", "中学", "小学", "幼儿园", "大学", "学院",
            "公司企业", "公司", "工厂", "政府机构", "派出所", "消防队",
            "医院", "诊所", "药店", "殡仪馆", "墓地",
            "加油站", "停车场", "收费站", "住宅区", "小区"
        };
        bool blacklisted = false;
        for (const auto& tag : poi.tags) {
            if (blacklistTags.count(tag)) { blacklisted = true; break; }
        }
        if (blacklisted) continue;

        // Skip POIs with non-tourist names (schools, etc.) unless whitelisted
        static const std::vector<std::string> nameBlacklist = {
            "职业学院", "职业技术", "中学", "小学", "幼儿园", "学校"
        };
        static const std::vector<std::string> nameWhitelist = {
            "博物馆", "美术馆", "科技馆"
        };
        {
            bool nameBlacklisted = false;
            bool nameWhitelisted = false;
            for (const auto& wl : nameWhitelist) {
                if (poi.name.find(wl) != std::string::npos) { nameWhitelisted = true; break; }
            }
            if (!nameWhitelisted) {
                for (const auto& bl : nameBlacklist) {
                    if (poi.name.find(bl) != std::string::npos) { nameBlacklisted = true; break; }
                }
            }
            if (nameBlacklisted) continue;
        }

        double score = 0.0;
        std::vector<std::string> matchedTerms;
        const std::string& name = entry.nameLc;
        const std::string& area = entry.areaLc;
        const std::string& description = entry.descriptionLc;
        const std::string& tagsText = entry.tagsTextLc;
        const double docLength = entry.docLength;
        std::vector<ScoreComponent> contributions;

        for (const auto& token : tokens) {
            double nameTf = fieldTermFrequency(name, token, 3.0);
            double tagsTf = fieldTermFrequency(tagsText, token, 2.4);
            double areaTf = fieldTermFrequency(area, token, 1.5);
            double descriptionTf = fieldTermFrequency(description, token, 1.0);
            double tf = nameTf + tagsTf + areaTf + descriptionTf;
            if (tf > 0.0) {
                matchedTerms.push_back(token);
                double documentCount = static_cast<double>(index_.size());
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
            score = entry.poi->popularity;
            matchedTerms.push_back("热度");
            contributions.push_back({"热度", poi.popularity, "空查询按 POI 热度排序。"});
        }
        score += entry.poi->popularity;
        contributions.push_back({"热度加权", entry.poi->popularity, "检索排序叠加 POI 热度，避免低质量文本匹配靠前。"});

        if (score > 0.0) {
            SearchResult result;
            result.id = entry.poi->id;
            result.name = entry.poi->name;
            result.type = poiTypeToString(entry.poi->type);
            result.area = entry.poi->area;
            result.score = std::round(score * 10.0) / 10.0;
            result.popularity = entry.poi->popularity;
            result.description = entry.poi->description;
            result.matchedTerms = matchedTerms;
            result.scoreExplanation = tokens.empty()
                ? "空查询按 POI 热度排序。"
                : "BM25 + 字段权重：名称、标签、区域和描述共同贡献，匹配词为「" + joinTerms(matchedTerms) + "」。";
            result.scoreContributions = contributions;
            result.lat = entry.poi->lat;
            result.lng = entry.poi->lng;
            result.priceLevel = entry.poi->priceLevel;
            result.mealType = entry.poi->mealType;
            result.visitDurationMinutes = entry.poi->visitDurationMinutes;
            result.openMinutes = entry.poi->openMinutes;
            result.closeMinutes = entry.poi->closeMinutes;
            result.recommendation = entry.poi->recommendation;
            result.imageUrl = entry.poi->imageUrl;
            result.guideText = entry.poi->guideText;
            result.images = entry.poi->images;
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
    nlohmann::json j = {
        {"id", result.id},
        {"name", result.name},
        {"type", result.type},
        {"area", result.area},
        {"score", result.score},
        {"popularity", result.popularity},
        {"description", result.description},
        {"matched_terms", result.matchedTerms},
        {"score_explanation", result.scoreExplanation},
        {"score_contributions", contributions},
        {"lat", result.lat},
        {"lng", result.lng},
        {"price_level", result.priceLevel},
        {"meal_type", result.mealType},
        {"visit_duration", result.visitDurationMinutes},
        {"open_minutes", result.openMinutes},
        {"close_minutes", result.closeMinutes},
        {"recommendation", result.recommendation},
        {"image_url", result.imageUrl},
        {"guide_text", result.guideText}
    };
    // Serialize images array
    nlohmann::json imgs = nlohmann::json::array();
    for (const auto& img : result.images) {
        imgs.push_back({{"url", img.url}, {"source", img.source}});
    }
    j["images"] = imgs;
    return j;
}

}  // namespace tourpass
