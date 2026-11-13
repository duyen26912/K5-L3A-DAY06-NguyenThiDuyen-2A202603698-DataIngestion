"""Check benchmark/questions.jsonl against the cleaned corpus BEFORE any retrieval run.

Checks: required fields, unique ids, split sizes (>=15 dev, >=5 test), >=3 filter
questions with >=1 in test, every evidence quote present verbatim on its gold page
(whitespace-normalized), gold page lies in the gold Điều, filter value matches the
gold page's chapter, and the question text does not leak the gold Điều/page.

Run from starter/ after `python -m src.ingestion`:  python scripts/verify_benchmark.py
"""
import json
import re
import sys
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))
from src.ingestion import metadata_at  # noqa: E402
from src.models import DocumentPage  # noqa: E402

REQUIRED = ["id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote", "filter"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    pages = {}
    for line in open(STARTER / "results" / "pages.jsonl", encoding="utf-8"):
        r = json.loads(line)
        meta = {k: r.get(k) for k in ("chuong", "chuong_title", "muc", "muc_title", "dieu", "dieu_title", "headings")}
        pages[(r["document_id"], r["page"])] = DocumentPage(r["document_id"], r["source"], r["page"], r["text"], meta)
    qs = [json.loads(l) for l in open(STARTER.parent / "benchmark" / "questions.jsonl", encoding="utf-8") if l.strip()]
    errors: list[str] = []

    ids = [q["id"] for q in qs]
    if len(ids) != len(set(ids)):
        errors.append("duplicate ids")
    for q in qs:
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            errors.append(f"{q.get('id')}: missing {missing}")
            continue
        golds = [{"source_id": q["gold_source_id"], "page": q["gold_page"], "dieu": q.get("gold_dieu"),
                  "evidence_quote": q["evidence_quote"]}] + q.get("alt_gold", [])
        for g in golds:
            page = pages.get((g["source_id"], g["page"]))
            if page is None:
                errors.append(f"{q['id']}: gold page {g['page']} not in corpus")
                continue
            quotes = g["evidence_quote"] if isinstance(g["evidence_quote"], list) else [g["evidence_quote"]]
            text = norm(page.text)
            for quote in quotes:
                pos = text.find(norm(quote))
                if pos < 0:
                    errors.append(f"{q['id']}: evidence not found on page {g['page']}: {quote[:60]!r}")
                    continue
                offset = page.text.find(quote)
                if offset < 0:
                    errors.append(f"{q['id']}: evidence only matches after whitespace normalization: {quote[:60]!r}")
                    continue
                at = metadata_at(page, offset)
                if g.get("dieu") and at["dieu"] != g["dieu"]:
                    errors.append(f"{q['id']}: evidence on page {g['page']} belongs to Điều {at['dieu']}, not {g['dieu']}")
                if q["filter"] and q["filter"].get("chuong") != at["chuong"]:
                    errors.append(f"{q['id']}: filter chuong={q['filter']['chuong']} but evidence is in Chương {at['chuong']}")
        if re.search(r"Điều \d+|trang \d+", q["question"], re.IGNORECASE):
            errors.append(f"{q['id']}: question leaks article/page number")

    dev = [q for q in qs if q["split"] == "dev"]
    test = [q for q in qs if q["split"] == "test"]
    filt = [q for q in qs if q.get("filter")]
    if len(dev) < 15 or len(test) < 5:
        errors.append(f"split sizes dev={len(dev)} test={len(test)} (need >=15/>=5)")
    if len(filt) < 3 or not any(q["split"] == "test" for q in filt):
        errors.append(f"filter questions={len(filt)}, in test={sum(q['split'] == 'test' for q in filt)} (need >=3, >=1 test)")

    print(f"{len(qs)} questions: dev={len(dev)} test={len(test)} filter={len(filt)} "
          f"(test filter={sum(q['split'] == 'test' for q in filt)})")
    types = {}
    for q in qs:
        types.setdefault(q.get("type"), []).append(q["id"])
    for t, v in types.items():
        print(f"  {t}: {len(v)} -> {', '.join(v)}")
    if errors:
        print("ERRORS:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: all evidence quotes verified on their gold pages.")


if __name__ == "__main__":
    main()
