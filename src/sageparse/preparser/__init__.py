r"""The Sage preparser, complete and installed by import.

``sageparse`` recognizes and lowers; this module is the replacement
itself — the entrypoints Sage calls, the frontend text protocols that
surround them, and the installation over Sage's own hooks.  Importing
the module installs it, so a session needs one line and no ceremony::

    import sageparse.preparser            # the Sage dialect
    import sageparse.preparser.research   # the same, plus research notation

``time``, ``sage:``/``>>>`` prompts, ``...`` continuations, and
``load``/``attach`` are line protocols, not language: they are handled
here as text, around the compiler.  Sage's ``_sage_const_`` hoisting was
a loop optimization rather than parsing, so inline wrapping replaces it.

Extensions in :mod:`sageparse.extensions` register their rule tables
with :func:`register_extension`; every later ``preparse`` applies them.
Only this package imports Sage — the core and the rule tables stay
importable in any Python environment.
"""

from __future__ import annotations

import builtins
import re
from collections.abc import Mapping

from sage.repl import interpreter as sage_interpreter
from sage.repl import preparse as sage_preparse
from sage.repl.load import load_wrap

from sageparse import LoweringRule, Products, lower
from sageparse.runtime import IMPORTS as _CORE_IMPORTS
from sageparse.runtime import NAMESPACE as _CORE_NAMESPACE

_native_preparse = sage_preparse.preparse
_native_preparse_file = sage_preparse.preparse_file

_TIME_STATEMENT = re.compile(r"^(\s*)time +(\S[^\n]*)$", re.MULTILINE)
_LOAD_ATTACH = re.compile(r"^(\s*)(load|attach) ([^(].*)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Dialect extensions
# ---------------------------------------------------------------------------

_extensions: list[Mapping[str, LoweringRule]] = []
_runtime: dict[str, object] = dict(_CORE_NAMESPACE)
_imports: dict[str, str] = dict(_CORE_IMPORTS)


def register_extension(
    rules: Mapping[str, LoweringRule],
    runtime: Mapping[str, object] | None = None,
    imports: Mapping[str, str] | None = None,
) -> None:
    r"""Add a lowering rule table to every later ``preparse``.

    ``runtime`` maps each name the table's lowerings emit to the object
    that name must resolve to; an imported ``.sage`` module gets that
    mapping as its prelude.  ``imports`` gives the same bindings as
    source lines, which is what a module lowered ahead of time carries
    instead.  Resolution-based tools read the keys from
    :func:`runtime_names`.  Registering the same table twice is a no-op,
    so a module can register at import and be imported repeatedly.
    """
    if rules in _extensions:
        return
    _extensions.append(rules)
    if runtime is not None:
        _runtime.update(runtime)
    if imports is not None:
        _imports.update(imports)


def runtime_namespace() -> dict[str, object]:
    """A fresh prelude for one lowered module: emitted names to objects."""
    return dict(_runtime)


def runtime_imports() -> dict[str, str]:
    """Emitted name to the import statement that binds it, for built modules."""
    return dict(_imports)


def runtime_names() -> tuple[str, ...]:
    """Names the installed dialect emits into generated Python."""
    return tuple(_runtime)


# ---------------------------------------------------------------------------
# Implicit multiplication, as a session setting
# ---------------------------------------------------------------------------

_products: Products = "explicit"


def implicit_multiplication(enable: bool = True) -> bool:
    r"""Turn implicit multiplication on or off, and report the state.

    Sage's own default is off, so this replacement starts there: with it
    off, ``2x`` reaches CPython unchanged and fails as the syntax error
    it is, at the author's own position.
    """
    global _products
    previous = _products == "implicit"
    _products = "implicit" if enable else "explicit"
    return previous


# ---------------------------------------------------------------------------
# The installed dialect, applied to a whole module
# ---------------------------------------------------------------------------


def lower_module(source: str) -> str:
    r"""Lower one whole ``.sage`` module under the installed dialect.

    The importer and the build frontend compile through this, and
    :func:`preparse` applies the same registered extensions and product
    mode cell by cell, so one source has one meaning no matter which
    frontend reads it.  The line protocols stay out: a module is
    language, not a session transcript.
    """
    return lower(source, products=_products, extensions=tuple(_extensions)).python


# ---------------------------------------------------------------------------
# Line protocols around the compiler
# ---------------------------------------------------------------------------


def _strip_prompts(line: str) -> str:
    for prompt in ("sage:", ">>>"):
        if line.startswith(prompt):
            return line[len(prompt) :].lstrip()
    return line


def _wrap_time_statements(source: str) -> str:
    return _TIME_STATEMENT.sub(
        lambda match: (
            f"{match.group(1)}__time__ = cputime(); __wall__ = walltime(); "
            f"{match.group(2)}; "
            'print("Time: CPU {:.2f} s, Wall: {:.2f} s".format(cputime(__time__), walltime(__wall__)))'
        ),
        source,
    )


def preparse(
    line: str,
    reset: bool = True,
    do_time: bool = False,
    ignore_prompts: bool = False,
    numeric_literals: bool = True,
) -> str:
    r"""Transform one cell of Sage source into ordinary Python source.

    The signature matches ``sage.repl.preparse.preparse``; ``reset`` is
    accepted for compatibility but unused — every call transforms a
    whole, lexically complete cell.
    """
    del reset
    if line.lstrip().startswith("..."):
        cut = line.find("...") + 3
        return line[:cut] + preparse(line[cut:], do_time=do_time, ignore_prompts=ignore_prompts, numeric_literals=numeric_literals)
    if ignore_prompts:
        line = _strip_prompts(line)
    if do_time:
        line = _wrap_time_statements(line)
    return lower(
        line,
        numbers="wrapped" if numeric_literals else "raw",
        products=_products,
        extensions=tuple(_extensions),
    ).python


def preparse_file(contents: str, globals: dict | None = None, numeric_literals: bool = True) -> str:
    r"""Preparse the contents of a ``.sage`` file.

    The signature matches ``sage.repl.preparse.preparse_file``.  Bare
    ``load``/``attach`` directives are wrapped exactly as Sage wraps
    them, and the ``time`` keyword is active.  ``globals`` and
    ``numeric_literals`` are accepted for the contract and unused: they
    served Sage's ``_sage_const_`` hoisting, which inline wrapping
    replaces without a change in meaning.
    """
    del globals, numeric_literals
    assert isinstance(contents, str), "preparse_file expects a string"
    lines: list[str] = []
    start = 0
    for directive in _LOAD_ATTACH.finditer(contents):
        lines += preparse(contents[start : directive.start()], do_time=True).splitlines()
        lines.append(directive.group(1) + load_wrap(directive.group(3), directive.group(2) == "attach"))
        start = directive.end()
    lines += preparse(contents[start:], do_time=True).splitlines()
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install() -> None:
    r"""Replace Sage's preparser entrypoints with this one.

    Idempotent, and refuses to install over a third party: a session
    that already routes preparsing somewhere else is a state this module
    cannot restore, so it says so rather than overwriting it.
    """
    builtins.__dict__["implicit_multiplication"] = implicit_multiplication
    if sage_preparse.preparse is preparse and sage_interpreter.preparse is preparse and sage_preparse.preparse_file is preparse_file:
        return
    if not (sage_preparse.preparse is _native_preparse and sage_interpreter.preparse is _native_preparse and sage_preparse.preparse_file is _native_preparse_file):
        raise RuntimeError("Sage's preparser entrypoints are not in an installable state")
    sage_preparse.preparse = preparse
    sage_interpreter.preparse = preparse
    sage_preparse.preparse_file = preparse_file


install()
