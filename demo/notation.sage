r"""Sage notation this grammar recognizes, in a file Sage can run.

Every construct below is one the preparser rewrites, so preparsing this
file exercises the compiler against the interpreter it replaces: QC runs
``sage --preparse`` over it and byte-compiles the result, and the test
suite runs it as the script it is and checks the numbers.  A script
inherits ``sage.all_cmdline``; the ``.sage`` importer's module namespace
is the other side of that split and is tested separately.

Written in core notation only — the notation any Sage session gets from
``sageparse.preparser``.  The research dialect's additions live with
their own tests, not here.
"""

# `^` is exponentiation, not xor, and integer literals are Sage Integers
# rather than machine ints -- so this is exact, not a float.
MERSENNE = 2^127 - 1

# Postfix factorial.
ARRANGEMENTS = 10!

# A generator declaration names the ring and binds its generators in one
# statement.  `...` spans the names at compile time, so nothing
# downstream ever sees an ellipsis.
R.<x, y> = QQ[]
S.<a0, ..., a4> = ZZ[]

# Implicit multiplication -- juxtaposition as a product, `2x` for `2*x`
# -- is off by default, as it is in Sage; `implicit_multiplication()`
# turns it on, and the compiler tests cover it with it on.  This file is
# core-default notation, so the product is written out.  It was not,
# and the file only preparsed because the research dialect happened to
# be loaded in the session preparsing it.
CONIC = x^2 + 2*x*y + y^2

# An ellipsis range builds the whole list.
SQUARES = [n^2 for n in [1..10]]

# Matrix literals use a semicolon between rows.
ROTATION = [0, -1; 1, 0]


def demonstrate() -> dict:
    """Values a caller can check, computed from the notation above."""
    return {
        "mersenne_is_prime": MERSENNE.is_prime(),
        "arrangements": ARRANGEMENTS,
        "conic_factors": CONIC == (x + y)^2,
        "generators": S.ngens(),
        "squares": SQUARES,
        "rotation_order": ROTATION.multiplicative_order(),
    }
