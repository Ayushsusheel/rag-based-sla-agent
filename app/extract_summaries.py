from app.logging_config import logger
from app.utils import build_citation, normalize_ws, stable_hash


def extract_summaries(doc_id: str, services: list[dict]) -> list[dict]:
    summaries = []

    for svc in services:
        lines = [normalize_ws(x) for x in svc["text"].split("\n") if normalize_ws(x)]
        body = lines[1:8] if len(lines) > 1 else lines[:5]
        content = " ".join(body)

        summaries.append(
            {
                "summary_id": f"summary_{stable_hash(doc_id, svc['service_name'])}",
                "doc_id": doc_id,
                "service_name": svc["service_name"],
                "page_num": svc.get("start_page"),
                "citation": build_citation(svc["service_name"], svc.get("start_page"), "service_summary"),
                "content": content,
            }
        )

    logger.info(f"[bold yellow]Summaries extracted[/] count={len(summaries)}")
    return summaries