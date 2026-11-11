import dataclasses
import reprlib
from abc import ABC
from collections.abc import (
    Hashable,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
)
from enum import Enum
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, get_args, get_origin, override

import attrs

from fast_ddd.utils import copy_if_mutable


def _resolve_identity_root(cls: type) -> type:
    """Return the direct subclass of Entity that anchors cls's hierarchy."""
    parent_roots = {
        base._identity_root
        for base in cls.__bases__
        if isinstance(base, type)
        and issubclass(base, EntityIdentity)
        and base._identity_root is not None
    }
    if len(parent_roots) > 1:
        names = ", ".join(sorted(r.__qualname__ for r in parent_roots))
        raise TypeError(
            f"{cls.__qualname__} inherits from several identity roots ({names}); "
            "an entity must belong to exactly one identity space"
        )
    return parent_roots.pop() if parent_roots else cls


def _check_identity_semantics(cls: type) -> None:
    """Raise if cls overrides BaseEntity's __eq__ or __hash__."""
    overridden = [n for n in ("__eq__", "__hash__") if n in cls.__dict__]
    if overridden:
        raise TypeError(
            f"{cls.__qualname__} overrides {' and '.join(overridden)}; "
            "identity semantics come from BaseEntity"
        )


class EntityIdentity[TId: Hashable](ABC):
    """
    Base class for all identity-like objects.

    Treats each hierarchy as one identity space, so that Customer(id=1) equals
    PremiumCustomer(id=1). The identity space is anchored at the first
    non-abstract class below EntityIdentity, and is resolved once when
    the class is defined.

    `id` is protected against reassignment.

    Equality and hash use `(identity root, id)`.
    Overriding `__eq__` or `__hash__` is rejected at class definition.
    """

    _identity_root: ClassVar[type | None] = None  # None marks abstract bases.

    if TYPE_CHECKING:

        @property
        def id(self) -> TId: ...

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _check_identity_semantics(cls)
        cls._identity_root = None if abstract else _resolve_identity_root(cls)

    def _validate_id(self) -> None:
        _ensure_id_is_valid(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EntityIdentity):
            return NotImplemented
        return self._identity_root is other._identity_root and self.id == other.id

    def __hash__(self) -> int:
        return hash((self._identity_root, self.id))


# Only one parent may contribute a non-empty __slots__.
@attrs.define(kw_only=True, slots=False)
class State[TId: Hashable]:
    """Mutable container for an entity's data.

    Attributes:
        id: Identity field. Cannot be reassigned after construction.
            Can be a UUID, an int, a string, or a value object such as `OrderId`.
                Rules enforced at construction time:
                    - the id must not be None (use an id generated up front);
                    - the id must be hashable;
                    - a dataclass id must be frozen;
                    - a non-builtin id type must define value-based `__eq__`.
    """

    id: TId = attrs.field(on_setattr=attrs.setters.frozen)


# attrs library allows a frozen class to inherit from a non-frozen one
# Only one parent may contribute a non-empty __slots__.
@attrs.frozen(kw_only=True, slots=False)
class Snapshot[TId: Hashable]:
    """Immutable Memento of an entity, holding a chosen subset of its state fields.

    Nested entities appear as their own Snapshot, inside tuple, frozenset
    or Mapping fields.

    Mutable containers are rejected (see
    `_ensure_deeply_immutable`).
    Use tuple/frozenset/Mapping fields, with an attrs converter if the state holds
    the mutable equivalent:

        tags: tuple[str, ...] = attrs.field(converter=tuple)

    Equality is by value, unlike the entity's.
    Subclasses that define `__attrs_post_init__` must call
    `super().__attrs_post_init__()`.
    """

    id: TId

    def __attrs_post_init__(self) -> None:
        owner = type(self).__name__
        for f in attrs.fields(type(self)):
            _ensure_deeply_immutable(f"{owner}.{f.name}", getattr(self, f.name))


