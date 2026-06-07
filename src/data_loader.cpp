#include "tourpass/data_loader.h"

#include <fstream>
#include <set>
#include <stdexcept>

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

        if (ids.count(edge.from) == 0) {
            throw std::runtime_error("edge references unknown from poi: " + edge.from);
        }
        if (ids.count(edge.to) == 0) {
            throw std::runtime_error("edge references unknown to poi: " + edge.to);
        }
        if (edgeTravelMinutes(edge) < 0) {
            throw std::runtime_error("edge has no usable travel minutes: " + edge.from + " -> " + edge.to);
        }
        edges.push_back(edge);
    }
    return edges;
}

DataSet loadDataSet(const std::string& poiPath, const std::string& edgePath) {
    DataSet data;
    data.pois = loadPois(poiPath);
    data.edges = loadEdges(edgePath, data.pois);
    return data;
}

}  // namespace tourpass
