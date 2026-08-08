r"""Incremental lowering must be indistinguishable from fresh lowering.

Each test drives ``lower(source, previous=...)`` through document
revisions — including transient error states while a construct is being
typed — and asserts byte-identical output and source maps against a
fresh ``lower(source)``.
"""

import pytest

from sageparse import LoweredSource, lower


def _segment_tuples(result: LoweredSource) -> list[tuple[str, int, int, bool]]:
    return [(segment.text, segment.original_start, segment.original_end, segment.exact) for segment in result.source_map.segments]


def _assert_equivalent(source: str, previous: LoweredSource) -> LoweredSource:
    incremental = lower(source, previous=previous)
    fresh = lower(source)
    assert incremental.python == fresh.python
    assert _segment_tuples(incremental) == _segment_tuples(fresh)
    return incremental


def test_typing_a_generator_assignment_through_error_states() -> None:
    revisions = [
        "R\n",
        "R.\n",
        "R.<\n",
        "R.<x\n",
        "R.<x>\n",
        "R.<x> = \n",
        "R.<x> = QQ[\n",
        "R.<x> = QQ[]\n",
        "R.<x> = QQ[]\nf(t) = t^2\n",
    ]
    state = lower(revisions[0])
    for revision in revisions[1:]:
        state = _assert_equivalent(revision, state)


def test_editing_inside_an_existing_construct() -> None:
    state = lower("R.<x, y> = QQ[]\nq = 2^5\n")
    state = _assert_equivalent("R.<x, zed> = QQ[]\nq = 2^5\n", state)
    _assert_equivalent("R.<x, zed> = QQ[]\nq = 2^12\n", state)


def test_multiline_insertion_between_constructs() -> None:
    state = lower("a = 1\nz = {n^2 | n in [1..5]}\n")
    _assert_equivalent("a = 1\nf(t) = t^3 - t\nw = 5r\nz = {n^2 | n in [1..5]}\n", state)


def test_error_to_valid_transition() -> None:
    state = lower("v = [1..\n")
    _assert_equivalent("v = [1..9]\n", state)


def test_deleting_a_leading_construct() -> None:
    state = lower("R.<x> = QQ[]\nq = 2x + 1\n")
    _assert_equivalent("q = 2x + 1\n", state)


def test_wrap_mode_mismatch_falls_back_to_a_fresh_parse() -> None:
    state = lower("q = 2^3\n", numbers="raw")

    result = lower("q = 2^3 + 1\n", numbers="wrapped", previous=state)

    assert result.python == lower("q = 2^3 + 1\n").python


def test_incremental_source_map_translates_like_a_fresh_one() -> None:
    state = lower("R.<x, y> = QQ[]\nq = 2^5 + zz\n")
    edited = "R.<x, y> = QQ[]\nq = 2^5 + zz + 1\n"

    incremental = lower(edited, previous=state)
    fresh = lower(edited)

    generated_column = fresh.python.split("\n")[1].find("zz")
    assert incremental.source_map.original_position(2, generated_column) == fresh.source_map.original_position(2, generated_column)
    assert incremental.source_map.original_position(2, generated_column) == (2, 10)


def test_error_regions_pass_through_unlowered() -> None:
    # sage#38949: `0..2` outside brackets is invalid; upstream reported
    # the error on the wrong line, and lowering recovered fragments here
    # once produced accidentally-compilable garbage.  The correct outer
    # loop still lowers; the broken line reaches CPython verbatim.
    result = lower("for a in [0..2]:\n    for b in 0..2:\n        pass\n")
    assert "ellipsis_range" in result.python.splitlines()[0]
    try:
        compile(result.python, "<cell>", "exec")
        raise AssertionError("invalid input compiled")
    except SyntaxError as error:
        assert error.lineno == 2


def test_literal_assignment_stays_a_clean_error() -> None:
    # sage#24971: `0 = x` upstream becomes a symbolic-function definition
    # that rebinds the name Integer.
    result = lower("0 = x\n")
    assert result.python == "0 = x\n"


def test_unbalanced_symbolic_assignment_stays_an_error() -> None:
    # sage#17434: `f(x) = 1 ) + ( cos(x)` upstream silently produces
    # valid Python.
    result = lower("f(x) = 1 ) + ( cos(x)\n")
    try:
        compile(result.python, "<cell>", "exec")
        raise AssertionError("invalid input compiled")
    except SyntaxError as error:
        assert error.lineno == 1


