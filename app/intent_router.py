from app.config import SMALLTALK
from app.utils import extract_percent_value, normalize_key, normalize_ws


def is_smalltalk(query: str) -> bool:
    return normalize_ws(query).lower() in SMALLTALK


def detect_appendix_topic(query: str) -> str | None:
    q = normalize_key(query)
    if "false positive" in q:
        return "False Positive Service Level"
    if "spam effectiveness" in q:
        return "Spam Effectiveness Service Level"
    if "virus detection and blocking" in q or "virus detection" in q:
        return "Virus Detection and Blocking Service Level"
    return None


def is_credit_query(query: str) -> bool:
    q = normalize_key(query)
    pct = extract_percent_value(query)
    if pct is None:
        return False

    credit_like = (
        "credit" in q
        or "credits" in q
        or "service credit" in q
        or "service credits" in q
        or "applicable" in q
        or "eligible" in q
    )
    uptime_like = (
        "uptime" in q
        or "percentage" in q
        or "%" in q
    )
    return credit_like and uptime_like


def is_formula_query(query: str) -> bool:
    q = normalize_key(query)
    return "formula" in q or "calculate" in q or "how to calculate" in q


def is_definition_query(query: str) -> bool:
    q = normalize_key(query)
    return (
        q.startswith("what is")
        or q.startswith("what does")
        or q.startswith("define")
        or q.startswith("meaning of")
    )


def is_exception_query(query: str) -> bool:
    q = normalize_key(query)
    return (
        "service level exception" in q
        or "service level exceptions" in q
        or "exception" in q
        or "exceptions" in q
        or "does not apply" in q
        or "shall not apply" in q
        or "not subject to" in q
        or "exclusion" in q
        or "exclusions" in q
    )


def is_compare_query(query: str) -> bool:
    q = normalize_key(query)
    return "compare" in q or "difference" in q or " vs " in f" {q} " or " versus " in f" {q} "