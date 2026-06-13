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


struct PoiImage {
    std::string url;
    std::string source;    // "xiaohongshu" / "amap"
    std::string noteUrl;
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
    std::string mealType = "main";  // main | snack | drink (only for Restaurant type)
    std::string recommendation;     // user-friendly tip, e.g. "傍晚去橘子洲看日落"

    std::string imageUrl;              // main image path for backward compat
    std::vector<PoiImage> images;      // all candidate images
    std::string guideText;             // guide text from travel notes
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
    std::string strategy = "balanced";
};

struct ScoreComponent {
    std::string label;
    double value = 0.0;
    std::string reason;
};

struct BeamTraceEntry {
    std::string slot;
    int inputStates = 0;
    int expandedStates = 0;
    int keptStates = 0;
    std::vector<std::string> keptStateSummaries;
    std::string decision;
};

struct Stop {
    std::string slot;
    std::string poiId;
    std::string poiName;
    std::string poiType;
    std::string mealType;
    std::string recommendation;

    std::string area;
    std::string imageUrl;
    std::string guideText;
    double lat = 0.0;
    double lng = 0.0;
    int startMinutes = 0;
    int endMinutes = 0;
    int visitDurationMinutes = 0;
    int travelMinutesFromPrevious = 0;
    bool openTimeMatched = true;
    std::string timeWindowStatus = "ok";
    std::string timeWindowReason;
    double score = 0.0;
    std::string reason;
    std::vector<ScoreComponent> scoreBreakdown;
};

struct ComparisonMetrics {
    int totalStops = 0;
    int totalTravelMinutes = 0;
    int totalVisitMinutes = 0;
    int mustVisitCovered = 0;
    int openTimeRisks = 0;
    int unscheduledCount = 0;
    double totalScore = 0.0;
    int paretoRank = 0;
    bool dominated = false;
    std::string tradeoffSummary;
    std::vector<std::string> paretoDebug;
    double poiOverlapWithBaseline = 1.0;
    double areaOverlapWithBaseline = 1.0;
    int uniquePoiCount = 0;
    std::vector<std::string> uniquePois;
    std::vector<std::string> diversityTags;
    std::string diversitySummary;
};

struct DayPlan {
    int day = 1;
    std::vector<Stop> stops;
    int totalTravelMinutes = 0;
    int originalTravelMinutes = 0;
    int optimizedTravelMinutes = 0;
    int totalVisitMinutes = 0;
    double interestScore = 0.0;
    bool timeWindowFeasible = true;
    std::string summary;
    std::string optimizationSummary;
    std::vector<std::string> constraintExplanations;
    std::vector<std::string> unscheduledReasons;
    std::vector<std::string> timeWindowDiagnostics;
    std::vector<BeamTraceEntry> beamTrace;
};

struct HotelInfo {
    std::string id;
    std::string name;
    std::string area;
    double lat = 0.0;
    double lng = 0.0;
    double popularity = 0.0;
};

struct Itinerary {
    std::string city;
    std::string variantName = "推荐方案";
    std::string strategy = "balanced";
    std::vector<DayPlan> days;
    double totalScore = 0.0;
    std::vector<std::string> alternatives;
    ComparisonMetrics comparison;
    HotelInfo hotel;
};

struct RouteResult {
    std::string from;
    std::string to;
    int travelMinutes = 0;
    std::vector<std::string> path;
    std::vector<std::pair<double,double>> pathCoords;
    std::string algorithm;
};

std::string poiTypeToString(PoiType type);
PoiType poiTypeFromString(const std::string& value);
int parseTimeToMinutes(const std::string& value);
std::string formatMinutes(int minutes);
bool containsText(const std::vector<std::string>& values, const std::string& value);

nlohmann::json stopToJson(const Stop& stop);
nlohmann::json scoreComponentToJson(const ScoreComponent& component);
nlohmann::json beamTraceEntryToJson(const BeamTraceEntry& entry);
nlohmann::json comparisonMetricsToJson(const ComparisonMetrics& metrics);
nlohmann::json dayPlanToJson(const DayPlan& day);
nlohmann::json itineraryToJson(const Itinerary& itinerary);
nlohmann::json routeResultToJson(const RouteResult& route);
nlohmann::json poiToJson(const Poi& poi);
TripRequest tripRequestFromJson(const nlohmann::json& input, const std::string& defaultCity = "");

}  // namespace tourpass


