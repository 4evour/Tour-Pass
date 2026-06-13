"""Shared POI filtering logic for data cleanup scripts.

Usage:
    from poi_filters import (
        filter_attractions, filter_restaurants, filter_hotels, filter_transit,
        MALL_PATTERNS, HOTEL_KEYWORDS, EDUCATION_KEYWORDS, CHAIN_RESTAURANTS,
    )
"""
import re

MALL_PATTERNS = [
    '购物广场','购物中心','商业广场','商贸城','百货大楼','百货商场',
    '奥特莱斯','outlets','Outlets','万达广场','天河城','太古汇','万菱汇','K11','SKP','蓝色港湾',
    '颐堤港','芳草地','华贸中心','国贸商城','新天地','合生汇',
    '大悦城','万象城','万象汇','天街','印象城','来福士',
    '银泰百货','银泰城','世纪金源','荟聚','熙地港',
    '群光广场','世茂广场','协信星光','和悦广场','星光广场',
    '凯德广场','凯德MALL','正佳广场','安华汇','花城汇','太古里',
    '恒隆广场','华润万象','宝龙广场','九方','海岸城',
    '茂业百货','天虹','德基广场','虹悦城','水游城',
    '龙湖里','吾悦广场','芮欧百货','嘉里城','静安嘉里',
    '过载空间','西红门','WellTown','融城','丽泽天街',
    '龙德广场','银座和谐','龙湖北京','北京朝阳','北京SKP','北京超极','北京清河','北京亦庄',
    '北京大兴','北京丽泽','北京长楹','首开通州','西北旺',
    '北京东方新天地','劝业场','中关村ARTPARK','新光界',
    '永旺梦乐城','骏壹万邦','百信广场','奥园广场',
    '海印广场','中华广场','广百百货','摩登百货','新大新',
    '友谊商店','丽柏广场','国金中心','天德广场','合汇广场',
    '壹方城','星河COCO','保利广场','悦汇广场','侨光广场',
    '花城湾','嘉裕太阳城','壹号广场','环贸iapm','前滩太古里','BFC外滩金融中心',
]
HOTEL_KEYWORDS = ['度假酒店','度假村','大酒店','酒店','宾馆','客栈','民宿','公寓酒店','温泉度假','度假区酒店','青年旅社','旅馆','招待所','温泉酒店','会所','养生馆','洗浴','温泉中心','汤泉']
EDUCATION_KEYWORDS = ['学校','大学(?!城)','中学','小学','幼儿园','教育(?!园)','培训','辅导','补习','公考','公务员','学而思','好未来','猿辅导','作业帮','华图教育','中公教育','粉笔教育','金榜公考','芒果公考','驾校','职业技术学校','研究所(?!生)']
CHAIN_RESTAURANTS = ['星巴克','STARBUCKS','肯德基','KFC','麦当劳','必胜客','汉堡王','赛百味','达美乐','棒约翰','真功夫','吉野家','味千拉面','海底捞','呷哺呷哺','湊湊火锅','巴奴毛肚','小龙坎','德庄','外婆家','绿茶餐厅','西贝莜面村','太二酸菜鱼','探鱼','蛙来哒','老乡鸡','乡村基','大米先生','永和大王','面点王','李先生','鼎泰丰','一兰拉面','奈雪的茶','喜茶','瑞幸','Manner','茶颜悦色','Coco都可','一点点','书亦烧仙草','古茗','茶百道','沪上阿姨','霸王茶姬','蜜雪冰城','益禾堂','甜啦啦','七分甜','绝味鸭脖','周黑鸭','煌上煌','紫燕百味鸡','袁记云饺','饺子里','大鸽饭','DQ','哈根达斯','满记甜品','许留山','全聚德','便宜坊','东来顺']
GENERIC_REST_NAMES = ['早茶饭市','粤式早茶','早茶正餐','内设早茶','宵夜','美食城','美食街','茶室','茶馆','甜品站','小吃街','夜市美食广场']

