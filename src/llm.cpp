#include "tourpass/llm.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>

#include "httplib.h"

#ifdef _WIN32
#ifndef CPPHTTPLIB_OPENSSL_SUPPORT
#include <windows.h>
#include <winhttp.h>
#endif
#endif

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

bool envDebugEnabled() {
    return envFlagEnabled("LLM_DEBUG");
}

void debugLlm(const std::string& message) {
    if (envDebugEnabled()) {
        std::cerr << "[llm] " << message << std::endl;
    }
}

struct Endpoint {
    std::string scheme;
    std::string host;
    int port = 0;
    std::string pathPrefix;
    bool https = false;

    std::string origin() const {
        std::ostringstream out;
        out << scheme << "://" << host;
        const bool defaultPort = (https && port == 443) || (!https && port == 80);
        if (port > 0 && !defaultPort) {
            out << ":" << port;
        }
        return out.str();
    }
};

Endpoint parseEndpoint(std::string baseUrl) {
    while (!baseUrl.empty() && baseUrl.back() == '/') {
        baseUrl.pop_back();
    }
    std::string schemeValue = "https";
    bool https = true;
    size_t hostStart = 0;
    size_t scheme = baseUrl.find("://");
    if (scheme != std::string::npos) {
        schemeValue = baseUrl.substr(0, scheme);
        https = schemeValue == "https";
        hostStart = scheme + 3;
    }
    size_t pathStart = baseUrl.find('/', hostStart);
    std::string hostPort = pathStart == std::string::npos
        ? baseUrl.substr(hostStart)
        : baseUrl.substr(hostStart, pathStart - hostStart);
    std::string host = hostPort;
    int port = https ? 443 : 80;
    size_t colon = hostPort.rfind(':');
    if (colon != std::string::npos) {
        host = hostPort.substr(0, colon);
        try {
            port = std::stoi(hostPort.substr(colon + 1));
        } catch (...) {
            port = https ? 443 : 80;
        }
    }
    if (pathStart == std::string::npos) {
        return {schemeValue, host, port, "", https};
    }
    return {schemeValue, host, port, baseUrl.substr(pathStart), https};
}

std::string parseChatCompletionContent(const std::string& responseBody) {
    auto json = nlohmann::json::parse(responseBody);
    return json.at("choices").at(0).at("message").at("content").get<std::string>();
}

#ifdef _WIN32
#ifndef CPPHTTPLIB_OPENSSL_SUPPORT
std::wstring utf8ToWide(const std::string& value) {
    if (value.empty()) {
        return L"";
    }
    int length = MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0);
    if (length <= 0) {
        return L"";
    }
    std::wstring wide(static_cast<size_t>(length), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), wide.data(), length);
    return wide;
}

struct WinHttpHandle {
    HINTERNET value = nullptr;

    explicit WinHttpHandle(HINTERNET handle = nullptr) : value(handle) {}
    ~WinHttpHandle() {
        if (value) {
            WinHttpCloseHandle(value);
        }
    }

    WinHttpHandle(const WinHttpHandle&) = delete;
    WinHttpHandle& operator=(const WinHttpHandle&) = delete;
};

