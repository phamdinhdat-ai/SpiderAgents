"""PDF ingestion, recovery and local retrieval without an embedding service."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject,
)

from openspider.knowledge.chunker import TextChunker
from openspider.knowledge.knowledge_base_manager import KnowledgeBaseManager
from openspider.knowledge.models import DocumentScope, DocumentStatus
from openspider.knowledge.storage_backend import LocalStorageBackend
from openspider.knowledge.vector_store import LocalVectorStore


@pytest.fixture
async def kb(tmp_path):
    manager = KnowledgeBaseManager(str(tmp_path / "workspace"), "default")
    manager._ensure_dirs()
    manager._chunker = TextChunker()
    manager._embedding_config = {"dimensions": 8}
    manager._storage_backend = LocalStorageBackend(manager._files_dir)
    manager._vector_store = LocalVectorStore("kb_test", str(manager._store_dir))
    await manager._storage_backend.start()
    await manager._vector_store.start()
    yield manager
    await manager.close()


@pytest.fixture
def pdf(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 50 700 Td (Probability distributions) Tj ET")
    page[NameObject("/Contents")] = content
    path = tmp_path / "probability.pdf"
    writer.write(path)
    return path


async def test_pdf_upload_and_search_without_embeddings(kb, pdf):
    doc = await kb.ingest_document(pdf, owner="alice")
    assert doc.status == DocumentStatus.READY
    assert doc.chunk_count > 0
    results = await kb.search("probability", user_id="alice")
    assert results[0].document_id == doc.id
    assert results[0].filename == pdf.name
    assert "Probability" in results[0].text


async def test_missing_pdf_dependency_can_be_recovered(kb, pdf, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setitem(__import__("sys").modules, "pdfplumber", None)
        patch.setitem(__import__("sys").modules, "pypdf", None)
        doc = await kb.ingest_document(pdf, owner="alice")
    assert doc.status == DocumentStatus.ERROR
    assert "Neither pdfplumber nor pypdf" in doc.error_message
    original = (doc.id, doc.file_path, doc.created_at)
    summary = await kb.reindex_all(user_id="alice")
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}
    assert doc.status == DocumentStatus.READY
    assert doc.error_message is None
    assert (doc.id, doc.file_path, doc.created_at) == original
    assert len(kb._document_registry) == 1


async def test_reindex_ready_document_preserves_chunks_acl_and_identity(kb, pdf):
    doc = await kb.ingest_document(pdf, owner="alice")
    doc.scope = DocumentScope.SHARED
    doc.shared_with = ["bob"]
    for _ in range(2):
        assert (await kb.reindex_all(user_id="alice"))["succeeded"] == 1
        assert await kb._vector_store.count() == doc.chunk_count
    assert len(kb._document_registry) == 1
    assert doc.shared_with == ["bob"]
    assert doc.scope == DocumentScope.SHARED
    assert (await kb.search("probability", user_id="bob"))[0].document_id == doc.id
    assert await kb.search("probability", user_id="mallory") == []
    restored = KnowledgeBaseManager(str(kb.working_dir), "default")
    restored._load_registry()
    assert restored._document_registry[doc.id].status == DocumentStatus.READY
    store = LocalVectorStore("kb_test", str(kb._store_dir))
    await store.start()
    assert await store.count() == doc.chunk_count


async def test_reindex_does_not_modify_shared_document_owned_by_other_user(kb, pdf):
    doc = await kb.ingest_document(pdf, owner="alice")
    doc.scope = DocumentScope.SHARED
    doc.shared_with = ["bob"]
    kb._vector_store.delete = AsyncMock()
    assert await kb.reindex_all(user_id="bob") == {
        "total": 0, "succeeded": 0, "failed": 0,
    }
    kb._vector_store.delete.assert_not_awaited()


@pytest.mark.parametrize("failure", ["missing", "empty", "embedding"])
async def test_reindex_reports_failure_without_duplicate_records(kb, pdf, failure):
    doc = await kb.ingest_document(pdf, owner="alice")
    if failure == "missing":
        Path(doc.file_path).unlink()
    elif failure == "empty":
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.write(doc.file_path)
    else:
        kb._embed_texts = AsyncMock(side_effect=RuntimeError("Embedding unavailable"))
    summary = await kb.reindex_all(user_id="alice")
    assert summary == {"total": 1, "succeeded": 0, "failed": 1}
    assert doc.status == DocumentStatus.ERROR
    assert doc.error_message
    assert doc.chunk_count == 0
    assert await kb._vector_store.count() == 0
    assert list(kb._document_registry) == [doc.id]


async def test_storage_failure_does_not_leave_indexing_status(kb, pdf):
    kb._storage_backend.store = AsyncMock(side_effect=OSError("Storage unavailable"))
    doc = await kb.ingest_document(pdf)
    assert doc.status == DocumentStatus.ERROR
    assert doc.error_message == "Storage unavailable"


async def test_keyword_search_filters_acl_kb_before_limit_and_normalizes_vietnamese(kb, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Xác suất và phân bố xác suất. Độc lập.", encoding="utf-8")
    for _ in range(30):
        # Different filenames avoid deduplication of the inaccessible candidates.
        await kb.ingest_document(path, owner="other", original_name=f"hidden-{_}.txt")
    visible = await kb.ingest_document(path, owner="alice", kb_name="statistics")
    assert (await kb.search("xac suat", user_id="alice", top_k=1))[0].document_id == visible.id
    assert (await kb.search("độc lập", user_id="alice"))[0].document_id == visible.id
    assert await kb.search("xac suat", user_id="alice", kb_names=["default"]) == []
    assert await kb.search("unrelated", user_id="alice") == []
    assert await kb.search(" ", user_id="alice") == []


async def test_reindex_uses_storage_retrieval(kb, pdf):
    doc = await kb.ingest_document(pdf)
    local = Path(doc.file_path)
    doc.file_path = "s3://bucket/document.pdf"
    kb._storage_backend.retrieve = AsyncMock(return_value=local)
    assert (await kb.reindex_all())["succeeded"] == 1
    kb._storage_backend.retrieve.assert_awaited_once_with(doc.file_path)
    assert len(kb._document_registry) == 1
