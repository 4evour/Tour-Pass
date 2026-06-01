#include "tourpass/api.h"

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <thread>
#include <unordered_map>

#include "httplib.h"
#ifdef _WIN32
#include <winhttp.h>
#endif
#include "tourpass/auth.h"

// ---- Email sending via Resend API ----
namespace {
bool sendVerificationEmail(const std::string& toEmail, const std::string& code) {
    const char* apiKey = std::getenv("RESEND_API_KEY");
    const char* fromEmail = std::getenv("RESEND_FROM_EMAIL");
    if (!apiKey || !fromEmail) {
        std::cerr << "EMAIL: RESEND_API_KEY or RESEND_FROM_EMAIL not set" << std::endl;
        return false;
    }
    // cpp-httplib supports HTTPS when compiled with OpenSSL
    httplib::Client client("https://api.resend.com");
    client.set_connection_timeout(10);
    std::string body = "{\"from\":\"" + std::string(fromEmail) + "\","
                       "\"to\":\"" + toEmail + "\","
                       "\"subject\":\"Tour Pass - 验证码\","
                       "\"html\":\"<h2>Tour Pass 注册验证</h2><p>您的验证码是：<strong>" + code + "</strong></p><p>5 分钟内有效。</p>\"}";
    httplib::Headers headers = {
        {"Authorization", "Bearer " + std::string(apiKey)},
        {"Content-Type", "application/json"}
    };
    auto res = client.Post("/emails", headers, body, "application/json");
    if (res && res->status == 200) {
        std::cout << "EMAIL: sent verification code to " << toEmail << std::endl;
        return true;
    }
    std::cerr << "EMAIL: failed to send to " << toEmail
              << " status=" << (res ? res->status : 0)
              << " body=" << (res ? res->body : "no response") << std::endl;
    return false;
}

std::string generateNumericCode(int digits) {
    static thread_local std::mt19937 gen(std::random_device{}());
    std::uniform_int_distribution<int> dist(0, 9);
    std::string code;
    for (int i = 0; i < digits; ++i) code += std::to_string(dist(gen));
    return code;
}

int getQueryLimit(const std::string& role) {
    if (role == "admin") return 999999;
    if (role == "guest") return 3;
    return 10;
}
}

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
    std::unordered_map<std::string, CityBundle*> cities;
    std::string defaultCity;
    LlmClient& llm;
    RuntimeConfig config;
    ResponseCache cache;
    ServiceMetrics metrics;
    TripJobStore jobs;
    DataStore* store;

    ApiContext(std::unordered_map<std::string, CityBundle*> cityMap, const std::string& defCity,
               LlmClient& llmRef, const RuntimeConfig& runtimeConfig, DataStore* sqliteStore)
        : cities(std::move(cityMap)),
          defaultCity(defCity),
          llm(llmRef),
          config(runtimeConfig),
          cache(runtimeConfig.cacheEntries, std::chrono::seconds(runtimeConfig.cacheTtlSeconds)),
          jobs(runtimeConfig.maxTripJobs, runtimeConfig.jobWorkerCount),
          store(sqliteStore) {}

    CityBundle* getCity(const std::string& city) {
        auto it = cities.find(city);
        if (it != cities.end()) return it->second;
        auto def = cities.find(defaultCity);
        return def != cities.end() ? def->second : nullptr;
    }
};

struct RequestMeta {
    std::string id;
    std::chrono::steady_clock::time_point startedAt;
    int64_t userId = 0;
    std::string role;
};

std::mutex metaMutex;
std::unordered_map<const httplib::Request*, RequestMeta> requestMeta;

std::string requiredApiKey() {
    static const std::string key = [] {
        const char* env = std::getenv("TOURPASS_API_KEY");
        return env ? std::string(env) : std::string();
    }();
    return key;
}

bool isAdminValue(const char* envList, const std::string& value) {
    if (!envList || !*envList) return false;
    std::string list(envList);
    std::istringstream ss(list);
    std::string item;
    while (std::getline(ss, item, ',')) {
        size_t start = item.find_first_not_of(" \t");
        size_t end = item.find_last_not_of(" \t");
        if (start == std::string::npos) continue;
        if (item.substr(start, end - start + 1) == value) return true;
    }
    return false;
}

bool shouldAutoPromoteAdmin(DataStore* store) {
    if (!store || !store->enabled()) return false;
    try {
        auto allUsers = store->listUsers(500);
        for (const auto& u : allUsers) {
            if (u.value("role", "") == "admin") return false;
        }
    } catch (...) {
        return false;
    }
    return true;
}

struct IpRateLimiter {
    static constexpr size_t maxTotalIps = 100000;
    std::mutex mu;
    std::unordered_map<std::string, std::deque<std::chrono::steady_clock::time_point>> hits;
    int maxRequests;
    std::chrono::seconds window;

    IpRateLimiter(int max, int windowSec) : maxRequests(max), window(windowSec) {}

    bool allow(const std::string& ip) {
        std::lock_guard<std::mutex> lock(mu);
        auto now = std::chrono::steady_clock::now();
        auto& q = hits[ip];
        while (!q.empty() && now - q.front() > window) {
            q.pop_front();
        }
        if (static_cast<int>(q.size()) >= maxRequests) return false;
        q.push_back(now);
        if (hits.size() > maxTotalIps) {
            for (auto it = hits.begin(); it != hits.end();) {
                if (it->second.empty()) it = hits.erase(it);
                else ++it;
            }
        }
        return true;
    }
};

struct EmailRateLimiter {
    std::mutex mu;
    std::unordered_map<std::string, std::chrono::steady_clock::time_point> lastSentAt;
    std::chrono::seconds minInterval;
    EmailRateLimiter(int intervalSec) : minInterval(intervalSec) {}
    bool allow(const std::string& email) {
        std::lock_guard<std::mutex> lock(mu);
        auto now = std::chrono::steady_clock::now();
        auto it = lastSentAt.find(email);
        if (it != lastSentAt.end() && now - it->second < minInterval) return false;
        lastSentAt[email] = now;
        return true;
    }
};

void setJson(httplib::Response& res, const nlohmann::json& body, int status = 200) {
    res.status = status;
    res.set_content(body.dump(2), "application/json; charset=utf-8");
}

std::string corsOrigin() {
    static const std::string origin = [] {
        const char* env = std::getenv("TOURPASS_CORS_ORIGIN");
        return env ? std::string(env) : std::string();
    }();
    return origin;
}

