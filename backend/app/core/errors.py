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


class MetadataStoreError(ApplicationError):
    pass
