const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {
    pois: 100,
    outDir: "output/synthetic",
    city: "synthetic",
    seed: 42,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--pois") args.pois = Number(value);
    if (key === "--out-dir") args.outDir = value;
    if (key === "--city") args.city = value;
    if (key === "--seed") args.seed = Number(value);
    if (key.startsWith("--")) i += 1;
  }
  args.pois = Math.max(10, args.pois);
  return args;
}

function rng(seed) {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

function pick(values, random) {
  return values[Math.floor(random() * values.length)];
}

function timeForDistance(distanceMeters, multiplier) {
  return Math.max(5, Math.round((distanceMeters / 1000) * multiplier));
}

function distanceMeters(a, b) {
  const dx = (a.lat - b.lat) * 111000;
  const dy = (a.lng - b.lng) * 91000;
  return Math.round(Math.sqrt(dx * dx + dy * dy));
}

function createPoi(index, type, area, random) {
  const tagsByType = {
    hotel: ["酒店", "交通便利"],
    attraction: ["历史文化", "城市漫步", "室内", "艺术", "公园", "亲子"],
    restaurant: ["美食", "小吃", "预算友好", "本地菜"],
    nightlife: ["夜景", "街区", "夜市", "休闲"],
  };
  const baseLat = 28.19;
  const baseLng = 112.98;
  const areaIndex = Number(area.replace("area_", ""));
  return {
    id: `${type}_${index}`,
    name: `合成${type}${index}`,
    type,
    lat: Number((baseLat + areaIndex * 0.012 + random() * 0.01).toFixed(6)),
    lng: Number((baseLng + areaIndex * 0.014 + random() * 0.01).toFixed(6)),
    area,
    open_time: type === "nightlife" ? "18:00" : "09:00",
    close_time: type === "nightlife" ? "23:00" : "21:30",
    visit_duration_minutes: type === "restaurant" ? 60 : 90,
    tags: Array.from(new Set([pick(tagsByType[type], random), pick(tagsByType[type], random)])),
    popularity: Number((60 + random() * 40).toFixed(1)),
    price_level: Math.floor(random() * 4) + 1,
    description: `用于规模实验的${area} ${type} POI，模拟标签、开放时间和通勤边。`,
  };
}

function main() {
  const args = parseArgs(process.argv);
  const random = rng(args.seed);
  const areas = Array.from({ length: Math.max(4, Math.ceil(args.pois / 120)) }, (_, i) => `area_${i}`);
  const pois = [];
  pois.push(createPoi(0, "hotel", areas[0], random));
  for (let i = 1; i < args.pois; i += 1) {
    let type = "attraction";
    if (i % 7 === 0) type = "restaurant";
    if (i % 11 === 0) type = "nightlife";
    const area = areas[i % areas.length];
    pois.push(createPoi(i, type, area, random));
  }

  const edges = [];
  const byArea = new Map();
  for (const poi of pois) {
    if (!byArea.has(poi.area)) byArea.set(poi.area, []);
    byArea.get(poi.area).push(poi);
  }

  for (const group of byArea.values()) {
    for (let i = 0; i < group.length; i += 1) {
      for (let offset = 1; offset <= 3 && i + offset < group.length; offset += 1) {
        const from = group[i];
        const to = group[i + offset];
        const distance = distanceMeters(from, to);
        edges.push({
          from: from.id,
          to: to.id,
          distance_meters: distance,
          walk_minutes: timeForDistance(distance, 12),
          transit_minutes: timeForDistance(distance, 4.5),
          taxi_minutes: timeForDistance(distance, 2.8),
        });
      }
    }
  }

  for (let i = 0; i < areas.length - 1; i += 1) {
    const from = byArea.get(areas[i])[0];
    const to = byArea.get(areas[i + 1])[0];
    const distance = distanceMeters(from, to);
    edges.push({
      from: from.id,
      to: to.id,
      distance_meters: distance,
      walk_minutes: timeForDistance(distance, 14),
      transit_minutes: timeForDistance(distance, 5),
      taxi_minutes: timeForDistance(distance, 3),
    });
  }

  fs.mkdirSync(args.outDir, { recursive: true });
  fs.writeFileSync(path.join(args.outDir, "pois.json"), `${JSON.stringify(pois, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(args.outDir, "edges.json"), `${JSON.stringify(edges, null, 2)}\n`, "utf8");
  console.log(`Synthetic data written: ${pois.length} POIs, ${edges.length} edges, ${areas.length} areas -> ${args.outDir}`);
}

main();
