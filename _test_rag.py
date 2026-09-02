import sys, os
sys.stdout.reconfigure(encoding='utf-8')

try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env')
    load_dotenv('.env')
except: pass

from tools import rag

print('=== RAG Initialization ===')
cities = rag.init_rag("data")
print(f'Cities loaded: {cities}')

stats = rag.get_index_stats()
print(f'Stats: {stats}')

# Test search
print('\n=== Search tests ===')
results = rag.search_guides("广州", "广州美食推荐", top_k=3)
print(f'food query: {len(results)} results')
for r in results[:3]:
    print(f'  - {r[:80]}...')

results2 = rag.search_for_poi("广州", "广州塔", top_k=3)
print(f'\nPOI query (广州塔): {len(results2)} results')
for r in results2[:3]:
    print(f'  - {r[:80]}...')

results3 = rag.search_guides_broad("广州", categories=["xhs_tips"], top_k=3)
print(f'\nXHS tips: {len(results3)} results')
for r in results3[:3]:
    print(f'  - {r[:80]}...')
