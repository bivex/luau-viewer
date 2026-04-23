"""End-to-end integration tests using realistic Roblox Luau files."""

import pytest

from luau_viewer.application.smell_detection import (
    DetectDirectorySmellsCommand,
    DetectSmellsCommand,
    SmellDetectionConfig,
    SmellDetectionService,
)
from luau_viewer.infrastructure.antlr.control_flow_extractor import AntlrLuauControlFlowExtractor
from luau_viewer.infrastructure.filesystem.source_repository import FileSystemSourceRepository
from luau_viewer.infrastructure.smell_detection import StepTreeSmellDetector

FIXTURES = "tests/fixtures/roblox_smells"


def _service() -> SmellDetectionService:
    return SmellDetectionService(
        source_repository=FileSystemSourceRepository(),
        extractor=AntlrLuauControlFlowExtractor(),
        smell_detector=StepTreeSmellDetector(),
        config=SmellDetectionConfig(),
    )


def _file(name: str):
    return _service().detect_file_smells(DetectSmellsCommand(path=f"{FIXTURES}/{name}"))


def _rules(report) -> set[str]:
    return {s.rule for s in report.smells}


# ---------------------------------------------------------------------------
# clean_module.luau — zero smells on well-written code
# ---------------------------------------------------------------------------


class TestCleanModule:
    def test_no_smells(self):
        report = _file("clean_module.luau")
        assert report.smell_count == 0

    def test_zero_summary(self):
        report = _file("clean_module.luau")
        assert report.summary.error == 0
        assert report.summary.warning == 0
        assert report.summary.info == 0


# ---------------------------------------------------------------------------
# security.luau — RemoteEvent security patterns
# ---------------------------------------------------------------------------


class TestSecuritySmells:
    def test_detects_unprotected_remote(self):
        report = _file("security.luau")
        assert "unprotected-remote" in _rules(report)

    def test_detects_connect_leak(self):
        report = _file("security.luau")
        assert "connect-leak" in _rules(report)

    def test_smell_count(self):
        report = _file("security.luau")
        assert report.smell_count >= 4


# ---------------------------------------------------------------------------
# performance.luau — frame-tight and loop performance
# ---------------------------------------------------------------------------


class TestPerformanceSmells:
    def test_detects_instance_in_loop(self):
        report = _file("performance.luau")
        assert "instance-in-loop" in _rules(report)

    def test_detects_getchildren_in_loop(self):
        report = _file("performance.luau")
        assert "getchildren-in-loop" in _rules(report)

    def test_detects_task_spawn_storm(self):
        report = _file("performance.luau")
        assert "task-spawn-storm" in _rules(report)

    def test_detects_require_in_loop(self):
        report = _file("performance.luau")
        assert "require-in-loop" in _rules(report)

    def test_detects_remote_spam(self):
        report = _file("performance.luau")
        assert "remote-spam" in _rules(report)

    def test_detects_empty_loop(self):
        report = _file("performance.luau")
        assert "empty-loop" in _rules(report)

    def test_detects_deprecated_api(self):
        report = _file("performance.luau")
        assert "deprecated-api" in _rules(report)

    def test_detects_wait_in_loop(self):
        report = _file("performance.luau")
        assert "wait-in-loop" in _rules(report)

    def test_smell_count(self):
        report = _file("performance.luau")
        assert report.smell_count >= 9


# ---------------------------------------------------------------------------
# reliability.luau — correctness and error handling
# ---------------------------------------------------------------------------


class TestReliabilitySmells:
    def test_detects_pcall_ignored(self):
        report = _file("reliability.luau")
        assert "pcall-ignored-result" in _rules(report)

    def test_detects_infinite_yield_risk(self):
        report = _file("reliability.luau")
        assert "infinite-yield-risk" in _rules(report)

    def test_detects_unsafe_tonumber(self):
        report = _file("reliability.luau")
        assert "unsafe-tonumber" in _rules(report)

    def test_detects_self_assignment(self):
        report = _file("reliability.luau")
        assert "self-assignment" in _rules(report)

    def test_detects_empty_function(self):
        report = _file("reliability.luau")
        assert "empty-function" in _rules(report)

    def test_detects_unreachable(self):
        report = _file("reliability.luau")
        assert "unreachable" in _rules(report)

    def test_detects_redundant_condition(self):
        report = _file("reliability.luau")
        assert "redundant-condition" in _rules(report)

    def test_smell_count(self):
        report = _file("reliability.luau")
        assert report.smell_count >= 9


# ---------------------------------------------------------------------------
# style.luau — code style and architecture
# ---------------------------------------------------------------------------


class TestStyleSmells:
    def test_detects_magic_numbers(self):
        report = _file("style.luau")
        assert "magic-numbers" in _rules(report)

    def test_detects_global_variable(self):
        report = _file("style.luau")
        assert "global-variable" in _rules(report)

    def test_detects_deprecated_api(self):
        report = _file("style.luau")
        assert "deprecated-api" in _rules(report)

    def test_detects_deep_nesting(self):
        report = _file("style.luau")
        assert "deep-nesting" in _rules(report)

    def test_detects_duplicate_condition(self):
        report = _file("style.luau")
        assert "duplicate-condition" in _rules(report)

    def test_detects_identical_actions(self):
        report = _file("style.luau")
        assert "identical-actions" in _rules(report)

    def test_detects_complex_condition(self):
        report = _file("style.luau")
        assert "complex-condition" in _rules(report)

    def test_detects_nested_loops(self):
        report = _file("style.luau")
        assert "nested-loops" in _rules(report)

    def test_detects_empty_then(self):
        report = _file("style.luau")
        assert "empty-then" in _rules(report)

    def test_smell_count(self):
        report = _file("style.luau")
        assert report.smell_count >= 12


# ---------------------------------------------------------------------------
# directory scan
# ---------------------------------------------------------------------------


class TestDirectoryScan:
    def test_detects_all_files(self):
        report = _service().detect_directory_smells(
            DetectDirectorySmellsCommand(root_path=FIXTURES)
        )
        assert report.file_count == 5

    def test_total_smells(self):
        report = _service().detect_directory_smells(
            DetectDirectorySmellsCommand(root_path=FIXTURES)
        )
        assert report.total_smells >= 35

    def test_clean_file_has_zero(self):
        report = _service().detect_directory_smells(
            DetectDirectorySmellsCommand(root_path=FIXTURES)
        )
        clean = [f for f in report.files if "clean_module" in f.source_location]
        assert len(clean) == 1
        assert clean[0].smell_count == 0

    def test_has_errors(self):
        report = _service().detect_directory_smells(
            DetectDirectorySmellsCommand(root_path=FIXTURES)
        )
        assert report.summary.error >= 5

    def test_has_warnings(self):
        report = _service().detect_directory_smells(
            DetectDirectorySmellsCommand(root_path=FIXTURES)
        )
        assert report.summary.warning >= 20

    def test_has_info(self):
        report = _service().detect_directory_smells(
            DetectDirectorySmellsCommand(root_path=FIXTURES)
        )
        assert report.summary.info >= 3
