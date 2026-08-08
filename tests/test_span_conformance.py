r"""Generator spans against Sage's own ``ellipsis_range``.

``x0, x2, ..., x10`` is the stem ``x`` over the indices
``ellipsis_range(0, 2, Ellipsis, 10)``; the names are decoration and the
arithmetic is Sage's.  The compiler cannot call it — the core is
Sage-free so the grammar's CI can run without an installation — so it
conforms instead, and this module is where that conformance is checked
against the live function rather than against remembered values.

Skipped without Sage, like ``test_sage_modules``.  The claims about what
the compiler emits live in the Sage-free modules; only the agreement
with Sage lives here.
"""

from __future__ import annotations

import pytest

from sageparse import expand_generator_ellipsis

# `pytest.importorskip` is not usable here for the reason given in
# `test_sage_modules`: this repo ships a `sage.so` that shadows the name.
try:
    from sage.arith.srange import ellipsis_range
except Exception:
    pytest.skip("no usable Sage in this interpreter", allow_module_level=True)

# (from, then, stop) — `then` is the name that sets the step, or None for
# a bare span.  Chosen so a naive step-1 walk fails on most rows: spans
# that overshoot the endpoint, descend, or cover a single index.
SPANS = [
    (0, None, 10),
    (5, None, 5),
    (0, 2, 10),
    (0, 3, 10),
    (1, 4, 20),
    (0, 5, 7),
    (10, 8, 0),
    (7, 5, 1),
    (2, 6, 30),
    (3, 3 + 7, 100),
]


def _slots(start: int, then: int | None, stop: int) -> list[str]:
    """The generator list `x<start>, [x<then>,] ..., x<stop>`."""
    named = [f"x{start}"] if then is None else [f"x{start}", f"x{then}"]
    return [*named, "...", f"x{stop}"]


def _oracle(start: int, then: int | None, stop: int) -> list[str]:
    arguments = (start, Ellipsis, stop) if then is None else (start, then, Ellipsis, stop)
    return [f"x{index}" for index in ellipsis_range(*arguments)]


@pytest.mark.parametrize(("start", "then", "stop"), SPANS)
def test_expansion_is_ellipsis_range_over_the_indices(start: int, then: int | None, stop: int) -> None:
    assert expand_generator_ellipsis(_slots(start, then, stop)) == _oracle(start, then, stop)


def test_letter_spans_are_ellipsis_range_over_the_code_points() -> None:
    assert expand_generator_ellipsis(["a", "c", "...", "i"]) == [chr(c) for c in ellipsis_range(ord("a"), ord("c"), Ellipsis, ord("i"))]
    assert expand_generator_ellipsis(["a", "...", "e"]) == [chr(c) for c in ellipsis_range(ord("a"), Ellipsis, ord("e"))]


def test_an_empty_span_is_refused_where_sage_returns_nothing() -> None:
    # The one deliberate divergence, and it is not arithmetic: Sage is
    # right that the span is empty, but a declaration naming nothing
    # would emit `(,) = R._first_ngens(0)`, which is a SyntaxError.
    assert ellipsis_range(10, Ellipsis, 0) == []
    with pytest.raises(AssertionError):
        expand_generator_ellipsis(["x10", "...", "x0"])
