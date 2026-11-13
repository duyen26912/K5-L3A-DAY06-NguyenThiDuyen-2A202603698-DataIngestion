"""Real embedding provider: local Sentence Transformers model (no API key, cost 0)."""
from __future__ import annotations

from typing import Protocol

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Sentence Transformers adapter. Queries and documents are encoded the same way
    (this model has no query/document prefixes); vectors are L2-normalized so cosine
    distance in pgvector equals 1 - dot product. Fails loudly if the model cannot load:
    there is no fallback to random or mock vectors."""

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 64) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device="cpu")
        self.dimensions = int(self.model.get_sentence_embedding_dimension())
        self.max_seq_length = int(self.model.max_seq_length)

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer(text, add_special_tokens=True)["input_ids"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                 show_progress_bar=False, convert_to_numpy=True)
        return vecs.tolist()

    def embed_query(self, question: str) -> list[float]:
        return self.model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0].tolist()

    def versions(self) -> dict[str, str]:
        import sentence_transformers
        import torch
        import transformers

        return {"sentence_transformers": sentence_transformers.__version__, "torch": torch.__version__,
                "transformers": transformers.__version__}
