# tree-sitter-sage

[Sage (SageMath)](https://www.sagemath.org/) grammar for [tree-sitter](https://github.com/tree-sitter/tree-sitter), maintained as a dialect fork of [tree-sitter-python](https://github.com/tree-sitter/tree-sitter-python).

Sage source is Python plus a small syntax delta.
This grammar adds exactly that delta and nothing else:

- `sage_generator_assignment` — `R.<x, y> = QQ[]`, `F.<b>, f, g = S.field_extension()`

- `sage_symbolic_function_assignment` — `f(x, y) = x^2 - y`

- `sage_generator_access` — `R.0`

- `sage_ellipsis_span` / `sage_ellipsis` — `[1..5]`, `[1, 3..9]`, `(a..b)`, `[1, .., n]`

- `sage_raw_literal` — `5r`, `2.5R`, `0xEAr`, `10jr`

- `sage_empty_subscript` — `QQ[]`

- `^` is exponentiation (right-associative, power precedence); `^^`/`^^=` are xor

- attribute calls on numeric literals — `1.sqrt()`, `15.10.sqrt()`

- the `float` token lives in the external scanner so that `[1..5]`, `1.sqrt()`, and `2.5r` lex correctly with one character of lookahead

Ordinary Python syntax is inherited from upstream and kept unpatched: general Python fixes belong in tree-sitter-python and arrive here by merging upstream.
The full upstream corpus passes unchanged.

## Feature modules

The grammar is composed at build time from a base definition (Sage's default preparser surface: generator assignments, symbolic functions, `R.0`, ellipsis ranges, raw literals, `^`/`^^`, literal method calls) plus feature modules under `features/`, each a self-contained set of rules and choice-rule extensions.
Implicit multiplication — optional in Sage itself — is the first such module.

Develop a feature in isolation:

```
SAGE_FEATURES=core tree-sitter generate        # base only
SAGE_FEATURES=implicit_multiplication tree-sitter generate
tree-sitter generate                           # everything (shipped)
```

Each feature keeps its corpus tests in `test/corpus/<feature>.txt`; when testing a reduced build, exclude the absent features' tests with `tree-sitter test -e '<feature name>'`. The shipped artifacts (`src/`, bindings, WASM) are always the full composition.

Lowering in `sageparse` is node-driven, so compiler behavior follows whatever the built grammar recognizes; semantics-only dialect notation (no new syntax) skips the grammar entirely and ships as compiler extension rule tables like `sageparse.extensions.research`.

## sageparse — the preparser

This repo ships the complete replacement for Sage's preparser, not a component of one.
Sage preparses with regular expressions over source text; `sageparse` parses, lowers from the tree, and lets CPython compile the result.
A session installs it with one import and no other code:

```
import sageparse.preparser            # the Sage dialect
import sageparse.preparser.research   # the same, plus research notation
```

Importing installs `preparse`, `preparse_file`, and the `time`, `sage:`/`>>>`, `...`, and `load`/`attach` line protocols over `sage.repl.preparse` and `sage.repl.interpreter`.  `implicit_multiplication()` is a session setting, off by default as in Sage; with it off a juxtaposition reaches CPython as the author wrote it and fails there.

Non-standard notation is optional and modular.
Each extension is one rule table under `sageparse.extensions`, plus the module under `sageparse.preparser` that registers it into a live session.
`sageparse.extensions.research` is the catch-all for non-standard notation migrated upstream out of research use; it currently holds the set-builder forms.

The boundary is what a rule can decide from source text alone.
`^` is exponentiation and lowers to `**`; what `R**n` then *means* is the ring's `__pow__`, so a session that wants `R^n` to build its own module overrides `__pow__` on that parent's class and needs nothing from the preparser.
Lowering `^` to a function call instead would force this repo to reassociate around implicit products by hand, because the grammar's tree is not the precedence — `x^2 y` is one product node.
Textual `**` avoids the whole problem: CPython re-parses and supplies the grouping.

## `.sage` as library source

Sage treats `.sage` as a script language: `sage foo.sage` writes a `foo.sage.py` beside it, and `load()` executes a file into an existing namespace.
Neither makes a module, so using Sage's own syntax disqualifies a file from being library source.
That is missing integration, not a language limit, and `sageparse` supplies it two ways over the one compiler.

At import time:

```python
import sageparse.preparser.importer

import mypkg.algorithms          # mypkg/algorithms.sage
from mypkg.algorithms import foo
```

Python keeps module semantics — `ModuleSpec`, `sys.modules`, packages via `__init__.sage`, relative imports, cycles, `reload`, and `__pycache__` — because the loader subclasses `SourceFileLoader` and overrides exactly two of its steps: `source_to_code` lowers the source, and `exec_module` seeds the module namespace with the runtime prelude before the body runs, then records the bindings the body left standing as `__sageparse_runtime_names__`. Seeding the namespace instead of prepending source is what preserves line geometry, so a traceback names the `.sage` file *and* the author's line.

At build time:

```python
from sageparse.build import lower_tree
lower_tree(Path("src"), Path("build"))     # algorithms.sage -> algorithms.py
```

The `.sage` file stays the source nobody generates and the `.py` an artifact nobody edits.
A built module carries import lines for only the runtime names its own lowering emitted, so it depends on the Sage libraries it uses and not on this compiler, the preparser, or the REPL layer.
Its positions are its own, since the prelude has to precede the module body — which is why the importer exists for development and the artifact for release.

Neither frontend gets `sage.all`. A script may reasonably want every Sage name in scope; a library module states its own mathematical imports.

Three layers, three dependencies: the grammar recognizes, `sageparse` lowers with no Sage import at all, and `sageparse.preparser` is the only part that touches a Sage session.
Editors and language servers use the middle layer without a Sage installation.
