#include <iostream>
#include <stdexcept>
#include <string>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <filesystem>
#include <atomic>
#include <thread>
#include <vector>

#include "httplib.h"
#include "tourpass/api.h"
#include "tourpass/data_loader.h"
#include "tourpass/llm.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"
#include "tourpass/service_runtime.h"
#include "tourpass/sqlite_store.h"

namespace {

int testsRun = 0;

void setEnvVar(const char* key, const char* value) {
#ifdef _WIN32
    _putenv_s(key, value);
#else
    if (value[0] == '\0') {
        unsetenv(key);
    } else {
        setenv(key, value, 1);
    }
#endif
}

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
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    expectTrue(data.pois.size() >= 10, "loads changsha pois");
    expectTrue(data.edges.size() >= 10, "loads commute edges");
}

void testGraphShortestPath() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
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

void testGraphPrecomputesShortestMinuteCache() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);

    auto stats = graph.distanceCacheStats();
    expectTrue(stats.enabled, "graph precomputes shortest-minute cache");
    expectTrue(stats.mode == "all_pairs", "small default graph uses all-pairs cache");
    expectTrue(stats.poiCount == data.pois.size(), "distance cache reports poi count");
    expectTrue(stats.entries >= data.pois.size() * data.pois.size(), "distance cache stores all-pairs minute entries");
    expectTrue(graph.shortestMinutes("hotel_wuyi", "yuelu_academy") == graph.shortestRoute("hotel_wuyi", "yuelu_academy").travelMinutes,
               "cached shortest minutes match dijkstra route cost");
}

void testGraphDistanceCacheModesReturnSameShortestMinutes() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::DistanceCacheConfig allPairsConfig;
    allPairsConfig.mode = tourpass::DistanceCacheMode::AllPairs;
    tourpass::DistanceCacheConfig onDemandConfig;
    onDemandConfig.mode = tourpass::DistanceCacheMode::OnDemand;
    onDemandConfig.onDemandEntries = 2;
    tourpass::DistanceCacheConfig disabledConfig;
    disabledConfig.mode = tourpass::DistanceCacheMode::Disabled;

    tourpass::PoiGraph allPairs(data.pois, data.edges, allPairsConfig);
    tourpass::PoiGraph onDemand(data.pois, data.edges, onDemandConfig);
    tourpass::PoiGraph disabled(data.pois, data.edges, disabledConfig);

    int expected = allPairs.shortestRoute("hotel_wuyi", "yuelu_academy").travelMinutes;
    expectTrue(allPairs.shortestMinutes("hotel_wuyi", "yuelu_academy") == expected, "all-pairs mode matches route cost");
    expectTrue(onDemand.shortestMinutes("hotel_wuyi", "yuelu_academy") == expected, "on-demand mode matches route cost");
    expectTrue(disabled.shortestMinutes("hotel_wuyi", "yuelu_academy") == expected, "disabled cache mode matches route cost");

    (void)onDemand.shortestMinutes("hotel_wuyi", "yuelu_academy");
    (void)onDemand.shortestMinutes("hotel_wuyi", "hunan_museum");
    (void)onDemand.shortestMinutes("hotel_wuyi", "juzizhou");
    auto stats = onDemand.distanceCacheStats();
    expectTrue(stats.mode == "on_demand", "on-demand cache reports active mode");
    expectTrue(stats.entries <= 2, "on-demand cache respects configured capacity");
    expectTrue(stats.hits >= 1, "on-demand cache records hits");
    expectTrue(stats.misses >= 3, "on-demand cache records misses");
    expectTrue(stats.evictions >= 1, "on-demand cache evicts least recently used distances");

    auto disabledStats = disabled.distanceCacheStats();
    expectTrue(!disabledStats.enabled, "disabled distance cache reports disabled");
    expectTrue(disabledStats.mode == "disabled", "disabled cache reports active mode");
}

void testGraphAutoDistanceCacheChoosesOnDemandForLargeGraph() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::DistanceCacheConfig config;
    config.mode = tourpass::DistanceCacheMode::Auto;
    config.maxAllPairsPois = 1;
    config.onDemandEntries = 8;
    tourpass::PoiGraph graph(data.pois, data.edges, config);
    auto stats = graph.distanceCacheStats();
    expectTrue(stats.mode == "on_demand", "auto cache switches to on-demand when POI count exceeds threshold");
    expectTrue(stats.maxEntries == 8, "auto on-demand cache reports configured capacity");
}

