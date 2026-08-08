r"""The research dialect's lowering rules.

Sage-free like the compiler core, so the rules are testable without a
Sage installation.  :mod:`sageparse.preparser.research` is the
installable half: importing it applies this table to a Sage session.

Brace notation is syntactically valid Python; CPython precedence gives
every builder form a canonical tree shape, so no grammar is involved —
these are lowering rules only:

- ``{1, 2}`` → ``Set([1, 2])``; comprehensions likewise
- ``{f(x) | x in D}`` / ``{f(x) | x in D and P}`` → ``ImageSet`` over
  ``D`` or a ``ConditionSet``
- ``{x in D | P}`` → ``ConditionSet`` (chained-``in`` predicates
  recovered from the comparison chain)
- ``{1..5}`` → ``Set`` of an ``ellipsis_range``
- dictionaries and dict comprehensions stay dictionaries

``R^n`` is deliberately not here.  ``^`` is exponentiation, the core
lowers it to ``**``, and what ``R**n`` means is decided by the ring's
``__pow__`` — a runtime question for whoever owns the ring, not a
preparser one.
"""

from __future__ import annotations

import builtins

from sageparse import (
    Context,
    LoweringRule,
    Node,
    ellipsis_arguments,
    expand_generator_ellipsis,
    has_ellipsis,
    lower_generator_assignment,
    lower_node,
    named_elements,
    pad_to_source_lines,
    splice,
)

# ---------------------------------------------------------------------------
# Brace notation: sets and the research set-builder forms
# ---------------------------------------------------------------------------


def _and_chain(node: Node) -> list[Node]:
    """Flatten a left-associated ``and`` chain into its operands."""
    if node.type == "boolean_operator":
        operator = node.child_by_field_name("operator")
        if operator is not None and operator.text == b"and":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            assert left is not None and right is not None
            return _and_chain(left) + [right]
    return [node]


def _comparison_chain(node: Node) -> tuple[list[Node], list[str]] | None:
    """Operands and operator spellings of a comparison chain."""
    if node.type != "comparison_operator":
        return None
    operands = [child for child in node.children if child.is_named]
    operators = [operator.text.decode() for operator in node.children_by_field_name("operators") if operator.text is not None]
    if len(operands) != len(operators) + 1:
        return None
    return operands, operators


def _top_bitwise_or(node: Node) -> tuple[Node, Node] | None:
    if node.type == "binary_operator":
        operator = node.child_by_field_name("operator")
        if operator is not None and operator.text == b"|":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            assert left is not None and right is not None
            return left, right
    return None


def _lower_builder(element: Node, context: Context) -> str | None:
    """Lower a one-element brace body if it is a set-builder form."""
    chain = _and_chain(element)
    head, conditions = chain[0], chain[1:]
    comparison = _comparison_chain(head)
    if comparison is None:
        return None
    operands, operators = comparison

    condition_text = " and ".join(lower_node(condition, context) for condition in conditions)

    # Form A — `{image | x in domain [and P...]}`:
    # comparison(bitor(image, x), in, domain) [wrapped in `and` chain].
    if len(operands) == 2 and operators == ["in"]:
        split = _top_bitwise_or(operands[0])
        if split is not None and split[1].type == "identifier":
            image, variable = split
            domain = lower_node(operands[1], context)
            variable_text = variable.text.decode() if variable.text else ""
            image_text = lower_node(image, context)
            if condition_text:
                domain = f"ConditionSet({domain}, lambda {variable_text}: {condition_text})"
            if context.text(image).strip() == variable_text:
                return domain if condition_text else f"Set({domain})"
            return f"ImageSet(lambda {variable_text}: {image_text}, {domain})"

    # Form B — `{x in domain | P [and Q...]}`: the bar lands inside the
    # second operand, and a predicate containing comparisons continues
    # the chain: comparison(x, in, bitor(domain, P), op, rest...).
    if operands[0].type == "identifier" and operators[0] == "in":
        split = _top_bitwise_or(operands[1])
        if split is not None:
            domain_node, predicate_head = split
            variable_text = operands[0].text.decode() if operands[0].text else ""
            predicate = lower_node(predicate_head, context)
            for operator, operand in zip(operators[1:], operands[2:]):
                predicate += f" {operator} {lower_node(operand, context)}"
            if condition_text:
                predicate = f"{predicate} and {condition_text}"
            return f"ConditionSet({lower_node(domain_node, context)}, lambda {variable_text}: {predicate})"
    return None


def _lower_set(node: Node, context: Context) -> str:
    elements = named_elements(node)
    if len(elements) == 1:
        builder = _lower_builder(elements[0], context)
        if builder is not None:
            return builder
    if has_ellipsis(elements):
        return f"Set((ellipsis_range({ellipsis_arguments(elements, context)})))"
    inner = ", ".join(lower_node(element, context) for element in elements)
    return f"Set([{inner}])"


def _lower_set_comprehension(node: Node, context: Context) -> str:
    inner = splice(node, context)
    assert inner.startswith("{") and inner.endswith("}")
    return f"Set([{inner[1:-1]}])"


# ---------------------------------------------------------------------------
# Polynomial rings: the ring names its own generators
# ---------------------------------------------------------------------------


