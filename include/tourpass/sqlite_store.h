#pragma once

#include <mutex>
#include <string>

#include "tourpass/models.h"

struct sqlite3;

namespace tourpass {

class SQLiteStore {
public:
    explicit SQLiteStore(const std::string& path);
    ~SQLiteStore();

    SQLiteStore(const SQLiteStore&) = delete;
    SQLiteStore& operator=(const SQLiteStore&) = delete;

    bool enabled() const { return db_ != nullptr; }
    const std::string& path() const { return path_; }

    void recordDataVersion(size_t poiCount, size_t edgeCount, const std::string& poisHash, const std::string& edgesHash);
    void recordPlanningRequest(const std::string& requestId,
                               const std::string& route,
                               const std::string& cacheStatus,
                               const std::string& requestJson,
                               int responseStatus,
                               int64_t latencyMs);
    void recordTripJob(const std::string& id,
                       const std::string& status,
                       const std::string& requestJson,
                       const std::string& resultJson,
                       const std::string& error,
                       int64_t queueWaitMs,
                       int64_t executionMs);
    void recordBenchmarkRun(const std::string& startedAt,
                            int durationSeconds,
                            const std::string& concurrencyStepsJson,
                            const std::string& summaryJson,
                            const std::string& reportPath);

    nlohmann::json recentJobs(int limit) const;
    nlohmann::json stats() const;

private:
    void open();
    void exec(const std::string& sql);
    void initializeSchema();
    void recordWrite(bool ok);

    std::string path_;
    sqlite3* db_ = nullptr;
    mutable std::mutex mutex_;
    uint64_t writeCount_ = 0;
    uint64_t writeFailures_ = 0;
};

}  // namespace tourpass
