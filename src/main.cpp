#include <cstdlib>
#include <iostream>

#include "tourpass/api.h"
#include "tourpass/data_loader.h"

int main() {
    try {
        tourpass::DataSet data = tourpass::loadDataSet("data/pois.json", "data/edges.json");
        tourpass::PoiGraph graph(data.pois, data.edges);
        tourpass::TripPlanner planner(graph);
        tourpass::SearchEngine search(graph);
        tourpass::LlmClient llm;

        int port = 8080;
        if (const char* envPort = std::getenv("PORT")) {
            port = std::atoi(envPort);
            if (port <= 0) port = 8080;
        }
        return tourpass::runServer(graph, planner, search, llm, port);
    } catch (const std::exception& ex) {
        std::cerr << "startup failed: " << ex.what() << std::endl;
        return 1;
    }
}
