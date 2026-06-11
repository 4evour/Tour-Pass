#include "tourpass/planner.h"

#include <algorithm>
#include <cstdlib>
#include <cmath>
#include <limits>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace tourpass {

TripPlanner::TripPlanner(const PoiGraph& graph) : graph_(graph) {}

namespace {

// Extract brand name from POI name (e.g. "茶颜悦色(蝴蝶大厦店)" -> "茶颜悦色")
std::string extractBrand(const std::string& name) {
    auto pos = name.find('(');
    if (pos == std::string::npos) pos = name.find('（');
    if (pos == std::string::npos) pos = name.find('(');
    std::string brand = (pos != std::string::npos) ? name.substr(0, pos) : name;
    // Trim trailing whitespace
    while (!brand.empty() && brand.back() == ' ') brand.pop_back();
    return brand;
}

// Check if a POI brand is already used in the itinerary
bool isBrandDuplicate(const std::string& poiName, const std::set<std::string>& usedNames) {
    std::string brand = extractBrand(poiName);
    if (brand.size() < 2) return false;
    for (const auto& used : usedNames) {
        std::string usedBrand = extractBrand(used);
        if (brand == usedBrand) return true;
    }
    return false;
}

std::string joinTags(const std::vector<std::string>& values) {
    if (values.empty()) {
        return "热度、时间窗和通勤成本";
    }
    std::ostringstream out;
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) out << "、";
        out << values[i];
    }
    return out.str();
}

void annotateVariantFocus(Itinerary& itinerary, const std::string& focus) {
    for (auto& day : itinerary.days) {
        if (day.summary.find("演示重点") == std::string::npos) {
            day.summary += " 演示重点：" + focus;
        }
    }
}

double rounded(double value) {
    return std::round(value * 10.0) / 10.0;
}

double breakdownTotal(const std::vector<ScoreComponent>& breakdown) {
    double total = 0.0;
    for (const auto& component : breakdown) {
        total += component.value;
    }
    return rounded(total);
}

bool hasTag(const Poi& poi, const std::string& tag) {
    return containsText(poi.tags, tag);
}

bool hasAnyTag(const Poi& poi, const std::vector<std::string>& tags) {
    for (const auto& tag : tags) {
        if (hasTag(poi, tag)) {
            return true;
        }
    }
    return false;
}

bool betterOrEqualOnAllObjectives(const ComparisonMetrics& left, const ComparisonMetrics& right) {
    return left.totalScore >= right.totalScore &&
           left.mustVisitCovered >= right.mustVisitCovered &&
           left.totalTravelMinutes <= right.totalTravelMinutes &&
           left.openTimeRisks <= right.openTimeRisks &&
           left.unscheduledCount <= right.unscheduledCount;
}

bool strictlyBetterOnAnyObjective(const ComparisonMetrics& left, const ComparisonMetrics& right) {
    return left.totalScore > right.totalScore ||
           left.mustVisitCovered > right.mustVisitCovered ||
           left.totalTravelMinutes < right.totalTravelMinutes ||
           left.openTimeRisks < right.openTimeRisks ||
           left.unscheduledCount < right.unscheduledCount;
}

bool dominates(const ComparisonMetrics& left, const ComparisonMetrics& right) {
    return betterOrEqualOnAllObjectives(left, right) && strictlyBetterOnAnyObjective(left, right);
}

std::set<std::string> collectPoiIds(const Itinerary& itinerary) {
    std::set<std::string> values;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            values.insert(stop.poiId);
        }
    }
    return values;
}

std::set<std::string> collectAreas(const Itinerary& itinerary) {
    std::set<std::string> values;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            if (!stop.area.empty()) {
                values.insert(stop.area);
            }
        }
    }
    return values;
}

std::vector<std::string> collectUniquePoiNames(const Itinerary& itinerary, const std::set<std::string>& baselinePoiIds) {
    std::vector<std::string> values;
    std::set<std::string> seen;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            if (baselinePoiIds.count(stop.poiId) == 0 && seen.insert(stop.poiId).second) {
                values.push_back(stop.poiName);
            }
        }
    }
    return values;
}

double overlapRatio(const std::set<std::string>& left, const std::set<std::string>& right) {
    if (left.empty() && right.empty()) {
        return 1.0;
    }
    std::vector<std::string> intersection;
    std::vector<std::string> unionValues;
    std::set_intersection(left.begin(), left.end(), right.begin(), right.end(), std::back_inserter(intersection));
    std::set_union(left.begin(), left.end(), right.begin(), right.end(), std::back_inserter(unionValues));
    if (unionValues.empty()) {
        return 1.0;
    }
    return rounded(static_cast<double>(intersection.size()) / static_cast<double>(unionValues.size()));
}

std::string diversityLevel(double poiOverlap, int uniquePoiCount) {
    if (poiOverlap <= 0.35 || uniquePoiCount >= 4) return "高差异";
    if (poiOverlap <= 0.65 || uniquePoiCount >= 2) return "中差异";
    return "低差异";
}

std::string strategyDiversityTag(const std::string& strategy) {
    if (strategy == "low_travel") return "体力友好差异";
    if (strategy == "compact") return "覆盖密度差异";
    if (strategy == "culture") return "文化主题差异";
    if (strategy == "food") return "美食主题差异";
    if (strategy == "rainy") return "雨天场景差异";
    return "时间偏移差异";
}

int mealWindowStart(const std::string& slot) {
    if (slot == "午餐") return 11 * 60 + 30;
    if (slot == "下午茶") return 14 * 60 + 30;
    if (slot == "晚餐") return 17 * 60 + 30;
    return -1;
}

int mealWindowEnd(const std::string& slot) {
    if (slot == "午餐") return 13 * 60 + 30;
    if (slot == "下午茶") return 16 * 60 + 30;
    if (slot == "晚餐") return 19 * 60 + 30;
    return -1;
}

bool isMealSlot(const std::string& slot) {
    return slot == "午餐" || slot == "晚餐" || slot == "下午茶";
}

bool slotAcceptsPoi(const std::string& slot, const Poi& poi) {
    if (slot == "午餐" || slot == "晚餐") {
        // Lunch/dinner only accept main restaurants (not drinks/snacks)
        return poi.type == PoiType::Restaurant && poi.mealType == "main";
    }
    if (slot == "下午茶") {
        return poi.type == PoiType::Restaurant && poi.mealType == "drink";
    }
    if (slot == "晚上") {
        return poi.type == PoiType::Nightlife;
    }
    // Activity slots accept attractions + nightlife + drink/snack restaurants
    if (poi.type == PoiType::Restaurant && (poi.mealType == "drink" || poi.mealType == "snack")) {
        return true;
    }
    return poi.type == PoiType::Attraction || poi.type == PoiType::Nightlife;
}

