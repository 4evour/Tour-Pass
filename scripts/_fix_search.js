const fs = require('fs');
let c = fs.readFileSync('src/search.cpp', 'utf-8');

const old = '{"recommendation", result.recommendation}\n    };';
const rep = '{"recommendation", result.recommendation},\n        {"image_url", result.imageUrl}\n    };';

if (c.includes(old)) {
  c = c.replace(old, rep);
  console.log('Added image_url to searchResultToJson');
} else {
  // Try \r\n
  const old2 = '{"recommendation", result.recommendation}\r\n    };';
  if (c.includes(old2)) {
    c = c.replace(old2, rep);
    console.log('Added image_url (crlf)');
  } else {
    console.log('Pattern not found');
  }
}

fs.writeFileSync('src/search.cpp', c);
console.log('Done');
