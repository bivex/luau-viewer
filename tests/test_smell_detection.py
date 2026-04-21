import pytest

from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    ControlFlowDiagram,
    ForInFlowStep,
    FunctionControlFlow,
    IfFlowStep,
    RepeatUntilFlowStep,
    WhileFlowStep,
)
from luau_viewer.domain.model import Smell, SmellSeverity
from luau_viewer.infrastructure.smell_detection import StepTreeSmellDetector

detector = StepTreeSmellDetector()


def _diagram(*functions: FunctionControlFlow) -> ControlFlowDiagram:
    return ControlFlowDiagram(source_location="test.luau", functions=functions)


def _func(name: str, *steps) -> FunctionControlFlow:
    return FunctionControlFlow(name=name, signature="", container=None, steps=tuple(steps))


# -- empty-function --

def test_empty_function_detected():
    diag = _diagram(_func("noop"))
    smells = detector.detect(diag)
    assert len(smells) == 1
    assert smells[0].rule == "empty-function"
    assert smells[0].severity == SmellSeverity.INFO


def test_non_empty_function_not_flagged():
    diag = _diagram(_func("f", ActionFlowStep(label="x = 1")))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "empty-function" not in rules


# -- long-function --

def test_long_function_detected():
    steps = tuple(ActionFlowStep(label=f"x = {i}") for i in range(51))
    diag = _diagram(_func("big", *steps))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "long-function" in rules


def test_function_under_limit_not_flagged():
    steps = tuple(ActionFlowStep(label=f"x = {i}") for i in range(10))
    diag = _diagram(_func("small", *steps))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "long-function" not in rules


def test_custom_step_threshold():
    steps = tuple(ActionFlowStep(label=f"x = {i}") for i in range(6))
    diag = _diagram(_func("f", *steps))
    smells = detector.detect(diag, max_function_steps=5)
    rules = [s.rule for s in smells]
    assert "long-function" in rules


# -- unreachable --

def test_unreachable_after_return():
    diag = _diagram(_func("f",
        ActionFlowStep(label="return 1"),
        ActionFlowStep(label="print('never')"),
    ))
    smells = detector.detect(diag)
    unreachable = [s for s in smells if s.rule == "unreachable"]
    assert len(unreachable) == 1
    assert "return" in unreachable[0].message


def test_unreachable_after_break():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="true", body_steps=(
            ActionFlowStep(label="break"),
            ActionFlowStep(label="y = 1"),
        )),
    ))
    smells = detector.detect(diag)
    unreachable = [s for s in smells if s.rule == "unreachable"]
    assert len(unreachable) == 1


def test_no_unreachable_when_sequential():
    diag = _diagram(_func("f",
        ActionFlowStep(label="x = 1"),
        ActionFlowStep(label="return x"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "unreachable" not in rules


# -- deep-nesting --

def test_deep_nesting_detected():
    inner = IfFlowStep(condition="x > 40", then_steps=(ActionFlowStep(label="return x"),), else_steps=())
    l4 = IfFlowStep(condition="x > 30", then_steps=(inner,), else_steps=())
    l3 = IfFlowStep(condition="x > 20", then_steps=(l4,), else_steps=())
    l2 = IfFlowStep(condition="x > 10", then_steps=(l3,), else_steps=())
    l1 = IfFlowStep(condition="x > 0", then_steps=(l2,), else_steps=())
    diag = _diagram(_func("nested", l1))
    smells = detector.detect(diag)
    deep = [s for s in smells if s.rule == "deep-nesting"]
    assert len(deep) == 1
    assert "5 levels" in deep[0].message


def test_nesting_within_threshold():
    l2 = IfFlowStep(condition="x > 10", then_steps=(ActionFlowStep(label="y"),), else_steps=())
    l1 = IfFlowStep(condition="x > 0", then_steps=(l2,), else_steps=())
    diag = _diagram(_func("f", l1))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "deep-nesting" not in rules


# -- infinite-loop --

def test_infinite_loop_while_true():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="true", body_steps=(
            ActionFlowStep(label="x = x + 1"),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "infinite-loop" in rules


def test_while_true_with_return_not_flagged():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="true", body_steps=(
            ActionFlowStep(label="return x"),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "infinite-loop" not in rules


def test_while_true_with_nested_break():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="true", body_steps=(
            IfFlowStep(condition="done", then_steps=(ActionFlowStep(label="break"),), else_steps=()),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "infinite-loop" not in rules


def test_repeat_until_false_infinite():
    diag = _diagram(_func("f",
        RepeatUntilFlowStep(condition="false", body_steps=(
            ActionFlowStep(label="x = 1"),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "infinite-loop" in rules


# -- deprecated-api --

def test_deprecated_spawn():
    diag = _diagram(_func("f",
        ActionFlowStep(label="spawn(function() print(1) end)"),
    ))
    smells = detector.detect(diag)
    dep = [s for s in smells if s.rule == "deprecated-api"]
    assert len(dep) == 1
    assert "spawn" in dep[0].message


def test_deprecated_wait():
    diag = _diagram(_func("f",
        ActionFlowStep(label="wait(0.1)"),
    ))
    smells = detector.detect(diag)
    dep = [s for s in smells if s.rule == "deprecated-api"]
    assert len(dep) == 1
    assert "wait" in dep[0].message


def test_task_spawn_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="task.spawn(function() end)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "deprecated-api" not in rules


def test_task_wait_not_deprecated():
    diag = _diagram(_func("f",
        ActionFlowStep(label="task.wait(1)"),
    ))
    smells = detector.detect(diag)
    dep = [s for s in smells if s.rule == "deprecated-api"]
    assert len(dep) == 0


# -- empty-then --

def test_empty_then_detected():
    diag = _diagram(_func("f",
        IfFlowStep(condition="x", then_steps=(), else_steps=(ActionFlowStep(label="y = 1"),)),
    ))
    smells = detector.detect(diag)
    empty = [s for s in smells if s.rule == "empty-then"]
    assert len(empty) == 1


def test_non_empty_then_not_flagged():
    diag = _diagram(_func("f",
        IfFlowStep(condition="x", then_steps=(ActionFlowStep(label="y = 1"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "empty-then" not in rules


# -- wait-in-loop --

def test_wait_in_loop():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="running", body_steps=(
            ActionFlowStep(label="task.wait(1)"),
        )),
    ))
    smells = detector.detect(diag)
    wait_smells = [s for s in smells if s.rule == "wait-in-loop"]
    assert len(wait_smells) == 1


def test_wait_in_for_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="i = 1, 10", body_steps=(
            ActionFlowStep(label="wait(0.5)"),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "wait-in-loop" in rules


def test_wait_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="task.wait(1)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "wait-in-loop" not in rules


# -- integration: fixture file --

def test_smells_fixture():
    from luau_viewer.application.smell_detection import (
        DetectSmellsCommand,
        SmellDetectionService,
    )
    from luau_viewer.infrastructure.antlr.control_flow_extractor import AntlrLuauControlFlowExtractor
    from luau_viewer.infrastructure.filesystem.source_repository import FileSystemSourceRepository

    service = SmellDetectionService(
        source_repository=FileSystemSourceRepository(),
        extractor=AntlrLuauControlFlowExtractor(),
        smell_detector=StepTreeSmellDetector(),
    )
    report = service.detect_file_smells(
        DetectSmellsCommand(path="tests/fixtures/smells/smells.luau")
    )
    rules = {s.rule for s in report.smells}
    assert "empty-function" in rules
    assert "deprecated-api" in rules
    assert "infinite-loop" in rules
    assert "wait-in-loop" in rules
    assert report.smell_count >= 5
