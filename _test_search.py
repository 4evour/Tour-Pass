import sys
sys.stdout.reconfigure(encoding='utf-8')
from tools.rag import _tokenize, _corpus, _bm25_score, search_guides
from tools import rag

rag.init_rag("data")

# Direct search_guides call with debug
city = "guangzhou"
query = "广州美食推荐"
print(f'search_guides("{city}", "{query}")')
results = search_guides(city, query, top_k=5)
print(f'Results: {len(results)}')

# Manual test
q_tokens = _tokenize(query)
candidates = [doc for doc in _corpus if doc["city"] == city]
print(f'Candidates for {city}: {len(candidates)}')

scored = []
for doc in candidates:
    score = _bm25_score(q_tokens, doc["tokens"])
    if score > 0:
        scored.append((score, doc["text"][:60]))

scored.sort(key=lambda x: x[0], reverse=True)
print(f'Scored > 0: {len(scored)}')
for s, t in scored[:5]:
    print(f'  {s:.3f}: {t}...')
