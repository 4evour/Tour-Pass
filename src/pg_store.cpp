#include "tourpass/pg_store.h"

#include <cstring>
#include <iostream>
#include <sstream>

#include <libpq-fe.h>

#include "tourpass/auth.h"

namespace tourpass {

namespace {

std::string esc(PGconn* conn, const std::string& value) {
    std::string buf(value.size() * 2 + 1, '\0');
    int err = 0;
    PQescapeStringConn(conn, buf.data(), value.c_str(), value.size(), &err);
    buf.resize(std::strlen(buf.data()));
    return buf;
}

int64_t queryInt64(PGconn* conn, const std::string& sql) {
    PGresult* res = PQexec(conn, sql.c_str());
    int64_t val = 0;
    if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0 && PQgetisnull(res, 0, 0) == 0) {
        val = std::stoll(PQgetvalue(res, 0, 0));
    }
    PQclear(res);
    return val;
}

std::string queryString(PGconn* conn, const std::string& sql) {
    PGresult* res = PQexec(conn, sql.c_str());
    std::string val;
    if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0 && PQgetisnull(res, 0, 0) == 0) {
        val = PQgetvalue(res, 0, 0);
    }
    PQclear(res);
    return val;
}

std::optional<UserRecord> extractUser(PGresult* res) {
    if (PQresultStatus(res) != PGRES_TUPLES_OK || PQntuples(res) == 0) return std::nullopt;
    UserRecord u;
    u.id = std::stoll(PQgetvalue(res, 0, 0));
    u.username = PQgetvalue(res, 0, 1);
    u.email = PQgetisnull(res, 0, 2) ? "" : PQgetvalue(res, 0, 2);
    u.passwordHash = PQgetvalue(res, 0, 3);
    u.role = PQgetvalue(res, 0, 4);
    u.bonusQueries = std::stoi(PQgetvalue(res, 0, 5));
    u.createdAt = PQgetisnull(res, 0, 6) ? "" : PQgetvalue(res, 0, 6);
    return u;
}

}  // namespace

PostgresStore::PostgresStore(const std::string& connStr) : connStr_(connStr) {
    open();
    if (conn_) initializeSchema();
}

PostgresStore::~PostgresStore() {
    if (conn_) PQfinish(conn_);
}

void PostgresStore::open() {
    conn_ = PQconnectdb(connStr_.c_str());
    if (PQstatus(conn_) != CONNECTION_OK) {
        std::cerr << "PostgreSQL connection failed: " << PQerrorMessage(conn_) << std::endl;
        PQfinish(conn_);
        conn_ = nullptr;
    }
}

void PostgresStore::exec(const std::string& sql) {
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) != PGRES_COMMAND_OK && PQresultStatus(res) != PGRES_TUPLES_OK) {
        std::cerr << "PostgreSQL exec error: " << PQresultErrorMessage(res) << " [SQL: " << sql.substr(0, 120) << "]" << std::endl;
        writeFailures_++;
    } else {
        writeCount_++;
    }
    PQclear(res);
}

std::string PostgresStore::queryScalar(const std::string& sql) const {
    PGresult* res = PQexec(conn_, sql.c_str());
    std::string val;
    if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0 && PQgetisnull(res, 0, 0) == 0) {
        val = PQgetvalue(res, 0, 0);
    }
    PQclear(res);
    return val;
}

