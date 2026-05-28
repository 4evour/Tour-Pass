#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdlib>
#include <stdexcept>
#include <string>

namespace tourpass {

inline size_t envSize(const char* key, size_t fallback, size_t minValue, size_t maxValue) {
    const char* value = std::getenv(key);
    if (!value || !*value) return fallback;
    try {
        size_t parsed = static_cast<size_t>(std::stoul(value));
        return std::max(minValue, std::min(maxValue, parsed));
    } catch (...) {
        return fallback;
    }
}

}  // namespace tourpass
