from pathlib import Path

from app.domain.analysis import SnapshotAnalysis
from app.modules.analysis.python_ast import PythonAstAnalyzer


def analyze_sources(
    tmp_path: Path,
    sources: dict[str, str | bytes],
    snapshot_id: str = "snapshot-1",
) -> SnapshotAnalysis:
    files: list[Path] = []
    for file_path, source in sources.items():
        relative_path = Path(file_path)
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, bytes):
            target.write_bytes(source)
        else:
            target.write_text(source, encoding="utf-8")
        files.append(relative_path)
    return PythonAstAnalyzer().analyze(snapshot_id, tmp_path, files)


def symbols_by_name(analysis: SnapshotAnalysis) -> dict[str, object]:
    return {
        symbol.qualified_name: symbol for symbol in analysis.symbols if symbol.symbol_type != "file"
    }


def test_extracts_simple_function_with_decorator_and_multiline_span(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "app.py": """@registered
def greet(
    name: str,
) -> str:
    return f\"Hello {name}\"
"""
        },
    )

    file_symbol, function = analysis.symbols
    assert file_symbol.symbol_type == "file"
    assert file_symbol.file_path == "app.py"
    assert file_symbol.start_line == 1
    assert file_symbol.end_line == 5
    assert file_symbol.line_count == 5
    assert file_symbol.content_hash is not None
    assert function.symbol_name == "greet"
    assert function.qualified_name == "app.greet"
    assert function.symbol_type == "function"
    assert function.start_line == 1
    assert function.end_line == 5


def test_extracts_classes_methods_async_functions_and_inheritance(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "services.py": """class Base:
    pass

class Service(Base):
    async def fetch(self):
        return self.helper()

    def helper(self):
        return 1

async def run():
    return await Service.fetch()
"""
        },
    )
    symbols = symbols_by_name(analysis)

    base = symbols["services.Base"]
    service = symbols["services.Service"]
    fetch = symbols["services.Service.fetch"]
    helper = symbols["services.Service.helper"]
    run = symbols["services.run"]

    assert base.symbol_type == "class"
    assert service.symbol_type == "class"
    assert fetch.symbol_type == "method"
    assert fetch.is_async is True
    assert fetch.parent_symbol_id == service.id
    assert helper.symbol_type == "method"
    assert run.symbol_type == "function"
    assert run.is_async is True

    inheritance = analysis.inheritances[0]
    assert inheritance.class_symbol_id == service.id
    assert inheritance.base_text == "Base"
    assert inheritance.resolution == "resolved"
    assert inheritance.resolved_symbol_id == base.id


def test_extracts_nested_functions_and_classes_with_qualified_names(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "nested.py": """def outer():
    def inner():
        return 1

    class Local:
        def method(self):
            return inner()

    return inner()
"""
        },
    )
    symbols = symbols_by_name(analysis)

    outer = symbols["nested.outer"]
    inner = symbols["nested.outer.inner"]
    local = symbols["nested.outer.Local"]
    method = symbols["nested.outer.Local.method"]

    assert inner.symbol_type == "function"
    assert inner.parent_symbol_id == outer.id
    assert local.symbol_type == "class"
    assert local.parent_symbol_id == outer.id
    assert method.symbol_type == "method"
    assert method.parent_symbol_id == local.id

    inner_calls = [call for call in analysis.calls if call.callee_text == "inner"]
    assert len(inner_calls) == 2
    assert all(call.resolved_symbol_id == inner.id for call in inner_calls)


def test_extracts_all_supported_import_forms_and_aliases(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "imports.py": """import os
import package.module as module_alias
from collections import defaultdict
from package.tools import helper as renamed
"""
        },
    )

    assert [
        (item.module, item.imported_name, item.alias, item.local_name) for item in analysis.imports
    ] == [
        ("os", None, None, "os"),
        ("package.module", None, "module_alias", "module_alias"),
        ("collections", "defaultdict", None, "defaultdict"),
        ("package.tools", "helper", "renamed", "renamed"),
    ]


def test_resolves_only_imports_with_known_snapshot_modules(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/helpers.py": "def helper():\n    pass\n",
            "pkg/main.py": "from . import helpers\nimport missing\n",
        },
    )
    files = {
        symbol.file_path: symbol for symbol in analysis.symbols if symbol.symbol_type == "file"
    }
    imports = {record.module: record for record in analysis.imports}

    assert imports["."].resolution == "resolved"
    assert imports["."].resolved_file_id == files["pkg/helpers.py"].id
    assert imports["missing"].resolution == "unresolved"
    assert imports["missing"].resolved_file_id is None


