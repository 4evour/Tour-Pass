#include <iostream>
#include <stdexcept>
#include <string>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <thread>

#include "httplib.h"
#include "tourpass/data_loader.h"
#include "tourpass/llm.h"
#include "tourpass/planner.h"
#include "tourpass/search.h"

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
        int previousStart = 0;
        for (const auto& stop : day.stops) {
            if (stop.slot == "午餐") hasLunch = true;
            if (stop.slot == "晚餐") hasDinner = true;
            if (stop.poiName == "湖南博物院") hasHunanMuseum = true;
            if (stop.poiName == "橘子洲") hasJuzizhou = true;
            expectTrue(stop.startMinutes >= previousStart, "planner keeps stops in chronological order");
            previousStart = stop.startMinutes;
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
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
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
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
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
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
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
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
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
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
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

void testSearchExplainsBm25Matches() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
    tourpass::PoiGraph graph(data.pois, data.edges);
    tourpass::SearchEngine search(graph);
    auto results = search.search("室内 艺术", "attraction", 5);

    expectTrue(!results.empty(), "bm25 search returns indoor art attractions");
    expectTrue(results.front().id == "xie_zilong" || results.front().id == "li_zijian", "field-weighted search ranks indoor art venues first");
    expectTrue(!results.front().matchedTerms.empty(), "search result exposes matched terms");
    expectTrue(results.front().scoreExplanation.find("BM25") != std::string::npos, "search result explains BM25 scoring");
}

void testLlmTemplateFallback() {
    auto data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
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

}  // namespace

int main() {
    try {
        testDataLoading();
        testGraphShortestPath();
        testPlanner();
        testUnscheduledReasonForUnknownMustVisit();
        testCandidatePlans();
        testPlannerExplanationsAreInterviewFriendly();
        testPlannerStopScoreBreakdown();
        testCandidateStrategiesHaveRealWeights();
        testCandidateParetoRanking();
        testPlannerUsesBeamSearchForTopKChoices();
        testTripRequestCandidateValidation();
        testSearch();
        testSearchExplainsBm25Matches();
        testLlmTemplateFallback();
        testLlmCanBeDisabledForDemo();
        testLlmUsesBuiltInHttpClient();
        testLlmRemoteErrorsFallBackToTemplate();
        std::cout << "All " << testsRun << " tests passed." << std::endl;
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Test failed: " << ex.what() << std::endl;
        return 1;
    }
}
