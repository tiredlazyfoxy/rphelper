"""LLM server registrations and the one connection probe — feature `006`, step `003` (FEAT-004).

Plain functions: a Core `Connection` first, plain arguments, a frozen dataclass out or a
typed `DomainError` raised. This module never imports `fastapi`, never sees a `Request`,
never names a status code and never calls `get_settings` — `Settings`, the snowflake
generator and any acting administrator's id arrive as plain arguments. Every write opens
its own `with connection.begin():`; the connection arrives with no transaction open.

There is no branch on `kind` anywhere here (`context.md` D5). The stored pointer text is
never returned — the row value carries a boolean only. Step `004` adds model enablement,
designation and the use-time validators to this same module, sharing the client-factory
seam declared below.
"""

from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any, Final, Protocol

from sqlalchemy import Connection, or_, select

from app.config import Settings
from app.db.schema import llm_servers, models
from app.errors import LlmServerNotFoundError, LlmUnreachableError, ModelNotEnabledError, NoEmbeddingModelError
from app.ids import SnowflakeGenerator
from app.secrets import resolve_secret
from app.services.llm.client import EMBED_NO_VECTOR_REASON, LlmClient, ProbeOutcome, ProbeResult


class Unset(Enum):
    """The "not supplied" marker for partial updates (`context.md` D9).

    Distinct from `""` (supplied as empty) and from any real value, so the three pointer
    states stay different inputs at the service boundary.
    """

    UNSET = "unset"


UNSET: Final = Unset.UNSET
"""The single "field not supplied" value; compare with `is UNSET`."""


class LlmClientLike(Protocol):
    """What the registry needs from a client — step `002`'s probe and embed operations."""

    async def probe(self) -> ProbeResult: ...

    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]: ...


LlmClientFactory = Callable[[str, str | None, float], LlmClientLike]
"""`(base_url, resolved_api_key, timeout_seconds) -> client`. The default is `LlmClient`
itself; tests inject a fake so no network is involved."""


@dataclass(frozen=True)
class LlmServer:
    """One registration as every operation here returns it.

    The pointer text is deliberately not a field — only `has_api_key`. `enabled_model_names`
    is in `models.id` order. `embedding_model_name` / `embedding_dim` are set only when the
    embedding designation lives on this server. `last_test_error` is the outcome value
    itself (never prose) and `None` when the last test was reachable or never ran.
    """

    id: int
    name: str
    kind: str
    base_url: str
    has_api_key: bool
    enabled_model_names: tuple[str, ...]
    embedding_model_name: str | None
    embedding_dim: int | None
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_error: ProbeOutcome | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ConnectionTestResult:
    """What test-connection answers: the probe's outcome and the refreshed row."""

    outcome: ProbeOutcome
    server: LlmServer


def list_servers(connection: Connection) -> list[LlmServer]:
    """Every registration, in id order, with enabled names and designation. No filter, page or sort."""
    with _reading(connection):
        server_rows = connection.execute(select(*_SERVER_COLUMNS).order_by(llm_servers.c.id)).all()
        model_rows = connection.execute(
            select(
                models.c.server_id,
                models.c.model_name,
                models.c.is_enabled,
                models.c.is_embedding_designated,
                models.c.embedding_dim,
            )
            .where(or_(models.c.is_enabled, models.c.is_embedding_designated))
            .order_by(models.c.id)
        ).all()
    enabled: dict[int, list[str]] = {}
    designation: dict[int, tuple[str, int | None]] = {}
    for model_row in model_rows:
        if model_row.is_enabled:
            enabled.setdefault(model_row.server_id, []).append(model_row.model_name)
        if model_row.is_embedding_designated:
            designation[model_row.server_id] = (model_row.model_name, model_row.embedding_dim)
    return [
        _to_server(row._mapping, tuple(enabled.get(row.id, ())), designation.get(row.id)) for row in server_rows
    ]


def get_server(connection: Connection, server_id: int) -> LlmServer:
    """One registration; raises `LlmServerNotFoundError` when no row has `server_id`."""
    with _reading(connection):
        server = _fetch_server(connection, server_id)
    if server is None:
        raise _not_found()
    return server


