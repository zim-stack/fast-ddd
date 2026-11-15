import pytest

from fast_ddd.common import BaseError
from fast_ddd.domain.exceptions import DomainError


class SampleError(DomainError):
    """Concrete subclass used only in these tests."""


class SampleMessageError(BaseError):
    """Concrete subclass with a class-level default message."""

    message = "sample default"


class TestBaseErrorInstantiation:
    def test_direct_instantiation_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="BaseError is abstract"):
            # pyrefly: ignore[direct-abstract-base-instantiation]
            BaseError("my error")

    def test_direct_instantiation_error_includes_attempted_message(self) -> None:
        with pytest.raises(TypeError, match="insufficient stock"):
            # pyrefly: ignore[direct-abstract-base-instantiation]
            BaseError("insufficient stock")

    def test_direct_instantiation_without_args_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="BaseError is abstract"):
            # pyrefly: ignore[direct-abstract-base-instantiation]
            BaseError()


class TestBaseErrorSubclasses:
    def test_subclass_uses_provided_message(self) -> None:
        error = SampleError("my error")

        assert error.message == "my error"
        assert str(error) == "my error"

    def test_subclass_uses_class_level_default_message(self) -> None:
        error = SampleMessageError()

        assert error.message == "sample default"
        assert str(error) == "sample default"

    def test_subclass_without_message_falls_back_to_class_name(self) -> None:
        error = SampleError()

        assert error.message == "SampleError occurred"

    def test_custom_message_overrides_class_level_default(self) -> None:
        error = SampleMessageError("custom")

        assert error.message == "custom"

    def test_domain_error_subclass_still_instantiates(self) -> None:
        error = SampleError("my error")

        assert isinstance(error, DomainError)
        assert isinstance(error, BaseError)
