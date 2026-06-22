#include "tourpass/sqlite_store.h"
#include "tourpass/auth.h"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>

#include "sqlite3.h"

namespace tourpass {

namespace {

std::string nowSql() {
    return "strftime('%Y-%m-%dT%H:%M:%fZ','now')";
}

void bindText(sqlite3_stmt* stmt, int index, const std::string& value) {
    sqlite3_bind_text(stmt, index, value.c_str(), static_cast<int>(value.size()), SQLITE_TRANSIENT);
}

const char* safeColumnText(sqlite3_stmt* stmt, int col) {
    const char* p = reinterpret_cast<const char*>(sqlite3_column_text(stmt, col));
    return p ? p : "";
}

class Statement {
public:
    Statement(sqlite3* db, const std::string& sql) : db_(db) {
        if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt_, nullptr) != SQLITE_OK) {
            throw std::runtime_error(sqlite3_errmsg(db_));
        }
    }

    ~Statement() {
        if (stmt_) sqlite3_finalize(stmt_);
    }

    sqlite3_stmt* get() const { return stmt_; }

private:
    sqlite3* db_;
    sqlite3_stmt* stmt_ = nullptr;
};

}  // namespace

SQLiteStore::SQLiteStore(const std::string& path) : path_(path) {
    open();
    initializeSchema();
}

SQLiteStore::~SQLiteStore() {
    if (db_) {
        sqlite3_close(db_);
        db_ = nullptr;
    }
}

void SQLiteStore::open() {
    std::filesystem::path dbPath(path_);
    if (dbPath.has_parent_path()) {
        std::filesystem::create_directories(dbPath.parent_path());
    }
    if (sqlite3_open(path_.c_str(), &db_) != SQLITE_OK) {
        std::string reason = db_ ? sqlite3_errmsg(db_) : "unknown sqlite open error";
        if (db_) sqlite3_close(db_);
        db_ = nullptr;
        throw std::runtime_error(reason);
    }
    exec("PRAGMA journal_mode=WAL;");
    exec("PRAGMA synchronous=NORMAL;");
    exec("PRAGMA busy_timeout=5000;");
    exec("PRAGMA foreign_keys=ON;");
}

void SQLiteStore::exec(const std::string& sql) {
    char* error = nullptr;
    if (sqlite3_exec(db_, sql.c_str(), nullptr, nullptr, &error) != SQLITE_OK) {
        std::string reason = error ? error : sqlite3_errmsg(db_);
        sqlite3_free(error);
        throw std::runtime_error(reason);
    }
}