def create_server(
    connection: Connection,
    generator: SnowflakeGenerator,
    name: str,
    kind: str,
    base_url: str,
    api_key_ref: str | None = None,
) -> LlmServer:
    """Insert one registration with a minted id and both timestamps; `""` pointer stores `NULL`."""
    with connection.begin():
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            llm_servers.insert().values(
                id=new_id,
                name=name,
                kind=kind,
                base_url=base_url,
                api_key_ref=api_key_ref or None,
                last_test_at=None,
                last_test_ok=None,
                last_test_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        server = _fetch_server(connection, new_id)
    assert server is not None
    return server


def update_server(
    connection: Connection,
    server_id: int,
    *,
    name: str | Unset = UNSET,
    kind: str | Unset = UNSET,
    base_url: str | Unset = UNSET,
    api_key_ref: str | Unset = UNSET,
) -> LlmServer:
    """Write only the supplied fields and bump `updated_at`, in one transaction.

    `api_key_ref`: `UNSET` leaves the stored pointer unchanged, `""` clears it (stores
    `NULL`), any other string replaces it. Raises `LlmServerNotFoundError` for an unknown id.
    """
    values: dict[str, Any] = {}
    if name is not UNSET:
        values["name"] = name
    if kind is not UNSET:
        values["kind"] = kind
    if base_url is not UNSET:
        values["base_url"] = base_url
    if api_key_ref is not UNSET:
        values["api_key_ref"] = api_key_ref or None
    values["updated_at"] = _now_text()
    with connection.begin():
        _require_exists(connection, server_id)
        connection.execute(llm_servers.update().where(llm_servers.c.id == server_id).values(**values))
        server = _fetch_server(connection, server_id)
    assert server is not None
    return server


def delete_server(connection: Connection, server_id: int) -> None:
    """Delete the server's `models` rows, then the server row, in one transaction.

    Raises `LlmServerNotFoundError` for an unknown id. Consults nothing else.
    """
    # The child delete is explicit so the behaviour never depends on `PRAGMA foreign_keys`.
    with connection.begin():
        _require_exists(connection, server_id)
        connection.execute(models.delete().where(models.c.server_id == server_id))
        connection.execute(llm_servers.delete().where(llm_servers.c.id == server_id))


async def probe_server(
    connection: Connection,
    server_id: int,
    settings: Settings,
    *,
    client_factory: LlmClientFactory = LlmClient,
) -> ProbeResult:
    """The one probe primitive: read the row, `resolve_secret` its pointer, build a client, probe.

    Writes nothing. Raises only `LlmServerNotFoundError` and `SecretRefError` (the latter
    before `client_factory` is called). Passes `settings.llm_request_timeout_seconds`.
    """
    with _reading(connection):
        row = connection.execute(
            select(llm_servers.c.base_url, llm_servers.c.api_key_ref).where(llm_servers.c.id == server_id)
        ).first()
    if row is None:
        raise _not_found()
    # Resolved at call time; a missing variable raises before any client exists.
    api_key = resolve_secret(row.api_key_ref)
    client = client_factory(row.base_url, api_key, settings.llm_request_timeout_seconds)
    return await client.probe()


async def check_server_connection(
    connection: Connection,
    server_id: int,
    settings: Settings,
    *,
    client_factory: LlmClientFactory = LlmClient,
) -> ConnectionTestResult:
    """Probe, then record `last_test_at` / `last_test_ok` / `last_test_error` in its own transaction.

    `SecretRefError` propagates and nothing is recorded.
    """
    result = await probe_server(connection, server_id, settings, client_factory=client_factory)
    reachable = result.outcome is ProbeOutcome.REACHABLE
    with connection.begin():
        _require_exists(connection, server_id)
        connection.execute(
            llm_servers.update()
            .where(llm_servers.c.id == server_id)
            .values(
                last_test_at=_now_text(),
                last_test_ok=reachable,
                last_test_error=None if reachable else result.outcome.value,
            )
        )
        server = _fetch_server(connection, server_id)
    assert server is not None
    return ConnectionTestResult(outcome=result.outcome, server=server)


async def list_available_models(
    connection: Connection,
    server_id: int,
    settings: Settings,
    *,
    client_factory: LlmClientFactory = LlmClient,
) -> list[str]:
    """Probe and return the model names; records nothing on the row.

    `reachable` -> the names; `model_list_empty` -> `[]`; `unreachable` / `auth_failed`
    -> `LlmUnreachableError` with `detail == {"reason": outcome.value}`.
    """
    result = await probe_server(connection, server_id, settings, client_factory=client_factory)
    if result.outcome is ProbeOutcome.REACHABLE:
        return list(result.model_names)
    if result.outcome is ProbeOutcome.MODEL_LIST_EMPTY:
        return []
    raise LlmUnreachableError("The LLM server could not list its models.", {"reason": result.outcome.value})


_SERVER_COLUMNS: Final = (
    llm_servers.c.id,
    llm_servers.c.name,
    llm_servers.c.kind,
    llm_servers.c.base_url,
    llm_servers.c.api_key_ref,
    llm_servers.c.last_test_at,
    llm_servers.c.last_test_ok,
    llm_servers.c.last_test_error,
    llm_servers.c.created_at,
    llm_servers.c.updated_at,
)


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def _fetch_server(connection: Connection, server_id: int) -> LlmServer | None:
    """One server row plus its enabled names and designation, in the caller's transaction state."""
    row = connection.execute(select(*_SERVER_COLUMNS).where(llm_servers.c.id == server_id)).first()
    if row is None:
        return None
    model_rows = connection.execute(
        select(models.c.model_name, models.c.is_enabled, models.c.is_embedding_designated, models.c.embedding_dim)
        .where(models.c.server_id == server_id)
        .order_by(models.c.id)
    ).all()
    enabled = tuple(m.model_name for m in model_rows if m.is_enabled)
    designation = next(((m.model_name, m.embedding_dim) for m in model_rows if m.is_embedding_designated), None)
    return _to_server(row._mapping, enabled, designation)


def _to_server(
    row: Any,
    enabled_model_names: tuple[str, ...],
    designation: tuple[str, int | None] | None,
) -> LlmServer:
    """Map a server row mapping to the value; the pointer becomes a boolean and nothing more."""
    last_test_ok = row["last_test_ok"]
    last_test_error = row["last_test_error"]
    return LlmServer(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        base_url=row["base_url"],
        has_api_key=bool(row["api_key_ref"]),
        enabled_model_names=enabled_model_names,
        embedding_model_name=designation[0] if designation is not None else None,
        embedding_dim=designation[1] if designation is not None else None,
        last_test_at=_parse_time(row["last_test_at"]),
        last_test_ok=bool(last_test_ok) if last_test_ok is not None else None,
        last_test_error=ProbeOutcome(last_test_error) if last_test_error else None,
        created_at=_require_time(row["created_at"]),
        updated_at=_require_time(row["updated_at"]),
    )


def _parse_time(text: str | None) -> datetime | None:
    """Stored UTC ISO-8601 text to an aware datetime."""
    if text is None:
        return None
    value = datetime.fromisoformat(text)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _require_time(text: str) -> datetime:
    value = _parse_time(text)
    assert value is not None
    return value


def _require_exists(connection: Connection, server_id: int) -> None:
    """Raise `LlmServerNotFoundError` when no registration has `server_id` — before any write."""
    found = connection.execute(select(llm_servers.c.id).where(llm_servers.c.id == server_id)).first()
    if found is None:
        raise _not_found()


def _not_found() -> LlmServerNotFoundError:
    return LlmServerNotFoundError("That LLM server registration does not exist.")


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


# --- Step 004: model enablement, the embedding designation and the use-time validators ---

EMBEDDING_PROBE_TEXT: Final = "RPHelper embedding dimension probe"
"""The one fixed input sent when designating an embedding model (`context.md` D2).

Not configurable and carries no user content (R5); its vector's length is the recorded
`embedding_dim`."""


class ModelRefLevel(StrEnum):
    """Which level set a chat-model reference — `character` or `session`, never `user`."""

    CHARACTER = "character"
    SESSION = "session"


@dataclass(frozen=True)
class EnabledChatModel:
    """What the chat-model validator answers: the enabled model and its server registration."""

    server: LlmServer
    model_name: str


@dataclass(frozen=True)
class DesignatedEmbeddingModel:
    """What the embedding validator answers: the designated model, its server and dimension."""

    server: LlmServer
    model_name: str
    embedding_dim: int


def set_enabled_models(
    connection: Connection,
    generator: SnowflakeGenerator,
    server_id: int,
    model_names: Collection[str],
) -> list[str]:
    """Replace the server's enabled set with exactly `model_names`, in one transaction.

    Named models without a row get one (minted id, `is_enabled` true); named rows are set
    true; unnamed rows are set false. No row is deleted; `is_embedding_designated` and
    `embedding_dim` are never touched. Raises only `LlmServerNotFoundError`. Returns the
    enabled names as stored afterwards, in `models.id` order.
    """
    wanted = dict.fromkeys(model_names)
    with connection.begin():
        _require_exists(connection, server_id)
        now = _now_text()
        rows = connection.execute(
            select(models.c.id, models.c.model_name, models.c.is_enabled).where(models.c.server_id == server_id)
        ).all()
        existing = {row.model_name for row in rows}
        for row in rows:
            should_enable = row.model_name in wanted
            if bool(row.is_enabled) != should_enable:
                connection.execute(
                    models.update().where(models.c.id == row.id).values(is_enabled=should_enable, updated_at=now)
                )
        for name in wanted:
            if name not in existing:
                connection.execute(
                    models.insert().values(
                        id=generator.next_id(),
                        server_id=server_id,
                        model_name=name,
                        is_enabled=True,
                        is_embedding_designated=False,
                        embedding_dim=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        enabled: list[str] = list(
            connection.execute(
                select(models.c.model_name)
                .where(models.c.server_id == server_id, models.c.is_enabled)
                .order_by(models.c.id)
            )
            .scalars()
            .all()
        )
    return enabled


async def designate_embedding_model(
    connection: Connection,
    generator: SnowflakeGenerator,
    server_id: int,
    model_name: str,
    settings: Settings,
    *,
    client_factory: LlmClientFactory = LlmClient,
) -> LlmServer:
    """Measure the model's dimension with one embeddings call, then designate it.

    Order: read the server (`LlmServerNotFoundError`), `resolve_secret` (`SecretRefError`
    before the factory is called), embed `[EMBEDDING_PROBE_TEXT]` outside any transaction
    (`LlmUnreachableError` propagates, nothing written), then one transaction clears the
    flag on every row of the table and upserts this (server, model) row with the flag true
    and the measured `embedding_dim`. Never touches `is_enabled`. Returns the server row.
    """
    with _reading(connection):
        row = connection.execute(
            select(llm_servers.c.base_url, llm_servers.c.api_key_ref).where(llm_servers.c.id == server_id)
        ).first()
    if row is None:
        raise _not_found()
    # Resolved at call time; a missing variable raises before any client exists.
    api_key = resolve_secret(row.api_key_ref)
    client = client_factory(row.base_url, api_key, settings.llm_request_timeout_seconds)
    # The network call stays outside any transaction; a failure propagates with nothing written.
    vectors = await client.embed(model_name, [EMBEDDING_PROBE_TEXT])
    if not vectors or not vectors[0]:
        raise LlmUnreachableError(
            "The LLM server returned no usable embedding vector.", {"reason": EMBED_NO_VECTOR_REASON}
        )
    dimension = len(vectors[0])
    with connection.begin():
        _require_exists(connection, server_id)
        now = _now_text()
        # Table-wide, not server-wide: at most one row carries the designation.
        connection.execute(
            models.update()
            .where(models.c.is_embedding_designated)
            .values(is_embedding_designated=False, updated_at=now)
        )
        existing = connection.execute(
            select(models.c.id).where(models.c.server_id == server_id, models.c.model_name == model_name)
        ).first()
        if existing is not None:
            connection.execute(
                models.update()
                .where(models.c.id == existing.id)
                .values(is_embedding_designated=True, embedding_dim=dimension, updated_at=now)
            )
        else:
            connection.execute(
                models.insert().values(
                    id=generator.next_id(),
                    server_id=server_id,
                    model_name=model_name,
                    is_enabled=False,
                    is_embedding_designated=True,
                    embedding_dim=dimension,
                    created_at=now,
                    updated_at=now,
                )
            )
        server = _fetch_server(connection, server_id)
    assert server is not None
    return server


def clear_embedding_designation(connection: Connection, server_id: int) -> None:
    """Clear `is_embedding_designated` on this server's rows, in one transaction.

    Idempotent; leaves `is_enabled`, `embedding_dim` and every row alone; no outbound call.
    Raises `LlmServerNotFoundError` for an unknown id.
    """
    with connection.begin():
        _require_exists(connection, server_id)
        connection.execute(
            models.update()
            .where(models.c.server_id == server_id, models.c.is_embedding_designated)
            .values(is_embedding_designated=False, updated_at=_now_text())
        )


def validate_chat_model(
    connection: Connection,
    server_id: int,
    model_name: str,
    level: ModelRefLevel,
) -> EnabledChatModel:
    """Use-time check: the (server, model) row exists and is enabled — no substitute, ever.

    Otherwise (row disabled, row absent, server gone) raises `ModelNotEnabledError` with
    `detail == {"server_id": str(server_id), "model_name": model_name, "level": level.value}`.
    """
    with _reading(connection):
        enabled = connection.execute(
            select(models.c.id).where(
                models.c.server_id == server_id,
                models.c.model_name == model_name,
                models.c.is_enabled,
            )
        ).first()
        server = _fetch_server(connection, server_id) if enabled is not None else None
    if server is None:
        raise ModelNotEnabledError(
            "The selected model is not enabled.",
            {"server_id": str(server_id), "model_name": model_name, "level": ModelRefLevel(level).value},
        )
    return EnabledChatModel(server=server, model_name=model_name)


def validate_embedding_model(connection: Connection) -> DesignatedEmbeddingModel:
    """Use-time check: a designation exists and that model is enabled — no substitute, ever.

    Otherwise raises `NoEmbeddingModelError` whose `detail` carries nothing user-scoped.
    """
    with _reading(connection):
        designated = connection.execute(
            select(models.c.server_id, models.c.model_name, models.c.is_enabled, models.c.embedding_dim).where(
                models.c.is_embedding_designated
            )
        ).first()
        server = None
        if designated is not None and designated.is_enabled and designated.embedding_dim is not None:
            server = _fetch_server(connection, designated.server_id)
    if designated is None or server is None or designated.embedding_dim is None:
        raise NoEmbeddingModelError("No enabled embedding model is designated.")
    return DesignatedEmbeddingModel(
        server=server, model_name=designated.model_name, embedding_dim=int(designated.embedding_dim)
    )
