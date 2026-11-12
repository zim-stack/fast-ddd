from abc import ABC

from fast_ddd.common import BaseError


class DomainError(BaseError, ABC):
    """Abstract root of all domain errors.

    Catch this type to handle any error raised by the domain layer in one place.

    Raise one of its subclasses instead of this class directly.
    """

    def __init__(self, message: str | None = None) -> None:
        """
        Args:
            message: Custom message for this instance. See BaseError.
        """
        if type(self) is DomainError:
            hint = f" (attempted message: {message!r})" if message is not None else ""
            msg = f"DomainError is abstract; instantiate a subclass instead{hint}."
            raise TypeError(msg)
        super().__init__(message)


class DomainValidationError(DomainError):
    """Invalid data attempting to enter the domain.

    Raised when input fails validation, before any business rule runs.

    Subclass it for each specific validation failure, or raise directly for generic cases.
    """


class BusinessRuleViolationError(DomainError):
    """Expected, recoverable domain rule violation.

    Raised when a command breaks a business rule. The caller caused it through
    a valid but disallowed request, so it can be handled as a normal outcome,
    for example by returning a message to the user.

    Subclass it for specific business rule violations or raise directly for generic cases.
    """


class InvariantViolationError(DomainError):
    """Unexpected internal consistency error.

    Raised when the domain model reaches an impossible state.
    This points to a bug or corrupted state, not to bad input from the caller.
    Let it propagate and investigate the cause.

    Usually raised directly without subclassing.
    """
