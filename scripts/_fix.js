const fs = require('fs');
let c = fs.readFileSync('scripts/crawl_xhs_guides.js', 'utf-8');
c = c.replace(
  "if (!r.data?.items) { console.error('Cookie validation failed'); process.exit(1); }",
  "if (!r.data?.items) { console.error('Validation response: ' + JSON.stringify(r).substring(0, 800)); process.exit(1); }"
);
fs.writeFileSync('scripts/crawl_xhs_guides.js', c);
console.log('patched');