void PostgresStore::initializeSchema() {
    exec(R"(
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (NOW()::text)
        );
    )");

    // Check current version
    int currentVersion = 0;
    {
        PGresult* res = PQexec(conn_, "SELECT MAX(version) FROM schema_migrations;");
        if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0 && PQgetisnull(res, 0, 0) == 0) {
            currentVersion = std::stoi(PQgetvalue(res, 0, 0));
        }
        PQclear(res);
    }

    if (currentVersion < 1) {
        exec(R"(
            CREATE TABLE IF NOT EXISTS planning_requests (
                id BIGSERIAL PRIMARY KEY,
                request_id TEXT NOT NULL,
                route TEXT NOT NULL,
                cache_status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                response_status INTEGER NOT NULL,
                latency_ms INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS trip_jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                error TEXT NOT NULL,
                queue_wait_ms BIGINT NOT NULL,
                execution_ms BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id BIGSERIAL PRIMARY KEY,
                started_at TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                concurrency_steps_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                report_path TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS data_versions (
                id BIGSERIAL PRIMARY KEY,
                poi_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL,
                pois_hash TEXT NOT NULL,
                edges_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        )");
        exec("INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;");
    }

    if (currentVersion < 2) {
        exec(R"(
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                bonus_queries INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS query_usage (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                query_date TEXT NOT NULL,
                query_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, query_date)
            );
            CREATE TABLE IF NOT EXISTS easter_egg_log (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                claimed_date TEXT NOT NULL,
                UNIQUE(user_id, claimed_date)
            );
            CREATE TABLE IF NOT EXISTS saved_trips (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL DEFAULT '',
                request_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                share_id TEXT UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                category TEXT NOT NULL DEFAULT 'other',
                content TEXT NOT NULL,
                contact TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                admin_reply TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        )");
        exec("INSERT INTO schema_migrations(version) VALUES (2) ON CONFLICT DO NOTHING;");
    }

    if (currentVersion < 3) {
        exec(R"(
            CREATE TABLE IF NOT EXISTS verification_codes (
                id BIGSERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT 'register',
                expires_at TIMESTAMPTZ NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        )");
        // Add email column if missing
        exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT '';");
        exec("INSERT INTO schema_migrations(version) VALUES (3) ON CONFLICT DO NOTHING;");
    }

    if (currentVersion < 4) {
        exec(R"(
            CREATE TABLE IF NOT EXISTS guest_creation_log (
                id BIGSERIAL PRIMARY KEY,
                ip TEXT NOT NULL,
                created_date TEXT NOT NULL,
                UNIQUE(ip, created_date)
            );
        )");
        exec("INSERT INTO schema_migrations(version) VALUES (4) ON CONFLICT DO NOTHING;");
    }
    // Schema v5: guest device binding
    if (!queryScalar("SELECT 1 FROM schema_migrations WHERE version = 5;").empty()) {
        // already migrated
    } else {
        try { exec("ALTER TABLE users ADD COLUMN device_id TEXT NOT NULL DEFAULT '';"); } catch (...) {}
        try { exec("CREATE INDEX idx_users_device_id ON users(device_id);"); } catch (...) {}
        exec("INSERT INTO schema_migrations(version) VALUES (5) ON CONFLICT DO NOTHING;");
    }
}

// ---- Recording ----

void PostgresStore::recordDataVersion(size_t poiCount, size_t edgeCount, const std::string& poisHash, const std::string& edgesHash) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO data_versions(poi_count, edge_count, pois_hash, edges_hash) VALUES ("
        << poiCount << ", " << edgeCount << ", '" << esc(conn_, poisHash) << "', '" << esc(conn_, edgesHash) << "');";
    exec(sql.str());
}

void PostgresStore::recordPlanningRequest(const std::string& requestId, const std::string& route, const std::string& cacheStatus, const std::string& requestJson, int responseStatus, int64_t latencyMs) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO planning_requests(request_id, route, cache_status, request_json, response_status, latency_ms) VALUES ('"
        << esc(conn_, requestId) << "', '" << esc(conn_, route) << "', '" << esc(conn_, cacheStatus) << "', '"
        << esc(conn_, requestJson) << "', " << responseStatus << ", " << latencyMs << ");";
    exec(sql.str());
}

void PostgresStore::recordTripJob(const std::string& id, const std::string& status, const std::string& requestJson, const std::string& resultJson, const std::string& error, int64_t queueWaitMs, int64_t executionMs) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO trip_jobs(id, status, request_json, result_json, error, queue_wait_ms, execution_ms) VALUES ('"
        << esc(conn_, id) << "', '" << esc(conn_, status) << "', '" << esc(conn_, requestJson) << "', '"
        << esc(conn_, resultJson) << "', '" << esc(conn_, error) << "', " << queueWaitMs << ", " << executionMs
        << ") ON CONFLICT(id) DO UPDATE SET status=EXCLUDED.status, request_json=EXCLUDED.request_json, result_json=EXCLUDED.result_json, error=EXCLUDED.error, queue_wait_ms=EXCLUDED.queue_wait_ms, execution_ms=EXCLUDED.execution_ms, updated_at=NOW();";
    exec(sql.str());
}

void PostgresStore::recordBenchmarkRun(const std::string& startedAt, int durationSeconds, const std::string& concurrencyStepsJson, const std::string& summaryJson, const std::string& reportPath) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO benchmark_runs(started_at, duration_seconds, concurrency_steps_json, summary_json, report_path) VALUES ('"
        << esc(conn_, startedAt) << "', " << durationSeconds << ", '" << esc(conn_, concurrencyStepsJson) << "', '"
        << esc(conn_, summaryJson) << "', '" << esc(conn_, reportPath) << "');";
    exec(sql.str());
}

nlohmann::json PostgresStore::recentJobs(int limit) const {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json arr = nlohmann::json::array();
    std::string sql = "SELECT id, status, queue_wait_ms, execution_ms, created_at::text, updated_at::text FROM trip_jobs ORDER BY updated_at DESC LIMIT " + std::to_string(limit) + ";";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) == PGRES_TUPLES_OK) {
        for (int i = 0; i < PQntuples(res); i++) {
            arr.push_back({
                {"id", PQgetvalue(res, i, 0)},
                {"status", PQgetvalue(res, i, 1)},
                {"queue_wait_ms", std::stoll(PQgetvalue(res, i, 2))},
                {"execution_ms", std::stoll(PQgetvalue(res, i, 3))},
                {"created_at", PQgetvalue(res, i, 4)},
                {"updated_at", PQgetvalue(res, i, 5)}
            });
        }
    }
    PQclear(res);
    return arr;
}