void SQLiteStore::initializeSchema() {
    std::lock_guard<std::mutex> lock(mutex_);
    exec("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);");
    exec("CREATE TABLE IF NOT EXISTS planning_requests ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "request_id TEXT NOT NULL,"
         "route TEXT NOT NULL,"
         "cache_status TEXT NOT NULL,"
         "request_json TEXT NOT NULL,"
         "response_status INTEGER NOT NULL,"
         "latency_ms INTEGER NOT NULL,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");
    exec("CREATE TABLE IF NOT EXISTS trip_jobs ("
         "id TEXT PRIMARY KEY,"
         "status TEXT NOT NULL,"
         "request_json TEXT NOT NULL,"
         "result_json TEXT NOT NULL,"
         "error TEXT NOT NULL,"
         "queue_wait_ms INTEGER NOT NULL,"
         "execution_ms INTEGER NOT NULL,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
         "updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");
    exec("CREATE TABLE IF NOT EXISTS benchmark_runs ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "started_at TEXT NOT NULL,"
         "duration_seconds INTEGER NOT NULL,"
         "concurrency_steps_json TEXT NOT NULL,"
         "summary_json TEXT NOT NULL,"
         "report_path TEXT NOT NULL,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");
    exec("CREATE TABLE IF NOT EXISTS data_versions ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "poi_count INTEGER NOT NULL,"
         "edge_count INTEGER NOT NULL,"
         "pois_hash TEXT NOT NULL,"
         "edges_hash TEXT NOT NULL,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");
    exec("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (1, " + nowSql() + ");");

    // Auth tables (schema v2)
    exec("CREATE TABLE IF NOT EXISTS users ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
         "password_hash TEXT NOT NULL,"
         "role TEXT NOT NULL DEFAULT 'user',"
         "bonus_queries INTEGER NOT NULL DEFAULT 0,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");

    exec("CREATE TABLE IF NOT EXISTS query_usage ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "user_id INTEGER NOT NULL REFERENCES users(id),"
         "query_date TEXT NOT NULL,"
         "query_count INTEGER NOT NULL DEFAULT 0,"
         "UNIQUE(user_id, query_date)"
         ");");

    exec("CREATE TABLE IF NOT EXISTS easter_egg_log ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "user_id INTEGER NOT NULL REFERENCES users(id),"
         "claimed_date TEXT NOT NULL,"
         "UNIQUE(user_id, claimed_date)"
         ");");

    exec("CREATE TABLE IF NOT EXISTS saved_trips ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "user_id INTEGER NOT NULL REFERENCES users(id),"
         "title TEXT NOT NULL DEFAULT '',"
         "request_json TEXT NOT NULL,"
         "response_json TEXT NOT NULL,"
         "share_id TEXT UNIQUE,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
         "updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");
    // Add updated_at column if missing (existing DBs)
    try { exec("ALTER TABLE saved_trips ADD COLUMN updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'));"); }
    catch (...) { /* column already exists */ }

    exec("CREATE TABLE IF NOT EXISTS feedback ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "user_id INTEGER NOT NULL REFERENCES users(id),"
         "category TEXT NOT NULL DEFAULT 'other',"
         "content TEXT NOT NULL,"
         "contact TEXT NOT NULL DEFAULT '',"
         "page_url TEXT NOT NULL DEFAULT '',"
         "user_agent TEXT NOT NULL DEFAULT '',"
         "status TEXT NOT NULL DEFAULT 'pending',"
         "admin_reply TEXT NOT NULL DEFAULT '',"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");

    exec("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (2, " + nowSql() + ");");

    // Schema v3: email verification, guest mode
    exec("CREATE TABLE IF NOT EXISTS verification_codes ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "email TEXT NOT NULL,"
         "code TEXT NOT NULL,"
         "purpose TEXT NOT NULL DEFAULT 'register',"
         "expires_at TEXT NOT NULL,"
         "used INTEGER NOT NULL DEFAULT 0,"
         "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
         ");");
    // Add email column to users if not exists (ignore error if already exists)
    try { exec("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT '';"); } catch (const std::exception& e) {
        std::string msg = e.what();
        if (msg.find("duplicate column") == std::string::npos) throw;
    }
    exec("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (3, " + nowSql() + ");");

    // Schema v4: guest IP limit
    exec("CREATE TABLE IF NOT EXISTS guest_creation_log ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
         "ip TEXT NOT NULL,"
         "created_date TEXT NOT NULL,"
         "UNIQUE(ip, created_date)"
         ");");
    exec("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (4, " + nowSql() + ");");

    // Schema v5: guest device binding
    try { exec("ALTER TABLE users ADD COLUMN device_id TEXT NOT NULL DEFAULT '';"); } catch (const std::exception& e) {
        std::string msg = e.what();
        if (msg.find("duplicate column") == std::string::npos) throw;
    }
    exec("CREATE INDEX IF NOT EXISTS idx_users_device_id ON users(device_id);");
    exec("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (5, " + nowSql() + ");");
}

void SQLiteStore::recordWrite(bool ok) {
    if (ok) {
        ++writeCount_;
    } else {
        ++writeFailures_;
    }
}

void SQLiteStore::recordDataVersion(size_t poiCount, size_t edgeCount, const std::string& poisHash, const std::string& edgesHash) {
    std::lock_guard<std::mutex> lock(mutex_);
    try {
        Statement stmt(db_, "INSERT INTO data_versions(poi_count, edge_count, pois_hash, edges_hash) VALUES (?, ?, ?, ?);");
        sqlite3_bind_int64(stmt.get(), 1, static_cast<sqlite3_int64>(poiCount));
        sqlite3_bind_int64(stmt.get(), 2, static_cast<sqlite3_int64>(edgeCount));
        bindText(stmt.get(), 3, poisHash);
        bindText(stmt.get(), 4, edgesHash);
        recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
    } catch (...) {
        recordWrite(false);
        throw;
    }
}

void SQLiteStore::recordPlanningRequest(const std::string& requestId,
                                        const std::string& route,
                                        const std::string& cacheStatus,
                                        const std::string& requestJson,
                                        int responseStatus,
                                        int64_t latencyMs) {
    std::lock_guard<std::mutex> lock(mutex_);
    try {
        Statement stmt(db_, "INSERT INTO planning_requests(request_id, route, cache_status, request_json, response_status, latency_ms) VALUES (?, ?, ?, ?, ?, ?);");
        bindText(stmt.get(), 1, requestId);
        bindText(stmt.get(), 2, route);
        bindText(stmt.get(), 3, cacheStatus);
        bindText(stmt.get(), 4, requestJson);
        sqlite3_bind_int(stmt.get(), 5, responseStatus);
        sqlite3_bind_int64(stmt.get(), 6, static_cast<sqlite3_int64>(latencyMs));
        recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
    } catch (...) {
        recordWrite(false);
        throw;
    }
}

void SQLiteStore::recordTripJob(const std::string& id,
                                const std::string& status,
                                const std::string& requestJson,
                                const std::string& resultJson,
                                const std::string& error,
                                int64_t queueWaitMs,
                                int64_t executionMs) {
    std::lock_guard<std::mutex> lock(mutex_);
    try {
        Statement stmt(db_, "INSERT INTO trip_jobs(id, status, request_json, result_json, error, queue_wait_ms, execution_ms, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
                            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, request_json=excluded.request_json, result_json=excluded.result_json, "
                            "error=excluded.error, queue_wait_ms=excluded.queue_wait_ms, execution_ms=excluded.execution_ms, updated_at=excluded.updated_at;");
        bindText(stmt.get(), 1, id);
        bindText(stmt.get(), 2, status);
        bindText(stmt.get(), 3, requestJson);
        bindText(stmt.get(), 4, resultJson);
        bindText(stmt.get(), 5, error);
        sqlite3_bind_int64(stmt.get(), 6, static_cast<sqlite3_int64>(queueWaitMs));
        sqlite3_bind_int64(stmt.get(), 7, static_cast<sqlite3_int64>(executionMs));
        recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
    } catch (...) {
        recordWrite(false);
        throw;
    }
}

void SQLiteStore::recordBenchmarkRun(const std::string& startedAt,
                                     int durationSeconds,
                                     const std::string& concurrencyStepsJson,
                                     const std::string& summaryJson,
                                     const std::string& reportPath) {
    std::lock_guard<std::mutex> lock(mutex_);
    try {
        Statement stmt(db_, "INSERT INTO benchmark_runs(started_at, duration_seconds, concurrency_steps_json, summary_json, report_path) VALUES (?, ?, ?, ?, ?);");
        bindText(stmt.get(), 1, startedAt);
        sqlite3_bind_int(stmt.get(), 2, durationSeconds);
        bindText(stmt.get(), 3, concurrencyStepsJson);
        bindText(stmt.get(), 4, summaryJson);
        bindText(stmt.get(), 5, reportPath);
        recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
    } catch (...) {
        recordWrite(false);
        throw;
    }
}

nlohmann::json SQLiteStore::recentJobs(int limit) const {
    std::lock_guard<std::mutex> lock(mutex_);
    int boundedLimit = std::max(1, std::min(100, limit));
    Statement stmt(db_, "SELECT id, status, queue_wait_ms, execution_ms, created_at, updated_at FROM trip_jobs ORDER BY updated_at DESC LIMIT ?;");
    sqlite3_bind_int(stmt.get(), 1, boundedLimit);
    nlohmann::json jobs = nlohmann::json::array();
    while (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        jobs.push_back({
            {"id", safeColumnText(stmt.get(), 0)},
            {"status", safeColumnText(stmt.get(), 1)},
            {"queue_wait_ms", sqlite3_column_int64(stmt.get(), 2)},
            {"execution_ms", sqlite3_column_int64(stmt.get(), 3)},
            {"created_at", safeColumnText(stmt.get(), 4)},
            {"updated_at", safeColumnText(stmt.get(), 5)}
        });
    }
    return jobs;
}

nlohmann::json SQLiteStore::stats() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return {
        {"enabled", enabled()},
        {"path", path_},
        {"write_count", writeCount_},
        {"write_failures", writeFailures_}
    };
}

