# -*- coding: utf-8 -*-
"""Update regen_recommendations.py with new angles and prompts."""

# Read the file
with open('D:/Tour Pass/scripts/regen_recommendations.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the docstring
old_docstring = '"""Regenerate POI recommendations with differentiation.\n\nEach POI gets a unique "angle" for its recommendation:\n- 摄影技巧 (photography tips)\n- 历史故事 (historical stories)\n- 隐藏玩法 (hidden gems / insider tips)\n- 美食搭配 (food pairing nearby)\n- 最佳时间 (best time to visit)\n- 亲子建议 (family-friendly tips)\n- 避坑指南 (what to avoid)\n- 文化体验 (cultural experience)\n- 小众视角 (off-the-beaten-path perspective)\n"""'

new_docstring = '"""Regenerate POI recommendations with differentiation.\n\nEach POI gets a recommendation with two parts:\n1. 景点介绍: Core feature/highlight of the attraction\n2. 实用建议: Practical tip from one of 6 universal angles\n\nAngles (6 universal):\n- 隐藏玩法 (hidden gems / insider tips)\n- 最佳时间 (best time to visit)\n- 避坑指南 (what to avoid)\n- 交通攻略 (transport tips)\n- 省钱技巧 (money-saving tips)\n- 本地人推荐 (local recommendations)\n"""'

content = content.replace(old_docstring, new_docstring)

# Update the angles
old_angles = '# Recommendation angles — each POI gets a different one\nANGLES = [\n    {"key": "photography", "label": "摄影技巧", "instruction": "写一句实用的拍照建议（最佳机位、光线、构图），15字以内"},\n    {"key": "history", "label": "历史故事", "instruction": "讲一个这个景点鲜为人知的历史细节或典故，20字以内"},\n    {"key": "hidden", "label": "隐藏玩法", "instruction": "给一个本地人才知道的体验技巧，15字以内"},\n    {"key": "food", "label": "美食搭配", "instruction": "推荐附近一个具体的美食或餐厅，15字以内"},\n    {"key": "timing", "label": "最佳时间", "instruction": "说清楚什么时间段去体验最好及原因，15字以内"},\n    {"key": "family", "label": "亲子建议", "instruction": "给带小孩的家庭一个实用建议，15字以内"},\n    {"key": "avoid", "label": "避坑指南", "instruction": "提醒一个容易踩的坑或常见误区，15字以内"},\n    {"key": "culture", "label": "文化体验", "instruction": "推荐一个能深度感受当地文化的体验方式，15字以内"},\n]'

new_angles = '# Recommendation angles — 6 universal angles that apply to all POI types\nANGLES = [\n    {"key": "hidden", "label": "隐藏玩法", "instruction": "给一个本地人才知道的体验技巧，15字以内"},\n    {"key": "timing", "label": "最佳时间", "instruction": "说清楚什么时间段去体验最好及原因，15字以内"},\n    {"key": "avoid", "label": "避坑指南", "instruction": "提醒一个容易踩的坑或常见误区，15字以内"},\n    {"key": "transport", "label": "交通攻略", "instruction": "给一个具体的交通建议（地铁、公交、自驾），15字以内"},\n    {"key": "saving", "label": "省钱技巧", "instruction": "给一个省钱的小窍门（门票、优惠、免费时段），15字以内"},\n    {"key": "local", "label": "本地人推荐", "instruction": "给一个本地人才知道的推荐，15字以内"},\n]'

content = content.replace(old_angles, new_angles)

# Update the system prompt
old_system = 'system_prompt = """你是旅行攻略达人。为每个景点写一句差异化推荐语。\n\n要求：\n1. 每个景点的推荐语必须按照指定的"推荐角度"来写\n2. 语言简洁有力，像本地朋友给的建议\n3. 不要重复简介里已有的信息\n4. 不要用"推荐"、"建议"等空话开头\n5. 直接输出 JSON 数组，不要其他文字\n\n输出格式：\n[{"name": "景点名", "recommendation": "推荐语"}]"""'

new_system = 'system_prompt = """你是旅行攻略达人。为每个景点写一句推荐语。\n\n要求：\n1. 推荐语必须包含两部分：\n   - 景点介绍：用一句话概括景点的核心特色（高度、建造时间、特色等）\n   - 实用建议：按照指定的"推荐角度"写一句实用建议\n2. 两部分用句号连接，总长度控制在30-50字\n3. 语言简洁有力，像本地朋友给的建议\n4. 不要用"推荐"、"建议"等空话开头\n5. 直接输出 JSON 数组，不要其他文字\n\n输出格式：\n[{"name": "景点名", "recommendation": "推荐语"}]"""'

content = content.replace(old_system, new_system)

# Write the file
with open('D:/Tour Pass/scripts/regen_recommendations.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('脚本更新完成')
