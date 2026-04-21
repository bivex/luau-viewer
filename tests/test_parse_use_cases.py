import json
import subprocess
import sys
from pathlib import Path

from luau_viewer.application.dto import ParseDirectoryCommand, ParseFileCommand
from luau_viewer.application.use_cases import ParsingJobService
from luau_viewer.infrastructure.antlr.parser_adapter import AntlrLuauSyntaxParser
from luau_viewer.infrastructure.filesystem.source_repository import FileSystemSourceRepository
from luau_viewer.infrastructure.system import (
    InMemoryParsingJobRepository,
    StructuredLoggingEventPublisher,
    SystemClock,
)


ROOT = Path(__file__).resolve().parent.parent


def _ensure_generated_parser() -> None:
    generated_parser = (
        ROOT / "src" / "luau_viewer" / "infrastructure" / "antlr" / "generated" / "luau" / "LuauParser.py"
    )
    if generated_parser.exists():
        return
    subprocess.run(
        [sys.executable, "scripts/generate_luau_parser.py"],
        cwd=ROOT,
        check=True,
    )


def _build_service() -> ParsingJobService:
    _ensure_generated_parser()
    return ParsingJobService(
        source_repository=FileSystemSourceRepository(),
        parser=AntlrLuauSyntaxParser(),
        event_publisher=StructuredLoggingEventPublisher(),
        clock=SystemClock(),
        job_repository=InMemoryParsingJobRepository(),
    )


def test_parse_file_extracts_structure() -> None:
    service = _build_service()
    report = service.parse_file(ParseFileCommand(path=str(ROOT / "tests" / "fixtures" / "valid.luau")))

    assert report.summary.source_count == 1
    assert report.summary.technical_failure_count == 0
    assert report.sources[0].status in {"succeeded", "succeeded_with_diagnostics"}
    kinds = {element.kind for element in report.sources[0].structural_elements}
    assert "function" in kinds


def test_parse_directory_returns_report_for_all_files() -> None:
    service = _build_service()
    report = service.parse_directory(ParseDirectoryCommand(root_path=str(ROOT / "tests" / "fixtures")))

    assert report.summary.source_count == 3
    assert len(report.sources) == 3


def test_parse_file_handles_local_function(tmp_path: Path) -> None:
    service = _build_service()
    source_path = tmp_path / "local_func.luau"
    source_path.write_text(
        """
local function greet(name)
    return "Hello, " .. name
end

return greet
""".strip(),
        encoding="utf-8",
    )

    report = service.parse_file(ParseFileCommand(path=str(source_path)))

    assert report.summary.source_count == 1
    assert report.summary.technical_failure_count == 0
    kinds = {element.kind for element in report.sources[0].structural_elements}
    assert "local_function" in kinds


def test_cli_outputs_json() -> None:
    _ensure_generated_parser()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "luau_viewer.presentation.cli.main",
            "parse-file",
            str(ROOT / "tests" / "fixtures" / "valid.luau"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["source_count"] == 1
