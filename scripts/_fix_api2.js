const fs = require('fs');
let c = fs.readFileSync('src/api.cpp', 'utf-8');

const old = '{"recommendation", e.poi->recommendation}\r\n            };';
const rep = '{"recommendation", e.poi->recommendation},\r\n                {"image_url", e.poi->imageUrl}\r\n            };';

if (c.includes(old)) {
  c = c.replace(old, rep);
  console.log('Added image_url to browse response');
} else {
  console.log('Pattern still not found');
}

fs.writeFileSync('src/api.cpp', c);
console.log('Done');
