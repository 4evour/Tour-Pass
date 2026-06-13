#pragma once

#include <string>
#include <vector>

#include "tourpass/models.h"

namespace tourpass {

struct DataSet {
    std::vector<Poi> pois;
    std::vector<Edge> edges;
};

std::vector<Poi> loadPois(const std::string& path);
std::vector<Edge> loadEdges(const std::string& path, const std::vector<Poi>& pois);
DataSet loadDataSet(const std::string& poiPath, const std::string& edgePath);
void savePois(const std::string& path, const std::vector<Poi>& pois);

}  // namespace tourpass
