from app.logging_config import logger
from app.utils import build_citation, normalize_key, normalize_ws, stable_hash


FORMULA_ANCHORS = (
    "calculated using the following formula",
    "is represented by the following formula",
    "represented by the following formula",
    "is calculated using the following formula",
)


def extract_formulas(doc_id: str, services: list[dict]) -> list[dict]:
    formulas = []

    for svc in services:
        lines = [normalize_ws(x) for x in svc["text"].split("\n") if normalize_ws(x)]
        for i, line in enumerate(lines):
            low = normalize_key(line)
            if not any(anchor in low for anchor in FORMULA_ANCHORS):
                continue

            label = line
            for back in range(max(0, i - 3), i):
                prev = lines[back]
                prev_low = normalize_key(prev)
                if (
                    prev.endswith(":")
                    or "uptime calculation" in prev_low
                    or "service levels for" in prev_low
                    or "query availability percentage" in prev_low
                    or "monthly uptime percentage" in prev_low
                    or "good call rate" in prev_low
                    or "recovery time objective" in prev_low
                ):
                    label = prev

            formula_lines = []
            for j in range(i + 1, min(i + 7, len(lines))):
                nxt = lines[j]
                low2 = normalize_key(nxt)

                if low2.startswith(("where ", "service credit", "the following service", "additional terms", "service level exceptions")):
                    break

                formula_lines.append(nxt.replace("−", "-"))

            if not formula_lines:
                continue

            formula_text = " ".join(formula_lines)

            if len(formula_lines) >= 2 and len(formula_lines[1].split()) <= 20:
                formula_text = f"({formula_lines[0]}) / ({formula_lines[1]})"
                if len(formula_lines) >= 3 and "100" in formula_lines[2]:
                    formula_text = f"{formula_text} × 100"

            formula_text = normalize_ws(formula_text)

            formulas.append(
                {
                    "formula_id": f"formula_{stable_hash(doc_id, svc['service_name'], label, formula_text)}",
                    "doc_id": doc_id,
                    "service_name": svc["service_name"],
                    "label": label,
                    "formula_text": formula_text,
                    "page_num": svc.get("start_page"),
                    "citation": build_citation(svc["service_name"], svc.get("start_page"), "formula"),
                }
            )

    best = {}
    for f in formulas:
        best[f["formula_id"]] = f

    formulas = list(best.values())
    logger.info(f"[bold yellow]Formulas extracted[/] count={len(formulas)}")
    return formulas