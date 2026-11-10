"""The snowflake id generator — infrastructure, beside `config.py` and `secrets.py`.

`docs/architecture/backend-structure.md` § The id generator places this module at
`app/ids.py` deliberately: **not** under `services/`, because it takes no `user_id` and
enforces no rule from `domain-rules.md` and every service that inserts anything needs
it; and **not** under `db/`, because it opens no connection and names no table — the
database does not issue ids here, application code mints them before the INSERT.

Layout (`docs/architecture/data-model.md` § Identifiers), 64-bit signed, 63 usable:

```
 41 bits   milliseconds since epoch 2026-01-01T00:00:00Z   (~69 years)
 10 bits   node id, from config, default 0
 12 bits   per-millisecond sequence                        (4096 ids/ms)
```

The three layout constants below are public because the layout *is* the contract: a
caller decoding an id must not have to re-derive the shifts. `EPOCH_MS` is a literal
and is **never read from configuration** — it is the whole 41-bit budget, and moving it
re-bases every future id against a different origin and invalidates the ordering of
every row already stored.

`BackwardsClockError` is deliberately a plain `Exception` and **not** a subclass of
`app.errors.DomainError`. `backend-structure.md` classifies a backwards clock step as
an operational fault — a 500 — not as a domain failure the SPA is expected to render;
giving it a `code` would promise the SPA a renderer it does not have. Do not tidy it
into the error hierarchy.

A *small* backwards step does not raise. A wall clock that NTP slews or steps (seen as
~70 ms steps under a WSL host's clock sync, and possible on any production host) reads
earlier than the last issued millisecond for a moment; refusing every such read turned
an ordinary clock correction into random 500s. A read up to `BACKWARDS_TOLERANCE_MS`
behind is treated as the last issued millisecond itself: the sequence continues within
it and, on exhaustion, the generator waits (re-reading the clock) until the clock passes
it. Ids stay strictly increasing and unique because they are issued from the last
millisecond, never from the earlier reading. Only a step beyond the tolerance raises
`BackwardsClockError`.
"""

import threading
import time
from collections.abc import Callable

from app.config import Settings

#: Milliseconds since the Unix epoch at `2026-01-01T00:00:00Z`. A constant, forever.
EPOCH_MS: int = 1767225600000

#: Width of the node-id field, in bits.
NODE_ID_BITS: int = 10

#: Width of the per-millisecond sequence field, in bits.
SEQUENCE_BITS: int = 12

#: How far behind the last issued millisecond a clock read may be and still mint (by
#: continuing from that millisecond). A step further back raises `BackwardsClockError`.
BACKWARDS_TOLERANCE_MS: int = 1000


class BackwardsClockError(Exception):
    """The clock read more than `BACKWARDS_TOLERANCE_MS` before the last issued millisecond.

    A plain `Exception` on purpose — an operational fault, not a `DomainError`.
    """


def _system_clock_ms() -> int:
    """Current wall-clock time in milliseconds since the Unix epoch."""
    return time.time_ns() // 1_000_000


class SnowflakeGenerator:
    """Mints k-sortable 63-bit ids: milliseconds, then node id, then sequence.

    Process-local and thread-safe: its whole state is the last millisecond issued and
    the sequence within it, held behind a lock, because uvicorn serves requests on a
    thread pool and two inserts can land in the same millisecond.

    The clock is a constructor argument — a callable returning the current time in
    milliseconds — so sequence exhaustion and a backwards step (tolerated or refused)
    are testable without touching real time.
    """

    node_id: int

    _clock: Callable[[], int]
    _lock: threading.Lock
    _last_ms: int
    _sequence: int

    def __init__(self, node_id: int, clock: Callable[[], int] = _system_clock_ms) -> None:
        """Read the node id once; refuse one outside the range `NODE_ID_BITS` allows."""
        if not 0 <= node_id < (1 << NODE_ID_BITS):
            raise ValueError(f"node_id must fit in {NODE_ID_BITS} bits (0..{(1 << NODE_ID_BITS) - 1}), got {node_id}")
        self.node_id = node_id
        self._clock = clock
        self._lock = threading.Lock()
        self._last_ms = -1
        self._sequence = 0

    def next_id(self) -> int:
        """Return the next id.

        Blocks into the next millisecond when the sequence exhausts within one. A clock
        read at most `BACKWARDS_TOLERANCE_MS` behind the last issued millisecond (a
        slewed or stepped wall clock) is treated as that millisecond, so the id is
        issued from it and ids stay strictly increasing; a read further behind raises
        `BackwardsClockError`.
        """
        max_sequence = (1 << SEQUENCE_BITS) - 1
        with self._lock:
            now_ms = self._read_clock()
            if now_ms == self._last_ms:
                if self._sequence >= max_sequence:
                    # Sequence exhausted within this millisecond. Wrapping would mint a
                    # duplicate and raising would fail a burst the caller cannot act on,
                    # so wait until the clock passes the last issued millisecond —
                    # re-reading the injected clock, never real elapsed time.
                    while now_ms <= self._last_ms:
                        time.sleep(0)
                        now_ms = self._read_clock()
                    self._sequence = 0
                else:
                    self._sequence += 1
            else:
                self._sequence = 0
            self._last_ms = now_ms
            timestamp_shift = NODE_ID_BITS + SEQUENCE_BITS
            return (
                ((now_ms - EPOCH_MS) << timestamp_shift)
                | (self.node_id << SEQUENCE_BITS)
                | self._sequence
            )

    def _read_clock(self) -> int:
        """Read the clock, clamping a tolerated backwards step up to the last issued ms.

        Caller holds the lock. Raises `BackwardsClockError` for a step beyond
        `BACKWARDS_TOLERANCE_MS`.
        """
        now_ms = self._clock()
        if now_ms < self._last_ms:
            if self._last_ms - now_ms > BACKWARDS_TOLERANCE_MS:
                raise BackwardsClockError(
                    f"clock moved backwards: read {now_ms} ms, last issued at {self._last_ms} ms"
                    f" (beyond the {BACKWARDS_TOLERANCE_MS} ms tolerance)"
                )
            return self._last_ms
        return now_ms


def build_id_generator(settings: Settings) -> SnowflakeGenerator:
    """Build the process's single generator from settings, reading `node_id`."""
    return SnowflakeGenerator(node_id=settings.node_id)
