import re

from app.logging_config import logger
from app.utils import (
    build_citation,
    json_dumps_compact,
    normalize_key,
    normalize_ws,
    stable_hash,
)


def _drop_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return rows

    max_cols = max(len(r) for r in rows)
    keep = []

    for c in range(max_cols):
        col_vals = []
        for r in rows:
            val = r[c] if c < len(r) else ""
            col_vals.append(normalize_ws(val))
        if any(col_vals):
            keep.append(c)

    cleaned = []
    for r in rows:
        cleaned.append([normalize_ws(r[c]) if c < len(r) else "" for c in keep])

    return cleaned


def _find_service_for_page(page_num: int, rows: list[list[str]], services: list[dict]) -> dict | None:
    candidates = []
    for svc in services:
        start_page = svc.get("start_page")
        end_page = svc.get("end_page")
        if start_page is None:
            continue
        if end_page is None:
            end_page = start_page
        if start_page <= page_num <= end_page:
            candidates.append(svc)

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    non_empty_cells = []
    for row in rows[:8]:
        for cell in row:
            cell_k = normalize_key(cell)
            if cell_k and len(cell_k) >= 4:
                non_empty_cells.append(cell_k)

    best = None
    best_score = -1

    for svc in candidates:
        svc_text_k = normalize_key(svc.get("text", ""))
        score = 0
        for cell in non_empty_cells:
            if cell in svc_text_k:
                score += len(cell)
            if ("<" in cell or ">" in cell) and cell in svc_text_k:
                score += 20

        span = (svc.get("end_page", svc.get("start_page", 999999)) - svc.get("start_page", 999999))
        score -= span

        if score > best_score:
            best = svc
            best_score = score

    return best or candidates[0]


def _normalize_table_headers(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    return [normalize_ws(x) for x in rows[0]]


def _classify_table_type(headers: list[str], rows: list[list[str]]) -> str:
    joined_headers = normalize_key(" | ".join(headers))
    flat = normalize_key("\n".join(" | ".join(r) for r in rows[:8]))

    header_match = (
        ("uptime percentage" in joined_headers and "service credit" in joined_headers)
        or ("average email delivery time" in joined_headers and "service credit" in joined_headers)
        or ("false positive ratio" in joined_headers and "service credit" in joined_headers)
        or ("query availability percentage" in joined_headers and "service credit" in joined_headers)
        or ("good call rate" in joined_headers and "service credit" in joined_headers)
        or ("availability percentage" in joined_headers and "service credit" in joined_headers)
    )

    threshold_rows = 0
    for row in rows[1:6]:
        row_text = normalize_key(" | ".join(row))
        if ("<" in row_text or ">" in row_text or "less than" in row_text or "greater than" in row_text) and "%" in row_text:
            threshold_rows += 1

    if header_match and threshold_rows >= 1:
        return "service_credit"

    if "service credit" in flat and threshold_rows >= 2:
        return "service_credit"

    return "generic_table"


def _make_table_name(service_name: str, table_type: str, headers: list[str], page_num: int, table_index: int) -> str:
    if table_type == "service_credit":
        return f"{service_name}_ServiceCredit_p{page_num}_{table_index}"

    if headers:
        header_part = "_".join(
            re.sub(r"[^A-Za-z0-9]+", "", h)[:20] for h in headers[:3] if h
        )
        if header_part:
            return f"{service_name}_{header_part}_p{page_num}_{table_index}"

    return f"{service_name}_Table_p{page_num}_{table_index}"


def _pretty_service_credit_rows(rows: list[list[str]]) -> list[str]:
    out = []
    for row in rows[1:]:
        non_empty = [normalize_ws(x) for x in row if normalize_ws(x)]
        if len(non_empty) < 2:
            continue

        condition = None
        credit = None

        for cell in non_empty:
            low = normalize_key(cell)
            if ("<" in cell or ">" in cell or "less than" in low or "greater than" in low) and "%" in cell:
                condition = cell
                break

        for cell in reversed(non_empty):
            c = normalize_ws(cell)
            if re.fullmatch(r"\d+(?:\.\d+)?%?", c):
                credit = c if c.endswith("%") else f"{c}%"
                break

        if condition and credit:
            out.append(f"{condition} -> {credit}")

    return out


def extract_tables(doc_id: str, pdf_tables: list[dict], services: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    raw_tables = []
    table_rows = []
    table_text_chunks = []

    for t in pdf_tables:
        page_num = t["page_num"]
        rows = _drop_empty_columns(t["rows"])

        if not rows or len(rows) < 2:
            continue

        svc = _find_service_for_page(page_num, rows, services)
        service_name = svc["service_name"] if svc else "UNASSIGNED"

        headers = _normalize_table_headers(rows)
        table_type = _classify_table_type(headers, rows)
        table_name = _make_table_name(service_name, table_type, headers, page_num, t["table_index"])

        table_id = f"tbl_{stable_hash(doc_id, service_name, table_name, str(page_num))}"
        citation = build_citation(service_name if service_name else "Table", page_num, "table")

        raw_tables.append(
            {
                "table_id": table_id,
                "doc_id": doc_id,
                "service_name": service_name,
                "table_name": table_name,
                "table_type": table_type,
                "page_num": page_num,
                "header_json": json_dumps_compact(headers),
                "rows_json": json_dumps_compact(rows),
                "citation": citation,
            }
        )

        for idx, row in enumerate(rows):
            row_id = f"row_{stable_hash(table_id, str(idx), *row)}"
            table_rows.append(
                {
                    "row_id": row_id,
                    "table_id": table_id,
                    "doc_id": doc_id,
                    "service_name": service_name,
                    "table_name": table_name,
                    "row_order": idx,
                    "row_json": json_dumps_compact(row),
                }
            )

        if table_type == "service_credit":
            lines = _pretty_service_credit_rows(rows)
            text_repr = "\n".join(lines)
        else:
            text_repr = "\n".join(" | ".join(normalize_ws(c) for c in row) for row in rows)

        if text_repr:
            table_text_chunks.append(
                {
                    "entity_id": table_id,
                    "doc_id": doc_id,
                    "entity_type": "table_text",
                    "service_name": service_name,
                    "topic_name": "",
                    "page_num": page_num,
                    "citation": citation,
                    "content": f"{table_name}\n{text_repr}",
                }
            )

    logger.info(f"[bold yellow]Raw tables extracted[/] count={len(raw_tables)}")
    logger.info(f"[bold yellow]Table rows extracted[/] count={len(table_rows)}")
    logger.info(f"[bold yellow]Table text chunks built[/] count={len(table_text_chunks)}")

    return raw_tables, table_rows, table_text_chunks