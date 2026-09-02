import httpx
resp = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'type': 'hotel', 'limit': 5}, timeout=30)
data = resp.json()
print(f'Hotels: {data.get("total", 0)}')
for h in data.get('data', [])[:5]:
    print(f'  {h.get("name", "?")} | {h.get("area", "?")} | pop={h.get("popularity", 0)}')
