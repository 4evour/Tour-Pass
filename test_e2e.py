import http.client, json

print("=" * 60)
print("TourPass 端到端测试")
print("=" * 60)

# Test 1: C++ health
print("\n[1] C++ 后端健康检查...")
c = http.client.HTTPConnection("127.0.0.1", 8080)
c.request("GET", "/health")
r = c.getresponse()
data = json.loads(r.read())
print(f"  Status: {r.status}, POI: {data['total_poi_count']}, Cities: {data['city_count']}")
c.close()

# Test 2: Agent health through proxy
print("\n[2] Agent 健康检查 (via proxy)...")
c = http.client.HTTPConnection("127.0.0.1", 8080)
c.request("GET", "/agent/health")
r = c.getresponse()
data = json.loads(r.read())
print(f"  Status: {r.status}, Service: {data['service']}")
c.close()

# Test 3: Editor page
print("\n[3] Editor 页面...")
c = http.client.HTTPConnection("127.0.0.1", 8080)
c.request("GET", "/editor/")
r = c.getresponse()
html = r.read().decode()
has_agent = "CfPyiyD5" in html
print(f"  Status: {r.status}, Agent JS included: {has_agent}")
c.close()

# Test 4: Agent SSE streaming through proxy
print("\n[4] Agent SSE 流式代理...")
c = http.client.HTTPConnection("127.0.0.1", 8080)
body = json.dumps({"message": "\u5e26\u7236\u6bcd\u53bb\u957f\u6c992\u5929\uff0c\u60f3\u53bb\u5cb3\u9e93\u5c71"})
c.request("POST", "/agent/plan", body, {"Content-Type": "application/json", "Content-Length": str(len(body))})
r = c.getresponse()
ct = r.getheader("Content-Type")
events = []
total = 0
while True:
    chunk = r.read(256)
    if not chunk:
        break
    total += len(chunk)
    text = chunk.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        if line.startswith("event:"):
            events.append(line.strip())
print(f"  Status: {r.status}, Content-Type: {ct}")
print(f"  Events: {len(events)}, Total bytes: {total}")
for e in events:
    print(f"    {e}")
c.close()

# Test 5: Agent plan-sync through proxy
print("\n[5] Agent plan-sync 代理...")
c = http.client.HTTPConnection("127.0.0.1", 8080)
body = json.dumps({"message": "\u6210\u90fd\u7f8e\u98df3\u5929"})
c.request("POST", "/agent/plan-sync", body, {"Content-Type": "application/json", "Content-Length": str(len(body))})
r = c.getresponse()
data = json.loads(r.read())
itinerary = data.get("itinerary", {})
print(f"  Status: {r.status}, Source: {data.get('source')}")
print(f"  City: {itinerary.get('city')}, Days: {len(itinerary.get('days', []))}")
if itinerary.get("days"):
    for d in itinerary["days"]:
        stops = [s.get("poi_name", "?") for s in d.get("stops", [])]
        print(f"    Day {d.get('day')}: {', '.join(stops)}")
c.close()

print("\n" + "=" * 60)
print("全部测试完成!")
print("=" * 60)
