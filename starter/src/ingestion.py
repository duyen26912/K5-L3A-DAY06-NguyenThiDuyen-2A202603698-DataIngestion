"""Read and normalize source data.

Corpus: Bộ luật Lao động 2019 (45/2019/QH14) as published in Công báo
số 993 + 994 ngày 26-12-2019 (PDF with a text layer).

Extraction notes (found by inspecting every page):
- pypdf's default mode inserts spaces inside words on justified lines
  ("ng ười làm vi ệc"); extraction_mode="layout" does not, so layout is used.
- In layout mode each paragraph (Điều heading, khoản, điểm) starts with an
  indented line and wrapped lines start at column 0. Paragraphs are rebuilt
  from that indentation.
- Every page has a running header "CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019"
  with the gazette page number; it is removed and the number kept as metadata.
- The last physical page is empty.

Run from starter/:  python -m src.ingestion
Outputs: results/pages.jsonl, results/ingest_log.json, ../data/manifest.json
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .models import DocumentPage

STARTER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = STARTER_DIR.parent
RESULTS_DIR = STARTER_DIR / "results"
MIN_PAGE_CHARS = 50

# Static corpus description (written by hand, checked against the source).
SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "blld-2019",
        "title": "Bộ luật Lao động số 45/2019/QH14",
        "source_path": "starter/data/bo-luat-lao-dong-2019.pdf",
        "source_url": "CẦN BỔ SUNG: link nơi đã tải file PDF Công báo",
        "publication": "Công báo số 993 + 994, ngày 26-12-2019, trang 3–95",
        "license_or_permission": (
            "Văn bản quy phạm pháp luật – không thuộc đối tượng bảo hộ quyền tác giả "
            "(Luật Sở hữu trí tuệ, Điều 15). Bản đăng Công báo chính thức."
        ),
        "accessed_at": "2026-11-13",
        "version": "Văn bản gốc, thông qua 20/11/2019, hiệu lực 01/01/2021 (Điều 220); chưa gồm các sửa đổi sau này",
        "document_type": "bo_luat",
        "language": "vi",
    }
]

HEADER_RE = re.compile(r"^\s*(\d+)?\s*CÔNG BÁO/Số 993 \+ 994/Ngày 26-12-2019\s*(\d+)?\s*$")
CHAPTER_RE = re.compile(r"^Chương ([IVXL]+)$")
SECTION_RE = re.compile(r"^Mục (\d+)$")
ARTICLE_RE = re.compile(r"^Điều (\d+)\. (.*)$")


def _is_upper_title(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFC) and whitespace, keeping one paragraph per line.

    Expects layout-mode lines: an indented line starts a paragraph, a line at
    column 0 continues the previous one. Blank lines also end a paragraph.
    Inner runs of spaces (layout padding) collapse to one space.
    """
    text = unicodedata.normalize("NFC", text).replace(" ", " ")
    paras: list[str] = []
    open_para = False
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            open_para = False
            continue
        if open_para and not raw[:1].isspace():
            paras[-1] = f"{paras[-1]} {line}"
        else:
            paras.append(line)
        open_para = True
    return "\n".join(paras)


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page; keep page number, source and structure metadata.

    Metadata per page:
      chuong / chuong_title / muc / muc_title / dieu / dieu_title: structure in
          force at the START of the page (carried over from previous pages)
      headings: [{offset, type, value, title}] inside the cleaned text, so a
          chunker can resolve metadata for any character offset (metadata_at)
      cong_bao_page: printed gazette page number from the running header
      has_text / raw_chars / clean_chars / removed_header: extraction log
    Article numbers must increase by exactly 1. Articles of other laws quoted
    inside Điều 219 start with “ and are therefore not treated as headings.
    """
    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []
    state: dict[str, Any] = dict.fromkeys(("chuong", "chuong_title", "muc", "muc_title", "dieu", "dieu_title"))
    pending_title: str | None = None  # "chuong" or "muc" waiting for its title line
    for page_no, pdf_page in enumerate(reader.pages, start=1):
        raw = unicodedata.normalize("NFC", pdf_page.extract_text(extraction_mode="layout") or "")
        kept, header, cong_bao_page = [], None, None
        for ln in raw.splitlines():
            m = HEADER_RE.match(ln)
            if m and header is None:
                header = ln.strip()
                cong_bao_page = int(m.group(1) or m.group(2))
                continue
            kept.append(ln)
        text = normalize_text("\n".join(kept))

        start_state = dict(state)
        headings: list[dict[str, Any]] = []
        next_offset = 0
        for para in text.split("\n") if text else []:
            offset, next_offset = next_offset, next_offset + len(para) + 1
            if pending_title and _is_upper_title(para):
                # Titles may wrap over several upper-case lines; keep appending.
                title = f"{state[f'{pending_title}_title']} {para}" if state[f"{pending_title}_title"] else para
                state[f"{pending_title}_title"] = title
                headings[-1]["title"] = title
                continue
            pending_title = None
            if m := CHAPTER_RE.match(para):
                state.update(chuong=m.group(1), chuong_title=None, muc=None, muc_title=None)
                headings.append({"offset": offset, "type": "chuong", "value": m.group(1), "title": None})
                pending_title = "chuong"
            elif m := SECTION_RE.match(para):
                state.update(muc=int(m.group(1)), muc_title=None)
                headings.append({"offset": offset, "type": "muc", "value": int(m.group(1)), "title": None})
                pending_title = "muc"
            elif m := ARTICLE_RE.match(para):
                n, expected = int(m.group(1)), (state["dieu"] or 0) + 1
                if n != expected:
                    raise ValueError(f"Page {page_no}: found Điều {n}, expected Điều {expected}")
                state.update(dieu=n, dieu_title=m.group(2))
                headings.append({"offset": offset, "type": "dieu", "value": n, "title": m.group(2)})
        for h in headings:  # every heading offset must point at its own line
            prefix = {"chuong": "Chương ", "muc": "Mục ", "dieu": "Điều "}[h["type"]] + str(h["value"])
            if not text.startswith(prefix, h["offset"]):
                raise AssertionError(f"Page {page_no}: bad offset for {prefix}")

        meta = {
            **start_state,
            "headings": headings,
            "cong_bao_page": cong_bao_page,
            "has_text": len(text) >= MIN_PAGE_CHARS,
            "raw_chars": len(raw),
            "clean_chars": len(text),
            "removed_header": header,
        }
        pages.append(DocumentPage(document_id=document_id, source=source, page=page_no, text=text, metadata=meta))
    return pages


def metadata_at(page: DocumentPage, offset: int) -> dict[str, Any]:
    """Structure metadata (chuong, muc, dieu + titles) in force at a character offset of a page."""
    keys = ("chuong", "chuong_title", "muc", "muc_title", "dieu", "dieu_title")
    out = {k: page.metadata.get(k) for k in keys}
    for h in page.metadata.get("headings", []):
        if h["offset"] > offset:
            break
        if h["type"] == "chuong":
            out.update(chuong=h["value"], chuong_title=h["title"], muc=None, muc_title=None)
        elif h["type"] == "muc":
            out.update(muc=h["value"], muc_title=h["title"])
        else:
            out.update(dieu=h["value"], dieu_title=h["title"])
    return out


def load_corpus() -> list[DocumentPage]:
    """Load every source in SOURCES and keep only content pages."""
    pages: list[DocumentPage] = []
    for src in SOURCES:
        pages.extend(p for p in load_pdf(REPO_DIR / src["source_path"], src["source_id"], src["source_path"])
                     if p.metadata["has_text"])
    return pages


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    manifest: list[dict[str, Any]] = []
    log: dict[str, Any] = {"extractor": "pypdf extract_text(extraction_mode='layout')", "sources": []}
    rows: list[str] = []
    for src in SOURCES:
        pages = load_pdf(REPO_DIR / src["source_path"], src["source_id"], src["source_path"])
        empty = [p.page for p in pages if not p.metadata["has_text"]]
        counted = [p for p in pages if p.metadata["has_text"]]
        if len(counted) < 30:
            raise SystemExit(f"{src['source_id']}: only {len(counted)} content pages (< 30)")
        for p in counted:
            row = {"document_id": p.document_id, "source": p.source, "page": p.page, "text": p.text}
            row.update({k: v for k, v in p.metadata.items()
                        if k not in ("has_text", "raw_chars", "clean_chars", "removed_header")})
            rows.append(json.dumps(row, ensure_ascii=False))
        dieu = [h for p in pages for h in p.metadata["headings"] if h["type"] == "dieu"]
        chuong = [h for p in pages for h in p.metadata["headings"] if h["type"] == "chuong"]
        manifest.append({
            **src,
            "physical_pages": len(pages),
            "counted_pages": [p.page for p in counted],
            "counted_page_total": len(counted),
            "empty_pages": empty,
            "page_counting_rule": (
                "Trang = trang vật lý của file PDF (page 1 = trang 3 Công báo). Tính mọi trang có "
                f"≥{MIN_PAGE_CHARS} ký tự nội dung Bộ luật sau khi bỏ dòng header Công báo; loại trang trống. "
                "Không có trang bìa/mục lục/tài liệu tham khảo trong file."
            ),
            "chars_per_page": {str(p.page): p.metadata["clean_chars"] for p in counted},
            "total_clean_chars": sum(p.metadata["clean_chars"] for p in counted),
            "articles_found": f"Điều {dieu[0]['value']}–{dieu[-1]['value']} ({len(dieu)} điều)",
            "chapters_found": [f"Chương {h['value']}: {h['title']}" for h in chuong],
        })
        log["sources"].append({
            "source_id": src["source_id"],
            "empty_pages": empty,
            "pages_without_header": [p.page for p in pages if p.metadata["has_text"] and not p.metadata["removed_header"]],
            "pages": [{"page": p.page, "cong_bao_page": p.metadata["cong_bao_page"], "raw_chars": p.metadata["raw_chars"],
                       "clean_chars": p.metadata["clean_chars"], "removed_header": p.metadata["removed_header"]}
                      for p in pages],
        })
    (RESULTS_DIR / "pages.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (RESULTS_DIR / "ingest_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPO_DIR / "data" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    for m, s in zip(manifest, log["sources"]):
        print(f"{m['source_id']}: {m['physical_pages']} physical pages, {m['counted_page_total']} counted, "
              f"empty={s['empty_pages']}, no-header={s['pages_without_header']}")
        print(f"  {m['total_clean_chars']} chars, {m['articles_found']}, {len(m['chapters_found'])} chương")


if __name__ == "__main__":
    main()
