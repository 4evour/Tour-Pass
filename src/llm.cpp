#include "tourpass/llm.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <algorithm>

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
    if (!json.contains("choices") || !json["choices"].is_array() || json["choices"].empty()) {
        return "";
    }
    auto& first = json["choices"][0];
    if (!first.contains("message") || !first["message"].contains("content")) {
        return "";
    }
    return first["message"]["content"].get<std::string>();
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
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
            if (ep.https) {
                httpClient_ = std::make_shared<httplib::Client>(ep.host, ep.port, ep.path);
                if (httpClient_->is_valid()) {
                    httpClient_->set_connection_timeout(5);
                    httpClient_->set_read_timeout(30);
                    httpClient_->set_write_timeout(30);
                } else {
                    httpClient_.reset();
                }
            } else
#endif
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
    out << "杩欐槸涓轰綘鐢熸垚鐨?" << itinerary.city << " 琛岀▼銆?;
    for (const auto& day : itinerary.days) {
        out << "\n绗?" << day.day << " 澶╋細" << day.summary;
        for (const auto& stop : day.stops) {
            out << "\n- " << stop.slot << " " << stop.poiName << "锛?
                << formatMinutes(stop.startMinutes) << "-" << formatMinutes(stop.endMinutes)
                << "锛夛細 " << stop.reason;
        }
    }
    out << "\n鏁翠綋瀹夋帓浼樺厛鍏奸【鍏磋叮鍖归厤銆佸紑鏀炬椂闂村拰閫氬嫟鎴愭湰銆?;
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
        {"system", R"(浣犳槸涓€浣嶈祫娣辨梾琛屾敾鐣ヨ揪浜猴紝鍍忔湅鍙嬩竴鏍蜂负鐢ㄦ埛瑙勫垝琛岀▼銆傛牴鎹粨鏋勫寲琛岀▼鏁版嵁锛岀敤杞绘澗鑷劧鐨勪腑鏂囪緭鍑烘敾鐣ュ紡瑙ｉ噴銆?

瑕佹眰锛?
1. 鐢ㄧ涓€浜虹О"鎴?鎴?鍜变滑"寮€澶达紝鍍忔湅鍙嬫帹鑽愪竴鏍蜂翰鍒囪嚜鐒?
2. 姣忎釜鏅偣/椁愬巺绠€瑕佽鏄?涓轰粈涔堥€夎繖閲?鈥斺€旂壒鑹层€佷寒鐐广€佹媿鐓х偣銆佹嫑鐗岃彍绛?
3. 鐩搁偦琛岀▼鑷劧涓茶仈锛屽舰鎴愬姩绾挎晠浜嬶紙濡?閫涘畬XX姝ｅソ璧板埌YY鍚冧釜楗?锛?
4. 缁欏嚭瀹炵敤灏忚创澹細鏈€浣虫椂闂淬€佹帓闃熷缓璁€佷氦閫氭柟寮忋€佺┛鐫€寤鸿绛?
5. 濡傛灉鏈変笅鍗堣尪瀹夋帓锛岃鏄庢槸浼戞伅璋冩暣鐨勫ソ鏃舵満
6. 椁愬巺鎺ㄨ崘瑕佽鏄庣壒鑹茶彍鎴栨帹鑽愮悊鐢憋紝涓嶈鍙"鐢ㄩ"
7. 淇濇寔鏁翠綋鑺傚鎰燂細涓婂崍绮惧姏鍏呮矝閫傚悎閫涙櫙鐐癸紝涓嬪崍杞绘澗浼戦棽锛屾櫄涓婃劅鍙楀鐢熸椿
8. 鎬诲瓧鏁版帶鍒跺湪 500 瀛椾互鍐?

涓嶈杈撳嚭 JSON锛屽彧杈撳嚭鏀荤暐寮忎腑鏂囨枃鏈€?"},
        {"user", itineraryToJson(itinerary).dump()}
    };
    return chatCompletion(messages, 0.5);
}