std::string postJsonWithWinHttp(const Endpoint& endpoint, const std::string& path, const std::string& apiKey, const std::string& body) {
    std::wstring host = utf8ToWide(endpoint.host);
    std::wstring requestPath = utf8ToWide(path.empty() ? "/" : path);
    if (host.empty() || requestPath.empty()) {
        return "";
    }

    WinHttpHandle session(WinHttpOpen(L"TourPass/1.0",
                                      WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                      WINHTTP_NO_PROXY_NAME,
                                      WINHTTP_NO_PROXY_BYPASS,
                                      0));
    if (!session.value) {
        debugLlm("WinHttpOpen failed: " + std::to_string(GetLastError()));
        return "";
    }

    WinHttpHandle connect(WinHttpConnect(session.value, host.c_str(), static_cast<INTERNET_PORT>(endpoint.port), 0));
    if (!connect.value) {
        debugLlm("WinHttpConnect failed: " + std::to_string(GetLastError()));
        return "";
    }

    DWORD flags = endpoint.https ? WINHTTP_FLAG_SECURE : 0;
    WinHttpHandle request(WinHttpOpenRequest(connect.value,
                                             L"POST",
                                             requestPath.c_str(),
                                             nullptr,
                                             WINHTTP_NO_REFERER,
                                             WINHTTP_DEFAULT_ACCEPT_TYPES,
                                             flags));
    if (!request.value) {
        debugLlm("WinHttpOpenRequest failed: " + std::to_string(GetLastError()));
        return "";
    }

    std::wstring contentType = L"Content-Type: application/json";
    std::wstring authorization = L"Authorization: Bearer " + utf8ToWide(apiKey);
    if (!WinHttpAddRequestHeaders(request.value,
                                  contentType.c_str(),
                                  static_cast<DWORD>(-1L),
                                  WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE) ||
        !WinHttpAddRequestHeaders(request.value,
                                  authorization.c_str(),
                                  static_cast<DWORD>(-1L),
                                  WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE)) {
        debugLlm("WinHttpAddRequestHeaders failed: " + std::to_string(GetLastError()));
        return "";
    }

    BOOL sent = WinHttpSendRequest(request.value,
                                   WINHTTP_NO_ADDITIONAL_HEADERS,
                                   0,
                                   WINHTTP_NO_REQUEST_DATA,
                                   0,
                                   static_cast<DWORD>(body.size()),
                                   0);
    if (!sent) {
        debugLlm("WinHttpSendRequest failed: " + std::to_string(GetLastError()));
        return "";
    }

    DWORD written = 0;
    if (!WinHttpWriteData(request.value, body.data(), static_cast<DWORD>(body.size()), &written) ||
        written != body.size()) {
        debugLlm("WinHttpWriteData failed: " + std::to_string(GetLastError()));
        return "";
    }

    if (!WinHttpReceiveResponse(request.value, nullptr)) {
        debugLlm("WinHttpReceiveResponse failed: " + std::to_string(GetLastError()));
        return "";
    }

    DWORD status = 0;
    DWORD statusSize = sizeof(status);
    if (!WinHttpQueryHeaders(request.value,
                             WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX,
                             &status,
                             &statusSize,
                             WINHTTP_NO_HEADER_INDEX)) {
        debugLlm("WinHttpQueryHeaders failed: " + std::to_string(GetLastError()));
        return "";
    }
    std::string response;
    DWORD available = 0;
    while (WinHttpQueryDataAvailable(request.value, &available) && available > 0) {
        std::string chunk(available, '\0');
        DWORD read = 0;
        if (!WinHttpReadData(request.value, chunk.data(), available, &read)) {
            debugLlm("WinHttpReadData failed: " + std::to_string(GetLastError()));
            return "";
        }
        chunk.resize(read);
        response += chunk;
    }
    if (status < 200 || status >= 300) {
        debugLlm("WinHTTP status " + std::to_string(status) + " body=" + response);
        return "";
    }
    return response;
}
#endif
#endif

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
    bool hasLocalKey = !config_.apiKey.empty();
    bool hasEnvProviderOverride = !envBase.empty() || !envModel.empty();
    if (!envKey.empty() && (!hasLocalKey || hasEnvProviderOverride)) config_.apiKey = envKey;
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
        std::string path = endpoint.pathPrefix + "/chat/completions";

#ifdef _WIN32
#ifndef CPPHTTPLIB_OPENSSL_SUPPORT
        if (endpoint.https) {
            std::string responseBody = postJsonWithWinHttp(endpoint, path, config_.apiKey, body.dump());
            if (!responseBody.empty()) {
                return parseChatCompletionContent(responseBody);
            }
            return "";
        }
#endif
#endif

        httplib::Client client(endpoint.origin());
        if (!client.is_valid()) {
            return "";
        }
        client.set_connection_timeout(5);
        client.set_read_timeout(20);
        client.set_write_timeout(20);

        httplib::Headers headers = {
            {"Authorization", "Bearer " + config_.apiKey}
        };
        auto result = client.Post(path, headers, body.dump(), "application/json");
        if (!result || result->status < 200 || result->status >= 300) {
            return "";
        }
        return parseChatCompletionContent(result->body);
    } catch (...) {
        return "";
    }
}

}  // namespace tourpass
