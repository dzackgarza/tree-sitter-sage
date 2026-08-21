r"""The names lowered Sage source calls, and nothing else.

A ``.sage`` module gets this namespace, not ``sage.all_cmdline``.  The
distinction is the point: a script may reasonably want every Sage name in
scope, but a library module must state its own mathematical dependencies
and inherit only what the compiler itself emits.  Keeping the prelude
this small is what lets a lowered module depend on the Sage libraries it
actually uses rather than on the whole interactive layer.

Each import is the object the name resolves to in a Sage session, which
is not always the class that shares its name: ``RealNumber`` and
``ComplexNumber`` are literal constructors taking a string, while the
classes called ``RealNumber`` and ``ComplexNumber`` take a parent and
would reject the compiler's output.

Extensions supply their own names the same way, through
``register_extension(rules, runtime=...)``.
"""

from __future__ import annotations

from sage.arith.srange import ellipsis_iter, ellipsis_range
from sage.calculus.expr import symbolic_expression
from sage.calculus.var import var
from sage.functions.other import factorial
from sage.matrix.constructor import matrix
from sage.rings.complex_mpfr import create_ComplexNumber as ComplexNumber
from sage.rings.integer import Integer
from sage.rings.real_mpfr import create_RealNumber as RealNumber

# Keyed by the name the lowering emits, which is the only contract here.
NAMESPACE: dict[str, object] = {
    "Integer": Integer,
    "RealNumber": RealNumber,
    "ComplexNumber": ComplexNumber,
    "ellipsis_range": ellipsis_range,
    "ellipsis_iter": ellipsis_iter,
    "var": var,
    "symbolic_expression": symbolic_expression,
    "factorial": factorial,
    "matrix": matrix,
}

# The same bindings as source, for a module lowered ahead of time.  A
# built ``.py`` carries these lines instead of importing sageparse, so a
# release install depends on the Sage libraries the module uses and not
# on the compiler that produced it.
IMPORTS: dict[str, str] = {
    "Integer": "from sage.rings.integer import Integer",
    "RealNumber": "from sage.rings.real_mpfr import create_RealNumber as RealNumber",
    "ComplexNumber": "from sage.rings.complex_mpfr import create_ComplexNumber as ComplexNumber",
    "ellipsis_range": "from sage.arith.srange import ellipsis_range",
    "ellipsis_iter": "from sage.arith.srange import ellipsis_iter",
    "var": "from sage.calculus.var import var",
    "symbolic_expression": "from sage.calculus.expr import symbolic_expression",
    "factorial": "from sage.functions.other import factorial",
    "matrix": "from sage.matrix.constructor import matrix",
}

assert set(IMPORTS) == set(NAMESPACE), "every runtime name needs both a binding and an import line"
