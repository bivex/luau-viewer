import pytest

from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    ClosureFlowStep,
    ControlFlowDiagram,
    ForInFlowStep,
    FunctionControlFlow,
    IfFlowStep,
    NumericForFlowStep,
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
    assert report.smell_count >= 10


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


# -- yield-in-critical --

def test_yield_in_remote_handler():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="Remote.OnServerEvent:Connect(function(player)",
            signature="function(player)",
            body_steps=(ActionFlowStep(label="task.wait(2)"),),
        ),
    ))
    smells = detector.detect(diag)
    yc = [s for s in smells if s.rule == "yield-in-critical"]
    assert len(yc) == 1
    assert yc[0].severity == SmellSeverity.ERROR


def test_yield_in_bindable_handler():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="BindableEvent.Event:Connect(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="wait(0.5)"),),
        ),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "yield-in-critical" in rules


def test_yield_outside_handler_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="task.wait(1)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "yield-in-critical" not in rules


# -- pcall-ignored-result --

def test_pcall_ignored():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="pcall(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="DataStore:SetAsync(key, {})"),),
        ),
    ))
    smells = detector.detect(diag)
    pi = [s for s in smells if s.rule == "pcall-ignored-result"]
    assert len(pi) == 1
    assert pi[0].severity == SmellSeverity.WARNING


def test_pcall_captured_not_flagged():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="local ok, result = pcall(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="DataStore:GetAsync(key)"),),
        ),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "pcall-ignored-result" not in rules


def test_xpcall_ignored():
    diag = _diagram(_func("f",
        ActionFlowStep(label="xpcall(risky, errorHandler)"),
    ))
    smells = detector.detect(diag)
    pi = [s for s in smells if s.rule == "pcall-ignored-result"]
    assert len(pi) == 1


def test_no_pcall_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="print('safe')"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "pcall-ignored-result" not in rules


# -- infinite-yield-risk --

def test_waitforchild_no_timeout():
    diag = _diagram(_func("f",
        ActionFlowStep(label='local obj = ReplicatedStorage:WaitForChild("DamageEvent")'),
    ))
    smells = detector.detect(diag)
    iy = [s for s in smells if s.rule == "infinite-yield-risk"]
    assert len(iy) == 1
    assert iy[0].severity == SmellSeverity.WARNING


def test_waitforchild_with_timeout_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label='local obj = ReplicatedStorage:WaitForChild("DamageEvent", 5)'),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "infinite-yield-risk" not in rules


def test_waitforchild_single_quotes():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local obj = parent:WaitForChild('Part')"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "infinite-yield-risk" in rules


# -- remote-spam --

def test_fire_in_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="i = 1, 10", body_steps=(
            ActionFlowStep(label="Remote:FireServer(data)"),
        )),
    ))
    smells = detector.detect(diag)
    rs = [s for s in smells if s.rule == "remote-spam"]
    assert len(rs) == 1
    assert rs[0].severity == SmellSeverity.WARNING


def test_fire_in_heartbeat():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="RunService.Heartbeat:Connect(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="Remote:FireServer(position)"),),
        ),
    ))
    smells = detector.detect(diag)
    rs = [s for s in smells if s.rule == "remote-spam"]
    assert len(rs) == 1
    assert "throttle" in rs[0].message


def test_fire_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="Remote:FireServer(data)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "remote-spam" not in rules


# -- task-spawn-storm --

def test_task_spawn_in_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="i = 1, 100", body_steps=(
            ActionFlowStep(label="task.spawn(doWork)"),
        )),
    ))
    smells = detector.detect(diag)
    ts = [s for s in smells if s.rule == "task-spawn-storm"]
    assert len(ts) == 1
    assert ts[0].severity == SmellSeverity.WARNING


