import json

with open('data/pois.json', 'r', encoding='utf-8') as f:
    pois = json.load(f)

print(f'Total POIs in data/pois.json: {len(pois)}')

types = {}
for p in pois:
    t = p.get('type', 'unknown')
    types[t] = types.get(t, 0) + 1

print('Types:')
for t, count in sorted(types.items(), key=lambda x: -x[1]):
    print(f'  {t}: {count}')

hotels = [p for p in pois if p.get('type') == 'hotel']
print(f'Hotel-type POIs: {len(hotels)}')
for h in hotels[:5]:
    hname = h.get('name', '?')
    harea = h.get('area', '?')
    hpop = h.get('popularity', 0)
    print(f'  {hname} | {harea} | pop={hpop}')
