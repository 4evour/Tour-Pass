#include <limits>

#include "gtest/gtest.h"

#include "tourpass/data_loader.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"

namespace {

tourpass::TripRequest sampleRequest() {
    tourpass::TripRequest request;
    request.city = "长沙";
    request.days = 2;
    request.startMinutes = tourpass::parseTimeToMinutes("09:30");
    request.endMinutes = tourpass::parseTimeToMinutes("21:30");
    request.hotelLocation = "五一广场酒店";
    request.interests = {"历史文化", "美食", "夜景"};
    request.pace = "轻松";
    request.mustVisit = {"湖南博物院", "橘子洲"};
    request.avoid = {"排队太久"};
    return request;
}

tourpass::PoiGraph loadGraph() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    return tourpass::PoiGraph(data.pois, data.edges);
}

}  // namespace

TEST(DataLoading, LoadsExpandedChangshaData) {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    EXPECT_GE(data.pois.size(), 25u);
    EXPECT_GE(data.edges.size(), 40u);
}

TEST(Graph, AStarMatchesDijkstraCost) {
    auto graph = loadGraph();
    auto dijkstra = graph.shortestRoute("hotel_wuyi", "yuelu_academy");
    auto astar = graph.aStarRoute("hotel_wuyi", "yuelu_academy");
    EXPECT_EQ(astar.travelMinutes, dijkstra.travelMinutes);
    EXPECT_EQ(astar.algorithm, "astar");
}

TEST(Planner, OptimizationDoesNotIncreaseTravel) {
    auto graph = loadGraph();
    tourpass::TripPlanner planner(graph);
    auto itinerary = planner.plan(sampleRequest());
    ASSERT_FALSE(itinerary.days.empty());
    for (const auto& day : itinerary.days) {
        EXPECT_LE(day.optimizedTravelMinutes, day.originalTravelMinutes);
        EXPECT_FALSE(day.optimizationSummary.empty());
        EXPECT_FALSE(day.constraintExplanations.empty());
        EXPECT_FALSE(day.unscheduledReasons.empty());
    }
}

TEST(Search, FindsIndoorRainAlternatives) {
    auto graph = loadGraph();
    tourpass::SearchEngine search(graph);
    auto results = search.search("室内", "attraction", 5);
    ASSERT_FALSE(results.empty());
    EXPECT_TRUE(results.front().name == "湖南博物院" || results.front().name == "长沙 IFS" || results.front().name == "长沙博物馆");
}
