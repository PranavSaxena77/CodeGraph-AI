import hashlib
from dataclasses import dataclass

from app.domain.analysis import SnapshotAnalysis, StructuralSymbol
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.domain.vector import CodeChunk

CHUNKING_VERSION = "python-semantic-v1"


def normalize_source(source: str) -> str:
    """Normalize line endings and trailing whitespace without changing indentation."""
    return "\n".join(line.rstrip() for line in source.splitlines())


def chunk_embedding_text(chunk: CodeChunk) -> str:
    return (
        f"File: {chunk.file_path}\n"
        f"Symbol: {chunk.qualified_name}\n"
        f"Type: {chunk.symbol_type}\n"
        f"Lines: {chunk.start_line}-{chunk.end_line}\n"
        f"{chunk.content}"
    )


@dataclass(frozen=True, slots=True)
class _ChunkPart:
    start_line: int
    end_line: int
    content: str
    part_index: int


class SemanticChunker:
    """Create deterministic source-evidence chunks using AST symbol boundaries."""

    def __init__(self, max_chunk_chars: int, version: str = CHUNKING_VERSION) -> None:
        if max_chunk_chars < 1:
            raise ValueError("max_chunk_chars must be positive")
        self.max_chunk_chars = max_chunk_chars
        self.version = version

    def build_chunks(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        analysis: SnapshotAnalysis,
        sources: dict[str, str],
    ) -> list[CodeChunk]:
        if analysis.snapshot_id != snapshot.id:
            raise ValueError("Analysis and snapshot identities do not match")

        file_symbols = {
            symbol.file_path: symbol for symbol in analysis.symbols if symbol.symbol_type == "file"
        }
        declarations: dict[str, list[StructuralSymbol]] = {}
        for symbol in analysis.symbols:
            if symbol.symbol_type != "file":
                declarations.setdefault(symbol.file_path, []).append(symbol)

        chunks: list[CodeChunk] = []
        for file_path in sorted(sources):
            file_symbol = file_symbols.get(file_path)
            if file_symbol is None:
                continue
            normalized_source = normalize_source(sources[file_path])
            lines = normalized_source.splitlines()
            if not lines:
                continue

            file_declarations = sorted(
                declarations.get(file_path, []),
                key=lambda symbol: (symbol.start_line, symbol.end_line, symbol.id),
            )
            module_end = file_declarations[0].start_line - 1 if file_declarations else len(lines)
            if module_end >= 1:
                chunks.extend(
                    self._chunks_for_range(
                        repository,
                        snapshot,
                        file_symbol,
                        lines,
                        1,
                        min(module_end, len(lines)),
                        symbol_id=None,
                    )
                )

            for symbol in file_declarations:
                if symbol.start_line > len(lines):
                    continue
                chunks.extend(
                    self._chunks_for_range(
                        repository,
                        snapshot,
                        symbol,
                        lines,
                        symbol.start_line,
                        min(symbol.end_line, len(lines)),
                        symbol_id=symbol.id,
                    )
                )
        return sorted(
            chunks,
            key=lambda chunk: (
                chunk.file_path,
                chunk.start_line,
                chunk.end_line,
                chunk.symbol_id or "",
                chunk.part_index,
                chunk.id,
            ),
        )

    def _chunks_for_range(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        symbol: StructuralSymbol,
        lines: list[str],
        start_line: int,
        end_line: int,
        *,
        symbol_id: str | None,
    ) -> list[CodeChunk]:
        selected_lines = lines[start_line - 1 : end_line]
        parts = self._split_lines(selected_lines, start_line)
        return [
            self._build_chunk(repository, snapshot, symbol, symbol_id, part)
            for part in parts
            if part.content
        ]

    def _split_lines(self, lines: list[str], absolute_start_line: int) -> list[_ChunkPart]:
        parts: list[_ChunkPart] = []
        buffered: list[str] = []
        buffered_start = absolute_start_line
        part_index = 0

        def flush(end_line: int) -> None:
            nonlocal buffered, buffered_start, part_index
            content = "\n".join(buffered)
            if content:
                parts.append(_ChunkPart(buffered_start, end_line, content, part_index))
                part_index += 1
            buffered = []

        for offset, line in enumerate(lines):
            line_number = absolute_start_line + offset
            if len(line) > self.max_chunk_chars:
                if buffered:
                    flush(line_number - 1)
                for start in range(0, len(line), self.max_chunk_chars):
                    content = line[start : start + self.max_chunk_chars]
                    parts.append(_ChunkPart(line_number, line_number, content, part_index))
                    part_index += 1
                buffered_start = line_number + 1
                continue

            candidate = "\n".join([*buffered, line])
            if buffered and len(candidate) > self.max_chunk_chars:
                flush(line_number - 1)
                buffered_start = line_number
            if not buffered:
                buffered_start = line_number
            buffered.append(line)

        if buffered:
            flush(absolute_start_line + len(lines) - 1)
        return parts

    def _build_chunk(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        symbol: StructuralSymbol,
        symbol_id: str | None,
        part: _ChunkPart,
    ) -> CodeChunk:
        content_hash = hashlib.sha256(part.content.encode("utf-8")).hexdigest()
        identity = "\x1f".join(
            (
                repository.id,
                snapshot.id,
                snapshot.commit_sha,
                self.version,
                symbol_id or symbol.id,
                str(part.part_index),
                str(part.start_line),
                str(part.end_line),
                content_hash,
            )
        )
        return CodeChunk(
            id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            repository_id=repository.id,
            snapshot_id=snapshot.id,
            commit_sha=snapshot.commit_sha,
            file_path=symbol.file_path,
            symbol_id=symbol_id,
            symbol_name=symbol.symbol_name,
            qualified_name=symbol.qualified_name,
            symbol_type=symbol.symbol_type,
            start_line=part.start_line,
            end_line=part.end_line,
            content=part.content,
            part_index=part.part_index,
            chunking_version=self.version,
        )
