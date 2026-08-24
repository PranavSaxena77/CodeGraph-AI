import stat
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from app.core.errors import InvalidGithubUrlError, UnsafeArchiveError
from app.domain.repositories import RepositoryRegistrationRequest
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.analysis.service import SnapshotAnalysisService
from app.modules.ingestion.archive import SafeZipExtractor, discover_python_files
from app.modules.ingestion.service import RepositoryIngestionService
from app.modules.ingestion.url import parse_github_repository_url
from tests.fakes import FakeGithubClient, InMemoryMetadataStore


def build_zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


@pytest.mark.parametrize(
    ("url", "owner", "name"),
    [
        ("https://github.com/openai/openai-python", "openai", "openai-python"),
        ("https://github.com/pallets/flask/", "pallets", "flask"),
        ("https://github.com/psf/requests.git", "psf", "requests"),
    ],
)
def test_parse_valid_github_urls(url: str, owner: str, name: str) -> None:
    location = parse_github_repository_url(url)

    assert location.owner == owner
    assert location.name == name
    assert location.canonical_url == f"https://github.com/{owner}/{name}"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/openai/openai-python",
        "https://gitlab.com/openai/openai-python",
        "https://github.com.evil.example/openai/openai-python",
        "https://github.com/openai",
        "https://github.com/openai/openai-python/issues",
        "https://github.com/openai/openai-python?tab=readme",
        "git@github.com:openai/openai-python.git",
    ],
)
def test_reject_invalid_github_urls(url: str) -> None:
    with pytest.raises(InvalidGithubUrlError):
        parse_github_repository_url(url)


def test_safe_archive_extraction_and_python_discovery(tmp_path: Path) -> None:
    archive = build_zip(
        {
            "project-sha/app.py": "print('safe')",
            "project-sha/src/service.py": "def service(): pass",
            "project-sha/node_modules/ignored.py": "raise RuntimeError",
            "project-sha/.venv/ignored.py": "raise RuntimeError",
            "project-sha/build/ignored.py": "raise RuntimeError",
            "project-sha/__pycache__/ignored.py": "raise RuntimeError",
            "project-sha/README.md": "documentation",
        }
    )
    extractor = SafeZipExtractor(
        max_members=100,
        max_extracted_bytes=100_000,
        max_file_bytes=10_000,
    )

    repository_root = extractor.extract(archive, tmp_path)

    assert discover_python_files(repository_root) == [Path("app.py"), Path("src/service.py")]
    assert (repository_root / "app.py").read_text() == "print('safe')"


@pytest.mark.parametrize("member_name", ["../escape.py", "/absolute.py", "..\\escape.py"])
def test_safe_extraction_rejects_path_traversal(tmp_path: Path, member_name: str) -> None:
    archive = build_zip({member_name: "unsafe"})
    extractor = SafeZipExtractor(10, 10_000, 1_000)

    with pytest.raises(UnsafeArchiveError):
        extractor.extract(archive, tmp_path)


def test_safe_extraction_rejects_symlinks(tmp_path: Path) -> None:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        member = ZipInfo("project-sha/link.py")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "target.py")

    with pytest.raises(UnsafeArchiveError):
        SafeZipExtractor(10, 10_000, 1_000).extract(output.getvalue(), tmp_path)


def test_registration_resolves_requested_ref_and_is_idempotent() -> None:
    github = FakeGithubClient(build_zip({"project-sha/main.py": "value = 1"}))
    store = InMemoryMetadataStore()
    service = RepositoryIngestionService(
        github=github,
        store=store,
        extractor=SafeZipExtractor(10, 10_000, 1_000),
    )
    request = RepositoryRegistrationRequest(
        github_url="https://github.com/octocat/hello-python",
        ref="release/v0.1",
    )

    first = service.register(request)
    second = service.register(request)

    assert github.resolved_refs == ["release/v0.1", "release/v0.1"]
    assert github.download_count == 1
    assert first.idempotent is False
    assert second.idempotent is True
    assert first.repository.id == second.repository.id
    assert first.snapshot.id == second.snapshot.id
    assert first.snapshot.commit_sha == "a" * 40
    assert first.snapshot.status == "ready"
    assert first.snapshot.discovered_file_count == 1


def test_registration_uses_default_branch_when_ref_is_omitted() -> None:
    github = FakeGithubClient(build_zip({"project-sha/main.py": "value = 1"}))
    service = RepositoryIngestionService(
        github=github,
        store=InMemoryMetadataStore(),
        extractor=SafeZipExtractor(10, 10_000, 1_000),
    )

    result = service.register(
        RepositoryRegistrationRequest(github_url="https://github.com/octocat/hello-python")
    )

    assert github.resolved_refs == ["main"]
    assert result.snapshot.ref == "main"


def test_analysis_service_reuses_ingested_snapshot_identity() -> None:
    github = FakeGithubClient(build_zip({"project-sha/main.py": "def main():\n    pass\n"}))
    store = InMemoryMetadataStore()
    extractor = SafeZipExtractor(10, 10_000, 1_000)
    ingestion = RepositoryIngestionService(github=github, store=store, extractor=extractor)
    registration = ingestion.register(
        RepositoryRegistrationRequest(github_url="https://github.com/octocat/hello-python")
    )
    analysis_service = SnapshotAnalysisService(
        github=github,
        store=store,
        extractor=extractor,
        analyzer=PythonAstAnalyzer(),
    )

    analysis = analysis_service.analyze_snapshot(
        registration.repository.id,
        registration.snapshot.id,
    )

    assert analysis.snapshot_id == registration.snapshot.id
    assert [symbol.qualified_name for symbol in analysis.symbols] == ["main", "main.main"]
    assert github.download_count == 2
