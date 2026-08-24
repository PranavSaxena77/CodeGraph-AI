import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import faiss
import numpy as np
from pydantic import TypeAdapter, ValidationError

from app.core.errors import (
    VectorIndexCorruptError,
    VectorIndexNotFoundError,
    VectorStoreError,
)
from app.domain.vector import (
    CodeChunk,
    VectorIndexManifest,
    VectorIndexSpec,
    VectorIndexStatus,
    VectorSearchResponse,
    VectorSearchResult,
)

INDEX_VERSION = "faiss-flatip-v1"
CHUNK_LIST_ADAPTER = TypeAdapter(list[CodeChunk])


class FaissVectorIndex:
    """Persist exact cosine-similarity indexes in immutable snapshot-specific directories."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def get_status(self, spec: VectorIndexSpec) -> VectorIndexStatus | None:
        loaded = self._load(spec, missing_is_error=False)
        if loaded is None:
            return None
        manifest, _, _ = loaded
        return self._status(manifest, idempotent=True)

    def build_index(
        self,
        spec: VectorIndexSpec,
        chunks: list[CodeChunk],
        vectors: list[list[float]],
    ) -> VectorIndexStatus:
        existing = self.get_status(spec)
        if existing is not None:
            return existing
        self._validate_chunks(spec, chunks)
        matrix = (
            np.asarray(vectors, dtype=np.float32)
            if vectors
            else np.empty((0, spec.vector_dimension), dtype=np.float32)
        )
        expected_shape = (len(chunks), spec.vector_dimension)
        if matrix.shape != expected_shape or not np.isfinite(matrix).all():
            raise VectorStoreError("Embedding matrix has an invalid shape or value")
        matrix = np.ascontiguousarray(matrix)
        if len(chunks):
            faiss.normalize_L2(matrix)

        index = faiss.IndexFlatIP(spec.vector_dimension)
        index.add(matrix)
        metadata_bytes = self._metadata_bytes(chunks)
        index_id = self._index_id(spec, chunks)
        directory = self._directory(spec)
        directory.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        index_temp = directory / f"index.{token}.tmp"
        metadata_temp = directory / f"chunks.{token}.tmp"
        manifest_temp = directory / f"manifest.{token}.tmp"
        try:
            faiss.write_index(index, str(index_temp))
            metadata_temp.write_bytes(metadata_bytes)
            manifest = VectorIndexManifest(
                **spec.model_dump(),
                index_id=index_id,
                chunk_count=len(chunks),
                index_checksum=self._checksum(index_temp.read_bytes()),
                metadata_checksum=self._checksum(metadata_bytes),
            )
            manifest_temp.write_text(
                json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(index_temp, directory / "index.faiss")
            os.replace(metadata_temp, directory / "chunks.json")
            os.replace(manifest_temp, directory / "manifest.json")
        except (OSError, RuntimeError) as error:
            raise VectorStoreError("FAISS index persistence failed") from error
        finally:
            for temporary_path in (index_temp, metadata_temp, manifest_temp):
                temporary_path.unlink(missing_ok=True)
        return self._status(manifest, idempotent=False)

    def search(
        self,
        spec: VectorIndexSpec,
        query: str,
        query_vector: list[float],
        top_k: int,
    ) -> VectorSearchResponse:
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50")
        loaded = self._load(spec, missing_is_error=True)
        if loaded is None:
            raise VectorIndexNotFoundError("Vector index was not found")
        _, index, chunks = loaded
        vector = np.asarray([query_vector], dtype=np.float32)
        if vector.shape != (1, spec.vector_dimension) or not np.isfinite(vector).all():
            raise VectorStoreError("Query embedding has an invalid shape or value")
        vector = np.ascontiguousarray(vector)
        faiss.normalize_L2(vector)
        result_count = min(top_k, len(chunks))
        if result_count == 0:
            return VectorSearchResponse(
                repository_id=spec.repository_id,
                snapshot_id=spec.snapshot_id,
                query=query,
            )
        scores, positions = index.search(vector, result_count)
        results = [
            self._search_result(float(score), chunks[int(position)])
            for score, position in zip(scores[0], positions[0], strict=True)
            if position >= 0
        ]
        return VectorSearchResponse(
            repository_id=spec.repository_id,
            snapshot_id=spec.snapshot_id,
            query=query,
            results=results,
        )

    def _load(
        self, spec: VectorIndexSpec, *, missing_is_error: bool
    ) -> tuple[VectorIndexManifest, Any, list[CodeChunk]] | None:
        directory = self._directory(spec)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            if missing_is_error:
                raise VectorIndexNotFoundError("Vector index was not found")
            return None
        index_path = directory / "index.faiss"
        metadata_path = directory / "chunks.json"
        try:
            manifest = VectorIndexManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            self._validate_manifest(spec, manifest)
            index_bytes = index_path.read_bytes()
            metadata_bytes = metadata_path.read_bytes()
            if self._checksum(index_bytes) != manifest.index_checksum:
                raise VectorIndexCorruptError("FAISS index checksum does not match its manifest")
            if self._checksum(metadata_bytes) != manifest.metadata_checksum:
                raise VectorIndexCorruptError("Chunk metadata checksum does not match its manifest")
            chunks = CHUNK_LIST_ADAPTER.validate_json(metadata_bytes)
            index = faiss.read_index(str(index_path))
        except VectorIndexCorruptError:
            raise
        except (OSError, RuntimeError, ValueError, ValidationError) as error:
            raise VectorIndexCorruptError("Vector index manifest or data is corrupt") from error
        if len(chunks) != manifest.chunk_count or index.ntotal != manifest.chunk_count:
            raise VectorIndexCorruptError("Vector index count does not match its manifest")
        if index.d != manifest.vector_dimension:
            raise VectorIndexCorruptError("Vector index dimension does not match its manifest")
        self._validate_chunks(spec, chunks)
        return manifest, index, chunks

    @staticmethod
    def _validate_manifest(spec: VectorIndexSpec, manifest: VectorIndexManifest) -> None:
        for field_name in VectorIndexSpec.model_fields:
            if getattr(spec, field_name) != getattr(manifest, field_name):
                raise VectorIndexCorruptError(
                    f"Vector index manifest {field_name} does not match the request"
                )

    @staticmethod
    def _validate_chunks(spec: VectorIndexSpec, chunks: list[CodeChunk]) -> None:
        seen_ids: set[str] = set()
        for chunk in chunks:
            if (
                chunk.repository_id != spec.repository_id
                or chunk.snapshot_id != spec.snapshot_id
                or chunk.commit_sha != spec.commit_sha
                or chunk.chunking_version != spec.chunking_version
            ):
                raise VectorIndexCorruptError("Chunk metadata crosses vector-index boundaries")
            if chunk.id in seen_ids:
                raise VectorIndexCorruptError("Chunk metadata contains duplicate IDs")
            seen_ids.add(chunk.id)

    def _directory(self, spec: VectorIndexSpec) -> Path:
        repository_key = self._checksum(spec.repository_id.encode("utf-8"))
        snapshot_key = self._checksum(spec.snapshot_id.encode("utf-8"))
        configuration = "\x1f".join(
            (
                spec.embedding_provider,
                spec.embedding_model,
                str(spec.vector_dimension),
                spec.chunking_version,
                spec.index_version,
            )
        )
        configuration_key = self._checksum(configuration.encode("utf-8"))
        return self._root / repository_key / snapshot_key / configuration_key

    @staticmethod
    def _metadata_bytes(chunks: list[CodeChunk]) -> bytes:
        payload = [chunk.model_dump(mode="json") for chunk in chunks]
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _index_id(spec: VectorIndexSpec, chunks: list[CodeChunk]) -> str:
        payload = {
            "spec": spec.model_dump(mode="json"),
            "chunk_ids": [chunk.id for chunk in chunks],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _status(manifest: VectorIndexManifest, *, idempotent: bool) -> VectorIndexStatus:
        return VectorIndexStatus(
            repository_id=manifest.repository_id,
            snapshot_id=manifest.snapshot_id,
            index_id=manifest.index_id,
            chunk_count=manifest.chunk_count,
            vector_dimension=manifest.vector_dimension,
            embedding_provider=manifest.embedding_provider,
            embedding_model=manifest.embedding_model,
            chunking_version=manifest.chunking_version,
            index_version=manifest.index_version,
            idempotent=idempotent,
        )

    @staticmethod
    def _search_result(score: float, chunk: CodeChunk) -> VectorSearchResult:
        return VectorSearchResult(
            score=score,
            chunk_id=chunk.id,
            file_path=chunk.file_path,
            symbol_id=chunk.symbol_id,
            symbol_name=chunk.symbol_name,
            qualified_name=chunk.qualified_name,
            symbol_type=chunk.symbol_type,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
        )
