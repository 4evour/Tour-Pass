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
        if (i > 0) out << "銆?;
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
        auto it = invertedIndex_.find(token);
        int count = (it != invertedIndex_.end()) ? static_cast<int>(it->second.size()) : 0;
        documentFrequency[token] = std::max(1, count);
    }
    }

    const double averageLength = averageLength_;

    for (const auto& entry : index_) {
        const auto& poi = *entry.poi;
        if (!type.empty() && poiTypeToString(poi.type) != type) {
            continue;
        }

        // Skip non-tourist POIs (schools, companies, factories, etc.)
        static const std::unordered_set<std::string> blacklistTags = {
            "瀛︽牎", "鑱屼笟鎶€鏈鏍?, "鑱屼笟鎶€鏈闄?, "涓", "灏忓", "骞煎効鍥?, "澶у", "瀛﹂櫌",
            "鍏徃浼佷笟", "鍏徃", "宸ュ巶", "鏀垮簻鏈烘瀯", "娲惧嚭鎵€", "娑堥槻闃?,
            "鍖婚櫌", "璇婃墍", "鑽簵", "娈′华棣?, "澧撳湴",
            "鍔犳补绔?, "鍋滆溅鍦?, "鏀惰垂绔?, "浣忓畢鍖?, "灏忓尯"
        };
        bool blacklisted = false;
        for (const auto& tag : poi.tags) {
            if (blacklistTags.count(tag)) { blacklisted = true; break; }
        }
        if (blacklisted) continue;

        // Skip POIs with non-tourist names (schools, etc.) unless whitelisted
        static const std::vector<std::string> nameBlacklist = {
            "鑱屼笟瀛﹂櫌", "鑱屼笟鎶€鏈?, "涓", "灏忓", "骞煎効鍥?, "瀛︽牎"
        };
        static const std::vector<std::string> nameWhitelist = {
            "鍗氱墿棣?, "缇庢湳棣?, "绉戞妧棣?
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
                    contributions.push_back({"鍚嶇ОBM25", std::round(bm25Contribution(nameTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "鏌ヨ璇嶃€? + token + "銆嶅懡涓悕绉板瓧娈点€?});
                }
                if (tagsTf > 0.0) {
                    contributions.push_back({"鏍囩BM25", std::round(bm25Contribution(tagsTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "鏌ヨ璇嶃€? + token + "銆嶅懡涓爣绛惧瓧娈点€?});
                }
                if (areaTf > 0.0) {
                    contributions.push_back({"鍖哄煙BM25", std::round(bm25Contribution(areaTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "鏌ヨ璇嶃€? + token + "銆嶅懡涓尯鍩熷瓧娈点€?});
                }
                if (descriptionTf > 0.0) {
                    contributions.push_back({"鎻忚堪BM25", std::round(bm25Contribution(descriptionTf, documentCount, df, docLength, averageLength) * 10.0) / 10.0, "鏌ヨ璇嶃€? + token + "銆嶅懡涓弿杩板瓧娈点€?});
                }
            }
        }
        if (tokens.empty()) {
            score = entry.poi->popularity;
            matchedTerms.push_back("鐑害");
            contributions.push_back({"鐑害", poi.popularity, "绌烘煡璇㈡寜 POI 鐑害鎺掑簭銆?});
        }
        score += entry.poi->popularity;
        contributions.push_back({"鐑害鍔犳潈", entry.poi->popularity, "妫€绱㈡帓搴忓彔鍔?POI 鐑害锛岄伩鍏嶄綆璐ㄩ噺鏂囨湰鍖归厤闈犲墠銆?});

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
                ? "绌烘煡璇㈡寜 POI 鐑害鎺掑簭銆?
                : "BM25 + 瀛楁鏉冮噸锛氬悕绉般€佹爣绛俱€佸尯鍩熷拰鎻忚堪鍏卞悓璐＄尞锛屽尮閰嶈瘝涓恒€? + joinTerms(matchedTerms) + "銆嶃€?;
            result.scoreContributions = contributions;
            result.lat = entry.poi->lat;
            result.lng = entry.poi->lng;
            result.priceLevel = entry.poi->priceLevel;
            result.mealType = entry.poi->mealType;
            result.visitDurationMinutes = entry.poi->visitDurationMinutes;
            result.openMinutes = entry.poi->openMinutes;
            result.closeMinutes = entry.poi->closeMinutes;
            result.recommendation = entry.poi->recommendation;
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
        {"recommendation", result.recommendation}
    };
}

}  // namespace tourpass