void setCommonHeaders(httplib::Response& res, const std::string& requestId) {
    res.set_header("X-Request-Id", requestId);
    std::string origin = corsOrigin();
    if (!origin.empty()) {
        res.set_header("Access-Control-Allow-Origin", origin);
    }
    res.set_header("Access-Control-Allow-Headers", "Content-Type, X-Request-Id, Authorization");
    res.set_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS");
    res.set_header("Access-Control-Expose-Headers", "X-Request-Id, X-Response-Time-Ms, X-Cache, X-Query-Remaining");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_header("Referrer-Policy", "no-referrer");
    res.set_header("X-Frame-Options", "DENY");
    res.set_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https://*.tile.openstreetmap.org https://*.is.autonavi.com https://webapi.amap.com data:");
}

std::string queryString(const httplib::Request& req) {
    auto pos = req.target.find('?');
    if (pos == std::string::npos) return "";
    return req.target.substr(pos + 1);
}

bool constantTimeEquals(const std::string& a, const std::string& b) {
    if (a.size() != b.size()) return false;
    volatile unsigned char result = 0;
    for (size_t i = 0; i < a.size(); ++i) {
        result |= static_cast<unsigned char>(a[i]) ^ static_cast<unsigned char>(b[i]);
    }
    return result == 0;
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
    if (req.method == "POST" && req.path == "/trip/chat") return "POST /trip/chat";
    return req.method + " " + req.path;
}

std::string extractJobId(const httplib::Request& req) {
    const std::string prefix = "/trip/jobs/";
    if (req.path.find(prefix) != 0) return "";
    return req.path.substr(prefix.size());
}

