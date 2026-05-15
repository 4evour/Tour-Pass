#pragma once

#include <set>

#include "tourpass/graph.h"

namespace tourpass {

class TripPlanner {
public:
    explicit TripPlanner(const PoiGraph& graph);

    Itinerary plan(const TripRequest& request) const;
    std::vector<Itinerary> planCandidates(const TripRequest& request) const;
    double scorePoi(const TripRequest& request, const Poi& poi, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const;

private:
    const PoiGraph& graph_;

    const Poi* chooseHotel(const TripRequest& request) const;
    const Poi* chooseMustVisit(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const;
    const Poi* chooseBestPoi(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used, bool nightOnly) const;
    const Poi* chooseRestaurant(const TripRequest& request, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const;
    std::vector<const Poi*> rankedPoisForSlot(const TripRequest& request, const std::string& slot, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const;
    Stop makeStop(const std::string& slot, const Poi& poi, int startMinutes, int travelMinutes, double score, const TripRequest& request) const;
    std::vector<ScoreComponent> buildScoreBreakdown(const TripRequest& request, const Poi& poi, const std::string& currentPoiId, int currentTime, const std::set<std::string>& used) const;
    DayPlan planDayWithBeamSearch(const TripRequest& request, int day, const std::string& hotelId, std::set<std::string>& used) const;
    int paceExtraBreakMinutes(const std::string& pace) const;
    int routeTravelMinutes(const std::string& startId, const std::vector<Stop>& stops) const;
    void optimizeDayOrder(const std::string& startId, DayPlan& day) const;
    void explainDayConstraints(const TripRequest& request, const std::set<std::string>& used, DayPlan& day) const;
    ComparisonMetrics buildComparisonMetrics(const TripRequest& request, const Itinerary& itinerary) const;
    void assignParetoRanks(std::vector<Itinerary>& candidates) const;
};

}  // namespace tourpass
