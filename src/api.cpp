#include "tourpass/api.h"

#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <thread>
#include <unordered_map>

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

struct ApiContext {
    const PoiGraph& graph;
    TripPlanner& planner;
    SearchEngine& search;
    LlmClient& llm;
    RuntimeConfig config;
    ResponseCache cache;
    ServiceMetrics metrics;
    TripJobStore jobs;
    SQLiteStore* store;

    ApiContext(const PoiGraph& graphRef, TripPlanner& plannerRef, SearchEngine& searchRef, LlmClient& llmRef, const RuntimeConfig& runtimeConfig, SQLiteStore* sqliteStore)
        : graph(graphRef),
          planner(plannerRef),
          search(searchRef),
          llm(llmRef),
          config(runtimeConfig),
          cache(runtimeConfig.cacheEntries, std::chrono::seconds(runtimeConfig.cacheTtlSeconds)),
          jobs(runtimeConfig.maxTripJobs, runtimeConfig.jobWorkerCount),
          store(sqliteStore) {}
};

struct RequestMeta {
    std::string id;
    std::chrono::steady_clock::time_point startedAt;
};

std::mutex metaMutex;
std::unordered_map<const httplib::Request*, RequestMeta> requestMeta;

void setJson(httplib::Response& res, const nlohmann::json& body, int status = 200) {
    res.status = status;
    res.set_content(body.dump(2), "application/json; charset=utf-8");
}

void setCommonHeaders(httplib::Response& res, const std::string& requestId) {
    res.set_header("X-Request-Id", requestId);
    res.set_header("Access-Control-Allow-Origin", "*");
    res.set_header("Access-Control-Allow-Headers", "Content-Type, X-Request-Id");
    res.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_header("Referrer-Policy", "no-referrer");
}

std::string queryString(const httplib::Request& req) {
    auto pos = req.target.find('?');
    if (pos == std::string::npos) return "";
    return req.target.substr(pos + 1);
}

std::string routeName(const httplib::Request& req) {
    if (req.method == "GET" && req.path == "/health") return "GET /health";
    if (req.method == "GET" && req.path == "/metrics") return "GET /metrics";
    if (req.method == "GET" && req.path == "/history/jobs") return "GET /history/jobs";
    if (req.method == "POST" && req.path == "/benchmark/runs") return "POST /benchmark/runs";
    if (req.method == "POST" && req.path == "/trip/plan") return "POST /trip/plan";
    if (req.method == "POST" && req.path == "/trip/jobs") return "POST /trip/jobs";
    if (req.method == "GET" && req.path.find("/trip/jobs/") == 0) return "GET /trip/jobs/{id}";
    if (req.method == "DELETE" && req.path.find("/trip/jobs/") == 0) return "DELETE /trip/jobs/{id}";
    if (req.method == "GET" && req.path == "/route/shortest") return "GET /route/shortest";
    if (req.method == "POST" && req.path == "/trip/alternatives") return "POST /trip/alternatives";
    if (req.method == "GET" && req.path == "/poi/search") return "GET /poi/search";
    if (req.method == "POST" && req.path == "/itinerary/explain") return "POST /itinerary/explain";
    return req.method + " " + req.path;
}

std::string extractJobId(const httplib::Request& req) {
    const std::string prefix = "/trip/jobs/";
    if (req.path.find(prefix) != 0) return "";
    return req.path.substr(prefix.size());
}

nlohmann::json planJson(ApiContext& context, const TripRequest& tripRequest) {
    if (tripRequest.candidateCount > 1) {
        nlohmann::json candidates = nlohmann::json::array();
        for (const auto& itinerary : context.planner.planCandidates(tripRequest)) {
            candidates.push_back(itineraryToJson(itinerary));
        }
        return {{"city", tripRequest.city}, {"candidates", candidates}};
    }
    return itineraryToJson(context.planner.plan(tripRequest));
}