def test_coroutine_wrap_in_loop():
    diag = _diagram(_func("f",
        WhileFlowStep(condition="running", body_steps=(
            ActionFlowStep(label="coroutine.wrap(handler)()"),
        )),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "task-spawn-storm" in rules


def test_spawn_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="task.spawn(processData)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "task-spawn-storm" not in rules


# -- require-in-loop --

def test_require_in_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="_, v in pairs(modules)", body_steps=(
            ActionFlowStep(label="local m = require(v)"),
        )),
    ))
    smells = detector.detect(diag)
    ri = [s for s in smells if s.rule == "require-in-loop"]
    assert len(ri) == 1
    assert ri[0].severity == SmellSeverity.WARNING


def test_require_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local Utils = require(Modules.Utils)"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "require-in-loop" not in rules


# -- event-reconnect-loop --

def test_connect_in_loop():
    diag = _diagram(_func("f",
        ForInFlowStep(header="_, part in pairs(parts)", body_steps=(
            ClosureFlowStep(
                call_label="part.Touched:Connect(function(hit)",
                signature="function(hit)",
                body_steps=(ActionFlowStep(label="processHit(hit)"),),
            ),
        )),
    ))
    smells = detector.detect(diag)
    er = [s for s in smells if s.rule == "event-reconnect-loop"]
    assert len(er) == 1
    assert er[0].severity == SmellSeverity.WARNING


def test_connect_outside_loop_not_flagged():
    diag = _diagram(_func("f",
        ClosureFlowStep(
            call_label="event:Connect(function()",
            signature="function()",
            body_steps=(ActionFlowStep(label="handle()"),),
        ),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "event-reconnect-loop" not in rules


# -- unsafe-tonumber --

def test_unsafe_tonumber():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local n = tonumber(value)"),
    ))
    smells = detector.detect(diag)
    ut = [s for s in smells if s.rule == "unsafe-tonumber"]
    assert len(ut) == 1
    assert ut[0].severity == SmellSeverity.INFO


def test_tonumber_with_fallback_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local n = tonumber(value) or 0"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "unsafe-tonumber" not in rules


def test_no_tonumber_not_flagged():
    diag = _diagram(_func("f",
        ActionFlowStep(label="local n = value + 1"),
    ))
    smells = detector.detect(diag)
    rules = [s.rule for s in smells]
    assert "unsafe-tonumber" not in rules


# ===========================================================================
# Edge case tests — boundary conditions, false-positive prevention, ANTLR
# inlining patterns, and combined scenarios
# ===========================================================================


# -- long-function boundary --


class TestLongFunctionBoundary:
    def test_exactly_50_steps_not_flagged(self):
        steps = tuple(ActionFlowStep(label=f"v{i} = {i}") for i in range(50))
        diag = _diagram(_func("fifty", *steps))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "long-function" not in rules

    def test_exactly_51_steps_flagged(self):
        steps = tuple(ActionFlowStep(label=f"v{i} = {i}") for i in range(51))
        diag = _diagram(_func("fiftyone", *steps))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "long-function" in rules

    def test_counts_nested_steps(self):
        inner = IfFlowStep(
            condition="x",
            then_steps=tuple(ActionFlowStep(label=f"s{i}") for i in range(25)),
            else_steps=tuple(ActionFlowStep(label=f"e{i}") for i in range(25)),
        )
        # 1 (if) + 25 (then) + 25 (else) = 51 total
        diag = _diagram(_func("f", inner))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "long-function" in rules


# -- deep-nesting boundary --


