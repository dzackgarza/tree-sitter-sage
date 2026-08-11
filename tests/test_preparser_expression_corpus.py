r"""Blind, executable Sage-expression corpus for the research preparser.

The rest of the suite compares lowered *text*, which pins the shape of what
the compiler emits and cannot see what that text does when it runs.  These
cases execute it and assert on the objects built, so they are what proves the
caret swap, implicit multiplication firing and declining, calculus
assignment, literal bases and the raw suffix, and ordinary Python surviving
untouched.

Came from the research repository, which consumes this compiler and had
grown the corpus while the compiler still lived there.

Plain-Python test file: it is never passed through Sage's preparser, so the
only transformation under test is ``preparse`` applied to each ``source``.
The names that preparse output may reference are supplied explicitly below,
mirroring the notebook REPL namespace.  Builder results are compared by
materialization (``list(r)``), because ``ImageSet == Set([...])`` is not
elementwise equality.
"""

from typing import Any

from dataclasses import dataclass
from itertools import islice

import pytest

# Names the research preparse output may reference (REPL globals in a notebook).
from sage.all import (
    CC,
    GF,
    NN,
    QQ,
    SR,
    ZZ,
    ComplexNumber,
    FreeAlgebra,
    Integer,
    NumberField,
    O,
    PolynomialRing,
    PowerSeriesRing,
    QuadraticField,
    RealNumber,
    Set,
    Sets,
    cached_function,
    cos,
    diff,
    ellipsis_iter,
    ellipsis_range,
    exp,
    expand,
    factor,
    identity_matrix,
    integral,
    matrix,
    pi,
    sin,
    symbolic_expression,
    var,
    vector,
)
from sage.repl.preparse import preparse as sage_preparse

from sageparse.preparser import preparse, research

# What an executed cell's namespace is: names bound to whatever objects the
# cell builds.  ``Any`` is the honest element type -- the values are Sage
# parents, elements, functions and modules with nothing in common -- and
# naming it once keeps that admission in one place instead of at every use.
type SessionNamespace = dict[str, Any]

# The namespace an executed cell sees.  Built rather than taken from
# ``globals()``: the lowering's output names ``Set``/``ImageSet``/
# ``ConditionSet``, and the dialect itself declares which those are, so the
# runtime half comes from ``research.RUNTIME`` instead of a second list here
# that could drift from it.
_NAMESPACE: SessionNamespace = {
    **research.RUNTIME,
    "islice": islice,
    "CC": CC,
    "GF": GF,
    "NN": NN,
    "QQ": QQ,
    "SR": SR,
    "ZZ": ZZ,
    "ComplexNumber": ComplexNumber,
    "FreeAlgebra": FreeAlgebra,
    "Integer": Integer,
    "NumberField": NumberField,
    "O": O,
    "PolynomialRing": PolynomialRing,
    "PowerSeriesRing": PowerSeriesRing,
    "QuadraticField": QuadraticField,
    "RealNumber": RealNumber,
    "Set": Set,
    "Sets": Sets,
    "cached_function": cached_function,
    "cos": cos,
    "diff": diff,
    "ellipsis_iter": ellipsis_iter,
    "ellipsis_range": ellipsis_range,
    "exp": exp,
    "expand": expand,
    "factor": factor,
    "identity_matrix": identity_matrix,
    "integral": integral,
    "matrix": matrix,
    "pi": pi,
    "sin": sin,
    "symbolic_expression": symbolic_expression,
    "var": var,
    "vector": vector,
}


@dataclass
class Case:
    group: str
    name: str
    source: str
    oracle: str


