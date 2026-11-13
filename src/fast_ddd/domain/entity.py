import reprlib
import types
from abc import ABC
from collections.abc import (
    Collection,
    Hashable,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Sequence,
)
from collections.abc import Set as AbstractSet
from enum import Enum
from functools import cache
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    NamedTuple,
    Protocol,
    TypeVar,
    Union,
    get_args,
    get_origin,
    override,
)

from fast_ddd.domain.models import adapter_for
from fast_ddd.optional import require_attrs
from fast_ddd.utils import copy_if_mutable


def __getattr__(name: str) -> Any:
    """Lazy access to the attrs flavor, so attrs stays an optional dependency."""
    if name in ("State", "Snapshot"):
        require_attrs()  # raises the helpful ImportError if attrs is missing
        from fast_ddd.domain.flavors import attrs_models

        return getattr(attrs_models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    """Raise if cls overrides EntityIdentity's __eq__ or __hash__."""
    overridden = [n for n in ("__eq__", "__hash__") if n in cls.__dict__]
    if overridden:
        raise TypeError(
            f"{cls.__qualname__} overrides {' and '.join(overridden)}; "
            "identity semantics come from EntityIdentity"
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
        _ensure_id_is_valid(type(self), self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EntityIdentity):
            return NotImplemented
        return self._identity_root is other._identity_root and self.id == other.id

    def __hash__(self) -> int:
        return hash((self._identity_root, self.id))


class HasId(Protocol):
    """Structural contract for state and snapshot classes: they expose `id`."""

    @property
    def id(self) -> Any: ...


class Entity[TId: Hashable, M: HasId, S: HasId](
    EntityIdentity[TId], ABC, abstract=True
):
    """Base class for entities in a DDD aggregate.

    An entity is defined by its identity, not by its data: two entities are
    equal when they share an identity space and an `id`, whatever their other
    fields hold. It keeps its data in a private, mutable state (`_state`) and
    exposes it as a frozen, typed snapshot. It is always built from a snapshot
    and always produces one:

    ````
    snapshot -> Entity(snapshot) -> commands change _state -> to_snapshot()
    ````

    State and snapshot may be attrs classes or dataclasses, in any combination.
    The optional bases (`State`/`Snapshot` for attrs, `DataclassState`/
    `DataclassSnapshot` for dataclasses) add the `id` field and, for states,
    protect it against reassignment. Parametrize the entity directly with its
    types; they are validated once, when the class is defined. Intermediate
    bases that are never instantiated must be declared with `abstract=True`.

    Only `id` is immutable after construction. All other state fields may
    change through the entity's methods.

    The snapshot may expose any subset of the state fields. State-only fields
    need a default (or `init=False`) and are reset to it whenever the entity is
    rebuilt from a snapshot.

    Fields of `_state` that hold entities in a `list`, `tuple`, `set`,
    `frozenset` or `dict` are converted to snapshots and back automatically.
    The container kind of the restored value follows the state field's
    annotation (`list[...]`, `set[...]`, `dict[...]`, ...), so no converters are
    needed.

    Type Parameters:
        TId: Type of the entity identifier.
        M: Snapshot type returned by `to_snapshot()`. A frozen attrs class or
            frozen dataclass with an `id` field.
        S: Mutable state type, private to the entity as `_state`. An attrs class
            or dataclass with an `id` field.

    Note:
        The `id` is validated when the entity is constructed: it must not be
        `None`, must be hashable, must be frozen if it is an attrs class or
        dataclass, and a non-builtin id type must define value-based `__eq__`.

        Snapshots are validated whenever one is produced or consumed. Mutable
        containers, live entities, state objects and non-frozen attrs or
        dataclass instances are rejected at any depth.

    Note:
        Equality and hashing use `(identity root, id)`. A subclass of a concrete
        entity shares its parent's identity space, and each concrete class under
        an abstract base is its own. Overriding `__eq__` or `__hash__` is
        rejected when the class is defined.

    Warning:
        An inner entity's id is local to its aggregate. `OrderLine(id=1)` in
        order A equals `OrderLine(id=1)` in order B. Do not put inner entities
        from different aggregates in the same set, dict or identity map. If you
        need globally unique identity, use a compound id such as
        `OrderLineId(order_id, line_no)`.

    Warning:
        A concrete entity must name its types in its own base. Indirect
        parametrization through a generic intermediate base is not supported
        yet. A snapshot class belongs to exactly one concrete entity.

    Examples:
        ```python
        @attrs.define(kw_only=True)
        class OrderLineState(State[int]):
            sku: str
            quantity: int

        @attrs.frozen(kw_only=True)
        class OrderLineSnapshot(Snapshot[int]):
            sku: str
            quantity: int

        class OrderLine(Entity[int, OrderLineSnapshot, OrderLineState]):
            def change_quantity(self, quantity: int) -> None:
                self._state.quantity = quantity
        ```

        An entity that holds other entities. The annotation decides that the
        restored value is a `list`:

        ```python
        @attrs.define(kw_only=True)
        class PackageState(State[int]):
            lines: list[OrderLine] = attrs.field(factory=list)
        ```
    """

    # Filled in by __init_subclass__; do not declare them in subclasses.
    _state_cls: type[S]
    _snapshot_cls: type[M]
    _shared_fields: ClassVar[tuple["_SharedField", ...]]
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

        _bind_types(cls, snapshot_cls, state_cls, abstract=abstract)

    def __init__(self, snapshot: M) -> None:
        if not isinstance(snapshot, self._snapshot_cls):
            raise TypeError(
                f"{type(self).__qualname__} expects a {self._snapshot_cls.__name__}, "
                f"got {type(snapshot).__qualname__}"
            )
        _ensure_id_is_valid(type(self), snapshot.id)
        self._state: S = self._state_from_snapshot(snapshot)

    @override
    @property
    def id(self) -> TId:
        return self._state.id

    def to_snapshot(self) -> M:
        """Produce a deeply immutable snapshot of the current state.

        Returns:
            A snapshot instance containing the shared fields at the time of the call.

        Raises:
            TypeError: If a state value cannot be represented immutably.
        """
        data = {
            f.snapshot_init: _freeze(getattr(self._state, f.name))
            for f in self._shared_fields
        }
        snapshot = self._snapshot_cls(**data)
        _ensure_snapshot_is_immutable(snapshot)
        return snapshot

    # -- Helpers ----------------------------------------------------

    def _state_from_snapshot(self, snapshot: M) -> S:
        """Reconstruct a mutable state instance from an immutable snapshot."""
        _ensure_snapshot_is_immutable(snapshot)
        data = {
            f.state_init: _thaw(getattr(snapshot, f.name), f.state_annotation)
            for f in self._shared_fields
            if f.state_init is not None
        }
        return self._state_cls(**data)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(state={reprlib.repr(self._state)})"

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.id})"