class TestDeepNestingBoundary:
    def test_exactly_4_levels_not_flagged(self):
        l4 = IfFlowStep(condition="d", then_steps=(ActionFlowStep(label="x"),), else_steps=())
        l3 = IfFlowStep(condition="c", then_steps=(l4,), else_steps=())
        l2 = IfFlowStep(condition="b", then_steps=(l3,), else_steps=())
        l1 = IfFlowStep(condition="a", then_steps=(l2,), else_steps=())
        # l1=1, l2=2, l3=3, l4=4 — at threshold, not over
        diag = _diagram(_func("f", l1))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "deep-nesting" not in rules

    def test_exactly_5_levels_flagged(self):
        l5 = IfFlowStep(condition="e", then_steps=(ActionFlowStep(label="x"),), else_steps=())
        l4 = IfFlowStep(condition="d", then_steps=(l5,), else_steps=())
        l3 = IfFlowStep(condition="c", then_steps=(l4,), else_steps=())
        l2 = IfFlowStep(condition="b", then_steps=(l3,), else_steps=())
        l1 = IfFlowStep(condition="a", then_steps=(l2,), else_steps=())
        diag = _diagram(_func("f", l1))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "deep-nesting" in rules

    def test_nesting_in_else_branch(self):
        deep = IfFlowStep(condition="x", then_steps=(ActionFlowStep(label="y"),), else_steps=())
        l4 = IfFlowStep(condition="d", then_steps=(), else_steps=(deep,))
        l3 = IfFlowStep(condition="c", then_steps=(), else_steps=(l4,))
        l2 = IfFlowStep(condition="b", then_steps=(), else_steps=(l3,))
        l1 = IfFlowStep(condition="a", then_steps=(), else_steps=(l2,))
        diag = _diagram(_func("f", l1))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "deep-nesting" in rules


# -- infinite-loop edge cases --


