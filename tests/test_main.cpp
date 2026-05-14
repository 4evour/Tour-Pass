#include <iostream>
#include <stdexcept>
#include <string>
#include <cstdlib>

#include "tourpass/data_loader.h"
#include "tourpass/llm.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"

namespace {

int testsRun = 0;

void expectTrue(bool condition, const std::string& message) {
    ++testsRun;
    if (!condition) {
        throw std::runtime_error(message);
    }
}

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

void testDataLoading() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    expectTrue(data.pois.size() >= 10, "loads changsha pois");
    expectTrue(data.edges.size() >= 10, "loads commute edges");
}

void testGraphShortestPath() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    int minutes = graph.shortestMinutes("hotel_wuyi", "hunan_museum");
    expectTrue(minutes == 22, "uses transit minutes for direct shortest path");
    expectTrue(graph.shortestMinutes("missing", "hunan_museum") == std::numeric_limits<int>::max(), "unknown node is unreachable");

    tourpass::RouteResult route = graph.shortestRoute("hotel_wuyi", "yuelu_academy");
    expectTrue(route.travelMinutes > 0 && route.travelMinutes < 90, "dijkstra returns route travel minutes");
    expectTrue(route.path.front() == "hotel_wuyi", "route starts from requested node");
    expectTrue(route.path.back() == "yuelu_academy", "route ends at requested node");

    tourpass::RouteResult astar = graph.aStarRoute("hotel_wuyi", "yuelu_academy");
    expectTrue(astar.algorithm == "astar", "astar route reports algorithm");
    expectTrue(astar.travelMinutes == route.travelMinutes, "astar route matches dijkstra cost on sample graph");
}

void testPlanner() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::Itinerary itinerary = planner.plan(sampleRequest());

    expectTrue(itinerary.days.size() == 2, "planner returns requested days");
    expectTrue(!itinerary.days.front().stops.empty(), "planner creates stops");

    bool hasLunch = false;
    bool hasDinner = false;
    bool hasHunanMuseum = false;
    bool hasJuzizhou = false;
    for (const auto& day : itinerary.days) {
        expectTrue(day.optimizedTravelMinutes <= day.originalTravelMinutes, "2-opt/local swap does not increase travel");
        expectTrue(!day.optimizationSummary.empty(), "planner returns optimization summary");
        expectTrue(!day.constraintExplanations.empty(), "planner explains constraints");
        expectTrue(!day.unscheduledReasons.empty(), "planner returns unscheduled reasons");
        for (const auto& stop : day.stops) {
            if (stop.slot == "午餐") hasLunch = true;
            if (stop.slot == "晚餐") hasDinner = true;
            if (stop.poiName == "湖南博物院") hasHunanMuseum = true;
            if (stop.poiName == "橘子洲") hasJuzizhou = true;
            expectTrue(stop.endMinutes <= sampleRequest().endMinutes, "stop stays within day end time");
        }
    }
    expectTrue(hasLunch, "planner inserts lunch");
    expectTrue(hasDinner, "planner inserts dinner");
    expectTrue(hasHunanMuseum, "planner prioritizes Hunan Museum must visit");
    expectTrue(hasJuzizhou, "planner prioritizes Juzizhou must visit");
}

void testUnscheduledReasonForUnknownMustVisit() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.mustVisit.push_back("不存在的景点");
    tourpass::Itinerary itinerary = planner.plan(request);

    bool explained = false;
    for (const auto& day : itinerary.days) {
        for (const auto& reason : day.unscheduledReasons) {
            if (reason.find("不存在的景点") != std::string::npos) {
                explained = true;
            }
        }
    }
    expectTrue(explained, "unknown must visit gets unscheduled reason");
}

void testCandidatePlans() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 3;
    auto candidates = planner.planCandidates(request);
    expectTrue(candidates.size() == 3, "planner returns requested candidate count");
    expectTrue(candidates.front().city == "长沙", "candidate keeps city");
    expectTrue(candidates.front().totalScore > 0.0, "candidate has score");
}

void testTripRequestCandidateValidation() {
    nlohmann::json input = {
        {"city", "长沙"},
        {"days", 2},
        {"candidate_count", 3}
    };
    tourpass::TripRequest request = tourpass::tripRequestFromJson(input);
    expectTrue(request.candidateCount == 3, "request parses candidate count");

    input["candidate_count"] = 6;
    bool threw = false;
    try {
        (void)tourpass::tripRequestFromJson(input);
    } catch (...) {
        threw = true;
    }
    expectTrue(threw, "request rejects too many candidates");
}

void testSearch() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::SearchEngine search(graph);
    auto results = search.search("历史文化", "", 5);
    expectTrue(!results.empty(), "search returns results");
    expectTrue(results.front().name == "湖南博物院" || results.front().name == "岳麓书院", "search ranks culture pois");
}

void testLlmTemplateFallback() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    _putenv_s("OPENAI_API_KEY", "");
    _putenv_s("LLM_BASE_URL", "");
    _putenv_s("LLM_MODEL", "");
    tourpass::LlmClient llm("config/not-exists.json");
    std::string explanation = llm.explain(planner.plan(sampleRequest()));
    expectTrue(explanation.find("长沙") != std::string::npos, "template fallback mentions city");
    expectTrue(explanation.find("第 1 天") != std::string::npos, "template fallback explains days");
}

}  // namespace

int main() {
    try {
        testDataLoading();
        testGraphShortestPath();
        testPlanner();
        testUnscheduledReasonForUnknownMustVisit();
        testCandidatePlans();
        testTripRequestCandidateValidation();
        testSearch();
        testLlmTemplateFallback();
        std::cout << "All " << testsRun << " tests passed." << std::endl;
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Test failed: " << ex.what() << std::endl;
        return 1;
    }
}