void testPlanner() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
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
        expectTrue(day.timeWindowFeasible, "sample itinerary passes strict time-window feasibility");
        expectTrue(!day.timeWindowDiagnostics.empty(), "planner returns day-level time-window diagnostics");
        int previousStart = 0;
        for (const auto& stop : day.stops) {
            if (stop.slot == "午餐") hasLunch = true;
            if (stop.slot == "晚餐") hasDinner = true;
            if (stop.poiName == "湖南博物院") hasHunanMuseum = true;
            if (stop.poiName == "橘子洲") hasJuzizhou = true;
            expectTrue(stop.startMinutes >= previousStart, "planner keeps stops in chronological order");
            previousStart = stop.startMinutes;
            expectTrue(stop.endMinutes <= sampleRequest().endMinutes, "stop stays within day end time");
            expectTrue(!stop.timeWindowStatus.empty(), "stop exposes time-window status");
            expectTrue(!stop.timeWindowReason.empty(), "stop exposes precise time-window reason");
            if (stop.slot == "午餐") {
                expectTrue(stop.startMinutes >= tourpass::parseTimeToMinutes("11:30"), "lunch starts inside lunch window");
                expectTrue(stop.endMinutes <= tourpass::parseTimeToMinutes("13:30"), "lunch ends inside lunch window");
            }
            if (stop.slot == "晚餐") {
                expectTrue(stop.startMinutes >= tourpass::parseTimeToMinutes("17:30"), "dinner starts inside dinner window");
                expectTrue(stop.endMinutes <= tourpass::parseTimeToMinutes("19:30"), "dinner ends inside dinner window");
            }
        }
    }
    expectTrue(hasLunch, "planner inserts lunch");
    expectTrue(hasDinner, "planner inserts dinner");
    expectTrue(hasHunanMuseum, "planner prioritizes Hunan Museum must visit");
    expectTrue(hasJuzizhou, "planner prioritizes Juzizhou must visit");
}

void testStrictTimeWindowDiagnosticsForTightDay() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.days = 1;
    request.startMinutes = tourpass::parseTimeToMinutes("16:20");
    request.endMinutes = tourpass::parseTimeToMinutes("19:00");
    request.mustVisit = {"湖南博物院"};

    tourpass::Itinerary itinerary = planner.plan(request);
    expectTrue(!itinerary.days.empty(), "tight day still returns a day plan");
    const auto& day = itinerary.days.front();
    expectTrue(!day.timeWindowDiagnostics.empty(), "tight day returns time-window diagnostics");

    bool explainsSpecificIssue = false;
    for (const auto& diagnostic : day.timeWindowDiagnostics) {
        if (diagnostic.find("晚于关闭时间") != std::string::npos ||
            diagnostic.find("超出") != std::string::npos ||
            diagnostic.find("餐饮窗口") != std::string::npos) {
            explainsSpecificIssue = true;
        }
    }
    for (const auto& stop : day.stops) {
        if (stop.timeWindowStatus != "ok" && !stop.timeWindowReason.empty()) {
            explainsSpecificIssue = true;
        }
    }
    expectTrue(explainsSpecificIssue, "time-window diagnostics explain precise feasibility issues");
}

void testUnscheduledReasonForUnknownMustVisit() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
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
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 3;
    auto candidates = planner.planCandidates(request);
    expectTrue(candidates.size() == 3, "planner returns requested candidate count");
    expectTrue(candidates.front().city == "长沙", "candidate keeps city");
    expectTrue(candidates.front().totalScore > 0.0, "candidate has score");

    bool hasDistinctVariantName = false;
    bool hasDistinctSummary = false;
    std::set<std::string> variantNames;
    for (const auto& candidate : candidates) {
        variantNames.insert(candidate.variantName);
        if (candidate.variantName.find("方案") != std::string::npos) {
            hasDistinctVariantName = true;
        }
        if (!candidate.days.empty() && candidate.days.front().summary.find("演示重点") != std::string::npos) {
            hasDistinctSummary = true;
        }
    }
    expectTrue(hasDistinctVariantName, "candidates expose interview-friendly variant names");
    expectTrue(hasDistinctSummary, "candidates explain each variant focus");
    expectTrue(variantNames.size() == candidates.size(), "candidate variant names are unique");
    expectTrue(candidates.front().comparison.totalStops > 0, "candidate exposes total stop count for comparison");
    expectTrue(candidates.front().comparison.mustVisitCovered >= 2, "candidate exposes must visit coverage");
    expectTrue(candidates.front().comparison.openTimeRisks == 0, "candidate exposes open time risk count");
    expectTrue(candidates.front().comparison.unscheduledCount == 0, "candidate comparison excludes informational unscheduled notes");
}

void testPlannerExplanationsAreInterviewFriendly() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::Itinerary itinerary = planner.plan(sampleRequest());

    bool stopExplainsDecision = false;
    bool constraintsExplainAlgorithm = false;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            if (stop.reason.find("决策依据") != std::string::npos &&
                stop.reason.find("通勤") != std::string::npos) {
                stopExplainsDecision = true;
            }
        }
        for (const auto& explanation : day.constraintExplanations) {
            if (explanation.find("算法") != std::string::npos ||
                explanation.find("约束") != std::string::npos) {
                constraintsExplainAlgorithm = true;
            }
        }
    }
    expectTrue(stopExplainsDecision, "stop reason explains decision inputs");
    expectTrue(constraintsExplainAlgorithm, "constraints mention algorithm or constraints");
}