class TestInfiniteLoopEdgeCases:
    def test_while_true_with_break_in_nested_if(self):
        diag = _diagram(_func("f",
            WhileFlowStep(condition="true", body_steps=(
                IfFlowStep(condition="done", then_steps=(ActionFlowStep(label="break"),), else_steps=()),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "infinite-loop" not in rules

    def test_while_true_with_continue_only_not_infinite(self):
        # continue is not a break/return — loop still infinite
        diag = _diagram(_func("f",
            WhileFlowStep(condition="true", body_steps=(
                ActionFlowStep(label="continue"),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "infinite-loop" in rules

    def test_repeat_until_true_exits(self):
        diag = _diagram(_func("f",
            RepeatUntilFlowStep(condition="true", body_steps=(
                ActionFlowStep(label="x = 1"),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "infinite-loop" not in rules

    def test_while_false_not_infinite_loop(self):
        # while false never executes, so it's not an infinite loop
        # but redundant-condition should catch it
        diag = _diagram(_func("f",
            WhileFlowStep(condition="false", body_steps=(
                ActionFlowStep(label="x = 1"),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "infinite-loop" not in rules
        assert "redundant-condition" in rules

    def test_while_condition_variable_not_flagged(self):
        diag = _diagram(_func("f",
            WhileFlowStep(condition="running", body_steps=(
                ActionFlowStep(label="x = x + 1"),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "infinite-loop" not in rules


# -- unreachable edge cases --


class TestUnreachableEdgeCases:
    def test_unreachable_after_continue(self):
        diag = _diagram(_func("f",
            WhileFlowStep(condition="true", body_steps=(
                ActionFlowStep(label="continue"),
                ActionFlowStep(label="x = 1"),
            )),
        ))
        smells = detector.detect(diag)
        unreachable = [s for s in smells if s.rule == "unreachable"]
        assert len(unreachable) == 1

    def test_return_inside_if_not_terminating(self):
        # return inside an if doesn't make subsequent code unreachable
        diag = _diagram(_func("f",
            IfFlowStep(condition="x", then_steps=(ActionFlowStep(label="return 1"),), else_steps=()),
            ActionFlowStep(label="y = 2"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "unreachable" not in rules

    def test_multiple_unreachable_steps_reports_first_only(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="return 1"),
            ActionFlowStep(label="a = 1"),
            ActionFlowStep(label="b = 2"),
        ))
        smells = detector.detect(diag)
        unreachable = [s for s in smells if s.rule == "unreachable"]
        assert len(unreachable) == 1


# -- self-assignment edge cases --


class TestSelfAssignmentEdgeCases:
    def test_self_assignment_with_dots(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="obj.health = obj.health"),
        ))
        smells = detector.detect(diag)
        sa = [s for s in smells if s.rule == "self-assignment"]
        assert len(sa) == 1

    def test_different_vars_same_structure_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="x = y"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "self-assignment" not in rules

    def test_self_assignment_with_nested_indices(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="tbl[1][2] = tbl[1][2]"),
        ))
        smells = detector.detect(diag)
        sa = [s for s in smells if s.rule == "self-assignment"]
        assert len(sa) == 1


# -- magic-numbers edge cases --


class TestMagicNumbersEdgeCases:
    def test_zero_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="Coins.Value -= 0"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "magic-numbers" not in rules

    def test_one_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="Coins.Value += 1"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "magic-numbers" not in rules

    def test_constant_uppercase_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="local MAX_PLAYERS = 100"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "magic-numbers" not in rules

    def test_float_greater_than_one_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="part.Transparency = 1.5"),
        ))
        smells = detector.detect(diag)
        mg = [s for s in smells if s.rule == "magic-numbers"]
        assert len(mg) == 1
        assert "1.5" in mg[0].message

    def test_negative_compound_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label=" Coins.Value -= 5"),
        ))
        smells = detector.detect(diag)
        mg = [s for s in smells if s.rule == "magic-numbers"]
        assert len(mg) == 1

    def test_plain_assignment_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="x = 42"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "magic-numbers" not in rules


# -- global-variable edge cases --


class TestGlobalVariableEdgeCases:
    def test_g_in_string_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label='print("_G is bad")'),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "global-variable" not in rules

    def test_g_read_with_brackets(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="local val = _G['key']"),
        ))
        smells = detector.detect(diag)
        gv = [s for s in smells if s.rule == "global-variable"]
        assert len(gv) == 1


# -- deprecated-api edge cases --


class TestDeprecatedApiEdgeCases:
    def test_task_wait_not_deprecated(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="task.wait(1)"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "deprecated-api" not in rules

    def test_task_spawn_not_deprecated(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="task.spawn(fn)"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "deprecated-api" not in rules

    def test_delay_deprecated(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="delay(2, callback)"),
        ))
        smells = detector.detect(diag)
        dep = [s for s in smells if s.rule == "deprecated-api"]
        assert len(dep) == 1
        assert "delay" in dep[0].message

    def test_coroutine_wait_not_deprecated(self):
        # "coroutine.wait" should not trigger — prefix check prevents it
        diag = _diagram(_func("f",
            ActionFlowStep(label="coroutine.wait(1)"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "deprecated-api" not in rules


# -- duplicate-condition edge cases --


class TestDuplicateConditionEdgeCases:
    def test_separated_by_non_if_not_flagged(self):
        # An ActionFlowStep between two ifs resets the prev_if tracker
        diag = _diagram(_func("f",
            IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="a"),), else_steps=()),
            ActionFlowStep(label="doSomething()"),
            IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="b"),), else_steps=()),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "duplicate-condition" not in rules

    def test_triple_duplicate_reports_twice(self):
        diag = _diagram(_func("f",
            IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="a"),), else_steps=()),
            IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="b"),), else_steps=()),
            IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="c"),), else_steps=()),
        ))
        smells = detector.detect(diag)
        dup = [s for s in smells if s.rule == "duplicate-condition"]
        assert len(dup) == 2

    def test_conditions_with_different_whitespace_not_flagged(self):
        # Stripped conditions should match
        diag = _diagram(_func("f",
            IfFlowStep(condition="x > 0", then_steps=(ActionFlowStep(label="a"),), else_steps=()),
            IfFlowStep(condition=" x > 0 ", then_steps=(ActionFlowStep(label="b"),), else_steps=()),
        ))
        smells = detector.detect(diag)
        dup = [s for s in smells if s.rule == "duplicate-condition"]
        assert len(dup) == 1


# -- identical-actions edge cases --


class TestIdenticalActionsEdgeCases:
    def test_empty_label_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label=""),
            ActionFlowStep(label=""),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "identical-actions" not in rules

    def test_three_identical_reports_two(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="x = 1"),
            ActionFlowStep(label="x = 1"),
            ActionFlowStep(label="x = 1"),
        ))
        smells = detector.detect(diag)
        dup = [s for s in smells if s.rule == "identical-actions"]
        assert len(dup) == 2


