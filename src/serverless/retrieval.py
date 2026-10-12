"""Real BGE and cross-encoder inference without PyTorch or a writable database."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

from src.ingestion.chunker import CodeChunk
from src.ingestion.graph_builder import DependencyGraphBuilder
from src.retrieval.bm25 import BM25SearchEngine
from src.retrieval.reranker import _rerank_text
from src.security.rbac import rbac_manager

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class OnnxModel:
    def __init__(self, directory: Path):
        self.directory = directory
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._session = None
        self._lock = threading.Lock()

    def run(self, inputs):
        # Tokenizer configuration and the session are shared safely across requests.
        with self._lock:
            if self._session is None:
                import onnxruntime as ort
                options = ort.SessionOptions()
                options.intra_op_num_threads = 1
                options.inter_op_num_threads = 1
                self._session = ort.InferenceSession(
                    str(self.directory / "model.onnx"), options,
                    providers=["CPUExecutionProvider"],
                )
            encodings = self.tokenizer.encode_batch(inputs)
            values = {
                "input_ids": np.asarray([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.asarray([e.attention_mask for e in encodings], dtype=np.int64),
                "token_type_ids": np.asarray([e.type_ids for e in encodings], dtype=np.int64),
            }
            return self._session.run(None, values)[0]


class OnnxEmbedding(OnnxModel):
    def encode(self, texts):
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        vectors = []
        # Small batches bound peak memory even while preparing a longer corpus.
        for start in range(0, len(texts), 4):
            cls = self.run(texts[start:start + 4])[:, 0, :]
            cls = cls / np.maximum(np.linalg.norm(cls, axis=1, keepdims=True), 1e-12)
            vectors.append(cls.astype(np.float32))
        return np.concatenate(vectors)


class OnnxReranker(OnnxModel):
    def score(self, query, chunks):
        result = []
        for start in range(0, len(chunks), 4):
            pairs = [(query, _rerank_text(c)) for c in chunks[start:start + 4]]
            logits = self.run(pairs).reshape(-1)
            result.extend((1 / (1 + np.exp(-np.clip(logits, -80, 80)))).tolist())
        return result


class ReadOnlyDenseIndex:
    def __init__(self, chunks, vectors, model):
        self.chunks, self.vectors, self.model = chunks, vectors, model
        if vectors.shape != (len(chunks), 384) or not np.isfinite(vectors).all():
            raise ValueError("Invalid bundled dense index.")

    def search(self, query, role="Junior Dev", top_k=10, tenant_id=None):
        clearance = rbac_manager.get_clearance_for_role(role)
        allowed = [i for i, c in enumerate(self.chunks)
                   if c.security_level.lower() in clearance
                   and (tenant_id is None or c.tenant_id == tenant_id)]
        if not allowed:
            return []
        query_vector = self.model.encode([QUERY_PREFIX + query])[0]
        scores = self.vectors[allowed] @ query_vector
        ranked = np.argsort(-scores, kind="stable")[:top_k]
        return [(self.chunks[allowed[i]], float(scores[i])) for i in ranked]


class ReadOnlyIndexer:
    def __init__(self, assets: Path):
        self.chunks = [CodeChunk.model_validate(c) for c in
                       json.loads((assets / "chunks.json").read_text())]
        self.graph_builder = DependencyGraphBuilder()
        self.graph_builder.load_graph(assets / "graph.json")
        self.bm25_index = BM25SearchEngine()
        self.bm25_index.build_index(self.chunks)
        self.vector_index = ReadOnlyDenseIndex(
            self.chunks, np.load(assets / "vectors.npy", allow_pickle=False),
            OnnxEmbedding(assets / "embedding"),
        )
