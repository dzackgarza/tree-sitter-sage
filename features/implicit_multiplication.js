/**
 * Implicit multiplication (Sage preparser level 5): `2x`, `a b c`,
 * `(2y^2-4y+3)y`, `2sin(x)`, `f(a)b`.
 *
 * This is an optional feature in Sage itself (`implicit_multiplication()`
 * defaults to off), so it lives as a grammar feature module: developed and
 * tested in isolation, excluded from a build with
 * `SAGE_FEATURES=core tree-sitter generate`, and shipped enabled in the
 * default build.
 */

// Matches the base grammar's PREC table; a product binds like `*`.
const PREC = { times: 19 };

module.exports = {
  name: 'implicit_multiplication',

  rules: {
    // Implicit multiplication (Sage preparser level 5): `2x`, `a b c`,
    // `(2y^2-4y+3)y`, `2sin(x)`, `f(a)b`.  The left operand mirrors
    // Sage's rule table: numbers, names, parenthesis-closed
    // expressions, attributes, and generator accesses.  The right
    // operand is name-headed, so `f(x)` stays a call and string
    // juxtaposition stays concatenation.  Grammar keywords exclude
    // themselves.  Multiplication never crosses a line; the grammar
    // cannot see whitespace, so the compiler enforces that with node
    // positions.
    sage_implicit_product: $ => prec.left(PREC.times, prec.dynamic(-1, seq(
      // Every primary_expression alternative except keyword_identifier
      // (`await x`, `match p:` keep their expression/statement readings)
      // and the string nodes (juxtaposed strings stay concatenation).
      // Keep in sync with primary_expression when merging upstream.
      // Known shape caveat: `2^n x0` groups as 2^(n x0) in the tree; the
      // compiler's textual lowering (insert `*`, rewrite `^` to `**`)
      // still yields (2**n)*x0 under CPython's precedence.
      field('left', choice(
        $.await,
        $.binary_operator,
        $.identifier,
        $.integer,
        $.float,
        $.true,
        $.false,
        $.none,
        $.unary_operator,
        $.attribute,
        $.subscript,
        $.call,
        $.list,
        $.list_comprehension,
        $.dictionary,
        $.dictionary_comprehension,
        $.set,
        $.set_comprehension,
        $.tuple,
        $.parenthesized_expression,
        $.generator_expression,
        $.ellipsis,
        $.sage_generator_access,
        $.sage_raw_literal,
        $.sage_empty_subscript,
        $.sage_implicit_product,
      )),
      $._sage_juxtaposition,
      field('right', choice(
        $.identifier,
        $.call,
        $.attribute,
        $.subscript,
      )),
    ))),
  },

  extend: {
    primary_expression: ($) => $.sage_implicit_product,
  },
};
