#include "tree_sitter/array.h"
#include "tree_sitter/parser.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <string.h>

enum TokenType {
    NEWLINE,
    INDENT,
    DEDENT,
    STRING_START,
    STRING_CONTENT,
    ESCAPE_INTERPOLATION,
    STRING_END,
    COMMENT,
    CLOSE_PAREN,
    CLOSE_BRACKET,
    CLOSE_BRACE,
    EXCEPT,
    FLOAT,
    SAGE_JUXTAPOSITION,
};

typedef enum {
    SingleQuote = 1 << 0,
    DoubleQuote = 1 << 1,
    BackQuote = 1 << 2,
    Raw = 1 << 3,
    Format = 1 << 4,
    Triple = 1 << 5,
    Bytes = 1 << 6,
} Flags;

typedef struct {
    char flags;
} Delimiter;

static inline Delimiter new_delimiter() { return (Delimiter){0}; }

static inline bool is_format(Delimiter *delimiter) { return delimiter->flags & Format; }

static inline bool is_raw(Delimiter *delimiter) { return delimiter->flags & Raw; }

static inline bool is_triple(Delimiter *delimiter) { return delimiter->flags & Triple; }

static inline bool is_bytes(Delimiter *delimiter) { return delimiter->flags & Bytes; }

static inline int32_t end_character(Delimiter *delimiter) {
    if (delimiter->flags & SingleQuote) {
        return '\'';
    }
    if (delimiter->flags & DoubleQuote) {
        return '"';
    }
    if (delimiter->flags & BackQuote) {
        return '`';
    }
    return 0;
}

static inline void set_format(Delimiter *delimiter) { delimiter->flags |= Format; }

static inline void set_raw(Delimiter *delimiter) { delimiter->flags |= Raw; }

static inline void set_triple(Delimiter *delimiter) { delimiter->flags |= Triple; }

static inline void set_bytes(Delimiter *delimiter) { delimiter->flags |= Bytes; }

static inline void set_end_character(Delimiter *delimiter, int32_t character) {
    switch (character) {
        case '\'':
            delimiter->flags |= SingleQuote;
            break;
        case '"':
            delimiter->flags |= DoubleQuote;
            break;
        case '`':
            delimiter->flags |= BackQuote;
            break;
        default:
            assert(false);
    }
}

typedef struct {
    Array(uint16_t) indents;
    Array(Delimiter) delimiters;
    bool inside_interpolated_string;
} Scanner;

static inline void advance(TSLexer *lexer) { lexer->advance(lexer, false); }

static inline void skip(TSLexer *lexer) { lexer->advance(lexer, true); }


static inline bool is_id_start(int32_t c) {
    return c == '_' || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z') || c > 127;
}

static inline bool is_id_continue(int32_t c) {
    return is_id_start(c) || ('0' <= c && c <= '9');
}

