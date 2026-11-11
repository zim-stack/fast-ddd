from abc import ABC
from collections.abc import Hashable
from typing import ClassVar, override

from fast_ddd.domain.entity import Entity, Snapshot, State
from fast_ddd.domain.event import DomainEvent


# Todo Support Indirect parametrization (isn’t supported).
#  class Tok(Base[Snap, State]), where Base is a generic intermediate that itself parametrizes Aggregate, fails with “must parametrize Aggregate directly”.
#  Resolving it needs a TypeVar substitution map.
class Aggregate[TId: Hashable, M: Snapshot, S: State](
    Entity[TId, M, S], ABC, abstract=True
):
    """Base class for aggregate roots.

    Type Parameters:
        TId: Type of the entity identifier.
        M: Snapshot type returned by `to_snapshot()`.
        S: Internal state type that holds internal mutable data.

    Intermediate abstract aggregates must be declared with `abstract=True`.
    """

    # Filled in by __init_subclass__; do not declare in subclasses.
    _nestable: ClassVar[bool] = (
        False  # aggregates reference each other by id, not by holding objects.
    )

    def __init__(self, snapshot: M) -> None:
        super().__init__(snapshot)
        self._domain_events: list[DomainEvent] = []

    def pull_domain_events(self) -> list[DomainEvent]:
        """Return all recorded domain events and clear the list."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

    @override
    def to_snapshot(self) -> M:
        self.validate_invariants()
        return super().to_snapshot()

    def record_event(self, event: DomainEvent) -> None:
        """Record domain event. Called inside domain methods."""
        self._domain_events.append(event)

    # -- Hooks --------------------------------------------------------------

    def validate_invariants(self) -> None:
        """Check aggregate invariants before a snapshot is taken.

        The default implementation does nothing. Subclasses override this
        method to enforce their own invariants.

        Raises:
            Exception: Subclasses should raise when an invariant is violated.
                Use the specific exception type your domain defines.
        """
        pass
