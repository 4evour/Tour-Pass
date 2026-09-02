import http.client, json
conn = http.client.HTTPConnection("127.0.0.1", 8080)
body = json.dumps({"message": "test: changsha 1 day"})
headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
conn.request("POST", "/agent/plan-sync", body, headers)
resp = conn.getresponse()
print(f"Status: {resp.status}")
data = resp.read(500)
print(data.decode("utf-8", errors="replace"))
conn.close()
