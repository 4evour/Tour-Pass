#include "tourpass/data_loader.h"

#include <fstream>
#include <iostream>
#include <queue>
#include <set>
#include <stdexcept>
#include <unordered_map>

#include "tourpass/graph.h"

namespace tourpass {

namespace {

nlohmann::json readJsonFile(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("cannot open file: " + path);
    }
    nlohmann::json json;
    input >> json;
    return json;
}

std::string requiredString(const nlohmann::json& item, const std::string& key) {
    if (!item.contains(key) || !item.at(key).is_string()) {
        throw std::runtime_error("missing string field: " + key);
    }
    return item.at(key).get<std::string>();
}

double requiredNumber(const nlohmann::json& item, const std::string& key) {
    if (!item.contains(key) || !item.at(key).is_number()) {
        throw std::runtime_error("missing number field: " + key);
    }
    return item.at(key).get<double>();
}

std::vector<std::string> requiredStringArray(const nlohmann::json& item, const std::string& key) {
    if (!item.contains(key) || !item.at(key).is_array()) {
        throw std::runtime_error("missing array field: " + key);
    }
    std::vector<std::string> values;
    for (const auto& value : item.at(key)) {
        if (!value.is_string()) {
            throw std::runtime_error("array must contain strings: " + key);
        }
        values.push_back(value.get<std::string>());
    }
    return values;
}

}  // namespace

std::vector<Poi> loadPois(const std::string& path) {
    const auto json = readJsonFile(path);
    if (!json.is_array()) {
        throw std::runtime_error("pois file must be an array");
    }

    std::vector<Poi> pois;
    std::set<std::string> ids;
    for (const auto& item : json) {
        Poi poi;
        poi.id = requiredString(item, "id");
        poi.name = requiredString(item, "name");
        poi.type = poiTypeFromString(requiredString(item, "type"));
        poi.lat = requiredNumber(item, "lat");
        poi.lng = requiredNumber(item, "lng");
        poi.tags = requiredStringArray(item, "tags");
        poi.openMinutes = item.contains("open_time") ? parseTimeToMinutes(item.at("open_time").get<std::string>()) : 0;
        poi.closeMinutes = item.contains("close_time") ? parseTimeToMinutes(item.at("close_time").get<std::string>()) : 24 * 60;
        poi.visitDurationMinutes = item.contains("visit_duration_minutes") ? static_cast<int>(item.at("visit_duration_minutes").get<double>()) : 60;
        poi.popularity = requiredNumber(item, "popularity");
        poi.priceLevel = static_cast<int>(requiredNumber(item, "price_level"));
        poi.description = requiredString(item, "description");
        poi.area = requiredString(item, "area");
        poi.mealType = item.value("meal_type", "main");
        poi.recommendation = item.value("recommendation", "");
          poi.imageUrl = item.value("image_url", "");
          poi.guideText = item.value("guide_text", "");
          if (item.contains("images") && item["images"].is_array()) {
              for (const auto& img : item["images"]) {
                  PoiImage pi;
                  pi.url = img.value("url", "");
                  pi.source = img.value("source", "");
                  pi.noteUrl = img.value("note_url", "");
                  poi.images.push_back(pi);
              }
          }

        if (!ids.insert(poi.id).second) {
            throw std::runtime_error("duplicate poi id: " + poi.id);
        }
        pois.push_back(poi);
    }
    return pois;
}

std::vector<Edge> loadEdges(const std::string& path, const std::vector<Poi>& pois) {
    const auto json = readJsonFile(path);
    if (!json.is_array()) {
        throw std::runtime_error("edges file must be an array");
    }

    std::set<std::string> ids;
    for (const auto& poi : pois) {
        ids.insert(poi.id);
    }

    std::vector<Edge> edges;
    for (const auto& item : json) {
        Edge edge;
        edge.from = requiredString(item, "from");
        edge.to = requiredString(item, "to");
        edge.distanceMeters = static_cast<int>(requiredNumber(item, "distance_meters"));
        edge.walkMinutes = item.value("walk_minutes", -1);
        edge.transitMinutes = item.value("transit_minutes", -1);
        edge.taxiMinutes = item.value("taxi_minutes", -1);

        if (ids.count(edge.from) == 0 || ids.count(edge.to) == 0 || edgeTravelMinutes(edge) < 0) {
            continue;  // skip edges with missing POIs or no travel time
        }
        edges.push_back(edge);
    }
    return edges;
}

DataSet loadDataSet(const std::string& poiPath, const std::string& edgePath) {
    DataSet data;
    data.pois = loadPois(poiPath);
    data.edges = loadEdges(edgePath, data.pois);

    // Check graph connectivity and warn if disconnected
    if (!data.pois.empty() && !data.edges.empty()) {
        // Build adjacency set from loaded edges
        std::unordered_map<std::string, std::vector<std::string>> adj;
        for (const auto& edge : data.edges) {
            adj[edge.from].push_back(edge.to);
            adj[edge.to].push_back(edge.from);
        }

        // BFS from first POI
        std::set<std::string> visited;
        std::queue<std::string> bfsQueue;
        bfsQueue.push(data.pois.front().id);
        visited.insert(data.pois.front().id);
        while (!bfsQueue.empty()) {
            std::string current = bfsQueue.front();
            bfsQueue.pop();
            auto it = adj.find(current);
            if (it != adj.end()) {
                for (const auto& neighbor : it->second) {
                    if (visited.insert(neighbor).second) {
                        bfsQueue.push(neighbor);
                    }
                }
            }
        }

        // Count non-hotel/transit POIs that are unreachable
        int unreachable = 0;
        for (const auto& poi : data.pois) {
            if (poi.type != PoiType::Hotel && poi.type != PoiType::Transit && visited.count(poi.id) == 0) {
                ++unreachable;
            }
        }
        if (unreachable > 0) {
            std::cerr << "WARNING: " << unreachable << " POIs are unreachable from the main graph component. "
                      << "This may indicate missing edges in " << edgePath << std::endl;
        }
    }

    return data;
}

}  // namespace tourpass
