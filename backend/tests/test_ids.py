"""Tests for ``app.ids`` — the snowflake generator, its layout and its refusals.

Every expected value here comes from ``004.ids-and-json-boundary.md`` (Definition of
done) and ``004.context.md`` (§ "The bit layout, verbatim", § "Why the epoch is a
constant", § "Sequence exhaustion — a planner ruling", § "Backwards clock — why it
refuses, and why it is not a ``DomainError``", § "The clock seam"). Covers DoD-1 .. DoD-6.

The clock is injected everywhere it matters: a test cannot hold the machine's clock at
one millisecond, nor make it jump backwards, so DoD-5 and DoD-6 are reachable only
through the constructor's ``clock`` argument. DoD-1 and DoD-4 deliberately use the
default system clock, because that is the configuration production runs.

Assumption recorded for DoD-5 (see ``StallingClock``): a single ``next_id`` call reads
the clock at most ``SPIN_READS_BEFORE_ADVANCE`` times while it is *not* blocked, and the
block on sequence exhaustion is a loop that **re-reads the clock**. Both hold for any
implementation that waits for the next millisecond by observing the injected clock.
"""

import threading
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.errors import DomainError
from app.ids import (
    EPOCH_MS,
    NODE_ID_BITS,
    SEQUENCE_BITS,
    BackwardsClockError,
    SnowflakeGenerator,
    build_id_generator,
)

# Decoding follows from the two public widths; no shift constant is frozen, so the tests
# derive theirs from the constants rather than hard-coding them.
NODE_ID_MASK = (1 << NODE_ID_BITS) - 1
SEQUENCE_MASK = (1 << SEQUENCE_BITS) - 1
TIMESTAMP_SHIFT = NODE_ID_BITS + SEQUENCE_BITS
MAX_NODE_ID = NODE_ID_MASK
SEQUENCE_CAPACITY = 1 << SEQUENCE_BITS
SIGNED_64_BIT_CEILING = 1 << 63


def decode(snowflake: int) -> tuple[int, int, int]:
    """Split an id into (milliseconds since the epoch, node id, sequence)."""
    return (
        snowflake >> TIMESTAMP_SHIFT,
        (snowflake >> SEQUENCE_BITS) & NODE_ID_MASK,
        snowflake & SEQUENCE_MASK,
    )


def timestamps_of(ids: list[int]) -> list[int]:
    return [decode(snowflake)[0] for snowflake in ids]


def strictly_increases(values: list[int]) -> bool:
    return all(values[index] < values[index + 1] for index in range(len(values) - 1))


class FixedClock:
    """A millisecond clock the test moves by assigning to ``now``."""

    def __init__(self, now: int) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


SPIN_READS_BEFORE_ADVANCE = 4


class StallingClock:
    """A millisecond clock that holds still during a mint and moves on during a block.

    It returns the same millisecond for every read until it has been read
    ``SPIN_READS_BEFORE_ADVANCE`` times without the test marking a completed mint, at
    which point it advances by exactly one millisecond. So a normal mint sees a frozen
    clock — which is how the sequence reaches its capacity — while a generator blocking
    for the next millisecond sees that millisecond arrive, without the test depending on
    real elapsed time.
    """

    def __init__(self, now: int) -> None:
        self.now = now
        self._reads_since_mark = 0

    def __call__(self) -> int:
        self._reads_since_mark += 1
        if self._reads_since_mark > SPIN_READS_BEFORE_ADVANCE:
            self.now += 1
            self._reads_since_mark = 0
        return self.now

    def mark_mint_returned(self) -> None:
        self._reads_since_mark = 0


# --------------------------------------------------------------------------- DoD-1


def test_successive_ids_strictly_increase__DoD1() -> None:
    """DoD-1: ids minted in succession from one generator strictly increase."""
    generator = SnowflakeGenerator(node_id=1)
    ids = [generator.next_id() for _ in range(500)]
    assert strictly_increases(ids)


def test_every_id_is_positive_and_fits_in_63_bits__DoD1() -> None:
    """DoD-1: every id is positive and fits in 63 bits (the signed int64 SQLite stores)."""
    generator = SnowflakeGenerator(node_id=1)
    ids = [generator.next_id() for _ in range(500)]
    assert all(snowflake > 0 for snowflake in ids)
    assert all(snowflake < SIGNED_64_BIT_CEILING for snowflake in ids)


# --------------------------------------------------------------------------- DoD-2


def test_epoch_constant_is_midnight_2026_01_01_utc__DoD2() -> None:
    """DoD-2: the epoch is milliseconds since the Unix epoch at 2026-01-01T00:00:00Z."""
    expected = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    assert EPOCH_MS == expected


def test_layout_widths_are_ten_node_bits_and_twelve_sequence_bits__DoD2() -> None:
    """DoD-2: the public constants declare 10 node bits and 12 sequence bits."""
    assert NODE_ID_BITS == 10
    assert SEQUENCE_BITS == 12


def test_high_field_is_milliseconds_since_the_epoch__DoD2() -> None:
    """DoD-2: at a known clock reading the high field is that reading minus the epoch."""
    clock_ms = EPOCH_MS + 123_456_789
    generator = SnowflakeGenerator(node_id=7, clock=FixedClock(clock_ms))
    timestamp, _node_id, _sequence = decode(generator.next_id())
    assert timestamp == clock_ms - EPOCH_MS


def test_middle_field_is_the_node_id__DoD2() -> None:
    """DoD-2: the middle field, at the declared width, is the node id."""
    generator = SnowflakeGenerator(node_id=7, clock=FixedClock(EPOCH_MS + 123_456_789))
    _timestamp, node_id, _sequence = decode(generator.next_id())
    assert node_id == 7