class Entity[TId: Hashable, M: Snapshot, S: State](
    EntityIdentity[TId], ABC, abstract=True
):
    """Base class for inner entities in a DDD aggregate.

    Type Parameters:
        TId: Type of the entity identifier.
        M: Snapshot type returned by `to_snapshot()`.
        S: Internal state type that holds internal mutable data.

    Scope of identity:
        Equality is only meaningful within ONE aggregate. `OrderLine(id=1)` in
        order A equals `OrderLine(id=1)` in order B, because an inner entity's
        id is local to its aggregate.
        Do not put inner entities from different aggregates in the same set,
        dict, or identity map.
        If you need globally unique identity, use a compound id that includes the
        aggregate's id, e.g. `OrderLineId(order_id, line_no)`.

    Mutability:
        Only `id` is immutable after construction. Other fields may change.

    Entity has mutable state and a frozen, typed snapshot.

        class OrderLine(Entity[OrderLineId, OrderLineSnapshot, OrderLineState]): ...

    The snapshot may expose any subset of the state fields.
    State-only fields need a default (or init=False) and are reset to
    it when the entity is rebuilt from a snapshot.

    Fields of `_state` holding entities (list/tuple/set/frozenset/dict) are
    converted to snapshots and back. Give the state field a converter for its
    container type, so the restored value gets the right kind:

        lines: list[OrderLine] = attrs.field(factory=list, converter=list)
    """

    # Filled in by __init_subclass__; do not declare them in subclasses.
    _state_cls: type[S]
    _snapshot_cls: type[M]
    _shared_field_names: ClassVar[tuple[str, ...]]
    _nestable: ClassVar[bool] = (
        True  # an entity may appear inside another entity’s state
    )

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        super().__init_subclass__(abstract=abstract, **kwargs)

        args = _generic_args(cls)
        if args is None:
            if not abstract and not hasattr(cls, "_state_cls"):
                raise TypeError(
                    f"{cls.__qualname__} must parametrize its entity base directly, "
                    "e.g. Entity[OrderLineId, MySnapshot, MyState], "
                    "or be declared with abstract=True"
                )
            return

        _, snapshot_cls, state_cls = args
        if isinstance(snapshot_cls, TypeVar) or isinstance(state_cls, TypeVar):
            if not abstract:
                raise TypeError(
                    f"{cls.__qualname__} leaves snapshot/state types unresolved; "
                    "pass concrete types or declare it with abstract=True"
                )
            return

        _bind_types(cls, snapshot_cls, state_cls)

    def __init__(self, snapshot: M) -> None:
        self._state: S = self._state_from_snapshot(snapshot)
        self._validate_id()

    @override
    @property
    def id(self) -> TId:
        return self._state.id

    def to_snapshot(self) -> M:
        """Produce a deeply immutable snapshot of the current state.

        Returns:
            A snapshot instance containing the shared fields at the time of the call.
        """
        data = {n: _freeze(getattr(self._state, n)) for n in self._shared_field_names}
        return self._snapshot_cls(**data)

    # -- Helpers ----------------------------------------------------

    def _state_from_snapshot(self, snapshot: M) -> S:
        """Reconstruct a mutable state instance from an immutable snapshot."""
        data = {n: _thaw(getattr(snapshot, n)) for n in self._shared_field_names}
        return self._state_cls(**data)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(state={reprlib.repr(self._state)})"

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.id})"


# ---------------------------------------------------------------------------
# Private utils
# ---------------------------------------------------------------------------

_ENTITY_BY_SNAPSHOT: dict[type, type[Entity]] = {}
_MUTABLE_ABCS = (MutableSequence, MutableMapping, MutableSet)


def _generic_args(cls: type) -> tuple[Any, ...] | None:
    """Return (TId, M, S) from a direct `Entity[...]`/`Aggregate[...]` base."""
    for base in cls.__dict__.get("__orig_bases__", ()):
        origin = get_origin(base)
        if isinstance(origin, type) and issubclass(origin, Entity):
            args = get_args(base)
            if len(args) == 3:
                return args
    return None


