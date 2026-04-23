from __future__ import annotations

import re
from dataclasses import dataclass

from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    ClosureFlowStep,
    ControlFlowDiagram,
    ControlFlowStep,
    ForInFlowStep,
    FunctionControlFlow,
    IfFlowStep,
    NumericForFlowStep,
    RepeatUntilFlowStep,
    WhileFlowStep,
)
from luau_viewer.domain.model import Smell, SmellSeverity
from luau_viewer.domain.ports import SmellDetector


@dataclass(slots=True)
class StepTreeSmellDetector(SmellDetector):
    def detect(
        self,
        diagram: ControlFlowDiagram,
        *,
        max_nesting_depth: int = 4,
        max_function_steps: int = 50,
    ) -> tuple[Smell, ...]:
        smells: list[Smell] = []
        for function in diagram.functions:
            self._check_empty_function(function, smells)
            self._check_long_function(function, max_function_steps, smells)
            self._check_unreachable(function.steps, function.name, smells)
            self._check_deep_nesting(function.steps, 0, max_nesting_depth, function.name, smells)
            self._check_deprecated_api(function.steps, function.name, smells)
            self._check_infinite_loop(function.steps, function.name, smells)
            self._check_empty_then(function.steps, function.name, smells)
            self._check_wait_in_loop(function.steps, False, function.name, smells)
            self._check_duplicate_condition(function.steps, function.name, smells)
            self._check_identical_actions(function.steps, function.name, smells)
            self._check_nested_loops(function.steps, 0, function.name, smells)
            _check_self_assignment(function.steps, function.name, smells)
            _check_empty_loop(function.steps, function.name, smells)
            _check_redundant_condition(function.steps, function.name, smells)
            _check_complex_condition(function.steps, function.name, smells)
            _check_nested_closures(function.steps, 0, function.name, smells)
            _check_magic_numbers(function.steps, function.name, smells)
            _check_global_variable(function.steps, function.name, smells)
            _check_instance_in_loop(function.steps, False, function.name, smells)
            _check_getchildren_in_loop(function.steps, False, function.name, smells)
            _check_unprotected_remote(function.steps, function.name, smells)
            _check_connect_leak(function, smells)
        return tuple(smells)

    # -- Rule: empty-function --

    @staticmethod
    def _check_empty_function(
        function: FunctionControlFlow,
        smells: list[Smell],
    ) -> None:
        if len(function.steps) == 0:
            smells.append(Smell(
                rule="empty-function",
                severity=SmellSeverity.INFO,
                message=f"Function '{function.name}' has an empty body",
                function_name=function.name,
            ))

    # -- Rule: long-function --

    @staticmethod
    def _check_long_function(
        function: FunctionControlFlow,
        max_steps: int,
        smells: list[Smell],
    ) -> None:
        count = _count_total_steps(function.steps)
        if count > max_steps:
            smells.append(Smell(
                rule="long-function",
                severity=SmellSeverity.WARNING,
                message=f"Function '{function.name}' has {count} steps (exceeds {max_steps})",
                function_name=function.name,
            ))

    # -- Rule: unreachable --

    @staticmethod
    def _check_unreachable(
        steps: tuple[ControlFlowStep, ...],
        function_name: str,
        smells: list[Smell],
    ) -> None:
        terminated = False
        terminator = ""
        for step in steps:
            if terminated:
                label = _action_label(step) or "..."
                smells.append(Smell(
                    rule="unreachable",
                    severity=SmellSeverity.ERROR,
                    message=f"Unreachable code after '{terminator}' in function '{function_name}': {label}",
                    function_name=function_name,
                ))
                break
            if isinstance(step, ActionFlowStep):
                stripped = step.label.strip()
                if _is_terminator(stripped):
                    terminated = True
                    terminator = stripped.split("(")[0].split()[0]
            elif isinstance(step, IfFlowStep):
                StepTreeSmellDetector._check_unreachable(step.then_steps, function_name, smells)
                StepTreeSmellDetector._check_unreachable(step.else_steps, function_name, smells)
            elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                StepTreeSmellDetector._check_unreachable(step.body_steps, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_unreachable(step.body_steps, function_name, smells)

    # -- Rule: deep-nesting --

    @staticmethod
    def _check_deep_nesting(
        steps: tuple[ControlFlowStep, ...],
        current_depth: int,
        max_depth: int,
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for step in steps:
            if isinstance(step, IfFlowStep):
                new_depth = current_depth + 1
                if new_depth > max_depth:
                    smells.append(Smell(
                        rule="deep-nesting",
                        severity=SmellSeverity.WARNING,
                        message=f"Nested {new_depth} levels deep in function '{function_name}' (max {max_depth})",
                        function_name=function_name,
                    ))
                StepTreeSmellDetector._check_deep_nesting(step.then_steps, new_depth, max_depth, function_name, smells)
                StepTreeSmellDetector._check_deep_nesting(step.else_steps, new_depth, max_depth, function_name, smells)
            elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                StepTreeSmellDetector._check_deep_nesting(step.body_steps, current_depth, max_depth, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_deep_nesting(step.body_steps, current_depth, max_depth, function_name, smells)

    # -- Rule: deprecated-api --

    @staticmethod
    def _check_deprecated_api(
        steps: tuple[ControlFlowStep, ...],
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for step in steps:
            if isinstance(step, ActionFlowStep):
                for call in _DEPRECATED_CALLS:
                    if call in step.label:
                        prefix = step.label[:step.label.index(call)]
                        if "task." not in prefix and "coroutine." not in prefix:
                            smells.append(Smell(
                                rule="deprecated-api",
                                severity=SmellSeverity.WARNING,
                                message=f"Deprecated API '{call}(...)' in function '{function_name}': use task.{call}() instead",
                                function_name=function_name,
                            ))
            elif isinstance(step, IfFlowStep):
                StepTreeSmellDetector._check_deprecated_api(step.then_steps, function_name, smells)
                StepTreeSmellDetector._check_deprecated_api(step.else_steps, function_name, smells)
            elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                StepTreeSmellDetector._check_deprecated_api(step.body_steps, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_deprecated_api(step.body_steps, function_name, smells)

    # -- Rule: infinite-loop --

    @staticmethod
    def _check_infinite_loop(
        steps: tuple[ControlFlowStep, ...],
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for step in steps:
            if isinstance(step, WhileFlowStep):
                cond = step.condition.strip().lower()
                if cond == "true" and not _body_has_exit(step.body_steps):
                    smells.append(Smell(
                        rule="infinite-loop",
                        severity=SmellSeverity.WARNING,
                        message=f"'while true' without break/return in function '{function_name}'",
                        function_name=function_name,
                    ))
                StepTreeSmellDetector._check_infinite_loop(step.body_steps, function_name, smells)
            elif isinstance(step, RepeatUntilFlowStep):
                cond = step.condition.strip().lower()
                if cond == "false" and not _body_has_exit(step.body_steps):
                    smells.append(Smell(
                        rule="infinite-loop",
                        severity=SmellSeverity.WARNING,
                        message=f"'repeat ... until false' without break/return in function '{function_name}'",
                        function_name=function_name,
                    ))
                StepTreeSmellDetector._check_infinite_loop(step.body_steps, function_name, smells)
            elif isinstance(step, IfFlowStep):
                StepTreeSmellDetector._check_infinite_loop(step.then_steps, function_name, smells)
                StepTreeSmellDetector._check_infinite_loop(step.else_steps, function_name, smells)
            elif isinstance(step, (ForInFlowStep, NumericForFlowStep)):
                StepTreeSmellDetector._check_infinite_loop(step.body_steps, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_infinite_loop(step.body_steps, function_name, smells)

    # -- Rule: empty-then --

    @staticmethod
    def _check_empty_then(
        steps: tuple[ControlFlowStep, ...],
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for step in steps:
            if isinstance(step, IfFlowStep):
                if len(step.then_steps) == 0:
                    smells.append(Smell(
                        rule="empty-then",
                        severity=SmellSeverity.WARNING,
                        message=f"Empty 'then' branch in function '{function_name}' for condition: {step.condition}",
                        function_name=function_name,
                    ))
                StepTreeSmellDetector._check_empty_then(step.then_steps, function_name, smells)
                StepTreeSmellDetector._check_empty_then(step.else_steps, function_name, smells)
            elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                StepTreeSmellDetector._check_empty_then(step.body_steps, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_empty_then(step.body_steps, function_name, smells)

    # -- Rule: wait-in-loop --

    @staticmethod
    def _check_wait_in_loop(
        steps: tuple[ControlFlowStep, ...],
        inside_loop: bool,
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for step in steps:
            if isinstance(step, ActionFlowStep) and inside_loop:
                label = step.label.lower()
                if "wait(" in label or "wait (" in label:
                    smells.append(Smell(
                        rule="wait-in-loop",
                        severity=SmellSeverity.WARNING,
                        message=f"wait() inside loop in function '{function_name}' hurts performance: {step.label.strip()}",
                        function_name=function_name,
                    ))
            elif isinstance(step, IfFlowStep):
                StepTreeSmellDetector._check_wait_in_loop(step.then_steps, inside_loop, function_name, smells)
                StepTreeSmellDetector._check_wait_in_loop(step.else_steps, inside_loop, function_name, smells)
            elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                StepTreeSmellDetector._check_wait_in_loop(step.body_steps, True, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_wait_in_loop(step.body_steps, inside_loop, function_name, smells)

    # -- Rule: duplicate-condition --

    @staticmethod
    def _check_duplicate_condition(
        steps: tuple[ControlFlowStep, ...],
        function_name: str,
        smells: list[Smell],
    ) -> None:
        prev_if: IfFlowStep | None = None
        for step in steps:
            if isinstance(step, IfFlowStep):
                if prev_if is not None and step.condition.strip() == prev_if.condition.strip():
                    smells.append(Smell(
                        rule="duplicate-condition",
                        severity=SmellSeverity.WARNING,
                        message=f"Duplicate condition '{step.condition.strip()}' in function '{function_name}' — likely a copy-paste error",
                        function_name=function_name,
                    ))
                prev_if = step
                StepTreeSmellDetector._check_duplicate_condition(step.then_steps, function_name, smells)
                StepTreeSmellDetector._check_duplicate_condition(step.else_steps, function_name, smells)
            else:
                prev_if = None
                if isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                    StepTreeSmellDetector._check_duplicate_condition(step.body_steps, function_name, smells)
                elif isinstance(step, ClosureFlowStep):
                    StepTreeSmellDetector._check_duplicate_condition(step.body_steps, function_name, smells)

    # -- Rule: identical-actions --

    @staticmethod
    def _check_identical_actions(
        steps: tuple[ControlFlowStep, ...],
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for i in range(1, len(steps)):
            if (isinstance(steps[i], ActionFlowStep) and isinstance(steps[i - 1], ActionFlowStep)
                    and steps[i].label.strip() == steps[i - 1].label.strip()
                    and steps[i].label.strip()):
                smells.append(Smell(
                    rule="identical-actions",
                    severity=SmellSeverity.WARNING,
                    message=f"Duplicated action in function '{function_name}': {steps[i].label.strip()[:60]}",
                    function_name=function_name,
                ))
        for step in steps:
            if isinstance(step, IfFlowStep):
                StepTreeSmellDetector._check_identical_actions(step.then_steps, function_name, smells)
                StepTreeSmellDetector._check_identical_actions(step.else_steps, function_name, smells)
            elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                StepTreeSmellDetector._check_identical_actions(step.body_steps, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_identical_actions(step.body_steps, function_name, smells)

    # -- Rule: nested-loops --

    @staticmethod
    def _check_nested_loops(
        steps: tuple[ControlFlowStep, ...],
        depth: int,
        function_name: str,
        smells: list[Smell],
    ) -> None:
        for step in steps:
            if isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
                new_depth = depth + 1
                if new_depth > 2:
                    smells.append(Smell(
                        rule="nested-loops",
                        severity=SmellSeverity.WARNING,
                        message=f"{new_depth} nested loops in function '{function_name}' — O(n^{new_depth}) complexity, risky in frame-tight code",
                        function_name=function_name,
                    ))
                StepTreeSmellDetector._check_nested_loops(step.body_steps, new_depth, function_name, smells)
            elif isinstance(step, IfFlowStep):
                StepTreeSmellDetector._check_nested_loops(step.then_steps, depth, function_name, smells)
                StepTreeSmellDetector._check_nested_loops(step.else_steps, depth, function_name, smells)
            elif isinstance(step, ClosureFlowStep):
                StepTreeSmellDetector._check_nested_loops(step.body_steps, depth, function_name, smells)


_DEPRECATED_CALLS = ("spawn(", "delay(", "wait(")
_SELF_ASSIGN_RE = re.compile(r"(?P<left>[\w.:\[\]]+)\s*=\s*(?P<right>[\w.:\[\]]+)\s*$")
_MAGIC_NUM_COMPOUND_RE = re.compile(r'[+\-*/]=\s*(\d+(?:\.\d+)?)\s*(?:--.*)?$')
_MAGIC_NUM_PROPERTY_RE = re.compile(r'\.\w+\s*=\s*(\d+(?:\.\d+)?)\s*(?:--.*)?$')
_CONSTANT_DEF_RE = re.compile(r'^local\s+[A-Z_][A-Z0-9_]*\s*=')
_GLOBAL_RE = re.compile(r'_G\s*[\.\[]')
_GETCHILDREN_RE = re.compile(r':Get(?:Children|Descendants)\(\)')
_REMOTE_CALL_RE = re.compile(r':(?:Fire|Invoke)Server\(')
_CLEANUP_MARKERS = ('Maid', 'Janitor', 'Trove', ':Disconnect()')


def _check_self_assignment(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ActionFlowStep):
            label = step.label.strip()
            # Match "x = x" or "x.y = x.y" — left side equals right side
            m = _SELF_ASSIGN_RE.match(label)
            if m and m.group("left").strip() == m.group("right").strip():
                smells.append(Smell(
                    rule="self-assignment",
                    severity=SmellSeverity.ERROR,
                    message=f"Self-assignment in function '{function_name}': {label[:60]} — variable assigns to itself",
                    function_name=function_name,
                ))
        elif isinstance(step, IfFlowStep):
            _check_self_assignment(step.then_steps, function_name, smells)
            _check_self_assignment(step.else_steps, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_self_assignment(step.body_steps, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_self_assignment(step.body_steps, function_name, smells)


def _check_empty_loop(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            if len(step.body_steps) == 0:
                header = getattr(step, "header", None) or getattr(step, "condition", "")
                smells.append(Smell(
                    rule="empty-loop",
                    severity=SmellSeverity.WARNING,
                    message=f"Empty loop body in function '{function_name}': {type(step).__name__} ({header.strip()[:40]})",
                    function_name=function_name,
                ))
            _check_empty_loop(step.body_steps, function_name, smells)
        elif isinstance(step, IfFlowStep):
            _check_empty_loop(step.then_steps, function_name, smells)
            _check_empty_loop(step.else_steps, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_empty_loop(step.body_steps, function_name, smells)


def _check_redundant_condition(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, IfFlowStep):
            cond = step.condition.strip().lower()
            if cond in ("true", "false"):
                smells.append(Smell(
                    rule="redundant-condition",
                    severity=SmellSeverity.WARNING,
                    message=f"Hard-coded '{step.condition.strip()}' condition in function '{function_name}' — dead code or debug leftover",
                    function_name=function_name,
                ))
            _check_redundant_condition(step.then_steps, function_name, smells)
            _check_redundant_condition(step.else_steps, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            cond = getattr(step, "condition", "").strip().lower()
            if cond == "false" and isinstance(step, WhileFlowStep):
                smells.append(Smell(
                    rule="redundant-condition",
                    severity=SmellSeverity.WARNING,
                    message=f"'while false' in function '{function_name}' — loop never executes",
                    function_name=function_name,
                ))
            _check_redundant_condition(step.body_steps, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_redundant_condition(step.body_steps, function_name, smells)


def _check_complex_condition(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, IfFlowStep):
            if len(step.condition) > 80:
                smells.append(Smell(
                    rule="complex-condition",
                    severity=SmellSeverity.INFO,
                    message=f"Complex condition ({len(step.condition)} chars) in function '{function_name}' — extract to a named variable",
                    function_name=function_name,
                ))
            _check_complex_condition(step.then_steps, function_name, smells)
            _check_complex_condition(step.else_steps, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_complex_condition(step.body_steps, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_complex_condition(step.body_steps, function_name, smells)


def _check_nested_closures(
    steps: tuple[ControlFlowStep, ...],
    depth: int,
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ClosureFlowStep):
            new_depth = depth + 1
            if new_depth > 1:
                smells.append(Smell(
                    rule="nested-closures",
                    severity=SmellSeverity.WARNING,
                    message=f"{new_depth} nested closures in function '{function_name}' — callback hell, refactor with named functions",
                    function_name=function_name,
                ))
            _check_nested_closures(step.body_steps, new_depth, function_name, smells)
        elif isinstance(step, IfFlowStep):
            _check_nested_closures(step.then_steps, depth, function_name, smells)
            _check_nested_closures(step.else_steps, depth, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_nested_closures(step.body_steps, depth, function_name, smells)


# -- Rule: magic-numbers --

def _check_magic_numbers(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ActionFlowStep):
            label = step.label.strip()
            if _CONSTANT_DEF_RE.match(label):
                continue
            for m in _MAGIC_NUM_COMPOUND_RE.finditer(label):
                _flag_magic(m.group(1), label, function_name, smells)
            for m in _MAGIC_NUM_PROPERTY_RE.finditer(label):
                _flag_magic(m.group(1), label, function_name, smells)
        elif isinstance(step, IfFlowStep):
            _check_magic_numbers(step.then_steps, function_name, smells)
            _check_magic_numbers(step.else_steps, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_magic_numbers(step.body_steps, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_magic_numbers(step.body_steps, function_name, smells)


def _flag_magic(
    num_str: str,
    label: str,
    function_name: str,
    smells: list[Smell],
) -> None:
    val = float(num_str)
    if val > 1:
        display = int(val) if val == int(val) else val
        smells.append(Smell(
            rule="magic-numbers",
            severity=SmellSeverity.INFO,
            message=f"Magic number {display} in function '{function_name}': "
                    f"extract to a named constant in Shared/Balance — {label[:60]}",
            function_name=function_name,
        ))


# -- Rule: global-variable --

def _check_global_variable(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ActionFlowStep):
            if _GLOBAL_RE.search(step.label):
                smells.append(Smell(
                    rule="global-variable",
                    severity=SmellSeverity.ERROR,
                    message=f"_G usage in function '{function_name}': "
                            f"never use global state in production Roblox code — {step.label.strip()[:60]}",
                    function_name=function_name,
                ))
        elif isinstance(step, IfFlowStep):
            _check_global_variable(step.then_steps, function_name, smells)
            _check_global_variable(step.else_steps, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_global_variable(step.body_steps, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_global_variable(step.body_steps, function_name, smells)


# -- Rule: instance-in-loop --

def _check_instance_in_loop(
    steps: tuple[ControlFlowStep, ...],
    inside_loop: bool,
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ActionFlowStep) and inside_loop:
            if 'Instance.new(' in step.label:
                smells.append(Smell(
                    rule="instance-in-loop",
                    severity=SmellSeverity.WARNING,
                    message=f"Instance.new() inside loop in function '{function_name}': "
                            f"use object pooling to avoid GC pressure — {step.label.strip()[:60]}",
                    function_name=function_name,
                ))
        elif isinstance(step, IfFlowStep):
            _check_instance_in_loop(step.then_steps, inside_loop, function_name, smells)
            _check_instance_in_loop(step.else_steps, inside_loop, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_instance_in_loop(step.body_steps, True, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_instance_in_loop(step.body_steps, inside_loop, function_name, smells)


# -- Rule: getchildren-in-loop --

def _check_getchildren_in_loop(
    steps: tuple[ControlFlowStep, ...],
    inside_loop: bool,
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ActionFlowStep) and inside_loop:
            if _GETCHILDREN_RE.search(step.label):
                smells.append(Smell(
                    rule="getchildren-in-loop",
                    severity=SmellSeverity.WARNING,
                    message=f":GetChildren() inside loop in function '{function_name}': "
                            f"cache the result outside the loop",
                    function_name=function_name,
                ))
        elif isinstance(step, IfFlowStep):
            _check_getchildren_in_loop(step.then_steps, inside_loop, function_name, smells)
            _check_getchildren_in_loop(step.else_steps, inside_loop, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_getchildren_in_loop(step.body_steps, True, function_name, smells)
        elif isinstance(step, ClosureFlowStep):
            _check_getchildren_in_loop(step.body_steps, inside_loop, function_name, smells)


# -- Rule: unprotected-remote --

def _check_unprotected_remote(
    steps: tuple[ControlFlowStep, ...],
    function_name: str,
    smells: list[Smell],
) -> None:
    for step in steps:
        if isinstance(step, ActionFlowStep):
            if _REMOTE_CALL_RE.search(step.label):
                smells.append(Smell(
                    rule="unprotected-remote",
                    severity=SmellSeverity.ERROR,
                    message=f"Remote call in function '{function_name}': "
                            f"ensure server validates all parameters — {step.label.strip()[:60]}",
                    function_name=function_name,
                ))
        elif isinstance(step, ClosureFlowStep):
            if 'OnServerEvent' in step.call_label or 'OnServerInvoke' in step.call_label:
                if not _body_has_type_check(step.body_steps):
                    smells.append(Smell(
                        rule="unprotected-remote",
                        severity=SmellSeverity.ERROR,
                        message=f"Remote handler in function '{function_name}' has no type validation — "
                                f"exploiters can send any data",
                        function_name=function_name,
                    ))
            _check_unprotected_remote(step.body_steps, function_name, smells)
        elif isinstance(step, IfFlowStep):
            _check_unprotected_remote(step.then_steps, function_name, smells)
            _check_unprotected_remote(step.else_steps, function_name, smells)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            _check_unprotected_remote(step.body_steps, function_name, smells)


def _body_has_type_check(steps: tuple[ControlFlowStep, ...]) -> bool:
    for step in steps:
        if isinstance(step, ActionFlowStep):
            if 'type(' in step.label or 'typeof(' in step.label:
                return True
        elif isinstance(step, IfFlowStep):
            if 'type(' in step.condition or 'typeof(' in step.condition:
                return True
            if _body_has_type_check(step.then_steps) or _body_has_type_check(step.else_steps):
                return True
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            if _body_has_type_check(step.body_steps):
                return True
        elif isinstance(step, ClosureFlowStep):
            if _body_has_type_check(step.body_steps):
                return True
    return False


# -- Rule: connect-leak --

def _check_connect_leak(
    function: FunctionControlFlow,
    smells: list[Smell],
) -> None:
    all_labels = _collect_all_labels(function.steps)
    has_connect = any(':Connect(' in label for label in all_labels)
    if not has_connect:
        return
    has_cleanup = any(
        any(marker in label for marker in _CLEANUP_MARKERS)
        for label in all_labels
    )
    if not has_cleanup:
        smells.append(Smell(
            rule="connect-leak",
            severity=SmellSeverity.WARNING,
            message=f":Connect() in function '{function.name}' without cleanup — "
                    f"use Maid/Janitor/Trove to prevent memory leaks",
            function_name=function.name,
        ))


def _collect_all_labels(steps: tuple[ControlFlowStep, ...]) -> list[str]:
    labels: list[str] = []
    for step in steps:
        if isinstance(step, ActionFlowStep):
            labels.append(step.label)
        elif isinstance(step, IfFlowStep):
            labels.extend(_collect_all_labels(step.then_steps))
            labels.extend(_collect_all_labels(step.else_steps))
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            labels.extend(_collect_all_labels(step.body_steps))
        elif isinstance(step, ClosureFlowStep):
            labels.append(step.call_label)
            labels.extend(_collect_all_labels(step.body_steps))
    return labels


def _count_total_steps(steps: tuple[ControlFlowStep, ...]) -> int:
    count = 0
    for step in steps:
        count += 1
        if isinstance(step, IfFlowStep):
            count += _count_total_steps(step.then_steps)
            count += _count_total_steps(step.else_steps)
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            count += _count_total_steps(step.body_steps)
        elif isinstance(step, ClosureFlowStep):
            count += _count_total_steps(step.body_steps)
    return count


def _is_terminator(label: str) -> bool:
    first = label.split()[0].split("(")[0] if label.strip() else ""
    return first in ("return", "break", "continue")


def _action_label(step: ControlFlowStep) -> str | None:
    if isinstance(step, ActionFlowStep):
        return step.label.strip()[:60]
    return None


def _body_has_exit(steps: tuple[ControlFlowStep, ...]) -> bool:
    for step in steps:
        if isinstance(step, ActionFlowStep):
            stripped = step.label.strip()
            if stripped:
                first = stripped.split()[0].split("(")[0]
                if first in ("break", "return"):
                    return True
        elif isinstance(step, IfFlowStep):
            if _body_has_exit(step.then_steps) or _body_has_exit(step.else_steps):
                return True
        elif isinstance(step, (WhileFlowStep, ForInFlowStep, NumericForFlowStep, RepeatUntilFlowStep)):
            if _body_has_exit(step.body_steps):
                return True
        elif isinstance(step, ClosureFlowStep):
            if _body_has_exit(step.body_steps):
                return True
    return False
