import sys
sys.stdout.reconfigure(encoding='utf-8')

content = open('agents/reviewer_agent.py', 'r', encoding='utf-8').read()

# 1. Make _check_must_visit defensive
old_check = '''    @staticmethod
    def _check_must_visit(daily_plans: list, must_visit: list) -> list[str]:
        planned = set()
        for day in daily_plans:
            for stop in day.get("stops", []):
                planned.add(stop.get("poi_name", ""))
        return [mv for mv in must_visit if not any(mv in name for name in planned)]'''

new_check = '''    @staticmethod
    def _check_must_visit(daily_plans: list, must_visit: list) -> list[str]:
        planned = set()
        for day in daily_plans:
            if not isinstance(day, dict):
                continue
            for stop in day.get("stops", []):
                if isinstance(stop, dict):
                    planned.add(stop.get("poi_name", ""))
        return [mv for mv in must_visit if not any(mv in name for name in planned)]'''

content = content.replace(old_check, new_check)

# 2. Make _hard_check defensive 
old_hard = '''    def _hard_check(self, daily_plans: list, must_visit: list, missing_must_visit: list[str]) -> list[dict]:
        issues: list[dict] = []

        # 1. Missing must-visit -> critical
        if missing_must_visit:
            issues.append({'''

new_hard = '''    def _hard_check(self, daily_plans: list, must_visit: list, missing_must_visit: list[str]) -> list[dict]:
        issues: list[dict] = []
        # Filter out non-dict items (safety)
        valid_plans = [d for d in daily_plans if isinstance(d, dict)]

        # 1. Missing must-visit -> critical
        if missing_must_visit:
            issues.append({'''

content = content.replace(old_hard, new_hard)

# Replace all "for day in daily_plans:" in _hard_check with "for day in valid_plans:"
# Need to be careful - only inside _hard_check
old_for = '''        # 2. Too many stops -> high
        for day in daily_plans:
            stops = day.get("stops", [])
            if len(stops) > 6:'''
new_for = '''        # 2. Too many stops -> high
        for day in valid_plans:
            stops = day.get("stops", [])
            if len(stops) > 6:'''
content = content.replace(old_for, new_for)

old_for2 = '''        # 3. Time overlap -> high  (uses start_minutes / end_minutes)
        for day in daily_plans:'''
new_for2 = '''        # 3. Time overlap -> high  (uses start_minutes / end_minutes)
        for day in valid_plans:'''
content = content.replace(old_for2, new_for2)

old_for3 = '''        # 4. Empty day -> critical (NOT auto-pass)
        for day in daily_plans:'''
new_for3 = '''        # 4. Empty day -> critical (NOT auto-pass)
        for day in valid_plans:'''
content = content.replace(old_for3, new_for3)

old_for4 = '''        # 5. Duplicate POI within same day -> low
        for day in daily_plans:'''
new_for4 = '''        # 5. Duplicate POI within same day -> low
        for day in valid_plans:'''
content = content.replace(old_for4, new_for4)

# 3. Make execute defensive about intent
old_intent = '''        intent = state.get("trip_intent", {})
        must_visit = intent.get("must_visit", [])
        daily_plans = state.get("daily_plans", [])'''

new_intent = '''        intent = state.get("trip_intent") or {}
        if isinstance(intent, str):
            try:
                import json as _json
                intent = _json.loads(intent)
            except Exception:
                intent = {}
        must_visit = intent.get("must_visit", []) if isinstance(intent, dict) else []
        daily_plans = state.get("daily_plans", [])'''

content = content.replace(old_intent, new_intent)

# 4. Fix the "for day in daily_plans:" in the summary builder
old_summary = '''        lines: list[str] = []
        lines.append(f"Must visit: {", ".join(must_visit) if must_visit else "none"}")
        for day in daily_plans:
            lines.append(f"\\nDay {day.get("day", 0)}:")
            for stop in day.get("stops", []):
                start = stop.get("start_minutes", 0)
                end = stop.get("end_minutes", 0)
                lines.append(f"  - {stop.get("poi_name", "")} [{start}-{end}min]")'''

new_summary = '''        lines: list[str] = []
        lines.append("Must visit: " + (", ".join(must_visit) if must_visit else "none"))
        for day in daily_plans:
            if not isinstance(day, dict):
                continue
            lines.append(f"\\nDay {day.get('day', 0)}:")
            for stop in day.get("stops", []):
                if not isinstance(stop, dict):
                    continue
                start = stop.get("start_minutes", 0)
                end = stop.get("end_minutes", 0)
                lines.append(f"  - {stop.get('poi_name', '')} [{start}-{end}min]")'''

content = content.replace(old_summary, new_summary)

with open('agents/reviewer_agent.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("ReviewerAgent patched with defensive type checks")