def test_generator_ellipsis_expands_at_compile_time() -> None:
    # research#catalogue: `L.<a1, ..., a8>` is pure string manipulation,
    # so the compiler expands it — downstream code sees only real names
    # and stays focused on the mathematics.  (Stock Sage instead emits a
    # literal 'Ellipsis' slot for constructors to interpret; the
    # compiler once even dropped the slot outright.)
    result = lower("L.<a1, ..., a8> = IntegralLattice('E8')\n")
    names = ", ".join(f"'a{i}'" for i in range(1, 9))
    assert result.python == (f"L = IntegralLattice('E8', names=({names},)); (a1, a2, a3, a4, a5, a6, a7, a8,) = L._first_ngens(8)\n")


def test_generator_ellipsis_multiple_spans_and_suffixes() -> None:
    result = lower("M.<v1,v2,e1,...,e4,ep1,...,ep4> = Lattice(10)\n")
    assert "names=('v1', 'v2', 'e1', 'e2', 'e3', 'e4', 'ep1', 'ep2', 'ep3', 'ep4',)" in result.python
    assert "= M._first_ngens(10)" in result.python


def test_generator_ellipsis_letter_range() -> None:
    result = lower("L.<a, ..., d> = Lattice(4)\n")
    assert "names=('a', 'b', 'c', 'd',)" in result.python
    assert "(a, b, c, d,) = L._first_ngens(4)" in result.python


def test_generator_ellipsis_rejects_malformed_spans() -> None:
    # Mismatched stems cannot expand; failing at preparse beats emitting
    # a wrong declaration.
    with pytest.raises(AssertionError):
        lower("L.<a1, ..., b8> = X(8)\n")
    with pytest.raises(AssertionError):
        lower("L.<a8, ..., a1> = X(8)\n")


def test_rules_never_fire_over_error_bearing_nodes() -> None:
    # The silent-drop class: a construct with an internal parse error
    # must never lower to shorter output — the broken text survives and
    # CPython rejects it at its real position.
    result = lower("L.<a, ?, b> = X(2)\n")
    assert "a, ?, b" in result.python
    with pytest.raises(SyntaxError):
        compile(result.python, "<cell>", "exec")


def test_generator_ellipsis_infers_a_step_from_the_first_two_names() -> None:
    # `x0, x2, ..., x10` is Haskell's `[a,b..c]`: the step is `b - a`, so
    # this names six generators, not the eleven of a step-1 walk.  The
    # expansion once took `x2` as the left endpoint and walked to `x10`
    # by ones, silently building a ten-generator ring.
    result = lower("R.<x0, x2, ..., x10> = ZZ[]\n")
    assert "R = ZZ['x0, x2, x4, x6, x8, x10']" in result.python
    assert "(x0, x2, x4, x6, x8, x10,) = R._first_ngens(6)" in result.python


def test_generator_ellipsis_step_applies_to_letter_ranges() -> None:
    result = lower("L.<a, c, ..., i> = Lattice(5)\n")
    assert "names=('a', 'c', 'e', 'g', 'i',)" in result.python


def test_generator_ellipsis_matches_the_decided_span_semantics() -> None:
    # Haskell's `[a,b..c]` and Sage's own `ellipsis_range` agree on every
    # span, and `range` implements both.  These expectations are theirs,
    # not this compiler's: a step that overshoots truncates rather than
    # failing, a span that cannot ascend is empty, and a repeated name
    # is a zero step.  Reproducing them by hand invented a fourth
    # dialect, which is what these rows exist to prevent.
    #   ellipsis_range(0, 3, Ellipsis, 10) == [0, 3, 6, 9]
    assert "names=('x0', 'x3', 'x6', 'x9',)" in lower("R.<x0, x3, ..., x10> = Lattice(4)\n").python
    #   ellipsis_range(5, Ellipsis, 5) == [5]
    assert "names=('x5',)" in lower("R.<x5, ..., x5> = Lattice(1)\n").python
    #   ellipsis_range(10, Ellipsis, 0) == [] — legal as numbers, but a
    #   declaration naming nothing would emit `(,) = R._first_ngens(0)`.
    with pytest.raises(AssertionError):
        lower("R.<x10, ..., x0> = Lattice(0)\n")
    #   ellipsis_range(0, 0, Ellipsis, 10) raises — a step of zero
    with pytest.raises(ValueError):
        lower("R.<x0, x0, ..., x10> = Lattice(2)\n")
