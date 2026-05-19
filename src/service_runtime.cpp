#include "tourpass/service_runtime.h"

#include <algorithm>
#include <cstdlib>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace tourpass {

namespace {

size_t envSize(const char* key, size_t fallback, size_t minValue, size_t maxValue) {
    const char* value = std::getenv(key);
    if (!value || !*value) return fallback;
    try {
        size_t parsed = static_cast<size_t>(std::stoul(value));
        return std::max(minValue, std::min(maxValue, parsed));
    } catch (...) {
        return fallback;
    }
}

uint64_t percentile(std::vector<int64_t> values, double p) {
    if (values.empty()) return 0;
    std::sort(values.begin(), values.end());
    size_t index = static_cast<size_t>(std::ceil((p / 100.0) * values.size()));
    if (index == 0) index = 1;
    return static_cast<uint64_t>(values[index - 1]);
}

std::string hexHash(size_t value) {
    std::ostringstream out;
    out << std::hex << value;
    return out.str();
}

}  // namespace

RuntimeConfig runtimeConfigFromEnv() {
    RuntimeConfig config;
    const size_t hardware = std::max<size_t>(2, std::thread::hardware_concurrency());
    config.workerCount = envSize("TOURPASS_WORKERS", std::min<size_t>(hardware, 8), 1, 64);
    config.maxQueuedRequests = envSize("TOURPASS_MAX_QUEUE", 64, 1, 4096);
    config.maxBodyBytes = envSize("TOURPASS_MAX_BODY_BYTES", 64 * 1024, 1024, 1024 * 1024);
    config.cacheEntries = envSize("TOURPASS_CACHE_ENTRIES", 64, 1, 4096);
    config.cacheTtlSeconds = static_cast<int>(envSize("TOURPASS_CACHE_TTL_SECONDS", 120, 1, 3600));
    config.maxTripJobs = envSize("TOURPASS_MAX_TRIP_JOBS", 32, 1, 1024);
    return config;
}

std::string makeRequestId() {
    static std::atomic<uint64_t> next{1};
    auto now = std::chrono::system_clock::now().time_since_epoch().count();
    std::ostringstream out;
    out << "req-" << std::hex << now << "-" << next.fetch_add(1);
    return out.str();
}

std::string requestCacheKey(const std::string& method, const std::string& path, const std::string& query, const std::string& body) {
    std::hash<std::string> hasher;
    return method + " " + path + "?" + query + "#" + hexHash(hasher(body));
}

ResponseCache::ResponseCache(size_t capacity, std::chrono::seconds ttl)
    : capacity_(std::max<size_t>(1, capacity)), ttl_(ttl) {}

bool ResponseCache::get(const std::string& key, nlohmann::json& value) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto found = index_.find(key);
    if (found == index_.end()) {
        ++misses_;
        return false;
    }
    auto now = std::chrono::steady_clock::now();
    if (found->second->expiresAt <= now) {
        entries_.erase(found->second);
        index_.erase(found);
        ++misses_;
        ++evictions_;
        return false;
    }
    entries_.splice(entries_.begin(), entries_, found->second);
    value = entries_.front().value;
    ++hits_;
    return true;
}

void ResponseCache::put(const std::string& key, const nlohmann::json& value) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto found = index_.find(key);
    if (found != index_.end()) {
        found->second->value = value;
        found->second->expiresAt = std::chrono::steady_clock::now() + ttl_;
        entries_.splice(entries_.begin(), entries_, found->second);
        return;
    }
    entries_.push_front(Entry{key, value, std::chrono::steady_clock::now() + ttl_});
    index_[key] = entries_.begin();
    while (entries_.size() > capacity_) {
        index_.erase(entries_.back().key);
        entries_.pop_back();
        ++evictions_;
    }
}

CacheStats ResponseCache::stats() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return CacheStats{entries_.size(), hits_, misses_, evictions_};
}

void ServiceMetrics::beginRequest() {
    totalRequests_.fetch_add(1);
    inFlightRequests_.fetch_add(1);
}

void ServiceMetrics::endRequest() {
    inFlightRequests_.fetch_sub(1);
}

void ServiceMetrics::recordRequest(const std::string& route, int status, std::chrono::milliseconds latency, bool) {
    std::lock_guard<std::mutex> lock(mutex_);
    statusCodes_[status] += 1;
    auto& stats = routes_[route.empty() ? "unknown" : route];
    stats.count += 1;
    stats.totalMs += static_cast<uint64_t>(std::max<int64_t>(0, latency.count()));
    stats.samples.push_back(std::max<int64_t>(0, latency.count()));
    if (stats.samples.size() > 256) {
        stats.samples.erase(stats.samples.begin(), stats.samples.begin() + static_cast<long>(stats.samples.size() - 256));
    }
}

void ServiceMetrics::recordCacheHit() {
    std::lock_guard<std::mutex> lock(mutex_);
    ++cacheHits_;
}

void ServiceMetrics::recordCacheMiss() {
    std::lock_guard<std::mutex> lock(mutex_);
    ++cacheMisses_;
}

void ServiceMetrics::recordJobStatus(const std::string& status, int delta) {
    std::lock_guard<std::mutex> lock(mutex_);
    jobStatuses_[status] += delta;
    if (jobStatuses_[status] < 0) jobStatuses_[status] = 0;
}

