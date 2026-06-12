"""Clean POI data: fix nightlife, remove no-source_id, remove pop=0."""
import json, os, re
from collections import Counter

DATA_DIR = r'D:\Tour Pass\data'

HOTEL_KW = ['酒店','宾馆','客栈','民宿','旅馆','公寓','度假村']
REST_KW = ['烧烤','火锅','餐厅','饭店','菜','面','粉','粥','串','锅','小吃','美食','料理','烤肉','烤鱼','炖品','肠粉','茶楼','早茶']
BAR_KW = ['酒吧','酒馆','pub','lounge','KTV','ktv','夜店','派对','party','club','清吧','餐吧','小酒馆']
NIGHT_MKT_KW = ['夜市','夜街','宵夜']

def classify_nightlife(name):
    """Return target type or None to remove."""
    if any(k in name for k in HOTEL_KW): return None  # remove
    if any(k in name for k in BAR_KW): return 'restaurant'  # treat as dining
    if any(k in name for k in NIGHT_MKT_KW): return 'restaurant'
    if any(k in name for k in REST_KW): return 'restaurant'
    # Coffee shops, venues etc. → keep as restaurant
    if '咖啡' in name or '茶' in name or '烤吧' in name or '啤酒' in name:
        return 'restaurant'
    if '公馆' in name or '会所' in name or '中心' in name:
        return 'restaurant'
    return 'restaurant'  # default: merge to restaurant

results = {}
for city_dir in sorted(os.listdir(DATA_DIR)):
    poi_path = os.path.join(DATA_DIR, city_dir, 'pois.json')
    if not os.path.isfile(poi_path): continue
    pois = json.load(open(poi_path, 'r', encoding='utf-8'))
    
    stats = {'nightlife_removed': 0, 'nightlife_merged': 0, 'no_sid_removed': 0, 'pop0_removed': 0}
    cleaned = []
    
    for p in pois:
        typ = p.get('type', '')
        pop = p.get('popularity', 0)
        sid = p.get('source_id', '')
        
        # 1. Nightlife: reclassify or remove
        if typ == 'nightlife':
            target = classify_nightlife(p['name'])
            if target is None:
                stats['nightlife_removed'] += 1
                continue
            else:
                p['type'] = target
                if target == 'restaurant' and not p.get('meal_type'):
                    p['meal_type'] = 'nightlife'
                stats['nightlife_merged'] += 1
        
        # 2. No source_id: remove (except transit which we handle separately)
        if not sid and typ != 'transit':
            stats['no_sid_removed'] += 1
            continue
        
        # 3. Popularity=0: remove
        if pop == 0:
            stats['pop0_removed'] += 1
            continue
        
        cleaned.append(p)
    
    # Save
    with open(poi_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    # Count by type
    types = Counter(p.get('type') for p in cleaned)
    
    results[city_dir] = {
        'before': len(pois),
        'after': len(cleaned),
        'removed': len(pois) - len(cleaned),
        'stats': stats,
        'types': dict(types),
    }

print('%-15s %5s %5s %5s  %s' % ('City', 'Before', 'After', 'Removed', 'Details'))
print('-' * 80)
tb = ta = tr = 0
for city, r in results.items():
    tb += r['before']
    ta += r['after']
    tr += r['removed']
    s = r['stats']
    details = 'night_del=%d night_merge=%d no_sid=%d pop0=%d' % (
        s['nightlife_removed'], s['nightlife_merged'], s['no_sid_removed'], s['pop0_removed'])
    print('%-15s %5d %5d %5d  %s' % (city, r['before'], r['after'], r['removed'], details))
print('-' * 80)
print('%-15s %5d %5d %5d' % ('TOTAL', tb, ta, tr))

# Show type distribution after cleanup
print()
print('Final type distribution (all cities):')
all_types = Counter()
for r in results.values():
    for t, c in r['types'].items():
        all_types[t] += c
for t, c in all_types.most_common():
    print('  %s: %d' % (t, c))
