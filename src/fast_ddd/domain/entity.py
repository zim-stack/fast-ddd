from abc import ABC
from collections.abc import Hashable
from dataclasses import dataclass
from enum import Enum
from functools import cache
from typing import TYPE_CHECKING, Any, ClassVar, cast, dataclass_transform


class BaseEntity[TId: Hashable](ABC):
    """Base class for all entity-like objects.

    Treats each hierarchy as one identity space, so that Customer(id=1) equals
    PremiumCustomer(id=1). The identity space is anchored at the first
    non-abstract class under BaseEntity or Entity, and is resolved once when
    the class is defined.

    Only `id` is protected against reassignment. All other attributes are
    mutable. Equality and hashing use `(identity root, id)`.

    Subclasses that define `__post_init__` must call `super().__post_init__()`.
    """

    # Resolved once per class in __init_subclass__. None marks abstract bases.
    _identity_root: ClassVar[type | None] = None

    if TYPE_CHECKING:

        @property
        def id(self) -> TId: ...

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._identity_root = None if abstract else _resolve_identity_root(cls)

    def __post_init__(self) -> None:
        _ensure_id_is_valid(self)
        _ensure_identity_verified(type(self))

    def __setattr__(self, name: str, value: object) -> None:
        if name == "id" and "id" in self.__dict__:
            raise AttributeError(
                f"{type(self).__qualname__}.id is immutable once assigned"
            )
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name == "id":
            raise AttributeError(f"{type(self).__qualname__}.id cannot be deleted")
        super().__delattr__(name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEntity):
            return NotImplemented
        return self._identity_root is other._identity_root and self.id == other.id

    def __hash__(self) -> int:
        return hash((self._identity_root, self.id))


@dataclass(kw_only=True, eq=False)
class Entity[TId: Hashable](BaseEntity[TId], ABC, abstract=True):
    """Base class for inner entities in a DDD aggregate.

    An entity is defined by its identity rather than its attributes. Two
    entities are equal when they share an identity root and their `id` values
    match, even if their other fields differ. Entities are owned by an
    aggregate root and are never persisted or loaded on their own; they are
    always accessed through the root.

    Scope of identity:
        Equality is only meaningful within ONE aggregate. `OrderLine(id=1)` in
        order A equals `OrderLine(id=1)` in order B, because an inner entity's
        id is local to its aggregate. Do not put inner entities from different
        aggregates in the same set, dict, or identity map. If you need
        globally unique identity, use a compound id that includes the
        aggregate's id, e.g. `OrderLineId(order_id, line_no)`.

    The ID type is a type parameter chosen by each subclass. It can be a UUID,
    an int, a string, or a value object such as `OrderId`. Rules enforced at
    construction time:
        - the id must not be None (use an id generated up front);
        - the id must be hashable;
        - a dataclass id must be frozen;
        - a non-builtin id type must define value-based `__eq__`.

    Mutability:
        Only `id` is immutable after construction. Other fields may change.

    Subclasses must use `@dataclass(kw_only=True, eq=False)` or `@entity`.
    Setting `eq=False` keeps the identity-based `__eq__` and `__hash__` from
    BaseEntity.

    Example:
        Value object as an ID.
        ```python
        @dataclass(frozen=True)
        class OrderId:
            value: UUID

            @classmethod
            def new(cls) -> Self:
                return cls(uuid4())

        @entity
        class OrderLine(Entity[OrderId]):
            sku: str
            quantity: int
        ```
    """

    id: TId


@dataclass_transform(kw_only_default=True, eq_default=False)
def entity[C: type](cls: C) -> C:
    """Class decorator that turns an `Entity` subclass into an identity-based dataclass.

    It applies `@dataclass(kw_only=True, eq=False)` to the class. Passing
    `eq=False` keeps the identity-based `__eq__` and `__hash__` inherited from
    `BaseEntity` instead of letting dataclasses generate field-based ones.
    After decoration, the decorator checks that neither method was overridden.

    Args:
        cls: The `Entity` subclass to decorate. Must inherit from `BaseEntity`.

    Returns:
        The same class with dataclass behavior applied.

    Raises:
        TypeError: If `cls` does not inherit from `BaseEntity`, or if the class
            overrides `__eq__` or `__hash__`.

    Example:
        ```python
        @entity
        class OrderLine(Entity[OrderId]):
            sku: str
            quantity: int
        ```

        Declaring `__eq__` in the body is rejected at definition time:
        ```python
        @entity
        class Broken(Entity[int]):
            def __eq__(self, other: object) -> bool:
                return True  # raises TypeError
        ```
    """
    if not issubclass(cls, BaseEntity):
        raise TypeError(
            f"@entity can only decorate BaseEntity subclasses, got {cls.__qualname__}"
        )
    decorated = dataclass(kw_only=True, eq=False)(cls)
    _check_identity_semantics(decorated)
    return cast(C, decorated)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_identity_root(cls: type) -> type:
    """Return the direct subclass of Entity that anchors cls's hierarchy."""
    parent_roots = {
        base._identity_root
        for base in cls.__bases__
        if isinstance(base, type)
        and issubclass(base, BaseEntity)
        and base._identity_root is not None
    }
    if len(parent_roots) > 1:
        names = ", ".join(sorted(r.__qualname__ for r in parent_roots))
        raise TypeError(
            f"{cls.__qualname__} inherits from several identity roots ({names}); "
            "an entity must belong to exactly one identity space"
        )
    return parent_roots.pop() if parent_roots else cls


def _ensure_id_is_valid(instance: object) -> None:
    """Fail at construction time if the entity's id is unusable as a key."""
    entity_id = getattr(instance, "id")
    owner = type(instance).__qualname__

    if entity_id is None:
        raise TypeError(f"{owner}.id must not be None; assign an id up front")
    try:
        hash(entity_id)
    except TypeError as exc:
        raise TypeError(
            f"{owner}.id must be hashable, got {type(entity_id).__qualname__}"
        ) from exc
    try:
        _ensure_id_type_has_value_semantics(type(entity_id))
    except TypeError as exc:
        raise TypeError(f"{owner}.id: {exc}") from exc


@cache
def _ensure_id_type_has_value_semantics(id_type: type) -> None:
    """Check once per id type that it compares by value and cannot mutate."""
    params = getattr(id_type, "__dataclass_params__", None)
    if params is not None and not params.frozen:
        raise TypeError(
            f"{id_type.__qualname__} is a dataclass and must be frozen=True"
        )
    is_builtin = id_type.__module__ == "builtins"
    # Enum members are singletons, so identity equality is value equality.
    if (
        not is_builtin
        and not issubclass(id_type, Enum)
        and id_type.__eq__ is object.__eq__
    ):
        raise TypeError(
            f"{id_type.__qualname__} uses identity equality; "
            "define __eq__ (e.g. a frozen dataclass) so equal ids compare equal"
        )


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
            "declare it with @dataclass(kw_only=True, eq=False)"
        )


def _ensure_identity_verified(cls: type) -> None:
    """Run the identity check once per class, at first instantiation."""
    if "_identity_verified" not in cls.__dict__:
        _check_identity_semantics(cls)
        setattr(cls, "_identity_verified", True)