void testPlannerStopScoreBreakdown() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::Itinerary itinerary = planner.plan(sampleRequest());

    bool hasBreakdown = false;
    bool breakdownMatchesScore = false;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            if (!stop.scoreBreakdown.empty()) {
                hasBreakdown = true;
                double total = 0.0;
                for (const auto& component : stop.scoreBreakdown) {
                    total += component.value;
                }
                if (std::abs(total - stop.score) < 0.2) {
                    breakdownMatchesScore = true;
                }
            }
        }
    }

    expectTrue(hasBreakdown, "planner exposes score breakdown for stops");
    expectTrue(breakdownMatchesScore, "score breakdown adds up to the stop score");
}

bool itineraryHasScoreComponent(const tourpass::Itinerary& itinerary, const std::string& label) {
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            for (const auto& component : stop.scoreBreakdown) {
                if (component.label == label) {
                    return true;
                }
            }
        }
    }
    return false;
}

void testCandidateStrategiesHaveRealWeights() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 5;
    auto candidates = planner.planCandidates(request);

    bool hasLowTravel = false;
    bool hasCompact = false;
    bool hasCulture = false;
    bool hasFood = false;
    bool hasRainy = false;
    for (const auto& candidate : candidates) {
        if (candidate.variantName.find("轻松少走路") != std::string::npos) {
            hasLowTravel = itineraryHasScoreComponent(candidate, "短通勤策略");
        }
        if (candidate.variantName.find("紧凑多覆盖") != std::string::npos) {
            hasCompact = itineraryHasScoreComponent(candidate, "紧凑策略");
        }
        if (candidate.variantName.find("文化优先") != std::string::npos) {
            hasCulture = itineraryHasScoreComponent(candidate, "文化策略");
        }
        if (candidate.variantName.find("美食优先") != std::string::npos) {
            hasFood = itineraryHasScoreComponent(candidate, "美食策略");
        }
        if (candidate.variantName.find("雨天室内") != std::string::npos) {
            hasRainy = itineraryHasScoreComponent(candidate, "雨天策略");
        }
    }

    expectTrue(hasLowTravel, "low travel candidate applies short commute weights");
    expectTrue(hasCompact, "compact candidate applies compact weights");
    expectTrue(hasCulture, "culture candidate applies culture weights");
    expectTrue(hasFood, "food candidate applies food weights");
    expectTrue(hasRainy, "rainy candidate applies indoor/rainy weights");
}

void testCandidateParetoRanking() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 5;
    auto candidates = planner.planCandidates(request);

    bool hasFrontier = false;
    bool allRanked = true;
    bool allExplainTradeoff = true;
    bool mentionsNonDominatedSorting = false;
    for (const auto& candidate : candidates) {
        if (candidate.comparison.paretoRank == 1) {
            hasFrontier = true;
        }
        if (candidate.comparison.paretoRank < 1) {
            allRanked = false;
        }
        if (candidate.comparison.tradeoffSummary.empty()) {
            allExplainTradeoff = false;
        }
        if (candidate.comparison.tradeoffSummary.find("标准非支配分层") != std::string::npos) {
            mentionsNonDominatedSorting = true;
        }
        if (candidate.comparison.dominated) {
            expectTrue(candidate.comparison.paretoRank > 1, "dominated candidate is not on first Pareto front");
        }
    }

    expectTrue(hasFrontier, "at least one candidate is on Pareto frontier");
    expectTrue(allRanked, "all candidates receive Pareto ranks");
    expectTrue(allExplainTradeoff, "all candidates explain multi-objective tradeoff");
    expectTrue(mentionsNonDominatedSorting, "pareto explanation states standard non-dominated sorting");
}