def _subscript_names(node: Node, context: Context) -> list[str] | None:
    """Generator names of ``ZZ[x, y]``, or ``None`` if it is not that."""
    children = node.children_by_field_name("subscript")
    if not children or any(child.type not in ("identifier", "ellipsis") for child in children):
        return None
    return expand_generator_ellipsis([context.text(child) for child in children])


def _lower_generator_assignment(node: Node, context: Context) -> str:
    r"""Lower ``R.<x,y> = ZZ[x,y]``, the ring written as it is written.

    Sage spells this ``R.<x,y> = ZZ[]``, whose right-hand side denotes no
    object at all: ``ZZ[]`` is not even Python, and exists only to give
    the declared names somewhere to land.  Writing the generators inside
    the ring instead says the same thing about a ring that is really
    there, so the subscript is quoted in place.

    Sage's own reading of ``R.<x,y> = ZZ[x,y]`` evaluates the subscript
    before the names exist, which is a ``NameError``; the core reproduces
    that faithfully, and only this dialect reinterprets it.  Names that
    do not match the declaration are left to the core, where they keep
    meaning whatever Sage says they mean.
    """
    right = node.child_by_field_name("right")
    name = node.child_by_field_name("name")
    if right is None or name is None or right.type != "subscript" or node.children_by_field_name("other_target"):
        return lower_generator_assignment(node, context)
    generators = expand_generator_ellipsis([context.text(child) for child in node.children_by_field_name("generator")])
    if _subscript_names(right, context) != generators:
        return lower_generator_assignment(node, context)
    value = right.child_by_field_name("value")
    assert value is not None
    obj = context.text(name)
    quoted = "'" + ", ".join(generators) + "'"
    gens = ", ".join(generators)
    rebuilt = f"{obj} = {lower_node(value, context)}[{quoted}]; ({gens},) = {obj}._first_ngens({len(generators)})"
    return pad_to_source_lines(rebuilt, node, context)


# Subtrees whose identifiers name something the file binds.  Reading a
# whole node rather than its precise target over-collects — `G[i] = 1`
# marks `G` and `i` bound, `import a.b` marks `a` and `b` — and that is
# the safe direction: an over-collected name only keeps the ring rule
# from firing, while a missed one would rewrite working code.
_BINDING_FIELDS = {
    "assignment": ("left",),
    "augmented_assignment": ("left",),
    "for_statement": ("left",),
    "for_in_clause": ("left",),
    "function_definition": ("name", "parameters"),
    "lambda": ("parameters",),
    "class_definition": ("name",),
    "named_expression": ("name",),
    "sage_generator_assignment": ("name", "generator", "other_target"),
}
_BINDING_NODES = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "as_pattern_target",
        "global_statement",
        "nonlocal_statement",
    }
)


def _identifiers(node: Node, into: set[str]) -> None:
    if node.type == "identifier" and node.text is not None:
        into.add(node.text.decode())
    for child in node.children:
        _identifiers(child, into)


def _bound_names(node: Node) -> set[str]:
    """Every name the file containing ``node`` binds, plus the builtins."""
    root = node
    while root.parent is not None:
        root = root.parent
    names = set(dir(builtins))
    stack = [root]
    while stack:
        current = stack.pop()
        for field in _BINDING_FIELDS.get(current.type, ()):
            for target in current.children_by_field_name(field):
                _identifiers(target, names)
        if current.type in _BINDING_NODES:
            _identifiers(current, names)
        stack.extend(current.children)
    return names


def _lower_assignment(node: Node, context: Context) -> str | None:
    r"""Lower ``R = ZZ[x,y]`` when nothing in the file binds ``x`` or ``y``.

    ``ZZ[x, y]`` is how the ring is written, and Sage already builds it
    from symbolic variables or generators — the one case it cannot serve
    is names that do not exist yet, where it raises ``NameError``.  This
    binds them instead, exactly as ``R.<x,y> = ZZ[x,y]`` does.

    Unboundness is what separates a ring from a subscript: ``G[i, j]``
    and ``dict[str, Any]`` are the same shape, and both name things the
    file binds — loop targets, imports, builtins.  A name bound nowhere
    can only be a ``NameError`` today, so no working code changes
    meaning.  The limit is that the file is all the compiler sees: in a
    notebook, names bound in an earlier cell look unbound here, and
    ``M = G[i, j]`` in a fresh cell would become a ring.  Declare the
    generators with ``R.<i,j> = ...`` in that situation, or index with an
    explicit tuple.
    """
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None or left.type != "identifier" or right.type != "subscript":
        return None
    generators = _subscript_names(right, context)
    if generators is None:
        return None
    bound = _bound_names(node)
    if any(generator in bound for generator in generators):
        return None
    value = right.child_by_field_name("value")
    assert value is not None
    obj = context.text(left)
    quoted = "'" + ", ".join(generators) + "'"
    gens = ", ".join(generators)
    rebuilt = f"{obj} = {lower_node(value, context)}[{quoted}]; ({gens},) = {obj}._first_ngens({len(generators)})"
    return pad_to_source_lines(rebuilt, node, context)


EXTENSION: dict[str, LoweringRule] = {
    "set": _lower_set,
    "set_comprehension": _lower_set_comprehension,
    "sage_generator_assignment": _lower_generator_assignment,
    "assignment": _lower_assignment,
}

# Names the extension's lowerings emit into generated Python.
RUNTIME_NAMES: tuple[str, ...] = ("Set", "ImageSet", "ConditionSet")