LlmParsedRequest LlmClient::parseNaturalLanguageRequest(const std::string& message, const std::vector<ChatMessage>& context, const std::string& defaultCity) const {
    LlmParsedRequest result;

    std::string defaultCityLabel = defaultCity.empty() ? "" : defaultCity;
    std::string systemPrompt =
        "浣犳槸涓€涓梾琛岃鍒掓剰鍥捐В鏋愬櫒銆傜敤鎴蜂細鐢ㄨ嚜鐒惰瑷€鎻忚堪鏃呰闇€姹傦紝浣犻渶瑕佷粠涓彁鍙栫粨鏋勫寲鍙傛暟銆俓n\n"
        "璇蜂弗鏍兼寜鐓т互涓?JSON 鏍煎紡杈撳嚭锛屼笉瑕佽緭鍑轰换浣曞叾浠栧唴瀹癸細\n"
        "{\n"
        "  \"days\": 3,\n"
        "  \"city\": \"\",\n"
        "  \"interests\": [\"鍘嗗彶鏂囧寲\", \"缇庨\"],\n"
        "  \"must_visit\": [\"姗樺瓙娲插ご\", \"宀抽簱灞盶"],\n"
        "  \"avoid\": [],\n"
        "  \"pace\": \"鏍囧噯\",\n"
        "  \"start_minutes\": 540,\n"
        "  \"end_minutes\": 1260,\n"
        "  \"notes\": \"鐢ㄦ埛鎻愬埌鐨勭壒娈婇渶姹俓"\n"
        "}\n\n"
        "瀛楁璇存槑锛歕n"
        "- days: 鏃呰澶╂暟锛?-7锛夛紝濡傛灉鐢ㄦ埛娌¤榛樿涓?3\n"
        "- city: 鍩庡競鍚嶏紝濡傛灉鐢ㄦ埛鏈槑纭彁鍒板煄甯傚垯鐣欑┖瀛楃涓诧紝鐢辩郴缁熻嚜鍔ㄩ€夋嫨\n"
        "- interests: 鍏磋叮鏍囩鏁扮粍锛屼粠浠ヤ笅閫夊彇锛氬巻鍙叉枃鍖栥€佺編椋熴€佽嚜鐒堕鍏夈€佸崥鐗╅銆佸彜寤虹瓚銆佸鏅€佽喘鐗┿€佷紤闂层€佹埛澶栥€佸鍐呫€佷翰瀛愩€佹枃鑹恒€佸皬鍚冦€佺綉绾㈡墦鍗n"
        "- must_visit: 鐢ㄦ埛鏄庣‘鎻愬埌鎯冲幓鐨勬櫙鐐瑰悕绉版暟缁刓n"
        "- avoid: 鐢ㄦ埛涓嶆兂鍘荤殑绫诲瀷鎴栨櫙鐐筡n"
        "- pace: 琛岀▼鑺傚锛孿"杞绘澗\"(relaxed)/\"鏍囧噯\"(standard)/\"绱у噾\"(compact)锛岄粯璁"鏍囧噯\"\n"
        "- start_minutes: 姣忔棩鍑哄彂鏃堕棿锛堝垎閽熸暟锛屽 540=9:00锛夛紝榛樿 540\n"
        "- end_minutes: 姣忔棩缁撴潫鏃堕棿锛堝垎閽熸暟锛屽 1260=21:00锛夛紝榛樿 1260\n"
        "- notes: 鐢ㄦ埛鎻愬埌鐨勪换浣曠壒娈婇渶姹傛垨绾︽潫";

    std::vector<ChatMessage> messages = {{"system", systemPrompt}};
    for (const auto& msg : context) {
        messages.push_back(msg);
    }
    messages.push_back({"user", message});

    std::string response = chatCompletion(messages, 0.1);
    if (response.empty()) {
        result.parseNote = "LLM 鏈嶅姟涓嶅彲鐢紝鏃犳硶瑙ｆ瀽鑷劧璇█璇锋眰";
        return result;
    }

    try {
        size_t start = response.find('{');
        size_t end = response.rfind('}');
        if (start == std::string::npos || end == std::string::npos || end <= start) {
            result.parseNote = "LLM 杩斿洖鐨勫唴瀹逛笉鏄湁鏁?JSON: " + response.substr(0, 200);
            return result;
        }
        std::string jsonStr = response.substr(start, end - start + 1);
        auto parsed = nlohmann::json::parse(jsonStr);

        TripRequest req;
        req.city = parsed.value("city", defaultCityLabel);
        req.days = parsed.value("days", 3);
        req.days = std::max(1, std::min(7, req.days));
        req.pace = parsed.value("pace", "鏍囧噯");
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
        result.parseNote = std::string("瑙ｆ瀽 LLM 鍝嶅簲澶辫触: ") + ex.what();
    }
    return result;
}

