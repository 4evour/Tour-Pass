#include <limits>

#include "gtest/gtest.h"

#include "tourpass/data_loader.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"

namespace {

tourpass::TripRequest sampleRequest() {
    tourpass::TripRequest request;
    request.city = "广州";
    request.days = 2;
    request.startMinutes = tourpass::parseTimeToMinutes("09:30");
    request.endMinutes = tourpass::parseTimeToMinutes("21:30");
    request.hotelLocation = "海友酒店";
    request.interests = {"历史文化", "美食", "自然风光"};
    request.pace = "轻松";
    request.mustVisit = {"广州塔", "广州市白云山风景名胜区"};
    request.avoid = {"排队太久"};
    return request;
}

tourpass::PoiGraph loadGraph() {
    auto data = tourpass::loadDataSet("data/guangzhou/pois.json", "data/guangzhou/edges.json");
    return tourpass::PoiGraph(data.pois, data.edges);
}

}  // namespace

TEST(DataLoading, LoadsGuangzhouData) {
    auto data = tourpass::loadDataSet("data/guangzhou/pois.json", "data/guangzhou/edges.json");
    EXPECT_GE(data.pois.size(), 100u);
    EXPECT_GE(data.edges.size(), 100u);
}

TEST(Graph, AStarMatchesDijkstraCost) {
    auto graph = loadGraph();
    auto dijkstra = graph.shortestRoute("amap_bfa8f6e6", "amap_a5dbc74f");
    auto astar = graph.aStarRoute("amap_bfa8f6e6", "amap_a5dbc74f");
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

TEST(Search, FindsAttractions) {
    auto graph = loadGraph();
    tourpass::SearchEngine search(graph);
    auto results = search.search("动物园", "attraction", 5);
    ASSERT_FALSE(results.empty());
    EXPECT_TRUE(results.front().name.find("动物园") != std::string::npos);
}
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
