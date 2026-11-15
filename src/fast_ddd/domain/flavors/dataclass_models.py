"""Dataclass flavor of the optional state and snapshot base classes.

These bases are a convenience: they add the `id` field and, for
`DataclassState`, protect it against reassignment. They need no extra
dependency. Any dataclass with an `id` field also works as an entity state, and
any frozen one as a snapshot.

Examples:
    ```python
    @dataclass(kw_only=True)
    class OrderLineState(DataclassState[int]):
        sku: str
        quantity: int

    @dataclass(frozen=True, kw_only=True)
    class OrderLineSnapshot(DataclassSnapshot[int]):
        sku: str
        quantity: int
    ```
"""

from collections.abc import Hashable
from dataclasses import dataclass


@dataclass(kw_only=True)
class DataclassState[TId: Hashable]:
    """Optional base class for an entity's mutable state (dataclass flavor).

    Declare subclasses with `@dataclass(kw_only=True)`; `slots=True` works too.
    The inherited `id` cannot be reassigned or deleted after construction, so
    the owning entity's hash and identity stay stable. All other fields are
    mutable.

    Type Parameters:
        TId: Type of the entity identifier.

    Attributes:
        id: Identity of the entity. An `int`, `str`, `UUID`, enum, or a frozen
            value object such as `OrderId`.

    Note:
        The entity validates `id` when it is constructed:

        - it must not be `None` (generate ids up front);
        - it must be hashable;
        - a dataclass or attrs id must be frozen;
        - a non-builtin id type must define value-based `__eq__`.

    Warning:
        Without this base (a bare `@dataclass` state) the `id` protection is
        not enforced.

        Dataclasses forbid a frozen class inheriting from a non-frozen one
        (Python 3.13 and later also when another base is frozen), so a state and
        a snapshot cannot share a fields mixin. Use the attrs [`State`][fast_ddd.domain.flavors.attrs_models.State]
        flavor if you need that.

    Examples:
        ```python
        @dataclass(kw_only=True)
        class OrderLineState(DataclassState[int]):
            sku: str
            quantity: int
        ```
    """

    id: TId

    def __setattr__(self, name: str, value: object) -> None:
        """Set an attribute, refusing to reassign `id`.

        Raises:
            AttributeError: If `name` is `id` and it is already assigned.
        """
        if name == "id" and _is_assigned(self, "id"):
            raise AttributeError(
                f"{type(self).__qualname__}.id is immutable once assigned"
            )
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        """Delete an attribute, refusing to delete `id`.

        Raises:
            AttributeError: If `name` is `id`.
        """
        if name == "id":
            raise AttributeError(f"{type(self).__qualname__}.id cannot be deleted")
        object.__delattr__(self, name)


@dataclass(frozen=True, kw_only=True)
class DataclassSnapshot[TId: Hashable]:
    """Optional base class for an entity's immutable snapshot (dataclass flavor).

    A snapshot is a frozen memento holding a chosen subset of the state's
    fields. Declare subclasses with `@dataclass(frozen=True, kw_only=True)`.

    Nested entities appear as their own snapshots, inside `tuple`, `frozenset`
    or read-only mapping fields. The entity checks immutability deeply whenever
    a snapshot is produced or consumed. Mutable containers, live entities and
    non-frozen attrs or dataclass instances are rejected.

    Equality is by value, unlike the entity's identity-based equality.

    Type Parameters:
        TId: Type of the entity identifier.

    Attributes:
        id: Identity of the entity this snapshot belongs to.

    Examples:
        ```python
        @dataclass(frozen=True, kw_only=True)
        class OrderLineSnapshot(DataclassSnapshot[int]):
            sku: str
            quantity: int
        ```
    """

    id: TId


def _is_assigned(instance: object, name: str) -> bool:
    try:
        object.__getattribute__(instance, name)
    except AttributeError:
        return False
    return True
