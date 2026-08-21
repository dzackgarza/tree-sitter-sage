r"""Lower a ``.sage`` source tree to importable Python, ahead of time.

The second frontend over the same compiler.  Where
:mod:`sageparse.preparser.importer` lowers at import time, this lowers
once into ``.py`` files, so a wheel can ship ordinary Python built from
canonical ``.sage`` source::

    src/mypkg/algorithms.sage   ->   build/mypkg/algorithms.py

That is the ``.pyx``/``.c`` arrangement: the ``.sage`` file is the
source nobody generates, the ``.py`` is an artifact nobody edits, and
neither is checked in twice.

The dependency direction is the reason to prefer this for distribution.
A built module carries import lines for the names its own lowering
emitted, so it needs the Sage libraries it actually uses and does not
need this compiler, or the preparser, or the REPL layer, at run time.
Only building needs them.

Source locations are the one thing this frontend gives up.  The prelude
has to bind its names before module-level code runs, so it goes at the
top and shifts every following line; a traceback in a built module
reports positions in the generated ``.py``.  That is the same trade a
built Cython module makes, and it is why the importer exists for
development: work against ``.sage`` locations, ship the artifact.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sageparse import lower
from sageparse.preparser import runtime_imports

SUFFIX = ".sage"

_HEADER = "# Generated from {source} by sageparse. Do not edit; edit the .sage source.\n"


def _prelude(python: str) -> str:
    """Import lines for exactly the runtime names this output references.

    The names come off the parse tree, not out of the text.  A word
    search cannot tell a reference from prose, so a module whose
    docstring said "matrix" used to gain a Sage matrix dependency for
    saying it -- which contradicts the whole reason to build ahead of
    time.  ``ast`` already draws that line, and draws it in the same
    place Python does.
    """
    referenced = {node.id for node in ast.walk(ast.parse(python)) if isinstance(node, ast.Name)}
    imports = runtime_imports()
    names = sorted(referenced & imports.keys())
    if not names:
        return ""
    bindings = "".join(f"{imports[name]}\n" for name in names)
    return f"{bindings}__sageparse_runtime_names__ = frozenset({names!r})\n"


def lower_source(source: str) -> str:
    r"""Lower Sage source to a standalone Python module.

    The prelude must precede the module body, because module-level code
    calls the names it binds while the module is executing.  That shifts
    the body down by the number of prelude lines, which is why a built
    module's positions are its own and not the ``.sage`` file's.
    """
    lowered = lower(source).python
    prelude = _prelude(lowered)
    if not prelude:
        return lowered
    return f"{prelude}{lowered}"


def lower_file(source: Path, target: Path) -> Path:
    """Lower one ``.sage`` file to ``target``, creating parent directories."""
    assert source.suffix == SUFFIX, f"not a Sage source file: {source}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_HEADER.format(source=source.name) + lower_source(source.read_text()))
    return target


def lower_tree(source_root: Path, target_root: Path) -> list[Path]:
    r"""Lower every ``.sage`` file under ``source_root`` into ``target_root``.

    Returns the files written.  Nothing else is copied: a build backend
    already knows how to place package data, and guessing here would put
    this in the business of packaging rather than compiling.
    """
    assert source_root.is_dir(), f"not a directory: {source_root}"
    written = []
    for source in sorted(source_root.rglob(f"*{SUFFIX}")):
        relative = source.relative_to(source_root).with_suffix(".py")
        written.append(lower_file(source, target_root / relative))
    return written
