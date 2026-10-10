"""Frozen page-text corpus preparation and real PostgreSQL publication.

Only ``gold.documents`` is used during preparation; questions, answers,
requirements, and supporting quotes never influence chunk construction.
Character offsets refer to the unmodified original page ``content`` string.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

NAMESPACE = "evidence-review-live-v1"
USER_ID = str(uuid5(NAMESPACE_URL, "knowhere:evidence-review-live-v1:user"))
POLICY = {
    "version": "page-text-paragraph-windows-v1",
    "source_type": "page",
    "target_characters": 3500,
    "overlap_characters": 400,
    "paragraph_minimum_characters": 1750,
    "offset_unit": "python_unicode_code_points",
    "normalization": "none",
    "summaries_and_assets": "excluded",
}


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_id(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"knowhere:{NAMESPACE}:{kind}:{value}"))


def _windows(content: str):
    """Cover the entire page with bounded, overlapping unmodified slices."""
    start = 0
    while start < len(content):
        end = min(len(content), start + POLICY["target_characters"])
        if end < len(content):
            lower = start + POLICY["paragraph_minimum_characters"]
            boundary = content.rfind("\n\n", lower, end)
            if boundary >= lower:
                end = boundary + 2
            else:
                boundary = content.rfind("\n", lower, end)
                if boundary >= lower:
                    end = boundary + 1
        yield start, end
        if end == len(content):
            return
        start = end - POLICY["overlap_characters"]


def prepare_corpus(repo_root: Path, gold_path: Path) -> dict[str, Any]:
    """Derive all page text from the frozen document inventory, never gold labels."""
    repo_root = repo_root.resolve()
    inventory = json.loads(gold_path.read_text(encoding="utf-8"))["documents"]
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("gold.documents must be a nonempty document inventory")
    documents: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for spec in inventory:
        source_path = (repo_root / spec["source_path"]).resolve()
        if not source_path.is_relative_to(repo_root):
            raise ValueError("corpus source must be inside the repository")
        raw = source_path.read_bytes()
        source_sha = hashlib.sha256(raw).hexdigest()
        if source_sha != spec["source_sha256"]:
            raise ValueError(f"source digest mismatch: {spec['source_path']}")
        doc_key = str(spec.get("doc_key") or spec.get("document_key") or source_path.parent.name)
        if doc_key in seen_keys:
            raise ValueError(f"duplicate corpus doc_key: {doc_key}")
        seen_keys.add(doc_key)
        source_name = str(spec.get("source_file_name") or f"{doc_key}.pdf")
        identity = _digest({
            "doc_key": doc_key, "source_sha256": source_sha,
            "source_file_name": source_name, "policy": POLICY,
        })
        parsed = json.loads(raw)
        originals = parsed["chunks"] if isinstance(parsed, dict) else parsed
        if not isinstance(originals, list):
            raise ValueError(f"source chunks must be a list: {doc_key}")
        chunks: list[dict[str, Any]] = []
        mapping: list[dict[str, Any]] = []
        page_count = 0
        for source_index, original in enumerate(originals):
            if original.get("type", original.get("chunk_type")) != "page":
                continue
            content = original.get("content")
            if not isinstance(content, str) or not content:
                continue
            if "\x00" in content:
                raise ValueError("page contains NUL; publication would change the frozen text")
            original_id = str(original.get("chunk_id") or "")
            if not original_id:
                raise ValueError("page source is missing chunk_id")
            page_count += 1
            page_nums = (original.get("metadata") or {}).get("page_nums") or []
            if not isinstance(page_nums, list):
                page_nums = [page_nums]
            page_nums = [int(number) for number in page_nums]
            for start, end in _windows(content):
                chunk_id = _stable_id("chunk", f"{identity}:{source_index}:{original_id}:{start}:{end}")
                provenance = {
                    "original_chunk_id": original_id,
                    "original_source_index": source_index,
                    "source_start": start,
                    "source_end": end,
                    "original_content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "source_sha256": source_sha,
                    "page_nums": page_nums,
                }
                chunks.append({
                    "chunk_id": chunk_id,
                    "type": "text",
                    "content": content[start:end],
                    "path": f"{source_name}/Page {page_count:04d}/Span {start:06d}-{end:06d}",
                    "order": len(chunks),
                    "metadata": {**provenance, "derivation_policy": POLICY["version"]},
                })
                mapping.append({"chunk_id": chunk_id, **provenance})
        if not chunks:
            raise ValueError(f"no page text found in corpus document: {doc_key}")
        documents.append({
            "doc_key": doc_key,
            "document_id": _stable_id("document", identity),
            "job_id": _stable_id("job", identity),
            "job_result_id": _stable_id("revision", identity),
            "source_path": str(source_path.relative_to(repo_root)),
            "source_sha256": source_sha,
            "source_file_name": source_name,
            "original_page_count": page_count,
            "derived_chunk_count": len(chunks),
            "chunks_sha256": _digest(chunks),
            "chunks": chunks,
            "source_mapping": mapping,
        })
    documents.sort(key=lambda document: document["doc_key"])
    index_sources = [
        "packages/shared-python/shared/services/retrieval/map_unit_index.py",
        "packages/shared-python/shared/services/retrieval/search/lexical_text.py",
        "packages/shared-python/shared/services/retrieval/scoring/score_units.py",
    ]
    index_source_digests = {
        path: hashlib.sha256((repo_root / path).read_bytes()).hexdigest()
        for path in index_sources
    }
    corpus_digest = _digest({
        "policy": POLICY,
        "documents": [{key: doc[key] for key in (
            "doc_key", "document_id", "job_result_id", "source_sha256", "chunks_sha256",
        )} for doc in documents],
    })
    return {
        "schema_version": "evidence-review-live-corpus/1",
        "user_id": USER_ID,
        "namespace": NAMESPACE,
        "policy": dict(POLICY),
        "documents": documents,
        "revision_pins": {doc["document_id"]: doc["job_result_id"] for doc in documents},
        "corpus_digest": corpus_digest,
        "index_source_digests": index_source_digests,
        "index_input_digest": _digest({"corpus": corpus_digest, "sources": index_source_digests}),
    }


def migrate_database(repo_root: Path | None = None) -> dict[str, Any]:
    """Run the repository's real migrations; upgrading an existing head is a no-op."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from shared.core.config import settings
    from shared.services.auth.user_table_bootstrap import ensure_better_auth_user_table

    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    url = (settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL).replace("asyncpg", "psycopg2")
    engine = create_engine(url, poolclass=NullPool, connect_args=settings.get_ssl_connect_args())
    config = Config(str(root / "apps/api/alembic.ini"))
    config.set_main_option("script_location", str(root / "apps/api/alembic"))
    try:
        with engine.connect() as connection:
            ensure_better_auth_user_table(connection)
            connection.commit()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            return {"alembic_heads": list(connection.scalars(text("SELECT version_num FROM alembic_version")))}
    finally:
        engine.dispose()