nlohmann::json ServiceMetrics::toJson() const {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json routeJson = nlohmann::json::object();
    for (const auto& item : routes_) {
        const auto& stats = item.second;
        routeJson[item.first] = {
            {"count", stats.count},
            {"avg_ms", stats.count == 0 ? 0.0 : static_cast<double>(stats.totalMs) / static_cast<double>(stats.count)},
            {"p95_ms", percentile(stats.samples, 95)}
        };
    }
    nlohmann::json statusJson = nlohmann::json::object();
    for (const auto& item : statusCodes_) {
        statusJson[std::to_string(item.first)] = item.second;
    }
    nlohmann::json jobJson = nlohmann::json::object();
    for (const auto& item : jobStatuses_) {
        jobJson[item.first] = item.second;
    }
    uint64_t totalCache = cacheHits_ + cacheMisses_;
    return {
        {"total_requests", totalRequests_.load()},
        {"in_flight_requests", inFlightRequests_.load()},
        {"status_codes", statusJson},
        {"routes", routeJson},
        {"cache", {
            {"hits", cacheHits_},
            {"misses", cacheMisses_},
            {"hit_rate", totalCache == 0 ? 0.0 : static_cast<double>(cacheHits_) / static_cast<double>(totalCache)}
        }},
        {"jobs", jobJson}
    };
}

TripJobStore::TripJobStore(size_t maxJobs) : maxJobs_(std::max<size_t>(1, maxJobs)), worker_([this]() { workerLoop(); }) {}

TripJobStore::~TripJobStore() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stopping_ = true;
    }
    condition_.notify_all();
    if (worker_.joinable()) worker_.join();
}

std::string TripJobStore::submit(const TripRequest& request, PlannerFn planner) {
    if (!planner) {
        throw std::runtime_error("planner callback is required");
    }
    std::string id = makeRequestId();
    auto now = std::chrono::system_clock::now();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        trimLocked();
        Job job;
        job.id = id;
        job.status = "QUEUED";
        job.request = request;
        job.planner = std::move(planner);
        job.createdAt = now;
        job.updatedAt = now;
        jobs_[id] = std::move(job);
        queue_.push(id);
    }
    condition_.notify_one();
    return id;
}

bool TripJobStore::get(const std::string& id, TripJobSnapshot& snapshot) const {
    std::lock_guard<std::mutex> lock(mutex_);
    auto found = jobs_.find(id);
    if (found == jobs_.end()) return false;
    const auto& job = found->second;
    snapshot = TripJobSnapshot{job.id, job.status, job.result, job.error, job.createdAt, job.updatedAt};
    return true;
}

bool TripJobStore::cancel(const std::string& id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto found = jobs_.find(id);
    if (found == jobs_.end()) return false;
    if (found->second.status == "RUNNING") return false;
    found->second.status = "CANCELLED";
    found->second.updatedAt = std::chrono::system_clock::now();
    return true;
}

nlohmann::json TripJobStore::stats() const {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json counts = {
        {"QUEUED", 0},
        {"RUNNING", 0},
        {"SUCCEEDED", 0},
        {"FAILED", 0},
        {"CANCELLED", 0}
    };
    for (const auto& item : jobs_) {
        counts[item.second.status] = counts.value(item.second.status, 0) + 1;
    }
    counts["total"] = jobs_.size();
    counts["queue_depth"] = queue_.size();
    return counts;
}

void TripJobStore::workerLoop() {
    for (;;) {
        std::string id;
        PlannerFn planner;
        TripRequest request;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            condition_.wait(lock, [&]() { return stopping_ || !queue_.empty(); });
            if (stopping_ && queue_.empty()) return;
            id = queue_.front();
            queue_.pop();
            auto found = jobs_.find(id);
            if (found == jobs_.end() || found->second.status == "CANCELLED") {
                continue;
            }
            planner = std::move(found->second.planner);
            found->second.status = "RUNNING";
            found->second.updatedAt = std::chrono::system_clock::now();
            request = found->second.request;
        }

        try {
            nlohmann::json result = planner(request);
            std::lock_guard<std::mutex> lock(mutex_);
            auto found = jobs_.find(id);
            if (found != jobs_.end() && found->second.status != "CANCELLED") {
                found->second.result = result;
                found->second.status = "SUCCEEDED";
                found->second.updatedAt = std::chrono::system_clock::now();
            }
        } catch (const std::exception& ex) {
            std::lock_guard<std::mutex> lock(mutex_);
            auto found = jobs_.find(id);
            if (found != jobs_.end() && found->second.status != "CANCELLED") {
                found->second.error = ex.what();
                found->second.status = "FAILED";
                found->second.updatedAt = std::chrono::system_clock::now();
            }
        }
    }
}

void TripJobStore::trimLocked() {
    while (jobs_.size() >= maxJobs_) {
        auto oldest = jobs_.end();
        for (auto it = jobs_.begin(); it != jobs_.end(); ++it) {
            if (it->second.status == "RUNNING") continue;
            if (oldest == jobs_.end() || it->second.updatedAt < oldest->second.updatedAt) {
                oldest = it;
            }
        }
        if (oldest == jobs_.end()) break;
        jobs_.erase(oldest);
    }
}

}  // namespace tourpass
