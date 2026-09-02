import sys, re
sys.stdout.reconfigure(encoding='utf-8')
content = open('agents/scheduler_agent.py', 'r', encoding='utf-8').read()

# Find and replace _find_meal_slot
m = re.search(r'(    def _find_meal_slot\(.*?\n(?:.*?\n)*?.*?return \{"start": preferred, "end": preferred \+ dur\})', content)
if m:
    old = m.group(1)
    new = old.replace('return {"start": preferred, "end": preferred + dur}', 'return None  # No non-conflicting slot')
    content = content.replace(old, new)
    print("Fixed _find_meal_slot fallback")
else:
    print("_find_meal_slot not found")

# Find and fix the restaurant scheduling loop
m2 = re.search(r'(            # Schedule restaurants\n            for rest in cluster\.restaurants\[:2\]:\n                has_lunch = any\(s\.get\("slot"\) == "lunch" for s in stops\)\n                meal_type = "dinner" if has_lunch else "lunch"\n                meal_slot = self\._find_meal_slot\(stops, meal_type\)\n                stops\.append\(\{)', content)
if m2:
    old2 = m2.group(1)
    new2 = old2.replace(
        'meal_slot = self._find_meal_slot(stops, meal_type)\n                stops.append({',
        'meal_slot = self._find_meal_slot(stops, meal_type)\n                if meal_slot is None:\n                    continue\n                stops.append({'
    )
    content = content.replace(old2, new2)
    print("Fixed restaurant loop to skip None slots")
else:
    print("Restaurant loop not found, showing context...")
    idx = content.find("Schedule restaurants")
    if idx >= 0:
        print(content[idx:idx+400])

open('agents/scheduler_agent.py', 'w', encoding='utf-8').write(content)
