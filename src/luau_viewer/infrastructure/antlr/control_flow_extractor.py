"""Extract structured control flow from Luau source through ANTLR."""

from __future__ import annotations

import re
from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream
from antlr4.Token import Token

from luau_viewer.domain.control_flow import (
    ActionFlowStep,
    ControlFlowDiagram,
    ControlFlowStep,
    ForInFlowStep,
    FunctionControlFlow,
    IfFlowStep,
    NumericForFlowStep,
    RepeatUntilFlowStep,
    WhileFlowStep,
)
from luau_viewer.domain.model import SourceUnit
from luau_viewer.domain.ports import ControlFlowExtractor
from luau_viewer.infrastructure.antlr.runtime import (
    load_generated_types,
    parse_code_block_text,
    parse_source_text,
    parse_statement_text,
)


@dataclass(frozen=True, slots=True)
class _ExtractorContext:
    token_stream: object

    def text(self, ctx) -> str:
        if ctx is None:
            return ""
        return ctx.start.getInputStream().getText(
            ctx.start.start, ctx.stop.stop
        )

    def compact(self, ctx, *, limit: int = 96) -> str:
        text = re.sub(r"\s+", " ", self.text(ctx)).strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1]}..."


@dataclass(frozen=True, slots=True)
class _FunctionSlice:
    name: str
    signature: str
    container: str | None
    body_text: str


_MAX_STRUCTURED_PARSE_CHARS = 1400
_MAX_STRUCTURED_PARSE_TOKENS = 220
_MAX_STRUCTURED_PARSE_LINES = 24
_SUMMARY_LABEL_LIMIT = 96


class AntlrLuauControlFlowExtractor(ControlFlowExtractor):
    def __init__(self) -> None:
        self._generated = load_generated_types()
        self._lexer_type = self._generated.lexer_type

    def extract(self, source_unit: SourceUnit) -> ControlFlowDiagram:
        try:
            function_slices = _scan_function_slices(source_unit.content, self._generated)
            functions = tuple(
                self._extract_function_slice(function_slice) for function_slice in function_slices
            )
            return ControlFlowDiagram(
                source_location=source_unit.location,
                functions=functions,
            )
        except Exception:
            return self._extract_via_full_parse(source_unit)

    def _extract_function_slice(self, function_slice: _FunctionSlice) -> FunctionControlFlow:
        quick_steps = _extract_lightweight_steps(
            function_slice.body_text,
            self._generated,
            self._generated.visitor_type,
            self._lexer_type,
        )
        if quick_steps is not None:
            return FunctionControlFlow(
                name=function_slice.name,
                signature=function_slice.signature,
                container=function_slice.container,
                steps=quick_steps,
            )

        parse_result = parse_code_block_text(function_slice.body_text, self._generated)
        visitor = _build_control_flow_visitor(
            self._generated.visitor_type,
            _ExtractorContext(token_stream=parse_result.token_stream),
        )()
        return FunctionControlFlow(
            name=function_slice.name,
            signature=function_slice.signature,
            container=function_slice.container,
            steps=visitor._extract_block(parse_result.tree),
        )

    def _extract_via_full_parse(self, source_unit: SourceUnit) -> ControlFlowDiagram:
        parse_result = parse_source_text(source_unit.content, self._generated)
        visitor = _build_control_flow_visitor(
            self._generated.visitor_type,
            _ExtractorContext(token_stream=parse_result.token_stream),
        )()
        visitor.visit(parse_result.tree)
        return ControlFlowDiagram(
            source_location=source_unit.location,
            functions=tuple(visitor.functions),
        )


def _scan_function_slices(
    source_text: str,
    generated: object,
) -> tuple[_FunctionSlice, ...]:
    lexer = generated.lexer_type(InputStream(source_text))
    token_stream = CommonTokenStream(lexer)
    token_stream.fill()
    tokens = tuple(
        token
        for token in token_stream.tokens
        if token.type != Token.EOF and token.channel == Token.DEFAULT_CHANNEL
    )
    lexer_type = generated.lexer_type

    functions: list[_FunctionSlice] = []
    index = 0

    while index < len(tokens):
        token = tokens[index]

        if token.type == lexer_type.FUNCTION:
            is_local = (
                index > 0
                and tokens[index - 1].type == lexer_type.LOCAL
                and tokens[index - 1].line == token.line
            )
            function_slice, next_index = _try_scan_function_slice(
                source_text,
                tokens,
                index,
                is_local=is_local,
                lexer_type=lexer_type,
            )
            if function_slice is not None:
                functions.append(function_slice)
                index = next_index
                continue

        index += 1

    return tuple(functions)


