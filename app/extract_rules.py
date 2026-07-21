import re

from app.logging_config import logger
from app.utils import build_citation, json_loads_safe, normalize_key, normalize_ws, stable_hash


def _parse_condition_to_bounds(text: str):
    t = normalize_ws(text).lower()
    t = t.replace("less than or equal to", "<=")
    t = t.replace("greater than or equal to", ">=")
    t = t.replace("less than", "<")
    t = t.replace("greater than", ">")
    t = re.sub(r"\s+", " ", t)

    pairs = re.findall(r"(<=|>=|<|>)\s*(\d+(?:\.\d+)?)\s*%?", t)
    if not pairs:
        return None

    lower = None
    lower_inc = False
    upper = None
    upper_inc = False

    for op, val_str in pairs:
        val = float(val_str)
        if op in (">", ">="):
            lower = val
            lower_inc = op == ">="
        else:
            upper = val
            upper_inc = op == "<="

    return {
        "lower_bound": lower,
        "lower_inclusive": lower_inc,
        "upper_bound": upper,
        "upper_inclusive": upper_inc,
    }


def _parse_credit_percent(value):
    if value is None:
        return None

    s = normalize_ws(str(value))
    if not s:
        return None

    s = s.rstrip("%").strip()
    if not s:
        return None

    s = re.sub(r"\s+", "", s)

    try:
        return float(s)
    except Exception:
        return None


def _looks_like_threshold(text: str) -> bool:
    low = normalize_key(text)
    return bool(re.search(r"(<=|>=|<|>)\s*\d", text)) or "less than" in low or "greater than" in low


def _looks_like_header_cell(text: str) -> bool:
    low = normalize_key(text)
    return low in {
        "uptime percentage",
        "service credit",
        "average email delivery time",
        "query availability percentage",
        "good call rate",
        "availability percentage",
        "monthly uptime percentage",
        "readiness percentage",
        "conformance percentage",
    }


def _extract_credit_from_row(row: list[str]):
    if not row:
        return None, None

    cleaned = [normalize_ws(x) for x in row]
    non_empty = [x for x in cleaned if x]

    if len(non_empty) < 2:
        return None, None

    condition = None
    for cell in non_empty:
        if _looks_like_threshold(cell):
            condition = cell
            break

    if not condition:
        return None, None

    credit = None
    for cell in reversed(non_empty):
        parsed = _parse_credit_percent(cell)
        if parsed is not None:
            credit = parsed
            break

    if credit is None:
        return None, None

    return condition, credit


def _extract_rules_from_service_credit_tables(doc_id: str, raw_tables: list[dict]) -> list[dict]:
    rules = []

    for tbl in raw_tables:
        if tbl.get("table_type") != "service_credit":
            continue

        service_name = tbl["service_name"]
        table_name = tbl["table_name"]
        page_num = tbl.get("page_num")

        try:
            rows = json_loads_safe(tbl["rows_json"])
        except Exception:
            rows = []

        try:
            headers = json_loads_safe(tbl["header_json"])
        except Exception:
            headers = []

        if not rows or len(rows) < 2:
            continue

        metric_name = headers[0] if headers else "Uptime Percentage"
        variant_name = ""

        for row in rows[1:]:
            if not row:
                continue

            if all(_looks_like_header_cell(c) for c in row if normalize_ws(c)):
                continue

            condition, credit = _extract_credit_from_row(row)
            if not condition or credit is None:
                continue

            bounds = _parse_condition_to_bounds(condition)
            if not bounds:
                continue

            rules.append(
                {
                    "rule_id": f"rule_{stable_hash(doc_id, service_name, table_name, condition, str(credit), str(page_num))}",
                    "doc_id": doc_id,
                    "service_name": service_name,
                    "service_group": "",
                    "metric_name": metric_name,
                    "variant_name": variant_name,
                    "lower_bound": bounds["lower_bound"],
                    "lower_inclusive": bounds["lower_inclusive"],
                    "upper_bound": bounds["upper_bound"],
                    "upper_inclusive": bounds["upper_inclusive"],
                    "credit_percent": credit,
                    "page_num": page_num,
                    "citation": build_citation(service_name, page_num, "rule"),
                    "rule_text": f"{condition} -> {credit}%",
                }
            )

    return rules