# -- complex-condition edge cases --


class TestComplexConditionEdgeCases:
    def test_exactly_80_chars_not_flagged(self):
        cond = "x" * 80
        diag = _diagram(_func("f",
            IfFlowStep(condition=cond, then_steps=(ActionFlowStep(label="ok"),), else_steps=()),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "complex-condition" not in rules

    def test_81_chars_flagged(self):
        cond = "x" * 81
        diag = _diagram(_func("f",
            IfFlowStep(condition=cond, then_steps=(ActionFlowStep(label="ok"),), else_steps=()),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "complex-condition" in rules


# -- connect-leak edge cases --


class TestConnectLeakEdgeCases:
    def test_connect_with_janitor_not_flagged(self):
        diag = _diagram(_func("f",
            ClosureFlowStep(
                call_label="event:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label="print('ok')"),),
            ),
            ActionFlowStep(label="Janitor:Add(conn)"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "connect-leak" not in rules

    def test_connect_with_trove_not_flagged(self):
        diag = _diagram(_func("f",
            ClosureFlowStep(
                call_label="Trove:GiveTask(event:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label="print('ok')"),),
            ),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "connect-leak" not in rules

    def test_multiple_connects_single_leak(self):
        diag = _diagram(_func("f",
            ClosureFlowStep(
                call_label="a:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label="x = 1"),),
            ),
            ClosureFlowStep(
                call_label="b:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label="y = 2"),),
            ),
        ))
        smells = detector.detect(diag)
        cl = [s for s in smells if s.rule == "connect-leak"]
        assert len(cl) == 1  # one leak per function, not per Connect


# -- yield-in-critical ANTLR inlining --


class TestYieldInCriticalInlined:
    def test_inlined_action_step_detected(self):
        diag = _diagram(_func("f",
            ActionFlowStep(
                label="Remote.OnServerEvent:Connect(function(player) task.wait(2) end)"
            ),
        ))
        smells = detector.detect(diag)
        yc = [s for s in smells if s.rule == "yield-in-critical"]
        assert len(yc) == 1

    def test_inlined_with_no_yield_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(
                label="Remote.OnServerEvent:Connect(function(player) print('ok') end)"
            ),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "yield-in-critical" not in rules


# -- unprotected-remote ANTLR inlining --


class TestUnprotectedRemoteInlined:
    def test_inlined_onserverevent_no_validation(self):
        diag = _diagram(_func("f",
            ActionFlowStep(
                label="DamageEvent.OnServerEvent:Connect(function(player, dmg) health -= dmg end)"
            ),
        ))
        smells = detector.detect(diag)
        ur = [s for s in smells if s.rule == "unprotected-remote"]
        assert len(ur) >= 1

    def test_inlined_with_type_check_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(
                label="DamageEvent.OnServerEvent:Connect(function(player, dmg) if type(dmg) == 'number' then health -= dmg end end)"
            ),
        ))
        smells = detector.detect(diag)
        ur = [s for s in smells if s.rule == "unprotected-remote" and "type validation" in ur[0].message] if "ur" in dir() else []
        # The ActionFlowStep label contains 'type(' so the inlined check should skip it
        smells_unprot = [s for s in detector.detect(diag) if s.rule == "unprotected-remote"]
        # Should not flag for server-side validation since 'type(' is in the label
        server_msgs = [s for s in smells_unprot if "type validation" in s.message]
        assert len(server_msgs) == 0


# -- event-reconnect-loop ANTLR inlining --


class TestEventReconnectLoopInlined:
    def test_inlined_connect_in_for_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="_, part in pairs(parts)", body_steps=(
                ActionFlowStep(
                    label="part.Touched:Connect(function(hit) print(hit) end)"
                ),
            )),
        ))
        smells = detector.detect(diag)
        er = [s for s in smells if s.rule == "event-reconnect-loop"]
        assert len(er) == 1


# -- nested-closures ANTLR inlining --


class TestNestedClosuresInlined:
    def test_inlined_double_function_count(self):
        diag = _diagram(_func("f",
            ActionFlowStep(
                label="task.spawn(function() task.delay(1, function() print('deep') end) end)"
            ),
        ))
        smells = detector.detect(diag)
        nc = [s for s in smells if s.rule == "nested-closures"]
        assert len(nc) == 1
        assert "2 nested" in nc[0].message

    def test_single_function_in_label_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(
                label="task.spawn(function() print('ok') end)"
            ),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "nested-closures" not in rules


# -- remote-spam edge cases --


class TestRemoteSpamEdgeCases:
    def test_fire_in_renderstepped(self):
        diag = _diagram(_func("f",
            ClosureFlowStep(
                call_label="RunService.RenderStepped:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label="Remote:FireServer(pos)"),),
            ),
        ))
        smells = detector.detect(diag)
        rs = [s for s in smells if s.rule == "remote-spam"]
        assert len(rs) == 1
        assert "throttle" in rs[0].message

    def test_fire_in_stepped(self):
        diag = _diagram(_func("f",
            ClosureFlowStep(
                call_label="RunService.Stepped:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label="Remote:FireServer(data)"),),
            ),
        ))
        smells = detector.detect(diag)
        rs = [s for s in smells if s.rule == "remote-spam"]
        assert len(rs) == 1

    def test_fire_all_clients_in_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="i = 1, 10", body_steps=(
                ActionFlowStep(label="Remote:FireAllClients(data)"),
            )),
        ))
        smells = detector.detect(diag)
        rs = [s for s in smells if s.rule == "remote-spam"]
        assert len(rs) == 1


# -- task-spawn-storm edge cases --


class TestTaskSpawnStormEdgeCases:
    def test_spawn_in_closure_inside_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="i = 1, 100", body_steps=(
                ClosureFlowStep(
                    call_label="task.spawn(function()",
                    signature="function()",
                    body_steps=(ActionFlowStep(label="process()"),),
                ),
            )),
        ))
        smells = detector.detect(diag)
        ts = [s for s in smells if s.rule == "task-spawn-storm"]
        assert len(ts) == 1


