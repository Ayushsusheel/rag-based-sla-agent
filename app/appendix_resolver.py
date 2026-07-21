import re

from rapidfuzz import fuzz

from app.storage import fetch_appendix_topics
from app.utils import normalize_key, normalize_ws


def _find_topic_record(query: str, appendix_topics: list[dict]):
    q = normalize_key(query)
    best = None
    best_score = 0

    for t in appendix_topics:
        score = fuzz.partial_ratio(q, normalize_key(t["topic_name"]))
        if "false positive" in q and "false positive" in normalize_key(t["topic_name"]):
            score += 25
        if "spam effectiveness" in q and "spam effectiveness" in normalize_key(t["topic_name"]):
            score += 25
        if "virus detection" in q and "virus detection" in normalize_key(t["topic_name"]):
            score += 25

        if score > best_score:
            best_score = score
            best = t

    return best if best_score >= 70 else None


def _appendix_definition(topic: dict):
    text = topic["text"]
    tkey = normalize_key(topic["topic_name"])

    if "false positive" in tkey:
        m = re.search(r'“False Positive” is defined as (.+?)(?:\n|$)', text, flags=re.IGNORECASE)
        if m:
            return "False Positive: " + normalize_ws(m.group(1))

    if "spam effectiveness" in tkey:
        m = re.search(r'“Spam Effectiveness” is defined as (.+?)(?:\n|$)', text, flags=re.IGNORECASE)
        if m:
            return "Spam Effectiveness: " + normalize_ws(m.group(1))

    if "virus detection and blocking" in tkey:
        m = re.search(r'“Virus Detection and Blocking” is defined as (.+?)(?:\n|$)', text, flags=re.IGNORECASE)
        if m:
            return "Virus Detection and Blocking: " + normalize_ws(m.group(1))

    return None


def _appendix_exclusions(topic: dict):
    text = topic["text"]
    low = normalize_key(text)
    marker = "shall not apply to:"
    pos = low.find(marker)
    if pos < 0:
        return None

    body = text[pos + len(marker):]
    body = re.split(r"\n\s*[a-z]\.\s+the service credit", body, maxsplit=1, flags=re.IGNORECASE)[0]
    lines = [normalize_ws(x) for x in body.split("\n") if normalize_ws(x)]

    items = []
    for line in lines:
        if re.match(r"^(?:[ivx]+\.)\s+", line, flags=re.IGNORECASE):
            items.append(re.sub(r"^(?:[ivx]+\.)\s+", "", line, flags=re.IGNORECASE))
        elif line.startswith("•"):
            items.append(line.lstrip("•").strip())

    return items or None


def _appendix_table(topic: dict):
    lines = [normalize_ws(x) for x in topic["text"].split("\n") if normalize_ws(x)]
    rows = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if re.search(r"(>|<)\s*\d", line):
            if i + 1 < len(lines) and re.fullmatch(r"(\d+(?:\.\d+)?)\s*%?", lines[i + 1]):
                rows.append((line, lines[i + 1] + "%"))
                i += 2
                continue
            m_same = re.match(r"^(.*?(?:>|<)\s*[\d:,]+.*?)\s+(\d+(?:\.\d+)?)\s*%?$", line)
            if m_same:
                rows.append((normalize_ws(m_same.group(1)), m_same.group(2) + "%"))
                i += 1
                continue
        i += 1

    return rows or None


def answer_appendix_query(doc_id: str, query: str):
    appendix_topics = fetch_appendix_topics(doc_id)
    if not appendix_topics:
        return None

    topic = _find_topic_record(query, appendix_topics)
    if not topic:
        return None

    q = normalize_key(query)

    if "table" in q or "service credit" in q or "list" in q:
        rows = _appendix_table(topic)
        if rows:
            answer_lines = [f"{topic['topic_name']}:"]
            for cond, credit in rows:
                answer_lines.append(f"- {cond} -> {credit}")
            return {
                "answer": "\n".join(answer_lines) + " [Source 1]",
                "resolved_mode": "appendix_topic_table",
                "subqueries": [query],
                "evidence": [
                    {
                        "entity_id": topic["topic_id"],
                        "entity_type": "appendix_topic",
                        "service_name": "",
                        "topic_name": topic["topic_name"],
                        "page_num": topic["page_num"],
                        "citation": topic["citation"],
                        "content": topic["text"][:2600],
                        "score": 1.0,
                    }
                ],
            }

    if "not apply" in q or "exclusion" in q or "exceptions" in q:
        items = _appendix_exclusions(topic)
        if items:
            answer = [f"{topic['topic_name']} shall not apply to:"]
            for item in items:
                answer.append(f"- {item}")
            return {
                "answer": "\n".join(answer) + " [Source 1]",
                "resolved_mode": "appendix_topic_exclusions",
                "subqueries": [query],
                "evidence": [
                    {
                        "entity_id": topic["topic_id"],
                        "entity_type": "appendix_topic",
                        "service_name": "",
                        "topic_name": topic["topic_name"],
                        "page_num": topic["page_num"],
                        "citation": topic["citation"],
                        "content": topic["text"][:2600],
                        "score": 1.0,
                    }
                ],
            }

    definition = _appendix_definition(topic)
    if definition:
        return {
            "answer": definition + " [Source 1]",
            "resolved_mode": "appendix_topic_definition",
            "subqueries": [query],
            "evidence": [
                {
                    "entity_id": topic["topic_id"],
                    "entity_type": "appendix_topic",
                    "service_name": "",
                    "topic_name": topic["topic_name"],
                    "page_num": topic["page_num"],
                    "citation": topic["citation"],
                    "content": topic["text"][:2600],
                    "score": 1.0,
                }
            ],
        }

    return None