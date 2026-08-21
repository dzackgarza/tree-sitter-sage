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
from collections.abc import Iterator
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
        print("Integer" in A.__sageparse_runtime_names__)
        print("ring" not in A.__sageparse_runtime_names__)
        """,
    )
    assert "mypkg.algorithms mypkg True" in out
    assert out.count("True") == 5


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
    # A host interpreter may preinstall the finder at startup (the research
    # venv ships a sitecustomize that does exactly that), so the probe first
    # strips startup-installed sageparse machinery; the claim under test is
    # that importing the compiler itself puts none of it back.
    probe = textwrap.dedent(
        """\
        import importlib.util
        import sys

        sys.meta_path[:] = [
            finder
            for finder in sys.meta_path
            if "sageparse" not in type(finder).__module__
        ]
        sys.path_importer_cache.clear()
        before = list(sys.meta_path)
        import sageparse

        print(sys.meta_path == before)
        print(importlib.util.find_spec("mypkg.algorithms") is None)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["True", "True"]


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
    # The one sanctioned appearance of the compiler's name is the
    # `__sageparse_runtime_names__` metadata constant — plain data naming
    # the injected runtime bindings, not a dependency on the compiler.
    compiler_mentions = [line for line in body.splitlines() if "sageparse" in line]
    assert all(line.startswith("__sageparse_runtime_names__ =") for line in compiler_mentions), "a built module must not depend on the compiler that made it"
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
    assert "__sageparse_runtime_names__ = frozenset(['Integer', 'ellipsis_range'])" in generated
    for unused in ("matrix", "symbolic_expression", "factorial"):
        assert f"import {unused}" not in generated, f"{unused} is never emitted by this module"


@pytest.fixture
def core_defaults() -> Iterator[None]:
    """Preparser settings as a plain ``sageparse.preparser`` install has them.

    A session that has loaded a dialect is not the default one — the
    research dialect turns implicit multiplication on at import — and on
    this developer's machine a sitecustomize loads it into every Sage
    process.  Anything claiming to be core notation has to be checked
    against the core settings, not against whatever the session picked
    up.
    """
    from sageparse.preparser import implicit_multiplication

    previous = implicit_multiplication(False)
    yield
    implicit_multiplication(previous)


def test_the_notation_demo_runs_and_computes(core_defaults: None) -> None:
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

    # The prelude is the generated import lines, and the docstring is the
    # one place the nouns legitimately are, so the claim is about the
    # imports rather than about a slice of the file.
    prelude = [line for line in generated.splitlines() if line.startswith(("import ", "from "))]
    assert "from sage.rings.integer import Integer" in prelude, "2^3 emits Integer, so its import belongs"
    assert not [line for line in prelude if "matrix" in line], "the docstring's nouns are not references"
    assert not [line for line in prelude if "symbolic_expression" in line]


# Heads a module may legally open with, each of which the prelude has to
# stay below.  A future statement is a compiler directive Python accepts
# only above every other statement, so an import placed over one is a
# syntax error and the built module does not exist.
HEADS = {
    "nothing": "",
    "one future statement": "from __future__ import annotations\n",
    "a docstring, then a future statement": 'r"""What this module is for."""\n\nfrom __future__ import annotations\n',
    "several future statements": "from __future__ import annotations\nfrom __future__ import division\n",
}


@pytest.mark.parametrize("head", HEADS.values(), ids=list(HEADS))
def test_a_module_head_keeps_its_place_above_the_prelude(head: str, tmp_path: Path) -> None:
    r"""A built module compiles whatever its source legally opened with.

    Emitting the prelude at the very top put it over the source's own
    ``__future__`` block, and CPython rejects the result outright --
    every ``.sage`` file carrying ``from __future__ import annotations``
    lowered to a module that could not be compiled at all.

    Running the module is what proves the placement: the fix must not be
    the prelude going missing, so the Sage literal still has to build a
    Sage integer.
    """
    source = tmp_path / "head.sage"
    source.write_text(f"{head}SIZE = 2^3\n")
    from sageparse.build import lower_file

    generated = lower_file(source, tmp_path / "head.py").read_text()
    namespace: dict = {}
    exec(compile(generated, "head.py", "exec"), namespace)

    assert namespace["SIZE"] == 8
    assert type(namespace["SIZE"]).__name__ == INTEGER, "the prelude is still there and still binds Sage's Integer"


def test_the_head_keeps_its_meaning_and_not_just_its_legality(tmp_path: Path) -> None:
    r"""Both head statements mean something the prelude must not take.

    A string literal is the docstring only while it is the first
    statement, so an import above it leaves ``__doc__`` empty without
    any error to say so.  ``annotations`` is the directive that makes an
    annotation a string rather than an expression evaluated at
    definition, so the module's own reading of ``Undefined`` -- a name
    nothing binds -- is what shows the directive still governs the
    lowered module.
    """
    source = tmp_path / "governed.sage"
    source.write_text(
        textwrap.dedent(
            """\
            r'''The docstring.'''

            from __future__ import annotations

            SIZE = 2^3


            def scale(n: Undefined) -> Undefined:
                return n * SIZE
            """
        )
    )
    from sageparse.build import lower_file

    generated = lower_file(source, tmp_path / "governed.py").read_text()
    namespace: dict = {}
    exec(compile(generated, "governed.py", "exec"), namespace)

    assert namespace["__doc__"] == "The docstring."
    assert namespace["scale"].__annotations__ == {"n": "Undefined", "return": "Undefined"}
    assert namespace["scale"](2) == 16


