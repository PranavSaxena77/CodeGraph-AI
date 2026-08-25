from typing import Literal

from pydantic import BaseModel, Field

GraphNodeType = Literal["Repository", "Snapshot", "File", "Class", "Function", "Method"]
GraphRelationshipType = Literal[
    "HAS_SNAPSHOT",
    "CONTAINS",
    "DECLARES",
    "IMPORTS",
    "INHERITS",
    "CALLS",
]


class GraphPersistenceStatus(BaseModel):
    repository_id: str
    snapshot_id: str
    status: Literal["persisted"] = "persisted"
    node_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    idempotent: bool = False
    diagnostic_count: int = Field(default=0, ge=0)


class GraphNode(BaseModel):
    id: str
    node_type: GraphNodeType
    repository_id: str
    snapshot_id: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    symbol_name: str | None = None
    qualified_name: str | None = None
    symbol_type: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class GraphRelationship(BaseModel):
    id: str
    relationship_type: GraphRelationshipType
    source_id: str
    target_id: str
    repository_id: str
    snapshot_id: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class GraphNeighborhood(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)