std::string LlmClient::generateItineraryReply(const std::string& userMessage, const TripRequest& /*request*/, const Itinerary& itinerary, const CityGuide& guide) const {
    std::string systemPrompt = R"(浣犳槸涓€浣嶇儹鎯呯殑鏃呰鏀荤暐杈句汉銆傜敤鎴锋彁鍑轰簡鏃呰闇€姹傦紝绯荤粺宸茬敓鎴愯绋嬭鍒掋€?
鐢ㄦ湅鍙嬭亰澶╃殑鍙ｅ惢鍥炲鐢ㄦ埛锛?1. 鍏堢敤涓€鍙ヨ瘽姒傛嫭鏁翠綋琛岀▼鎰熻
2. 鐢?2-3 涓寒鐐瑰惛寮曠敤鎴凤紙涓轰粈涔堣繖涓畨鎺掑緢妫掋€佹湁浠€涔堥殣钘忕帺娉曪級
3. 缁?1-2 鏉″疄鐢ㄨ创澹紙绌夸粈涔堛€佸甫浠€涔堛€佹敞鎰忎簨椤癸級
4. 濡傛灉鏈変笅鍗堣尪/灏忓悆瀹夋帓锛屾彁涓€涓嬪綋鍦扮壒鑹?5. 淇濇寔鍦?250 瀛椾互鍐咃紝璇皵杞绘澗鑷劧

涓嶈杈撳嚭 JSON锛屽彧杈撳嚭绾枃鏈洖澶嶃€?";

    if (guide.loaded) {
        systemPrompt += "\n\n浠ヤ笅鏄綋鍦版梾琛屾敾鐣ワ紝鍙互鍙傝€冿細\n";
        if (!guide.transportTips.empty()) {
            systemPrompt += "浜ら€氬缓璁細";
            for (size_t i = 0; i < guide.transportTips.size() && i < 3; i++) {
                if (i > 0) systemPrompt += "锛?;
                systemPrompt += guide.transportTips[i];
            }
            systemPrompt += "\n";
        }
        if (!guide.crowdTips.empty()) {
            systemPrompt += "閬垮潙寤鸿锛?;
            for (size_t i = 0; i < guide.crowdTips.size() && i < 3; i++) {
                if (i > 0) systemPrompt += "锛?;
                systemPrompt += guide.crowdTips[i];
            }
            systemPrompt += "\n";
        }
        if (!guide.seasonalTips.empty()) {
            systemPrompt += "瀛ｈ妭寤鸿锛?;
            for (size_t i = 0; i < guide.seasonalTips.size() && i < 2; i++) {
                if (i > 0) systemPrompt += "锛?;
                systemPrompt += guide.seasonalTips[i];
            }
            systemPrompt += "\n";
        }
        if (!guide.hiddenGems.empty()) {
            systemPrompt += "闅愯棌鐜╂硶锛?;
            for (size_t i = 0; i < guide.hiddenGems.size() && i < 2; i++) {
                if (i > 0) systemPrompt += "锛?;
                systemPrompt += guide.hiddenGems[i];
            }
            systemPrompt += "\n";
        }
        if (!guide.foodTips.empty()) {
            systemPrompt += "缇庨鎺ㄨ崘锛?;
            for (size_t i = 0; i < guide.foodTips.size() && i < 3; i++) {
                if (i > 0) systemPrompt += "锛?;
                systemPrompt += guide.foodTips[i];
            }
            systemPrompt += "\n";
        }
    }

    std::string itinerarySummary = "鐢ㄦ埛闇€姹傦細" + userMessage + "\n\n瑙勫垝缁撴灉锛歕n";
    itinerarySummary += "鍩庡競锛? + itinerary.city + "锛屽ぉ鏁帮細" + std::to_string(itinerary.days.size()) + "\n";
    for (const auto& day : itinerary.days) {
        itinerarySummary += "绗? + std::to_string(day.day) + "澶╋細" + day.summary + "\n";
        for (const auto& stop : day.stops) {
            itinerarySummary += "  " + stop.slot + " " + stop.poiName + "锛? + formatMinutes(stop.startMinutes) + "-" + formatMinutes(stop.endMinutes) + "锛塡n";
            if (!stop.reason.empty()) {
                itinerarySummary += "    鎺ㄨ崘鐞嗙敱锛? + stop.reason + "\n";
            }
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



CityGuide LlmClient::loadCityGuide(const std::string& city) {
    CityGuide guide;
    guide.city = city;
    std::string path = "data/" + city + "/city_guide.json";
    std::ifstream file(path);
    if (!file.is_open()) {
        debugLlm("City guide not found: " + path);
        return guide;
    }
    try {
        nlohmann::json j;
        file >> j;
        if (j.contains("best_routes") && j["best_routes"].is_array())
            for (const auto& r : j["best_routes"]) guide.bestRoutes.push_back(r.get<std::string>());
        if (j.contains("timing_tips") && j["timing_tips"].is_array())
            for (const auto& t : j["timing_tips"]) guide.timingTips.push_back(t.get<std::string>());
        if (j.contains("crowd_tips") && j["crowd_tips"].is_array())
            for (const auto& c : j["crowd_tips"]) guide.crowdTips.push_back(c.get<std::string>());
        if (j.contains("food_tips") && j["food_tips"].is_array())
            for (const auto& f : j["food_tips"]) guide.foodTips.push_back(f.get<std::string>());
        if (j.contains("transport_tips") && j["transport_tips"].is_array())
            for (const auto& t : j["transport_tips"]) guide.transportTips.push_back(t.get<std::string>());
        if (j.contains("seasonal_tips") && j["seasonal_tips"].is_array())
            for (const auto& s : j["seasonal_tips"]) guide.seasonalTips.push_back(s.get<std::string>());
        if (j.contains("hidden_gems") && j["hidden_gems"].is_array())
            for (const auto& h : j["hidden_gems"]) guide.hiddenGems.push_back(h.get<std::string>());
        guide.loaded = true;
        debugLlm("Loaded city guide for " + city + ": " +
                 std::to_string(guide.bestRoutes.size()) + " routes, " +
                 std::to_string(guide.timingTips.size()) + " tips");
    } catch (const std::exception& ex) {
        debugLlm("Failed to parse city guide: " + std::string(ex.what()));
    }
    return guide;
}

int LlmClient::evaluateItinerary(const std::vector<Itinerary>& candidates, const CityGuide& guide) const {
    if (candidates.size() <= 1) return 0;
    std::string prompt = R"(浣犳槸鏃呰琛岀▼璇勪及涓撳銆傝璇勪及浠ヤ笅鍊欓€夋柟妗堬紝閫夊嚭鏈€浣崇殑涓€涓€?
璇勪及缁村害锛?1. 璺嚎鍚堢悊鎬э紙鏅偣涔嬮棿璺濈鏄惁鍚堢悊锛屾槸鍚﹁蛋鍥炲ご璺級
2. 鏃堕棿瀹夋帓锛堟瘡涓櫙鐐规椂闂存槸鍚﹀厖瑁曪紝鏄惁鏈夎刀鍦猴級
3. 澶氭牱鎬э紙鏅偣绫诲瀷鏄惁涓板瘜锛岄伩鍏嶉噸澶嶏級
4. 浣撻獙鎰燂紙璺嚎鏄惁鏈夎妭濂忔劅锛屽姵閫哥粨鍚堬級)";
    if (guide.loaded) {
        prompt += "\n\n褰撳湴鏀荤暐鍙傝€冿細\n";
        if (!guide.bestRoutes.empty()) prompt += "缁忓吀璺嚎锛? + guide.bestRoutes[0] + "\n";
        if (!guide.timingTips.empty())
            for (const auto& tip : guide.timingTips) prompt += "- " + tip + "\n";
    }
    prompt += "\n\n鍊欓€夋柟妗堬細\n";
    for (size_t i = 0; i < candidates.size(); i++) {
        const auto& it = candidates[i];
        prompt += "鏂规" + std::to_string(i + 1) + "锛? + it.variantName + "锛夛細\n";
        for (const auto& day : it.days) {
            prompt += "  绗? + std::to_string(day.day) + "澶╋細";
            for (size_t j = 0; j < day.stops.size(); j++) {
                if (j > 0) prompt += " 鈫?";
                prompt += day.stops[j].poiName;
            }
            prompt += "\n";
        }
        prompt += "\n";
    }
    prompt += "璇峰彧鍥炲鏈€浣虫柟妗堢殑缂栧彿锛?-" + std::to_string(candidates.size()) + "锛夛紝涓嶈瑙ｉ噴銆?;
    std::vector<ChatMessage> messages = {{"user", prompt}};
    std::string response = chatCompletion(messages, 0.1);
    try {
        for (char c : response) {
            if (c >= '1' && c <= '9') {
                int idx = c - '1';
                if (idx >= 0 && idx < static_cast<int>(candidates.size())) {
                    debugLlm("LLM selected candidate " + std::to_string(idx + 1));
                    return idx;
                }
            }
        }
    } catch (...) {}
    debugLlm("LLM evaluation failed, defaulting to candidate 0");
    return 0;
}

std::vector<std::string> LlmClient::enrichStopReasons(const Itinerary& itinerary, const CityGuide& guide) const {
    std::vector<std::string> reasons;
    std::string prompt = R"(浣犳槸鏃呰鏀荤暐杈句汉銆傝涓轰互涓嬭绋嬬殑姣忎釜鏅偣鐢熸垚绠€鐭殑鎺ㄨ崘鐞嗙敱锛?5-30瀛楋級銆?
瑕佹眰锛?- 绐佸嚭鏅偣鐗硅壊鍜屼负浠€涔堝€煎緱鍘?- 濡傛灉鏈夋渶浣虫父瑙堟椂闂存垨灏忚创澹紝绠€瑕佹彁鍙?- 璇皵杞绘澗鏈夎叮锛屽儚鏈嬪弸鎺ㄨ崘)";
    if (guide.loaded) {
        prompt += "\n\n褰撳湴鏀荤暐锛歕n";
        if (!guide.timingTips.empty())
            for (const auto& tip : guide.timingTips) prompt += "- " + tip + "\n";
        if (!guide.hiddenGems.empty())
            for (const auto& gem : guide.hiddenGems) prompt += "- " + gem + "\n";
    }
    prompt += "\n\n琛岀▼绔欑偣锛歕n";
    int idx = 1;
    for (const auto& day : itinerary.days) {
        for (const auto& stop : day.stops) {
            prompt += std::to_string(idx) + ". " + stop.poiName + "锛? + stop.slot + "锛? + formatMinutes(stop.startMinutes) + "-" + formatMinutes(stop.endMinutes) + "锛塡n";
            idx++;
        }
    }
    prompt += "\n璇锋寜椤哄簭涓烘瘡涓珯鐐硅緭鍑烘帹鑽愮悊鐢憋紝姣忚涓€涓紝鏍煎紡锛氱紪鍙? 鐞嗙敱\n鍙緭鍑虹悊鐢憋紝涓嶈鍏朵粬鍐呭銆?;
    std::vector<ChatMessage> messages = {{"user", prompt}};
    std::string response = chatCompletion(messages, 0.5);
    std::istringstream stream(response);
    std::string line;
    int expectedCount = 0;
    for (const auto& day : itinerary.days) expectedCount += day.stops.size();
    while (std::getline(stream, line)) {
        if (line.empty()) continue;
        size_t dotPos = line.find('.');
        if (dotPos != std::string::npos && dotPos < 4) line = line.substr(dotPos + 1);
        while (!line.empty() && (line[0] == ' ' || line[0] == '\t')) line = line.substr(1);
        if (!line.empty()) reasons.push_back(line);
    }
    while (static_cast<int>(reasons.size()) < expectedCount) reasons.push_back("鐑害鍜岃矾绾块『搴忚緝鍚堥€?);
    if (static_cast<int>(reasons.size()) > expectedCount) reasons.resize(expectedCount);
    debugLlm("Enriched " + std::to_string(reasons.size()) + " stop reasons");
    return reasons;
}

}  // namespace tourpass
