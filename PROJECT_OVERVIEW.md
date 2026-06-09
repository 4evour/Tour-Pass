# PROJECT_OVERVIEW

## ��ĿĿ��
- �ṩ������������е��г̹滮����֧����Ȼ���Ժͽṹ������������ڡ�
- ���ɶ��ѡ�������г̣���չʾ�ɽ��͵����֡�ͨ�ڡ�ʱ�䴰�������ָ�ꡣ
- ���㷨�ɸ��֡���ѹ�⡢����ʾΪ���Ķ�λ����� LLM ��ǿ�ظ�������������Ϊ�滮��·����

## ����ջ
- **���**��C++17������ cpp-httplib �ṩ REST API��
- **������洢**��
lohmann/json��sqlite3����ѡ PostgreSQL������������ data/ �� JSON Ϊ����
- **�滮�㷨**��Dijkstra / A* ���·��Beam Search ����ʱ��۹滮��BM25 ������Pareto ��Ŀ������
- **LLM ����**������ OpenAI/DeepSeek ��� Chat Completions��Ĭ��֧�� config/llm.local.json �򻷾�����ע�롣
- **ǰ��**��Leaflet + ԭ�� JS ��Ӧ�ã����� web/editor �� React/Vite/Tailwind �г̱༭����
- **���̻�**��MinGW Make �� CMake ˫������Docker ��׶ξ���GitHub Actions CI��Render ����ݰ���

## Ŀ¼�ṹ
- src/����˺���ʵ�֣�API���滮��������ͼ��LLM���洢������ʱ����
- include/tourpass/������ͷ�ļ�������ģ�͡�
- 	hird_party/�����õ�����������httplib��json��sqlite3����
- web/��ǰ��ҳ�桢������Ⱦ�������̨��༭����
- data/������ POI��ͨ�ڱ����ݣ�config/��AMap �� LLM ����ģ�塣
- scripts/�����ݲɼ�����ϴ��У�顢ѹ����ð�̽ű���
- 	ests/��C++ ������ؼ� Node ���Խű���
- docs/��OpenAPI������˵������������

## ��������
1. �û�������� /trip/plan��/trip/chat ���첽 /trip/jobs��
2. ��˰����в��Ҷ�Ӧ CityBundle�����а��� PoiGraph��TripPlanner��SearchEngine��
3. /trip/chat ʹ�� LLM ������ͼ����ͨ�� BM25 ƥ�� POI���ṹ������ֱ�ӽ���滮��
4. �滮��·������ Beam Search��������/���/����/���/���ʱ�������������״̬���С�
5. ���ɶ����ѡ�����󣬽��� Pareto �ֲ�������Զ����������� LLM ������Ȼ���Խ��͡�
6. ǰ�˶�ȡ��ѡ������·�����㷨������Ϣ������ Leaflet ��ͼ����Ⱦ·����վ�����顣

## �ؼ�Լ��
- �������ͨ������������ config/llm.local.json ע�룬�����ڲ�Ӳ������Կ��
- API Key У����ó���ʱ��Ƚϣ������ϣʹ�� PBKDF2��
- ���� SQL ����������ʾ���ݲ���ͬ��ʵ��ͼ��ʵʱ�չݻ����� SLA��
- ���� Demo ��������ʵ�ʲ���֤��һ�£�����Ѳݰ��������������߷���

## ���������
- **���ع���**��mingw32-make build��mingw32-make run
- **CMake ����**��cmake -S . -B build��cmake --build build
- **����**��mingw32-make test �� CMake �� ctest --test-dir build
- **����У��**��mingw32-make validate-data
- **����ð��**��
ode scripts/container_smoke.js http://127.0.0.1:8080
- **��׼����**��
ode scripts/benchmark.js ...

## ��֪����
- Ĭ�ϳ������ݿ����ͺ���������� POI ��ͨ�ڱߡ�
- LLM ������ɿأ��豣���㷨��·���������á�
- SQLite Ϊ���ظ����洢����������޳־þ�ᶪʧ�滮��ʷ��
- ѹ����ð�̽������ӳ��ǰ����������ֱ�ӵ�ͬ���� SLA��

