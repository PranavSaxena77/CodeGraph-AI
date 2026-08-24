import ast
import hashlib
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal, cast

from app.domain.analysis import (
    AnalysisDiagnostic,
    CallRecord,
    ImportRecord,
    InheritanceRecord,
    SnapshotAnalysis,
    StructuralSymbol,
    SymbolType,
)

AnalysisRecord = StructuralSymbol | ImportRecord | InheritanceRecord | CallRecord


def _stable_id(snapshot_id: str, record_type: str, *identity: object) -> str:
    canonical = "\x1f".join(str(part) for part in (snapshot_id, record_type, *identity))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _module_name(file_path: str) -> str:
    path = Path(file_path)
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or path.stem


def _start_line(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    decorator_lines = [decorator.lineno for decorator in node.decorator_list]
    return min([node.lineno, *decorator_lines])


def _end_line(node: ast.AST) -> int:
    end_line = getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)
    return cast(int, end_line)


def _expression_text(node: ast.AST) -> str:
    return ast.unparse(node)


@dataclass(frozen=True, slots=True)
class _Scope:
    key: tuple[str, ...]
    kind: str
    qualified_name: str
    symbol_id: str | None


@dataclass(frozen=True, slots=True)
class _SymbolInfo:
    record: StructuralSymbol
    parent_scope_key: tuple[str, ...]
    body_scope_key: tuple[str, ...]


