r"""``.sage`` files as ordinary Python modules.

Importing this module makes ``.sage`` importable::

    import sageparse.preparser.importer

    import mypkg.algorithms          # mypkg/algorithms.sage
    from mypkg.algorithms import foo

Sage treats ``.sage`` as a script language: ``sage foo.sage`` writes a
``foo.sage.py`` beside it, and ``load()`` executes a file into an
existing namespace.  Neither produces a module, so using Sage's own
syntax disqualifies a file from being library source.  Nothing about
that is fundamental — Python's import machinery is documented as
extensible to other source languages, and the compiler already does the
only Sage-specific part.

So this owns nothing but source recognition and lowering.  Python keeps
module semantics: :class:`~importlib.machinery.ModuleSpec`,
``sys.modules``, packages, relative imports, cycles, and ``reload`` all
behave as they do for ``.py``, because :class:`SageLoader` subclasses
:class:`importlib.machinery.SourceFileLoader` and overrides only
``source_to_code``.  Bytecode caching comes with it, so ``__pycache__``
holds the compiled form and a file is re-lowered only when it changes.

A lowered module is given the compiler's runtime prelude — the names the
lowering emits, and no more.  It is not given ``sage.all``: a module
states its own mathematical imports, exactly as a ``.py`` module in Sage
does.  ``__init__.sage`` makes a package.
"""

from __future__ import annotations

import sys
from ast import Expression, Interactive, Module
from collections.abc import Buffer, Sequence
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, SourceFileLoader
from importlib.util import spec_from_file_location
from os import PathLike, fspath
from pathlib import Path
from types import CodeType, ModuleType

from sageparse import lower
from sageparse.preparser import runtime_namespace

SUFFIX = ".sage"


class SageLoader(SourceFileLoader):
    """Load a ``.sage`` file as a module, lowering it to Python first.

    ``SourceFileLoader`` is CPython's own pairing of a file loader with a
    source loader, so subclassing it brings the file access, the bytecode
    cache, and the module protocol together already reconciled.
    """

    @staticmethod
    def source_to_code(data: Buffer | str | Module | Expression | Interactive, path: bytes | str | PathLike[str] = "<string>", *, _optimize: int = -1) -> CodeType:
        # The supertypes accept an AST, which is meaningless here: Sage
        # source has to be lowered before there is a tree CPython can
        # read. Refusing loudly beats compiling something unlowered.
        assert isinstance(data, str | bytes | bytearray | memoryview), f"Sage source must be text, not {type(data).__name__}"
        source = data if isinstance(data, str) else bytes(data).decode("utf-8")
        filename = path.decode("utf-8") if isinstance(path, bytes) else fspath(path)
        # `filename` is the .sage file, so a traceback names the author's
        # file; the lowerings preserve line geometry, so the line numbers
        # in it are the author's lines too.
        return compile(lower(source).python, filename, "exec", dont_inherit=True, optimize=_optimize)

    def exec_module(self, module: ModuleType) -> None:
        prelude = runtime_namespace()
        module.__dict__.update({name: value for name, value in prelude.items() if name not in module.__dict__})
        super().exec_module(module)
        module.__dict__["__sageparse_runtime_names__"] = frozenset(
            name for name, value in prelude.items()
            if module.__dict__.get(name) is value
        )


class SageFinder(MetaPathFinder):
    r"""Find ``foo.sage`` and ``foo/__init__.sage`` on the import path.

    Registered at the *front* of ``sys.meta_path``, and it declines
    anything Python can already import.  Running last would not work:
    the default finder turns any directory into a namespace package, so
    a package whose ``__init__`` is ``.sage`` would resolve to an empty
    namespace before this was ever consulted.

    Precedence therefore has to be explicit instead of positional.  Each
    path entry is checked for ``.py`` first and skipped if it has one, so
    a package that ships a generated ``foo.py`` beside its ``foo.sage``
    source imports the built artifact, which is what a release install
    should do.
    """

    def find_spec(self, fullname: str, path: Sequence[str] | None = None, target: ModuleType | None = None) -> ModuleSpec | None:
        tail = fullname.rpartition(".")[2]
        for entry in sys.path if path is None else path:
            directory = Path(entry or ".")
            package = directory / tail
            if (package / "__init__.py").is_file():
                return None
            if (package / f"__init__{SUFFIX}").is_file():
                return self._spec(fullname, package / f"__init__{SUFFIX}", [str(package)])
            if (directory / f"{tail}.py").is_file():
                return None
            module = directory / f"{tail}{SUFFIX}"
            if module.is_file():
                return self._spec(fullname, module, None)
        return None

    @staticmethod
    def _spec(fullname: str, source: Path, locations: list[str] | None) -> ModuleSpec | None:
        return spec_from_file_location(
            fullname,
            str(source),
            loader=SageLoader(fullname, str(source)),
            submodule_search_locations=locations,
        )


def install() -> None:
    """Teach the running interpreter to import ``.sage`` files. Idempotent."""
    if not any(isinstance(finder, SageFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, SageFinder())


def uninstall() -> None:
    """Undo :func:`install`, for a test that needs the interpreter back."""
    sys.meta_path[:] = [finder for finder in sys.meta_path if not isinstance(finder, SageFinder)]


install()