bool isMustVisitPoi(const TripRequest& request, const Poi& poi) {
    return containsText(request.mustVisit, poi.name) || containsText(request.mustVisit, poi.id);
}

bool isHardAvoidedPoi(const TripRequest& request, const Poi& poi) {
    for (const auto& avoid : request.avoid) {
        if (avoid == poi.name || avoid == poi.id) {
            return true;
        }
    }
    return false;
}

double strategyTagBonus(const TripRequest& request, const Poi& poi) {
    if (request.strategy == "culture" && hasAnyTag(poi, {"历史文化", "博物馆", "古建筑", "书院", "寺庙"})) {
        return 80.0;
    }
    if (request.strategy == "food" && hasAnyTag(poi, {"美食", "小吃", "湘菜", "夜市", "茶饮", "街区"})) {
        return 75.0;
    }
    if (request.strategy == "rainy") {
        double bonus = hasTag(poi, "室内") ? 90.0 : -30.0;
        if (hasTag(poi, "户外")) bonus -= 90.0;
        return bonus;
    }
    if (request.strategy == "low_travel") {
        return 25.0;
    }
    if (request.strategy == "compact") {
        return 35.0;
    }
    return 0.0;
}

double coarseCandidateScore(const TripRequest& request, const Poi& poi, int travelMinutes, int currentTime) {
    double score = poi.popularity * 10.0 - poi.priceLevel * 3.0;
    for (const auto& interest : request.interests) {
        if (containsText(poi.tags, interest)) {
            score += 45.0;
        }
    }
    if (isMustVisitPoi(request, poi)) {
        score += 10000.0;
    }
    score += strategyTagBonus(request, poi);
    double travelPenalty = request.strategy == "low_travel" ? 2.0 : 1.0;
    if (request.strategy == "compact") travelPenalty = 0.55;
    score -= travelMinutes * travelPenalty;
    int arrival = currentTime + travelMinutes;
    if (arrival < poi.openMinutes) {
        score -= (poi.openMinutes - arrival) * 0.35;
    }
    if (arrival + poi.visitDurationMinutes > poi.closeMinutes) {
        score -= 900.0;
    }
    return score;
}

std::string timeWindowIssueStatus(const Stop& stop, const Poi* poi, int previousEnd, int requestEndMinutes) {
    if (stop.startMinutes < previousEnd) return "sequence";
    if (stop.endMinutes > requestEndMinutes) return "day_end";
    if (isMealSlot(stop.slot) && (stop.startMinutes < mealWindowStart(stop.slot) || stop.endMinutes > mealWindowEnd(stop.slot))) {
        return "meal_window";
    }
    if (!poi) return "missing_poi";
    if (stop.startMinutes < poi->openMinutes) return "wait";
    if (stop.endMinutes > poi->closeMinutes) return "closed";
    return "ok";
}

std::string timeWindowIssueReason(const Stop& stop, const Poi* poi, int previousEnd, int requestEndMinutes) {
    if (stop.startMinutes < previousEnd) {
        return stop.poiName + " 开始时间 " + formatMinutes(stop.startMinutes) +
               " 早于上一站结束/休息后时间 " + formatMinutes(previousEnd) + "，最终顺序不可行。";
    }
    if (stop.endMinutes > requestEndMinutes) {
        return stop.poiName + " 预计 " + formatMinutes(stop.endMinutes) +
               " 结束，超出当日结束时间 " + formatMinutes(requestEndMinutes) + "。";
    }
    if (isMealSlot(stop.slot) && (stop.startMinutes < mealWindowStart(stop.slot) || stop.endMinutes > mealWindowEnd(stop.slot))) {
        return stop.poiName + " 的" + stop.slot + "安排为 " + formatMinutes(stop.startMinutes) + "-" +
               formatMinutes(stop.endMinutes) + "，未完整落在 " + formatMinutes(mealWindowStart(stop.slot)) +
               "-" + formatMinutes(mealWindowEnd(stop.slot)) + " 餐饮窗口内。";
    }
    if (!poi) {
        return stop.poiName + " 在 POI 图中缺失，无法复核开放时间。";
    }
    if (stop.startMinutes < poi->openMinutes) {
        return stop.poiName + " 预计 " + formatMinutes(stop.startMinutes) +
               " 到达，早于开放时间 " + formatMinutes(poi->openMinutes) +
               "，需要等待 " + std::to_string(poi->openMinutes - stop.startMinutes) + " 分钟。";
    }
    if (stop.endMinutes > poi->closeMinutes) {
        return stop.poiName + " 预计 " + formatMinutes(stop.endMinutes) +
               " 离开，但 " + formatMinutes(poi->closeMinutes) + " 关闭，超出 " +
               std::to_string(stop.endMinutes - poi->closeMinutes) + " 分钟。";
    }
    return stop.poiName + " 时间窗复核通过：" + formatMinutes(stop.startMinutes) + "-" +
           formatMinutes(stop.endMinutes) + " 位于开放与行程约束内。";
}

struct BeamState {
    std::vector<Stop> stops;
    std::set<std::string> used;
    std::string currentId;
    int currentTime = 0;
    int totalTravelMinutes = 0;
    int totalVisitMinutes = 0;
    double interestScore = 0.0;
};

struct RankedPoiCandidate {
    const Poi* poi = nullptr;
    double score = -100000.0;
    int travelMinutes = std::numeric_limits<int>::max();
    double coarseScore = -100000.0;
    bool mustVisit = false;
};

int envInt(const char* key, int fallback, int minValue, int maxValue) {
    const char* value = std::getenv(key);
    if (!value || !*value) return fallback;
    try {
        int parsed = std::stoi(value);
        return std::max(minValue, std::min(maxValue, parsed));
    } catch (...) {
        return fallback;
    }
}

int plannerBeamWidth() {
    return envInt("TOURPASS_BEAM_WIDTH", 5, 1, 50);
}

int plannerBranchFactor() {
    return envInt("TOURPASS_BRANCH_FACTOR", 6, 1, 50);
}

double beamStateScore(const TripRequest& request, const BeamState& state) {
    double travelPenalty = request.strategy == "low_travel" ? 0.55 : 0.25;
    if (request.strategy == "compact") {
        travelPenalty = 0.12;
    }
    return state.interestScore - state.totalTravelMinutes * travelPenalty + state.stops.size() * 8.0;
}

std::string summarizeBeamState(const TripRequest& request, const BeamState& state) {
    std::ostringstream summary;
    summary << "score=" << rounded(beamStateScore(request, state))
            << " travel=" << state.totalTravelMinutes
            << " stops=" << state.stops.size();
    if (!state.stops.empty()) {
        summary << " path=";
        for (size_t i = 0; i < state.stops.size(); ++i) {
            if (i > 0) summary << " -> ";
            summary << state.stops[i].poiName;
        }
    } else {
        summary << " path=起点";
    }
    return summary.str();
}

}  // namespace