def _publish(sync_db: Any, document: dict[str, Any]) -> None:
    from shared.services.retrieval.namespace_map_snapshot import patch_namespace_map_snapshot
    from shared.services.retrieval.publication_content import replace_document_revision_content
    from shared.services.retrieval.publication_models import DocumentPublicationScope
    from shared.services.retrieval.serving_generation import (
        advance_namespace_generation,
        lock_namespace_generation,
    )

    scope = DocumentPublicationScope(
        user_id=USER_ID, namespace=NAMESPACE,
        document_id=document["document_id"], job_result_id=document["job_result_id"],
        source_file_name=document["source_file_name"],
    )
    generation = lock_namespace_generation(sync_db, user_id=USER_ID, namespace=NAMESPACE)
    payload = replace_document_revision_content(sync_db, scope=scope, chunks=document["chunks"])
    patch_namespace_map_snapshot(
        sync_db, scope=scope, manifest_payload=payload, current_generation=generation,
    )
    advance_namespace_generation(
        sync_db, user_id=USER_ID, namespace=NAMESPACE, locked_generation=generation,
    )


def _seed_sync(manifest: dict[str, Any]) -> None:
    from psycopg2.extensions import get_wait_callback, set_wait_callback
    from psycopg2.extras import wait_select
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    from shared.core.config import settings

    if manifest["user_id"] != USER_ID or manifest["namespace"] != NAMESPACE:
        raise ValueError("seeding is restricted to the dedicated benchmark scope")
    documents = manifest["documents"]
    wanted = {document["document_id"] for document in documents}
    url = (settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL).replace("asyncpg", "psycopg2")
    engine = create_engine(url, poolclass=NullPool, connect_args=settings.get_ssl_connect_args())
    # The production publication layer uses execute_values when psycopg2 has
    # a cooperative callback. This supported SQL path avoids PGlite's socket
    # COPY-stream limitation without replacing publication/indexing functions.
    # Benchmark seeding is sequential; restore the process-wide callback before
    # returning to the asynchronous retrieval phase.
    previous_wait_callback = get_wait_callback()
    set_wait_callback(wait_select)
    try:
        with Session(engine) as db:
            existing = set(db.scalars(text(
                "SELECT document_id FROM documents WHERE user_id=:user_id AND namespace=:namespace"
            ), {"user_id": USER_ID, "namespace": NAMESPACE}).all())
            if existing - wanted:
                raise ValueError("benchmark namespace contains a different frozen corpus; use a fresh database")
            db.execute(text(
                'INSERT INTO "user" (id, name, email) VALUES (:id, :name, :email) '
                'ON CONFLICT (id) DO NOTHING'
            ), {"id": USER_ID, "name": "Evidence review benchmark", "email": "evidence-benchmark@knowhere.invalid"})
            db.commit()
        for document in documents:
            if _digest(document["chunks"]) != document["chunks_sha256"]:
                raise ValueError("derived chunk manifest was modified after freezing")
            params = {**document, "user_id": USER_ID, "namespace": NAMESPACE}
            with Session(engine) as db:
                db.execute(text("""
                    INSERT INTO jobs (job_id, user_id, job_type, status, source_type, version,
                        webhook_enabled, created_at, updated_at, credits_charged, billing_status)
                    VALUES (:job_id, :user_id, 'document_ingestion', 'done', 'file', 0,
                        false, NOW(), NOW(), 0, 'skipped') ON CONFLICT (job_id) DO NOTHING
                """), params)
                db.execute(text("""
                    INSERT INTO documents (document_id, user_id, namespace, status,
                        source_file_name, parse_track, created_at, updated_at)
                    VALUES (:document_id, :user_id, :namespace, 'active', :source_file_name,
                        'chunk', NOW(), NOW()) ON CONFLICT (document_id) DO NOTHING
                """), params)
                db.execute(text("""
                    INSERT INTO job_results (id, job_id, document_id, delivery_mode, created_at, updated_at)
                    VALUES (:job_result_id, :job_id, :document_id, 'inline', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                """), params)
                db.execute(text("""
                    UPDATE documents SET current_job_result_id=:job_result_id
                    WHERE document_id=:document_id AND user_id=:user_id AND namespace=:namespace
                """), params)
                _publish(db, document)
                db.commit()
    finally:
        engine.dispose()
        set_wait_callback(previous_wait_callback)


