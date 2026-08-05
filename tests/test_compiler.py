r"""Incremental lowering must be indistinguishable from fresh lowering.

Each test drives ``lower(source, previous=...)`` through document
revisions — including transient error states while a construct is being
typed — and asserts byte-identical output and source maps against a
fresh ``lower(source)``.
"""

from sagepython import LoweredSource, lower


def _segment_tuples(result: LoweredSource) -> list[tuple[str, int, int, bool]]:
    return [
        (segment.text, segment.original_start, segment.original_end, segment.exact)
        for segment in result.source_map.segments
    ]


def _assert_equivalent(source: str, previous: LoweredSource) -> LoweredSource:
    incremental = lower(source, previous=previous)
    fresh = lower(source)
    assert incremental.python == fresh.python
    assert _segment_tuples(incremental) == _segment_tuples(fresh)
    return incremental


def test_typing_a_generator_assignment_through_error_states() -> None:
    revisions = [
        "R\n",
        "R.\n",
        "R.<\n",
        "R.<x\n",
        "R.<x>\n",
        "R.<x> = \n",
        "R.<x> = QQ[\n",
        "R.<x> = QQ[]\n",
        "R.<x> = QQ[]\nf(t) = t^2\n",
    ]
    state = lower(revisions[0])
    for revision in revisions[1:]:
        state = _assert_equivalent(revision, state)


def test_editing_inside_an_existing_construct() -> None:
    state = lower("R.<x, y> = QQ[]\nq = 2^5\n")
    state = _assert_equivalent("R.<x, zed> = QQ[]\nq = 2^5\n", state)
    _assert_equivalent("R.<x, zed> = QQ[]\nq = 2^12\n", state)


def test_multiline_insertion_between_constructs() -> None:
    state = lower("a = 1\nz = {n^2 | n in [1..5]}\n")
    _assert_equivalent(
        "a = 1\nf(t) = t^3 - t\nw = 5r\nz = {n^2 | n in [1..5]}\n", state
    )


def test_error_to_valid_transition() -> None:
    state = lower("v = [1..\n")
    _assert_equivalent("v = [1..9]\n", state)


def test_deleting_a_leading_construct() -> None:
    state = lower("R.<x> = QQ[]\nq = 2x + 1\n")
    _assert_equivalent("q = 2x + 1\n", state)


def test_wrap_mode_mismatch_falls_back_to_a_fresh_parse() -> None:
    state = lower("q = 2^3\n", wrap_numbers=False)

    result = lower("q = 2^3 + 1\n", wrap_numbers=True, previous=state)

    assert result.python == lower("q = 2^3 + 1\n").python


def test_incremental_source_map_translates_like_a_fresh_one() -> None:
    state = lower("R.<x, y> = QQ[]\nq = 2^5 + zz\n")
    edited = "R.<x, y> = QQ[]\nq = 2^5 + zz + 1\n"

    incremental = lower(edited, previous=state)
    fresh = lower(edited)

    generated_column = fresh.python.split("\n")[1].find("zz")
    assert incremental.source_map.original_position(
        2, generated_column
    ) == fresh.source_map.original_position(2, generated_column)
    assert incremental.source_map.original_position(2, generated_column) == (2, 10)
