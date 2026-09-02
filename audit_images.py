import json, os

data = json.load(open('D:/Tour Pass/data/guangzhou/pois.json', encoding='utf-8'))
attractions = [p for p in data if p.get('type') in ('attraction', 'nightlife')]
with_img = [p for p in attractions if p.get('image_url')]

print('=== Current Image Stats ===')
print('Total attractions: ' + str(len(attractions)))
print('With images: ' + str(len(with_img)))
print('Without images: ' + str(len(attractions) - len(with_img)))

# Check image source
from collections import Counter
sources = Counter()
for p in with_img:
    imgs = p.get('images', [])
    for img in imgs:
        sources[img.get('source', 'unknown')] += 1
print('---')
print('Image sources:')
for s, c in sources.most_common():
    print('  ' + s + ': ' + str(c))

# Check for duplicate images (same URL across different POIs)
url_to_pois = {}
for p in with_img:
    url = p.get('image_url', '')
    if url not in url_to_pois:
        url_to_pois[url] = []
    url_to_pois[url].append(p['name'])

dupes = {u: names for u, names in url_to_pois.items() if len(names) > 1}
print('---')
print('Duplicate image URLs: ' + str(len(dupes)))
for u, names in list(dupes.items())[:5]:
    print('  ' + u + ' -> ' + ', '.join(names))

# Check image file sizes
img_base = 'D:/Tour Pass/data/guangzhou/images'
total_size = 0
file_count = 0
for root, dirs, files in os.walk(img_base):
    for f in files:
        if f.endswith('.png') or f.endswith('.jpg'):
            total_size += os.path.getsize(os.path.join(root, f))
            file_count += 1
print('---')
print('Total image files: ' + str(file_count))
print('Total size: ' + str(round(total_size / 1024 / 1024, 1)) + ' MB')
