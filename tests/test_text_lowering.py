"""Text-only compilation preserves the mapped compiler's exact output."""

import pytest

import sageparse
from sageparse.extensions.research import EXTENSION


@pytest.mark.parametrize("numbers", ["wrapped", "raw"])
@pytest.mark.parametrize("products", ["implicit", "explicit"])
@pytest.mark.parametrize(
    "source",
    [
        "R.<x, y> = QQ[]\nf(t) = t^2 + 1\n",
        "q = 2x + 3.5\nv = [1..9]\n",
        "s = {x^2 | x in D and x > 0}\n",
        "match value:\n    case 3:\n        result = 5\n",
        "# α comment\nα = 'verbatim 2^3'\n",
        "for a in [0..2]:\n    for b in 0..2:\n        pass\n",
        "def broken(:\n    pass\n",
        "",
    ],
)
def test_text_lowering_matches_mapped_output(source, numbers, products):
    expected = sageparse.lower(source, numbers=numbers, products=products, extensions=(EXTENSION,)).python
    assert sageparse.lower_python(source, numbers=numbers, products=products, extensions=(EXTENSION,)) == expected
