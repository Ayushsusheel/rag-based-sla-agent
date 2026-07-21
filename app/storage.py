import duckdb

from app.config import DUCKDB_PATH
from app.utils import normalize_key


def get_conn():
    return duckdb.connect(str(DUCKDB_PATH))


def _rows_to_dicts(cur):
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def init_db():
    con = get_conn()

    con.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            file_name TEXT,
            file_type TEXT,
            raw_path TEXT,
            canonical_pdf_path TEXT,
            pipeline_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS top_sections (
            section_id TEXT PRIMARY KEY,
            doc_id TEXT,
            section_name TEXT,
            start_page INTEGER,
            end_page INTEGER,
            text TEXT,
            citation TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS services (
            service_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_group TEXT,
            service_name TEXT,
            service_key TEXT,
            start_page INTEGER,
            end_page INTEGER,
            text TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS definitions (
            def_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            service_group TEXT,
            source_section TEXT,
            term TEXT,
            definition_text TEXT,
            page_num INTEGER,
            citation TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS formulas (
            formula_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            label TEXT,
            formula_text TEXT,
            page_num INTEGER,
            citation TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_tables (
            table_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            table_name TEXT,
            table_type TEXT,
            page_num INTEGER,
            header_json TEXT,
            rows_json TEXT,
            citation TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS table_rows (
            row_id TEXT PRIMARY KEY,
            table_id TEXT,
            doc_id TEXT,
            service_name TEXT,
            table_name TEXT,
            row_order INTEGER,
            row_json TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            rule_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            service_group TEXT,
            metric_name TEXT,
            variant_name TEXT,
            lower_bound DOUBLE,
            lower_inclusive BOOLEAN,
            upper_bound DOUBLE,
            upper_inclusive BOOLEAN,
            credit_percent DOUBLE,
            page_num INTEGER,
            citation TEXT,
            rule_text TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS service_exceptions (
            exception_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            section_label TEXT,
            exception_text TEXT,
            page_num INTEGER,
            citation TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            summary_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            page_num INTEGER,
            citation TEXT,
            content TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT,
            service_name TEXT,
            topic_name TEXT,
            entity_type TEXT,
            page_num INTEGER,
            citation TEXT,
            content TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS appendix_topics (
            topic_id TEXT PRIMARY KEY,
            doc_id TEXT,
            topic_name TEXT,
            text TEXT,
            page_num INTEGER,
            citation TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            session_id TEXT,
            doc_id TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.close()


def upsert_document(row: dict):
    con = get_conn()
    con.execute("DELETE FROM documents WHERE doc_id = ?", [row["doc_id"]])
    con.execute("""
        INSERT INTO documents (
            doc_id, file_name, file_type, raw_path, canonical_pdf_path, pipeline_version
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, [
        row["doc_id"],
        row["file_name"],
        row["file_type"],
        row["raw_path"],
        row["canonical_pdf_path"],
        row["pipeline_version"],
    ])
    con.close()


def fetch_document(doc_id: str):
    con = get_conn()
    cur = con.execute("SELECT * FROM documents WHERE doc_id = ?", [doc_id])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows[0] if rows else None


def list_documents():
    con = get_conn()
    cur = con.execute("""
        SELECT doc_id, file_name, file_type, created_at
        FROM documents
        ORDER BY created_at DESC
    """)
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def _replace_many(con, table_name: str, doc_id: str, rows: list[dict], columns: list[str]):
    con.execute(f"DELETE FROM {table_name} WHERE doc_id = ?", [doc_id])
    if not rows:
        return

    placeholders = ", ".join(["?"] * len(columns))
    col_sql = ", ".join(columns)
    values = []
    for r in rows:
        values.append([r.get(c) for c in columns])

    con.executemany(
        f"INSERT INTO {table_name} ({col_sql}) VALUES ({placeholders})",
        values
    )


def replace_top_sections(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "top_sections", doc_id, rows,
                  ["section_id", "doc_id", "section_name", "start_page", "end_page", "text", "citation"])
    con.close()


def replace_services(doc_id: str, rows: list[dict]):
    best = {}
    for r in rows:
        sid = r["service_id"]
        prev = best.get(sid)
        if prev is None or len(r.get("text", "")) > len(prev.get("text", "")):
            best[sid] = r
    rows = list(best.values())

    con = get_conn()
    _replace_many(con, "services", doc_id, rows,
                  ["service_id", "doc_id", "service_group", "service_name", "service_key", "start_page", "end_page", "text"])
    con.close()


def replace_definitions(doc_id: str, rows: list[dict]):
    best = {}
    for r in rows:
        key = r["def_id"]
        prev = best.get(key)
        if prev is None or len(r.get("definition_text", "")) > len(prev.get("definition_text", "")):
            best[key] = r
    rows = list(best.values())

    con = get_conn()
    _replace_many(con, "definitions", doc_id, rows,
                  ["def_id", "doc_id", "service_name", "service_group", "source_section", "term", "definition_text", "page_num", "citation"])
    con.close()


def replace_formulas(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "formulas", doc_id, rows,
                  ["formula_id", "doc_id", "service_name", "label", "formula_text", "page_num", "citation"])
    con.close()


def replace_raw_tables(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "raw_tables", doc_id, rows,
                  ["table_id", "doc_id", "service_name", "table_name", "table_type", "page_num", "header_json", "rows_json", "citation"])
    con.close()


def replace_table_rows(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "table_rows", doc_id, rows,
                  ["row_id", "table_id", "doc_id", "service_name", "table_name", "row_order", "row_json"])
    con.close()


def replace_rules(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "rules", doc_id, rows,
                  ["rule_id", "doc_id", "service_name", "service_group", "metric_name", "variant_name",
                   "lower_bound", "lower_inclusive", "upper_bound", "upper_inclusive",
                   "credit_percent", "page_num", "citation", "rule_text"])
    con.close()


def replace_service_exceptions(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "service_exceptions", doc_id, rows,
                  ["exception_id", "doc_id", "service_name", "section_label", "exception_text", "page_num", "citation"])
    con.close()


def replace_summaries(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "summaries", doc_id, rows,
                  ["summary_id", "doc_id", "service_name", "page_num", "citation", "content"])
    con.close()


def replace_chunks(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "chunks", doc_id, rows,
                  ["chunk_id", "doc_id", "service_name", "topic_name", "entity_type", "page_num", "citation", "content"])
    con.close()


def replace_appendix_topics(doc_id: str, rows: list[dict]):
    con = get_conn()
    _replace_many(con, "appendix_topics", doc_id, rows,
                  ["topic_id", "doc_id", "topic_name", "text", "page_num", "citation"])
    con.close()


def fetch_services(doc_id: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM services
        WHERE doc_id = ?
        ORDER BY COALESCE(start_page, 999999), service_name
    """, [doc_id])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_service_by_name(doc_id: str, service_name: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM services
        WHERE doc_id = ? AND service_name = ?
    """, [doc_id, service_name])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows[0] if rows else None


def fetch_rules_for_service(doc_id: str, service_name: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM rules
        WHERE doc_id = ? AND service_name = ?
        ORDER BY COALESCE(page_num, 999999), metric_name, variant_name
    """, [doc_id, service_name])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_formulas_for_service(doc_id: str, service_name: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM formulas
        WHERE doc_id = ? AND service_name = ?
        ORDER BY COALESCE(page_num, 999999), label
    """, [doc_id, service_name])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_definitions_for_service(doc_id: str, service_name: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM definitions
        WHERE doc_id = ? AND service_name = ?
        ORDER BY COALESCE(page_num, 999999), term
    """, [doc_id, service_name])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_all_definitions(doc_id: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM definitions
        WHERE doc_id = ?
        ORDER BY COALESCE(page_num, 999999), term
    """, [doc_id])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_appendix_topics(doc_id: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM appendix_topics
        WHERE doc_id = ?
        ORDER BY COALESCE(page_num, 999999), topic_name
    """, [doc_id])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_top_sections(doc_id: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM top_sections
        WHERE doc_id = ?
        ORDER BY COALESCE(start_page, 999999), section_name
    """, [doc_id])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_raw_tables_for_service(doc_id: str, service_name: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM raw_tables
        WHERE doc_id = ? AND service_name = ?
        ORDER BY COALESCE(page_num, 999999), table_name
    """, [doc_id, service_name])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def fetch_service_exceptions(doc_id: str, service_name: str):
    con = get_conn()
    cur = con.execute("""
        SELECT * FROM service_exceptions
        WHERE doc_id = ? AND service_name = ?
        ORDER BY COALESCE(page_num, 999999), section_label
    """, [doc_id, service_name])
    rows = _rows_to_dicts(cur)
    con.close()
    return rows


def search_lexical_entities(doc_id: str, query: str, service_name: str = "", topic_name: str = "", limit: int = 25):
    q = normalize_key(query)
    tokens = [t for t in q.split() if len(t) >= 2]

    con = get_conn()
    rows = []

    datasets = [
        ("chunks", "chunk_id", "entity_type", "service_name", "topic_name", "page_num", "citation", "content"),
        ("summaries", "summary_id", "'service_summary'", "service_name", "''", "page_num", "citation", "content"),
        ("definitions", "def_id", "'definition'", "service_name", "''", "page_num", "citation", "term || ': ' || definition_text"),
        ("formulas", "formula_id", "'formula'", "service_name", "''", "page_num", "citation", "label || ' ' || formula_text"),
        ("appendix_topics", "topic_id", "'appendix_topic'", "''", "topic_name", "page_num", "citation", "text"),
        ("service_exceptions", "exception_id", "'service_exception'", "service_name", "''", "page_num", "citation", "exception_text"),
        ("raw_tables", "table_id", "'table_text'", "service_name", "''", "page_num", "citation", "rows_json"),
    ]

    for table_name, id_col, etype, svc_col, topic_col, page_col, cit_col, content_expr in datasets:
        sql = f"""
            SELECT {id_col} as entity_id, {etype} as entity_type, {svc_col} as service_name,
                   {topic_col} as topic_name, {page_col} as page_num, {cit_col} as citation,
                   {content_expr} as content
            FROM {table_name}
            WHERE doc_id = ?
        """
        params = [doc_id]

        if service_name and svc_col != "''":
            sql += " AND service_name = ?"
            params.append(service_name)
        if topic_name and topic_col != "''":
            sql += " AND topic_name = ?"
            params.append(topic_name)

        cur = con.execute(sql, params)
        rows.extend(_rows_to_dicts(cur))

    con.close()

    scored = []
    for r in rows:
        content_key = normalize_key(r.get("content", ""))
        score = 0.0

        if q and q in content_key:
            score += 50.0

        for tok in tokens:
            if tok in content_key:
                score += 5.0

        if service_name and normalize_key(r.get("service_name", "")) == normalize_key(service_name):
            score += 20.0

        if topic_name and normalize_key(r.get("topic_name", "")) == normalize_key(topic_name):
            score += 20.0

        if score > 0:
            r["score"] = score
            scored.append(r)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def add_chat_message(session_id: str, doc_id: str, role: str, content: str):
    con = get_conn()
    con.execute("""
        INSERT INTO chat_history (session_id, doc_id, role, content)
        VALUES (?, ?, ?, ?)
    """, [session_id, doc_id, role, content])
    con.close()


def get_chat_history(session_id: str, doc_id: str, limit: int = 20):
    con = get_conn()
    cur = con.execute("""
        SELECT role, content
        FROM chat_history
        WHERE session_id = ? AND doc_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, [session_id, doc_id, limit])
    rows = _rows_to_dicts(cur)
    con.close()
    rows.reverse()
    return rows


def clear_chat_history(session_id: str, doc_id: str | None = None):
    con = get_conn()
    if doc_id:
        con.execute("DELETE FROM chat_history WHERE session_id = ? AND doc_id = ?", [session_id, doc_id])
    else:
        con.execute("DELETE FROM chat_history WHERE session_id = ?", [session_id])
    con.close()


def delete_document_all(doc_id: str):
    con = get_conn()
    for tbl in [
        "chat_history",
        "appendix_topics",
        "service_exceptions",
        "chunks",
        "summaries",
        "rules",
        "table_rows",
        "raw_tables",
        "formulas",
        "definitions",
        "services",
        "top_sections",
        "documents",
    ]:
        con.execute(f"DELETE FROM {tbl} WHERE doc_id = ?", [doc_id])
    con.close()


def clear_all_data_duckdb():
    con = get_conn()
    for tbl in [
        "chat_history",
        "appendix_topics",
        "service_exceptions",
        "chunks",
        "summaries",
        "rules",
        "table_rows",
        "raw_tables",
        "formulas",
        "definitions",
        "services",
        "top_sections",
        "documents",
    ]:
        con.execute(f"DELETE FROM {tbl}")
    con.close()