## AI Agent ����2026-06 ������
- **Python Agent ����**������ LangGraph + DeepSeek-V3 �����й滮 Agent���˿� 8090��
- **�ܹ�**���û����� �� ��ͼ���� �� RAG ���Լ��� �� ���� POI/�Ƶ����� �� �Ƶ�ê��ѡ�� �� ÿ�չ滮 �� Beam Search ·���Ż� �� ��ʽ�����
- **���ݲ���**���������ȣ�C++ ��� POI/�Ƶ�� + ͨ��ͼ�����ߵ� MCP �������䡣
- **RAG**��ChromaDB �洢���й��ԣ�city_guide + wikivoyage + POI ������������������
- **����**���������棨�����г�Ԥ���� + Redis �г̼����� + �ڴ滺�棩��
- **���� C++ API**��`/api/travel-time`��`/api/optimize-route`��`/api/city-guide`��`/api/cities`��
- **ǰ��**��`AgentChat.tsx`����ʽ�Ի�����`StreamingItinerary.tsx`����ʽ�г���Ⱦ����`HotItineraries.tsx`�������г̣���`QuickCustomize.tsx`�����ٵ�������
- **���**��`pip install -r agent/requirements.txt` �� `python -m uvicorn agent.main:app --port 8090`��
- **RAG ���**��`python scripts/ingest_rag.py`��


## �����޸� (2026-06-09)

