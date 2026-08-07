"""Behavioral proofs for the research-notation compiler extension.

The rules import directly: ``sagepython.preparser.research`` is the
installable half and needs Sage, while the lowering it applies does not.
"""

from sagepython import lower
from sagepython.research import EXTENSION


def _research(source: str) -> str:
    return lower(source, extensions=(EXTENSION,)).python


def test_core_keeps_python_set_semantics() -> None:
    assert lower("s = {1, 2}\n").python == "s = {Integer(1), Integer(2)}\n"


def test_extension_lowers_set_literals() -> None:
    assert _research("s = {1, 2}\n") == "s = Set([Integer(1), Integer(2)])\n"


def test_extension_lowers_builders() -> None:
    assert _research("s = {x^2 | x in D}\n") == ("s = ImageSet(lambda x: research_pow(x, Integer(2)), D)\n")
    assert _research("s = {x in D | P(x)}\n") == ("s = ConditionSet(D, lambda x: P(x))\n")
    assert _research("s = {x | x in D and P(x) and Q(x)}\n") == ("s = ConditionSet(D, lambda x: P(x) and Q(x))\n")


def test_extension_lowers_brace_ellipsis() -> None:
    assert _research("t = {1..3}\n") == ("t = Set((ellipsis_range(Integer(1),Ellipsis,Integer(3))))\n")


def test_extension_keeps_dictionaries() -> None:
    assert _research("d = {'a': 1}\n") == "d = {'a': Integer(1)}\n"


def test_bitwise_or_sets_are_not_builders() -> None:
    assert _research("s = {1 | 2}\n") == "s = Set([Integer(1) | Integer(2)])\n"


def test_incremental_reuse_is_equivalent_under_extensions() -> None:
    state = lower("s = {x | x in D}\n", extensions=(EXTENSION,))
    edited = "s = {x | x in D and P(x)}\n"
    incremental = lower(edited, previous=state, extensions=(EXTENSION,))
    assert incremental.python == lower(edited, extensions=(EXTENSION,)).python


def test_caret_binds_tighter_than_implicit_multiplication() -> None:
    # Lowering `^` to a call freezes the grammar's tree, and that tree is
    # not the semantics: an implicit product is one node, so the caret's
    # operand there is the whole product.  The core's `**` substitution
    # never had to care, because Python re-parsed the result.
    assert _research("3x^2\n") == "Integer(3)*research_pow(x, Integer(2))\n"
    assert _research("x^2 y\n") == "research_pow(x, Integer(2))*y\n"
    assert _research("x^2 y^3 z\n") == "research_pow(x, Integer(2))*research_pow(y, Integer(3))*z\n"
    # Right-associative, like the operator it replaces.
    assert _research("a^b^c\n") == "research_pow(a, research_pow(b, c))\n"


def test_caret_caret_stays_python_xor() -> None:
    assert _research("a ^^ b\n") == "(a) ^ (b)\n"


def test_multiline_set_with_interior_comments_lowers_compilably() -> None:
    # A comment node spliced into the single-line Set([...]) rewrite
    # once swallowed the rest of the line (found by the research repo's
    # route-audit suite).
    result = lower(
        'exempt = {\n    # the first entry\n    "a",\n    # a trailing note\n    "b", "c",\n}\n',
        extensions=(EXTENSION,),
    )
    compile(result.python, "<cell>", "exec")
    assert "#" not in result.python.splitlines()[0][result.python.find("Set") :]