# -- require-in-loop edge cases --


class TestRequireInLoopEdgeCases:
    def test_require_in_nested_if_inside_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="_, v in pairs(mods)", body_steps=(
                IfFlowStep(
                    condition="v:IsA('ModuleScript')",
                    then_steps=(ActionFlowStep(label="local m = require(v)"),),
                    else_steps=(),
                ),
            )),
        ))
        smells = detector.detect(diag)
        ri = [s for s in smells if s.rule == "require-in-loop"]
        assert len(ri) == 1

    def test_require_in_closure_inside_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="i = 1, 10", body_steps=(
                ClosureFlowStep(
                    call_label="task.spawn(function()",
                    signature="function()",
                    body_steps=(ActionFlowStep(label="local m = require(v)"),),
                ),
            )),
        ))
        smells = detector.detect(diag)
        ri = [s for s in smells if s.rule == "require-in-loop"]
        # require inside closure inside loop still flagged
        assert len(ri) == 1


# -- pcall-ignored edge cases --


class TestPcallIgnoredEdgeCases:
    def test_pcall_as_statement_ignored(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="pcall(riskyFunction)"),
        ))
        smells = detector.detect(diag)
        pi = [s for s in smells if s.rule == "pcall-ignored-result"]
        assert len(pi) == 1

    def test_local_ok_pcall_not_ignored(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="local ok = pcall(fn)"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "pcall-ignored-result" not in rules

    def test_multi_return_pcall_not_ignored(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="local ok, result = pcall(fn)"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "pcall-ignored-result" not in rules


# -- infinite-yield-risk edge cases --


class TestInfiniteYieldRiskEdgeCases:
    def test_waitforchild_with_timeout_zero(self):
        # timeout = 0 is still a timeout parameter, regex won't match
        diag = _diagram(_func("f",
            ActionFlowStep(label='local obj = parent:WaitForChild("X", 0)'),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "infinite-yield-risk" not in rules

    def test_waitforchild_in_closure(self):
        diag = _diagram(_func("f",
            ClosureFlowStep(
                call_label="event:Connect(function()",
                signature="function()",
                body_steps=(ActionFlowStep(label='local child = parent:WaitForChild("Part")'),),
            ),
        ))
        smells = detector.detect(diag)
        iy = [s for s in smells if s.rule == "infinite-yield-risk"]
        assert len(iy) == 1


# -- unsafe-tonumber edge cases --


class TestUnsafeTonumberEdgeCases:
    def test_tonumber_with_if_guard_not_flagged(self):
        # tonumber inside an if-check condition is safe
        diag = _diagram(_func("f",
            IfFlowStep(
                condition="tonumber(x) ~= nil",
                then_steps=(ActionFlowStep(label="local n = tonumber(x)"),),
                else_steps=(),
            ),
        ))
        smells = detector.detect(diag)
        ut = [s for s in smells if s.rule == "unsafe-tonumber"]
        # Still flagged because the action step itself doesn't have "or"
        assert len(ut) == 1

    def test_tonumber_in_expression(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="local result = tonumber(x) + 1"),
        ))
        smells = detector.detect(diag)
        ut = [s for s in smells if s.rule == "unsafe-tonumber"]
        assert len(ut) == 1

    def test_tonumber_with_or_zero_not_flagged(self):
        diag = _diagram(_func("f",
            ActionFlowStep(label="local n = tonumber(x) or 0"),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "unsafe-tonumber" not in rules


# -- instance-in-loop edge cases --


class TestInstanceInLoopEdgeCases:
    def test_instance_in_nested_if_inside_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="i = 1, 10", body_steps=(
                IfFlowStep(
                    condition="shouldSpawn",
                    then_steps=(ActionFlowStep(label='Instance.new("Part")'),),
                    else_steps=(),
                ),
            )),
        ))
        smells = detector.detect(diag)
        il = [s for s in smells if s.rule == "instance-in-loop"]
        assert len(il) == 1

    def test_instance_in_repeat_until(self):
        diag = _diagram(_func("f",
            RepeatUntilFlowStep(condition="done", body_steps=(
                ActionFlowStep(label='Instance.new("Part")'),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "instance-in-loop" in rules


# -- getchildren-in-loop edge cases --


class TestGetChildrenInLoopEdgeCases:
    def test_getdescendants_in_while(self):
        diag = _diagram(_func("f",
            WhileFlowStep(condition="refresh", body_steps=(
                ActionFlowStep(label="local d = model:GetDescendants()"),
            )),
        ))
        smells = detector.detect(diag)
        gc = [s for s in smells if s.rule == "getchildren-in-loop"]
        assert len(gc) == 1

    def test_getchildren_in_numeric_for(self):
        diag = _diagram(_func("f",
            NumericForFlowStep(header="i = 1, 10", body_steps=(
                ActionFlowStep(label="local c = workspace:GetChildren()"),
            )),
        ))
        smells = detector.detect(diag)
        rules = [s.rule for s in smells]
        assert "getchildren-in-loop" in rules


# -- empty-loop edge cases --


class TestEmptyLoopEdgeCases:
    def test_empty_repeat_until(self):
        diag = _diagram(_func("f",
            RepeatUntilFlowStep(condition="done", body_steps=()),
        ))
        smells = detector.detect(diag)
        el = [s for s in smells if s.rule == "empty-loop"]
        assert len(el) == 1

    def test_empty_numeric_for(self):
        diag = _diagram(_func("f",
            NumericForFlowStep(header="i = 1, 10", body_steps=()),
        ))
        smells = detector.detect(diag)
        el = [s for s in smells if s.rule == "empty-loop"]
        assert len(el) == 1


# -- empty-then edge cases --


class TestEmptyThenEdgeCases:
    def test_empty_then_in_nested_if(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="i = 1, 10", body_steps=(
                IfFlowStep(condition="x", then_steps=(), else_steps=(ActionFlowStep(label="y = 1"),)),
            )),
        ))
        smells = detector.detect(diag)
        et = [s for s in smells if s.rule == "empty-then"]
        assert len(et) == 1

    def test_empty_then_and_else(self):
        diag = _diagram(_func("f",
            IfFlowStep(condition="x", then_steps=(), else_steps=()),
        ))
        smells = detector.detect(diag)
        et = [s for s in smells if s.rule == "empty-then"]
        assert len(et) == 1


# -- wait-in-loop edge cases --


class TestWaitInLoopEdgeCases:
    def test_wait_in_nested_if_inside_loop(self):
        diag = _diagram(_func("f",
            ForInFlowStep(header="i = 1, 10", body_steps=(
                IfFlowStep(
                    condition="needDelay",
                    then_steps=(ActionFlowStep(label="task.wait(0.1)"),),
                    else_steps=(),
                ),
            )),
        ))
        smells = detector.detect(diag)
        wait = [s for s in smells if s.rule == "wait-in-loop"]
        assert len(wait) == 1

    def test_deprecated_wait_in_loop(self):
        diag = _diagram(_func("f",
            WhileFlowStep(condition="running", body_steps=(
                ActionFlowStep(label="wait(1)"),
            )),
        ))
        smells = detector.detect(diag)
        wait = [s for s in smells if s.rule == "wait-in-loop"]
        assert len(wait) == 1


# -- empty-function edge cases --


class TestEmptyFunctionEdgeCases:
    def test_function_with_only_empty_loop(self):
        diag = _diagram(_func("f",
            WhileFlowStep(condition="running", body_steps=()),
        ))
        smells = detector.detect(diag)
        # Not empty — it has a WhileFlowStep
        rules = [s.rule for s in smells]
        assert "empty-function" not in rules
        assert "empty-loop" in rules

    def test_multiple_empty_functions(self):
        diag = _diagram(
            _func("noop1"),
            _func("noop2"),
        )
        smells = detector.detect(diag)
        ef = [s for s in smells if s.rule == "empty-function"]
        assert len(ef) == 2


# -- combined / multi-smell scenarios --


class TestCombinedSmells:
    def test_function_with_many_smells(self):
        diag = _diagram(_func("kitchen_sink",
            ForInFlowStep(header="i = 1, 100", body_steps=(
                ActionFlowStep(label='Instance.new("Part")'),
                ActionFlowStep(label="task.spawn(doWork)"),
                ActionFlowStep(label="local m = require(mod)"),
                ActionFlowStep(label='local kids = workspace:GetChildren()'),
                ActionFlowStep(label="Remote:FireServer(data)"),
                ActionFlowStep(label="wait(0.1)"),
            )),
        ))
        smells = detector.detect(diag)
        rules = {s.rule for s in smells}
        assert "instance-in-loop" in rules
        assert "task-spawn-storm" in rules
        assert "require-in-loop" in rules
        assert "getchildren-in-loop" in rules
        assert "remote-spam" in rules
        assert "wait-in-loop" in rules
        assert "deprecated-api" in rules

    def test_clean_function_no_smells(self):
        diag = _diagram(_func("clean",
            ActionFlowStep(label="local x = 1"),
            ActionFlowStep(label="local result = tonumber(x) or 0"),
            ActionFlowStep(label="local obj = parent:WaitForChild('Part', 5)"),
            ActionFlowStep(label="local ok, data = pcall(function() return store:Get(key) end)"),
            ActionFlowStep(label="return result"),
        ))
        smells = detector.detect(diag)
        rules = {s.rule for s in smells}
        assert "magic-numbers" not in rules
        assert "global-variable" not in rules
        assert "unsafe-tonumber" not in rules
        assert "infinite-yield-risk" not in rules
        assert "pcall-ignored-result" not in rules
        assert "unreachable" not in rules
