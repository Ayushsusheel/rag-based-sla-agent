import shutil
from pathlib import Path

from app.config import PIPELINE_VERSION, PROCESSED_DIR, RAW_DIR
from app.docx_canonicalizer import convert_docx_to_pdf
from app.extract_appendix import extract_appendix_topics
from app.extract_chunks import extract_chunks
from app.extract_definitions import extract_definitions
from app.extract_exceptions import extract_service_exceptions
from app.extract_formulas import extract_formulas
from app.extract_rules import extract_rules
from app.extract_summaries import extract_summaries
from app.extract_tables import extract_tables
from app.loader_pdf import extract_pdf_tables, load_pdf_document
from app.logging_config import log_step, logger
from app.slicer import extract_services_from_pdf, extract_top_sections_from_pdf
from app.storage import (
    clear_all_data_duckdb,
    delete_document_all,
    fetch_document,
    init_db,
    replace_appendix_topics,
    replace_chunks,
    replace_definitions,
    replace_formulas,
    replace_raw_tables,
    replace_rules,
    replace_service_exceptions,
    replace_services,
    replace_summaries,
    replace_table_rows,
    replace_top_sections,
    upsert_document,
)
from app.toc_parser import build_service_index, build_top_sections, parse_toc_from_pdf
from app.utils import dump_json, safe_filename, sha256_bytes
from app.vector_store import get_vector_store


