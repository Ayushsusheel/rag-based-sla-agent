import re

from app.logging_config import logger
from app.utils import build_citation, normalize_key, normalize_ws, stable_hash


def extract_appendix_topics(doc_id: str, top_sections: list[dict]) -> list[dict]:
    appendix = None
    for sec in top_sections:
        if normalize_key(sec["section_name"]).startswith("appendix a"):
            appendix = sec
            break

    if not appendix:
        logger.info("[bold yellow]Appendix topics extracted[/] count=0")
        return []

    text = normalize_ws(appendix["text"] or "")
    if not text:
        logger.info("[bold yellow]Appendix topics extracted[/] count=0")
        return []

    topic_patterns = [
        ("Virus Detection and Blocking Service Level", r"(?:^|\n)\s*1\.?\s*Virus Detection and Blocking Service Level"),
        ("Spam Effectiveness Service Level", r"(?:^|\n)\s*2\.?\s*Spam Effectiveness Service Level"),
        ("False Positive Service Level", r"(?:^|\n)\s*3\.?\s*False Positive Service Level"),
    ]

    hits = []
    for topic_name, pat in topic_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            hits.append((m.start(), topic_name))

    if not hits:
        for topic_name, _ in topic_patterns:
            m = re.search(re.escape(topic_name), text, flags=re.IGNORECASE)
            if m:
                hits.append((m.start(), topic_name))

    if not hits:
        logger.info("[bold yellow]Appendix topics extracted[/] count=0")
        return []

    hits.sort()
    topics = []
    for idx, (start_pos, topic_name) in enumerate(hits):
        end_pos = hits[idx + 1][0] if idx + 1 < len(hits) else len(text)
        body = text[start_pos:end_pos].strip()

        topics.append(
            {
                "topic_id": f"appendix_{stable_hash(doc_id, topic_name)}",
                "doc_id": doc_id,
                "topic_name": topic_name,
                "text": body,
                "page_num": appendix.get("start_page"),
                "citation": build_citation(topic_name, appendix.get("start_page"), "appendix_topic"),
            }
        )

    logger.info(f"[bold yellow]Appendix topics extracted[/] count={len(topics)}")
    return topics