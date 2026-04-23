import pytest

from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    ClosureFlowStep,
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
    assert "magic-numbers" in rules
    assert "global-variable" in rules
    assert "connect-leak" in rules
    assert report.smell_count >= 8


# -- duplicate-condition --

def test_duplicate_condition_detected():
    diag = _diagram(_func("f",
        IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="a"),), else_steps=()),
        IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="b"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    dup = [s for s in smells if s.rule == "duplicate-condition"]
    assert len(dup) == 1
    assert "x > 0" in dup[0].message


def test_different_conditions_not_flagged():
    diag = _diagram(_func("f",
        IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="a"),), else_steps=()),
        IfFlowStep(condition="x > 10", then_steps=(ActionFlowStep(label="b"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "duplicate-condition" not in rules


# -- identical-actions --

def test_identical_actions_detected():
    diag = _diagram(_func("f",
        ActionFlowStep(label="x = x + 1"),
        ActionFlowStep(label="x = x + 1"),
    ))
    smells = detector.detect(diag)
    dup = [s for s in smells if s.rule == "identical-actions"]
    assert len(dup) == 1


def test_different_actions_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="x = 1"),
        ActionFlowStep(label="y = 2"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "identical-actions" not in rules


# -- nested-loops --

def test_triple_nested_loops():
    inner = ForInFlowStep(header="k, v in pairs(t)", body_steps=(ActionFlowStep(label="print(v)"),))
    mid = ForInFlowStep(header="j = 1, 10", body_steps=(inner,))
    outer = ForInFlowStep(header="i = 1, 10", body_steps=(mid,))
    diag = _diagram(_func("f", outer))
    smells = detector.detect(diag)
    nested = [s for s in smells if s.rule == "nested-loops"]
    assert len(nested) == 1
    assert "3 nested" in nested[0].message


def test_double_nested_loops_ok():
    inner = ForInFlowStep(header="j = 1, 10", body_steps=(ActionFlowStep(label="x = 1"),))
    outer = ForInFlowStep(header="i = 1, 10", body_steps=(inner,))
    diag = _diagram(_func("f", outer))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "nested-loops" not in rules


# -- self-assignment --

def test_self_assignment_detected():
    diag = _diagram(_func("f",
        ActionFlowStep(label="x = x"),
    ))
    smells = detector.detect(diag)
    sa = [s for s in smells if s.rule == "self-assignment"]
    assert len(sa) == 1
    assert sa[0].severity == SmellSeverity.ERROR


def test_self_assignment_with_index():
    diag = _diagram(_func("f",
        ActionFlowStep(label="data[i] = data[i]"),
    ))
    smells = detector.detect(diag)
    sa = [s for s in smells if s.rule == "self-assignment"]
    assert len(sa) == 1


def test_normal_assignment_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="x = y + 1"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "self-assignment" not in rules


# -- empty-loop --

def test_empty_while_loop():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="running", body_steps=()),
    ))
    smells = detector.detect(diag)
    el = [s for s in smells if s.rule == "empty-loop"]
    assert len(el) == 1


def test_empty_for_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="i = 1, 10", body_steps=()),
    ))
    smells = detector.detect(diag)
    el = [s for s in smells if s.rule == "empty-loop"]
    assert len(el) == 1


def test_non_empty_loop_not_flagged():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="running", body_steps=(ActionFlowStep(label="x = 1"),)),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "empty-loop" not in rules


# -- redundant-condition --

