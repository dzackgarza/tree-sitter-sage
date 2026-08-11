r"""Isolated behavioral proofs for the notebook's mathematical preparser.

Plain-Python test file: it is never passed through Sage's preparser, so the
only transformation under test is ``sageparse.preparser.preparse``
applied to the source strings below.  The names that Sage's preparse output may
reference (``Integer``, ``RealNumber``, ``ellipsis_range``, ``Set``, ...) are
supplied explicitly, exactly as a notebook REPL namespace supplies them.
"""

from typing import Any

from itertools import islice

from sage.all import (
    CC,
    NN,
    QQ,
    SR,
    ZZ,
    ComplexNumber,
    Integer,
    PolynomialRing,
    RealNumber,
    Set,
    diff,
    ellipsis_range,
    integral,
    matrix,
    symbolic_expression,
    var,
)

from sageparse.preparser import preparse, research



# What an executed cell's namespace is: names bound to whatever objects the
# cell builds.  ``Any`` is the honest element type -- the values are Sage
# parents, elements, functions and modules with nothing in common -- and
# naming it once keeps that admission in one place instead of at every use.
type SessionNamespace = dict[str, Any]

# The namespace an executed cell sees.  Built rather than taken from
# ``globals()``, so every name here is a real use: the lowering's output
# names ``Set``/``ImageSet``/``ConditionSet``, and the dialect declares
# which those are, so that half comes from ``research.RUNTIME``.
_NAMESPACE: SessionNamespace = {
    **research.RUNTIME,
    "CC": CC,
    "NN": NN,
    "QQ": QQ,
    "SR": SR,
    "ZZ": ZZ,
    "ComplexNumber": ComplexNumber,
    "Integer": Integer,
    "PolynomialRing": PolynomialRing,
    "RealNumber": RealNumber,
    "Set": Set,
    "diff": diff,
    "ellipsis_range": ellipsis_range,
    "integral": integral,
    "matrix": matrix,
    "symbolic_expression": symbolic_expression,
    "var": var,
}


def _execute(source: str) -> SessionNamespace:
    namespace = dict(_NAMESPACE)
    exec(preparse(source), namespace)
    return namespace


def test_mathematical_set_notation_executes_without_loading_the_preamble() -> None:
    namespace = _execute(
        "literal = {1, 2, 3}; "
        "nested = {{1, 2}, {3, 4}}; "
        'mapping = {"one": 1}; '
        'sets_in_mapping = {"odds": {1, 3}}; '
        "comprehension = {x for x in [1, 2, 2, 3]}; "
        "negatives = {-n | n in NN}; "
        "primes = {x in NN | x.is_prime()}; "
        "primes_right = {x | x in NN and x.is_prime()}; "
        "affine = {3x + 2 | x in ZZ}; "
        "even_integers = {x in ZZ | x in 2*ZZ}"
    )

    assert namespace["literal"] == Set([1, 2, 3])
    assert namespace["nested"] == Set([Set([1, 2]), Set([3, 4])])
    assert namespace["mapping"] == {"one": 1}
    assert namespace["sets_in_mapping"]["odds"] == Set([1, 3])
    assert namespace["comprehension"] == Set([1, 2, 3])
    assert tuple(islice(namespace["negatives"], 4)) == (0, -1, -2, -3)
    assert tuple(islice(namespace["primes"], 4)) == (2, 3, 5, 7)
    assert tuple(islice(namespace["primes_right"], 4)) == (2, 3, 5, 7)
    assert tuple(islice(namespace["affine"], 5)) == (2, 5, -1, 8, -4)
    assert tuple(islice(namespace["even_integers"], 8)) == (
        0,
        2,
        -2,
        4,
        -4,
        6,
        -6,
        8,
    )


def test_preparser_composes_with_sage_generator_declarations() -> None:
    namespace = _execute("R.<x, y> = PolynomialRing(QQ, 2); generators = {x, y}; quadrics = {u^2 | u in generators}")

    assert namespace["R"].gens() == (namespace["x"], namespace["y"])
    assert namespace["generators"] == Set([namespace["x"], namespace["y"]])
    assert Set(tuple(namespace["quadrics"])) == Set([namespace["x"] ** 2, namespace["y"] ** 2])


def test_direct_preparse_applies_implicit_multiplication_in_derivatives() -> None:
    namespace = _execute("x = var('x'); result = diff(x^5 + 2x, x)")

    assert namespace["result"] == 5 * namespace["x"] ** 4 + 2


