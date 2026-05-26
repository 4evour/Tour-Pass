#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace tourpass {

// Password hashing (SHA256 + random salt)
std::string hashPassword(const std::string& password);
bool verifyPassword(const std::string& password, const std::string& storedHash);

// JWT token (HMAC-SHA256)
std::string createToken(int64_t userId, const std::string& username, const std::string& role, int ttlSeconds = 86400 * 7);
struct TokenPayload {
    int64_t userId = 0;
    std::string username;
    std::string role;
    int64_t expiresAt = 0;
};
std::optional<TokenPayload> verifyToken(const std::string& token);

// JWT secret from env
const std::string& jwtSecret();

// Base64url helpers
std::string base64urlEncode(const std::string& input);
std::string base64urlDecode(const std::string& input);

// Random hex string for salt
std::string randomHex(size_t bytes);

}  // namespace tourpass