def test_resolves_only_conservative_same_file_calls(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "calls.py": """def helper():
    return 1

class Worker:
    def execute(self):
        helper()
        self.cleanup()
        external.call()

    def cleanup(self):
        pass

def run():
    helper()
    Worker.cleanup()
    missing()
"""
        },
    )
    symbols = symbols_by_name(analysis)
    calls = {(call.caller_symbol_id, call.callee_text): call for call in analysis.calls}

    execute = symbols["calls.Worker.execute"]
    cleanup = symbols["calls.Worker.cleanup"]
    run = symbols["calls.run"]
    helper = symbols["calls.helper"]

    assert calls[(execute.id, "helper")].resolved_symbol_id == helper.id
    assert calls[(execute.id, "self.cleanup")].resolved_symbol_id == cleanup.id
    assert calls[(run.id, "helper")].resolved_symbol_id == helper.id
    assert calls[(run.id, "Worker.cleanup")].resolved_symbol_id == cleanup.id
    assert calls[(execute.id, "external.call")].resolution == "unresolved"
    assert calls[(execute.id, "external.call")].resolved_symbol_id is None
    assert calls[(run.id, "missing")].resolution == "unresolved"


def test_does_not_resolve_shadowed_or_static_method_receivers(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "shadowing.py": """def helper():
    return 1

def parameter_shadow(helper):
    return helper()

class Worker:
    def cleanup(self):
        pass

    @staticmethod
    def static(self):
        self.cleanup()

Worker = object()
Worker.cleanup()
"""
        },
    )

    calls = {(call.callee_text, call.start_line): call for call in analysis.calls}
    assert calls[("helper", 5)].resolution == "unresolved"
    assert calls[("self.cleanup", 13)].resolution == "unresolved"
    assert calls[("Worker.cleanup", 16)].resolution == "unresolved"


def test_syntax_and_encoding_errors_are_isolated_between_files(tmp_path: Path) -> None:
    analysis = analyze_sources(
        tmp_path,
        {
            "good.py": "def valid():\n    return 1\n",
            "syntax_error.py": "def broken(:\n    pass\n",
            "encoding_error.py": b"# coding: ascii\nvalue = '\xff'\n",
        },
    )

    assert any(symbol.qualified_name == "good.valid" for symbol in analysis.symbols)
    assert {diagnostic.file_path for diagnostic in analysis.diagnostics} == {
        "encoding_error.py",
        "syntax_error.py",
    }
    assert {diagnostic.code for diagnostic in analysis.diagnostics} == {
        "python_syntax_error",
        "source_decode_error",
    }
    assert len([symbol for symbol in analysis.symbols if symbol.symbol_type == "file"]) == 3


def test_source_read_failure_does_not_abort_other_files(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("def valid():\n    pass\n", encoding="utf-8")

    analysis = PythonAstAnalyzer().analyze(
        "snapshot-1",
        tmp_path,
        [Path("missing.py"), Path("good.py")],
    )

    assert any(symbol.qualified_name == "good.valid" for symbol in analysis.symbols)
    diagnostic = next(item for item in analysis.diagnostics if item.file_path == "missing.py")
    assert diagnostic.code == "source_read_error"
    assert diagnostic.message == "Source file could not be read"


def test_empty_and_multiple_files_produce_deterministic_records(tmp_path: Path) -> None:
    sources = {
        "empty.py": "",
        "pkg/alpha.py": "def alpha():\n    return beta()\n",
        "pkg/beta.py": "def beta():\n    return 2\n",
    }

    first = analyze_sources(tmp_path, sources)
    second = analyze_sources(tmp_path, sources)

    assert first.model_dump() == second.model_dump()
    assert len({record.id for record in first.symbols}) == len(first.symbols)
    empty_file = next(symbol for symbol in first.symbols if symbol.file_path == "empty.py")
    assert empty_file.start_line == 1
    assert empty_file.end_line == 1
    assert {symbol.file_path for symbol in first.symbols} == {
        "empty.py",
        "pkg/alpha.py",
        "pkg/beta.py",
    }
    beta_call = next(call for call in first.calls if call.callee_text == "beta")
    assert beta_call.resolution == "unresolved"