void testCandidateDiversityMetrics() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 5;
    auto candidates = planner.planCandidates(request);

    expectTrue(candidates.size() >= 2, "planner returns multiple candidates for diversity metrics");
    expectTrue(candidates.front().comparison.poiOverlapWithBaseline == 1.0, "baseline has full poi overlap with itself");
    expectTrue(candidates.front().comparison.areaOverlapWithBaseline == 1.0, "baseline has full area overlap with itself");
    expectTrue(candidates.front().comparison.uniquePoiCount == 0, "baseline has no unique pois relative to itself");
    expectTrue(!candidates.front().comparison.diversityTags.empty(), "baseline exposes diversity tag");

    bool hasNonBaselineDiversity = false;
    for (size_t i = 1; i < candidates.size(); ++i) {
        const auto& metrics = candidates[i].comparison;
        expectTrue(metrics.poiOverlapWithBaseline >= 0.0 && metrics.poiOverlapWithBaseline <= 1.0, "poi overlap ratio stays in range");
        expectTrue(metrics.areaOverlapWithBaseline >= 0.0 && metrics.areaOverlapWithBaseline <= 1.0, "area overlap ratio stays in range");
        expectTrue(metrics.uniquePoiCount >= 0, "unique poi count is non-negative");
        expectTrue(!metrics.diversityTags.empty(), "candidate exposes diversity tags");
        expectTrue(!metrics.diversitySummary.empty(), "candidate explains diversity summary");
        if (metrics.uniquePoiCount > 0 || metrics.poiOverlapWithBaseline < 1.0) {
            hasNonBaselineDiversity = true;
        }
    }
    expectTrue(hasNonBaselineDiversity, "at least one candidate differs from the baseline");

    nlohmann::json serialized = tourpass::itineraryToJson(candidates[1]);
    expectTrue(serialized["comparison"]["poi_overlap_with_baseline"].is_number(), "json includes poi overlap");
    expectTrue(serialized["comparison"]["area_overlap_with_baseline"].is_number(), "json includes area overlap");
    expectTrue(serialized["comparison"]["unique_poi_count"].is_number_integer(), "json includes unique poi count");
    expectTrue(serialized["comparison"]["diversity_tags"].is_array(), "json includes diversity tags");
    expectTrue(serialized["comparison"]["diversity_summary"].is_string(), "json includes diversity summary");
}

std::string itinerarySignature(const tourpass::Itinerary& itinerary) {
    std::string signature;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            signature += stop.poiId + "|";
        }
    }
    return signature;
}

void testPlannerUsesBeamSearchForTopKChoices() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 5;
    auto candidates = planner.planCandidates(request);

    bool explainsBeamSearch = false;
    std::set<std::string> signatures;
    for (const auto& candidate : candidates) {
        signatures.insert(itinerarySignature(candidate));
        for (const auto& day : candidate.days) {
            if (day.optimizationSummary.find("Beam Search") != std::string::npos ||
                day.summary.find("Beam Search") != std::string::npos) {
                explainsBeamSearch = true;
            }
        }
    }

    expectTrue(explainsBeamSearch, "planner exposes Beam Search in explanations");
    expectTrue(signatures.size() >= 2, "top-k candidates contain different stop sequences");
}

void testPlannerExposesAlgorithmDebugTrace() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.candidateCount = 5;
    auto candidates = planner.planCandidates(request);

    expectTrue(!candidates.empty(), "planner returns candidates for debug trace");
    expectTrue(!candidates.front().days.empty(), "candidate has days for debug trace");
    expectTrue(!candidates.front().days.front().beamTrace.empty(), "day exposes beam trace entries");
    expectTrue(candidates.front().days.front().beamTrace.front().inputStates >= 1, "beam trace records input state count");
    expectTrue(!candidates.front().days.front().beamTrace.front().decision.empty(), "beam trace explains retention decision");
    expectTrue(candidates.front().days.front().beamTrace.front().decision.find("候选池") != std::string::npos,
               "beam trace explains candidate-pool pruning");
    expectTrue(!candidates.front().comparison.paretoDebug.empty(), "comparison exposes pareto debug evidence");

    nlohmann::json serialized = tourpass::itineraryToJson(candidates.front());
    expectTrue(serialized["days"][0]["beam_trace"].is_array(), "itinerary json includes beam_trace");
    expectTrue(serialized["comparison"]["pareto_debug"].is_array(), "itinerary json includes pareto_debug");
}

void testPlannerReadsBeamSearchParametersFromEnvironment() {
    setEnvVar("TOURPASS_BEAM_WIDTH", "2");
    setEnvVar("TOURPASS_BRANCH_FACTOR", "2");
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    tourpass::Itinerary itinerary = planner.plan(request);
    setEnvVar("TOURPASS_BEAM_WIDTH", "");
    setEnvVar("TOURPASS_BRANCH_FACTOR", "");

    expectTrue(!itinerary.days.empty(), "env-configured planner still returns days");
    expectTrue(itinerary.days.front().summary.find("最多 2") != std::string::npos,
               "planner summary reflects TOURPASS_BEAM_WIDTH");
    for (const auto& trace : itinerary.days.front().beamTrace) {
        expectTrue(trace.keptStates <= 2, "beam trace respects TOURPASS_BEAM_WIDTH");
    }
}

void testPlannerAvoidCanHardExcludePoiByName() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripRequest request = sampleRequest();
    request.days = 1;
    request.mustVisit.clear();
    request.avoid.push_back("太平老街");

    tourpass::Itinerary itinerary = planner.plan(request);
    bool hasAvoidedPoi = false;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            if (stop.poiName == "太平老街") {
                hasAvoidedPoi = true;
            }
        }
    }
    expectTrue(!hasAvoidedPoi, "avoid can hard-exclude a POI by exact name");
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
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::SearchEngine search(graph);
    auto results = search.search("历史文化", "", 5);
    expectTrue(!results.empty(), "search returns results");
    expectTrue(results.front().name == "湖南博物院" || results.front().name == "岳麓书院", "search ranks culture pois");
}

