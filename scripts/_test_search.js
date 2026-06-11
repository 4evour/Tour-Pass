// Quick test: search XHS for "广州旅游" and print full response
const path = require('path');
const fs = require('fs');
const https = require('https');

// Load .env
const envPath = path.join(__dirname, '..', '.env');
const env = fs.readFileSync(envPath, 'utf-8');
const cookieMatch = env.match(/^XHS_COOKIE=(.+)$/m);
if (!cookieMatch) { console.log('No XHS_COOKIE'); process.exit(1); }
const cookie = cookieMatch[1].trim();

// Load signing engine
const xsPath = path.join(__dirname, 'xhs_sign', 'xhs_xs_xsc_56.js');
const _origWrite = process.stdout.write.bind(process.stdout);
process.stdout.write = function() {};
const _origLog = console.log;
console.log = function() {};
const xs = require(xsPath);
console.log = _origLog;
process.stdout.write = _origWrite;

// Parse cookie
function transCookies(str) {
  const ck = {};
  for (const item of str.split(/;\s*/)) {
    const idx = item.indexOf('=');
    if (idx > 0) ck[item.substring(0, idx).trim()] = item.substring(idx + 1).trim();
  }
  return ck;
}

const ck = transCookies(cookie);
const a1 = ck.a1 || '';
console.log('a1:', a1.substring(0, 20) + '...');

// Generate signature
const api = '/api/sns/web/v1/search/notes';
const data = {
  keyword: '广州旅游', page: 1, page_size: 20,
  search_id: 'abcdef0123456789abcde', sort: 'general', note_type: 0, ext_flags: [],
  filters: [
    { tags: ['general'], type: 'sort_type' },
    { tags: ['not limited'], type: 'filter_note_type' },
    { tags: ['not limited'], type: 'filter_note_time' },
    { tags: ['not limited'], type: 'filter_note_range' },
    { tags: ['not limited'], type: 'filter_pos_distance' },
  ],
  geo: '', image_formats: ['jpg', 'webp', 'avif'],
};

console.log('Generating signature...');
const ret = xs.get_request_headers_params(api, JSON.stringify(data), a1, 'POST');
console.log('Signature result:', JSON.stringify({
  xs: ret.xs ? ret.xs.substring(0, 30) + '...' : 'EMPTY',
  xt: ret.xt,
  xs_common: ret.xs_common ? ret.xs_common.substring(0, 30) + '...' : 'EMPTY',
}));

// Build headers
const headers = {
  'authority': 'edith.xiaohongshu.com',
  'accept': 'application/json, text/plain, */*',
  'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
  'content-type': 'application/json;charset=UTF-8',
  'origin': 'https://www.xiaohongshu.com',
  'referer': 'https://www.xiaohongshu.com/',
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
  'x-s': ret.xs,
  'x-t': String(ret.xt),
  'x-s-common': ret.xs_common,
  'x-b3-traceid': 'abcdef0123456789',
  'x-xray-traceid': 'abcdef0123456789',
  'cookie': cookie,
};

console.log('\nSending request to:', 'https://edith.xiaohongshu.com' + api);
console.log('x-s header:', (ret.xs || '').substring(0, 50));

const postData = JSON.stringify(data);
const url = new URL('https://edith.xiaohongshu.com' + api);
const options = {
  hostname: url.hostname,
  path: url.pathname,
  method: 'POST',
  headers: { ...headers, 'content-length': Buffer.byteLength(postData) },
};

const req = https.request(options, (res) => {
  let body = '';
  res.on('data', (chunk) => body += chunk);
  res.on('end', () => {
    console.log('\nStatus:', res.statusCode);
    console.log('Response:', body.substring(0, 1000));
    try {
      const j = JSON.parse(body);
      console.log('\nParsed: code=', j.code, 'success=', j.success, 'items=', j.data?.items?.length || 0);
      if (j.data?.items?.length > 0) {
        console.log('First item:', JSON.stringify(j.data.items[0]).substring(0, 300));
      }
    } catch(e) {
      console.log('Parse error:', e.message);
    }
  });
});
req.on('error', (e) => console.log('Request error:', e.message));
req.write(postData);
req.end();
