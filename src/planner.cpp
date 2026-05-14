#include "tourpass/planner.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <sstream>
#include <vector>

namespace tourpass {

TripPlanner::TripPlanner(const PoiGraph& graph) : graph_(graph) {}

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

double TripPlanner::scorePoi(const TripRequest& request, const Poi& poi, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const {
    if (used.count(poi.id) > 0) {
        return -100000.0;
    }
    if (poi.type == PoiType::Hotel || poi.type == PoiType::Transit) {
        return -100000.0;
    }

    double score = poi.popularity * 10.0;
    for (const auto& interest : request.interests) {
        if (containsText(poi.tags, interest)) {
            score += 35.0;
        }
    }
    if (containsText(request.mustVisit, poi.name) || containsText(request.mustVisit, poi.id)) {
        score += 120.0;
    }
    for (const auto& avoid : request.avoid) {
        if (poi.description.find(avoid) != std::string::npos || containsText(poi.tags, avoid)) {
            score -= 40.0;
        }
    }

    int travel = graph_.shortestMinutes(currentPoiId, poi.id);
    if (travel == std::numeric_limits<int>::max()) {
        return -100000.0;
    }
    score -= travel * 1.2;
    score -= poi.priceLevel * 3.0;

    int arrival = currentTime + travel;
    if (arrival < poi.openMinutes) {
        score -= (poi.openMinutes - arrival) * 0.5;
    }
    if (arrival + poi.visitDurationMinutes > poi.closeMinutes) {
        score -= 1000.0;
    }
    return score;
}

const Poi* TripPlanner::chooseBestPoi(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used, bool nightOnly) const {
    const Poi* best = nullptr;
    double bestScore = -100000.0;
    for (const auto& poi : graph_.pois()) {
        if (nightOnly && poi.type != PoiType::Nightlife) continue;
        if (!nightOnly && poi.type != PoiType::Attraction && poi.type != PoiType::Nightlife) continue;
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

Stop TripPlanner::makeStop(const std::string& slot, const Poi& poi, int startMinutes, int travelMinutes, double score, const TripRequest& request) const {
    int actualStart = std::max(startMinutes, poi.openMinutes);
    Stop stop;
    stop.slot = slot;
    stop.poiId = poi.id;
    stop.poiName = poi.name;
    stop.poiType = poiTypeToString(poi.type);
    stop.area = poi.area;
    stop.startMinutes = actualStart;
    stop.endMinutes = actualStart + poi.visitDurationMinutes;
    stop.visitDurationMinutes = poi.visitDurationMinutes;
    stop.travelMinutesFromPrevious = travelMinutes;
    stop.openTimeMatched = actualStart >= poi.openMinutes && stop.endMinutes <= poi.closeMinutes;
    stop.score = std::round(score * 10.0) / 10.0;

    std::ostringstream reason;
    reason << poi.name << " 位于" << poi.area << "，";
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
    reason << "预计停留 " << poi.visitDurationMinutes << " 分钟。";
    stop.reason = reason.str();
    return stop;
}

void TripPlanner::optimizeDayOrder(const std::string& startId, DayPlan& day) const {
    day.originalTravelMinutes = routeTravelMinutes(startId, day.stops);
    day.optimizedTravelMinutes = day.originalTravelMinutes;
    if (day.stops.size() < 4) {
        day.optimizationSummary = "当日站点较少，保持原顺序。";
        return;
    }

    bool improved = true;
    while (improved) {
        improved = false;
        for (size_t i = 0; i < day.stops.size(); ++i) {
            if (day.stops[i].slot == "午餐" || day.stops[i].slot == "晚餐") continue;
            for (size_t j = i + 1; j < day.stops.size(); ++j) {
                if (day.stops[j].slot == "午餐" || day.stops[j].slot == "晚餐") continue;
                std::swap(day.stops[i], day.stops[j]);
                int candidateTravel = routeTravelMinutes(startId, day.stops);
                if (candidateTravel < day.optimizedTravelMinutes) {
                    day.optimizedTravelMinutes = candidateTravel;
                    day.totalTravelMinutes = candidateTravel;
                    improved = true;
                } else {
                    std::swap(day.stops[i], day.stops[j]);
                }
            }
        }
    }

    std::string currentId = startId;
    for (auto& stop : day.stops) {
        int travel = graph_.shortestMinutes(currentId, stop.poiId);
        if (travel != std::numeric_limits<int>::max()) {
            stop.travelMinutesFromPrevious = travel;
        }
        currentId = stop.poiId;
    }

    int saved = std::max(0, day.originalTravelMinutes - day.optimizedTravelMinutes);
    std::ostringstream summary;
    summary << "局部交换优化前通勤 " << day.originalTravelMinutes
            << " 分钟，优化后 " << day.optimizedTravelMinutes
            << " 分钟，节省 " << saved << " 分钟。";
    day.optimizationSummary = summary.str();
}

void TripPlanner::explainDayConstraints(const TripRequest& request, const std::set<std::string>& used, DayPlan& day) const {
    int lunchCount = 0;
    int dinnerCount = 0;
    for (const auto& stop : day.stops) {
        if (stop.openTimeMatched) {
            day.constraintExplanations.push_back(stop.poiName + " 命中开放时间窗口。");
        } else {
            day.constraintExplanations.push_back(stop.poiName + " 存在开放时间风险。");
        }
        if (stop.slot == "午餐") ++lunchCount;
        if (stop.slot == "晚餐") ++dinnerCount;
        if (containsText(request.mustVisit, stop.poiName) || containsText(request.mustVisit, stop.poiId)) {
            day.constraintExplanations.push_back(stop.poiName + " 属于必去点，已优先安排。");
        }
    }
    if (lunchCount > 0) day.constraintExplanations.push_back("午餐已按 11:30-13:30 时间窗插入。");
    if (dinnerCount > 0) day.constraintExplanations.push_back("晚餐已按 17:30-19:30 时间窗插入。");
    day.constraintExplanations.push_back("当日通勤成本来自本地 POI 图最短路计算。");

    for (const auto& must : request.mustVisit) {
        const Poi* poi = graph_.findPoi(must);
        if (!poi) {
            day.unscheduledReasons.push_back(must + " 未安排：样例数据中不存在该 POI。");
        } else if (used.count(poi->id) == 0) {
            day.unscheduledReasons.push_back(poi->name + " 未安排：当日时间预算或通勤成本不足。");
        }
    }
    if (day.unscheduledReasons.empty()) {
        day.unscheduledReasons.push_back("必去点均已安排或已在其他日期覆盖。");
    }
}

Itinerary TripPlanner::plan(const TripRequest& request) const {
    const Poi* hotel = chooseHotel(request);
    if (!hotel) {
        throw std::runtime_error("no hotel poi available");
    }

    Itinerary itinerary;
    itinerary.city = request.city;
    itinerary.variantName = request.pace + "节奏方案";
    std::set<std::string> used;
    int breakMinutes = paceExtraBreakMinutes(request.pace);

    for (int day = 1; day <= request.days; ++day) {
        DayPlan dayPlan;
        dayPlan.day = day;
        std::string currentId = hotel->id;
        int currentTime = request.startMinutes;

        auto addPoi = [&](const std::string& slot, const Poi* poi) {
            if (!poi) return false;
            int travel = graph_.shortestMinutes(currentId, poi->id);
            if (travel == std::numeric_limits<int>::max()) return false;
            double score = scorePoi(request, *poi, currentId, currentTime, used);
            Stop stop = makeStop(slot, *poi, currentTime + travel, travel, score, request);
            if (stop.endMinutes > request.endMinutes) return false;
            dayPlan.totalTravelMinutes += travel;
            dayPlan.totalVisitMinutes += stop.visitDurationMinutes;
            dayPlan.interestScore += std::max(0.0, stop.score);
            currentTime = stop.endMinutes + breakMinutes;
            currentId = poi->id;
            used.insert(poi->id);
            dayPlan.stops.push_back(stop);
            return true;
        };

        const Poi* morning = chooseMustVisit(request, currentId, currentTime, used);
        if (!morning) {
            morning = chooseBestPoi(request, currentId, currentTime, used, false);
        }
        addPoi("上午", morning);

        if (currentTime < 11 * 60 + 30) currentTime = 11 * 60 + 30;
        addPoi("午餐", chooseRestaurant(request, currentId, currentTime, used));

        const Poi* afternoon = chooseMustVisit(request, currentId, currentTime, used);
        if (!afternoon) {
            afternoon = chooseBestPoi(request, currentId, currentTime, used, false);
        }
        addPoi("下午", afternoon);

        if (currentTime < 17 * 60 + 30) currentTime = 17 * 60 + 30;
        addPoi("晚餐", chooseRestaurant(request, currentId, currentTime, used));

        addPoi("晚上", chooseBestPoi(request, currentId, currentTime, used, true));

        std::ostringstream summary;
        summary << "第 " << day << " 天围绕";
        if (!dayPlan.stops.empty()) {
            summary << dayPlan.stops.front().area;
        } else {
            summary << hotel->area;
        }
        summary << "展开，优先减少跨区域通勤。";
        dayPlan.summary = summary.str();
        optimizeDayOrder(hotel->id, dayPlan);
        explainDayConstraints(request, used, dayPlan);
        itinerary.totalScore += dayPlan.interestScore;
        itinerary.days.push_back(dayPlan);
    }

    itinerary.alternatives = {
        "下雨时可将户外点替换为湖南博物院、潮宗街室内店铺或商场休闲。",
        "如果体力不足，可减少下午景点并延长餐饮和休息时间。",
        "预算降低时优先选择地铁可达区域和小吃街餐饮。"
    };
    itinerary.totalScore = std::round(itinerary.totalScore * 10.0) / 10.0;
    return itinerary;
}

std::vector<Itinerary> TripPlanner::planCandidates(const TripRequest& request) const {
    std::vector<Itinerary> candidates;
    std::vector<TripRequest> variants;
    variants.push_back(request);

    TripRequest relaxed = request;
    relaxed.pace = "轻松";
    variants.push_back(relaxed);

    TripRequest compact = request;
    compact.pace = "紧凑";
    variants.push_back(compact);

    TripRequest reversed = request;
    std::reverse(reversed.interests.begin(), reversed.interests.end());
    variants.push_back(reversed);

    for (auto variant : variants) {
        if (static_cast<int>(candidates.size()) >= request.candidateCount) break;
        Itinerary itinerary = plan(variant);
        bool duplicate = false;
        for (const auto& existing : candidates) {
            if (!existing.days.empty() && !itinerary.days.empty() &&
                !existing.days.front().stops.empty() && !itinerary.days.front().stops.empty() &&
                existing.days.front().stops.front().poiId == itinerary.days.front().stops.front().poiId &&
                existing.days.front().stops.size() == itinerary.days.front().stops.size()) {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) {
            if (variant.pace == "轻松") itinerary.variantName = "轻松少走路方案";
            else if (variant.pace == "紧凑") itinerary.variantName = "紧凑多覆盖方案";
            else if (variant.interests != request.interests) itinerary.variantName = "兴趣顺序调整方案";
            candidates.push_back(itinerary);
        }
    }

    while (static_cast<int>(candidates.size()) < request.candidateCount && !candidates.empty()) {
        TripRequest variant = request;
        variant.startMinutes += static_cast<int>(candidates.size()) * 15;
        Itinerary itinerary = plan(variant);
        itinerary.variantName = "错峰出发方案";
        candidates.push_back(itinerary);
    }
    return candidates;
}

}  // namespace tourpass
