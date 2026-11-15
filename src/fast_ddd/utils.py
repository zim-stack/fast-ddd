import copy
from decimal import Decimal
from uuid import UUID


def copy_if_mutable[T](value: T) -> T:
    """Conditionally deep copy object if it is mutable, or return original otherwise."""
    skip_copy = (
        int,
        float,
        complex,
        bool,
        str,
        bytes,
        type(None),
        UUID,
        Decimal,
        frozenset,
    )
    return value if isinstance(value, skip_copy) else copy.deepcopy(value)
