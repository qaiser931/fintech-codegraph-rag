"""Show where process_jazzcash_callback ranks for the semantic query."""

from src.config import settings
from src.ingestion.indexer import CodebaseIndexer

indexer = CodebaseIndexer()
indexer.index_codebase(settings.sample_codebase_dir, base_dir=settings.base_dir)

query = "code that holds a database lock while making a network call"
hits = indexer.vector_index.search(query, role="Senior Dev", top_k=20)
for rank, (chunk, score) in enumerate(hits, start=1):
    print(f"{rank:>2}. {score:.3f}  {chunk.doc_id}")