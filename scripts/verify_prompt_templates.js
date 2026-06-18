const fs = require("fs");
const path = require("path");

const indexHtml = fs.readFileSync(path.join(__dirname, "..", "web", "index.html"), "utf8");
const appJs = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

const promptMatches = [...indexHtml.matchAll(/data-prompt="([^"]+)"/g)].map((match) => match[1]);
if (promptMatches.length < 6) {
  throw new Error(`Expected at least 6 chat hint prompts, got ${promptMatches.length}`);
}

const requiredPromptHints = [
  "每晚",
  "预算",
  "优先",
  "要去",
];

for (const prompt of promptMatches) {
  for (const hint of requiredPromptHints) {
    if (!prompt.includes(hint)) {
      throw new Error(`Prompt is missing "${hint}": ${prompt}`);
    }
  }
}

const templateMessages = [...appJs.matchAll(/msg:\s*"([^"]+)"/g)].map((match) => match[1]);
if (templateMessages.length < 10) {
  throw new Error(`Expected itinerary template messages, got ${templateMessages.length}`);
}

for (const message of templateMessages) {
  for (const hint of requiredPromptHints) {
    if (!message.includes(hint)) {
      throw new Error(`Template message is missing "${hint}": ${message}`);
    }
  }
}

const placeholderMatch = indexHtml.match(/<textarea[^>]+id="chatInput"[^>]+placeholder="([^"]+)"/s);
if (!placeholderMatch) {
  throw new Error("Expected chat input placeholder");
}
for (const hint of requiredPromptHints) {
  if (!placeholderMatch[1].includes(hint)) {
    throw new Error(`Placeholder is missing "${hint}": ${placeholderMatch[1]}`);
  }
}

console.log(`Prompt template verification passed: ${promptMatches.length} hints, ${templateMessages.length} templates.`);
