import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('data/guangzhou/city_tips.json', encoding='utf-8') as f:
    data = json.load(f)
print(f'POI count: {len(data)}')
for name, info in list(data.items())[:5]:
    print(f'\n=== {name} ===')
    print(f'  source_count: {info["source_count"]}, avg_likes: {info["avg_likes"]:.0f}')
    for t in info['tips']:
        print(f'  [{t["category"]}] {t["text"][:80]}  (votes={t["votes"]})')
