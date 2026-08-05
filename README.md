# tree-sitter-sage

[Sage (SageMath)](https://www.sagemath.org/) grammar for
[tree-sitter](https://github.com/tree-sitter/tree-sitter), maintained as a
dialect fork of
[tree-sitter-python](https://github.com/tree-sitter/tree-sitter-python).

Sage source is Python plus a small syntax delta. This grammar adds exactly
that delta and nothing else:

- `sage_generator_assignment` — `R.<x, y> = QQ[]`, `F.<b>, f, g = S.field_extension()`
- `sage_symbolic_function_assignment` — `f(x, y) = x^2 - y`
- `sage_generator_access` — `R.0`
- `sage_ellipsis_span` / `sage_ellipsis` — `[1..5]`, `[1, 3..9]`, `(a..b)`, `[1, .., n]`
- `sage_raw_literal` — `5r`, `2.5R`, `0xEAr`, `10jr`
- `sage_empty_subscript` — `QQ[]`
- `^` is exponentiation (right-associative, power precedence); `^^`/`^^=` are xor
- attribute calls on numeric literals — `1.sqrt()`, `15.10.sqrt()`
- the `float` token lives in the external scanner so that `[1..5]`,
  `1.sqrt()`, and `2.5r` lex correctly with one character of lookahead

Ordinary Python syntax is inherited from upstream and kept unpatched: general
Python fixes belong in tree-sitter-python and arrive here by merging upstream.
The full upstream corpus passes unchanged.

## Feature modules

The grammar is composed at build time from a base definition (Sage's
default preparser surface: generator assignments, symbolic functions,
`R.0`, ellipsis ranges, raw literals, `^`/`^^`, literal method calls)
plus feature modules under `features/`, each a self-contained set of
rules and choice-rule extensions.  Implicit multiplication — optional
in Sage itself — is the first such module.

Develop a feature in isolation:

    SAGE_FEATURES=core tree-sitter generate        # base only
    SAGE_FEATURES=implicit_multiplication tree-sitter generate
    tree-sitter generate                           # everything (shipped)

Each feature keeps its corpus tests in
`test/corpus/<feature>.txt`; when testing a reduced build, exclude the
absent features' tests with `tree-sitter test -e '<feature name>'`.
The shipped artifacts (`src/`, bindings, WASM) are always the full
composition.

Lowering in `sagepython` is node-driven, so compiler behavior follows
whatever the built grammar recognizes; semantics-only dialect notation
(no new syntax) skips the grammar entirely and ships as compiler
extension rule tables like `sagepython.research`.
