#include "tourpass/llm.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <process.h>

namespace tourpass {

namespace {

std::string getenvString(const char* key) {
    const char* value = std::getenv(key);
    return value ? std::string(value) : std::string();
}

std::string escapeForCommand(const std::string& value) {
    std::string escaped;
    for (char ch : value) {
        if (ch == '"') escaped += "\\\"";
        else if (ch == '\n' || ch == '\r') escaped += ' ';
        else escaped += ch;
    }
    return escaped;
}

std::string runCommandCapture(const std::string& command) {
    std::array<char, 256> buffer{};
    std::string result;
    FILE* pipe = _popen(command.c_str(), "r");
    if (!pipe) return "";
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        result += buffer.data();
    }
    int exitCode = _pclose(pipe);
    if (exitCode != 0) return "";
    return result;
}

std::string tempRequestPath() {
    std::string dir = getenvString("TEMP");
    if (dir.empty()) dir = ".";
    char last = dir.empty() ? '\0' : dir.back();
    if (last != '\\' && last != '/') dir += "\\";
    return dir + "tourpass_llm_request_" + std::to_string(_getpid()) + ".json";
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

    std::string url = config_.baseUrl;
    if (!url.empty() && url.back() == '/') {
        url.pop_back();
    }
    url += "/chat/completions";

    std::string requestPath = tempRequestPath();
    {
        std::ofstream requestFile(requestPath, std::ios::binary);
        if (!requestFile) return "";
        requestFile << body.dump();
    }

    std::string command = "curl.exe -sS --max-time 20 -X POST \"" + escapeForCommand(url) +
        "\" -H \"Content-Type: application/json\" -H \"Authorization: Bearer " + escapeForCommand(config_.apiKey) +
        "\" --data-binary \"@" + escapeForCommand(requestPath) + "\" 2>NUL";
    std::string response = runCommandCapture(command);
    std::remove(requestPath.c_str());
    if (response.empty()) return "";

    try {
        auto json = nlohmann::json::parse(response);
        return json.at("choices").at(0).at("message").at("content").get<std::string>();
    } catch (...) {
        return "";
    }
}

}  // namespace tourpass
