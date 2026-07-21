import re
from rapidfuzz import fuzz

from app.alias_resolver import resolve_service, service_aliases
from app.storage import (
    fetch_all_definitions,
    fetch_definitions_for_service,
    fetch_service_by_name,
    fetch_services,
)
from app.utils import normalize_key, normalize_ws, stable_dedupe, strip_query_prefixes


STOPWORDS = {
    "in", "for", "of", "the", "a", "an", "service", "services",
    "azure", "microsoft", "what", "is", "does", "mean", "means"
}


def _normalize_query_term(query: str) -> str:
    # Preserve quoted exact term if present
    m = re.search(r'"([^"]+)"', query)
    if m:
        return normalize_key(m.group(1))
    m = re.search(r"“([^”]+)”", query)
    if m:
        return normalize_key(m.group(1))
    return strip_query_prefixes(query)


def _find_definition_candidates(term_text: str, definitions: list[dict], preferred_service: str | None = None):
    q = normalize_key(term_text)
    ranked = []

    for d in definitions:
        tk = normalize_key(d["term"])

        score = 0.0
        if tk == q:
            score += 120.0
        if f" {tk} " in f" {q} ":
            score += 60.0

        score += fuzz.partial_ratio(q, tk)
        score += 0.5 * fuzz.token_set_ratio(q, tk)

        if preferred_service and normalize_key(d.get("service_name", "")) == normalize_key(preferred_service):
            score += 20.0

        if score >= 70:
            ranked.append((score, d))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in ranked]


def _extract_target_term(query: str, service_name: str = "") -> str:
    q = _normalize_query_term(query)

    # remove service aliases from target
    if service_name:
        for alias in service_aliases(service_name):
            ak = normalize_key(alias)
            q = re.sub(rf"\b{re.escape(ak)}\b", " ", q)

    tokens = [t for t in q.split() if t not in STOPWORDS]
    q = " ".join(tokens)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _build_service_summary(svc_row: dict, defs: list[dict]) -> str:
    svc_name = svc_row["service_name"]

    # prefer exact first 2–3 canonical-looking definitions only
    useful = []
    for d in defs:
        tk = normalize_key(d["term"])
        if tk in {
            "additional terms",
            "service level exceptions",
            "service exceptions",
            "service credit",
            "uptime percentage",
        }:
            continue
        useful.append(d)

    if useful:
        preferred_terms = []
        for priority in [
            "app",
            "deployment minutes",
            "maximum available minutes",
            "downtime",
            "azure databricks gateway",
            "client",
            "request",
        ]:
            for d in useful:
                if normalize_key(d["term"]) == priority:
                    preferred_terms.append(d)

        if not preferred_terms:
            preferred_terms = useful[:3]

        parts = [f"{d['term']}: {d['definition_text']}" for d in preferred_terms[:3]]
        return f"{svc_name}: " + " ".join(parts)

    lines = [normalize_ws(x) for x in svc_row["text"].split("\n") if normalize_ws(x)]
    body = lines[1:5] if len(lines) > 1 else lines[:4]
    return f"{svc_name}: " + " ".join(body)


def answer_definition_query(doc_id: str, query: str):
    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)

    # ---------------------------------------
    # 1. If no service matched, try exact global definition
    # ---------------------------------------
    if not svc_candidates:
        global_defs = fetch_all_definitions(doc_id)
        normalized_term = _normalize_query_term(query)
        cand_defs = _find_definition_candidates(normalized_term, global_defs)

        if not cand_defs:
            return None

        distinct_services = stable_dedupe(
            [d["service_name"] for d in cand_defs if normalize_ws(d.get("service_name", ""))]
        )

        if normalized_term in {"downtime", "uptime percentage", "service credit"} and distinct_services:
            return {
                "answer": f"'{normalized_term}' is defined differently across multiple services. Please specify the service name.",
                "resolved_mode": "ambiguity_definition",
                "subqueries": [query],
                "evidence": [],
            }

        if len(distinct_services) > 1:
            return {
                "answer": "I found multiple matching service-specific definitions. Please specify the service name.",
                "resolved_mode": "ambiguity_definition",
                "subqueries": [query],
                "evidence": [],
            }

        best = cand_defs[0]
        return {
            "answer": f"{best['term']}: {best['definition_text']} [Source 1]",
            "resolved_mode": "global_definition",
            "subqueries": [query],
            "evidence": [{
                "entity_id": best["def_id"],
                "entity_type": "definition",
                "service_name": best.get("service_name", ""),
                "topic_name": "",
                "page_num": best.get("page_num"),
                "citation": best.get("citation"),
                "content": f"{best['term']}: {best['definition_text']}",
                "score": 1.0,
            }],
        }

    # ---------------------------------------
    # 2. service matched
    # ---------------------------------------
    svc_name = svc_candidates[0]["service_name"]
    svc_row = fetch_service_by_name(doc_id, svc_name)
    defs = fetch_definitions_for_service(doc_id, svc_name)

    # 2a. exact service-title query => summary path
    stripped = strip_query_prefixes(query)
    if stripped == normalize_key(svc_name) or fuzz.partial_ratio(stripped, normalize_key(svc_name)) >= 96:
        return {
            "answer": _build_service_summary(svc_row, defs) + " [Source 1]",
            "resolved_mode": "service_summary",
            "subqueries": [query],
            "evidence": [{
                "entity_id": svc_row["service_id"],
                "entity_type": "service_text",
                "service_name": svc_name,
                "topic_name": "",
                "page_num": svc_row.get("start_page"),
                "citation": f"{svc_name} :: page {svc_row.get('start_page')} :: service_text",
                "content": svc_row["text"][:2600],
                "score": 1.0,
            }],
        }

    # 2b. term query inside service => exact definition
    target_term = _extract_target_term(query, svc_name)
    if target_term:
        cand_defs = _find_definition_candidates(target_term, defs, preferred_service=svc_name)
        if cand_defs:
            best = cand_defs[0]
            return {
                "answer": f"{best['term']}: {best['definition_text']} [Source 1]",
                "resolved_mode": "deterministic_definition",
                "subqueries": [query],
                "evidence": [{
                    "entity_id": best["def_id"],
                    "entity_type": "definition",
                    "service_name": svc_name,
                    "topic_name": "",
                    "page_num": best.get("page_num"),
                    "citation": best.get("citation"),
                    "content": f"{best['term']}: {best['definition_text']}",
                    "score": 1.0,
                }],
            }

    return None