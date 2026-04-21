"""Domain model for structured control flow diagrams."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControlFlowStep:
    """Base type for a structured control flow step."""


@dataclass(frozen=True, slots=True)
class ActionFlowStep(ControlFlowStep):
    label: str


@dataclass(frozen=True, slots=True)
class IfFlowStep(ControlFlowStep):
    condition: str
    then_steps: tuple[ControlFlowStep, ...]
    else_steps: tuple[ControlFlowStep, ...]


@dataclass(frozen=True, slots=True)
class WhileFlowStep(ControlFlowStep):
    condition: str
    body_steps: tuple[ControlFlowStep, ...]


@dataclass(frozen=True, slots=True)
class ForInFlowStep(ControlFlowStep):
    header: str
    body_steps: tuple[ControlFlowStep, ...]


@dataclass(frozen=True, slots=True)
class NumericForFlowStep(ControlFlowStep):
    header: str
    body_steps: tuple[ControlFlowStep, ...]


@dataclass(frozen=True, slots=True)
class RepeatUntilFlowStep(ControlFlowStep):
    condition: str
    body_steps: tuple[ControlFlowStep, ...]


@dataclass(frozen=True, slots=True)
class FunctionControlFlow:
    name: str
    signature: str
    container: str | None
    steps: tuple[ControlFlowStep, ...]

    @property
    def qualified_name(self) -> str:
        if self.container:
            return f"{self.container}.{self.name}"
        return self.name


@dataclass(frozen=True, slots=True)
class ControlFlowDiagram:
    source_location: str
    functions: tuple[FunctionControlFlow, ...]
