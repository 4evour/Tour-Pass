#pragma once

#include <mutex>
#include <optional>
#include <string>

#include "json.hpp"
#include "tourpass/data_store.h"

struct pg_conn;

namespace tourpass {

class PostgresStore : public DataStore {
public:
    explicit PostgresStore(const std::string& connStr);
    ~PostgresStore() override;

    PostgresStore(const PostgresStore&) = delete;
    PostgresStore& operator=(const PostgresStore&) = delete;

    bool enabled() const override { return conn_ != nullptr; }

    // --- recording ---
    void recordDataVersion(size_t poiCount, size_t edgeCount, const std::string& poisHash, const std::string& edgesHash) override;
    void recordPlanningRequest(const std::string& requestId, const std::string& route, const std::string& cacheStatus, const std::string& requestJson, int responseStatus, int64_t latencyMs) override;
    void recordTripJob(const std::string& id, const std::string& status, const std::string& requestJson, const std::string& resultJson, const std::string& error, int64_t queueWaitMs, int64_t executionMs) override;
    void recordBenchmarkRun(const std::string& startedAt, int durationSeconds, const std::string& concurrencyStepsJson, const std::string& summaryJson, const std::string& reportPath) override;

    nlohmann::json recentJobs(int limit) const override;
    nlohmann::json stats() const override;

    // --- auth ---
    int64_t createUser(const std::string& username, const std::string& passwordHash, const std::string& role = "user", const std::string& email = "", const std::string& deviceId = "") override;
    std::optional<UserRecord> findUserByUsername(const std::string& username) override;
    std::optional<UserRecord> findUserByEmail(const std::string& email) override;
    std::optional<UserRecord> findUserById(int64_t id) override;
    std::optional<UserRecord> findUserByDeviceId(const std::string& deviceId) override;
    void updatePassword(int64_t userId, const std::string& newHash) override;
    void updateRole(int64_t userId, const std::string& role) override;

    // --- email verification ---
    void storeVerificationCode(const std::string& email, const std::string& code, const std::string& purpose, int ttlSeconds) override;
    std::optional<std::string> getValidVerificationCode(const std::string& email, const std::string& code, const std::string& purpose) override;
    void markCodeUsed(int64_t codeId) override;

    // --- query usage ---
    int getQueryCount(int64_t userId) override;
    int getBonusQueries(int64_t userId) override;
    void incrementQueryCount(int64_t userId) override;
    void addBonusQueries(int64_t userId, int amount) override;
    bool hasEasterEggToday(int64_t userId) override;
    void recordEasterEgg(int64_t userId) override;

    // --- saved trips ---
    int64_t saveTrip(int64_t userId, const std::string& title, const std::string& requestJson, const std::string& responseJson) override;
    nlohmann::json listTrips(int64_t userId) override;
    std::optional<nlohmann::json> getTrip(int64_t tripId, int64_t userId) override;
    std::string generateShareId(int64_t tripId) override;
    std::optional<nlohmann::json> getTripByShareId(const std::string& shareId) override;

    // --- feedback ---
    void submitFeedback(int64_t userId, const std::string& category, const std::string& content, const std::string& contact, const std::string& pageUrl, const std::string& userAgent) override;
    nlohmann::json listFeedback(const std::string& status, int limit) override;
    void updateFeedbackStatus(int64_t feedbackId, const std::string& status, const std::string& adminReply) override;

    // --- admin ---
    nlohmann::json adminStats() override;
    nlohmann::json listUsers(int limit) override;
    nlohmann::json queryStatsByDay(int days) override;
    void cleanupExpiredGuests(int daysRetention) override;

private:
    void open();
    void initializeSchema();
    void exec(const std::string& sql);
    std::string queryScalar(const std::string& sql) const;

    std::string connStr_;
    pg_conn* conn_ = nullptr;
    mutable std::mutex mutex_;
    uint64_t writeCount_ = 0;
    uint64_t writeFailures_ = 0;
};

}  // namespace tourpass