def _extract_rules_from_service_text(doc_id: str, services: list[dict]) -> list[dict]:
    rules = []
    metric_hints = (
        "uptime percentage",
        "availability percentage",
        "monthly uptime percentage",
        "query availability percentage",
        "good call rate",
        "readiness percentage",
        "conformance percentage",
        "recovery time objective",
    )

    for svc in services:
        lines = [normalize_ws(x) for x in svc["text"].split("\n") if normalize_ws(x)]
        current_metric = "Uptime Percentage"
        current_variant = ""
        i = 0

        while i < len(lines):
            line = lines[i]
            low = normalize_key(line)

            if any(h in low for h in metric_hints):
                current_metric = line

            if line.endswith(":") and len(line) < 180 and "service credit" not in low and "downtime" not in low:
                current_variant = line.rstrip(":")

            if low == "service credit" or low.startswith("service credit for"):
                j = i + 1
                while j < len(lines):
                    row = lines[j]
                    row_low = normalize_key(row)

                    if row_low.startswith(("additional terms", "service level exceptions", "downtime", "uptime calculation")):
                        break

                    same_line = re.match(
                        r"^(.*?(?:<=|>=|<|>|less than|greater than).*?)\s+(\d+(?:\.\d+)?)\s*%?$",
                        row,
                        flags=re.IGNORECASE,
                    )
                    if same_line:
                        cond = same_line.group(1)
                        credit = _parse_credit_percent(same_line.group(2))
                        bounds = _parse_condition_to_bounds(cond)

                        if bounds and credit is not None:
                            rules.append(
                                {
                                    "rule_id": f"rule_{stable_hash(doc_id, svc['service_name'], current_metric, current_variant, cond, str(credit))}",
                                    "doc_id": doc_id,
                                    "service_name": svc["service_name"],
                                    "service_group": svc.get("service_group", ""),
                                    "metric_name": current_metric,
                                    "variant_name": current_variant,
                                    "lower_bound": bounds["lower_bound"],
                                    "lower_inclusive": bounds["lower_inclusive"],
                                    "upper_bound": bounds["upper_bound"],
                                    "upper_inclusive": bounds["upper_inclusive"],
                                    "credit_percent": credit,
                                    "page_num": svc.get("start_page"),
                                    "citation": build_citation(svc["service_name"], svc.get("start_page"), "rule"),
                                    "rule_text": f"{normalize_ws(cond)} -> {credit}%",
                                }
                            )
                            j += 1
                            continue

                    if _looks_like_threshold(row):
                        if j + 1 < len(lines):
                            credit = _parse_credit_percent(lines[j + 1])
                            cond = row
                            bounds = _parse_condition_to_bounds(cond)

                            if bounds and credit is not None:
                                rules.append(
                                    {
                                        "rule_id": f"rule_{stable_hash(doc_id, svc['service_name'], current_metric, current_variant, cond, str(credit))}",
                                        "doc_id": doc_id,
                                        "service_name": svc["service_name"],
                                        "service_group": svc.get("service_group", ""),
                                        "metric_name": current_metric,
                                        "variant_name": current_variant,
                                        "lower_bound": bounds["lower_bound"],
                                        "lower_inclusive": bounds["lower_inclusive"],
                                        "upper_bound": bounds["upper_bound"],
                                        "upper_inclusive": bounds["upper_inclusive"],
                                        "credit_percent": credit,
                                        "page_num": svc.get("start_page"),
                                        "citation": build_citation(svc["service_name"], svc.get("start_page"), "rule"),
                                        "rule_text": f"{normalize_ws(cond)} -> {credit}%",
                                    }
                                )
                                j += 2
                                continue

                    if j > i + 12:
                        break

                    j += 1

                i = j
                continue

            i += 1

    return rules


def extract_rules(doc_id: str, services: list[dict], raw_tables: list[dict]) -> list[dict]:
    table_rules = _extract_rules_from_service_credit_tables(doc_id, raw_tables)
    text_rules = _extract_rules_from_service_text(doc_id, services)

    best = {}
    for r in table_rules + text_rules:
        key = (
            r["service_name"],
            normalize_key(r["metric_name"] or ""),
            normalize_key(r["variant_name"] or ""),
            r["lower_bound"],
            r["upper_bound"],
            r["credit_percent"],
        )
        best[key] = r

    rules = list(best.values())
    logger.info(f"[bold yellow]Rules extracted[/] count={len(rules)}")
    return rules