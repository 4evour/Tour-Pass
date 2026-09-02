import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')

# Safer emoji removal - only actual emoji codepoints
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FAFF"  # extended-A
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # ZWJ
    "]+",
    flags=re.UNICODE,
)

desc = '「当玻璃柜里的广彩瓷闪着光，我好像真的听见了两百年前的潮汐声。」\n原来广州的繁华，早就在十三行的码头边泊岸🌊——\n📌【实用TIPS】\n🕘开放时间：9:00-17:30（周一闭馆/法定节假日除外）\n🎫门票：免费！无需预约！！入馆参观请出示有效证件（如身份证、学生证、老人证、护照、港澳通行证等）\n🎺免费定时讲解服务时间：上午：10:00/下午：15:00\n🚇交通：地铁6/8号线文化公园站B口步行3分钟（文化公园内）\n👗穿搭建议：新中式/浅色系更出片'

# Method 1: remove specific emoji codepoints only
cleaned1 = _EMOJI_RE.sub('', desc)
cleaned1 = re.sub(r'\s+', ' ', cleaned1).strip()
print('=== Method 1 (precise ranges) ===')
print(cleaned1[:200])
print()

# Method 2: keep only CJK + ASCII + common punctuation
cleaned2 = re.sub(r'[\U00010000-\U0010ffff]', '', desc)  # remove all supplementary plane (emoji live here)
cleaned2 = re.sub(r'[\u2600-\u27BF]', '', cleaned2)  # remove misc symbols block  
cleaned2 = re.sub(r'\s+', ' ', cleaned2).strip()
print('=== Method 2 (supplementary plane) ===')
print(cleaned2[:200])
print()

# Method 3: simplest - just strip chars above U+FFFF (all emoji are there)
cleaned3 = ''.join(c for c in desc if ord(c) <= 0xFFFF)
cleaned3 = re.sub(r'\s+', ' ', cleaned3).strip()
print('=== Method 3 (filter > U+FFFF) ===')
print(cleaned3[:200])
