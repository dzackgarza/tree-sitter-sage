r"""The SagePython compiler: tree-sitter-sage recognition and lowering.

Sage-free by construction — importable in any Python environment.
``lower(source, wrap_numbers=True, previous=None, extensions=())``
returns :class:`LoweredSource` (ordinary Python plus a
:class:`SourceMap` translating positions in both directions), with
incremental parse reuse via ``previous``.  The core lowers exactly the
Sage language delta; dialect notation ships as opt-in extension rule
tables (see :mod:`sagepython.research` for the set-builder notation).
CPython compiles the output as the semantic authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field, replace
from collections.abc import Mapping, Sequence
from typing import Callable

import tree_sitter_sage
from tree_sitter import Language, Node, Parser

_LANGUAGE = Language(tree_sitter_sage.language())
_PARSER = Parser(_LANGUAGE)

_HUGE_INTEGER_DIGITS = 4300
_RAW_SUFFIX = re.compile(r"[rRlLjJ]+$")


@dataclass(frozen=True)
class _Context:
    source: bytes
    rules: "Mapping[str, LoweringRule]"
    wrap_numbers: bool = True
    in_case_pattern: bool = False

    def text(self, node: Node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8")


def _segments(node: Node, context: _Context) -> list["Segment"]:
    """Lower ``node`` into source-mapped segments.

    Nodes with a lowering rule become one rebuilt segment covering the
    construct; other nodes interleave verbatim gaps with their children's
    segments.  Parse-error regions are never lowered: rules firing on
    recovered fragments can assemble accidentally-compilable garbage, so
    the author's text passes through verbatim and CPython reports the
    real mistake at its real position (sage#38949's failure class).
    """
    if node.is_error or node.is_missing:
        return [
            Segment(
                text=context.text(node),
                original_start=node.start_byte,
                original_end=node.end_byte,
                exact=True,
            )
        ]
    if node.type == "case_pattern" and not context.in_case_pattern:
        context = replace(context, in_case_pattern=True)
    rule = context.rules.get(node.type)
    if rule is not None:
        lowered = rule(node, context)
        if lowered is not None:
            return [
                Segment(
                    text=lowered,
                    original_start=node.start_byte,
                    original_end=node.end_byte,
                    exact=False,
                )
            ]
    segments: list[Segment] = []
    cursor = node.start_byte
    for child in node.children:
        if cursor < child.start_byte:
            segments.append(
                Segment(
                    text=context.source[cursor : child.start_byte].decode("utf-8"),
                    original_start=cursor,
                    original_end=child.start_byte,
                    exact=True,
                )
            )
        segments.extend(_segments(child, context))
        cursor = child.end_byte
    if cursor < node.end_byte:
        segments.append(
            Segment(
                text=context.source[cursor : node.end_byte].decode("utf-8"),
                original_start=cursor,
                original_end=node.end_byte,
                exact=True,
            )
        )
    if not node.children and node.start_byte == node.end_byte:
        return segments
    if not segments:
        segments.append(
            Segment(
                text=context.text(node),
                original_start=node.start_byte,
                original_end=node.end_byte,
                exact=True,
            )
        )
    return segments


@dataclass(frozen=True)
class Segment:
    """One span of generated Python and the original span it came from.

    ``exact`` segments are verbatim copies, so positions map one-to-one;
    rebuilt segments map every inner position to the start of the
    originating construct.
    """

    text: str
    original_start: int
    original_end: int
    exact: bool


@dataclass(frozen=True)
class SourceMap:
    """Maps positions in generated Python back to the Sage source."""

    original: str
    python: str
    segments: tuple[Segment, ...]

    def original_offset(self, generated_offset: int) -> int:
        cursor = 0
        for segment in self.segments:
            end = cursor + len(segment.text.encode("utf-8"))
            if generated_offset < end or segment is self.segments[-1]:
                if segment.exact:
                    return segment.original_start + max(
                        0, min(generated_offset, end) - cursor
                    )
                return segment.original_start
            cursor = end
        return len(self.original.encode("utf-8"))

    def exact_at_generated(self, line: int, column: int) -> bool:
        """Whether a 1-based generated position lies in verbatim source.

        Diagnostics about generated (non-exact) text describe the
        compiler's output, not the author's input; style checkers should
        drop them.
        """
        generated = self.python.encode("utf-8")
        line_starts = [0]
        for index, byte in enumerate(generated):
            if byte == 0x0A:
                line_starts.append(index + 1)
        offset = line_starts[min(line - 1, len(line_starts) - 1)] + column
        cursor = 0
        for segment in self.segments:
            end = cursor + len(segment.text.encode("utf-8"))
            if offset < end or segment is self.segments[-1]:
                return segment.exact
            cursor = end
        return True

    def generated_offset(self, original_offset: int) -> int:
        generated_cursor = 0
        for segment in self.segments:
            width = len(segment.text.encode("utf-8"))
            if original_offset < segment.original_end or segment is self.segments[-1]:
                if segment.exact:
                    inner = max(0, original_offset - segment.original_start)
                    return generated_cursor + min(inner, width)
                return generated_cursor
            generated_cursor += width
        return len(self.python.encode("utf-8"))

    def generated_position(self, line: int, column: int) -> tuple[int, int]:
        """Translate a 1-based original (line, column) to the generated Python."""
        original = self.original.encode("utf-8")
        line_starts = [0]
        for index, byte in enumerate(original):
            if byte == 0x0A:
                line_starts.append(index + 1)
        offset = line_starts[min(line - 1, len(line_starts) - 1)] + column
        generated_offset = self.generated_offset(offset)
        prefix = self.python.encode("utf-8")[:generated_offset]
        generated_line = prefix.count(b"\n") + 1
        last_newline = prefix.rfind(b"\n")
        return generated_line, generated_offset - (last_newline + 1)

    def original_position(self, line: int, column: int) -> tuple[int, int]:
        """Translate a 1-based generated (line, column) to the original."""
        generated = self.python.encode("utf-8")
        line_starts = [0]
        for index, byte in enumerate(generated):
            if byte == 0x0A:
                line_starts.append(index + 1)
        offset = line_starts[min(line - 1, len(line_starts) - 1)] + column
        original_offset = self.original_offset(offset)
        prefix = self.original.encode("utf-8")[:original_offset]
        original_line = prefix.count(b"\n") + 1
        last_newline = prefix.rfind(b"\n")
        original_column = original_offset - (last_newline + 1)
        return original_line, original_column


@dataclass(frozen=True)
class LoweredSource:
    """The compiler's output: ordinary Python plus its source map.

    The parse tree is retained so a subsequent :func:`lower` call can
    reuse it incrementally.  Passing this object as ``previous``
    consumes it: the retained tree is edited in place, so keep only the
    returned object for further edits.
    """

    python: str
    source_map: SourceMap
    _tree: object = dataclass_field(default=None, repr=False, compare=False)
    _wrap_numbers: bool = dataclass_field(default=True, repr=False, compare=False)


def _lower(node: Node, context: _Context) -> str:
    if node.is_error or node.is_missing:
        return context.text(node)
    if node.type == "case_pattern" and not context.in_case_pattern:
        context = replace(context, in_case_pattern=True)
    rule = context.rules.get(node.type)
    if rule is not None:
        lowered = rule(node, context)
        if lowered is not None:
            return lowered
    return _splice(node, context)


def _splice(node: Node, context: _Context) -> str:
    pieces = []
    cursor = node.start_byte
    for child in node.children:
        pieces.append(context.source[cursor : child.start_byte].decode("utf-8"))
        pieces.append(_lower(child, context))
        cursor = child.end_byte
    pieces.append(context.source[cursor : node.end_byte].decode("utf-8"))
    return "".join(pieces)


def _gap(left: Node, right: Node, context: _Context) -> str:
    return context.source[left.end_byte : right.start_byte].decode("utf-8")


# ---------------------------------------------------------------------------
# Numeric literals
# ---------------------------------------------------------------------------

def _integer_stem(text: str) -> str:
    stripped = text.lstrip("0")
    return stripped if stripped else "0"


def _lower_integer(node: Node, context: _Context) -> str | None:
    text = context.text(node)
    if not context.wrap_numbers or context.in_case_pattern:
        return None
    if text[-1] in "jJ":
        return f"ComplexNumber(0, '{text[:-1]}')"
    if text[:2].lower() in {"0x", "0o", "0b"}:
        return f"Integer({text})"
    stem = _integer_stem(text)
    if len(stem) <= _HUGE_INTEGER_DIGITS:
        return f"Integer({stem})"
    return f"Integer('{stem}')"


def _lower_float(node: Node, context: _Context) -> str | None:
    text = context.text(node)
    if not context.wrap_numbers or context.in_case_pattern:
        return None
    if text[-1] in "jJ":
        return f"ComplexNumber(0, '{text[:-1]}')"
    return f"RealNumber('{text}')"


def _lower_raw_literal(node: Node, context: _Context) -> str:
    text = context.text(node)
    suffix = _RAW_SUFFIX.search(text)
    assert suffix is not None, f"raw literal without suffix: {text!r}"
    base = text[: suffix.start()]
    if "j" in suffix.group().lower():
        return base + "J"
    return base


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

_CARET_OPERATORS = {"^": "**", "^^": "^", "^=": "**=", "^^=": "^="}


def _lower_operator_node(node: Node, context: _Context) -> str | None:
    operator = node.child_by_field_name("operator")
    if operator is None or operator.text is None:
        return None
    replacement = _CARET_OPERATORS.get(operator.text.decode())
    if replacement is None:
        return None
    pieces = []
    cursor = node.start_byte
    for child in node.children:
        pieces.append(context.source[cursor : child.start_byte].decode("utf-8"))
        if child.id == operator.id:
            pieces.append(replacement)
        else:
            pieces.append(_lower(child, context))
        cursor = child.end_byte
    pieces.append(context.source[cursor : node.end_byte].decode("utf-8"))
    return "".join(pieces)


def _lower_implicit_product(node: Node, context: _Context) -> str:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    assert left is not None and right is not None
    return (
        _lower(left, context)
        + "*"
        + _gap(left, right, context)
        + _lower(right, context)
    )


# ---------------------------------------------------------------------------
# Generators and symbolic functions
# ---------------------------------------------------------------------------

def _lower_generator_assignment(node: Node, context: _Context) -> str:
    name = node.child_by_field_name("name")
    right = node.child_by_field_name("right")
    assert name is not None and right is not None
    generators = [
        context.text(child)
        for child in node.children_by_field_name("generator")
    ]
    others = [
        context.text(child)
        for child in node.children_by_field_name("other_target")
    ]
    constructor = _lower_constructor(right, generators, context)
    obj = context.text(name)
    targets = "".join(f", {other}" for other in others)
    gens = ", ".join(generators)
    return (
        f"{obj}{targets} = {constructor}; "
        f"({gens},) = {obj}._first_ngens({len(generators)})"
    )


def _lower_constructor(right: Node, generators: list[str], context: _Context) -> str:
    names = "('" + "', '".join(generators) + "',)"
    if right.type == "sage_empty_subscript":
        value = right.child_by_field_name("value")
        assert value is not None
        quoted = "'" + ", ".join(generators) + "'"
        return f"{_lower(value, context)}[{quoted}]"
    if right.type == "call":
        arguments = right.child_by_field_name("arguments")
        assert arguments is not None
        lowered = _lower(right, context)
        has_arguments = any(
            child.is_named for child in arguments.children
        )
        comma = ", " if has_arguments else ""
        assert lowered.endswith(")")
        return f"{lowered[:-1]}{comma}names={names})"
    if right.type == "subscript":
        # `S.<q> = QQ[[]]`: fill an empty innermost bracket with the names.
        subscript = right.child_by_field_name("subscript")
        if subscript is not None and subscript.type == "list" and not any(
            child.is_named for child in subscript.children
        ):
            value = right.child_by_field_name("value")
            assert value is not None
            quoted = "'" + ", ".join(generators) + "'"
            return f"{_lower(value, context)}[[{quoted}]]"
    return _lower(right, context)


def _lower_symbolic_function(node: Node, context: _Context) -> str:
    name = node.child_by_field_name("name")
    body = node.child_by_field_name("body")
    assert name is not None and body is not None
    parameters = ",".join(
        context.text(child)
        for child in node.children_by_field_name("parameter")
    )
    return (
        f'__tmp__=var("{parameters}"); '
        f"{context.text(name)} = "
        f"symbolic_expression({_lower(body, context)}).function({parameters})"
    )


def _lower_generator_access(node: Node, context: _Context) -> str:
    target = node.child_by_field_name("object")
    index = node.child_by_field_name("index")
    assert target is not None and index is not None
    digits = context.text(index)[1:]
    return f"{_lower(target, context)}.gen({int(digits)})"


# ---------------------------------------------------------------------------
# Ellipsis ranges
# ---------------------------------------------------------------------------

def _ellipsis_arguments(elements: list[Node], context: _Context) -> str:
    pieces = []
    for element in elements:
        if element.type == "sage_ellipsis_span":
            start = element.child_by_field_name("start")
            end = element.child_by_field_name("end")
            assert start is not None and end is not None
            pieces.append(
                f"{_lower(start, context)},Ellipsis,{_lower(end, context)}"
            )
        elif element.type == "sage_ellipsis":
            pieces.append("Ellipsis")
        else:
            pieces.append(_lower(element, context))
    return ",".join(pieces)


def _has_ellipsis(elements: list[Node]) -> bool:
    return any(
        element.type in {"sage_ellipsis_span", "sage_ellipsis"}
        for element in elements
    )


def _named_elements(node: Node) -> list[Node]:
    return [child for child in node.children if child.is_named]


def _lower_list(node: Node, context: _Context) -> str | None:
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return f"(ellipsis_range({_ellipsis_arguments(elements, context)}))"
    return None


def _lower_parenthesized(node: Node, context: _Context) -> str | None:
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return f"(ellipsis_iter({_ellipsis_arguments(elements, context)}))"
    return None


def _lower_tuple(node: Node, context: _Context) -> str | None:
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return f"(ellipsis_iter({_ellipsis_arguments(elements, context)}))"
    return None




# ---------------------------------------------------------------------------
# The lowering table and the preparser
# ---------------------------------------------------------------------------

LoweringRule = Callable[[Node, "_Context"], "str | None"]

_LOWERINGS: dict[str, LoweringRule] = {
    "integer": _lower_integer,
    "float": _lower_float,
    "sage_raw_literal": _lower_raw_literal,
    "binary_operator": _lower_operator_node,
    "augmented_assignment": _lower_operator_node,
    "sage_implicit_product": _lower_implicit_product,
    "sage_generator_assignment": _lower_generator_assignment,
    "sage_symbolic_function_assignment": _lower_symbolic_function,
    "sage_generator_access": _lower_generator_access,
    "list": _lower_list,
    "parenthesized_expression": _lower_parenthesized,
    "tuple": _lower_tuple,
}

def _byte_point(encoded: bytes, offset: int) -> tuple[int, int]:
    prefix = encoded[:offset]
    return prefix.count(b"\n"), offset - (prefix.rfind(b"\n") + 1)


def lower(
    source: str,
    wrap_numbers: bool = True,
    previous: LoweredSource | None = None,
    extensions: Sequence["Mapping[str, LoweringRule]"] = (),
) -> LoweredSource:
    r"""Compile SagePython source to ordinary Python plus a source map.

    With ``previous`` (the result of lowering an earlier revision of the
    same document), the parse is incremental: the single contiguous
    change between the revisions is computed as a common prefix/suffix
    delta and applied to the retained tree.  The result is identical to
    a fresh ``lower(source)``; ``previous`` is consumed.
    """
    encoded = source.encode("utf-8")
    rules: dict[str, LoweringRule] = dict(_LOWERINGS)
    for extension in extensions:
        rules.update(extension)
    old_tree = None
    if (
        previous is not None
        and previous._tree is not None
        and previous._wrap_numbers == wrap_numbers
    ):
        old = previous.source_map.original.encode("utf-8")
        prefix = 0
        limit = min(len(old), len(encoded))
        while prefix < limit and old[prefix] == encoded[prefix]:
            prefix += 1
        suffix = 0
        while (
            suffix < limit - prefix
            and old[len(old) - 1 - suffix] == encoded[len(encoded) - 1 - suffix]
        ):
            suffix += 1
        old_end = len(old) - suffix
        new_end = len(encoded) - suffix
        previous._tree.edit(  # type: ignore[attr-defined]
            start_byte=prefix,
            old_end_byte=old_end,
            new_end_byte=new_end,
            start_point=_byte_point(old, prefix),
            old_end_point=_byte_point(old, old_end),
            new_end_point=_byte_point(encoded, new_end),
        )
        old_tree = previous._tree
    if old_tree is not None:
        tree = _PARSER.parse(encoded, old_tree)
    else:
        tree = _PARSER.parse(encoded)
    context = _Context(source=encoded, rules=rules, wrap_numbers=wrap_numbers)
    segments = tuple(_segments(tree.root_node, context))
    python = "".join(segment.text for segment in segments)
    return LoweredSource(
        python=python,
        source_map=SourceMap(original=source, python=python, segments=segments),
        _tree=tree,
        _wrap_numbers=wrap_numbers,
    )


# Public surface for dialect extensions: a rule table maps node types to
# functions (node, context) -> replacement text or None to decline.
Context = _Context
lower_node = _lower
splice = _splice
named_elements = _named_elements
has_ellipsis = _has_ellipsis
ellipsis_arguments = _ellipsis_arguments

# Names the core lowerings emit into generated Python; resolution-based
# tools (pyflakes, jedi) must treat them as defined.
RUNTIME_NAMES: tuple[str, ...] = (
    "Integer",
    "RealNumber",
    "ComplexNumber",
    "ellipsis_range",
    "ellipsis_iter",
    "var",
    "symbolic_expression",
)
