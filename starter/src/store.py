"""Store and search vectors using PostgreSQL + pgvector.

One table holds every indexed strategy, keyed by (strategy, chunk_id). Chunk IDs
are deterministic (document, page, chunker, position), so re-ingesting the same
version updates rows instead of duplicating them; chunks of a re-ingested document
that no longer exist are deleted. No ANN index is created: with a few hundred rows
PostgreSQL does a sequential scan, i.e. exact cosine search, and metadata filters
cannot reduce recall the way they can with approximate indexes.
"""
from __future__ import annotations

import json
from typing import Any

import psycopg

from .models import Chunk

FILTER_COLUMNS = {"document_id", "chuong", "muc", "dieu"}  # whitelist for user-supplied filters


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, table: str = "chunks") -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is empty; copy .env.example to .env")
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not table.isidentifier():
            raise ValueError("invalid table name")
        self.database_url = database_url
        self.dimensions = dimensions
        self.table = table

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, connect_timeout=5)

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    strategy     TEXT    NOT NULL,
                    chunk_id     TEXT    NOT NULL,
                    document_id  TEXT    NOT NULL,
                    source       TEXT    NOT NULL,
                    page         INTEGER NOT NULL,
                    chuong       TEXT,
                    muc          INTEGER,
                    dieu         INTEGER,
                    text         TEXT    NOT NULL,
                    content_hash TEXT    NOT NULL,
                    metadata     JSONB   NOT NULL,
                    embedding    vector({self.dimensions}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )""")
            row = conn.execute(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'embedding'",
                (self.table,)).fetchone()
            if row and row[0] != self.dimensions:
                raise ValueError(f"table {self.table} stores vector({row[0]}), model gives {self.dimensions}")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> dict[str, int]:
        """Insert/update chunks for one strategy; delete obsolete chunks of the same documents."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if any(len(v) != self.dimensions for v in vectors):
            raise ValueError("vector dimension mismatch")
        ids = [c.chunk_id for c in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chunk_id in batch")
        docs = sorted({c.document_id for c in chunks})
        rows = [(strategy, c.chunk_id, c.document_id, c.source, c.page, c.metadata.get("chuong"),
                 c.metadata.get("muc"), c.metadata.get("dieu"), c.text, c.metadata["content_hash"],
                 json.dumps(c.metadata, ensure_ascii=False), _vec(v)) for c, v in zip(chunks, vectors)]
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.table} WHERE strategy = %s AND document_id = ANY(%s) "
                        "AND NOT (chunk_id = ANY(%s))", (strategy, docs, ids))
            deleted = cur.rowcount
            cur.executemany(f"""
                INSERT INTO {self.table} (strategy, chunk_id, document_id, source, page, chuong, muc, dieu,
                                          text, content_hash, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
                ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                    document_id = EXCLUDED.document_id, source = EXCLUDED.source, page = EXCLUDED.page,
                    chuong = EXCLUDED.chuong, muc = EXCLUDED.muc, dieu = EXCLUDED.dieu, text = EXCLUDED.text,
                    content_hash = EXCLUDED.content_hash, metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding""", rows)
        return {"upserted": len(rows), "deleted_obsolete": deleted}

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute(f"SELECT count(*) FROM {self.table} WHERE strategy = %s", (strategy,)).fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Exact cosine search within one strategy, optionally filtered on whitelisted columns."""
        if len(query_vector) != self.dimensions:
            raise ValueError("query vector dimension mismatch")
        where, params = ["strategy = %s"], [strategy]
        for key, value in (filters or {}).items():
            if key not in FILTER_COLUMNS:
                raise ValueError(f"filter on {key!r} is not allowed")
            where.append(f"{key} = %s")
            params.append(value)
        qv = _vec(query_vector)
        sql = (f"SELECT chunk_id, document_id, source, page, chuong, muc, dieu, text, metadata, "
               f"1 - (embedding <=> %s::vector) AS score FROM {self.table} WHERE {' AND '.join(where)} "
               f"ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s")
        with self._connect() as conn:
            rows = conn.execute(sql, [qv, *params, qv, top_k]).fetchall()
        keys = ["chunk_id", "document_id", "source", "page", "chuong", "muc", "dieu", "text", "metadata", "score"]
        return [dict(zip(keys, r)) for r in rows]
