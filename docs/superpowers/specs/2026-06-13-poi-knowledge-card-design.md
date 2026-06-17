---
title: POI Knowledge Card - Data Pipeline Redesign
date: 2026-06-13
scope: data/guangzhou, agent/rag.py, agents/retrieve_agent.py, scripts/extract_xhs_tips.py
status: draft
---

# POI Knowledge Card 数据管道重设计

## 1. 背景与问题

### 当前数据现状
- 22 个城市有高德 POI 数据（pois.json）
- 仅广州有 XHS 爬取数据（xhs_guides.json，118 条）
- 广州有已提取的 XHS tips（city_tips.json，覆盖 20 个 POI）
- 所有城市有 LLM 生成的 city_guide.json 和 guidebook.json

### 核心问题
1. **XHS 数据含垃圾**：26 条限流占位符、19 条无 POI 匹配
2. **数据格式不统一**：5 套格式互不关联，agent 无法综合利用
3. **Agent 链路断层**：RetrieveAgent 只索引 LLM 生成的 city_guide + guidebook，XHS 真实攻略完全未被消费
4. **图片不再需要**：后续爬取只保留文本攻略，跳过图片

### 数据质量（广州）
| 分类 | 数量 |
|------|------|
| 总爬取 | 118 |
| 限流垃圾 | 26 |
| 无 POI 匹配 | 19 |
| 可用（tier2+） | 59 |
| 高质量（tier1） | 32 |

## 2. 设计目标

1. 每个城市生成一份 poi_knowledge.json，作为 agent 的唯一数据消费入口
2. 多来源数据（高德 POI + XHS tips + city_guide）融合到统一 schema
3. 每条 tip 带来源和可信度权重
4. 清洗脚本可复用，后续扩展到其他城市只需运行 pipeline

## 3. 数据 Schema

### poi_knowledge.json 结构

`json
{
  "city": "广州",
  "generated_at": "2026-06-13T10:00:00",
  "stats": {
    "total_pois": 200,
    "pois_with_tips": 20,
    "total_tips": 85,
    "sources": {"xhs": 59, "city_guide": 20, "llm_supplement": 0}
  },
  "pois": {
    "amap_bc53213a": {
      "name": "广州十三行博物馆",
      "type": "attraction",
      "lat": 23.1123,
      "lng": 113.2534,
      "area": "荔湾区",
      "open_time": "09:00",
      "close_time": "17:30",
      "visit_duration_minutes": 90,
      "popularity": 4.8,
      "price_level": 0,
      "tags": ["博物馆", "历史", "免费"],
      "description": "...",
      "recommendation": "...",
      "tips": [
        {
          "category": "time",
          "text": "周二-周日 09:00-17:30，周一闭馆",
          "source": "xhs",
          "source_likes": 450,
          "confidence": 0.85
        },
        {
          "category": "transport",
          "text": "地铁8号线文化公园站B口步行3分钟",
          "source": "xhs",
          "source_likes": 195,
          "confidence": 0.9
        },
        {
          "category": "photography",
          "text": "穿纯色/浅色衣服更出片，馆内灯光较暗",
          "source": "xhs",
          "source_likes": 195,
          "confidence": 0.7
        }
      ],
      "related_pois": ["amap_ca3a003e", "amap_a0d833e3"],
      "closed_days": ["Monday"],
      "free": true
    }
  }
}
`

### tip.category 枚举值
- 	ime — 开放时间、最佳到访时间、游览时长
- 	ransport — 交通方式、地铁出口、停车建议
- photography — 拍照建议、穿搭、机位
- crowd — 避坑、避人流、排队建议
- ood — 周边美食、餐厅推荐
- hidden — 隐藏玩法、本地人技巧
- general — 其他实用建议

### confidence 计算规则
- source = "xhs": base 0.7，likes > 500 → +0.1，likes > 1000 → +0.15
- source = "city_guide": base 0.5（LLM 生成）
- source = "llm_supplement": base 0.4（LLM 补充，仅在 tips 不足时使用）
- 上限 1.0

