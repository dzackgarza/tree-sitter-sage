r"""Contract tests for the preparser's keyword modes and error surface.

These pin the two real call shapes of the installed preparser:

- ``preparse(cell)`` — whole-cell transform used by ``SagePreparseTransformer``;
- ``preparse(contents, do_time=True, ignore_prompts=False,
  numeric_literals=False)`` — the shape ``sage.repl.preparse.preparse_file``
  uses for ``.sage`` files (``time`` keyword active, no numeric wrapping).

Plain-Python test file: source strings below pass only through the research
``preparse`` under test.
"""

import ast
import contextlib
import io
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import sage.repl.load
from sage.all import (
    QQ,
    ZZ,
    Integer,
    PolynomialRing,
    RealNumber,
    Set,
    cputime,
    ellipsis_range,
    factorial,
    matrix,
    walltime,
)

from sageparse import lower
from sageparse.preparser import preparse, preparse_file, research

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
    "QQ": QQ,
    "ZZ": ZZ,
    "Integer": Integer,
    "PolynomialRing": PolynomialRing,
    "RealNumber": RealNumber,
    "Set": Set,
    "cputime": cputime,
    "ellipsis_range": ellipsis_range,
    "factorial": factorial,
    "matrix": matrix,
    "walltime": walltime,
    # ``load foo.sage`` lowers to a call through ``sage.repl.load``, so the
    # executed source needs the top-level package name bound.
    "sage": sage,
}


def _execute(source: str, **preparse_kwargs: bool) -> SessionNamespace:
    namespace = dict(_NAMESPACE)
    exec(preparse(source, **preparse_kwargs), namespace)
    return namespace


def test_do_time_executes_statement_and_reports_timings() -> None:
    namespace = dict(_NAMESPACE)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(preparse("time r = 2^5", do_time=True), namespace)

    assert namespace["r"] == 32
    assert "Time: CPU" in buffer.getvalue() and "Wall:" in buffer.getvalue()


def test_do_time_without_time_keyword_is_plain_execution() -> None:
    namespace = _execute("r = 2 + 3", do_time=True)

    assert namespace["r"] == 5 and namespace["r"].parent() == ZZ


def test_numeric_literals_disabled_yields_python_ints_but_keeps_caret() -> None:
    namespace = _execute("r = 2^3 + 1", numeric_literals=False)

    assert namespace["r"] == 9 and type(namespace["r"]) is int


def test_ignore_prompts_strips_sage_prompt() -> None:
    namespace = _execute("sage: r = 2 + 2", ignore_prompts=True)

    assert namespace["r"] == 4 and namespace["r"].parent() == ZZ


def test_ignore_prompts_strips_doctest_prompt() -> None:
    namespace = _execute(">>> r = 3 + 2", ignore_prompts=True)

    assert namespace["r"] == 5


def test_doctest_continuation_prefix_is_preserved_and_rest_preparsed() -> None:
    out = preparse("...     x = 2^3")

    assert out.startswith("...")
    remainder = out[3:].lstrip()
    compile(remainder, "<continuation>", "exec")
    namespace = dict(_NAMESPACE)
    exec(remainder, namespace)
    assert namespace["x"] == 8


def test_empty_and_comment_only_cells_pass_through() -> None:
    for cell in ("", "# just a comment", "\n\n"):
        compile(preparse(cell), "<cell>", "exec")


def test_sequential_cells_are_independent() -> None:
    first = _execute("s = 'first'; r = 2^2")
    second = _execute("t = 'second'; r = 3^2")

    assert first["r"] == 4 and first["s"] == "first"
    assert second["r"] == 9 and second["t"] == "second"


def test_augmented_call_assignment_is_not_calculus_and_stays_invalid() -> None:
    out = preparse("f(x) -= 5")

    assert "symbolic_expression" not in out
    with pytest.raises(SyntaxError):
        compile(out, "<cell>", "exec")


def test_incomplete_generator_declaration_stays_invalid() -> None:
    with pytest.raises(SyntaxError):
        compile(preparse("R.<x> = "), "<cell>", "exec")


def test_generator_declaration_keeps_ellipsis_as_a_name() -> None:
    r"""``L.<a, ..., d>`` expands to the full four-name declaration.

    The preparser owns the expansion; no constructor ever sees an
    ellipsis.  Dropping the slot is worse than refusing it — the
    declaration would still compile and silently name the wrong number
    of generators.
    """
    out = preparse("L.<a, ..., d> = Lattice(4)")

    assert "names=('a', 'b', 'c', 'd',)" in out, out
    assert "_first_ngens(4)" in out, out


