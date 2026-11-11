import dataclasses
import reprlib
from abc import ABC
from collections.abc import Hashable, MutableMapping, MutableSequence, MutableSet
from typing import Any, ClassVar, TypeVar, get_args, get_origin, override

import attrs

from fast_ddd.domain.entity import BaseEntity
from fast_ddd.domain.event import DomainEvent
from fast_ddd.utils import copy_if_mutable


# Only one parent may contribute a non-empty __slots__.
@attrs.define(kw_only=True, slots=False)
class AggregateState[TId: Hashable]:
    """Mutable container for an aggregate's data.

    `id` cannot be reassigned after construction, so the aggregate's hash and
    identity stay stable.
    """

    id: TId = attrs.field(on_setattr=attrs.setters.frozen)


# attrs library allows a frozen class to inherit from a non-frozen one
# Only one parent may contribute a non-empty __slots__.
@attrs.frozen(kw_only=True, slots=False)
class AggregateSnapshot[TId: Hashable]:
    """Immutable Memento-like representation of an aggregate. Always has id.

    Immutability is checked deeply for the standard mutable containers (list,
    dict, set, bytearray, ...), including inside tuples and frozensets. Use
    tuple/frozenset/Mapping fields, with an attrs converter if the state holds
    the mutable equivalent:

        tags: tuple[str, ...] = attrs.field(converter=tuple)

    Subclasses that define `__attrs_post_init__` must call
    `super().__attrs_post_init__()`.
    """

    id: TId

    def __attrs_post_init__(self) -> None:
        owner = type(self).__name__
        for f in attrs.fields(type(self)):
            _ensure_deeply_immutable(f"{owner}.{f.name}", getattr(self, f.name))


# Todo Support Indirect parametrization (isn’t supported).
#  class Tok(Base[Snap, State]), where Base is a generic intermediate that itself parametrizes Aggregate, fails with “must parametrize Aggregate directly”.
#  Resolving it needs a TypeVar substitution map.
class Aggregate[TId: Hashable, M: AggregateSnapshot, S: AggregateState](
    BaseEntity[TId], ABC, abstract=True
):
    """Base class for aggregate roots.

    Parametrize it directly with the id, snapshot and state types:

        class RefreshToken(Aggregate[UUID, RefreshTokenSnapshot, RefreshTokenState]): ...

    The state and snapshot classes are read from these arguments and validated
    once, when the subclass is defined. A subclass of a concrete aggregate
    inherits the binding. Intermediate abstract aggregates must be declared
    with `abstract=True`.
    """

    # Filled in by __init_subclass__; do not declare them in subclasses.
    _state_cls: type[S]
    _snapshot_cls: type[M]
    _shared_field_names: ClassVar[tuple[str, ...]]

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        super().__init_subclass__(abstract=abstract, **kwargs)

        args = _generic_args_of_aggregate(cls)
        if args is None:
            # Not parametrized here: fine if it inherits a binding or is abstract.
            if not abstract and not hasattr(cls, "_state_cls"):
                raise TypeError(
                    f"{cls.__qualname__} must parametrize Aggregate directly, "
                    "e.g. Aggregate[UUID, MySnapshot, MyState], "
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
        self._state = self._state_from_snapshot(snapshot)
        self._domain_events: list[DomainEvent] = []
        self.__post_init__()  # validates id (None, hashability, value semantics)

    @override
    @property
    def id(self) -> TId:
        return self._state.id

    def to_snapshot(self) -> M:
        """Capture the aggregate's current state as an immutable snapshot.

        Invariants are validated before capture, so a snapshot is only
        produced from a consistent aggregate.
        Mutable field values are copied, so later changes to the aggregate do not affect the snapshot.

        Returns:
            A snapshot instance of type ``M`` containing the shared fields at the time of the call.

        Raises:
            Exception: Whatever `_validate_invariants` hook raises when the
                aggregate's invariants do not hold.
        """
        self._validate_invariants()
        data = {
            name: copy_if_mutable(getattr(self._state, name))
            for name in self._shared_field_names
        }
        return self._snapshot_cls(**data)

    def pull_domain_events(self) -> list[DomainEvent]:
        """Return all recorded domain events and clear the list."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

    # -- Hooks --------------------------------------------------------------

    def _validate_invariants(self) -> None:
        """Check aggregate invariants before a snapshot is taken.

        The default implementation does nothing. Subclasses override this
        method to enforce their own invariants.

        Raises:
            Exception: Subclasses should raise when an invariant is violated.
                Use the specific exception type your domain defines.
        """
        pass

    # -- Helpers ------------------------------------------------------------

    def _record_event(self, event: DomainEvent) -> None:
        """Record domain event. Called inside command methods."""
        self._domain_events.append(event)

    def _state_from_snapshot(self, snapshot: M) -> S:
        """Reconstruct a mutable state instance from an immutable snapshot."""
        data = {
            name: copy_if_mutable(getattr(snapshot, name))
            for name in self._shared_field_names
        }
        return self._state_cls(**data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(state={reprlib.repr(self._state)})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.id})"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_MUTABLE_ABCS = (
    MutableSequence,
    MutableMapping,
    MutableSet,
)  # bytearray is a MutableSequence


def _generic_args_of_aggregate(cls: type) -> tuple[Any, ...] | None:
    """Return the (TId, M, S) arguments from `Aggregate[...]` in cls's own bases."""
    for base in cls.__dict__.get("__orig_bases__", ()):
        if get_origin(base) is Aggregate:
            args = get_args(base)
            if len(args) == 3:
                return args
    return None


def _bind_types(
    cls: type[Aggregate[Any, Any, Any]], snapshot_cls: Any, state_cls: Any
) -> None:
    """Validate the state/snapshot pair once and cache what the instances need."""
    owner = cls.__qualname__
    snapshot_cls = get_origin(snapshot_cls) or snapshot_cls
    state_cls = get_origin(state_cls) or state_cls

    for label, klass, base in (
        ("state", state_cls, AggregateState),
        ("snapshot", snapshot_cls, AggregateSnapshot),
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
        if name not in snapshot_names and f.default is attrs.NOTHING
    )
    if unfillable:
        raise TypeError(
            f"{owner}: {state_cls.__name__} requires fields not present on "
            f"{snapshot_cls.__name__} and with no default: {unfillable}"
        )

    # Guard against `dataclasses.field(...)` used instead of `attrs.field(...)`.
    # attrs silently stores the raw Field object as the default value.
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

    # pyrefly: ignore[no-access]
    cls._state_cls = state_cls
    # pyrefly: ignore[no-access]
    cls._snapshot_cls = snapshot_cls
    # Every snapshot field exists on the state (checked above), so this one
    # tuple serves both directions of the copy.
    cls._shared_field_names = tuple(snapshot_names)


# Todo The inner-entity tension. This links to the earlier decision to drop frozen from Entity.
#  If a snapshot holds inner entities and those are now mutable, the “snapshot must be immutable” requirement breaks.
#  You would need either frozen inner entities or nested snapshot classes.
#  Because of that, the check deliberately does not inspect dataclass instances, so a mutable inner Entity inside a snapshot is not detected.
def _ensure_deeply_immutable(path: str, value: object) -> None:
    """Reject standard mutable containers, also when nested in tuple/frozenset."""
    if isinstance(value, _MUTABLE_ABCS):
        raise TypeError(
            f"{path} holds a mutable {type(value).__name__}; use an immutable "
            "type (tuple, frozenset, Mapping view) or an attrs converter"
        )
    if isinstance(value, (tuple, frozenset)):
        for i, item in enumerate(value):
            _ensure_deeply_immutable(f"{path}[{i}]", item)
