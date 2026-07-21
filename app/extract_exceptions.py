from app.logging_config import logger
from app.utils import build_citation, normalize_key, normalize_ws, stable_hash


STOP_MARKERS = (
    "additional terms",
    "service credit",
    "uptime percentage",
    "downtime",
    "table of contents / definitions",
    "table of contents",
)

EXCEPTION_MARKERS = (
    "service level exceptions:",
    "service exceptions:",
    "this sla does not apply to:",
    "this service level does not apply to:",
)


def extract_service_exceptions(doc_id: str, services: list[dict]) -> list[dict]:
    rows = []

    for svc in services:
        text = svc.get("text", "") or ""
        lines = [normalize_ws(x) for x in text.split("\n") if normalize_ws(x)]

        i = 0
        while i < len(lines):
            raw_line = lines[i]
            low = normalize_key(raw_line)

            matched_marker = None
            for marker in EXCEPTION_MARKERS:
                if marker in low:
                    matched_marker = marker
                    break

            if matched_marker:
                label = raw_line

                remainder = ""
                parts = raw_line.split(":", 1)
                if len(parts) == 2:
                    remainder = normalize_ws(parts[1])

                buf = []
                if remainder:
                    buf.append(remainder)

                j = i + 1
                while j < len(lines):
                    line = lines[j]
                    line_low = normalize_key(line)

                    if any(line_low.startswith(stop) for stop in STOP_MARKERS) and j > i + 1:
                        break

                    if line.endswith(":") and len(line) < 140 and "exception" not in line_low and j > i + 1:
                        break

                    buf.append(line)
                    j += 1

                exception_text = normalize_ws(" ".join(buf))
                if exception_text:
                    rows.append(
                        {
                            "exception_id": f"exc_{stable_hash(doc_id, svc['service_name'], label, exception_text)}",
                            "doc_id": doc_id,
                            "service_name": svc["service_name"],
                            "section_label": label,
                            "exception_text": exception_text,
                            "page_num": svc.get("start_page"),
                            "citation": build_citation(svc["service_name"], svc.get("start_page"), "service_exception"),
                        }
                    )

                i = j
                continue

            i += 1

    best = {}
    for r in rows:
        best[r["exception_id"]] = r

    rows = list(best.values())
    logger.info(f"[bold yellow]Service exceptions extracted[/] count={len(rows)}")
    return rows