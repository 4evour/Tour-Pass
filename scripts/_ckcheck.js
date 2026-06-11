const fs = require('fs');
const env = fs.readFileSync('.env', 'utf-8');
const match = env.match(/^XHS_COOKIE=(.+)$/m);
if (!match) { console.log('No XHS_COOKIE found'); process.exit(1); }
const ck = match[1].trim();
const fields = ck.split(';').map(s => s.trim().split('=')[0]);
console.log('Cookie fields:', fields.join(', '));
console.log('Has a1:', fields.includes('a1'));
console.log('Has web_session:', fields.includes('web_session'));
console.log('Total length:', ck.length);
console.log('First 100 chars:', ck.substring(0, 100));