def ingest_document(file_path: Path):
    init_db()

    data = file_path.read_bytes()
    doc_id = sha256_bytes(data)[:16]
    ext = file_path.suffix.lower()

    if ext not in {".pdf", ".docx"}:
        raise ValueError("Only PDF and DOCX are supported in this production pipeline.")

    existing = fetch_document(doc_id)
    if existing and existing.get("pipeline_version") == PIPELINE_VERSION:
        logger.info(f"[bold green]Reusing cached document[/] doc_id={doc_id}")
        return {
            "doc_id": existing["doc_id"],
            "file_name": existing["file_name"],
            "payload": {"pipeline_version": existing["pipeline_version"], "reused": True},
        }

    with log_step("ingest_document", file=file_path.name, ext=ext, doc_id=doc_id):
        raw_copy = RAW_DIR / f"{doc_id}_{safe_filename(file_path.name)}"
        raw_copy.parent.mkdir(parents=True, exist_ok=True)
        if not raw_copy.exists():
            shutil.copy2(file_path, raw_copy)

        canonical_pdf_path = raw_copy
        if ext == ".docx":
            canonical_pdf_path = convert_docx_to_pdf(raw_copy, RAW_DIR / "_canonical_pdf")

        loaded = load_pdf_document(canonical_pdf_path)
        pdf_tables = extract_pdf_tables(canonical_pdf_path)

        toc_rows = parse_toc_from_pdf(loaded)
        page_count = len(loaded["pages"])
        top_sections = build_top_sections(doc_id, toc_rows, page_count)
        top_sections = extract_top_sections_from_pdf(loaded, top_sections)
        service_index = build_service_index(doc_id, toc_rows, page_count)
        services = extract_services_from_pdf(loaded, service_index)

        if not top_sections or not services:
            raise ValueError("SLA structure extraction failed. No top sections or services were extracted.")

        raw_tables, table_rows, table_text_chunks = extract_tables(doc_id, pdf_tables, services)
        rules = extract_rules(doc_id, services, raw_tables)
        formulas = extract_formulas(doc_id, services)
        definitions = extract_definitions(doc_id, services, top_sections)
        appendix_topics = extract_appendix_topics(doc_id, top_sections)
        service_exceptions = extract_service_exceptions(doc_id, services)
        summaries = extract_summaries(doc_id, services)
        chunks = extract_chunks(doc_id, services)

        replace_top_sections(doc_id, top_sections)
        replace_services(doc_id, services)
        replace_raw_tables(doc_id, raw_tables)
        replace_table_rows(doc_id, table_rows)
        replace_rules(doc_id, rules)
        replace_formulas(doc_id, formulas)
        replace_definitions(doc_id, definitions)
        replace_appendix_topics(doc_id, appendix_topics)
        replace_service_exceptions(doc_id, service_exceptions)
        replace_summaries(doc_id, summaries)
        replace_chunks(doc_id, chunks)

        store = get_vector_store()
        store.delete_doc(doc_id)

        service_chunk_rows = [
            {
                "entity_id": c["chunk_id"],
                "doc_id": c["doc_id"],
                "entity_type": c["entity_type"],
                "service_name": c["service_name"],
                "topic_name": c["topic_name"],
                "page_num": c["page_num"],
                "citation": c["citation"],
                "content": c["content"],
            }
            for c in chunks
        ]
        store.upsert_service_chunks(service_chunk_rows)

        summary_rows = [
            {
                "entity_id": s["summary_id"],
                "doc_id": s["doc_id"],
                "entity_type": "service_summary",
                "service_name": s["service_name"],
                "topic_name": "",
                "page_num": s["page_num"],
                "citation": s["citation"],
                "content": s["content"],
            }
            for s in summaries
        ]
        store.upsert_service_summaries(summary_rows)

        appendix_rows = [
            {
                "entity_id": a["topic_id"],
                "doc_id": a["doc_id"],
                "entity_type": "appendix_topic",
                "service_name": "",
                "topic_name": a["topic_name"],
                "page_num": a["page_num"],
                "citation": a["citation"],
                "content": a["text"],
            }
            for a in appendix_topics
        ]
        store.upsert_appendix_chunks(appendix_rows)

        definition_rows = [
            {
                "entity_id": d["def_id"],
                "doc_id": d["doc_id"],
                "entity_type": "definition",
                "service_name": d["service_name"],
                "topic_name": "",
                "page_num": d["page_num"],
                "citation": d["citation"],
                "content": f"{d['term']}: {d['definition_text']}",
            }
            for d in definitions
        ]
        store.upsert_definition_text(definition_rows)

        formula_rows = [
            {
                "entity_id": f["formula_id"],
                "doc_id": f["doc_id"],
                "entity_type": "formula",
                "service_name": f["service_name"],
                "topic_name": "",
                "page_num": f["page_num"],
                "citation": f["citation"],
                "content": f"{f['label']} {f['formula_text']}",
            }
            for f in formulas
        ]
        store.upsert_formula_text(formula_rows)

        store.upsert_table_text(table_text_chunks)

        parsed_path = PROCESSED_DIR / f"{doc_id}_meta.json"
        payload = {
            "pipeline_version": PIPELINE_VERSION,
            "toc_count": len(toc_rows),
            "top_section_count": len(top_sections),
            "service_count": len(services),
            "raw_table_count": len(raw_tables),
            "table_row_count": len(table_rows),
            "rule_count": len(rules),
            "formula_count": len(formulas),
            "definition_count": len(definitions),
            "appendix_topic_count": len(appendix_topics),
            "service_exception_count": len(service_exceptions),
            "summary_count": len(summaries),
            "chunk_count": len(chunks),
        }
        dump_json(parsed_path, payload)

        upsert_document(
            {
                "doc_id": doc_id,
                "file_name": file_path.name,
                "file_type": ext.lstrip("."),
                "raw_path": str(raw_copy),
                "canonical_pdf_path": str(canonical_pdf_path),
                "pipeline_version": PIPELINE_VERSION,
            }
        )

        logger.info(f"[bold yellow]Ingestion summary[/] {payload}")
        return {
            "doc_id": doc_id,
            "file_name": file_path.name,
            "payload": payload,
        }


def clear_all_runtime():
    from app.storage import list_documents
    docs = list_documents()
    store = get_vector_store()
    for d in docs:
        try:
            store.delete_doc(d["doc_id"])
        except Exception as e:
            logger.warning(f"Chroma delete warning for doc={d['doc_id']}: {e}")
    clear_all_data_duckdb()


def delete_document_runtime(doc_id: str):
    store = get_vector_store()
    try:
        store.delete_doc(doc_id)
    except Exception as e:
        logger.warning(f"Chroma delete warning for doc={doc_id}: {e}")
    delete_document_all(doc_id)