## 4. Pipeline 步骤

### Step 1: 清洗 XHS 数据
输入: data/guangzhou/xhs_guides.json
输出: data/guangzhou/xhs_clean.json

清洗规则:
1. 删除 desc 包含 "访问频繁" 的条目（限流垃圾）
2. 删除 matchedPois 为空的条目
3. 删除 desc 长度 < 30 字符的条目
4. 保留字段: 
oteId, 	itle, likes, desc, matchedPois（丢弃 images, 
oteUrl）

### Step 2: 提取 Tips
输入: data/guangzhou/xhs_clean.json
输出: data/guangzhou/xhs_tips_extracted.json

提取方式: 复用现有 scripts/extract_xhs_tips.py 的规则+LLM 提取逻辑
- 规则匹配: 开放时间、门票、交通、拍照等模式
- LLM 提取: 从长文中提取结构化 tips（仅在规则匹配不足时调用）
- 按 POI 聚合，按 category 分类

### Step 3: 融合生成 poi_knowledge.json
输入:
- data/guangzhou/pois.json（高德 POI）
- data/guangzhou/xhs_tips_extracted.json（XHS tips）
- data/guangzhou/city_tips.json（已有提取结果）
- data/guangzhou/city_guide.json（LLM 生成）

输出: data/guangzhou/poi_knowledge.json

融合逻辑:
1. 以 pois.json 为基础，每个 POI 创建一条记录
2. 从 xhs_tips_extracted.json 和 city_tips.json 合并 tips（去重，XHS 优先）
3. 从 city_guide.json 提取 POI 相关建议作为补充 tips（仅在 XHS tips 不足时）
4. 从 XHS 笔记中提取 closed_days 和 ree 字段
5. 从 matchedPois 推导 elated_pois（同一笔记中出现的 POI 互相关联）
6. 计算每条 tip 的 confidence

### Step 4: 接入 Agent
修改 gent/rag.py:
- 新增 ingest_poi_knowledge() 函数，索引 poi_knowledge.json
- 每个 POI 的 tips 合并为一个 chunk，带 POI name 作为检索关键词
- 保留原有 ingest_city_guide 和 ingest_guidebook 作为 fallback

修改 gents/retrieve_agent.py:
- 优先从 poi_knowledge.json 检索
- 查询逻辑: 按 interest + must_visit + category 组合检索
- 返回时附带 tips 的 confidence，供下游 agent 参考

修改 gents/scheduler_agent.py:
- 读取 POI 的 closed_days，自动避开闭馆日
- 读取 	ips 中 	ime 类别的建议，优化时间安排

## 5. 不做的事

- 不重新爬取 XHS 数据（现有数据够用）
- 不爬取 XHS 图片（只要文本攻略）
- 不修改 agent 架构（只改数据消费方式）
- 不动其他城市的数据（后续推广时复用 pipeline）
- 不引入新的依赖或数据库（保持 JSON 文件存储）

## 6. 文件变更清单

### 新增
- scripts/build_poi_knowledge.py — 融合 pipeline（Step 1-3 合并）
- data/guangzhou/poi_knowledge.json — 生成产物
- data/guangzhou/xhs_clean.json — 中间产物

### 修改
- gent/rag.py — 新增 ingest_poi_knowledge()
- gents/retrieve_agent.py — 优先从 poi_knowledge 检索
- gents/scheduler_agent.py — 读取 closed_days 和 tips

### 不变
- data/guangzhou/pois.json — 原始数据不动
- data/guangzhou/xhs_guides.json — 原始数据不动
- data/guangzhou/city_guide.json — 原始数据不动
- 所有其他城市的文件

## 7. 验证方式

1. 运行 python scripts/build_poi_knowledge.py --city guangzhou
2. 检查 poi_knowledge.json 的 stats 和 POI 数量
3. 运行现有测试: python -m pytest tests/
4. 手动测试: 用多 agent 系统生成广州 3 天行程，对比前后效果