def test_generator_declaration_ellipsis_survives_repeated_ranges() -> None:
    r"""Every ``...`` keeps its slot, so the rank check downstream can pass.

    ``catalogue.sage``'s ``LK3`` is the specimen: ``U^3 + E8^2`` has rank 22,
    and the declaration only reaches that count if both ranges survive.
    """
    out = preparse("LK3.<v1, v2, u1, u2, up1, up2, e1, ..., e8, ep1, ..., ep8> = (U^3).direct_sum(E8^2)")

    e_names = ", ".join(f"'e{i}'" for i in range(1, 9))
    ep_names = ", ".join(f"'ep{i}'" for i in range(1, 9))
    assert f"names=('v1', 'v2', 'u1', 'u2', 'up1', 'up2', {e_names}, {ep_names},)" in out, out
    assert "_first_ngens(22)" in out, out


def test_preparse_file_keeps_match_case_integer_patterns() -> None:
    source = (
        "def classify(x):\n"
        "    match x:\n"
        "        case 0:\n"
        "            return 0\n"
        "        case -1:\n"
        "            return -1\n"
        "        case 1 | 2:\n"
        "            return 12\n"
        "        case _:\n"
        "            return x\n"
    )
    transformed = preparse_file(source)

    assert "_sage_const_" not in transformed
    namespace = dict(_NAMESPACE)
    exec(transformed, namespace)
    classify = namespace["classify"]
    assert (classify(0), classify(-1), classify(2), classify(7)) == (0, -1, 12, 7)


def test_preparse_file_time_keyword_is_active() -> None:
    namespace = dict(_NAMESPACE)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(preparse_file("time r = 3^4"), namespace)

    assert namespace["r"] == 81
    assert "Time: CPU" in buffer.getvalue()


def test_preparse_file_wraps_bare_load_directives(tmp_path: Path) -> None:
    loaded = tmp_path / "loaded.sage"
    loaded.write_text("w = 2^10\n")
    contents = f"before = 2^2\nload {loaded}\nafter = before + w\n"

    namespace = dict(_NAMESPACE)
    exec(preparse_file(contents), namespace)

    assert namespace["w"] == 1024
    assert namespace["after"] == 1028


def test_source_map_translates_verbatim_positions_exactly() -> None:
    result = lower("R.<x, y> = QQ[]\nq = 2^5 + zz\n")

    generated_column = result.python.split("\n")[1].find("zz")
    assert result.source_map.original_position(2, generated_column) == (2, 10)


def test_source_map_points_rebuilt_constructs_at_their_origin() -> None:
    result = lower("v = 1\nR.<x, y> = QQ[]\n")

    assert result.python.split("\n")[1].startswith("R = QQ[")
    assert result.source_map.original_position(2, 20) == (2, 0)


def test_source_map_translates_a_real_syntax_error() -> None:
    result = lower("R.<x> = QQ[]\ndef broken(:\n    pass\n")

    with pytest.raises(SyntaxError) as excinfo:
        compile(result.python, "<cell>", "exec")
    line, column = result.source_map.original_position(excinfo.value.lineno or 0, excinfo.value.offset or 0)
    assert line == 2 and column == 12


def test_source_map_generated_position_round_trips_verbatim_spans() -> None:
    result = lower("R.<x, y> = QQ[]\nq = 2^5 + zz\n")

    line, column = result.source_map.generated_position(2, 10)
    assert result.python.split("\n")[line - 1][column : column + 2] == "zz"
    assert result.source_map.original_position(line, column) == (2, 10)


def test_source_map_generated_position_anchors_rebuilt_constructs() -> None:
    result = lower("v = 1\nR.<x, y> = QQ[]\n")

    assert result.source_map.generated_position(2, 8) == (2, 0)


def test_source_map_distinguishes_generated_from_verbatim_text() -> None:
    result = lower("R.<x, y> = QQ[]\nq = zz\n")

    # Inside the rebuilt generator statement: generated text.
    assert not result.source_map.exact_at_generated(1, 5)
    # The untouched second line: verbatim author text.
    generated_column = result.python.split("\n")[1].find("zz")
    assert result.source_map.exact_at_generated(2, generated_column)


def test_lint_sensitive_constructs_lower_to_ordinary_python() -> None:
    # The construct list sage-lsp monkey-patches into pycodestyle
    # (E201/E202/E225/E227/E231 suppressions around `R.<...>` and `^^`).
    # Lowering removes the need for any of that: the output is ordinary
    # Python that the stock toolchain parses.
    for source in (
        "R.<x, y> = QQ[]",
        "R.< x , y > = QQ[]",
        "b = 123 ^^ 123",
        "w = 5r + 2.5R + 0xEAr",
    ):
        ast.parse(preparse(source))


def test_sage_34678_match_case_repro_executes() -> None:
    # Upstream: patterns became Integer(1) calls, a TypeError at runtime.
    namespace = dict(_NAMESPACE)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(
            preparse("x = 2\nmatch x:\n    case 1: print('hello')\n    case 2: print('world')\n"),
            namespace,
        )
    assert buffer.getvalue() == "world\n"


