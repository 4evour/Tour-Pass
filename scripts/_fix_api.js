const fs = require('fs');
let c = fs.readFileSync('src/api.cpp', 'utf-8');

// Add image_url to browse response
const old = '{"recommendation", e.poi->recommendation}\n            };';
const rep = '{"recommendation", e.poi->recommendation},\n                {"image_url", e.poi->imageUrl}\n            };';

if (c.includes(old)) {
  c = c.replace(old, rep);
  console.log('Added image_url to browse response');
} else {
  console.log('Pattern not found, checking...');
  const idx = c.indexOf('e.poi->recommendation}');
  if (idx > 0) {
    console.log('Found at index', idx);
    console.log('Context:', JSON.stringify(c.substring(idx, idx + 100)));
  }
}

fs.writeFileSync('src/api.cpp', c);
console.log('Done');
