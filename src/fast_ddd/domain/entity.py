from abc import ABC
from collections.abc import Hashable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast, dataclass_transform


class BaseEntity[TId: Hashable](ABC):
    """
    Base class for all entity-like objects.

    Treats hierarchy as one identity space, so that Customer(id=1) equals PremiumCustomer(id=1)
    """

    if TYPE_CHECKING:

        @property
        def id(self) -> TId: ...

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEntity):
            return NotImplemented
        return (
            _identity_root(type(self)) is _identity_root(type(other))
            and self.id == other.id
        )

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(frozen=True, kw_only=True, eq=False)
class Entity[TId: Hashable](BaseEntity[TId], ABC):
    """
    Base class for inner entities in DDD aggregate.

    An entity is defined by its identity rather than its attributes. Two
    entities are equal when their `id` values match, even if their other
    fields differ. Entities are owned by an aggregate root and are never
    persisted or loaded on their own; they are always accessed through the
    root.

    The ID type is a type parameter chosen by each subclass. It can be a
    UUID, an int, a string, or a value object such as `OrderId`. The ID must
    be hashable; a frozen dataclass is recommended so it compares by value.

    Subclasses must use `@dataclass(frozen=True, kw_only=True, eq=False)`.
    Setting `eq=False` keeps the identity-based `__eq__` and `__hash__` from
    this class.

    Example:
        Value object as an ID.
        ```python
        @dataclass(frozen=True)
        class OrderId:
            value: UUID

            @classmethod
            def new(cls) -> Self:
                return cls(uuid4())

        @dataclass(frozen=True, kw_only=True, eq=False)
        class OrderLine(Entity[OrderId]):
            sku: str
            quantity: int
        ```
    """

    id: TId

    def __post_init__(self) -> None:
        _ensure_id_is_hashable(self)
        _ensure_identity_verified(type(self))


@dataclass_transform(frozen_default=True, kw_only_default=True, eq_default=False)
def entity[C: type](cls: C) -> C:
    """
    Class decorator that turns an `Entity` subclass into an identity-based frozen dataclass.

    It applies `@dataclass(frozen=True, kw_only=True, eq=False)` to the class.
    Passing `eq=False` keeps the identity-based `__eq__` and `__hash__` inherited
    from `BaseEntity` instead of letting dataclasses generate field-based ones.
    After decoration, the decorator checks that neither method was overridden.

    Args:
        cls: The `Entity` subclass to decorate. Must inherit from `BaseEntity`.

    Returns:
        The same class, rebuilt as a frozen dataclass. The return type matches
            the input type, so type checkers keep the original class signature.

    Raises:
        TypeError: If `cls` does not inherit from `BaseEntity`, or if the class
            overrides `__eq__` or `__hash__`.

    Example:
        Decorate an entity:
        ```python
        @entity
        class OrderLine(Entity[OrderId]):
            sku: str
            quantity: int
        ```

        Declaring `__eq__` in the body is rejected at definition time
        ```python
        @entity
        class Broken(Entity[int]):
            def __eq__(self, other: object) -> bool:
                return True  # raises TypeError
        ```
    """
    if not issubclass(cls, BaseEntity):
        raise TypeError(
            f"@entity can only decorate Entity subclasses, got {cls.__qualname__}"
        )
    decorated = dataclass(frozen=True, kw_only=True, eq=False)(cls)
    _check_identity_semantics(decorated)
    return cast(C, decorated)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _identity_root(cls: type) -> type:
    """Return the direct subclass of Entity that anchors cls's hierarchy."""
    for klass in cls.__mro__:
        if Entity in klass.__bases__:
            return klass
    return cls


def _ensure_id_is_hashable(instance: object) -> None:
    """Fail at construction time if the entity's id cannot be hashed."""
    entity_id = getattr(instance, "id")
    try:
        hash(entity_id)
    except TypeError as exc:
        raise TypeError(
            f"{type(instance).__qualname__}.id must be hashable, "
            f"got {type(entity_id).__qualname__}"
        ) from exc


def _check_identity_semantics(cls: type) -> None:
    """Raise if cls overrides BaseEntity's __eq__ or __hash__. Does not cache."""
    overridden = [
        name
        for name in ("__eq__", "__hash__")
        if getattr(cls, name) is not getattr(BaseEntity, name)
    ]
    if overridden:
        raise TypeError(
            f"{cls.__qualname__} overrides {' and '.join(overridden)}; "
            "declare it with @dataclass(frozen=True, kw_only=True, eq=False)"
        )


def _ensure_identity_verified(cls: type) -> None:
    """Run the identity check once per class, at first instantiation."""
    if "_identity_verified" not in cls.__dict__:
        _check_identity_semantics(cls)
        setattr(cls, "_identity_verified", True)
