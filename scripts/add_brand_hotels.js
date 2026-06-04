const fs = require("fs");
const path = require("path");

const brands = [
  { name: "如家酒店", prefix: "如家快捷酒店", rating: [3.5, 4.2] },
  { name: "汉庭酒店", prefix: "汉庭酒店", rating: [3.6, 4.3] },
  { name: "7天酒店", prefix: "7天优品酒店", rating: [3.3, 4.0] },
  { name: "维也纳酒店", prefix: "维也纳国际酒店", rating: [4.0, 4.6] },
  { name: "锦江之星", prefix: "锦江之星酒店", rating: [3.5, 4.2] },
  { name: "亚朵酒店", prefix: "亚朵酒店", rating: [4.2, 4.7] },
  { name: "全季酒店", prefix: "全季酒店", rating: [4.0, 4.5] },
  { name: "格林豪泰", prefix: "格林豪泰酒店", rating: [3.4, 4.1] },
];

const cities = {
  beijing: { name: "北京", areas: ["朝阳区", "海淀区", "东城区", "西城区", "丰台区"], lat: 39.9042, lng: 116.4074 },
  shanghai: { name: "上海", areas: ["黄浦区", "静安区", "徐汇区", "浦东新区", "长宁区"], lat: 31.2304, lng: 121.4737 },
  guangzhou: { name: "广州", areas: ["天河区", "越秀区", "海珠区", "荔湾区", "白云区"], lat: 23.1291, lng: 113.2644 },
  shenzhen: { name: "深圳", areas: ["福田区", "南山区", "罗湖区", "宝安区", "龙岗区"], lat: 22.5431, lng: 114.0579 },
  chengdu: { name: "成都", areas: ["锦江区", "青羊区", "武侯区", "金牛区", "成华区"], lat: 30.5728, lng: 104.0668 },
  hangzhou: { name: "杭州", areas: ["西湖区", "上城区", "拱墅区", "滨江区", "萧山区"], lat: 30.2741, lng: 120.1551 },
  nanjing: { name: "南京", areas: ["玄武区", "秦淮区", "鼓楼区", "建邺区", "栖霞区"], lat: 32.0603, lng: 118.7969 },
  wuhan: { name: "武汉", areas: ["武昌区", "江汉区", "硚口区", "洪山区", "汉阳区"], lat: 30.5928, lng: 114.3055 },
  xian: { name: "西安", areas: ["碑林区", "莲湖区", "新城区", "雁塔区", "未央区"], lat: 34.3416, lng: 108.9398 },
  chongqing: { name: "重庆", areas: ["渝中区", "江北区", "南岸区", "沙坪坝区", "九龙坡区"], lat: 29.563, lng: 106.5516 },
  suzhou: { name: "苏州", areas: ["姑苏区", "虎丘区", "吴中区", "相城区", "工业园区"], lat: 31.299, lng: 120.5853 },
  xiamen: { name: "厦门", areas: ["思明区", "湖里区", "集美区", "海沧区", "翔安区"], lat: 24.4798, lng: 118.0894 },
  qingdao: { name: "青岛", areas: ["市南区", "市北区", "李沧区", "崂山区", "城阳区"], lat: 36.0671, lng: 120.3826 },
  sanya: { name: "三亚", areas: ["天涯区", "吉阳区", "海棠区", "崖州区"], lat: 18.2528, lng: 109.512 },
  kunming: { name: "昆明", areas: ["五华区", "盘龙区", "官渡区", "西山区", "呈贡区"], lat: 25.0389, lng: 102.7183 },
};

let totalAdded = 0;

for (const [cityDir, city] of Object.entries(cities)) {
  const poisPath = path.join("data", cityDir, "pois.json");
  if (!fs.existsSync(poisPath)) continue;

  let pois = JSON.parse(fs.readFileSync(poisPath, "utf8"));
  const existingHotels = pois.filter(p => p.type === "hotel").length;

  const hotels = [];
  for (let i = 0; i < 10; i++) {
    const brand = brands[i % brands.length];
    const area = city.areas[i % city.areas.length];
    const lat = city.lat + (Math.random() - 0.5) * 0.05;
    const lng = city.lng + (Math.random() - 0.5) * 0.05;
    const rating = +(brand.rating[0] + Math.random() * (brand.rating[1] - brand.rating[0])).toFixed(1);

    hotels.push({
      id: cityDir + "_hotel_" + i,
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
      source_id: cityDir + "_hotel_" + i,
      meal_type: "",
      recommendation: brand.name + "是知名连锁品牌，品质有保障。",
      visit_duration: 30
    });
  }

  pois = pois.concat(hotels);
  fs.writeFileSync(poisPath, JSON.stringify(pois, null, 2));
  totalAdded += hotels.length;
  console.log(city.name + ": +" + hotels.length + " hotels (was " + existingHotels + ")");
}

console.log("Total added: " + totalAdded + " hotels");
