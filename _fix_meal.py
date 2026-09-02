import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('agents/scheduler_agent.py', 'r', encoding='utf-8').read()

old_slot = '''    def _find_meal_slot(stops: list, meal_type: str) -> dict:
        window = MEAL_WINDOWS.get(meal_type, MEAL_WINDOWS["lunch"])
        dur = window["duration"]
        preferred = window["default_start"]
        w_start, w_end = window["start"], window["end"]

        def _conflicts(start: int, end: int) -> bool:
            return any(start < s.get("end_minutes", 0) and end > s.get("start_minutes", 0) for s in stops)

        # Try preferred -> earlier
        for attempt in range(preferred, w_start - 30, -30):
            if not _conflicts(attempt, attempt + dur) and attempt >= w_start:
                return {"start": attempt, "end": attempt + dur}
        # Try later
        for attempt in range(preferred + 30, w_end, 30):
            if not _conflicts(attempt, attempt + dur) and attempt + dur <= w_end:
                return {"start": attempt, "end": attempt + dur}
        return {"start": preferred, "end": preferred + dur}'''

new_slot = '''    def _find_meal_slot(stops: list, meal_type: str) -> dict | None:
        """Find a non-conflicting meal slot. Returns None if no slot available."""
        window = MEAL_WINDOWS.get(meal_type, MEAL_WINDOWS["lunch"])
        dur = window["duration"]
        preferred = window["default_start"]
        w_start, w_end = window["start"], window["end"]

        def _conflicts(start: int, end: int) -> bool:
            return any(start < s.get("end_minutes", 0) and end > s.get("start_minutes", 0) for s in stops)

        # Try preferred -> earlier
        for attempt in range(preferred, w_start - 30, -30):
            if not _conflicts(attempt, attempt + dur) and attempt >= w_start:
                return {"start": attempt, "end": attempt + dur}
        # Try later
        for attempt in range(preferred + 30, w_end, 30):
            if not _conflicts(attempt, attempt + dur) and attempt + dur <= w_end:
                return {"start": attempt, "end": attempt + dur}
        # No non-conflicting slot found
        return None'''

if old_slot in content:
    content = content.replace(old_slot, new_slot)
    
    # Also fix the restaurant scheduling loop to handle None
    old_sched = '''            # Schedule restaurants
            for rest in cluster.restaurants[:2]:
                has_lunch = any(s.get("slot") == "lunch" for s in stops)
                meal_type = "dinner" if has_lunch else "lunch"
                meal_slot = self._find_meal_slot(stops, meal_type)
                stops.append({'''

    new_sched = '''            # Schedule restaurants (max 2 per day: 1 lunch + 1 dinner)
            for rest in cluster.restaurants[:2]:
                has_lunch = any(s.get("slot") == "lunch" for s in stops)
                meal_type = "dinner" if has_lunch else "lunch"
                meal_slot = self._find_meal_slot(stops, meal_type)
                if meal_slot is None:
                    logger.info("No %s slot available for %s, skipping", meal_type, rest.get("name"))
                    continue
                stops.append({'''

    content = content.replace(old_sched, new_sched)
    open('agents/scheduler_agent.py', 'w', encoding='utf-8').write(content)
    print("Fixed: _find_meal_slot returns None when no slot, scheduler skips")
else:
    print("Pattern not found")
