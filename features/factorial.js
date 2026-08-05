/**
 * Postfix factorial (sage#30982): `5!` lowers to `factorial(5)`.
 *
 * The bang must be adjacent to its argument (`5 !` stays an error) and
 * loses lexically to the longer tokens that also start with `!`:
 * `5!=3` stays a comparison, `f"{x!r}"` keeps its conversion.
 */

// Matches the base grammar's PREC table; postfix binds like a call.
const PREC = { call: 22 };

module.exports = {
  name: 'factorial',

  rules: {
    sage_factorial: $ => prec.left(PREC.call, seq(
      field('argument', $.primary_expression),
      token.immediate('!'),
    )),
  },

  extend: {
    primary_expression: ($) => $.sage_factorial,
  },
};
