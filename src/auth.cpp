#include "tourpass/auth.h"

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <mutex>
#include <random>
#include <sstream>
#include <stdexcept>

#include "json.hpp"

#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
#include <openssl/evp.h>
#include <openssl/hmac.h>
#else
#pragma message("WARNING: Building without OpenSSL. Password hashing and JWT signatures use insecure fallbacks. Production deployments MUST enable TOURPASS_ENABLE_OPENSSL.")
#endif

namespace tourpass {

namespace {

// ---- hex helpers ----

std::string toHex(const unsigned char* data, size_t len) {
    std::ostringstream oss;
    for (size_t i = 0; i < len; ++i) {
        oss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(data[i]);
    }
    return oss.str();
}

std::vector<unsigned char> fromHex(const std::string& hex) {
    std::vector<unsigned char> out;
    for (size_t i = 0; i + 1 < hex.size(); i += 2) {
        unsigned int byte;
        std::istringstream(hex.substr(i, 2)) >> std::hex >> byte;
        out.push_back(static_cast<unsigned char>(byte));
    }
    return out;
}

std::string sha256(const std::string& data) {
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hashLen = 0;
    EVP_Digest(data.data(), data.size(), hash, &hashLen, EVP_sha256(), nullptr);
    return toHex(hash, hashLen);
#else
    std::hash<std::string> hasher;
    size_t h = hasher(data);
    return toHex(reinterpret_cast<const unsigned char*>(&h), sizeof(h));
#endif
}

std::string pbkdf2Hex(const std::string& password, const std::string& salt) {
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
    unsigned char dk[32];
    PKCS5_PBKDF2_HMAC(password.data(), static_cast<int>(password.size()),
                      reinterpret_cast<const unsigned char*>(salt.data()), static_cast<int>(salt.size()),
                      100000, EVP_sha256(), sizeof(dk), dk);
    return toHex(dk, sizeof(dk));
#else
    return sha256(salt + ":" + password);
#endif
}

// ---- HMAC-SHA256 ----

std::string hmacSha256(const std::string& key, const std::string& data) {
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hashLen = 0;
    HMAC(EVP_sha256(), key.data(), static_cast<int>(key.size()),
         reinterpret_cast<const unsigned char*>(data.data()), data.size(),
         hash, &hashLen);
    return std::string(reinterpret_cast<char*>(hash), hashLen);
#else
    // Fallback: XOR-based pseudo-HMAC (NOT secure - only for dev)
    std::string combined = key + data;
    size_t h = std::hash<std::string>{}(combined);
    return std::string(reinterpret_cast<const char*>(&h), sizeof(h));
#endif
}

}  // namespace

bool constantTimeEquals(const std::string& a, const std::string& b) {
    if (a.size() != b.size()) return false;
    volatile unsigned char result = 0;
    for (size_t i = 0; i < a.size(); ++i) {
        result |= static_cast<unsigned char>(a[i]) ^ static_cast<unsigned char>(b[i]);
    }
    return result == 0;
}

std::string randomHex(size_t bytes) {
    static thread_local std::mt19937 gen(std::random_device{}());
    std::uniform_int_distribution<int> dist(0, 255);
    std::ostringstream oss;
    for (size_t i = 0; i < bytes; ++i) {
        oss << std::hex << std::setw(2) << std::setfill('0') << dist(gen);
    }
    return oss.str();
}

std::string hashPassword(const std::string& password) {
    std::string salt = randomHex(16);
    std::string hash = pbkdf2Hex(password, salt);
    return salt + ":" + hash;
}

bool verifyPassword(const std::string& password, const std::string& storedHash) {
    auto colonPos = storedHash.find(':');
    if (colonPos == std::string::npos) return false;
    std::string salt = storedHash.substr(0, colonPos);
    std::string expectedHash = storedHash.substr(colonPos + 1);
    std::string computedHash;
    if (expectedHash.size() == 64) {
        computedHash = sha256(salt + ":" + password);
    } else {
        computedHash = pbkdf2Hex(password, salt);
    }
    return constantTimeEquals(computedHash, expectedHash);
}

// ---- Base64url ----

static const char BASE64URL_CHARS[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

std::string base64urlEncode(const std::string& input) {
    std::string out;
    size_t len = input.size();
    const unsigned char* data = reinterpret_cast<const unsigned char*>(input.data());
    for (size_t i = 0; i < len; i += 3) {
        unsigned int n = static_cast<unsigned int>(data[i]) << 16;
        if (i + 1 < len) n |= static_cast<unsigned int>(data[i + 1]) << 8;
        if (i + 2 < len) n |= static_cast<unsigned int>(data[i + 2]);
        out += BASE64URL_CHARS[(n >> 18) & 0x3F];
        out += BASE64URL_CHARS[(n >> 12) & 0x3F];
        if (i + 1 < len) out += BASE64URL_CHARS[(n >> 6) & 0x3F];
        if (i + 2 < len) out += BASE64URL_CHARS[n & 0x3F];
    }
    // Remove padding (base64url typically has no padding)
    return out;
}

std::string base64urlDecode(const std::string& input) {
    static unsigned char lookup[256];
    static std::once_flag lookupInit;
    std::call_once(lookupInit, [] {
        std::memset(lookup, 0xFF, 256);
        for (int i = 0; i < 64; ++i) {
            lookup[static_cast<unsigned char>(BASE64URL_CHARS[i])] = static_cast<unsigned char>(i);
        }
    });

    std::string out;
    size_t len = input.size();
    for (size_t i = 0; i < len; i += 4) {
        unsigned int n = 0;
        for (int j = 0; j < 4 && i + j < len; ++j) {
            unsigned char c = lookup[static_cast<unsigned char>(input[i + j])];
            if (c == 0xFF) throw std::runtime_error("invalid base64url character");
            n |= static_cast<unsigned int>(c) << (18 - j * 6);
        }
        out += static_cast<char>((n >> 16) & 0xFF);
        if (i + 2 < len) out += static_cast<char>((n >> 8) & 0xFF);
        if (i + 3 < len) out += static_cast<char>(n & 0xFF);
    }
    return out;
}

// ---- JWT ----

const std::string& jwtSecret() {
    static const std::string secret = [] {
        const char* env = std::getenv("TOURPASS_JWT_SECRET");
        if (env && env[0]) return std::string(env);
        throw std::runtime_error("TOURPASS_JWT_SECRET environment variable is required");
    }();
    return secret;
}

std::string createToken(int64_t userId, const std::string& username, const std::string& role, int ttlSeconds) {
    // Header
    nlohmann::json header = {{"alg", "HS256"}, {"typ", "JWT"}};

    // Payload
    auto now = std::chrono::system_clock::now();
    auto epoch = now.time_since_epoch();
    int64_t nowSec = std::chrono::duration_cast<std::chrono::seconds>(epoch).count();

    nlohmann::json payload = {
        {"sub", userId},
        {"username", username},
        {"role", role},
        {"iat", nowSec},
        {"exp", nowSec + ttlSeconds}
    };

    std::string headerB64 = base64urlEncode(header.dump());
    std::string payloadB64 = base64urlEncode(payload.dump());
    std::string signingInput = headerB64 + "." + payloadB64;
    std::string signature = hmacSha256(jwtSecret(), signingInput);
    std::string signatureB64 = base64urlEncode(signature);

    return signingInput + "." + signatureB64;
}

std::optional<TokenPayload> verifyToken(const std::string& token) {
    // Split into 3 parts
    size_t dot1 = token.find('.');
    if (dot1 == std::string::npos) return std::nullopt;
    size_t dot2 = token.find('.', dot1 + 1);
    if (dot2 == std::string::npos) return std::nullopt;

    std::string headerB64 = token.substr(0, dot1);
    std::string payloadB64 = token.substr(dot1 + 1, dot2 - dot1 - 1);
    std::string signatureB64 = token.substr(dot2 + 1);

    // Verify signature
    std::string signingInput = headerB64 + "." + payloadB64;
    std::string expectedSig = hmacSha256(jwtSecret(), signingInput);
    std::string expectedSigB64 = base64urlEncode(expectedSig);

    if (!constantTimeEquals(signatureB64, expectedSigB64)) return std::nullopt;

    // Parse payload
    try {
        std::string payloadJson = base64urlDecode(payloadB64);
        auto payload = nlohmann::json::parse(payloadJson);

        TokenPayload result;
        result.userId = payload.value("sub", 0LL);
        result.username = payload.value("username", "");
        result.role = payload.value("role", "user");
        result.expiresAt = payload.value("exp", 0LL);

        // Check expiration
        auto now = std::chrono::system_clock::now();
        int64_t nowSec = std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count();
        if (result.expiresAt <= nowSec) return std::nullopt;

        return result;
    } catch (...) {
        return std::nullopt;
    }
}

}  // namespace tourpass
