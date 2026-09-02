import sys
sys.stdout.reconfigure(encoding='utf-8')
from tools import rag
rag.init_rag("data")

results = rag.search_guides("广州", "广州美食推荐", top_k=3)
print(f'Chinese city search: {len(results)} results')
for r in results[:3]:
    print(f'  - {r[:80]}')

results2 = rag.search_for_poi("广州", "广州塔", top_k=3)
print(f'\nPOI search: {len(results2)} results')
for r in results2[:3]:
    print(f'  - {r[:80]}')

results3 = rag.search_guides_broad("广州", categories=["xhs_tips"], top_k=3)
print(f'\nXHS tips: {len(results3)} results')
for r in results3[:3]:
    print(f'  - {r[:80]}')
