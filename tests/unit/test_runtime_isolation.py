from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("configured", [False, True], ids=["offline", "canned-generation"])
def test_runtime_startup_json_and_sse_without_experimental_imports(configured) -> None:
    script = textwrap.dedent(
        r"""
        import importlib.abc
        import json
        import sys
        from unittest.mock import AsyncMock, patch

        blocked = (
            "app.experiments", "app.providers.embeddings", "app.providers.device",
            "app.providers.reranker", "app.retrieval.vector", "app.retrieval.hybrid",
            "app.retrieval.fusion", "app.retrieval.reranker", "app.retrieval.self_rag",
            "app.retrieval.query_rewrite", "app.memory", "app.prompts",
            "app.guardrails.hallucination", "qdrant_client", "sentence_transformers",
            "torch", "unstructured", "asyncpg", "modelscope",
        )
        attempts = []

        class RejectExperimentalImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == prefix or fullname.startswith(prefix + ".") for prefix in blocked):
                    attempts.append(fullname)
                    raise ImportError("production attempted experimental import: " + fullname)

        sys.meta_path.insert(0, RejectExperimentalImports())

        import httpx
        from fastapi.testclient import TestClient
        from app.config.settings import Settings
        from app.asgi import app as entry_app
        from app.main import create_app
        from app.providers.fake import FakeLLMProvider
        from app.retrieval.bm25 import BM25Retriever
        from app.schemas.retrieval import RetrievedChunk
        from app.services import container as container_module

        assert entry_app.title == "GeoExplore"
        configured = sys.argv[1] == "True"
        chunk = RetrievedChunk(
            chunk_id="synthetic-seismic-0", document_id="synthetic-seismic",
            title="Synthetic seismic fixture", content="Seismic refraction constrains velocity.",
            score=0.0, metadata={"source_file": "synthetic.pdf", "page_number": "3",
                                 "document_type": "paper", "language": "en"},
        )

        async def synthetic_ingest(*args, **kwargs):
            return BM25Retriever([chunk]), [chunk]

        canned = FakeLLMProvider({"Question:": json.dumps({
            "status": "answered", "answer": "Seismic refraction constrains velocity.",
            "citation_chunk_ids": [chunk.chunk_id],
        })})
        settings = Settings(
            _env_file=None, app_env="testing", log_level="ERROR",
            database_url="sqlite+aiosqlite:///:memory:", redis_url="", qdrant_url="",
            deepseek_api_key="test-only" if configured else "", embedding_api_key="",
        )
        network = AsyncMock(side_effect=AssertionError("unexpected outbound HTTP request"))
        with patch.object(container_module, "ingest_bm25", synthetic_ingest), \
             patch.object(container_module, "DeepSeekProvider", return_value=canned), \
             patch.object(httpx.AsyncClient, "send", network):
            with TestClient(create_app(settings)) as client:
                container = client.app.state.container
                assert container.vector_store is None
                assert container.retriever.backend == "bm25"
                assert not hasattr(container.chat_service, "_reranker")
                expected = "answered" if configured else "evidence_only"
                response = client.post("/api/v1/chat", json={"message": "seismic refraction"})
                assert response.status_code == 200, response.text
                answer = response.json()
                assert answer["status"] == expected, answer
                assert answer["retrieval_backend"] == "bm25"
                assert answer["citations"][0]["chunk_id"] == chunk.chunk_id
                assert answer["citations"][0]["page_number"] == 3
                assert answer["citations"][0]["source_file"] == "synthetic.pdf"
                assert answer["session_id"]

                filtered = client.post("/api/v1/chat", json={
                    "message": "seismic refraction", "session_id": answer["session_id"],
                    "filters": {"document_ids": ["absent-document"]},
                })
                assert filtered.status_code == 200, filtered.text
                assert filtered.json()["status"] == "insufficient_evidence"
                assert filtered.json()["citations"] == []

                stream = client.post("/api/v1/chat/stream", json={"message": "seismic refraction"})
                assert stream.status_code == 200, stream.text
                assert "text/event-stream" in stream.headers["content-type"]
                events = [json.loads(line[6:]) for line in stream.text.splitlines()
                          if line.startswith("data: ")]
                final = next(event["data"] for event in events if event["event"] == "answer")
                assert final["status"] == expected
                assert final["citations"][0]["chunk_id"] == chunk.chunk_id
                assert "".join(event["text"] for event in events if event["event"] == "token") == final["answer"]
                assert events[-1]["event"] == "done"
            network.assert_not_called()
        assert not attempts, attempts
        assert not any(name == prefix or name.startswith(prefix + ".")
                       for name in sys.modules for prefix in blocked)
        print("runtime isolation verified: " + expected)
        """
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(configured)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "runtime isolation verified:" in result.stdout
