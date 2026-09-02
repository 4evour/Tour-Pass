import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('data/guangzhou/xhs_guides.json', encoding='utf-8') as f:
    notes = json.load(f)
print(f'Total notes: {len(notes)}')
for i, n in enumerate(notes[:5]):
    mp = n.get('matchedPois', [])
    desc = n.get('desc', '')
    print(f'--- Note {i} ---')
    print(f'  title: {n.get("title","")[:60]}')
    print(f'  matchedPois: {mp}')
    print(f'  desc len: {len(desc)}')
    print(f'  desc[:80]: {desc[:80]}')
    has_poi = bool(mp) and bool(mp[0].get('name',''))
    print(f'  has_poi_name: {has_poi}')
    print()