bool serveFromCache(ApiContext& context, httplib::Response& res, const std::string& key) {
    nlohmann::json cached;
    if (context.cache.get(key, cached)) {
        context.metrics.recordCacheHit();
        res.set_header("X-Cache", "HIT");
        setJson(res, cached);
        return true;
    }
    context.metrics.recordCacheMiss();
    res.set_header("X-Cache", "MISS");
    return false;
}

void recordDbWrite(ApiContext& context, const std::function<void(SQLiteStore&)>& writer) {
    if (!context.store || !context.store->enabled()) return;
    try {
        writer(*context.store);
        context.metrics.recordDbWrite(true);
    } catch (...) {
        context.metrics.recordDbWrite(false);
    }
}

void installMiddleware(httplib::Server& server, ApiContext& context) {
    server.set_payload_max_length(context.config.maxBodyBytes);
    server.set_pre_routing_handler([&](const httplib::Request& req, httplib::Response& res) {
        std::string requestId = req.get_header_value("X-Request-Id");
        if (requestId.empty()) requestId = makeRequestId();
        context.metrics.beginRequest();
        setCommonHeaders(res, requestId);
        {
            std::lock_guard<std::mutex> lock(metaMutex);
            requestMeta[&req] = RequestMeta{requestId, std::chrono::steady_clock::now()};
        }
        if (context.config.maxInFlightRequests > 0 &&
            context.metrics.inFlightRequests() > static_cast<int64_t>(context.config.maxInFlightRequests)) {
            context.metrics.recordRejectedRequest();
            setJson(res, errorJson("TOO_MANY_REQUESTS", "当前进行中的请求过多", {{"max_in_flight", context.config.maxInFlightRequests}}), 429);
            return httplib::Server::HandlerResponse::Handled;
        }

        if (req.method == "OPTIONS") {
            res.status = 204;
            return httplib::Server::HandlerResponse::Handled;
        }
        if ((req.method == "POST" || req.method == "PUT" || req.method == "PATCH") && req.body.size() > context.config.maxBodyBytes) {
            setJson(res, errorJson("PAYLOAD_TOO_LARGE", "请求体超过服务限制", {{"max_body_bytes", context.config.maxBodyBytes}}), 413);
            return httplib::Server::HandlerResponse::Handled;
        }
        return httplib::Server::HandlerResponse::Unhandled;
    });

    server.set_post_routing_handler([&](const httplib::Request& req, httplib::Response& res) {
        RequestMeta meta;
        {
            std::lock_guard<std::mutex> lock(metaMutex);
            auto found = requestMeta.find(&req);
            if (found != requestMeta.end()) {
                meta = found->second;
                requestMeta.erase(found);
            } else {
                meta = RequestMeta{makeRequestId(), std::chrono::steady_clock::now()};
            }
        }
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - meta.startedAt);
        res.set_header("X-Request-Id", meta.id);
        res.set_header("X-Response-Time-Ms", std::to_string(elapsed.count()));
        if (req.method == "POST" && req.path == "/trip/plan") {
            std::string cacheStatus = res.has_header("X-Cache") ? res.get_header_value("X-Cache") : "NONE";
            recordDbWrite(context, [&](SQLiteStore& store) {
                store.recordPlanningRequest(meta.id, "POST /trip/plan", cacheStatus, req.body, res.status, elapsed.count());
            });
        }
        context.metrics.recordRequest(routeName(req), res.status, elapsed, res.has_header("X-Cache"));
        context.metrics.endRequest();
    });

    server.set_exception_handler([&](const httplib::Request& req, httplib::Response& res, std::exception_ptr ep) {
        std::string reason = "unknown";
        try {
            if (ep) std::rethrow_exception(ep);
        } catch (const std::exception& ex) {
            reason = ex.what();
        }
        RequestMeta meta;
        {
            std::lock_guard<std::mutex> lock(metaMutex);
            auto found = requestMeta.find(&req);
            if (found != requestMeta.end()) {
                meta = found->second;
                requestMeta.erase(found);
            } else {
                meta = RequestMeta{makeRequestId(), std::chrono::steady_clock::now()};
            }
        }
        setCommonHeaders(res, meta.id);
        setJson(res, errorJson("INTERNAL_ERROR", "服务端处理失败", {{"reason", reason}}), 500);
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - meta.startedAt);
        res.set_header("X-Response-Time-Ms", std::to_string(elapsed.count()));
        context.metrics.recordRequest(routeName(req), 500, elapsed, false);
        context.metrics.endRequest();
    });

    server.set_error_handler([&](const httplib::Request& req, httplib::Response& res) {
        if (res.status == 404 && res.body.empty()) {
            setJson(res, errorJson("NOT_FOUND", "接口不存在", {{"path", req.path}}), 404);
        }
        return httplib::Server::HandlerResponse::Handled;
    });

    server.set_logger([](const httplib::Request& req, const httplib::Response& res) {
        std::cout << req.method << " " << req.path << " -> " << res.status;
        if (res.has_header("X-Response-Time-Ms")) {
            std::cout << " " << res.get_header_value("X-Response-Time-Ms") << "ms";
        }
        if (res.has_header("X-Request-Id")) {
            std::cout << " request_id=" << res.get_header_value("X-Request-Id");
        }
        std::cout << std::endl;
    });
}

}  // namespace

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port) {
    return runServer(graph, planner, search, llm, port, runtimeConfigFromEnv());
}

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port, const RuntimeConfig& config) {
    return runServer(graph, planner, search, llm, port, config, nullptr);
}

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, int port, const RuntimeConfig& config, SQLiteStore* store) {
    return runServer(graph, planner, search, llm, "127.0.0.1", port, config, store);
}

