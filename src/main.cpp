#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <unordered_map>

#ifdef _WIN32
#include <direct.h>
#define getcwd _getcwd
#else
#include <unistd.h>
#endif

#include "tourpass/api.h"
#include "tourpass/auth.h"
#include "tourpass/data_loader.h"
#include "tourpass/sqlite_store.h"
#include "tourpass/travel_time_provider.h"

#ifdef TOURPASS_HAS_POSTGRES
#include "tourpass/pg_store.h"
#endif

namespace {

std::string currentWorkingDir() {
    char buf[1024];
    if (getcwd(buf, sizeof(buf))) return std::string(buf);
    return ".";
}

std::string resolveRelativePath(const std::string& path) {
    if (path.empty() || path[0] == '/' || (path.size() >= 2 && path[1] == ':')) {
        return path;
    }
    return currentWorkingDir() + "/" + path;
}

}  // namespace

int main() {
    try {
        // ---- Load all available cities ----
        std::unordered_map<std::string, std::unique_ptr<tourpass::CityBundle>> cities;

        // Directory name -> display name mapping
        struct CityEntry { std::string dir; std::string name; };
        std::vector<CityEntry> cityList = {
            {"changsha", "闀挎矙"}, {"wuhan", "姝︽眽"}, {"dali", "澶х悊"},
            {"lijiang", "涓芥睙"}, {"nanjing", "鍗椾含"}, {"suzhou", "鑻忓窞"},
            {"chengdu", "鎴愰兘"}, {"chongqing", "閲嶅簡"}, {"xian", "瑗垮畨"},
            {"hangzhou", "鏉窞"}, {"beijing", "鍖椾含"},
            {"shanghai", "涓婃捣"}, {"guangzhou", "骞垮窞"}, {"shenzhen", "娣卞湷"},
            {"xiamen", "鍘﹂棬"}, {"qingdao", "闈掑矝"},
            {"guilin", "妗傛灄"}, {"sanya", "涓変簹"}, {"harbin", "鍝堝皵婊?},
            {"kunming", "鏄嗘槑"}, {"zhangjiajie", "寮犲鐣?}
        };

        for (const auto& entry : cityList) {
            std::string poisPath, edgesPath;

            // Root data files serve as changsha (legacy)
            if (entry.dir == "changsha") {
                poisPath = "data/pois.json";
                edgesPath = "data/edges.json";
            } else {
                poisPath = "data/" + entry.dir + "/pois.json";
                edgesPath = "data/" + entry.dir + "/edges.json";
            }

            if (!std::filesystem::exists(poisPath) || !std::filesystem::exists(edgesPath)) {
                continue;
            }
            try {
                auto data = tourpass::loadDataSet(poisPath, edgesPath);
                std::cout << "Loaded city " << entry.name << ": " << data.pois.size() << " POIs" << std::endl;
                cities[entry.name] = std::make_unique<tourpass::CityBundle>(std::move(data.pois), std::move(data.edges));
            } catch (const std::exception& ex) {
                std::cerr << "Warning: failed to load " << entry.name << ": " << ex.what() << std::endl;
            }
        }

        if (cities.empty()) {
            std::cerr << "No city data found. Exiting." << std::endl;
            return 1;
        }
        std::cout << "Total cities loaded: " << cities.size() << std::endl;

        // ---- LLM ----
        tourpass::LlmClient llm;

        try {
            static_cast<void>(tourpass::jwtSecret());
        } catch (const std::exception& ex) {
            std::cerr << ex.what() << std::endl;
            std::cerr << "Set TOURPASS_JWT_SECRET environment variable." << std::endl;
            return 1;
        }

        // ---- Config ----
        tourpass::RuntimeConfig config = tourpass::runtimeConfigFromEnv();
        config.dbPath = resolveRelativePath(config.dbPath);

        // ---- Database ----
        std::unique_ptr<tourpass::DataStore> store;
        const char* databaseUrl = std::getenv("DATABASE_URL");
#ifdef TOURPASS_HAS_POSTGRES
        if (databaseUrl && *databaseUrl) {
            std::cout << "Using PostgreSQL backend" << std::endl;
            auto pg = std::make_unique<tourpass::PostgresStore>(databaseUrl);
            if (pg->enabled()) {
                store = std::move(pg);
            } else {
                std::cerr << "PostgreSQL connection failed, falling back to SQLite" << std::endl;
            }
        }
#endif
        if (!store && config.dbEnabled) {
            std::cout << "Using SQLite backend: " << config.dbPath << std::endl;
            store = std::make_unique<tourpass::SQLiteStore>(config.dbPath);
        }

        if (store && store->enabled()) {
            std::cout << "Cleaning up expired guest accounts (7 days)..." << std::endl;
            store->cleanupExpiredGuests(7);
        }

        // ---- Server ----
        int port = 8080;
        if (const char* envPort = std::getenv("PORT")) {
            try {
                port = std::stoi(envPort);
                if (port <= 0 || port > 65535) port = 8080;
            } catch (...) {
                port = 8080;
            }
        }
        std::string host = "127.0.0.1";
        if (const char* envHost = std::getenv("TOURPASS_HOST")) {
            if (*envHost) host = envHost;
        } else if (const char* hostEnv = std::getenv("HOST")) {
            if (*hostEnv) host = hostEnv;
        }

        std::string envDefaultCity;
        if (const char* envCity = std::getenv("TOURPASS_DEFAULT_CITY")) {
            envDefaultCity = envCity;
        }

        std::string defaultCity = envDefaultCity;
        if (defaultCity.empty()) {
            // No env override 鈥?pick first loaded city from list order
            for (const auto& entry : cityList) {
                if (cities.count(entry.name)) {
                    defaultCity = entry.name;
                    break;
                }
            }
            if (!defaultCity.empty()) {
                std::cout << "Note: TOURPASS_DEFAULT_CITY not set, using first available city: "
                          << defaultCity << std::endl;
            }
        }

        // cityList order already handled above; no fallback needed for unordered_map

        if (!defaultCity.empty()) {
            std::cout << "Default city: " << defaultCity << std::endl;
        }

        return tourpass::runServer(std::move(cities), defaultCity, llm, host, port, config, store.get());
    } catch (const std::exception& ex) {
        std::cerr << "startup failed: " << ex.what() << std::endl;
        return 1;
    }
}

