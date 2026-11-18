"""BM25 lexical retriever over a jieba-tokenised inverted index."""

from __future__ import annotations

from collections import defaultdict

from rank_bm25 import BM25Okapi

from app.retrieval.cache import RetrievalCache
from app.retrieval.chunking import OVERLAP_CHARS
from app.retrieval.filters import effective_filters, matches_retrieval_filters
from app.retrieval.tokenizer import tokenize
from app.schemas.geological import CorpusIdentity
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk

EMBEDDED_TERM_MIN_CHARS = 5
EMBEDDED_TERM_MATCH_BONUS = 2.0


def _embedded_query_term_count(query_tokens: list[str], document_tokens: list[str]) -> int:
    """Count query words recoverable inside whitespace-corrupted English tokens.

    PDF extraction can join adjacent English words (for example,
    ``dippingboundary``). Exact BM25 still handles clean tokens; this signal only
    adds credit when an original query word is embedded in a longer source token.
    """
    query_terms = {
        token
        for token in query_tokens
        if len(token) >= EMBEDDED_TERM_MIN_CHARS and token.isascii() and token.isalpha()
    }
    return sum(
        any(term != token and term in token for token in document_tokens) for term in query_terms
    )


class BM25Retriever:
    """Lexical retriever for technical terms and exact document identifiers."""

    def __init__(
        self,
        corpus: list[RetrievedChunk] | None = None,
        *,
        corpus_identity: CorpusIdentity | None = None,
    ) -> None:
        self._chunks: list[RetrievedChunk] = []
        self._tokenized_chunks: list[list[str]] = []
        self._chunks_by_position: dict[tuple[str, int], RetrievedChunk] = {}
        self._bm25: BM25Okapi | None = None
        self.corpus_identity = corpus_identity
        if corpus:
            self.build(corpus)

    def build(self, corpus: list[RetrievedChunk]) -> None:
        self._chunks = list(corpus)
        self._chunks_by_position = {
            (chunk.document_id, chunk.chunk_index): chunk for chunk in self._chunks
        }
        tokenized = [tokenize(chunk.content) for chunk in self._chunks]
        self._tokenized_chunks = tokenized
        # BM25Okapi requires a non-empty corpus; keep None if ingest has not run.
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        if self._bm25 is None or not self._chunks:
            return []
        filters = effective_filters(filters)
        query_tokens = tokenize(query)
        scores = self._bm25.get_scores(query_tokens)
        candidate_indexes = [
            index
            for index, chunk in enumerate(self._chunks)
            if matches_retrieval_filters(chunk, filters)
        ]
        for index in candidate_indexes:
            scores[index] += EMBEDDED_TERM_MATCH_BONUS * _embedded_query_term_count(
                query_tokens, self._tokenized_chunks[index]
            )
        ranked = sorted(
            candidate_indexes,
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]
        results: list[RetrievedChunk] = []
        for rank, index in enumerate(ranked, start=1):
            # BM25 IDF can be negative on tiny corpora; still return the ranked docs.
            chunk = self._chunks[index].model_copy(deep=True)
            chunk.score = float(scores[index])
            chunk.rank = rank
            chunk.source = "bm25"
            results.append(chunk)
        return results

    def expand_overlapping_predecessors(
        self,
        seeds: list[RetrievedChunk],
        *,
        limit: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        """Complete fixed-window hits with their overlapping predecessor.

        The PDF parser uses overlapping character windows. A BM25 hit can start
        halfway through a sentence or numbered procedure, so the preceding window
        is part of the same evidence unit. Expansion stays on the same document and
        physical page, obeys request filters, and never increases the result limit.
        """
        filters = effective_filters(filters)
        expanded: list[RetrievedChunk] = []
        seen: set[str] = set()
        ranked_seeds = {seed.chunk_id: seed for seed in seeds}

        def append(chunk: RetrievedChunk) -> None:
            if chunk.chunk_id not in seen and len(expanded) < limit:
                expanded.append(chunk.model_copy(deep=True))
                seen.add(chunk.chunk_id)

        for seed in seeds:
            append(seed)
            predecessor = self._chunks_by_position.get((seed.document_id, seed.chunk_index - 1))
            if predecessor is not None and _is_overlapping_predecessor(predecessor, seed):
                if matches_retrieval_filters(predecessor, filters):
                    ranked_predecessor = ranked_seeds.get(predecessor.chunk_id)
                    if ranked_predecessor is not None:
                        append(ranked_predecessor)
                    else:
                        adjacent = predecessor.model_copy(deep=True)
                        adjacent.rank = None
                        adjacent.source = "bm25-adjacent"
                        append(adjacent)
            if len(expanded) >= limit:
                break
        return expanded


def _is_overlapping_predecessor(
    predecessor: RetrievedChunk,
    current: RetrievedChunk,
) -> bool:
    if predecessor.document_id != current.document_id:
        return False
    predecessor_page = predecessor.metadata.get("page_number", "")
    current_page = current.metadata.get("page_number", "")
    if not predecessor_page or predecessor_page != current_page:
        return False
    if predecessor.chunk_index + 1 != current.chunk_index:
        return False

    maximum = min(OVERLAP_CHARS, len(predecessor.content), len(current.content))
    minimum = max(20, OVERLAP_CHARS // 2)
    return any(
        predecessor.content.endswith(current.content[:overlap])
        for overlap in range(maximum, minimum - 1, -1)
    )


class AsyncBM25Retriever:
    """Thin async production adapter for the synchronous BM25 index.

    The existing cache key is safe only for unrestricted searches. Filtered
    requests deliberately bypass both cache reads and writes.
    """

    backend = "bm25"

    def __init__(self, bm25: BM25Retriever, *, cache: RetrievalCache | None = None) -> None:
        self._bm25 = bm25
        self._cache = cache
        self.corpus_identity = bm25.corpus_identity

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        filters = effective_filters(filters)
        cacheable = filters is None
        if self._cache is not None and cacheable:
            cached = await self._cache.get(query, top_k)
            if cached is not None:
                return self._bm25.expand_overlapping_predecessors(
                    cached,
                    limit=top_k,
                    filters=filters,
                )

        chunks = self._bm25.search(query, top_k=top_k, filters=filters)
        if self._cache is not None and cacheable:
            await self._cache.set(query, top_k, chunks)
        return self._bm25.expand_overlapping_predecessors(
            chunks,
            limit=top_k,
            filters=filters,
        )


class InvertedIndex:
    """Tiny helper used in tests to inspect token coverage."""

    def __init__(self, corpus: list[RetrievedChunk]) -> None:
        self.postings: dict[str, set[str]] = defaultdict(set)
        for chunk in corpus:
            for token in tokenize(chunk.content):
                self.postings[token].add(chunk.chunk_id)
