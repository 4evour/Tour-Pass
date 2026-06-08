/**
 * fix_ratings.js
 * 优化评分系统：
 * 1. 修复 popularity=0 的景点/餐饮/夜游
 * 2. 根据名称知名度和类型重新赋分
 * 3. 确保评分在 3.0-5.0 的合理范围
 */

const fs = require("fs");
const path = require("path");

// 知名景点高分名单（部分城市）
const FAMOUS_POIS = {
  "故宫博物院": 4.9, "故宫": 4.9, "天安门": 4.8, "天安门广场": 4.8,
  "长城": 4.9, "八达岭长城": 4.9, "慕田峪长城": 4.8,
  "颐和园": 4.8, "天坛": 4.7, "圆明园": 4.6, "鸟巢": 4.5, "水立方": 4.5,
  "南锣鼓巷": 4.4, "什刹海": 4.5, "王府井": 4.3, "798": 4.4,
  "西湖": 4.9, "灵隐寺": 4.7, "西溪湿地": 4.5, "千岛湖": 4.6,
  "外滩": 4.8, "东方明珠": 4.7, "豫园": 4.5, "城隍庙": 4.4,
  "南京路": 4.3, "田子坊": 4.4, "迪士尼": 4.8, "新天地": 4.5,
  "兵马俑": 4.9, "大雁塔": 4.7, "华清宫": 4.6, "回民街": 4.4,
  "钟楼": 4.5, "鼓楼": 4.4, "城墙": 4.6, "大唐不夜城": 4.7,
  "鼓浪屿": 4.8, "南普陀寺": 4.6, "曾厝垵": 4.4, "环岛路": 4.5,
  "武侯祠": 4.6, "锦里": 4.5, "宽窄巷子": 4.6, "都江堰": 4.8,
  "青城山": 4.7, "大熊猫": 4.7, "春熙路": 4.3, "太古里": 4.4,
  "洪崖洞": 4.7, "解放碑": 4.5, "磁器口": 4.4, "长江索道": 4.5,
  "三峡": 4.6, "武隆": 4.7,
  "黄鹤楼": 4.6, "户部巷": 4.2, "东湖": 4.5, "武汉大学": 4.4,
  "江汉路": 4.3,
  "橘子洲": 4.7, "岳麓山": 4.6, "岳麓书院": 4.6, "太平街": 4.3,
  "五一广场": 4.2, "湖南省博物馆": 4.6,
  "中山陵": 4.7, "夫子庙": 4.5, "秦淮河": 4.5, "总统府": 4.5,
  "明孝陵": 4.6, "玄武湖": 4.4,
  "崂山": 4.6, "栈桥": 4.4, "八大关": 4.5, "五四广场": 4.3,
  "天涯海角": 4.5, "亚龙湾": 4.6, "南山寺": 4.6, "蜈支洲岛": 4.7,
  "大东海": 4.4, "海棠湾": 4.5,
  "石林": 4.6, "滇池": 4.4, "翠湖": 4.3, "西山": 4.2,
  "丽江古城": 4.7, "玉龙雪山": 4.8, "束河古镇": 4.5, "拉市海": 4.3,
  "大理古城": 4.6, "洱海": 4.7, "苍山": 4.5, "崇圣寺三塔": 4.5,
  "象鼻山": 4.5, "漓江": 4.8, "阳朔": 4.7, "龙脊梯田": 4.6,
  "张家界国家森林公园": 4.8, "天门山": 4.8, "玻璃桥": 4.5,
  "武陵源": 4.7, "黄龙洞": 4.4,
  "广州塔": 4.6, "沙面": 4.4, "白云山": 4.4, "陈家祠": 4.5,
  "长隆": 4.7, "北京路": 4.2,
  "世界之窗": 4.5, "欢乐谷": 4.6, "大梅沙": 4.3, "东部华侨城": 4.5,
  "拙政园": 4.7, "虎丘": 4.5, "寒山寺": 4.4, "平江路": 4.5,
  "周庄": 4.6, "同里": 4.5,
  "中央大街": 4.5, "索菲亚教堂": 4.5, "冰雪大世界": 4.7,
  "太阳岛": 4.3, "东北虎林园": 4.2,
};

