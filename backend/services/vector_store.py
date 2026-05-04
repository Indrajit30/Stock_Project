import asyncio
import logging
import os
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLECTION = "sec_filings"
VECTOR_SIZE = 1536  # text-embedding-3-small


class VectorStore:
    def __init__(self):
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=os.getenv("QDRANT_URL", "http://localhost:6333")
            )
            await self._ensure_collection()
        return self._client

    async def _ensure_collection(self):
        client = self._client
        existing = {c.name for c in (await client.get_collections()).collections}
        if COLLECTION not in existing:
            await client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            for field, schema_type in [
                ("ticker", models.PayloadSchemaType.KEYWORD),
                ("form_type", models.PayloadSchemaType.KEYWORD),
                ("fiscal_period", models.PayloadSchemaType.KEYWORD),
                ("section", models.PayloadSchemaType.KEYWORD),
            ]:
                await client.create_payload_index(
                    collection_name=COLLECTION,
                    field_name=field,
                    field_schema=schema_type,
                )
            logger.info("Created Qdrant collection: %s", COLLECTION)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        import openai

        oai = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        all_embeddings: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await oai.embeddings.create(
                input=batch, model="text-embedding-3-small"
            )
            all_embeddings.extend([e.embedding for e in resp.data])
        return all_embeddings

    async def upsert_filing_chunks(
        self,
        ticker: str,
        form_type: str,
        period: str,
        chunks: list[dict],
    ):
        client = await self._get_client()
        contextualized = [
            f"This chunk is from {ticker} {form_type} {period}, section: {c['section']}. Content: {c['text']}"
            for c in chunks
        ]
        embeddings = await self._embed(contextualized)
        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{ticker}:{form_type}:{period}:{c['chunk_id']}")),
                vector=emb,
                payload={
                    "ticker": ticker,
                    "form_type": form_type,
                    "fiscal_period": period,
                    "section": c["section"],
                    "text": c["text"],
                    "chunk_id": c["chunk_id"],
                },
            )
            for c, emb in zip(chunks, embeddings)
        ]
        await client.upsert(collection_name=COLLECTION, points=points)
        logger.info("Upserted %d chunks for %s %s %s", len(points), ticker, form_type, period)

    async def hybrid_search(
        self,
        ticker: str,
        query: str,
        top_k: int = 8,
        form_type: str | None = None,
        section: str | None = None,
    ) -> list[dict]:
        from rank_bm25 import BM25Okapi

        client = await self._get_client()

        # Build filter
        must = [FieldCondition(key="ticker", match=MatchValue(value=ticker))]
        if form_type:
            must.append(FieldCondition(key="form_type", match=MatchValue(value=form_type)))
        if section:
            must.append(FieldCondition(key="section", match=MatchValue(value=section)))
        flt = Filter(must=must)

        # Dense search
        query_emb = (await self._embed([query]))[0]
        dense_results = await client.search(
            collection_name=COLLECTION,
            query_vector=query_emb,
            query_filter=flt,
            limit=top_k * 2,
            with_payload=True,
        )

        # BM25 over retrieved corpus
        corpus = [r.payload["text"] for r in dense_results]
        if not corpus:
            return []

        tokenized = [doc.lower().split() for doc in corpus]
        bm25 = BM25Okapi(tokenized)
        bm25_scores = bm25.get_scores(query.lower().split())

        # RRF merge
        def rrf_score(rank: int, k: int = 60) -> float:
            return 1.0 / (k + rank + 1)

        dense_rank = {r.id: i for i, r in enumerate(dense_results)}
        bm25_rank = {dense_results[i].id: i for i in sorted(range(len(bm25_scores)), key=lambda x: -bm25_scores[x])}

        merged: dict[Any, float] = {}
        for rid in dense_rank:
            merged[rid] = merged.get(rid, 0) + rrf_score(dense_rank[rid])
        for rid in bm25_rank:
            merged[rid] = merged.get(rid, 0) + rrf_score(bm25_rank[rid])

        sorted_ids = sorted(merged, key=lambda x: -merged[x])[:top_k]
        id_to_result = {r.id: r for r in dense_results}

        return [
            {
                "text": id_to_result[rid].payload["text"],
                "source": id_to_result[rid].payload.get("section", ""),
                "score": merged[rid],
                "ticker": ticker,
                "form_type": id_to_result[rid].payload.get("form_type"),
                "section": id_to_result[rid].payload.get("section"),
            }
            for rid in sorted_ids
            if rid in id_to_result
        ]

    async def delete_ticker_chunks(self, ticker: str):
        client = await self._get_client()
        await client.delete(
            collection_name=COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]
            ),
        )
        logger.info("Deleted all chunks for %s", ticker)
