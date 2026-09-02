import httpx

# Test hotel search
resp = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'type': 'hotel', 'limit': 5}, timeout=10)
data = resp.json()
total = data.get('total', 0)
print(f'Hotels found: {total}')
for h in data.get('data', [])[:5]:
    hname = h.get('name', '?')
    harea = h.get('area', '?')
    hpop = h.get('popularity', 0)
    print(f'  {hname} | {harea} | pop={hpop}')

print()

# Test optimize-route
print('=== Testing optimize-route ===')
payload = {
    'city': 'changsha',
    'must_visit': ['岳麓山风景名胜区', '橘子洲风景名胜区'],
    'days': 1,
    'start_time': '09:00',
    'end_time': '21:00',
    'pace': '标准',
    'candidate_count': 1,
    'strategy': 'balanced'
}
resp2 = httpx.post('http://localhost:8080/api/optimize-route', json=payload, timeout=15)
print(f'Status: {resp2.status_code}')
if resp2.status_code == 200:
    result = resp2.json()
    days = result.get('days', [])
    if days:
        stops = days[0].get('stops', [])
        print(f'Stops: {len(stops)}')
        for s in stops[:3]:
            print(f'  {s.get("poiName", "?")} | {s.get("slot", "?")}')
    else:
        print('No days in result')
else:
    print(f'Error: {resp2.text[:300]}')
