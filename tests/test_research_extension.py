"""Behavioral proofs for the research-notation compiler extension.

The rules import directly: ``sageparse.preparser.research`` is the
installable half and needs Sage, while the lowering it applies does not.
"""

from sageparse import lower
from sageparse.extensions.research import EXTENSION


def _research(source: str) -> str:
    return lower(source, extensions=(EXTENSION,)).python


def test_core_keeps_python_set_semantics() -> None:
    assert lower("s = {1, 2}\n").python == "s = {Integer(1), Integer(2)}\n"


def test_extension_lowers_set_literals() -> None:
    assert _research("s = {1, 2}\n") == "s = Set([Integer(1), Integer(2)])\n"


def test_extension_lowers_builders() -> None:
    assert _research("s = {x^2 | x in D}\n") == ("s = ImageSet(lambda x: x**Integer(2), D)\n")
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


def test_extension_lets_a_ring_name_its_own_generators() -> None:
    # `ZZ[]` denotes nothing — it is not even Python — and exists only so
    # Sage's `R.<x,y> = ZZ[]` has somewhere to put the declared names.
    # The dialect lets the ring be written as it is written on paper.
    assert _research("R.<x,y> = ZZ[x,y]\n") == ("R = ZZ['x, y']; (x, y,) = R._first_ngens(2)\n")
    assert _research("R.<x> = QQ[x]\n") == "R = QQ['x']; (x,) = R._first_ngens(1)\n"


def test_extension_expands_ellipsis_inside_the_ring() -> None:
    assert _research("S.<a0,...,a3> = ZZ[a0,...,a3]\n") == ("S = ZZ['a0, a1, a2, a3']; (a0, a1, a2, a3,) = S._first_ngens(4)\n")


def test_core_reproduces_sage_for_a_self_naming_ring() -> None:
    # Stock Sage evaluates the subscript before the names exist, so
    # `R.<x,y> = ZZ[x,y]` raises NameError.  The core is a drop-in
    # replacement and reproduces that; only the dialect reinterprets it.
    assert lower("R.<x,y> = ZZ[x,y]\n").python == ("R = ZZ[x,y]; (x, y,) = R._first_ngens(2)\n")


def test_extension_leaves_a_ring_whose_subscript_is_not_its_generators() -> None:
    # `a, b` name no generator of `R`, so the subscript keeps meaning
    # whatever Sage says it means rather than being quoted.
    assert _research("R.<x,y> = ZZ[a,b]\n") == "R = ZZ[a,b]; (x, y,) = R._first_ngens(2)\n"


def test_extension_leaves_ordinary_two_index_subscripts_alone() -> None:
    # A rule firing on subscript shape alone would turn matrix element
    # access into a polynomial ring.  Nothing declares generators here.
    assert _research("M = G[i,j]\n") == "M = G[i,j]\n"
    assert _research("entry = A[row, column]\n") == "entry = A[row, column]\n"


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
