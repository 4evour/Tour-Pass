import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('data/guangzhou/pois.json', encoding='utf-8') as f:
    data = json.load(f)
rests = [p for p in data if p.get('type') == 'restaurant']
print(f'Total restaurants: {len(rests)}')
print()
for r in rests[:8]:
    print(f'  name: {r.get("name")}')
    print(f'  rating: {r.get("rating")} popularity: {r.get("popularity")}')
    print(f'  tags: {r.get("tags",[])}')
    print(f'  price_level: {r.get("price_level")} area: {r.get("area")}')
    print(f'  lat/lng: {r.get("lat")}, {r.get("lng")}')
    print(f'  description: {str(r.get("description",""))[:80]}')
    print()
