import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')

# Replicate the cleaning
_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000026ff"
    "\U0000fe00-\U0000fe0f"
    "\U0000200d"
    "\U00002b50"
    "]+",
    flags=re.UNICODE,
)

_HASHTAG_RE = re.compile(r"#[^\s#]+")

with open('data/guangzhou/xhs_guides.json', encoding='utf-8') as f:
    notes = json.load(f)

# Debug note 1 (the one with open time)
n = notes[1]
desc = n.get('desc', '')
print('=== RAW DESC ===')
print(desc[:300])
print()

# Clean
cleaned = _EMOJI_RE.sub('', desc)
cleaned = _HASHTAG_RE.sub('', cleaned)
cleaned = re.sub(r'\s+', ' ', cleaned).strip()
print('=== CLEANED ===')
print(cleaned[:300])
print()

# Try time pattern
time_pat = re.compile(
    r'(?:开放时间|营业时间|开馆时间|开门时间)[：:]\s*'
    r'(\d{1,2}[：:]\d{2}\s*[-—~～至到]\s*\d{1,2}[：:]\d{2})'
)
m = time_pat.search(cleaned)
print(f'Time match: {m}')
if m:
    print(f'  Matched: {m.group(0)}')

# Try broader time pattern
time_pat2 = re.compile(r'(\d{1,2}[：:]\d{2})\s*[-—~～至到]\s*(\d{1,2}[：:]\d{2})')
m2 = time_pat2.search(cleaned)
print(f'Broader time match: {m2}')
if m2:
    print(f'  Matched: {m2.group(0)}')

# Try metro pattern
metro_pat = re.compile(
    r'(?:地铁|地铁线)\s*(\d+\s*号线|[A-Za-z]+\s*线)\s*'
    r'([\u4e00-\u9fff]+(?:站|口|出口))(?:.*?(?:步行|走)\s*(\d+)\s*[m米])?'
)
m3 = metro_pat.search(cleaned)
print(f'Metro match: {m3}')
if m3:
    print(f'  Matched: {m3.group(0)}')

# Check for closed day
closed = re.compile(r'(?:周[一二三四五六日天]|星期[一二三四五六日天])闭馆')
m4 = closed.search(cleaned)
print(f'Closed day match: {m4}')
if m4:
    print(f'  Matched: {m4.group(0)}')

# Check for free
free = re.compile(r'(?:免门票|免费|无需预约|不需预约|不要门票)')
m5 = free.search(cleaned)
print(f'Free match: {m5}')
if m5:
    print(f'  Matched: {m5.group(0)}')