def test_sage_19088_multiline_generator_with_trailing_statement() -> None:
    # Upstream: the regex generator rewrite broke on multiline
    # constructors followed by `; A` (and carets inside string args).
    namespace = dict(_NAMESPACE)
    exec(
        preparse("A.<n> = PolynomialRing(QQ,\n                       sparse=False); B = 'n^2 * log(n)^QQ'\n"),
        namespace,
    )
    assert namespace["A"].gen() == namespace["n"]
    assert namespace["B"] == "n^2 * log(n)^QQ"


def test_sage_33942_multiline_fstring_literal_lines_untouched() -> None:
    # Upstream: literal lines inside multiline f-strings were rewritten
    # (a bare `2` became `_sage_const_2` / `Integer(2)`).
    namespace = dict(_NAMESPACE)
    exec(
        preparse('value = f"""\na: {1:0.2f}\na: 2\na: 3\n"""'),
        namespace,
    )
    assert namespace["value"] == "\na: 1.00\na: 2\na: 3\n"


def test_factorial_feature_executes() -> None:
    namespace = dict(_NAMESPACE)
    exec(preparse("a = 5!\nb = 3!=3\n"), namespace)
    assert namespace["a"] == 120
    assert namespace["b"] is False


def test_matrix_literal_feature_executes() -> None:
    namespace = dict(_NAMESPACE)
    exec(preparse("m = [1, 2; 3, 4]\nd = m.det()\n"), namespace)
    assert namespace["m"] == matrix([[1, 2], [3, 4]])
    assert namespace["d"] == -2


def test_version_literal_feature_executes() -> None:
    namespace = dict(_NAMESPACE)
    exec(preparse("newer = 4.10.0 > 4.1.1\nw = 1.2\n"), namespace)
    assert namespace["newer"] is True
    assert namespace["w"] == RealNumber("1.2")


def test_generator_ellipsis_expands_at_preparse() -> None:
    # The preparser owns the string manipulation: the endpoints
    # determine the range textually, so downstream code sees only real
    # names and stays focused on the mathematics.  (The compiler once
    # silently dropped the slot; stock Sage leaves a literal 'Ellipsis'
    # for constructors to interpret.)
    a_names = ", ".join(f"'a{i}'" for i in range(1, 9))
    a_targets = ", ".join(f"a{i}" for i in range(1, 9))
    assert preparse("L.<a1,...,a8> = IntegralLattice('E8')") == (f"L = IntegralLattice('E8', names=({a_names},)); ({a_targets},) = L._first_ngens(8)")
    out = preparse("M.<v1,v2,e1,...,e8,ep1,...,ep8> = X(22)")
    e_names = ", ".join(f"'e{i}'" for i in range(1, 9))
    ep_names = ", ".join(f"'ep{i}'" for i in range(1, 9))
    assert f"names=('v1', 'v2', {e_names}, {ep_names},)" in out
    assert "_first_ngens(18)" in out


def test_backslash_operator_surfaces_as_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        compile(preparse("A \\ B"), "<cell>", "exec")


def test_unbalanced_bracket_surfaces_as_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        compile(preparse("r = [1.."), "<cell>", "exec")


def test_sage_cli_preparse_is_the_research_preparser(tmp_path: Path) -> None:
    r"""``sage --preparse`` compiles with this preparser, not Sage's own.

    ``src/sitecustomize.py`` installs it into every process that can import
    the package, and a Sage process can, so the CLI, the QC gates -- which
    shell out to ``$SAGE_BIN --preparse`` -- and any editor tooling all lower
    the same source the same way.

    Nothing else would notice if that stopped holding: every ``.sage`` file
    would still preparse, into a different language.  The two witnesses below
    are the ones that differ.  ``{1, 2}`` is set-builder notation Sage does
    not have -- its own preparser leaves a Python set literal -- and
    ``case -1:`` is what Sage's own rewrites into ``case -_sage_const_1:``,
    which is not a valid pattern.
    """
    source = tmp_path / "probe.sage"
    source.write_text("def classify(x):\n    match x:\n        case -1:\n            return -1\n        case _:\n            return x\nS = {1, 2}\n")

    subprocess.run(
        # The sage profile binds the driver through the validated SAGE_BIN;
        # a bare-`sage` PATH fallback here would let the proof run under an
        # interpreter nobody validated, so its absence is a loud KeyError.
        [os.environ["SAGE_BIN"], "--preparse", source.name],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    generated = (tmp_path / "probe.sage.py").read_text()

    assert "Set([Integer(1), Integer(2)])" in generated, "brace notation is this preparser's; Sage's own leaves a set literal"
    assert "case -1:" in generated and "_sage_const_" not in generated, "Sage's own preparser rewrites integer patterns into invalid syntax"
    ast.parse(generated)
