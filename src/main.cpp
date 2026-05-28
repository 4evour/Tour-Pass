#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>

#ifdef _WIN32
#include <direct.h>
#define getcwd _getcwd
#else
#include <unistd.h>
#endif

#include "tourpass/api.h"
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
        return path; // already absolute
    }
    return currentWorkingDir() + "/" + path;
}

std::string fileHash(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    std::ostringstream buffer;
    buffer << input.rdbuf();
    std::hash<std::string> hasher;
    std::ostringstream out;
    out << std::hex << hasher(buffer.str());
    return out.str();
}

}  // namespace

int main() {
    try {
        const char* cityEnv = std::getenv("TOURPASS_CITY");
        std::string city = cityEnv && *cityEnv ? cityEnv : "";

        const char* poiPathEnv = std::getenv("TOURPASS_POIS_PATH");
        const char* edgePathEnv = std::getenv("TOURPASS_EDGES_PATH");

        std::string poiPath;
        std::string edgePath;
        if (poiPathEnv && *poiPathEnv) {
            poiPath = poiPathEnv;
        } else if (!city.empty()) {
            poiPath = "data/" + city + "/pois.json";
        } else {
            poiPath = "data/pois.json";
        }
        if (edgePathEnv && *edgePathEnv) {
            edgePath = edgePathEnv;
        } else if (!city.empty()) {
            edgePath = "data/" + city + "/edges.json";
        } else {
            edgePath = "data/edges.json";
        }
        tourpass::DataSet data = tourpass::loadDataSet(poiPath, edgePath);
        tourpass::PoiGraph graph(data.pois, data.edges);
        auto travelProvider = tourpass::createTravelTimeProvider(graph);
        tourpass::TripPlanner planner(graph);
        tourpass::SearchEngine search(graph);
        tourpass::LlmClient llm;
        // Resolve relative paths to absolute at startup (prevents DB loss on CWD change)
        poiPath = resolveRelativePath(poiPath);
        edgePath = resolveRelativePath(edgePath);

        tourpass::RuntimeConfig config = tourpass::runtimeConfigFromEnv();
        config.travelProviderName = travelProvider->name();
        config.dbPath = resolveRelativePath(config.dbPath);

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
        if (store) {
            store->recordDataVersion(graph.pois().size(), graph.edgeCount(), fileHash(poiPath), fileHash(edgePath));
        }

        int port = 8080;
        if (const char* envPort = std::getenv("PORT")) {
            port = std::atoi(envPort);
            if (port <= 0) port = 8080;
        }
        std::string host = "127.0.0.1";
        if (const char* envHost = std::getenv("TOURPASS_HOST")) {
            if (*envHost) host = envHost;
        } else if (const char* hostEnv = std::getenv("HOST")) {
            if (*hostEnv) host = hostEnv;
        }
        return tourpass::runServer(graph, planner, search, llm, host, port, config, store.get());
    } catch (const std::exception& ex) {
        std::cerr << "startup failed: " << ex.what() << std::endl;
        return 1;
    }
}
