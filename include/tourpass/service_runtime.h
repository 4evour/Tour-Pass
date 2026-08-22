#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <functional>
#include <list>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <stdexcept>

#include "tourpass/models.h"

namespace tourpass {

struct RuntimeConfig {
    size_t workerCount = 0;
    size_t maxQueuedRequests = 64;
    size_t maxBodyBytes = 256 * 1024;
    size_t cacheEntries = 64;
    int cacheTtlSeconds = 120;
    size_t maxTripJobs = 32;
    size_t jobWorkerCount = 1;
    size_t maxInFlightRequests = 0;
    bool dbEnabled = true;
    std::string dbPath = "storage/tourpass.sqlite";
    std::string travelProviderName = "local";
};

RuntimeConfig runtimeConfigFromEnv();
std::string makeRequestId();
std::string requestCacheKey(const std::string& method, const std::string& path, const std::string& query, const std::string& body);

struct CacheStats {
    size_t entries = 0;
    uint64_t hits = 0;
    uint64_t misses = 0;
    uint64_t evictions = 0;
};

class ResponseCache {
public:
    ResponseCache(size_t capacity = 64, std::chrono::seconds ttl = std::chrono::seconds(120));

    bool get(const std::string& key, nlohmann::json& value);
    void put(const std::string& key, const nlohmann::json& value);
    void clear();
    CacheStats stats() const;

private:
    struct Entry {
        std::string key;
        nlohmann::json value;
        std::chrono::steady_clock::time_point expiresAt;
    };

    size_t capacity_;
    std::chrono::seconds ttl_;
    mutable std::mutex mutex_;
    std::list<Entry> entries_;
    std::unordered_map<std::string, std::list<Entry>::iterator> index_;
    uint64_t hits_ = 0;
    uint64_t misses_ = 0;
    uint64_t evictions_ = 0;
};

class ServiceMetrics {
public:
    void beginRequest();
    void endRequest();
    int64_t inFlightRequests() const { return inFlightRequests_.load(); }
    void recordRequest(const std::string& route, int status, std::chrono::milliseconds latency, bool cacheable);
    void recordCacheHit();
    void recordCacheMiss();
    void recordRejectedRequest();
    void recordDbWrite(bool ok);
    void recordJobStatus(const std::string& status, int delta);
    nlohmann::json toJson() const;

private:
    struct RouteStats {
        uint64_t count = 0;
        uint64_t totalMs = 0;
        std::deque<int64_t> samples;
    };

    mutable std::mutex mutex_;
    std::atomic<uint64_t> totalRequests_{0};
    std::atomic<int64_t> inFlightRequests_{0};
    uint64_t rejectedRequests_ = 0;
    uint64_t cacheHits_ = 0;
    uint64_t cacheMisses_ = 0;
    uint64_t dbWrites_ = 0;
    uint64_t dbWriteFailures_ = 0;
    std::unordered_map<int, uint64_t> statusCodes_;
    std::unordered_map<std::string, RouteStats> routes_;
    std::unordered_map<std::string, int> jobStatuses_;
};

class QueueFullError : public std::runtime_error {
public:
    explicit QueueFullError(const std::string& message) : std::runtime_error(message) {}
};

struct TripJobSnapshot {
    std::string id;
    std::string status;
    nlohmann::json result;
    std::string error;
    int64_t queueWaitMs = 0;
    int64_t executionMs = 0;
    std::chrono::system_clock::time_point createdAt;
    std::chrono::system_clock::time_point updatedAt;
};

class TripJobStore {
public:
    explicit TripJobStore(size_t maxJobs = 32, size_t workerCount = 1);
    ~TripJobStore();

    using PlannerFn = std::function<nlohmann::json(const TripRequest&)>;
    std::string submit(const TripRequest& request, PlannerFn planner);
    std::string submitWithId(const std::string& id, const TripRequest& request, PlannerFn planner);
    bool get(const std::string& id, TripJobSnapshot& snapshot) const;
    bool cancel(const std::string& id);
    nlohmann::json stats() const;

private:
    struct Job {
        std::string id;
        std::string status = "QUEUED";
        TripRequest request;
        PlannerFn planner;
        nlohmann::json result;
        std::string error;
        int64_t queueWaitMs = 0;
        int64_t executionMs = 0;
        std::chrono::system_clock::time_point createdAt;
        std::chrono::system_clock::time_point updatedAt;
    };

    void workerLoop();
    void trimLocked();

    size_t maxJobs_;
    size_t workerCount_;
    mutable std::mutex mutex_;
    std::condition_variable condition_;
    std::unordered_map<std::string, Job> jobs_;
    std::queue<std::string> queue_;
    std::atomic<bool> stopping_{false};
    uint64_t completedJobs_ = 0;
    uint64_t failedJobs_ = 0;
    uint64_t totalQueueWaitMs_ = 0;
    uint64_t totalExecutionMs_ = 0;
    std::vector<std::thread> workers_;
};

}  // namespace tourpass
