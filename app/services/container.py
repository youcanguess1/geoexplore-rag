"""Dependency-injection container and runtime composition."""

from __future__ import annotations

import logging

from app.config.settings import Settings
from app.infra.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.infra.redis_client import connect_redis
from app.providers.base import LLMProvider
from app.providers.deepseek import DeepSeekProvider
from app.providers.fake import OfflineLLMProvider
from app.repositories.db import create_engine, create_session_factory, init_schema
from app.retrieval.base import Retriever
from app.retrieval.bm25 import AsyncBM25Retriever
from app.retrieval.cache import MemoryRetrievalCache, RedisRetrievalCache
from app.retrieval.ingest import ingest_bm25
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)


class AppContainer:
    def __init__(
        self,
        settings: Settings,
        llm: LLMProvider,
        chat_service: ChatService,
        engine,
        session_factory,
        retriever: Retriever,
        redis=None,
        vector_store=None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.chat_service = chat_service
        self.engine = engine
        self.session_factory = session_factory
        self.retriever = retriever
        self.redis = redis
        self.vector_store = vector_store

    async def aclose(self) -> None:
        closer = getattr(self.llm, "aclose", None)
        if closer:
            await closer()
        if self.redis is not None:
            closer = getattr(self.redis, "aclose", None)
            if closer:
                await closer()
        await self.engine.dispose()


async def build_infrastructure(settings: Settings):
    """Create the database session factory and optional Redis connection."""
    engine = create_engine(settings)
    await init_schema(engine)
    session_factory = create_session_factory(engine)
    redis = await connect_redis(settings)
    return engine, session_factory, redis


async def build_retrieval(settings: Settings, redis) -> AsyncBM25Retriever:
    """Build the production BM25 retriever without loading dense embeddings."""
    cache = (
        RedisRetrievalCache(redis, ttl_seconds=settings.retrieval_cache_ttl_seconds)
        if redis is not None
        else MemoryRetrievalCache(ttl_seconds=settings.retrieval_cache_ttl_seconds)
    )
    bm25, _ = await ingest_bm25(
        settings.geological_knowledge_dir,
        settings=settings,
        manifest_path=settings.geological_manifest_path,
    )
    return AsyncBM25Retriever(bm25, cache=cache)


async def build_container(settings: Settings, seed: bool = False) -> AppContainer:
    """Compose runtime services from independently testable infrastructure builders."""
    llm: LLMProvider = (
        DeepSeekProvider(settings) if settings.llm_configured else OfflineLLMProvider()
    )
    engine, session_factory, redis = await build_infrastructure(settings)
    rate_limiter = (
        RedisRateLimiter(redis, limit=settings.rate_limit_per_minute)
        if redis is not None
        else InMemoryRateLimiter(limit=settings.rate_limit_per_minute)
    )
    retriever = await build_retrieval(settings, redis)
    chat_service = ChatService(
        settings=settings,
        llm=llm,
        retriever=retriever,
        session_factory=session_factory,
        rate_limiter=rate_limiter,
    )
    return AppContainer(
        settings=settings,
        llm=llm,
        chat_service=chat_service,
        engine=engine,
        session_factory=session_factory,
        retriever=retriever,
        redis=redis,
        vector_store=None,
    )
