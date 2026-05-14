#pragma once

#include <string>
#include <vector>

#include "json.hpp"

namespace tourpass {

enum class PoiType {
    Attraction,
    Restaurant,
    Hotel,
    Transit,
    Nightlife
};

struct Poi {
    std::string id;
    std::string name;
    PoiType type = PoiType::Attraction;
    double lat = 0.0;
    double lng = 0.0;
    std::vector<std::string> tags;
    int openMinutes = 0;
    int closeMinutes = 24 * 60;
    int visitDurationMinutes = 60;
    double popularity = 0.0;
    int priceLevel = 1;
    std::string description;
    std::string area;
};

struct Edge {
    std::string from;
    std::string to;
    int distanceMeters = 0;
    int walkMinutes = -1;
    int transitMinutes = -1;
    int taxiMinutes = -1;
};

struct TripRequest {
    std::string city;
    int days = 1;
    int startMinutes = 9 * 60;
    int endMinutes = 21 * 60;
    std::string hotelLocation;
    std::vector<std::string> interests;
    std::string pace = "标准";
    std::vector<std::string> mustVisit;
    std::vector<std::string> avoid;
    int candidateCount = 1;
};

struct Stop {
    std::string slot;
    std::string poiId;
    std::string poiName;
    std::string poiType;
    std::string area;
    int startMinutes = 0;
    int endMinutes = 0;
    int visitDurationMinutes = 0;
    int travelMinutesFromPrevious = 0;
    bool openTimeMatched = true;
    double score = 0.0;
    std::string reason;
};

struct DayPlan {
    int day = 1;
    std::vector<Stop> stops;
    int totalTravelMinutes = 0;
    int originalTravelMinutes = 0;
    int optimizedTravelMinutes = 0;
    int totalVisitMinutes = 0;
    double interestScore = 0.0;
    std::string summary;
    std::string optimizationSummary;
    std::vector<std::string> constraintExplanations;
    std::vector<std::string> unscheduledReasons;
};

struct Itinerary {
    std::string city;
    std::string variantName = "推荐方案";
    std::vector<DayPlan> days;
    double totalScore = 0.0;
    std::vector<std::string> alternatives;
};

struct RouteResult {
    std::string from;
    std::string to;
    int travelMinutes = 0;
    std::vector<std::string> path;
    std::string algorithm;
};

std::string poiTypeToString(PoiType type);
PoiType poiTypeFromString(const std::string& value);
int parseTimeToMinutes(const std::string& value);
std::string formatMinutes(int minutes);
bool containsText(const std::vector<std::string>& values, const std::string& value);

nlohmann::json stopToJson(const Stop& stop);
nlohmann::json dayPlanToJson(const DayPlan& day);
nlohmann::json itineraryToJson(const Itinerary& itinerary);
nlohmann::json routeResultToJson(const RouteResult& route);
TripRequest tripRequestFromJson(const nlohmann::json& input);

}  // namespace tourpass