bool tree_sitter_sage_external_scanner_scan(void *payload, TSLexer *lexer, const bool *valid_symbols) {
    Scanner *scanner = (Scanner *)payload;

    bool error_recovery_mode = valid_symbols[STRING_CONTENT] && valid_symbols[INDENT];
    bool within_brackets = valid_symbols[CLOSE_BRACE] || valid_symbols[CLOSE_PAREN] || valid_symbols[CLOSE_BRACKET];

    bool advanced_once = false;
    if (valid_symbols[ESCAPE_INTERPOLATION] && scanner->delimiters.size > 0 &&
        (lexer->lookahead == '{' || lexer->lookahead == '}') && !error_recovery_mode) {
        Delimiter *delimiter = array_back(&scanner->delimiters);
        if (is_format(delimiter)) {
            lexer->mark_end(lexer);
            bool is_left_brace = lexer->lookahead == '{';
            advance(lexer);
            advanced_once = true;
            if ((lexer->lookahead == '{' && is_left_brace) || (lexer->lookahead == '}' && !is_left_brace)) {
                advance(lexer);
                lexer->mark_end(lexer);
                lexer->result_symbol = ESCAPE_INTERPOLATION;
                return true;
            }
            return false;
        }
    }

    if (valid_symbols[STRING_CONTENT] && scanner->delimiters.size > 0 && !error_recovery_mode) {
        Delimiter *delimiter = array_back(&scanner->delimiters);
        int32_t end_char = end_character(delimiter);
        bool has_content = advanced_once;
        while (lexer->lookahead) {
            if ((advanced_once || lexer->lookahead == '{' || lexer->lookahead == '}') && is_format(delimiter)) {
                lexer->mark_end(lexer);
                lexer->result_symbol = STRING_CONTENT;
                return has_content;
            }
            if (lexer->lookahead == '\\') {
                if (is_raw(delimiter)) {
                    // Step over the backslash.
                    advance(lexer);
                    // Step over any escaped quotes.
                    if (lexer->lookahead == end_character(delimiter) || lexer->lookahead == '\\') {
                        advance(lexer);
                    }
                    // Step over newlines
                    if (lexer->lookahead == '\r') {
                        advance(lexer);
                        if (lexer->lookahead == '\n') {
                            advance(lexer);
                        }
                    } else if (lexer->lookahead == '\n') {
                        advance(lexer);
                    }
                    continue;
                }
                if (is_bytes(delimiter)) {
                    lexer->mark_end(lexer);
                    advance(lexer);
                    if (lexer->lookahead == 'N' || lexer->lookahead == 'u' || lexer->lookahead == 'U') {
                        // In bytes string, \N{...}, \uXXXX and \UXXXXXXXX are
                        // not escape sequences
                        // https://docs.python.org/3/reference/lexical_analysis.html#string-and-bytes-literals
                        advance(lexer);
                    } else {
                        lexer->result_symbol = STRING_CONTENT;
                        return has_content;
                    }
                } else {
                    lexer->mark_end(lexer);
                    lexer->result_symbol = STRING_CONTENT;
                    return has_content;
                }
            } else if (lexer->lookahead == end_char) {
                if (is_triple(delimiter)) {
                    lexer->mark_end(lexer);
                    advance(lexer);
                    if (lexer->lookahead == end_char) {
                        advance(lexer);
                        if (lexer->lookahead == end_char) {
                            if (has_content) {
                                lexer->result_symbol = STRING_CONTENT;
                            } else {
                                advance(lexer);
                                lexer->mark_end(lexer);
                                array_pop(&scanner->delimiters);
                                lexer->result_symbol = STRING_END;
                                scanner->inside_interpolated_string = false;
                            }
                            return true;
                        }
                        lexer->mark_end(lexer);
                        lexer->result_symbol = STRING_CONTENT;
                        return true;
                    }
                    lexer->mark_end(lexer);
                    lexer->result_symbol = STRING_CONTENT;
                    return true;
                }
                if (has_content) {
                    lexer->result_symbol = STRING_CONTENT;
                } else {
                    advance(lexer);
                    array_pop(&scanner->delimiters);
                    lexer->result_symbol = STRING_END;
                    scanner->inside_interpolated_string = false;
                }
                lexer->mark_end(lexer);
                return true;

            } else if (lexer->lookahead == '\n' && has_content && !is_triple(delimiter)) {
                return false;
            }
            advance(lexer);
            has_content = true;
        }
    }

    lexer->mark_end(lexer);

    bool found_end_of_line = false;
    uint16_t indent_length = 0;
    int32_t first_comment_indent_length = -1;
    for (;;) {
        if (lexer->lookahead == '\n') {
            found_end_of_line = true;
            indent_length = 0;
            skip(lexer);
        } else if (lexer->lookahead == ' ') {
            indent_length++;
            skip(lexer);
        } else if (lexer->lookahead == '\r' || lexer->lookahead == '\f') {
            indent_length = 0;
            skip(lexer);
        } else if (lexer->lookahead == '\t') {
            indent_length += 8;
            skip(lexer);
        } else if (lexer->lookahead == '#' && (valid_symbols[INDENT] || valid_symbols[DEDENT] ||
                                               valid_symbols[NEWLINE] || valid_symbols[EXCEPT])) {
            // If we haven't found an EOL yet,
            // then this is a comment after an expression:
            //   foo = bar # comment
            // Just return, since we don't want to generate an indent/dedent
            // token.
            if (!found_end_of_line) {
                return false;
            }
            if (first_comment_indent_length == -1) {
                first_comment_indent_length = (int32_t)indent_length;
            }
            while (lexer->lookahead && lexer->lookahead != '\n') {
                skip(lexer);
            }
            skip(lexer);
            indent_length = 0;
        } else if (lexer->lookahead == '\\') {
            skip(lexer);
            if (lexer->lookahead == '\r') {
                skip(lexer);
            }
            if (lexer->lookahead == '\n' || lexer->eof(lexer)) {
                skip(lexer);
            } else {
                return false;
            }
        } else if (lexer->eof(lexer)) {
            indent_length = 0;
            found_end_of_line = true;
            break;
        } else {
            break;
        }
    }

    if (found_end_of_line) {
        if (scanner->indents.size > 0) {
            uint16_t current_indent_length = *array_back(&scanner->indents);

            if (valid_symbols[INDENT] && indent_length > current_indent_length) {
                array_push(&scanner->indents, indent_length);
                lexer->result_symbol = INDENT;
                return true;
            }

            bool next_tok_is_string_start =
                lexer->lookahead == '\"' || lexer->lookahead == '\'' || lexer->lookahead == '`';

            if ((valid_symbols[DEDENT] ||
                 (!valid_symbols[NEWLINE] && !(valid_symbols[STRING_START] && next_tok_is_string_start) &&
                  !within_brackets)) &&
                indent_length < current_indent_length && !scanner->inside_interpolated_string &&

                // Wait to create a dedent token until we've consumed any
                // comments
                // whose indentation matches the current block.
                first_comment_indent_length < (int32_t)current_indent_length) {
                array_pop(&scanner->indents);
                lexer->result_symbol = DEDENT;
                return true;
            }
        }

        if (valid_symbols[NEWLINE] && !error_recovery_mode) {
            lexer->result_symbol = NEWLINE;
            return true;
        }
    }


    if (valid_symbols[SAGE_JUXTAPOSITION] && !error_recovery_mode && !found_end_of_line &&
        is_id_start(lexer->lookahead)) {
        // Zero-width marker: implicit multiplication binds only within a
        // line, immediately before a name-headed operand.  A reserved
        // keyword can never be a factor, and emitting the marker before
        // one would starve the branch that must shift the keyword.
        lexer->mark_end(lexer);
        char word[10] = {0};
        size_t length = 0;
        while (is_id_continue(lexer->lookahead)) {
            if (length < sizeof(word) - 1 && lexer->lookahead < 128) {
                word[length] = (char)lexer->lookahead;
            }
            length++;
            advance(lexer);
        }
        static const char *const reserved[] = {
            "and", "as", "assert", "async", "await", "break", "class",
            "continue", "def", "del", "elif", "else", "except", "finally",
            "for", "from", "global", "if", "import", "in", "is", "lambda",
            "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield",
        };
        if (length < sizeof(word)) {
            for (size_t i = 0; i < sizeof(reserved) / sizeof(reserved[0]); i++) {
                if (strcmp(word, reserved[i]) == 0) {
                    return false;
                }
            }
        }
        if (length <= 2 && (lexer->lookahead == '\'' || lexer->lookahead == '"')) {
            // A string prefix, not a factor: `y + r'a' r'b'` must stay
            // implicit string concatenation.  Returning false would
            // starve STRING_START (external, and only scanned once per
            // position), so emit it here with the flags read from the
            // already-consumed prefix, mirroring the block below.
            bool is_string_prefix = true;
            Delimiter delimiter = new_delimiter();
            for (size_t i = 0; i < length; i++) {
                char c = (char)(word[i] | 32);
                if (c == 'r') {
                    set_raw(&delimiter);
                } else if (c == 'b') {
                    set_bytes(&delimiter);
                } else if (c == 'f' || c == 't') {
                    set_format(&delimiter);
                } else if (c != 'u') {
                    is_string_prefix = false;
                    break;
                }
            }
            if (is_string_prefix) {
                if (!valid_symbols[STRING_START]) {
                    return false;
                }
                int32_t quote = lexer->lookahead;
                set_end_character(&delimiter, (char)quote);
                advance(lexer);
                lexer->mark_end(lexer);
                if (lexer->lookahead == quote) {
                    advance(lexer);
                    if (lexer->lookahead == quote) {
                        advance(lexer);
                        lexer->mark_end(lexer);
                        set_triple(&delimiter);
                    }
                }
                array_push(&scanner->delimiters, delimiter);
                lexer->result_symbol = STRING_START;
                scanner->inside_interpolated_string = is_format(&delimiter);
                return true;
            }
        }
        lexer->result_symbol = SAGE_JUXTAPOSITION;
        return true;
    }

    if (valid_symbols[FLOAT] &&
        (('0' <= lexer->lookahead && lexer->lookahead <= '9') || lexer->lookahead == '.')) {
        bool has_digits = false;
        bool is_float = false;
        while (('0' <= lexer->lookahead && lexer->lookahead <= '9') || lexer->lookahead == '_') {
            has_digits = true;
            advance(lexer);
        }
        if (lexer->lookahead == '.') {
            advance(lexer);
            if (lexer->lookahead == '.') {
                // A Sage range ellipsis follows (`1..5`); the dot is not part
                // of a float, so the integer and `..` tokens lex instead.
                return false;
            }
            if (!has_digits && !('0' <= lexer->lookahead && lexer->lookahead <= '9')) {
                return false; // a lone '.' operator
            }
            if (lexer->lookahead == 'e' || lexer->lookahead == 'E') {
                // `1.e5` is a float; `1.exp()` is attribute access on an
                // integer literal.  Only a digit sign distinguishes them.
                advance(lexer);
                if (lexer->lookahead == '+' || lexer->lookahead == '-') {
                    advance(lexer);
                }
                if (!('0' <= lexer->lookahead && lexer->lookahead <= '9')) {
                    return false;
                }
                while (('0' <= lexer->lookahead && lexer->lookahead <= '9') || lexer->lookahead == '_') {
                    advance(lexer);
                }
                lexer->mark_end(lexer);
                if (lexer->lookahead == 'j' || lexer->lookahead == 'J') {
                    advance(lexer);
                    if (lexer->lookahead == 'r' || lexer->lookahead == 'R' ||
                        is_id_continue(lexer->lookahead)) {
                        lexer->result_symbol = FLOAT;
                        return true;
                    }
                    lexer->mark_end(lexer);
                }
                lexer->result_symbol = FLOAT;
                return true;
            }
            if (is_id_start(lexer->lookahead) &&
                lexer->lookahead != 'j' && lexer->lookahead != 'J') {
                // Sage attribute access on an integer literal: `1.sqrt()`.
                return false;
            }
            is_float = true;
            while (('0' <= lexer->lookahead && lexer->lookahead <= '9') || lexer->lookahead == '_') {
                advance(lexer);
            }
        }
        lexer->mark_end(lexer);
        if ((has_digits || is_float) && (lexer->lookahead == 'e' || lexer->lookahead == 'E')) {
            advance(lexer);
            if (lexer->lookahead == '+' || lexer->lookahead == '-') {
                advance(lexer);
            }
            if ('0' <= lexer->lookahead && lexer->lookahead <= '9') {
                while (('0' <= lexer->lookahead && lexer->lookahead <= '9') || lexer->lookahead == '_') {
                    advance(lexer);
                }
                is_float = true;
                lexer->mark_end(lexer);
            } else if (!is_float) {
                return false; // `1eels`: an integer followed by an identifier
            }
        }
        if (!is_float) {
            return false; // a plain integer: the internal lexer owns it
        }
        if (lexer->lookahead == 'r' || lexer->lookahead == 'R') {
            return false; // a Sage raw literal (`2.5r`): internal token
        }
        if (lexer->lookahead == 'j' || lexer->lookahead == 'J') {
            advance(lexer);
            if (lexer->lookahead == 'r' || lexer->lookahead == 'R') {
                return false; // a Sage raw complex literal (`2.5jr`)
            }
            if (is_id_continue(lexer->lookahead)) {
                return false; // `1.junk`: attribute access on an integer
            }
            lexer->mark_end(lexer);
        }
        lexer->result_symbol = FLOAT;
        return true;
    }

    if (first_comment_indent_length == -1 && valid_symbols[STRING_START]) {
        Delimiter delimiter = new_delimiter();

        bool has_flags = false;
        while (lexer->lookahead) {
            if (lexer->lookahead == 'f' || lexer->lookahead == 'F' || lexer->lookahead == 't' ||
                lexer->lookahead == 'T') {
                set_format(&delimiter);
            } else if (lexer->lookahead == 'r' || lexer->lookahead == 'R') {
                set_raw(&delimiter);
            } else if (lexer->lookahead == 'b' || lexer->lookahead == 'B') {
                set_bytes(&delimiter);
            } else if (lexer->lookahead != 'u' && lexer->lookahead != 'U') {
                break;
            }
            has_flags = true;
            advance(lexer);
        }

        if (lexer->lookahead == '`') {
            set_end_character(&delimiter, '`');
            advance(lexer);
            lexer->mark_end(lexer);
        } else if (lexer->lookahead == '\'') {
            set_end_character(&delimiter, '\'');
            advance(lexer);
            lexer->mark_end(lexer);
            if (lexer->lookahead == '\'') {
                advance(lexer);
                if (lexer->lookahead == '\'') {
                    advance(lexer);
                    lexer->mark_end(lexer);
                    set_triple(&delimiter);
                }
            }
        } else if (lexer->lookahead == '"') {
            set_end_character(&delimiter, '"');
            advance(lexer);
            lexer->mark_end(lexer);
            if (lexer->lookahead == '"') {
                advance(lexer);
                if (lexer->lookahead == '"') {
                    advance(lexer);
                    lexer->mark_end(lexer);
                    set_triple(&delimiter);
                }
            }
        }

        if (end_character(&delimiter)) {
            array_push(&scanner->delimiters, delimiter);
            lexer->result_symbol = STRING_START;
            scanner->inside_interpolated_string = is_format(&delimiter);
            return true;
        }
        if (has_flags) {
            return false;
        }
    }

    return false;
}

