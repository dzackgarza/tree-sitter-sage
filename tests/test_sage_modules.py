r"""``.sage`` as library source: the importer and the build backend.

Both frontends bind the names the lowering emits to real Sage objects,
so these need Sage, like the rest of the suite.  Sage is a hard
dependency of a Sage preparser: a missing one is a broken setup and
fails loudly here rather than quietly proving less.  QC runs the suite
in a Sage session for this reason, and
``test_the_suite_runs_in_a_sage_session`` below checks that here rather
than trusting the ``_sage-pytest`` recipe to keep doing it.

The core's Sage-free claim is not established by these tests being
optional — it is checked on the import graph, in
``test_sage_free_core``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from sage.rings.integer import Integer

# The parent type of a wrapped literal, asserted against below rather than
# spelled twice.
INTEGER = Integer.__name__

PACKAGE = {
    "__init__.sage": "VERSION = 2^3\n",
    "algorithms.sage": textwrap.dedent(
        """\
        from sage.rings.rational_field import QQ


        def ring():
            R.<x, y> = QQ[]
            return R


        def span():
            return [1,
                    ..,
                    5]


        def boom():
            raise ValueError("raised from Sage source")
        """
    ),
}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    package = tmp_path / "mypkg"
    package.mkdir()
    for name, body in PACKAGE.items():
        (package / name).write_text(body)
    return tmp_path


def _run(cwd: Path, body: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# ---------------------------------------------------------------------------
# The importer
# ---------------------------------------------------------------------------


def test_a_sage_package_imports_like_any_other(tree: Path) -> None:
    out = _run(
        tree,
        """
        import sageparse.preparser.importer
        import mypkg
        from mypkg.algorithms import ring, span
        print(mypkg.VERSION, type(mypkg.VERSION).__name__)
        print(span())
        print(ring())
        """,
    )
    assert f"8 {INTEGER}" in out
    assert "[1, 2, 3, 4, 5]" in out
    assert "Multivariate Polynomial Ring in x, y over Rational Field" in out


def test_module_identity_is_pythons(tree: Path) -> None:
    # Sage's own load() executes into a namespace and produces no module;
    # the point of a loader is that everything below is ordinary.
    out = _run(
        tree,
        """
        import importlib, sys
        import sageparse.preparser.importer
        import mypkg.algorithms as A
        print(A.__spec__.name, A.__package__, A.__file__.endswith("algorithms.sage"))
        print("mypkg.algorithms" in sys.modules)
        print(importlib.reload(A) is A)
        """,
    )
    assert "mypkg.algorithms mypkg True" in out
    assert out.count("True") == 3


def test_a_traceback_names_the_sage_file_and_line(tree: Path) -> None:
    # The raise sits below a construct that lowers onto one line, so this
    # fails if the padding ever stops holding the geometry.
    source = (tree / "mypkg" / "algorithms.sage").read_text().splitlines()
    expected_line = source.index('    raise ValueError("raised from Sage source")') + 1
    out = _run(
        tree,
        """
        import traceback
        import sageparse.preparser.importer
        from mypkg.algorithms import boom
        try:
            boom()
        except ValueError:
            frame = traceback.extract_tb(__import__("sys").exc_info()[2])[-1]
            print(frame.filename.endswith("mypkg/algorithms.sage"), frame.lineno)
        """,
    )
    assert out.strip() == f"True {expected_line}"


def test_a_built_py_wins_over_its_sage_source(tree: Path) -> None:
    (tree / "mypkg" / "other.sage").write_text("WHICH = 'sage'\n")
    (tree / "mypkg" / "other.py").write_text("WHICH = 'py'\n")
    out = _run(
        tree,
        """
        import sageparse.preparser.importer
        from mypkg.other import WHICH
        print(WHICH)
        """,
    )
    assert out.strip() == "py"


def test_importing_the_compiler_alone_changes_no_import_semantics(tree: Path) -> None:
    # `import mypkg` always succeeds — any directory is a namespace
    # package — so the claim is about the module, not the directory:
    # without the finder installed, nothing reaches the .sage source.
    result = subprocess.run(
        [sys.executable, "-c", "import sageparse; from mypkg.algorithms import ring"],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr


# ---------------------------------------------------------------------------
# The build backend
# ---------------------------------------------------------------------------


def test_lower_tree_produces_importable_python(tree: Path, tmp_path: Path) -> None:
    out = _run(
        tree,
        f"""
        from pathlib import Path
        import sageparse.preparser
        from sageparse.build import lower_tree
        written = lower_tree(Path("."), Path({str(tmp_path / "built")!r}))
        print(sorted(p.name for p in written))
        """,
    )
    assert "['__init__.py', 'algorithms.py']" in out

    built = tmp_path / "built"
    out = _run(
        built,
        """
        import mypkg
        from mypkg.algorithms import ring, span
        print(mypkg.VERSION, span(), ring())
        """,
    )
    assert "8 [1, 2, 3, 4, 5]" in out


def test_a_built_module_needs_no_compiler(tree: Path, tmp_path: Path) -> None:
    _run(
        tree,
        f"""
        from pathlib import Path
        import sageparse.preparser
        from sageparse.build import lower_tree
        lower_tree(Path("."), Path({str(tmp_path / "clean")!r}))
        """,
    )
    generated = (tmp_path / "clean" / "mypkg" / "algorithms.py").read_text()
    body = generated.split("\n", 1)[1]
    assert "sageparse" not in body, "a built module must not depend on the compiler that made it"
    assert "sage.all" not in body, "a library module gets the names it emits, not the interactive layer"


def test_the_prelude_imports_only_the_names_used(tree: Path, tmp_path: Path) -> None:
    _run(
        tree,
        f"""
        from pathlib import Path
        import sageparse.preparser
        from sageparse.build import lower_tree
        lower_tree(Path("."), Path({str(tmp_path / "narrow")!r}))
        """,
    )
    generated = (tmp_path / "narrow" / "mypkg" / "algorithms.py").read_text()
    assert "from sage.rings.integer import Integer" in generated
    assert "from sage.arith.srange import ellipsis_range" in generated
    for unused in ("matrix", "symbolic_expression", "factorial"):
        assert f"import {unused}" not in generated, f"{unused} is never emitted by this module"


def test_the_notation_demo_runs_and_computes() -> None:
    r"""`demo/notation.sage` is executable Sage, not a syntax display.

    QC preparses it and byte-compiles the result, which proves the
    compiler emits Python — not that the Python means anything.  This
    runs it, as the script it is: `sage-preparse` emits its header line
    and then `preparse_file`'s output, so a script gets the whole
    `sage.all_cmdline` namespace.  That is the other half of the split
    `sageparse.runtime` documents — a module states its own imports, a
    script inherits the interactive layer — and the demo is on the
    script side.

    Values are checked against arithmetic known independently of Sage:
    2^127-1 is a Mersenne prime, 10! is 3628800, and [0,-1; 1,0] is the
    quarter-turn, so it has order 4.
    """
    from sageparse.preparser import preparse_file

    source = (Path(__file__).resolve().parent.parent / "demo" / "notation.sage").read_text()
    script = "from sage.all_cmdline import *\n" + preparse_file(source)
    namespace: dict = {}
    exec(compile(script, "<demo>", "exec"), namespace)

    computed = namespace["demonstrate"]()
    assert computed["mersenne_is_prime"] is True
    assert computed["arrangements"] == 3628800
    assert computed["conic_factors"] is True
    assert computed["generators"] == 5
    assert computed["squares"] == [n * n for n in range(1, 11)]
    assert computed["rotation_order"] == 4
    # `^` is exponentiation, so this is the exact Mersenne prime rather
    # than the 2 xor 127 a plain Python reading would produce.
    assert namespace["MERSENNE"] == 2**127 - 1


def test_the_prelude_reads_references_not_prose(tmp_path: Path) -> None:
    r"""A runtime name written in prose is not a dependency.

    A built module is worth building because it needs the Sage libraries
    it uses and nothing else.  A word search over the output cannot tell
    ``matrix`` the call from ``matrix`` the noun, so a module that only
    described matrices used to import the matrix constructor -- an
    import that is unused, that ruff flags, and that makes the
    dependency claim untrue.
    """
    source = tmp_path / "prose.sage"
    source.write_text('"""Builds a matrix from a symbolic_expression, eventually."""\nSIZE = 2^3\n')
    from sageparse.build import lower_file

    generated = lower_file(source, tmp_path / "prose.py").read_text()

    # The prelude precedes the module body, so it is everything before
    # the docstring -- which is the one place the nouns legitimately are.
    prelude = generated.split('"""')[0]
    assert "from sage.rings.integer import Integer" in prelude, "2^3 emits Integer, so its import belongs"
    assert "matrix" not in prelude, "the docstring's nouns are not references"
    assert "symbolic_expression" not in prelude