async def seed_corpus(manifest: dict[str, Any]) -> dict[str, Any]:
    """Publish with the real cooperative psycopg2 path; validate with asyncpg.

    The synchronous production publication driver avoids pglite-socket's
    asyncpg executemany pipeline limitation. Retrieval remains asynchronous.
    """
    from sqlalchemy import text

    from shared.core.database import AsyncSessionFactory

    if manifest["user_id"] != USER_ID or manifest["namespace"] != NAMESPACE:
        raise ValueError("seeding is restricted to the dedicated benchmark scope")
    for document in manifest["documents"]:
        if _digest(document["chunks"]) != document["chunks_sha256"]:
            raise ValueError("derived chunk manifest was modified after freezing")
    async with AsyncSessionFactory() as db:
        existing = set((await db.scalars(text(
            "SELECT document_id FROM documents WHERE user_id=:user_id AND namespace=:namespace"
        ), {"user_id": USER_ID, "namespace": NAMESPACE})).all())
    if existing:
        wanted = {document["document_id"] for document in manifest["documents"]}
        if existing != wanted:
            raise ValueError("benchmark database has a different or partial corpus; use a fresh database")
        # Never repair an existing corpus silently. Full text, pins, and actual
        # token/index completeness are checked again before reuse.
        return await verify_corpus(manifest)
    await asyncio.to_thread(_seed_sync, manifest)
    return await verify_corpus(manifest)


