#include "tourpass/api.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <filesystem>
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
#include "tourpass/data_loader.h"

// ---- Email sending via Resend API ----
namespace {

// HTML-escape a string to prevent XSS in email templates
std::string htmlEscape(const std::string& input) {
    std::string out;
    out.reserve(input.size());
    for (char c : input) {
        switch (c) {
            case '&': out += "&amp;"; break;
            case '<': out += "&lt;"; break;
            case '>': out += "&gt;"; break;
            case '"': out += "&quot;"; break;
            case '\'': out += "&#39;"; break;
            default: out += c;
        }
    }
    return out;
}

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
    nlohmann::json bodyJson = {
        {"from", std::string(fromEmail)},
        {"to", toEmail},
        {"subject", "Tour Pass - 验证码"},
        {"html", "<h2>Tour Pass 注册验证</h2><p>您的验证码是：<strong>" + htmlEscape(code) + "</strong></p><p>5 分钟内有效。</p>"}
    };
    std::string body = bodyJson.dump();
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

        if (!defaultCity.empty()) {
            auto def = cities.find(defaultCity);
            if (def != cities.end()) return def->second;
        }

        if (!cities.empty()) {
            return cities.begin()->second;
        }

        return nullptr;
    }

    // Exact city lookup without fallback — returns nullptr if city not found
    CityBundle* findCityExact(const std::string& city) const {
        auto it = cities.find(city);
        return (it != cities.end()) ? it->second : nullptr;
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
    static constexpr size_t maxTotalIps = 50000;
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
        // Evict idle entries, then force-evict oldest if still over limit
        if (hits.size() > maxTotalIps / 2) {
            for (auto it = hits.begin(); it != hits.end();) {
                auto& dq = it->second;
                while (!dq.empty() && now - dq.front() > window) dq.pop_front();
                if (dq.empty()) it = hits.erase(it);
                else ++it;
            }
        }
        if (hits.size() > maxTotalIps) {
            // Force-evict oldest 10% entries by last activity
            size_t toEvict = maxTotalIps / 10;
            for (auto it = hits.begin(); it != hits.end() && toEvict > 0;) {
                if (it->first != ip) { it = hits.erase(it); --toEvict; }
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

struct VerificationAttemptLimiter {
    static constexpr int maxAttempts = 5;
    std::mutex mu;
    std::unordered_map<std::string, int> failedAttempts;  // email -> count
    bool recordFailure(const std::string& email) {
        std::lock_guard<std::mutex> lock(mu);
        return ++failedAttempts[email] >= maxAttempts;
    }
    void reset(const std::string& email) {
        std::lock_guard<std::mutex> lock(mu);
        failedAttempts.erase(email);
    }
    bool isLocked(const std::string& email) {
        std::lock_guard<std::mutex> lock(mu);
        auto it = failedAttempts.find(email);
        return it != failedAttempts.end() && it->second >= maxAttempts;
    }
};

void setJson(httplib::Response& res, const nlohmann::json& body, int status = 200) {
    res.status = status;
    res.set_content(body.dump(2), "application/json; charset=utf-8");
}

std::string trimCopy(const std::string& value) {
    const auto start = value.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    const auto end = value.find_last_not_of(" \t\r\n");
    return value.substr(start, end - start + 1);
}

std::vector<std::string> allowedCorsOrigins() {
    static const std::vector<std::string> origins = [] {
        const char* env = std::getenv("TOURPASS_ALLOWED_ORIGINS");
        if (!env || !*env) env = std::getenv("TOURPASS_CORS_ORIGIN");
        std::vector<std::string> values;
        if (!env || !*env) return values;
        std::istringstream input(env);
        std::string item;
        while (std::getline(input, item, ',')) {
            item = trimCopy(item);
            if (!item.empty()) values.push_back(item);
        }
        return values;
    }();
    return origins;
}

std::string allowedCorsOrigin(const httplib::Request& req) {
    const std::string origin = req.get_header_value("Origin");
    if (origin.empty()) return "";
    const auto origins = allowedCorsOrigins();
    if (origins.empty()) return "";
    if (std::find(origins.begin(), origins.end(), "*") != origins.end()) return "*";
    return std::find(origins.begin(), origins.end(), origin) != origins.end() ? origin : "";
}

bool isSafeCspSource(const std::string& source) {
    if (source.empty()) return false;
    for (unsigned char c : source) {
        if (std::isalnum(c) || c == ':' || c == '/' || c == '.' || c == '-' || c == '_') continue;
        return false;
    }
    return true;
}

std::string configuredAssetOrigin() {
    const char* env = std::getenv("ASSET_BASE_URL");
    if (!env || !*env) env = std::getenv("TOURPASS_ASSET_BASE_URL");
    if (!env || !*env) return "";

    std::string base = trimCopy(env);
    while (!base.empty() && base.back() == '/') {
        base.pop_back();
    }

    const bool isHttp = base.rfind("http://", 0) == 0;
    const bool isHttps = base.rfind("https://", 0) == 0;
    if (!isHttp && !isHttps) return "";

    const size_t schemeEnd = base.find("://");
    const size_t originEnd = base.find_first_of("/?#", schemeEnd + 3);
    std::string origin = originEnd == std::string::npos ? base : base.substr(0, originEnd);
    return isSafeCspSource(origin) ? origin : "";
}

void setCommonHeaders(const httplib::Request& req, httplib::Response& res, const std::string& requestId) {
    res.set_header("X-Request-Id", requestId);
    std::string origin = allowedCorsOrigin(req);
    if (!origin.empty()) {
        res.set_header("Access-Control-Allow-Origin", origin);
        res.set_header("Vary", "Origin");
    }
    res.set_header("Access-Control-Allow-Headers", "Content-Type, X-Request-Id, Authorization");
    res.set_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS");
    res.set_header("Access-Control-Expose-Headers", "X-Request-Id, X-Response-Time-Ms, X-Cache, X-Query-Remaining");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_header("Referrer-Policy", "no-referrer");
    res.set_header("X-Frame-Options", req.path.find("/editor") == 0 ? "SAMEORIGIN" : "DENY");
    // CSP is set in post_routing_handler so individual routes can override it
}

std::string queryString(const httplib::Request& req) {
    auto pos = req.target.find('?');
    if (pos == std::string::npos) return "";
    return req.target.substr(pos + 1);
}

std::string upstreamPathWithQuery(const httplib::Request& req) {
    const std::string qs = queryString(req);
    if (qs.empty()) return req.path;
    return req.path + "?" + qs;
}

bool isAllowedImageRequestPath(const std::string& path) {
    if (path.empty() || path.front() == '/' || path.find("..") != std::string::npos || path.find('\\') != std::string::npos) {
        return false;
    }
    std::string lowered = path;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    const std::vector<std::string> extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"};
    bool hasImageExtension = false;
    for (const auto& ext : extensions) {
        if (lowered.size() >= ext.size() && lowered.compare(lowered.size() - ext.size(), ext.size(), ext) == 0) {
            hasImageExtension = true;
            break;
        }
    }
    return hasImageExtension && (lowered.find("/images/") != std::string::npos || lowered.find("images/") == 0);
}

void serveWhitelistedImage(const httplib::Request& req, httplib::Response& res) {
    const std::string relative = req.matches.size() > 1 ? req.matches[1].str() : "";
    if (!isAllowedImageRequestPath(relative)) {
        setJson(res, errorJson("NOT_FOUND", "图片不存在"), 404);
        return;
    }

    std::filesystem::path root = std::filesystem::weakly_canonical("data");
    std::filesystem::path file = std::filesystem::weakly_canonical(root / std::filesystem::path(relative));
    const std::string rootString = root.string();
    const std::string fileString = file.string();
    if (fileString.compare(0, rootString.size(), rootString) != 0 || !std::filesystem::is_regular_file(file)) {
        setJson(res, errorJson("NOT_FOUND", "图片不存在"), 404);
        return;
    }

    res.set_file_content(fileString);
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
    auto* city = context.findCityExact(tripRequest.city);
    if (!city) return errorJson("CITY_NOT_FOUND", "未找到城市数据: " + tripRequest.city);
    try {
        if (tripRequest.candidateCount > 1) {
            nlohmann::json candidates = nlohmann::json::array();
            for (const auto& itinerary : city->planner.planCandidates(tripRequest)) {
                candidates.push_back(itineraryToJson(itinerary));
            }
            return {{"city", tripRequest.city}, {"candidates", candidates}};
        }
        return itineraryToJson(city->planner.plan(tripRequest));
    } catch (const std::runtime_error& ex) {
        std::string msg = ex.what();
        if (msg.find("\xe9\x85\x92\xe5\xba\x97") != std::string::npos) {  // contains "酒店"
            return errorJson("NO_HOTEL", msg);
        }
        throw;  // re-throw other errors
    }
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
static VerificationAttemptLimiter verifyAttemptLimiter;

void installMiddleware(httplib::Server& server, ApiContext& context) {
    static IpRateLimiter rateLimiter(60, 60);
    server.set_payload_max_length(context.config.maxBodyBytes);
    server.set_pre_routing_handler([&](const httplib::Request& req, httplib::Response& res) {
        std::string requestId = req.get_header_value("X-Request-Id");

        if (requestId.empty()) requestId = makeRequestId();
        context.metrics.beginRequest();
        setCommonHeaders(req, res, requestId);
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
                         || req.path.find("/api/share/") == 0
                         || req.method == "OPTIONS"
                         || req.path == "/" || req.path == "/index.html"
                         || req.path == "/app.js" || req.path == "/styles.css"
                         || req.path.find("/css/") == 0
                         || req.path == "/favicon.ico"
                         || req.path == "/admin.html"  // static page; /admin/* API endpoints require admin role
                         || req.path == "/admin.js"
                         || req.path == "/profile.html"
                         || req.path == "/profile.js"
                         || req.path == "/share.html"
                         || req.path == "/share-render.js"
                         || req.path.find("/vendor/") == 0
                         || req.path.find("/assets/") == 0
                         || req.path.find("/images/") == 0
                         || req.path.find("/city/") == 0
                         || req.path == "/cities"
                         || req.path == "/poi/browse"
                         || req.path == "/poi/search"
                         || req.path == "/poi/areas"
                         || req.path.find("/poi/by-area") == 0
                         || req.path == "/api/travel-time"
                         || req.path == "/api/city-guide"
                         || req.path == "/api/cities"
                         || req.path == "/api/optimize-route"
                         || req.path == "/api/xhs/parse"
                         || req.path == "/api/xhs/proxy"
                         || req.path == "/agent/ping"
                         || req.path == "/agent/health"
                         || req.path == "/agent/stats"
                         || req.path == "/agent/hot"
                         || req.path.find("/agent/hot/") == 0
                         || req.path == "/agent/plan"
                         || req.path == "/agent/plan-structured"
                         || req.path == "/agent/plan-sync"
                         || req.path == "/agent/plan-multi"
                         || req.path == "/agent/chat"
                         || req.path.find("/editor") == 0
                         || req.path.find("/editor-dist/") == 0;

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

        if (req.path == "/agent/rag/ingest" && authRole != "admin") {
            context.metrics.recordRejectedRequest();
            setJson(res, errorJson("FORBIDDEN", "需要管理员权限"), 403);
            return httplib::Server::HandlerResponse::Handled;
        }

        // Query rate limit for /trip/plan and /trip/chat
        bool isQueryPath = req.path == "/trip/plan" || req.path == "/trip/chat";
        // API key rate limit (separate from per-user limits)
        if (isQueryPath && authUserId == -1) {
            static IpRateLimiter apiKeyLimiter(1000, 86400);  // 1000 queries/day for API key
            if (!apiKeyLimiter.allow("apikey")) {
                context.metrics.recordRejectedRequest();
                setJson(res, errorJson("DAILY_LIMIT_EXCEEDED", "API Key 今日查询次数已用完", {{"remaining", 0}}), 429);
                return httplib::Server::HandlerResponse::Handled;
            }
        }
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
        // Set default CSP if the route handler didn't set a custom one
        if (!res.has_header("Content-Security-Policy")) {
            res.set_header("Content-Security-Policy", contentSecurityPolicy());
        }
        // Force no-cache for editor SPA to prevent stale HTML
        if (req.path.find("/editor") == 0) {
            res.set_header("Cache-Control", "no-cache, no-store, must-revalidate");
            res.set_header("Pragma", "no-cache");
            res.set_header("Expires", "0");
        }
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
        setCommonHeaders(req, res, meta.id);
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

std::string contentSecurityPolicy(const std::string& scriptSrc, const std::string& connectSrc) {
    std::string imageSources = "'self' https://*.tile.openstreetmap.org https://*.is.autonavi.com https://webapi.amap.com data:";
    const std::string assetOrigin = configuredAssetOrigin();
    if (!assetOrigin.empty()) {
        imageSources += " " + assetOrigin;
    }

    return "default-src 'self'; script-src " + scriptSrc
        + "; style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; img-src " + imageSources
        + "; connect-src " + connectSrc;
}

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
    server.set_mount_point("/editor", "web/editor-dist");
    server.set_mount_point("/", "web");
    server.Get(R"(/images/(.+))", serveWhitelistedImage);
    // ── Agent service reverse proxy (WinHTTP streaming) ─────────────────
    {
        // Read agent port from environment (default 8090)
        int agentPort = 8090;
        if (const char* envAgentPort = std::getenv("AGENT_PORT")) {
            try {
                int p = std::stoi(envAgentPort);
                if (p > 0 && p <= 65535) agentPort = p;
            } catch (...) {}
        }

        // State holder for streaming WinHTTP proxy (RAII closes handles)
#ifdef _WIN32
        struct WinHttpStreamState {
            HINTERNET hRequest, hConnect, hSession;
            bool done;
            WinHttpStreamState(HINTERNET r, HINTERNET c, HINTERNET s)
                : hRequest(r), hConnect(c), hSession(s), done(false) {}
            ~WinHttpStreamState() {
                if (hRequest) WinHttpCloseHandle(hRequest);
                if (hConnect) WinHttpCloseHandle(hConnect);
                if (hSession) WinHttpCloseHandle(hSession);
            }
        };
#endif // _WIN32

        // Shared proxy handler for all /agent/* endpoints.
        // For SSE (text/event-stream) responses, uses chunked content provider
        // to stream data from upstream without buffering.
        // For non-SSE responses, buffers the entire response.
        auto agentProxyHandler = [agentPort](const httplib::Request& req, httplib::Response& res) {
#ifdef _WIN32
            HINTERNET hSession = WinHttpOpen(L"TourPass-Agent/1.0",
                WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
            if (!hSession) {
                res.status = 502;
                res.set_content("{\"error\":\"Agent proxy init failed\"}", "application/json");
                return;
            }

            HINTERNET hConnect = WinHttpConnect(hSession, L"127.0.0.1", agentPort, 0);
            if (!hConnect) {
                WinHttpCloseHandle(hSession);
                res.status = 502;
                res.set_content("{\"error\":\"Agent service unreachable\"}", "application/json");
                return;
            }

            const std::string upstreamPath = upstreamPathWithQuery(req);
            std::wstring wpath(upstreamPath.begin(), upstreamPath.end());
            LPCWSTR verb = (req.method == "POST") ? L"POST" : L"GET";

            HINTERNET hRequest = WinHttpOpenRequest(hConnect, verb, wpath.c_str(),
                nullptr, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
            if (!hRequest) {
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                res.status = 502;
                res.set_content("{\"error\":\"Agent request creation failed\"}", "application/json");
                return;
            }

            WinHttpSetTimeouts(hRequest, 5000, 5000, 5000, 120000);

            // Build headers: forward query string already handled by wpath
            std::wstring whdrs = L"Content-Type: application/json\r\n";
            BOOL sendResult;
            if (req.method == "POST" && !req.body.empty()) {
                sendResult = WinHttpSendRequest(hRequest, whdrs.c_str(), (DWORD)-1,
                    (LPVOID)req.body.data(), (DWORD)req.body.size(), (DWORD)req.body.size(), 0);
            } else {
                sendResult = WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                    nullptr, 0, 0, 0);
            }

            if (!sendResult || !WinHttpReceiveResponse(hRequest, nullptr)) {
                WinHttpCloseHandle(hRequest);
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                res.status = 502;
                res.set_content("{\"error\":\"Agent service unavailable\"}", "application/json");
                return;
            }

            // Read upstream status code
            DWORD statusCode = 0;
            DWORD scSize = sizeof(statusCode);
            WinHttpQueryHeaders(hRequest,
                WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                WINHTTP_HEADER_NAME_BY_INDEX, &statusCode, &scSize, WINHTTP_NO_HEADER_INDEX);
            res.status = (int)statusCode;

            // Read upstream Content-Type
            DWORD ctSize = 0;
            WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_CONTENT_TYPE,
                WINHTTP_HEADER_NAME_BY_INDEX, WINHTTP_NO_OUTPUT_BUFFER, &ctSize, WINHTTP_NO_HEADER_INDEX);
            std::wstring wct(ctSize / sizeof(wchar_t), L'\0');
            if (ctSize > 0) {
                WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_CONTENT_TYPE,
                    WINHTTP_HEADER_NAME_BY_INDEX, &wct[0], &ctSize, WINHTTP_NO_HEADER_INDEX);
            }
            std::string upstreamCT;
            for (wchar_t wc : wct) { if (wc != L'\0') upstreamCT += static_cast<char>(wc); }
            if (upstreamCT.empty()) upstreamCT = "application/json";

            bool isSSE = (upstreamCT.find("event-stream") != std::string::npos);

            if (isSSE) {
                // Streaming: use chunked content provider with WinHTTP reads
                auto state = std::make_shared<WinHttpStreamState>(hRequest, hConnect, hSession);

                res.set_chunked_content_provider("text/event-stream",
                    [state](size_t /*offset*/, httplib::DataSink& sink) -> bool {
                        if (state->done) return false;
                        char buf[4096];
                        DWORD bytesRead = 0;
                        if (!WinHttpReadData(state->hRequest, buf, sizeof(buf), &bytesRead)) {
                            state->done = true;
                            sink.done();
                            return false;
                        }
                        if (bytesRead == 0) {
                            state->done = true;
                            sink.done();
                            return false;
                        }
                        return sink.write(buf, static_cast<size_t>(bytesRead));
                    },
                    [state](bool /*success*/) { /* handles closed by destructor */ }
                );
            } else {
                // Non-SSE: buffer entire response
                std::string body;
                char buf[4096];
                DWORD bytesRead = 0;
                do {
                    bytesRead = 0;
                    if (WinHttpReadData(hRequest, buf, sizeof(buf), &bytesRead) && bytesRead > 0) {
                        body.append(buf, bytesRead);
                    } else { break; }
                } while (bytesRead > 0);
                res.set_content(body, upstreamCT);
                WinHttpCloseHandle(hRequest);
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
            }

            res.set_header("Cache-Control", "no-cache, no-store");
            res.set_header("X-Accel-Buffering", "no");
#else
            httplib::Client client("127.0.0.1", agentPort);
            client.set_connection_timeout(5);
            client.set_read_timeout(180);
            client.set_write_timeout(30);

            httplib::Headers headers;
            if (req.has_header("Accept")) {
                headers.emplace("Accept", req.get_header_value("Accept"));
            }
            if (req.has_header("Authorization")) {
                headers.emplace("Authorization", req.get_header_value("Authorization"));
            }
            if (req.has_header("X-Request-Id")) {
                headers.emplace("X-Request-Id", req.get_header_value("X-Request-Id"));
            }

            const std::string upstreamPath = upstreamPathWithQuery(req);
            const std::string contentType = req.has_header("Content-Type")
                ? req.get_header_value("Content-Type")
                : "application/json";

            httplib::Result upstream;
            if (req.method == "POST") {
                upstream = client.Post(upstreamPath, headers, req.body, contentType);
            } else {
                upstream = client.Get(upstreamPath, headers);
            }

            if (!upstream) {
                std::cerr << "AGENT_PROXY_ERROR path=" << upstreamPath
                          << " port=" << agentPort
                          << " reason=" << httplib::to_string(upstream.error())
                          << std::endl;
                res.status = 502;
                setJson(res, errorJson(
                    "AGENT_PROXY_ERROR",
                    "Agent service unavailable",
                    {{"reason", httplib::to_string(upstream.error())}}
                ), 502);
                return;
            }

            res.status = upstream->status;
            std::string upstreamCT = upstream->get_header_value("Content-Type");
            if (upstreamCT.empty()) upstreamCT = "application/json";
            res.set_content(upstream->body, upstreamCT);
            res.set_header("Cache-Control", "no-cache, no-store");
            res.set_header("X-Accel-Buffering", "no");
#endif
        };

        server.Get("/agent/ping", agentProxyHandler);
        server.Get("/agent/health", agentProxyHandler);
        server.Get("/agent/stats", agentProxyHandler);
        server.Get("/agent/hot", agentProxyHandler);
        server.Post("/agent/plan", agentProxyHandler);
        server.Post("/agent/plan-structured", agentProxyHandler);
        server.Post("/agent/plan-sync", agentProxyHandler);
        server.Post("/agent/plan-multi", agentProxyHandler);
        server.Post("/agent/chat", agentProxyHandler);
        server.Post("/agent/modify", agentProxyHandler);
        server.Post("/agent/rag/ingest", agentProxyHandler);
        server.Post("/api/xhs/parse", agentProxyHandler);
        server.Post("/api/xhs/analyze", agentProxyHandler);
        server.Get("/api/xhs/proxy", agentProxyHandler);
    }


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
            TripRequest tripRequest = tripRequestFromJson(body, context.defaultCity);
            if (!context.findCityExact(tripRequest.city)) {
                setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市数据: " + tripRequest.city), 404);
                return;
            }
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
            TripRequest tripRequest = tripRequestFromJson(body, context.defaultCity);
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
        limit = std::max(1, std::min(200, limit));
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

    // ── Agent API: Travel time lookup between two POIs ─────────────────────
    server.Get("/api/travel-time", [&](const httplib::Request& req, httplib::Response& res) {
        if (!req.has_param("from") || !req.has_param("to")) {
            setJson(res, errorJson("VALIDATION_ERROR", "from 和 to 参数必填"), 400);
            return;
        }
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        auto* city = context.getCity(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }

        std::string from = req.get_param_value("from");
        std::string to = req.get_param_value("to");

        RouteResult route = city->graph.shortestRoute(from, to);
        int travelMinutes = (route.travelMinutes == std::numeric_limits<int>::max()) ? -1 : route.travelMinutes;
        int distanceMeters = travelMinutes < 0 ? -1 : travelMinutes * 80;

        setJson(res, {
            {"from", from},
            {"to", to},
            {"travelMinutes", travelMinutes},
            {"distanceMeters", distanceMeters}  // rough estimate
        });
    });

    // ── Agent API: Beam Search route optimization ──────────────────────────
    server.Post("/api/optimize-route", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            TripRequest tripRequest = tripRequestFromJson(body, context.defaultCity);

            auto* city = context.getCity(tripRequest.city);
            if (!city) {
                setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + tripRequest.city), 404);
                return;
            }

            // Use the existing planner
            TripPlanner planner(city->graph);
            Itinerary itinerary = planner.plan(tripRequest);
            nlohmann::json result = itineraryToJson(itinerary);
            setJson(res, result);
        } catch (const std::exception& ex) {
            std::cerr << "VALIDATION /api/optimize-route: " << ex.what() << std::endl;
            setJson(res, errorJson("OPTIMIZATION_ERROR", ex.what()), 400);
        }
    });

    // ── Agent API: City guide ──────────────────────────────────────────────
    server.Get("/api/city-guide", [&](const httplib::Request& req, httplib::Response& res) {
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        std::string path = "data/" + cityName + "/city_guide.json";
        std::ifstream file(path);
        if (!file.is_open()) {
            setJson(res, errorJson("NOT_FOUND", "暂无该城市攻略", {{"city", cityName}}), 404);
            return;
        }
        std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        try {
            setJson(res, nlohmann::json::parse(content));
        } catch (...) {
            setJson(res, errorJson("PARSE_ERROR", "攻略数据格式错误"), 500);
        }
    });

    // ── Agent API: List available cities ────────────────────────────────────
    server.Get("/api/cities", [&](const httplib::Request& req, httplib::Response& res) {
        nlohmann::json data = nlohmann::json::array();
        for (const auto& [name, bundle] : context.cities) {
            int poiCount = 0, hotelCount = 0;
            for (const auto& poi : bundle->graph.pois()) {
                poiCount++;
                if (poi.type == PoiType::Hotel) hotelCount++;
            }
            data.push_back({
                {"name", name},
                {"poi_count", poiCount},
                {"hotel_count", hotelCount}
            });
        }
        setJson(res, {{"data", data}});
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

    // GET /poi/browse - browse POIs by type on the map
    server.Get("/poi/browse", [&](const httplib::Request& req, httplib::Response& res) {
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        std::string typeFilter = req.has_param("type") ? req.get_param_value("type") : "";
        auto* city = context.getCity(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }
        int limit = 50;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) { limit = 50; }
        }
        limit = std::max(1, std::min(500, limit));

        std::string key = requestCacheKey(req.method, req.path, queryString(req), "");
        if (serveFromCache(context, res, key)) return;

        // Collect POIs from graph, filter by type, sort by popularity
        struct PoiEntry { const Poi* poi; };
        std::vector<PoiEntry> entries;
        for (const auto& poi : city->graph.pois()) {
            // Skip Hotel/Transit by default, but allow when explicitly requested
            if (!typeFilter.empty()) {
                std::string pType = poiTypeToString(poi.type);
                if (pType != typeFilter) continue;
            } else {
                if (poi.type == PoiType::Hotel || poi.type == PoiType::Transit) continue;
            }
            entries.push_back({&poi});
        }
        std::sort(entries.begin(), entries.end(), [](const PoiEntry& a, const PoiEntry& b) {
            return a.poi->popularity > b.poi->popularity;
        });
        if (static_cast<int>(entries.size()) > limit) entries.resize(limit);

        nlohmann::json data = nlohmann::json::array();
        for (const auto& e : entries) {
            nlohmann::json item = {
                {"id", e.poi->id},
                {"name", e.poi->name},
                {"type", poiTypeToString(e.poi->type)},
                {"meal_type", e.poi->mealType},
                {"lat", e.poi->lat},
                {"lng", e.poi->lng},
                {"area", e.poi->area},
                {"popularity", e.poi->popularity},
                {"description", e.poi->description},
                {"recommendation", e.poi->recommendation},
                {"image_url", resolveAssetUrl(e.poi->imageUrl)},
                {"guide_text", e.poi->guideText}
            };
            // Serialize images array
            nlohmann::json imgs = nlohmann::json::array();
            for (const auto& img : e.poi->images) {
                imgs.push_back(poiImageToJson(img, true));
            }
            item["images"] = imgs;
            data.push_back(item);
        }
        nlohmann::json result = {{"data", data}, {"total", static_cast<int>(entries.size())}};
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
        }
        // Sort by popularity descending, then truncate to limit
        std::sort(data.begin(), data.end(), [](const nlohmann::json& a, const nlohmann::json& b) {
            return a["popularity"].get<double>() > b["popularity"].get<double>();
        });
        if (static_cast<int>(data.size()) > limit) {
            data.erase(data.begin() + limit, data.end());
        }

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
            int wlen = MultiByteToWideChar(CP_UTF8, 0, url.c_str(), -1, nullptr, 0);
            std::wstring wurl(wlen - 1, L'\0');
            MultiByteToWideChar(CP_UTF8, 0, url.c_str(), -1, &wurl[0], wlen);
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
            itinerary.city = body.value("city", context.defaultCity);
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
                TripRequest request = tripRequestFromJson(body, context.defaultCity);
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

            LlmParsedRequest parsed = context.llm.parseNaturalLanguageRequest(message, chatHistory, context.defaultCity);
            if (!parsed.parsed) {
                setJson(res, errorJson("PARSE_FAILED", "无法理解您的旅行需求", {{"detail", parsed.parseNote}}), 422);
                return;
            }

            // Resolve city: use parsed city if non-empty, otherwise defaultCity
            std::string resolvedCity = parsed.request.city.empty() ? context.defaultCity : parsed.request.city;
            parsed.request.city = resolvedCity;

            // Get city context (strict lookup — no silent fallback)
            auto* city = context.findCityExact(resolvedCity);
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

            // Step 4: Load city guide and evaluate candidates
            CityGuide cityGuide = LlmClient::loadCityGuide(resolvedCity);

            Itinerary bestItinerary;
            if (!itineraries.empty()) {
                int bestIdx = context.llm.evaluateItinerary(itineraries, cityGuide);
                if (bestIdx < 0) bestIdx = 0;
                if (bestIdx >= static_cast<int>(itineraries.size())) bestIdx = static_cast<int>(itineraries.size()) - 1;
                bestItinerary = itineraries[bestIdx];

                // Enrich stop reasons with expert tips
                auto enrichedReasons = context.llm.enrichStopReasons(bestItinerary, cityGuide);
                int reasonIdx = 0;
                for (auto& day : bestItinerary.days) {
                    for (auto& stop : day.stops) {
                        if (reasonIdx < static_cast<int>(enrichedReasons.size())) {
                            stop.reason = enrichedReasons[reasonIdx++];
                        }
                    }
                }
            }

            // Step 5: Generate natural language reply
            std::string reply = context.llm.generateItineraryReply(message, parsed.request, bestItinerary, cityGuide);

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

            if (!emailLimiter.allow(email)) {
                setJson(res, errorJson("RATE_LIMITED", "验证码发送过于频繁，请 60 秒后重试"), 429); return;
            }

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
            if (verifyAttemptLimiter.isLocked(email)) {
                setJson(res, errorJson("TOO_MANY_ATTEMPTS", "验证码尝试次数过多，请重新获取"), 429); return;
            }
            auto codeId = context.store->getValidVerificationCode(email, code, "register");
            if (!codeId) {
                verifyAttemptLimiter.recordFailure(email);
                setJson(res, errorJson("INVALID_CODE", "验证码无效或已过期"), 400); return;
            }
            verifyAttemptLimiter.reset(email);
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

    server.Put(R"(/trips/(\d+))", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        int64_t tripId = 0;
        try { tripId = std::stoll(req.matches[1]); } catch (...) {}
        if (tripId <= 0) { setJson(res, errorJson("INVALID_REQUEST", "无效的行程ID"), 400); return; }
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string title = body.value("title", "");
            std::string reqJson = body.contains("request") ? body["request"].dump() : "";
            std::string respJson = body.contains("response") ? body["response"].dump() : "";
            if (!context.store->updateTrip(tripId, userId, title, reqJson, respJson)) {
                setJson(res, errorJson("NOT_FOUND", "行程不存在或无权修改"), 404); return;
            }
            setJson(res, {{"status", "updated"}, {"id", tripId}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", "更新失败", {{"reason", ex.what()}}), 500);
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

    server.Delete(R"(/trips/(\d+))", [&](const httplib::Request& req, httplib::Response& res) {
        auto [userId, role] = getAuthUser(req);
        if (userId <= 0) { setJson(res, errorJson("UNAUTHORIZED", "请先登录"), 401); return; }
        int64_t tripId = 0;
        try { tripId = std::stoll(req.matches[1]); } catch (...) {}
        if (tripId <= 0) { setJson(res, errorJson("INVALID_REQUEST", "无效的行程ID"), 400); return; }
        if (!context.store->deleteTrip(tripId, userId)) {
            setJson(res, errorJson("NOT_FOUND", "行程不存在或无权删除"), 404);
            return;
        }
        setJson(res, {{"status", "deleted"}, {"id", tripId}});
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


    // JSON API for share data (used by main app hash routing)
    server.Get(R"(/api/share/([a-z0-9]+))", [&](const httplib::Request& req, httplib::Response& res) {
        std::string shareId = req.matches[1];
        auto trip = context.store->getTripByShareId(shareId);
        if (!trip) {
            setJson(res, errorJson("NOT_FOUND", "分享链接无效或已过期"), 404);
            return;
        }
        setJson(res, *trip);
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
        // Use JSON.parse to prevent XSS: data in a non-executing script tag
        std::string escaped = trip->dump();
        // Escape </ sequences in JSON to prevent script tag breakout
        size_t pos2 = 0;
        while ((pos2 = escaped.find("</", pos2)) != std::string::npos) {
            escaped.replace(pos2, 2, "<\\/");
            pos2 += 3;  // skip past the replaced <\/ (3 chars)
        }
        // Generate a CSP nonce so the browser allows these specific inline scripts
        std::string nonce = randomHex(16);
        std::string script = "<script type=\"application/json\" id=\"share-data\">" + escaped + "</script>"
            "<script nonce=\"" + nonce + "\">window.__SHARE_DATA__=JSON.parse(document.getElementById('share-data').textContent);</script></head>";
        auto pos = html.find("</head>");
        if (pos != std::string::npos) {
            html.replace(pos, 7, script);
        }
        // Override CSP for this response to allow the nonce'd inline script
        res.set_header("Content-Security-Policy",
            contentSecurityPolicy("'self' 'nonce-" + nonce + "'", "'self' https://*.tile.openstreetmap.org https://*.is.autonavi.com"));
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
        limit = std::max(1, std::min(500, limit));
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

    // ---- Admin POI Management ----
    // GET /admin/pois - list POIs for a city with pagination
    server.Get("/admin/pois", [&](const httplib::Request& req, httplib::Response& res) {
        std::string cityName = req.has_param("city") ? req.get_param_value("city") : context.defaultCity;
        auto* city = context.findCityExact(cityName);
        if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市: " + cityName), 404); return; }

        std::string typeFilter = req.has_param("type") ? req.get_param_value("type") : "";
        std::string q = req.has_param("q") ? req.get_param_value("q") : "";
        int page = 1;
        int pageSize = 50;
        if (req.has_param("page")) { try { page = std::stoi(req.get_param_value("page")); } catch (...) {} }
        if (req.has_param("page_size")) { try { pageSize = std::stoi(req.get_param_value("page_size")); } catch (...) {} }
        page = std::max(1, page);
        pageSize = std::max(1, std::min(200, pageSize));

        // Collect filtered POIs
        std::vector<const Poi*> filtered;
        for (const auto& poi : city->graph.pois()) {
            if (!typeFilter.empty() && poiTypeToString(poi.type) != typeFilter) continue;
            if (!q.empty()) {
                std::string lower = poi.name;
                std::string lowerQ = q;
                for (auto& c : lower) c = std::tolower(c);
                for (auto& c : lowerQ) c = std::tolower(c);
                if (lower.find(lowerQ) == std::string::npos &&
                    poi.id.find(q) == std::string::npos) continue;
            }
            filtered.push_back(&poi);
        }

        int total = static_cast<int>(filtered.size());
        int start = (page - 1) * pageSize;
        nlohmann::json data = nlohmann::json::array();
        for (int i = start; i < std::min(start + pageSize, total); ++i) {
            data.push_back(poiToJson(*filtered[i]));
        }
        setJson(res, {{"data", data}, {"total", total}, {"page", page}, {"page_size", pageSize}});
    });

    // GET /admin/pois/:id - get single POI detail
    server.Get(R"(/admin/pois/([^/]+))", [&](const httplib::Request& req, httplib::Response& res) {
        std::string poiId = req.matches[1];
        // Search across all cities
        for (auto& [name, city] : context.cities) {
            const auto* poi = city->graph.findPoi(poiId);
            if (poi) {
                nlohmann::json result = poiToJson(*poi);
                result["_city"] = name;
                setJson(res, result);
                return;
            }
        }
        setJson(res, errorJson("NOT_FOUND", "未找到 POI: " + poiId), 404);
    });

    // PUT /admin/pois/:id - update POI fields
    server.Put(R"(/admin/pois/([^/]+))", [&](const httplib::Request& req, httplib::Response& res) {
        std::string poiId = req.matches[1];
        nlohmann::json body;
        try { body = nlohmann::json::parse(req.body); } catch (...) {
            setJson(res, errorJson("VALIDATION_ERROR", "无效的 JSON"), 400); return;
        }

        std::string cityName = body.value("_city", "");
        CityBundle* city = nullptr;
        if (!cityName.empty()) {
            city = context.findCityExact(cityName);
        } else {
            // Search all cities
            for (auto& [name, c] : context.cities) {
                if (c->graph.findPoi(poiId)) { city = c; cityName = name; break; }
            }
        }
        if (!city) { setJson(res, errorJson("NOT_FOUND", "未找到 POI: " + poiId), 404); return; }

        Poi* poi = city->graph.findMutablePoi(poiId);
        if (!poi) { setJson(res, errorJson("NOT_FOUND", "未找到 POI: " + poiId), 404); return; }

        // Update fields
        if (body.contains("name")) poi->name = body["name"].get<std::string>();
        if (body.contains("type")) poi->type = poiTypeFromString(body["type"].get<std::string>());
        if (body.contains("lat")) poi->lat = body["lat"].get<double>();
        if (body.contains("lng")) poi->lng = body["lng"].get<double>();
        if (body.contains("area")) poi->area = body["area"].get<std::string>();
        if (body.contains("description")) poi->description = body["description"].get<std::string>();
        if (body.contains("recommendation")) poi->recommendation = body["recommendation"].get<std::string>();
        if (body.contains("guide_text")) poi->guideText = body["guide_text"].get<std::string>();
        if (body.contains("meal_type")) poi->mealType = body["meal_type"].get<std::string>();
        if (body.contains("popularity")) poi->popularity = body["popularity"].get<double>();
        if (body.contains("price_level")) poi->priceLevel = body["price_level"].get<int>();
        if (body.contains("visit_duration_minutes")) poi->visitDurationMinutes = body["visit_duration_minutes"].get<int>();
        if (body.contains("tags") && body["tags"].is_array()) {
            poi->tags.clear();
            for (const auto& tag : body["tags"]) poi->tags.push_back(tag.get<std::string>());
        }
        if (body.contains("open_time")) poi->openMinutes = parseTimeToMinutes(body["open_time"].get<std::string>());
        if (body.contains("close_time")) poi->closeMinutes = parseTimeToMinutes(body["close_time"].get<std::string>());
        if (body.contains("image_url")) poi->imageUrl = body["image_url"].get<std::string>();
        if (body.contains("images") && body["images"].is_array()) {
            poi->images.clear();
            for (const auto& img : body["images"]) {
                PoiImage pi;
                pi.url = img.value("url", "");
                pi.source = img.value("source", "");
                pi.noteUrl = img.value("note_url", "");
                poi->images.push_back(pi);
            }
        }

        // Save to disk
        try {
            savePois(city->poisPath, city->graph.pois());
        } catch (const std::exception& ex) {
            setJson(res, errorJson("SAVE_FAILED", "保存失败: " + std::string(ex.what())), 500);
            return;
        }

        setJson(res, {{"status", "updated"}, {"poi", poiToJson(*poi)}});
    });

    // PUT /admin/pois/:id/image - set primary image
    server.Put(R"(/admin/pois/([^/]+)/image)", [&](const httplib::Request& req, httplib::Response& res) {
        std::string poiId = req.matches[1];
        nlohmann::json body;
        try { body = nlohmann::json::parse(req.body); } catch (...) {
            setJson(res, errorJson("VALIDATION_ERROR", "无效的 JSON"), 400); return;
        }

        std::string imageUrl = body.value("image_url", "");
        if (imageUrl.empty()) {
            setJson(res, errorJson("VALIDATION_ERROR", "image_url 不能为空"), 400); return;
        }

        std::string cityName = body.value("_city", "");
        CityBundle* city = nullptr;
        if (!cityName.empty()) {
            city = context.findCityExact(cityName);
        } else {
            for (auto& [name, c] : context.cities) {
                if (c->graph.findPoi(poiId)) { city = c; break; }
            }
        }
        if (!city) { setJson(res, errorJson("NOT_FOUND", "未找到 POI: " + poiId), 404); return; }

        Poi* poi = city->graph.findMutablePoi(poiId);
        if (!poi) { setJson(res, errorJson("NOT_FOUND", "未找到 POI: " + poiId), 404); return; }

        poi->imageUrl = imageUrl;
        try {
            savePois(city->poisPath, city->graph.pois());
        } catch (const std::exception& ex) {
            setJson(res, errorJson("SAVE_FAILED", "保存失败: " + std::string(ex.what())), 500);
            return;
        }
        setJson(res, {{"status", "updated"}, {"poi_id", poiId}, {"image_url", imageUrl}});
    });

    // ---- Editor APIs ----
    server.Post("/editor/batch-route", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            auto poiIds = body.value("poi_ids", std::vector<std::string>{});
            std::string cityName = body.value("city", context.defaultCity);
            auto* city = context.getCity(cityName);
            if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市"), 404); return; }
            nlohmann::json segments = nlohmann::json::array();
            for (size_t i = 0; i + 1 < poiIds.size(); ++i) {
                int travel = city->graph.shortestMinutes(poiIds[i], poiIds[i + 1]);
                if (travel == std::numeric_limits<int>::max()) travel = -1;
                auto route = city->graph.shortestRoute(poiIds[i], poiIds[i + 1]);
                nlohmann::json coords = nlohmann::json::array();
                for (const auto& [lat, lng] : route.pathCoords) {
                    coords.push_back(nlohmann::json::array({lat, lng}));
                }
                segments.push_back({{"from", poiIds[i]}, {"to", poiIds[i + 1]}, {"travelMinutes", travel}, {"coords", coords}});
            }
            setJson(res, {{"segments", segments}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", ex.what()), 500);
        }
    });

    server.Post("/editor/validate", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            auto stops = body.value("stops", nlohmann::json::array());
            int endMinutes = body.value("end_minutes", 21 * 60);
            nlohmann::json issues = nlohmann::json::array();
            for (const auto& stop : stops) {
                int departure = stop.value("departure", 0);
                std::string name = stop.value("poi_name", "");
                if (departure > endMinutes) {
                    issues.push_back({{"type", "overtime"}, {"poi", name}, {"message", name + " 结束时间超出当日限制"}});
                }
                int arrival = stop.value("arrival", 0);
                int closeMin = stop.value("close_minutes", 24 * 60);
                if (arrival > closeMin) {
                    issues.push_back({{"type", "closed"}, {"poi", name}, {"message", name + " 到达时已关门"}});
                }
            }
            setJson(res, {{"issues", issues}, {"valid", issues.empty()}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", ex.what()), 500);
        }
    });

    server.Post("/editor/ai-suggest", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto body = nlohmann::json::parse(req.body);
            std::string currentPoiId = body.value("current_poi_id", "");
            int currentTime = body.value("current_time", 12 * 60);
            auto usedIds = body.value("used_poi_ids", std::vector<std::string>{});
            int limit = body.value("limit", 3);
            std::string cityName = body.value("city", context.defaultCity);

            auto* city = context.getCity(cityName);
            if (!city) { setJson(res, errorJson("CITY_NOT_FOUND", "未找到城市"), 404); return; }

            std::set<std::string> usedSet(usedIds.begin(), usedIds.end());
            struct ScoredPoi { const Poi* poi; double score; std::string reason; };
            std::vector<ScoredPoi> scored;

            for (const auto& poi : city->graph.pois()) {
                if (usedSet.count(poi.id) > 0) continue;
                if (poi.type == PoiType::Hotel || poi.type == PoiType::Transit) continue;
                int travel = city->graph.shortestMinutes(currentPoiId, poi.id);
                if (travel == std::numeric_limits<int>::max()) continue;
                int arrival = currentTime + travel;
                if (arrival + poi.visitDurationMinutes > poi.closeMinutes) continue;

                double score = poi.popularity * 10.0 - travel * 1.5 - poi.priceLevel * 2.0;
                std::string reason = "热度 " + std::to_string(static_cast<int>(poi.popularity * 10)) + "，通勤 " + std::to_string(travel) + " 分";
                if (poi.type == PoiType::Restaurant && (currentTime >= 11 * 60 && currentTime <= 13 * 60)) {
                    score += 50.0;
                    reason = "午餐时间，推荐餐厅";
                }
                if (poi.type == PoiType::Restaurant && (currentTime >= 17 * 60 && currentTime <= 19 * 60)) {
                    score += 50.0;
                    reason = "晚餐时间，推荐餐厅";
                }
                scored.push_back({&poi, score, reason});
            }

            std::sort(scored.begin(), scored.end(), [](const ScoredPoi& a, const ScoredPoi& b) {
                return a.score > b.score;
            });

            nlohmann::json recs = nlohmann::json::array();
            for (int i = 0; i < std::min(limit, static_cast<int>(scored.size())); ++i) {
                const auto& sp = scored[i];
                nlohmann::json poiJson = {
                    {"id", sp.poi->id}, {"name", sp.poi->name}, {"type", poiTypeToString(sp.poi->type)},
                    {"area", sp.poi->area}, {"lat", sp.poi->lat}, {"lng", sp.poi->lng},
                    {"popularity", sp.poi->popularity}, {"price_level", sp.poi->priceLevel},
                    {"description", sp.poi->description}, {"meal_type", sp.poi->mealType},
                    {"recommendation", sp.poi->recommendation},
                };
                nlohmann::json rec = {{"poi", poiJson}, {"score", std::round(sp.score * 10.0) / 10.0}, {"reason", sp.reason}};
                recs.push_back(rec);
            }
            setJson(res, {{"recommendations", recs}});
        } catch (const std::exception& ex) {
            setJson(res, errorJson("INTERNAL_ERROR", ex.what()), 500);
        }
    });

    // Serve editor React app
    server.Get("/editor", [&](const httplib::Request&, httplib::Response& res) {
        std::ifstream file("web/editor-dist/index.html");
        if (file.is_open()) {
            std::string html((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
            res.set_content(html, "text/html; charset=utf-8");
        } else {
            res.status = 404;
            res.set_content("Editor not built. Run: cd web/editor && npm run build", "text/plain");
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





