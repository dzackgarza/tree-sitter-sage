"""Behavioral proofs for the research-notation compiler extension."""

from sagepython import lower
from sagepython.research import EXTENSION


def _research(source: str) -> str:
    return lower(source, extensions=(EXTENSION,)).python


def test_core_keeps_python_set_semantics() -> None:
    assert lower("s = {1, 2}\n").python == "s = {Integer(1), Integer(2)}\n"


def test_extension_lowers_set_literals() -> None:
    assert _research("s = {1, 2}\n") == "s = Set([Integer(1), Integer(2)])\n"


def test_extension_lowers_builders() -> None:
    assert _research("s = {x^2 | x in D}\n") == (
        "s = ImageSet(lambda x: x**Integer(2), D)\n"
    )
    assert _research("s = {x in D | P(x)}\n") == (
        "s = ConditionSet(D, lambda x: P(x))\n"
    )
    assert _research("s = {x | x in D and P(x) and Q(x)}\n") == (
        "s = ConditionSet(D, lambda x: P(x) and Q(x))\n"
    )


def test_extension_lowers_brace_ellipsis() -> None:
    assert _research("t = {1..3}\n") == (
        "t = Set((ellipsis_range(Integer(1),Ellipsis,Integer(3))))\n"
    )


def test_extension_keeps_dictionaries() -> None:
    assert _research("d = {'a': 1}\n") == "d = {'a': Integer(1)}\n"


def test_bitwise_or_sets_are_not_builders() -> None:
    assert _research("s = {1 | 2}\n") == "s = Set([Integer(1) | Integer(2)])\n"


def test_incremental_reuse_is_equivalent_under_extensions() -> None:
    state = lower("s = {x | x in D}\n", extensions=(EXTENSION,))
    edited = "s = {x | x in D and P(x)}\n"
    incremental = lower(edited, previous=state, extensions=(EXTENSION,))
    assert incremental.python == lower(edited, extensions=(EXTENSION,)).python


def test_multiline_set_with_interior_comments_lowers_compilably() -> None:
    # A comment node spliced into the single-line Set([...]) rewrite
    # once swallowed the rest of the line (found by the research repo's
    # route-audit suite).
    result = lower(
        "exempt = {\n"
        "    # the first entry\n"
        '    "a",\n'
        "    # a trailing note\n"
        '    "b", "c",\n'
        "}\n",
        extensions=(EXTENSION,),
    )
    compile(result.python, "<cell>", "exec")
    assert "#" not in result.python.splitlines()[0][result.python.find("Set") :]
