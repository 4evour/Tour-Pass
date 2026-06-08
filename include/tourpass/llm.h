#pragma once

#include <memory>
#include <string>
#include <vector>

#include "tourpass/models.h"

// Forward declare in global namespace (httplib lives there)
namespace httplib { class Client; }

namespace tourpass {

struct LlmConfig {
    std::string apiKey;
    std::string baseUrl = "https://api.openai.com/v1";
    std::string model = "gpt-4o-mini";
};

struct ChatMessage {
    std::string role;
    std::string content;
};

struct LlmParsedRequest {
    TripRequest request;
    std::vector<std::string> unmatchedNames;
    std::string parseNote;
    bool parsed = false;
};

class LlmClient {
public:
    explicit LlmClient(const std::string& configPath = "config/llm.local.json");

    bool isConfigured() const;
    std::string explain(const Itinerary& itinerary) const;
    const LlmConfig& config() const { return config_; }

    LlmParsedRequest parseNaturalLanguageRequest(const std::string& message, const std::vector<ChatMessage>& context, const std::string& defaultCity) const;
    std::string generateItineraryReply(const std::string& userMessage, const TripRequest& request, const Itinerary& itinerary) const;

    std::string chatCompletion(const std::vector<ChatMessage>& messages, double temperature = 0.4) const;

private:
    LlmConfig config_;
    mutable std::shared_ptr<::httplib::Client> httpClient_;

    std::string explainWithTemplate(const Itinerary& itinerary) const;
    std::string explainWithRemote(const Itinerary& itinerary) const;
};

}  // namespace tourpass