def test_direct_preparse_applies_implicit_multiplication_in_integrals() -> None:
    namespace = _execute("x = var('x'); result = integral(3x^2, x)")

    assert namespace["result"] == namespace["x"] ** 3


def test_direct_preparse_applies_implicit_multiplication_in_matrices() -> None:
    namespace = _execute("x = var('x'); result = matrix(SR, [[x, 2x], [3x, 4x]])")
    x = namespace["x"]

    assert namespace["result"] == matrix(SR, [[x, 2 * x], [3 * x, 4 * x]])


def test_direct_preparse_applies_implicit_multiplication_in_functions() -> None:
    namespace = _execute("f(x, y) = x^2 + 2x*y + y^2; result = f(1, 2)")

    assert namespace["result"] == 9


def test_identity_builder_on_a_finite_range_is_the_extensional_set() -> None:
    namespace = _execute("result = {x | x in [1..5]}")

    assert namespace["result"] == Set([1, 2, 3, 4, 5])


def test_identity_builder_on_nested_sets_is_the_extensional_set() -> None:
    namespace = _execute("result = {x | x in {{1, 2}, {3, 4}}}")

    assert namespace["result"] == Set([Set([1, 2]), Set([3, 4])])


def test_fstring_replacement_fields_preserve_sage_expressions() -> None:
    namespace = _execute("x = 7; result = f'{x}'")

    assert namespace["result"] == "7"


def test_fstring_escaped_braces_preserve_replacement_fields() -> None:
    namespace = _execute("x = 7; result = f'{{{x}}}'")

    assert namespace["result"] == "{7}"


def test_fstring_dictionary_expressions_remain_dictionaries() -> None:
    namespace = _execute("""result = f"{ {'a': 1} }" """)

    assert namespace["result"] == "{'a': 1}"


def test_python_native_binary_literals_survive_preparsing() -> None:
    namespace = _execute("result = 0b111001")

    assert namespace["result"] == 57


def test_python_native_octal_literals_survive_preparsing() -> None:
    namespace = _execute("result = 0o100")

    assert namespace["result"] == 64


def test_python_native_underscore_literals_survive_preparsing() -> None:
    namespace = _execute("result = 1_000_000 + 3_000")

    assert namespace["result"] == 1003000


def test_python_native_complex_literals_survive_preparsing() -> None:
    namespace = _execute("result = 2.5j")

    assert namespace["result"] == CC(0, 2.5)


def test_python_native_negative_complex_literals_survive_preparsing() -> None:
    namespace = _execute("result = -2.5j")

    assert namespace["result"] == CC(0, -2.5)


def test_python_native_underscore_complex_literals_survive_preparsing() -> None:
    namespace = _execute("result = 1_000.5j")

    assert namespace["result"] == CC(0, 1000.5)


def test_native_sage_preparse_does_not_break_match_case_integers() -> None:
    source = (
        "def classify(x):\n"
        "    match x:\n"
        "        case 0:\n"
        "            return 0\n"
        "        case -1:\n"
        "            return -1\n"
        "        case 1:\n"
        "            return 1\n"
        "        case _:\n"
        "            return x\n"
    )
    repaired = preparse(source)
    compile(repaired, "<preparsed>", "exec")

    namespace = _execute(source)
    assert namespace["classify"](0) == 0
    assert namespace["classify"](-1) == -1
    assert namespace["classify"](1) == 1
    assert namespace["classify"](7) == 7


def test_multiline_identity_builder_preserves_its_domain() -> None:
    namespace = _execute(
        """
result = {
    x |
    x in ZZ
}
"""
    )

    assert tuple(islice(namespace["result"], 5)) == (0, 1, -1, 2, -2)


def test_bitwise_or_is_an_ordinary_set_element() -> None:
    namespace = _execute("result = {1 | 2}")

    assert namespace["result"] == Set([3])


def test_bitwise_or_is_an_ordinary_dictionary_value() -> None:
    namespace = _execute("result = {'a': 1 | 2}")

    assert namespace["result"] == {"a": 3}


def test_bitwise_or_is_preserved_in_set_comprehensions() -> None:
    namespace = _execute("result = {x | 1 for x in range(3)}")

    assert namespace["result"] == Set([1, 3])


def test_bitwise_or_is_preserved_in_dictionary_comprehensions() -> None:
    namespace = _execute("result = {x: x | 1 for x in range(3)}")

    assert namespace["result"] == {0: 1, 1: 1, 2: 3}
