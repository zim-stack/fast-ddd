"""Events raised by the application layer."""

from dataclasses import dataclass

from fast_ddd.common import BaseEvent


@dataclass(frozen=True, kw_only=True)
class ApplicationEvent(BaseEvent):
    """Base class for events that originate in the application layer.

    Use it for facts about use-case orchestration, such as a command having been
    handled, as opposed to domain events, which aggregates record when their own
    state changes. Like every event it is immutable, and it gets a unique
    `event_id` and a UTC `occurred_at` timestamp automatically, so subclasses
    only add their own fields.

    Declare subclasses with `@dataclass(frozen=True, kw_only=True)`. A frozen
    dataclass cannot inherit from a non-frozen one, and `kw_only=True` lets you
    add required fields after the inherited defaults.

    Attributes:
        event_id: Unique identifier for this event. Generated with `uuid4()`
            when not provided.
        occurred_at: When the event occurred, in UTC. Set to the current time
            when not provided.

    Examples:
        ```python
        @dataclass(frozen=True, kw_only=True)
        class PaymentRequested(ApplicationEvent):
            order_id: UUID

        event = PaymentRequested(order_id=order_id)
        event.event_id      # generated
        event.occurred_at   # now, in UTC
        ```
    """
