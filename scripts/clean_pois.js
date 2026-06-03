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
    '职业学院', '职业技术', '中学', '小学', '幼儿园', '学校',
];

// ── Name whitelist: even if a name matches a blacklist pattern, keep it if it contains one of these ──
const NAME_WHITELIST_PATTERNS = [
    '博物馆', '美术馆', '科技馆',
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