# ---------------------------------------------------------------------------
# Private utils
# ---------------------------------------------------------------------------


class _SharedField(NamedTuple):
    """A snapshot field and where its value lives on the state."""

    name: str  # attribute name, same on state and snapshot
    snapshot_init: str  # snapshot __init__ keyword
    state_init: str | None  # state __init__ keyword, None if not init-able
    state_annotation: Any  # drives the container kind when restoring


_ENTITY_BY_SNAPSHOT: dict[type, type[Entity]] = {}
_STATE_CLASSES: set[type] = set()
_MUTABLE_ABCS = (MutableSequence, MutableMapping, MutableSet)

# Concrete and mutable-abstract annotations -> the container restored in state.
_STATE_KINDS: dict[Any, type] = {
    list: list,
    set: set,
    frozenset: frozenset,
    tuple: tuple,
    dict: dict,
    MutableSequence: list,
    MutableSet: set,
    MutableMapping: dict,
}
# Read-only abstract annotations: the default thawed kind already satisfies
# them, but their element annotations still guide nested restoration.
_SEQUENCE_LIKE = (Sequence, AbstractSet, Collection, Iterable)


def _generic_args(cls: type) -> tuple[Any, ...] | None:
    """Return (TId, M, S) from a direct `Entity[...]`/`Aggregate[...]` base."""
    for base in cls.__dict__.get("__orig_bases__", ()):
        origin = get_origin(base)
        if isinstance(origin, type) and issubclass(origin, Entity):
            args = get_args(base)
            if len(args) == 3:
                return args
    return None