void testSearchExplainsBm25Matches() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::SearchEngine search(graph);
    auto results = search.search("室内 艺术", "attraction", 5);

    expectTrue(!results.empty(), "bm25 search returns indoor art attractions");
    expectTrue(results.front().id == "xie_zilong" || results.front().id == "li_zijian", "field-weighted search ranks indoor art venues first");
    expectTrue(!results.front().matchedTerms.empty(), "search result exposes matched terms");
    expectTrue(results.front().scoreExplanation.find("BM25") != std::string::npos, "search result explains BM25 scoring");
    expectTrue(!results.front().scoreContributions.empty(), "search result exposes BM25 score contributions");

    nlohmann::json serialized = tourpass::searchResultToJson(results.front());
    expectTrue(serialized["score_contributions"].is_array(), "search json includes score contributions");
}

void testResponseCacheTracksHitsAndEvictsLeastRecentEntry() {
    tourpass::ResponseCache cache(2, std::chrono::seconds(60));
    cache.put("a", nlohmann::json{{"value", 1}});
    cache.put("b", nlohmann::json{{"value", 2}});

    nlohmann::json cached;
    expectTrue(cache.get("a", cached), "cache returns stored response");
    expectTrue(cached["value"] == 1, "cache returns the expected JSON body");

    cache.put("c", nlohmann::json{{"value", 3}});
    expectTrue(cache.get("a", cached), "recently used cache entry is kept");
    expectTrue(!cache.get("b", cached), "least recently used cache entry is evicted");
    expectTrue(cache.stats().hits == 2, "cache records hits");
    expectTrue(cache.stats().misses == 1, "cache records misses");
}

void testSearchRebuildAndResponseCacheClear() {
    tourpass::Poi poi;
    poi.id = "mutable-poi";
    poi.name = "Old Landmark";
    poi.type = tourpass::PoiType::Attraction;
    poi.popularity = 0.0;
    tourpass::PoiGraph graph({poi}, {});
    tourpass::SearchEngine search(graph);

    auto oldResults = search.search("Old", "", 5);
    expectTrue(!oldResults.empty() && !oldResults.front().matchedTerms.empty(), "search index contains original POI fields");

    graph.findMutablePoi("mutable-poi")->name = "New Landmark";
    search.rebuild();
    auto newResults = search.search("New", "", 5);
    expectTrue(!newResults.empty() && !newResults.front().matchedTerms.empty(), "search rebuild reflects updated POI fields");

    tourpass::ResponseCache cache(2, std::chrono::seconds(60));
    cache.put("poi", nlohmann::json{{"name", "Old Landmark"}});
    cache.clear();
    expectTrue(cache.stats().entries == 0, "cache clear removes stale responses");
}

void testSavePoisAtomicallyReplacesTarget() {
    const std::string path = "output/test-pois-atomic.json";
    std::filesystem::create_directories("output");
    {
        std::ofstream out(path);
        out << "[]";
    }

    tourpass::Poi poi;
    poi.id = "saved-poi";
    poi.name = "Saved Landmark";
    poi.type = tourpass::PoiType::Attraction;
    poi.openMinutes = 0;
    poi.closeMinutes = 23 * 60 + 59;
    tourpass::savePois(path, {poi});

    auto saved = tourpass::loadPois(path);
    expectTrue(saved.size() == 1 && saved.front().name == "Saved Landmark", "atomic POI save replaces target with valid JSON");
    expectTrue(!std::filesystem::exists(path + ".tmp"), "atomic POI save removes its temporary file");
    std::filesystem::remove(path);
}

void testServiceMetricsRecordsStatusAndLatency() {
    tourpass::ServiceMetrics metrics;
    metrics.beginRequest();
    metrics.recordRequest("GET /health", 200, std::chrono::milliseconds(12), true);
    metrics.endRequest();
    metrics.recordRejectedRequest();
    metrics.recordDbWrite(true);
    metrics.recordDbWrite(false);

    nlohmann::json snapshot = metrics.toJson();
    expectTrue(snapshot["total_requests"] == 1, "metrics records total request count");
    expectTrue(snapshot["in_flight_requests"] == 0, "metrics tracks in-flight requests");
    expectTrue(snapshot["rejected_requests"] == 1, "metrics tracks rejected requests");
    expectTrue(snapshot["db"]["write_count"] == 1, "metrics tracks db writes");
    expectTrue(snapshot["db"]["write_failures"] == 1, "metrics tracks db write failures");
    expectTrue(snapshot["status_codes"]["200"] == 1, "metrics records status code buckets");
    expectTrue(snapshot["routes"]["GET /health"]["count"] == 1, "metrics records per-route count");
    expectTrue(snapshot["routes"]["GET /health"]["p95_ms"].get<double>() >= 12.0, "metrics records route latency");
}

