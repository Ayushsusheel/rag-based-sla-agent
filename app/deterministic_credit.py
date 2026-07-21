from app.storage import fetch_rules_for_service, fetch_services
from app.alias_resolver import resolve_service
from app.utils import extract_percent_value, normalize_key


def _choose_best_rule(value: float, rules: list[dict]):
    matched = []

    for r in rules:
        lb = r.get("lower_bound")
        ub = r.get("upper_bound")
        lb_inc = bool(r.get("lower_inclusive", 0))
        ub_inc = bool(r.get("upper_inclusive", 0))

        ok = True
        if lb is not None:
            if lb_inc:
                if value < lb:
                    ok = False
            else:
                if value <= lb:
                    ok = False

        if ub is not None:
            if ub_inc:
                if value > ub:
                    ok = False
            else:
                if value >= ub:
                    ok = False

        if ok:
            matched.append(r)

    if not matched:
        return None

    # Highest credit among matched thresholds wins
    matched.sort(
        key=lambda r: (
            float(r.get("credit_percent") or 0.0),
            -(r.get("lower_bound") or -1e9),
            (r.get("upper_bound") or 1e9),
        ),
        reverse=True,
    )
    return matched[0]


def answer_credit_query(doc_id: str, query: str):
    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)

    if not svc_candidates:
        return {
            "answer": "Please specify the Microsoft SLA service name.",
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

    value = extract_percent_value(query)
    svc_name = svc_candidates[0]["service_name"]

    rules = fetch_rules_for_service(doc_id, svc_name)
    if not rules:
        return {
            "answer": f"{svc_name}: I do not have enough evidence in the uploaded document.",
            "resolved_mode": "deterministic_credit",
            "subqueries": [query],
            "evidence": [],
        }

    match = _choose_best_rule(value, rules)

    if not match:
        return {
            "answer": f"{svc_name}: no service credit applies because uptime percentage {value}% does not breach any listed threshold.",
            "resolved_mode": "deterministic_credit",
            "subqueries": [query],
            "evidence": [],
        }

    credit = float(match["credit_percent"])
    credit_str = int(credit) if credit.is_integer() else credit

    return {
        "answer": f"{svc_name}: for uptime percentage {value}%, the applicable service credit is {credit_str}% [Source 1]",
        "resolved_mode": "deterministic_credit",
        "subqueries": [query],
        "evidence": [{
            "entity_id": match["rule_id"],
            "entity_type": "rule",
            "service_name": svc_name,
            "topic_name": "",
            "page_num": match.get("page_num"),
            "citation": match.get("citation"),
            "content": match.get("rule_text", ""),
            "score": 1.0,
        }],
    }