class _TypeBinder:
    """Validates a state/snapshot pair and caches what Entity instances need."""

    def __init__(
        self,
        cls: type[Entity[Any, Any, Any]],
        snapshot_cls: Any,
        state_cls: Any,
        *,
        abstract: bool,
    ) -> None:
        self.cls = cls
        self.abstract = abstract
        self.owner = cls.__qualname__
        self.snapshot_cls = get_origin(snapshot_cls) or snapshot_cls
        self.state_cls = get_origin(state_cls) or state_cls

    def bind(self) -> None:
        self._resolve_adapters()
        self._check_frozen()
        self._collect_fields()
        self._check_id_fields()
        self._check_init_fields()
        self._check_definitions()
        self._commit()

    def _resolve_adapters(self) -> None:
        """Find an attrs or dataclass adapter for both the state and snapshot types."""
        adapters = {}
        for label, klass in (
            ("state", self.state_cls),
            ("snapshot", self.snapshot_cls),
        ):
            adapter = adapter_for(klass)
            if adapter is None:
                raise TypeError(
                    f"{self.owner}: {label} type must be an attrs class or a dataclass, "
                    f"got {klass!r}"
                )
            adapters[label] = adapter
        self.state_adapter = adapters["state"]
        self.snapshot_adapter = adapters["snapshot"]

    def _check_frozen(self) -> None:
        """Require the snapshot type to be frozen."""
        if not self.snapshot_adapter.is_frozen(self.snapshot_cls):
            raise TypeError(
                f"{self.owner}: snapshot type {self.snapshot_cls.__name__} must be frozen "
                f"({self.snapshot_adapter.frozen_hint})"
            )

    def _collect_fields(self) -> None:
        """Read the field descriptions of the state and snapshot types."""
        self.state_fields = {
            f.name: f for f in self.state_adapter.fields(self.state_cls)
        }
        self.snapshot_fields = self.snapshot_adapter.fields(self.snapshot_cls)
        self.snapshot_names = {f.name for f in self.snapshot_fields}

    def _check_id_fields(self) -> None:
        """Require an `id` field on both the state and the snapshot."""
        for label, names in (
            ("state", self.state_fields.keys()),
            ("snapshot", self.snapshot_names),
        ):
            if "id" not in names:
                raise TypeError(f"{self.owner}: {label} type must define an `id` field")

    def _check_init_fields(self) -> None:
        """Ensure the state can accept every snapshot field and fill its own extras."""
        missing = sorted(
            f.name
            for f in self.snapshot_fields
            if f.init and f.name not in self.state_fields
        )
        if missing:
            raise TypeError(
                f"{self.owner}: {self.state_cls.__name__} is missing fields required by "
                f"{self.snapshot_cls.__name__}: {missing}"
            )

        unfillable = sorted(
            name
            for name, f in self.state_fields.items()
            if name not in self.snapshot_names and f.init and not f.has_default
        )
        if unfillable:
            raise TypeError(
                f"{self.owner}: {self.state_cls.__name__} requires fields not present on "
                f"{self.snapshot_cls.__name__} and with no default: {unfillable}"
            )

    def _check_definitions(self) -> None:
        """Reject raw dataclasses.Field defaults on either type."""
        issues = self.state_adapter.definition_issues(
            self.state_cls
        ) + self.snapshot_adapter.definition_issues(self.snapshot_cls)
        if issues:
            raise TypeError(
                f"{self.owner}: {issues} default to a raw dataclasses.Field; "
                "use attrs.field(...) instead of dataclasses.field(...)"
            )

    def _commit(self) -> None:
        """Register the snapshot pairing and cache the binding on the entity class."""
        # An abstract class never claims a snapshot: only concrete entities can be
        # restored from one.
        if self.cls._nestable and not self.abstract:  # type: ignore[attr-defined]
            self._register_snapshot()
        _STATE_CLASSES.add(self.state_cls)

        self.cls._state_cls = self.state_cls  # type: ignore[attr-defined]
        self.cls._snapshot_cls = self.snapshot_cls  # type: ignore[attr-defined]
        self.cls._shared_fields = self._shared_field_specs()  # type: ignore[attr-defined]

    def _register_snapshot(self) -> None:
        """Pair the snapshot class with this entity, one entity per snapshot."""
        existing = _ENTITY_BY_SNAPSHOT.get(self.snapshot_cls)
        if existing is not None and existing is not self.cls:
            raise TypeError(
                f"{self.owner}: {self.snapshot_cls.__name__} is already paired with "
                f"{existing.__qualname__}; one snapshot class per entity"
            )
        _ENTITY_BY_SNAPSHOT[self.snapshot_cls] = self.cls  # type: ignore[assignment]

    def _shared_field_specs(self) -> tuple[_SharedField, ...]:
        """Build the snapshot-to-state field mapping used at runtime."""
        return tuple(
            _SharedField(
                name=f.name,
                snapshot_init=f.init_name,
                state_init=(
                    self.state_fields[f.name].init_name
                    if self.state_fields[f.name].init
                    else None
                ),
                state_annotation=self.state_fields[f.name].annotation,
            )
            for f in self.snapshot_fields
            if f.init
        )