void testSQLiteStorePersistsOperationalRecords() {
    std::remove("output/test-tourpass.sqlite");
    {
        tourpass::SQLiteStore store("output/test-tourpass.sqlite");
        expectTrue(store.enabled(), "sqlite store opens database");

        store.recordDataVersion(25, 46, "pois-hash", "edges-hash");
        store.recordPlanningRequest("req-test", "POST /trip/plan", "MISS", "{\"city\":\"长沙\"}", 200, 12);
        store.recordTripJob("job-test", "QUEUED", "{\"days\":2}", "", "", 0, 0);
        store.recordTripJob("job-test", "SUCCEEDED", "{\"days\":2}", "{\"city\":\"长沙\"}", "", 3, 42);
        store.recordBenchmarkRun("2026-05-22T00:00:00Z", 60, "[1,10,50,100,200]", "{\"ok\":true}", "docs/performance_report.md");

        auto jobs = store.recentJobs(10);
        expectTrue(!jobs.empty(), "sqlite store reads recent jobs");
        expectTrue(jobs.front()["id"] == "job-test", "sqlite store returns job id");
        expectTrue(jobs.front()["status"] == "SUCCEEDED", "sqlite store updates job status");

        int64_t userId = store.createUser("delete-trip-user", "hash", "user");
        expectTrue(userId > 0, "sqlite store creates user for trip deletion");
        int64_t tripId = store.saveTrip(userId, "长沙 2日游", "{\"city\":\"长沙\"}", "{\"city\":\"长沙\"}");
        expectTrue(tripId > 0, "sqlite store saves trip before deletion");
        expectTrue(store.deleteTrip(tripId, userId), "sqlite store deletes a user's own trip");
        expectTrue(!store.getTrip(tripId, userId).has_value(), "sqlite store no longer returns deleted trip");
        expectTrue(!store.deleteTrip(tripId, userId), "sqlite store reports missing trip on repeated deletion");

        int64_t quotaUserId = store.createUser("quota-user", "hash", "user");
        expectTrue(store.tryConsumeQuery(quotaUserId, 2) == std::optional<int>(1), "first query reservation reports one remaining");
        expectTrue(store.tryConsumeQuery(quotaUserId, 2) == std::optional<int>(0), "second query reservation consumes final quota");
        expectTrue(!store.tryConsumeQuery(quotaUserId, 2).has_value(), "query reservation rejects exhausted quota");
        store.refundQuery(quotaUserId);
        expectTrue(store.getQueryCount(quotaUserId) == 1, "failed query refunds one reservation");
        store.refundQuery(quotaUserId);
        store.refundQuery(quotaUserId);
        expectTrue(store.getQueryCount(quotaUserId) == 0, "query refunds never make usage negative");

        int64_t concurrentQuotaUserId = store.createUser("concurrent-quota-user", "hash", "user");
        std::atomic<int> acceptedReservations{0};
        std::vector<std::thread> quotaWorkers;
        for (int i = 0; i < 20; ++i) {
            quotaWorkers.emplace_back([&] {
                if (store.tryConsumeQuery(concurrentQuotaUserId, 7).has_value()) {
                    ++acceptedReservations;
                }
            });
        }
        for (auto& worker : quotaWorkers) worker.join();
        expectTrue(acceptedReservations == 7, "concurrent query reservations never exceed the limit");
        expectTrue(store.getQueryCount(concurrentQuotaUserId) == 7, "concurrent reservations persist the exact limit");

        expectTrue(store.stats()["write_count"] >= 5, "sqlite store tracks writes");
    }
    std::remove("output/test-tourpass.sqlite");
    std::remove("output/test-tourpass.sqlite-wal");
    std::remove("output/test-tourpass.sqlite-shm");
}

void testTripJobStoreRunsPlannerJobsAsynchronously() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    tourpass::TripJobStore jobs(4);

    std::string id = jobs.submit(sampleRequest(), [&](const tourpass::TripRequest& request) {
        return tourpass::itineraryToJson(planner.plan(request));
    });

    tourpass::TripJobSnapshot snapshot;
    bool finished = false;
    for (int i = 0; i < 50; ++i) {
        expectTrue(jobs.get(id, snapshot), "submitted job can be fetched");
        if (snapshot.status == "SUCCEEDED") {
            finished = true;
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }

    expectTrue(finished, "background job eventually succeeds");
    expectTrue(snapshot.result.is_object(), "successful job stores JSON result");
    expectTrue(snapshot.result["city"] == "长沙", "job result contains itinerary payload");
    expectTrue(jobs.cancel(id), "completed job can be marked cancelled for cleanup");
    expectTrue(jobs.get(id, snapshot) && snapshot.status == "CANCELLED", "cancelled job exposes cancelled status");
}

