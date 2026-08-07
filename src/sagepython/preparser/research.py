r"""The research dialect, installed by import.

One line puts a Sage session on this dialect — the Sage language, the
set-builder notation, implicit multiplication, and ``R^n`` as a free
module::

    import sagepython.preparser.research

:mod:`sagepython.research` holds the lowering itself and stays
Sage-free.  This module is the half that a Sage session needs: the
runtime meaning of ``^``, and the registration that makes the rules
live.

``R^n`` is the one lowering whose meaning a session must supply.  Until
:func:`register_ring_power` names a module class — and for every ring
Sage builds inside its own algorithms, which write ``R**n`` in ordinary
Python — ``R^n`` stays Sage's native power.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import Any

from sage.categories.rings import Rings
from sage.rings.integer import Integer
from sage.structure.parent import Parent

from sagepython.preparser import implicit_multiplication, register_extension
from sagepython.research import EXTENSION, RUNTIME_NAMES

# Sage's own objects are dynamically typed, so the ring, the module class,
# and the result are Any: the meaning of `R^n` is decided at runtime by
# the category test below, not by a static type.
_ring_power: Callable[..., Any] | None = None


def register_ring_power(constructor: Callable[..., Any]) -> None:
    """Name the free module ``R^n`` builds for a ring ``R``."""
    global _ring_power
    _ring_power = constructor


def research_pow(base: Any, exponent: Any) -> Any:
    r"""Evaluate ``base ^ exponent`` as written in research source.

    Only a ring parent raised to a cardinality is the dialect's noun;
    everything else — ring elements, group elements, symbolic
    expressions, non-ring parents — is Python's ``**`` unchanged.
    """
    if _ring_power is not None and isinstance(exponent, (int, Integer)) and exponent >= 0 and isinstance(base, Parent) and base in Rings():
        return _ring_power(base, exponent)
    return base**exponent


# Lowered source names ``research_pow`` at every caret, including inside
# scripts that carry no imports of their own, so it is a builtin rather
# than a global of any one namespace.
builtins.__dict__["research_pow"] = research_pow
register_extension(EXTENSION, RUNTIME_NAMES)
implicit_multiplication(True)
