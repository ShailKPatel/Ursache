"""Idempotently create versioned Qdrant collections and point stable aliases at them."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qdrant_client import AsyncQdrantClient, models

from ursache.config import Settings

logger = logging.getLogger(__name__)

PayloadIndexes = dict[str, models.PayloadSchemaType]


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    alias: str
    dense: dict[str, models.VectorParams]
    sparse: dict[str, models.SparseVectorParams] = field(
        default_factory=dict[str, models.SparseVectorParams]
    )
    payload_indexes: PayloadIndexes = field(default_factory=PayloadIndexes)


def collection_specs(settings: Settings) -> list[CollectionSpec]:
    cosine = models.Distance.COSINE
    t = models.PayloadSchemaType
    return [
        CollectionSpec(
            name=settings.qdrant_doc_chunks_collection,
            alias=settings.qdrant_doc_chunks_alias,
            dense={"dense": models.VectorParams(size=settings.embedding_dim, distance=cosine)},
            sparse={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
            payload_indexes={
                "chunk_id": t.UUID,
                "doc_type": t.KEYWORD,
                "language": t.KEYWORD,
                "line_ids": t.UUID,
                "equipment_ids": t.UUID,
                "effective_from": t.DATETIME,
                "effective_to": t.DATETIME,
            },
        ),
        CollectionSpec(
            name=settings.qdrant_defect_images_collection,
            alias=settings.qdrant_defect_images_alias,
            dense={
                "gemb2": models.VectorParams(size=settings.embedding_dim, distance=cosine),
                "dino": models.VectorParams(size=settings.dino_dim, distance=cosine),
            },
            payload_indexes={
                "image_id": t.UUID,
                "defect_class": t.KEYWORD,
                "line_id": t.UUID,
                "coil_id": t.UUID,
                "detected_at": t.DATETIME,
                "severity": t.INTEGER,
            },
        ),
    ]


def make_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        cloud_inference=settings.qdrant_cloud_inference,
        timeout=10,
    )


async def ensure_collection(client: AsyncQdrantClient, spec: CollectionSpec) -> bool:
    """Create the collection, payload indexes and alias if missing. Returns True if created."""
    created = False
    if not await client.collection_exists(spec.name):
        await client.create_collection(
            collection_name=spec.name,
            vectors_config=spec.dense,
            sparse_vectors_config=spec.sparse or None,
        )
        created = True
        logger.info("created collection", extra={"collection": spec.name})

    existing = (await client.get_collection(spec.name)).payload_schema
    for field_name, schema in spec.payload_indexes.items():
        if field_name not in existing:
            await client.create_payload_index(
                spec.name, field_name=field_name, field_schema=schema, wait=True
            )

    aliases = (await client.get_aliases()).aliases
    current = next((a.collection_name for a in aliases if a.alias_name == spec.alias), None)
    if current != spec.name:
        # Delete + create in one request so the alias switch is atomic.
        ops: list[models.AliasOperations] = []
        if current is not None:
            ops.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=spec.alias))
            )
        ops.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=spec.name, alias_name=spec.alias)
            )
        )
        await client.update_collection_aliases(change_aliases_operations=ops)
        logger.info("alias set", extra={"alias": spec.alias, "collection": spec.name})
    return created


async def bootstrap(settings: Settings, client: AsyncQdrantClient | None = None) -> list[str]:
    owns_client = client is None
    qdrant = client or make_qdrant_client(settings)
    try:
        return [
            spec.name
            for spec in collection_specs(settings)
            if await ensure_collection(qdrant, spec)
        ]
    finally:
        if owns_client:
            await qdrant.close()
