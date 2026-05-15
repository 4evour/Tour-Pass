#include "tourpass/models.h"

#include <algorithm>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace tourpass {

namespace {

std::string requireString(const nlohmann::json& input, const std::string& key) {
    if (!input.contains(key) || !input.at(key).is_string()) {
        throw std::runtime_error("missing string field: " + key);
    }
    return input.at(key).get<std::string>();
}

std::vector<std::string> optionalStringArray(const nlohmann::json& input, const std::string& key) {
    std::vector<std::string> result;
    if (!input.contains(key)) {
        return result;
    }
    if (!input.at(key).is_array()) {
        throw std::runtime_error("field must be an array: " + key);
    }
    for (const auto& item : input.at(key)) {
        if (!item.is_string()) {
            throw std::runtime_error("array field must contain strings: " + key);
        }
        result.push_back(item.get<std::string>());
    }
    return result;
}

}  // namespace

std::string poiTypeToString(PoiType type) {
    switch (type) {
        case PoiType::Attraction: return "attraction";
        case PoiType::Restaurant: return "restaurant";
        case PoiType::Hotel: return "hotel";
        case PoiType::Transit: return "transit";
        case PoiType::Nightlife: return "nightlife";
    }
    return "attraction";
}

PoiType poiTypeFromString(const std::string& value) {
    if (value == "attraction" || value == "景点") return PoiType::Attraction;
    if (value == "restaurant" || value == "餐厅") return PoiType::Restaurant;
    if (value == "hotel" || value == "酒店") return PoiType::Hotel;
    if (value == "transit" || value == "交通站点") return PoiType::Transit;
    if (value == "nightlife" || value == "夜间活动点") return PoiType::Nightlife;
    throw std::runtime_error("unknown poi type: " + value);
}

int parseTimeToMinutes(const std::string& value) {
    if (value.size() != 5 || value[2] != ':') {
        throw std::runtime_error("invalid time format: " + value);
    }
    int hour = std::stoi(value.substr(0, 2));
    int minute = std::stoi(value.substr(3, 2));
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
        throw std::runtime_error("invalid time value: " + value);
    }
    return hour * 60 + minute;
}

std::string formatMinutes(int minutes) {
    if (minutes < 0) minutes = 0;
    minutes %= 24 * 60;
    std::ostringstream out;
    out << std::setw(2) << std::setfill('0') << (minutes / 60)
        << ":" << std::setw(2) << std::setfill('0') << (minutes % 60);
    return out.str();
}

bool containsText(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}

nlohmann::json scoreComponentToJson(const ScoreComponent& component) {
    return {
        {"label", component.label},
        {"value", component.value},
        {"reason", component.reason}
    };
}

nlohmann::json comparisonMetricsToJson(const ComparisonMetrics& metrics) {
    return {
        {"total_stops", metrics.totalStops},
        {"total_travel_minutes", metrics.totalTravelMinutes},
        {"total_visit_minutes", metrics.totalVisitMinutes},
        {"must_visit_covered", metrics.mustVisitCovered},
        {"open_time_risks", metrics.openTimeRisks},
        {"unscheduled_count", metrics.unscheduledCount},
        {"total_score", metrics.totalScore},
        {"pareto_rank", metrics.paretoRank},
        {"dominated", metrics.dominated},
        {"tradeoff_summary", metrics.tradeoffSummary}
    };
}

nlohmann::json stopToJson(const Stop& stop) {
    nlohmann::json breakdown = nlohmann::json::array();
    for (const auto& component : stop.scoreBreakdown) {
        breakdown.push_back(scoreComponentToJson(component));
    }
    return {
        {"slot", stop.slot},
        {"poi_id", stop.poiId},
        {"poi_name", stop.poiName},
        {"poi_type", stop.poiType},
        {"area", stop.area},
        {"start_time", formatMinutes(stop.startMinutes)},
        {"end_time", formatMinutes(stop.endMinutes)},
        {"visit_duration_minutes", stop.visitDurationMinutes},
        {"travel_minutes_from_previous", stop.travelMinutesFromPrevious},
        {"open_time_matched", stop.openTimeMatched},
        {"score", stop.score},
        {"score_breakdown", breakdown},
        {"reason", stop.reason}
    };
}

nlohmann::json dayPlanToJson(const DayPlan& day) {
    nlohmann::json stops = nlohmann::json::array();
    for (const auto& stop : day.stops) {
        stops.push_back(stopToJson(stop));
    }
    return {
        {"day", day.day},
        {"summary", day.summary},
        {"optimization_summary", day.optimizationSummary},
        {"total_travel_minutes", day.totalTravelMinutes},
        {"original_travel_minutes", day.originalTravelMinutes},
        {"optimized_travel_minutes", day.optimizedTravelMinutes},
        {"total_visit_minutes", day.totalVisitMinutes},
        {"interest_score", day.interestScore},
        {"constraint_explanations", day.constraintExplanations},
        {"unscheduled_reasons", day.unscheduledReasons},
        {"stops", stops}
    };
}

nlohmann::json itineraryToJson(const Itinerary& itinerary) {
    nlohmann::json days = nlohmann::json::array();
    for (const auto& day : itinerary.days) {
        days.push_back(dayPlanToJson(day));
    }
    return {
        {"city", itinerary.city},
        {"variant_name", itinerary.variantName},
        {"strategy", itinerary.strategy},
        {"total_score", itinerary.totalScore},
        {"comparison", comparisonMetricsToJson(itinerary.comparison)},
        {"days", days},
        {"alternatives", itinerary.alternatives}
    };
}

TripRequest tripRequestFromJson(const nlohmann::json& input) {
    if (!input.is_object()) {
        throw std::runtime_error("request body must be a JSON object");
    }

    TripRequest request;
    request.city = input.value("city", "长沙");
    request.days = input.value("days", 1);
    request.startMinutes = parseTimeToMinutes(input.value("start_time", "09:30"));
    request.endMinutes = parseTimeToMinutes(input.value("end_time", "21:30"));
    request.hotelLocation = input.value("hotel_location", "五一广场");
    request.interests = optionalStringArray(input, "interests");
    request.pace = input.value("pace", "标准");
    request.mustVisit = optionalStringArray(input, "must_visit");
    request.avoid = optionalStringArray(input, "avoid");
    request.candidateCount = input.value("candidate_count", 1);
    request.strategy = input.value("strategy", "balanced");

    if (request.days < 1 || request.days > 7) {
        throw std::runtime_error("days must be between 1 and 7");
    }
    if (request.candidateCount < 1 || request.candidateCount > 5) {
        throw std::runtime_error("candidate_count must be between 1 and 5");
    }
    if (request.startMinutes >= request.endMinutes) {
        throw std::runtime_error("start_time must be earlier than end_time");
    }
    if (request.city.empty()) {
        request.city = requireString(input, "city");
    }
    return request;
}

nlohmann::json routeResultToJson(const RouteResult& route) {
    return {
        {"from", route.from},
        {"to", route.to},
        {"travel_minutes", route.travelMinutes},
        {"path", route.path},
        {"algorithm", route.algorithm}
    };
}

}  // namespace tourpass
