import re

from app.logging_config import logger
from app.utils import build_citation, normalize_key, normalize_ws, stable_hash


GENERIC_LABELS = {
    "service credit",
    "uptime percentage",
    "additional definitions",
    "definitions",
    "introduction",
    "general terms",
    "service specific terms",
    "table of contents",
    "table of contents / definitions",
    "appendices",
    "additional terms",
    "service level exceptions",
    "service exceptions",
    "service levels and service credits",
    "service level commitment",
    "terms",
    "claims",
    "limitations",
}


def _is_new_definition_line(line: str) -> bool:
    line = normalize_ws(line)
    if re.match(r'^[“"](.*?)[”"]\s+(?:is|means)\s+', line, flags=re.IGNORECASE):
        return True
    if re.match(r'^("?[^":]{2,120}"?)\s*:\s*(.+)$', line):
        return True
    return False


def _is_tableish_or_heading(line: str) -> bool:
    low = normalize_key(line)
    return (
        low in GENERIC_LABELS
        or low.startswith("service credit")
        or low.startswith("uptime percentage")
        or low.startswith("the following service")
        or low.startswith("service level exceptions")
        or low.startswith("additional terms")
        or low.startswith("appendix")
    )


def _is_noise_term(term: str) -> bool:
    tk = normalize_key(term)
    if tk in GENERIC_LABELS:
        return True
    if len(tk.split()) > 6:
        return True
    return False


def _parse_rows(lines, source_file_label: str, doc_id: str, service_name: str, service_group: str, source_section: str, page_num):
    defs = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m_quote = re.match(r'^[“"](.*?)[”"]\s+(?:is|means)\s+(.*)$', line, flags=re.IGNORECASE)
        m_colon = re.match(r'^("?[^":]{2,120}"?)\s*:\s*(.+)$', line)

        term = None
        value = None

        if m_quote:
            term = normalize_ws(m_quote.group(1))
            value = normalize_ws(m_quote.group(2))
        elif m_colon:
            term = normalize_ws(m_colon.group(1)).strip('"')
            value = normalize_ws(m_colon.group(2))

        if term and value and not _is_noise_term(term):
            continuation = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if _is_new_definition_line(nxt):
                    break
                if _is_tableish_or_heading(nxt):
                    break
                continuation.append(nxt)
                j += 1

            full_value = normalize_ws(" ".join([value] + continuation))

            defs.append(
                {
                    "def_id": f"def_{stable_hash(doc_id, service_name, source_section, term, full_value, str(page_num))}",
                    "doc_id": doc_id,
                    "service_name": service_name,
                    "service_group": service_group,
                    "source_section": source_section,
                    "term": term,
                    "definition_text": full_value,
                    "page_num": page_num,
                    "citation": build_citation(source_section or service_name or source_file_label, page_num, "definition"),
                }
            )

            i = j
            continue

        i += 1

    return defs


def extract_definitions(doc_id: str, services: list[dict], top_sections: list[dict]) -> list[dict]:
    defs = []

    for svc in services:
        lines = [normalize_ws(x) for x in svc["text"].split("\n") if normalize_ws(x)]
        defs.extend(
            _parse_rows(
                lines=lines,
                source_file_label=svc["service_name"],
                doc_id=doc_id,
                service_name=svc["service_name"],
                service_group=svc.get("service_group", ""),
                source_section=svc["service_name"],
                page_num=svc.get("start_page"),
            )
        )

    for sec in top_sections:
        lines = [normalize_ws(x) for x in sec["text"].split("\n") if normalize_ws(x)]
        defs.extend(
            _parse_rows(
                lines=lines,
                source_file_label=sec["section_name"],
                doc_id=doc_id,
                service_name="",
                service_group="",
                source_section=sec["section_name"],
                page_num=sec.get("start_page"),
            )
        )

    best = {}
    for d in defs:
        key = d["def_id"]
        prev = best.get(key)
        if prev is None or len(d["definition_text"]) > len(prev["definition_text"]):
            best[key] = d

    defs = list(best.values())
    logger.info(f"[bold yellow]Definitions extracted[/] count={len(defs)}")
    return defs