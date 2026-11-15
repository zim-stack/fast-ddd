from abc import ABC
from collections.abc import Hashable
from typing import ClassVar, override

from fast_ddd.domain.entity import Entity, HasId
from fast_ddd.domain.events import DomainEvent


class Aggregate[TId: Hashable, M: HasId, S: HasId](
    Entity[TId, M, S], ABC, abstract=True
):
    """Base class for aggregate roots.

    An aggregate is an [`Entity`][fast_ddd.domain.entity.Entity] that is also a
    consistency boundary. On top of the entity behavior (identity, typed state,
    snapshots) it:

    - records domain events with `record_event()`, which callers collect with
      `pull_domain_events()`;
    - validates its invariants in `validate_invariants()` before every
      `to_snapshot()`, so an inconsistent aggregate is never persisted;
    - can own inner entities in its state, which are converted to snapshots and
      back automatically;
    - cannot be nested inside another aggregate. Aggregates reference each other
      by id.

    Bind the id, snapshot and state types by parametrizing it, directly or
    through a generic base that passes them on. The state and snapshot may be
    attrs classes or dataclasses, in any combination. They are validated once,
    when the subclass is defined. A subclass of a concrete aggregate inherits
    that binding, and each concrete aggregate is its own identity space.
    Intermediate bases that are never instantiated must be declared with
    `abstract=True`.

    Type Parameters:
        TId: Type of the aggregate identifier.
        M: Snapshot type returned by `to_snapshot()`. A frozen attrs class or
            frozen dataclass with an `id` field.
        S: Mutable state type, private to the aggregate as `_state`. An attrs
            class or dataclass with an `id` field.

    Note:
        A generic base may leave some or all of the types open, as long as it is
        declared with `abstract=True`. Each concrete subclass subscripts it with
        its own snapshot and state, and type checkers then see the concrete
        types inside the shared code.

    Examples:
        ```python
        class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
            def place(self) -> None:
                self._state.placed = True
                self.record_event(OrderPlaced(order_id=self.id))

            def validate_invariants(self) -> None:
                if self._state.placed and not self._state.lines:
                    raise ValueError("a placed order needs at least one line")
        ```

        Sharing behavior through a generic base:

        ```python
        class User[M: UserSnapshot, S: UserState](
            Aggregate[UUID, M, S], abstract=True
        ):
            def deactivate(self) -> None:
                self._state.is_active = False

        class Candidate(User[CandidateSnapshot, CandidateState]):
            pass

        class Recruiter(User[RecruiterSnapshot, RecruiterState]):
            pass
        ```
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

        Note:
            This method is a hook, that runs before a snapshot is instantiated.
            The default implementation does nothing. Subclasses override this
            method to enforce their own invariants.

        Raises:
            Exception: Subclasses should raise when an invariant is violated.
                Use the specific exception type your domain defines.
        """
