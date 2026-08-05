/**
 * Version-number literals (sage#14384): `4.1.1` lowers to the int
 * tuple `(4, 1, 1)`, so version literals compare lexicographically.
 *
 * Lexically a version literal is a float followed by an immediate
 * dotted-digit tail.  Two-component numbers stay floats, and `R.0` on
 * names stays generator access; only a float base with three or more
 * dotted components reads as a version.  In the core build that shape
 * is `RealNumber('1.2').gen(3)`, a guaranteed runtime AttributeError,
 * so the feature claims no meaningful surface.
 */

module.exports = {
  name: 'version_literals',

  rules: {
    // The tail token swallows every remaining `.N` component at once,
    // so it wins over a single generator index by longest match; the
    // token precedence breaks the tie on the three-component case.
    sage_version_literal: $ => seq(
      $.float,
      token.immediate(prec(1, /(\.[0-9]+)+/)),
    ),
  },

  extend: {
    primary_expression: ($) => $.sage_version_literal,
  },
};
