r"""sageparse: Sage's preparser, rebuilt on a real grammar.

Sage preparses with regular expressions over source text.  This package
parses instead — tree-sitter-sage recognizes the construct, a lowering
table rewrites it, and CPython compiles the output as the semantic
authority.  Positions survive the rewrite, so a diagnostic about
generated Python can be reported against the line the author wrote.

This module is the compiler core, and is Sage-free by construction —
importable in any Python environment.  ``lower(source,
numbers="wrapped", previous=None, extensions=(), products="implicit")``
returns :class:`LoweredSource` (ordinary Python plus a
:class:`SourceMap` translating positions in both directions), with
incremental parse reuse via ``previous``.

The replacement itself is :mod:`sageparse.preparser`, which installs
over Sage's hooks when imported.  Optional notation lives in
:mod:`sageparse.extensions`, one rule table each, activated by the
matching module under :mod:`sageparse.preparser`.  Importing one of
those is all a Sage session needs.

The split is internal, not a package boundary: the core and the rule
tables carry no Sage import, so editors, linters, and language servers
lower source without a Sage installation, while the package as a whole
is still the complete replacement.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from typing import Literal

import tree_sitter_sage

from tree_sitter import Language, Node, Parser, Tree

# Number-literal handling: "wrapped" emits Integer()/RealNumber() calls,
# "raw" leaves numeric literals as CPython sees them.
Numbers = Literal["wrapped", "raw"]

# Implicit multiplication: "implicit" reads `2x` as a product, "explicit"
# leaves the juxtaposition alone so CPython rejects it as the syntax
# error it is under Sage's default.
Products = Literal["implicit", "explicit"]

_LANGUAGE = Language(tree_sitter_sage.language())
_PARSER = Parser(_LANGUAGE)

_HUGE_INTEGER_DIGITS = 4300
_RAW_SUFFIX = re.compile(r"[rRlLjJ]+$")


@dataclass(frozen=True)
class _Context:
    source: bytes
    rules: Mapping[str, LoweringRule]
    numbers: Numbers = "wrapped"
    products: Products = "implicit"
    in_case_pattern: bool = False

    def text(self, node: Node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8")


def _segments(node: Node, context: _Context) -> list[Segment]:
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
    if rule is not None and not node.has_error:
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
                    return segment.original_start + max(0, min(generated_offset, end) - cursor)
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
    _tree: Tree | None = dataclass_field(default=None, repr=False, compare=False)
    _numbers: Numbers = dataclass_field(default="wrapped", repr=False, compare=False)
    _products: Products = dataclass_field(default="implicit", repr=False, compare=False)


def _lower(node: Node, context: _Context) -> str:
    if node.is_error or node.is_missing:
        return context.text(node)
    if node.type == "case_pattern" and not context.in_case_pattern:
        context = replace(context, in_case_pattern=True)
    rule = context.rules.get(node.type)
    if rule is not None and not node.has_error:
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
    if context.numbers == "raw" or context.in_case_pattern:
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
    if context.numbers == "raw" or context.in_case_pattern:
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


def _lower_factorial(node: Node, context: _Context) -> str:
    argument = node.child_by_field_name("argument")
    assert argument is not None
    return f"factorial({_lower(argument, context)})"


def _lower_matrix_literal(node: Node, context: _Context) -> str:
    rows = ", ".join("[" + ", ".join(_lower(element, context) for element in _named_elements(row)) + "]" for row in node.children_by_field_name("row"))
    return f"matrix([{rows}])"


def _lower_version_literal(node: Node, context: _Context) -> str:
    return "(" + ", ".join(context.text(node).split(".")) + ")"


def _lower_implicit_product(node: Node, context: _Context) -> str:
    # With implicit multiplication off, the juxtaposition is not a
    # product: it is a syntax error, and the author's own text is what
    # CPython should see and report.  Lowering the operands instead would
    # hand CPython `Integer(2)x` and blame a construct nobody wrote.
    if context.products == "explicit":
        return context.text(node)
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    assert left is not None and right is not None
    return _lower(left, context) + "*" + _gap(left, right, context) + _lower(right, context)


# ---------------------------------------------------------------------------
# Generators and symbolic functions
# ---------------------------------------------------------------------------


_INDEXED_NAME = re.compile(r"([A-Za-z_]+)(\d+)([A-Za-z_]*)")


def _expand_generator_ellipsis(slots: list[str]) -> list[str]:
    r"""Expand ``['a1', '...', 'a8']`` through ``'a8'`` at compile time.

    The endpoints determine the range textually — indexed names share a
    stem (``e1..e8``, ``a1t..a8t``) and single letters step through the
    alphabet — so no downstream constructor ever sees an ellipsis.
    Malformed spans fail here, at preparse, never as a wrong declaration.
    """
    expanded: list[str] = []
    for i, slot in enumerate(slots):
        if slot != "...":
            expanded.append(slot)
            continue
        assert 0 < i < len(slots) - 1, "'...' needs a name on each side"
        before, after = expanded[-1], slots[i + 1]
        left = _INDEXED_NAME.fullmatch(before)
        right = _INDEXED_NAME.fullmatch(after)
        if left and right:
            assert left.group(1) == right.group(1) and left.group(3) == right.group(3), f"'...' between different stems: {before} and {after}"
            start, stop = int(left.group(2)), int(right.group(2))
            assert stop > start, f"'...' range does not ascend: {before}..{after}"
            stem, suffix = left.group(1), left.group(3)
            expanded.extend(f"{stem}{k}{suffix}" for k in range(start + 1, stop))
            continue
        assert len(before) == 1 and len(after) == 1 and before < after, f"'...' needs indexed or single-letter endpoints: {before}, {after}"
        expanded.extend(chr(c) for c in range(ord(before) + 1, ord(after)))
    return expanded


def _lower_generator_assignment(node: Node, context: _Context) -> str:
    name = node.child_by_field_name("name")
    right = node.child_by_field_name("right")
    assert name is not None and right is not None
    generators = _expand_generator_ellipsis([context.text(child) for child in node.children_by_field_name("generator")])
    others = [context.text(child) for child in node.children_by_field_name("other_target")]
    constructor = _lower_constructor(right, generators, context)
    obj = context.text(name)
    targets = "".join(f", {other}" for other in others)
    gens = ", ".join(generators)
    rebuilt = f"{obj}{targets} = {constructor}; ({gens},) = {obj}._first_ngens({len(generators)})"
    return _pad_to_source_lines(rebuilt, node, context)


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
        has_arguments = any(child.is_named for child in arguments.children)
        comma = ", " if has_arguments else ""
        assert lowered.endswith(")")
        return f"{lowered[:-1]}{comma}names={names})"
    if right.type == "subscript":
        # `S.<q> = QQ[[]]`: fill an empty innermost bracket with the names.
        subscript = right.child_by_field_name("subscript")
        if subscript is not None and subscript.type == "list" and not any(child.is_named for child in subscript.children):
            value = right.child_by_field_name("value")
            assert value is not None
            quoted = "'" + ", ".join(generators) + "'"
            return f"{_lower(value, context)}[[{quoted}]]"
    return _lower(right, context)


def _lower_symbolic_function(node: Node, context: _Context) -> str:
    name = node.child_by_field_name("name")
    body = node.child_by_field_name("body")
    assert name is not None and body is not None
    parameters = ",".join(context.text(child) for child in node.children_by_field_name("parameter"))
    return f'__tmp__=var("{parameters}"); {context.text(name)} = symbolic_expression({_lower(body, context)}).function({parameters})'


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
            pieces.append(f"{_lower(start, context)},Ellipsis,{_lower(end, context)}")
        elif element.type == "sage_ellipsis":
            pieces.append("Ellipsis")
        else:
            pieces.append(_lower(element, context))
    return ",".join(pieces)


def _has_ellipsis(elements: list[Node]) -> bool:
    return any(element.type in {"sage_ellipsis_span", "sage_ellipsis"} for element in elements)


def _pad_to_source_lines(rebuilt: str, node: Node, context: _Context) -> str:
    r"""Give ``rebuilt`` the newline count of the span it replaces.

    A rule that joins a multi-line construct onto one line shifts every
    later line of the file, so a traceback, a coverage report, or a
    breakpoint would name the wrong one.  These rewrites all end in a
    closing bracket, where newlines are insignificant, so the lines can
    simply be put back and the geometry holds without a second pass over
    the tree.
    """
    missing = context.text(node).count("\n") - rebuilt.count("\n")
    if missing <= 0:
        return rebuilt
    assert rebuilt.endswith(")"), f"cannot pad a rewrite that does not close a bracket: {rebuilt!r}"
    return rebuilt[:-1] + "\n" * missing + ")"


def _named_elements(node: Node) -> list[Node]:
    # Comments are named extras; splicing them into a joined single-line
    # rewrite would comment out everything after them.
    return [child for child in node.children if child.is_named and child.type != "comment"]


def _lower_list(node: Node, context: _Context) -> str | None:
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return _pad_to_source_lines(f"(ellipsis_range({_ellipsis_arguments(elements, context)}))", node, context)
    return None


def _lower_parenthesized(node: Node, context: _Context) -> str | None:
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return _pad_to_source_lines(f"(ellipsis_iter({_ellipsis_arguments(elements, context)}))", node, context)
    return None


def _lower_tuple(node: Node, context: _Context) -> str | None:
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return _pad_to_source_lines(f"(ellipsis_iter({_ellipsis_arguments(elements, context)}))", node, context)
    return None


def _lower_set(node: Node, context: _Context) -> str | None:
    # The grammar recognizes `{1..5}`, so the table has to lower it:
    # spliced children would emit `{Integer(1)..Integer(5)}`, which is
    # not Python.  Dialects that give braces their own meaning replace
    # this rule wholesale.
    elements = _named_elements(node)
    if _has_ellipsis(elements):
        return _pad_to_source_lines(f"set(ellipsis_range({_ellipsis_arguments(elements, context)}))", node, context)
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
    "sage_factorial": _lower_factorial,
    "sage_matrix_literal": _lower_matrix_literal,
    "sage_version_literal": _lower_version_literal,
    "sage_generator_assignment": _lower_generator_assignment,
    "sage_symbolic_function_assignment": _lower_symbolic_function,
    "sage_generator_access": _lower_generator_access,
    "list": _lower_list,
    "parenthesized_expression": _lower_parenthesized,
    "tuple": _lower_tuple,
    "set": _lower_set,
}


def _byte_point(encoded: bytes, offset: int) -> tuple[int, int]:
    prefix = encoded[:offset]
    return prefix.count(b"\n"), offset - (prefix.rfind(b"\n") + 1)


def lower(
    source: str,
    numbers: Numbers = "wrapped",
    previous: LoweredSource | None = None,
    extensions: Sequence[Mapping[str, LoweringRule]] = (),
    products: Products = "implicit",
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
    if previous is not None and previous._tree is not None and previous._numbers == numbers and previous._products == products:
        old = previous.source_map.original.encode("utf-8")
        prefix = 0
        limit = min(len(old), len(encoded))
        while prefix < limit and old[prefix] == encoded[prefix]:
            prefix += 1
        suffix = 0
        while suffix < limit - prefix and old[len(old) - 1 - suffix] == encoded[len(encoded) - 1 - suffix]:
            suffix += 1
        old_end = len(old) - suffix
        new_end = len(encoded) - suffix
        previous._tree.edit(
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
    context = _Context(source=encoded, rules=rules, numbers=numbers, products=products)
    segments = tuple(_segments(tree.root_node, context))
    python = "".join(segment.text for segment in segments)
    return LoweredSource(
        python=python,
        source_map=SourceMap(original=source, python=python, segments=segments),
        _tree=tree,
        _numbers=numbers,
        _products=products,
    )


# Public surface for dialect extensions: a rule table maps node types to
# functions (node, context) -> replacement text or None to decline.
Context = _Context
lower_node = _lower
splice = _splice
named_elements = _named_elements
has_ellipsis = _has_ellipsis
pad_to_source_lines = _pad_to_source_lines
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
    "factorial",
    "matrix",
)