def test_a_modules_own_bindings_are_not_dependencies(tmp_path: Path) -> None:
    r"""A name the module binds itself is the module's, not a Sage import.

    The prelude is a dependency claim: a built module needs the Sage
    libraries it actually references.  A module that assigns ``matrix``,
    or defines its own ``factorial``, or names a parameter ``matrix``,
    has bound that name itself — importing the Sage object those
    bindings replace adds a dependency the module does not have, and
    puts names in ``__sageparse_runtime_names__`` that the runtime
    namespace never supplies to it.  What decides is scope resolution,
    not identifier occurrence: only a read that resolves to a name the
    module never binds reaches the prelude.
    """
    source = tmp_path / "shadow.sage"
    source.write_text(
        textwrap.dedent(
            """\
            SIZE = 2^3
            matrix = [[SIZE]]


            def factorial(n):
                return n


            COUNT = factorial(SIZE)


            def scale(matrix):
                return [entry * SIZE for entry in matrix[0]]
            """
        )
    )
    from sageparse.build import lower_file

    generated = lower_file(source, tmp_path / "shadow.py").read_text()
    assert "sage.matrix" not in generated, "an assignment target and a parameter are bindings, not references"
    assert "sage.functions" not in generated, "the module's own factorial replaces Sage's"
    assert "from sage.rings.integer import Integer" in generated, "2^3 emits Integer, so its import belongs"

    namespace: dict = {}
    exec(compile(generated, "<shadow>", "exec"), namespace)
    assert namespace["__sageparse_runtime_names__"] == frozenset({"Integer"})
    assert namespace["COUNT"] == 8, "the module's factorial is the identity, not Sage's 40320"
    assert namespace["scale"]([[2, 3]]) == [16, 24]


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


# ---------------------------------------------------------------------------
# One meaning across the frontends
# ---------------------------------------------------------------------------

# Source that only the installed dialect can read correctly: ``2k`` is a
# product exactly when implicit multiplication is on, and ``{1, 3}`` is a
# Sage ``Set`` exactly when the research rules are registered.
DIALECT_SOURCE = textwrap.dedent(
    """\
    def double(k):
        return 2k


    PAIR = {1, 3}
    """
)


@pytest.fixture
def research_dialect() -> Iterator[None]:
    """The research dialect installed, with the product mode restored after."""
    import sageparse.preparser.research  # noqa: F401 — registering the dialect is the point
    from sageparse.preparser import implicit_multiplication

    previous = implicit_multiplication(True)
    yield
    implicit_multiplication(previous)


def _session_meaning(source: str) -> dict:
    """What a Sage session makes of ``source``.

    ``sage-preparse`` emits ``preparse_file``'s output under the whole
    ``sage.all_cmdline`` namespace; this is that script, executed.
    """
    from sageparse.preparser import preparse_file

    namespace: dict = {}
    exec(compile("from sage.all_cmdline import *\n" + preparse_file(source), "<session>", "exec"), namespace)
    return namespace


def _imported_meaning(source: str, directory: Path, stem: str) -> dict:
    """What the importer makes of ``source``, through a real ``import``."""
    import importlib

    import sageparse.preparser.importer  # noqa: F401 — installs the finder

    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.sage").write_text(source)
    sys.path.insert(0, str(directory))
    importlib.invalidate_caches()
    try:
        return dict(vars(importlib.import_module(stem)))
    finally:
        sys.path.remove(str(directory))
        sys.modules.pop(stem, None)


def _built_meaning(source: str, directory: Path, stem: str) -> dict:
    """What a built module makes of ``source``: the generated ``.py``, executed."""
    from sageparse.build import lower_file

    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.sage").write_text(source)
    generated = lower_file(directory / f"{stem}.sage", directory / "built" / f"{stem}.py").read_text()
    namespace: dict = {}
    exec(compile(generated, f"{stem}.py", "exec"), namespace)
    return namespace


def test_one_source_means_the_same_in_every_frontend(research_dialect: None, tmp_path: Path) -> None:
    r"""The installed dialect governs every frontend, not only the session.

    The session preparser, the importer, and the build frontend read the
    same ``.sage`` source; the dialect — registered extensions and the
    product mode — is one setting, so the source has one meaning.  A
    frontend lowering with its own settings would hand back a Python
    ``set`` where the session hands back a Sage ``Set`` (no
    ``cardinality``), or refuse ``2k`` where the session multiplies, and
    the same file would change meaning with the road taken to it.
    """
    meanings = {
        "session": _session_meaning(DIALECT_SOURCE),
        "imported": _imported_meaning(DIALECT_SOURCE, tmp_path / "imported", "frontends_dialect"),
        "built": _built_meaning(DIALECT_SOURCE, tmp_path / "building", "frontends_dialect"),
    }
    for frontend, meaning in meanings.items():
        assert meaning["double"](21) == 42, f"{frontend}: 2k is twice k under the dialect"
        assert meaning["PAIR"].cardinality() == 2, f"{frontend}: {{1, 3}} is a Sage Set under the dialect"
    assert meanings["session"]["PAIR"] == meanings["imported"]["PAIR"] == meanings["built"]["PAIR"]


def test_every_frontend_refuses_what_the_dialect_refuses(core_defaults: None, tmp_path: Path) -> None:
    r"""With implicit multiplication off, ``2x`` is a syntax error everywhere.

    Sage's own default refuses ``2x`` and the session starts there.  The
    importer and the build frontend read the same setting: a frontend
    that quietly multiplied would give the one source a second meaning,
    and would do it silently.
    """
    source = "y = 2x\n"
    from sageparse.preparser import preparse_file

    with pytest.raises(SyntaxError):
        compile(preparse_file(source), "<session>", "exec")
    with pytest.raises(SyntaxError):
        _imported_meaning(source, tmp_path / "imported", "frontends_refused")
    with pytest.raises(SyntaxError):
        _built_meaning(source, tmp_path / "building", "frontends_refused")


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
