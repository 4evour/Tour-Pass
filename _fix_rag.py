import sys
sys.stdout.reconfigure(encoding='utf-8')

# Read current file
with open('tools/rag.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check if the city mapping is already there
if '_CITY_DIR_MAP' not in content:
    # Add after logger line
    content = content.replace(
        'logger = logging.getLogger(__name__)',
        """logger = logging.getLogger(__name__)

# Chinese city name -> directory name mapping
_CITY_DIR_MAP = {
    "广州": "guangzhou", "北京": "beijing", "上海": "shanghai",
    "深圳": "shenzhen", "成都": "chengdu", "重庆": "chongqing",
    "杭州": "hangzhou", "武汉": "wuhan", "南京": "nanjing",
    "西安": "xian", "长沙": "changsha", "昆明": "kunming",
    "大理": "dali", "丽江": "lijiang", "三亚": "sanya",
    "桂林": "guilin", "厦门": "xiamen", "青岛": "qingdao",
    "哈尔滨": "harbin", "苏州": "suzhou", "张家界": "zhangjiajie",
}


def _normalize_city(city: str) -> str:
    \"\"\"Map Chinese city name to directory name if needed.\"\"\"
    return _CITY_DIR_MAP.get(city, city)""",
    )

# Fix search_guides to normalize city
old1 = '    candidates = [doc for doc in _corpus if doc["city"] == city]'
new1 = '    norm_city = _normalize_city(city)\n    candidates = [doc for doc in _corpus if doc["city"] == norm_city]'
content = content.replace(old1, new1)

# Fix search_for_poi
old2 = '        if doc["city"] == city\n        and doc["category"] in ("poi_description", "xhs_tips")'
new2 = '        if doc["city"] == _normalize_city(city)\n        and doc["category"] in ("poi_description", "xhs_tips")'
content = content.replace(old2, new2)

with open('tools/rag.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
