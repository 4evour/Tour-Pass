import httpx

resp = httpx.get('http://localhost:8080/poi/browse', params={'city': 'changsha', 'limit': 500}, timeout=10)
data = resp.json()
pois = data.get('data', [])
print(f'Total POIs returned: {len(pois)}')

types = {}
for p in pois:
    t = p.get('type', 'unknown')
    types[t] = types.get(t, 0) + 1

print('Types:')
for t, count in sorted(types.items(), key=lambda x: -x[1]):
    print(f'  {t}: {count}')

hotel_like = [p for p in pois if '酒店' in p.get('name', '') or 'hotel' in p.get('name', '').lower()]
print(f'Hotel-like names: {len(hotel_like)}')
for h in hotel_like[:5]:
    hname = h.get('name', '?')
    htype = h.get('type', '?')
    harea = h.get('area', '?')
    print(f'  {hname} | type={htype} | {harea}')