def _bind_types(
    cls: type[Entity[Any, Any, Any]],
    snapshot_cls: Any,
    state_cls: Any,
    *,
    abstract: bool,
) -> None:
    """Validate the state/snapshot pair once and cache what instances need."""
    _TypeBinder(cls, snapshot_cls, state_cls, abstract=abstract).bind()


# -- State <-> snapshot conversion ------------------------------------------


def _unwrap_annotation(annotation: Any) -> Any:
    """Strip Annotated[...] and Optional/`| None`. Returns None if ambiguous."""
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
        elif origin is Union or origin is types.UnionType:
            args = [a for a in get_args(annotation) if a is not type(None)]
            if len(args) != 1:
                return None
            annotation = args[0]
        else:
            return annotation


def _container_hint(annotation: Any) -> tuple[type | None, Any, Any]:
    """Return (kind to restore, item annotation, mapping value annotation)."""
    annotation = _unwrap_annotation(annotation) if annotation is not None else None
    if annotation is None:
        return None, None, None
    origin = get_origin(annotation) or annotation
    args = get_args(annotation)
    try:
        kind = _STATE_KINDS.get(origin)
    except TypeError:  # unhashable annotation object
        kind = None

    if kind is dict:
        return dict, None, args[1] if len(args) == 2 else None
    if kind is tuple:
        return tuple, args[0] if len(args) == 2 and args[1] is Ellipsis else None, None
    if kind is not None:  # list, set, frozenset
        return kind, args[0] if args else None, None
    if origin in _SEQUENCE_LIKE:
        return None, args[0] if args else None, None
    if origin is Mapping:
        return None, None, args[1] if len(args) == 2 else None
    return None, None, None


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


def _thaw(value: Any, annotation: Any = None) -> Any:
    """Snapshot value -> state value.

    The state field's annotation picks the container kind (list, set, ...).
    Without a usable annotation the snapshot's own kind is kept.
    """
    entity_cls = _ENTITY_BY_SNAPSHOT.get(type(value))
    if entity_cls is not None:
        return entity_cls(value)
    if isinstance(value, (tuple, frozenset)):
        kind, item_annotation, _ = _container_hint(annotation)
        items = [_thaw(v, item_annotation) for v in value]
        if kind not in (list, set, frozenset, tuple):
            kind = tuple if isinstance(value, tuple) else frozenset
        return kind(items)
    if isinstance(value, Mapping):
        _, _, value_annotation = _container_hint(annotation)
        return {k: _thaw(v, value_annotation) for k, v in value.items()}
    adapter = adapter_for(type(value))
    if adapter is not None and adapter.is_frozen(type(value)):
        return value  # frozen and already validated: safe to share
    return copy_if_mutable(value)


