#include "tourpass/llm.h"

#include <cstdlib>
#include <fstream>
#include <sstream>

#include "httplib.h"

namespace tourpass {

namespace {

std::string getenvString(const char* key) {
    const char* value = std::getenv(key);
    return value ? std::string(value) : std::string();
}

bool envFlagEnabled(const char* key) {
    std::string value = getenvString(key);
    return value == "1" || value == "true" || value == "TRUE" || value == "yes" || value == "YES";
}

struct Endpoint {
    std::string origin;
    std::string pathPrefix;
};

Endpoint parseEndpoint(std::string baseUrl) {
    while (!baseUrl.empty() && baseUrl.back() == '/') {
        baseUrl.pop_back();
    }
    size_t hostStart = 0;
    size_t scheme = baseUrl.find("://");
    if (scheme != std::string::npos) {
        hostStart = scheme + 3;
    }
    size_t pathStart = baseUrl.find('/', hostStart);
    if (pathStart == std::string::npos) {
        return {baseUrl, ""};
    }
    return {baseUrl.substr(0, pathStart), baseUrl.substr(pathStart)};
}

}  // namespace

LlmClient::LlmClient(const std::string& configPath) {
    std::ifstream input(configPath);
    if (input) {
        try {
            nlohmann::json json;
            input >> json;
            config_.apiKey = json.value("api_key", "");
            config_.baseUrl = json.value("base_url", config_.baseUrl);
            config_.model = json.value("model", config_.model);
        } catch (...) {
            config_ = LlmConfig{};
        }
    }

    if (envFlagEnabled("LLM_DISABLED")) {
        config_.apiKey.clear();
        return;
    }

    std::string envKey = getenvString("OPENAI_API_KEY");
    std::string envBase = getenvString("LLM_BASE_URL");
    std::string envModel = getenvString("LLM_MODEL");
    if (!envKey.empty()) config_.apiKey = envKey;
    if (!envBase.empty()) config_.baseUrl = envBase;
    if (!envModel.empty()) config_.model = envModel;
}

bool LlmClient::isConfigured() const {
    return !config_.apiKey.empty();
}

std::string LlmClient::explain(const Itinerary& itinerary) const {
    if (isConfigured()) {
        std::string remote = explainWithRemote(itinerary);
        if (!remote.empty()) {
            return remote;
        }
    }
    return explainWithTemplate(itinerary);
}

std::string LlmClient::explainWithTemplate(const Itinerary& itinerary) const {
    std::ostringstream out;
    out << "这是为你生成的 " << itinerary.city << " 行程。";
    for (const auto& day : itinerary.days) {
        out << "\n第 " << day.day << " 天：" << day.summary;
        for (const auto& stop : day.stops) {
            out << "\n- " << stop.slot << " " << stop.poiName << "（"
                << formatMinutes(stop.startMinutes) << "-" << formatMinutes(stop.endMinutes)
                << "）： " << stop.reason;
        }
    }
    out << "\n整体安排优先兼顾兴趣匹配、开放时间和通勤成本。";
    return out.str();
}

std::string LlmClient::explainWithRemote(const Itinerary& itinerary) const {
    nlohmann::json messages = nlohmann::json::array({
        {
            {"role", "system"},
            {"content", "你是中文旅行规划助手。根据结构化行程，输出简洁、可信、适合演示的中文解释。"}
        },
        {
            {"role", "user"},
            {"content", itineraryToJson(itinerary).dump()}
        }
    });
    nlohmann::json body = {
        {"model", config_.model},
        {"messages", messages},
        {"temperature", 0.4}
    };

    try {
        Endpoint endpoint = parseEndpoint(config_.baseUrl);
        httplib::Client client(endpoint.origin);
        if (!client.is_valid()) {
            return "";
        }
        client.set_connection_timeout(5);
        client.set_read_timeout(20);
        client.set_write_timeout(20);

        httplib::Headers headers = {
            {"Authorization", "Bearer " + config_.apiKey}
        };
        std::string path = endpoint.pathPrefix + "/chat/completions";
        auto result = client.Post(path, headers, body.dump(), "application/json");
        if (!result || result->status < 200 || result->status >= 300) {
            return "";
        }
        auto json = nlohmann::json::parse(result->body);
        return json.at("choices").at(0).at("message").at("content").get<std::string>();
    } catch (...) {
        return "";
    }
}

}  // namespace tourpass
