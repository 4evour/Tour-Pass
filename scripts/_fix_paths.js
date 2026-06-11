const fs = require('fs');
const poisPath = 'data/guangzhou/pois.json';
const pois = JSON.parse(fs.readFileSync(poisPath, 'utf-8'));

let fixed = 0;
for (const poi of pois) {
  if (poi.image_url && poi.image_url.startsWith('images/guangzhou/')) {
    // Fix: images/guangzhou/amap_xxx/1.png -> images/guangzhou/images/amap_xxx/1.png
    const oldPath = poi.image_url;
    poi.image_url = poi.image_url.replace('images/guangzhou/', 'images/guangzhou/images/');
    
    // Also fix images array
    if (poi.images) {
      for (const img of poi.images) {
        if (img.url) img.url = img.url.replace('images/guangzhou/', 'images/guangzhou/images/');
      }
    }
    fixed++;
  }
}

fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
console.log('Fixed', fixed, 'POI paths');