nlohmann::json PostgresStore::stats() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return {
        {"enabled", conn_ != nullptr},
        {"backend", "postgresql"},
        {"write_count", writeCount_},
        {"write_failures", writeFailures_}
    };
}

// ---- Auth ----

int64_t PostgresStore::createUser(const std::string& username, const std::string& passwordHash, const std::string& role, const std::string& email, const std::string& deviceId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO users(username, password_hash, role, email, device_id) VALUES ('"
        << esc(conn_, username) << "', '" << esc(conn_, passwordHash) << "', '" << esc(conn_, role) << "', '"
        << esc(conn_, email) << "', '" << esc(conn_, deviceId) << "') RETURNING id;";
    PGresult* res = PQexec(conn_, sql.str().c_str());
    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        std::string err = PQresultErrorMessage(res);
        PQclear(res);
        if (err.find("unique") != std::string::npos || err.find("duplicate") != std::string::npos) {
            throw std::runtime_error("USERNAME_TAKEN");
        }
        throw std::runtime_error("createUser failed: " + err);
    }
    int64_t id = std::stoll(PQgetvalue(res, 0, 0));
    PQclear(res);
    return id;
}

std::optional<UserRecord> PostgresStore::findUserByUsername(const std::string& username) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at::text FROM users WHERE username = '" + esc(conn_, username) + "';";
    PGresult* res = PQexec(conn_, sql.c_str());
    auto user = extractUser(res);
    PQclear(res);
    return user;
}

std::optional<UserRecord> PostgresStore::findUserByEmail(const std::string& email) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at::text FROM users WHERE email = '" + esc(conn_, email) + "';";
    PGresult* res = PQexec(conn_, sql.c_str());
    auto user = extractUser(res);
    PQclear(res);
    return user;
}

std::optional<UserRecord> PostgresStore::findUserById(int64_t id) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at::text FROM users WHERE id = " + std::to_string(id) + ";";
    PGresult* res = PQexec(conn_, sql.c_str());
    auto user = extractUser(res);
    PQclear(res);
    return user;
}

std::optional<UserRecord> PostgresStore::findUserByDeviceId(const std::string& deviceId) {
    if (deviceId.empty()) return std::nullopt;
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id, username, COALESCE(email,''), password_hash, role, bonus_queries, created_at::text FROM users WHERE device_id = '" + esc(conn_, deviceId) + "' AND role = 'guest' ORDER BY created_at DESC LIMIT 1;";
    PGresult* res = PQexec(conn_, sql.c_str());
    auto user = extractUser(res);
    PQclear(res);
    return user;
}

void PostgresStore::updatePassword(int64_t userId, const std::string& newHash) {
    std::lock_guard<std::mutex> lock(mutex_);
    exec("UPDATE users SET password_hash = '" + esc(conn_, newHash) + "' WHERE id = " + std::to_string(userId) + ";");
}

