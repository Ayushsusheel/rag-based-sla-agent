from rapidfuzz import fuzz

from app.alias_resolver import resolve_service
from app.storage import fetch_formulas_for_service, fetch_services
from app.utils import normalize_key


def answer_formula_query(doc_id: str, query: str):
    services = fetch_services(doc_id)
    candidates = resolve_service(query, services)

    if not candidates:
        return {
            "answer": "Please specify the Microsoft SLA service name for the formula you want.",
            "resolved_mode": "need_service_name",
            "subqueries": [query],
            "evidence": [],
        }

    if len(candidates) > 1 and candidates[0]["score"] - candidates[1]["score"] <= 8:
        return {
            "answer": "I found multiple matching services. Please specify the service name.",
            "resolved_mode": "ambiguity_service",
            "subqueries": [query],
            "evidence": [],
        }

    svc_name = candidates[0]["service_name"]
    formulas = fetch_formulas_for_service(doc_id, svc_name)

    if not formulas:
        return {
            "answer": f"{svc_name}: I do not have enough evidence in the uploaded document.",
            "resolved_mode": "deterministic_formula",
            "subqueries": [query],
            "evidence": [],
        }

    if len(formulas) > 1:
        q = normalize_key(query)
        ranked = []
        for f in formulas:
            score = fuzz.partial_ratio(q, normalize_key(f["label"]))
            ranked.append((score, f))
        ranked.sort(key=lambda x: x[0], reverse=True)

        if ranked[0][0] < 70:
            labels = ", ".join([f["label"] for _, f in ranked[:6]])
            return {
                "answer": f"{svc_name} has multiple formulas. Please specify one of: {labels}",
                "resolved_mode": "ambiguity_formula_group",
                "subqueries": [query],
                "evidence": [],
            }

        chosen = ranked[0][1]
    else:
        chosen = formulas[0]

    return {
        "answer": f"{svc_name}: {chosen['formula_text']} [Source 1]",
        "resolved_mode": "deterministic_formula",
        "subqueries": [query],
        "evidence": [
            {
                "entity_id": chosen["formula_id"],
                "entity_type": "formula",
                "service_name": svc_name,
                "topic_name": "",
                "page_num": chosen.get("page_num"),
                "citation": chosen.get("citation"),
                "content": chosen.get("formula_text", ""),
                "score": 1.0,
            }
        ],
    }