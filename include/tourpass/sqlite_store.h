#pragma once

#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include "json.hpp"
#include "tourpass/models.h"

struct sqlite3;

namespace tourpass {

struct UserRecord {
    int64_t id = 0;
    std::string username;
    std::string passwordHash;
    std::string role;
    int bonusQueries = 0;
    std::string createdAt;
};

class SQLiteStore {
public:
    explicit SQLiteStore(const std::string& path);
    ~SQLiteStore();

    SQLiteStore(const SQLiteStore&) = delete;
    SQLiteStore& operator=(const SQLiteStore&) = delete;

    bool enabled() const { return db_ != nullptr; }
    const std::string& path() const { return path_; }

    // --- existing ---
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

    // --- auth ---
    int64_t createUser(const std::string& username, const std::string& passwordHash);
    std::optional<UserRecord> findUserByUsername(const std::string& username);
    std::optional<UserRecord> findUserById(int64_t id);

    // --- query usage ---
    int getQueryCount(int64_t userId);               // today's count
    int getBonusQueries(int64_t userId);             // unused bonus for today
    void incrementQueryCount(int64_t userId);         // +1 query
    void addBonusQueries(int64_t userId, int amount); // +N bonus (easter egg)
    bool hasEasterEggToday(int64_t userId);
    void recordEasterEgg(int64_t userId);

    // --- saved trips ---
    void saveTrip(int64_t userId, const std::string& title, const std::string& requestJson, const std::string& responseJson);
    nlohmann::json listTrips(int64_t userId);
    std::optional<nlohmann::json> getTrip(int64_t tripId, int64_t userId);
    std::string generateShareId(int64_t tripId);
    std::optional<nlohmann::json> getTripByShareId(const std::string& shareId);

    // --- feedback ---
    void submitFeedback(int64_t userId, const std::string& category, const std::string& content, const std::string& contact, const std::string& pageUrl, const std::string& userAgent);
    nlohmann::json listFeedback(const std::string& status, int limit);
    void updateFeedbackStatus(int64_t feedbackId, const std::string& status, const std::string& adminReply);

    // --- admin ---
    nlohmann::json adminStats();
    nlohmann::json listUsers(int limit);
    nlohmann::json queryStatsByDay(int days);

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
