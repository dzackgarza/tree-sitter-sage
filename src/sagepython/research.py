r"""The research set-builder notation, as a compiler extension.

Brace notation is syntactically valid Python; CPython precedence gives
every builder form a canonical tree shape, so no grammar is involved —
these are lowering rules only, applied via
``lower(source, extensions=(sagepython.research.EXTENSION,))``:

- ``{1, 2}`` → ``Set([1, 2])``; comprehensions likewise
- ``{f(x) | x in D}`` / ``{f(x) | x in D and P}`` → ``ImageSet`` over
  ``D`` or a ``ConditionSet``
- ``{x in D | P}`` → ``ConditionSet`` (chained-``in`` predicates
  recovered from the comparison chain)
- ``{1..5}`` → ``Set`` of an ``ellipsis_range``
- dictionaries and dict comprehensions stay dictionaries
"""

from __future__ import annotations

from sagepython import (
    Context,
    LoweringRule,
    Node,
    ellipsis_arguments,
    has_ellipsis,
    lower_node,
    named_elements,
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


EXTENSION: dict[str, LoweringRule] = {
    "set": _lower_set,
    "set_comprehension": _lower_set_comprehension,
}

# Names the extension's lowerings emit into generated Python.
RUNTIME_NAMES: tuple[str, ...] = ("Set", "ImageSet", "ConditionSet")