def test_if_true_detected():
    diag = _diagram(_func("f",
        IfFlowStep(condition="true", then_steps=(ActionFlowStep(label="x = 1"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    rc = [s for s in smells if s.rule == "redundant-condition"]
    assert len(rc) == 1
    assert "true" in rc[0].message


def test_if_false_detected():
    diag = _diagram(_func("f",
        IfFlowStep(condition="false", then_steps=(ActionFlowStep(label="x = 1"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    rc = [s for s in smells if s.rule == "redundant-condition"]
    assert len(rc) == 1
    assert "false" in rc[0].message


def test_normal_condition_not_flagged():
    diag = _diagram(_func("f",
        IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="y = 1"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "redundant-condition" not in rules


# -- complex-condition --

def test_complex_condition_detected():
    long_cond = "x > 0 and y < 100 and z ~= nil and a == true and b == false and c ~= d and e >= f"
    diag = _diagram(_func("f",
        IfFlowStep(condition=long_cond, then_steps=(ActionFlowStep(label="ok"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    cc = [s for s in smells if s.rule == "complex-condition"]
    assert len(cc) == 1
    assert cc[0].severity == SmellSeverity.INFO


def test_short_condition_not_flagged():
    diag = _diagram(_func("f",
        IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="ok"),), else_steps=()),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "complex-condition" not in rules


# -- nested-closures --

def test_nested_closures_detected():
    inner = ClosureFlowStep(
        call_label="task.delay(1, function()",
        signature="function()",
        body_steps=(ActionFlowStep(label="print('inner')"),),
    )
    outer = ClosureFlowStep(
        call_label="task.spawn(function()",
        signature="function()",
        body_steps=(inner,),
    )
    diag = _diagram(_func("f", outer))
    smells = detector.detect(diag)
    nc = [s for s in smells if s.rule == "nested-closures"]
    assert len(nc) == 1
    assert "2 nested" in nc[0].message


def test_single_closure_not_flagged():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="task.spawn(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="print('ok')"),),
        ),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "nested-closures" not in rules


# -- magic-numbers --

def test_magic_number_compound():
    diag = _diagram(_func("f",
        ActionFlowStep(label="player.leaderstats.Coins.Value += 15"),
    ))
    smells = detector.detect(diag)
    mg = [s for s in smells if s.rule == "magic-numbers"]
    assert len(mg) == 1
    assert "15" in mg[0].message
    assert mg[0].severity == SmellSeverity.INFO


def test_magic_number_property():
    diag = _diagram(_func("f",
        ActionFlowStep(label="light.Brightness = 2"),
    ))
    smells = detector.detect(diag)
    mg = [s for s in smells if s.rule == "magic-numbers"]
    assert len(mg) == 1


def test_magic_number_constant_def_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local MAX_DAMAGE = 100"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "magic-numbers" not in rules


def test_magic_number_one_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="Coins.Value += 1"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "magic-numbers" not in rules


def test_magic_number_plain_var_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="x = 15"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "magic-numbers" not in rules


# -- global-variable --

def test_global_variable_dot():
    diag = _diagram(_func("f",
        ActionFlowStep(label="_G.PlayerData = {}"),
    ))
    smells = detector.detect(diag)
    gv = [s for s in smells if s.rule == "global-variable"]
    assert len(gv) == 1
    assert gv[0].severity == SmellSeverity.ERROR


def test_global_variable_bracket():
    diag = _diagram(_func("f",
        ActionFlowStep(label='_G["key"] = 42'),
    ))
    smells = detector.detect(diag)
    gv = [s for s in smells if s.rule == "global-variable"]
    assert len(gv) == 1


def test_no_global_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local data = {}"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "global-variable" not in rules


# -- instance-in-loop --

def test_instance_in_for_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="i = 1, 10", body_steps=(
            ActionFlowStep(label='Instance.new("Part")'),
        )),
    ))
    smells = detector.detect(diag)
    il = [s for s in smells if s.rule == "instance-in-loop"]
    assert len(il) == 1
    assert il[0].severity == SmellSeverity.WARNING


def test_instance_in_while_loop():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="spawning", body_steps=(
            ActionFlowStep(label='local part = Instance.new("Part")'),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "instance-in-loop" in rules


def test_instance_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label='local part = Instance.new("Part")'),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "instance-in-loop" not in rules


# -- getchildren-in-loop --

def test_getchildren_in_loop():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="running", body_steps=(
            ActionFlowStep(label="local children = workspace:GetChildren()"),
        )),
    ))
    smells = detector.detect(diag)
    gc = [s for s in smells if s.rule == "getchildren-in-loop"]
    assert len(gc) == 1


def test_getdescendants_in_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="i = 1, 10", body_steps=(
            ActionFlowStep(label="local desc = model:GetDescendants()"),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "getchildren-in-loop" in rules


def test_getchildren_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local children = workspace:GetChildren()"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "getchildren-in-loop" not in rules


# -- unprotected-remote --

def test_fire_server_detected():
    diag = _diagram(_func("f",
        ActionFlowStep(label="DamageRemote:FireServer(enemy, 25)"),
    ))
    smells = detector.detect(diag)
    ur = [s for s in smells if s.rule == "unprotected-remote"]
    assert len(ur) == 1
    assert ur[0].severity == SmellSeverity.ERROR


def test_invoke_server_detected():
    diag = _diagram(_func("f",
        ActionFlowStep(label="ShopRemote:InvokeServer(item)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "unprotected-remote" in rules


def test_onserverevent_without_validation():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="Remote.OnServerEvent:Connect(function(player, damage)",
            signature="function(player, damage)",
            body_steps=(ActionFlowStep(label="enemy.Health -= damage"),),
        ),
    ))
    smells = detector.detect(diag)
    ur = [s for s in smells if s.rule == "unprotected-remote"]
    assert len(ur) == 1
    assert "type validation" in ur[0].message


def test_onserverevent_with_type_check():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="Remote.OnServerEvent:Connect(function(player, damage)",
            signature="function(player, damage)",
            body_steps=(
                IfFlowStep(
                    condition='type(damage) ~= "number"',
                    then_steps=(ActionFlowStep(label="return"),),
                    else_steps=(ActionFlowStep(label="enemy.Health -= damage"),),
                ),
            ),
        ),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "unprotected-remote" not in rules


def test_no_remote_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="print('hello')"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "unprotected-remote" not in rules


# -- connect-leak --

def test_connect_without_cleanup():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="player.CharacterAdded:Connect(function(character)",
            signature="function(character)",
            body_steps=(ActionFlowStep(label="print('loaded')"),),
        ),
    ))
    smells = detector.detect(diag)
    cl = [s for s in smells if s.rule == "connect-leak"]
    assert len(cl) == 1
    assert cl[0].severity == SmellSeverity.WARNING


def test_connect_with_maid_not_flagged():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="Maid:GiveTask(event:Connect(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="print('ok')"),),
        ),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "connect-leak" not in rules


def test_connect_with_disconnect_not_flagged():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="local conn = event:Connect(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="print('ok')"),),
        ),
        ActionFlowStep(label="conn:Disconnect()"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "connect-leak" not in rules


def test_no_connect_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="print('no events')"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "connect-leak" not in rules