def _try_scan_function_slice(
    source_text: str,
    tokens: tuple[object, ...],
    func_index: int,
    *,
    is_local: bool,
    lexer_type: object,
) -> tuple[_FunctionSlice | None, int]:
    name, name_end_index = _extract_function_name(tokens, func_index + 1, lexer_type)
    if name is None:
        return None, func_index + 1

    paren_open = _find_open_paren(tokens, name_end_index, lexer_type)
    if paren_open is None:
        return None, func_index + 1

    paren_close = _find_matching_paren(tokens, paren_open, lexer_type)
    if paren_close is None:
        return None, func_index + 1

    body_close_index = _find_matching_end(tokens, paren_close, lexer_type)
    if body_close_index is None:
        return None, func_index + 1

    body_start_index = _skip_type_annotation(tokens, paren_close + 1, lexer_type)

    start_token = tokens[func_index - 1] if is_local else tokens[func_index]
    signature_text = source_text[start_token.start : tokens[paren_close].stop + 1]
    body_text = source_text[
        tokens[body_start_index].start : tokens[body_close_index].start
    ]

    container = _extract_container_from_name(name)

    return (
        _FunctionSlice(
            name=name,
            signature=_compact_source_text(signature_text),
            container=container,
            body_text=body_text,
        ),
        body_close_index + 1,
    )


def _extract_container_from_name(name: str) -> str | None:
    if "." in name:
        parts = name.rsplit(".", 1)
        return parts[0]
    if ":" in name:
        parts = name.rsplit(":", 1)
        return parts[0]
    return None


