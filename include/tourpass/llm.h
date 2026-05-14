#pragma once

#include <string>

#include "tourpass/models.h"

namespace tourpass {

struct LlmConfig {
    std::string apiKey;
    std::string baseUrl = "https://api.openai.com/v1";
    std::string model = "gpt-4o-mini";
};

class LlmClient {
public:
    explicit LlmClient(const std::string& configPath = "config/llm.local.json");

    bool isConfigured() const;
    std::string explain(const Itinerary& itinerary) const;
    const LlmConfig& config() const { return config_; }

private:
    LlmConfig config_;

    std::string explainWithTemplate(const Itinerary& itinerary) const;
    std::string explainWithRemote(const Itinerary& itinerary) const;
};

}  // namespace tourpass