int runServer(const PoiGraph& graph, TripPlanner& planner, SearchEngine& search, LlmClient& llm, const std::string& host, int port, const RuntimeConfig& config, SQLiteStore* store) {
    ApiContext context(graph, planner, search, llm, config, store);
    httplib::Server server;
    server.new_task_queue = [workers = config.workerCount, maxQueue = config.maxQueuedRequests]() {
        return new httplib::ThreadPool(workers, maxQueue);
    };
    server.set_mount_point("/", "web");
    installMiddleware(server, context);

    server.Get("/health", [&](const httplib::Request&, httplib::Response& res) {
        DistanceCacheStats distanceCache = context.graph.distanceCacheStats();
        setJson(res, {
            {"status", "ok"},
            {"data_loaded", !context.graph.empty()},
            {"poi_count", context.graph.pois().size()},
            {"edge_count", context.graph.edgeCount()},
            {"distance_cache", {
                {"enabled", distanceCache.enabled},
                {"mode", distanceCache.mode},
                {"poi_count", distanceCache.poiCount},
                {"entries", distanceCache.entries},
                {"max_entries", distanceCache.maxEntries},
                {"hits", distanceCache.hits},
                {"misses", distanceCache.misses},
                {"evictions", distanceCache.evictions},
                {"startup_ms", distanceCache.startupMs}
            }},
            {"llm_configured", context.llm.isConfigured()},
            {"workers", context.config.workerCount},
            {"job_workers", context.config.jobWorkerCount},
            {"max_queue", context.config.maxQueuedRequests},
            {"max_in_flight", context.config.maxInFlightRequests},
            {"in_flight_requests", context.metrics.toJson()["in_flight_requests"]},
            {"cache_enabled", context.config.cacheEntries > 0},
            {"db_enabled", context.store && context.store->enabled()},
            {"db_path", context.store ? context.store->path() : ""}
        });
    });

    server.Get("/metrics", [&](const httplib::Request&, httplib::Response& res) {
        nlohmann::json body = context.metrics.toJson();
        CacheStats cacheStats = context.cache.stats();
        body["runtime"] = {
            {"workers", context.config.workerCount},
            {"job_workers", context.config.jobWorkerCount},
            {"max_queue", context.config.maxQueuedRequests},
            {"max_in_flight", context.config.maxInFlightRequests},
            {"max_body_bytes", context.config.maxBodyBytes}
        };
        body["cache"]["entries"] = cacheStats.entries;
        body["cache"]["evictions"] = cacheStats.evictions;
        body["jobs"] = context.jobs.stats();
        body["max_in_flight"] = context.config.maxInFlightRequests;
        if (context.store) {
            body["db"] = context.store->stats();
        } else {
            body["db"].update({{"enabled", false}, {"path", ""}});
        }
        setJson(res, body);
    });

    server.Post("/trip/plan", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            std::string key = requestCacheKey(req.method, req.path, queryString(req), req.body);
            if (serveFromCache(context, res, key)) {
                return;
            }
            auto body = nlohmann::json::parse(req.body);
            TripRequest tripRequest = tripRequestFromJson(body);
            nlohmann::json result = planJson(context, tripRequest);
            context.cache.put(key, result);
            setJson(res, result);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    server.Post("/trip/jobs", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            TripRequest tripRequest = tripRequestFromJson(body);
            std::string id = makeRequestId();
            context.jobs.submitWithId(id, tripRequest, [&, id, requestBody = req.body](const TripRequest& request) {
                nlohmann::json result = planJson(context, request);
                recordDbWrite(context, [&](SQLiteStore& store) {
                    store.recordTripJob(id, "SUCCEEDED", requestBody, result.dump(), "", 0, 0);
                });
                return result;
            });
            recordDbWrite(context, [&](SQLiteStore& store) {
                store.recordTripJob(id, "QUEUED", req.body, "", "", 0, 0);
            });
            setJson(res, {
                {"job_id", id},
                {"status", "QUEUED"},
                {"status_url", "/trip/jobs/" + id}
            }, 202);
        } catch (const QueueFullError& ex) {
            setJson(res, errorJson("QUEUE_FULL", "异步任务队列已满", {{"reason", ex.what()}, {"max_trip_jobs", context.config.maxTripJobs}}), 429);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    server.Get(R"(/trip/jobs/([A-Za-z0-9\-]+))", [&](const httplib::Request& req, httplib::Response& res) {
        TripJobSnapshot snapshot;
        std::string id = extractJobId(req);
        if (!context.jobs.get(id, snapshot)) {
            setJson(res, errorJson("JOB_NOT_FOUND", "异步任务不存在", {{"job_id", id}}), 404);
            return;
        }
        nlohmann::json body = {
            {"job_id", snapshot.id},
            {"status", snapshot.status}
        };
        if (snapshot.status == "SUCCEEDED") body["result"] = snapshot.result;
        if (snapshot.status == "FAILED") body["error"] = errorJson("JOB_FAILED", "异步任务执行失败", {{"reason", snapshot.error}})["error"];
        body["queue_wait_ms"] = snapshot.queueWaitMs;
        body["execution_ms"] = snapshot.executionMs;
        if (snapshot.status == "SUCCEEDED" || snapshot.status == "FAILED" || snapshot.status == "CANCELLED") {
            recordDbWrite(context, [&](SQLiteStore& store) {
                store.recordTripJob(snapshot.id,
                                    snapshot.status,
                                    "",
                                    snapshot.result.is_null() ? "" : snapshot.result.dump(),
                                    snapshot.error,
                                    snapshot.queueWaitMs,
                                    snapshot.executionMs);
            });
        }
        setJson(res, body);
    });

    server.Delete(R"(/trip/jobs/([A-Za-z0-9\-]+))", [&](const httplib::Request& req, httplib::Response& res) {
        std::string id = extractJobId(req);
        if (!context.jobs.cancel(id)) {
            setJson(res, errorJson("JOB_NOT_FOUND", "异步任务不存在或正在运行", {{"job_id", id}}), 404);
            return;
        }
        recordDbWrite(context, [&](SQLiteStore& store) {
            store.recordTripJob(id, "CANCELLED", "", "", "", 0, 0);
        });
        setJson(res, {{"job_id", id}, {"status", "CANCELLED"}});
    });

    server.Get("/history/jobs", [&](const httplib::Request& req, httplib::Response& res) {
        if (!context.store || !context.store->enabled()) {
            setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用", nlohmann::json::object()), 503);
            return;
        }
        int limit = 20;
        if (req.has_param("limit")) {
            try {
                limit = std::stoi(req.get_param_value("limit"));
            } catch (...) {
                setJson(res, errorJson("VALIDATION_ERROR", "limit 必须是数字"), 400);
                return;
            }
        }
        try {
            setJson(res, {{"data", context.store->recentJobs(limit)}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("DB_UNAVAILABLE", "读取任务历史失败", {{"reason", ex.what()}}), 503);
        }
    });

    server.Post("/benchmark/runs", [&](const httplib::Request& req, httplib::Response& res) {
        if (!context.store || !context.store->enabled()) {
            setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用", nlohmann::json::object()), 503);
            return;
        }
        try {
            auto body = nlohmann::json::parse(req.body);
            context.store->recordBenchmarkRun(
                body.value("started_at", ""),
                body.value("duration_seconds", 0),
                body.value("concurrency_steps_json", "[]"),
                body.value("summary_json", "{}"),
                body.value("report_path", "")
            );
            context.metrics.recordDbWrite(true);
            setJson(res, {{"status", "recorded"}}, 201);
        } catch (const std::exception& ex) {
            context.metrics.recordDbWrite(false);
            setJson(res, errorJson("DB_UNAVAILABLE", "记录 benchmark 失败", {{"reason", ex.what()}}), 503);
        }
    });

    server.Get("/route/shortest", [&](const httplib::Request& req, httplib::Response& res) {
        if (!req.has_param("from") || !req.has_param("to")) {
            setJson(res, errorJson("VALIDATION_ERROR", "from 和 to 参数必填"), 400);
            return;
        }
        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;
        std::string from = req.get_param_value("from");
        std::string to = req.get_param_value("to");
        std::string algorithm = req.has_param("algorithm") ? req.get_param_value("algorithm") : "dijkstra";
        RouteResult route = algorithm == "astar" ? context.graph.aStarRoute(from, to) : context.graph.shortestRoute(from, to);
        if (route.travelMinutes == std::numeric_limits<int>::max()) {
            setJson(res, errorJson("NOT_FOUND", "无法找到可达路线", {{"from", from}, {"to", to}}), 404);
            return;
        }
        nlohmann::json result = routeResultToJson(route);
        context.cache.put(key, result);
        setJson(res, result);
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
            for (const auto& result : context.search.search(query, type, body.value("limit", 5))) {
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

        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;
        nlohmann::json data = nlohmann::json::array();
        for (const auto& result : context.search.search(q, type, limit)) {
            data.push_back(searchResultToJson(result));
        }
        nlohmann::json result = {{"data", data}};
        context.cache.put(key, result);
        setJson(res, result);
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
                itinerary = context.planner.plan(request);
            }
            setJson(res, {{"explanation", context.llm.explain(itinerary)}, {"llm_configured", context.llm.isConfigured()}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    std::cout << "Tour Pass server listening on http://" << host << ":" << port << std::endl;
    std::cout << "Demo UI available at http://" << host << ":" << port << "/" << std::endl;
    std::cout << "Runtime workers=" << config.workerCount << " job_workers=" << config.jobWorkerCount << " max_queue=" << config.maxQueuedRequests << std::endl;
    if (!server.listen(host, port)) {
        std::cerr << "failed to listen on " << host << ":" << port << std::endl;
        return 1;
    }
    return 0;
}

}  // namespace tourpass
