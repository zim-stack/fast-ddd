"""attrs flavor of the optional state and snapshot base classes.

Requires the optional dependency: `pip install "fast-ddd[attrs]"`.

These bases are a convenience: they add the `id` field and, for `State`,
protect it against reassignment. Any attrs class or dataclass with an `id`
field also works as an entity state, and any frozen one as a snapshot.

attrs allows a frozen class to inherit from a non-frozen one, so a state and a
snapshot can share one plain fields mixin. Dataclasses cannot do this.

Examples:
    ```python
    @attrs.define(kw_only=True)
    class RefreshTokenFields:
        user_id: UUID
        token: str

    @attrs.define(kw_only=True)
    class RefreshTokenState(RefreshTokenFields, State[UUID]): ...

    @attrs.frozen(kw_only=True)
    class RefreshTokenSnapshot(RefreshTokenFields, Snapshot[UUID]): ...
    ```
"""

from collections.abc import Hashable
from typing import TYPE_CHECKING

from fast_ddd.optional import require_attrs

if TYPE_CHECKING:
    import attrs
else:
    attrs = require_attrs()


# Only one parent may contribute a non-empty __slots__.
@attrs.define(kw_only=True, slots=False)
class State[TId: Hashable]:
    """Optional base class for an entity's mutable state (attrs flavor).

    Declare subclasses with `@attrs.define(kw_only=True)`. The inherited `id`
    cannot be reassigned after construction, so the owning entity's hash and
    identity stay stable. All other fields are mutable.

    Type Parameters:
        TId: Type of the entity identifier.

    Attributes:
        id: Identity of the entity. An `int`, `str`, `UUID`, enum, or a frozen
            value object such as `OrderId`.

    Note:
        The entity validates `id` when it is constructed:

        - it must not be `None` (generate ids up front);
        - it must be hashable;
        - an attrs class or dataclass id must be frozen;
                - a non-builtin id type must define value-based `__eq__`.

    Examples:
        ```python
        @attrs.define(kw_only=True)
        class OrderLineState(State[int]):
            sku: str
            quantity: int
        ```
    """

    id: TId = attrs.field(on_setattr=attrs.setters.frozen)


# attrs allows a frozen class to inherit from a non-frozen one.
# Only one parent may contribute a non-empty __slots__.
@attrs.frozen(kw_only=True, slots=False)
class Snapshot[TId: Hashable]:
    """Optional base class for an entity's immutable snapshot (attrs flavor).

    A snapshot is a frozen memento holding a chosen subset of the state's
    fields. Declare subclasses with `@attrs.frozen(kw_only=True)`.

    Nested entities appear as their own snapshots, inside `tuple`, `frozenset`
    or read-only mapping fields. The entity checks immutability deeply whenever
    a snapshot is produced or consumed, so subclasses need no post-init hook.
    Mutable containers, live entities and non-frozen attrs or dataclass
    instances are rejected.

    Equality is by value, unlike the entity's identity-based equality.

    Type Parameters:
        TId: Type of the entity identifier.

    Attributes:
        id: Identity of the entity this snapshot belongs to.

    Examples:
        ```python
        @attrs.frozen(kw_only=True)
        class OrderLineSnapshot(Snapshot[int]):
            sku: str
            quantity: int
        ```
    """

    id: TId
