#pragma once

#include <optional>
#include <string>

#include "json.hpp"

namespace tourpass {

struct UserRecord {
    int64_t id = 0;
    std::string username;
    std::string email;
    std::string passwordHash;
    std::string role;
    int bonusQueries = 0;
    std::string createdAt;
};

class DataStore {
public:
    virtual ~DataStore() = default;
    virtual bool enabled() const = 0;
    virtual nlohmann::json stats() const = 0;

    // Recording
    virtual void recordDataVersion(size_t poiCount, size_t edgeCount, const std::string& poisHash, const std::string& edgesHash) = 0;
    virtual void recordPlanningRequest(const std::string& requestId, const std::string& route, const std::string& cacheStatus, const std::string& requestJson, int responseStatus, int64_t latencyMs) = 0;
    virtual void recordTripJob(const std::string& id, const std::string& status, const std::string& requestJson, const std::string& resultJson, const std::string& error, int64_t queueWaitMs, int64_t executionMs) = 0;
    virtual void recordBenchmarkRun(const std::string& startedAt, int durationSeconds, const std::string& concurrencyStepsJson, const std::string& summaryJson, const std::string& reportPath) = 0;
    virtual nlohmann::json recentJobs(int limit) const = 0;

    // Auth
    virtual int64_t createUser(const std::string& username, const std::string& passwordHash, const std::string& role = "user", const std::string& email = "", const std::string& deviceId = "") = 0;
    virtual std::optional<UserRecord> findUserByUsername(const std::string& username) = 0;
    virtual std::optional<UserRecord> findUserByEmail(const std::string& email) = 0;
    virtual std::optional<UserRecord> findUserById(int64_t id) = 0;
    virtual std::optional<UserRecord> findUserByDeviceId(const std::string& deviceId) = 0;
    virtual void updatePassword(int64_t userId, const std::string& newHash) = 0;
    virtual void updateRole(int64_t userId, const std::string& role) = 0;

    // Email verification
    virtual void storeVerificationCode(const std::string& email, const std::string& code, const std::string& purpose, int ttlSeconds) = 0;
    virtual std::optional<std::string> getValidVerificationCode(const std::string& email, const std::string& code, const std::string& purpose) = 0;
    virtual void markCodeUsed(int64_t codeId) = 0;

    // Query usage
    virtual int getQueryCount(int64_t userId) = 0;
    virtual int getBonusQueries(int64_t userId) = 0;
    virtual void incrementQueryCount(int64_t userId) = 0;
    virtual void addBonusQueries(int64_t userId, int amount) = 0;
    virtual bool hasEasterEggToday(int64_t userId) = 0;
    virtual void recordEasterEgg(int64_t userId) = 0;

    // Saved trips
    virtual void saveTrip(int64_t userId, const std::string& title, const std::string& requestJson, const std::string& responseJson) = 0;
    virtual nlohmann::json listTrips(int64_t userId) = 0;
    virtual std::optional<nlohmann::json> getTrip(int64_t tripId, int64_t userId) = 0;
    virtual std::string generateShareId(int64_t tripId) = 0;
    virtual std::optional<nlohmann::json> getTripByShareId(const std::string& shareId) = 0;

    // Feedback
    virtual void submitFeedback(int64_t userId, const std::string& category, const std::string& content, const std::string& contact, const std::string& pageUrl, const std::string& userAgent) = 0;
    virtual nlohmann::json listFeedback(const std::string& status, int limit) = 0;
    virtual void updateFeedbackStatus(int64_t feedbackId, const std::string& status, const std::string& adminReply) = 0;

    // Admin
    virtual nlohmann::json adminStats() = 0;
    virtual nlohmann::json listUsers(int limit) = 0;
    virtual nlohmann::json queryStatsByDay(int days) = 0;
    virtual void cleanupExpiredGuests(int daysRetention) = 0;
};

}  // namespace tourpass
