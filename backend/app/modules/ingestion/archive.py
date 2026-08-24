import stat
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.core.errors import ArchiveLimitError, UnsafeArchiveError

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "pycache",
        "site-packages",
        "venv",
    }
)


class SafeZipExtractor:
    """Extract ZIP data without trusting member paths, types, or declared sizes."""

    def __init__(self, max_members: int, max_extracted_bytes: int, max_file_bytes: int) -> None:
        self._max_members = max_members
        self._max_extracted_bytes = max_extracted_bytes
        self._max_file_bytes = max_file_bytes

    def extract(self, archive: bytes, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        destination_root = destination.resolve()
        try:
            with ZipFile(BytesIO(archive)) as zip_file:
                members = zip_file.infolist()
                self._validate_member_count(members)
                archive_root = self._extract_members(zip_file, members, destination_root)
        except BadZipFile as error:
            raise UnsafeArchiveError("Repository archive is not a valid ZIP file") from error
        return archive_root

    def _validate_member_count(self, members: list[ZipInfo]) -> None:
        if len(members) > self._max_members:
            raise ArchiveLimitError("Repository archive contains too many members")

    def _extract_members(
        self,
        zip_file: ZipFile,
        members: list[ZipInfo],
        destination_root: Path,
    ) -> Path:
        total_size = 0
        top_level_names: set[str] = set()
        seen_targets: set[Path] = set()

        for member in members:
            relative_path = self._validate_member(member)
            if relative_path is None:
                continue
            top_level_names.add(relative_path.parts[0])
            target = (destination_root / Path(*relative_path.parts)).resolve()
            if not target.is_relative_to(destination_root):
                raise UnsafeArchiveError("Repository archive contains path traversal")
            if target in seen_targets:
                raise UnsafeArchiveError("Repository archive contains duplicate members")
            seen_targets.add(target)

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            total_size += member.file_size
            if member.file_size > self._max_file_bytes:
                raise ArchiveLimitError("Repository archive contains an oversized file")
            if total_size > self._max_extracted_bytes:
                raise ArchiveLimitError("Repository archive exceeds the extracted-size limit")

            target.parent.mkdir(parents=True, exist_ok=True)
            self._copy_member(zip_file, member, target)

        if len(top_level_names) == 1:
            candidate = destination_root / next(iter(top_level_names))
            if candidate.is_dir():
                return candidate
        return destination_root

    @staticmethod
    def _validate_member(member: ZipInfo) -> PurePosixPath | None:
        name = member.filename
        if not name or "\x00" in name or "\\" in name or len(name) > 4096:
            raise UnsafeArchiveError("Repository archive contains an unsafe member name")
        if member.flag_bits & 0x1:
            raise UnsafeArchiveError("Encrypted archive members are not supported")

        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise UnsafeArchiveError("Repository archive contains path traversal")
        cleaned_parts = tuple(part for part in path.parts if part not in {"", "."})
        if not cleaned_parts:
            return None

        mode = member.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise UnsafeArchiveError("Repository archive contains a non-regular member")
        return PurePosixPath(*cleaned_parts)

    def _copy_member(self, zip_file: ZipFile, member: ZipInfo, target: Path) -> None:
        written = 0
        with zip_file.open(member, "r") as source, target.open("xb") as destination:
            while chunk := source.read(64 * 1024):
                written += len(chunk)
                if written > self._max_file_bytes or written > member.file_size:
                    raise ArchiveLimitError("Archive member exceeds its declared size")
                destination.write(chunk)
        if written != member.file_size:
            raise UnsafeArchiveError("Archive member size does not match its declaration")


def discover_python_files(repository_root: Path) -> list[Path]:
    """Return deterministic repository-relative paths for supported Python files."""
    discovered: list[Path] = []
    for candidate in repository_root.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() != ".py":
            continue
        relative_path = candidate.relative_to(repository_root)
        if any(part.lower() in IGNORED_DIRECTORIES for part in relative_path.parts[:-1]):
            continue
        discovered.append(relative_path)
    return sorted(discovered, key=lambda path: path.as_posix())