def _extract_function_name(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> tuple[str | None, int]:
    index = start_index
    parts: list[str] = []

    while index < len(tokens):
        token = tokens[index]
        if token.type == lexer_type.NAME:
            if not parts:
                parts.append(token.text)
            else:
                return None, index
            index += 1
            continue
        if token.text == "." and parts:
            if index + 1 < len(tokens) and tokens[index + 1].type == lexer_type.NAME:
                parts.append(".")
                parts.append(tokens[index + 1].text)
                index += 2
                continue
            return "".join(parts), index
        if token.text == ":" and parts:
            if index + 1 < len(tokens) and tokens[index + 1].type == lexer_type.NAME:
                parts.append(":")
                parts.append(tokens[index + 1].text)
                index += 2
                continue
            return "".join(parts), index
        if token.type == lexer_type.LPAREN:
            return "".join(parts) if parts else None, index
        return None, index

    return "".join(parts) if parts else None, index


def _find_open_paren(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> int | None:
    index = start_index
    while index < len(tokens):
        token = tokens[index]
        if token.type == lexer_type.LPAREN:
            return index
        if token.type in {lexer_type.END, lexer_type.LBRACE, lexer_type.RBRACE}:
            return None
        index += 1
    return None


def _find_matching_paren(
    tokens: tuple[object, ...],
    open_index: int,
    lexer_type: object,
) -> int | None:
    depth = 1
    index = open_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token.type == lexer_type.LPAREN:
            depth += 1
        elif token.type == lexer_type.RPAREN:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _find_matching_end(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> int | None:
    depth = 1
    index = start_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token.type in {
            lexer_type.DO,
            lexer_type.THEN,
            lexer_type.FUNCTION,
        }:
            depth += 1
        elif token.type == lexer_type.ELSEIF:
            depth -= 1
        elif token.type == lexer_type.END:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _skip_type_annotation(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> int:
    """Skip past a return type annotation (``: Type``) after ``)``."""
    if start_index >= len(tokens):
        return start_index
    if tokens[start_index].type != lexer_type.COLON:
        return start_index

    index = start_index + 1
    depth = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type in {lexer_type.LPAREN, lexer_type.LBRACE}:
            depth += 1
        elif token.type in {lexer_type.RPAREN, lexer_type.RBRACE}:
            depth -= 1
        elif depth == 0 and token.type in {
            lexer_type.DO,
            lexer_type.THEN,
            lexer_type.FUNCTION,
            lexer_type.END,
            lexer_type.IF,
            lexer_type.WHILE,
            lexer_type.FOR,
            lexer_type.REPEAT,
            lexer_type.LOCAL,
            lexer_type.RETURN,
            lexer_type.ELSE,
            lexer_type.ELSEIF,
        }:
            return index
        index += 1
    return start_index


def _compact_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_lightweight_steps(
    body_text: str,
    generated: object,
    visitor_type: type,
    lexer_type: object,
) -> tuple[ControlFlowStep, ...] | None:
    statement_spans = _split_top_level_statement_spans(body_text, lexer_type)
    if statement_spans is None:
        return None

    steps: list[ControlFlowStep] = []
    structured_starters = _structured_token_types(lexer_type)

    for statement_text, tokens, base_offset in statement_spans:
        if not tokens:
            continue

        if tokens[0].type == lexer_type.DO:
            # Inline do-block: extract body between DO and matching END
            end_index = _find_matching_end(tokens, 0, lexer_type)
            if end_index is not None:
                inner_text = _slice_token_text(
                    statement_text, tokens, base_offset, 1, end_index - 1,
                )
                inner_steps = _summarize_code_block_steps(inner_text, lexer_type)
                steps.extend(inner_steps)
                continue

        if tokens[0].type in structured_starters:
            if _should_summarize_structured_statement(statement_text, tokens):
                steps.append(
                    _build_summarized_structured_step(
                        statement_text,
                        tokens,
                        base_offset,
                        lexer_type,
                    )
                )
                continue
            try:
                parse_result = parse_statement_text(statement_text, generated)
                visitor = _build_control_flow_visitor(
                    visitor_type,
                    _ExtractorContext(token_stream=parse_result.token_stream),
                )()
                extracted = visitor._extract_stat(parse_result.tree)
                if extracted is not None:
                    steps.append(extracted)
            except Exception:
                steps.append(ActionFlowStep(_compact_source_text(statement_text.strip())))
            continue

        steps.append(ActionFlowStep(_compact_source_text(statement_text.strip().removesuffix(";"))))

    return tuple(steps)


def _should_summarize_structured_statement(
    statement_text: str,
    tokens: tuple[object, ...],
) -> bool:
    return (
        len(statement_text) > _MAX_STRUCTURED_PARSE_CHARS
        or len(tokens) > _MAX_STRUCTURED_PARSE_TOKENS
        or statement_text.count("\n") > _MAX_STRUCTURED_PARSE_LINES
    )


def _summarize_code_block_steps(
    body_text: str,
    lexer_type: object,
) -> tuple[ControlFlowStep, ...]:
    statement_spans = _split_top_level_statement_spans(body_text, lexer_type)
    if statement_spans is None:
        label = _compact_label_text(body_text.strip())
        return (ActionFlowStep(label),) if label else ()

    steps: list[ControlFlowStep] = []
    structured_starters = _structured_token_types(lexer_type)

    for statement_text, tokens, base_offset in statement_spans:
        if not tokens:
            continue
        if tokens[0].type in structured_starters:
            steps.append(
                _build_summarized_structured_step(
                    statement_text,
                    tokens,
                    base_offset,
                    lexer_type,
                )
            )
            continue
        label = _compact_label_text(statement_text.strip().removesuffix(";"))
        if label:
            steps.append(ActionFlowStep(label))

    return tuple(steps)


def _build_summarized_structured_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    if not tokens:
        return ActionFlowStep(_compact_label_text(statement_text))

    starter = tokens[0]
    if starter.type == lexer_type.IF:
        return _build_summarized_if_step(statement_text, tokens, base_offset, lexer_type)
    if starter.type == lexer_type.WHILE:
        return _build_summarized_while_step(statement_text, tokens, base_offset, lexer_type)
    if starter.type == lexer_type.FOR:
        return _build_summarized_for_step(statement_text, tokens, base_offset, lexer_type)
    if starter.type == lexer_type.REPEAT:
        return _build_summarized_repeat_until_step(statement_text, tokens, base_offset, lexer_type)
    return ActionFlowStep(_summarize_structured_header(statement_text, tokens, base_offset, lexer_type))


def _build_summarized_if_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    then_index = None
    for i in range(1, len(tokens)):
        if tokens[i].type == lexer_type.THEN:
            then_index = i
            break
    if then_index is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip()))

    # Collect boundary markers (ELSEIF, ELSE, END) with corrected depth tracking
    depth = 0
    prev_was_elseif = False
    boundaries: list[tuple[int, int]] = []  # (token_index, type)
    end_index = None

    for i in range(then_index + 1, len(tokens)):
        token = tokens[i]
        if token.type == lexer_type.ELSEIF:
            depth -= 1
            prev_was_elseif = True
            if depth == 0:
                boundaries.append((i, token.type))
        elif token.type in {lexer_type.DO, lexer_type.THEN, lexer_type.FUNCTION}:
            if token.type == lexer_type.THEN and prev_was_elseif:
                prev_was_elseif = False
            else:
                depth += 1
                prev_was_elseif = False
        elif token.type == lexer_type.END:
            depth -= 1
            prev_was_elseif = False
            if depth == -1:
                end_index = i
                break
        elif token.type == lexer_type.ELSE:
            prev_was_elseif = False
            if depth == 0:
                boundaries.append((i, token.type))
        else:
            prev_was_elseif = False

    if end_index is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip()))

    condition = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, then_index - 1)
    )

    # Split into segments between boundaries
    segments: list[tuple[int, int]] = []  # (start_token_index, end_token_index) inclusive
    prev_boundary = then_index
    for boundary_index, _ in boundaries:
        segments.append((prev_boundary + 1, boundary_index - 1))
        prev_boundary = boundary_index
    segments.append((prev_boundary + 1 if boundaries else then_index + 1, end_index - 1))

    # First segment is the then-body
    then_start, then_end = segments[0]
    then_body = _slice_token_text(statement_text, tokens, base_offset, then_start, then_end)
    then_steps = _summarize_code_block_steps(then_body, lexer_type) if then_body.strip() else ()

    # Build elseif chain from inside out
    inner_else: tuple[ControlFlowStep, ...] = ()

    # Process boundaries in reverse
    for seg_idx in range(len(segments) - 1, 0, -1):
        boundary_index, boundary_type = boundaries[seg_idx - 1]
        seg_start, seg_end = segments[seg_idx]
        seg_body = _slice_token_text(statement_text, tokens, base_offset, seg_start, seg_end)

        if boundary_type == lexer_type.ELSEIF:
            elseif_condition = _compact_label_text(
                _slice_token_text(statement_text, tokens, base_offset, boundary_index + 1, seg_start - 1)
            )
            # Find THEN for this elseif to split condition from body
            elseif_then = None
            for ti in range(boundary_index + 1, seg_start):
                if tokens[ti].type == lexer_type.THEN:
                    elseif_then = ti
                    break
            if elseif_then is not None:
                elseif_condition = _compact_label_text(
                    _slice_token_text(statement_text, tokens, base_offset, boundary_index + 1, elseif_then - 1)
                )
                seg_body = _slice_token_text(statement_text, tokens, base_offset, elseif_then + 1, seg_end)

            elseif_steps = _summarize_code_block_steps(seg_body, lexer_type) if seg_body.strip() else ()
            inner_else = (
                IfFlowStep(
                    condition=elseif_condition or "condition",
                    then_steps=elseif_steps,
                    else_steps=inner_else,
                ),
            )
        else:  # ELSE
            inner_else = _summarize_code_block_steps(seg_body, lexer_type) if seg_body.strip() else ()

    return IfFlowStep(
        condition=condition or "condition",
        then_steps=then_steps,
        else_steps=inner_else,
    )


