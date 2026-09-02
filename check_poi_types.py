import httpx

# Test without type filter
resp = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'limit': 700}, timeout=10)
data = resp.json()
pois = data.get('data', [])
total = data.get('total', 0)
print(f'Total POIs (no filter): {total}')

types = {}
for p in pois:
    t = p.get('type', 'unknown')
    types[t] = types.get(t, 0) + 1
print('Types:')
for t, count in sorted(types.items(), key=lambda x: -x[1]):
    print(f'  {t}: {count}')

# Now test with hotel filter
resp2 = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'type': 'hotel', 'limit': 10}, timeout=10)
data2 = resp2.json()
print(f'With type=hotel filter: {data2.get("total", 0)} hotels')

# Try with different type names
for t in ['Hotel', 'hotel', 'accommodation', 'lodging']:
    resp3 = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'type': t, 'limit': 5}, timeout=10)
    d3 = resp3.json()
    print(f'  type={t}: {d3.get("total", 0)} results')
