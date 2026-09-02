import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('graph.py', 'r', encoding='utf-8').read()

old_state = '''        "review_result": None,
        "tickets": [],'''

new_state = '''        "review_result": None,
        "review_feedback": None,
        "review_cycle": 0,
        "tickets": [],'''

content = content.replace(old_state, new_state)

with open('graph.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Added review_cycle and review_feedback to initial state")