TRANSIT_SKIP = [
    '地铁站','公交站','进站口','出站口','出发','到达','国内出发','国际出发','国内到达','国际到达','港澳台',
    '卫星厅','航站楼','公务机','城市航站','客舱服务','航空客货','已关闭','通用机场','直升机场','候机楼','候机厅',
    '落客区','候车区','停车场','换乘','休息室','环卫','停靠点','交通枢纽','长途','货运','建设中','运行基地','城市候机',
    '贵宾','VIP','vip','大巴车场','出租车服务','商务贵宾','暂停营业','乘车点','上客区','出发厅','明珠贵宾',
]
TRANSIT_FORCE_KEEP = {'广州白云国际机场'}
TRANSIT_FORCE_REMOVE = {'沙湾机场','黄埔穗港澳直升机机场','从化良口机场'}


def is_mall(n): return any(k in n for k in MALL_PATTERNS)
def is_edu(n): return any(re.search(k, n) for k in EDUCATION_KEYWORDS)
def is_hotel(n): return any(k in n for k in HOTEL_KEYWORDS)

def brand_key(name):
    b = re.sub(r'[(（].*?[)）]', '', name)
    return b.strip()[:6]

def norm_station(name):
    return re.sub(r'[(（].*?[)）]', '', name).strip()

def is_valid_transit(name):
    if name in TRANSIT_FORCE_KEEP: return True
    if name in TRANSIT_FORCE_REMOVE: return False
    for kw in TRANSIT_SKIP:
        if kw in name: return False
    return True


def filter_attractions(pois):
    attrs = [p for p in pois if p.get('type') == 'attraction']
    attrs = [p for p in attrs if '-' not in p['name'] and '\u2014' not in p['name']]
    attrs = [p for p in attrs if '\u4e0d\u5bf9\u5916' not in p.get('name', '')]
    attrs = [p for p in attrs if not is_mall(p['name'])]
    attrs = [p for p in attrs if not is_edu(p['name'])]
    attrs = [p for p in attrs if '电视台' not in p['name'] and 'TV' not in p['name'].upper()]
    attrs = [p for p in attrs if not is_hotel(p['name'])]
    attrs = [p for p in attrs if '度假区' not in p['name'] or '旅游' in p['name']]
    cruise = [p for p in attrs if '\u591c\u6e38' in p['name'] and '\u73e0\u6c5f' in p['name']]
    rest = [p for p in attrs if not ('\u591c\u6e38' in p['name'] and '\u73e0\u6c5f' in p['name'])]
    if cruise:
        cruise.sort(key=lambda p: -p.get('popularity', 0))
        rest.append(cruise[0])
    rest.sort(key=lambda p: -p.get('popularity', 0))
    return rest


def filter_restaurants(pois):
    rests = [p for p in pois if p.get('type') == 'restaurant']
    rests = [p for p in rests if not any(k in p['name'] for k in GENERIC_REST_NAMES)]
    rests = [p for p in rests if not any(k in p['name'] for k in CHAIN_RESTAURANTS)]
    groups = {}
    for r in rests:
        groups.setdefault(brand_key(r['name']), []).append(r)
    deduped = []
    for g in groups.values():
        g.sort(key=lambda p: -p.get('popularity', 0))
        deduped.append(g[0])
    deduped.sort(key=lambda p: -p.get('popularity', 0))
    return deduped


def filter_hotels(pois):
    hotels = [p for p in pois if p.get('type') == 'hotel']
    hotels = [p for p in hotels if p.get('source_id')]
    hotels = [p for p in hotels if p.get('popularity', 0) > 0]
    return hotels


def filter_transit(pois):
    transits = [p for p in pois if p.get('type') == 'transit']
    filtered = [p for p in transits if is_valid_transit(p['name'])]
    groups = {}
    for p in filtered:
        groups.setdefault(norm_station(p['name']), []).append(p)
    deduped = []
    for g in groups.values():
        g.sort(key=lambda p: -p.get('popularity', 0))
        deduped.append(g[0])
    airports = [p for p in deduped if '机场' in p['name']][:2]
    stations = [p for p in deduped if '机场' not in p['name'] and p['name'].endswith('站') and '客运' not in p['name'] and '汽车' not in p['name']][:5]
    return airports + stations