// ---- Auth ----

int64_t SQLiteStore::createUser(const std::string& username, const std::string& passwordHash, const std::string& role, const std::string& email, const std::string& deviceId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "INSERT INTO users(username, password_hash, role, email, device_id) VALUES (?, ?, ?, ?, ?);");
    bindText(stmt.get(), 1, username);
    bindText(stmt.get(), 2, passwordHash);
    bindText(stmt.get(), 3, role);
    bindText(stmt.get(), 4, email);
    bindText(stmt.get(), 5, deviceId);
    if (sqlite3_step(stmt.get()) != SQLITE_DONE) {
        std::string err = sqlite3_errmsg(db_);
        if (err.find("UNIQUE") != std::string::npos) {
            throw std::runtime_error("USERNAME_TAKEN");
        }
        throw std::runtime_error(err);
    }
    return sqlite3_last_insert_rowid(db_);
}

std::optional<UserRecord> SQLiteStore::findUserByUsername(const std::string& username) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at FROM users WHERE username = ?;");
    bindText(stmt.get(), 1, username);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        UserRecord u;
        u.id = sqlite3_column_int64(stmt.get(), 0);
        u.username = safeColumnText(stmt.get(), 1);
        u.email = safeColumnText(stmt.get(), 2);
        u.passwordHash = safeColumnText(stmt.get(), 3);
        u.role = safeColumnText(stmt.get(), 4);
        u.bonusQueries = sqlite3_column_int(stmt.get(), 5);
        u.createdAt = safeColumnText(stmt.get(), 6);
        return u;
    }
    return std::nullopt;
}

