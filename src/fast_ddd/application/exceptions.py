"""Errors raised by the application layer."""

from http import HTTPStatus

from fast_ddd.common import BaseError


class ApplicationError(BaseError):
    """Base class for failures in use-case orchestration.

    Raise a subclass when a use case cannot complete for a reason the caller
    should know about, for example a missing resource or a request that is not
    allowed in the current situation. Violations of business rules belong to
    `DomainError`, and failures in external systems to `InfrastructureError`.

    Each subclass can define its defaults as class attributes, so that every
    instance of that error type carries the same message, error code and HTTP
    status, which an HTTP layer can use to build a response. A message passed to
    the constructor overrides the class-level `message` for that one instance.

    Attributes:
        message (str): Human-readable description of the error. Defaults to
            `"Unexpected error"`. Read it from a caught exception with
            `exc.message`.
        error_code (str): Stable, machine-readable identifier for the error
            type, for clients to branch on. Defaults to `"APPLICATION_ERROR"`.
        status_code (HTTPStatus): HTTP status that best describes the error.
            Defaults to `HTTPStatus.BAD_REQUEST`.

    Examples:
        Define an error type with its own defaults:

        ```python
        class OrderNotFound(ApplicationError):
            message = "Order not found"
            error_code = "ORDER_NOT_FOUND"
            status_code = HTTPStatus.NOT_FOUND

        raise OrderNotFound()                  # uses the class-level message
        raise OrderNotFound("Order 42 not found")  # overrides it for this instance
        ```
    """

    message: str = "Unexpected error"  # default message
    error_code: str = "APPLICATION_ERROR"
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST
