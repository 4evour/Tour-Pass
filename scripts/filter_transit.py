"""Filter transit POIs v2 - only major hubs."""
import json, os, re

DATA_DIR = r'D:\Tour Pass\data'

SKIP_KEYWORDS = [
    '地铁站', '公交站', '进站口', '出站口', '出发', '到达',
    '国内出发', '国际出发', '国内到达', '国际到达', '港澳台',
    '卫星厅', '航站楼', '公务机', '城市航站', '客舱服务',
    '航空客货', '已关闭', '通用机场', '直升机场', '候机楼', '候机厅',
    '落客区', '候车区', '停车场', '换乘', '休息室', '环卫',
    '停靠点', '客运站', '汽车站', '交通枢纽', '长途', '货运',
    '建设中', '运行基地', '城市候机',
]

MINOR_STATION_KW = [
    '货站', '货运', '南站(非主线)', '北站(非主线)',
]

def is_main_transit(name):
    for kw in SKIP_KEYWORDS:
        if kw in name:
            return False
    return True

def normalize_station(name):
    base = re.sub(r'[(\uff08].*?[)\uff09]', '', name).strip()
    return base

def station_importance(name):
    """Higher = more important."""
    n = name
    # Airports
    if '机场' in n and '国际' in n: return 100
    if '机场' in n and '荷花' in n: return 100
    if '机场' in n: return 90
    # Major train stations (city name + 站)
    if re.match(r'^.{2,4}(站)$', n): return 80
    # Named stations
    if n.endswith('站'): return 50
    # Bus terminals
    if '客运' in n or '汽车' in n: return 20
    return 10

results = {}
for city_dir in sorted(os.listdir(DATA_DIR)):
    poi_path = os.path.join(DATA_DIR, city_dir, 'pois.json')
    if not os.path.isfile(poi_path): continue
    pois = json.load(open(poi_path, 'r', encoding='utf-8'))
    transits = [p for p in pois if p.get('type') == 'transit']
    
    filtered = [p for p in transits if is_main_transit(p['name'])]
    
    # Deduplicate
    groups = {}
    for p in filtered:
        base = normalize_station(p['name'])
        groups.setdefault(base, []).append(p)
    deduped = []
    for base, group in groups.items():
        group.sort(key=lambda p: -p.get('popularity', 0))
        deduped.append(group[0])
    
    # Sort by importance then popularity
    deduped.sort(key=lambda p: (-station_importance(p['name']), -p.get('popularity', 0)))
    
    # Keep top N: 2 airports + 5 stations + 3 bus = 10 max
    airports = [p for p in deduped if '机场' in p['name']][:2]
    stations = [p for p in deduped if '站' in p['name'] and '机场' not in p['name'] and '客运' not in p['name'] and '汽车' not in p['name']][:5]
    bus = [p for p in deduped if '客运' in p['name'] or '汽车' in p['name']][:3]
    final = airports + stations + bus
    
    results[city_dir] = {
        'original': len(transits),
        'filtered': len(final),
        'list': [{'name': p['name'], 'pop': p.get('popularity',0), 'area': p.get('area','')} for p in final],
    }

print('%-15s %5s %5s' % ('City', 'Orig', 'Final'))
print('-' * 30)
to = tf = 0
for city, r in results.items():
    to += r['original']
    tf += r['filtered']
    print('%-15s %5d %5d' % (city, r['original'], r['filtered']))
print('-' * 30)
print('%-15s %5d %5d' % ('TOTAL', to, tf))

print()
for city, r in results.items():
    print('=== %s (%d) ===' % (city.upper(), r['filtered']))
    for item in r['list']:
        print('  %-40s %.1f  %s' % (item['name'][:40], item['pop'], item['area']))
    print()