std::optional<UserRecord> SQLiteStore::findUserByEmail(const std::string& email) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at FROM users WHERE email = ?;");
    bindText(stmt.get(), 1, email);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        UserRecord u;
        u.id = sqlite3_column_int64(stmt.get(), 0);
        u.username = safeColumnText(stmt.get(), 1);
        u.email = safeColumnText(stmt.get(), 2);
        u.passwordHash = safeColumnText(stmt.get(), 3);
        u.role = safeColumnText(stmt.get(), 4);
        u.bonusQueries = sqlite3_column_int(stmt.get(), 5);
        u.createdAt = safeColumnText(stmt.get(), 6);
        return u;
    }
    return std::nullopt;
}

std::optional<UserRecord> SQLiteStore::findUserById(int64_t id) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at FROM users WHERE id = ?;");
    sqlite3_bind_int64(stmt.get(), 1, id);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        UserRecord u;
        u.id = sqlite3_column_int64(stmt.get(), 0);
        u.username = safeColumnText(stmt.get(), 1);
        u.email = safeColumnText(stmt.get(), 2);
        u.passwordHash = safeColumnText(stmt.get(), 3);
        u.role = safeColumnText(stmt.get(), 4);
        u.bonusQueries = sqlite3_column_int(stmt.get(), 5);
        u.createdAt = safeColumnText(stmt.get(), 6);
        return u;
    }
    return std::nullopt;
}

std::optional<UserRecord> SQLiteStore::findUserByDeviceId(const std::string& deviceId) {
    if (deviceId.empty()) return std::nullopt;
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at FROM users WHERE device_id = ? AND role = 'guest' ORDER BY created_at DESC LIMIT 1;");
    bindText(stmt.get(), 1, deviceId);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        UserRecord u;
        u.id = sqlite3_column_int64(stmt.get(), 0);
        u.username = safeColumnText(stmt.get(), 1);
        u.email = safeColumnText(stmt.get(), 2);
        u.passwordHash = safeColumnText(stmt.get(), 3);
        u.role = safeColumnText(stmt.get(), 4);
        u.bonusQueries = sqlite3_column_int(stmt.get(), 5);
        u.createdAt = safeColumnText(stmt.get(), 6);
        return u;
    }
    return std::nullopt;
}

