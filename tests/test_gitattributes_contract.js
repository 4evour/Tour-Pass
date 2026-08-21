const fs = require("fs");
const path = require("path");

const attributesPath = path.join(__dirname, "..", ".gitattributes");
const content = fs.readFileSync(attributesPath);

if (content.length >= 3 && content[0] === 0xef && content[1] === 0xbb && content[2] === 0xbf) {
  throw new Error(".gitattributes must not start with a UTF-8 BOM because Git treats the first comment as attributes.");
}

const text = content.toString("utf8");
if (!text.includes("Dockerfile text eol=lf")) {
  throw new Error("Expected Dockerfile to be normalized to LF line endings.");
}
if (!text.includes("web/editor-dist/** text eol=lf")) {
  throw new Error("Expected generated editor assets to be normalized to LF line endings.");
}

console.log(".gitattributes syntax guard passed.");
