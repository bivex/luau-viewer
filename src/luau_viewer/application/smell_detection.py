from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from luau_viewer.domain.control_flow import ControlFlowDiagram
from luau_viewer.domain.model import Smell
from luau_viewer.domain.ports import ControlFlowExtractor, SmellDetector, SourceRepository


@dataclass(frozen=True, slots=True)
class DetectSmellsCommand:
    path: str


@dataclass(frozen=True, slots=True)
class DetectDirectorySmellsCommand:
    root_path: str


@dataclass(frozen=True, slots=True)
class SmellDetectionConfig:
    max_nesting_depth: int = 4
    max_function_steps: int = 50


@dataclass(frozen=True, slots=True)
class SmellDTO:
    rule: str
    severity: str
    message: str
    function: str | None
    line: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "function": self.function,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class SmellSummaryDTO:
    error: int
    warning: int
    info: int

    def to_dict(self) -> dict[str, object]:
        return {
            "error": self.error,
            "warning": self.warning,
            "info": self.info,
        }


@dataclass(frozen=True, slots=True)
class FileSmellReportDTO:
    source_location: str
    smell_count: int
    summary: SmellSummaryDTO
    smells: tuple[SmellDTO, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_location": self.source_location,
            "smell_count": self.smell_count,
            "summary": self.summary.to_dict(),
            "smells": [s.to_dict() for s in self.smells],
        }


@dataclass(frozen=True, slots=True)
class DirectorySmellReportDTO:
    root_path: str
    file_count: int
    total_smells: int
    summary: SmellSummaryDTO
    files: tuple[FileSmellReportDTO, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "root_path": self.root_path,
            "file_count": self.file_count,
            "total_smells": self.total_smells,
            "summary": self.summary.to_dict(),
            "files": [f.to_dict() for f in self.files],
        }


@dataclass(slots=True)
class SmellDetectionService:
    source_repository: SourceRepository
    extractor: ControlFlowExtractor
    smell_detector: SmellDetector
    config: SmellDetectionConfig = field(default_factory=SmellDetectionConfig)

    def detect_file_smells(self, command: DetectSmellsCommand) -> FileSmellReportDTO:
        source_unit = self.source_repository.load_file(command.path)
        return self._detect_for_source(source_unit)

    def detect_directory_smells(
        self, command: DetectDirectorySmellsCommand
    ) -> DirectorySmellReportDTO:
        source_units = tuple(self.source_repository.list_sources(command.root_path))
        file_reports = tuple(self._detect_for_source(unit) for unit in source_units)
        total_smells = sum(r.smell_count for r in file_reports)
        return DirectorySmellReportDTO(
            root_path=str(Path(command.root_path).expanduser().resolve()),
            file_count=len(file_reports),
            total_smells=total_smells,
            summary=_aggregate_summary(file_reports),
            files=file_reports,
        )

    def _detect_for_source(self, source_unit: object) -> FileSmellReportDTO:
        from luau_viewer.domain.model import SourceUnit
        assert isinstance(source_unit, SourceUnit)
        diagram = self.extractor.extract(source_unit)
        smells = self.smell_detector.detect(
            diagram,
            max_nesting_depth=self.config.max_nesting_depth,
            max_function_steps=self.config.max_function_steps,
        )
        return _map_to_file_report(diagram.source_location, smells)


def _map_to_file_report(
    source_location: str, smells: tuple[Smell, ...]
) -> FileSmellReportDTO:
    smell_dtos = tuple(_map_smell(s) for s in smells)
    return FileSmellReportDTO(
        source_location=source_location,
        smell_count=len(smell_dtos),
        summary=_count_severities(smells),
        smells=smell_dtos,
    )


def _map_smell(smell: Smell) -> SmellDTO:
    return SmellDTO(
        rule=smell.rule,
        severity=smell.severity.value,
        message=smell.message,
        function=smell.function_name,
        line=smell.line,
    )


def _count_severities(smells: tuple[Smell, ...]) -> SmellSummaryDTO:
    counts = {"error": 0, "warning": 0, "info": 0}
    for smell in smells:
        counts[smell.severity.value] += 1
    return SmellSummaryDTO(**counts)


def _aggregate_summary(
    reports: tuple[FileSmellReportDTO, ...],
) -> SmellSummaryDTO:
    return SmellSummaryDTO(
        error=sum(r.summary.error for r in reports),
        warning=sum(r.summary.warning for r in reports),
        info=sum(r.summary.info for r in reports),
    )