class _DefinitionCollector(ast.NodeVisitor):
    def __init__(self, snapshot_id: str, file_path: str, module_name: str) -> None:
        self._snapshot_id = snapshot_id
        self._file_path = file_path
        self._scopes = [_Scope(("module",), "module", module_name, None)]
        self.symbols: list[StructuralSymbol] = []
        self.node_symbols: dict[int, _SymbolInfo] = {}
        self.declarations: dict[tuple[str, ...], dict[str, list[StructuralSymbol]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.scope_kinds: dict[tuple[str, ...], str] = {self._scopes[0].key: "module"}
        self.class_body_scopes: dict[str, tuple[str, ...]] = {}
        self.symbol_body_scopes: dict[str, tuple[str, ...]] = {}
        self.method_receivers: dict[str, tuple[str, set[str]]] = {}
        self.blocked_names: dict[tuple[str, ...], set[str]] = defaultdict(set)
        self.reassigned_names: dict[tuple[str, ...], set[str]] = defaultdict(set)

    @property
    def current_scope(self) -> _Scope:
        return self._scopes[-1]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        info = self._add_symbol(node, "class", is_async=False)
        self.class_body_scopes[info.record.id] = info.body_scope_key
        self._visit_body(node.body, info, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        symbol_type: SymbolType = "method" if self.current_scope.kind == "class" else "function"
        info = self._add_symbol(node, symbol_type, is_async=is_async)
        self.blocked_names[info.body_scope_key].update(self._argument_names(node))
        if symbol_type == "method" and self.current_scope.symbol_id is not None:
            receiver_names = set() if self._is_static_method(node) else self._receiver_names(node)
            self.method_receivers[info.record.id] = (
                self.current_scope.symbol_id,
                receiver_names,
            )
        self._visit_body(node.body, info, symbol_type)

    def _add_symbol(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        symbol_type: SymbolType,
        *,
        is_async: bool,
    ) -> _SymbolInfo:
        parent_scope = self.current_scope
        qualified_name = f"{parent_scope.qualified_name}.{node.name}"
        symbol_id = _stable_id(
            self._snapshot_id,
            "symbol",
            self._file_path,
            symbol_type,
            qualified_name,
            node.lineno,
            node.col_offset,
        )
        record = StructuralSymbol(
            id=symbol_id,
            snapshot_id=self._snapshot_id,
            file_path=self._file_path,
            symbol_name=node.name,
            qualified_name=qualified_name,
            symbol_type=symbol_type,
            start_line=_start_line(node),
            end_line=_end_line(node),
            parent_symbol_id=parent_scope.symbol_id,
            is_async=is_async,
        )
        body_scope_key = (*parent_scope.key, symbol_id)
        info = _SymbolInfo(record, parent_scope.key, body_scope_key)
        self.symbols.append(record)
        self.node_symbols[id(node)] = info
        self.declarations[parent_scope.key][node.name].append(record)
        self.symbol_body_scopes[record.id] = body_scope_key
        return info

    def _visit_body(self, body: list[ast.stmt], info: _SymbolInfo, scope_kind: str) -> None:
        scope = _Scope(
            info.body_scope_key,
            scope_kind,
            info.record.qualified_name,
            info.record.id,
        )
        self.scope_kinds[scope.key] = scope_kind
        self._scopes.append(scope)
        for statement in body:
            self.visit(statement)
        self._scopes.pop()

    @staticmethod
    def _receiver_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        positional = [*node.args.posonlyargs, *node.args.args]
        return {positional[0].arg} if positional else set()

    @staticmethod
    def _argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        names = {argument.arg for argument in arguments}
        if node.args.vararg is not None:
            names.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            names.add(node.args.kwarg.arg)
        return names

    @staticmethod
    def _is_static_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        return any(
            (isinstance(decorator, ast.Name) and decorator.id == "staticmethod")
            or (isinstance(decorator, ast.Attribute) and decorator.attr == "staticmethod")
            for decorator in node.decorator_list
        )

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.blocked_names[self.current_scope.key].add(node.id)
            self.reassigned_names[self.current_scope.key].add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
            self.blocked_names[self.current_scope.key].add(local_name)
            self.reassigned_names[self.current_scope.key].add(local_name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name
            self.blocked_names[self.current_scope.key].add(local_name)
            self.reassigned_names[self.current_scope.key].add(local_name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        self.blocked_names[self.current_scope.key].update(argument.arg for argument in arguments)
        self.visit(node.body)


class _ReferenceCollector(ast.NodeVisitor):
    def __init__(
        self,
        snapshot_id: str,
        file_path: str,
        definitions: _DefinitionCollector,
    ) -> None:
        self._snapshot_id = snapshot_id
        self._file_path = file_path
        self._definitions = definitions
        self._scope_keys: list[tuple[str, ...]] = [("module",)]
        self._symbol_stack: list[StructuralSymbol] = []
        self.imports: list[ImportRecord] = []
        self.inheritances: list[InheritanceRecord] = []
        self.calls: list[CallRecord] = []

    def visit_Import(self, node: ast.Import) -> None:
        for index, alias in enumerate(node.names):
            local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
            self.imports.append(
                ImportRecord(
                    id=_stable_id(
                        self._snapshot_id,
                        "import",
                        self._file_path,
                        node.lineno,
                        node.col_offset,
                        index,
                        alias.name,
                        alias.asname,
                    ),
                    snapshot_id=self._snapshot_id,
                    file_path=self._file_path,
                    module=alias.name,
                    alias=alias.asname,
                    local_name=local_name,
                    start_line=node.lineno,
                    end_line=_end_line(node),
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = f"{'.' * node.level}{node.module or ''}"
        for index, alias in enumerate(node.names):
            self.imports.append(
                ImportRecord(
                    id=_stable_id(
                        self._snapshot_id,
                        "import",
                        self._file_path,
                        node.lineno,
                        node.col_offset,
                        index,
                        module,
                        alias.name,
                        alias.asname,
                    ),
                    snapshot_id=self._snapshot_id,
                    file_path=self._file_path,
                    module=module,
                    imported_name=alias.name,
                    alias=alias.asname,
                    local_name=alias.asname or alias.name,
                    start_line=node.lineno,
                    end_line=_end_line(node),
                )
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        info = self._definitions.node_symbols[id(node)]
        for base in node.bases:
            resolved = self._resolve_class(base, info.parent_scope_key)
            self.inheritances.append(
                InheritanceRecord(
                    id=_stable_id(
                        self._snapshot_id,
                        "inheritance",
                        self._file_path,
                        info.record.id,
                        base.lineno,
                        base.col_offset,
                        _expression_text(base),
                    ),
                    snapshot_id=self._snapshot_id,
                    file_path=self._file_path,
                    class_symbol_id=info.record.id,
                    base_text=_expression_text(base),
                    start_line=base.lineno,
                    end_line=_end_line(base),
                    resolved_symbol_id=resolved.id if resolved else None,
                    resolution="resolved" if resolved else "unresolved",
                )
            )
            self.visit(base)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._enter_definition(node, info)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved = self._resolve_call(node.func)
        caller = self._nearest_caller()
        callee_text = _expression_text(node.func)
        self.calls.append(
            CallRecord(
                id=_stable_id(
                    self._snapshot_id,
                    "call",
                    self._file_path,
                    node.lineno,
                    node.col_offset,
                    getattr(node, "end_lineno", node.lineno),
                    getattr(node, "end_col_offset", node.col_offset),
                    callee_text,
                ),
                snapshot_id=self._snapshot_id,
                file_path=self._file_path,
                caller_symbol_id=caller.id if caller else None,
                callee_text=callee_text,
                start_line=node.lineno,
                end_line=_end_line(node),
                resolved_symbol_id=resolved.id if resolved else None,
                resolution="resolved" if resolved else "unresolved",
            )
        )
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        info = self._definitions.node_symbols[id(node)]
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]:
            if argument.annotation is not None:
                self.visit(argument.annotation)
        if node.args.vararg is not None and node.args.vararg.annotation is not None:
            self.visit(node.args.vararg.annotation)
        if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
            self.visit(node.args.kwarg.annotation)
        if node.returns is not None:
            self.visit(node.returns)
        self._enter_definition(node, info)

    def _enter_definition(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        info: _SymbolInfo,
    ) -> None:
        self._scope_keys.append(info.body_scope_key)
        self._symbol_stack.append(info.record)
        for statement in node.body:
            self.visit(statement)
        self._symbol_stack.pop()
        self._scope_keys.pop()

    def _nearest_caller(self) -> StructuralSymbol | None:
        for symbol in reversed(self._symbol_stack):
            if symbol.symbol_type in {"function", "method"}:
                return symbol
        return None

    def _resolve_call(self, target: ast.expr) -> StructuralSymbol | None:
        if isinstance(target, ast.Name):
            return self._resolve_name(target.id, {"function", "method"})
        if not isinstance(target, ast.Attribute):
            return None

        if isinstance(target.value, ast.Name):
            receiver = target.value.id
            method = self._resolve_receiver_method(receiver, target.attr)
            if method is not None:
                return method
            class_symbol = self._resolve_name(receiver, {"class"})
            if class_symbol is not None:
                return self._class_member(class_symbol.id, target.attr, {"method"})
        return None

    def _resolve_receiver_method(self, receiver: str, name: str) -> StructuralSymbol | None:
        for symbol in reversed(self._symbol_stack):
            method_context = self._definitions.method_receivers.get(symbol.id)
            if method_context is None:
                continue
            class_id, receiver_names = method_context
            body_scope = self._definitions.symbol_body_scopes[symbol.id]
            body_scope_index = self._scope_keys.index(body_scope)
            nested_scopes = self._scope_keys[body_scope_index + 1 :]
            if (
                receiver in receiver_names
                and receiver not in self._definitions.reassigned_names[body_scope]
                and all(
                    receiver not in self._definitions.blocked_names[scope]
                    for scope in nested_scopes
                )
            ):
                return self._class_member(class_id, name, {"method"})
        return None

    def _resolve_class(
        self, target: ast.expr, parent_scope_key: tuple[str, ...]
    ) -> StructuralSymbol | None:
        if isinstance(target, ast.Name):
            return self._resolve_name_from_scopes(target.id, {"class"}, parent_scope_key)
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            outer = self._resolve_name_from_scopes(target.value.id, {"class"}, parent_scope_key)
            if outer is not None:
                return self._class_member(outer.id, target.attr, {"class"})
        return None

    def _resolve_name(self, name: str, kinds: set[str]) -> StructuralSymbol | None:
        for scope_key in reversed(self._scope_keys):
            if self._definitions.scope_kinds[scope_key] == "class":
                continue
            if name in self._definitions.blocked_names[scope_key]:
                return None
            candidate = self._unique_declaration(scope_key, name, kinds)
            if candidate is not None:
                return candidate
        return None

    def _resolve_name_from_scopes(
        self,
        name: str,
        kinds: set[str],
        starting_scope: tuple[str, ...],
    ) -> StructuralSymbol | None:
        scope_chain = [scope for scope in self._scope_keys if len(scope) <= len(starting_scope)]
        for scope_key in reversed(scope_chain):
            if self._definitions.scope_kinds[scope_key] == "class":
                continue
            if name in self._definitions.blocked_names[scope_key]:
                return None
            candidate = self._unique_declaration(scope_key, name, kinds)
            if candidate is not None:
                return candidate
        return None

    def _class_member(self, class_id: str, name: str, kinds: set[str]) -> StructuralSymbol | None:
        scope_key = self._definitions.class_body_scopes[class_id]
        if name in self._definitions.blocked_names[scope_key]:
            return None
        return self._unique_declaration(scope_key, name, kinds)

    def _unique_declaration(
        self, scope_key: tuple[str, ...], name: str, kinds: set[str]
    ) -> StructuralSymbol | None:
        candidates = [
            symbol
            for symbol in self._definitions.declarations[scope_key].get(name, [])
            if symbol.symbol_type in kinds
        ]
        return candidates[0] if len(candidates) == 1 else None


class PythonAstAnalyzer:
    """Parse Python source into deterministic, graph-ready structural records."""

    def analyze(
        self, snapshot_id: str, repository_root: Path, files: list[Path]
    ) -> SnapshotAnalysis:
        symbols: list[StructuralSymbol] = []
        imports: list[ImportRecord] = []
        inheritances: list[InheritanceRecord] = []
        calls: list[CallRecord] = []
        diagnostics: list[AnalysisDiagnostic] = []

        for relative_path in sorted(files, key=lambda path: path.as_posix()):
            result = self._analyze_file(snapshot_id, repository_root, relative_path)
            symbols.extend(result.symbols)
            imports.extend(result.imports)
            inheritances.extend(result.inheritances)
            calls.extend(result.calls)
            diagnostics.extend(result.diagnostics)

        return SnapshotAnalysis(
            snapshot_id=snapshot_id,
            symbols=sorted(symbols, key=self._record_sort_key),
            imports=sorted(
                self._resolve_imports(symbols, imports),
                key=self._record_sort_key,
            ),
            inheritances=sorted(inheritances, key=self._record_sort_key),
            calls=sorted(calls, key=self._record_sort_key),
            diagnostics=sorted(diagnostics, key=self._diagnostic_sort_key),
        )

    @staticmethod
    def _resolve_imports(
        symbols: list[StructuralSymbol], imports: list[ImportRecord]
    ) -> list[ImportRecord]:
        module_files = {
            symbol.qualified_name: symbol.id for symbol in symbols if symbol.symbol_type == "file"
        }
        resolved: list[ImportRecord] = []
        for record in imports:
            module_name = PythonAstAnalyzer._absolute_import_module(record, module_files)
            resolved_file_id = module_files.get(module_name) if module_name else None
            resolved.append(
                record.model_copy(
                    update={
                        "resolved_file_id": resolved_file_id,
                        "resolution": "resolved" if resolved_file_id else "unresolved",
                    }
                )
            )
        return resolved

    @staticmethod
    def _absolute_import_module(record: ImportRecord, module_files: dict[str, str]) -> str | None:
        if not record.module.startswith("."):
            return record.module

        level = len(record.module) - len(record.module.lstrip("."))
        relative_module = record.module[level:]
        current_module = _module_name(record.file_path)
        package_parts = current_module.split(".")
        if Path(record.file_path).name != "__init__.py":
            package_parts.pop()
        parents_to_remove = level - 1
        if parents_to_remove > len(package_parts):
            return None
        if parents_to_remove:
            package_parts = package_parts[:-parents_to_remove]

        base_parts = [*package_parts]
        if relative_module:
            base_parts.extend(relative_module.split("."))
        base_module = ".".join(base_parts)
        if relative_module or record.imported_name is None:
            return base_module

        imported_module = ".".join([*base_parts, record.imported_name])
        if imported_module in module_files:
            return imported_module
        return base_module

    def _analyze_file(
        self, snapshot_id: str, repository_root: Path, relative_path: Path
    ) -> SnapshotAnalysis:
        file_path = relative_path.as_posix()
        try:
            raw_source = (repository_root / relative_path).read_bytes()
        except OSError as error:
            content_hash = hashlib.sha256(b"").hexdigest()
            file_symbol = self._file_symbol(snapshot_id, file_path, content_hash, b"")
            diagnostic = self._diagnostic(snapshot_id, file_path, "decode", error)
            return SnapshotAnalysis(
                snapshot_id=snapshot_id,
                symbols=[file_symbol],
                diagnostics=[diagnostic],
            )
        content_hash = hashlib.sha256(raw_source).hexdigest()
        try:
            encoding, _ = tokenize.detect_encoding(BytesIO(raw_source).readline)
            source = raw_source.decode(encoding)
        except (SyntaxError, UnicodeDecodeError) as error:
            file_symbol = self._file_symbol(snapshot_id, file_path, content_hash, raw_source)
            diagnostic = self._diagnostic(snapshot_id, file_path, "decode", error)
            return SnapshotAnalysis(
                snapshot_id=snapshot_id,
                symbols=[file_symbol],
                diagnostics=[diagnostic],
            )

        file_symbol = self._file_symbol(snapshot_id, file_path, content_hash, source)
        try:
            tree = ast.parse(source, filename=file_path, type_comments=True)
        except SyntaxError as error:
            diagnostic = self._diagnostic(snapshot_id, file_path, "parse", error)
            return SnapshotAnalysis(
                snapshot_id=snapshot_id,
                symbols=[file_symbol],
                diagnostics=[diagnostic],
            )

        module_name = _module_name(file_path)
        definitions = _DefinitionCollector(snapshot_id, file_path, module_name)
        definitions.visit(tree)
        references = _ReferenceCollector(snapshot_id, file_path, definitions)
        references.visit(tree)
        return SnapshotAnalysis(
            snapshot_id=snapshot_id,
            symbols=[file_symbol, *definitions.symbols],
            imports=references.imports,
            inheritances=references.inheritances,
            calls=references.calls,
        )

    @staticmethod
    def _file_symbol(
        snapshot_id: str,
        file_path: str,
        content_hash: str,
        source: str | bytes,
    ) -> StructuralSymbol:
        line_count = max(1, len(source.splitlines()))
        return StructuralSymbol(
            id=_stable_id(snapshot_id, "file", file_path, content_hash),
            snapshot_id=snapshot_id,
            file_path=file_path,
            symbol_name=Path(file_path).name,
            qualified_name=_module_name(file_path),
            symbol_type="file",
            start_line=1,
            end_line=line_count,
            content_hash=content_hash,
            line_count=line_count,
        )

    @staticmethod
    def _diagnostic(
        snapshot_id: str,
        file_path: str,
        stage: Literal["decode", "parse"],
        error: SyntaxError | UnicodeDecodeError | OSError,
    ) -> AnalysisDiagnostic:
        line = error.lineno if isinstance(error, SyntaxError) else None
        if isinstance(error, SyntaxError):
            message = error.msg
            code = "python_syntax_error" if stage == "parse" else "source_decode_error"
        elif isinstance(error, UnicodeDecodeError):
            message = "Source encoding is invalid"
            code = "source_decode_error"
        else:
            message = "Source file could not be read"
            code = "source_read_error"
        return AnalysisDiagnostic(
            id=_stable_id(snapshot_id, "diagnostic", file_path, stage, line, message),
            snapshot_id=snapshot_id,
            file_path=file_path,
            stage=stage,
            code=code,
            message=message,
            start_line=line,
            end_line=line,
        )

    @staticmethod
    def _record_sort_key(record: AnalysisRecord) -> tuple[object, ...]:
        file_rank = (
            0 if isinstance(record, StructuralSymbol) and record.symbol_type == "file" else 1
        )
        return (
            record.file_path,
            file_rank,
            record.start_line,
            record.end_line,
            record.id,
        )

    @staticmethod
    def _diagnostic_sort_key(record: AnalysisDiagnostic) -> tuple[object, ...]:
        return (record.file_path, record.start_line or 0, record.id)