// 知名连锁餐饮高分
const FAMOUS_RESTAURANTS = {
  "海底捞": 4.6, "西贝": 4.4, "外婆家": 4.3, "绿茶": 4.2,
  "全聚德": 4.3, "东来顺": 4.4, "便宜坊": 4.2,
  "茶颜悦色": 4.5, "文和友": 4.4, "炊烟": 4.3,
  "小龙坎": 4.3, "大龙燚": 4.3, "蜀大侠": 4.2,
};

function resolvePoisPath(cityDir) {
  const cityPath = path.join("data", cityDir, "pois.json");
  if (fs.existsSync(cityPath)) return cityPath;
  if (cityDir === "changsha") {
    const rootPath = path.join("data", "pois.json");
    if (fs.existsSync(rootPath)) return rootPath;
  }
  return null;
}

function getFamousScore(name) {
  for (const [key, score] of Object.entries(FAMOUS_POIS)) {
    if (name.includes(key)) return score;
  }
  for (const [key, score] of Object.entries(FAMOUS_RESTAURANTS)) {
    if (name.includes(key)) return score;
  }
  return null;
}

function inferScore(poi) {
  const name = poi.name || "";
  const type = poi.type || "";
  const tags = (poi.tags || []).join(" ");

  // 1. 知名景点/餐饮
  const famous = getFamousScore(name);
  if (famous !== null) return famous;

  // 2. 按类型给基础分
  if (type === "attraction") {
    if (tags.includes("世界遗产") || tags.includes("5A")) return 4.7;
    if (tags.includes("国家级") || tags.includes("风景名胜")) return 4.4;
    if (tags.includes("博物馆") || tags.includes("历史文化")) return 4.3;
    if (tags.includes("公园") || tags.includes("广场")) return 4.0;
    if (tags.includes("商圈") || tags.includes("购物")) return 3.9;
    if (tags.includes("古镇") || tags.includes("古城")) return 4.3;
    if (tags.includes("寺庙") || tags.includes("宗教")) return 4.2;
    return 4.0;
  }

  if (type === "restaurant") {
    if (name.includes("老字号") || name.includes("百年")) return 4.5;
    if (tags.includes("美食街") || tags.includes("小吃街")) return 4.2;
    if (tags.includes("夜市")) return 4.1;
    return 4.0;
  }

  if (type === "nightlife") {
    return 4.1;
  }

  // transit 不需要评分
  return 3.8;
}

function main() {
  const cityDirs = fs.readdirSync("data", { withFileTypes: true })
    .filter(d => d.isDirectory())
    .map(d => d.name);

  console.log("=== 评分优化 ===\n");

  let totalFixed = 0, totalAdjusted = 0, totalScanned = 0;

  for (const cityDir of cityDirs) {
    const poisPath = resolvePoisPath(cityDir);
    if (!poisPath) continue;

    const pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
    let fixed = 0, adjusted = 0;

    for (const poi of pois) {
      if (poi.type === "transit" || poi.type === "hotel") continue; // 跳过交通和酒店
      totalScanned++;

      if (!poi.popularity || poi.popularity === 0) {
        // 修复 0 分
        poi.popularity = inferScore(poi);
        fixed++;
      } else if (poi.popularity > 0 && poi.popularity < 3.0) {
        // 低于 3.0 的向上修正
        poi.popularity = Math.max(3.0, inferScore(poi));
        adjusted++;
      } else if (poi.popularity > 5.0) {
        // 高于 5.0 的向下修正（高德评分是 5 分制）
        poi.popularity = Math.min(5.0, poi.popularity);
        adjusted++;
      }
    }

    if (fixed > 0 || adjusted > 0) {
      fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
      console.log(cityDir + ": 修复 " + fixed + " 个0分, 调整 " + adjusted + " 个异常分");
    }
    totalFixed += fixed;
    totalAdjusted += adjusted;
  }

  console.log("\n=== 汇总 ===");
  console.log("扫描: " + totalScanned + " 个POI");
  console.log("修复0分: " + totalFixed + " 个");
  console.log("调整异常分: " + totalAdjusted + " 个");
}

main();
