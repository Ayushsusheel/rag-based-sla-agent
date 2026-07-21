from app.alias_resolver import resolve_service
from app.storage import fetch_service_exceptions, fetch_services


def answer_service_exception_query(doc_id: str, query: str):
    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)

    if not svc_candidates:
        return {
            "answer": "Please specify the Microsoft SLA service name for the exception you want.",
            "resolved_mode": "need_service_name",
            "subqueries": [query],
            "evidence": [],
        }

    if len(svc_candidates) > 1 and svc_candidates[0]["score"] - svc_candidates[1]["score"] <= 8:
        return {
            "answer": "I found multiple matching services. Please specify the service name.",
            "resolved_mode": "ambiguity_service",
            "subqueries": [query],
            "evidence": [],
        }

    svc_name = svc_candidates[0]["service_name"]
    rows = fetch_service_exceptions(doc_id, svc_name)

    if not rows:
        return {
            "answer": f"{svc_name}: I do not have enough evidence in the uploaded document.",
            "resolved_mode": "deterministic_exception",
            "subqueries": [query],
            "evidence": [],
        }

    rows = sorted(rows, key=lambda r: len(r.get("exception_text", "")), reverse=True)

    answer_lines = [f"{svc_name} service level exceptions:"]
    evidence = []
    seen = set()

    for r in rows:
        txt = r["exception_text"].strip()
        if not txt or txt in seen:
            continue
        seen.add(txt)
        answer_lines.append(f"- {txt}")
        evidence.append({
            "entity_id": r["exception_id"],
            "entity_type": "service_exception",
            "service_name": svc_name,
            "topic_name": "",
            "page_num": r.get("page_num"),
            "citation": r.get("citation"),
            "content": txt,
            "score": 1.0,
        })

    return {
        "answer": "\n".join(answer_lines) + " [Source 1]",
        "resolved_mode": "deterministic_exception",
        "subqueries": [query],
        "evidence": evidence[:4],
    }