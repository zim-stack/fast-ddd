import pytest

from fast_ddd.common import BaseError
from fast_ddd.domain.exceptions import DomainError


class SampleError(DomainError):
    """Concrete subclass used only in these tests."""


# ---------------------------------------------------------------------------
# DomainError
# ---------------------------------------------------------------------------


class TestDomainErrorInstantiation:
    def test_direct_instantiation_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="DomainError is abstract"):
            # pyrefly: ignore[direct-abstract-base-instantiation]
            DomainError("my error")

    def test_direct_instantiation_error_includes_attempted_message(self) -> None:
        with pytest.raises(TypeError, match="insufficient stock"):
            # pyrefly: ignore[direct-abstract-base-instantiation]
            DomainError("insufficient stock")

    def test_direct_instantiation_without_args_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="DomainError is abstract"):
            # pyrefly: ignore[direct-abstract-base-instantiation]
            DomainError()


class TestDomainErrorSubclasses:
    def test_subclass_can_be_instantiated(self) -> None:
        error = SampleError("my error")

        assert isinstance(error, DomainError)

    def test_subclass_forwards_arguments_to_base_class(self) -> None:
        error = SampleError("my error")

        assert str(error) == "my error"

    def test_subclass_is_a_base_error(self) -> None:
        error = SampleError("my error")

        assert isinstance(error, BaseError)

    def test_subclass_can_be_raised_and_caught_as_domain_error(self) -> None:
        with pytest.raises(DomainError) as exc_info:
            raise SampleError("my error")

        assert isinstance(exc_info.value, SampleError)

    def test_guard_does_not_block_subclass_of_subclass(self) -> None:
        class _NestedError(SampleError):
            pass

        error = _NestedError("nested")

        assert isinstance(error, DomainError)
        assert str(error) == "nested"
