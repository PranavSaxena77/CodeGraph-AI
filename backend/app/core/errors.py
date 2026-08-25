class ApplicationError(Exception):
    """Base class for expected, safely reportable application failures."""


class InvalidGithubUrlError(ApplicationError):
    pass


class GithubRepositoryNotFoundError(ApplicationError):
    pass


class GithubServiceError(ApplicationError):
    pass


class UnsafeArchiveError(ApplicationError):
    pass


class ArchiveLimitError(ApplicationError):
    pass


class RepositoryNotFoundError(ApplicationError):
    pass


class SnapshotNotFoundError(ApplicationError):
    pass


class SnapshotNotReadyError(ApplicationError):
    pass


class MetadataStoreError(ApplicationError):
    pass


class GraphStoreError(ApplicationError):
    pass


class GraphSnapshotNotFoundError(ApplicationError):
    pass


class EmbeddingProviderError(ApplicationError):
    pass


class VectorStoreError(ApplicationError):
    pass


class VectorIndexNotFoundError(ApplicationError):
    pass


class VectorIndexCorruptError(ApplicationError):
    pass


class RetrievalIdentityMismatchError(ApplicationError):
    pass


class ReasoningProviderError(ApplicationError):
    pass


class MalformedReasoningOutputError(ApplicationError):
    pass


class CitationValidationError(ApplicationError):
    pass