def _build_summarized_while_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    block_range = _find_top_level_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip()))

    open_index, close_index = block_range
    condition = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, open_index - 1)
    )
    return WhileFlowStep(
        condition=condition or "condition",
        body_steps=_summarize_code_block_steps(
            _slice_token_text(statement_text, tokens, base_offset, open_index, close_index),
            lexer_type,
        ),
    )


def _build_summarized_for_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    block_range = _find_top_level_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip()))

    open_index, close_index = block_range
    header = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, open_index - 1)
    )
    body_steps = _summarize_code_block_steps(
        _slice_token_text(statement_text, tokens, base_offset, open_index, close_index),
        lexer_type,
    )

    if _is_numeric_for(tokens, lexer_type):
        return NumericForFlowStep(
            header=header or "i = start, finish",
            body_steps=body_steps,
        )
    return ForInFlowStep(
        header=header or "item in collection",
        body_steps=body_steps,
    )


def _is_numeric_for(tokens: tuple[object, ...], lexer_type: object) -> bool:
    for token in tokens:
        if token.type == lexer_type.ASSIGN:
            return True
        if token.type == lexer_type.IN:
            return False
        if token.type == lexer_type.DO:
            break
    return False


def _build_summarized_repeat_until_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    until_index = _find_matching_until(tokens, 1, lexer_type)
    if until_index is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip()))

    condition = ""
    if until_index + 1 < len(tokens):
        condition = _compact_label_text(
            _slice_token_text(
                statement_text,
                tokens,
                base_offset,
                until_index + 1,
                len(tokens) - 1,
            ).removesuffix(";")
        )

    body_text = _slice_token_text(statement_text, tokens, base_offset, 1, until_index - 1)
    return RepeatUntilFlowStep(
        condition=condition or "condition",
        body_steps=_summarize_code_block_steps(
            body_text,
            lexer_type,
        ) if body_text.strip() else (),
    )