def test_low_field_is_the_per_millisecond_sequence__DoD2() -> None:
    """DoD-2: within one millisecond the low field counts 0, 1, 2, ... (4096 per ms)."""
    generator = SnowflakeGenerator(node_id=7, clock=FixedClock(EPOCH_MS + 123_456_789))
    sequences = [decode(generator.next_id())[2] for _ in range(5)]
    assert sequences == [0, 1, 2, 3, 4]


# --------------------------------------------------------------------------- DoD-3


@pytest.mark.parametrize("node_id", [0, 1, 511, MAX_NODE_ID])
def test_every_minted_id_carries_the_constructed_node_id__DoD3(node_id: int) -> None:
    """DoD-3: the node id given at construction is what every minted id carries."""
    generator = SnowflakeGenerator(node_id=node_id)
    ids = [generator.next_id() for _ in range(20)]
    assert all(decode(snowflake)[1] == node_id for snowflake in ids)


def test_node_id_is_read_once_at_construction__DoD3(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-3: the node id is read once at construction, not re-read on every mint."""
    monkeypatch.setenv("RPHELPER_NODE_ID", "5")
    settings = Settings(_env_file=None)
    generator = build_id_generator(settings)

    before = decode(generator.next_id())[1]
    settings.node_id = 9
    after = decode(generator.next_id())[1]

    assert before == 5
    assert after == 5


@pytest.mark.parametrize("node_id", [MAX_NODE_ID + 1, 2048, -1])
def test_node_id_outside_the_representable_range_is_refused__DoD3(node_id: int) -> None:
    """DoD-3: a node id the declared bits cannot hold is refused at construction."""
    # The plan fixes the refusal but not the exception type, so the assertion is only
    # that construction fails, and fails for a reason other than "not implemented".
    with pytest.raises(Exception) as excinfo:
        SnowflakeGenerator(node_id=node_id)
    assert not isinstance(excinfo.value, NotImplementedError)


# --------------------------------------------------------------------------- DoD-4


def test_concurrent_minting_produces_no_duplicate_ids__DoD4() -> None:
    """DoD-4: several threads minting against one generator produce no duplicates."""
    thread_count = 8
    per_thread = 500
    generator = SnowflakeGenerator(node_id=3)
    barrier = threading.Barrier(thread_count)
    minted: list[list[int]] = [[] for _ in range(thread_count)]

    def worker(slot: int) -> None:
        collected = minted[slot]
        barrier.wait()
        for _ in range(per_thread):
            collected.append(generator.next_id())

    threads = [threading.Thread(target=worker, args=(slot,)) for slot in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not any(thread.is_alive() for thread in threads)
    ids = [snowflake for slot in minted for snowflake in slot]
    assert len(ids) == thread_count * per_thread
    assert len(set(ids)) == len(ids)


# --------------------------------------------------------------------------- DoD-5


def test_exhausting_the_sequence_blocks_into_the_next_millisecond__DoD5() -> None:
    """DoD-5: past 4096 ids in one millisecond the generator moves into the next one."""
    overflow = 500
    clock = StallingClock(EPOCH_MS + 1_000)
    generator = SnowflakeGenerator(node_id=2, clock=clock)

    ids: list[int] = []
    for _ in range(SEQUENCE_CAPACITY + overflow):
        ids.append(generator.next_id())
        clock.mark_mint_returned()

    timestamps = timestamps_of(ids)
    first = timestamps[0]
    assert sorted(set(timestamps)) == [first, first + 1]
    assert timestamps.count(first) == SEQUENCE_CAPACITY
    assert timestamps.count(first + 1) == overflow


def test_exhausting_the_sequence_still_yields_unique_increasing_ids__DoD5() -> None:
    """DoD-5: exhaustion neither raises nor repeats — the ids stay unique and ordered."""
    overflow = 500
    clock = StallingClock(EPOCH_MS + 1_000)
    generator = SnowflakeGenerator(node_id=2, clock=clock)

    ids: list[int] = []
    for _ in range(SEQUENCE_CAPACITY + overflow):
        ids.append(generator.next_id())
        clock.mark_mint_returned()

    assert len(ids) == SEQUENCE_CAPACITY + overflow
    assert len(set(ids)) == len(ids)
    assert strictly_increases(ids)


# --------------------------------------------------------------------------- DoD-6


def test_backwards_clock_makes_minting_raise__DoD6() -> None:
    """DoD-6: a clock earlier than the last millisecond issued refuses to mint."""
    clock = FixedClock(EPOCH_MS + 5_000)
    generator = SnowflakeGenerator(node_id=4, clock=clock)
    generator.next_id()

    clock.now = EPOCH_MS + 4_990
    with pytest.raises(BackwardsClockError):
        generator.next_id()


def test_backwards_clock_error_is_not_a_domain_error_subclass__DoD6() -> None:
    """DoD-6: the backwards-clock exception is deliberately outside the error hierarchy."""
    assert issubclass(BackwardsClockError, Exception)
    assert not issubclass(BackwardsClockError, DomainError)


def test_raised_backwards_clock_error_is_not_a_domain_error__DoD6() -> None:
    """DoD-6: the raised instance is an operational fault, not a renderable domain error."""
    clock = FixedClock(EPOCH_MS + 5_000)
    generator = SnowflakeGenerator(node_id=4, clock=clock)
    generator.next_id()

    clock.now = EPOCH_MS + 1
    with pytest.raises(BackwardsClockError) as excinfo:
        generator.next_id()
    assert not isinstance(excinfo.value, DomainError)
