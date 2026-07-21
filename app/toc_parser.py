import re

from app.config import MS_SLA_GROUP_NAMES, MS_SLA_TOP_SECTION_NAMES
from app.logging_config import logger
from app.utils import normalize_ws

APPENDIX_PREFIX = "APPENDIX A"


def _classify_entry(entry: str, current_group: str):
    entry_upper = entry.upper()

    if entry_upper in {x.upper() for x in MS_SLA_TOP_SECTION_NAMES}:
        return "top_section", ""

    if entry_upper.startswith(APPENDIX_PREFIX):
        return "top_section", ""

    if entry_upper in {x.upper() for x in MS_SLA_GROUP_NAMES}:
        return "group", entry

    return "service", current_group


def _merge_toc_lines(raw_lines: list[str]) -> list[str]:
    merged = []
    buf = ""

    for raw in raw_lines:
        line = normalize_ws(raw)
        if not line:
            continue

        low = line.lower()
        if low.startswith("microsoft volume licensing service level agreement"):
            continue
        if "table of contents →" in low:
            continue
        if line in {"Table of Contents", "Introduction", "General Terms", "Service Specific Terms", "Appendices"}:
            continue

        if re.search(r"(?:[.\u2026]{2,}|\s)\d+\s*$", line):
            full = f"{buf} {line}".strip() if buf else line
            merged.append(normalize_ws(full))
            buf = ""
        else:
            if line.isdigit():
                continue
            buf = f"{buf} {line}".strip() if buf else line

    if buf:
        merged.append(normalize_ws(buf))

    return merged


def _parse_toc_entries(merged_lines: list[str]) -> list[dict]:
    rows = []
    current_group = ""

    for line in merged_lines:
        m = re.match(r"^(.*?)\s*(?:[.\u2026]{2,}|\s)\s*(\d+)\s*$", line)
        if not m:
            continue

        entry = normalize_ws(m.group(1))
        page_num = int(m.group(2))

        entry_type, group_or_reset = _classify_entry(entry, current_group)
        if entry_type == "top_section":
            current_group = ""
        elif entry_type == "group":
            current_group = group_or_reset

        rows.append(
            {
                "entry_text": entry,
                "page_num": page_num,
                "entry_type": entry_type,
                "group_name": current_group if entry_type == "service" else "",
            }
        )

    return rows


def parse_toc_from_pdf(pdf_doc: dict) -> list[dict]:
    toc_pages = [p for p in pdf_doc["pages"] if p["page_num"] in {2, 3}]
    raw_lines = []
    for page in toc_pages:
        raw_lines.extend(page["text"].split("\n"))

    merged_lines = _merge_toc_lines(raw_lines)
    rows = _parse_toc_entries(merged_lines)

    logger.info(f"[bold yellow]PDF TOC parsed[/] count={len(rows)}")
    return rows


def build_top_sections(doc_id: str, toc_rows: list[dict], page_count: int) -> list[dict]:
    tops = [r for r in toc_rows if r["entry_type"] == "top_section"]

    appendix_rows = [
        r for r in toc_rows
        if r["entry_text"].upper().startswith(APPENDIX_PREFIX)
    ]
    if appendix_rows and not any(t["entry_text"].upper().startswith(APPENDIX_PREFIX) for t in tops):
        tops.extend(appendix_rows)

    tops = sorted(
        {(r["entry_text"], r["page_num"]): r for r in tops}.values(),
        key=lambda x: x["page_num"],
    )

    out = []
    for i, row in enumerate(tops):
        next_row = tops[i + 1] if i + 1 < len(tops) else None
        start_page = row["page_num"]
        end_page = (next_row["page_num"] - 1) if next_row else page_count

        out.append(
            {
                "section_id": f"{doc_id}_top_{i:03d}",
                "doc_id": doc_id,
                "section_name": row["entry_text"],
                "start_page": start_page,
                "end_page": end_page,
                "text": "",
                "citation": "",
            }
        )

    logger.info(f"[bold yellow]Top sections built[/] count={len(out)}")
    return out


def build_service_index(doc_id: str, toc_rows: list[dict], page_count: int) -> list[dict]:
    services = [
        r for r in toc_rows
        if r["entry_type"] == "service"
        and not r["entry_text"].upper().startswith(APPENDIX_PREFIX)
    ]
    services = sorted(services, key=lambda x: x["page_num"])

    out = []
    for i, row in enumerate(services):
        next_row = services[i + 1] if i + 1 < len(services) else None
        start_page = row["page_num"]

        if next_row:
            end_page = max(start_page, next_row["page_num"])
        else:
            end_page = min(page_count, start_page + 4)

        out.append(
            {
                "service_id": f"{doc_id}_svc_{i:05d}",
                "doc_id": doc_id,
                "service_group": row.get("group_name", ""),
                "service_name": row["entry_text"],
                "service_key": row["entry_text"].lower(),
                "start_page": start_page,
                "end_page": end_page,
                "text": "",
            }
        )

    logger.info(f"[bold yellow]Service index built[/] count={len(out)}")
    return out