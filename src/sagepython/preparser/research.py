r"""The research dialect, installed by import.

One line puts a Sage session on this dialect — the Sage language, the
set-builder notation, and implicit multiplication::

    import sagepython.preparser.research

:mod:`sagepython.research` holds the lowering itself and stays
Sage-free.  This module is the half that needs a Sage session: the
registration that makes those rules live.
"""

from __future__ import annotations

from sagepython.preparser import implicit_multiplication, register_extension
from sagepython.research import EXTENSION, RUNTIME_NAMES

register_extension(EXTENSION, RUNTIME_NAMES)
implicit_multiplication(True)