### Agent �����޸�
- **����**��C++ ��� /agent/* ����ʹ�� httplib::Client ����������Ӧ��SSE ��ʽ���䲻������
- **����**��pre_routing_handler �� body ��ȡǰ���У�POST body Ϊ�ա�
- **�޸�**��������� pre_routing_handler ������ʽ·�ɴ�������server.Get/Post����ʹ�� WinHTTP ԭʼ���� + set_chunked_content_provider ʵ�� SSE ��ʽ�����
- **�ṹ**��WinHttpStreamState RAII �ṹ�������������ڣ�chunked content provider �ص�����ȡ�������ݡ�

### ǰ���޸�
- **����**��main.tsx ʹ�� NewEditorApp ���� App��Agent �����AgentChat��HotItineraries �ȣ�δ�����롣
- **�޸�**���� NewEditorApp.tsx ����� AiChat ����������Ⱦ��
- **����**������˳�����/ ���� /editor ���·��� dev HTML��
- **�޸�**����������˳��/editor �� / ֮ǰע�ᡣ

### ��ǰ״̬
- **C++ ���**���˿� 8080��21 ���� 15140 POI
- **Agent ����**���˿� 8090��DeepSeek-V3 ����
- **ǰ��**��/editor/ ��ȷ���� Agent ���
- **SSE ��ʽ**������֧�֣�Content-Type: text/event-stream
- **����**���ڴ滺�湤�����ڶ������� < 5s
- **�����**��ChromaDB RAG embedding ģ�����ء�Redis ���桢�����г�Ԥ����


## CI �޸� (2026-06-09)

### ������֤�޸�
- **����**��156 �� POI �� price_level=0����֤�ű�Ҫ�� 1..5 ��Χ��
- **�޸�**�������� price_level=0 ��Ϊ price_level=1��Ӱ�� 21 �����й� 7688 �� POI����

### �ظ�������
- **����**��414 ���ظ�����ߣ�A->B �� B->A ͬʱ���ڣ���
- **�޸�**��ȥ�غ���Ψһ��Ŀ����ȥ�� 2620 ���ظ��ߣ���

### API Smoke ����
- **����**��api_smoke.ps1 Ӳ���� expectedPoiCount=461��ʵ��Ϊ 15140��
- **�޸�**������ minPoiCount=100 ����Сֵ��顣

### Docker ����
- **����**��Dockerfile �� entrypoint.sh �� UTF-8 BOM������ bash ����ʧ�ܡ�
- **�޸�**���Ƴ� BOM����� .gitattributes ǿ�� LF ��β��

### ��ǰ״̬
- CI ȫ��ͨ����CMake (Windows) + CMake (Ubuntu) + Docker smoke
- 21 ���� 15140 POI��2034 ���ߣ������ݼ���

## ���������޸� (2026-06-09)

### P0-Critical ��ȫ�޸�
- **SQL ע���޸�**��`cleanupExpiredGuests` ���ò�������ѯ������ SQL ƴ�ӷ��ա�
- **�����ϣ��ȫ**��`hashPassword` ��Ӱ汾ǰ׺ `v2:`��`verifyPassword` ֧�ְ汾ʶ�𣬱����㷨��ƥ�䡣
- **����ʱ��Ƚ�**��`constantTimeEquals` �޸�����й©��ʼ�ձ����ϳ����ȡ�

### P1-High �߼��޸�
- **optimizeDayOrder**���޸�δд���Ż������ bug������ `day.stops` �����Ϊ�Ż����˳��
- **�ߵ� API**��`fetchFromAmap` ���� `/v3/direction/walking` ���нӿڣ�ƥ��������γ�����
- **findPoi �ݹ�**����Ϊ������ѯ�����������ݵ���ջ�����

### P2-Medium �����Ż�
- **buildScoreBreakdown**���ϲ����ͺ�����ͳ��ѭ���������ظ�������
- **Dijkstra ����**��`computeSingleSourceShortestMinutes` ���� `size_t idx` ��� `std::string`�������ַ���������
- **������������**��`SearchEngine::search` ʹ�� `invertedIndex_` �����ĵ�Ƶ�ʣ����� O(N) ȫ��ɨ�衣
- **LLM �ͻ���**��HTTPS ģʽ��Ҳ��ʼ���־û� HTTP client��֧�����Ӹ��á�
- **ʱ�����**��`parseTimeToMinutes` ֧�� `H:MM` �� `HH:MM` ���ָ�ʽ��
- **ʱ���ʽ��**��`formatMinutes` ���� clamp ��� modulo�����ⳬʱ��ʾ����

### P2-Medium ��ȫ�뽡׳��
- **LLM ��Ӧ����**��`parseChatCompletionContent` ��Ӱ�ȫ��飬�������Ӧ������
- **���ֱ�ǩͳһ**��`scoreBreakdown` ��Ӣ�ı�ǩͳһΪ���ġ�
- **defaultCity ѡ��**���Ƴ����� `unordered_map` ����˳��������֧��

### ��ǰ״̬
- ���޸� 3 �� P0-Critical��3 �� P1-High��8 �� P2-Medium ���⡣
- ʣ�� P2/P3 ����Ϊ�����Ż��ʹ��������Ľ�����Ӱ����Ĺ�����ȷ�ԡ�

## must_visit 景点修复 (2026-06-09)

### 问题描述
用户在提示词中强烈要求去长城和故宫，但行程中始终不包含这些景点。

### 根因分析
1. **数据缺失**：北京 POI 数据库中没有"八达岭长城"（最热门的长城段），只有"司马台长城旅游区"。
2. **匹配缺陷**：select_pois_and_hotels 用精确名称匹配检查 must_visit，"长城"匹配不到任何 POI 名称，仅输出警告。
3. **LLM 提示词无强制约束**：DAY_PLANNING_SYSTEM 告诉 LLM "从候选中选择最适合的"，未提及 must_visit 必须包含。即使 must_visit POI 进入候选列表，LLM 也可能跳过。
4. **无后处理验证**：LLM 返回后未检查 must_visit 是否被包含。

### 修复内容
- **数据**：在 beijing/pois.json 中添加"八达岭长城"和"慕田峪长城"。
- **匹配**：select_pois_and_hotels 改用子串模糊匹配（"长城" 匹配 "八达岭长城"）。
- **提示词**：DAY_PLANNING_SYSTEM 首条规则改为"必须包含标记为必去的景点"；候选列表中标注【必去】；user_context 明确列出必去景点名称。
- **后处理验证**：plan_each_day 在 LLM 返回后检查 must_visit POI 是否在 stops 中，缺失时强制注入。
- **搜索范围**：search_pois limit 从 100 增加到 200，确保远郊景点（如延庆区的八达岭长城）被检索到。

## Agent 数据加载与鲁棒性修复 (2026-06-09)

### 问题描述
- "Failed to fetch" 错误：Agent 服务无法加载 POI 数据，LLM 凭训练数据生成泛化内容。
- must_visit 景点（长城、故宫）始终不出现。

### 根因分析
1. **C++ 后端未运行**：端口 8080 被其他应用占用，Agent 的 POI/酒店搜索全部 404。
2. **无本地数据 fallback**：search_pois/search_hotels 失败后直接返回空列表。
3. **城市名映射缺失**：数据目录用英文名（beijing），LLM 输出中文名（北京），路径不匹配。
4. **故宫子景点污染**："故宫" 子串匹配到几十个子景点（钦安殿、永寿宫等），must_visit 验证全部注入。
5. **Pydantic 验证脆弱**：LLM 返回 avoid=""（空字符串）而非 []，导致意图解析崩溃。
6. **城市名 fallback 粗暴**：user_message[:4] 截取 "去北京3" 作为城市名。

### 修复内容
- **tools.py**：search_pois/search_hotels 失败时自动从 data/{city}/pois.json 加载；添加 _CITY_DIR_MAP 中英文城市名映射。
- **models.py**：TripIntent 添加 field_validator，兼容 LLM 返回空字符串/字符串天数。
- **graph.py / graph_simple.py**：must_visit 匹配改为"每个关键词只取最佳匹配"（最短名称 + 最高 popularity）；城市名 fallback 改为已知城市列表匹配。
- **prompts.py**：DAY_PLANNING_SYSTEM 首条规则改为强制包含 must_visit。