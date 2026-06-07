const fs = require("fs");

const brands = [
  { name: "如家酒店", prefix: "如家快捷酒店", rating: [3.5, 4.2] },
  { name: "汉庭酒店", prefix: "汉庭酒店", rating: [3.6, 4.3] },
  { name: "维也纳酒店", prefix: "维也纳国际酒店", rating: [4.0, 4.6] },
  { name: "锦江之星", prefix: "锦江之星酒店", rating: [3.5, 4.2] },
  { name: "亚朵酒店", prefix: "亚朵酒店", rating: [4.2, 4.7] },
  { name: "全季酒店", prefix: "全季酒店", rating: [4.0, 4.5] },
  { name: "格林豪泰", prefix: "格林豪泰酒店", rating: [3.4, 4.1] },
];

const city = { name: "长沙", areas: ["芙蓉区", "天心区", "岳麓区", "开福区", "雨花区"], lat: 28.2282, lng: 112.9388 };

const poisPath = "data/pois.json";
let pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
const existingHotels = pois.filter(p => p.type === "hotel").length;

// Check which brands already exist
const existingBrands = new Set();
for (const p of pois) {
  if (p.type === "hotel") {
    for (const b of brands) {
      if (p.name.includes(b.name) || p.name.includes(b.prefix)) {
        existingBrands.add(b.name);
      }
    }
  }
}
console.log("Existing brand hotels:", [...existingBrands].join(", ") || "none");

const hotels = [];
for (let i = 0; i < brands.length; i++) {
  const brand = brands[i];
  const area = city.areas[i % city.areas.length];
  const lat = city.lat + (Math.random() - 0.5) * 0.05;
  const lng = city.lng + (Math.random() - 0.5) * 0.05;
  const rating = +(brand.rating[0] + Math.random() * (brand.rating[1] - brand.rating[0])).toFixed(1);

  hotels.push({
    id: "changsha_brand_hotel_" + i,
    name: brand.prefix + "(" + city.name + area + "店)",
    type: "hotel",
    lat, lng,
    area,
    open_time: "00:00",
    close_time: "23:59",
    visit_duration_minutes: 30,
    tags: ["住宿", "酒店", brand.name, city.name],
    popularity: rating,
    price_level: (brand.name.includes("维也纳") || brand.name.includes("亚朵") || brand.name.includes("全季")) ? 2 : 1,
    description: brand.name + city.name + area + "店，位于" + area + "核心地段，交通便利。标准连锁酒店，干净舒适，性价比高。",
    source: "generated",
    source_id: "changsha_brand_hotel_" + i,
    meal_type: "",
    recommendation: brand.name + "是知名连锁品牌，品质有保障。",
    visit_duration: 30
  });
}

pois = pois.concat(hotels);
fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
console.log("Added " + hotels.length + " brand hotels to Changsha (was " + existingHotels + ", now " + pois.filter(p => p.type === "hotel").length + ")");
