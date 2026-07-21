import re

from app.appendix_resolver import answer_appendix_query
from app.deterministic_credit import answer_credit_query
from app.deterministic_definition import answer_definition_query
from app.deterministic_formula import answer_formula_query
from app.intent_router import (
    detect_appendix_topic,
    is_compare_query,
    is_credit_query,
    is_definition_query,
    is_exception_query,
    is_formula_query,
    is_smalltalk,
)
from app.llm_runtime import ask_llm
from app.logging_config import log_step, logger
from app.retrieval_pipeline import hybrid_retrieve
from app.service_exception_resolver import answer_service_exception_query
from app.storage import (
    add_chat_message,
    fetch_document,
    fetch_service_by_name,
    fetch_services,
)
from app.alias_resolver import resolve_service, service_aliases
from app.utils import extract_percent_value, normalize_key, shorten, stable_dedupe


def _hybrid_answer(query: str, doc_id: str):
    service_name = ""
    topic_name = detect_appendix_topic(query) or ""

    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)
    if svc_candidates:
        service_name = svc_candidates[0]["service_name"]

    evidences = hybrid_retrieve(doc_id, query, service_name=service_name, topic_name=topic_name)
    if not evidences:
        return {
            "answer": "I do not have enough evidence in the uploaded document.",
            "resolved_mode": "no_evidence",
            "subqueries": [query],
            "evidence": [],
        }

    prompt_blocks = []
    for idx, ev in enumerate(evidences[:6], start=1):
        prompt_blocks.append(
            f"[Source {idx}] citation={ev.citation}\n{shorten(ev.content, 1800)}"
        )

    prompt = (
        f"Question:\n{query}\n\n"
        f"Evidence:\n{chr(10).join(prompt_blocks)}\n\n"
        f"Answer only from this evidence. "
        f"Be concise and grounded. "
        f"Cite like [Source 1]. "
        f"If insufficient, say exactly: I do not have enough evidence in the uploaded document."
    )

    logger.info("[bold yellow]Hybrid prompt[/]")
    logger.info(shorten(prompt, 3500))
    answer = ask_llm(prompt)

    return {
        "answer": answer,
        "resolved_mode": "hybrid_rag",
        "subqueries": [query],
        "evidence": [ev.to_dict() for ev in evidences[:6]],
    }


def _compare_answer(query: str, doc_id: str):
    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)

    if len(svc_candidates) < 2:
        return _hybrid_answer(query, doc_id)

    chosen = [x["service_name"] for x in svc_candidates[:3]]
    evidence = []
    prompt_blocks = []

    for idx, svc_name in enumerate(chosen, start=1):
        svc = fetch_service_by_name(doc_id, svc_name)
        if not svc:
            continue

        citation = f"{svc_name} :: page {svc.get('start_page')} :: service_text"
        content = shorten(svc["text"], 2200)

        prompt_blocks.append(f"[Source {idx}] citation={citation}\n{content}")
        evidence.append(
            {
                "entity_id": svc["service_id"],
                "entity_type": "service_text",
                "service_name": svc_name,
                "topic_name": "",
                "page_num": svc.get("start_page"),
                "citation": citation,
                "content": content,
                "score": 1.0,
            }
        )

    prompt = (
        f"Question:\n{query}\n\n"
        f"Evidence:\n{chr(10).join(prompt_blocks)}\n\n"
        f"Compare the services only from the evidence. "
        f"If there are formulas, service-credit thresholds, exceptions, or terms, mention them clearly. "
        f"Cite like [Source 1]. "
        f"If insufficient, say exactly: I do not have enough evidence in the uploaded document."
    )

    logger.info("[bold yellow]Compare prompt[/]")
    logger.info(shorten(prompt, 3500))
    answer = ask_llm(prompt)

    return {
        "answer": answer,
        "resolved_mode": "compare",
        "subqueries": [query],
        "evidence": evidence,
    }


def _force_credit_path(query: str, doc_id: str):
    qk = normalize_key(query)
    pct = extract_percent_value(query)
    if pct is None:
        return None

    credit_like = (
        "credit" in qk
        or "credits" in qk
        or "service credit" in qk
        or "service credits" in qk
        or "applicable" in qk
        or "eligible" in qk
        or "claim" in qk
    )

    if not credit_like:
        return None

    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)
    if svc_candidates:
        logger.info("[bold magenta]FORCED deterministic credit route[/]")
        return answer_credit_query(doc_id, query)

    return None


def _extract_explicit_service(query: str, doc_id: str) -> str:
    services = fetch_services(doc_id)
    svc_candidates = resolve_service(query, services)
    if svc_candidates:
        return svc_candidates[0]["service_name"]
    return ""


