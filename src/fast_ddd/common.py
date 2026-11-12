from abc import ABC
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class BaseEvent:
    """Base class for domain events.

    Instances are immutable. Every event gets a unique identifier and a
    UTC timestamp automatically, so subclasses only add their own fields.

    Attributes:
        event_id: Unique identifier for this event. Generated with
            ``uuid4()`` when not provided.
        occurred_at: When the event occurred, in UTC. Set to the current
            time when not provided.
    """

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BaseError(Exception, ABC):
    """Base class for all DDD exceptions.

    Use one of the concrete subclasses of the following, rather than this class directly:

    - `DomainError` for violations of business rules.
    - `ApplicationError` for failures in use-case orchestration.
    - `InfrastructureError` for failures in external systems.

    Subclasses can set a class-level `message` attribute to define
    a default message for every instance of that exception type.

    Attributes:
        message (str): Human-readable description of the error. Read it
            from any caught exception with `exc.message`. It comes from the
            `message` argument passed to the constructor, or from a
            `message` class attribute on a subclass. If neither is set,
            it defaults to `"<ClassName> occurred"`.
    """

    def __init__(self, message: str | None = None):
        """
        Create the error.

        Args:
            message: Custom message for this instance.

        Raises:
            TypeError: If `BaseError` itself is instantiated.
        """
        if type(self) is BaseError:
            hint = f" (attempted message: {message!r})" if message else ""
            msg = f"BaseError is abstract; instantiate a subclass instead{hint}."
            raise TypeError(msg)
        # Use custom message if provided; otherwise use class-level default
        msg = message or getattr(self, "message", f"{self.__class__.__name__} occurred")
        self.message = msg
        super().__init__(msg)
