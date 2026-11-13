"""Evaluate retrieved evidence and keep per-query traces.

Definition (GUIDE.md): a retrieved chunk is a HIT when it comes from a gold
(source, page) AND contains the full gold evidence (every quote when the
evidence is a list). Alternative gold sources listed in `alt_gold` are accepted.
Matching is exact after whitespace normalization. Human labels (coherence,
grounding) are NOT inferred here; this only supports them.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def gold_list(question: dict[str, Any]) -> list[dict[str, Any]]:
    golds = [{"source_id": question["gold_source_id"], "page": question["gold_page"],
              "dieu": question.get("gold_dieu"), "evidence_quote": question["evidence_quote"]}]
    return golds + list(question.get("alt_gold", []))


def judge_hit(hit: dict[str, Any], golds: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {'hit', 'gold_page_match', 'evidence_fraction'} for one retrieved chunk."""
    text = norm(hit["text"])
    cands = []
    for g in golds:
        if (hit["document_id"], hit["page"]) != (g["source_id"], g["page"]):
            continue
        quotes = g["evidence_quote"] if isinstance(g["evidence_quote"], list) else [g["evidence_quote"]]
        found = sum(norm(q) in text for q in quotes)
        cands.append({"hit": found == len(quotes), "gold_page_match": True,
                      "evidence_fraction": round(found / len(quotes), 3)})
    if not cands:
        return {"hit": False, "gold_page_match": False, "evidence_fraction": 0.0}
    return max(cands, key=lambda c: (c["hit"], c["evidence_fraction"]))


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Judge top-k hits for one question; keep full trace for audit."""
    golds = gold_list(question)
    judged = []
    for rank, h in enumerate(hits, start=1):
        j = judge_hit(h, golds)
        judged.append({"rank": rank, "chunk_id": h["chunk_id"], "score": round(float(h["score"]), 4),
                       "document_id": h["document_id"], "source": h["source"], "page": h["page"],
                       "chuong": h["chuong"], "muc": h["muc"], "dieu": h["dieu"],
                       "dieu_list": h["metadata"].get("dieu_list"), "text": h["text"], **j})
    first = next((x["rank"] for x in judged if x["hit"]), None)
    return {
        "question_id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold": [{"page": g["page"], "dieu": g.get("dieu")} for g in golds],
        "hit1": first == 1,
        "hit3": first is not None and first <= 3,
        "first_hit_rank": first,
        "gold_page_in_top3": any(x["gold_page_match"] for x in judged[:3]),
        "evidence_split_suspected": (first is None and any(x["gold_page_match"] and 0 < x["evidence_fraction"] < 1
                                                           for x in judged[:3])),
        "hits": judged,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and split, as counts n/N."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out = {}
    for (strategy, split), ts in sorted(groups.items()):
        n = len(ts)
        h1 = sum(t["hit1"] for t in ts)
        h3 = sum(t["hit3"] for t in ts)
        filt = [t for t in ts if t.get("question_has_filter")]  # same subset for A, B and C
        out[f"{strategy}/{split}"] = {
            "strategy": strategy, "split": split, "N": n,
            "hit1": h1, "hit1_str": f"{h1}/{n}", "hit1_rate": round(h1 / n, 3),
            "hit3": h3, "hit3_str": f"{h3}/{n}", "hit3_rate": round(h3 / n, 3),
            "filter_questions": len(filt),
            "filter_hit3_str": f"{sum(t['hit3'] for t in filt)}/{len(filt)}" if filt else "N/A",
            "missed": [t["question_id"] for t in ts if not t["hit3"]],
        }
    return out