void SQLiteStore::updatePassword(int64_t userId, const std::string& newHash) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "UPDATE users SET password_hash = ? WHERE id = ?;");
    bindText(stmt.get(), 1, newHash);
    sqlite3_bind_int64(stmt.get(), 2, userId);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

void SQLiteStore::updateRole(int64_t userId, const std::string& role) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "UPDATE users SET role = ? WHERE id = ?;");
    bindText(stmt.get(), 1, role);
    sqlite3_bind_int64(stmt.get(), 2, userId);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

void SQLiteStore::storeVerificationCode(const std::string& email, const std::string& code, const std::string& purpose, int ttlSeconds) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "INSERT INTO verification_codes(email, code, purpose, expires_at) VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now',?));");
    bindText(stmt.get(), 1, email);
    bindText(stmt.get(), 2, code);
    bindText(stmt.get(), 3, purpose);
    std::string ttl = "+" + std::to_string(ttlSeconds) + " seconds";
    bindText(stmt.get(), 4, ttl);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

std::optional<std::string> SQLiteStore::getValidVerificationCode(const std::string& email, const std::string& code, const std::string& purpose) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id FROM verification_codes WHERE email = ? AND code = ? AND purpose = ? AND used = 0 AND expires_at > strftime('%Y-%m-%dT%H:%M:%fZ','now') ORDER BY created_at DESC LIMIT 1;");
    bindText(stmt.get(), 1, email);
    bindText(stmt.get(), 2, code);
    bindText(stmt.get(), 3, purpose);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        return std::to_string(sqlite3_column_int64(stmt.get(), 0));
    }
    return std::nullopt;
}

void SQLiteStore::markCodeUsed(int64_t codeId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "UPDATE verification_codes SET used = 1 WHERE id = ?;");
    sqlite3_bind_int64(stmt.get(), 1, codeId);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

static std::string todayDate() {
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    struct tm utc;
#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif
    char buf[11];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d", utc.tm_year + 1900, utc.tm_mon + 1, utc.tm_mday);
    return buf;
}

// canCreateGuest / logGuestCreation removed (dead code, always returned true)

// ---- Query usage ----

int SQLiteStore::getQueryCount(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT COALESCE(query_count, 0) FROM query_usage WHERE user_id = ? AND query_date = ?;");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    std::string today = todayDate();
    bindText(stmt.get(), 2, today);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        return sqlite3_column_int(stmt.get(), 0);
    }
    return 0;
}

int SQLiteStore::getBonusQueries(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT COALESCE(bonus_queries, 0) FROM users WHERE id = ?;");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        return sqlite3_column_int(stmt.get(), 0);
    }
    return 0;
}

void SQLiteStore::incrementQueryCount(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = todayDate();
    Statement stmt(db_, "INSERT INTO query_usage(user_id, query_date, query_count) VALUES (?, ?, 1) "
                        "ON CONFLICT(user_id, query_date) DO UPDATE SET query_count = query_count + 1;");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    bindText(stmt.get(), 2, today);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

void SQLiteStore::addBonusQueries(int64_t userId, int amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "UPDATE users SET bonus_queries = bonus_queries + ? WHERE id = ?;");
    sqlite3_bind_int(stmt.get(), 1, amount);
    sqlite3_bind_int64(stmt.get(), 2, userId);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

bool SQLiteStore::hasEasterEggToday(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = todayDate();
    Statement stmt(db_, "SELECT 1 FROM easter_egg_log WHERE user_id = ? AND claimed_date = ?;");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    bindText(stmt.get(), 2, today);
    return sqlite3_step(stmt.get()) == SQLITE_ROW;
}

void SQLiteStore::recordEasterEgg(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = todayDate();
    Statement stmt(db_, "INSERT OR IGNORE INTO easter_egg_log(user_id, claimed_date) VALUES (?, ?);");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    bindText(stmt.get(), 2, today);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

// ---- Saved trips ----

int64_t SQLiteStore::saveTrip(int64_t userId, const std::string& title, const std::string& requestJson, const std::string& responseJson) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "INSERT INTO saved_trips(user_id, title, request_json, response_json) VALUES (?, ?, ?, ?);");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    bindText(stmt.get(), 2, title);
    bindText(stmt.get(), 3, requestJson);
    bindText(stmt.get(), 4, responseJson);
    if (sqlite3_step(stmt.get()) == SQLITE_DONE) {
        recordWrite(true);
        return sqlite3_last_insert_rowid(db_);
    }
    recordWrite(false);
    return 0;
}

