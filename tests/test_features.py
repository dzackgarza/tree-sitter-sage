r"""Feature modules: factorial, matrix literals, version literals.

Each feature ships with two proof layers.  The protection tests pin the
adjacent base-grammar surface a feature could plausibly steal — they
predate the features and must never change.  The feature tests state
the new lowering contract.
"""

from sageparse import lower

# ---------------------------------------------------------------------------
# Protections: base surface the features must not disturb
# ---------------------------------------------------------------------------


def test_not_equal_never_becomes_factorial() -> None:
    assert lower("a = 5!=3\n").python == "a = Integer(5)!=Integer(3)\n"
    assert lower("b = 5 != 3\n").python == "b = Integer(5) != Integer(3)\n"
    assert lower("c = [n for n in d if n != 0]\n").python == "c = [n for n in d if n != Integer(0)]\n"


def test_fstring_conversions_are_not_factorials() -> None:
    assert lower('s = f"{x!r} {y!s}"\n').python == 's = f"{x!r} {y!s}"\n'


def test_plain_lists_dicts_and_statement_semicolons_survive() -> None:
    assert lower("u = [1, 2]\n").python == "u = [Integer(1), Integer(2)]\n"
    assert lower("d = {1: 2}\n").python == "d = {Integer(1): Integer(2)}\n"
    assert lower("a = 1; b = 2\n").python == "a = Integer(1); b = Integer(2)\n"
    assert lower("s = x[1:2]\n").python == "s = x[Integer(1):Integer(2)]\n"


def test_ellipsis_lists_survive() -> None:
    assert lower("r = [1..5]\n").python == "r = (ellipsis_range(Integer(1),Ellipsis,Integer(5)))\n"


def test_floats_and_generator_access_survive() -> None:
    assert lower("w = 1.2\n").python == "w = RealNumber('1.2')\n"
    assert lower("t = 2.5.sqrt()\n").python == "t = RealNumber('2.5').sqrt()\n"
    assert lower("g = R.0\n").python == "g = R.gen(0)\n"
    assert lower("h = R.0 + R.1\n").python == "h = R.gen(0) + R.gen(1)\n"


def test_string_prefixes_are_not_implicit_factors() -> None:
    # numpy's crackfortran.py: adjacent prefixed strings after a binary
    # operand must stay implicit concatenation, not a juxtaposed
    # product against the prefix letter.  The wrapped integer proves the
    # statement parsed (an error region would splice verbatim).
    result = lower("v = [1, y + r'aa' r'bb']\n")
    assert result.python == "v = [Integer(1), y + r'aa' r'bb']\n"
    continued = lower("x = y + \\\n    r'aa'\\\n    r'bb'\nn = 5\n")
    assert continued.python.endswith("n = Integer(5)\n")
    compile(continued.python, "<cell>", "exec")


# ---------------------------------------------------------------------------
# Factorial (sage#30982): postfix `!` lowers to factorial()
# ---------------------------------------------------------------------------


def test_factorial_on_literals_and_names() -> None:
    assert lower("x = 5!\n").python == "x = factorial(Integer(5))\n"
    assert lower("y = n!\n").python == "y = factorial(n)\n"
    assert lower("z = (n + 1)!\n").python == "z = factorial((n + Integer(1)))\n"


def test_factorial_composes_with_operators() -> None:
    assert lower("a = 5! + 3!\n").python == "a = factorial(Integer(5)) + factorial(Integer(3))\n"
    assert lower("b = 5!!\n").python == "b = factorial(factorial(Integer(5)))\n"
    assert lower("c = 5! < 10\n").python == "c = factorial(Integer(5)) < Integer(10)\n"


def test_factorial_requires_adjacency() -> None:
    # A detached `!` stays the syntax error it is in Python.
    result = lower("x = 5 !\n")
    assert result.python == "x = 5 !\n"


# ---------------------------------------------------------------------------
# Matrix literals (sage#12354): `[a,b; c,d]` lowers to matrix([[a,b],[c,d]])
# ---------------------------------------------------------------------------


def test_matrix_literal_two_by_two() -> None:
    assert lower("m = [1,2; 3,4]\n").python == "m = matrix([[Integer(1), Integer(2)], [Integer(3), Integer(4)]])\n"


def test_matrix_literal_column_and_expressions() -> None:
    assert lower("v = [1; 2]\n").python == "v = matrix([[Integer(1)], [Integer(2)]])\n"
    assert lower("m = [x + 1, 0; 0, x^2]\n").python == "m = matrix([[x + Integer(1), Integer(0)], [Integer(0), x**Integer(2)]])\n"


# ---------------------------------------------------------------------------
# Version literals (sage#14384): `1.2.3` lowers to an int tuple
# ---------------------------------------------------------------------------


def test_version_literal_three_and_four_components() -> None:
    assert lower("v = 1.2.3\n").python == "v = (1, 2, 3)\n"
    assert lower("w = 10.20.30.40\n").python == "w = (10, 20, 30, 40)\n"


def test_version_literals_compare_lexicographically() -> None:
    result = lower("ok = 4.1.1 < 4.10.0\n")
    assert result.python == "ok = (4, 1, 1) < (4, 10, 0)\n"
    namespace: dict = {}
    exec(result.python, namespace)
    assert namespace["ok"] is True


# ---------------------------------------------------------------------------
# Brace ellipsis, and implicit multiplication as a setting
# ---------------------------------------------------------------------------


def test_brace_ellipsis_lowers_to_a_python_set() -> None:
    # The grammar recognizes `{1..5}`, so the table has to lower it:
    # splicing the children emitted `{Integer(1)..Integer(5)}`, which
    # does not compile.
    result = lower("s = {1..5}\n")
    assert result.python == "s = set(ellipsis_range(Integer(1),Ellipsis,Integer(5)))\n"
    compile(result.python, "<cell>", "exec")


def test_brace_without_ellipsis_stays_a_set_literal() -> None:
    assert lower("s = {1, 2}\n").python == "s = {Integer(1), Integer(2)}\n"


def test_explicit_products_leave_juxtaposition_for_cpython_to_reject() -> None:
    # Sage's own default is off.  Declining the rule keeps the author's
    # text, so CPython reports the syntax error at the author's position
    # instead of the compiler inventing a product.
    assert lower("y = 2x\n", products="explicit").python == "y = 2x\n"
    assert lower("y = 2x\n").python == "y = Integer(2)*x\n"


def test_caret_keeps_its_precedence_over_implicit_products() -> None:
    # `^` lowers to `**` textually, so CPython re-parses and supplies the
    # grouping.  The grammar's tree does not show it — an implicit product
    # is one node — which is why lowering `^` to a call instead would have
    # to reassociate by hand.  It does not, so nothing has to.
    result = lower("v = 3x^2\n")
    assert result.python == "v = Integer(3)*x**Integer(2)\n"
    namespace = {"Integer": int, "x": 5}
    exec(result.python, namespace)
    assert namespace["v"] == 75  # 3*(5**2), not (3*5)**2 == 225

    result = lower("w = x^2 y^3\n")
    namespace = {"Integer": int, "x": 2, "y": 3}
    exec(result.python, namespace)
    assert namespace["w"] == 108  # (2**2)*(3**3), not 2**(2*3**3)
