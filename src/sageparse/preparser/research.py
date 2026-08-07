r"""The research dialect, installed by import.

One line puts a Sage session on this dialect — the Sage language, the
set-builder notation, and implicit multiplication::

    import sageparse.preparser.research

:mod:`sageparse.extensions.research` holds the lowering itself and stays
Sage-free.  This module is the half that needs a Sage session: the
objects the lowered source names, and the registration that makes the
rules live.
"""

from __future__ import annotations

from sage.sets.condition_set import ConditionSet
from sage.sets.image_set import ImageSet
from sage.sets.set import Set

from sageparse.extensions.research import EXTENSION, RUNTIME_NAMES
from sageparse.preparser import implicit_multiplication, register_extension

RUNTIME: dict[str, object] = {"Set": Set, "ImageSet": ImageSet, "ConditionSet": ConditionSet}
IMPORTS: dict[str, str] = {
    "Set": "from sage.sets.set import Set",
    "ImageSet": "from sage.sets.image_set import ImageSet",
    "ConditionSet": "from sage.sets.condition_set import ConditionSet",
}
assert set(RUNTIME) == set(RUNTIME_NAMES) == set(IMPORTS), "the dialect emits a name this module does not supply"

register_extension(EXTENSION, RUNTIME, IMPORTS)
implicit_multiplication(True)
