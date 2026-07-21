import re

from rapidfuzz import fuzz

from app.utils import normalize_key, normalize_ws, stable_dedupe


def service_aliases(service_name: str) -> list[str]:
    full = normalize_ws(service_name)
    aliases = {full, full.replace("–", "-"), full.replace("—", "-")}
    lowered = full.lower()

    # remove vendor prefixes
    for prefix in ("microsoft ", "azure "):
        if lowered.startswith(prefix):
            aliases.add(full[len(prefix):])

    # semicolon split for multi-service titles
    for part in re.split(r"\s*;\s*", full):
        part = normalize_ws(part)
        if part:
            aliases.add(part)
            p_low = part.lower()
            if p_low.startswith("microsoft "):
                aliases.add(part[len("microsoft "):])
            if p_low.startswith("azure "):
                aliases.add(part[len("azure "):])

    # 365 special handling
    tokens = full.split()
    if "365" in tokens:
        idx = tokens.index("365")
        aliases.add(" ".join(tokens[idx:]))          # 365 Business Central
        if idx + 1 < len(tokens):
            aliases.add(" ".join(tokens[idx + 1:])) # Business Central

    # remove common suffixes
    aliases.add(full.replace("Services", "").replace("Service", "").strip())
    aliases.add(full.replace("Online", "").strip())

    if len(tokens) >= 2:
        aliases.add(" ".join(tokens[1:]))

    return stable_dedupe([a for a in aliases if a and len(a.strip()) >= 3])


def resolve_service(query: str, services: list[dict]) -> list[dict]:
    q = normalize_key(query)
    ranked = []

    for svc in services:
        best_score = 0.0
        best_alias = svc["service_name"]

        for alias in service_aliases(svc["service_name"]):
            ak = normalize_key(alias)
            score = 0.0

            if ak and f" {ak} " in f" {q} ":
                score += 200.0 + min(len(ak), 40)

            score += fuzz.partial_ratio(q, ak)
            score += 0.5 * fuzz.token_set_ratio(q, ak)

            q_tokens = set(q.split())
            a_tokens = set(ak.split())
            overlap = len(q_tokens & a_tokens)
            score += overlap * 20

            if score > best_score:
                best_score = score
                best_alias = alias

        if best_score >= 95:
            ranked.append(
                {
                    "service_name": svc["service_name"],
                    "score": best_score,
                    "alias": best_alias,
                }
            )

    ranked.sort(key=lambda x: x["score"], reverse=True)

    out = []
    seen = set()
    for r in ranked:
        k = normalize_key(r["service_name"])
        if k not in seen:
            seen.add(k)
            out.append(r)

    return out[:8]