def _bind_types(
    cls: type[Entity[Any, Any, Any]], snapshot_cls: Any, state_cls: Any
) -> None:
    """Validate the state/snapshot pair once and cache what instances need."""
    owner = cls.__qualname__
    snapshot_cls = get_origin(snapshot_cls) or snapshot_cls
    state_cls = get_origin(state_cls) or state_cls

    for label, klass, base in (
        ("state", state_cls, State),
        ("snapshot", snapshot_cls, Snapshot),
    ):
        if not (
            isinstance(klass, type) and issubclass(klass, base) and attrs.has(klass)
        ):
            raise TypeError(
                f"{owner}: {label} type must be an attrs class deriving from "
                f"{base.__name__}, got {klass!r}"
            )

    state_fields = {f.name: f for f in attrs.fields(state_cls)}
    snapshot_names = [f.name for f in attrs.fields(snapshot_cls)]

    missing = sorted(set(snapshot_names) - state_fields.keys())
    if missing:
        raise TypeError(
            f"{owner}: {state_cls.__name__} is missing fields required by "
            f"{snapshot_cls.__name__}: {missing}"
        )

    unfillable = sorted(
        name
        for name, f in state_fields.items()
        if name not in snapshot_names and f.init and f.default is attrs.NOTHING
    )
    if unfillable:
        raise TypeError(
            f"{owner}: {state_cls.__name__} requires fields not present on "
            f"{snapshot_cls.__name__} and with no default: {unfillable}"
        )

    stray = [
        f"{klass.__name__}.{f.name}"
        for klass in (state_cls, snapshot_cls)
        for f in attrs.fields(klass)
        if isinstance(f.default, dataclasses.Field)
    ]
    if stray:
        raise TypeError(
            f"{owner}: {stray} default to a raw dataclasses.Field; "
            "use attrs.field(...) instead of dataclasses.field(...)"
        )

    if cls._nestable:  # type: ignore[attr-defined]
        existing = _ENTITY_BY_SNAPSHOT.get(snapshot_cls)
        if existing is not None and existing is not cls:
            raise TypeError(
                f"{owner}: {snapshot_cls.__name__} is already paired with "
                f"{existing.__qualname__}; one snapshot class per entity"
            )
        _ENTITY_BY_SNAPSHOT[snapshot_cls] = cls  # type: ignore[assignment]

    cls._state_cls = state_cls  # type: ignore[attr-defined]
    cls._snapshot_cls = snapshot_cls  # type: ignore[attr-defined]
    cls._shared_field_names = tuple(snapshot_names)  # type: ignore[attr-defined]


def _freeze(value: Any) -> Any:
    """State value -> snapshot value (entities become snapshots, containers frozen)."""
    if isinstance(value, Entity):
        if not value._nestable:
            raise TypeError(
                f"{type(value).__qualname__} is not nestable; "
                "aggregates reference each other by id"
            )
        return value.to_snapshot()
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(v) for v in value)
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    return copy_if_mutable(value)


def _thaw(value: Any) -> Any:
    """Snapshot value -> state value. The state field's converter picks the container."""
    if isinstance(value, Snapshot):
        entity_cls = _ENTITY_BY_SNAPSHOT.get(type(value))
        return entity_cls(value) if entity_cls is not None else value
    if isinstance(value, tuple):
        return tuple(_thaw(v) for v in value)
    if isinstance(value, frozenset):
        return frozenset(_thaw(v) for v in value)
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    return copy_if_mutable(value)


def _ensure_deeply_immutable(path: str, value: object) -> None:
    """Reject mutable containers, entities and state objects, at any depth."""
    if isinstance(value, (EntityIdentity, State)):
        raise TypeError(
            f"{path} holds {type(value).__name__}; use its snapshot instead"
        )
    if isinstance(value, _MUTABLE_ABCS):
        raise TypeError(
            f"{path} holds a mutable {type(value).__name__}; use an immutable "
            "type (tuple, frozenset, Mapping view) or an attrs converter"
        )
    if isinstance(value, (tuple, frozenset)):
        for i, item in enumerate(value):
            _ensure_deeply_immutable(f"{path}[{i}]", item)
    elif isinstance(value, Mapping):
        for k, item in value.items():
            _ensure_deeply_immutable(f"{path}[{k!r}]", item)


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
