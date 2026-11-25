"""Compiler results and bidirectional source-position mappings."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Literal

from tree_sitter import Tree

# Number-literal handling: "wrapped" emits Integer()/RealNumber() calls,
# "raw" leaves numeric literals as CPython sees them.
Numbers = Literal["wrapped", "raw"]

# Implicit multiplication: "implicit" reads `2x` as a product, "explicit"
# leaves the juxtaposition alone so CPython rejects it as the syntax
# error it is under Sage's default.
Products = Literal["implicit", "explicit"]

@dataclass(frozen=True)
class Segment:
    """One span of generated Python and the original span it came from.

    ``exact`` segments are verbatim copies, so positions map one-to-one;
    rebuilt segments map every inner position to the start of the
    originating construct.
    """

    text: str
    original_start: int
    original_end: int
    exact: bool


@dataclass(frozen=True)
class SourceMap:
    """Maps positions in generated Python back to the Sage source."""

    original: str
    python: str
    segments: tuple[Segment, ...]

    def original_offset(self, generated_offset: int) -> int:
        cursor = 0
        for segment in self.segments:
            end = cursor + len(segment.text.encode("utf-8"))
            if generated_offset < end or segment is self.segments[-1]:
                if segment.exact:
                    return segment.original_start + max(0, min(generated_offset, end) - cursor)
                return segment.original_start
            cursor = end
        return len(self.original.encode("utf-8"))

    def exact_at_generated(self, line: int, column: int) -> bool:
        """Whether a 1-based generated position lies in verbatim source.

        Diagnostics about generated (non-exact) text describe the
        compiler's output, not the author's input; style checkers should
        drop them.
        """
        generated = self.python.encode("utf-8")
        line_starts = [0]
        for index, byte in enumerate(generated):
            if byte == 0x0A:
                line_starts.append(index + 1)
        offset = line_starts[min(line - 1, len(line_starts) - 1)] + column
        cursor = 0
        for segment in self.segments:
            end = cursor + len(segment.text.encode("utf-8"))
            if offset < end or segment is self.segments[-1]:
                return segment.exact
            cursor = end
        return True

    def generated_offset(self, original_offset: int) -> int:
        generated_cursor = 0
        for segment in self.segments:
            width = len(segment.text.encode("utf-8"))
            if original_offset < segment.original_end or segment is self.segments[-1]:
                if segment.exact:
                    inner = max(0, original_offset - segment.original_start)
                    return generated_cursor + min(inner, width)
                return generated_cursor
            generated_cursor += width
        return len(self.python.encode("utf-8"))

    def generated_position(self, line: int, column: int) -> tuple[int, int]:
        """Translate a 1-based original (line, column) to the generated Python."""
        original = self.original.encode("utf-8")
        line_starts = [0]
        for index, byte in enumerate(original):
            if byte == 0x0A:
                line_starts.append(index + 1)
        offset = line_starts[min(line - 1, len(line_starts) - 1)] + column
        generated_offset = self.generated_offset(offset)
        prefix = self.python.encode("utf-8")[:generated_offset]
        generated_line = prefix.count(b"\n") + 1
        last_newline = prefix.rfind(b"\n")
        return generated_line, generated_offset - (last_newline + 1)

    def original_position(self, line: int, column: int) -> tuple[int, int]:
        """Translate a 1-based generated (line, column) to the original."""
        generated = self.python.encode("utf-8")
        line_starts = [0]
        for index, byte in enumerate(generated):
            if byte == 0x0A:
                line_starts.append(index + 1)
        offset = line_starts[min(line - 1, len(line_starts) - 1)] + column
        original_offset = self.original_offset(offset)
        prefix = self.original.encode("utf-8")[:original_offset]
        original_line = prefix.count(b"\n") + 1
        last_newline = prefix.rfind(b"\n")
        original_column = original_offset - (last_newline + 1)
        return original_line, original_column


@dataclass(frozen=True)
class LoweredSource:
    """The compiler's output: ordinary Python plus its source map.

    The parse tree is retained so a subsequent :func:`lower` call can
    reuse it incrementally.  Passing this object as ``previous``
    consumes it: the retained tree is edited in place, so keep only the
    returned object for further edits.
    """

    python: str
    source_map: SourceMap
    _tree: Tree | None = dataclass_field(default=None, repr=False, compare=False)
    _numbers: Numbers = dataclass_field(default="wrapped", repr=False, compare=False)
    _products: Products = dataclass_field(default="implicit", repr=False, compare=False)