def _summarize_structured_header(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> str:
    block_range = _find_top_level_block(tokens, 1, lexer_type)
    if block_range is None:
        return _compact_label_text(statement_text.strip())
    open_index, _ = block_range
    return _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 0, open_index - 1)
    )


def _find_top_level_block(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> tuple[int, int] | None:
    for index in range(start_index, len(tokens)):
        token = tokens[index]
        if token.type in {lexer_type.DO, lexer_type.THEN}:
            close_index = _find_matching_end(tokens, index, lexer_type)
            if close_index is not None:
                return index, close_index
            return None
    return None


def _find_matching_until(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> int | None:
    depth = 1
    for index in range(start_index, len(tokens)):
        token = tokens[index]
        if token.type == lexer_type.REPEAT:
            depth += 1
        elif token.type == lexer_type.UNTIL:
            depth -= 1
            if depth == 0:
                return index
    return None


def _slice_token_text(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    start_index: int,
    end_index: int,
) -> str:
    if start_index < 0 or end_index < start_index or end_index >= len(tokens):
        return ""
    start = tokens[start_index].start - base_offset
    end = tokens[end_index].stop + 1 - base_offset
    return statement_text[start:end]


def _compact_label_text(text: str, *, limit: int = _SUMMARY_LABEL_LIMIT) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}..."


def _split_top_level_statement_spans(
    body_text: str,
    lexer_type: object,
) -> tuple[tuple[str, tuple[object, ...], int], ...] | None:
    tokens = _lex_default_tokens(body_text, lexer_type)
    if not tokens:
        return None

    spans: list[tuple[str, tuple[object, ...], int]] = []
    depth = 0
    paren_depth = 0
    statement_start_index: int | None = None
    prev_was_elseif = False

    for index in range(0, len(tokens)):
        token = tokens[index]
        if statement_start_index is None:
            statement_start_index = index

        if token.type == lexer_type.LPAREN:
            paren_depth += 1
        elif token.type == lexer_type.RPAREN:
            paren_depth = max(paren_depth - 1, 0)
        elif token.type == lexer_type.ELSEIF:
            depth -= 1
            prev_was_elseif = True
        elif token.type in {lexer_type.DO, lexer_type.THEN, lexer_type.FUNCTION, lexer_type.REPEAT}:
            if token.type == lexer_type.THEN and prev_was_elseif:
                prev_was_elseif = False
            else:
                depth += 1
                prev_was_elseif = False
        elif token.type == lexer_type.END:
            depth -= 1
            prev_was_elseif = False
        elif token.type == lexer_type.UNTIL:
            if depth > 0:
                depth -= 1
            prev_was_elseif = False
        else:
            prev_was_elseif = False

        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        at_statement_end = False

        if token.text == ";" and depth == 0 and paren_depth == 0:
            at_statement_end = True
        elif (
            next_token is not None
            and depth == 0
            and paren_depth == 0
            and next_token.type not in {
                lexer_type.ELSE,
                lexer_type.ELSEIF,
                lexer_type.UNTIL,
            }
            and next_token.line > token.line
        ):
            at_statement_end = True
        elif next_token is None:
            at_statement_end = True

        if at_statement_end and statement_start_index is not None:
            statement_tokens = tokens[statement_start_index : index + 1]
            statement_text = body_text[
                statement_tokens[0].start : statement_tokens[-1].stop + 1
            ]
            if statement_text.strip():
                spans.append((statement_text, statement_tokens, statement_tokens[0].start))
            statement_start_index = None

    return tuple(spans)


def _structured_token_types(lexer_type: object) -> set[int]:
    return {
        token_type
        for token_type in {
            getattr(lexer_type, "IF", None),
            getattr(lexer_type, "WHILE", None),
            getattr(lexer_type, "FOR", None),
            getattr(lexer_type, "REPEAT", None),
        }
        if token_type is not None
    }


def _lex_default_tokens(source_text: str, lexer_type: object) -> tuple[object, ...]:
    lexer = lexer_type(InputStream(source_text))
    token_stream = CommonTokenStream(lexer)
    token_stream.fill()
    return tuple(
        token
        for token in token_stream.tokens
        if token.type != Token.EOF and token.channel == Token.DEFAULT_CHANNEL
    )


def _build_control_flow_visitor(visitor_base: type, context: _ExtractorContext) -> type:
    class LuauControlFlowVisitor(visitor_base):
        def __init__(self) -> None:
            super().__init__()
            self.functions: list[FunctionControlFlow] = []
            self._containers: list[str] = []

        def visitFunctionStat(self, ctx):
            name = ctx.funcname().getText()
            if ctx.funcbody() is None:
                return None
            signature = context.compact(ctx.funcbody())
            block = ctx.funcbody().block()
            container_from_name = _extract_container_from_name(name)
            container = container_from_name or (
                ".".join(self._containers) if self._containers else None
            )
            self.functions.append(
                FunctionControlFlow(
                    name=name,
                    signature=f"function {name}{signature}",
                    container=container,
                    steps=self._extract_block(block),
                )
            )
            return None

        def visitLocalFunctionStat(self, ctx):
            name = ctx.NAME().getText()
            if ctx.funcbody() is None:
                return None
            signature = context.compact(ctx.funcbody())
            block = ctx.funcbody().block()
            self.functions.append(
                FunctionControlFlow(
                    name=name,
                    signature=f"local function {name}{signature}",
                    container=None,
                    steps=self._extract_block(block),
                )
            )
            return None

        def _extract_block(self, block_ctx) -> tuple[ControlFlowStep, ...]:
            if block_ctx is None:
                return ()
            steps: list[ControlFlowStep] = []
            for stat_ctx in block_ctx.stat():
                if stat_ctx is None:
                    continue
                if stat_ctx.doStat() is not None:
                    inner = self._extract_block(stat_ctx.doStat().block())
                    steps.extend(inner)
                    continue
                extracted = self._extract_stat(stat_ctx)
                if extracted is not None:
                    steps.append(extracted)
            return tuple(steps)

        def _extract_stat(self, stat_ctx) -> ControlFlowStep | None:
            if stat_ctx.ifStat() is not None:
                return self._extract_if_stat(stat_ctx.ifStat())
            if stat_ctx.whileStat() is not None:
                return self._extract_while_stat(stat_ctx.whileStat())
            if stat_ctx.forNumericalStat() is not None:
                return self._extract_for_numerical_stat(stat_ctx.forNumericalStat())
            if stat_ctx.forGenericStat() is not None:
                return self._extract_for_generic_stat(stat_ctx.forGenericStat())
            if stat_ctx.repeatStat() is not None:
                return self._extract_repeat_stat(stat_ctx.repeatStat())
            if stat_ctx.breakStat() is not None:
                return ActionFlowStep("break")
            if stat_ctx.continueStat() is not None:
                return ActionFlowStep("continue")
            if stat_ctx.returnStat() is not None:
                return ActionFlowStep(context.compact(stat_ctx.returnStat()))
            if stat_ctx.localStat() is not None:
                return ActionFlowStep(context.compact(stat_ctx.localStat()))
            if stat_ctx.localFunctionStat() is not None:
                return ActionFlowStep(context.compact(stat_ctx.localFunctionStat()))
            if stat_ctx.assignmentStat() is not None:
                return ActionFlowStep(context.compact(stat_ctx.assignmentStat()))
            if stat_ctx.compoundAssignStat() is not None:
                return ActionFlowStep(context.compact(stat_ctx.compoundAssignStat()))
            if stat_ctx.callStat() is not None:
                return ActionFlowStep(context.compact(stat_ctx.callStat()))
            if stat_ctx.doStat() is not None:
                return self._extract_block_as_steps(stat_ctx.doStat().block())
            if stat_ctx.functionStat() is not None:
                self.visitFunctionStat(stat_ctx.functionStat())
                return None
            return ActionFlowStep(context.compact(stat_ctx))

        def _extract_block_as_steps(self, block_ctx) -> ControlFlowStep | None:
            steps = self._extract_block(block_ctx)
            if not steps:
                return None
            if len(steps) == 1:
                return steps[0]
            return None

        def _extract_if_stat(self, if_ctx) -> IfFlowStep:
            condition = context.compact(if_ctx.exp())
            then_steps = self._extract_block(if_ctx.block())

            elseif_clauses = if_ctx.elseifClause()
            else_clause = if_ctx.elseClause()

            # Build elseif chain from inside out
            inner_else: tuple[ControlFlowStep, ...] = ()
            if else_clause is not None:
                inner_else = self._extract_block(else_clause.block())

            if elseif_clauses:
                for elseif_ctx in reversed(elseif_clauses):
                    inner_else = (
                        IfFlowStep(
                            condition=context.compact(elseif_ctx.exp()),
                            then_steps=self._extract_block(elseif_ctx.block()),
                            else_steps=inner_else,
                        ),
                    )

            return IfFlowStep(
                condition=condition,
                then_steps=then_steps,
                else_steps=inner_else,
            )

        def _extract_while_stat(self, while_ctx) -> WhileFlowStep:
            return WhileFlowStep(
                condition=context.compact(while_ctx.exp()),
                body_steps=self._extract_block(while_ctx.block()),
            )

        def _extract_for_numerical_stat(self, for_ctx) -> NumericForFlowStep:
            binding = for_ctx.binding()
            binding_name = binding.NAME().getText() if binding else "i"
            exps = for_ctx.exp()
            if len(exps) >= 3:
                header = f"{binding_name} = {context.compact(exps[0])}, {context.compact(exps[1])}, {context.compact(exps[2])}"
            elif len(exps) >= 2:
                header = f"{binding_name} = {context.compact(exps[0])}, {context.compact(exps[1])}"
            else:
                header = f"{binding_name} = ..."
            return NumericForFlowStep(
                header=header,
                body_steps=self._extract_block(for_ctx.block()),
            )

        def _extract_for_generic_stat(self, for_ctx) -> ForInFlowStep:
            header = context.compact(for_ctx.bindingList()) + " in " + context.compact(for_ctx.explist())
            return ForInFlowStep(
                header=header,
                body_steps=self._extract_block(for_ctx.block()),
            )

        def _extract_repeat_stat(self, repeat_ctx) -> RepeatUntilFlowStep:
            return RepeatUntilFlowStep(
                condition=context.compact(repeat_ctx.exp()),
                body_steps=self._extract_block(repeat_ctx.block()),
            )

    return LuauControlFlowVisitor