void PostgresStore::updateRole(int64_t userId, const std::string& role) {
    std::lock_guard<std::mutex> lock(mutex_);
    exec("UPDATE users SET role = '" + esc(conn_, role) + "' WHERE id = " + std::to_string(userId) + ";");
}

// ---- Email verification ----

void PostgresStore::storeVerificationCode(const std::string& email, const std::string& code, const std::string& purpose, int ttlSeconds) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO verification_codes(email, code, purpose, expires_at) VALUES ('"
        << esc(conn_, email) << "', '" << esc(conn_, code) << "', '" << esc(conn_, purpose)
        << "', NOW() + INTERVAL '" << ttlSeconds << " seconds');";
    exec(sql.str());
}

std::optional<std::string> PostgresStore::getValidVerificationCode(const std::string& email, const std::string& code, const std::string& purpose) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id::text FROM verification_codes WHERE email = '" + esc(conn_, email) + "' AND code = '" + esc(conn_, code) + "' AND purpose = '" + esc(conn_, purpose) + "' AND used = 0 AND expires_at > NOW() ORDER BY created_at DESC LIMIT 1;";
    PGresult* res = PQexec(conn_, sql.c_str());
    std::optional<std::string> result;
    if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0) {
        result = PQgetvalue(res, 0, 0);
    }
    PQclear(res);
    return result;
}

void PostgresStore::markCodeUsed(int64_t codeId) {
    std::lock_guard<std::mutex> lock(mutex_);
    exec("UPDATE verification_codes SET used = 1 WHERE id = " + std::to_string(codeId) + ";");
}

// ---- Query usage ----

int PostgresStore::getQueryCount(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = queryScalar("SELECT CURRENT_DATE::text;");
    std::string sql = "SELECT COALESCE(query_count, 0)::text FROM query_usage WHERE user_id = " + std::to_string(userId) + " AND query_date = '" + esc(conn_, today) + "';";
    std::string val = queryScalar(sql);
    return val.empty() ? 0 : std::stoi(val);
}

int PostgresStore::getBonusQueries(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string val = queryScalar("SELECT COALESCE(bonus_queries, 0)::text FROM users WHERE id = " + std::to_string(userId) + ";");
    return val.empty() ? 0 : std::stoi(val);
}

void PostgresStore::incrementQueryCount(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = queryScalar("SELECT CURRENT_DATE::text;");
    std::ostringstream sql;
    sql << "INSERT INTO query_usage(user_id, query_date, query_count) VALUES (" << userId << ", '" << esc(conn_, today) << "', 1) "
        << "ON CONFLICT(user_id, query_date) DO UPDATE SET query_count = query_usage.query_count + 1;";
    exec(sql.str());
}

void PostgresStore::addBonusQueries(int64_t userId, int amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    exec("UPDATE users SET bonus_queries = bonus_queries + " + std::to_string(amount) + " WHERE id = " + std::to_string(userId) + ";");
}

bool PostgresStore::hasEasterEggToday(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = queryScalar("SELECT CURRENT_DATE::text;");
    std::string sql = "SELECT 1 FROM easter_egg_log WHERE user_id = " + std::to_string(userId) + " AND claimed_date = '" + esc(conn_, today) + "';";
    PGresult* res = PQexec(conn_, sql.c_str());
    bool found = (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0);
    PQclear(res);
    return found;
}

void PostgresStore::recordEasterEgg(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string today = queryScalar("SELECT CURRENT_DATE::text;");
    exec("INSERT INTO easter_egg_log(user_id, claimed_date) VALUES (" + std::to_string(userId) + ", '" + esc(conn_, today) + "') ON CONFLICT DO NOTHING;");
}

// ---- Saved trips ----

void PostgresStore::saveTrip(int64_t userId, const std::string& title, const std::string& requestJson, const std::string& responseJson) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO saved_trips(user_id, title, request_json, response_json) VALUES ("
        << userId << ", '" << esc(conn_, title) << "', '" << esc(conn_, requestJson) << "', '" << esc(conn_, responseJson) << "');";
    exec(sql.str());
}

