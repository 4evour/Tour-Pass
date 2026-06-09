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

// Extract brand name from POI name (e.g. "鑼堕鎮﹁壊(铦磋澏澶у帵搴?" -> "鑼堕鎮﹁壊")
std::string extractBrand(const std::string& name) {
    auto pos = name.find('(');
    if (pos == std::string::npos) pos = name.find('锛?);
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
        return "鐑害銆佹椂闂寸獥鍜岄€氬嫟鎴愭湰";
    }
    std::ostringstream out;
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) out << "銆?;
        out << values[i];
    }
    return out.str();
}

void annotateVariantFocus(Itinerary& itinerary, const std::string& focus) {
    for (auto& day : itinerary.days) {
        if (day.summary.find("婕旂ず閲嶇偣") == std::string::npos) {
            day.summary += " 婕旂ず閲嶇偣锛? + focus;
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
    if (poiOverlap <= 0.35 || uniquePoiCount >= 4) return "楂樺樊寮?;
    if (poiOverlap <= 0.65 || uniquePoiCount >= 2) return "涓樊寮?;
    return "浣庡樊寮?;
}

std::string strategyDiversityTag(const std::string& strategy) {
    if (strategy == "low_travel") return "浣撳姏鍙嬪ソ宸紓";
    if (strategy == "compact") return "瑕嗙洊瀵嗗害宸紓";
    if (strategy == "culture") return "鏂囧寲涓婚宸紓";
    if (strategy == "food") return "缇庨涓婚宸紓";
    if (strategy == "rainy") return "闆ㄥぉ鍦烘櫙宸紓";
    return "鏃堕棿鍋忕Щ宸紓";
}

int mealWindowStart(const std::string& slot) {
    if (slot == "鍗堥") return 11 * 60 + 30;
    if (slot == "涓嬪崍鑼?) return 14 * 60 + 30;
    if (slot == "鏅氶") return 17 * 60 + 30;
    return -1;
}

int mealWindowEnd(const std::string& slot) {
    if (slot == "鍗堥") return 13 * 60 + 30;
    if (slot == "涓嬪崍鑼?) return 16 * 60 + 30;
    if (slot == "鏅氶") return 19 * 60 + 30;
    return -1;
}

bool isMealSlot(const std::string& slot) {
    return slot == "鍗堥" || slot == "鏅氶" || slot == "涓嬪崍鑼?;
}

bool slotAcceptsPoi(const std::string& slot, const Poi& poi) {
    if (slot == "鍗堥" || slot == "鏅氶") {
        // Lunch/dinner only accept main restaurants (not drinks/snacks)
        return poi.type == PoiType::Restaurant && poi.mealType == "main";
    }
    if (slot == "涓嬪崍鑼?) {
        return poi.type == PoiType::Restaurant && poi.mealType == "drink";
    }
    if (slot == "鏅氫笂") {
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
    if (request.strategy == "culture" && hasAnyTag(poi, {"鍘嗗彶鏂囧寲", "鍗氱墿棣?, "鍙ゅ缓绛?, "涔﹂櫌", "瀵哄簷"})) {
        return 80.0;
    }
    if (request.strategy == "food" && hasAnyTag(poi, {"缇庨", "灏忓悆", "婀樿彍", "澶滃競", "鑼堕ギ", "琛楀尯"})) {
        return 75.0;
    }
    if (request.strategy == "rainy") {
        double bonus = hasTag(poi, "瀹ゅ唴") ? 90.0 : -30.0;
        if (hasTag(poi, "鎴峰")) bonus -= 90.0;
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
        return stop.poiName + " 寮€濮嬫椂闂?" + formatMinutes(stop.startMinutes) +
               " 鏃╀簬涓婁竴绔欑粨鏉?浼戞伅鍚庢椂闂?" + formatMinutes(previousEnd) + "锛屾渶缁堥『搴忎笉鍙銆?;
    }
    if (stop.endMinutes > requestEndMinutes) {
        return stop.poiName + " 棰勮 " + formatMinutes(stop.endMinutes) +
               " 缁撴潫锛岃秴鍑哄綋鏃ョ粨鏉熸椂闂?" + formatMinutes(requestEndMinutes) + "銆?;
    }
    if (isMealSlot(stop.slot) && (stop.startMinutes < mealWindowStart(stop.slot) || stop.endMinutes > mealWindowEnd(stop.slot))) {
        return stop.poiName + " 鐨? + stop.slot + "瀹夋帓涓?" + formatMinutes(stop.startMinutes) + "-" +
               formatMinutes(stop.endMinutes) + "锛屾湭瀹屾暣钀藉湪 " + formatMinutes(mealWindowStart(stop.slot)) +
               "-" + formatMinutes(mealWindowEnd(stop.slot)) + " 椁愰ギ绐楀彛鍐呫€?;
    }
    if (!poi) {
        return stop.poiName + " 鍦?POI 鍥句腑缂哄け锛屾棤娉曞鏍稿紑鏀炬椂闂淬€?;
    }
    if (stop.startMinutes < poi->openMinutes) {
        return stop.poiName + " 棰勮 " + formatMinutes(stop.startMinutes) +
               " 鍒拌揪锛屾棭浜庡紑鏀炬椂闂?" + formatMinutes(poi->openMinutes) +
               "锛岄渶瑕佺瓑寰?" + std::to_string(poi->openMinutes - stop.startMinutes) + " 鍒嗛挓銆?;
    }
    if (stop.endMinutes > poi->closeMinutes) {
        return stop.poiName + " 棰勮 " + formatMinutes(stop.endMinutes) +
               " 绂诲紑锛屼絾 " + formatMinutes(poi->closeMinutes) + " 鍏抽棴锛岃秴鍑?" +
               std::to_string(stop.endMinutes - poi->closeMinutes) + " 鍒嗛挓銆?;
    }
    return stop.poiName + " 鏃堕棿绐楀鏍搁€氳繃锛? + formatMinutes(stop.startMinutes) + "-" +
           formatMinutes(stop.endMinutes) + " 浣嶄簬寮€鏀句笌琛岀▼绾︽潫鍐呫€?;
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
        summary << " path=璧风偣";
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
    if (pace == "杞绘澗") return 20;
    if (pace == "绱у噾") return 0;
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
        breakdown.push_back({"閲嶅鎺掗櫎", -100000.0, "璇?POI 宸插湪褰撳墠琛岀▼涓娇鐢ㄣ€?});
        return breakdown;
    }
    if (isHardAvoidedPoi(request, poi)) {
        breakdown.push_back({"閬垮厤椤圭‖鎺掗櫎", -100000.0, "璇?POI 琚姹傜殑 avoid 鍚嶇О鎴?id 鏄庣‘鎺掗櫎銆?});
        return breakdown;
    }
    if (poi.type == PoiType::Hotel || poi.type == PoiType::Transit) {
        breakdown.push_back({"绫诲瀷鎺掗櫎", -100000.0, "閰掑簵鍜屼氦閫氱珯鐐逛笉浣滀负娓哥帺绔欑偣璇勫垎銆?});
        return breakdown;
    }

    double popularityMultiplier = request.strategy == "compact" ? 12.0 : 10.0;
    breakdown.push_back({"鐑害", rounded(poi.popularity * popularityMultiplier), "POI 鐑害鍩虹鍒嗐€?});
    for (const auto& interest : request.interests) {
        if (containsText(poi.tags, interest)) {
            double interestBonus = request.strategy == "compact" ? 42.0 : 35.0;
            breakdown.push_back({"鍏磋叮鍖归厤", interestBonus, "鍖归厤鐢ㄦ埛鍋忓ソ銆? + interest + "銆嶃€?});
        }
    }
    if (request.strategy == "low_travel") {
        breakdown.push_back({"鐭€氬嫟绛栫暐", 25.0, "杞绘澗鏂规鍋忓ソ鐭€氬嫟鍜屽悓鍖哄煙娲诲姩銆?});
    }
    if (request.strategy == "compact") {
        breakdown.push_back({"绱у噾绛栫暐", 28.0, "绱у噾鏂规鎻愰珮楂樼儹搴﹀拰鍏磋叮鐐硅鐩栨潈閲嶃€?});
    }
    if (request.strategy == "culture" && hasAnyTag(poi, {"鍘嗗彶鏂囧寲", "鍗氱墿棣?, "鍙ゅ缓绛?, "涔﹂櫌", "瀵哄簷"})) {
        breakdown.push_back({"鏂囧寲绛栫暐", 70.0, "鏂囧寲浼樺厛鏂规鍔犳潈鍗氱墿棣嗐€佷功闄€佸彜寤虹瓚绛?POI銆?});
    }
    if (request.strategy == "food" && hasAnyTag(poi, {"缇庨", "灏忓悆", "婀樿彍", "澶滃競", "鑼堕ギ", "琛楀尯"})) {
        breakdown.push_back({"缇庨绛栫暐", 65.0, "缇庨浼樺厛鏂规鍔犳潈椁愰ギ銆佸皬鍚冭鍜屽闂寸編椋熷満鏅€?});
    }
    if (request.strategy == "rainy") {
        if (hasTag(poi, "瀹ゅ唴")) {
            breakdown.push_back({"闆ㄥぉ绛栫暐", 80.0, "闆ㄥぉ鏂规浼樺厛瀹ゅ唴鍜岀ǔ瀹氬紑鏀惧満鎵€銆?});
        } else {
            breakdown.push_back({"闆ㄥぉ绛栫暐", -20.0, "闆ㄥぉ鏂规鏇村亸濂藉鍐呯偣锛岃 POI 涓嶆槸鏄庣‘瀹ゅ唴鍦烘墍銆?});
        }
        if (hasTag(poi, "鎴峰")) {
            breakdown.push_back({"鎴峰鎯╃綒", -80.0, "闆ㄥぉ鏂规闄嶄綆鎴峰鐐逛紭鍏堢骇銆?});
        }
    }
    if (containsText(request.mustVisit, poi.name) || containsText(request.mustVisit, poi.id)) {
        breakdown.push_back({"蹇呭幓鍔犳潈", 120.0, "鍛戒腑鐢ㄦ埛蹇呭幓鍦扮偣銆?});
    }
    for (const auto& avoid : request.avoid) {
        if (poi.description.find(avoid) != std::string::npos || containsText(poi.tags, avoid)) {
            breakdown.push_back({"閬垮厤椤?, -40.0, "鍛戒腑鐢ㄦ埛閬垮厤椤广€? + avoid + "銆嶃€?});
        }
    }

    int travel = graph_.shortestMinutes(currentPoiId, poi.id);
    if (travel == std::numeric_limits<int>::max()) {
        breakdown.push_back({"涓嶅彲杈?, -100000.0, "鏈湴 POI 鍥句腑鏃犳硶鍒拌揪銆?});
        return breakdown;
    }
    double travelMultiplier = 1.2;
    if (request.strategy == "low_travel") travelMultiplier = 2.0;
    if (request.strategy == "compact") travelMultiplier = 0.8;
    breakdown.push_back({"閫氬嫟鎯╃綒", rounded(-travel * travelMultiplier), "浠庝笂涓€绔欓€氬嫟 " + std::to_string(travel) + " 鍒嗛挓銆?});
    breakdown.push_back({"浠锋牸鎯╃綒", rounded(-poi.priceLevel * 3.0), "娑堣垂绛夌骇 " + std::to_string(poi.priceLevel) + "銆?});

    int arrival = currentTime + travel;
    if (arrival < poi.openMinutes) {
        breakdown.push_back({"绛夊緟鎯╃綒", rounded(-(poi.openMinutes - arrival) * 0.5), "鏃╀簬寮€鏀炬椂闂达紝闇€瑕佺瓑寰呫€?});
    }
    if (arrival + poi.visitDurationMinutes > poi.closeMinutes) {
        breakdown.push_back({"闂鎯╃綒", -1000.0, "棰勮缁撴潫鏃堕棿瓒呰繃鍏抽棴鏃堕棿銆?});
    }
    
    // === Type and area diversity bonus (combined loop for performance) ===
    int attractionCount = 0, restaurantCount = 0;
    std::set<std::string> visitedAreas;
    for (const auto& usedId : used) {
        const Poi* usedPoi = graph_.findPoi(usedId);
        if (!usedPoi) continue;
        if (usedPoi->type == PoiType::Attraction) attractionCount++;
        else if (usedPoi->type == PoiType::Restaurant) restaurantCount++;
        if (!usedPoi->area.empty()) visitedAreas.insert(usedPoi->area);
    }
    if (poi.type == PoiType::Attraction && attractionCount > restaurantCount + 1) {
        breakdown.push_back({"类型多样性", -15.0, "景点过多，建议穿插餐饮。"});
    }
    if (poi.type == PoiType::Restaurant && restaurantCount < attractionCount) {
        breakdown.push_back({"类型多样性", 12.0, "适合安排用餐休息。"});
    }
    if (!poi.area.empty() && visitedAreas.count(poi.area) == 0) {
        breakdown.push_back({"区域多样性", 8.0, "新区域增加丰富度。"});
    }

    // === Time-appropriate bonus ===
    if (poi.type == PoiType::Restaurant) {
        bool isLunchTime = (arrival >= 660 && arrival <= 780);
        bool isDinnerTime = (arrival >= 1020 && arrival <= 1200);
        if (isLunchTime) breakdown.push_back({"时间契合", 18.0, "午餐时段。"});
        else if (isDinnerTime) breakdown.push_back({"时间契合", 18.0, "晚餐时段。"});
        else breakdown.push_back({"时间契合", -10.0, "非用餐时段。"});
    }
    if (poi.type == PoiType::Nightlife && arrival >= 1080) {
        breakdown.push_back({"时间契合", 15.0, "晚间夜生活时段。"});
    }

    // === Popularity tier bonus ===
    if (poi.popularity >= 4.7) {
        breakdown.push_back({"热门景点", 10.0, "必看高评分景点。"});
    } else if (poi.popularity >= 4.3) {
        breakdown.push_back({"top_attraction", 5.0, "High-rated attraction."});
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
    stop.startMinutes = actualStart;
    stop.endMinutes = actualStart + poi.visitDurationMinutes;
    stop.visitDurationMinutes = poi.visitDurationMinutes;
    stop.travelMinutesFromPrevious = travelMinutes;
    stop.openTimeMatched = actualStart >= poi.openMinutes && stop.endMinutes <= poi.closeMinutes;
    stop.timeWindowStatus = stop.openTimeMatched ? "ok" : (actualStart < poi.openMinutes ? "wait" : "closed");
    stop.timeWindowReason = timeWindowIssueReason(stop, &poi, 0, request.endMinutes);
    stop.score = std::round(score * 10.0) / 10.0;

    std::ostringstream reason;
    reason << "鍐崇瓥渚濇嵁锛? << poi.name << " 浣嶄簬" << poi.area << "锛?;
    bool matched = false;
    for (const auto& interest : request.interests) {
        if (containsText(poi.tags, interest)) {
            reason << "鍖归厤銆? << interest << "銆嶅亸濂斤紝";
            matched = true;
            break;
        }
    }
    if (!matched) {
        reason << "鐑害鍜岃矾绾块『搴忚緝鍚堥€傦紝";
    }
    reason << "浠庝笂涓€绔欓€氬嫟 " << travelMinutes << " 鍒嗛挓锛?
           << "璇勫垎 " << stop.score << "锛?
           << "棰勮鍋滅暀 " << poi.visitDurationMinutes << " 鍒嗛挓銆?;
    if (stop.openTimeMatched) {
        reason << "寮€鏀炬椂闂存弧瓒冲綋鍓嶆椂闂寸獥銆?;
    } else {
        reason << "寮€鏀炬椂闂村瓨鍦ㄩ闄╋紝婕旂ず鏃跺彲璇存槑杩欐槸绾︽潫鎯╃綒椤广€?;
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
        day.timeWindowDiagnostics.push_back("褰撴棩娌℃湁鍙畨鎺掔珯鐐癸紝鏃堕棿绐楀鏍告棤鍙鏌ュ璞°€?);
    } else if (day.timeWindowFeasible) {
        day.timeWindowDiagnostics.push_back("鏈€缁堥『搴忓凡閫氳繃缁熶竴鏃堕棿绐楀鏍革細绔欑偣椤哄簭銆佸紑鏀炬椂闂淬€侀楗獥鍙ｅ拰褰撴棩缁撴潫鏃堕棿鍧囧彲琛屻€?);
    }
}

DayPlan TripPlanner::planDayWithBeamSearch(const TripRequest& request, int day, const std::string& hotelId, std::set<std::string>& used) const {
    const int beamWidth = plannerBeamWidth();
    const int breakMinutes = paceExtraBreakMinutes(request.pace);
    const std::vector<std::string> slots = {"涓婂崍", "鍗堥", "涓嬪崍", "涓嬪崍鑼?, "鏅氶", "鏅氫笂"};

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
            if (slot == "鍗堥" && slotStart < 11 * 60 + 30) slotStart = 11 * 60 + 30;
            if (slot == "涓嬪崍鑼? && slotStart < 14 * 60 + 30) slotStart = 14 * 60 + 30;
            if (slot == "鏅氶" && slotStart < 17 * 60 + 30) slotStart = 17 * 60 + 30;

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
            trace.decision = "璇ユ椂闂存Ы娌℃湁鍙鎵╁睍锛屼繚鐣欎笂涓€杞?Beam 鐘舵€佺户缁悗缁椂闂存Ы銆?;
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
        trace.decision = "鎸?Beam 鐘舵€佽瘎鍒嗕繚鐣?Top-" + std::to_string(trace.keptStates) +
                         "锛涙瘡涓姸鎬佸厛鍋氬€欓€夋睜鍙洖涓庣矖绛涳紝淇濈暀蹇呭幓鐐瑰苟瑁佸壀鏅€氬€欓€夊悗鍐嶈瘎鍒嗭紝鏈€缁堢患鍚堝叴瓒ｃ€侀€氬嫟鎯╃綒鍜岀珯鐐硅鐩栥€?;
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
    summary << "绗?" << day << " 澶╁洿缁?;
    if (!dayPlan.stops.empty()) {
        summary << dayPlan.stops.front().area;
    } else if (const Poi* hotel = graph_.findPoi(hotelId)) {
        summary << hotel->area;
    } else {
        summary << "閰掑簵鍛ㄨ竟";
    }
    summary << "灞曞紑锛孊eam Search 鍦ㄦ瘡涓椂闂存Ы淇濈暀鏈€澶?" << beamWidth
            << " 涓€欓€夌姸鎬侊紝缁煎悎璇勫垎銆侀€氬嫟銆佸紑鏀炬椂闂村拰蹇呭幓鐐硅鐩栧悗閫夋嫨褰撳墠璺嚎銆傛紨绀洪噸鐐癸細"
            << request.pace << "鑺傚锛屼紭鍏堝尮閰?
            << joinTags(request.interests)
            << "锛屽悓鏃舵鏌ュ紑鏀炬椂闂淬€侀楗獥鍙ｅ拰蹇呭幓鐐硅鐩栥€?;
    dayPlan.summary = summary.str();

    optimizeDayOrder(hotelId, dayPlan);
    dayPlan.optimizationSummary = "Beam Search 宸插厛瀹屾垚 Top-K 灞€閮ㄨ矾寰勯€夋嫨锛? + dayPlan.optimizationSummary;
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

    // Write back the optimized stops to day.stops
    day.stops = candidateStops;

    int saved = std::max(0, day.originalTravelMinutes - day.optimizedTravelMinutes);
    std::ostringstream summary;
    summary << "算法用日内局部交换评估通勤潜力：当前时间轴通勤 " << day.originalTravelMinutes
            << " 分钟，理论更优顺序 " << day.optimizedTravelMinutes
            << " 分钟，可节省 " << saved << " 分钟；只有同时满足开放时间、餐饮窗口和站点顺序的交换才计入收益。";
    day.optimizationSummary = summary.str();
}
    day.originalTravelMinutes = routeTravelMinutes(startId, day.stops);
    day.optimizedTravelMinutes = day.originalTravelMinutes;
    if (day.stops.size() < 4) {
        day.optimizationSummary = "褰撴棩绔欑偣杈冨皯锛岀畻娉曚繚鎸佸師椤哄簭锛涢€氬嫟鎴愭湰浠嶆潵鑷?POI 鍥炬渶鐭矾銆?;
        return;
    }

    std::vector<Stop> candidateStops = day.stops;
    bool improved = true;
    while (improved) {
        improved = false;
        for (size_t i = 0; i < candidateStops.size(); ++i) {
            if (candidateStops[i].slot == "鍗堥" || candidateStops[i].slot == "鏅氶" || candidateStops[i].slot == "涓嬪崍鑼?) continue;
            for (size_t j = i + 1; j < candidateStops.size(); ++j) {
                if (candidateStops[j].slot == "鍗堥" || candidateStops[j].slot == "鏅氶" || candidateStops[j].slot == "涓嬪崍鑼?) continue;
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
    summary << "绠楁硶鐢ㄦ棩鍐呭眬閮ㄤ氦鎹㈣瘎浼伴€氬嫟娼滃姏锛氬綋鍓嶆椂闂磋酱閫氬嫟 " << day.originalTravelMinutes
            << " 鍒嗛挓锛岀悊璁烘洿浼橀『搴?" << day.optimizedTravelMinutes
            << " 鍒嗛挓锛屽彲鑺傜渷 " << saved << " 鍒嗛挓锛涘彧鏈夊悓鏃舵弧瓒冲紑鏀炬椂闂淬€侀楗獥鍙ｅ拰绔欑偣椤哄簭鐨勪氦鎹㈡墠璁″叆鏀剁泭銆?;
    day.optimizationSummary = summary.str();
}

void TripPlanner::explainDayConstraints(const TripRequest& request, const std::set<std::string>& used, DayPlan& day) const {
    int lunchCount = 0;
    int dinnerCount = 0;
    int teaCount = 0;
    for (const auto& stop : day.stops) {
        if (stop.openTimeMatched) {
            day.constraintExplanations.push_back(stop.poiName + " 鍛戒腑寮€鏀炬椂闂寸害鏉熴€?);
        } else {
            day.constraintExplanations.push_back(stop.poiName + " 瀛樺湪寮€鏀炬椂闂寸害鏉熼闄┿€?);
        }
        if (stop.slot == "鍗堥") ++lunchCount;
        if (stop.slot == "鏅氶") ++dinnerCount;
        if (stop.slot == "涓嬪崍鑼?) ++teaCount;
        if (containsText(request.mustVisit, stop.poiName) || containsText(request.mustVisit, stop.poiId)) {
            day.constraintExplanations.push_back(stop.poiName + " 灞炰簬蹇呭幓鐐癸紝宸蹭紭鍏堝畨鎺掋€?);
        }
    }
    if (lunchCount > 0) day.constraintExplanations.push_back("鍗堥宸叉寜 11:30-13:30 鏃堕棿绐楁彃鍏ャ€?);
    if (teaCount > 0) day.constraintExplanations.push_back("涓嬪崍鑼跺凡鎸?14:30-16:30 鏃堕棿绐楁彃鍏ャ€?);
    if (dinnerCount > 0) day.constraintExplanations.push_back("鏅氶宸叉寜 17:30-19:30 鏃堕棿绐楁彃鍏ャ€?);
    day.constraintExplanations.push_back("绠楁硶绾︽潫锛氬綋鏃ラ€氬嫟鎴愭湰鏉ヨ嚜鏈湴 POI 鍥炬渶鐭矾璁＄畻銆?);

    for (const auto& must : request.mustVisit) {
        const Poi* poi = graph_.findPoi(must);
        if (!poi) {
            day.unscheduledReasons.push_back(must + " 鏈畨鎺掞細鏍蜂緥鏁版嵁涓笉瀛樺湪璇?POI锛屾紨绀烘椂鍙綔涓鸿緭鍏ユ牎楠岃鏄庛€?);
        } else if (used.count(poi->id) == 0) {
            day.unscheduledReasons.push_back(poi->name + " 鏈畨鎺掞細褰撴棩鏃堕棿棰勭畻銆佸紑鏀炬椂闂存垨閫氬嫟鎴愭湰绾︽潫涓嶈冻銆?);
        }
    }
    if (day.unscheduledReasons.empty()) {
        day.unscheduledReasons.push_back("蹇呭幓鐐瑰潎宸插畨鎺掓垨宸插湪鍏朵粬鏃ユ湡瑕嗙洊锛屾湭瀹夋帓鍒楄〃鐢ㄤ簬瑙ｉ噴绾︽潫鍙栬垗銆?);
    }
}

ComparisonMetrics TripPlanner::buildComparisonMetrics(const TripRequest& request, const Itinerary& itinerary) const {
    ComparisonMetrics metrics;
    std::set<std::string> coveredMustVisits;
    for (const auto& day : itinerary.days) {
        metrics.totalTravelMinutes += day.totalTravelMinutes;
        metrics.totalVisitMinutes += day.totalVisitMinutes;
        for (const auto& reason : day.unscheduledReasons) {
            if (reason.find(" 鏈畨鎺掞細") != std::string::npos) {
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
    metrics.tradeoffSummary = "寰呰繘琛屽鐩爣闈炴敮閰嶆帓搴忋€?;
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
            summary << "鏍囧噯闈炴敮閰嶅垎灞?Pareto 绗?1 灞傦細鍦ㄨ瘎鍒嗐€侀€氬嫟銆侀闄╁拰蹇呭幓瑕嗙洊涔嬮棿娌℃湁琚叾浠栧€欓€夊畬鍏ㄦ敮閰嶃€?;
            candidate.comparison.paretoDebug.push_back("鏈彂鐜板叾浠栧€欓€夊湪鎬诲垎銆佸繀鍘昏鐩栥€侀€氬嫟銆佸紑鏀炬椂闂撮闄╁拰鏈畨鎺掓暟閲忎笂鍚屾椂涓嶅樊涓旇嚦灏戜竴椤规洿浼樸€?);
        } else {
            summary << "鏍囧噯闈炴敮閰嶅垎灞?Pareto 绗?" << candidate.comparison.paretoRank
                    << " 灞傦細绉婚櫎鏇翠紭鍓嶆部鍚庤繘鍏ヤ笅涓€灞傦紝璇存槑璇ユ柟妗堝湪鑷冲皯涓€涓洰鏍囦笂鏈夊彇鑸嶆垚鏈€?;
            candidate.comparison.paretoDebug.push_back("瀛樺湪鏇撮珮灞傚€欓€夊湪澶氱洰鏍囨寚鏍囦笂褰㈡垚鏀厤鎴栬繎浼兼敮閰嶅叧绯汇€?);
        }
        std::ostringstream metrics;
        metrics << "鎸囨爣鍚戦噺锛歴core=" << candidate.comparison.totalScore
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
            candidate.comparison.diversityTags.push_back("鍩虹嚎鏂规");
            candidate.comparison.diversitySummary = "浣滀负鍊欓€夊姣斿熀绾匡紝鍏朵粬鏂规浼氳绠楃浉瀵瑰畠鐨?POI 鍜屽尯鍩熷樊寮傘€?;
            continue;
        }

        candidate.comparison.diversityTags.push_back(diversityLevel(candidate.comparison.poiOverlapWithBaseline, candidate.comparison.uniquePoiCount));
        candidate.comparison.diversityTags.push_back(strategyDiversityTag(candidate.strategy));
        if (candidate.comparison.areaOverlapWithBaseline <= 0.6) {
            candidate.comparison.diversityTags.push_back("鍖哄煙璺緞宸紓");
        }
        if (candidate.comparison.uniquePoiCount > 0) {
            candidate.comparison.diversityTags.push_back("鍖呭惈鐙湁 POI");
        }

        std::ostringstream summary;
        summary << "鐩稿鍩虹嚎 POI 閲嶅悎鐜?" << static_cast<int>(std::round(candidate.comparison.poiOverlapWithBaseline * 100))
                << "%锛屽尯鍩熼噸鍚堢巼 " << static_cast<int>(std::round(candidate.comparison.areaOverlapWithBaseline * 100))
                << "%锛岀嫭鏈?POI " << candidate.comparison.uniquePoiCount << " 涓?;
        if (!candidate.comparison.uniquePois.empty()) {
            summary << "锛?;
            for (size_t i = 0; i < candidate.comparison.uniquePois.size() && i < 3; ++i) {
                if (i > 0) summary << "銆?;
                summary << candidate.comparison.uniquePois[i];
            }
        }
        summary << "銆?;
        candidate.comparison.diversitySummary = summary.str();
    }
}

Itinerary TripPlanner::plan(const TripRequest& request) const {
    const Poi* hotel = chooseHotel(request);
    if (!hotel) {
        throw std::runtime_error("璇ュ煄甯傛殏鏃犻厭搴楁暟鎹紝鏃犳硶鐢熸垚琛岀▼銆傝纭鍩庡競鏁版嵁涓寘鍚厭搴楃被鍨嬬殑 POI銆?);
    }

    Itinerary itinerary;
    itinerary.city = request.city;
    itinerary.hotel = {hotel->id, hotel->name, hotel->area, hotel->lat, hotel->lng, hotel->popularity};
    itinerary.variantName = request.pace + "鑺傚鏂规";
    itinerary.strategy = request.strategy;
    std::set<std::string> used;

    for (int day = 1; day <= request.days; ++day) {
        DayPlan dayPlan = planDayWithBeamSearch(request, day, hotel->id, used);
        itinerary.totalScore += dayPlan.interestScore;
        itinerary.days.push_back(dayPlan);
    }

    itinerary.alternatives = {
        "涓嬮洦鏃跺彲灏嗘埛澶栨櫙鐐规浛鎹负瀹ゅ唴灞曢銆佸挅鍟￠鎴栧晢鍦轰紤闂层€?,
        "濡傛灉浣撳姏涓嶈冻锛屽彲鍑忓皯涓嬪崍鏅偣骞跺欢闀块楗拰浼戞伅鏃堕棿銆?,
        "棰勭畻闄嶄綆鏃朵紭鍏堥€夋嫨鍏叡浜ら€氬彲杈惧尯鍩熷拰骞充环椁愰ギ銆?
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
    relaxed.pace = "杞绘澗";
    relaxed.strategy = "low_travel";
    variants.push_back(relaxed);
    names.push_back("杞绘澗灏戣蛋璺柟妗?);
    focuses.push_back("鎻愰珮閫氬嫟鎯╃綒骞跺亸濂藉悓鍖哄煙娲诲姩锛岄€傚悎灞曠ず浣撳姏鍙嬪ソ鍙栬垗銆?);

    TripRequest compact = request;
    compact.pace = "绱у噾";
    compact.strategy = "compact";
    variants.push_back(compact);
    names.push_back("绱у噾澶氳鐩栨柟妗?);
    focuses.push_back("闄嶄綆閫氬嫟鎯╃綒骞舵彁楂樿鐩栨潈閲嶏紝閫傚悎灞曠ず鏃堕棿绐楄皟搴︺€?);

    TripRequest culture = request;
    culture.strategy = "culture";
    culture.interests = {"鍘嗗彶鏂囧寲", "鍗氱墿棣?, "鍙ゅ缓绛?};
    variants.push_back(culture);
    names.push_back("鏂囧寲浼樺厛鏂规");
    focuses.push_back("鍔犳潈鍗氱墿棣嗐€佷功闄€佸彜寤虹瓚鍜屽搴欙紝灞曠ず涓婚鍖栧€欓€夈€?);

    TripRequest food = request;
    food.strategy = "food";
    food.interests = {"缇庨", "灏忓悆", "澶滄櫙"};
    variants.push_back(food);
    names.push_back("缇庨浼樺厛鏂规");
    focuses.push_back("鍔犳潈椁愰ギ銆佸皬鍚冭鍜屽闂寸編椋熷満鏅紝灞曠ず缇庨璺嚎銆?);

    TripRequest rainy = request;
    rainy.strategy = "rainy";
    rainy.interests = {"瀹ゅ唴", "鍘嗗彶鏂囧寲", "缇庨"};
    variants.push_back(rainy);
    names.push_back("闆ㄥぉ瀹ゅ唴鏂规");
    focuses.push_back("鍔犳潈瀹ゅ唴 POI 骞堕檷浣庢埛澶栫偣浼樺厛绾э紝灞曠ず鍦烘櫙鍖栨浛鎹€?);

    for (size_t index = 0; index < variants.size(); ++index) {
        if (static_cast<int>(candidates.size()) >= request.candidateCount) break;
        auto variant = variants[index];
        Itinerary itinerary = plan(variant);
        bool duplicate = false;
        for (const auto& existing : candidates) {
            if (!existing.days.empty() && !itinerary.days.empty() &&
                !existing.days.front().stops.empty() && !itinerary.days.front().stops.empty() &&
                existing.days.front().stops.front().poiId == itinerary.days.front().stops.front().poiId &&
                existing.days.front().stops.size() == itinerary.days.front().stops.size() &&
                existing.variantName == names[index]) {
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
        itinerary.variantName = "閿欏嘲鍑哄彂 +" + std::to_string(offsetMinutes) + " 鍒嗛挓鏂规";
        annotateVariantFocus(itinerary, "寤跺悗鍑哄彂 " + std::to_string(offsetMinutes) + " 鍒嗛挓锛屽睍绀烘椂闂寸獥鍙樺寲瀵瑰畨鎺掔粨鏋滅殑褰卞搷銆?);
        candidates.push_back(itinerary);
    }
    assignDiversityMetrics(candidates);
    assignParetoRanks(candidates);
    return candidates;
}

}  // namespace tourpass