async def verify_corpus(manifest: dict[str, Any]) -> dict[str, Any]:
    """Check revision pins, exact stored text, completeness markers, and token rows."""
    from sqlalchemy import text

    from shared.core.database import AsyncSessionFactory

    report: list[dict[str, Any]] = []
    async with AsyncSessionFactory() as db:
        rows = (await db.execute(text("""
            SELECT document_id, current_job_result_id FROM documents
            WHERE user_id=:user_id AND namespace=:namespace AND status='active'
        """), {"user_id": USER_ID, "namespace": NAMESPACE})).all()
        pins = {str(row[0]): str(row[1]) for row in rows}
        if pins != manifest["revision_pins"]:
            raise ValueError("published revision pins differ from the frozen manifest")
        for document in manifest["documents"]:
            params = {"document_id": document["document_id"], "revision": document["job_result_id"]}
            stored = (await db.execute(text("""
                SELECT chunk_id, content FROM document_chunks
                WHERE document_id=:document_id AND job_result_id=:revision ORDER BY chunk_id
            """), params)).all()
            expected = sorted((chunk["chunk_id"], chunk["content"]) for chunk in document["chunks"])
            if [tuple(row) for row in stored] != expected:
                raise ValueError(f"stored text differs from source slices: {document['doc_key']}")
            marker = (await db.execute(text("""
                SELECT format_version, unit_count, token_count FROM document_map_unit_indexes
                WHERE document_id=:document_id AND job_result_id=:revision
            """), params)).mappings().one()
            units = (await db.execute(text("""
                SELECT s.section_path, u.unit_kind, u.sort_order,
                    u.path_token_count, u.content_token_count
                FROM document_map_units u JOIN document_sections s ON s.section_id=u.section_id
                WHERE u.document_id=:document_id AND u.job_result_id=:revision
                ORDER BY s.section_path, u.unit_kind, u.sort_order
            """), params)).all()
            tokens = (await db.execute(text("""
                SELECT s.section_path, u.unit_kind, u.sort_order, t.channel, t.token, t.frequency
                FROM document_map_unit_tokens t JOIN document_map_units u ON u.id=t.map_unit_id
                JOIN document_sections s ON s.section_id=u.section_id
                WHERE u.document_id=:document_id AND u.job_result_id=:revision
                ORDER BY s.section_path, u.unit_kind, u.sort_order, t.channel, t.token, t.frequency
            """), params)).all()
            if not units or not tokens or marker["unit_count"] != len(units) or marker["token_count"] != len(tokens):
                raise ValueError(f"incomplete published lexical index: {document['doc_key']}")
            report.append({
                "doc_key": document["doc_key"], "document_id": document["document_id"],
                "job_result_id": document["job_result_id"], "chunk_count": len(stored),
                "map_unit_count": len(units), "token_row_count": len(tokens),
                "index_format_version": marker["format_version"],
                "index_digest": _digest({"units": [tuple(row) for row in units], "tokens": [tuple(row) for row in tokens]}),
            })
    return {
        "status": "verified", "user_id": USER_ID, "namespace": NAMESPACE,
        "revision_pins": pins, "documents": report,
        "chunk_count": sum(doc["chunk_count"] for doc in report),
        "map_unit_count": sum(doc["map_unit_count"] for doc in report),
        "token_row_count": sum(doc["token_row_count"] for doc in report),
        "index_digest": _digest(report), "corpus_digest": manifest["corpus_digest"],
    }