nlohmann::json PostgresStore::listTrips(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json arr = nlohmann::json::array();
    std::string sql = "SELECT id::text, title, created_at::text, COALESCE(share_id, '') FROM saved_trips WHERE user_id = " + std::to_string(userId) + " ORDER BY created_at DESC LIMIT 50;";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) == PGRES_TUPLES_OK) {
        for (int i = 0; i < PQntuples(res); i++) {
            nlohmann::json item = {{"id", std::stoll(PQgetvalue(res, i, 0))}, {"title", PQgetvalue(res, i, 1)}, {"created_at", PQgetvalue(res, i, 2)}};
            std::string shareId = PQgetvalue(res, i, 3);
            if (!shareId.empty()) item["share_id"] = shareId;
            arr.push_back(item);
        }
    }
    PQclear(res);
    return arr;
}

std::optional<nlohmann::json> PostgresStore::getTrip(int64_t tripId, int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id::text, title, request_json, response_json, COALESCE(share_id, ''), created_at::text FROM saved_trips WHERE id = " + std::to_string(tripId) + " AND user_id = " + std::to_string(userId) + ";";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) != PGRES_TUPLES_OK || PQntuples(res) == 0) { PQclear(res); return std::nullopt; }
    nlohmann::json item = {{"id", std::stoll(PQgetvalue(res, 0, 0))}, {"title", PQgetvalue(res, 0, 1)}, {"request_json", PQgetvalue(res, 0, 2)}, {"response_json", PQgetvalue(res, 0, 3)}, {"created_at", PQgetvalue(res, 0, 5)}};
    std::string shareId = PQgetvalue(res, 0, 4);
    if (!shareId.empty()) item["share_id"] = shareId;
    PQclear(res);
    return item;
}

std::string PostgresStore::generateShareId(int64_t tripId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string shareId = randomHex(6);
    exec("UPDATE saved_trips SET share_id = '" + esc(conn_, shareId) + "' WHERE id = " + std::to_string(tripId) + " AND share_id IS NULL;");
    return shareId;
}

std::optional<nlohmann::json> PostgresStore::getTripByShareId(const std::string& shareId) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string sql = "SELECT id::text, title, request_json, response_json, created_at::text FROM saved_trips WHERE share_id = '" + esc(conn_, shareId) + "';";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) != PGRES_TUPLES_OK || PQntuples(res) == 0) { PQclear(res); return std::nullopt; }
    nlohmann::json item = {{"id", std::stoll(PQgetvalue(res, 0, 0))}, {"title", PQgetvalue(res, 0, 1)}, {"request_json", PQgetvalue(res, 0, 2)}, {"response_json", PQgetvalue(res, 0, 3)}, {"created_at", PQgetvalue(res, 0, 4)}};
    PQclear(res);
    return item;
}

// ---- Feedback ----

void PostgresStore::submitFeedback(int64_t userId, const std::string& category, const std::string& content, const std::string& contact, const std::string& pageUrl, const std::string& userAgent) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream sql;
    sql << "INSERT INTO feedback(user_id, category, content, contact, page_url, user_agent) VALUES ("
        << userId << ", '" << esc(conn_, category) << "', '" << esc(conn_, content) << "', '"
        << esc(conn_, contact) << "', '" << esc(conn_, pageUrl) << "', '" << esc(conn_, userAgent) << "');";
    exec(sql.str());
}

nlohmann::json PostgresStore::listFeedback(const std::string& status, int limit) {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json arr = nlohmann::json::array();
    std::string sql = "SELECT f.id::text, f.user_id::text, COALESCE(u.username, ''), f.category, f.content, f.contact, f.status, f.admin_reply, f.created_at::text FROM feedback f LEFT JOIN users u ON f.user_id = u.id";
    if (!status.empty()) sql += " WHERE f.status = '" + esc(conn_, status) + "'";
    sql += " ORDER BY f.created_at DESC LIMIT " + std::to_string(limit) + ";";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) == PGRES_TUPLES_OK) {
        for (int i = 0; i < PQntuples(res); i++) {
            arr.push_back({{"id", std::stoll(PQgetvalue(res, i, 0))}, {"user_id", std::stoll(PQgetvalue(res, i, 1))}, {"username", PQgetvalue(res, i, 2)}, {"category", PQgetvalue(res, i, 3)}, {"content", PQgetvalue(res, i, 4)}, {"contact", PQgetvalue(res, i, 5)}, {"status", PQgetvalue(res, i, 6)}, {"admin_reply", PQgetvalue(res, i, 7)}, {"created_at", PQgetvalue(res, i, 8)}});
        }
    }
    PQclear(res);
    return arr;
}

