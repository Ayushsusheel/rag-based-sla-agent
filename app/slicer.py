import re

from app.logging_config import logger
from app.utils import build_citation, normalize_ws


def clean_ms_sla_noise(text: str) -> str:
    lines = []
    for raw in text.split("\n"):
        line = normalize_ws(raw)
        if not line:
            continue

        low = line.lower()
        if low.startswith("microsoft volume licensing service level agreement"):
            continue
        if "table of contents →" in low:
            continue
        if line == "Table of Contents / Definitions":
            continue
        if line == "Table of Contents":
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if low.startswith("trusted 0/877"):
            continue
        if line in {"→ Introduction", "→ General Terms", "→ Service Specific Terms", "→ Appendices"}:
            continue

        lines.append(line)

    return "\n".join(lines)


def _find_title_pos(text: str, title: str) -> int:
    if not text or not title:
        return -1

    candidates = [
        title,
        title.replace("–", "-"),
        title.replace("—", "-"),
        normalize_ws(title),
    ]

    low_text = text.lower()
    for cand in candidates:
        pos = low_text.find(cand.lower())
        if pos >= 0:
            return pos

    title_words = normalize_ws(title).split()
    if len(title_words) >= 2:
        pattern = r"\s+".join(re.escape(w) for w in title_words)
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.start()

    return -1


def _slice_text_between(text: str, current_title: str, next_title: str | None) -> str:
    if not text:
        return ""

    start_idx = _find_title_pos(text, current_title)
    if start_idx < 0:
        start_idx = 0

    end_idx = len(text)
    if next_title:
        tail = text[start_idx + max(1, len(current_title)):]
        next_idx = _find_title_pos(tail, next_title)
        if next_idx >= 0:
            end_idx = start_idx + max(1, len(current_title)) + next_idx

    sliced = text[start_idx:end_idx].strip()
    return clean_ms_sla_noise(sliced)


def extract_top_sections_from_pdf(pdf_doc: dict, top_sections: list[dict]) -> list[dict]:
    page_map = {p["page_num"]: clean_ms_sla_noise(p["text"]) for p in pdf_doc["pages"]}
    out = []

    for i, sec in enumerate(top_sections):
        next_sec = top_sections[i + 1]["section_name"] if i + 1 < len(top_sections) else None
        pages = range(sec["start_page"], sec["end_page"] + 1)

        text = "\n".join(
            [page_map.get(p, "") for p in pages if page_map.get(p, "")]
        ).strip()

        text = _slice_text_between(text, sec["section_name"], next_sec)

        out.append(
            {
                **sec,
                "text": text,
                "citation": build_citation(sec["section_name"], sec["start_page"], "top_section"),
            }
        )

    logger.info(f"[bold yellow]PDF top sections extracted[/] count={len(out)}")
    return out


def extract_services_from_pdf(pdf_doc: dict, service_index: list[dict]) -> list[dict]:
    page_map = {p["page_num"]: clean_ms_sla_noise(p["text"]) for p in pdf_doc["pages"]}
    page_count = len(pdf_doc["pages"])
    out = []

    for i, svc in enumerate(service_index):
        current_name = svc["service_name"]
        next_name = service_index[i + 1]["service_name"] if i + 1 < len(service_index) else None

        start_page = svc["start_page"]
        next_start_page = service_index[i + 1]["start_page"] if i + 1 < len(service_index) else None

        if next_start_page is None:
            pages = range(start_page, min(page_count, svc["end_page"]) + 1)
        else:
            pages = range(start_page, max(start_page, next_start_page) + 1)

        joined = "\n".join(
            [page_map.get(p, "") for p in pages if page_map.get(p, "")]
        )
        sliced = _slice_text_between(joined, current_name, next_name)

        if not sliced:
            pages_fallback = range(start_page, min(page_count, svc["end_page"]) + 1)
            joined_fallback = "\n".join(
                [page_map.get(p, "") for p in pages_fallback if page_map.get(p, "")]
            )
            sliced = _slice_text_between(joined_fallback, current_name, next_name)

        out.append({**svc, "text": sliced})

    logger.info(f"[bold yellow]PDF service bodies extracted[/] count={len(out)}")
    return out