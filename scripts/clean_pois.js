/**
 * POI Data Cleaning Script
 *
 * Removes POIs that are not tourist-relevant (schools, companies, hospitals,
 * residential areas, etc.) from all city POI JSON files.
 *
 * Usage: node scripts/clean_pois.js
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');

// ── Blacklist terms that match POI tags (exact match) ──
const TAG_BLACKLIST = new Set([
    '学校', '职业技术学校', '职业技术学院', '中学', '小学', '幼儿园', '大学', '学院',
    '公司企业', '公司', '工厂',
    '政府机构', '派出所', '消防队',
    '医院', '诊所', '药店', '殡仪馆', '墓地',
    '加油站', '停车场', '收费站', '住宅区', '小区',
]);

// ── Name patterns that indicate non-tourist POIs ──
const NAME_BLACKLIST_PATTERNS = [
    // 学校类
    '职业学院', '职业技术', '中学', '小学', '幼儿园', '学校',
    // 批发/市场类（非旅游市场）
    '批发市场', '批发城', '批发部', '批发', '二手手机', '二手市场',
    '手机维修', '手机回收', '电脑维修', '电子市场',
    '经营部', '用品批发', '商贸城', '小商品城',
    // 医疗/殡葬类
    '殡仪馆', '殡葬', '公墓', '墓地',
    '诊所', '卫生院', '卫生室', '社区卫生服务中心',
    // 交通设施（非旅游）
    '加油站', '加气站', '充电站',
    '停车场', '收费处', '收费站',
    // 住宅/物业
    '住宅区', '小区', '公寓楼',
    // 公交/地铁站（非旅游线路）
    '公交站', '地铁站',
    // 其他非旅游
    '废品', '回收站', '垃圾', '污水处理',
    '工厂', '仓库', '物流园',
    '网吧', '棋牌室', '台球',
    // 科研/办公机构
    '研究院', '研究所', '研究中心', '实验室', '检测中心',
    '办事处', '事务所', '写字楼', '商务中心',
    // 工业/仓储
    '工业园', '产业园', '科技园', '开发区',
    // 其他非旅游
    '殡仪馆', '火葬场', '陵园', '公墓',
    '驾校', '培训中心', '培训机构',
    '养老院', '敬老院', '福利院',
    '戒毒所', '看守所', '拘留所',
];

// ── Name whitelist: even if a name matches a blacklist pattern, keep it if it contains one of these ──
const NAME_WHITELIST_PATTERNS = [
    // 文化场馆
    '博物馆', '美术馆', '科技馆', '展览馆', '纪念馆', '故居', '旧址',
    // 夜市/美食街（旅游热点）
    '夜市', '早市', '美食街', '小吃街', '步行街', '老街', '古街',
    // 住宿（旅游相关）
    '民宿', '酒店', '旅馆', '宾馆', '客栈', '青年旅舍',
    // 景点类
    '古城', '古镇', '古村', '古建筑',
    '景点', '景区', '公园', '广场', '风景区',
    '寺', '庙', '教堂', '清真寺',
    '塔', '楼', '阁', '亭', '桥',
    '山', '湖', '河', '江', '海', '岛',
    // 特色街区
    '步行街', '商业街', '文化街', '美食城',
    // 剧院/演出
    '剧院', '剧场', '电影院',
];

/**
 * Check whether a POI should be removed based on its tags.
 */
function hasBlacklistedTag(tags) {
    if (!Array.isArray(tags)) return false;
    return tags.some(tag => TAG_BLACKLIST.has(tag));
}

/**
 * Check whether a POI should be removed based on its name.
 * Returns true if the name matches a blacklist pattern AND does NOT match a whitelist pattern.
 */
function hasBlacklistedName(name) {
    if (!name) return false;

    // If the name contains any whitelist term, keep it
    if (NAME_WHITELIST_PATTERNS.some(wl => name.includes(wl))) {
        return false;
    }

    return NAME_BLACKLIST_PATTERNS.some(bl => name.includes(bl));
}

/**
 * Find all POI JSON files in the data directory.
 */
function findPoiFiles() {
    const files = [];

    // data/pois.json (changsha)
    const rootPois = path.join(DATA_DIR, 'pois.json');
    if (fs.existsSync(rootPois)) {
        files.push({ city: 'changsha', filePath: rootPois });
    }

    // data/<city>/pois.json
    const entries = fs.readdirSync(DATA_DIR, { withFileTypes: true });
    for (const entry of entries) {
        if (entry.isDirectory()) {
            const poisFile = path.join(DATA_DIR, entry.name, 'pois.json');
            if (fs.existsSync(poisFile)) {
                files.push({ city: entry.name, filePath: poisFile });
            }
        }
    }

    return files;
}

/**
 * Clean a single POI file: filter out blacklisted POIs, write back, return stats.
 */
function cleanFile(filePath) {
    const raw = fs.readFileSync(filePath, 'utf-8');
    const pois = JSON.parse(raw);
    const original = pois.length;

    const kept = pois.filter(poi => {
        if (hasBlacklistedTag(poi.tags)) return false;
        if (hasBlacklistedName(poi.name)) return false;
        return true;
    });

    const removed = original - kept.length;

    if (removed > 0) {
        fs.writeFileSync(filePath, JSON.stringify(kept, null, 2) + '\n', 'utf-8');
    }

    return { original, removed, remaining: kept.length };
}

// ── Main ──
function main() {
    const files = findPoiFiles();
    if (files.length === 0) {
        console.error('No POI files found in data/ directory.');
        process.exit(1);
    }

    console.log(`Found ${files.length} city POI file(s).\n`);
    console.log('City              | Original | Removed | Remaining');
    console.log('------------------|----------|---------|----------');

    let totalOriginal = 0;
    let totalRemoved = 0;
    let totalRemaining = 0;

    for (const { city, filePath } of files) {
        const stats = cleanFile(filePath);
        totalOriginal += stats.original;
        totalRemoved += stats.removed;
        totalRemaining += stats.remaining;

        const cityPadded = city.padEnd(18);
        const origPadded = String(stats.original).padStart(8);
        const remPadded = String(stats.removed).padStart(7);
        const keptPadded = String(stats.remaining).padStart(9);
        console.log(`${cityPadded}| ${origPadded} | ${remPadded} | ${keptPadded}`);
    }

    console.log('------------------|----------|---------|----------');
    const totalOrigPadded = String(totalOriginal).padStart(8);
    const totalRemPadded = String(totalRemoved).padStart(7);
    const totalKeptPadded = String(totalRemaining).padStart(9);
    console.log(`${'TOTAL'.padEnd(18)}| ${totalOrigPadded} | ${totalRemPadded} | ${totalKeptPadded}`);

    console.log('\nDone. Cleaned POI files written back in place.');
}

main();
