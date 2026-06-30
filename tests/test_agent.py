from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from xml.sax.saxutils import escape

from knowledge_agent.auth import AuthStore
from knowledge_agent.config import Settings
from knowledge_agent.models import SearchResult
from knowledge_agent.pdf_loader import load_document_text
from knowledge_agent.search import SearchProvider
from knowledge_agent.service import KnowledgeAgent
from knowledge_agent.llm import ExtractiveLlmProvider, OpenAICompatibleLlmProvider


def write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    """Write a tiny .docx fixture without depending on Word or LibreOffice."""
    body = "".join(f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>" for paragraph in paragraphs)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


class FakeSearchProvider(SearchProvider):
    """Search provider used by tests to avoid real network calls."""

    def __init__(self) -> None:
        """Track each query issued by the agent."""
        self.calls: list[str] = []

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Return one deterministic web result and record the query."""
        self.calls.append(query)
        return [
            SearchResult(
                title="最新资料",
                url="https://example.com/latest",
                snippet="联网搜索补充了最新信息。",
                fetched_at="2026-06-22T00:00:00+00:00",
            )
        ]


class KnowledgeAgentTest(unittest.TestCase):
    """Integration-style tests for indexing, retrieval, routing, and answer shape."""

    def make_agent(self, root: Path, search_provider: SearchProvider | None = None) -> KnowledgeAgent:
        """Create a temporary agent instance isolated from project runtime data."""
        settings = Settings(
            data_dir=root,
            upload_dir=root / "uploads",
            index_path=root / "index" / "store.json",
            chunk_size=120,
            chunk_overlap=20,
            confidence_threshold=0.72,
            llm_provider="local",
            llm_api_key=None,
        )
        return KnowledgeAgent(settings=settings, search_provider=search_provider, llm_provider=ExtractiveLlmProvider())

    def test_upload_text_indexes_chunks_and_answers_locally(self) -> None:
        """Local-answer flow should summarize knowledge base evidence in Markdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            payload = agent.upload_bytes(
                "rag.txt",
                "RAG 系统会先检索本地知识库，再把相关片段交给模型生成答案。".encode("utf-8"),
            )

            self.assertEqual(payload["chunks"], 1)
            self.assertEqual(payload["source"], "rag.txt")
            response = agent.query("RAG 系统如何回答问题", use_online_fallback=False)

            self.assertFalse(response.used_search)
            self.assertGreater(response.confidence, 0)
            self.assertTrue(response.citations)
            self.assertEqual(response.citations[0].title, "rag.txt")
            self.assertIn("## 回答", response.text)
            self.assertIn("## 依据摘要", response.text)
            self.assertIn("RAG 系统", response.text)

    def test_list_and_delete_documents(self) -> None:
        """Documents can be listed and deleted at document granularity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            payload = agent.upload_bytes("rag.txt", "RAG 系统会检索本地知识库。".encode("utf-8"))

            documents = agent.list_documents()
            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0].doc_id, payload["documentId"])
            self.assertEqual(documents[0].source, "rag.txt")
            self.assertEqual(documents[0].category, "默认")
            self.assertEqual(documents[0].chunks, 1)

            result = agent.delete_document(str(payload["documentId"]))

            self.assertEqual(result["deletedChunks"], 1)
            self.assertEqual(agent.store.count(), 0)
            self.assertEqual(agent.list_documents(), [])

    def test_update_document_renames_source_and_category(self) -> None:
        """Document editing should update its display name and category across stored chunks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            payload = agent.upload_bytes("rag.txt", "RAG 系统会检索本地知识库。".encode("utf-8"), category="默认")

            result = agent.update_document(str(payload["documentId"]), "新文件名.txt", "产品资料")
            documents = agent.list_documents()

            self.assertEqual(result["source"], "新文件名.txt")
            self.assertEqual(result["category"], "产品资料")
            self.assertEqual(result["updatedChunks"], 1)
            self.assertEqual(documents[0].source, "新文件名.txt")
            self.assertEqual(documents[0].category, "产品资料")
            self.assertEqual(documents[0].folder_path, "产品资料")
            self.assertIn("产品资料", agent.list_categories())

    def test_create_folders_allows_three_levels_only(self) -> None:
        """Folder creation should support up to 3 path levels and reject deeper paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))

            first = agent.add_folder("产品")
            second = agent.add_folder("需求", parent_path="产品")
            third = agent.add_folder("2026", parent_path="产品/需求")

            self.assertTrue(first["created"])
            self.assertEqual(second["folderPath"], "产品/需求")
            self.assertEqual(third["folderPath"], "产品/需求/2026")
            self.assertEqual(agent.list_folders(), ["默认", "产品", "产品/需求", "产品/需求/2026"])
            with self.assertRaises(ValueError):
                agent.add_folder("Q1", parent_path="产品/需求/2026")

    def test_create_root_folder_without_parent_path(self) -> None:
        """Root-level folders should be creatable without passing the default folder as parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))

            result = agent.add_folder("白虎纪", parent_path=None)

            self.assertEqual(result["folderPath"], "白虎纪")
            self.assertIn("白虎纪", agent.list_folders())

    def test_rename_parent_folder_updates_children_and_documents(self) -> None:
        """Renaming a parent folder should update child folders and document folder paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            agent.add_folder("产品")
            agent.add_folder("需求", parent_path="产品")
            agent.add_folder("2026", parent_path="产品/需求")
            agent.upload_bytes("prd.txt", "产品需求文档包含用户故事。".encode("utf-8"), folder_path="产品/需求/2026")

            result = agent.rename_folder("产品/需求", "PRD")
            response = agent.query("用户故事", use_online_fallback=False, folder_path="产品/PRD/2026")

            self.assertEqual(result["folderPath"], "产品/PRD")
            self.assertIn("产品/PRD", agent.list_folders())
            self.assertIn("产品/PRD/2026", agent.list_folders())
            self.assertNotIn("产品/需求/2026", agent.list_folders())
            self.assertEqual(agent.list_documents()[0].folder_path, "产品/PRD/2026")
            self.assertTrue(response.local_results)

    def test_delete_folder_moves_nested_documents_to_default(self) -> None:
        """Deleting a folder should preserve nested documents by moving them to the default folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            agent.add_folder("产品")
            agent.add_folder("需求", parent_path="产品")
            agent.upload_bytes("prd.txt", "产品需求文档包含用户故事。".encode("utf-8"), folder_path="产品/需求")

            result = agent.delete_folder("产品")

            self.assertEqual(result["fallbackFolderPath"], "默认")
            self.assertEqual(result["updatedDocuments"], 1)
            self.assertEqual(agent.list_folders(), ["默认"])
            self.assertEqual(agent.list_documents()[0].folder_path, "默认")

    def test_folder_path_filters_query_results(self) -> None:
        """Query folderPath should restrict local retrieval to matching documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            agent.add_folder("前端")
            agent.add_folder("后端")
            agent.upload_bytes("frontend.txt", "Vue 页面使用 Element Plus 组件库。".encode("utf-8"), folder_path="前端")
            agent.upload_bytes("backend.txt", "FastAPI 后端提供文档上传接口。".encode("utf-8"), folder_path="后端")

            frontend_response = agent.query("组件库", use_online_fallback=False, folder_path="前端")
            backend_response = agent.query("组件库", use_online_fallback=False, folder_path="后端")

            self.assertTrue(frontend_response.local_results)
            self.assertEqual(frontend_response.local_results[0].source, "frontend.txt")
            self.assertFalse(backend_response.local_results)

    def test_legacy_category_arguments_still_work_as_folder_paths(self) -> None:
        """Legacy category arguments should still upload, edit, and query folder-compatible paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            payload = agent.upload_bytes("legacy.txt", "旧分类参数仍然可以过滤。".encode("utf-8"), category="旧分类")

            edit_result = agent.update_document(str(payload["documentId"]), "legacy-renamed.txt", "旧分类/归档")
            response = agent.query("过滤", use_online_fallback=False, category="旧分类/归档")

            self.assertEqual(payload["folderPath"], "旧分类")
            self.assertEqual(edit_result["folderPath"], "旧分类/归档")
            self.assertTrue(response.local_results)
            self.assertEqual(response.local_results[0].source, "legacy-renamed.txt")

    def test_category_filters_query_results(self) -> None:
        """Query category should restrict local retrieval to matching documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            agent.upload_bytes("frontend.txt", "Vue 页面使用 Element Plus 组件库。".encode("utf-8"), category="前端")
            agent.upload_bytes("backend.txt", "FastAPI 后端提供文档上传接口。".encode("utf-8"), category="后端")

            frontend_response = agent.query("组件库", use_online_fallback=False, category="前端")
            backend_response = agent.query("组件库", use_online_fallback=False, category="后端")

            self.assertTrue(frontend_response.local_results)
            self.assertEqual(frontend_response.local_results[0].source, "frontend.txt")
            self.assertFalse(backend_response.local_results)
            self.assertEqual(agent.list_categories(), ["默认", "前端", "后端"])

    def test_category_can_exist_without_documents(self) -> None:
        """Manually created categories should be listed before any document is uploaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))

            result = agent.add_category("产品资料")

            self.assertTrue(result["created"])
            self.assertEqual(agent.list_categories(), ["默认", "产品资料"])

    def test_rename_category_updates_existing_documents(self) -> None:
        """Renaming a category should move all existing chunks into the new category name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            agent.upload_bytes("frontend.txt", "Vue 页面使用 Element Plus 组件库。".encode("utf-8"), category="前端")

            result = agent.rename_category("前端", "前端资料")
            response = agent.query("组件库", use_online_fallback=False, category="前端资料")

            self.assertEqual(result["updatedDocuments"], 1)
            self.assertEqual(agent.list_documents()[0].category, "前端资料")
            self.assertTrue(response.local_results)
            self.assertEqual(response.local_results[0].source, "frontend.txt")

    def test_delete_category_reassigns_documents_to_default(self) -> None:
        """Deleting a category should preserve its documents by moving them to the default category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            agent.upload_bytes("backend.txt", "FastAPI 后端提供文档上传接口。".encode("utf-8"), category="后端")

            result = agent.delete_category("后端")

            self.assertEqual(result["fallbackCategory"], "默认")
            self.assertEqual(result["updatedDocuments"], 1)
            self.assertEqual(agent.list_categories(), ["默认"])
            self.assertEqual(agent.list_documents()[0].category, "默认")

    def test_default_category_cannot_be_deleted(self) -> None:
        """The default category is required as a fallback and must not be deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))

            with self.assertRaises(ValueError):
                agent.delete_category("默认")

    def test_low_confidence_query_uses_search_fallback(self) -> None:
        """Low-confidence local retrieval should still trigger search fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            search = FakeSearchProvider()
            agent = self.make_agent(Path(tmpdir), search_provider=search)
            agent.upload_bytes("local.txt", "向量数据库用于保存文本片段的 embedding。".encode("utf-8"))

            response = agent.query("火星基地预算是多少", use_online_fallback=True)

            self.assertTrue(response.used_search)
            self.assertEqual(search.calls, ["火星基地预算是多少"])
            self.assertTrue(any(item.source == "web" for item in response.citations))
            self.assertIn("## 补充说明", response.text)

    def test_freshness_query_forces_search_even_with_local_hit(self) -> None:
        """Freshness-sensitive questions should force online search when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            search = FakeSearchProvider()
            agent = self.make_agent(Path(tmpdir), search_provider=search)
            agent.upload_bytes("local.txt", "OpenAI 模型发布信息需要关注官方更新。".encode("utf-8"))

            response = agent.query("OpenAI 最近7天有什么最新模型发布", use_online_fallback=True)

            self.assertTrue(response.used_search)
            self.assertEqual(len(search.calls), 1)
            self.assertGreaterEqual(response.confidence, 0.78)

    def test_missing_local_evidence_returns_insufficient_basis_message(self) -> None:
        """Queries with no useful local evidence should say the knowledge base is insufficient."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))

            response = agent.query("完全不存在的主题", use_online_fallback=False)

            self.assertFalse(response.used_search)
            self.assertIn("## 回答", response.text)
            self.assertIn("本地知识库没有足够依据", response.text)
            self.assertFalse(response.citations)

    def test_long_chunk_answer_is_summarized_not_copied_verbatim(self) -> None:
        """Long matching documents should produce concise evidence points instead of raw chunk dumps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            long_text = (
                "团队协作需要统一 AI 使用规范，避免每个人生成的代码风格完全不同。"
                "规范应包括命名方式、提交要求、接口文档和测试要求。"
                "如果没有这些约束，项目会出现文档漂移、重复实现和不可理解代码。"
                "知识库问答系统则需要关注文档切片、向量检索、引用来源和置信度。"
                "检索结果不能直接整段贴给用户，而应该先总结，再回答问题。"
            )
            agent.upload_bytes("long.txt", long_text.encode("utf-8"))

            response = agent.query("团队协作为什么需要 AI 使用规范", use_online_fallback=False)

            self.assertIn("## 回答", response.text)
            self.assertIn("## 依据摘要", response.text)
            self.assertLess(len(response.text), len(long_text) + 100)
            self.assertNotIn(long_text, response.text)

    def test_markdown_headings_are_not_used_as_summary_points(self) -> None:
        """Markdown structure in source documents should not become answer evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = self.make_agent(Path(tmpdir))
            document = (
                "### 1. 团队协作问题\n\n"
                "**问题要点：** 面试官关注 AI 生成内容在多人协作中的稳定性。\n\n"
                "**回答总结：** 团队需要统一 AI 使用规范，减少文档漂移和代码风格混乱。\n"
            )
            agent.upload_bytes("markdown.md", document.encode("utf-8"))

            response = agent.query("团队为什么需要 AI 使用规范", use_online_fallback=False)

            self.assertIn("团队需要统一 AI 使用规范", response.text)
            self.assertNotIn("###", response.text)
            self.assertNotIn("问题要点", response.text)

    def test_openai_provider_is_selected_from_settings(self) -> None:
        """OpenAI-compatible provider should be used when .env-style settings request it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                data_dir=root,
                upload_dir=root / "uploads",
                index_path=root / "index" / "store.json",
                llm_provider="openai",
                llm_api_key="test-key",
                llm_base_url="https://example.com/v1",
                llm_model="test-model",
            )
            agent = KnowledgeAgent(settings=settings)

            self.assertIsInstance(agent.llm_provider, OpenAICompatibleLlmProvider)

    def test_auth_store_register_login_and_logout(self) -> None:
        """Local auth storage should support registration, login, token lookup, and logout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AuthStore(Path(tmpdir) / "auth" / "users.json")

            register_result = store.register_user("demo_user", "secret123", "演示用户", remember_me=True)
            login_result = store.authenticate_user("demo_user", "secret123", remember_me=False)
            current_user = store.get_user_by_token(login_result["token"])
            revoked = store.revoke_token(login_result["token"])
            revoked_user = store.get_user_by_token(login_result["token"])
            register_expiry = datetime.fromisoformat(register_result["expiresAt"])
            login_expiry = datetime.fromisoformat(login_result["expiresAt"])
            register_span_days = (register_expiry - datetime.now(register_expiry.tzinfo)).total_seconds() / 86400
            login_span_days = (login_expiry - datetime.now(login_expiry.tzinfo)).total_seconds() / 86400

            self.assertEqual(register_result["user"]["displayName"], "演示用户")
            self.assertEqual(login_result["user"]["username"], "demo_user")
            self.assertEqual(current_user, {"username": "demo_user", "displayName": "演示用户"})
            self.assertGreater(register_span_days, 6.8)
            self.assertLess(login_span_days, 1.2)
            self.assertTrue(revoked)
            self.assertIsNone(revoked_user)

    def test_docx_loader_extracts_word_text(self) -> None:
        """Word .docx files should be converted into indexable plain text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "word.docx"
            write_minimal_docx(path, ["Word 知识库文档", "支持段落提取"])

            text, meta = load_document_text(path)

            self.assertIn("Word 知识库文档", text)
            self.assertEqual(meta["parser"], "python-docx")

    def test_xlsx_loader_extracts_spreadsheet_cells(self) -> None:
        """Excel .xlsx files should expose sheet names and cell values as plain text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sheet.xlsx"
            from openpyxl import Workbook

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "预算"
            sheet.append(["项目", "金额"])
            sheet.append(["RAG", 1200])
            workbook.save(path)

            text, meta = load_document_text(path)

            self.assertIn("# Sheet: 预算", text)
            self.assertIn("RAG | 1200", text)
            self.assertEqual(meta["parser"], "openpyxl")

    def test_csv_loader_extracts_rows(self) -> None:
        """CSV files should be converted into pipe-delimited text rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.csv"
            path.write_text("名称,说明\nExcel,表格知识库\n", encoding="utf-8")

            text, meta = load_document_text(path)

            self.assertIn("Excel | 表格知识库", text)
            self.assertEqual(meta["parser"], "csv")


if __name__ == "__main__":
    unittest.main()
