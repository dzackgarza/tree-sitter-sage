/**
 * Matrix literals (sage#12354): `[1, 2; 3, 4]` lowers to
 * `matrix([[1, 2], [3, 4]])`.
 *
 * At least one semicolon distinguishes a matrix from a list; the GLR
 * parser carries both readings until it sees one.  Subscripts are
 * unaffected: `a[1; 2]` stays an error.
 */

const commaSep1 = (rule) => seq(rule, repeat(seq(',', rule)));

module.exports = {
  name: 'matrix_literals',

  rules: {
    sage_matrix_literal: $ => seq(
      '[',
      field('row', $.sage_matrix_row),
      repeat1(seq(';', field('row', $.sage_matrix_row))),
      ']',
    ),

    sage_matrix_row: $ => commaSep1($.expression),
  },

  extend: {
    primary_expression: ($) => $.sage_matrix_literal,
  },

  conflicts: ($) => [
    [$.sage_matrix_row, $._collection_elements],
  ],
};
