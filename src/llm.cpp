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
        std::string truncated = response.substr(0, 200);
        debugLlm("WinHTTP status " + std::to_string(status) + " body=" + truncated);
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
        } catch (const std::exception&) {
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

    // Initialize persistent HTTP client for connection reuse
    if (isConfigured()) {
        try {
            Endpoint ep = parseEndpoint(config_.baseUrl);
            if (!ep.https) {
                httpClient_ = std::make_shared<httplib::Client>(ep.origin());
                if (httpClient_->is_valid()) {
                    httpClient_->set_connection_timeout(5);
                    httpClient_->set_read_timeout(30);
                    httpClient_->set_write_timeout(30);
                } else {
                    httpClient_.reset();
                }
            }
        } catch (const std::exception& ex) {
            std::cerr << "LLM HTTP client init failed: " << ex.what() << std::endl;
        }
    }
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

std::string LlmClient::chatCompletion(const std::vector<ChatMessage>& messages, double temperature) const {
    if (!isConfigured()) return "";

    nlohmann::json messagesJson = nlohmann::json::array();
    for (const auto& msg : messages) {
        messagesJson.push_back({{"role", msg.role}, {"content", msg.content}});
    }
    nlohmann::json body = {
        {"model", config_.model},
        {"messages", messagesJson},
        {"temperature", temperature}
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

        httplib::Client* client = httpClient_.get();
        std::unique_ptr<httplib::Client> fallbackClient;
        if (!client) {
            fallbackClient = std::make_unique<httplib::Client>(endpoint.origin());
            if (!fallbackClient->is_valid()) return "";
            fallbackClient->set_connection_timeout(5);
            fallbackClient->set_read_timeout(30);
            fallbackClient->set_write_timeout(30);
            client = fallbackClient.get();
        }

        httplib::Headers headers = {
            {"Authorization", "Bearer " + config_.apiKey}
        };
        auto result = client->Post(path, headers, body.dump(), "application/json");
        if (!result || result->status < 200 || result->status >= 300) {
            debugLlm("chatCompletion HTTP status=" + std::to_string(result ? result->status : 0));
            return "";
        }
        return parseChatCompletionContent(result->body);
    } catch (const std::exception& ex) {
        debugLlm(std::string("chatCompletion exception: ") + ex.what());
        return "";
    }
}

std::string LlmClient::explainWithRemote(const Itinerary& itinerary) const {
    std::vector<ChatMessage> messages = {
        {"system", R"(你是一位资深旅行攻略达人，像朋友一样为用户规划行程。根据结构化行程数据，用轻松自然的中文输出攻略式解释。

要求：
1. 用第一人称"我"或"咱们"开头，像朋友推荐一样亲切自然
2. 每个景点/餐厅简要说明"为什么选这里"——特色、亮点、拍照点、招牌菜等
3. 相邻行程自然串联，形成动线故事（如"逛完XX正好走到YY吃个饭"）
4. 给出实用小贴士：最佳时间、排队建议、交通方式、穿着建议等
5. 如果有下午茶安排，说明是休息调整的好时机
6. 餐厅推荐要说明特色菜或推荐理由，不要只说"用餐"
7. 保持整体节奏感：上午精力充沛适合逛景点，下午轻松休闲，晚上感受夜生活
8. 总字数控制在 500 字以内

不要输出 JSON，只输出攻略式中文文本。)"},
        {"user", itineraryToJson(itinerary).dump()}
    };
    return chatCompletion(messages, 0.5);
}

LlmParsedRequest LlmClient::parseNaturalLanguageRequest(const std::string& message, const std::vector<ChatMessage>& context, const std::string& defaultCity) const {
    LlmParsedRequest result;

    std::string defaultCityLabel = defaultCity.empty() ? "" : defaultCity;
    std::string systemPrompt =
        "你是一个旅行规划意图解析器。用户会用自然语言描述旅行需求，你需要从中提取结构化参数。\n\n"
        "请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
        "{\n"
        "  \"days\": 3,\n"
        "  \"city\": \"\",\n"
        "  \"interests\": [\"历史文化\", \"美食\"],\n"
        "  \"must_visit\": [\"橘子洲头\", \"岳麓山\"],\n"
        "  \"avoid\": [],\n"
        "  \"pace\": \"标准\",\n"
        "  \"start_minutes\": 540,\n"
        "  \"end_minutes\": 1260,\n"
        "  \"notes\": \"用户提到的特殊需求\"\n"
        "}\n\n"
        "字段说明：\n"
        "- days: 旅行天数（1-7），如果用户没说默认为 3\n"
        "- city: 城市名，如果用户未明确提到城市则留空字符串，由系统自动选择\n"
        "- interests: 兴趣标签数组，从以下选取：历史文化、美食、自然风光、博物馆、古建筑、夜景、购物、休闲、户外、室内、亲子、文艺、小吃、网红打卡\n"
        "- must_visit: 用户明确提到想去的景点名称数组\n"
        "- avoid: 用户不想去的类型或景点\n"
        "- pace: 行程节奏，\"轻松\"(relaxed)/\"标准\"(standard)/\"紧凑\"(compact)，默认\"标准\"\n"
        "- start_minutes: 每日出发时间（分钟数，如 540=9:00），默认 540\n"
        "- end_minutes: 每日结束时间（分钟数，如 1260=21:00），默认 1260\n"
        "- notes: 用户提到的任何特殊需求或约束";

    std::vector<ChatMessage> messages = {{"system", systemPrompt}};
    for (const auto& msg : context) {
        messages.push_back(msg);
    }
    messages.push_back({"user", message});

    std::string response = chatCompletion(messages, 0.1);
    if (response.empty()) {
        result.parseNote = "LLM 服务不可用，无法解析自然语言请求";
        return result;
    }

    try {
        size_t start = response.find('{');
        size_t end = response.rfind('}');
        if (start == std::string::npos || end == std::string::npos || end <= start) {
            result.parseNote = "LLM 返回的内容不是有效 JSON: " + response.substr(0, 200);
            return result;
        }
        std::string jsonStr = response.substr(start, end - start + 1);
        auto parsed = nlohmann::json::parse(jsonStr);

        TripRequest req;
        req.city = parsed.value("city", defaultCityLabel);
        req.days = parsed.value("days", 3);
        req.days = std::max(1, std::min(7, req.days));
        req.pace = parsed.value("pace", "标准");
        req.startMinutes = parsed.value("start_minutes", 540);
        req.endMinutes = parsed.value("end_minutes", 1260);
        req.candidateCount = 5;
        req.strategy = "balanced";

        if (parsed.contains("interests") && parsed["interests"].is_array()) {
            for (const auto& interest : parsed["interests"]) {
                req.interests.push_back(interest.get<std::string>());
            }
        }
        if (parsed.contains("must_visit") && parsed["must_visit"].is_array()) {
            for (const auto& name : parsed["must_visit"]) {
                req.mustVisit.push_back(name.get<std::string>());
                result.unmatchedNames.push_back(name.get<std::string>());
            }
        }
        if (parsed.contains("avoid") && parsed["avoid"].is_array()) {
            for (const auto& a : parsed["avoid"]) {
                req.avoid.push_back(a.get<std::string>());
            }
        }

        result.request = req;
        result.parseNote = parsed.value("notes", "");
        result.parsed = true;
    } catch (const std::exception& ex) {
        result.parseNote = std::string("解析 LLM 响应失败: ") + ex.what();
    }
    return result;
}

std::string LlmClient::generateItineraryReply(const std::string& userMessage, const TripRequest& /*request*/, const Itinerary& itinerary) const {
    std::string systemPrompt = R"(你是一位热情的旅行攻略达人。用户提出了旅行需求，系统已生成行程规划。

请用朋友聊天的口吻回复用户：
1. 先用一句话概括整体行程感觉（如"这条线路走的是XX风格"）
2. 用 2-3 个亮点吸引用户（为什么这个安排很棒、有什么隐藏玩法）
3. 给 1-2 条实用贴士（穿什么、带什么、注意事项）
4. 如果有下午茶/小吃安排，提一下当地特色
5. 保持在 250 字以内，语气轻松自然

不要输出 JSON，只输出纯文本回复。)";

    std::string itinerarySummary = "用户需求：" + userMessage + "\n\n规划结果：\n";
    itinerarySummary += "城市：" + itinerary.city + "，天数：" + std::to_string(itinerary.days.size()) + "\n";
    for (const auto& day : itinerary.days) {
        itinerarySummary += "第" + std::to_string(day.day) + "天：" + day.summary + "\n";
        for (const auto& stop : day.stops) {
            itinerarySummary += "  " + stop.slot + " " + stop.poiName + "（" + formatMinutes(stop.startMinutes) + "-" + formatMinutes(stop.endMinutes) + "）\n";
        }
    }

    std::vector<ChatMessage> messages = {
        {"system", systemPrompt},
        {"user", itinerarySummary}
    };

    std::string reply = chatCompletion(messages, 0.6);
    if (reply.empty()) {
        return explainWithTemplate(itinerary);
    }
    return reply;
}

}  // namespace tourpass
