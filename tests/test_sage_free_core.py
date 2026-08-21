r"""The compiler core imports no Sage, transitively.

The package docstring promises that ``editors, linters, and language
servers lower source without a Sage installation``, which holds exactly
as long as no module reachable from :mod:`sageparse` or
:mod:`sageparse.extensions` imports ``sage``.  One convenience import
added to the core would break every language server using this package,
and would do it silently — the author has Sage, so nothing local fails.

This used to be enforced by letting the Sage-requiring test modules skip
themselves, so the whole suite could run in a Sage-free interpreter.
That proved the claim only as a side effect of the tests being optional,
and made Sage look optional to a Sage preparser.  The claim is about the
import graph, so it is checked on the import graph, and the tests stay
mandatory.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src" / "sageparse"

# Sage is the whole point of the other half of the package; these are the
# modules that may import it.  Everything reachable from the core may not.
SAGE_OWNING = {"sageparse.runtime", "sageparse.preparser"}


def _module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE.parent).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts)


def _imports(tree: ast.Module) -> set[str]:
    """Every module named by an import in ``tree``, absolute form only."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _reachable_from(roots: list[str]) -> dict[str, set[str]]:
    """First-party modules reachable from ``roots``, mapped to their imports."""
    by_name = {_module_name(path): path for path in SOURCE.rglob("*.py")}
    graph: dict[str, set[str]] = {}
    pending = [name for name in roots if name in by_name]
    while pending:
        name = pending.pop()
        if name in graph:
            continue
        imported = _imports(ast.parse(by_name[name].read_text()))
        graph[name] = imported
        for target in imported:
            # `from sageparse.extensions import research` names the module;
            # `from sageparse import lower` names an attribute, not one.
            if target in by_name and target not in graph:
                pending.append(target)
    return graph


def _core_roots() -> list[str]:
    """The core, plus every rule table.

    An extension is selected by name and handed to ``lower``; nothing
    imports it from the package, so ``extensions/__init__`` is empty and
    following imports alone would never reach a rule table.  Seeding them
    from disk is what keeps a new extension covered the day it lands.
    """
    tables = [_module_name(path) for path in (SOURCE / "extensions").rglob("*.py")]
    return ["sageparse", *tables]


def test_the_core_and_its_rule_tables_import_no_sage() -> None:
    graph = _reachable_from(_core_roots())
    assert graph, "the core module graph is empty — the walk found nothing to check"
    offenders = {
        name: sorted(target for target in imported if target == "sage" or target.startswith("sage."))
        for name, imported in graph.items()
        if any(target == "sage" or target.startswith("sage.") for target in imported)
    }
    assert offenders == {}, f"the core reaches Sage: {offenders}"


def test_the_walk_reaches_the_extension_rule_tables() -> None:
    # Without this the test above passes by walking nothing interesting.
    # It has already earned its place once: `extensions/__init__` imports
    # nothing, so following imports alone reached no rule table at all.
    graph = _reachable_from(_core_roots())
    assert "sageparse.extensions.research" in graph
    assert "sageparse" in graph


def test_the_sage_owning_half_is_outside_that_graph() -> None:
    # The split is only meaningful if the modules that do import Sage are
    # genuinely unreachable from the core rather than absent by accident.
    graph = _reachable_from(_core_roots())
    assert SAGE_OWNING.isdisjoint(graph)
    reached = _reachable_from(sorted(SAGE_OWNING))
    assert any(any(target.startswith("sage.") for target in imported) for imported in reached.values())
