import http.client, json
c = http.client.HTTPConnection("127.0.0.1", 8080)
b = json.dumps({"message": "test changsha 1 day"})
c.request("POST", "/agent/plan", b, {"Content-Type": "application/json", "Content-Length": str(len(b))})
r = c.getresponse()
ct = r.getheader("Content-Type")
print(f"Status: {r.status}")
print(f"Content-Type: {ct}")
total = 0
while True:
    chunk = r.read(256)
    if not chunk:
        break
    total += len(chunk)
    text = chunk.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        if line.startswith("event:"):
            print(f"  EVENT: {line.strip()}")
    if total > 8000:
        print("  ... (truncated)")
        break
print(f"Total bytes: {total}")
c.close()
