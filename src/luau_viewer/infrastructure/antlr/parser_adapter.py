"""ANTLR-backed Luau parser adapter."""

from __future__ import annotations

from time import perf_counter

from luau_viewer.domain.model import (
    GrammarVersion,
    ParseOutcome,
    ParseStatistics,
    SourceUnit,
    StructuralElement,
    StructuralElementKind,
)
from luau_viewer.domain.ports import SyntaxParser
from luau_viewer.infrastructure.antlr.runtime import (
    ANTLR_GRAMMAR_VERSION,
    load_generated_types,
    parse_source_text,
)


class AntlrLuauSyntaxParser(SyntaxParser):
    def __init__(self) -> None:
        self._generated = load_generated_types()

    @property
    def grammar_version(self) -> GrammarVersion:
        return ANTLR_GRAMMAR_VERSION

    def parse(self, source_unit: SourceUnit) -> ParseOutcome:
        started_at = perf_counter()
        try:
            parse_result = parse_source_text(source_unit.content, self._generated)
            structure_visitor = _build_structure_visitor(self._generated.visitor_type)()
            structure_visitor.visit(parse_result.tree)

            elements = tuple(structure_visitor.elements)
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)

            return ParseOutcome.success(
                source_unit=source_unit,
                grammar_version=self.grammar_version,
                diagnostics=parse_result.diagnostics,
                structural_elements=elements,
                statistics=ParseStatistics(
                    token_count=len(parse_result.token_stream.tokens),
                    structural_element_count=len(elements),
                    diagnostic_count=len(parse_result.diagnostics),
                    elapsed_ms=elapsed_ms,
                ),
            )
        except Exception as error:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            return ParseOutcome.technical_failure(
                source_unit=source_unit,
                grammar_version=self.grammar_version,
                message=str(error),
                elapsed_ms=elapsed_ms,
            )


def _build_structure_visitor(visitor_base: type) -> type:
    class LuauStructureVisitor(visitor_base):
        def __init__(self) -> None:
            super().__init__()
            self.elements: list[StructuralElement] = []
            self._containers: list[str] = []

        def visitFunctionStat(self, ctx):
            name = ctx.funcname().getText()
            signature = ctx.funcbody().getText()
            self._append(
                StructuralElementKind.FUNCTION,
                name,
                ctx,
                signature=f"function {name}{signature}",
            )
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitLocalFunctionStat(self, ctx):
            name = ctx.NAME().getText()
            signature = ctx.funcbody().getText()
            self._append(
                StructuralElementKind.LOCAL_FUNCTION,
                name,
                ctx,
                signature=f"local function {name}{signature}",
            )
            return None

        def visitLocalStat(self, ctx):
            binding_list = ctx.bindingList()
            if binding_list is not None:
                for binding in binding_list.binding():
                    name = binding.NAME().getText()
                    kind = StructuralElementKind.VARIABLE
                    if ctx.ASSIGN() is not None:
                        explist = ctx.explist()
                        if explist is not None:
                            kind = StructuralElementKind.CONSTANT
                    self._append(kind, name, ctx, signature=f"local {name}")
            return None

        def visitTypeAliasStat(self, ctx):
            name = ctx.NAME().getText()
            self._append(
                StructuralElementKind.TYPE_ALIAS,
                name,
                ctx,
                signature=f"type {name}",
            )
            return None

        def visitExportTypeAliasStat(self, ctx):
            name = ctx.NAME().getText()
            self._append(
                StructuralElementKind.TYPE_ALIAS,
                name,
                ctx,
                signature=f"export type {name}",
            )
            return None

        def _append(self, kind, name: str, ctx, signature: str | None = None) -> None:
            container = ".".join(self._containers) if self._containers else None
            self.elements.append(
                StructuralElement(
                    kind=kind,
                    name=name,
                    line=ctx.start.line,
                    column=ctx.start.column,
                    container=container,
                    signature=signature,
                )
            )

        def _with_container(self, name: str, callback):
            self._containers.append(name)
            try:
                return callback()
            finally:
                self._containers.pop()

    return LuauStructureVisitor
