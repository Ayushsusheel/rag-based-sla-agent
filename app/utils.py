import hashlib
import json
import re
import unicodedata
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def stable_hash(*parts: str) -> str:
    payload = "||".join(str(p or "") for p in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def normalize_ws(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_multiline(text: str) -> str:
    if not text:
        return ""
    lines = []
    for line in str(text).splitlines():
        line = normalize_ws(line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def normalize_key(text: str) -> str:
    text = normalize_ws(text).lower()
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[^a-z0-9\s\-&/:.,;()%]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def dump_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def shorten(text: str, max_chars: int = 1200) -> str:
    text = str(text)
    return text if len(text) <= max_chars else text[:max_chars] + "...[TRUNCATED]"


def build_citation(label: str, page_num, kind: str) -> str:
    parts = [label]
    if page_num is not None:
        parts.append(f"page {page_num}")
    parts.append(kind)
    return " :: ".join(parts)


def extract_percent_value(query: str):
    q = normalize_key(query)
    q = q.replace(" percentage", "%").replace(" percent", "%")

    m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    if m:
        return float(m.group(1))

    if "uptime" in q or "percentage" in q or "credit" in q:
        patterns = [
            r"uptime(?: percentage)?(?: was| is| only)?\s+(\d+(?:\.\d+)?)",
            r"percentage(?: was| is| only)?\s+(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s+uptime(?: percentage)?",
        ]
        for pat in patterns:
            m2 = re.search(pat, q)
            if m2:
                return float(m2.group(1))
    return None


def split_questions(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    raw_parts = re.split(r"[?\n]+", text)
    parts = [normalize_ws(p) for p in raw_parts if normalize_ws(p)]
    return parts or [normalize_ws(text)]


def stable_dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = normalize_key(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def strip_query_prefixes(text: str) -> str:
    q = normalize_key(text)
    prefixes = [
        "what is ",
        "what does ",
        "define ",
        "meaning of ",
        "tell me about ",
        "explain ",
        "what is the ",
        "what are the ",
        "how to calculate ",
        "what is the formula for ",
    ]
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if q.startswith(p):
                q = q[len(p):].strip()
                changed = True
    return q


def json_dumps_compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_loads_safe(text: str):
    return json.loads(text)


def rows_to_table_text(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    if len(rows) == 1:
        return " | ".join(header)

    lines = []
    for row in rows[1:]:
        parts = []
        for i, h in enumerate(header):
            value = row[i] if i < len(row) else ""
            parts.append(f"{h}: {value}")
        lines.append("; ".join(parts))
    return "\n".join(lines)