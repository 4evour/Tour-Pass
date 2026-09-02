import sys
sys.stdout.reconfigure(encoding='utf-8')
content = open('agents/reviewer_agent.py', 'r', encoding='utf-8').read()

old = '        llm_issues = llm_result.get("issues", []) if isinstance(llm_result.get("issues"), list) else []'
new = '        raw_issues = llm_result.get("issues", []) if isinstance(llm_result.get("issues"), list) else []\n        llm_issues = [i for i in raw_issues if isinstance(i, dict)]'

content = content.replace(old, new)
open('agents/reviewer_agent.py', 'w', encoding='utf-8').write(content)
print("Fixed: filter non-dict LLM issues")
