import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.errors import InvalidGithubUrlError

OWNER_PATTERN = re.compile(r"^(?!-)[A-Za-z0-9-]{1,39}(?<!-)$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


@dataclass(frozen=True, slots=True)
class GithubRepositoryLocation:
    owner: str
    name: str

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


def parse_github_repository_url(raw_url: str) -> GithubRepositoryLocation:
    """Parse a canonical public github.com HTTPS repository URL."""
    try:
        parsed = urlsplit(raw_url)
    except ValueError as error:
        raise InvalidGithubUrlError("Invalid GitHub repository URL") from error

    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidGithubUrlError("Only public HTTPS github.com repository URLs are supported")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise InvalidGithubUrlError("GitHub URL must contain exactly an owner and repository")

    owner, name = path_parts
    if name.endswith(".git"):
        name = name[:-4]
    if not OWNER_PATTERN.fullmatch(owner) or not REPOSITORY_PATTERN.fullmatch(name):
        raise InvalidGithubUrlError("GitHub owner or repository name is invalid")
    return GithubRepositoryLocation(owner=owner, name=name)