# -- Validation -----------------------------------------------------------------


class _ImmutabilityChecker:
    """Boundary validation: snapshots must be deeply immutable at every depth."""

    @classmethod
    def check_snapshot(cls, snapshot: object) -> None:
        """Check every field of a snapshot is deeply immutable."""
        snapshot_cls = type(snapshot)
        adapter = adapter_for(snapshot_cls)
        assert adapter is not None  # guaranteed by _bind_types
        for f in adapter.fields(snapshot_cls):
            cls.check_value(
                f"{snapshot_cls.__name__}.{f.name}", getattr(snapshot, f.name)
            )

    @classmethod
    def check_value(cls, path: str, value: object) -> None:
        """Check a single value, rejecting  mutable containers, entities, state objects and non-frozen models."""
        cls._reject_forbidden_kinds(path, value)

        if isinstance(value, (tuple, frozenset, Mapping)):
            cls._check_container_items(path, value)
            return

        adapter = adapter_for(type(value))
        if adapter is None:
            return
        cls._check_frozen_model(path, value, adapter)

    @classmethod
    def _reject_forbidden_kinds(cls, path: str, value: object) -> None:
        """Reject entities, state objects and mutable containers."""
        value_cls = type(value)
        if isinstance(value, EntityIdentity) or value_cls in _STATE_CLASSES:
            raise TypeError(
                f"{path} holds {value_cls.__name__}; use its snapshot instead"
            )
        if isinstance(value, _MUTABLE_ABCS):
            raise TypeError(
                f"{path} holds a mutable {value_cls.__name__}; use an immutable "
                "type (tuple, frozenset, Mapping view)"
            )

    @classmethod
    def _check_container_items(
        cls, path: str, value: tuple | frozenset | Mapping
    ) -> None:
        """Recurse into the items of a tuple, frozenset or mapping."""
        if isinstance(value, Mapping):
            for k, item in value.items():
                cls.check_value(f"{path}[{k!r}]", item)
        else:
            for i, item in enumerate(value):
                cls.check_value(f"{path}[{i}]", item)

    @classmethod
    def _check_frozen_model(cls, path: str, value: object, adapter: Any) -> None:
        """Require an attrs/dataclass instance to be frozen and check its fields."""
        value_cls = type(value)
        if not adapter.is_frozen(value_cls):
            raise TypeError(
                f"{path} holds a non-frozen {value_cls.__name__}; "
                f"declare it with {adapter.frozen_hint}"
            )
        if value_cls in _ENTITY_BY_SNAPSHOT:
            return  # validated when its entity is constructed or snapshotted
        for f in adapter.fields(value_cls):
            cls.check_value(f"{path}.{f.name}", getattr(value, f.name))


def _ensure_snapshot_is_immutable(snapshot: object) -> None:
    """Boundary check: every field of a snapshot must be deeply immutable."""
    _ImmutabilityChecker.check_snapshot(snapshot)


def _ensure_id_is_valid(owner: type, entity_id: object) -> None:
    """Fail at construction time if the entity's id is unusable as a key."""
    name = owner.__qualname__
    if entity_id is None:
        raise TypeError(f"{name}.id must not be None; assign an id up front")
    try:
        hash(entity_id)
    except TypeError as exc:
        raise TypeError(
            f"{name}.id must be hashable, got {type(entity_id).__qualname__}"
        ) from exc
    try:
        _ensure_id_type_has_value_semantics(type(entity_id))
    except TypeError as exc:
        raise TypeError(f"{name}.id: {exc}") from exc


@cache
def _ensure_id_type_has_value_semantics(id_type: type) -> None:
    """Check once per id type that it compares by value and cannot mutate."""
    adapter = adapter_for(id_type)
    if adapter is not None and not adapter.is_frozen(id_type):
        raise TypeError(
            f"{id_type.__qualname__} is {adapter.label} and "
            f"must be {adapter.frozen_hint}"
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