def test_every_emitted_name_is_bound_by_both_frontends() -> None:
    r"""The two frontends must bind exactly what the compiler emits.

    ``RUNTIME_NAMES`` is what the lowerings put into generated Python.
    The importer binds them from ``NAMESPACE`` and a built module gets
    them from ``IMPORTS``.  Nothing previously compared the three, so a
    lowering that started emitting a tenth name would ship modules with
    an undefined reference and no test would notice.
    """
    import sageparse.runtime
    from sageparse import RUNTIME_NAMES
    from sageparse.preparser import runtime_imports

    assert set(RUNTIME_NAMES) == set(sageparse.runtime.NAMESPACE), "the importer binds what the core emits"
    assert set(RUNTIME_NAMES) <= set(runtime_imports()), "a built module imports what the core emits"


def test_the_literal_constructors_build_sage_numbers(tmp_path: Path) -> None:
    r"""``RealNumber`` and ``ComplexNumber`` are constructors, not classes.

    ``runtime.py`` binds both to ``create_*`` rather than to the classes
    of the same name, because the lowering hands them a string and the
    classes want a parent.  Getting that wrong is a ``TypeError`` at
    module import, so it is worth exercising rather than asserting.
    """
    source = tmp_path / "numbers.sage"
    source.write_text("REAL = 1.5\nIMAGINARY = 2j\n")
    from sageparse.build import lower_file

    generated = lower_file(source, tmp_path / "numbers.py").read_text()
    namespace: dict = {}
    exec(compile(generated, "<numbers>", "exec"), namespace)

    # 1/2 and 3/2 are exact in binary, so an exact Sage real compares
    # equal to them; the point is the type, not float tolerance.
    assert namespace["REAL"] + namespace["REAL"] == 3
    assert namespace["IMAGINARY"] ** 2 == -4


def test_the_suite_runs_in_a_sage_session() -> None:
    r"""The interpreter running these tests must have started Sage.

    `sage -python` makes `sage` importable; it is not a Sage session,
    and `sage.all` is absent from it.  Every way a person runs Sage code
    performs that startup import, and Sage's own library is written
    expecting it, so a suite run without it tests an environment no user
    has.  The docstring at the top of this file claims QC provides one;
    this is what makes the claim checkable here instead of true only in
    another repository's recipe.
    """
    assert "sage.all" in sys.modules, "the suite is running under sage -python, not in a Sage session"
