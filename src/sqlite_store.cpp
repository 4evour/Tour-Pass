#include "tourpass/sqlite_store.h"

#include <filesystem>
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
            {"id", reinterpret_cast<const char*>(sqlite3_column_text(stmt.get(), 0))},
            {"status", reinterpret_cast<const char*>(sqlite3_column_text(stmt.get(), 1))},
            {"queue_wait_ms", sqlite3_column_int64(stmt.get(), 2)},
            {"execution_ms", sqlite3_column_int64(stmt.get(), 3)},
            {"created_at", reinterpret_cast<const char*>(sqlite3_column_text(stmt.get(), 4))},
            {"updated_at", reinterpret_cast<const char*>(sqlite3_column_text(stmt.get(), 5))}
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

}  // namespace tourpass