bool SQLiteStore::updateTrip(int64_t tripId, int64_t userId, const std::string& title, const std::string& requestJson, const std::string& responseJson) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "UPDATE saved_trips SET response_json=?, "
                      "request_json=COALESCE(NULLIF(?, ''), request_json), "
                      "title=COALESCE(NULLIF(?, ''), title), "
                      "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                      "WHERE id=? AND user_id=?;";
    Statement stmt(db_, sql);
    bindText(stmt.get(), 1, responseJson);
    bindText(stmt.get(), 2, requestJson);
    bindText(stmt.get(), 3, title);
    sqlite3_bind_int64(stmt.get(), 4, tripId);
    sqlite3_bind_int64(stmt.get(), 5, userId);
    if (sqlite3_step(stmt.get()) == SQLITE_DONE) {
        recordWrite(true);
        return sqlite3_changes(db_) == 1;
    }
    recordWrite(false);
    return false;
}

nlohmann::json SQLiteStore::listTrips(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, title, created_at, share_id FROM saved_trips WHERE user_id = ? ORDER BY created_at DESC LIMIT 50;");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    nlohmann::json arr = nlohmann::json::array();
    while (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        nlohmann::json item = {
            {"id", sqlite3_column_int64(stmt.get(), 0)},
            {"title", safeColumnText(stmt.get(), 1)},
            {"created_at", safeColumnText(stmt.get(), 2)}
        };
        const char* shareId = safeColumnText(stmt.get(), 3);
        item["share_id"] = std::string(shareId);  // safeColumnText guarantees non-null
        arr.push_back(item);
    }
    return arr;
}

std::optional<nlohmann::json> SQLiteStore::getTrip(int64_t tripId, int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, title, request_json, response_json, share_id, created_at FROM saved_trips WHERE id = ? AND user_id = ?;");
    sqlite3_bind_int64(stmt.get(), 1, tripId);
    sqlite3_bind_int64(stmt.get(), 2, userId);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        nlohmann::json item = {
            {"id", sqlite3_column_int64(stmt.get(), 0)},
            {"title", safeColumnText(stmt.get(), 1)},
            {"request_json", safeColumnText(stmt.get(), 2)},
            {"response_json", safeColumnText(stmt.get(), 3)},
            {"created_at", safeColumnText(stmt.get(), 5)}
        };
        const char* shareId = safeColumnText(stmt.get(), 4);
        item["share_id"] = shareId ? std::string(shareId) : "";
        return item;
    }
    return std::nullopt;
}

std::string SQLiteStore::generateShareId(int64_t tripId) {
    std::lock_guard<std::mutex> lock(mutex_);
    // Check if share_id already exists
    {
        Statement checkStmt(db_, "SELECT share_id FROM saved_trips WHERE id = ?;");
        sqlite3_bind_int64(checkStmt.get(), 1, tripId);
        if (sqlite3_step(checkStmt.get()) == SQLITE_ROW) {
            std::string existing = safeColumnText(checkStmt.get(), 0);
            if (!existing.empty()) return existing;
        }
    }

    // Use cryptographically secure randomHex from auth module (6 bytes = 12 hex chars)
    std::string shareId = randomHex(6);

    Statement stmt(db_, "UPDATE saved_trips SET share_id = ? WHERE id = ? AND share_id IS NULL;");
    bindText(stmt.get(), 1, shareId);
    sqlite3_bind_int64(stmt.get(), 2, tripId);
    if (sqlite3_step(stmt.get()) != SQLITE_DONE || sqlite3_changes(db_) == 0) {
        // Race condition: another thread set share_id; fetch the real one
        Statement retryStmt(db_, "SELECT share_id FROM saved_trips WHERE id = ?;");
        sqlite3_bind_int64(retryStmt.get(), 1, tripId);
        if (sqlite3_step(retryStmt.get()) == SQLITE_ROW) {
            std::string actual = safeColumnText(retryStmt.get(), 0);
            if (!actual.empty()) return actual;
        }
    }
    return shareId;
}