const Poi* TripPlanner::chooseHotel(const TripRequest& request) const {
    if (const Poi* hotel = graph_.findPoi(request.hotelLocation)) {
        return hotel;
    }
    for (const auto& poi : graph_.pois()) {
        if (poi.type == PoiType::Hotel) {
            return &poi;
        }
    }
    return nullptr;
}

int TripPlanner::paceExtraBreakMinutes(const std::string& pace) const {
    if (pace == "轻松") return 20;
    if (pace == "紧凑") return 0;
    return 10;
}

int TripPlanner::routeTravelMinutes(const std::string& startId, const std::vector<Stop>& stops) const {
    std::string currentId = startId;
    int total = 0;
    for (const auto& stop : stops) {
        int travel = graph_.shortestMinutes(currentId, stop.poiId);
        if (travel == std::numeric_limits<int>::max()) {
            return travel;
        }
        total += travel;
        currentId = stop.poiId;
    }
    return total;
}

std::vector<ScoreComponent> TripPlanner::buildScoreBreakdown(const TripRequest& request, const Poi& poi, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const {
    std::vector<ScoreComponent> breakdown;
    if (used.count(poi.id) > 0) {
        breakdown.push_back({"重复排除", -100000.0, "该 POI 已在当前行程中使用。"});
        return breakdown;
    }
    if (isHardAvoidedPoi(request, poi)) {
        breakdown.push_back({"避免项硬排除", -100000.0, "该 POI 被请求的 avoid 名称或 id 明确排除。"});
        return breakdown;
    }
    if (poi.type == PoiType::Hotel || poi.type == PoiType::Transit) {
        breakdown.push_back({"类型排除", -100000.0, "酒店和交通站点不作为游玩站点评分。"});
        return breakdown;
    }

    double popularityMultiplier = request.strategy == "compact" ? 12.0 : 10.0;
    breakdown.push_back({"热度", rounded(poi.popularity * popularityMultiplier), "POI 热度基础分。"});
    for (const auto& interest : request.interests) {
        if (containsText(poi.tags, interest)) {
            double interestBonus = request.strategy == "compact" ? 42.0 : 35.0;
            breakdown.push_back({"兴趣匹配", interestBonus, "匹配用户偏好「" + interest + "」。"});
        }
    }
    if (request.strategy == "low_travel") {
        breakdown.push_back({"短通勤策略", 25.0, "轻松方案偏好短通勤和同区域活动。"});
    }
    if (request.strategy == "compact") {
        breakdown.push_back({"紧凑策略", 28.0, "紧凑方案提高高热度和兴趣点覆盖权重。"});
    }
    if (request.strategy == "culture" && hasAnyTag(poi, {"历史文化", "博物馆", "古建筑", "书院", "寺庙"})) {
        breakdown.push_back({"文化策略", 70.0, "文化优先方案加权博物馆、书院、古建筑等 POI。"});
    }
    if (request.strategy == "food" && hasAnyTag(poi, {"美食", "小吃", "湘菜", "夜市", "茶饮", "街区"})) {
        breakdown.push_back({"美食策略", 65.0, "美食优先方案加权餐饮、小吃街和夜间美食场景。"});
    }
    if (request.strategy == "rainy") {
        if (hasTag(poi, "室内")) {
            breakdown.push_back({"雨天策略", 80.0, "雨天方案优先室内和稳定开放场所。"});
        } else {
            breakdown.push_back({"雨天策略", -20.0, "雨天方案更偏好室内点，该 POI 不是明确室内场所。"});
        }
        if (hasTag(poi, "户外")) {
            breakdown.push_back({"户外惩罚", -80.0, "雨天方案降低户外点优先级。"});
        }
    }
    if (containsText(request.mustVisit, poi.name) || containsText(request.mustVisit, poi.id)) {
        breakdown.push_back({"必去加权", 120.0, "命中用户必去地点。"});
    }
    for (const auto& avoid : request.avoid) {
        if (poi.description.find(avoid) != std::string::npos || containsText(poi.tags, avoid)) {
            breakdown.push_back({"避免项", -40.0, "命中用户避免项「" + avoid + "」。"});
        }
    }

    int travel = graph_.shortestMinutes(currentPoiId, poi.id);
    if (travel == std::numeric_limits<int>::max()) {
        breakdown.push_back({"不可达", -100000.0, "本地 POI 图中无法到达。"});
        return breakdown;
    }
    double travelMultiplier = 1.2;
    if (request.strategy == "low_travel") travelMultiplier = 2.0;
    if (request.strategy == "compact") travelMultiplier = 0.8;
    breakdown.push_back({"通勤惩罚", rounded(-travel * travelMultiplier), "从上一站通勤 " + std::to_string(travel) + " 分钟。"});
    breakdown.push_back({"价格惩罚", rounded(-poi.priceLevel * 3.0), "消费等级 " + std::to_string(poi.priceLevel) + "。"});

    int arrival = currentTime + travel;
    if (arrival < poi.openMinutes) {
        breakdown.push_back({"等待惩罚", rounded(-(poi.openMinutes - arrival) * 0.5), "早于开放时间，需要等待。"});
    }
    if (arrival + poi.visitDurationMinutes > poi.closeMinutes) {
        breakdown.push_back({"闭馆惩罚", -1000.0, "预计结束时间超过关闭时间。"});
    }
    
    // === Type diversity bonus ===
    int attractionCount = 0, restaurantCount = 0;
    for (const auto& usedId : used) {
        const Poi* usedPoi = graph_.findPoi(usedId);
        if (!usedPoi) continue;
        if (usedPoi->type == PoiType::Attraction) attractionCount++;
        else if (usedPoi->type == PoiType::Restaurant) restaurantCount++;
    }
    if (poi.type == PoiType::Attraction && attractionCount > restaurantCount + 1) {
        breakdown.push_back({"\xe7\xb1\xbb\xe5\x9e\x8b\xe5\xa4\x9a\xe6\xa0\xb7", -15.0, "\xe6\x99\xaf\xe7\x82\xb9\xe8\xbf\x87\xe5\xa4\x9a\xef\xbc\x8c\xe5\x81\x8f\xe5\xa5\xbd\xe5\xa4\x9a\xe6\xa0\xb7\xe6\x80\xa7\xe3\x80\x82"});
    }
    if (poi.type == PoiType::Restaurant && restaurantCount < attractionCount) {
        breakdown.push_back({"\xe7\xb1\xbb\xe5\x9e\x8b\xe5\xa4\x9a\xe6\xa0\xb7", 12.0, "\xe7\x94\xa8\xe9\xa4\x90\xe6\x97\xb6\xe6\xae\xb5\xe5\x8a\xa0\xe5\x88\x86\xe3\x80\x82"});
    }

    // === Area diversity bonus ===
    std::set<std::string> visitedAreas;
    for (const auto& usedId : used) {
        const Poi* usedPoi = graph_.findPoi(usedId);
        if (usedPoi && !usedPoi->area.empty()) visitedAreas.insert(usedPoi->area);
    }
    if (!poi.area.empty() && visitedAreas.count(poi.area) == 0) {
        breakdown.push_back({"\xe5\x8c\xba\xe5\x9f\x9f\xe5\xa4\x9a\xe6\xa0\xb7", 8.0, "\xe6\x8e\xa2\xe7\xb4\xa2\xe6\x96\xb0\xe5\x8c\xba\xe5\x9f\x9f\xe5\xa2\x9e\xe5\x8a\xa0\xe5\xa4\x9a\xe6\xa0\xb7\xe6\x80\xa7\xe3\x80\x82"});
    }

    // === Time-appropriate bonus ===
    if (poi.type == PoiType::Restaurant) {
        bool isLunchTime = (arrival >= 660 && arrival <= 780);
        bool isDinnerTime = (arrival >= 1020 && arrival <= 1200);
        if (isLunchTime) breakdown.push_back({"\xe6\x97\xb6\xe9\x97\xb4\xe9\x80\x82\xe9\x85\x8d", 18.0, "\xe5\x8d\x88\xe9\xa4\x90\xe6\x97\xb6\xe6\xae\xb5\xe3\x80\x82"});
        else if (isDinnerTime) breakdown.push_back({"\xe6\x97\xb6\xe9\x97\xb4\xe9\x80\x82\xe9\x85\x8d", 18.0, "\xe6\x99\x9a\xe9\xa4\x90\xe6\x97\xb6\xe6\xae\xb5\xe3\x80\x82"});
        else breakdown.push_back({"\xe6\x97\xb6\xe9\x97\xb4\xe9\x80\x82\xe9\x85\x8d", -10.0, "\xe9\x9d\x9e\xe7\x94\xa8\xe9\xa4\x90\xe6\x97\xb6\xe6\xae\xb5\xe3\x80\x82"});
    }
    if (poi.type == PoiType::Nightlife && arrival >= 1080) {
        breakdown.push_back({"\xe6\x97\xb6\xe9\x97\xb4\xe9\x80\x82\xe9\x85\x8d", 15.0, "\xe5\xa4\x9c\xe9\x97\xb4\xe5\x9c\xba\xe6\x99\xaf\xe3\x80\x82"});
    }

    // === Popularity tier bonus ===
    if (poi.popularity >= 4.7) {
        breakdown.push_back({"\xe9\xa1\xb6\xe7\xba\xa7\xe6\x99\xaf\xe7\x82\xb9", 10.0, "\xe5\xbf\x85\xe7\x9c\x8b\xe9\xa1\xb6\xe7\xba\xa7\xe6\x99\xaf\xe7\x82\xb9\xe3\x80\x82"});
    } else if (poi.popularity >= 4.3) {
        breakdown.push_back({"\xe9\xa1\xb6\xe7\xba\xa7\xe6\x99\xaf\xe7\x82\xb9", 5.0, "\xe9\xab\x98\xe5\x88\x86\xe6\x99\xaf\xe7\x82\xb9\xe3\x80\x82"});
    }

    return breakdown;
}

double TripPlanner::scorePoi(const TripRequest& request, const Poi& poi, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const {
    return breakdownTotal(buildScoreBreakdown(request, poi, currentPoiId, currentTime, used));
}

const Poi* TripPlanner::chooseBestPoi(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used, bool nightOnly) const {
    const Poi* best = nullptr;
    double bestScore = -100000.0;
    for (const auto& poi : graph_.pois()) {
        if (nightOnly && poi.type != PoiType::Nightlife) continue;
        if (!nightOnly && poi.type != PoiType::Attraction && poi.type != PoiType::Nightlife) continue;
        if (isHardAvoidedPoi(request, poi)) continue;
        double score = scorePoi(request, poi, currentPoiId, currentTime, used);
        if (score > bestScore) {
            bestScore = score;
            best = &poi;
        }
    }
    return bestScore > -999.0 ? best : nullptr;
}

const Poi* TripPlanner::chooseMustVisit(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const {
    const Poi* best = nullptr;
    double bestScore = -100000.0;
    for (const auto& must : request.mustVisit) {
        const Poi* poi = graph_.findPoi(must);
        if (!poi || used.count(poi->id) > 0) {
            continue;
        }
        double score = scorePoi(request, *poi, currentPoiId, currentTime, used);
        if (score > bestScore) {
            bestScore = score;
            best = poi;
        }
    }
    return bestScore > -999.0 ? best : nullptr;
}

const Poi* TripPlanner::chooseRestaurant(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const {
    const Poi* best = nullptr;
    double bestScore = -100000.0;
    for (const auto& poi : graph_.pois()) {
        if (poi.type != PoiType::Restaurant || used.count(poi.id) > 0) continue;
        // Brand dedup: skip same-brand restaurants
        {
            std::string brand = extractBrand(poi.name);
            bool brandUsed = false;
            for (const auto& usedId : used) {
                const Poi* usedPoi = graph_.findPoi(usedId);
                if (usedPoi && extractBrand(usedPoi->name) == brand) {
                    brandUsed = true; break;
                }
            }
            if (brandUsed) continue;
        }
        // For meal slots, only pick main restaurants (not drinks/snacks)
        if (poi.mealType != "main") continue;
        if (isHardAvoidedPoi(request, poi)) continue;
        int travel = graph_.shortestMinutes(currentPoiId, poi.id);
        if (travel == std::numeric_limits<int>::max()) continue;
        double score = poi.popularity * 10.0 - travel * 1.5 - poi.priceLevel * 2.0;
        for (const auto& interest : request.interests) {
            if (containsText(poi.tags, interest)) score += 20.0;
        }
        int arrival = currentTime + travel;
        if (arrival + poi.visitDurationMinutes > poi.closeMinutes || arrival < poi.openMinutes - 30) {
            score -= 200.0;
        }
        if (score > bestScore) {
            bestScore = score;
            best = &poi;
        }
    }
    return best;
}

std::vector<const Poi*> TripPlanner::rankedPoisForSlot(const TripRequest& request, const std::string& slot, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const {
    std::vector<RankedPoiCandidate> coarseCandidates;
    for (const auto& poi : graph_.pois()) {
        if (used.count(poi.id) > 0) continue;
        if (isHardAvoidedPoi(request, poi)) continue;
        if (!slotAcceptsPoi(slot, poi)) continue;
        // Brand dedup: skip same-brand restaurants/tea shops
        if (isMealSlot(slot) || poi.type == PoiType::Restaurant) {
            std::string brand = extractBrand(poi.name);
            bool brandUsed = false;
            for (const auto& usedId : used) {
                const Poi* usedPoi = graph_.findPoi(usedId);
                if (usedPoi && extractBrand(usedPoi->name) == brand) {
                    brandUsed = true;
                    break;
                }
            }
            if (brandUsed) continue;
        }
        int travel = graph_.shortestMinutes(currentPoiId, poi.id);
        if (travel == std::numeric_limits<int>::max()) continue;
        int arrival = currentTime + travel;
        if (arrival + poi.visitDurationMinutes > poi.closeMinutes && !isMustVisitPoi(request, poi)) continue;
        double coarseScore = coarseCandidateScore(request, poi, travel, currentTime);
        if (coarseScore > -999.0 || isMustVisitPoi(request, poi)) {
            coarseCandidates.push_back({&poi, -100000.0, travel, coarseScore, isMustVisitPoi(request, poi)});
        }
    }

    std::stable_sort(coarseCandidates.begin(), coarseCandidates.end(), [](const RankedPoiCandidate& left, const RankedPoiCandidate& right) {
        if (left.mustVisit != right.mustVisit) {
            return left.mustVisit;
        }
        return left.coarseScore > right.coarseScore;
    });

    const size_t maxScoredPool = 80;
    std::vector<RankedPoiCandidate> scoredCandidates;
    scoredCandidates.reserve(std::min(coarseCandidates.size(), maxScoredPool));
    size_t ordinaryKept = 0;
    for (const auto& candidate : coarseCandidates) {
        if (!candidate.mustVisit && ordinaryKept >= maxScoredPool) {
            continue;
        }
        RankedPoiCandidate scored = candidate;
        scored.score = scorePoi(request, *candidate.poi, currentPoiId, currentTime, used);
        if (scored.score > -999.0 || scored.mustVisit) {
            scoredCandidates.push_back(scored);
            if (!scored.mustVisit) {
                ++ordinaryKept;
            }
        }
    }

    std::sort(scoredCandidates.begin(), scoredCandidates.end(), [](const RankedPoiCandidate& left, const RankedPoiCandidate& right) {
        if (std::abs(left.score - right.score) > 0.01) {
            return left.score > right.score;
        }
        return left.travelMinutes < right.travelMinutes;
    });

    const size_t maxBranching = static_cast<size_t>(plannerBranchFactor());
    if (scoredCandidates.size() > maxBranching) {
        scoredCandidates.resize(maxBranching);
    }

    std::vector<const Poi*> candidates;
    candidates.reserve(scoredCandidates.size());
    for (const auto& candidate : scoredCandidates) {
        candidates.push_back(candidate.poi);
    }
    return candidates;
}

Stop TripPlanner::makeStop(const std::string& slot, const Poi& poi, int startMinutes, int travelMinutes, double score, const TripRequest& request) const {
    int actualStart = std::max(startMinutes, poi.openMinutes);
    Stop stop;
    stop.slot = slot;
    stop.poiId = poi.id;
    stop.poiName = poi.name;
    stop.poiType = poiTypeToString(poi.type);
    stop.mealType = poi.mealType;
    stop.recommendation = poi.recommendation;
    stop.area = poi.area;
    stop.lat = poi.lat;
    stop.lng = poi.lng;
    stop.imageUrl = poi.imageUrl;
    stop.guideText = poi.guideText;
    stop.startMinutes = actualStart;
    stop.endMinutes = actualStart + poi.visitDurationMinutes;
    stop.visitDurationMinutes = poi.visitDurationMinutes;
    stop.travelMinutesFromPrevious = travelMinutes;
    stop.openTimeMatched = actualStart >= poi.openMinutes && stop.endMinutes <= poi.closeMinutes;
    stop.timeWindowStatus = stop.openTimeMatched ? "ok" : (actualStart < poi.openMinutes ? "wait" : "closed");
    stop.timeWindowReason = timeWindowIssueReason(stop, &poi, 0, request.endMinutes);
    stop.score = std::round(score * 10.0) / 10.0;

    std::ostringstream reason;
    reason << "决策依据：" << poi.name << " 位于" << poi.area << "，";
    bool matched = false;
    for (const auto& interest : request.interests) {
        if (containsText(poi.tags, interest)) {
            reason << "匹配「" << interest << "」偏好，";
            matched = true;
            break;
        }
    }
    if (!matched) {
        reason << "热度和路线顺序较合适，";
    }
    reason << "从上一站通勤 " << travelMinutes << " 分钟，"
           << "评分 " << stop.score << "，"
           << "预计停留 " << poi.visitDurationMinutes << " 分钟。";
    if (stop.openTimeMatched) {
        reason << "开放时间满足当前时间窗。";
    } else {
        reason << "开放时间存在风险，演示时可说明这是约束惩罚项。";
    }
    stop.reason = reason.str();
    return stop;
}

bool TripPlanner::routeOrderFeasible(const std::string& startId, const std::vector<Stop>& stops) const {
    std::string currentId = startId;
    int previousEnd = 0;
    for (const auto& stop : stops) {
        const Poi* poi = graph_.findPoi(stop.poiId);
        int travel = graph_.shortestMinutes(currentId, stop.poiId);
        if (!poi || travel == std::numeric_limits<int>::max()) {
            return false;
        }
        if (previousEnd > 0 && stop.startMinutes < previousEnd + travel) {
            return false;
        }
        if (isMealSlot(stop.slot) && (stop.startMinutes < mealWindowStart(stop.slot) || stop.endMinutes > mealWindowEnd(stop.slot))) {
            return false;
        }
        if (stop.startMinutes < poi->openMinutes || stop.endMinutes > poi->closeMinutes) {
            return false;
        }
        previousEnd = stop.endMinutes;
        currentId = stop.poiId;
    }
    return true;
}

void TripPlanner::validateDayTimeWindows(const TripRequest& request, DayPlan& day) const {
    day.timeWindowDiagnostics.clear();
    day.timeWindowFeasible = true;
    int previousEnd = request.startMinutes;

    for (auto& stop : day.stops) {
        const Poi* poi = graph_.findPoi(stop.poiId);
        std::string status = timeWindowIssueStatus(stop, poi, previousEnd, request.endMinutes);
        std::string reason = timeWindowIssueReason(stop, poi, previousEnd, request.endMinutes);
        stop.timeWindowStatus = status;
        stop.timeWindowReason = reason;
        stop.openTimeMatched = status == "ok";
        day.timeWindowDiagnostics.push_back(reason);
        if (status != "ok") {
            day.timeWindowFeasible = false;
        }
        previousEnd = std::max(previousEnd, stop.endMinutes);
    }

    if (day.stops.empty()) {
        day.timeWindowDiagnostics.push_back("当日没有可安排站点，时间窗复核无可检查对象。");
    } else if (day.timeWindowFeasible) {
        day.timeWindowDiagnostics.push_back("最终顺序已通过统一时间窗复核：站点顺序、开放时间、餐饮窗口和当日结束时间均可行。");
    }
}

DayPlan TripPlanner::planDayWithBeamSearch(const TripRequest& request, int day, const std::string& hotelId, std::set<std::string>& used) const {
    const int beamWidth = plannerBeamWidth();
    const int breakMinutes = paceExtraBreakMinutes(request.pace);
    const std::vector<std::string> slots = {"上午", "午餐", "下午", "下午茶", "晚餐", "晚上"};

    BeamState initial;
    initial.used = used;
    initial.currentId = hotelId;
    initial.currentTime = request.startMinutes;
    std::vector<BeamState> beam = {initial};

    DayPlan dayPlan;
    dayPlan.day = day;

    for (const auto& slot : slots) {
        BeamTraceEntry trace;
        trace.slot = slot;
        trace.inputStates = static_cast<int>(beam.size());
        std::vector<BeamState> expanded;
        for (const auto& state : beam) {
            int slotStart = state.currentTime;
            if (slot == "午餐" && slotStart < 11 * 60 + 30) slotStart = 11 * 60 + 30;
            if (slot == "下午茶" && slotStart < 14 * 60 + 30) slotStart = 14 * 60 + 30;
            if (slot == "晚餐" && slotStart < 17 * 60 + 30) slotStart = 17 * 60 + 30;

            for (const Poi* poi : rankedPoisForSlot(request, slot, state.currentId, slotStart, state.used)) {
                int travel = graph_.shortestMinutes(state.currentId, poi->id);
                if (travel == std::numeric_limits<int>::max()) continue;
                double score = scorePoi(request, *poi, state.currentId, slotStart, state.used);
                Stop stop = makeStop(slot, *poi, slotStart + travel, travel, score, request);
                stop.scoreBreakdown = buildScoreBreakdown(request, *poi, state.currentId, slotStart, state.used);
                if (stop.endMinutes > request.endMinutes) continue;
                if (isMealSlot(slot) && (stop.startMinutes < mealWindowStart(slot) || stop.endMinutes > mealWindowEnd(slot))) continue;

                BeamState next = state;
                next.stops.push_back(stop);
                next.used.insert(poi->id);
                next.currentId = poi->id;
                next.currentTime = stop.endMinutes + breakMinutes;
                next.totalTravelMinutes += travel;
                next.totalVisitMinutes += stop.visitDurationMinutes;
                next.interestScore += std::max(0.0, stop.score);
                expanded.push_back(next);
            }
        }

        trace.expandedStates = static_cast<int>(expanded.size());
        if (expanded.empty()) {
            trace.keptStates = static_cast<int>(beam.size());
            trace.decision = "该时间槽没有可行扩展，保留上一轮 Beam 状态继续后续时间槽。";
            for (size_t i = 0; i < beam.size() && i < 3; ++i) {
                trace.keptStateSummaries.push_back(summarizeBeamState(request, beam[i]));
            }
            dayPlan.beamTrace.push_back(trace);
            continue;
        }
        std::sort(expanded.begin(), expanded.end(), [&](const BeamState& left, const BeamState& right) {
            double leftScore = beamStateScore(request, left);
            double rightScore = beamStateScore(request, right);
            if (std::abs(leftScore - rightScore) > 0.01) {
                return leftScore > rightScore;
            }
            return left.totalTravelMinutes < right.totalTravelMinutes;
        });
        if (static_cast<int>(expanded.size()) > beamWidth) {
            expanded.resize(static_cast<size_t>(beamWidth));
        }
        trace.keptStates = static_cast<int>(expanded.size());
        trace.decision = "按 Beam 状态评分保留 Top-" + std::to_string(trace.keptStates) +
                         "；每个状态先做候选池召回与粗筛，保留必去点并裁剪普通候选后再评分，最终综合兴趣、通勤惩罚和站点覆盖。";
        for (size_t i = 0; i < expanded.size() && i < 3; ++i) {
            trace.keptStateSummaries.push_back(summarizeBeamState(request, expanded[i]));
        }
        dayPlan.beamTrace.push_back(trace);
        beam = expanded;
    }

    const BeamState& best = beam.front();
    used = best.used;

    dayPlan.stops = best.stops;
    dayPlan.totalTravelMinutes = best.totalTravelMinutes;
    dayPlan.totalVisitMinutes = best.totalVisitMinutes;
    dayPlan.interestScore = best.interestScore;

    std::ostringstream summary;
    summary << "第 " << day << " 天围绕";
    if (!dayPlan.stops.empty()) {
        summary << dayPlan.stops.front().area;
    } else if (const Poi* hotel = graph_.findPoi(hotelId)) {
        summary << hotel->area;
    } else {
        summary << "酒店周边";
    }
    summary << "展开，Beam Search 在每个时间槽保留最多 " << beamWidth
            << " 个候选状态，综合评分、通勤、开放时间和必去点覆盖后选择当前路线。演示重点："
            << request.pace << "节奏，优先匹配"
            << joinTags(request.interests)
            << "，同时检查开放时间、餐饮窗口和必去点覆盖。";
    dayPlan.summary = summary.str();

    optimizeDayOrder(hotelId, dayPlan);
    dayPlan.optimizationSummary = "Beam Search 已先完成 Top-K 局部路径选择；" + dayPlan.optimizationSummary;
    validateDayTimeWindows(request, dayPlan);
    explainDayConstraints(request, used, dayPlan);
    return dayPlan;
}

void TripPlanner::optimizeDayOrder(const std::string& startId, DayPlan& day) const {
    day.originalTravelMinutes = routeTravelMinutes(startId, day.stops);
    day.optimizedTravelMinutes = day.originalTravelMinutes;
    if (day.stops.size() < 4) {
        day.optimizationSummary = "当日站点较少，算法保持原顺序；通勤成本仍来自 POI 图最短路。";
        return;
    }

    std::vector<Stop> candidateStops = day.stops;
    bool improved = true;
    while (improved) {
        improved = false;
        for (size_t i = 0; i < candidateStops.size(); ++i) {
            if (candidateStops[i].slot == "午餐" || candidateStops[i].slot == "晚餐" || candidateStops[i].slot == "下午茶") continue;
            for (size_t j = i + 1; j < candidateStops.size(); ++j) {
                if (candidateStops[j].slot == "午餐" || candidateStops[j].slot == "晚餐" || candidateStops[j].slot == "下午茶") continue;
                std::swap(candidateStops[i], candidateStops[j]);
                int candidateTravel = routeTravelMinutes(startId, candidateStops);
                if (candidateTravel < day.optimizedTravelMinutes && routeOrderFeasible(startId, candidateStops)) {
                    day.optimizedTravelMinutes = candidateTravel;
                    improved = true;
                } else {
                    std::swap(candidateStops[i], candidateStops[j]);
                }
            }
        }
    }

    int saved = std::max(0, day.originalTravelMinutes - day.optimizedTravelMinutes);
    std::ostringstream summary;
    summary << "算法用日内局部交换评估通勤潜力：当前时间轴通勤 " << day.originalTravelMinutes
            << " 分钟，理论更优顺序 " << day.optimizedTravelMinutes
            << " 分钟，可节省 " << saved << " 分钟；只有同时满足开放时间、餐饮窗口和站点顺序的交换才计入收益。";
    day.optimizationSummary = summary.str();

    // Write back optimized order if improvement found
    if (saved > 0) {
        day.stops = candidateStops;
    }
}

void TripPlanner::explainDayConstraints(const TripRequest& request, const std::set<std::string>& used, DayPlan& day) const {
    int lunchCount = 0;
    int dinnerCount = 0;
    int teaCount = 0;
    for (const auto& stop : day.stops) {
        if (stop.openTimeMatched) {
            day.constraintExplanations.push_back(stop.poiName + " 命中开放时间约束。");
        } else {
            day.constraintExplanations.push_back(stop.poiName + " 存在开放时间约束风险。");
        }
        if (stop.slot == "午餐") ++lunchCount;
        if (stop.slot == "晚餐") ++dinnerCount;
        if (stop.slot == "下午茶") ++teaCount;
        if (containsText(request.mustVisit, stop.poiName) || containsText(request.mustVisit, stop.poiId)) {
            day.constraintExplanations.push_back(stop.poiName + " 属于必去点，已优先安排。");
        }
    }
    if (lunchCount > 0) day.constraintExplanations.push_back("午餐已按 11:30-13:30 时间窗插入。");
    if (teaCount > 0) day.constraintExplanations.push_back("下午茶已按 14:30-16:30 时间窗插入。");
    if (dinnerCount > 0) day.constraintExplanations.push_back("晚餐已按 17:30-19:30 时间窗插入。");
    day.constraintExplanations.push_back("算法约束：当日通勤成本来自本地 POI 图最短路计算。");

    for (const auto& must : request.mustVisit) {
        const Poi* poi = graph_.findPoi(must);
        if (!poi) {
            day.unscheduledReasons.push_back(must + " 未安排：样例数据中不存在该 POI，演示时可作为输入校验说明。");
        } else if (used.count(poi->id) == 0) {
            day.unscheduledReasons.push_back(poi->name + " 未安排：当日时间预算、开放时间或通勤成本约束不足。");
        }
    }
    if (day.unscheduledReasons.empty()) {
        day.unscheduledReasons.push_back("必去点均已安排或已在其他日期覆盖，未安排列表用于解释约束取舍。");
    }
}

ComparisonMetrics TripPlanner::buildComparisonMetrics(const TripRequest& request, const Itinerary& itinerary) const {
    ComparisonMetrics metrics;
    std::set<std::string> coveredMustVisits;
    for (const auto& day : itinerary.days) {
        metrics.totalTravelMinutes += day.totalTravelMinutes;
        metrics.totalVisitMinutes += day.totalVisitMinutes;
        for (const auto& reason : day.unscheduledReasons) {
            if (reason.find(" 未安排：") != std::string::npos) {
                ++metrics.unscheduledCount;
            }
        }
        for (const auto& stop : day.stops) {
            ++metrics.totalStops;
            if (!stop.openTimeMatched) {
                ++metrics.openTimeRisks;
            }
            for (const auto& must : request.mustVisit) {
                if (must == stop.poiName || must == stop.poiId) {
                    coveredMustVisits.insert(must);
                }
            }
        }
    }
    metrics.mustVisitCovered = static_cast<int>(coveredMustVisits.size());
    metrics.totalScore = itinerary.totalScore;
    metrics.tradeoffSummary = "待进行多目标非支配排序。";
    return metrics;
}

void TripPlanner::assignParetoRanks(std::vector<Itinerary>& candidates) const {
    std::vector<bool> assigned(candidates.size(), false);
    int rank = 1;
    size_t assignedCount = 0;

    while (assignedCount < candidates.size()) {
        std::vector<size_t> front;
        for (size_t i = 0; i < candidates.size(); ++i) {
            if (assigned[i]) continue;
            bool dominatedByRemaining = false;
            for (size_t j = 0; j < candidates.size(); ++j) {
                if (i == j || assigned[j]) continue;
                if (dominates(candidates[j].comparison, candidates[i].comparison)) {
                    dominatedByRemaining = true;
                    break;
                }
            }
            if (!dominatedByRemaining) {
                front.push_back(i);
            }
        }

        if (front.empty()) {
            break;
        }
        for (size_t index : front) {
            candidates[index].comparison.paretoRank = rank;
            candidates[index].comparison.dominated = rank > 1;
            assigned[index] = true;
            ++assignedCount;
        }
        ++rank;
    }

    for (auto& candidate : candidates) {
        if (candidate.comparison.paretoRank < 1) {
            candidate.comparison.paretoRank = rank;
            candidate.comparison.dominated = true;
        }

        std::ostringstream summary;
        if (!candidate.comparison.dominated) {
            summary << "标准非支配分层 Pareto 第 1 层：在评分、通勤、风险和必去覆盖之间没有被其他候选完全支配。";
            candidate.comparison.paretoDebug.push_back("未发现其他候选在总分、必去覆盖、通勤、开放时间风险和未安排数量上同时不差且至少一项更优。");
        } else {
            summary << "标准非支配分层 Pareto 第 " << candidate.comparison.paretoRank
                    << " 层：移除更优前沿后进入下一层，说明该方案在至少一个目标上有取舍成本。";
            candidate.comparison.paretoDebug.push_back("存在更高层候选在多目标指标上形成支配或近似支配关系。");
        }
        std::ostringstream metrics;
        metrics << "指标向量：score=" << candidate.comparison.totalScore
                << ", must=" << candidate.comparison.mustVisitCovered
                << ", travel=" << candidate.comparison.totalTravelMinutes
                << ", risk=" << candidate.comparison.openTimeRisks
                << ", unscheduled=" << candidate.comparison.unscheduledCount;
        candidate.comparison.paretoDebug.push_back(metrics.str());
        candidate.comparison.tradeoffSummary = summary.str();
    }
}

void TripPlanner::assignDiversityMetrics(std::vector<Itinerary>& candidates) const {
    if (candidates.empty()) {
        return;
    }

    const std::set<std::string> baselinePoiIds = collectPoiIds(candidates.front());
    const std::set<std::string> baselineAreas = collectAreas(candidates.front());

    for (size_t index = 0; index < candidates.size(); ++index) {
        auto& candidate = candidates[index];
        const std::set<std::string> poiIds = collectPoiIds(candidate);
        const std::set<std::string> areas = collectAreas(candidate);
        std::vector<std::string> uniqueNames = collectUniquePoiNames(candidate, baselinePoiIds);

        candidate.comparison.poiOverlapWithBaseline = overlapRatio(poiIds, baselinePoiIds);
        candidate.comparison.areaOverlapWithBaseline = overlapRatio(areas, baselineAreas);
        candidate.comparison.uniquePoiCount = static_cast<int>(uniqueNames.size());
        candidate.comparison.uniquePois = uniqueNames;
        candidate.comparison.diversityTags.clear();

        if (index == 0) {
            candidate.comparison.poiOverlapWithBaseline = 1.0;
            candidate.comparison.areaOverlapWithBaseline = 1.0;
            candidate.comparison.uniquePoiCount = 0;
            candidate.comparison.uniquePois.clear();
            candidate.comparison.diversityTags.push_back("基线方案");
            candidate.comparison.diversitySummary = "作为候选对比基线，其他方案会计算相对它的 POI 和区域差异。";
            continue;
        }

        candidate.comparison.diversityTags.push_back(diversityLevel(candidate.comparison.poiOverlapWithBaseline, candidate.comparison.uniquePoiCount));
        candidate.comparison.diversityTags.push_back(strategyDiversityTag(candidate.strategy));
        if (candidate.comparison.areaOverlapWithBaseline <= 0.6) {
            candidate.comparison.diversityTags.push_back("区域路径差异");
        }
        if (candidate.comparison.uniquePoiCount > 0) {
            candidate.comparison.diversityTags.push_back("包含独有 POI");
        }

        std::ostringstream summary;
        summary << "相对基线 POI 重合率 " << static_cast<int>(std::round(candidate.comparison.poiOverlapWithBaseline * 100))
                << "%，区域重合率 " << static_cast<int>(std::round(candidate.comparison.areaOverlapWithBaseline * 100))
                << "%，独有 POI " << candidate.comparison.uniquePoiCount << " 个";
        if (!candidate.comparison.uniquePois.empty()) {
            summary << "：";
            for (size_t i = 0; i < candidate.comparison.uniquePois.size() && i < 3; ++i) {
                if (i > 0) summary << "、";
                summary << candidate.comparison.uniquePois[i];
            }
        }
        summary << "。";
        candidate.comparison.diversitySummary = summary.str();
    }
}

Itinerary TripPlanner::plan(const TripRequest& request) const {
    const Poi* hotel = chooseHotel(request);
    if (!hotel) {
        throw std::runtime_error("该城市暂无酒店数据，无法生成行程。请确认城市数据中包含酒店类型的 POI。");
    }

    Itinerary itinerary;
    itinerary.city = request.city;
    itinerary.hotel = {hotel->id, hotel->name, hotel->area, hotel->lat, hotel->lng, hotel->popularity};
    itinerary.variantName = request.pace + "节奏方案";
    itinerary.strategy = request.strategy;
    std::set<std::string> used;

    for (int day = 1; day <= request.days; ++day) {
        DayPlan dayPlan = planDayWithBeamSearch(request, day, hotel->id, used);
        itinerary.totalScore += dayPlan.interestScore;
        itinerary.days.push_back(dayPlan);
    }

    itinerary.alternatives = {
        "下雨时可将户外景点替换为室内展馆、咖啡馆或商场休闲。",
        "如果体力不足，可减少下午景点并延长餐饮和休息时间。",
        "预算降低时优先选择公共交通可达区域和平价餐饮。"
    };
    itinerary.totalScore = std::round(itinerary.totalScore * 10.0) / 10.0;
    itinerary.comparison = buildComparisonMetrics(request, itinerary);
    return itinerary;
}

std::vector<Itinerary> TripPlanner::planCandidates(const TripRequest& request) const {
    std::vector<Itinerary> candidates;
    std::vector<TripRequest> variants;
    std::vector<std::string> names;
    std::vector<std::string> focuses;

    TripRequest relaxed = request;
    relaxed.pace = "轻松";
    relaxed.strategy = "low_travel";
    variants.push_back(relaxed);
    names.push_back("轻松少走路方案");
    focuses.push_back("提高通勤惩罚并偏好同区域活动，适合展示体力友好取舍。");

    TripRequest compact = request;
    compact.pace = "紧凑";
    compact.strategy = "compact";
    variants.push_back(compact);
    names.push_back("紧凑多覆盖方案");
    focuses.push_back("降低通勤惩罚并提高覆盖权重，适合展示时间窗调度。");

    TripRequest culture = request;
    culture.strategy = "culture";
    culture.interests = {"历史文化", "博物馆", "古建筑"};
    variants.push_back(culture);
    names.push_back("文化优先方案");
    focuses.push_back("加权博物馆、书院、古建筑和寺庙，展示主题化候选。");

    TripRequest food = request;
    food.strategy = "food";
    food.interests = {"美食", "小吃", "夜景"};
    variants.push_back(food);
    names.push_back("美食优先方案");
    focuses.push_back("加权餐饮、小吃街和夜间美食场景，展示美食路线。");

    TripRequest rainy = request;
    rainy.strategy = "rainy";
    rainy.interests = {"室内", "历史文化", "美食"};
    variants.push_back(rainy);
    names.push_back("雨天室内方案");
    focuses.push_back("加权室内 POI 并降低户外点优先级，展示场景化替换。");

    for (size_t index = 0; index < variants.size(); ++index) {
        if (static_cast<int>(candidates.size()) >= request.candidateCount) break;
        auto variant = variants[index];
        Itinerary itinerary = plan(variant);
        // Build signature including variant name to preserve strategy diversity
        std::string signature = names[index] + ":";
        for (const auto& day : itinerary.days) {
            for (const auto& stop : day.stops) {
                signature += stop.poiId + "|";
            }
            signature += ";";
        }
        bool duplicate = false;
        for (const auto& existing : candidates) {
            std::string existingSig = existing.variantName + ":";
            for (const auto& day : existing.days) {
                for (const auto& stop : day.stops) {
                    existingSig += stop.poiId + "|";
                }
                existingSig += ";";
            }
            if (signature == existingSig) {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) {
            itinerary.variantName = names[index];
            annotateVariantFocus(itinerary, focuses[index]);
            candidates.push_back(itinerary);
        }
    }

    while (static_cast<int>(candidates.size()) < request.candidateCount && !candidates.empty()) {
        int offsetMinutes = static_cast<int>(candidates.size()) * 15;
        TripRequest variant = request;
        variant.startMinutes += offsetMinutes;
        variant.strategy = "balanced";
        Itinerary itinerary = plan(variant);
        itinerary.variantName = "错峰出发 +" + std::to_string(offsetMinutes) + " 分钟方案";
        annotateVariantFocus(itinerary, "延后出发 " + std::to_string(offsetMinutes) + " 分钟，展示时间窗变化对安排结果的影响。");
        candidates.push_back(itinerary);
    }
    assignDiversityMetrics(candidates);
    assignParetoRanks(candidates);
    return candidates;
}

}  // namespace tourpass
