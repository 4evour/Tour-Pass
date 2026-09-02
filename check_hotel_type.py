import httpx

# Test with different type names for hotel
for t in ['Hotel', 'hotel', 'accommodation', 'lodging']:
    resp = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'type': t, 'limit': 5}, timeout=10)
    d = resp.json()
    print(f'type={t}: {d.get("total", 0)} results')

# Check what poiTypeToString returns for Hotel
# Look at the C++ code to see the string mapping