cases = [
    # Generator declarations and algebraic constructions.
    Case("generators", "univariate_polynomial", "R.<x> = PolynomialRing(QQ)", "assert R.base_ring() == QQ and R.gen() == x and (x^2 + 1).degree() == 2"),
    Case("generators", "multivariate_polynomial", "R.<x,y,z> = PolynomialRing(QQ, 3)", "assert R.ngens() == 3 and R.gens() == (x,y,z) and (x*y+z).total_degree() == 2"),
    Case("generators", "power_series", "S.<t> = PowerSeriesRing(QQ); f = 1 + t^2 + O(t^5)", "assert S.gen() == t and f.valuation() == 0 and f.precision_absolute() == 5"),
    Case("generators", "multivariate_power_series", "S.<t,u,v> = PowerSeriesRing(QQ); f=t+u^2+v^3+S.O(4)", "assert S.ngens() == 3 and f in S"),
    Case("generators", "quotient_generator", "R.<x> = PolynomialRing(QQ); Q.<a> = R.quotient(x^2 + 1)", "assert a^2 == -1 and Q.gen() == a"),
    Case("generators", "number_field_generator", "R.<x> = PolynomialRing(QQ); K.<a> = NumberField(x^2 + 1)", "assert a^2 == -1 and K.degree() == 2"),
    Case("generators", "finite_field_generator", "F.<a> = GF(9)", "assert F.order() == 9 and a.parent() == F"),
    Case("generators", "double_bracket_power_series", "S.<q> = QQ[[]]; f=3-q^3+O(q^5)", "assert S.gen() == q and f.precision_absolute() == 5"),
    # Symbolic, function, and calculus-like notation.
    Case("symbolic", "symbolic_power", "var('x'); r=(x+1)^3", "assert expand(r) == x^3+3*x^2+3*x+1"),
    Case("symbolic", "function_assignment", "f(x) = x^3 - x", "assert f(3) == 24 and f.derivative()(2) == 11"),
    Case("symbolic", "two_variable_function", "g(u,v)=u^2+v^2", "assert g(3,4) == 25"),
    Case("symbolic", "negative_function", "h(t)=-t", "assert h(10) == -10"),
    Case("symbolic", "trig_identity", "var('x'); r=sin(x)^2+cos(x)^2", "assert r(x=0) == 1 and r(x=pi/2) == 1"),
    Case("symbolic", "differentiate", "var('x'); r=diff(x^5 + 2x, x)", "assert r == 5*x^4+2"),
    Case("symbolic", "integrate", "var('x'); r=integral(3x^2, x)", "assert diff(r,x) == 3*x^2"),
    Case("symbolic", "equation", "var('x'); eq=(x^2 == 4)", "assert eq.lhs() == x^2 and eq.rhs() == 4"),
    Case("symbolic", "generator_dot", "R.<x> = PolynomialRing(QQ); r=R.0", "assert r == x"),
    Case("symbolic", "integer_method", "r=87.factor()", "assert list(r) == [(3,1),(29,1)]"),
    Case("symbolic", "real_method", "r=15.10.sqrt()", "assert abs(r^2-15.10) < 1e-12"),
    Case("symbolic", "semicolons", "var('x'); f(x)=x^2; r=f(7)", "assert r == 49"),
    # Numeric and raw literals.
    Case("literals", "rational", "r=2/3", "assert r == QQ(2)/3 and r.parent() == QQ"),
    Case("literals", "real", "r=2.5", "assert r.parent().is_field() and r == 5/2"),
    Case("literals", "complex", "r=2.5j", "assert r^2 == -6.25"),
    Case("literals", "hex", "r=0x2e3", "assert r == 739 and r.parent() == ZZ"),
    Case("literals", "binary", "r=0b111001", "assert r == 57"),
    Case("literals", "octal", "r=0o100", "assert r == 64"),
    Case("literals", "underscores", "r=1_000_000 + 3_000", "assert r == 1003000"),
    Case("literals", "scientific", "r=1.25e3", "assert r == 1250"),
    Case("literals", "raw_integer", "r=393939r", "assert type(r) is int and r == 393939"),
    Case("literals", "raw_real", "r=1.5r", "assert type(r) is float and r == 1.5"),
    Case("literals", "unary_power", "r=-2^4", "assert r == -16"),
    Case("literals", "parenthesized_negative_power", "r=(-2)^4", "assert r == 16"),
    Case("literals", "integer_sqrt", "r=16.sqrt()", "assert r == 4"),
    # Ranges and ellipses.
    Case("ranges", "ellipsis_integer", "r=[1..5]", "assert r == [1,2,3,4,5]"),
    Case("ranges", "ellipsis_step", "r=[1,3..9]", "assert r == [1,3,5,7,9]"),
    Case("ranges", "ellipsis_real", "r=[1.0..2.0]", "assert r == [1.0,2.0]"),
    Case("ranges", "python_range", "r=list(range(2,10,3))", "assert r == [2,5,8]"),
    Case("ranges", "ellipsis_loop", "r=[]\nfor k in (1..5):\n    r.append(k^2)", "assert r == [1,4,9,16,25]"),
    # Matrix and vector expressions (ordinary documented constructors).
    Case("linear_algebra", "matrix_literal", "A=matrix(QQ, [[1,2],[3,4]])", "assert A.det() == -2 and A.rank() == 2"),
    Case("linear_algebra", "identity_matrix", "A=identity_matrix(ZZ, 3)", "assert A.det() == 1 and A^4 == A"),
    Case("linear_algebra", "matrix_implicit", "var('x'); A=matrix(SR, [[x,2x],[3x,4x]])", "assert A.det() == -2*x^2"),
    Case("linear_algebra", "vector", "v=vector(QQ, [1/2,2/3,3/4])", "assert v.dot_product(v) == 181/144"),
    # Ordinary braces, comprehensions, nesting, and unpacking.
    Case("ordinary_braces", "empty_braces_dictionary", "r={}", "assert type(r) is dict and r == {}"),
    Case("ordinary_braces", "finite_set", "r={1,2,3}", "assert r == Set([1,2,3])"),
    Case("ordinary_braces", "duplicate_set", "r={1,1,2}", "assert r == Set([1,2])"),
    Case("ordinary_braces", "nested_sets", "r={{1,2},{3,4}}", "assert r == Set([Set([1,2]),Set([3,4])])"),
    Case("ordinary_braces", "set_comprehension", "r={n^2 for n in [1..4]}", "assert r == Set([1,4,9,16])"),
    Case("ordinary_braces", "set_unpack", "xs=[2,3]; r={1,*xs,4}", "assert r == Set([1,2,3,4])"),
    Case("ordinary_braces", "dictionary", "r={'a':1,'b':2}", "assert r == {'a':1,'b':2}"),
    Case("ordinary_braces", "dictionary_comprehension", "r={n:n^2 for n in range(4)}", "assert r == {0:0,1:1,2:4,3:9}"),
    Case("ordinary_braces", "dictionary_unpack", "d={'a':1}; r={**d,'b':2}", "assert r == {'a':1,'b':2}"),
    Case("ordinary_braces", "nested_dictionary_set", "r={'a':{1,2},'b':{'c':3}}", "assert r['a'] == Set([1,2]) and r['b'] == {'c':3}"),
    Case("ordinary_braces", "set_of_tuple", "r={(1,2),(3,4)}", "assert r == Set([(1,2),(3,4)])"),
    Case("ordinary_braces", "set_slice_expression", "xs=[1,2,3,4]; r={tuple(xs[1:3])}", "assert r == Set([(2,3)])"),
    Case("ordinary_braces", "set_lambda_expression", "r={(lambda z: z+1)(2)}", "assert r == Set([3])"),
    Case("ordinary_braces", "dict_tuple_key", "r={(1,2):3}", "assert r == {(1,2):3}"),
    Case("ordinary_braces", "dict_set_values", "r={1:{2,3},4:{5,6}}", "assert r[1] == Set([2,3]) and r[4] == Set([5,6])"),
    # Added set-builder spellings, first in an execution namespace with ImageSet.
    Case("builders", "identity_domain", "r={x | x in ZZ}", "assert 0 in r and -7 in r and QQ(1)/2 not in r"),
    Case("builders", "domain_first_predicate", "r={x in NN | x.is_prime()}", "assert 2 in r and 13 in r and 9 not in r"),
    Case("builders", "domain_then_predicate", "r={x | x in NN and x.is_prime()}", "assert 2 in r and 11 in r and 1 not in r"),
    Case("builders", "negative_image", "r={-n | n in NN}", "assert list(islice(iter(r),6)) == [0,-1,-2,-3,-4,-5]"),
    Case("builders", "affine_image", "r={3x+2 | x in ZZ}", "assert list(islice(iter(r),6)) == [2,5,-1,8,-4,11]"),
    Case("builders", "square_finite_image", "r={x^2 | x in [1..5]}", "assert list(r) == [1,4,9,16,25]"),
    Case("builders", "finite_identity", "r={x | x in [1..5]}", "assert Set(r) == Set([1,2,3,4,5])"),
    Case("builders", "finite_set_domain", "r={x | x in {1,2,3}}", "assert list(r) == [1,2,3]"),
    Case("builders", "compound_predicate", "r={x | x in ZZ and x>0 and x<5}", "assert [k in r for k in [-1,0,1,4,5]] == [False,False,True,True,False]"),
    Case("builders", "implicit_mult_predicate", "r={x | x in ZZ and 2x > 3}", "assert 2 in r and 1 not in r"),
    Case("builders", "implicit_mult_image", "r={2x^2+3x+1 | x in [0..3]}", "assert list(r) == [1,6,15,28]"),
    Case("builders", "tuple_image", "r={(x,x^2) | x in [1..3]}", "assert list(r) == [(1,1),(2,4),(3,9)]"),
    Case("builders", "function_image", "r={factor(n) | n in [2..6]}", "assert list(r) == [factor(2),factor(3),factor(4),factor(5),factor(6)]"),
    Case("builders", "unicode_variable", "r={α^2 | α in [1..4]}", "assert list(r) == [1,4,9,16]"),
    Case("builders", "nested_set_domain", "r={x | x in {{1,2},{3,4}}}", "assert Set(r) == Set([Set([1,2]),Set([3,4])])"),
    # Strings, comments, formatting, and multiline cells.
    Case("lexical", "ordinary_string", "r='{x | x in ZZ}'", "assert r == '{x | x in ZZ}'"),
    Case("lexical", "raw_string", "r=r'{x | x in ZZ}'", "assert r == '{x | x in ZZ}'"),
    Case("lexical", "triple_string", "r='''{1,2}\n{x | x in ZZ}'''", "assert r == '{1,2}\\n{x | x in ZZ}'"),
    Case("lexical", "escaped_quote", "r='He said \\'{1,2}\\''", "assert r == \"He said '{1,2}'\""),
    Case("lexical", "fstring_simple", "x=7; r=f'value={x}'", "assert r == 'value=7'"),
    Case("lexical", "fstring_format", "x=7; r=f'{x:03d}'", "assert r == '007'"),
    Case("lexical", "fstring_escaped_braces", "x=7; r=f'{{{x}}}'", "assert r == '{7}'"),
    Case("lexical", "fstring_dict_expression", "r=f\"{ {'a': 1} }\"", "assert r == \"{'a': 1}\""),
    Case("lexical", "comment_braces", "# {x | x in ZZ}\nr=2^3", "assert r == 8"),
    Case("lexical", "inline_comment", "r={1,2} # {x | x in ZZ}", "assert r == Set([1,2])"),
    Case("lexical", "multiline_set", "r={\n  1,\n  2,\n  3\n}", "assert r == Set([1,2,3])"),
    Case("lexical", "multiline_dict", "r={\n 'a': 1,\n 'b': 2\n}", "assert r == {'a':1,'b':2}"),
    Case("lexical", "multiline_builder", "r={\n x |\n x in ZZ\n}", "assert 5 in r and QQ(1)/2 not in r"),
    Case("lexical", "backslash_continuation", "r={x | x in ZZ and \\\n x>0}", "assert 1 in r and 0 not in r"),
    Case("lexical", "unicode_identifier", "α=3; β=4; r=α^2+β^2", "assert r == 25"),
    # Valid Python/Sage uses of | inside braces which are not builders.
    Case("pipe_collisions", "set_bitwise_or_element", "r={1 | 2}", "assert r == Set([3])"),
    Case("pipe_collisions", "set_parenthesized_bitwise_or", "r={(1 | 2)}", "assert r == Set([3])"),
    Case("pipe_collisions", "dictionary_bitwise_or_value", "r={'a': 1 | 2}", "assert r == {'a':3}"),
    Case("pipe_collisions", "dictionary_parenthesized_or_value", "r={'a': (1 | 2)}", "assert r == {'a':3}"),
    Case("pipe_collisions", "dictionary_or_key", "r={(1 | 2): 4}", "assert r == {3:4}"),
    Case("pipe_collisions", "set_comprehension_or_expr", "r={x | 1 for x in range(3)}", "assert r == Set([1,3])"),
    Case("pipe_collisions", "dict_comprehension_or_value", "r={x: x | 1 for x in range(3)}", "assert r == {0:1,1:1,2:3}"),
    Case("pipe_collisions", "dict_union", "r=({'a':1} | {'b':2})", "assert r == {'a':1,'b':2}"),
    Case("pipe_collisions", "set_union", "r=({1,2} | {2,3})", "assert r == Set([1,2,3])"),
    Case(
        "pipe_collisions",
        "nested_set_union_element",
        "r={({1}|{2}), 3}",
        "assert r.cardinality() == 2 and 3 in r and any(element == Set([1,2]) for element in r if element != 3)",
    ),
    Case("pipe_collisions", "predicate_with_bitwise_or", "r={x | x in ZZ and (x | 1) == x}", "assert 1 in r and 3 in r and 2 not in r"),
    Case("pipe_collisions", "domain_with_set_union", "r={x | x in ({1,2}|{3,4})}", "assert list(r) == [1,2,3,4]"),
    # Repeated calls and realistic notebook cells.
    Case("notebook_cells", "repeated_sets", "a={1,2}; b={3,4}; r=a|b", "assert r == Set([1,2,3,4])"),
    Case("notebook_cells", "builder_after_ring", "R.<x>=PolynomialRing(QQ); r={x^n | n in [0..4]}", "assert list(r) == [1,x,x^2,x^3,x^4]"),
    Case("notebook_cells", "functions_and_sets", "f(n)=n^2+1; r={f(n) | n in [0..3]}", "assert list(r) == [1,2,5,10]"),
    Case("notebook_cells", "dict_and_builder", "d={n:n^2 for n in range(5)}; r={d[n] | n in [1..4]}", "assert list(r) == [1,4,9,16]"),
    Case("notebook_cells", "comments_semicolons", "# setup\nR.<x>=PolynomialRing(QQ); f=x^2+1\nr={f(n) | n in [0..3]} # image", "assert list(r) == [1,2,5,10]"),
    Case("notebook_cells", "multiline_function", "f(x,y) = (\n x^2\n + 2x*y\n + y^2\n)\nr=f(2,3)", "assert r == 25"),
    # Generator declarations: the full preparse_generators surface.
    Case(
        "generators",
        "names_injected_into_call",
        "A.<x,y,z> = FreeAlgebra(QQ, 3); r = x*y - y*x",
        "assert A.ngens() == 3 and r == A.gen(0)*A.gen(1) - A.gen(1)*A.gen(0) and r != 0",
    ),
    Case("generators", "bound_names_differ_from_ring_names", "R.<x> = ZZ['y']; r = x", "assert r == R.gen() and str(r) == 'y'"),
    Case("generators", "bind_existing_parent", "S0 = PolynomialRing(QQ, 'w'); T.<v> = S0; r = v", "assert T is S0 and r == S0.gen()"),
    Case(
        "generators",
        "multi_target_field_extension",
        "R.<x> = GF(2)[]; S = R.quotient(x^2 + x + 1); F.<b>, f_map, g_map = S.field_extension(); r = b^2 + b",
        "assert r == F(1) and F.cardinality() == 4",
    ),
    Case("generators", "statement_after_declaration", "R.<x> = ZZ['x']; r = 2", "assert R.gen() == x and r == 2 and r.parent() == ZZ"),
    Case("generators", "trailing_comment", "K.<a> = QuadraticField(5) # a comment\nr = a^2", "assert r == 5"),
    Case("generators", "multiline_constructor", "K.<a> = QuadraticField(2 +\n                       1)\nr = a^2", "assert r == 3"),
    Case("generators", "chained_gen_access", "R.<x> = PolynomialRing(QQ); r = R.0.degree()", "assert r == 1"),
    Case("generators", "gen_access_after_bracket", "r = QQ['s,t'].1", "assert str(r) == 't'"),
    Case("generators", "gen_access_on_numbered_name", "R0 = PolynomialRing(QQ, 'a,b'); r = R0.1", "assert str(r) == 'b'"),
    # Calculus assignment: the full preparse_calculus surface.
    Case("calculus", "equals_minus_is_function", "f(x) =- 5; r = f(3)", "assert r == -5"),
    Case("calculus", "comment_with_paren_in_body", "f(x) = (x + (x*x) +  # comment with matching )\n        1); r = f(2)", "assert r == 7"),
    Case("calculus", "multiline_parameter_list", "f(a,\n  b,\n  c,\n  d) = a + b*2 + c*3 + d*4\nr = f(1, 1, 1, 1)", "assert r == 10"),
    Case("calculus", "unicode_function_name", "\u03bc(x) = x^2; r = \u03bc(3)", "assert r == 9"),
    Case("calculus", "subscripted_call_is_not_calculus", "g = lambda z, store=[0]: store; g(1)[0] = 5; r = g(2)[0]", "assert r == 5"),
    # Numeric literals: edges of preparse_numeric_literals.
    Case("literals", "leading_zeros_decimal", "r = 042", "assert r == 42 and r.parent() == ZZ"),
    Case("literals", "leading_dot_real", "r = .5", "assert r == 1/2 and r.parent().is_field()"),
    Case("literals", "trailing_dot_real", "r = 5.", "assert r == 5 and str(r.parent()).startswith('Real')"),
    Case("literals", "integer_method_exp", "r = 1.exp()", "assert r == exp(1)"),
    Case("literals", "hex_method_call", "r = 0x10.sqrt()", "assert r == 4"),
    Case("literals", "huge_integer_literal", "r = " + "1" * 4301, "assert r == (10^4301 - 1)//9 and r.parent() == ZZ"),
    Case("literals", "real_exponent_power", "r = 2^0.5", "assert abs(r^2 - 2) < 1e-12"),
    Case("literals", "scientific_negative_exponent", "r = 2.5e-3", "assert r == 1/400"),
    Case("literals", "underscored_real_value", "r = 1_3.2_5e-2_2", "assert abs(r - 1.325e-21) < 1e-30"),
    # Implicit multiplication at level 5.
    Case("implicit", "space_separated_names", "a=2; b=3; c=4; r = a b c", "assert r == 24"),
    Case("implicit", "closing_paren_times_name", "y=3; r = (2y^2-4y+3)y", "assert r == 27"),
    Case("implicit", "number_times_name", "lam=7; r = 3lam", "assert r == 21"),
    Case("implicit", "adjacent_calls_not_multiplied", "F = lambda a: lambda b: a + b; r = F(1)(2)", "assert r == 3"),
    Case("implicit", "keywords_not_multiplied", "x=5; r = x and x", "assert r == 5"),
    Case("implicit", "conditional_not_multiplied", "r = 2 if False else 3", "assert r == 3"),
    Case("implicit", "power_then_space_times_name", "n=4; x0=3; r = 2^n x0", "assert r == 48"),
    # Ellipsis ranges and genuine Python Ellipsis.
    Case("ranges", "iterator_range", "r = list((1..5))", "assert r == [1,2,3,4,5]"),
    Case("ranges", "nested_ellipsis", "r = [1,..,2,..,len([1..3])]", "assert r == [1,2,3]"),
    Case("ranges", "expression_endpoints", "L=[10,20,30]; f0 = lambda t: t; r = [f0(1) .. L[2]]", "assert len(r) == 30 and r[0] == 1 and r[-1] == 30"),
    Case("ranges", "bare_ellipsis_assignment", "r = ...", "assert r is Ellipsis"),
    # No ``d[...]`` case.  Inside brackets ``...`` is this compiler's range
    # notation, so a subscript cannot also mean the Ellipsis object.  The
    # bare assignment above still holds, which is where Python's meaning
    # survives with nothing to collide with.
    # Caret rewriting: ^ is power, ^^ is xor, including augmented forms.
    Case("caret", "xor_operator", "r = 8^^1", "assert r == 9"),
    Case("caret", "inplace_power", "x=5; x ^= 2; r = x", "assert r == 25"),
    Case("caret", "inplace_xor", "x=5; x ^^= 3; r = x", "assert r == 6"),
    Case("caret", "caret_in_string_untouched", "r = '^ 2x [1..5] R.<x>'", "assert r == '^ 2x [1..5] R.<x>'"),
    # match statements that must survive literal wrapping.
    Case("match", "mapping_string_keys", "def h(p):\n    match p:\n        case {'k': v}:\n            return v\nr = h({'k': 9})", "assert r == 9"),
    Case(
        "match",
        "sage_integer_class_pattern",
        "def h(p):\n    match p:\n        case Integer() as n:\n            return n + 1\n        case _:\n            return 0\nr = h(5)",
        "assert r == 6",
    ),
    Case("match", "guarded_class_pattern", "def h(p):\n    match p:\n        case str() if p == 'a':\n            return 1\n    return 0\nr = h('a')", "assert r == 1"),
    Case(
        "match",
        "call_expression_subject",
        "q = lambda t: t\ndef h(p):\n    match q(p):\n        case 3:\n            return 'three'\n    return 0\nr = h(3)",
        "assert r == 'three'",
    ),
    Case(
        "match",
        "int_pattern_misses_sage_integer",
        "def h(p):\n    match p:\n        case int():\n            return 1\n        case _:\n            return 0\nr = h(5)",
        "assert r == 0",
    ),
    # Lexical: strings, escapes, percent formatting, f-strings.
    Case("lexical", "percent_format", "r = '%s' % 5", "assert r == '5'"),
    Case("lexical", "percent_escape", "r = '%d %% %s' % (1, 'a')", "assert r == '1 % a'"),
    Case("lexical", "percent_string_beside_set", "s = '100%'; r = {1, 2}", "assert s == '100%' and r == Set([1,2])"),
    Case("lexical", "bytes_literal", "r = b'\\x00ab'", "assert r == b'\\x00ab'"),
    Case("lexical", "raw_bytes_literal", "r = rb'\\n'", "assert r == b'\\\\n'"),
    Case("lexical", "fstring_raw_width_spec", "x=20; r = f'{x:{10r}}'", "assert r == '        20'"),
    Case("lexical", "fstring_triple_nested", "r = f'''1{ f\"2{ f'4{ 2^3 }4' }2\" }1'''", "assert r == '1248421'"),
    Case("lexical", "raw_fstring", "r = rf'{2^3}\\n'", "assert r == '8\\\\n'"),
    # Ordinary Python that must pass through with its semantics intact.
    Case("python", "walrus", "if (m := 10) > 5:\n    r = m", "assert r == 10"),
    Case("python", "comprehension_filters", "r = [y for y in range(10) if y % 2 == 0 if y > 2]", "assert r == [4,6,8]"),
    Case("python", "star_args_kwargs", "def f(*args, **kw):\n    return sum(args) + len(kw)\nr = f(1, 2, k=3)", "assert r == 4"),
    Case(
        "python",
        "nonlocal_closure",
        "def outer():\n    total = 0\n    def inner(v):\n        nonlocal total\n        total += v\n        return total\n    return inner\nacc = outer(); acc(1); r = acc(2)",
        "assert r == 3",
    ),
    Case("python", "yield_from", "def gen():\n    yield 1\n    yield from [2, 3]\nr = list(gen())", "assert r == [1,2,3]"),
    Case("python", "try_except", "try:\n    raise ValueError('v')\nexcept ValueError as err:\n    r = str(err)", "assert r == 'v'"),
    Case("python", "chained_comparison", "r = 1 < 2 < 3", "assert r is True"),
    Case("python", "annotations", "def f(x: int) -> int:\n    return x + 1\nr = f(1)", "assert r == 2"),
    Case("python", "annotated_assignment", "v: dict[str, int] = {'a': 1}; r = v", "assert r == {'a': 1}"),
    Case("python", "async_await", "async def af():\n    return 5\nimport asyncio\nr = asyncio.run(af())", "assert r == 5"),
    Case("python", "decorated_function", "@cached_function\ndef cf(n):\n    return n^2\nr = cf(3)", "assert r == 9"),
    Case(
        "python",
        "docstring_untouched",
        "def f(x):\n    '''doc with 2^3 and {a | a in ZZ} and [1..5]'''\n    return x\nr = f.__doc__",
        "assert r == 'doc with 2^3 and {a | a in ZZ} and [1..5]'",
    ),
    Case("python", "floor_mod_true_division", "r = (-7 // 2, -7 % 2, 7 / 2)", "assert r == (-4, 1, QQ(7)/2)"),
    Case("python", "lambda_keyword_default", "r = (lambda *a, k=2^2: sum(a) + k)(1, 2)", "assert r == 7"),
    Case("python", "extended_slicing", "xs = [1, 2, 3, 4]; r = xs[::2] + xs[::-1][:1]", "assert r == [1, 3, 4]"),
    Case("python", "del_statement", "x = 3\ndel x\nr = 'deleted'", "assert r == 'deleted'"),
    # Statement blocks whose bodies carry Sage syntax.
    Case("blocks", "default_argument", "def f(a=2^2):\n    return a\nr = f()", "assert r == 4"),
    Case("blocks", "class_body", "class C:\n    v = 2^3\nr = C.v", "assert r == 8"),
    Case("blocks", "backslash_continuation_expression", "r = 1 + \\\n2", "assert r == 3"),
    # Regressions fixed by the #308 rewrite: defects of the retired
    # compose-with-sage architecture that must never return.
    Case("literals", "raw_complex_literal", "r = 5jr", "assert type(r) is complex and r == 5j"),
    Case("literals", "exponent_with_plus_sign", "r = 1e+10", "assert r == 10^10"),
    Case("literals", "underscored_integer_parent", "r = 1_000_000", "assert r.parent() == ZZ"),
    Case("literals", "underscored_real_parent", "r = 1_000.5", "assert str(r.parent()).startswith('Real')"),
    Case(
        "match",
        "or_pattern",
        "def h(p):\n    match p:\n        case 1 | 2:\n            return 'small'\n        case _:\n            return 'big'\nr = h(2)",
        "assert r == 'small'",
    ),
    Case("match", "sequence_pattern", "def h(p):\n    match p:\n        case [1, *rest]:\n            return rest\nr = h([1,2,3])", "assert r == [2,3]"),
    Case(
        "match",
        "float_pattern",
        "def h(p):\n    match p:\n        case -1.5:\n            return 'neg'\n        case _:\n            return 0\nr = h(-1.5)",
        "assert r == 'neg'",
    ),
    Case("match", "mapping_integer_key", "def h(p):\n    match p:\n        case {1: v}:\n            return v\n    return 0\nr = h({1: 'one'})", "assert r == 'one'"),
    Case("ranges", "brace_ellipsis_set", "r = {1..5}", "assert r == Set([1,2,3,4,5])"),
    Case("lexical", "fstring_self_documenting", "x=7; r = f'{x=}'", "assert r == 'x=7'"),
]


@pytest.mark.parametrize(
    "case",
    cases,
    ids=lambda case: f"{case.group}:{case.name}",
)
def test_authored_expression_constructs_the_expected_sage_objects(case: Case) -> None:
    namespace = dict(_NAMESPACE)
    exec(preparse(case.source), namespace)
    exec(sage_preparse(case.oracle), namespace)
    if case.group == "builders":
        assert namespace["r"] in Sets()
