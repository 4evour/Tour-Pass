import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('agents/reviewer_agent.py', 'r', encoding='utf-8').read()

old = '''        if not daily_plans:
            review = {'''

new = '''        # Debug: log types
        if daily_plans:
            first = daily_plans[0]
            logger.info("Reviewer debug: daily_plans[0] type=%s, value=%s",
                        type(first).__name__, str(first)[:100])
        if not daily_plans:
            review = {'''

if old in content:
    content = content.replace(old, new)
    open('agents/reviewer_agent.py', 'w', encoding='utf-8').write(content)
    print("Debug log added")
else:
    print("Pattern not found")
