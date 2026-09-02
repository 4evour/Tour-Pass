import sys
sys.stdout.reconfigure(encoding='utf-8')
from tools.rag import _tokenize, _corpus, _idf, _bm25_score, is_rag_ready
from tools import rag

rag.init_rag("data")
print(f'Ready: {is_rag_ready()}')
print(f'Corpus size: {len(_corpus)}')

# Check corpus
gz_docs = [d for d in _corpus if d["city"] == "guangzhou"]
print(f'Guangzhou docs: {len(gz_docs)}')
for d in gz_docs[:3]:
    print(f'  [{d["category"]}] tokens={len(d["tokens"])}: {d["text"][:60]}...')

# Debug tokenization
query = "广州美食推荐"
q_tokens = _tokenize(query)
print(f'\nQuery tokens ({len(q_tokens)}): {q_tokens[:20]}')

# Check if any doc tokens overlap with query
if gz_docs:
    doc = gz_docs[0]
    overlap = set(q_tokens) & set(doc["tokens"])
    print(f'Overlap with first doc: {overlap}')
    
    # Manual BM25 check
    score = _bm25_score(q_tokens, doc["tokens"])
    print(f'BM25 score: {score}')
    
    # Check IDF values
    for t in set(q_tokens):
        idf = _idf.get(t, 0)
        print(f'  IDF({t}) = {idf:.3f}')
