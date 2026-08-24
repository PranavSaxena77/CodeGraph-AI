import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings


class ReadinessChecker(Protocol):
    async def check(self) -> dict[str, bool]:
        """Return connectivity status keyed by dependency name."""
        ...


@dataclass(frozen=True, slots=True)
class DependencyTarget:
    name: str
    host: str
    port: int


class SocketReadinessChecker:
    """Check basic dependency reachability without vendor client libraries."""

    def __init__(self, targets: tuple[DependencyTarget, ...], timeout_seconds: float) -> None:
        self._targets = targets
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> "SocketReadinessChecker":
        return cls(
            targets=(
                DependencyTarget("mongodb", settings.mongodb_host, settings.mongodb_port),
                DependencyTarget("neo4j", settings.neo4j_host, settings.neo4j_bolt_port),
            ),
            timeout_seconds=settings.dependency_timeout_seconds,
        )

    async def check(self) -> dict[str, bool]:
        results = await asyncio.gather(
            *(self._is_reachable(target) for target in self._targets),
        )
        return {
            target.name: available for target, available in zip(self._targets, results, strict=True)
        }

    async def _is_reachable(self, target: DependencyTarget) -> bool:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target.host, target.port),
                timeout=self._timeout_seconds,
            )
        except (OSError, TimeoutError):
            return False

        writer.close()
        await writer.wait_closed()
        return True