std::optional<nlohmann::json> SQLiteStore::getTripByShareId(const std::string& shareId) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT id, title, request_json, response_json, created_at FROM saved_trips WHERE share_id = ?;");
    bindText(stmt.get(), 1, shareId);
    if (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        return nlohmann::json{
            {"id", sqlite3_column_int64(stmt.get(), 0)},
            {"title", safeColumnText(stmt.get(), 1)},
            {"request_json", safeColumnText(stmt.get(), 2)},
            {"response_json", safeColumnText(stmt.get(), 3)},
            {"created_at", safeColumnText(stmt.get(), 4)}
        };
    }
    return std::nullopt;
}

// ---- Feedback ----

void SQLiteStore::submitFeedback(int64_t userId, const std::string& category, const std::string& content,
                                  const std::string& contact, const std::string& pageUrl, const std::string& userAgent) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "INSERT INTO feedback(user_id, category, content, contact, page_url, user_agent) VALUES (?, ?, ?, ?, ?, ?);");
    sqlite3_bind_int64(stmt.get(), 1, userId);
    bindText(stmt.get(), 2, category);
    bindText(stmt.get(), 3, content);
    bindText(stmt.get(), 4, contact);
    bindText(stmt.get(), 5, pageUrl);
    bindText(stmt.get(), 6, userAgent);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

nlohmann::json SQLiteStore::listFeedback(const std::string& status, int limit) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT f.id, f.user_id, u.username, f.category, f.content, f.contact, f.status, f.admin_reply, f.created_at "
                      "FROM feedback f LEFT JOIN users u ON f.user_id = u.id";
    if (!status.empty()) sql += " WHERE f.status = ?";
    sql += " ORDER BY f.created_at DESC LIMIT ?;";

    Statement stmt(db_, sql);
    int paramIdx = 1;
    if (!status.empty()) bindText(stmt.get(), paramIdx++, status);
    sqlite3_bind_int(stmt.get(), paramIdx, std::max(1, std::min(200, limit)));

    nlohmann::json arr = nlohmann::json::array();
    while (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        arr.push_back({
            {"id", sqlite3_column_int64(stmt.get(), 0)},
            {"user_id", sqlite3_column_int64(stmt.get(), 1)},
            {"username", safeColumnText(stmt.get(), 2)},
            {"category", safeColumnText(stmt.get(), 3)},
            {"content", safeColumnText(stmt.get(), 4)},
            {"contact", safeColumnText(stmt.get(), 5)},
            {"status", safeColumnText(stmt.get(), 6)},
            {"admin_reply", safeColumnText(stmt.get(), 7)},
            {"created_at", safeColumnText(stmt.get(), 8)}
        });
    }
    return arr;
}

void SQLiteStore::updateFeedbackStatus(int64_t feedbackId, const std::string& status, const std::string& adminReply) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "UPDATE feedback SET status = ?, admin_reply = ? WHERE id = ?;");
    bindText(stmt.get(), 1, status);
    bindText(stmt.get(), 2, adminReply);
    sqlite3_bind_int64(stmt.get(), 3, feedbackId);
    recordWrite(sqlite3_step(stmt.get()) == SQLITE_DONE);
}

// ---- Admin ----

