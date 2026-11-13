"""Day 06 pipeline: ingest -> chunk (A, B) -> embed -> pgvector -> retrieve A/B/C -> evaluate.

Run from starter/:
    python -m src.run --split dev     # build indexes, evaluate dev only (choose strategy here)
    python -m src.run --split test    # after the choice is frozen: evaluate test once

Strategies (same corpus, model, store, cosine metric, top-3):
    A: fixed 500 chars, overlap 50, no filter        (index A)
    B: paragraph-aware, max 500 chars, no filter     (index B)
    C: same index as B + metadata filter `chuong`, applied only to questions that carry a filter
A-B changes only chunking; B-C changes only filtering.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics as st
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import chunking
from .embeddings import DEFAULT_MODEL, MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import SOURCES, load_corpus
from .store import PgVectorStore

STARTER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = STARTER_DIR.parent
RESULTS = STARTER_DIR / "results"
TOP_K = 3

INDEXES: dict[str, dict[str, Any]] = {
    "A": {"chunker": "fixed_size", "params": {"size": 500, "overlap": 50}},
    "B": {"chunker": "by_paragraph", "params": {"max_size": 500}},
}
STRATEGIES: dict[str, dict[str, Any]] = {
    "A": {"index": "A", "use_filter": False, "desc": "Fixed 500 chars / overlap 50, no filter"},
    "B": {"index": "B", "use_filter": False, "desc": "Paragraph-aware (khoản/điểm), max 500 chars, no filter"},
    "C": {"index": "B", "use_filter": True, "desc": "Same chunks as B + filter `chuong` when the question has one"},
}
# Coherence audit positions, fixed before looking at any score: the paragraph
# closest to the middle of 10 evenly spaced content pages.
COHERENCE_PAGES = [5, 14, 23, 32, 41, 50, 59, 68, 77, 86]


def build_chunks(pages, index: str):
    cfg = INDEXES[index]
    fn = getattr(chunking, cfg["chunker"])
    return [c for p in pages for c in fn(p, **cfg["params"])]


def length_stats(chunks, embedder: MyEmbedder) -> dict[str, Any]:
    lens = sorted(len(c.text) for c in chunks)
    toks = [embedder.count_tokens(c.text) for c in chunks]
    q = lambda p: lens[min(len(lens) - 1, int(p * len(lens)))]  # noqa: E731
    return {"chunks": len(chunks), "chars_total": sum(lens), "chars_min": lens[0], "chars_p10": q(0.1),
            "chars_median": st.median(lens), "chars_p90": q(0.9), "chars_max": lens[-1],
            "tokens_total": sum(toks), "tokens_max": max(toks),
            "chunks_truncated_by_model": sum(t > embedder.max_seq_length for t in toks),
            "chunks_under_60_chars": sum(n < 60 for n in lens),
            "chunks_spanning_multiple_dieu": sum(len(c.metadata["dieu_list"]) > 1 for c in chunks)}


def coherence_rows(pages, chunks_by_index) -> list[dict[str, Any]]:
    rows = []
    by_page = {p.page: p for p in pages}
    for i, pg in enumerate(COHERENCE_PAGES, start=1):
        page = by_page[pg]
        mid, offset, best = len(page.text) // 2, 0, (10**9, 0)
        for para in page.text.split("\n"):
            best = min(best, (abs(offset - mid), offset))
            offset += len(para) + 1
        pos = best[1]
        para_text = page.text[pos:].split("\n")[0]
        for strategy, sc in STRATEGIES.items():
            cands = [c for c in chunks_by_index[sc["index"]]
                     if c.page == pg and c.metadata["char_start"] <= pos < c.metadata["char_end"]]
            c = cands[0]
            rows.append({"position_id": f"pos{i:02d}", "page": pg, "char_offset": pos,
                         "position_paragraph": para_text[:200], "strategy": strategy, "chunk_id": c.chunk_id,
                         "chunk_text": c.text, "label_0_1_2": "", "reason": ""})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], keep_existing: bool = False) -> None:
    if keep_existing and path.exists():  # audit sheets hold manual labels: never overwrite them
        print(f"keep existing {path.relative_to(STARTER_DIR)} (manual labels)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    args = ap.parse_args()
    load_dotenv(STARTER_DIR / ".env")
    RESULTS.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 1. corpus + benchmark
    t0 = time.perf_counter()
    pages = load_corpus()
    if len(pages) < 30:
        raise SystemExit(f"Only {len(pages)} content pages (< 30)")
    load_s = time.perf_counter() - t0
    questions = [json.loads(l) for l in open(REPO_DIR / "benchmark" / "questions.jsonl", encoding="utf-8") if l.strip()]
    selected = [q for q in questions if args.split == "all" or q["split"] == args.split]

    # 2. model + store
    model_name = os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL
    t0 = time.perf_counter()
    embedder = MyEmbedder(model_name)
    model_load_s = time.perf_counter() - t0
    store = PgVectorStore(os.environ.get("DATABASE_URL", ""), embedder.dimensions)
    store.create_schema()

    # 3. index A and B (chunk -> embed -> upsert), then re-ingest check
    index_stats, chunks_by_index = {}, {}
    for index in INDEXES:
        t0 = time.perf_counter()
        chunks = build_chunks(pages, index)
        t_chunk = time.perf_counter() - t0
        t0 = time.perf_counter()
        vectors = embedder.embed_documents([c.text for c in chunks])
        t_embed = time.perf_counter() - t0
        t0 = time.perf_counter()
        res1 = store.upsert(index, chunks, vectors)
        t_upsert = time.perf_counter() - t0
        n1 = store.count(index)
        res2 = store.upsert(index, chunks, vectors)  # same version again: must not duplicate
        n2 = store.count(index)
        if not (n1 == n2 == len(chunks)):
            raise SystemExit(f"Re-ingest check failed for {index}: {len(chunks)} chunks, {n1} -> {n2} rows")
        chunks_by_index[index] = chunks
        index_stats[index] = {**INDEXES[index], **length_stats(chunks, embedder),
                              "seconds_chunk": round(t_chunk, 2), "seconds_embed": round(t_embed, 2),
                              "seconds_upsert": round(t_upsert, 2),
                              "seconds_index_total": round(t_chunk + t_embed + t_upsert, 2),
                              "first_upsert": res1, "reingest_upsert": res2,
                              "rows_after_first": n1, "rows_after_reingest": n2, "cost_usd": 0.0}
        print(f"index {index}: {len(chunks)} chunks, embed {t_embed:.1f}s, rows {n1} -> {n2} after re-ingest")

    # 4. retrieve + evaluate
    traces = []
    qvecs = {q["id"]: embedder.embed_query(q["question"]) for q in selected}
    for strategy, sc in STRATEGIES.items():
        for q in selected:
            flt = q["filter"] if (sc["use_filter"] and q.get("filter")) else None
            t0 = time.perf_counter()
            hits = store.search(sc["index"], qvecs[q["id"]], TOP_K, flt)
            ms = (time.perf_counter() - t0) * 1000
            tr = evaluate_query(q, hits)
            tr.update(strategy=strategy, index=sc["index"], filter=flt, latency_ms=round(ms, 1),
                      question_has_filter=bool(q.get("filter")),
                      filter_respected=(all(h["chuong"] == flt["chuong"] for h in tr["hits"]) if flt else None))
            traces.append(tr)

    # 5. outputs
    tag = args.split
    with open(RESULTS / f"traces_{tag}.jsonl", "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = summarize(traces)
    for key, s in summary.items():  # filter compliance among questions that carry a filter
        ts = [t for t in traces if f"{t['strategy']}/{t['split']}" == key]
        with_filter = [t for t in ts if t["filter"]]
        s["filter_compliance_str"] = (f"{sum(t['filter_respected'] for t in with_filter)}/{len(with_filter)}"
                                      if with_filter else "N/A")
        s["mean_latency_ms"] = round(st.mean(t["latency_ms"] for t in ts), 1)
    (RESULTS / f"summary_{tag}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(RESULTS / f"summary_{tag}.csv",
              [{k: v for k, v in s.items() if k != "missed"} | {"missed": " ".join(s["missed"])}
               for s in summary.values()])

    stats = {"run_started_utc": started, "split": tag, "corpus": [s["source_id"] for s in SOURCES],
             "content_pages": len(pages), "seconds_load_corpus": round(load_s, 2),
             "embedding": {"provider": "local sentence-transformers", "model": embedder.model_name,
                           "dimensions": embedder.dimensions, "max_seq_length": embedder.max_seq_length,
                           "normalize": True, "query_document_handling": "same encoder, no prefixes",
                           "seconds_load_model": round(model_load_s, 2), **embedder.versions()},
             "vector_store": {"backend": "PostgreSQL 16 + pgvector 0.8.7 (docker pgvector/pgvector:0.8.7-pg16)",
                              "table": store.table, "metric": "cosine (<=>)", "search": "exact (no ANN index)"},
             "strategies": STRATEGIES, "indexes": index_stats, "top_k": TOP_K, "cost_usd_total": 0.0}
    (RESULTS / f"stats_{tag}.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    write_csv(RESULTS / "audit" / "coherence_labels.csv", coherence_rows(pages, chunks_by_index), keep_existing=True)
    if tag in ("test", "all"):
        rows = []
        for t in traces:
            if t["split"] != "test":
                continue
            for h in t["hits"]:
                rows.append({"strategy": t["strategy"], "question_id": t["question_id"], "rank": h["rank"],
                             "filter": json.dumps(t["filter"], ensure_ascii=False) if t["filter"] else "",
                             "chunk_id": h["chunk_id"], "source": h["source"], "page": h["page"],
                             "chuong": h["chuong"], "dieu_list": h["dieu_list"], "auto_hit": h["hit"],
                             "chunk_text": h["text"], "metadata_correct_y_n": "", "metadata_note": ""})
        write_csv(RESULTS / "audit" / "metadata_labels_test.csv", rows, keep_existing=True)
        write_csv(RESULTS / "audit" / "grounding_labels_test.csv",
                  [{"strategy": t["strategy"], "question_id": t["question_id"], "question": t["question"],
                    "expected_answer": t["expected_answer"], "auto_hit3": t["hit3"],
                    "top3_chunk_ids": " | ".join(h["chunk_id"] for h in t["hits"]),
                    "label_0_1_2": "", "reason": ""} for t in traces if t["split"] == "test"], keep_existing=True)

    print(f"\nResults ({tag}), Evidence Hit@k as n/N:")
    print(f"{'strategy':<9}{'split':<6}{'Hit@1':>7}{'Hit@3':>7}  {'filter Hit@3':>12}  {'filter ok':>9}  missed")
    for s in summary.values():
        print(f"{s['strategy']:<9}{s['split']:<6}{s['hit1_str']:>7}{s['hit3_str']:>7}  "
              f"{s['filter_hit3_str']:>12}  {s['filter_compliance_str']:>9}  {' '.join(s['missed'])}")


if __name__ == "__main__":
    main()