unsigned tree_sitter_sage_external_scanner_serialize(void *payload, char *buffer) {
    Scanner *scanner = (Scanner *)payload;

    size_t size = 0;

    buffer[size++] = (char)scanner->inside_interpolated_string;

    size_t delimiter_count = scanner->delimiters.size;
    if (delimiter_count > UINT8_MAX) {
        delimiter_count = UINT8_MAX;
    }
    buffer[size++] = (char)delimiter_count;

    if (delimiter_count > 0) {
        memcpy(&buffer[size], scanner->delimiters.contents, delimiter_count);
    }
    size += delimiter_count;

    uint32_t iter = 1;
    for (; iter < scanner->indents.size && size < TREE_SITTER_SERIALIZATION_BUFFER_SIZE; ++iter) {
        uint16_t indent_value = *array_get(&scanner->indents, iter);
        buffer[size++] = (char)(indent_value & 0xFF);
        buffer[size++] = (char)((indent_value >> 8) & 0xFF);
    }

    return size;
}

void tree_sitter_sage_external_scanner_deserialize(void *payload, const char *buffer, unsigned length) {
    Scanner *scanner = (Scanner *)payload;

    array_delete(&scanner->delimiters);
    array_delete(&scanner->indents);
    array_push(&scanner->indents, 0);

    if (length > 0) {
        size_t size = 0;

        scanner->inside_interpolated_string = (bool)buffer[size++];

        size_t delimiter_count = (uint8_t)buffer[size++];
        if (delimiter_count > 0) {
            array_reserve(&scanner->delimiters, delimiter_count);
            scanner->delimiters.size = delimiter_count;
            memcpy(scanner->delimiters.contents, &buffer[size], delimiter_count);
            size += delimiter_count;
        }

        for (; size + 1 < length; size += 2) {
            uint16_t indent_value = (unsigned char)buffer[size] | ((unsigned char)buffer[size + 1] << 8);
            array_push(&scanner->indents, indent_value);
        }
    }
}

void *tree_sitter_sage_external_scanner_create() {
#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
    _Static_assert(sizeof(Delimiter) == sizeof(char), "");
#else
    assert(sizeof(Delimiter) == sizeof(char));
#endif
    Scanner *scanner = calloc(1, sizeof(Scanner));
    array_init(&scanner->indents);
    array_init(&scanner->delimiters);
    tree_sitter_sage_external_scanner_deserialize(scanner, NULL, 0);
    return scanner;
}

void tree_sitter_sage_external_scanner_destroy(void *payload) {
    Scanner *scanner = (Scanner *)payload;
    array_delete(&scanner->indents);
    array_delete(&scanner->delimiters);
    free(scanner);
}
