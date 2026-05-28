const fs = require("fs");
const path = require("path");

const DRINK_KEYWORDS = ["茶饮", "冷饮", "甜品", "奶茶", "咖啡", "果汁", "饮品", "茶室", "茶馆", "冰淇淋", "冷饮店", "甜品店"];
const SNACK_KEYWORDS = ["夜市", "烧烤", "甜点", "点心", "面包店", "蛋糕", "串串", "炸鸡", "卤味", "鸭脖", "小吃街", "小吃店", "卤味店"];

function deriveMealType(poiType, tags) {
  if (poiType !== "restaurant") return "main";
  for (const kw of DRINK_KEYWORDS) {
    if (tags.some(t => t.includes(kw))) return "drink";
  }
  for (const kw of SNACK_KEYWORDS) {
    if (tags.some(t => t.includes(kw))) return "snack";
  }
  return "main";
}

function migrate(filePath) {
  const pois = JSON.parse(fs.readFileSync(filePath, "utf8"));
  let drinkCount = 0;
  let snackCount = 0;
  let mainCount = 0;

  for (const poi of pois) {
    const mealType = deriveMealType(poi.type, poi.tags || []);
    poi.meal_type = mealType;
    if (mealType === "drink") drinkCount++;
    else if (mealType === "snack") snackCount++;
    else mainCount++;
  }

  fs.writeFileSync(filePath, JSON.stringify(pois, null, 2) + "\n", "utf8");
  console.log(`${filePath}: ${pois.length} POIs migrated (main=${mainCount}, drink=${drinkCount}, snack=${snackCount})`);
}

const files = [
  path.join(__dirname, "..", "data", "pois.json"),
  path.join(__dirname, "..", "data", "wuhan", "pois.json"),
];

for (const f of files) {
  if (fs.existsSync(f)) {
    migrate(f);
  } else {
    console.log(`skip: ${f} not found`);
  }
}
