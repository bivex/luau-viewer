"""Use cases for structured control flow diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from luau_viewer.domain.ports import ControlFlowExtractor, NassiDiagramRenderer, SourceRepository
from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    IfFlowStep,
    WhileFlowStep,
    ForInFlowStep,
    NumericForFlowStep,
    RepeatUntilFlowStep,
    ClosureFlowStep,
    ControlFlowStep,
)
from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    IfFlowStep,
    WhileFlowStep,
    ForInFlowStep,
    NumericForFlowStep,
    RepeatUntilFlowStep,
    ClosureFlowStep,
    ControlFlowStep,
)


@dataclass(frozen=True, slots=True)
class BuildNassiDiagramCommand:
    path: str


@dataclass(frozen=True, slots=True)
class BuildNassiDirectoryCommand:
    root_path: str


@dataclass(frozen=True, slots=True)
class NassiDiagramDocumentDTO:
    source_location: str
    function_count: int
    function_names: tuple[str, ...]
    html: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source_location": self.source_location,
            "function_count": self.function_count,
            "function_names": list(self.function_names),
        }


@dataclass(frozen=True, slots=True)
class NassiDiagramBundleDTO:
    root_path: str
    document_count: int
    documents: tuple[NassiDiagramDocumentDTO, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "root_path": self.root_path,
            "document_count": self.document_count,
            "documents": [document.to_dict() for document in self.documents],
        }


@dataclass(slots=True)
class NassiDiagramService:
    source_repository: SourceRepository
    extractor: ControlFlowExtractor
    renderer: NassiDiagramRenderer

    def build_file_diagram(self, command: BuildNassiDiagramCommand) -> NassiDiagramDocumentDTO:
        source_unit = self.source_repository.load_file(command.path)
        return self._build_document(source_unit)

    def build_directory_diagrams(
        self, command: BuildNassiDirectoryCommand
    ) -> NassiDiagramBundleDTO:
        source_units = tuple(self.source_repository.list_sources(command.root_path))
        diagrams = [self.extractor.extract(source_unit) for source_unit in source_units]

        # Compute max nesting depth for CSS optimization (FEAT-8)
        max_depth = 0
        for diagram in diagrams:
            for function in diagram.functions:
                max_depth = max(max_depth, self._compute_max_depth(function.steps))
        # Set renderer depth: include the max level (add 1 if any depth)
        self.renderer.max_depth_for_css = max_depth + 1 if max_depth > 0 else 1
        self.renderer.use_shared_css = True

        documents = tuple(
            NassiDiagramDocumentDTO(
                source_location=diagram.source_location,
                function_count=len(diagram.functions),
                function_names=tuple(function.qualified_name for function in diagram.functions),
                html=self.renderer.render(diagram),
            )
            for diagram in diagrams
        )
        return NassiDiagramBundleDTO(
            root_path=str(Path(command.root_path).expanduser().resolve()),
            document_count=len(documents),
            documents=documents,
        )

    def _build_document(self, source_unit) -> NassiDiagramDocumentDTO:
        diagram = self.extractor.extract(source_unit)
        return NassiDiagramDocumentDTO(
            source_location=diagram.source_location,
            function_count=len(diagram.functions),
            function_names=tuple(function.qualified_name for function in diagram.functions),
            html=self.renderer.render(diagram),
        )

    @staticmethod
    def _compute_max_depth(steps: tuple[ControlFlowStep, ...], current: int = 0) -> int:
        max_seen = current
        for step in steps:
            if isinstance(step, IfFlowStep):
                max_seen = max(
                    max_seen, NassiDiagramService._compute_max_depth(step.then_steps, current + 1)
                )
                if step.else_steps:
                    max_seen = max(
                        max_seen,
                        NassiDiagramService._compute_max_depth(step.else_steps, current + 1),
                    )
            elif isinstance(
                step,
                (
                    WhileFlowStep,
                    ForInFlowStep,
                    NumericForFlowStep,
                    RepeatUntilFlowStep,
                    ClosureFlowStep,
                ),
            ):
                body = step.body_steps  # type: ignore[attr-defined]
                max_seen = max(max_seen, NassiDiagramService._compute_max_depth(body, current + 1))
        return max_seen
