from typing import Literal

from pydantic import BaseModel, Field

SymbolType = Literal["file", "class", "function", "method"]
DiagnosticSeverity = Literal["warning", "error"]
ReferenceResolution = Literal["resolved", "unresolved"]


class StructuralSymbol(BaseModel):
    id: str
    snapshot_id: str
    file_path: str
    symbol_name: str
    qualified_name: str
    symbol_type: SymbolType
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    parent_symbol_id: str | None = None
    is_async: bool = False
    content_hash: str | None = None
    line_count: int | None = Field(default=None, ge=1)


class ImportRecord(BaseModel):
    id: str
    snapshot_id: str
    file_path: str
    module: str
    imported_name: str | None = None
    alias: str | None = None
    local_name: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    resolved_file_id: str | None = None
    resolution: ReferenceResolution = "unresolved"


class InheritanceRecord(BaseModel):
    id: str
    snapshot_id: str
    file_path: str
    class_symbol_id: str
    base_text: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    resolved_symbol_id: str | None = None
    resolution: ReferenceResolution


class CallRecord(BaseModel):
    id: str
    snapshot_id: str
    file_path: str
    caller_symbol_id: str | None = None
    callee_text: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    resolved_symbol_id: str | None = None
    resolution: ReferenceResolution


class AnalysisDiagnostic(BaseModel):
    id: str
    snapshot_id: str
    file_path: str
    stage: Literal["decode", "parse"]
    code: str
    message: str
    severity: DiagnosticSeverity = "warning"
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class SnapshotAnalysis(BaseModel):
    snapshot_id: str
    symbols: list[StructuralSymbol] = Field(default_factory=list)
    imports: list[ImportRecord] = Field(default_factory=list)
    inheritances: list[InheritanceRecord] = Field(default_factory=list)
    calls: list[CallRecord] = Field(default_factory=list)
    diagnostics: list[AnalysisDiagnostic] = Field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.diagnostics)