nlohmann::json SQLiteStore::adminStats() {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json result;

    {
        Statement stmt(db_, "SELECT COUNT(*) FROM users;");
        if (sqlite3_step(stmt.get()) == SQLITE_ROW) result["total_users"] = sqlite3_column_int64(stmt.get(), 0);
    }
    {
        std::string today = todayDate();
        Statement stmt(db_, "SELECT COUNT(DISTINCT user_id) FROM query_usage WHERE query_date = ?;");
        bindText(stmt.get(), 1, today);
        if (sqlite3_step(stmt.get()) == SQLITE_ROW) result["today_active_users"] = sqlite3_column_int64(stmt.get(), 0);
    }
    {
        Statement stmt(db_, "SELECT COUNT(*) FROM planning_requests;");
        if (sqlite3_step(stmt.get()) == SQLITE_ROW) result["total_queries"] = sqlite3_column_int64(stmt.get(), 0);
    }
    {
        Statement stmt(db_, "SELECT COUNT(*) FROM feedback WHERE status = 'pending';");
        if (sqlite3_step(stmt.get()) == SQLITE_ROW) result["pending_feedback"] = sqlite3_column_int64(stmt.get(), 0);
    }
    return result;
}

nlohmann::json SQLiteStore::listUsers(int limit) {
    std::lock_guard<std::mutex> lock(mutex_);
    Statement stmt(db_, "SELECT u.id, u.username, u.role, u.created_at, "
                        "COALESCE((SELECT SUM(query_count) FROM query_usage WHERE user_id = u.id), 0) as total_queries "
                        "FROM users u ORDER BY u.created_at DESC LIMIT ?;");
    sqlite3_bind_int(stmt.get(), 1, std::max(1, std::min(500, limit)));

    nlohmann::json arr = nlohmann::json::array();
    while (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        arr.push_back({
            {"id", sqlite3_column_int64(stmt.get(), 0)},
            {"username", safeColumnText(stmt.get(), 1)},
            {"role", safeColumnText(stmt.get(), 2)},
            {"created_at", safeColumnText(stmt.get(), 3)},
            {"total_queries", sqlite3_column_int64(stmt.get(), 4)}
        });
    }
    return arr;
}

nlohmann::json SQLiteStore::queryStatsByDay(int days) {
    std::lock_guard<std::mutex> lock(mutex_);
    int boundedDays = std::max(1, std::min(90, days));
    Statement stmt(db_, "SELECT query_date, SUM(query_count) as total, COUNT(DISTINCT user_id) as users "
                        "FROM query_usage WHERE query_date >= date('now', ?) "
                        "GROUP BY query_date ORDER BY query_date;");
    std::string param = "-" + std::to_string(boundedDays) + " days";
    bindText(stmt.get(), 1, param);

    nlohmann::json arr = nlohmann::json::array();
    while (sqlite3_step(stmt.get()) == SQLITE_ROW) {
        arr.push_back({
            {"date", safeColumnText(stmt.get(), 0)},
            {"total_queries", sqlite3_column_int64(stmt.get(), 1)},
            {"active_users", sqlite3_column_int64(stmt.get(), 2)}
        });
    }
    return arr;
}

void SQLiteStore::cleanupExpiredGuests(int daysRetention) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string interval = "-" + std::to_string(daysRetention) + " days";
    try {
        // Use parameterized queries to prevent SQL injection
        const char* cleanupTables[] = {"saved_trips", "easter_egg_log", "query_usage", "feedback"};
        for (const char* table : cleanupTables) {
            std::string sql = std::string("DELETE FROM ") + table +
                " WHERE user_id IN (SELECT id FROM users WHERE role = 'guest' AND created_at < datetime('now', ?));";
            Statement stmt(db_, sql);
            bindText(stmt.get(), 1, interval);
            sqlite3_step(stmt.get());
        }
        {
            Statement stmt(db_, "DELETE FROM users WHERE role = 'guest' AND created_at < datetime('now', ?);");
            bindText(stmt.get(), 1, interval);
            sqlite3_step(stmt.get());
        }
    } catch (const std::exception& ex) {
        std::cerr << "cleanupExpiredGuests failed: " << ex.what() << std::endl;
    }
}

}  // namespace tourpass
