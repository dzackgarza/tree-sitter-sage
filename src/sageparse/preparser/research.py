r"""The research dialect, installed by import.

One line puts a Sage session on this dialect — the Sage language, the
set-builder notation, and implicit multiplication::

    import sageparse.preparser.research

:mod:`sageparse.extensions.research` holds the lowering itself and stays
Sage-free.  This module is the half that needs a Sage session: the
registration that makes those rules live.
"""

from __future__ import annotations

from sageparse.extensions.research import EXTENSION, RUNTIME_NAMES
from sageparse.preparser import implicit_multiplication, register_extension

register_extension(EXTENSION, RUNTIME_NAMES)
implicit_multiplication(True)