def _split_compound_query(query: str) -> list[str]:
    """
    Split multi-intent question into semantic sub-questions.
    Example:
      what is azure databricks and also tell how to calculate uptime percentage for this service
    becomes:
      1. what is azure databricks
      2. how to calculate uptime percentage for this service
    """
    q = query.strip()

    # first split on question marks / new lines
    primary_parts = re.split(r"[?\n]+", q)
    primary_parts = [p.strip(" ,.;") for p in primary_parts if p.strip(" ,.;")]

    final_parts = []

    for part in primary_parts:
        # split on common chaining phrases
        subparts = re.split(
            r"\b(?:and also|also tell me|also tell|also|then tell me|then tell|then|plus)\b",
            part,
            flags=re.IGNORECASE,
        )
        subparts = [s.strip(" ,.;") for s in subparts if s.strip(" ,.;")]
        final_parts.extend(subparts)

    # de-dup preserve order
    out = []
    seen = set()
    for p in final_parts:
        nk = normalize_key(p)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(p)

    return out or [query]


def _inject_service_context(subquery: str, service_name: str) -> str:
    """
    If follow-up clause says 'this service', 'its', etc., convert it into explicit service query.
    """
    if not service_name:
        return subquery

    sq = subquery
    low = normalize_key(sq)

    # if query already contains service alias, keep as-is
    for alias in service_aliases(service_name):
        ak = normalize_key(alias)
        if ak and ak in low:
            return sq

    replacements = [
        (r"\bthis service\b", service_name),
        (r"\bits service\b", service_name),
        (r"\bits\b", service_name),
        (r"\bfor this service\b", f"for {service_name}"),
        (r"\bfor this\b", f"for {service_name}"),
    ]

    for pat, rep in replacements:
        sq = re.sub(pat, rep, sq, flags=re.IGNORECASE)

    low2 = normalize_key(sq)

    # if still no explicit service, append only for deterministic-style follow-up queries
    if normalize_key(service_name) not in low2:
        if is_credit_query(sq) or is_formula_query(sq) or is_exception_query(sq) or is_definition_query(sq):
            sq = f"{sq} in {service_name}"

    return sq.strip()


def _answer_single(query: str, doc_id: str):
    appendix_topic = detect_appendix_topic(query)
    if appendix_topic:
        res = answer_appendix_query(doc_id, query)
        if res:
            return res

    forced_credit = _force_credit_path(query, doc_id)
    if forced_credit:
        return forced_credit

    if is_credit_query(query):
        return answer_credit_query(doc_id, query)

    if is_formula_query(query):
        return answer_formula_query(doc_id, query)

    if is_exception_query(query):
        res = answer_service_exception_query(doc_id, query)
        if res:
            return res

    if is_definition_query(query):
        res = answer_definition_query(doc_id, query)
        if res:
            return res

    if is_compare_query(query):
        return _compare_answer(query, doc_id)

    return _hybrid_answer(query, doc_id)


def answer_query(doc_id: str, session_id: str, query: str):
    doc = fetch_document(doc_id)
    if not doc:
        return {
            "answer": "No document selected.",
            "resolved_mode": "error",
            "subqueries": [query],
            "evidence": [],
        }

    if is_smalltalk(query):
        ans = "Hello! Please ask a question about the uploaded Microsoft SLA document."
        add_chat_message(session_id, doc_id, "user", query)
        add_chat_message(session_id, doc_id, "assistant", ans)
        return {
            "answer": ans,
            "resolved_mode": "smalltalk",
            "subqueries": [query],
            "evidence": [],
        }

    add_chat_message(session_id, doc_id, "user", query)

    with log_step("answer_query", doc_id=doc_id):
        parts = _split_compound_query(query)

        if len(parts) <= 1:
            res = _answer_single(query, doc_id)
            add_chat_message(session_id, doc_id, "assistant", res["answer"])
            return res

        current_service = _extract_explicit_service(query, doc_id)
        sub_answers = []
        subqueries = []
        evidence = []

        for idx, part in enumerate(parts, start=1):
            part_with_context = _inject_service_context(part, current_service)

            # if this clause explicitly contains another service, update context
            maybe_service = _extract_explicit_service(part_with_context, doc_id)
            if maybe_service:
                current_service = maybe_service

            res = _answer_single(part_with_context, doc_id)

            subqueries.extend(res.get("subqueries", [part_with_context]))
            evidence.extend(res.get("evidence", []))
            sub_answers.append(f"{idx}. {res['answer']}")

        final = {
            "answer": "\n".join(sub_answers),
            "resolved_mode": "multi_question",
            "subqueries": subqueries,
            "evidence": evidence[:8],
        }
        add_chat_message(session_id, doc_id, "assistant", final["answer"])
        return final