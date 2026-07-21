from pathlib import Path

import fitz
import pdfplumber

from app.logging_config import logger, log_step
from app.utils import normalize_multiline, normalize_ws


def _page_text_from_blocks(page: fitz.Page) -> str:
    blocks = page.get_text("blocks")
    blocks = sorted(blocks, key=lambda b: (round(b[1], 1), round(b[0], 1)))

    lines = []
    for b in blocks:
        text = normalize_multiline(b[4])
        if text:
            lines.append(text)

    return "\n".join(lines)


def load_pdf_document(pdf_path: Path) -> dict:
    with log_step("load_pdf_document", file=pdf_path.name):
        doc = fitz.open(str(pdf_path))
        pages = []
        try:
            for idx in range(len(doc)):
                page_num = idx + 1
                page = doc.load_page(idx)
                text = _page_text_from_blocks(page)
                pages.append(
                    {
                        "page_num": page_num,
                        "text": text,
                    }
                )
        finally:
            doc.close()

        logger.info(f"[bold yellow]PDF loaded[/] pages={len(pages)}")
        return {
            "source_file": pdf_path.name,
            "source_path": str(pdf_path),
            "file_type": "pdf",
            "pages": pages,
        }


def extract_pdf_tables(pdf_path: Path) -> list[dict]:
    tables = []

    with log_step("extract_pdf_tables", file=pdf_path.name):
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                try:
                    raw_tables = page.extract_tables()
                except Exception:
                    raw_tables = []

                for t_idx, tbl in enumerate(raw_tables):
                    cleaned_rows = []
                    for row in tbl or []:
                        if not row:
                            continue
                        cells = [normalize_ws(c or "") for c in row]
                        if any(cells):
                            cleaned_rows.append(cells)

                    if cleaned_rows:
                        tables.append(
                            {
                                "page_num": page_idx,
                                "table_index": t_idx,
                                "rows": cleaned_rows,
                            }
                        )

        logger.info(f"[bold yellow]PDF tables extracted[/] count={len(tables)}")
        return tables