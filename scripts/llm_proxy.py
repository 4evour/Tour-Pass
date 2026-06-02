#!/usr/bin/env python3
import json
import http.server
import urllib.request
import urllib.error
import os
import sys

LISTEN_PORT = int(os.environ.get("LLM_PROXY_PORT", 8888))
TARGET_URL = os.environ.get("LLM_TARGET_URL", "https://proxy.monkeycode-ai.com")
API_KEY = os.environ.get("LLM_PROXY_API_KEY", "")
MAX_BODY_SIZE = 1024 * 1024  # 1 MB


class LLMProxy(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            err = json.dumps({"error": f"Request body too large ({content_len} bytes, max {MAX_BODY_SIZE})"}).encode()
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return
        body = self.rfile.read(content_len)

        url = TARGET_URL + self.path
        headers = {"Content-Type": "application/json", "User-Agent": "tourpass-llm-proxy/1.0"}
        if API_KEY:
            headers["Authorization"] = "Bearer " + API_KEY

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def log_message(self, fmt, *args):
        sys.stdout.write(f"[llm-proxy] {fmt % args}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", LISTEN_PORT), LLMProxy)
    print(f"LLM proxy listening on http://127.0.0.1:{LISTEN_PORT} -> {TARGET_URL}", flush=True)
    server.serve_forever()