void testTripJobStoreRunsMultipleWorkersAndReportsDurations() {
    tourpass::TripJobStore jobs(8, 3);
    std::atomic<int> running{0};
    std::atomic<int> maxRunning{0};

    for (int i = 0; i < 6; ++i) {
        jobs.submit(sampleRequest(), [&](const tourpass::TripRequest&) {
            int current = ++running;
            int observed = maxRunning.load();
            while (current > observed && !maxRunning.compare_exchange_weak(observed, current)) {}
            std::this_thread::sleep_for(std::chrono::milliseconds(80));
            --running;
            return nlohmann::json{{"ok", true}};
        });
    }

    bool allFinished = false;
    for (int i = 0; i < 80; ++i) {
        auto stats = jobs.stats();
        if (stats["SUCCEEDED"] == 6) {
            allFinished = true;
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }

    auto stats = jobs.stats();
    expectTrue(allFinished, "job worker pool finishes all submitted jobs");
    expectTrue(maxRunning.load() >= 2, "job worker pool runs jobs concurrently");
    expectTrue(stats["completed_jobs"] == 6, "job stats count completed jobs");
    expectTrue(stats["failed_jobs"] == 0, "job stats count failed jobs");
    expectTrue(stats["avg_execution_ms"].get<double>() > 0.0, "job stats expose execution time");
    expectTrue(stats["avg_queue_wait_ms"].get<double>() >= 0.0, "job stats expose queue wait time");
    expectTrue(stats["worker_count"] == 3, "job stats expose worker count");
}

void testTripJobStoreRejectsWhenQueueIsFull() {
    tourpass::TripJobStore jobs(2, 1);
    jobs.submit(sampleRequest(), [](const tourpass::TripRequest&) {
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
        return nlohmann::json{{"ok", true}};
    });
    jobs.submit(sampleRequest(), [](const tourpass::TripRequest&) {
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
        return nlohmann::json{{"ok", true}};
    });
    bool rejected = false;
    try {
        jobs.submit(sampleRequest(), [](const tourpass::TripRequest&) {
            return nlohmann::json{{"ok", true}};
        });
    } catch (const tourpass::QueueFullError&) {
        rejected = true;
    }
    expectTrue(rejected, "job store rejects queued/running jobs beyond capacity");
}

void testLlmTemplateFallback() {
    auto data = tourpass::loadDataSet("data/pois_sample.json", "data/edges_sample.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::TripPlanner planner(graph);
    setEnvVar("LLM_DISABLED", "");
    setEnvVar("OPENAI_API_KEY", "");
    setEnvVar("LLM_BASE_URL", "");
    setEnvVar("LLM_MODEL", "");
    tourpass::LlmClient llm("config/not-exists.json");
    std::string explanation = llm.explain(planner.plan(sampleRequest()));
    expectTrue(explanation.find("长沙") != std::string::npos, "template fallback mentions city");
    expectTrue(explanation.find("第 1 天") != std::string::npos, "template fallback explains days");
}

void testLlmCanBeDisabledForDemo() {
    setEnvVar("LLM_DISABLED", "1");
    setEnvVar("OPENAI_API_KEY", "demo-key");
    tourpass::LlmClient llm("config/not-exists.json");
    expectTrue(!llm.isConfigured(), "LLM_DISABLED forces template mode for demos");
    setEnvVar("LLM_DISABLED", "");
    setEnvVar("OPENAI_API_KEY", "");
}

void testLlmLocalConfigIsNotOverriddenByStaleEnvKey() {
    const std::string configPath = "tourpass_llm_local_config_priority.json";
    {
        std::ofstream config(configPath);
        config << "{"
               << "\"api_key\":\"local-config-key\","
               << "\"base_url\":\"https://api.deepseek.com\","
               << "\"model\":\"deepseek-v4-flash\""
               << "}";
    }

    setEnvVar("LLM_DISABLED", "");
    setEnvVar("OPENAI_API_KEY", "stale-env-key");
    setEnvVar("LLM_BASE_URL", "");
    setEnvVar("LLM_MODEL", "");
    tourpass::LlmClient llm(configPath);
    std::remove(configPath.c_str());

    expectTrue(llm.config().apiKey == "local-config-key", "local llm config is not overridden by a stale standalone OPENAI_API_KEY");
    expectTrue(llm.config().baseUrl == "https://api.deepseek.com", "local llm config keeps provider base url");
    expectTrue(llm.config().model == "deepseek-v4-flash", "local llm config keeps provider model");
    setEnvVar("OPENAI_API_KEY", "");
}

void testLlmUsesBuiltInHttpClient() {
    httplib::Server server;
    bool sawAuthorization = false;
    server.Post("/v1/chat/completions", [&](const httplib::Request& req, httplib::Response& res) {
        sawAuthorization = req.get_header_value("Authorization") == "Bearer local-test-key";
        res.set_content(R"({"choices":[{"message":{"content":"内置 HTTP client mock explanation"}}]})", "application/json");
    });
    int port = server.bind_to_any_port("127.0.0.1");
    expectTrue(port > 0, "mock llm server binds to a local port");
    std::thread serverThread([&]() {
        server.listen_after_bind();
    });
    server.wait_until_ready();

    const std::string configPath = "tourpass_llm_test_config.json";
    {
        std::ofstream config(configPath);
        config << "{"
               << "\"api_key\":\"local-test-key\","
               << "\"base_url\":\"http://127.0.0.1:" << port << "/v1\","
               << "\"model\":\"mock-model\""
               << "}";
    }

    setEnvVar("LLM_DISABLED", "");
    setEnvVar("OPENAI_API_KEY", "");
    tourpass::LlmClient llm(configPath);
    tourpass::Itinerary itinerary;
    itinerary.city = "长沙";
    std::string explanation = llm.explain(itinerary);

    server.stop();
    serverThread.join();
    std::remove(configPath.c_str());

    expectTrue(sawAuthorization, "llm client sends bearer token through HTTP headers");
    expectTrue(explanation.find("内置 HTTP client") != std::string::npos, "llm client parses OpenAI-compatible response");
}

void testLlmRemoteErrorsFallBackToTemplate() {
    const std::string configPath = "tourpass_llm_bad_endpoint_config.json";
    {
        std::ofstream config(configPath);
        config << "{"
               << "\"api_key\":\"local-test-key\","
               << "\"base_url\":\"ftp://unsupported.example/v1\","
               << "\"model\":\"mock-model\""
               << "}";
    }

    setEnvVar("LLM_DISABLED", "");
    setEnvVar("OPENAI_API_KEY", "");
    tourpass::LlmClient llm(configPath);
    tourpass::Itinerary itinerary;
    itinerary.city = "长沙";
    std::string explanation = llm.explain(itinerary);
    std::remove(configPath.c_str());

    expectTrue(explanation.find("长沙") != std::string::npos, "remote client errors fall back to template");
}

void testCspAllowsConfiguredAssetImageOrigin() {
    setEnvVar("ASSET_BASE_URL", "");
    setEnvVar("TOURPASS_ASSET_BASE_URL", "https://pub-example.r2.dev/images");

    const std::string csp = tourpass::contentSecurityPolicy();

    expectTrue(csp.find("img-src") != std::string::npos, "csp contains img-src directive");
    expectTrue(csp.find("https://pub-example.r2.dev") != std::string::npos, "csp allows configured asset origin for images");
    expectTrue(csp.find("https://pub-example.r2.dev/images") == std::string::npos, "csp strips asset path down to origin");

    setEnvVar("TOURPASS_ASSET_BASE_URL", "");
}

}  // namespace

int main() {
    try {
        testDataLoading();
        testGraphShortestPath();
        testGraphPrecomputesShortestMinuteCache();
        testGraphDistanceCacheModesReturnSameShortestMinutes();
        testGraphAutoDistanceCacheChoosesOnDemandForLargeGraph();
        testPlanner();
        testStrictTimeWindowDiagnosticsForTightDay();
        testUnscheduledReasonForUnknownMustVisit();
        testCandidatePlans();
        testPlannerExplanationsAreInterviewFriendly();
        testPlannerStopScoreBreakdown();
        testCandidateStrategiesHaveRealWeights();
        testCandidateParetoRanking();
        testCandidateDiversityMetrics();
        testPlannerUsesBeamSearchForTopKChoices();
        testPlannerExposesAlgorithmDebugTrace();
        testPlannerReadsBeamSearchParametersFromEnvironment();
        testPlannerAvoidCanHardExcludePoiByName();
        testTripRequestCandidateValidation();
        testSearch();
        testSearchExplainsBm25Matches();
        testResponseCacheTracksHitsAndEvictsLeastRecentEntry();
        testSearchRebuildAndResponseCacheClear();
        testSavePoisAtomicallyReplacesTarget();
        testServiceMetricsRecordsStatusAndLatency();
        testSQLiteStorePersistsOperationalRecords();
        testTripJobStoreRunsPlannerJobsAsynchronously();
        testTripJobStoreRunsMultipleWorkersAndReportsDurations();
        testTripJobStoreRejectsWhenQueueIsFull();
        testLlmTemplateFallback();
        testLlmCanBeDisabledForDemo();
        testLlmLocalConfigIsNotOverriddenByStaleEnvKey();
        testLlmUsesBuiltInHttpClient();
        testLlmRemoteErrorsFallBackToTemplate();
        testCspAllowsConfiguredAssetImageOrigin();
        std::cout << "All " << testsRun << " tests passed." << std::endl;
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Test failed: " << ex.what() << std::endl;
        return 1;
    }
}
