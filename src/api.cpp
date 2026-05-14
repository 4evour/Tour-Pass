#include "tourpass/api.h"

#include <cstdlib>
#include <iostream>

#include "httplib.h"

namespace tourpass {

nlohmann::json errorJson(const std::string& code, const std::string& message, const nlohmann::json& details) {
    return {
        {"error", {
            {"code", code},
            {"message", message},
            {"details", details}
        }}
    };
}

namespace {

void setJson(httplib::Response& res, const nlohmann::json& body, int status = 200) {
    res.status = status;
    res.set_content(body.dump(2), "application/json; charset=utf-8");
}

}  // namespace

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port) {
    httplib::Server server;
    server.set_mount_point("/", "web");

    server.Get("/health", [&](const httplib::Request&, httplib::Response& res) {
        setJson(res, {
            {"status", "ok"},
            {"data_loaded", !graph.empty()},
            {"poi_count", graph.pois().size()},
            {"llm_configured", llm.isConfigured()}
        });
    });

    server.Post("/trip/plan", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            TripRequest tripRequest = tripRequestFromJson(body);
            if (tripRequest.candidateCount > 1) {
                nlohmann::json candidates = nlohmann::json::array();
                for (const auto& itinerary : planner.planCandidates(tripRequest)) {
                    candidates.push_back(itineraryToJson(itinerary));
                }
                setJson(res, {{"city", tripRequest.city}, {"candidates", candidates}});
            } else {
                Itinerary itinerary = planner.plan(tripRequest);
                setJson(res, itineraryToJson(itinerary));
            }
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    server.Get("/route/shortest", [&](const httplib::Request& req, httplib::Response& res) {
        if (!req.has_param("from") || !req.has_param("to")) {
            setJson(res, errorJson("VALIDATION_ERROR", "from 和 to 参数必填"), 400);
            return;
        }
        std::string from = req.get_param_value("from");
        std::string to = req.get_param_value("to");
        std::string algorithm = req.has_param("algorithm") ? req.get_param_value("algorithm") : "dijkstra";
        RouteResult route = algorithm == "astar" ? graph.aStarRoute(from, to) : graph.shortestRoute(from, to);
        if (route.travelMinutes == std::numeric_limits<int>::max()) {
            setJson(res, errorJson("NOT_FOUND", "无法找到可达路线", {{"from", from}, {"to", to}}), 404);
            return;
        }
        setJson(res, routeResultToJson(route));
    });

    server.Post("/trip/alternatives", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string scenario = body.value("scenario", "太累");
            std::string type = "attraction";
            std::string query = "室内";
            if (scenario == "下雨") {
                query = "室内";
            } else if (scenario == "闭馆") {
                query = "街区";
            } else if (scenario == "预算降低") {
                query = "预算友好";
                type = "restaurant";
            } else if (scenario == "太累") {
                query = "休闲";
            }

            nlohmann::json data = nlohmann::json::array();
            for (const auto& result : search.search(query, type, body.value("limit", 5))) {
                data.push_back(searchResultToJson(result));
            }
            setJson(res, {
                {"scenario", scenario},
                {"strategy", "按场景关键词召回可替换 POI，并优先选择低绕路、低体力成本方案。"},
                {"data", data}
            });
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    server.Get("/poi/search", [&](const httplib::Request& req, httplib::Response& res) {
        std::string q = req.has_param("q") ? req.get_param_value("q") : "";
        std::string type = req.has_param("type") ? req.get_param_value("type") : "";
        int limit = 10;
        if (req.has_param("limit")) {
            try {
                limit = std::stoi(req.get_param_value("limit"));
            } catch (...) {
                setJson(res, errorJson("VALIDATION_ERROR", "limit 必须是数字"), 400);
                return;
            }
        }

        nlohmann::json data = nlohmann::json::array();
        for (const auto& result : search.search(q, type, limit)) {
            data.push_back(searchResultToJson(result));
        }
        setJson(res, {{"data", data}});
    });

    server.Post("/itinerary/explain", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            Itinerary itinerary;
            itinerary.city = body.value("city", "长沙");
            if (body.contains("itinerary")) {
                itinerary.city = body.at("itinerary").value("city", itinerary.city);
            }
            if (body.contains("days")) {
                itinerary.city = body.value("city", itinerary.city);
            }

            if (body.contains("days") && body.at("days").is_array()) {
                for (const auto& dayJson : body.at("days")) {
                    DayPlan day;
                    day.day = dayJson.value("day", static_cast<int>(itinerary.days.size()) + 1);
                    day.summary = dayJson.value("summary", "");
                    if (dayJson.contains("stops")) {
                        for (const auto& stopJson : dayJson.at("stops")) {
                            Stop stop;
                            stop.slot = stopJson.value("slot", "");
                            stop.poiName = stopJson.value("poi_name", "");
                            stop.startMinutes = parseTimeToMinutes(stopJson.value("start_time", "09:00"));
                            stop.endMinutes = parseTimeToMinutes(stopJson.value("end_time", "10:00"));
                            stop.reason = stopJson.value("reason", "");
                            day.stops.push_back(stop);
                        }
                    }
                    itinerary.days.push_back(day);
                }
            } else {
                TripRequest request = tripRequestFromJson(body);
                itinerary = planner.plan(request);
            }
            setJson(res, {{"explanation", llm.explain(itinerary)}, {"llm_configured", llm.isConfigured()}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    std::cout << "Tour Pass server listening on http://127.0.0.1:" << port << std::endl;
    std::cout << "Demo UI available at http://127.0.0.1:" << port << "/" << std::endl;
    if (!server.listen("127.0.0.1", port)) {
        std::cerr << "failed to listen on port " << port << std::endl;
        return 1;
    }
    return 0;
}

}  // namespace tourpass
