r"""Lowering must not move a line.

Both frontends over the compiler depend on this.  The importer compiles
lowered Python under the ``.sage`` filename, so a shifted line makes
every traceback, breakpoint, and coverage record in the module name the
wrong one; the build backend relies on it to keep the offset it does
introduce equal to the prelude and nothing else.

These are Sage-free: they test the compiler core, not the runtime.
Whether the padded lowering still computes the right value is a claim
about the real prelude, so it is proved in ``test_sage_modules`` —
``test_a_sage_package_imports_like_any_other`` imports a multi-line
ellipsis through the importer under real Sage and checks the result.
"""

from sageparse import lower

COLLAPSING = {
    "list ellipsis": "v = [1,\n     ..,\n     9]\nz = 1\n",
    "parenthesized ellipsis": "v = (1,\n     ..,\n     9)\nz = 1\n",
    "brace ellipsis": "v = {1,\n     ..,\n     9}\nz = 1\n",
    "generator declaration": "R.<x,\n   y> = QQ[]\nz = 1\n",
    "ellipsis with step": "v = [1,\n     3,\n     ..,\n     9]\nz = 1\n",
}


def test_multi_line_constructs_keep_their_line_count() -> None:
    for name, source in COLLAPSING.items():
        result = lower(source)
        assert result.python.count("\n") == source.count("\n"), name
        compile(result.python, "<cell>", "exec")


def test_a_statement_after_a_collapsing_construct_keeps_its_line() -> None:
    # The failure this guards: everything below the construct slides up,
    # so a traceback names a line the author never wrote.
    source = "v = [1,\n     ..,\n     9]\nboom = 1/0\n"
    result = lower(source)
    assert source.splitlines().index("boom = 1/0") == 3
    assert result.python.splitlines().index("boom = Integer(1)/Integer(0)") == 3


def test_single_line_constructs_are_untouched() -> None:
    for source in ("v = [1..9]\n", "R.<x, y> = QQ[]\n", "a = 2^3\nb = 1.5\n"):
        assert lower(source).python.count("\n") == source.count("\n")
