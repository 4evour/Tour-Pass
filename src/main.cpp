#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>

#include "tourpass/api.h"
#include "tourpass/data_loader.h"

namespace {

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
        const char* poiPathEnv = std::getenv("TOURPASS_POIS_PATH");
        const char* edgePathEnv = std::getenv("TOURPASS_EDGES_PATH");
        std::string poiPath = poiPathEnv && *poiPathEnv ? poiPathEnv : "data/pois.json";
        std::string edgePath = edgePathEnv && *edgePathEnv ? edgePathEnv : "data/edges.json";
        tourpass::DataSet data = tourpass::loadDataSet(poiPath, edgePath);
        tourpass::PoiGraph graph(data.pois, data.edges);
        tourpass::TripPlanner planner(graph);
        tourpass::SearchEngine search(graph);
        tourpass::LlmClient llm;
        tourpass::RuntimeConfig config = tourpass::runtimeConfigFromEnv();
        std::unique_ptr<tourpass::SQLiteStore> store;
        if (config.dbEnabled) {
            store = std::make_unique<tourpass::SQLiteStore>(config.dbPath);
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