void PostgresStore::updateFeedbackStatus(int64_t feedbackId, const std::string& status, const std::string& adminReply) {
    std::lock_guard<std::mutex> lock(mutex_);
    exec("UPDATE feedback SET status = '" + esc(conn_, status) + "', admin_reply = '" + esc(conn_, adminReply) + "' WHERE id = " + std::to_string(feedbackId) + ";");
}

// ---- Admin ----

nlohmann::json PostgresStore::adminStats() {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json result;
    result["total_users"] = queryInt64(conn_, "SELECT COUNT(*) FROM users;");
    result["today_active_users"] = queryInt64(conn_, "SELECT COUNT(DISTINCT user_id) FROM query_usage WHERE query_date = CURRENT_DATE::text;");
    result["total_queries"] = queryInt64(conn_, "SELECT COUNT(*) FROM planning_requests;");
    result["pending_feedback"] = queryInt64(conn_, "SELECT COUNT(*) FROM feedback WHERE status = 'pending';");
    return result;
}

nlohmann::json PostgresStore::listUsers(int limit) {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json arr = nlohmann::json::array();
    std::string sql = "SELECT u.id::text, u.username, u.role, u.created_at::text, COALESCE((SELECT SUM(query_count) FROM query_usage WHERE user_id = u.id), 0)::text FROM users u ORDER BY u.created_at DESC LIMIT " + std::to_string(limit) + ";";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) == PGRES_TUPLES_OK) {
        for (int i = 0; i < PQntuples(res); i++) {
            arr.push_back({{"id", std::stoll(PQgetvalue(res, i, 0))}, {"username", PQgetvalue(res, i, 1)}, {"role", PQgetvalue(res, i, 2)}, {"created_at", PQgetvalue(res, i, 3)}, {"total_queries", std::stoll(PQgetvalue(res, i, 4))}});
        }
    }
    PQclear(res);
    return arr;
}

nlohmann::json PostgresStore::queryStatsByDay(int days) {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json arr = nlohmann::json::array();
    std::string sql = "SELECT query_date, SUM(query_count)::text, COUNT(DISTINCT user_id)::text FROM query_usage WHERE query_date >= (CURRENT_DATE - INTERVAL '" + std::to_string(days) + " days')::text GROUP BY query_date ORDER BY query_date;";
    PGresult* res = PQexec(conn_, sql.c_str());
    if (PQresultStatus(res) == PGRES_TUPLES_OK) {
        for (int i = 0; i < PQntuples(res); i++) {
            arr.push_back({{"query_date", PQgetvalue(res, i, 0)}, {"total", std::stoll(PQgetvalue(res, i, 1))}, {"users", std::stoi(PQgetvalue(res, i, 2))}});
        }
    }
    PQclear(res);
    return arr;
}

void PostgresStore::cleanupExpiredGuests(int daysRetention) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string cutoff = "CURRENT_TIMESTAMP - INTERVAL '" + std::to_string(daysRetention) + " days'";
    try {
        exec("DELETE FROM saved_trips WHERE user_id IN (SELECT id FROM users WHERE role = 'guest' AND created_at::timestamp < " + cutoff + ");");
        exec("DELETE FROM easter_egg_log WHERE user_id IN (SELECT id FROM users WHERE role = 'guest' AND created_at::timestamp < " + cutoff + ");");
        exec("DELETE FROM query_usage WHERE user_id IN (SELECT id FROM users WHERE role = 'guest' AND created_at::timestamp < " + cutoff + ");");
        exec("DELETE FROM feedback WHERE user_id IN (SELECT id FROM users WHERE role = 'guest' AND created_at::timestamp < " + cutoff + ");");
        exec("DELETE FROM users WHERE role = 'guest' AND created_at::timestamp < " + cutoff + ";");
    } catch (const std::exception& ex) {
        std::cerr << "cleanupExpiredGuests failed: " << ex.what() << std::endl;
    }
}

}  // namespace tourpass