nlohmann::json planJson(ApiContext& context, const TripRequest& tripRequest) {
    auto* city = context.getCity(tripRequest.city);
    if (!city) return errorJson("CITY_NOT_FOUND", "未找到城市数据: " + tripRequest.city);
    if (tripRequest.candidateCount > 1) {
        nlohmann::json candidates = nlohmann::json::array();
        for (const auto& itinerary : city->planner.planCandidates(tripRequest)) {
            candidates.push_back(itineraryToJson(itinerary));
        }
        return {{"city", tripRequest.city}, {"candidates", candidates}};
    }
    return itineraryToJson(city->planner.plan(tripRequest));
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

void recordDbWrite(ApiContext& context, const std::function<void(DataStore&)>& writer) {
    if (!context.store || !context.store->enabled()) return;
    try {
        writer(*context.store);
        context.metrics.recordDbWrite(true);
    } catch (const std::exception&) {
        context.metrics.recordDbWrite(false);
    }
}

    static EmailRateLimiter emailLimiter(60);

    void installMiddleware(httplib::Server& server, ApiContext& context) {
        static IpRateLimiter rateLimiter(60, 60);
    server.set_payload_max_length(context.config.maxBodyBytes);
    server.set_pre_routing_handler([&](const httplib::Request& req, httplib::Response& res) {
        std::string requestId = req.get_header_value("X-Request-Id");
        if (requestId.empty()) requestId = makeRequestId();
        context.metrics.beginRequest();
        setCommonHeaders(res, requestId);
        {
            std::lock_guard<std::mutex> lock(metaMutex);
            requestMeta[&req] = RequestMeta{requestId, std::chrono::steady_clock::now(), 0, ""};
        }

        if (req.method == "OPTIONS") {
            res.status = 204;
            return httplib::Server::HandlerResponse::Handled;
        }

        // --- JWT auth extraction (optional for most routes) ---
        int64_t authUserId = 0;
        std::string authRole;
        std::string authHeader = req.get_header_value("Authorization");
        if (authHeader.substr(0, 7) == "Bearer ") {
            std::string token = authHeader.substr(7);
            auto payload = verifyToken(token);
            if (payload) {
                authUserId = payload->userId;
                authRole = payload->role;
            }
        }

        // Paths that don't require auth at all
        bool isPublicPath = req.path == "/health" || req.path == "/metrics"
                         || req.path.find("/auth/") == 0
                         || req.path.find("/s/") == 0
                         || req.method == "OPTIONS"
                         || req.path == "/" || req.path == "/index.html"
                         || req.path == "/app.js" || req.path == "/styles.css"
                         || req.path == "/favicon.ico" || req.path == "/admin.html"
                         || req.path == "/admin.js" || req.path == "/profile.html"
                         || req.path == "/profile.js"
                         || req.path.find("/vendor/") == 0
                         || req.path.find("/assets/") == 0
                         || req.path.find("/images/") == 0
                         || req.path.find("/city/") == 0
                         || req.path == "/cities";

        // API key bypass (for programmatic access)
        const std::string& apiKey = requiredApiKey();
        if (!apiKey.empty()) {
            std::string provided = req.get_header_value("Authorization");
            if (provided == "Bearer " + apiKey || constantTimeEquals(req.get_header_value("X-API-Key"), apiKey)) {
                authUserId = -1;  // API key auth, no user
                authRole = "admin";
            }
        }

        // Require auth for non-public paths
        if (!isPublicPath && authUserId == 0) {
            context.metrics.recordRejectedRequest();
            setJson(res, errorJson("UNAUTHORIZED", "请先登录", {{"hint", "POST /auth/login 获取 token"}}), 401);
            return httplib::Server::HandlerResponse::Handled;
        }

        // Admin-only paths
        if (req.path.find("/admin/") == 0 && authRole != "admin") {
            context.metrics.recordRejectedRequest();
            setJson(res, errorJson("FORBIDDEN", "需要管理员权限"), 403);
            return httplib::Server::HandlerResponse::Handled;
        }

        // Query rate limit for /trip/plan and /trip/chat
        bool isQueryPath = req.path == "/trip/plan" || req.path == "/trip/chat";
        if (isQueryPath && authUserId > 0 && context.store && context.store->enabled()) {
            int used = context.store->getQueryCount(authUserId);
            int bonus = context.store->getBonusQueries(authUserId);
            int limit = getQueryLimit(authRole);
            int remaining = limit + bonus - used;
            res.set_header("X-Query-Remaining", std::to_string(std::max(0, remaining)));
            if (remaining <= 0) {
                context.metrics.recordRejectedRequest();
                setJson(res, errorJson("DAILY_LIMIT_EXCEEDED", "今日查询次数已用完，明天再来或触发彩蛋获取额外次数", {{"remaining", 0}}), 429);
                return httplib::Server::HandlerResponse::Handled;
            }
        }

        // Store auth info in response headers for route handlers to read via request
        // We use a trick: store in a thread-local map keyed by request pointer
        {
            std::lock_guard<std::mutex> lock(metaMutex);
            requestMeta[&req].userId = authUserId;
            requestMeta[&req].role = authRole;
        }

        std::string clientIp = req.remote_addr;
        if (!rateLimiter.allow(clientIp)) {
            context.metrics.recordRejectedRequest();
            setJson(res, errorJson("TOO_MANY_REQUESTS", "请求过于频繁，请稍后重试", {{"retry_after_seconds", 60}}), 429);
            return httplib::Server::HandlerResponse::Handled;
        }

        if (context.config.maxInFlightRequests > 0 &&
            context.metrics.inFlightRequests() > static_cast<int64_t>(context.config.maxInFlightRequests)) {
            context.metrics.recordRejectedRequest();
            setJson(res, errorJson("TOO_MANY_REQUESTS", "当前进行中的请求过多", {{"max_in_flight", context.config.maxInFlightRequests}}), 429);
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
                meta = RequestMeta{makeRequestId(), std::chrono::steady_clock::now(), 0, ""};
            }
        }
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - meta.startedAt);
        res.set_header("X-Request-Id", meta.id);
        res.set_header("X-Response-Time-Ms", std::to_string(elapsed.count()));
        if (req.method == "POST" && req.path == "/trip/plan") {
            std::string cacheStatus = res.has_header("X-Cache") ? res.get_header_value("X-Cache") : "NONE";
            recordDbWrite(context, [&](DataStore& store) {
                store.recordPlanningRequest(meta.id, "POST /trip/plan", cacheStatus, req.body, res.status, elapsed.count());
            });
            // Track query usage on success
            if (res.status == 200 && meta.userId > 0 && context.store && context.store->enabled()) {
                context.store->incrementQueryCount(meta.userId);
            }
        }
        if (req.method == "POST" && req.path == "/trip/chat" && res.status == 200 && meta.userId > 0 && context.store && context.store->enabled()) {
            context.store->incrementQueryCount(meta.userId);
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
            std::cerr << "ERROR " << req.method << " " << req.path << ": " << reason << std::endl;
        }
        RequestMeta meta;
        {
            std::lock_guard<std::mutex> lock(metaMutex);
            auto found = requestMeta.find(&req);
            if (found != requestMeta.end()) {
                meta = found->second;
                requestMeta.erase(found);
            } else {
                meta = RequestMeta{makeRequestId(), std::chrono::steady_clock::now(), 0, ""};
            }
        }
        setCommonHeaders(res, meta.id);
        setJson(res, errorJson("INTERNAL_ERROR", "服务端处理失败", nlohmann::json::object()), 500);
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

int runServer(std::unordered_map<std::string, std::unique_ptr<CityBundle>> cities, const std::string& defaultCity,
              LlmClient& llm, const std::string& host, int port, const RuntimeConfig& config, DataStore* store) {
    // Build raw pointer map (cities remain owned by the unique_ptr map)
    std::unordered_map<std::string, CityBundle*> cityPtrs;
    for (auto& [name, ptr] : cities) {
        cityPtrs[name] = ptr.get();
    }
    ApiContext context(std::move(cityPtrs), defaultCity, llm, config, store);
    httplib::Server server;
    server.new_task_queue = [workers = config.workerCount, maxQueue = config.maxQueuedRequests]() {
        return new httplib::ThreadPool(workers, maxQueue);
    };
    server.set_mount_point("/", "web");
    installMiddleware(server, context);

    server.Get("/health", [&](const httplib::Request&, httplib::Response& res) {
        nlohmann::json cityInfo = nlohmann::json::object();
        size_t totalPois = 0;
        for (const auto& [name, ptr] : context.cities) {
            cityInfo[name] = {{"poi_count", ptr->graph.pois().size()}, {"edge_count", ptr->graph.edgeCount()}};
            totalPois += ptr->graph.pois().size();
        }
        setJson(res, {
            {"status", "ok"},
            {"city_count", context.cities.size()},
            {"total_poi_count", totalPois},
            {"cities", cityInfo},
            {"default_city", context.defaultCity},
            {"llm_configured", context.llm.isConfigured()}
        });
    });

    // List available cities
    server.Get("/cities", [&](const httplib::Request&, httplib::Response& res) {
        nlohmann::json arr = nlohmann::json::array();
        for (const auto& [name, ptr] : context.cities) {
            arr.push_back({{"name", name}, {"poi_count", ptr->graph.pois().size()}});
        }
        setJson(res, {{"cities", arr}, {"default", context.defaultCity}});
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
            {
                std::lock_guard<std::mutex> lock(metaMutex);
                auto found = requestMeta.find(&req);
                if (found != requestMeta.end() && found->second.userId > 0) {
                    key += "@u" + std::to_string(found->second.userId);
                }
            }
            if (serveFromCache(context, res, key)) {
                return;
            }
            auto body = nlohmann::json::parse(req.body);
            TripRequest tripRequest = tripRequestFromJson(body);
            nlohmann::json result = planJson(context, tripRequest);
            context.cache.put(key, result);
            setJson(res, result);
        } catch (const std::exception& ex) {
            std::cerr << "VALIDATION /trip/plan: " << ex.what() << std::endl;
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", nlohmann::json::object()), 400);
        }
    });

    server.Post("/trip/jobs", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            TripRequest tripRequest = tripRequestFromJson(body);
            std::string id = makeRequestId();
            context.jobs.submitWithId(id, tripRequest, [&, id, requestBody = req.body](const TripRequest& request) {
                nlohmann::json result = planJson(context, request);
                recordDbWrite(context, [&](DataStore& store) {
                    store.recordTripJob(id, "SUCCEEDED", requestBody, result.dump(), "", 0, 0);
                });
                return result;
            });
            recordDbWrite(context, [&](DataStore& store) {
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
            recordDbWrite(context, [&](DataStore& store) {
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
        recordDbWrite(context, [&](DataStore& store) {
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
            std::cerr << "ERROR /history/jobs: " << ex.what() << std::endl;
            setJson(res, errorJson("DB_UNAVAILABLE", "读取任务历史失败", nlohmann::json::object()), 503);
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
            std::cerr << "ERROR /benchmark/runs: " << ex.what() << std::endl;
            context.metrics.recordDbWrite(false);
            setJson(res, errorJson("DB_UNAVAILABLE", "记录 benchmark 失败", nlohmann::json::object()), 503);
        }
    });

    server.Get("/route/shortest", [&](const httplib::Request& req, httplib::Response& res) {
        if (!req.has_param("from") || !req.has_param("to")) {
            setJson(res, errorJson("VALIDATION_ERROR", "from 和 to 参数必填"), 400);
            return;
        }
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        auto* city = context.getCity(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }
        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;
        std::string from = req.get_param_value("from");
        std::string to = req.get_param_value("to");
        std::string algorithm = req.has_param("algorithm") ? req.get_param_value("algorithm") : "dijkstra";
        RouteResult route = algorithm == "astar" ? city->graph.aStarRoute(from, to) : city->graph.shortestRoute(from, to);
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

            std::string cityName = body.value("city", context.defaultCity);
            auto* city = context.getCity(cityName);
            nlohmann::json data = nlohmann::json::array();
            if (city) {
                for (const auto& result : city->search.search(query, type, body.value("limit", 5))) {
                    data.push_back(searchResultToJson(result));
                }
            }
            setJson(res, {
                {"scenario", scenario},
                {"strategy", "按场景关键词召回可替换 POI，并优先选择低绕路、低体力成本方案。"},
                {"data", data}
            });
        } catch (const std::exception& ex) {
            std::cerr << "VALIDATION /trip/alternatives: " << ex.what() << std::endl;
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", nlohmann::json::object()), 400);
        }
    });

    server.Get("/poi/search", [&](const httplib::Request& req, httplib::Response& res) {
        std::string q = req.has_param("q") ? req.get_param_value("q") : "";
        std::string type = req.has_param("type") ? req.get_param_value("type") : "";
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        auto* city = context.getCity(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }
        int limit = 10;
        if (req.has_param("limit")) {
            try {
                limit = std::stoi(req.get_param_value("limit"));
            } catch (...) {
                setJson(res, errorJson("VALIDATION_ERROR", "limit 必须是数字"), 400);
                return;
            }
        }
        limit = std::max(1, std::min(100, limit));

        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;
        nlohmann::json data = nlohmann::json::array();
        for (const auto& result : city->search.search(q, type, limit)) {
            data.push_back(searchResultToJson(result));
        }
        nlohmann::json result = {{"data", data}};
        context.cache.put(key, result);
        setJson(res, result);
    });

    // GET /poi/areas - list all areas with POI counts
    server.Get("/poi/areas", [&](const httplib::Request& req, httplib::Response& res) {
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        auto* city = context.getCity(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }

        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;

        // Aggregate POIs by area
        std::map<std::string, nlohmann::json> areaMap;
        for (const auto& poi : city->graph.pois()) {
            if (poi.area.empty()) continue;
            auto& entry = areaMap[poi.area];
            if (!entry.contains("area")) {
                entry["area"] = poi.area;
                entry["total"] = 0;
                entry["attractions"] = 0;
                entry["restaurants"] = 0;
                entry["hotels"] = 0;
                entry["nightlife"] = 0;
                entry["lat_sum"] = 0.0;
                entry["lng_sum"] = 0.0;
            }
            entry["total"] = entry["total"].get<int>() + 1;
            if (poi.type == PoiType::Attraction) entry["attractions"] = entry["attractions"].get<int>() + 1;
            else if (poi.type == PoiType::Restaurant) entry["restaurants"] = entry["restaurants"].get<int>() + 1;
            else if (poi.type == PoiType::Hotel) entry["hotels"] = entry["hotels"].get<int>() + 1;
            else if (poi.type == PoiType::Nightlife) entry["nightlife"] = entry["nightlife"].get<int>() + 1;
            entry["lat_sum"] = entry["lat_sum"].get<double>() + poi.lat;
            entry["lng_sum"] = entry["lng_sum"].get<double>() + poi.lng;
        }

        nlohmann::json data = nlohmann::json::array();
        for (auto& [name, entry] : areaMap) {
            int total = entry["total"].get<int>();
            entry["lat"] = entry["lat_sum"].get<double>() / total;
            entry["lng"] = entry["lng_sum"].get<double>() / total;
            entry.erase("lat_sum");
            entry.erase("lng_sum");
            data.push_back(entry);
        }
        // Sort by total POI count descending
        std::sort(data.begin(), data.end(), [](const nlohmann::json& a, const nlohmann::json& b) {
            return a["total"].get<int>() > b["total"].get<int>();
        });

        nlohmann::json result = {{"data", data}};
        context.cache.put(key, result);
        setJson(res, result);
    });

    // GET /poi/by-area - list POIs in a specific area
    server.Get("/poi/by-area", [&](const httplib::Request& req, httplib::Response& res) {
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        std::string area = req.has_param("area") ? req.get_param_value("area") : "";
        std::string type = req.has_param("type") ? req.get_param_value("type") : "";
        auto* city = context.getCity(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }
        if (area.empty()) { setJson(res, errorJson("VALIDATION_ERROR", "area 参数不能为空"), 400); return; }

        int limit = 10;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) {}
        }
        limit = std::max(1, std::min(50, limit));

        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;

        nlohmann::json data = nlohmann::json::array();
        for (const auto& poi : city->graph.pois()) {
            if (poi.area != area) continue;
            if (!type.empty()) {
                std::string poiType = poi.type == PoiType::Attraction ? "attraction" :
                    poi.type == PoiType::Restaurant ? "restaurant" :
                    poi.type == PoiType::Hotel ? "hotel" :
                    poi.type == PoiType::Nightlife ? "nightlife" : "transit";
                if (poiType != type) continue;
            }
            data.push_back({
                {"id", poi.id}, {"name", poi.name},
                {"type", poi.type == PoiType::Attraction ? "attraction" :
                    poi.type == PoiType::Restaurant ? "restaurant" :
                    poi.type == PoiType::Hotel ? "hotel" :
                    poi.type == PoiType::Nightlife ? "nightlife" : "transit"},
                {"area", poi.area}, {"lat", poi.lat}, {"lng", poi.lng},
                {"popularity", poi.popularity}, {"price_level", poi.priceLevel},
                {"description", poi.description}, {"meal_type", poi.mealType},
                {"recommendation", poi.recommendation},
            });
            if (static_cast<int>(data.size()) >= limit) break;
        }
        // Sort by popularity descending
        std::sort(data.begin(), data.end(), [](const nlohmann::json& a, const nlohmann::json& b) {
            return a["popularity"].get<double>() > b["popularity"].get<double>();
        });

        nlohmann::json result = {{"data", data}, {"area", area}, {"total", static_cast<int>(data.size())}};
        context.cache.put(key, result);
        setJson(res, result);
    });

    // GET /poi/amap-search - proxy for Amap POI text search
    server.Get("/poi/amap-search", [&](const httplib::Request& req, httplib::Response& res) {
        std::string keywords = req.has_param("q") ? req.get_param_value("q") : "";
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        std::string cityCode = req.has_param("city_code") ? req.get_param_value("city_code") : "";
        int limit = 10;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) {}
        }
        limit = std::max(1, std::min(25, limit));

        if (keywords.empty()) {
            setJson(res, errorJson("VALIDATION_ERROR", "搜索关键词不能为空"), 400);
            return;
        }

        // Get Amap API key from environment
        std::string amapKey;
        if (const char* k = std::getenv("TOURPASS_AMAP_API_KEY")) amapKey = k;
        if (amapKey.empty()) {
            if (const char* k = std::getenv("AMAP_API_KEY")) amapKey = k;
        }
        if (amapKey.empty()) {
            setJson(res, errorJson("CONFIG_ERROR", "高德 API Key 未配置"), 503);
            return;
        }

        // Build Amap API URL
        std::string url = "/v3/place/text?key=" + amapKey +
            "&keywords=" + httplib::detail::encode_url(keywords) +
            "&offset=" + std::to_string(limit) +
            "&extensions=all";
        if (!cityCode.empty()) {
            url += "&city=" + cityCode;
        } else {
            url += "&city=" + httplib::detail::encode_url(cityName);
        }

        // Use WinHTTP on Windows (no OpenSSL needed), httplib SSLClient on Linux
        std::string responseBody;
        int responseStatus = 0;
#ifdef _WIN32
        {
            HINTERNET hSession = WinHttpOpen(L"TourPass/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, nullptr, nullptr, 0);
            if (!hSession) { setJson(res, errorJson("AMAP_ERROR", "WinHTTP 初始化失败"), 502); return; }
            HINTERNET hConnect = WinHttpConnect(hSession, L"restapi.amap.com", INTERNET_DEFAULT_HTTPS_PORT, 0);
            if (!hConnect) { WinHttpCloseHandle(hSession); setJson(res, errorJson("AMAP_ERROR", "WinHTTP 连接失败"), 502); return; }
            std::wstring wurl(url.begin(), url.end());
            HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", wurl.c_str(), nullptr, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
            if (!hRequest) { WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession); setJson(res, errorJson("AMAP_ERROR", "WinHTTP 请求失败"), 502); return; }
            WinHttpSetTimeouts(hRequest, 5000, 5000, 5000, 5000);
            if (WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
                WinHttpReceiveResponse(hRequest, nullptr)) {
                DWORD status = 0; DWORD statusSize = sizeof(status);
                WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &status, &statusSize, WINHTTP_NO_HEADER_INDEX);
                responseStatus = status;
                DWORD bytesRead = 0;
                char buf[4096];
                while (WinHttpReadData(hRequest, buf, sizeof(buf), &bytesRead) && bytesRead > 0) {
                    responseBody.append(buf, bytesRead);
                    bytesRead = 0;
                }
            }
            WinHttpCloseHandle(hRequest);
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
        }
#else
        {
            httplib::SSLClient amapClient("restapi.amap.com");
            amapClient.set_connection_timeout(5, 0);
            amapClient.set_read_timeout(5, 0);
            auto amapRes = amapClient.Get(url);
            if (amapRes) { responseStatus = amapRes->status; responseBody = amapRes->body; }
        }
#endif
        if (responseStatus != 200 || responseBody.empty()) {
            setJson(res, errorJson("AMAP_ERROR", "高德 API 请求失败, status=" + std::to_string(responseStatus)), 502);
            return;
        }

        try {
            auto amapData = nlohmann::json::parse(responseBody);
            if (amapData.value("status", "0") != "1") {
                setJson(res, errorJson("AMAP_ERROR", "高德 API 返回错误: " + amapData.value("info", "")), 502);
                return;
            }

            nlohmann::json data = nlohmann::json::array();
            for (const auto& poi : amapData.value("pois", nlohmann::json::array())) {
                try {
                    // Parse location "lng,lat"
                    std::string loc = poi.value("location", "");
                    double lng = 0, lat = 0;
                    if (!loc.empty()) {
                        auto comma = loc.find(',');
                        if (comma != std::string::npos) {
                            try {
                                lng = std::stod(loc.substr(0, comma));
                                lat = std::stod(loc.substr(comma + 1));
                            } catch (...) {}
                        }
                    }

                    // Safely extract fields (some may be arrays instead of strings)
                    auto safeStr = [](const nlohmann::json& j, const std::string& key) -> std::string {
                        auto it = j.find(key);
                        if (it == j.end()) return "";
                        if (it->is_string()) return it->get<std::string>();
                        if (it->is_array() && !it->empty() && (*it)[0].is_string()) return (*it)[0].get<std::string>();
                        return "";
                    };

                    nlohmann::json entry = {
                        {"id", safeStr(poi, "id")},
                        {"name", safeStr(poi, "name")},
                        {"address", safeStr(poi, "address")},
                        {"type", safeStr(poi, "type")},
                        {"lat", lat},
                        {"lng", lng},
                        {"city", safeStr(poi, "cityname")},
                        {"district", safeStr(poi, "adname")},
                        {"tel", safeStr(poi, "tel")},
                    };

                    // Safely extract biz_ext fields
                    if (poi.contains("biz_ext") && poi["biz_ext"].is_object()) {
                        entry["rating"] = safeStr(poi["biz_ext"], "rating");
                        entry["open_time"] = safeStr(poi["biz_ext"], "opentime2");
                    } else {
                        entry["rating"] = "";
                        entry["open_time"] = "";
                    }

                    // Safely extract photos
                    nlohmann::json urls = nlohmann::json::array();
                    if (poi.contains("photos") && poi["photos"].is_array()) {
                        for (const auto& p : poi["photos"]) {
                            if (p.is_object() && p.contains("url") && p["url"].is_string()) {
                                urls.push_back(p["url"].get<std::string>());
                                if (urls.size() >= 3) break;
                            }
                        }
                    }
                    entry["photos"] = urls;

                    data.push_back(entry);
                } catch (...) {
                    // Skip malformed POI entries
                    continue;
                }
            }

            nlohmann::json result = {{"data", data}, {"total", amapData.value("count", "0")}};
            setJson(res, result);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("PARSE_ERROR", "解析高德响应失败"), 502);
        }
    });

    // City guidebook (from Wikivoyage data)
    server.Get(R"(/city/([a-z]+)/guidebook)", [&](const httplib::Request& req, httplib::Response& res) {
        std::string city = req.matches[1];
        std::string path = "data/" + city + "/guidebook.json";
        std::ifstream file(path);
        if (!file.is_open()) {
            setJson(res, errorJson("NOT_FOUND", "暂无该城市攻略", {{"city", city}}), 404);
            return;
        }
        std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        try {
            setJson(res, nlohmann::json::parse(content));
        } catch (...) {
            setJson(res, errorJson("PARSE_ERROR", "攻略数据格式错误"), 500);
        }
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
                auto* city = context.getCity(request.city);
                if (city) itinerary = city->planner.plan(request);
            }
            setJson(res, {{"explanation", context.llm.explain(itinerary)}, {"llm_configured", context.llm.isConfigured()}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "请求参数不合法", {{"reason", ex.what()}}), 400);
        }
    });

    server.Post("/trip/chat", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string message = body.value("message", "");
            if (message.empty()) {
                setJson(res, errorJson("VALIDATION_ERROR", "message 不能为空"), 400);
                return;
            }

            if (!context.llm.isConfigured()) {
                setJson(res, errorJson("LLM_NOT_CONFIGURED", "自然语言规划需要配置 LLM API Key", {{"hint", "设置 LLM_BASE_URL 和 OPENAI_API_KEY 环境变量"}}), 503);
                return;
            }

            std::vector<ChatMessage> chatHistory;
            if (body.contains("context") && body["context"].is_array()) {
                for (const auto& msg : body["context"]) {
                    ChatMessage cm;
                    cm.role = msg.value("role", "user");
                    cm.content = msg.value("content", "");
                    if (!cm.content.empty()) {
                        chatHistory.push_back(cm);
                    }
                }
            }

            LlmParsedRequest parsed = context.llm.parseNaturalLanguageRequest(message, chatHistory);
            if (!parsed.parsed) {
                setJson(res, errorJson("PARSE_FAILED", "无法理解您的旅行需求", {{"detail", parsed.parseNote}}), 422);
                return;
            }

            // Get city context
            auto* city = context.getCity(parsed.request.city);
            if (!city) {
                setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市数据: " + parsed.request.city), 404);
                return;
            }

            // Step 2: Fuzzy match POI names via BM25 search
            nlohmann::json matchedPois = nlohmann::json::array();
            nlohmann::json suggestions = nlohmann::json::array();
            std::vector<std::string> resolvedMustVisit;

            for (const auto& name : parsed.unmatchedNames) {
                auto searchResults = city->search.search(name, "", 3);
                if (!searchResults.empty() && searchResults[0].score > 2.0) {
                    resolvedMustVisit.push_back(searchResults[0].id);
                    matchedPois.push_back({
                        {"query", name},
                        {"matched_id", searchResults[0].id},
                        {"matched_name", searchResults[0].name},
                        {"score", searchResults[0].score},
                        {"confidence", searchResults[0].score > 5.0 ? "high" : "medium"}
                    });
                } else {
                    suggestions.push_back("未找到与\"" + name + "\"匹配的景点，已忽略该需求");
                    matchedPois.push_back({
                        {"query", name},
                        {"matched_id", nullptr},
                        {"matched_name", nullptr},
                        {"score", 0},
                        {"confidence", "none"}
                    });
                }
            }
            parsed.request.mustVisit = resolvedMustVisit;

            // Step 3: Plan itinerary
            nlohmann::json candidates = nlohmann::json::array();
            std::vector<Itinerary> itineraries = city->planner.planCandidates(parsed.request);
            for (const auto& it : itineraries) {
                candidates.push_back(itineraryToJson(it));
            }

            // Step 4: Generate natural language reply
            Itinerary bestItinerary = itineraries.empty() ? Itinerary{} : itineraries[0];
            std::string reply = context.llm.generateItineraryReply(message, parsed.request, bestItinerary);

            nlohmann::json result = {
                {"reply", reply},
                {"parsed_request", {
                    {"city", parsed.request.city},
                    {"days", parsed.request.days},
                    {"interests", parsed.request.interests},
                    {"must_visit", parsed.request.mustVisit},
                    {"avoid", parsed.request.avoid},
                    {"pace", parsed.request.pace}
                }},
                {"poi_matching", matchedPois},
                {"candidates", candidates},
                {"suggestions", suggestions}
            };
            if (!parsed.parseNote.empty()) {
                result["parse_note"] = parsed.parseNote;
            }

            setJson(res, result);
        } catch (const std::exception& ex) {
            std::cerr << "ERROR /trip/chat: " << ex.what() << std::endl;
            setJson(res, errorJson("INTERNAL_ERROR", "处理聊天请求失败", {{"reason", ex.what()}}), 500);
        }
    });

    // Helper to get auth user from request metadata
    auto getAuthUser = [&](const httplib::Request& req) -> std::pair<int64_t, std::string> {
        std::lock_guard<std::mutex> lock(metaMutex);
        auto found = requestMeta.find(&req);
        if (found != requestMeta.end()) return {found->second.userId, found->second.role};
        return {0, ""};
    };

    // ---- Auth routes ----

    server.Post("/auth/register", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string username = body.value("username", "");
            std::string password = body.value("password", "");
            if (username.size() < 2 || username.size() > 20) {
                setJson(res, errorJson("VALIDATION_ERROR", "用户名长度需 2-20 字符"), 400);
                return;
            }
            if (password.size() < 6 || password.size() > 50) {
                setJson(res, errorJson("VALIDATION_ERROR", "密码长度需 6-50 字符"), 400);
                return;
            }
            if (!context.store || !context.store->enabled()) {
                setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用"), 503);
                return;
            }
            std::string hashed = hashPassword(password);
            std::string role = isAdminValue(std::getenv("TOURPASS_ADMIN_USERS"), username) ? "admin" : "user";
            if (role == "user" && shouldAutoPromoteAdmin(context.store)) role = "admin";
            int64_t userId = context.store->createUser(username, hashed, role);
            std::string token = createToken(userId, username, role);
            setJson(res, {{"token", token}, {"user", {{"id", userId}, {"username", username}, {"role", role}}}}, 201);
        } catch (const std::exception& ex) {
            std::string msg = ex.what();
            if (msg.find("USERNAME_TAKEN") != std::string::npos) {
                setJson(res, errorJson("USERNAME_TAKEN", "用户名已被注册"), 409);
            } else {
                setJson(res, errorJson("INTERNAL_ERROR", "注册失败", {{"reason", msg}}), 500);
            }
        }
    });

    server.Post("/auth/login", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string username = body.value("username", "");
            std::string password = body.value("password", "");
            if (!context.store || !context.store->enabled()) {
                setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用"), 503);
                return;
            }
            auto user = context.store->findUserByUsername(username);
            if (!user || !verifyPassword(password, user->passwordHash)) {
                setJson(res, errorJson("INVALID_CREDENTIALS", "用户名或密码错误"), 401);
                return;
            }
            int queryUsed = context.store->getQueryCount(user->id);
            int bonus = context.store->getBonusQueries(user->id);
            std::string token = createToken(user->id, user->username, user->role);
            setJson(res, {
                {"token", token},
                {"user", {
                    {"id", user->id},
                    {"username", user->username},
                    {"role", user->role},
                    {"query_remaining", std::max(0, getQueryLimit(user->role) + bonus - queryUsed)}
                }}
            });
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "登录失败", {{"reason", ex.what()}}), 500);
        }
    });

    server.Get("/auth/me", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) {
            setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401);
            return;
        }
        if (!context.store || !context.store->enabled()) {
            setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用"), 503);
            return;
        }
        auto user = context.store->findUserById(userId);
        if (!user) {
            setJson(res, errorJson("NOT_FOUND", "用户不存在"), 404);
            return;
        }
        int queryUsed = context.store->getQueryCount(userId);
        int bonus = context.store->getBonusQueries(userId);
        setJson(res, {
            {"id", user->id},
            {"username", user->username},
            {"role", user->role},
            {"query_remaining", std::max(0, getQueryLimit(user->role) + bonus - queryUsed)},
            {"created_at", user->createdAt}
        });
    });

    // ---- Guest mode ----
    static IpRateLimiter guestIpLimiter(5, 86400);
    server.Post("/auth/guest", [&](const httplib::Request& req, httplib::Response& res) {
        if (!context.store || !context.store->enabled()) {
            setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用"), 503); return;
        }
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string deviceId = body.value("device_id", "");
            if (deviceId.empty() || deviceId.size() > 128) {
                setJson(res, errorJson("VALIDATION_ERROR", "请提供有效的设备标识"), 400); return;
            }
            // Check existing guest FIRST (skip rate limit for returning guests)
            auto existing = context.store->findUserByDeviceId(deviceId);
            if (existing) {
                std::string token = createToken(existing->id, existing->username, "guest");
                int queryUsed = context.store->getQueryCount(existing->id);
                int bonus = context.store->getBonusQueries(existing->id);
                setJson(res, {
                    {"token", token},
                    {"user", {{"id", existing->id}, {"username", existing->username}, {"role", "guest"},
                              {"query_remaining", std::max(0, getQueryLimit("guest") + bonus - queryUsed)}}}
                });
                return;
            }
            // Rate limit only for NEW guest creation
            if (!guestIpLimiter.allow(req.remote_addr)) {
                setJson(res, errorJson("RATE_LIMITED", "今日创建游客次数过多，请明天再试"), 429); return;
            }
            std::string username = "guest_" + randomHex(3);
            std::string hashed = hashPassword(randomHex(8));
            int64_t userId = context.store->createUser(username, hashed, "guest", "", deviceId);
            std::string token = createToken(userId, username, "guest");
            setJson(res, {
                {"token", token},
                {"user", {{"id", userId}, {"username", username}, {"role", "guest"}, {"query_remaining", 3}}}
            }, 201);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "游客登录失败", {{"reason", ex.what()}}), 500);
        }
    });

    // ---- Send verification code ----
    server.Post("/auth/send-code", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string email = body.value("email", "");
            if (email.empty() || email.find('@') == std::string::npos) {
                setJson(res, errorJson("VALIDATION_ERROR", "请输入有效的邮箱地址"), 400); return;
            }
            if (!context.store || !context.store->enabled()) {
                setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用"), 503); return;
            }
            std::string remoteAddr = req.get_header_value("REMOTE_ADDR");
            if (!emailLimiter.allow(email)) {
                setJson(res, errorJson("RATE_LIMITED", "验证码发送过于频繁，请 60 秒后重试"), 429); return;
            }
            (void)remoteAddr;
            if (context.store->findUserByEmail(email)) {
                setJson(res, errorJson("EMAIL_TAKEN", "该邮箱已注册"), 409); return;
            }
            std::string code = generateNumericCode(6);
            context.store->storeVerificationCode(email, code, "register", 300);
            if (sendVerificationEmail(email, code)) {
                setJson(res, {{"status", "sent"}, {"message", "验证码已发送到 " + email}});
            } else {
                setJson(res, errorJson("EMAIL_FAILED", "邮件发送失败，请稍后重试"), 500);
            }
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "发送验证码失败", {{"reason", ex.what()}}), 500);
        }
    });

    // ---- Register with email verification ----
    server.Post("/auth/register-email", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string email = body.value("email", "");
            std::string code = body.value("code", "");
            std::string password = body.value("password", "");
            if (email.empty() || code.empty() || password.empty()) {
                setJson(res, errorJson("VALIDATION_ERROR", "邮箱、验证码和密码不能为空"), 400); return;
            }
            if (password.size() < 6) {
                setJson(res, errorJson("VALIDATION_ERROR", "密码长度至少 6 字符"), 400); return;
            }
            if (!context.store || !context.store->enabled()) {
                setJson(res, errorJson("DB_UNAVAILABLE", "数据库未启用"), 503); return;
            }
            // Verify code
            auto codeId = context.store->getValidVerificationCode(email, code, "register");
            if (!codeId) {
                setJson(res, errorJson("INVALID_CODE", "验证码无效或已过期"), 400); return;
            }
            context.store->markCodeUsed(std::stoll(*codeId));
            // Check email not taken (race condition guard)
            if (context.store->findUserByEmail(email)) {
                setJson(res, errorJson("EMAIL_TAKEN", "该邮箱已注册"), 409); return;
            }
            // Generate username from email
            std::string username = email.substr(0, email.find('@'));
            // Ensure unique username
            if (context.store->findUserByUsername(username)) {
                username += "_" + randomHex(2);
            }
            std::string hashed = hashPassword(password);
            std::string role = isAdminValue(std::getenv("TOURPASS_ADMIN_USERS"), email) ? "admin" : "user";
            if (role == "user" && shouldAutoPromoteAdmin(context.store)) role = "admin";
            int64_t userId = context.store->createUser(username, hashed, role, email);
            std::string token = createToken(userId, username, role);
            setJson(res, {{"token", token}, {"user", {{"id", userId}, {"username", username}, {"email", email}, {"role", role}}}}, 201);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "注册失败", {{"reason", ex.what()}}), 500);
        }
    });

    // ---- Change password ----
    server.Patch("/auth/password", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string oldPassword = body.value("old_password", "");
            std::string newPassword = body.value("new_password", "");
            if (oldPassword.empty() || newPassword.empty()) {
                setJson(res, errorJson("VALIDATION_ERROR", "旧密码和新密码不能为空"), 400); return;
            }
            if (newPassword.size() < 6) {
                setJson(res, errorJson("VALIDATION_ERROR", "新密码长度至少 6 字符"), 400); return;
            }
            auto user = context.store->findUserById(userId);
            if (!user || !verifyPassword(oldPassword, user->passwordHash)) {
                setJson(res, errorJson("INVALID_CREDENTIALS", "旧密码错误"), 401); return;
            }
            context.store->updatePassword(userId, hashPassword(newPassword));
            setJson(res, {{"status", "updated"}, {"message", "密码修改成功"}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "修改密码失败", {{"reason", ex.what()}}), 500);
        }
    });

    // ---- Saved trips ----

    server.Post("/trips/save", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string title = body.value("title", "未命名行程");
            std::string requestJson = body.contains("request") ? body["request"].dump() : "{}";
            std::string responseJson = body.contains("response") ? body["response"].dump() : "{}";
            int64_t tripId = context.store->saveTrip(userId, title, requestJson, responseJson);
            setJson(res, {{"status", "saved"}, {"id", tripId}}, 201);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "保存失败", {{"reason", ex.what()}}), 500);
        }
    });

    server.Get("/trips/list", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        setJson(res, {{"data", context.store->listTrips(userId)}});
    });

    server.Get(R"(/trips/(\d+))", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        int64_t tripId = 0;
        try { tripId = std::stoll(req.matches[1]); } catch (...) {}
        auto trip = context.store->getTrip(tripId, userId);
        if (!trip) { setJson(res, errorJson("NOT_FOUND", "行程不存在"), 404); return; }
        setJson(res, *trip);
    });

    server.Post(R"(/trips/(\d+)/share)", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        int64_t tripId = 0;
        try { tripId = std::stoll(req.matches[1]); } catch (...) {}
        try {
            auto trip = context.store->getTrip(tripId, userId);
            if (!trip) { setJson(res, errorJson("NOT_FOUND", "行程不存在"), 404); return; }
            std::string shareId = context.store->generateShareId(tripId);
            setJson(res, {{"share_id", shareId}, {"share_url", "/s/" + shareId}});
        } catch (const std::exception& e) {
            setJson(res, errorJson("INTERNAL_ERROR", std::string("分享失败: ") + e.what()), 500);
        }
    });

    server.Get(R"(/s/([a-z0-9]+))", [&](const httplib::Request& req, httplib::Response& res) {
        std::string shareId = req.matches[1];
        auto trip = context.store->getTripByShareId(shareId);
        if (!trip) {
            // Return 404 HTML page
            res.status = 404;
            res.set_content("<!DOCTYPE html><html><head><meta charset='utf-8'><title>链接无效</title>"
                "<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f5f7f6;}"
                ".box{text-align:center;padding:40px;}.box h1{font-size:48px;margin:0;}.box p{color:#65706d;}"
                "a{color:#146b5d;text-decoration:none;font-weight:600;}</style></head>"
                "<body><div class='box'><h1>😕</h1><p>分享链接无效或已过期</p><p><a href='/'>返回首页</a></p></div></body></html>",
                "text/html; charset=utf-8");
            return;
        }
        // Serve share.html with trip data embedded
        std::ifstream file("web/share.html");
        if (!file.is_open()) {
            setJson(res, *trip);
            return;
        }
        std::string html((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        // Inject trip data as a script tag
        std::string script = "<script>window.__SHARE_DATA__=" + trip->dump() + ";</script></head>";
        auto pos = html.find("</head>");
        if (pos != std::string::npos) {
            html.replace(pos, 7, script);
        }
        res.set_content(html, "text/html; charset=utf-8");
    });

    // ---- Feedback ----

    server.Post("/feedback", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string content = body.value("content", "");
            if (content.empty() || content.size() > 2000) {
                setJson(res, errorJson("VALIDATION_ERROR", "反馈内容长度需 1-2000 字符"), 400); return;
            }
            context.store->submitFeedback(userId,
                body.value("category", "other"),
                content,
                body.value("contact", ""),
                body.value("page_url", ""),
                req.get_header_value("User-Agent"));
            setJson(res, {{"status", "submitted"}}, 201);
        } catch (const std::exception& ex) {
            setJson(res, errorJson("VALIDATION_ERROR", "提交反馈失败", {{"reason", ex.what()}}), 400);
        }
    });

    // ---- Easter egg ----

    server.Get("/easter-egg", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        if (context.store->hasEasterEggToday(userId)) {
            setJson(res, errorJson("ALREADY_CLAIMED", "今日彩蛋已领取，明天再来~"), 400);
            return;
        }
        context.store->recordEasterEgg(userId);
        context.store->addBonusQueries(userId, 5);
        auto user = context.store->findUserById(userId);
        std::string username = user ? user->username : "旅行者";
        setJson(res, {{"status", "claimed"}, {"message", username + " 祝小 fi 天天开心！"}, {"bonus", 5}});
    });

    // ---- Admin routes ----

    server.Get("/admin/stats", [&](const httplib::Request&, httplib::Response& res) {
        setJson(res, context.store->adminStats());
    });

    server.Get("/admin/users", [&](const httplib::Request& req, httplib::Response& res) {
        int limit = 50;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) {}
        }
        setJson(res, {{"data", context.store->listUsers(limit)}});
    });

    server.Get("/admin/feedback", [&](const httplib::Request& req, httplib::Response& res) {
        std::string status = req.has_param("status") ? req.get_param_value("status") : "";
        int limit = 50;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) {}
        }
        setJson(res, {{"data", context.store->listFeedback(status, limit)}});
    });

    server.Patch(R"(/admin/feedback/(\d+))", [&](const httplib::Request& req, httplib::Response& res) {
        int64_t feedbackId = 0;
        try { feedbackId = std::stoll(req.matches[1]); } catch (...) {}
        try {
            auto body = nlohmann::json::parse(req.body);
            context.store->updateFeedbackStatus(feedbackId, body.value("status", "reviewed"), body.value("admin_reply", ""));
            setJson(res, {{"status", "updated"}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "更新失败", {{"reason", ex.what()}}), 500);
        }
    });

    server.Get("/admin/query-stats", [&](const httplib::Request& req, httplib::Response& res) {
        int days = 30;
        if (req.has_param("days")) {
            try { days = std::stoi(req.get_param_value("days")); } catch (...) {}
        }
        setJson(res, {{"data", context.store->queryStatsByDay(days)}});
    });

    server.Patch(R"(/admin/users/(\d+)/role)", [&](const httplib::Request& req, httplib::Response& res) {
        int64_t targetUserId = 0;
        try { targetUserId = std::stoll(req.matches[1]); } catch (...) {}
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string newRole = body.value("role", "");
            if (newRole != "user" && newRole != "admin" && newRole != "guest") {
                setJson(res, errorJson("VALIDATION_ERROR", "角色只能是 user/admin/guest"), 400); return;
            }
            context.store->updateRole(targetUserId, newRole);
            setJson(res, {{"status", "updated"}, {"user_id", targetUserId}, {"role", newRole}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "更新角色失败", {{"reason", ex.what()}}), 500);
        }
    });

    // ---- Track query usage after successful trip/plan and trip/chat ----
    // (We add a post-routing handler specifically for these)
    // Note: This is handled by incrementing in the existing post-routing handler

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
